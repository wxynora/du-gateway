from __future__ import annotations

import json
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import (
    WAKEUP_QUEUE_CLAIM_STALE_SECONDS,
    WAKEUP_QUEUE_DB,
    WAKEUP_QUEUE_DONE_TTL_DAYS,
    WAKEUP_QUEUE_KEEP_MAX,
)
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_SENT = "sent"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"

ACTIVE_STATUSES = {STATUS_PENDING, STATUS_CLAIMED}
DONE_STATUSES = {STATUS_SENT, STATUS_CANCELLED}

TYPE_FOLLOWUP = "followup"
TYPE_HARD_TRIGGER = "hard_trigger"
TYPE_SCHEDULE = "schedule"
TYPE_RANDOM_PROACTIVE = "random_proactive"

_QUEUE_KEEP_MAX = max(20, int(WAKEUP_QUEUE_KEEP_MAX or 80))
_DONE_TTL_DAYS = max(1, int(WAKEUP_QUEUE_DONE_TTL_DAYS or 1))
_CLAIM_STALE_SECONDS = max(60, int(WAKEUP_QUEUE_CLAIM_STALE_SECONDS or 600))
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _db_path() -> Path:
    return Path(WAKEUP_QUEUE_DB)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS wakeup_queue (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    due_at TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    window_id TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    claimed_at TEXT,
                    claimed_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT,
                    cancel_reason TEXT,
                    last_error TEXT,
                    last_result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_wakeup_queue_status_due
                    ON wakeup_queue(status, due_at, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_wakeup_queue_kind_status
                    ON wakeup_queue(kind, status);
                CREATE INDEX IF NOT EXISTS idx_wakeup_queue_updated
                    ON wakeup_queue(status, updated_at);
                """
            )
        _SCHEMA_READY = True


def _status(item: dict) -> str:
    return str((item or {}).get("status") or STATUS_PENDING).strip().lower() or STATUS_PENDING


def _dt(raw: Any):
    return parse_iso_to_beijing(str(raw or "").strip())


def _json_dumps(data: dict | None) -> str:
    return json.dumps(dict(data or {}), ensure_ascii=False, separators=(",", ":"))


def _json_loads(raw: str | None) -> dict:
    try:
        data = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _iso_after_seconds(seconds: int, now_iso: str | None = None) -> str:
    base = _dt(now_iso or now_beijing_iso())
    if not base:
        return now_iso or now_beijing_iso()
    return (base + timedelta(seconds=int(seconds or 0))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _cutoff_iso(now_iso: str, days: int = 3) -> str:
    now = _dt(now_iso)
    if not now:
        return now_iso
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _row_to_item(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"] or ""),
        "kind": str(row["kind"] or ""),
        "status": str(row["status"] or STATUS_PENDING),
        "due_at": str(row["due_at"] or ""),
        "dedupe_key": str(row["dedupe_key"] or ""),
        "priority": int(row["priority"] or 100),
        "window_id": str(row["window_id"] or ""),
        "channel": str(row["channel"] or ""),
        "target": str(row["target"] or ""),
        "payload": _json_loads(row["payload_json"]),
        "attempts": int(row["attempts"] or 0),
        "claimed_at": str(row["claimed_at"] or ""),
        "claimed_by": str(row["claimed_by"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
        "cancel_reason": str(row["cancel_reason"] or ""),
        "last_error": str(row["last_error"] or ""),
        "last_result": _json_loads(row["last_result_json"]),
    }


def _prune(conn: sqlite3.Connection, now_iso: str) -> None:
    cutoff = _cutoff_iso(now_iso, days=_DONE_TTL_DAYS)
    conn.execute(
        """
        DELETE FROM wakeup_queue
        WHERE status NOT IN (?, ?)
          AND COALESCE(finished_at, updated_at, created_at) < ?
        """,
        (STATUS_PENDING, STATUS_CLAIMED, cutoff),
    )
    active_count = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM wakeup_queue WHERE status IN (?, ?)",
            (STATUS_PENDING, STATUS_CLAIMED),
        ).fetchone()["n"]
        or 0
    )
    done_keep = max(0, _QUEUE_KEEP_MAX - active_count)
    if done_keep <= 0:
        conn.execute("DELETE FROM wakeup_queue WHERE status NOT IN (?, ?)", (STATUS_PENDING, STATUS_CLAIMED))
        return
    conn.execute(
        """
        DELETE FROM wakeup_queue
        WHERE status NOT IN (?, ?)
          AND id NOT IN (
              SELECT id
              FROM wakeup_queue
              WHERE status NOT IN (?, ?)
              ORDER BY COALESCE(finished_at, updated_at, created_at) DESC, id DESC
              LIMIT ?
          )
        """,
        (STATUS_PENDING, STATUS_CLAIMED, STATUS_PENDING, STATUS_CLAIMED, done_keep),
    )


def make_item(
    *,
    kind: str,
    due_at: str,
    dedupe_key: str,
    payload: dict | None = None,
    priority: int = 100,
    window_id: str = "",
    channel: str = "",
    target: str = "",
) -> dict:
    now_iso = now_beijing_iso()
    clean_kind = str(kind or "").strip()
    clean_dedupe = str(dedupe_key or "").strip()
    return {
        "id": f"wakeup_{uuid4()}",
        "kind": clean_kind,
        "status": STATUS_PENDING,
        "due_at": str(due_at or "").strip() or now_iso,
        "dedupe_key": clean_dedupe or f"{clean_kind}:{uuid4()}",
        "priority": int(priority or 100),
        "window_id": str(window_id or "").strip(),
        "channel": str(channel or "").strip(),
        "target": str(target or "").strip(),
        "payload": dict(payload or {}),
        "attempts": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def upsert_pending(item: dict) -> tuple[bool, str]:
    if not isinstance(item, dict):
        return False, ""
    dedupe = str(item.get("dedupe_key") or "").strip()
    if not dedupe:
        return False, ""
    ensure_schema()
    now_iso = now_beijing_iso()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _prune(conn, now_iso)
            row = conn.execute(
                "SELECT id, status, created_at FROM wakeup_queue WHERE dedupe_key=?",
                (dedupe,),
            ).fetchone()
            if row is not None:
                st = str(row["status"] or "").strip().lower()
                if st in ACTIVE_STATUSES or st in DONE_STATUSES:
                    conn.execute("COMMIT")
                    return False, str(row["id"] or "")
                existing_id = str(row["id"] or item.get("id") or f"wakeup_{uuid4()}")
                created_at = str(row["created_at"] or item.get("created_at") or now_iso)
                conn.execute(
                    """
                    UPDATE wakeup_queue
                    SET kind=?, status=?, due_at=?, priority=?, window_id=?, channel=?, target=?,
                        payload_json=?, attempts=0, claimed_at=NULL, claimed_by=NULL,
                        updated_at=?, finished_at=NULL, cancel_reason=NULL, last_error=NULL,
                        last_result_json='{}'
                    WHERE id=?
                    """,
                    (
                        str(item.get("kind") or "").strip(),
                        STATUS_PENDING,
                        str(item.get("due_at") or now_iso).strip() or now_iso,
                        int(item.get("priority") or 100),
                        str(item.get("window_id") or "").strip(),
                        str(item.get("channel") or "").strip(),
                        str(item.get("target") or "").strip(),
                        _json_dumps(item.get("payload") if isinstance(item.get("payload"), dict) else {}),
                        now_iso,
                        existing_id,
                    ),
                )
                conn.execute(
                    "UPDATE wakeup_queue SET created_at=? WHERE id=? AND (created_at IS NULL OR created_at='')",
                    (created_at, existing_id),
                )
                conn.execute("COMMIT")
                return True, existing_id
            item_id = str(item.get("id") or f"wakeup_{uuid4()}").strip()
            conn.execute(
                """
                INSERT INTO wakeup_queue (
                    id, dedupe_key, kind, status, due_at, priority, window_id, channel, target,
                    payload_json, attempts, claimed_at, claimed_by, created_at, updated_at,
                    finished_at, cancel_reason, last_error, last_result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, ?, ?, NULL, NULL, NULL, '{}')
                """,
                (
                    item_id,
                    dedupe,
                    str(item.get("kind") or "").strip(),
                    STATUS_PENDING,
                    str(item.get("due_at") or now_iso).strip() or now_iso,
                    int(item.get("priority") or 100),
                    str(item.get("window_id") or "").strip(),
                    str(item.get("channel") or "").strip(),
                    str(item.get("target") or "").strip(),
                    _json_dumps(item.get("payload") if isinstance(item.get("payload"), dict) else {}),
                    str(item.get("created_at") or now_iso).strip() or now_iso,
                    now_iso,
                ),
            )
            conn.execute("COMMIT")
            return True, item_id
        except Exception:
            conn.execute("ROLLBACK")
            raise


def has_active_kind(kind: str) -> bool:
    k = str(kind or "").strip()
    if not k:
        return False
    ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM wakeup_queue
            WHERE kind=? AND status IN (?, ?)
            LIMIT 1
            """,
            (k, STATUS_PENDING, STATUS_CLAIMED),
        ).fetchone()
    return row is not None


def cancel_active_kind(kind: str, reason: str = "") -> int:
    k = str(kind or "").strip()
    if not k:
        return 0
    ensure_schema()
    now_iso = now_beijing_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE wakeup_queue
            SET status=?, cancel_reason=?, finished_at=?, updated_at=?
            WHERE kind=? AND status IN (?, ?)
            """,
            (STATUS_CANCELLED, str(reason or "").strip(), now_iso, now_iso, k, STATUS_PENDING, STATUS_CLAIMED),
        )
        _prune(conn, now_iso)
    return int(cur.rowcount or 0)


def claim_due(limit: int = 1, worker_id: str = "async_scheduler") -> list[dict]:
    ensure_schema()
    now_iso = now_beijing_iso()
    stale_cutoff = _iso_after_seconds(-_CLAIM_STALE_SECONDS, now_iso)
    max_limit = max(1, int(limit or 1))
    claimed: list[dict] = []
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                UPDATE wakeup_queue
                SET status=?, claimed_at=NULL, claimed_by=NULL, updated_at=?
                WHERE status=?
                  AND (claimed_at IS NULL OR claimed_at='' OR claimed_at < ?)
                """,
                (STATUS_PENDING, now_iso, STATUS_CLAIMED, stale_cutoff),
            )
            rows = conn.execute(
                """
                SELECT *
                FROM wakeup_queue
                WHERE status=? AND due_at <= ?
                ORDER BY priority ASC, due_at ASC, created_at ASC, id ASC
                LIMIT ?
                """,
                (STATUS_PENDING, now_iso, max_limit),
            ).fetchall()
            for row in rows:
                attempts = int(row["attempts"] or 0) + 1
                conn.execute(
                    """
                    UPDATE wakeup_queue
                    SET status=?, claimed_at=?, claimed_by=?, attempts=?, updated_at=?, last_error=NULL
                    WHERE id=?
                    """,
                    (
                        STATUS_CLAIMED,
                        now_iso,
                        str(worker_id or "async_scheduler"),
                        attempts,
                        now_iso,
                        str(row["id"] or ""),
                    ),
                )
                item = _row_to_item(row)
                item["status"] = STATUS_CLAIMED
                item["claimed_at"] = now_iso
                item["claimed_by"] = str(worker_id or "async_scheduler")
                item["attempts"] = attempts
                item["updated_at"] = now_iso
                claimed.append(item)
            _prune(conn, now_iso)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return claimed


def mark_sent(item_id: str, result: dict | None = None) -> bool:
    return _finish(item_id, STATUS_SENT, result=result)


def mark_cancelled(item_id: str, reason: str = "", result: dict | None = None) -> bool:
    payload = dict(result or {})
    if reason:
        payload["cancel_reason"] = reason
    return _finish(item_id, STATUS_CANCELLED, reason=reason, result=payload)


def mark_failed_or_retry(
    item_id: str,
    error: str = "",
    retry_after_seconds: int = 60,
    max_attempts: int = 3,
    result: dict | None = None,
) -> bool:
    ensure_schema()
    now_iso = now_beijing_iso()
    max_attempts = int(max_attempts or 0)
    clean_error = str(error or "").strip()
    if len(clean_error) > 1000:
        clean_error = clean_error[:1000]
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT attempts FROM wakeup_queue WHERE id=?",
                (str(item_id or ""),),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return False
            attempts = int(row["attempts"] or 0)
            if attempts < max_attempts:
                conn.execute(
                    """
                    UPDATE wakeup_queue
                    SET status=?, due_at=?, claimed_at=NULL, claimed_by=NULL,
                        updated_at=?, last_error=?, last_result_json=?
                    WHERE id=?
                    """,
                    (
                        STATUS_PENDING,
                        _iso_after_seconds(max(5, int(retry_after_seconds or 60)), now_iso),
                        now_iso,
                        clean_error,
                        _json_dumps(result),
                        str(item_id or ""),
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE wakeup_queue
                    SET status=?, finished_at=?, updated_at=?, last_error=?, last_result_json=?
                    WHERE id=?
                    """,
                    (STATUS_FAILED, now_iso, now_iso, clean_error, _json_dumps(result), str(item_id or "")),
                )
            _prune(conn, now_iso)
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _finish(item_id: str, status: str, reason: str = "", result: dict | None = None) -> bool:
    ensure_schema()
    now_iso = now_beijing_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE wakeup_queue
            SET status=?, finished_at=?, updated_at=?, cancel_reason=?, last_result_json=?
            WHERE id=?
            """,
            (status, now_iso, now_iso, str(reason or "").strip(), _json_dumps(result), str(item_id or "")),
        )
        _prune(conn, now_iso)
    return int(cur.rowcount or 0) > 0


def queue_stats() -> dict[str, int]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM wakeup_queue
            GROUP BY status
            """
        ).fetchall()
    return {str(row["status"] or ""): int(row["n"] or 0) for row in rows}


def list_items(limit: int = 50, status: str = "") -> list[dict]:
    ensure_schema()
    n = max(1, min(200, int(limit or 50)))
    st = str(status or "").strip().lower()
    with _connect() as conn:
        if st:
            rows = conn.execute(
                """
                SELECT *
                FROM wakeup_queue
                WHERE status=?
                ORDER BY status ASC, due_at ASC, priority ASC, updated_at DESC
                LIMIT ?
                """,
                (st, n),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM wakeup_queue
                ORDER BY
                    CASE WHEN status IN ('pending', 'claimed') THEN 0 ELSE 1 END ASC,
                    due_at ASC,
                    priority ASC,
                    updated_at DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
    return [_row_to_item(row) for row in rows]
