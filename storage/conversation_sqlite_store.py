"""SQLite hot mirror for compact conversation archives."""
from __future__ import annotations

import os
import threading

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

WINDOW_ID_DEFAULT = "__default__"
_DEFAULT_MAX_ROUNDS_PER_WINDOW = 250

_write_lock = threading.Lock()

logger = get_logger(__name__)


def max_rounds_per_window(recent_keep: int = 0) -> int:
    raw = str(os.environ.get("CONVERSATION_SQLITE_MAX_ROUNDS_PER_WINDOW", "") or "").strip()
    try:
        configured = int(raw) if raw else _DEFAULT_MAX_ROUNDS_PER_WINDOW
    except Exception:
        configured = _DEFAULT_MAX_ROUNDS_PER_WINDOW
    try:
        keep = int(recent_keep or 0)
    except Exception:
        keep = 0
    return max(1, configured, keep)


def normalize_window_id(window_id: str) -> str:
    w = str(window_id or "").strip()
    return w if w else WINDOW_ID_DEFAULT


def _round_index_value(round_entry: dict) -> int:
    try:
        return int((round_entry or {}).get("index") or 0)
    except Exception:
        return 0


def _sort_rounds(rounds: list[dict]) -> list[dict]:
    return sorted(
        [r for r in (rounds or []) if isinstance(r, dict) and _round_index_value(r) > 0],
        key=lambda r: (_round_index_value(r), str(r.get("timestamp") or "")),
    )


def _json_dict(raw: str | None) -> dict:
    data = runtime_sqlite.json_loads(raw, {})
    return data if isinstance(data, dict) else {}


def _json_list(raw: str | None) -> list:
    data = runtime_sqlite.json_loads(raw, [])
    return data if isinstance(data, list) else []


def _row_to_round(row) -> dict:
    raw = _json_dict(row["raw_json"])
    out = raw if isinstance(raw, dict) else {}
    out["index"] = int(row["round_index"] or 0)
    out["timestamp"] = str(row["timestamp"] or out.get("timestamp") or "")
    out["messages"] = _json_list(row["messages_json"])
    action_note = str(row["action_note"] or "").strip()
    if action_note:
        out["action_note"] = action_note
    elif "action_note" in out:
        out.pop("action_note", None)
    return out


def _upsert_round_row(conn, window_id: str, round_entry: dict) -> bool:
    idx = _round_index_value(round_entry)
    if idx <= 0:
        return False
    messages = round_entry.get("messages") if isinstance(round_entry.get("messages"), list) else []
    timestamp = str(round_entry.get("timestamp") or "").strip()
    action_note = str(round_entry.get("action_note") or "").strip()
    conn.execute(
        """
        INSERT OR REPLACE INTO conversation_rounds
            (window_id, round_index, timestamp, messages_json, action_note, raw_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            window_id,
            idx,
            timestamp,
            runtime_sqlite.json_dumps(messages),
            action_note,
            runtime_sqlite.json_dumps(round_entry),
            now_beijing_iso(),
        ),
    )
    return True


def _save_window_meta(
    conn,
    window_id: str,
    *,
    last_round_index: int,
    next_round_index: int,
    round_count: int,
    recent_keep: int,
    updated_at: str = "",
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO conversation_windows
            (window_id, last_round_index, next_round_index, round_count, recent_keep, updated_at, bootstrapped_at)
        VALUES (
            ?, ?, ?, ?, ?, ?,
            COALESCE((SELECT bootstrapped_at FROM conversation_windows WHERE window_id = ?), ?)
        )
        """,
        (
            window_id,
            max(0, int(last_round_index or 0)),
            max(1, int(next_round_index or 1)),
            max(0, int(round_count or 0)),
            max(0, int(recent_keep or 0)),
            str(updated_at or "").strip() or now_beijing_iso(),
            window_id,
            now_beijing_iso(),
        ),
    )


def _prune_window_rounds(conn, window_id: str, recent_keep: int = 0) -> None:
    max_rows = max_rounds_per_window(recent_keep)
    conn.execute(
        """
        DELETE FROM conversation_rounds
        WHERE window_id = ?
          AND round_index NOT IN (
            SELECT round_index
            FROM conversation_rounds
            WHERE window_id = ?
            ORDER BY round_index DESC
            LIMIT ?
          )
        """,
        (window_id, window_id, max_rows),
    )


def has_window(window_id: str) -> bool:
    wid = normalize_window_id(window_id)
    try:
        with runtime_sqlite.connect() as conn:
            return conn.execute(
                "SELECT 1 FROM conversation_windows WHERE window_id = ?",
                (wid,),
            ).fetchone() is not None
    except Exception as e:
        logger.warning("conversation_sqlite has_window failed window_id=%s error=%s", wid, e)
        return False


def import_window_state(window_id: str, rounds: list[dict], meta: dict | None = None, recent_keep: int = 0) -> None:
    wid = normalize_window_id(window_id)
    sorted_rounds = _sort_rounds(rounds)
    loaded_max = max((_round_index_value(r) for r in sorted_rounds), default=0)
    meta = meta if isinstance(meta, dict) else {}
    try:
        meta_last = int(meta.get("last_round_index") or 0)
    except Exception:
        meta_last = 0
    try:
        meta_next = int(meta.get("next_round_index") or 0)
    except Exception:
        meta_next = 0
    try:
        meta_count = int(meta.get("round_count") or 0)
    except Exception:
        meta_count = 0
    last_idx = max(meta_last, loaded_max)
    next_idx = max(meta_next, last_idx + 1 if last_idx > 0 else 1, 1)
    round_count = max(meta_count, len(sorted_rounds))
    with _write_lock:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for item in sorted_rounds:
                    _upsert_round_row(conn, wid, item)
                _prune_window_rounds(conn, wid, recent_keep)
                _save_window_meta(
                    conn,
                    wid,
                    last_round_index=last_idx,
                    next_round_index=next_idx,
                    round_count=round_count,
                    recent_keep=recent_keep,
                    updated_at=str(meta.get("updated_at") or "").strip() or now_beijing_iso(),
                )
                conn.execute("COMMIT")
                logger.info(
                    "conversation_sqlite_bootstrap window_id=%s rounds=%s last_round_index=%s",
                    wid,
                    len(sorted_rounds),
                    last_idx,
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise


def get_window_meta(window_id: str) -> dict | None:
    wid = normalize_window_id(window_id)
    try:
        with runtime_sqlite.connect() as conn:
            row = conn.execute(
                """
                SELECT last_round_index, next_round_index, round_count, recent_keep, updated_at
                FROM conversation_windows
                WHERE window_id = ?
                """,
                (wid,),
            ).fetchone()
        if row is None:
            return None
        return {
            "window_id": wid,
            "last_round_index": int(row["last_round_index"] or 0),
            "next_round_index": int(row["next_round_index"] or 1),
            "round_count": int(row["round_count"] or 0),
            "recent_keep": int(row["recent_keep"] or 0),
            "updated_at": str(row["updated_at"] or ""),
        }
    except Exception as e:
        logger.warning("conversation_sqlite get_window_meta failed window_id=%s error=%s", wid, e)
        return None


def upsert_round(window_id: str, round_entry: dict, recent_keep: int = 0) -> bool:
    wid = normalize_window_id(window_id)
    idx = _round_index_value(round_entry)
    if idx <= 0:
        return False
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    existed = conn.execute(
                        "SELECT 1 FROM conversation_rounds WHERE window_id = ? AND round_index = ?",
                        (wid, idx),
                    ).fetchone() is not None
                    meta = conn.execute(
                        """
                        SELECT last_round_index, round_count
                        FROM conversation_windows
                        WHERE window_id = ?
                        """,
                        (wid,),
                    ).fetchone()
                    _upsert_round_row(conn, wid, round_entry)
                    _prune_window_rounds(conn, wid, recent_keep)
                    prev_last = int(meta["last_round_index"] or 0) if meta else 0
                    prev_count = int(meta["round_count"] or 0) if meta else 0
                    last_idx = max(prev_last, idx)
                    round_count = prev_count if existed else prev_count + 1
                    _save_window_meta(
                        conn,
                        wid,
                        last_round_index=last_idx,
                        next_round_index=last_idx + 1 if last_idx > 0 else 1,
                        round_count=round_count,
                        recent_keep=recent_keep,
                    )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("conversation_sqlite upsert_round failed window_id=%s index=%s error=%s", wid, idx, e)
            return False


def replace_window_rounds(window_id: str, rounds: list[dict], recent_keep: int = 0) -> bool:
    wid = normalize_window_id(window_id)
    sorted_rounds = _sort_rounds(rounds)
    last_idx = max((_round_index_value(r) for r in sorted_rounds), default=0)
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("DELETE FROM conversation_rounds WHERE window_id = ?", (wid,))
                    for item in sorted_rounds:
                        _upsert_round_row(conn, wid, item)
                    _prune_window_rounds(conn, wid, recent_keep)
                    _save_window_meta(
                        conn,
                        wid,
                        last_round_index=last_idx,
                        next_round_index=last_idx + 1 if last_idx > 0 else 1,
                        round_count=len(sorted_rounds),
                        recent_keep=recent_keep,
                    )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("conversation_sqlite replace_window_rounds failed window_id=%s error=%s", wid, e)
            return False


def get_rounds(window_id: str, last_n: int = 4) -> list[dict]:
    wid = normalize_window_id(window_id)
    try:
        n = int(last_n or 0)
    except Exception:
        n = 0
    if n <= 0:
        return []
    try:
        with runtime_sqlite.connect() as conn:
            rows = conn.execute(
                """
                SELECT round_index, timestamp, messages_json, action_note, raw_json
                FROM conversation_rounds
                WHERE window_id = ?
                ORDER BY round_index DESC
                LIMIT ?
                """,
                (wid, n),
            ).fetchall()
        return list(reversed([_row_to_round(row) for row in rows]))
    except Exception as e:
        logger.warning("conversation_sqlite get_rounds failed window_id=%s error=%s", wid, e)
        return []


def get_round_by_index(window_id: str, round_index: int) -> dict | None:
    wid = normalize_window_id(window_id)
    try:
        idx = int(round_index or 0)
    except Exception:
        idx = 0
    if idx <= 0:
        return None
    try:
        with runtime_sqlite.connect() as conn:
            row = conn.execute(
                """
                SELECT round_index, timestamp, messages_json, action_note, raw_json
                FROM conversation_rounds
                WHERE window_id = ? AND round_index = ?
                """,
                (wid, idx),
            ).fetchone()
        return _row_to_round(row) if row is not None else None
    except Exception as e:
        logger.warning("conversation_sqlite get_round_by_index failed window_id=%s index=%s error=%s", wid, idx, e)
        return None


def delete_round(window_id: str, round_index: int, recent_keep: int = 0) -> bool:
    wid = normalize_window_id(window_id)
    try:
        idx = int(round_index or 0)
    except Exception:
        idx = 0
    if idx <= 0:
        return False
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    existed = conn.execute(
                        "SELECT 1 FROM conversation_rounds WHERE window_id = ? AND round_index = ?",
                        (wid, idx),
                    ).fetchone() is not None
                    conn.execute(
                        "DELETE FROM conversation_rounds WHERE window_id = ? AND round_index = ?",
                        (wid, idx),
                    )
                    meta = conn.execute(
                        """
                        SELECT last_round_index, round_count
                        FROM conversation_windows
                        WHERE window_id = ?
                        """,
                        (wid,),
                    ).fetchone()
                    max_row = conn.execute(
                        "SELECT MAX(round_index) AS max_idx FROM conversation_rounds WHERE window_id = ?",
                        (wid,),
                    ).fetchone()
                    loaded_max = int(max_row["max_idx"] or 0) if max_row else 0
                    prev_last = int(meta["last_round_index"] or 0) if meta else 0
                    prev_count = int(meta["round_count"] or 0) if meta else 0
                    last_idx = loaded_max if idx >= prev_last else prev_last
                    round_count = max(0, prev_count - (1 if existed else 0))
                    _save_window_meta(
                        conn,
                        wid,
                        last_round_index=last_idx,
                        next_round_index=last_idx + 1 if last_idx > 0 else 1,
                        round_count=round_count,
                        recent_keep=recent_keep,
                    )
                    conn.execute("COMMIT")
                    return existed
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("conversation_sqlite delete_round failed window_id=%s index=%s error=%s", wid, idx, e)
            return False


def list_rounds_preview(window_id: str, preview_chars: int = 24) -> list[dict]:
    wid = normalize_window_id(window_id)
    try:
        with runtime_sqlite.connect() as conn:
            rows = conn.execute(
                """
                SELECT round_index, timestamp, messages_json, action_note, raw_json
                FROM conversation_rounds
                WHERE window_id = ?
                ORDER BY round_index ASC
                """,
                (wid,),
            ).fetchall()
    except Exception as e:
        logger.warning("conversation_sqlite list_rounds_preview failed window_id=%s error=%s", wid, e)
        return []

    out: list[dict] = []
    try:
        n = int(preview_chars or 0)
    except Exception:
        n = 0
    for row in rows:
        item = _row_to_round(row)
        user_text = ""
        asst_text = ""
        for message in item.get("messages") or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").lower()
            content = message.get("content")
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                text = " ".join(
                    str(part.get("text") or f"[{part.get('type', '')}]")
                    if isinstance(part, dict)
                    else str(part)
                    for part in content
                ).strip()
            else:
                text = str(content or "").strip()
            if role == "user" and not user_text:
                user_text = text
            if role == "assistant" and not asst_text:
                asst_text = text
        preview = f"user:{user_text} | assistant:{asst_text}".strip().replace("\n", " ").replace("\r", " ")
        if n > 0 and len(preview) > n:
            preview = preview[:n] + "…"
        out.append({"index": int(row["round_index"] or 0), "preview": preview})
    return out
