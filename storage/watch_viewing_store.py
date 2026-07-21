"""Persistent viewing aggregates and tickets for together-watch."""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any
from uuid import uuid4

from storage import runtime_sqlite


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _positive_int(value: Any, default: int = 1) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def derive_work_key(media: dict) -> str:
    supplied = _clean_text(media.get("work_key"))
    if supplied:
        return supplied
    source = _clean_text(media.get("source")).casefold()
    title = unicodedata.normalize("NFKC", _clean_text(media.get("title"))).casefold()
    normalized_title = "".join(char for char in title if char.isalnum())
    identity = f"{source}:{normalized_title or _clean_text(media.get('id'))}"
    return f"watch_work_{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def normalize_part(media: dict) -> dict:
    part_count = _positive_int(media.get("part_count"), 1)
    part_index = _positive_int(media.get("part_index"), 1)
    if part_index > part_count:
        raise ValueError("media.part_index 不能大于 media.part_count")
    media_id = _clean_text(media.get("id"))
    part_key = _clean_text(media.get("part_key")) or media_id
    return {
        "part_key": part_key,
        "media_id": media_id,
        "part_index": part_index,
        "part_count": part_count,
        "part_title": _clean_text(media.get("part_title")),
        "duration_ms": max(0, int(float(media.get("duration_ms") or 0))),
    }


def _parts(value: Any) -> list[dict]:
    parsed = runtime_sqlite.json_loads(value, []) if isinstance(value, str) else value
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _merge_part(parts: list[dict], incoming: dict) -> list[dict]:
    merged = [dict(item) for item in parts]
    match_index = next(
        (
            index
            for index, item in enumerate(merged)
            if _clean_text(item.get("part_key")) == _clean_text(incoming.get("part_key"))
        ),
        -1,
    )
    if match_index < 0:
        merged.append(
            {
                **incoming,
                "played_duration_ms": 0,
                "completed_at": "",
                "completion_event_id": "",
                "last_session_id": "",
            }
        )
    else:
        current = merged[match_index]
        merged[match_index] = {
            **current,
            **incoming,
            "played_duration_ms": int(current.get("played_duration_ms") or 0),
            "completed_at": _clean_text(current.get("completed_at")),
            "completion_event_id": _clean_text(current.get("completion_event_id")),
            "last_session_id": _clean_text(current.get("last_session_id")),
        }
    return sorted(
        merged,
        key=lambda item: (
            _positive_int(item.get("part_index"), 1),
            _clean_text(item.get("part_key")),
        ),
    )


def ensure_viewing(
    conn,
    *,
    requested_viewing_id: str,
    work_key: str,
    media: dict,
    companion_id: str,
    companion_name: str,
    device_id: str,
    window_id: str,
    now_iso: str,
) -> str:
    viewing_id = _clean_text(requested_viewing_id) or f"watch_viewing_{uuid4().hex}"
    part = normalize_part(media)
    row = conn.execute("SELECT * FROM watch_viewings WHERE id = ?", (viewing_id,)).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO watch_viewings (
                id, work_key, title, cover_url, companion_id, companion_name,
                created_by_device_id, source_window_id, part_count, parts_json,
                played_duration_ms, status, completed_at, last_session_id,
                ticket_id, ticket_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', '', '', '', '{}', ?, ?)
            """,
            (
                viewing_id,
                work_key,
                _clean_text(media.get("title")),
                _clean_text(media.get("cover_url")),
                companion_id,
                companion_name,
                device_id,
                window_id,
                int(part["part_count"]),
                runtime_sqlite.json_dumps(_merge_part([], part)),
                now_iso,
                now_iso,
            ),
        )
        return viewing_id

    if _clean_text(row["work_key"]) != work_key:
        raise ValueError("viewing_id 已属于其他作品")
    if _clean_text(row["status"]) in {"completed", "finalized"}:
        raise ValueError("这次一起看已经结束，请创建新的 viewing_id")
    parts = _merge_part(_parts(row["parts_json"]), part)
    conn.execute(
        """
        UPDATE watch_viewings
           SET part_count = ?, parts_json = ?, title = ?, cover_url = ?,
               updated_at = ?
         WHERE id = ?
        """,
        (
            max(int(row["part_count"] or 1), int(part["part_count"])),
            runtime_sqlite.json_dumps(parts),
            _clean_text(row["title"]) or _clean_text(media.get("title")),
            _clean_text(row["cover_url"]) or _clean_text(media.get("cover_url")),
            now_iso,
            viewing_id,
        ),
    )
    return viewing_id


def record_session_progress(
    conn,
    *,
    session_row: Any,
    played_delta_ms: int,
    completed_at: str,
    completion_event_id: str,
    now_iso: str,
) -> None:
    viewing_id = _clean_text(session_row["viewing_id"])
    if not viewing_id:
        return
    row = conn.execute("SELECT * FROM watch_viewings WHERE id = ?", (viewing_id,)).fetchone()
    if row is None or _clean_text(row["ticket_id"]):
        return

    part = normalize_part(
        {
            "id": session_row["media_id"],
            "part_key": session_row["part_key"],
            "part_index": session_row["part_index"],
            "part_count": session_row["part_count"],
            "part_title": session_row["part_title"],
            "duration_ms": session_row["duration_ms"],
        }
    )
    parts = _merge_part(_parts(row["parts_json"]), part)
    for item in parts:
        if _clean_text(item.get("part_key")) != _clean_text(part["part_key"]):
            continue
        item["played_duration_ms"] = int(item.get("played_duration_ms") or 0) + max(
            0, int(played_delta_ms or 0)
        )
        item["last_session_id"] = _clean_text(session_row["id"])
        if completed_at and not _clean_text(item.get("completed_at")):
            item["completed_at"] = completed_at
            item["completion_event_id"] = completion_event_id
        break

    played_duration_ms = int(row["played_duration_ms"] or 0) + max(
        0, int(played_delta_ms or 0)
    )
    part_count = max(int(row["part_count"] or 1), int(part["part_count"]))
    completed_indexes = {
        _positive_int(item.get("part_index"), 1)
        for item in parts
        if _clean_text(item.get("completed_at"))
    }
    viewing_completed = len(completed_indexes) >= part_count
    final_completed_at = _clean_text(row["completed_at"])
    status = _clean_text(row["status"]) or "active"
    if viewing_completed:
        status = "completed"
        final_completed_at = final_completed_at or completed_at or now_iso
    conn.execute(
        """
        UPDATE watch_viewings
           SET part_count = ?, parts_json = ?, played_duration_ms = ?, status = ?,
               completed_at = ?, last_session_id = ?, ticket_id = ?, ticket_json = ?,
               updated_at = ?
         WHERE id = ?
        """,
        (
            part_count,
            runtime_sqlite.json_dumps(parts),
            played_duration_ms,
            status,
            final_completed_at,
            _clean_text(session_row["id"]),
            _clean_text(row["ticket_id"]),
            _clean_text(row["ticket_json"]) or "{}",
            now_iso,
            viewing_id,
        ),
    )


def finalize_viewing_for_session(session_id: str, *, now_iso: str) -> dict | None:
    clean_session_id = _clean_text(session_id)
    if not clean_session_id:
        raise ValueError("session_id 不能为空")
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT v.* FROM watch_viewings AS v
            JOIN watch_sessions AS s ON s.viewing_id = v.id
            WHERE s.id = ?
            """,
            (clean_session_id,),
        ).fetchone()
        if row is None:
            return None
        existing_ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
        if _clean_text(row["ticket_id"]) and isinstance(existing_ticket, dict) and existing_ticket:
            return _row_to_viewing(row)

        viewing_id = _clean_text(row["id"])
        parts = _parts(row["parts_json"])
        ticket_id = "watch_ticket_" + hashlib.sha256(viewing_id.encode("utf-8")).hexdigest()
        work_completed = _clean_text(row["status"]) == "completed"
        ticket = {
            "ticket_id": ticket_id,
            "viewing_id": viewing_id,
            "work_key": _clean_text(row["work_key"]),
            "title": _clean_text(row["title"]),
            "cover_url": _clean_text(row["cover_url"]),
            "companion": {
                "id": _clean_text(row["companion_id"]),
                "name": _clean_text(row["companion_name"]),
            },
            "created_at": _clean_text(now_iso),
            "ended_at": _clean_text(now_iso),
            "completed_at": _clean_text(now_iso),
            "work_completed": work_completed,
            "work_completed_at": _clean_text(row["completed_at"]),
            "played_duration_ms": int(row["played_duration_ms"] or 0),
            "part_count": int(row["part_count"] or 1),
            "completed_parts": [
                {
                    "part_key": _clean_text(item.get("part_key")),
                    "media_id": _clean_text(item.get("media_id")),
                    "part_index": _positive_int(item.get("part_index"), 1),
                    "part_title": _clean_text(item.get("part_title")),
                    "played_duration_ms": int(item.get("played_duration_ms") or 0),
                    "completed_at": _clean_text(item.get("completed_at")),
                    "completion_event_id": _clean_text(item.get("completion_event_id")),
                    "last_session_id": _clean_text(item.get("last_session_id")),
                }
                for item in parts
                if _clean_text(item.get("completed_at"))
            ],
            "last_session_id": clean_session_id,
        }
        status = "completed" if work_completed else "finalized"
        conn.execute(
            """
            UPDATE watch_viewings
               SET status = ?, last_session_id = ?, ticket_id = ?, ticket_json = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (
                status,
                clean_session_id,
                ticket_id,
                runtime_sqlite.json_dumps(ticket),
                _clean_text(now_iso),
                viewing_id,
            ),
        )
        saved = conn.execute(
            "SELECT * FROM watch_viewings WHERE id = ?",
            (viewing_id,),
        ).fetchone()
    return _row_to_viewing(saved) if saved is not None else None


def _row_to_viewing(row: Any) -> dict:
    if row is None:
        return {}
    ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
    return {
        "viewing_id": _clean_text(row["id"]),
        "work_key": _clean_text(row["work_key"]),
        "title": _clean_text(row["title"]),
        "cover_url": _clean_text(row["cover_url"]),
        "companion": {
            "id": _clean_text(row["companion_id"]),
            "name": _clean_text(row["companion_name"]),
        },
        "part_count": int(row["part_count"] or 1),
        "parts": _parts(row["parts_json"]),
        "played_duration_ms": int(row["played_duration_ms"] or 0),
        "status": _clean_text(row["status"]) or "active",
        "completed": _clean_text(row["status"]) == "completed",
        "completed_at": _clean_text(row["completed_at"]),
        "last_session_id": _clean_text(row["last_session_id"]),
        "ticket_id": _clean_text(row["ticket_id"]),
        "ticket": ticket if isinstance(ticket, dict) and ticket else None,
        "created_at": _clean_text(row["created_at"]),
        "updated_at": _clean_text(row["updated_at"]),
    }


def get_viewing(viewing_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_viewings WHERE id = ?",
            (_clean_text(viewing_id),),
        ).fetchone()
    return _row_to_viewing(row) if row is not None else None


def get_for_session(session_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT v.* FROM watch_viewings AS v
            JOIN watch_sessions AS s ON s.viewing_id = v.id
            WHERE s.id = ?
            """,
            (_clean_text(session_id),),
        ).fetchone()
    return _row_to_viewing(row) if row is not None else None


def get_by_ticket_id(ticket_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_viewings
             WHERE ticket_id = ?
            """,
            (_clean_text(ticket_id),),
        ).fetchone()
    return _row_to_viewing(row) if row is not None else None


def update_ticket_title(
    ticket_id: str,
    *,
    title: str,
    now_iso: str,
    stay_with_du_entry: dict | None = None,
) -> dict | None:
    clean_ticket_id = _clean_text(ticket_id)
    clean_title = _clean_text(title)
    if not clean_ticket_id or not clean_title:
        raise ValueError("票根作品名不能为空")
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_viewings
             WHERE ticket_id = ?
            """,
            (clean_ticket_id,),
        ).fetchone()
        if row is None:
            return None
        ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
        if not isinstance(ticket, dict) or not ticket:
            return None
        ticket["title"] = clean_title
        if isinstance(stay_with_du_entry, dict):
            ticket["stay_with_du"] = {
                "entry_id": _clean_text(stay_with_du_entry.get("id")),
                "archived_at": _clean_text(now_iso),
            }
        conn.execute(
            """
            UPDATE watch_viewings
               SET title = ?, ticket_json = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                clean_title,
                runtime_sqlite.json_dumps(ticket),
                _clean_text(now_iso),
                _clean_text(row["id"]),
            ),
        )
        saved = conn.execute(
            "SELECT * FROM watch_viewings WHERE id = ?",
            (_clean_text(row["id"]),),
        ).fetchone()
    return _row_to_viewing(saved) if saved is not None else None


def list_tickets() -> list[dict]:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watch_viewings
             WHERE ticket_id != ''
             ORDER BY updated_at DESC
            """
        ).fetchall()
    return [_row_to_viewing(row) for row in rows]
