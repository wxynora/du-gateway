from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import (
    WATCH_VISUAL_CACHE_DIR,
    WATCH_VISUAL_CONTEXT_INTERVAL_SECONDS,
    WATCH_VISUAL_FRAME_FUTURE_WINDOW_MS,
    WATCH_VISUAL_FRAME_MAX_PER_SESSION,
    WATCH_VISUAL_FRAME_PAST_WINDOW_MS,
    WATCH_VISUAL_FRAME_TTL_SECONDS,
)
from storage import runtime_sqlite


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc)


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def upsert_frame(
    *,
    frame_id: str,
    session_id: str,
    media_id: str,
    timeline_epoch: int,
    at_ms: int,
    file_path: str,
    width: int,
    height: int,
    sha256: str,
    source_sample_id: str,
) -> dict:
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(now + timedelta(seconds=int(WATCH_VISUAL_FRAME_TTL_SECONDS)))
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_visual_frames (
                id, session_id, media_id, timeline_epoch, at_ms, file_path,
                mime_type, width, height, sha256, source_sample_id, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'image/webp', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                file_path = excluded.file_path, width = excluded.width,
                height = excluded.height, sha256 = excluded.sha256,
                source_sample_id = excluded.source_sample_id, expires_at = excluded.expires_at
            """,
            (
                _text(frame_id, 160),
                _text(session_id, 160),
                _text(media_id, 240),
                max(0, int(timeline_epoch)),
                max(0, int(at_ms)),
                _text(file_path, 4000),
                max(0, int(width)),
                max(0, int(height)),
                _text(sha256, 80),
                _text(source_sample_id, 160),
                now_iso,
                expires_at,
            ),
        )
        row = conn.execute(
            "SELECT * FROM watch_visual_frames WHERE id = ?",
            (_text(frame_id, 160),),
        ).fetchone()
    return dict(row) if row is not None else {}


def list_frames(
    session_id: str,
    *,
    timeline_epoch: int,
    through_ms: int,
    from_ms: int = 0,
    limit: int = 200,
) -> list[dict]:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watch_visual_frames
             WHERE session_id = ? AND timeline_epoch = ?
               AND at_ms BETWEEN ? AND ? AND expires_at > ?
             ORDER BY at_ms, id LIMIT ?
            """,
            (
                _text(session_id, 160),
                max(0, int(timeline_epoch)),
                max(0, int(from_ms)),
                max(0, int(through_ms)),
                now_iso,
                max(1, min(1000, int(limit or 200))),
            ),
        ).fetchall()
    frames: list[dict] = []
    for row in rows:
        item = dict(row)
        path = Path(str(item.get("file_path") or ""))
        if path.is_file():
            frames.append(item)
    return frames


def get_session_frame(session_id: str, frame_id: str) -> dict | None:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_visual_frames
             WHERE id = ? AND session_id = ? AND expires_at > ?
            """,
            (_text(frame_id, 160), _text(session_id, 160), now_iso),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    return item if Path(str(item.get("file_path") or "")).is_file() else None


def persist_ticket_frame(viewing_id: str, frame: dict) -> dict:
    source_path = Path(str(frame.get("file_path") or ""))
    if not source_path.is_file():
        raise ValueError("所选剧情画面已经失效")
    clean_viewing_id = _text(viewing_id, 160)
    if not clean_viewing_id:
        raise ValueError("viewing_id 不能为空")
    digest = _text(frame.get("sha256"), 80) or source_path.stem
    output_dir = Path(WATCH_VISUAL_CACHE_DIR) / "tickets" / clean_viewing_id
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{digest}.webp"
    temporary_path = output_dir / f".{digest}.tmp"
    shutil.copyfile(source_path, temporary_path)
    temporary_path.replace(target_path)
    return {
        "frame_id": _text(frame.get("id"), 160),
        "media_id": _text(frame.get("media_id"), 240),
        "at_ms": max(0, int(frame.get("at_ms") or 0)),
        "mime_type": _text(frame.get("mime_type"), 80) or "image/webp",
        "width": max(0, int(frame.get("width") or 0)),
        "height": max(0, int(frame.get("height") or 0)),
        "file_path": str(target_path),
    }


def delete_persisted_ticket_frame(frame: dict | None) -> bool:
    if not isinstance(frame, dict):
        return False
    raw_path = str(frame.get("file_path") or "").strip()
    if not raw_path:
        return False
    path = Path(raw_path)
    ticket_root = (Path(WATCH_VISUAL_CACHE_DIR) / "tickets").resolve()
    try:
        path.resolve().relative_to(ticket_root)
    except (OSError, ValueError):
        return False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def frame_cache_status(session_id: str, *, timeline_epoch: int) -> dict:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n, MIN(at_ms) AS min_ms, MAX(at_ms) AS max_ms
              FROM watch_visual_frames
             WHERE session_id = ? AND timeline_epoch = ? AND expires_at > ?
            """,
            (_text(session_id, 160), max(0, int(timeline_epoch)), now_iso),
        ).fetchone()
    return {
        "count": int(row["n"] or 0),
        "covered_from_ms": int(row["min_ms"] or 0),
        "covered_until_ms": int(row["max_ms"] or 0),
    }


def claim_visual_delivery(
    session_id: str,
    *,
    timeline_epoch: int,
    sheet_hash: str,
) -> bool:
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_sessions WHERE id = ? AND expires_at > ?",
                (_text(session_id, 160), now_iso),
            ).fetchone()
            if row is None or str(row["status"] or "") == "ended":
                conn.execute("COMMIT")
                return False
            if int(row["timeline_epoch"] or 0) != int(timeline_epoch):
                conn.execute("COMMIT")
                return False
            last_at = _parse_iso(row["visual_last_message_at"])
            last_epoch = int(row["visual_last_message_epoch"] or -1)
            due = (
                last_at is None
                or last_epoch != int(timeline_epoch)
                or (now - last_at).total_seconds() >= int(WATCH_VISUAL_CONTEXT_INTERVAL_SECONDS)
            )
            if not due:
                conn.execute(
                    """
                    UPDATE watch_sessions
                       SET visual_last_message_at = ?, visual_last_message_epoch = ?,
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (now_iso, int(timeline_epoch), now_iso, session_id),
                )
                conn.execute("COMMIT")
                return False
            conn.execute(
                """
                UPDATE watch_sessions
                   SET visual_last_message_at = ?, visual_last_message_epoch = ?,
                       visual_last_sent_at = ?, visual_last_timeline_epoch = ?,
                       visual_last_sheet_hash = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    now_iso,
                    int(timeline_epoch),
                    now_iso,
                    int(timeline_epoch),
                    _text(sheet_hash, 80),
                    now_iso,
                    session_id,
                ),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _delete_frame_rows(conn, rows: list[Any]) -> dict:
    deleted_ids: list[str] = []
    deleted_files = 0
    for row in rows:
        frame_id = str(row["id"] or "").strip()
        if not frame_id:
            continue
        path = Path(str(row["file_path"] or ""))
        try:
            if path.is_file():
                path.unlink()
                deleted_files += 1
        except OSError:
            continue
        deleted_ids.append(frame_id)
    if deleted_ids:
        placeholders = ",".join("?" for _ in deleted_ids)
        conn.execute(
            f"DELETE FROM watch_visual_frames WHERE id IN ({placeholders})",
            deleted_ids,
        )
    return {"rows_deleted": len(deleted_ids), "files_deleted": deleted_files}


def delete_session_frames(session_id: str) -> dict:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            "SELECT id, file_path FROM watch_visual_frames WHERE session_id = ?",
            (_text(session_id, 160),),
        ).fetchall()
        return _delete_frame_rows(conn, list(rows))


def prune_session_frames(
    session_id: str,
    *,
    timeline_epoch: int,
    playhead_ms: int,
) -> dict:
    epoch = max(0, int(timeline_epoch))
    playhead = max(0, int(playhead_ms))
    keep_from = max(0, playhead - int(WATCH_VISUAL_FRAME_PAST_WINDOW_MS))
    keep_until = playhead + int(WATCH_VISUAL_FRAME_FUTURE_WINDOW_MS)
    max_frames = max(1, int(WATCH_VISUAL_FRAME_MAX_PER_SESSION))
    with runtime_sqlite.connect() as conn:
        rows = list(
            conn.execute(
                "SELECT id, file_path, timeline_epoch, at_ms FROM watch_visual_frames WHERE session_id = ?",
                (_text(session_id, 160),),
            ).fetchall()
        )
        to_delete = [
            row
            for row in rows
            if int(row["timeline_epoch"] or 0) != epoch
            or int(row["at_ms"] or 0) < keep_from
            or int(row["at_ms"] or 0) > keep_until
        ]
        delete_ids = {str(row["id"] or "") for row in to_delete}
        retained = [row for row in rows if str(row["id"] or "") not in delete_ids]
        if len(retained) > max_frames:
            retained.sort(
                key=lambda row: (
                    abs(int(row["at_ms"] or 0) - playhead),
                    int(row["at_ms"] or 0),
                    str(row["id"] or ""),
                )
            )
            to_delete.extend(retained[max_frames:])
        deleted = _delete_frame_rows(conn, to_delete)
    return {
        **deleted,
        "retained": max(0, len(rows) - int(deleted["rows_deleted"])),
        "keep_from_ms": keep_from,
        "keep_until_ms": keep_until,
        "max_frames": max_frames,
    }


def cleanup_expired_frames() -> dict:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            "SELECT id, file_path FROM watch_visual_frames WHERE expires_at <= ?",
            (now_iso,),
        ).fetchall()
        return _delete_frame_rows(conn, list(rows))
