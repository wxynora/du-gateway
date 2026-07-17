from __future__ import annotations

import json
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import WAKEUP_STATE_DB
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


STATUS_PLANNED = "planned"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = (STATUS_PLANNED, STATUS_RUNNING)
TERMINAL_STATUSES = (STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELLED)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _db_path() -> Path:
    return Path(WAKEUP_STATE_DB)


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
                CREATE TABLE IF NOT EXISTS wakeup_events (
                    event_id TEXT PRIMARY KEY,
                    source_key TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    reason_code TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    planned_at TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT '',
                    reply_preview TEXT NOT NULL DEFAULT '',
                    cancel_reason TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_wakeup_events_status_planned
                    ON wakeup_events(status, planned_at);
                CREATE INDEX IF NOT EXISTS idx_wakeup_events_kind_source
                    ON wakeup_events(kind, source_key, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_wakeup_events_finished
                    ON wakeup_events(status, finished_at, updated_at);
                """
            )
        _SCHEMA_READY = True


def _clean(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[: max(1, int(limit or 500))]


def _json_dumps(value: dict | None) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None) -> dict:
    try:
        data = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _row_to_event(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {
        "event_id": str(row["event_id"] or ""),
        "source_key": str(row["source_key"] or ""),
        "kind": str(row["kind"] or ""),
        "reason_code": str(row["reason_code"] or ""),
        "reason": str(row["reason"] or ""),
        "planned_at": str(row["planned_at"] or ""),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
        "status": str(row["status"] or ""),
        "attempt_count": int(row["attempt_count"] or 0),
        "last_error": str(row["last_error"] or ""),
        "channel": str(row["channel"] or ""),
        "target": str(row["target"] or ""),
        "reply_preview": str(row["reply_preview"] or ""),
        "cancel_reason": str(row["cancel_reason"] or ""),
        "metadata": _json_loads(row["metadata_json"]),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def get_event(event_id: str) -> dict | None:
    ensure_schema()
    clean_id = _clean(event_id, 120)
    if not clean_id:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM wakeup_events WHERE event_id=?", (clean_id,)).fetchone()
    return _row_to_event(row)


def find_active_event(
    *,
    kind: str,
    source_key: str = "",
    planned_at: str = "",
) -> dict | None:
    ensure_schema()
    clean_kind = _clean(kind, 80)
    clean_source = _clean(source_key, 240)
    clean_planned = _clean(planned_at, 80)
    if not clean_kind:
        return None
    clauses = ["kind=?", "status IN (?, ?)"]
    params: list[Any] = [clean_kind, STATUS_PLANNED, STATUS_RUNNING]
    if clean_source:
        clauses.append("source_key=?")
        params.append(clean_source)
    if clean_planned:
        clauses.append("planned_at=?")
        params.append(clean_planned)
    sql = f"""
        SELECT * FROM wakeup_events
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
    """
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return _row_to_event(row)


def plan_event(
    *,
    kind: str,
    planned_at: str,
    reason: str,
    source_key: str = "",
    reason_code: str = "",
    channel: str = "",
    target: str = "",
    metadata: dict | None = None,
    replace_reason: str = "计划时间已重新安排",
) -> dict:
    ensure_schema()
    clean_kind = _clean(kind, 80)
    clean_planned = _clean(planned_at, 80)
    if not clean_kind or not clean_planned:
        raise ValueError("kind and planned_at are required")
    clean_source = _clean(source_key, 240)
    now_iso = now_beijing_iso()
    event_id = f"wakeup_{uuid4()}"
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = None
        if clean_source:
            existing = conn.execute(
                """
                SELECT * FROM wakeup_events
                WHERE kind=? AND source_key=? AND planned_at=? AND status IN (?, ?)
                ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 1
                """,
                (clean_kind, clean_source, clean_planned, STATUS_PLANNED, STATUS_RUNNING),
            ).fetchone()
        if existing is not None:
            conn.execute(
                """
                UPDATE wakeup_events
                SET reason_code=?, reason=?, channel=?, target=?, metadata_json=?, updated_at=?
                WHERE event_id=?
                """,
                (
                    _clean(reason_code, 120),
                    _clean(reason, 500),
                    _clean(channel, 40),
                    _clean(target, 160),
                    _json_dumps(metadata),
                    now_iso,
                    str(existing["event_id"]),
                ),
            )
            conn.execute("COMMIT")
            return get_event(str(existing["event_id"])) or {}
        if clean_source:
            conn.execute(
                """
                UPDATE wakeup_events
                SET status=?, finished_at=?, cancel_reason=?, updated_at=?
                WHERE kind=? AND source_key=? AND status=? AND planned_at!=?
                """,
                (
                    STATUS_CANCELLED,
                    now_iso,
                    _clean(replace_reason, 500),
                    now_iso,
                    clean_kind,
                    clean_source,
                    STATUS_PLANNED,
                    clean_planned,
                ),
            )
        conn.execute(
            """
            INSERT INTO wakeup_events (
                event_id, source_key, kind, reason_code, reason, planned_at,
                status, channel, target, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                clean_source,
                clean_kind,
                _clean(reason_code, 120),
                _clean(reason, 500),
                clean_planned,
                STATUS_PLANNED,
                _clean(channel, 40),
                _clean(target, 160),
                _json_dumps(metadata),
                now_iso,
                now_iso,
            ),
        )
        conn.execute("COMMIT")
    return get_event(event_id) or {}


def start_event(
    *,
    event_id: str = "",
    kind: str = "",
    reason: str = "",
    source_key: str = "",
    planned_at: str = "",
    reason_code: str = "",
    channel: str = "",
    target: str = "",
    metadata: dict | None = None,
) -> dict:
    ensure_schema()
    clean_id = _clean(event_id, 120)
    if not clean_id:
        active = find_active_event(kind=kind, source_key=source_key, planned_at=planned_at)
        clean_id = str((active or {}).get("event_id") or "")
    now_iso = now_beijing_iso()
    if not clean_id:
        clean_kind = _clean(kind, 80)
        if not clean_kind:
            raise ValueError("kind is required")
        clean_id = f"wakeup_{uuid4()}"
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO wakeup_events (
                    event_id, source_key, kind, reason_code, reason, planned_at,
                    started_at, status, attempt_count, channel, target,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    clean_id,
                    _clean(source_key, 240),
                    clean_kind,
                    _clean(reason_code, 120),
                    _clean(reason, 500),
                    _clean(planned_at or now_iso, 80),
                    now_iso,
                    STATUS_RUNNING,
                    _clean(channel, 40),
                    _clean(target, 160),
                    _json_dumps(metadata),
                    now_iso,
                    now_iso,
                ),
            )
        return get_event(clean_id) or {}
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wakeup_events
            SET status=?, started_at=CASE WHEN started_at='' THEN ? ELSE started_at END,
                attempt_count=attempt_count+1,
                reason_code=CASE WHEN ?!='' THEN ? ELSE reason_code END,
                reason=CASE WHEN ?!='' THEN ? ELSE reason END,
                channel=CASE WHEN ?!='' THEN ? ELSE channel END,
                target=CASE WHEN ?!='' THEN ? ELSE target END,
                metadata_json=CASE WHEN ?!='{}' THEN ? ELSE metadata_json END,
                updated_at=?
            WHERE event_id=? AND status IN (?, ?)
            """,
            (
                STATUS_RUNNING,
                now_iso,
                _clean(reason_code, 120),
                _clean(reason_code, 120),
                _clean(reason, 500),
                _clean(reason, 500),
                _clean(channel, 40),
                _clean(channel, 40),
                _clean(target, 160),
                _clean(target, 160),
                _json_dumps(metadata),
                _json_dumps(metadata),
                now_iso,
                clean_id,
                STATUS_PLANNED,
                STATUS_RUNNING,
            ),
        )
    return get_event(clean_id) or {}


def record_attempt_error(event_id: str, error: str) -> dict:
    ensure_schema()
    clean_id = _clean(event_id, 120)
    if not clean_id:
        return {}
    now_iso = now_beijing_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wakeup_events
            SET last_error=?, updated_at=?
            WHERE event_id=? AND status IN (?, ?)
            """,
            (_clean(error, 500), now_iso, clean_id, STATUS_PLANNED, STATUS_RUNNING),
        )
    return get_event(clean_id) or {}


def finish_event(
    event_id: str,
    *,
    success: bool,
    error: str = "",
    channel: str = "",
    reply_preview: str = "",
    kind: str = "",
    reason_code: str = "",
    reason: str = "",
) -> dict:
    ensure_schema()
    clean_id = _clean(event_id, 120)
    if not clean_id:
        return {}
    now_iso = now_beijing_iso()
    status = STATUS_SUCCESS if success else STATUS_FAILED
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wakeup_events
            SET status=?, finished_at=?, last_error=?, channel=?, reply_preview=?,
                kind=CASE WHEN ?!='' THEN ? ELSE kind END,
                reason_code=CASE WHEN ?!='' THEN ? ELSE reason_code END,
                reason=CASE WHEN ?!='' THEN ? ELSE reason END,
                updated_at=?
            WHERE event_id=? AND status IN (?, ?)
            """,
            (
                status,
                now_iso,
                _clean(error, 500),
                _clean(channel, 40),
                _clean(reply_preview, 240),
                _clean(kind, 80),
                _clean(kind, 80),
                _clean(reason_code, 120),
                _clean(reason_code, 120),
                _clean(reason, 500),
                _clean(reason, 500),
                now_iso,
                clean_id,
                STATUS_PLANNED,
                STATUS_RUNNING,
            ),
        )
    _prune_terminal_events()
    return get_event(clean_id) or {}


def cancel_event(event_id: str, reason: str) -> dict:
    ensure_schema()
    clean_id = _clean(event_id, 120)
    if not clean_id:
        return {}
    now_iso = now_beijing_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wakeup_events
            SET status=?, finished_at=?, cancel_reason=?, updated_at=?
            WHERE event_id=? AND status IN (?, ?)
            """,
            (
                STATUS_CANCELLED,
                now_iso,
                _clean(reason, 500),
                now_iso,
                clean_id,
                STATUS_PLANNED,
                STATUS_RUNNING,
            ),
        )
    _prune_terminal_events()
    return get_event(clean_id) or {}


def cancel_active_event(*, kind: str, source_key: str, reason: str) -> dict:
    event = find_active_event(kind=kind, source_key=source_key)
    if not event:
        return {}
    return cancel_event(str(event.get("event_id") or ""), reason)


def cancel_missing_plans(*, kind: str, active_source_keys: set[str], reason: str) -> int:
    ensure_schema()
    clean_kind = _clean(kind, 80)
    clean_keys = {_clean(x, 240) for x in active_source_keys if _clean(x, 240)}
    with _connect() as conn:
        rows = conn.execute(
            "SELECT event_id, source_key FROM wakeup_events WHERE kind=? AND status=?",
            (clean_kind, STATUS_PLANNED),
        ).fetchall()
    count = 0
    for row in rows:
        if str(row["source_key"] or "") in clean_keys:
            continue
        if cancel_event(str(row["event_id"] or ""), reason):
            count += 1
    return count


def expire_active_events(*, kind: str, before_iso: str, error: str) -> int:
    ensure_schema()
    clean_kind = _clean(kind, 80)
    clean_before = _clean(before_iso, 80)
    if not clean_kind or not clean_before:
        return 0
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_id FROM wakeup_events
            WHERE kind=? AND status IN (?, ?) AND planned_at!='' AND planned_at<?
            """,
            (clean_kind, STATUS_PLANNED, STATUS_RUNNING, clean_before),
        ).fetchall()
    for row in rows:
        finish_event(str(row["event_id"] or ""), success=False, error=error)
    return len(rows)


def _public_event(event: dict | None) -> dict | None:
    if not event:
        return None
    return {
        "event_id": str(event.get("event_id") or ""),
        "kind": str(event.get("kind") or ""),
        "reason_code": str(event.get("reason_code") or ""),
        "reason": str(event.get("reason") or ""),
        "planned_at": str(event.get("planned_at") or ""),
        "started_at": str(event.get("started_at") or ""),
        "finished_at": str(event.get("finished_at") or ""),
        "status": str(event.get("status") or ""),
        "attempt_count": int(event.get("attempt_count") or 0),
        "last_error": str(event.get("last_error") or ""),
        "channel": str(event.get("channel") or ""),
        "reply_preview": str(event.get("reply_preview") or ""),
        "cancel_reason": str(event.get("cancel_reason") or ""),
        "created_at": str(event.get("created_at") or ""),
        "updated_at": str(event.get("updated_at") or ""),
    }


def get_next_planned() -> dict | None:
    ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM wakeup_events
            WHERE status=? AND planned_at!=''
            ORDER BY planned_at ASC, created_at ASC
            LIMIT 1
            """,
            (STATUS_PLANNED,),
        ).fetchone()
    return _public_event(_row_to_event(row))


def list_history(limit: int = 30) -> list[dict]:
    ensure_schema()
    n = max(1, min(100, int(limit or 30)))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM wakeup_events
            WHERE status IN (?, ?, ?)
            ORDER BY CASE WHEN finished_at!='' THEN finished_at ELSE updated_at END DESC,
                     updated_at DESC,
                     rowid DESC
            LIMIT ?
            """,
            (*TERMINAL_STATUSES, n),
        ).fetchall()
    return [item for item in (_public_event(_row_to_event(row)) for row in rows) if item]


def snapshot(limit: int = 30) -> dict:
    return {"next": get_next_planned(), "history": list_history(limit)}


def _prune_terminal_events() -> None:
    ensure_schema()
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    cutoff = (now_dt - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S+08:00") if now_dt else ""
    with _connect() as conn:
        if cutoff:
            conn.execute(
                """
                DELETE FROM wakeup_events
                WHERE status IN (?, ?, ?)
                  AND CASE WHEN finished_at!='' THEN finished_at ELSE updated_at END < ?
                """,
                (*TERMINAL_STATUSES, cutoff),
            )
        conn.execute(
            """
            DELETE FROM wakeup_events
            WHERE event_id IN (
                SELECT event_id FROM wakeup_events
                WHERE status IN (?, ?, ?)
                ORDER BY CASE WHEN finished_at!='' THEN finished_at ELSE updated_at END DESC,
                         updated_at DESC,
                         rowid DESC
                LIMIT -1 OFFSET 1000
            )
            """,
            TERMINAL_STATUSES,
        )
