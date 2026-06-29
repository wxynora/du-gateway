import json
import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

try:
    import fcntl
except Exception:  # pragma: no cover - non-POSIX fallback for local tooling only.
    fcntl = None

from config import (
    DATA_DIR,
    STREAM_TIMEOUT_SECONDS,
    SUMITALK_CHAT_QUEUE_DB,
    SUMITALK_CHAT_QUEUE_STALE_SECONDS,
)
from storage import upstream_store
from services.upstream_policy import extract_upstream_error_detail
from utils.time_aware import now_beijing_iso


sumitalk_logger = logging.getLogger("sumitalk")

_SUMITALK_CHAT_JOB_DIR = DATA_DIR / "sumitalk_chat_jobs"
_SUMITALK_CHAT_JOB_LOCK = threading.RLock()
_SUMITALK_CHAT_JOB_STATE_LOCK_LOCAL = threading.local()
_SUMITALK_CHAT_JOB_TTL_SECONDS = 30 * 60
_SUMITALK_CHAT_JOB_STALE_SECONDS = max(60, int(STREAM_TIMEOUT_SECONDS or 300) + 60)
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
_ACTIVE_QUEUE_STATUSES = {"pending", "processing"}
_TERMINAL_JOB_STATUSES = {"done", "error", "cancelled"}
_QUEUE_HEARTBEAT_SECONDS = 20.0
_SUMITALK_CHAT_EVENT_LIMIT = max(10, int(os.environ.get("SUMITALK_CHAT_EVENT_LIMIT", "80") or "80"))
_SUMITALK_CHAT_EVENT_TEXT_LIMIT = max(80, int(os.environ.get("SUMITALK_CHAT_EVENT_TEXT_LIMIT", "1800") or "1800"))


@contextmanager
def _sumitalk_chat_job_state_lock():
    """Serialize JSON job-state read/modify/write across threads and worker processes."""
    with _SUMITALK_CHAT_JOB_LOCK:
        depth = int(getattr(_SUMITALK_CHAT_JOB_STATE_LOCK_LOCAL, "depth", 0) or 0)
        if depth > 0:
            _SUMITALK_CHAT_JOB_STATE_LOCK_LOCAL.depth = depth + 1
            try:
                yield
            finally:
                _SUMITALK_CHAT_JOB_STATE_LOCK_LOCAL.depth = depth
            return

        _SUMITALK_CHAT_JOB_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = _SUMITALK_CHAT_JOB_DIR / ".state.lock"
        fh = lock_path.open("a+", encoding="utf-8")
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            _SUMITALK_CHAT_JOB_STATE_LOCK_LOCAL.depth = 1
            yield
        finally:
            _SUMITALK_CHAT_JOB_STATE_LOCK_LOCAL.depth = 0
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            finally:
                fh.close()


@dataclass(frozen=True)
class EnqueueChatJobResult:
    enqueued: bool
    duplicate: bool
    job_id: str
    request_key: str


@dataclass(frozen=True)
class QueuedSumiTalkChatJob:
    id: int
    job_id: str
    request_key: str
    payload: dict
    attempts: int
    lease_token: str


def _connect() -> sqlite3.Connection:
    path = Path(SUMITALK_CHAT_QUEUE_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sumitalk_chat_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL UNIQUE,
                    request_key TEXT UNIQUE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    locked_at REAL,
                    lease_token TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sumitalk_chat_jobs_status_created
                    ON sumitalk_chat_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_sumitalk_chat_jobs_locked
                    ON sumitalk_chat_jobs(status, locked_at);
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(sumitalk_chat_jobs)").fetchall()
            }
            if "lease_token" not in columns:
                conn.execute("ALTER TABLE sumitalk_chat_jobs ADD COLUMN lease_token TEXT")
        _SCHEMA_READY = True


def valid_sumitalk_chat_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{32}", str(job_id or "").strip()))


def safe_sumitalk_client_request_id(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9_.:-]", "", text)[:120]


def sumitalk_chat_job_path(job_id: str) -> Path:
    return _SUMITALK_CHAT_JOB_DIR / f"{job_id}.json"


def make_sumitalk_request_key(client_request_id: str, window_id: str, reply_target: str) -> str:
    cid = safe_sumitalk_client_request_id(client_request_id)
    if not cid:
        return ""
    return "|".join(
        [
            cid,
            str(window_id or "").strip(),
            str(reply_target or "").strip(),
        ]
    )[:500]


def read_sumitalk_chat_job_state(job_id: str) -> dict | None:
    job_id = str(job_id or "").strip()
    if not valid_sumitalk_chat_job_id(job_id):
        return None
    path = sumitalk_chat_job_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_sumitalk_chat_job_state(state: dict) -> None:
    job_id = str((state or {}).get("id") or "").strip()
    if not valid_sumitalk_chat_job_id(job_id):
        raise ValueError("invalid job id")
    _SUMITALK_CHAT_JOB_DIR.mkdir(parents=True, exist_ok=True)
    path = sumitalk_chat_job_path(job_id)
    tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(state or {}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def patch_sumitalk_chat_job_state(job_id: str, patch: dict, *, protect_terminal: bool = False) -> bool:
    with _sumitalk_chat_job_state_lock():
        current = read_sumitalk_chat_job_state(job_id) or {
            "id": job_id,
            "created_ts": time.time(),
            "created_at": now_beijing_iso(),
        }
        if protect_terminal:
            current_status = str(current.get("status") or "").strip().lower()
            new_status = str((patch or {}).get("status") or "").strip().lower()
            if current_status in _TERMINAL_JOB_STATUSES and new_status != current_status:
                return False
        current.update(patch or {})
        current["updated_ts"] = time.time()
        current["updated_at"] = now_beijing_iso()
        write_sumitalk_chat_job_state(current)
        return True


def _short_chat_event_text(value, limit: int = _SUMITALK_CHAT_EVENT_TEXT_LIMIT) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    max_len = max(1, int(limit or _SUMITALK_CHAT_EVENT_TEXT_LIMIT))
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def _clean_chat_event_payload(payload: dict) -> dict:
    out: dict = {}
    for key, value in (payload or {}).items():
        clean_key = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(key or "").strip())[:80]
        if not clean_key:
            continue
        if isinstance(value, str):
            out[clean_key] = _short_chat_event_text(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            out[clean_key] = value
        elif isinstance(value, dict):
            out[clean_key] = _clean_chat_event_payload(value)
        elif isinstance(value, list):
            rows = []
            for item in value[:20]:
                if isinstance(item, dict):
                    rows.append(_clean_chat_event_payload(item))
                elif isinstance(item, str):
                    rows.append(_short_chat_event_text(item))
                elif isinstance(item, (int, float, bool)) or item is None:
                    rows.append(item)
                else:
                    rows.append(_short_chat_event_text(item))
            out[clean_key] = rows
        else:
            out[clean_key] = _short_chat_event_text(value)
    return out


def append_sumitalk_chat_job_event(job_id: str, kind: str, payload: dict | None = None) -> dict | None:
    job_id = str(job_id or "").strip()
    event_kind = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(kind or "").strip())[:80]
    if not valid_sumitalk_chat_job_id(job_id) or not event_kind:
        return None
    with _sumitalk_chat_job_state_lock():
        current = read_sumitalk_chat_job_state(job_id)
        if not isinstance(current, dict):
            return None
        status = str(current.get("status") or "").strip().lower()
        if status in _TERMINAL_JOB_STATUSES:
            return None
        try:
            seq = int(current.get("event_seq") or 0) + 1
        except Exception:
            seq = 1
        event = {
            "seq": seq,
            "event_id": uuid4().hex,
            "kind": event_kind,
            "created_at": now_beijing_iso(),
            **_clean_chat_event_payload(payload or {}),
        }
        events = current.get("events")
        if not isinstance(events, list):
            events = []
        events.append(event)
        current["events"] = events[-_SUMITALK_CHAT_EVENT_LIMIT:]
        current["event_seq"] = seq
        current["updated_ts"] = time.time()
        current["updated_at"] = now_beijing_iso()
        write_sumitalk_chat_job_state(current)
        return event


def cleanup_sumitalk_chat_jobs() -> None:
    try:
        if not _SUMITALK_CHAT_JOB_DIR.exists():
            _cleanup_sumitalk_chat_queue_rows()
            return
        cutoff = time.time() - max(60, int(_SUMITALK_CHAT_JOB_TTL_SECONDS))
        for path in _SUMITALK_CHAT_JOB_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
                updated_ts = float(data.get("updated_ts") or data.get("created_ts") or 0)
                if updated_ts and updated_ts < cutoff:
                    path.unlink(missing_ok=True)
            except Exception:
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass
    _cleanup_sumitalk_chat_queue_rows()


def _cleanup_sumitalk_chat_queue_rows() -> None:
    try:
        _ensure_schema()
        cutoff = time.time() - max(60, int(_SUMITALK_CHAT_JOB_TTL_SECONDS))
        with _connect() as conn:
            rows = conn.execute("SELECT id, job_id, status, updated_at FROM sumitalk_chat_jobs").fetchall()
            for row in rows:
                row_id = int(row["id"])
                job_id = str(row["job_id"] or "")
                status = str(row["status"] or "").strip().lower()
                updated_at = float(row["updated_at"] or 0)
                missing_state = valid_sumitalk_chat_job_id(job_id) and not sumitalk_chat_job_path(job_id).exists()
                if missing_state or (
                    status not in _ACTIVE_QUEUE_STATUSES and updated_at and updated_at < cutoff
                ):
                    conn.execute("DELETE FROM sumitalk_chat_jobs WHERE id=?", (row_id,))
    except Exception:
        pass


def _safe_job_log_value(value) -> str:
    text = str(value if value is not None else "").replace("\n", " ").replace("\r", " ").strip()
    return text[:160]


def _format_job_log_fields(fields: dict) -> str:
    parts = []
    for key, value in (fields or {}).items():
        k = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(key or "").strip())[:50]
        if not k:
            continue
        parts.append(f"{k}={_safe_job_log_value(value)}")
    return " ".join(parts)


def sumitalk_chat_job_elapsed_ms(state: dict | None) -> int:
    try:
        created_ts = float((state or {}).get("created_ts") or time.time())
        return max(0, int((time.time() - created_ts) * 1000))
    except Exception:
        return 0


def get_sumitalk_chat_queue_snapshot(job_id: str) -> dict | None:
    if not valid_sumitalk_chat_job_id(job_id):
        return None
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT status, attempts, locked_at, created_at, updated_at
            FROM sumitalk_chat_jobs
            WHERE job_id=?
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "status": str(row["status"] or "").strip().lower(),
        "attempts": int(row["attempts"] or 0),
        "locked_at": float(row["locked_at"] or 0),
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    }


def remove_sumitalk_chat_queue_job(job_id: str) -> None:
    if not valid_sumitalk_chat_job_id(job_id):
        return
    _ensure_schema()
    with _connect() as conn:
        conn.execute("DELETE FROM sumitalk_chat_jobs WHERE job_id=?", (job_id,))


def maybe_mark_sumitalk_chat_job_stale(job_id: str, state: dict | None = None) -> dict | None:
    state = state if isinstance(state, dict) else read_sumitalk_chat_job_state(job_id)
    if not isinstance(state, dict):
        return state
    status = str(state.get("status") or "").strip().lower()
    if status not in {"queued", "pending", "running"}:
        return state

    now = time.time()
    queue = get_sumitalk_chat_queue_snapshot(job_id)
    if queue:
        queue_status = str(queue.get("status") or "").strip().lower()
        touched_ts = float(queue.get("locked_at") or 0) if queue_status == "processing" else float(queue.get("updated_at") or 0)
        if touched_ts and now - touched_ts <= _SUMITALK_CHAT_JOB_STALE_SECONDS:
            return state
        reason = "SumiTalk 后台任务长时间没有更新，请重试"
        stage = "queue_processing_timeout" if queue_status == "processing" else "queue_wait_timeout"
    else:
        updated_ts = 0.0
        try:
            updated_ts = float(state.get("updated_ts") or state.get("created_ts") or 0)
        except Exception:
            updated_ts = 0.0
        if updated_ts and now - updated_ts <= _SUMITALK_CHAT_JOB_STALE_SECONDS:
            return state
        reason = "SumiTalk 后台队列没有接管任务，请重试"
        stage = "queue_missing"

    remove_sumitalk_chat_queue_job(job_id)
    elapsed_ms = sumitalk_chat_job_elapsed_ms(state)
    patch_sumitalk_chat_job_state(
        job_id,
        {
            "status": "error",
            "status_code": 504,
            "stage": stage,
            "stage_elapsed_ms": elapsed_ms,
            "stage_updated_at": now_beijing_iso(),
            "error": reason,
            "stale_detected_at": now_beijing_iso(),
        },
        protect_terminal=True,
    )
    sumitalk_logger.warning(
        "[SumiTalk] chat_job_marked_stale job_id=%s status=%s stage=%s elapsed_ms=%s queue_status=%s reason=%s",
        job_id,
        status,
        stage,
        elapsed_ms,
        str((queue or {}).get("status") or ""),
        reason,
    )
    return read_sumitalk_chat_job_state(job_id)


def is_sumitalk_chat_job_cancelled(job_id: str) -> bool:
    state = maybe_mark_sumitalk_chat_job_stale(job_id) or {}
    return str(state.get("status") or "").strip().lower() == "cancelled"


def cancel_sumitalk_chat_job(job_id: str, reason: str = "client_cancelled") -> bool:
    state = read_sumitalk_chat_job_state(job_id)
    if not state:
        return False
    status = str(state.get("status") or "").strip().lower()
    if status in _TERMINAL_JOB_STATUSES:
        return True
    elapsed_ms = sumitalk_chat_job_elapsed_ms(state)
    cancelled = patch_sumitalk_chat_job_state(
        job_id,
        {
            "status": "cancelled",
            "status_code": 499,
            "stage": "client_cancelled",
            "stage_elapsed_ms": elapsed_ms,
            "stage_updated_at": now_beijing_iso(),
            "error": (reason or "client_cancelled").strip()[:160] or "client_cancelled",
            "cancelled_at": now_beijing_iso(),
        },
        protect_terminal=True,
    )
    if cancelled:
        remove_sumitalk_chat_queue_job(job_id)
    return bool(cancelled)


def set_sumitalk_chat_job_stage(job_id: str, stage: str, **fields) -> None:
    stage_text = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(stage or "").strip())[:80] or "unknown"
    state = read_sumitalk_chat_job_state(job_id) or {}
    if str(state.get("status") or "").strip().lower() in _TERMINAL_JOB_STATUSES:
        return
    elapsed_ms = sumitalk_chat_job_elapsed_ms(state)
    patch_sumitalk_chat_job_state(
        job_id,
        {
            "stage": stage_text,
            "stage_elapsed_ms": elapsed_ms,
            "stage_updated_at": now_beijing_iso(),
        },
        protect_terminal=True,
    )
    sumitalk_logger.info(
        "[SumiTalk] chat_job_stage job_id=%s status=%s stage=%s elapsed_ms=%s %s",
        job_id,
        str(state.get("status") or "").strip() or "unknown",
        stage_text,
        elapsed_ms,
        _format_job_log_fields(fields),
    )


def find_sumitalk_chat_job_by_client_request_id(client_request_id: str, window_id: str, reply_target: str) -> dict | None:
    cid = safe_sumitalk_client_request_id(client_request_id)
    if not cid:
        return None
    request_key = make_sumitalk_request_key(cid, window_id, reply_target)
    queued_job_id = find_queued_sumitalk_chat_job_id(request_key=request_key)
    if queued_job_id:
        state = read_sumitalk_chat_job_state(queued_job_id)
        if state:
            return state
    if not _SUMITALK_CHAT_JOB_DIR.exists():
        return None
    best: dict | None = None
    best_ts = 0.0
    for path in _SUMITALK_CHAT_JOB_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            if not isinstance(data, dict):
                continue
            if safe_sumitalk_client_request_id(data.get("client_request_id")) != cid:
                continue
            if str(data.get("window_id") or "").strip() != str(window_id or "").strip():
                continue
            if str(data.get("reply_target") or "").strip() != str(reply_target or "").strip():
                continue
            status = str(data.get("status") or "").strip().lower()
            if status in {"error", "cancelled", "dead"}:
                continue
            job_id = str(data.get("id") or "").strip()
            if not valid_sumitalk_chat_job_id(job_id):
                continue
            ts = float(data.get("created_ts") or 0)
            if best is None or ts >= best_ts:
                best = data
                best_ts = ts
        except Exception:
            continue
    return best


def find_queued_sumitalk_chat_job_id(*, request_key: str = "", job_id: str = "") -> str:
    _ensure_schema()
    with _connect() as conn:
        row = None
        if job_id:
            row = conn.execute(
                "SELECT job_id FROM sumitalk_chat_jobs WHERE job_id=? AND status IN ('pending', 'processing')",
                (job_id,),
            ).fetchone()
        if row is None and request_key:
            row = conn.execute(
                "SELECT job_id FROM sumitalk_chat_jobs WHERE request_key=? AND status IN ('pending', 'processing')",
                (request_key,),
            ).fetchone()
    return str(row["job_id"] or "") if row else ""


def enqueue_sumitalk_chat_job(job_id: str, request_key: str, payload: dict) -> EnqueueChatJobResult:
    _ensure_schema()
    if not valid_sumitalk_chat_job_id(job_id):
        raise ValueError("invalid job id")
    now = time.time()
    clean_request_key = str(request_key or "").strip() or None
    payload_json = json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False, separators=(",", ":"))
    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO sumitalk_chat_jobs
                    (job_id, request_key, payload_json, status, attempts, locked_at, lease_token, created_at, updated_at, last_error)
                VALUES (?, ?, ?, 'pending', 0, NULL, NULL, ?, ?, NULL)
                """,
                (job_id, clean_request_key, payload_json, now, now),
            )
            return EnqueueChatJobResult(enqueued=True, duplicate=False, job_id=job_id, request_key=clean_request_key or "")
        except sqlite3.IntegrityError:
            existing = find_queued_sumitalk_chat_job_id(request_key=clean_request_key or "", job_id=job_id)
            if not existing:
                conn.execute(
                    """
                    DELETE FROM sumitalk_chat_jobs
                    WHERE (job_id=? OR request_key=?)
                      AND status NOT IN ('pending', 'processing')
                    """,
                    (job_id, clean_request_key),
                )
                conn.execute(
                    """
                    INSERT INTO sumitalk_chat_jobs
                        (job_id, request_key, payload_json, status, attempts, locked_at, lease_token, created_at, updated_at, last_error)
                    VALUES (?, ?, ?, 'pending', 0, NULL, NULL, ?, ?, NULL)
                    """,
                    (job_id, clean_request_key, payload_json, now, now),
                )
                return EnqueueChatJobResult(enqueued=True, duplicate=False, job_id=job_id, request_key=clean_request_key or "")
            return EnqueueChatJobResult(
                enqueued=False,
                duplicate=True,
                job_id=existing or job_id,
                request_key=clean_request_key or "",
            )


def claim_next_sumitalk_chat_job(
    *,
    stale_after_seconds: float | None = None,
) -> QueuedSumiTalkChatJob | None:
    _ensure_schema()
    _cleanup_sumitalk_chat_queue_rows()
    now = time.time()
    stale_after = max(float(stale_after_seconds or SUMITALK_CHAT_QUEUE_STALE_SECONDS or 300.0), 30.0)
    lease_token = uuid4().hex
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT id, job_id, request_key, payload_json, attempts
                FROM sumitalk_chat_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            attempts = int(row["attempts"] or 0) + 1
            conn.execute(
                """
                UPDATE sumitalk_chat_jobs
                SET status='processing', attempts=?, locked_at=?, lease_token=?, updated_at=?, last_error=NULL
                WHERE id=?
                """,
                (attempts, now, lease_token, now, int(row["id"])),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        sumitalk_logger.exception("[SumiTalk] chat_queue JSON 损坏 id=%s job_id=%s", row["id"], row["job_id"])
        fail_sumitalk_chat_queue_item(int(row["id"]), "invalid payload_json", lease_token=lease_token)
        return None
    if not isinstance(payload, dict):
        payload = {}
    return QueuedSumiTalkChatJob(
        id=int(row["id"]),
        job_id=str(row["job_id"] or ""),
        request_key=str(row["request_key"] or ""),
        payload=payload,
        attempts=attempts,
        lease_token=lease_token,
    )


def ack_sumitalk_chat_queue_item(queue_id: int, *, lease_token: str = "") -> bool:
    _ensure_schema()
    lease = str(lease_token or "").strip()
    with _connect() as conn:
        if lease:
            cur = conn.execute(
                "DELETE FROM sumitalk_chat_jobs WHERE id=? AND lease_token=?",
                (int(queue_id), lease),
            )
        else:
            cur = conn.execute("DELETE FROM sumitalk_chat_jobs WHERE id=?", (int(queue_id),))
    return int(cur.rowcount or 0) > 0


def heartbeat_sumitalk_chat_queue_item(queue_id: int, *, lease_token: str) -> bool:
    _ensure_schema()
    lease = str(lease_token or "").strip()
    if not lease:
        return False
    now = time.time()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE sumitalk_chat_jobs
            SET locked_at=?, updated_at=?
            WHERE id=? AND lease_token=? AND status='processing'
            """,
            (now, now, int(queue_id), lease),
        )
    return int(cur.rowcount or 0) > 0


def sumitalk_chat_queue_lease_active(queue_id: int, *, lease_token: str) -> bool:
    _ensure_schema()
    lease = str(lease_token or "").strip()
    if not lease:
        return False
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sumitalk_chat_jobs
            WHERE id=? AND lease_token=? AND status='processing'
            LIMIT 1
            """,
            (int(queue_id), lease),
        ).fetchone()
    return row is not None


def fail_sumitalk_chat_queue_item(
    queue_id: int,
    error: str,
    *,
    lease_token: str = "",
) -> bool:
    _ensure_schema()
    err = (error or "").strip()
    if len(err) > 1000:
        err = err[:1000]
    now = time.time()
    lease = str(lease_token or "").strip()
    with _connect() as conn:
        where = "id=?"
        params: list = [int(queue_id)]
        if lease:
            where += " AND lease_token=?"
            params.append(lease)
        row = conn.execute(
            f"SELECT job_id, attempts FROM sumitalk_chat_jobs WHERE {where}",
            tuple(params),
        ).fetchone()
        if row is None:
            return False
        conn.execute(f"DELETE FROM sumitalk_chat_jobs WHERE {where}", tuple(params))
        job_id = str(row["job_id"] or "")
    if valid_sumitalk_chat_job_id(job_id):
        patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "error",
                "status_code": 500,
                "stage": "queue_failed",
                "stage_updated_at": now_beijing_iso(),
                "error": err or "SumiTalk 后台任务失败",
            },
            protect_terminal=True,
        )
    return True


def sumitalk_chat_queue_stats() -> dict[str, int]:
    _ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM sumitalk_chat_jobs
            GROUP BY status
            """
        ).fetchall()
    return {str(r["status"]): int(r["n"] or 0) for r in rows}


def _extract_chat_completion_result(result) -> tuple[int, dict]:
    response = result
    status = 200
    if isinstance(result, tuple):
        response = result[0] if result else None
        for item in result[1:]:
            if isinstance(item, int):
                status = item
                break
    if hasattr(response, "status_code"):
        try:
            status = int(response.status_code)
        except Exception:
            pass
    data = None
    if hasattr(response, "get_json"):
        try:
            data = response.get_json(silent=True)
        except Exception:
            data = None
    if data is None and hasattr(response, "get_data"):
        try:
            text = response.get_data(as_text=True)
            data = json.loads(text) if text else {}
        except Exception:
            data = {"raw": response.get_data(as_text=True) if hasattr(response, "get_data") else ""}
    if not isinstance(data, dict):
        data = {"content": data}
    return status, data


def build_sumitalk_chat_job_payload(
    body: dict,
    *,
    reply_target: str,
    user_agent: str,
    force_last4: str,
    remote_addr: str,
) -> tuple[str, dict | None, EnqueueChatJobResult | None]:
    model = str(upstream_store.get_cached_active_model(refresh_if_missing=False) or "").strip()
    messages = (body or {}).get("messages") or []
    window_id = str((body or {}).get("window_id") or "").strip()
    reply_target = str(reply_target or "").strip()
    client_request_id = safe_sumitalk_client_request_id((body or {}).get("client_request_id"))
    if not model:
        return "", {"payload": {"ok": False, "error": "当前未设置全局模型"}, "status": 400}, None
    if not isinstance(messages, list) or not messages:
        return "", {"payload": {"ok": False, "error": "缺少 messages"}, "status": 400}, None
    if not window_id:
        return "", {"payload": {"ok": False, "error": "缺少 window_id"}, "status": 400}, None

    cleanup_sumitalk_chat_jobs()
    existing = find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
    if existing:
        existing_job_id = str(existing.get("id") or "").strip()
        existing = maybe_mark_sumitalk_chat_job_stale(existing_job_id, existing) or existing
        existing_status = str(existing.get("status") or "").strip().lower()
        if existing_status in {"error", "cancelled"}:
            existing = None
        else:
            sumitalk_logger.info(
                "chat_job_reused job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
                existing_job_id,
                client_request_id,
                window_id,
                reply_target,
                str(existing.get("status") or ""),
            )
            return existing_job_id, None, EnqueueChatJobResult(False, True, existing_job_id, "")

    chat_body = dict(body or {})
    chat_body["model"] = model
    chat_body["messages"] = messages
    chat_body["window_id"] = window_id
    chat_body["stream"] = False
    chat_body.pop("reply_target", None)
    job_id = uuid4().hex
    headers = {
        "Content-Type": "application/json",
        "User-Agent": user_agent or "SumiTalk MiniApp",
        "X-Force-Last4": str(force_last4 or (body or {}).get("force_last4") or "1"),
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": reply_target,
        "X-Window-Id": window_id,
        "X-SumiTalk-Job-Id": job_id,
    }
    request_key = make_sumitalk_request_key(client_request_id, window_id, reply_target)
    state = {
        "id": job_id,
        "ok": True,
        "status": "queued",
        "stage": "queued",
        "stage_elapsed_ms": 0,
        "created_ts": time.time(),
        "updated_ts": time.time(),
        "created_at": now_beijing_iso(),
        "updated_at": now_beijing_iso(),
        "client_request_id": client_request_id,
        "window_id": window_id,
        "reply_target": reply_target,
        "request_key": request_key,
    }
    payload = {
        "chat_body": chat_body,
        "headers": headers,
        "remote_addr": remote_addr or "127.0.0.1",
    }
    with _sumitalk_chat_job_state_lock():
        existing = find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
        if existing:
            existing_job_id = str(existing.get("id") or "").strip()
            existing = maybe_mark_sumitalk_chat_job_stale(existing_job_id, existing) or existing
            existing_status = str(existing.get("status") or "").strip().lower()
            if existing_status in {"error", "cancelled"}:
                existing = None
        if existing:
            sumitalk_logger.info(
                "chat_job_reused_after_race job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
                existing_job_id,
                client_request_id,
                window_id,
                reply_target,
                str(existing.get("status") or ""),
            )
            return existing_job_id, None, EnqueueChatJobResult(False, True, existing_job_id, request_key)
        write_sumitalk_chat_job_state(state)
        try:
            result = enqueue_sumitalk_chat_job(job_id, request_key, payload)
        except Exception:
            try:
                sumitalk_chat_job_path(job_id).unlink(missing_ok=True)
            except Exception:
                pass
            raise
        if result.duplicate and result.job_id != job_id:
            try:
                sumitalk_chat_job_path(job_id).unlink(missing_ok=True)
            except Exception:
                pass
            return result.job_id, None, result
    sumitalk_logger.info(
        "[SumiTalk] chat_job_enqueued job_id=%s window_id=%s target=%s messages=%s client_request_id=%s request_key=%s",
        job_id,
        window_id,
        reply_target,
        len(messages),
        client_request_id,
        request_key,
    )
    return job_id, None, result


def run_sumitalk_chat_job(
    app,
    job_id: str,
    payload: dict,
    *,
    queue_id: int | None = None,
    lease_token: str = "",
) -> str:
    chat_body = (payload or {}).get("chat_body") if isinstance(payload, dict) else {}
    headers = (payload or {}).get("headers") if isinstance(payload, dict) else {}
    remote_addr = str((payload or {}).get("remote_addr") or "127.0.0.1")
    if not isinstance(chat_body, dict) or not isinstance(headers, dict):
        raise ValueError("invalid sumitalk chat job payload")

    def _lease_alive() -> bool:
        if queue_id is None:
            return True
        return sumitalk_chat_queue_lease_active(int(queue_id), lease_token=lease_token)

    def _stage(stage: str, **fields) -> None:
        set_sumitalk_chat_job_stage(job_id, stage, **fields)
        if queue_id is not None:
            heartbeat_sumitalk_chat_queue_item(int(queue_id), lease_token=lease_token)

    state = read_sumitalk_chat_job_state(job_id) or {}
    status = str(state.get("status") or "").strip().lower()
    if status in _TERMINAL_JOB_STATUSES:
        return status
    if not _lease_alive():
        return "stale_lease"
    if not patch_sumitalk_chat_job_state(
        job_id,
        {
            "status": "running",
            "worker_pid": os.getpid(),
            "worker_started_at": now_beijing_iso(),
        },
        protect_terminal=True,
    ):
        state = read_sumitalk_chat_job_state(job_id) or {}
        return str(state.get("status") or "terminal").strip().lower() or "terminal"
    _stage(
        "worker_started",
        model=chat_body.get("model") or "",
        messages=len(chat_body.get("messages") or []) if isinstance(chat_body.get("messages"), list) else 0,
        window_id=chat_body.get("window_id") or "",
    )
    try:
        if is_sumitalk_chat_job_cancelled(job_id):
            _stage("cancelled_before_gateway_call")
            return "cancelled"
        from routes.chat import chat_completions

        environ_base = {"REMOTE_ADDR": remote_addr or "127.0.0.1"}
        _stage("gateway_call_start")
        call_started = time.time()
        heartbeat_stop = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        if queue_id is not None and str(lease_token or "").strip():
            def _heartbeat_loop() -> None:
                while not heartbeat_stop.wait(_QUEUE_HEARTBEAT_SECONDS):
                    if not heartbeat_sumitalk_chat_queue_item(int(queue_id), lease_token=lease_token):
                        break

            heartbeat_thread = threading.Thread(target=_heartbeat_loop, name=f"sumitalk-chat-heartbeat-{job_id[:8]}", daemon=True)
            heartbeat_thread.start()
        try:
            with app.test_request_context(
                "/v1/chat/completions",
                method="POST",
                json=chat_body,
                headers=headers,
                environ_base=environ_base,
            ):
                result = chat_completions()
                status_code, data = _extract_chat_completion_result(result)
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=1.0)
        gateway_ms = int((time.time() - call_started) * 1000)
        _stage(
            "gateway_call_returned",
            status_code=status_code,
            gateway_ms=gateway_ms,
            response_keys=",".join(list(data.keys())[:8]) if isinstance(data, dict) else "",
        )
        if not _lease_alive():
            _stage("lease_lost_after_gateway_return")
            return "stale_lease"
        if is_sumitalk_chat_job_cancelled(job_id):
            _stage("cancelled_after_gateway_return")
            return "cancelled"
        if status_code >= 400:
            err = extract_upstream_error_detail(data, status_code) or f"HTTP {status_code}"
            _stage("gateway_call_error", status_code=status_code, error=err)
            patch_sumitalk_chat_job_state(
                job_id,
                {
                    "status": "error",
                    "status_code": status_code,
                    "error": str(err),
                    "response": data,
                },
                protect_terminal=True,
            )
            return "error"
        _stage("reply_ready", status_code=status_code)
        if not patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "done",
                "status_code": status_code,
                "response": data,
            },
            protect_terminal=True,
        ):
            state = read_sumitalk_chat_job_state(job_id) or {}
            return str(state.get("status") or "terminal").strip().lower() or "terminal"
        return "done"
    except Exception as e:
        sumitalk_logger.exception("[SumiTalk] chat_job_failed job_id=%s", job_id)
        try:
            _stage("worker_exception", error=e)
        except Exception:
            pass
        if is_sumitalk_chat_job_cancelled(job_id):
            return "cancelled"
        raise
