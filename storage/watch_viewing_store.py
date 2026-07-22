"""Persistent viewing aggregates and tickets for together-watch."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unicodedata
from typing import Any
from uuid import uuid4

from config import WATCH_VISUAL_CACHE_DIR
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
    duration_ms = max(0, int(float(media.get("duration_ms") or 0)))
    raw_start = media.get("content_start_ms")
    raw_end = media.get("content_end_ms")
    content_start_ms = max(0, int(float(raw_start or 0)))
    content_end_ms = (
        max(0, int(float(raw_end)))
        if raw_end is not None and int(float(raw_end)) >= 0
        else duration_ms
    )
    return {
        "part_key": part_key,
        "media_id": media_id,
        "part_index": part_index,
        "part_count": part_count,
        "part_title": _clean_text(media.get("part_title")),
        "duration_ms": duration_ms,
        "content_start_ms": min(content_start_ms, duration_ms),
        "content_end_ms": min(content_end_ms, duration_ms),
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


def _session_progress(session_row: Any) -> dict:
    duration_ms = max(0, int(session_row["duration_ms"] or 0))
    content_start_ms = max(0, int(session_row["content_start_ms"] or 0))
    raw_content_end_ms = int(session_row["content_end_ms"] or -1)
    content_end_ms = raw_content_end_ms if raw_content_end_ms >= 0 else duration_ms
    content_end_ms = min(duration_ms, max(content_start_ms, content_end_ms))
    playhead_ms = min(duration_ms, max(0, int(session_row["playhead_ms"] or 0)))
    local_media = runtime_sqlite.json_loads(session_row["local_media_json"], {})
    if not isinstance(local_media, dict):
        local_media = {}
    return {
        "session_id": _clean_text(session_row["id"]),
        "media": {
            "id": _clean_text(session_row["media_id"]),
            "source": _clean_text(session_row["source"]),
            "url": _clean_text(session_row["source_url"]),
            "title": _clean_text(session_row["title"]),
            "part_title": _clean_text(session_row["part_title"]),
            "part_key": _clean_text(session_row["part_key"]),
            "part_index": int(session_row["part_index"] or 1),
            "part_count": int(session_row["part_count"] or 1),
            "duration_ms": duration_ms,
            "content_start_ms": content_start_ms,
            "content_end_ms": content_end_ms,
            "local_media": local_media,
        },
        "playback": {
            "playhead_ms": playhead_ms,
            "played_duration_ms": max(0, int(session_row["played_duration_ms"] or 0)),
            "timeline_epoch": max(0, int(session_row["timeline_epoch"] or 0)),
            "snapshot_seq": max(0, int(session_row["snapshot_seq"] or 0)),
            "captured_at": _clean_text(session_row["captured_at"]),
        },
        "analysis": {
            "status": _clean_text(session_row["analysis_status"]) or "pending",
            "covered_from_ms": max(0, int(session_row["analysis_covered_from_ms"] or 0)),
            "covered_until_ms": max(0, int(session_row["analysis_covered_until_ms"] or 0)),
            "retained": True,
        },
    }


def _watched_percent(progress: dict, *, completed: bool) -> int:
    if completed:
        return 100
    media = progress.get("media") if isinstance(progress.get("media"), dict) else {}
    playback = (
        progress.get("playback") if isinstance(progress.get("playback"), dict) else {}
    )
    start_ms = max(0, int(media.get("content_start_ms") or 0))
    end_ms = max(start_ms, int(media.get("content_end_ms") or media.get("duration_ms") or 0))
    playhead_ms = max(start_ms, int(playback.get("playhead_ms") or 0))
    if end_ms <= start_ms:
        return 0
    percent = round((min(playhead_ms, end_ms) - start_ms) * 100 / (end_ms - start_ms))
    return min(99, max(0, int(percent)))


def _public_ticket_frame(value: Any, *, viewing_id: str) -> dict | None:
    frame = runtime_sqlite.json_loads(value, {}) if isinstance(value, str) else value
    if not isinstance(frame, dict) or not _clean_text(frame.get("frame_id")):
        return None
    return {
        "frame_id": _clean_text(frame.get("frame_id")),
        "media_id": _clean_text(frame.get("media_id")),
        "at_ms": max(0, int(frame.get("at_ms") or 0)),
        "mime_type": _clean_text(frame.get("mime_type")) or "image/webp",
        "width": max(0, int(frame.get("width") or 0)),
        "height": max(0, int(frame.get("height") or 0)),
        "selected_at": _clean_text(frame.get("selected_at")),
        "image_url": f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame/image",
    }


def _public_ticket_frame_capture(value: Any) -> dict:
    capture = dict(value)
    viewing_id = _clean_text(capture.get("viewing_id"))
    capture_id = _clean_text(capture.get("id") or capture.get("frame_id"))
    return {
        "frame_id": capture_id,
        "media_id": _clean_text(capture.get("media_id")),
        "at_ms": max(0, int(capture.get("at_ms") or 0)),
        "width": max(0, int(capture.get("width") or 0)),
        "height": max(0, int(capture.get("height") or 0)),
        "mime_type": _clean_text(capture.get("mime_type")) or "image/jpeg",
        "image_url": (
            f"/miniapp-api/watch/viewings/{viewing_id}/"
            f"ticket-frame-captures/{capture_id}/image"
        ),
    }


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
    if _clean_text(row["status"]) == "completed" or _clean_text(row["ticket_id"]):
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
            "content_start_ms": session_row["content_start_ms"],
            "content_end_ms": session_row["content_end_ms"],
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
        final_completed_at = final_completed_at or completed_at or now_iso
    progress_json = _clean_text(row["progress_json"]) or "{}"
    if status == "saved":
        progress_json = runtime_sqlite.json_dumps(_session_progress(session_row))
        conn.execute(
            "UPDATE watch_sessions SET retained_for_resume = 1 WHERE id = ?",
            (_clean_text(session_row["id"]),),
        )
    conn.execute(
        """
        UPDATE watch_viewings
           SET part_count = ?, parts_json = ?, played_duration_ms = ?, status = ?,
               completed_at = ?, last_session_id = ?, ticket_id = ?, ticket_json = ?,
               progress_json = ?, updated_at = ?
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
            progress_json,
            now_iso,
            viewing_id,
        ),
    )


def save_progress_for_session(session_id: str, *, now_iso: str) -> dict | None:
    clean_session_id = _clean_text(session_id)
    if not clean_session_id:
        raise ValueError("session_id 不能为空")
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            session_row = conn.execute(
                "SELECT * FROM watch_sessions WHERE id = ?",
                (clean_session_id,),
            ).fetchone()
            if session_row is None:
                conn.execute("COMMIT")
                return None
            row = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (_clean_text(session_row["viewing_id"]),),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            if _clean_text(row["ticket_id"]) or _clean_text(row["status"]) == "completed":
                raise ValueError("已看完的观看记录不能再保存为续播进度")
            progress = _session_progress(session_row)
            conn.execute(
                """
                UPDATE watch_viewings
                   SET status = 'saved', progress_json = ?, saved_at = ?,
                       analysis_cache_expires_at = '', last_session_id = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    runtime_sqlite.json_dumps(progress),
                    _clean_text(now_iso),
                    clean_session_id,
                    _clean_text(now_iso),
                    _clean_text(row["id"]),
                ),
            )
            conn.execute(
                "UPDATE watch_sessions SET retained_for_resume = 1 WHERE viewing_id = ?",
                (_clean_text(row["id"]),),
            )
            saved = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (_clean_text(row["id"]),),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_viewing(saved) if saved is not None else None


def complete_viewing_for_session(
    session_id: str,
    *,
    now_iso: str,
    analysis_cache_expires_at: str,
) -> dict | None:
    clean_session_id = _clean_text(session_id)
    if not clean_session_id:
        raise ValueError("session_id 不能为空")
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT v.* FROM watch_viewings AS v
                JOIN watch_sessions AS s ON s.viewing_id = v.id
                WHERE s.id = ?
                """,
                (clean_session_id,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            existing_ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
            if (
                _clean_text(row["status"]) == "completed"
                and _clean_text(row["ticket_id"])
                and isinstance(existing_ticket, dict)
                and existing_ticket
            ):
                conn.execute("COMMIT")
                return _row_to_viewing(row)

            viewing_id = _clean_text(row["id"])
            parts = _parts(row["parts_json"])
            ticket_id = _clean_text(row["ticket_id"]) or (
                "watch_ticket_"
                + hashlib.sha256(viewing_id.encode("utf-8")).hexdigest()
            )
            playback_completed_at = _clean_text(row["completed_at"])
            ticket = dict(existing_ticket) if isinstance(existing_ticket, dict) else {}
            ticket.update(
                {
                    "ticket_id": ticket_id,
                    "viewing_id": viewing_id,
                    "work_key": _clean_text(row["work_key"]),
                    "title": _clean_text(row["title"]),
                    "cover_url": _clean_text(row["cover_url"]),
                    "companion": {
                        "id": _clean_text(row["companion_id"]),
                        "name": _clean_text(row["companion_name"]),
                    },
                    "created_at": _clean_text(ticket.get("created_at"))
                    or _clean_text(now_iso),
                    "ended_at": _clean_text(now_iso),
                    "completed_at": _clean_text(now_iso),
                    "work_completed": True,
                    "playback_completed": bool(playback_completed_at),
                    "work_completed_at": playback_completed_at or _clean_text(now_iso),
                    "played_duration_ms": int(row["played_duration_ms"] or 0),
                    "part_count": int(row["part_count"] or 1),
                    "completed_parts": [
                        {
                            "part_key": _clean_text(item.get("part_key")),
                            "media_id": _clean_text(item.get("media_id")),
                            "part_index": _positive_int(item.get("part_index"), 1),
                            "part_title": _clean_text(item.get("part_title")),
                            "played_duration_ms": int(
                                item.get("played_duration_ms") or 0
                            ),
                            "completed_at": _clean_text(item.get("completed_at")),
                            "completion_event_id": _clean_text(
                                item.get("completion_event_id")
                            ),
                            "last_session_id": _clean_text(
                                item.get("last_session_id")
                            ),
                        }
                        for item in parts
                        if _clean_text(item.get("completed_at"))
                    ],
                    "last_session_id": clean_session_id,
                    "back_frame": _public_ticket_frame(
                        row["ticket_frame_json"], viewing_id=viewing_id
                    ),
                }
            )
            conn.execute(
                """
                UPDATE watch_viewings
                   SET status = ?, last_session_id = ?, ticket_id = ?, ticket_json = ?,
                       completed_at = ?, progress_json = '{}', saved_at = '',
                       analysis_cache_expires_at = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    "completed",
                    clean_session_id,
                    ticket_id,
                    runtime_sqlite.json_dumps(ticket),
                    playback_completed_at or _clean_text(now_iso),
                    _clean_text(analysis_cache_expires_at),
                    _clean_text(now_iso),
                    viewing_id,
                ),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET retained_for_resume = 0, expires_at = ?
                 WHERE viewing_id = ?
                """,
                (_clean_text(analysis_cache_expires_at), viewing_id),
            )
            saved = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (viewing_id,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_viewing(saved) if saved is not None else None


def _row_to_viewing(row: Any) -> dict:
    if row is None:
        return {}
    viewing_id = _clean_text(row["id"])
    status = _clean_text(row["status"]) or "active"
    completed = status == "completed"
    progress = runtime_sqlite.json_loads(row["progress_json"], {})
    if not isinstance(progress, dict) or not progress:
        progress = None
    ticket_frame = _public_ticket_frame(row["ticket_frame_json"], viewing_id=viewing_id)
    ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
    if isinstance(ticket, dict) and ticket:
        ticket = dict(ticket)
        ticket["back_frame"] = ticket_frame
    else:
        ticket = None
    playback_completed = (
        bool(ticket.get("playback_completed"))
        if completed and isinstance(ticket, dict)
        else bool(_clean_text(row["completed_at"]))
    )
    watched_percent = _watched_percent(progress or {}, completed=completed)
    return {
        "viewing_id": viewing_id,
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
        "status": status,
        "completed": completed,
        "playback_completed": playback_completed,
        "recent_status": "completed" if completed else "in_progress",
        "watched_percent": watched_percent,
        "status_text": "已看完" if completed else f"已看{watched_percent}%",
        "can_resume": status == "saved" and progress is not None,
        "progress": progress,
        "saved_at": _clean_text(row["saved_at"]),
        "analysis_cache_expires_at": _clean_text(row["analysis_cache_expires_at"]),
        "ticket_back_frame": ticket_frame,
        "completed_at": _clean_text(row["completed_at"]),
        "last_session_id": _clean_text(row["last_session_id"]),
        "ticket_id": _clean_text(row["ticket_id"]),
        "ticket": ticket,
        "created_at": _clean_text(row["created_at"]),
        "updated_at": _clean_text(row["updated_at"]),
        "recent_at": (
            _clean_text(row["completed_at"])
            if completed
            else _clean_text(row["saved_at"]) or _clean_text(row["updated_at"])
        ),
    }


def saved_resume_state(conn, viewing_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM watch_viewings WHERE id = ? AND status = 'saved'",
        (_clean_text(viewing_id),),
    ).fetchone()
    if row is None or _clean_text(row["ticket_id"]):
        return None
    progress = runtime_sqlite.json_loads(row["progress_json"], {})
    if not isinstance(progress, dict) or not progress:
        return None
    return {"viewing": row, "progress": progress}


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


def list_recent_viewings(*, status: str = "recent") -> list[dict]:
    normalized = _clean_text(status).lower() or "recent"
    if normalized not in {"recent", "resumable", "completed"}:
        raise ValueError("status 必须是 recent、resumable 或 completed")
    if normalized == "resumable":
        where = "v.status = 'saved'"
    elif normalized == "completed":
        where = "v.status = 'completed'"
    else:
        where = "v.status IN ('saved', 'completed')"
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT v.* FROM watch_viewings AS v
             WHERE {where}
               AND (
                    v.status = 'completed'
                    OR NOT EXISTS (
                        SELECT 1 FROM watch_sessions AS s
                         WHERE s.viewing_id = v.id AND s.status != 'ended'
                    )
               )
             ORDER BY CASE
                        WHEN v.status = 'completed' THEN v.completed_at
                        ELSE v.saved_at
                      END DESC,
                      v.updated_at DESC
            """
        ).fetchall()
    return [_row_to_viewing(row) for row in rows]


def get_viewing_owner(viewing_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT id, created_by_device_id, source_window_id
              FROM watch_viewings
             WHERE id = ?
            """,
            (_clean_text(viewing_id),),
        ).fetchone()
    return dict(row) if row is not None else None


def create_ticket_frame_capture(
    viewing_id: str,
    *,
    session_id: str,
    media_id: str,
    timeline_epoch: int,
    at_ms: int,
    width: int,
    height: int,
    mime_type: str,
    image_bytes: bytes,
    now_iso: str,
) -> dict:
    clean_viewing_id = _clean_text(viewing_id)
    clean_session_id = _clean_text(session_id)
    clean_media_id = _clean_text(media_id)
    capture_id = f"capture_{uuid4().hex}"
    viewing_directory = hashlib.sha256(clean_viewing_id.encode("utf-8")).hexdigest()
    output_dir = (
        Path(WATCH_VISUAL_CACHE_DIR)
        / "tickets"
        / "captures"
        / viewing_directory
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{capture_id}.jpg"
    temporary_path = output_dir / f".{capture_id}.tmp"
    temporary_path.write_bytes(image_bytes)
    temporary_path.replace(target_path)
    digest = hashlib.sha256(image_bytes).hexdigest()
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                viewing = conn.execute(
                    "SELECT id FROM watch_viewings WHERE id = ?",
                    (clean_viewing_id,),
                ).fetchone()
                if viewing is None:
                    raise KeyError("watch_viewing_not_found")
                session = conn.execute(
                    """
                    SELECT id, viewing_id, media_id, timeline_epoch
                      FROM watch_sessions
                     WHERE id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()
                if session is None:
                    raise KeyError("watch_session_not_found")
                if _clean_text(session["viewing_id"]) != clean_viewing_id:
                    raise ValueError("截图不属于这次观看")
                if _clean_text(session["media_id"]) != clean_media_id:
                    raise ValueError("截图 media_id 与观看会话不一致")
                if int(session["timeline_epoch"] or 0) != int(timeline_epoch):
                    raise ValueError("截图时间轴已经失效")
                conn.execute(
                    """
                    INSERT INTO watch_ticket_frame_captures (
                        id, viewing_id, session_id, media_id, timeline_epoch,
                        at_ms, width, height, mime_type, file_path, sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        capture_id,
                        clean_viewing_id,
                        clean_session_id,
                        clean_media_id,
                        max(0, int(timeline_epoch)),
                        max(0, int(at_ms)),
                        max(0, int(width)),
                        max(0, int(height)),
                        _clean_text(mime_type) or "image/jpeg",
                        str(target_path),
                        digest,
                        _clean_text(now_iso),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM watch_ticket_frame_captures WHERE id = ?",
                    (capture_id,),
                ).fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    except Exception:
        target_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
        raise
    return _public_ticket_frame_capture(row)


def list_ticket_frame_captures(viewing_id: str) -> list[dict]:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watch_ticket_frame_captures
             WHERE viewing_id = ?
             ORDER BY created_at ASC, rowid ASC
            """,
            (_clean_text(viewing_id),),
        ).fetchall()
    return [_public_ticket_frame_capture(row) for row in rows]


def get_ticket_frame_capture(viewing_id: str, capture_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_ticket_frame_captures
             WHERE viewing_id = ? AND id = ?
            """,
            (_clean_text(viewing_id), _clean_text(capture_id)),
        ).fetchone()
    return dict(row) if row is not None else None


def ticket_frame_is_capture(frame: dict | None) -> bool:
    if not isinstance(frame, dict):
        return False
    return bool(_clean_text(frame.get("capture_id"))) or (
        _clean_text(frame.get("source")) == "user_capture"
    )


def set_ticket_frame(
    viewing_id: str,
    *,
    frame: dict,
    now_iso: str,
) -> dict | None:
    clean_viewing_id = _clean_text(viewing_id)
    if not clean_viewing_id:
        raise ValueError("viewing_id 不能为空")
    stored = {
        "frame_id": _clean_text(frame.get("frame_id")),
        "media_id": _clean_text(frame.get("media_id")),
        "at_ms": max(0, int(frame.get("at_ms") or 0)),
        "mime_type": _clean_text(frame.get("mime_type")) or "image/webp",
        "width": max(0, int(frame.get("width") or 0)),
        "height": max(0, int(frame.get("height") or 0)),
        "file_path": _clean_text(frame.get("file_path")),
        "selected_at": _clean_text(now_iso),
    }
    capture_id = _clean_text(frame.get("capture_id"))
    if capture_id:
        stored["capture_id"] = capture_id
        stored["source"] = "user_capture"
    if not stored["frame_id"] or not stored["file_path"]:
        raise ValueError("票根画面无效")
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (clean_viewing_id,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
            if isinstance(ticket, dict) and ticket:
                ticket = dict(ticket)
                ticket["back_frame"] = _public_ticket_frame(
                    stored, viewing_id=clean_viewing_id
                )
            conn.execute(
                """
                UPDATE watch_viewings
                   SET ticket_frame_json = ?, ticket_json = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    runtime_sqlite.json_dumps(stored),
                    runtime_sqlite.json_dumps(ticket if isinstance(ticket, dict) else {}),
                    _clean_text(now_iso),
                    clean_viewing_id,
                ),
            )
            saved = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (clean_viewing_id,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_viewing(saved) if saved is not None else None


def clear_ticket_frame(viewing_id: str, *, now_iso: str) -> tuple[dict | None, dict | None]:
    clean_viewing_id = _clean_text(viewing_id)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (clean_viewing_id,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None, None
            previous = runtime_sqlite.json_loads(row["ticket_frame_json"], {})
            ticket = runtime_sqlite.json_loads(row["ticket_json"], {})
            if isinstance(ticket, dict) and ticket:
                ticket = dict(ticket)
                ticket["back_frame"] = None
            conn.execute(
                """
                UPDATE watch_viewings
                   SET ticket_frame_json = '{}', ticket_json = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    runtime_sqlite.json_dumps(ticket if isinstance(ticket, dict) else {}),
                    _clean_text(now_iso),
                    clean_viewing_id,
                ),
            )
            saved = conn.execute(
                "SELECT * FROM watch_viewings WHERE id = ?",
                (clean_viewing_id,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return (
        _row_to_viewing(saved) if saved is not None else None,
        previous if isinstance(previous, dict) and previous else None,
    )


def get_ticket_frame_file(viewing_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT ticket_frame_json FROM watch_viewings WHERE id = ?",
            (_clean_text(viewing_id),),
        ).fetchone()
    if row is None:
        return None
    frame = runtime_sqlite.json_loads(row["ticket_frame_json"], {})
    return frame if isinstance(frame, dict) and frame else None


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
