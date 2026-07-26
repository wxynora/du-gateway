"""Persistent snapshot revisions for the lightweight memory organizer API."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import DYNAMIC_MEMORY_MIRROR_DB
from utils.time_aware import now_beijing_iso

_SCHEMA_LOCK = threading.Lock()
_WRITE_LOCK = threading.Lock()
_SCHEMA_PATH = ""
_CURSOR_VERSION = 1


def db_path() -> Path:
    return Path(DYNAMIC_MEMORY_MIRROR_DB)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except Exception:
        return fallback


def _connect_raw() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _connect():
    conn = _connect_raw()
    try:
        yield conn
    finally:
        conn.close()


def ensure_schema() -> None:
    global _SCHEMA_PATH
    current_path = str(db_path())
    if _SCHEMA_PATH == current_path:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_PATH == current_path:
            return
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_organizer_snapshots (
                    kind TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    item_hashes_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    item_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (kind, revision)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_organizer_snapshots_created
                    ON memory_organizer_snapshots(kind, created_at);
                """
            )
        _SCHEMA_PATH = current_path


def _item_id(item: dict) -> str:
    return str(item.get("id") or item.get("memory_id") or "").strip()


def save_snapshot(kind: str, items: list[dict], metadata: dict | None = None) -> dict:
    ensure_schema()
    clean_kind = str(kind or "").strip()
    if not clean_kind:
        raise ValueError("snapshot kind is required")

    clean_items = [dict(item) for item in items or [] if isinstance(item, dict)]
    item_hashes: dict[str, str] = {}
    for item in clean_items:
        item_id = _item_id(item)
        if not item_id:
            raise ValueError(f"{clean_kind} item is missing id")
        if item_id in item_hashes:
            raise ValueError(f"{clean_kind} contains duplicate id: {item_id}")
        item_hashes[item_id] = hashlib.sha256(_json_dumps(item).encode("utf-8")).hexdigest()

    clean_metadata = dict(metadata or {})
    canonical = _json_dumps({"items": clean_items, "metadata": clean_metadata})
    revision = "mo1_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with _WRITE_LOCK:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_organizer_snapshots(
                    kind, revision, items_json, item_hashes_json,
                    metadata_json, item_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_kind,
                    revision,
                    _json_dumps(clean_items),
                    _json_dumps(item_hashes),
                    _json_dumps(clean_metadata),
                    len(clean_items),
                    now_beijing_iso(),
                ),
            )
    return {
        "kind": clean_kind,
        "revision": revision,
        "items": clean_items,
        "item_hashes": item_hashes,
        "metadata": clean_metadata,
    }


def load_snapshot(kind: str, revision: str) -> dict | None:
    ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT kind, revision, items_json, item_hashes_json, metadata_json
            FROM memory_organizer_snapshots
            WHERE kind = ? AND revision = ?
            """,
            (str(kind or "").strip(), str(revision or "").strip()),
        ).fetchone()
    if row is None:
        return None
    return {
        "kind": str(row["kind"]),
        "revision": str(row["revision"]),
        "items": _json_loads(row["items_json"], []),
        "item_hashes": _json_loads(row["item_hashes_json"], {}),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _encode_cursor(payload: dict) -> str:
    raw = _json_dumps({"v": _CURSOR_VERSION, **payload}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict:
    clean = str(cursor or "").strip()
    if not clean:
        raise ValueError("cursor is required")
    try:
        padded = clean + ("=" * (-len(clean) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
        raise ValueError("invalid cursor")
    return payload


def cursor_kind(cursor: str) -> str:
    return str(_decode_cursor(cursor).get("kind") or "")


def _page_events(target: dict, base: dict | None, mode: str) -> list[tuple[str, Any]]:
    target_items = [item for item in target.get("items") or [] if isinstance(item, dict)]
    if mode == "snapshot":
        return [("item", item) for item in target_items]

    base_hashes = (base or {}).get("item_hashes") or {}
    target_hashes = target.get("item_hashes") or {}
    changed = [
        item
        for item in target_items
        if target_hashes.get(_item_id(item)) != base_hashes.get(_item_id(item))
    ]
    deleted = sorted(set(base_hashes) - set(target_hashes))
    return [("item", item) for item in changed] + [("deleted", item_id) for item_id in deleted]


def _build_page(
    *,
    target: dict,
    base: dict | None,
    mode: str,
    offset: int,
    limit: int,
) -> dict:
    events = _page_events(target, base, mode)
    start = max(0, int(offset or 0))
    page_size = max(1, int(limit or 1))
    selected = events[start : start + page_size]
    next_offset = start + len(selected)
    has_more = next_offset < len(events)
    next_cursor = ""
    if has_more:
        next_cursor = _encode_cursor(
            {
                "kind": target["kind"],
                "mode": mode,
                "target_revision": target["revision"],
                "base_revision": str((base or {}).get("revision") or ""),
                "offset": next_offset,
            }
        )
    return {
        "revision": target["revision"],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "items": [value for event_type, value in selected if event_type == "item"],
        "deleted_ids": [value for event_type, value in selected if event_type == "deleted"],
        "not_modified": False,
        "mode": mode,
        **dict(target.get("metadata") or {}),
    }


def start_page(
    *,
    kind: str,
    current_items: list[dict],
    metadata: dict | None,
    requested_revision: str,
    limit: int,
) -> dict:
    target = save_snapshot(kind, current_items, metadata)
    clean_revision = str(requested_revision or "").strip()
    if clean_revision == target["revision"]:
        return {
            "revision": target["revision"],
            "next_cursor": "",
            "has_more": False,
            "items": [],
            "deleted_ids": [],
            "not_modified": True,
            "mode": "not_modified",
            **dict(target.get("metadata") or {}),
        }

    base = load_snapshot(kind, clean_revision) if clean_revision else None
    mode = "delta" if base is not None else "snapshot"
    return _build_page(target=target, base=base, mode=mode, offset=0, limit=limit)


def continue_page(
    *,
    expected_kind: str,
    cursor: str,
    requested_revision: str,
    limit: int,
) -> dict:
    payload = _decode_cursor(cursor)
    kind = str(payload.get("kind") or "")
    if kind != str(expected_kind or ""):
        raise ValueError("cursor does not match endpoint")
    target_revision = str(payload.get("target_revision") or "")
    clean_requested_revision = str(requested_revision or "").strip()
    if clean_requested_revision and clean_requested_revision != target_revision:
        raise ValueError("revision does not match cursor")

    target = load_snapshot(kind, target_revision)
    if target is None:
        raise ValueError("cursor snapshot is unavailable")
    mode = str(payload.get("mode") or "")
    if mode not in {"snapshot", "delta"}:
        raise ValueError("invalid cursor mode")
    base_revision = str(payload.get("base_revision") or "")
    base = load_snapshot(kind, base_revision) if base_revision else None
    if mode == "delta" and base is None:
        raise ValueError("cursor base snapshot is unavailable")
    try:
        offset = int(payload.get("offset") or 0)
    except Exception as exc:
        raise ValueError("invalid cursor offset") from exc
    if offset < 0:
        raise ValueError("invalid cursor offset")
    return _build_page(target=target, base=base, mode=mode, offset=offset, limit=limit)
