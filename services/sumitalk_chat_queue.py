import codecs
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
    SUMITALK_CHAT_NATIVE_STREAM_ENABLED,
    SUMITALK_CHAT_QUEUE_DB,
    SUMITALK_CHAT_QUEUE_STALE_SECONDS,
)
from storage import upstream_store
from services.game_tool_runtime import normalize_game_id
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
_SUMITALK_CHAT_FINAL_TEXT_LIMIT = max(
    _SUMITALK_CHAT_EVENT_TEXT_LIMIT,
    int(os.environ.get("SUMITALK_CHAT_FINAL_TEXT_LIMIT", "500000") or "500000"),
)
_TERMINAL_EVENT_KINDS = {"assistant_final", "run_error", "run_cancelled"}
_TERMINAL_EVENT_STATUS = {
    "assistant_final": "done",
    "run_error": "error",
    "run_cancelled": "cancelled",
}
_TERMINAL_STATUS_EVENT = {value: key for key, value in _TERMINAL_EVENT_STATUS.items()}
_SUMITALK_NONSTREAM_SHARED_GAME_IDS = frozenset({"private_board", "wenyou", "captivity_simulator"})


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
                CREATE TABLE IF NOT EXISTS sumitalk_chat_run_events (
                    job_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    terminal INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(job_id, seq)
                );
                CREATE INDEX IF NOT EXISTS idx_sumitalk_chat_run_events_job_seq
                    ON sumitalk_chat_run_events(job_id, seq);
                CREATE INDEX IF NOT EXISTS idx_sumitalk_chat_run_events_created
                    ON sumitalk_chat_run_events(created_ts);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sumitalk_chat_run_events_one_terminal
                    ON sumitalk_chat_run_events(job_id)
                    WHERE terminal = 1;
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


def _short_chat_event_text(
    value,
    limit: int = _SUMITALK_CHAT_EVENT_TEXT_LIMIT,
    *,
    preserve_whitespace: bool = False,
) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not preserve_whitespace:
        text = re.sub(r"\n{4,}", "\n\n\n", text.strip())
    max_len = max(1, int(limit or _SUMITALK_CHAT_EVENT_TEXT_LIMIT))
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def _clean_chat_event_payload(
    payload: dict,
    *,
    text_limit: int = _SUMITALK_CHAT_EVENT_TEXT_LIMIT,
    preserve_whitespace: bool = False,
) -> dict:
    out: dict = {}
    for key, value in (payload or {}).items():
        clean_key = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(key or "").strip())[:80]
        if not clean_key:
            continue
        if isinstance(value, str):
            out[clean_key] = _short_chat_event_text(
                value,
                text_limit,
                preserve_whitespace=preserve_whitespace,
            )
        elif isinstance(value, (int, float, bool)) or value is None:
            out[clean_key] = value
        elif isinstance(value, dict):
            out[clean_key] = _clean_chat_event_payload(
                value,
                text_limit=text_limit,
                preserve_whitespace=preserve_whitespace,
            )
        elif isinstance(value, list):
            rows = []
            for item in value[:20]:
                if isinstance(item, dict):
                    rows.append(
                        _clean_chat_event_payload(
                            item,
                            text_limit=text_limit,
                            preserve_whitespace=preserve_whitespace,
                        )
                    )
                elif isinstance(item, str):
                    rows.append(
                        _short_chat_event_text(
                            item,
                            text_limit,
                            preserve_whitespace=preserve_whitespace,
                        )
                    )
                elif isinstance(item, (int, float, bool)) or item is None:
                    rows.append(item)
                else:
                    rows.append(
                        _short_chat_event_text(
                            item,
                            text_limit,
                            preserve_whitespace=preserve_whitespace,
                        )
                    )
            out[clean_key] = rows
        else:
            out[clean_key] = _short_chat_event_text(
                value,
                text_limit,
                preserve_whitespace=preserve_whitespace,
            )
    return out


def _decode_sumitalk_chat_event_json(value) -> dict | None:
    try:
        event = json.loads(str(value or "{}"))
    except Exception:
        return None
    return event if isinstance(event, dict) else None


def _read_durable_sumitalk_chat_events(job_id: str, after_seq: int, limit: int) -> list[dict]:
    _ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_json
            FROM sumitalk_chat_run_events
            WHERE job_id=? AND seq>?
            ORDER BY seq ASC
            LIMIT ?
            """,
            (job_id, max(0, int(after_seq or 0)), max(1, int(limit or 1))),
        ).fetchall()
    events = []
    for row in rows:
        event = _decode_sumitalk_chat_event_json(row["event_json"])
        if event is not None:
            events.append(event)
    return events


def list_sumitalk_chat_job_events(job_id: str, *, after_seq: int = 0, limit: int = 100) -> list[dict]:
    job_id = str(job_id or "").strip()
    if not valid_sumitalk_chat_job_id(job_id):
        return []
    after = max(0, int(after_seq or 0))
    cap = max(1, min(500, int(limit or 100)))
    durable = _read_durable_sumitalk_chat_events(job_id, after, cap)
    by_seq: dict[int, dict] = {}
    state = read_sumitalk_chat_job_state(job_id) or {}
    for event in state.get("events") or []:
        if not isinstance(event, dict):
            continue
        try:
            seq = int(event.get("seq") or 0)
        except Exception:
            continue
        if seq > after:
            by_seq[seq] = event
    for event in durable:
        try:
            seq = int(event.get("seq") or 0)
        except Exception:
            continue
        if seq > after:
            by_seq[seq] = event
    return [by_seq[seq] for seq in sorted(by_seq)[:cap]]


def latest_sumitalk_chat_job_event_seq(job_id: str) -> int:
    job_id = str(job_id or "").strip()
    if not valid_sumitalk_chat_job_id(job_id):
        return 0
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS seq FROM sumitalk_chat_run_events WHERE job_id=?",
            (job_id,),
        ).fetchone()
    durable_seq = int((row or {})["seq"] or 0) if row else 0
    try:
        state_seq = int((read_sumitalk_chat_job_state(job_id) or {}).get("event_seq") or 0)
    except Exception:
        state_seq = 0
    return max(durable_seq, state_seq)


def get_sumitalk_chat_terminal_event(job_id: str) -> dict | None:
    job_id = str(job_id or "").strip()
    if not valid_sumitalk_chat_job_id(job_id):
        return None
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT event_json
            FROM sumitalk_chat_run_events
            WHERE job_id=? AND terminal=1
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    return _decode_sumitalk_chat_event_json(row["event_json"]) if row else None


def _latest_sumitalk_chat_assistant_part(job_id: str) -> tuple[str, int] | None:
    if not valid_sumitalk_chat_job_id(job_id):
        return None
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT event_json
            FROM sumitalk_chat_run_events
            WHERE job_id=?
              AND kind IN ('assistant_text_started', 'assistant_delta', 'assistant_text_finished')
            ORDER BY seq DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    event = _decode_sumitalk_chat_event_json(row["event_json"]) if row else None
    if not event:
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    part_id = str(event.get("part_id") or payload.get("part_id") or "").strip()
    if not part_id:
        return None
    try:
        round_no = max(0, int(event.get("round", payload.get("round", 0)) or 0))
    except Exception:
        round_no = 0
    return part_id, round_no


def _append_sumitalk_chat_job_event_record(
    job_id: str,
    event_kind: str,
    payload: dict,
    current: dict,
) -> dict | None:
    terminal = event_kind in _TERMINAL_EVENT_KINDS
    text_limit = _SUMITALK_CHAT_FINAL_TEXT_LIMIT if terminal else _SUMITALK_CHAT_EVENT_TEXT_LIMIT
    preserve_whitespace = terminal or event_kind.endswith("_delta")
    clean_payload = _clean_chat_event_payload(
        payload or {},
        text_limit=text_limit,
        preserve_whitespace=preserve_whitespace,
    )
    created_ts = time.time()
    created_at = now_beijing_iso()
    try:
        minimum_seq = max(0, int(current.get("event_seq") or 0))
    except Exception:
        minimum_seq = 0

    _ensure_schema()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            terminal_row = conn.execute(
                """
                SELECT kind, event_json
                FROM sumitalk_chat_run_events
                WHERE job_id=? AND terminal=1
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if terminal_row is not None:
                conn.execute("COMMIT")
                if terminal and str(terminal_row["kind"] or "") == event_kind:
                    return _decode_sumitalk_chat_event_json(terminal_row["event_json"])
                return None
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS seq FROM sumitalk_chat_run_events WHERE job_id=?",
                (job_id,),
            ).fetchone()
            seq = max(minimum_seq, int((row or {})["seq"] or 0) if row else 0) + 1
            event_id = f"{job_id}:{seq}"
            event = {
                **clean_payload,
                "seq": seq,
                "event_id": event_id,
                "run_id": job_id,
                "job_id": job_id,
                "kind": event_kind,
                "created_at": created_at,
                "created_ts": created_ts,
                "payload": clean_payload,
            }
            conn.execute(
                """
                INSERT INTO sumitalk_chat_run_events
                    (job_id, seq, event_id, kind, event_json, created_at, created_ts, terminal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    seq,
                    event_id,
                    event_kind,
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")),
                    created_at,
                    created_ts,
                    1 if terminal else 0,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    if event_kind.endswith("_delta"):
        return event
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


def append_sumitalk_chat_job_event(job_id: str, kind: str, payload: dict | None = None) -> dict | None:
    job_id = str(job_id or "").strip()
    event_kind = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(kind or "").strip())[:80]
    if not valid_sumitalk_chat_job_id(job_id) or not event_kind:
        return None
    if event_kind.endswith("_delta"):
        current = read_sumitalk_chat_job_state(job_id)
        if not isinstance(current, dict):
            return None
        if str(current.get("status") or "").strip().lower() in _TERMINAL_JOB_STATUSES:
            return None
        return _append_sumitalk_chat_job_event_record(job_id, event_kind, payload or {}, current)
    with _sumitalk_chat_job_state_lock():
        current = read_sumitalk_chat_job_state(job_id)
        if not isinstance(current, dict):
            return None
        status = str(current.get("status") or "").strip().lower()
        if status in _TERMINAL_JOB_STATUSES and event_kind not in _TERMINAL_EVENT_KINDS:
            return None
        return _append_sumitalk_chat_job_event_record(job_id, event_kind, payload or {}, current)


def finalize_sumitalk_chat_job(
    job_id: str,
    status: str,
    *,
    state_patch: dict | None = None,
    event_payload: dict | None = None,
) -> bool:
    terminal_status = str(status or "").strip().lower()
    event_kind = _TERMINAL_STATUS_EVENT.get(terminal_status)
    if not valid_sumitalk_chat_job_id(job_id) or not event_kind:
        return False
    with _sumitalk_chat_job_state_lock():
        current = read_sumitalk_chat_job_state(job_id)
        if not isinstance(current, dict):
            return False
        current_status = str(current.get("status") or "").strip().lower()
        if current_status in _TERMINAL_JOB_STATUSES and current_status != terminal_status:
            return False
        existing_terminal = get_sumitalk_chat_terminal_event(job_id)
        if existing_terminal:
            existing_status = _TERMINAL_EVENT_STATUS.get(str(existing_terminal.get("kind") or ""))
            if existing_status != terminal_status:
                return False
        else:
            event = _append_sumitalk_chat_job_event_record(
                job_id,
                event_kind,
                event_payload or {},
                current,
            )
            if event is None:
                return False
            current = read_sumitalk_chat_job_state(job_id) or current
        current.update(state_patch or {})
        current["status"] = terminal_status
        current["updated_ts"] = time.time()
        current["updated_at"] = now_beijing_iso()
        write_sumitalk_chat_job_state(current)
        return True


def reconcile_sumitalk_chat_job_terminal_state(job_id: str, state: dict | None = None) -> dict | None:
    current = state if isinstance(state, dict) else read_sumitalk_chat_job_state(job_id)
    if not isinstance(current, dict):
        return current
    terminal_event = get_sumitalk_chat_terminal_event(job_id)
    if not terminal_event:
        return current
    terminal_status = _TERMINAL_EVENT_STATUS.get(str(terminal_event.get("kind") or ""))
    if not terminal_status:
        return current
    current_status = str(current.get("status") or "").strip().lower()
    if current_status == terminal_status:
        return current
    if current_status in _TERMINAL_JOB_STATUSES:
        sumitalk_logger.error(
            "[SumiTalk] terminal_state_conflict job_id=%s json_status=%s event_status=%s",
            job_id,
            current_status,
            terminal_status,
        )
        return current

    default_status_code = 200 if terminal_status == "done" else 499 if terminal_status == "cancelled" else 500
    status_code = int(terminal_event.get("status_code") or default_status_code)
    patch = {
        "status": terminal_status,
        "status_code": status_code,
        "stage": "terminal_event_recovered",
        "stage_updated_at": now_beijing_iso(),
    }
    if terminal_status == "done" and not isinstance(current.get("response"), dict):
        patch["response"] = {
            "id": f"chatcmpl-{job_id}",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": str(terminal_event.get("role") or "assistant"),
                        "content": str(terminal_event.get("text") or ""),
                    },
                    "finish_reason": str(terminal_event.get("finish_reason") or "stop"),
                }
            ],
        }
    elif terminal_status != "done":
        patch["error"] = str(
            terminal_event.get("error")
            or terminal_event.get("reason")
            or ("已取消发送" if terminal_status == "cancelled" else "渡回复失败")
        )
    patch_sumitalk_chat_job_state(job_id, patch, protect_terminal=True)
    return read_sumitalk_chat_job_state(job_id) or current


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
            conn.execute(
                "DELETE FROM sumitalk_chat_run_events WHERE created_ts<?",
                (cutoff,),
            )
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
    state = reconcile_sumitalk_chat_job_terminal_state(job_id, state) or state
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
    finalize_sumitalk_chat_job(
        job_id,
        "error",
        state_patch={
            "status_code": 504,
            "stage": stage,
            "stage_elapsed_ms": elapsed_ms,
            "stage_updated_at": now_beijing_iso(),
            "error": reason,
            "stale_detected_at": now_beijing_iso(),
        },
        event_payload={
            "error": reason,
            "stage": stage,
            "status_code": 504,
        },
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
    state = reconcile_sumitalk_chat_job_terminal_state(job_id, state) or state
    status = str(state.get("status") or "").strip().lower()
    if status in _TERMINAL_JOB_STATUSES:
        return True
    elapsed_ms = sumitalk_chat_job_elapsed_ms(state)
    cancel_reason = (reason or "client_cancelled").strip()[:160] or "client_cancelled"
    cancelled = finalize_sumitalk_chat_job(
        job_id,
        "cancelled",
        state_patch={
            "status_code": 499,
            "stage": "client_cancelled",
            "stage_elapsed_ms": elapsed_ms,
            "stage_updated_at": now_beijing_iso(),
            "error": cancel_reason,
            "cancelled_at": now_beijing_iso(),
        },
        event_payload={
            "reason": cancel_reason,
            "error": cancel_reason,
            "status_code": 499,
        },
    )
    if cancelled:
        remove_sumitalk_chat_queue_job(job_id)
    return bool(cancelled)


def set_sumitalk_chat_job_stage(job_id: str, stage: str, **fields) -> None:
    stage_text = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(stage or "").strip())[:80] or "unknown"
    state = read_sumitalk_chat_job_state(job_id) or {}
    state = reconcile_sumitalk_chat_job_terminal_state(job_id, state) or state
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
        error_text = err or "SumiTalk 后台任务失败"
        finalize_sumitalk_chat_job(
            job_id,
            "error",
            state_patch={
                "status_code": 500,
                "stage": "queue_failed",
                "stage_updated_at": now_beijing_iso(),
                "error": error_text,
            },
            event_payload={
                "error": error_text,
                "stage": "queue_failed",
                "status_code": 500,
            },
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


def is_sumitalk_native_android_user_agent(user_agent: str) -> bool:
    return "sumitalk native android" in str(user_agent or "").strip().lower()


def should_stream_sumitalk_chat_job(user_agent: str, game_id: str = "") -> bool:
    normalized_game_id = normalize_game_id(game_id)
    return bool(
        SUMITALK_CHAT_NATIVE_STREAM_ENABLED
        and is_sumitalk_native_android_user_agent(user_agent)
        and normalized_game_id not in _SUMITALK_NONSTREAM_SHARED_GAME_IDS
    )


def _chat_message_text(message: dict | None) -> str:
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _chat_event_text_chunks(text: str):
    value = str(text or "")
    size = max(1, _SUMITALK_CHAT_EVENT_TEXT_LIMIT - 16)
    for start in range(0, len(value), size):
        yield value[start : start + size]


def _chat_completion_message(data: dict) -> tuple[dict, str]:
    choices = (data or {}).get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    return message, str(choice.get("finish_reason") or "")


def _iter_sse_data(response):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buffer = ""
    data_lines: list[str] = []

    def _consume_line(line: str):
        nonlocal data_lines
        line = line.rstrip("\r")
        if not line:
            if data_lines:
                data = "\n".join(data_lines)
                data_lines = []
                return data
            return None
        if line.startswith(":"):
            return None
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
        return None

    iterable = getattr(response, "response", response)
    for chunk in iterable:
        if chunk is None:
            continue
        if isinstance(chunk, str):
            text = chunk
        else:
            text = decoder.decode(bytes(chunk), final=False)
        buffer += text
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            data = _consume_line(line)
            if data is not None:
                yield data
    buffer += decoder.decode(b"", final=True)
    if buffer:
        data = _consume_line(buffer)
        if data is not None:
            yield data
    if data_lines:
        yield "\n".join(data_lines)


def _consume_sumitalk_chat_stream(result, job_id: str) -> tuple[int, dict]:
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
    if status >= 400 or response is None:
        return _extract_chat_completion_result(result)

    rich_events_emitted = str(
        (getattr(response, "headers", None) or {}).get("X-SumiTalk-Rich-Events") or ""
    ).strip() == "1"
    content_parts: list[str] = []
    role = "assistant"
    finish_reason = ""
    response_id = ""
    response_model = ""
    response_created = None
    usage = None
    stream_error = ""
    text_started = False
    done_seen = False
    part_id = "assistant-final"
    try:
        for raw_data in _iter_sse_data(response):
            if raw_data.strip() == "[DONE]":
                done_seen = True
                break
            try:
                packet = json.loads(raw_data)
            except Exception:
                continue
            if not isinstance(packet, dict):
                continue
            if packet.get("error"):
                error_value = packet.get("error")
                if isinstance(error_value, dict):
                    stream_error = str(error_value.get("message") or error_value.get("error") or error_value)
                else:
                    stream_error = str(error_value)
                break
            response_id = str(packet.get("id") or response_id)
            response_model = str(packet.get("model") or response_model)
            response_created = packet.get("created", response_created)
            if isinstance(packet.get("usage"), dict):
                usage = packet.get("usage")
            choices = packet.get("choices") or []
            choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            if delta.get("role"):
                role = str(delta.get("role") or role)
            text = _chat_message_text(delta)
            if text:
                content_parts.append(text)
                if not rich_events_emitted and not text_started:
                    append_sumitalk_chat_job_event(
                        job_id,
                        "assistant_text_started",
                        {
                            "part_id": part_id,
                            "round": 0,
                            "mode": "delta",
                            "role": role,
                        },
                    )
                    text_started = True
                if not rich_events_emitted:
                    for event_text in _chat_event_text_chunks(text):
                        append_sumitalk_chat_job_event(
                            job_id,
                            "assistant_delta",
                            {
                                "part_id": part_id,
                                "round": 0,
                                "mode": "delta",
                                "role": role,
                                "text": event_text,
                            },
                        )
            if choice.get("finish_reason") is not None:
                finish_reason = str(choice.get("finish_reason") or "")
    finally:
        try:
            if hasattr(response, "close"):
                response.close()
        except Exception:
            pass

    if stream_error:
        return 502, {"error": stream_error}
    if not done_seen and not finish_reason:
        return 502, {"error": "流式响应异常中断"}
    if text_started:
        append_sumitalk_chat_job_event(
            job_id,
            "assistant_text_finished",
            {
                "part_id": part_id,
                "round": 0,
                "mode": "delta",
                "role": role,
            },
        )
    data = {
        "id": response_id or f"chatcmpl-{job_id}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": role or "assistant",
                    "content": "".join(content_parts),
                },
                "finish_reason": finish_reason or "stop",
            }
        ],
    }
    if response_model:
        data["model"] = response_model
    if response_created is not None:
        data["created"] = response_created
    if usage is not None:
        data["usage"] = usage
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
    body_for_queue = dict(body or {})
    try:
        from services.recall_message_targets import consume_recall_targets_from_body

        consume_recall_targets_from_body(
            body_for_queue,
            window_id=window_id,
            client_request_id=client_request_id,
        )
    except Exception:
        sumitalk_logger.debug(
            "recall_targets_consume_failed window_id=%s client_request_id=%s",
            window_id,
            client_request_id,
            exc_info=True,
        )

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

    game_id = normalize_game_id((body_for_queue or {}).get("game_id"))
    native_stream = should_stream_sumitalk_chat_job(user_agent, game_id=game_id)
    execution_mode = "stream" if native_stream else "nonstream"
    chat_body = dict(body_for_queue or {})
    chat_body["model"] = model
    chat_body["messages"] = messages
    chat_body["window_id"] = window_id
    chat_body["stream"] = native_stream
    chat_body.pop("game_id", None)
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
    if game_id:
        headers["X-SumiTalk-Game-Id"] = game_id
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
        "execution_mode": execution_mode,
    }
    if game_id:
        state["game_id"] = game_id
    payload = {
        "chat_body": chat_body,
        "headers": headers,
        "remote_addr": remote_addr or "127.0.0.1",
        "execution_mode": execution_mode,
    }
    if game_id:
        payload["game_id"] = game_id
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
        "[SumiTalk] chat_job_enqueued job_id=%s window_id=%s target=%s mode=%s game_id=%s messages=%s client_request_id=%s request_key=%s",
        job_id,
        window_id,
        reply_target,
        execution_mode,
        game_id,
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
    execution_mode = str((payload or {}).get("execution_mode") or "").strip().lower()
    if not isinstance(chat_body, dict) or not isinstance(headers, dict):
        raise ValueError("invalid sumitalk chat job payload")
    if execution_mode not in {"stream", "nonstream"}:
        execution_mode = "stream" if bool(chat_body.get("stream")) else "nonstream"

    def _lease_alive() -> bool:
        if queue_id is None:
            return True
        return sumitalk_chat_queue_lease_active(int(queue_id), lease_token=lease_token)

    def _stage(stage: str, **fields) -> None:
        set_sumitalk_chat_job_stage(job_id, stage, **fields)
        if queue_id is not None:
            heartbeat_sumitalk_chat_queue_item(int(queue_id), lease_token=lease_token)

    state = read_sumitalk_chat_job_state(job_id) or {}
    state = reconcile_sumitalk_chat_job_terminal_state(job_id, state) or state
    status = str(state.get("status") or "").strip().lower()
    if status in _TERMINAL_JOB_STATUSES:
        return status
    if not _lease_alive():
        return "stale_lease"
    if not patch_sumitalk_chat_job_state(
        job_id,
        {
            "status": "running",
            "execution_mode": execution_mode,
            "worker_pid": os.getpid(),
            "worker_started_at": now_beijing_iso(),
        },
        protect_terminal=True,
    ):
        state = read_sumitalk_chat_job_state(job_id) or {}
        return str(state.get("status") or "terminal").strip().lower() or "terminal"
    append_sumitalk_chat_job_event(
        job_id,
        "run_started",
        {
            "execution_mode": execution_mode,
            "mode": "snapshot",
        },
    )
    _stage(
        "worker_started",
        execution_mode=execution_mode,
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
                if bool(chat_body.get("stream")):
                    status_code, data = _consume_sumitalk_chat_stream(result, job_id)
                else:
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
            finalize_sumitalk_chat_job(
                job_id,
                "error",
                state_patch={
                    "status_code": status_code,
                    "error": str(err),
                    "response": data,
                },
                event_payload={
                    "error": str(err),
                    "status_code": status_code,
                    "execution_mode": execution_mode,
                },
            )
            return "error"
        _stage("reply_ready", status_code=status_code)
        message, finish_reason = _chat_completion_message(data)
        final_text = _chat_message_text(message)
        terminal_part = _latest_sumitalk_chat_assistant_part(job_id) if final_text else None
        terminal_part_id, terminal_round = terminal_part or ("assistant-final", 0)
        if not finalize_sumitalk_chat_job(
            job_id,
            "done",
            state_patch={
                "status_code": status_code,
                "response": data,
            },
            event_payload={
                "part_id": terminal_part_id,
                "round": terminal_round,
                "mode": "snapshot",
                "role": str(message.get("role") or "assistant"),
                "text": final_text,
                "finish_reason": finish_reason,
                "execution_mode": execution_mode,
            },
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
