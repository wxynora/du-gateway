"""SQLite hot mirror for schedule items and fired occurrence keys."""
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
            return conn.execute("SELECT 1 FROM schedule_items LIMIT 1").fetchone() is not None
    except Exception as e:
        logger.warning("schedule_sqlite has_items failed error=%s", e)
        return False


def replace_items(items: list[dict]) -> bool:
    rows = [dict(x) for x in (items or []) if isinstance(x, dict)]
    now = now_beijing_iso()
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("DELETE FROM schedule_items")
                    for pos, item in enumerate(rows):
                        item_id = str(item.get("id") or "").strip() or f"__legacy_{pos}"
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO schedule_items
                                (id, datetime, enabled, repeat, created_by, target_role, item_json, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                item_id,
                                str(item.get("datetime") or "").strip(),
                                1 if bool(item.get("enabled")) else 0,
                                str(item.get("repeat") or "").strip(),
                                str(item.get("created_by") or "").strip(),
                                str(item.get("target_role") or "").strip(),
                                runtime_sqlite.json_dumps(item),
                                now,
                            ),
                        )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("schedule_sqlite replace_items failed error=%s", e)
            return False


def get_items() -> list[dict]:
    try:
        with runtime_sqlite.connect() as conn:
            rows = conn.execute(
                """
                SELECT item_json
                FROM schedule_items
                ORDER BY datetime ASC, id ASC
                """
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = _json_dict(row["item_json"])
            if item:
                out.append(item)
        return out
    except Exception as e:
        logger.warning("schedule_sqlite get_items failed error=%s", e)
        return []


def has_fired_keys() -> bool:
    try:
        with runtime_sqlite.connect() as conn:
            return conn.execute("SELECT 1 FROM schedule_fired_keys LIMIT 1").fetchone() is not None
    except Exception as e:
        logger.warning("schedule_sqlite has_fired_keys failed error=%s", e)
        return False


def replace_fired_keys(keys: set[str] | list[str]) -> bool:
    clean = sorted({str(k or "").strip() for k in (keys or []) if str(k or "").strip()})
    now = now_beijing_iso()
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("DELETE FROM schedule_fired_keys")
                    for key in clean:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO schedule_fired_keys
                                (occurrence_key, created_at, updated_at)
                            VALUES (
                                ?, COALESCE((SELECT created_at FROM schedule_fired_keys WHERE occurrence_key = ?), ?), ?
                            )
                            """,
                            (key, key, now, now),
                        )
                    conn.execute("COMMIT")
                    return True
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except Exception as e:
            logger.warning("schedule_sqlite replace_fired_keys failed error=%s", e)
            return False


def get_fired_keys() -> set[str]:
    try:
        with runtime_sqlite.connect() as conn:
            rows = conn.execute("SELECT occurrence_key FROM schedule_fired_keys").fetchall()
        return {str(row["occurrence_key"] or "").strip() for row in rows if str(row["occurrence_key"] or "").strip()}
    except Exception as e:
        logger.warning("schedule_sqlite get_fired_keys failed error=%s", e)
        return set()


def add_fired_key(key: str) -> bool:
    clean = str(key or "").strip()
    if not clean:
        return False
    now = now_beijing_iso()
    with _write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schedule_fired_keys
                        (occurrence_key, created_at, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (clean, now, now),
                )
            return True
        except Exception as e:
            logger.warning("schedule_sqlite add_fired_key failed key=%s error=%s", clean, e)
            return False
