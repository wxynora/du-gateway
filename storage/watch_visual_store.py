from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import WATCH_VISUAL_CONTEXT_INTERVAL_SECONDS, WATCH_VISUAL_FRAME_TTL_SECONDS
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


def cleanup_expired_frames() -> dict:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            "SELECT id, file_path FROM watch_visual_frames WHERE expires_at <= ?",
            (now_iso,),
        ).fetchall()
        deleted_files = 0
        for row in rows:
            path = Path(str(row["file_path"] or ""))
            if path.exists():
                try:
                    path.unlink()
                    deleted_files += 1
                except OSError:
                    pass
        result = conn.execute(
            "DELETE FROM watch_visual_frames WHERE expires_at <= ?",
            (now_iso,),
        )
    return {"rows_deleted": int(result.rowcount or 0), "files_deleted": deleted_files}
