"""Local runtime state for together-watch sessions.

The watch feature deliberately keeps analysis and playback state in the local
runtime database. Nothing in this module reads from or writes to R2.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from config import (
    WATCH_ANALYSIS_FEAR_READY_BUFFER_MS,
    WATCH_ANALYSIS_PROMPT_VERSION,
    WATCH_CONTEXT_REPLY_LEAD_MS,
)
from storage import runtime_sqlite


ACTIVE_TTL = timedelta(hours=24)
ENDED_TTL = timedelta(hours=6)
DEFAULT_ANALYSIS_MODEL = "google/gemini-2.5-flash"
DEFAULT_PROMPT_VERSION = WATCH_ANALYSIS_PROMPT_VERSION

KNOWLEDGE_MODES = {"known", "needs_summary"}
FEAR_ACTIONS = {"warn_only", "cover_video"}
VISUAL_CONTEXT_MODES = {"text_only", "text_plus_contact_sheet"}
PREPARATION_STATUSES = {
    "identifying",
    "collecting_sources",
    "building_card",
    "searching_subtitles",
    "ready_to_confirm",
    "knowledge_failed",
    "confirmed",
}
SESSION_STATUSES = {"paused", "playing", "ended"}
ANALYSIS_STATUSES = {
    "pending",
    "warming_context",
    "analyzing",
    "ready",
    "degraded",
    "failed",
}
TIMELINE_SECTION_KINDS = {
    "recap",
    "cold_open",
    "intro",
    "content",
    "credits_over_story",
    "outro",
    "preview",
    "post_credit",
    "non_story",
    "unknown",
}
RISK_FEEDBACK_TYPES = {"false_positive", "missed", "too_early", "too_late"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, limit: int = 500) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _int(value: Any, default: int = 0, *, minimum: int = 0) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _enum(value: Any, allowed: set[str], default: str, field: str) -> str:
    normalized = _text(value, 80).lower() or default
    if normalized not in allowed:
        raise ValueError(f"{field} 无效")
    return normalized


def _optional_media_ms(value: Any, field: str) -> int:
    if value is None or str(value).strip() == "":
        return -1
    try:
        parsed = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是非负毫秒整数") from exc
    if parsed < 0:
        raise ValueError(f"{field} 必须是非负毫秒整数")
    return parsed


def _ensure_content_bound_sections(
    conn,
    *,
    session_id: str,
    timeline_epoch: int,
    duration_ms: int,
    content_start_ms: int,
    content_end_ms: int,
    now_iso: str,
) -> None:
    sections: list[tuple[str, str, int, int]] = []
    if content_start_ms > 0:
        sections.append(("content_start", "non_story", 0, content_start_ms))
    if 0 <= content_end_ms < duration_ms:
        sections.append(("content_end", "outro", content_end_ms, duration_ms))
    for suffix, kind, start_ms, end_ms in sections:
        conn.execute(
            """
            INSERT OR REPLACE INTO watch_timeline_sections (
                id, session_id, timeline_epoch, kind, start_ms, end_ms,
                source, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'manual', 1.0, ?, ?)
            """,
            (
                f"watch_section_{session_id}_{timeline_epoch}_{suffix}",
                session_id,
                int(timeline_epoch),
                kind,
                int(start_ms),
                int(end_ms),
                now_iso,
                now_iso,
            ),
        )


def _cleanup_expired(conn, now_iso: str) -> int:
    rows = conn.execute(
        "SELECT id FROM watch_sessions WHERE expires_at <= ?",
        (now_iso,),
    ).fetchall()
    session_ids = [str(row["id"]) for row in rows]
    for session_id in session_ids:
        frame_rows = conn.execute(
            "SELECT file_path FROM watch_visual_frames WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        for frame_row in frame_rows:
            file_path = str(frame_row["file_path"] or "").strip()
            if file_path:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except Exception:
                    pass
        sample_rows = conn.execute(
            "SELECT file_path FROM watch_analysis_samples WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        for sample_row in sample_rows:
            file_path = str(sample_row["file_path"] or "").strip()
            if file_path:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except Exception:
                    pass
        conn.execute("DELETE FROM watch_risk_feedback WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_risk_events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_plot_chunks WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_timeline_sections WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_story_checkpoints WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_subtitle_assets WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_visual_frames WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_analysis_samples WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_analysis_jobs WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_sessions WHERE id = ?", (session_id,))
    conn.execute("DELETE FROM watch_knowledge_cards WHERE expires_at <= ?", (now_iso,))
    return len(session_ids)


def cleanup_expired_sessions() -> int:
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            count = _cleanup_expired(conn, _iso(_now()))
            conn.execute("COMMIT")
            return count
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _row_to_session(row: Any) -> dict:
    if row is None:
        return {}
    subtitle_lookup = runtime_sqlite.json_loads(row["subtitle_lookup_json"], {})
    if not isinstance(subtitle_lookup, dict) or not subtitle_lookup:
        subtitle_lookup = {
            "lookup_id": "",
            "status": "pending",
            "provider": "",
            "query_title": "",
            "language_codes": [],
            "release_name": "",
            "format": "",
            "cue_count": 0,
            "coverage_start_ms": 0,
            "coverage_end_ms": 0,
            "message": "等待作品身份",
            "error": "",
            "can_retry": False,
        }
    else:
        subtitle_lookup = {
            key: value
            for key, value in subtitle_lookup.items()
            if not str(key).startswith("_")
        }
    return {
        "session_id": str(row["id"] or ""),
        "device_id": str(row["device_id"] or ""),
        "window_id": str(row["window_id"] or ""),
        "companion": {
            "id": str(row["companion_id"] or ""),
            "name": str(row["companion_name"] or ""),
        },
        "media": {
            "id": str(row["media_id"] or ""),
            "source": str(row["source"] or ""),
            "url": str(row["source_url"] or ""),
            "title": str(row["title"] or ""),
            "part_title": str(row["part_title"] or ""),
            "duration_ms": int(row["duration_ms"] or 0),
            "content_start_ms": (
                int(row["content_start_ms"])
                if int(row["content_start_ms"]) >= 0
                else None
            ),
            "content_end_ms": (
                int(row["content_end_ms"])
                if int(row["content_end_ms"]) >= 0
                else None
            ),
        },
        "mode": {
            "knowledge_mode": str(row["knowledge_mode"] or "known"),
            "fear_mode": bool(row["fear_mode"]),
            "fear_action": str(row["fear_action"] or "warn_only"),
            "reduce_volume": bool(row["reduce_volume"]),
            "danmaku_enabled": bool(row["danmaku_enabled"]),
            "force_unknown_analysis": bool(row["force_unknown_analysis"]),
            "reply_lead_ms": int(row["reply_lead_ms"] or 0),
            "visual_context_mode": str(row["visual_context_mode"] or "text_only"),
        },
        "preparation": {
            "status": str(row["preparation_status"] or "identifying"),
            "knowledge_card_key": str(row["knowledge_card_key"] or ""),
            "knowledge_card_status": str(row["knowledge_card_status"] or "pending"),
            "knowledge_card_error": str(row["knowledge_card_error"] or ""),
            "knowledge_card_confirmed_at": str(row["knowledge_card_confirmed_at"] or ""),
            "knowledge_card_skipped_at": str(row["knowledge_card_skipped_at"] or ""),
            "subtitle_lookup": subtitle_lookup,
            "subtitle_confirmed_at": str(row["subtitle_confirmed_at"] or ""),
            "started_at": str(row["started_at"] or ""),
        },
        "playback": {
            "status": str(row["status"] or "paused"),
            "playhead_ms": int(row["playhead_ms"] or 0),
            "is_playing": bool(row["is_playing"]),
            "playback_rate": float(row["playback_rate"] or 1.0),
            "timeline_epoch": int(row["timeline_epoch"] or 0),
            "snapshot_seq": int(row["snapshot_seq"] or 0),
            "captured_at": str(row["captured_at"] or ""),
        },
        "analysis": {
            "familiarity": str(row["analysis_familiarity"] or "pending"),
            "identity": str(row["analysis_identity"] or ""),
            "original_title": str(row["analysis_original_title"] or ""),
            "year": int(row["analysis_year"] or 0),
            "model": str(row["analysis_model"] or DEFAULT_ANALYSIS_MODEL),
            "prompt_version": str(row["analysis_prompt_version"] or DEFAULT_PROMPT_VERSION),
            "status": str(row["analysis_status"] or "pending"),
            "covered_from_ms": int(row["analysis_covered_from_ms"] or 0),
            "covered_until_ms": int(row["analysis_covered_until_ms"] or 0),
            "error": str(row["analysis_error"] or ""),
            "story_so_far": runtime_sqlite.json_loads(row["story_so_far_json"], {}),
            "story_state": runtime_sqlite.json_loads(row["analysis_story_state_json"], {}),
        },
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "ended_at": str(row["ended_at"] or ""),
        "expires_at": str(row["expires_at"] or ""),
    }


def _get_session_row(conn, session_id: str) -> Any:
    return conn.execute(
        "SELECT * FROM watch_sessions WHERE id = ? AND expires_at > ?",
        (_text(session_id, 120), _iso(_now())),
    ).fetchone()


def get_session(session_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        _cleanup_expired(conn, _iso(_now()))
        row = _get_session_row(conn, session_id)
        return _row_to_session(row) if row is not None else None


def list_sessions(
    *,
    device_id: str = "",
    window_id: str = "",
    include_ended: bool = False,
    limit: int = 20,
) -> list[dict]:
    clauses = ["expires_at > ?"]
    params: list[Any] = [_iso(_now())]
    if device_id:
        clauses.append("device_id = ?")
        params.append(_text(device_id, 160))
    if window_id:
        clauses.append("window_id = ?")
        params.append(_text(window_id, 160))
    if not include_ended:
        clauses.append("status != 'ended'")
    params.append(max(1, min(100, int(limit or 20))))
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM watch_sessions WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC LIMIT ?",
            params,
        ).fetchall()
    return [_row_to_session(row) for row in rows]


def create_session(
    *,
    device_id: str,
    window_id: str,
    companion: dict,
    media: dict,
    mode: dict,
) -> dict:
    media_id = _text(media.get("id"), 240)
    if not media_id:
        raise ValueError("media.id 不能为空")
    source = _text(media.get("source"), 80)
    if not source:
        raise ValueError("media.source 不能为空")
    duration_ms = _int(media.get("duration_ms"), 0)
    if duration_ms <= 0:
        raise ValueError("media.duration_ms 必须大于 0")
    content_start_ms = _optional_media_ms(media.get("content_start_ms"), "media.content_start_ms")
    content_end_ms = _optional_media_ms(media.get("content_end_ms"), "media.content_end_ms")
    if content_start_ms >= duration_ms:
        raise ValueError("media.content_start_ms 必须小于媒体时长")
    if content_end_ms > duration_ms:
        raise ValueError("media.content_end_ms 不能超过媒体时长")
    if content_end_ms == 0:
        raise ValueError("media.content_end_ms 必须大于 0")
    if content_start_ms >= 0 and content_end_ms >= 0 and content_start_ms >= content_end_ms:
        raise ValueError("media.content_start_ms 必须早于 content_end_ms")

    knowledge_mode = _enum(
        mode.get("knowledge_mode"), KNOWLEDGE_MODES, "known", "mode.knowledge_mode"
    )
    fear_action = _enum(mode.get("fear_action"), FEAR_ACTIONS, "warn_only", "mode.fear_action")
    visual_context_mode = _enum(
        mode.get("visual_context_mode"),
        VISUAL_CONTEXT_MODES,
        "text_only",
        "mode.visual_context_mode",
    )
    reply_lead_ms = _int(mode.get("reply_lead_ms"), int(WATCH_CONTEXT_REPLY_LEAD_MS))
    if reply_lead_ms > 120_000:
        raise ValueError("mode.reply_lead_ms 必须在 0 到 120000 之间")
    force_unknown = _bool(mode.get("force_unknown_analysis"))
    if force_unknown:
        knowledge_mode = "needs_summary"

    now = _now()
    now_iso = _iso(now)
    session_id = f"watch_{uuid4().hex}"
    values = (
        session_id,
        _text(device_id, 160),
        _text(window_id, 160),
        _text(companion.get("id"), 120) or "du",
        _text(companion.get("name"), 80) or "渡",
        media_id,
        source,
        _text(media.get("url"), 4000),
        _text(media.get("title"), 300),
        _text(media.get("part_title"), 300),
        duration_ms,
        content_start_ms,
        content_end_ms,
        knowledge_mode,
        _text(mode.get("analysis_model"), 160) or DEFAULT_ANALYSIS_MODEL,
        _text(mode.get("analysis_prompt_version"), 80) or DEFAULT_PROMPT_VERSION,
        int(force_unknown),
        int(_bool(mode.get("fear_mode"))),
        fear_action,
        int(_bool(mode.get("reduce_volume"))),
        int(_bool(mode.get("danmaku_enabled"), True)),
        reply_lead_ms,
        visual_context_mode,
        now_iso,
        now_iso,
        _iso(now + ACTIVE_TTL),
    )
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _cleanup_expired(conn, now_iso)
            conn.execute(
                """
                INSERT INTO watch_sessions (
                    id, device_id, window_id, companion_id, companion_name,
                    media_id, source, source_url, title, part_title, duration_ms,
                    content_start_ms, content_end_ms,
                    knowledge_mode, analysis_model, analysis_prompt_version,
                    force_unknown_analysis, fear_mode, fear_action, reduce_volume,
                    danmaku_enabled, reply_lead_ms, visual_context_mode,
                    created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            _ensure_content_bound_sections(
                conn,
                session_id=session_id,
                timeline_epoch=0,
                duration_ms=duration_ms,
                content_start_ms=content_start_ms,
                content_end_ms=content_end_ms,
                now_iso=now_iso,
            )
            row = _get_session_row(conn, session_id)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_session(row)


def update_playback(session_id: str, snapshot: dict) -> tuple[dict, bool, str]:
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _get_session_row(conn, session_id)
            if row is None:
                raise KeyError("watch_session_not_found")
            if str(row["status"] or "") == "ended":
                raise ValueError("观看会话已结束")
            media_id = _text(snapshot.get("media_id"), 240)
            if media_id and media_id != str(row["media_id"] or ""):
                raise ValueError("media_id 与观看会话不一致")

            incoming_epoch = _int(snapshot.get("timeline_epoch"), 0)
            incoming_seq = _int(snapshot.get("snapshot_seq"), 0)
            current_epoch = int(row["timeline_epoch"] or 0)
            current_seq = int(row["snapshot_seq"] or 0)
            if incoming_epoch < current_epoch:
                conn.execute("COMMIT")
                return _row_to_session(row), False, "stale_timeline_epoch"
            if incoming_epoch == current_epoch and incoming_seq <= current_seq:
                conn.execute("COMMIT")
                return _row_to_session(row), False, "stale_snapshot_seq"

            duration_ms = _int(snapshot.get("duration_ms"), int(row["duration_ms"] or 0))
            playhead_ms = _int(snapshot.get("playhead_ms"), int(row["playhead_ms"] or 0))
            if duration_ms > 0:
                playhead_ms = min(playhead_ms, duration_ms)
            is_playing = _bool(snapshot.get("is_playing"))
            if is_playing and not str(row["started_at"] or "").strip():
                raise ValueError("请先确认开播前资料，再正式开始一起看")
            playback_rate = min(4.0, max(0.25, _float(snapshot.get("playback_rate"), 1.0)))
            captured_at = _text(snapshot.get("captured_at"), 80) or now_iso
            status = "playing" if is_playing else "paused"
            conn.execute(
                """
                UPDATE watch_sessions
                   SET duration_ms = ?, playhead_ms = ?, is_playing = ?, playback_rate = ?,
                       timeline_epoch = ?, snapshot_seq = ?, captured_at = ?, status = ?,
                       updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    duration_ms,
                    playhead_ms,
                    int(is_playing),
                    playback_rate,
                    incoming_epoch,
                    incoming_seq,
                    captured_at,
                    status,
                    now_iso,
                    _iso(now + ACTIVE_TTL),
                    session_id,
                ),
            )
            if incoming_epoch > current_epoch:
                _ensure_content_bound_sections(
                    conn,
                    session_id=session_id,
                    timeline_epoch=incoming_epoch,
                    duration_ms=duration_ms,
                    content_start_ms=int(row["content_start_ms"]),
                    content_end_ms=int(row["content_end_ms"]),
                    now_iso=now_iso,
                )
            updated = _get_session_row(conn, session_id)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_session(updated), True, ""


def update_mode(session_id: str, changes: dict) -> dict:
    allowed = {
        "knowledge_mode",
        "fear_mode",
        "fear_action",
        "reduce_volume",
        "danmaku_enabled",
        "force_unknown_analysis",
        "reply_lead_ms",
        "visual_context_mode",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"不支持的 mode 字段: {', '.join(sorted(unknown))}")
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _get_session_row(conn, session_id)
            if row is None:
                raise KeyError("watch_session_not_found")
            old_force_unknown = bool(row["force_unknown_analysis"])
            if str(row["started_at"] or "").strip() and "force_unknown_analysis" in changes:
                raise ValueError("按陌生作品分析只能在正式开始前选择")
            knowledge_mode = _enum(
                changes.get("knowledge_mode", row["knowledge_mode"]),
                KNOWLEDGE_MODES,
                "known",
                "mode.knowledge_mode",
            )
            fear_action = _enum(
                changes.get("fear_action", row["fear_action"]),
                FEAR_ACTIONS,
                "warn_only",
                "mode.fear_action",
            )
            visual_context_mode = _enum(
                changes.get("visual_context_mode", row["visual_context_mode"]),
                VISUAL_CONTEXT_MODES,
                "text_only",
                "mode.visual_context_mode",
            )
            reply_lead_ms = _int(
                changes.get("reply_lead_ms"),
                int(row["reply_lead_ms"] or WATCH_CONTEXT_REPLY_LEAD_MS),
            )
            if reply_lead_ms > 120_000:
                raise ValueError("mode.reply_lead_ms 必须在 0 到 120000 之间")
            force_unknown = _bool(
                changes.get("force_unknown_analysis"), bool(row["force_unknown_analysis"])
            )
            if old_force_unknown and not force_unknown:
                raise ValueError("已手动降级为陌生作品分析，不能直接升级识别结果")
            if force_unknown:
                knowledge_mode = "needs_summary"
            conn.execute(
                """
                UPDATE watch_sessions
                   SET knowledge_mode = ?, fear_mode = ?, fear_action = ?,
                       reduce_volume = ?, danmaku_enabled = ?, force_unknown_analysis = ?,
                       reply_lead_ms = ?, visual_context_mode = ?,
                       updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    knowledge_mode,
                    int(_bool(changes.get("fear_mode"), bool(row["fear_mode"]))),
                    fear_action,
                    int(_bool(changes.get("reduce_volume"), bool(row["reduce_volume"]))),
                    int(_bool(changes.get("danmaku_enabled"), bool(row["danmaku_enabled"]))),
                    int(force_unknown),
                    reply_lead_ms,
                    visual_context_mode,
                    now_iso,
                    _iso(now + ACTIVE_TTL),
                    session_id,
                ),
            )
            if force_unknown and not old_force_unknown:
                conn.execute(
                    """
                    UPDATE watch_analysis_jobs
                       SET status = 'cancelled', error = 'force_unknown_analysis',
                           finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                     WHERE session_id = ? AND purpose = 'knowledge_card'
                       AND status IN ('queued', 'running')
                    """,
                    (now_iso, now_iso, session_id),
                )
                conn.execute(
                    """
                    UPDATE watch_sessions
                       SET analysis_familiarity = 'unknown', preparation_status = 'identifying',
                           knowledge_card_key = '', knowledge_card_status = 'pending',
                           knowledge_card_error = '', knowledge_card_confirmed_at = '',
                           knowledge_card_skipped_at = '', subtitle_lookup_json = '{}',
                           subtitle_asset_id = '', subtitle_confirmed_at = ''
                     WHERE id = ?
                    """,
                    (session_id,),
                )
            updated = _get_session_row(conn, session_id)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_session(updated)


def update_preparation_state(
    session_id: str,
    *,
    status: str,
    knowledge_card_key: str | None = None,
    knowledge_card_status: str | None = None,
    knowledge_card_error: str | None = None,
) -> dict:
    normalized_status = _enum(
        status,
        PREPARATION_STATUSES,
        "identifying",
        "preparation.status",
    )
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _get_session_row(conn, session_id)
            if row is None:
                raise KeyError("watch_session_not_found")
            if str(row["status"] or "") == "ended":
                raise ValueError("观看会话已结束")
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = ?, knowledge_card_key = ?,
                       knowledge_card_status = ?, knowledge_card_error = ?,
                       updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    normalized_status,
                    _text(
                        row["knowledge_card_key"]
                        if knowledge_card_key is None
                        else knowledge_card_key,
                        160,
                    ),
                    _text(
                        row["knowledge_card_status"]
                        if knowledge_card_status is None
                        else knowledge_card_status,
                        40,
                    ),
                    _text(
                        row["knowledge_card_error"]
                        if knowledge_card_error is None
                        else knowledge_card_error,
                        2000,
                    ),
                    now_iso,
                    _iso(now + ACTIVE_TTL),
                    session_id,
                ),
            )
            updated = _get_session_row(conn, session_id)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_session(updated)


def start_session(
    session_id: str,
    *,
    knowledge_card_action: str,
    knowledge_card_key: str = "",
    subtitle_lookup_id: str = "",
) -> dict:
    action = _enum(
        knowledge_card_action,
        {"confirm", "skip"},
        "",
        "knowledge_card_action",
    )
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _get_session_row(conn, session_id)
            if row is None:
                raise KeyError("watch_session_not_found")
            if str(row["status"] or "") == "ended":
                raise ValueError("观看会话已结束")
            if str(row["started_at"] or "").strip():
                conn.execute("COMMIT")
                return _row_to_session(row)

            card_status = str(row["knowledge_card_status"] or "pending")
            current_key = str(row["knowledge_card_key"] or "")
            if action == "confirm":
                if card_status == "ready":
                    if not knowledge_card_key or knowledge_card_key != current_key:
                        raise ValueError("知识卡版本已经变化，请重新确认")
                    available_card = conn.execute(
                        "SELECT 1 FROM watch_knowledge_cards WHERE cache_key = ? AND expires_at > ?",
                        (current_key, now_iso),
                    ).fetchone()
                    if available_card is None:
                        raise ValueError("知识卡已过期，请重新生成后再确认")
                elif card_status != "not_required":
                    raise ValueError("知识卡尚未准备好；要继续播放请明确选择跳过")

            subtitle_lookup = runtime_sqlite.json_loads(row["subtitle_lookup_json"], {})
            lookup_status = str(subtitle_lookup.get("status") or "pending")
            current_lookup_id = str(subtitle_lookup.get("lookup_id") or "")
            if lookup_status not in {
                "found",
                "not_found",
                "not_configured",
                "original_title_unavailable",
                "failed",
            }:
                raise ValueError("字幕仍在准备中，请等待结果")
            if not subtitle_lookup_id or subtitle_lookup_id != current_lookup_id:
                raise ValueError("字幕准备结果已经变化，请重新确认")

            confirmed_at = now_iso if action == "confirm" else ""
            skipped_at = now_iso if action == "skip" else ""
            if action == "skip":
                conn.execute(
                    """
                    UPDATE watch_analysis_jobs
                       SET status = 'cancelled', error = 'knowledge_card_skipped',
                           finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                     WHERE session_id = ? AND purpose = 'knowledge_card'
                       AND status IN ('queued', 'running')
                    """,
                    (now_iso, now_iso, session_id),
                )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = 'confirmed', started_at = ?,
                       knowledge_card_confirmed_at = ?, knowledge_card_skipped_at = ?,
                       knowledge_card_status = ?, subtitle_confirmed_at = ?,
                       updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    now_iso,
                    confirmed_at,
                    skipped_at,
                    "skipped" if action == "skip" else card_status,
                    now_iso,
                    now_iso,
                    _iso(now + ACTIVE_TTL),
                    session_id,
                ),
            )
            updated = _get_session_row(conn, session_id)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_session(updated)


def end_session(session_id: str) -> dict:
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _get_session_row(conn, session_id)
            if row is None:
                raise KeyError("watch_session_not_found")
            conn.execute(
                """
                UPDATE watch_sessions
                   SET status = 'ended', is_playing = 0, ended_at = ?, updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (now_iso, now_iso, _iso(now + ENDED_TTL), session_id),
            )
            updated = _get_session_row(conn, session_id)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_session(updated)


def _section_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"] or ""),
        "timeline_epoch": int(row["timeline_epoch"] or 0),
        "kind": str(row["kind"] or "unknown"),
        "start_ms": int(row["start_ms"] or 0),
        "end_ms": int(row["end_ms"] or 0),
        "source": str(row["source"] or "analysis"),
        "confidence": float(row["confidence"] or 0),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def get_timeline_sections(session_id: str, *, timeline_epoch: int | None = None) -> list[dict]:
    clauses = ["session_id = ?"]
    params: list[Any] = [_text(session_id, 120)]
    if timeline_epoch is not None:
        clauses.append("timeline_epoch = ?")
        params.append(_int(timeline_epoch, 0))
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM watch_timeline_sections WHERE {' AND '.join(clauses)} "
            "ORDER BY start_ms, end_ms, id",
            params,
        ).fetchall()
    return [_section_to_dict(row) for row in rows]


def replace_timeline_sections(
    session_id: str,
    sections: Iterable[dict],
    *,
    timeline_epoch: int | None = None,
) -> list[dict]:
    session = get_session(session_id)
    if session is None:
        raise KeyError("watch_session_not_found")
    epoch = _int(
        timeline_epoch,
        int(session["playback"]["timeline_epoch"]),
    )
    duration_ms = int(session["media"]["duration_ms"] or 0)
    now_iso = _iso(_now())
    normalized: list[dict] = []
    for raw in sections:
        if not isinstance(raw, dict):
            raise ValueError("timeline section 必须是对象")
        kind = _enum(raw.get("kind"), TIMELINE_SECTION_KINDS, "unknown", "section.kind")
        start_ms = _int(raw.get("start_ms"), 0)
        end_ms = _int(raw.get("end_ms"), 0)
        if end_ms <= start_ms:
            raise ValueError("section.end_ms 必须大于 start_ms")
        if duration_ms > 0 and end_ms > duration_ms:
            raise ValueError("section.end_ms 超过媒体时长")
        normalized.append(
            {
                "id": _text(raw.get("id"), 160) or f"watch_section_{uuid4().hex}",
                "kind": kind,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "source": _text(raw.get("source"), 40) or "manual",
                "confidence": min(1.0, max(0.0, _float(raw.get("confidence"), 1.0))),
            }
        )
    normalized.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["id"]))

    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            active_samples = conn.execute(
                """
                SELECT file_path FROM watch_analysis_samples
                 WHERE session_id = ? AND timeline_epoch = ? AND purged_at = ''
                """,
                (session_id, epoch),
            ).fetchall()
            for sample_row in active_samples:
                file_path = str(sample_row["file_path"] or "").strip()
                if file_path:
                    try:
                        Path(file_path).unlink(missing_ok=True)
                    except Exception:
                        pass
            conn.execute(
                """
                UPDATE watch_analysis_samples
                   SET file_path = '', purged_at = ?
                 WHERE session_id = ? AND timeline_epoch = ? AND purged_at = ''
                """,
                (now_iso, session_id, epoch),
            )
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'cancelled', error = 'timeline_sections_corrected',
                       finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                 WHERE session_id = ? AND timeline_epoch = ?
                   AND purpose != 'knowledge_card'
                   AND status IN ('queued', 'running')
                """,
                (now_iso, now_iso, session_id, epoch),
            )
            conn.execute(
                "DELETE FROM watch_timeline_sections WHERE session_id = ? AND timeline_epoch = ?",
                (session_id, epoch),
            )
            for item in normalized:
                conn.execute(
                    """
                    INSERT INTO watch_timeline_sections (
                        id, session_id, timeline_epoch, kind, start_ms, end_ms,
                        source, confidence, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"], session_id, epoch, item["kind"], item["start_ms"],
                        item["end_ms"], item["source"], item["confidence"], now_iso, now_iso,
                    ),
                )
            conn.execute(
                "DELETE FROM watch_plot_chunks WHERE session_id = ? AND timeline_epoch = ?",
                (session_id, epoch),
            )
            conn.execute(
                "DELETE FROM watch_risk_events WHERE session_id = ? AND timeline_epoch = ?",
                (session_id, epoch),
            )
            conn.execute(
                "DELETE FROM watch_story_checkpoints WHERE session_id = ? AND timeline_epoch = ?",
                (session_id, epoch),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET analysis_status = 'warming_context', analysis_error = '',
                       analysis_covered_from_ms = 0, analysis_covered_until_ms = 0,
                       story_so_far_json = '{}', analysis_story_state_json = '{}',
                       updated_at = ?
                 WHERE id = ?
                """,
                (now_iso, session_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return get_timeline_sections(session_id, timeline_epoch=epoch)


def _plot_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"] or ""),
        "media_id": str(row["media_id"] or ""),
        "timeline_epoch": int(row["timeline_epoch"] or 0),
        "start_ms": int(row["start_ms"] or 0),
        "end_ms": int(row["end_ms"] or 0),
        "summary": str(row["summary"] or ""),
        "visual_description": str(row["visual_description"] or ""),
        "dialogue_summary": str(row["dialogue_summary"] or ""),
        "characters": runtime_sqlite.json_loads(row["characters_json"], []),
        "tags": runtime_sqlite.json_loads(row["tags_json"], []),
        "confidence": float(row["confidence"] or 0),
        "analysis_version": str(row["analysis_version"] or ""),
    }


def upsert_plot_chunks(session_id: str, chunks: Iterable[dict]) -> list[dict]:
    session = get_session(session_id)
    if session is None:
        raise KeyError("watch_session_not_found")
    now_iso = _iso(_now())
    media_id = session["media"]["id"]
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            ids: list[str] = []
            for raw in chunks:
                if not isinstance(raw, dict):
                    continue
                start_ms = _int(raw.get("start_ms"), 0)
                end_ms = _int(raw.get("end_ms"), 0)
                if end_ms <= start_ms:
                    raise ValueError("plot chunk 时间范围无效")
                chunk_id = _text(raw.get("id"), 160) or f"watch_plot_{uuid4().hex}"
                ids.append(chunk_id)
                conn.execute(
                    """
                    INSERT INTO watch_plot_chunks (
                        id, session_id, media_id, timeline_epoch, start_ms, end_ms,
                        summary, visual_description, dialogue_summary, characters_json,
                        tags_json, confidence, analysis_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        session_id = excluded.session_id,
                        media_id = excluded.media_id,
                        timeline_epoch = excluded.timeline_epoch,
                        start_ms = excluded.start_ms,
                        end_ms = excluded.end_ms,
                        summary = excluded.summary,
                        visual_description = excluded.visual_description,
                        dialogue_summary = excluded.dialogue_summary,
                        characters_json = excluded.characters_json,
                        tags_json = excluded.tags_json,
                        confidence = excluded.confidence,
                        analysis_version = excluded.analysis_version,
                        updated_at = excluded.updated_at
                    """,
                    (
                        chunk_id,
                        session_id,
                        media_id,
                        _int(raw.get("timeline_epoch"), session["playback"]["timeline_epoch"]),
                        start_ms,
                        end_ms,
                        _text(raw.get("summary"), 6000),
                        _text(raw.get("visual_description"), 6000),
                        _text(raw.get("dialogue_summary"), 6000),
                        runtime_sqlite.json_dumps(raw.get("characters") if isinstance(raw.get("characters"), list) else []),
                        runtime_sqlite.json_dumps(raw.get("tags") if isinstance(raw.get("tags"), list) else []),
                        min(1.0, max(0.0, _float(raw.get("confidence"), 0.0))),
                        _text(raw.get("analysis_version"), 120),
                        now_iso,
                        now_iso,
                    ),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM watch_plot_chunks WHERE id IN ({placeholders}) ORDER BY start_ms, end_ms",
            ids,
        ).fetchall()
    return [_plot_to_dict(row) for row in rows]


def get_plot_chunks(
    session_id: str,
    *,
    timeline_epoch: int,
    start_before_ms: int,
    end_after_ms: int,
    limit: int = 24,
) -> list[dict]:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watch_plot_chunks
             WHERE session_id = ? AND timeline_epoch = ?
               AND start_ms <= ? AND end_ms >= ?
             ORDER BY start_ms, end_ms, id
             LIMIT ?
            """,
            (
                _text(session_id, 120),
                _int(timeline_epoch, 0),
                _int(start_before_ms, 0),
                _int(end_after_ms, 0),
                max(1, min(100, int(limit or 24))),
            ),
        ).fetchall()
    return [_plot_to_dict(row) for row in rows]


def get_completed_plot_chunks(
    session_id: str,
    *,
    timeline_epoch: int,
    through_ms: int,
) -> list[dict]:
    """Read fully watched cached chunks from one together-watch timeline."""
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watch_plot_chunks
             WHERE session_id = ? AND timeline_epoch = ? AND end_ms <= ?
             ORDER BY start_ms, end_ms, id
            """,
            (
                _text(session_id, 120),
                _int(timeline_epoch, 0),
                _int(through_ms, 0),
            ),
        ).fetchall()
    return [_plot_to_dict(row) for row in rows]


def upsert_risk_events(session_id: str, events: Iterable[dict]) -> list[dict]:
    session = get_session(session_id)
    if session is None:
        raise KeyError("watch_session_not_found")
    now_iso = _iso(_now())
    ids: list[str] = []
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for raw in events:
                if not isinstance(raw, dict):
                    continue
                start_ms = _int(raw.get("start_ms"), 0)
                end_ms = _int(raw.get("end_ms"), 0)
                warn_at_ms = _int(raw.get("warn_at_ms"), start_ms)
                if end_ms <= start_ms or warn_at_ms > end_ms:
                    raise ValueError("risk event 时间范围无效")
                event_id = _text(raw.get("id"), 160) or f"watch_risk_{uuid4().hex}"
                ids.append(event_id)
                conn.execute(
                    """
                    INSERT INTO watch_risk_events (
                        id, session_id, media_id, timeline_epoch, risk_type, severity,
                        start_ms, end_ms, warn_at_ms, label, companion_hint, confidence,
                        status, analysis_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        session_id = excluded.session_id,
                        media_id = excluded.media_id,
                        timeline_epoch = excluded.timeline_epoch,
                        risk_type = excluded.risk_type,
                        severity = excluded.severity,
                        start_ms = excluded.start_ms,
                        end_ms = excluded.end_ms,
                        warn_at_ms = excluded.warn_at_ms,
                        label = excluded.label,
                        companion_hint = excluded.companion_hint,
                        confidence = excluded.confidence,
                        status = excluded.status,
                        analysis_version = excluded.analysis_version,
                        updated_at = excluded.updated_at
                    """,
                    (
                        event_id,
                        session_id,
                        session["media"]["id"],
                        _int(raw.get("timeline_epoch"), session["playback"]["timeline_epoch"]),
                        _text(raw.get("risk_type"), 80) or "high_energy",
                        _text(raw.get("severity"), 40) or "medium",
                        start_ms,
                        end_ms,
                        warn_at_ms,
                        _text(raw.get("label"), 300),
                        _text(raw.get("companion_hint"), 1000),
                        min(1.0, max(0.0, _float(raw.get("confidence"), 0.0))),
                        _text(raw.get("status"), 40) or "pending",
                        _text(raw.get("analysis_version"), 120),
                        now_iso,
                        now_iso,
                    ),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM watch_risk_events WHERE id IN ({placeholders}) ORDER BY warn_at_ms, id",
            ids,
        ).fetchall()
    return [dict(row) for row in rows]


def get_risk_events(
    session_id: str,
    *,
    timeline_epoch: int | None = None,
    from_ms: int = 0,
    until_ms: int | None = None,
    limit: int = 50,
) -> list[dict]:
    clauses = ["session_id = ?", "end_ms >= ?"]
    params: list[Any] = [_text(session_id, 120), _int(from_ms, 0)]
    if timeline_epoch is not None:
        clauses.append("timeline_epoch = ?")
        params.append(_int(timeline_epoch, 0))
    if until_ms is not None:
        clauses.append("warn_at_ms <= ?")
        params.append(_int(until_ms, 0))
    params.append(max(1, min(200, int(limit or 50))))
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM watch_risk_events WHERE {' AND '.join(clauses)} "
            "ORDER BY warn_at_ms, start_ms, id LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def record_risk_feedback(
    session_id: str,
    *,
    device_id: str,
    feedback_type: str,
    risk_event_id: str = "",
    playhead_ms: int = 0,
    note: str = "",
) -> dict:
    if get_session(session_id) is None:
        raise KeyError("watch_session_not_found")
    normalized_type = _enum(
        feedback_type, RISK_FEEDBACK_TYPES, "", "feedback_type"
    )
    feedback_id = f"watch_feedback_{uuid4().hex}"
    created_at = _iso(_now())
    item = {
        "id": feedback_id,
        "session_id": session_id,
        "risk_event_id": _text(risk_event_id, 160),
        "feedback_type": normalized_type,
        "playhead_ms": _int(playhead_ms, 0),
        "note": _text(note, 2000),
        "device_id": _text(device_id, 160),
        "created_at": created_at,
    }
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_risk_feedback (
                id, session_id, risk_event_id, feedback_type, playhead_ms,
                note, device_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(item.values()),
        )
    return item


def update_analysis_state(session_id: str, changes: dict) -> dict:
    allowed = {
        "familiarity",
        "identity",
        "original_title",
        "year",
        "status",
        "covered_from_ms",
        "covered_until_ms",
        "error",
        "story_so_far",
        "story_state",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"不支持的 analysis 字段: {', '.join(sorted(unknown))}")
    session = get_session(session_id)
    if session is None:
        raise KeyError("watch_session_not_found")
    current = session["analysis"]
    status = _enum(changes.get("status", current["status"]), ANALYSIS_STATUSES, "pending", "analysis.status")
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE watch_sessions
               SET analysis_familiarity = ?, analysis_identity = ?,
                   analysis_original_title = ?, analysis_year = ?, analysis_status = ?,
                   analysis_covered_from_ms = ?, analysis_covered_until_ms = ?,
                   analysis_error = ?, story_so_far_json = ?, analysis_story_state_json = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (
                _text(changes.get("familiarity", current["familiarity"]), 80),
                _text(changes.get("identity", current["identity"]), 500),
                _text(changes.get("original_title", current["original_title"]), 300),
                _int(changes.get("year"), current["year"]),
                status,
                _int(changes.get("covered_from_ms"), current["covered_from_ms"]),
                _int(changes.get("covered_until_ms"), current["covered_until_ms"]),
                _text(changes.get("error", current["error"]), 2000),
                runtime_sqlite.json_dumps(changes.get("story_so_far", current["story_so_far"])),
                runtime_sqlite.json_dumps(changes.get("story_state", current["story_state"])),
                now_iso,
                session_id,
            ),
        )
    updated = get_session(session_id)
    if updated is None:
        raise KeyError("watch_session_not_found")
    return updated


def get_status(session_id: str) -> dict | None:
    session = get_session(session_id)
    if session is None:
        return None
    epoch = int(session["playback"]["timeline_epoch"])
    playhead = int(session["playback"]["playhead_ms"])
    future_until = playhead + 120_000
    analysis = session["analysis"]
    mode = session["mode"]
    media = session["media"]
    covered_until = int(analysis.get("covered_until_ms") or 0)
    coverage_remaining = max(0, covered_until - playhead)
    required_buffer = int(WATCH_ANALYSIS_FEAR_READY_BUFFER_MS)
    required_until = playhead + required_buffer
    content_end = media.get("content_end_ms")
    duration_ms = int(media.get("duration_ms") or 0)
    if content_end is not None:
        required_until = min(required_until, int(content_end))
    elif duration_ms > 0:
        required_until = min(required_until, duration_ms)

    if not bool(mode.get("fear_mode")):
        protection_status = "off"
        protection_reason = "fear_mode_off"
    elif str(session["playback"].get("status") or "") == "ended":
        protection_status = "off"
        protection_reason = "playback_ended"
    elif content_end is not None and playhead >= int(content_end):
        protection_status = "off"
        protection_reason = "outside_story_content"
    elif (
        str(analysis.get("status") or "") == "ready"
        and covered_until >= required_until
    ):
        protection_status = "protected"
        protection_reason = "coverage_ready"
    else:
        protection_status = "coverage_low"
        protection_reason = (
            "analysis_not_ready"
            if str(analysis.get("status") or "") != "ready"
            else "coverage_below_required"
        )
    return {
        "session_id": session["session_id"],
        "media_id": session["media"]["id"],
        "status": session["playback"]["status"],
        "playback": session["playback"],
        "analysis": analysis,
        "mode": mode,
        "fear_protection": {
            "status": protection_status,
            "reason": protection_reason,
            "playhead_ms": playhead,
            "covered_until_ms": covered_until,
            "coverage_remaining_ms": coverage_remaining,
            "required_buffer_ms": required_buffer,
            "required_until_ms": required_until,
        },
        "preparation": session["preparation"],
        "timeline_sections": get_timeline_sections(session_id, timeline_epoch=epoch),
        "upcoming_risks": get_risk_events(
            session_id,
            timeline_epoch=epoch,
            from_ms=playhead,
            until_ms=future_until,
        ),
        "updated_at": session["updated_at"],
    }
