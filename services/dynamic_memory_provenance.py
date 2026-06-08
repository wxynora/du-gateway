from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import DYNAMIC_MEMORY_PROVENANCE_DB
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _db_path() -> Path:
    return Path(DYNAMIC_MEMORY_PROVENANCE_DB)


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
                CREATE TABLE IF NOT EXISTS dynamic_memory_provenance_events (
                    event_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    window_id TEXT NOT NULL DEFAULT '',
                    round_index INTEGER NOT NULL DEFAULT 0,
                    event_time TEXT NOT NULL,
                    content_before TEXT NOT NULL DEFAULT '',
                    content_after TEXT NOT NULL DEFAULT '',
                    fused_with_id TEXT NOT NULL DEFAULT '',
                    related_memory_ids_json TEXT NOT NULL DEFAULT '[]',
                    tag TEXT NOT NULL DEFAULT '',
                    importance INTEGER NOT NULL DEFAULT 0,
                    emotion_label TEXT NOT NULL DEFAULT '',
                    scene_type TEXT NOT NULL DEFAULT '',
                    target_type TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'dynamic_layer_ds',
                    round_preview TEXT NOT NULL DEFAULT '',
                    decision_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_provenance_memory_time
                    ON dynamic_memory_provenance_events(memory_id, event_time, event_id);
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_provenance_round
                    ON dynamic_memory_provenance_events(window_id, round_index);
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_provenance_action
                    ON dynamic_memory_provenance_events(action, event_time);
                """
            )
        _SCHEMA_READY = True


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _json_dumps(value: Any, *, fallback: Any, limit: int = 12000) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        raw = json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))
    return _clip(raw, limit)


def _coerce_round_index(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def record_event(
    *,
    memory_id: str,
    action: str,
    window_id: str = "",
    round_index: Any = 0,
    event_time: str = "",
    content_before: str = "",
    content_after: str = "",
    fused_with_id: str = "",
    related_memory_ids: list[str] | None = None,
    tag: str = "",
    importance: Any = 0,
    emotion_label: str = "",
    scene_type: str = "",
    target_type: str = "",
    source: str = "dynamic_layer_ds",
    round_preview: str = "",
    decision: Any = None,
) -> bool:
    mid = str(memory_id or "").strip()
    act = str(action or "").strip().lower()
    if not mid or not act:
        return False
    try:
        imp = int(importance or 0)
    except Exception:
        imp = 0
    now = now_beijing_iso()
    row = {
        "event_id": str(uuid4()),
        "memory_id": mid,
        "action": act,
        "window_id": str(window_id or "").strip(),
        "round_index": _coerce_round_index(round_index),
        "event_time": str(event_time or "").strip() or now,
        "content_before": _clip(content_before, 4000),
        "content_after": _clip(content_after, 4000),
        "fused_with_id": str(fused_with_id or "").strip(),
        "related_memory_ids_json": _json_dumps([str(x).strip() for x in (related_memory_ids or []) if str(x).strip()], fallback=[]),
        "tag": str(tag or "").strip(),
        "importance": imp,
        "emotion_label": str(emotion_label or "").strip(),
        "scene_type": str(scene_type or "").strip(),
        "target_type": str(target_type or "").strip(),
        "source": str(source or "dynamic_layer_ds").strip() or "dynamic_layer_ds",
        "round_preview": _clip(round_preview, 1000),
        "decision_json": _json_dumps(decision if decision is not None else {}, fallback={}),
        "created_at": now,
    }
    try:
        ensure_schema()
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO dynamic_memory_provenance_events (
                    event_id, memory_id, action, window_id, round_index, event_time,
                    content_before, content_after, fused_with_id, related_memory_ids_json,
                    tag, importance, emotion_label, scene_type, target_type,
                    source, round_preview, decision_json, created_at
                )
                VALUES (
                    :event_id, :memory_id, :action, :window_id, :round_index, :event_time,
                    :content_before, :content_after, :fused_with_id, :related_memory_ids_json,
                    :tag, :importance, :emotion_label, :scene_type, :target_type,
                    :source, :round_preview, :decision_json, :created_at
                )
                """,
                row,
            )
        return True
    except Exception as e:
        logger.warning("dynamic memory provenance record failed memory_id=%s action=%s error=%s", mid, act, e)
        return False


def _row_to_event(row: sqlite3.Row) -> dict:
    try:
        related = json.loads(str(row["related_memory_ids_json"] or "[]"))
    except Exception:
        related = []
    try:
        decision = json.loads(str(row["decision_json"] or "{}"))
    except Exception:
        decision = {}
    return {
        "event_id": str(row["event_id"] or ""),
        "memory_id": str(row["memory_id"] or ""),
        "action": str(row["action"] or ""),
        "window_id": str(row["window_id"] or ""),
        "round_index": int(row["round_index"] or 0),
        "event_time": str(row["event_time"] or ""),
        "content_before": str(row["content_before"] or ""),
        "content_after": str(row["content_after"] or ""),
        "fused_with_id": str(row["fused_with_id"] or ""),
        "related_memory_ids": related if isinstance(related, list) else [],
        "tag": str(row["tag"] or ""),
        "importance": int(row["importance"] or 0),
        "emotion_label": str(row["emotion_label"] or ""),
        "scene_type": str(row["scene_type"] or ""),
        "target_type": str(row["target_type"] or ""),
        "source": str(row["source"] or ""),
        "round_preview": str(row["round_preview"] or ""),
        "decision": decision if isinstance(decision, dict) else {},
        "created_at": str(row["created_at"] or ""),
    }


def list_events_for_memory(memory_id: str, limit: int = 100) -> list[dict]:
    mid = str(memory_id or "").strip()
    if not mid:
        return []
    try:
        n = int(limit or 100)
    except Exception:
        n = 100
    n = max(1, min(n, 500))
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM dynamic_memory_provenance_events
            WHERE memory_id = ?
            ORDER BY event_time ASC, event_id ASC
            LIMIT ?
            """,
            (mid, n),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def list_events_for_round(window_id: str, round_index: Any, limit: int = 100) -> list[dict]:
    wid = str(window_id or "").strip()
    idx = _coerce_round_index(round_index)
    if not wid or idx <= 0:
        return []
    try:
        n = int(limit or 100)
    except Exception:
        n = 100
    n = max(1, min(n, 500))
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM dynamic_memory_provenance_events
            WHERE window_id = ? AND round_index = ?
            ORDER BY event_time ASC, event_id ASC
            LIMIT ?
            """,
            (wid, idx, n),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def delete_events_for_memories(memory_ids: set[str] | list[str] | tuple[str, ...]) -> int:
    ids = sorted({str(x or "").strip() for x in (memory_ids or []) if str(x or "").strip()})
    if not ids:
        return 0
    ensure_schema()
    placeholders = ",".join("?" for _ in ids)
    with _connect() as conn:
        cur = conn.execute(
            f"DELETE FROM dynamic_memory_provenance_events WHERE memory_id IN ({placeholders})",
            ids,
        )
        return int(cur.rowcount or 0)
