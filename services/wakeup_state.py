from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config import WAKEUP_STATE_DB
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

KIND_SCHEDULE = "schedule"
KIND_FOLLOWUP = "followup"
KIND_HARD_TRIGGER = "hard_trigger"
KIND_DU_DAILY_SLEEP = "du_daily_sleep"
KIND_RANDOM_PROACTIVE = "random_proactive"

STATUS_SCHEDULED = "scheduled"
STATUS_CHECKED = "checked"
STATUS_FIRED = "fired"
STATUS_ERROR = "error"

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
                CREATE TABLE IF NOT EXISTS wakeup_state (
                    key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    source_id TEXT NOT NULL DEFAULT '',
                    next_due_at TEXT NOT NULL DEFAULT '',
                    last_checked_at TEXT NOT NULL DEFAULT '',
                    last_fired_at TEXT NOT NULL DEFAULT '',
                    last_status TEXT NOT NULL DEFAULT '',
                    window_id TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    last_result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_wakeup_state_kind_due
                    ON wakeup_state(kind, source_id, next_due_at);
                CREATE INDEX IF NOT EXISTS idx_wakeup_state_updated
                    ON wakeup_state(updated_at);
                """
            )
        _SCHEMA_READY = True


def make_key(kind: str, source_id: str | int = "") -> str:
    clean_kind = str(kind or "").strip()
    clean_source = str(source_id or "default").strip() or "default"
    return f"{clean_kind}:{clean_source}"


def _json_dumps(data: dict | None) -> str:
    return json.dumps(dict(data or {}), ensure_ascii=False, separators=(",", ":"))


def _json_loads(raw: str | None) -> dict:
    try:
        data = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _row_to_state(row: sqlite3.Row) -> dict:
    return {
        "key": str(row["key"] or ""),
        "kind": str(row["kind"] or ""),
        "source_id": str(row["source_id"] or ""),
        "next_due_at": str(row["next_due_at"] or ""),
        "last_checked_at": str(row["last_checked_at"] or ""),
        "last_fired_at": str(row["last_fired_at"] or ""),
        "last_status": str(row["last_status"] or ""),
        "window_id": str(row["window_id"] or ""),
        "channel": str(row["channel"] or ""),
        "target": str(row["target"] or ""),
        "payload": _json_loads(row["payload_json"]),
        "last_result": _json_loads(row["last_result_json"]),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def upsert_state(
    *,
    kind: str,
    source_id: str | int = "",
    next_due_at: str = "",
    status: str = STATUS_SCHEDULED,
    payload: dict | None = None,
    window_id: str = "",
    channel: str = "",
    target: str = "",
) -> dict:
    ensure_schema()
    clean_kind = str(kind or "").strip()
    if not clean_kind:
        raise ValueError("kind is required")
    clean_source = str(source_id or "default").strip() or "default"
    key = make_key(clean_kind, clean_source)
    now_iso = now_beijing_iso()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM wakeup_state WHERE key=?", (key,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO wakeup_state (
                    key, kind, source_id, next_due_at, last_checked_at, last_fired_at,
                    last_status, window_id, channel, target, payload_json,
                    last_result_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    key,
                    clean_kind,
                    clean_source,
                    str(next_due_at or "").strip(),
                    str(status or STATUS_SCHEDULED).strip() or STATUS_SCHEDULED,
                    str(window_id or "").strip(),
                    str(channel or "").strip(),
                    str(target or "").strip(),
                    _json_dumps(payload),
                    now_iso,
                    now_iso,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE wakeup_state
                SET kind=?, source_id=?, next_due_at=?, last_status=?,
                    window_id=?, channel=?, target=?, payload_json=?, updated_at=?
                WHERE key=?
                """,
                (
                    clean_kind,
                    clean_source,
                    str(next_due_at or "").strip(),
                    str(status or STATUS_SCHEDULED).strip() or STATUS_SCHEDULED,
                    str(window_id or "").strip(),
                    str(channel or "").strip(),
                    str(target or "").strip(),
                    _json_dumps(payload),
                    now_iso,
                    key,
                ),
            )
    state = get_state(clean_kind, clean_source)
    return state or {}


def get_state(kind: str, source_id: str | int = "") -> dict | None:
    ensure_schema()
    key = make_key(kind, source_id)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM wakeup_state WHERE key=?", (key,)).fetchone()
    return _row_to_state(row) if row is not None else None


def list_due_states(
    *,
    kinds: list[str] | tuple[str, ...] | None = None,
    source_id: str | int = "",
    now_iso: str | None = None,
    limit: int = 20,
) -> list[dict]:
    ensure_schema()
    now_s = str(now_iso or now_beijing_iso()).strip()
    n = max(1, min(100, int(limit or 20)))
    kind_list = [str(x or "").strip() for x in (kinds or []) if str(x or "").strip()]
    clean_source = str(source_id or "").strip()
    params: list[Any] = [now_s]
    clauses = ["next_due_at != ''", "next_due_at <= ?"]
    if kind_list:
        clauses.append("kind IN (%s)" % ",".join("?" for _ in kind_list))
        params.extend(kind_list)
    if clean_source:
        clauses.append("source_id=?")
        params.append(clean_source)
    params.append(n)
    sql = f"""
        SELECT *
        FROM wakeup_state
        WHERE {' AND '.join(clauses)}
        ORDER BY next_due_at ASC, updated_at ASC, key ASC
        LIMIT ?
    """
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_state(row) for row in rows]


def next_due_at(*, kinds: list[str] | tuple[str, ...] | None = None, source_id: str | int = "") -> str:
    ensure_schema()
    kind_list = [str(x or "").strip() for x in (kinds or []) if str(x or "").strip()]
    clean_source = str(source_id or "").strip()
    params: list[Any] = []
    clauses = ["next_due_at != ''"]
    if kind_list:
        clauses.append("kind IN (%s)" % ",".join("?" for _ in kind_list))
        params.extend(kind_list)
    if clean_source:
        clauses.append("source_id=?")
        params.append(clean_source)
    sql = f"""
        SELECT next_due_at
        FROM wakeup_state
        WHERE {' AND '.join(clauses)}
        ORDER BY next_due_at ASC
        LIMIT 1
    """
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return str(row["next_due_at"] or "") if row is not None else ""


def record_result(
    *,
    kind: str,
    source_id: str | int = "",
    result: dict | None = None,
    next_due_at: str = "",
    status: str = "",
    fired: bool = False,
) -> dict:
    ensure_schema()
    clean_kind = str(kind or "").strip()
    clean_source = str(source_id or "default").strip() or "default"
    key = make_key(clean_kind, clean_source)
    now_iso = now_beijing_iso()
    clean_status = str(status or (STATUS_FIRED if fired else STATUS_CHECKED)).strip()
    row = get_state(clean_kind, clean_source)
    if row is None:
        upsert_state(kind=clean_kind, source_id=clean_source, next_due_at=next_due_at, status=clean_status)
    with _connect() as conn:
        conn.execute(
            """
            UPDATE wakeup_state
            SET next_due_at=?, last_checked_at=?,
                last_fired_at=CASE WHEN ? THEN ? ELSE last_fired_at END,
                last_status=?, last_result_json=?, updated_at=?
            WHERE key=?
            """,
            (
                str(next_due_at or "").strip(),
                now_iso,
                1 if fired else 0,
                now_iso,
                clean_status,
                _json_dumps(result),
                now_iso,
                key,
            ),
        )
    return get_state(clean_kind, clean_source) or {}


def seconds_until_next(*, kinds: list[str] | tuple[str, ...] | None = None, source_id: str | int = "") -> float | None:
    due_at = next_due_at(kinds=kinds, source_id=source_id)
    due_dt = parse_iso_to_beijing(due_at)
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not due_dt or not now_dt:
        return None
    return (due_dt - now_dt).total_seconds()


def list_states(limit: int = 100, kind: str = "") -> list[dict]:
    ensure_schema()
    n = max(1, min(500, int(limit or 100)))
    clean_kind = str(kind or "").strip()
    with _connect() as conn:
        if clean_kind:
            rows = conn.execute(
                """
                SELECT *
                FROM wakeup_state
                WHERE kind=?
                ORDER BY next_due_at ASC, updated_at DESC
                LIMIT ?
                """,
                (clean_kind, n),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM wakeup_state
                ORDER BY next_due_at ASC, updated_at DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
    return [_row_to_state(row) for row in rows]


def state_stats() -> dict[str, int]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT kind, COUNT(*) AS n
            FROM wakeup_state
            GROUP BY kind
            """
        ).fetchall()
    return {str(row["kind"] or ""): int(row["n"] or 0) for row in rows}
