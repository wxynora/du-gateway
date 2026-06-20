"""SQLite mirror for conversation followup queue items."""
from __future__ import annotations

import threading

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

_write_lock = threading.Lock()

logger = get_logger(__name__)


def _json_dict(raw: str | None) -> dict:
    data = runtime_sqlite.json_loads(raw, {})
    return data if isinstance(data, dict) else {}


def has_items() -> bool:
    try:
        with runtime_sqlite.connect() as conn:
            return conn.execute("SELECT 1 FROM conversation_followups LIMIT 1").fetchone() is not None
    except Exception as e:
        logger.warning("conversation_followup_sqlite has_items failed error=%s", e)
        return False


def replace_items(items: list[dict]) -> bool:
    rows = [dict(x) for x in (items or []) if isinstance(x, dict)]
    now = now_beijing_iso()
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("DELETE FROM conversation_followups")
                    for pos, item in enumerate(rows):
                        item_id = str(item.get("id") or "").strip() or f"__legacy_{pos}"
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO conversation_followups (
                                id, position, status, trigger_at, context_window_id,
                                reply_channel, reply_target, thread_key, created_at,
                                updated_at, item_json
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                item_id,
                                int(pos),
                                str(item.get("status") or "").strip().lower(),
                                str(item.get("trigger_at") or "").strip(),
                                str(item.get("context_window_id") or "").strip(),
                                str(item.get("reply_channel") or "").strip(),
                                str(item.get("reply_target") or "").strip(),
                                str(item.get("thread_key") or "").strip(),
                                str(item.get("created_at") or "").strip(),
                                now,
                                runtime_sqlite.json_dumps(item),
                            ),
                        )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("conversation_followup_sqlite replace_items failed error=%s", e)
            return False


def get_items() -> list[dict]:
    try:
        with runtime_sqlite.connect() as conn:
            rows = conn.execute(
                """
                SELECT item_json
                FROM conversation_followups
                ORDER BY position ASC, created_at DESC, id ASC
                """
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = _json_dict(row["item_json"])
            if item:
                out.append(item)
        return out
    except Exception as e:
        logger.warning("conversation_followup_sqlite get_items failed error=%s", e)
        return []
