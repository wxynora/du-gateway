"""Local runtime state for together-watch sessions.

The watch feature deliberately keeps analysis and playback state in the local
runtime database. Nothing in this module reads from or writes to R2.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4

from storage import runtime_sqlite


ACTIVE_TTL = timedelta(hours=24)
ENDED_TTL = timedelta(hours=6)
DEFAULT_ANALYSIS_MODEL = "google/gemini-2.5-flash"
DEFAULT_PROMPT_VERSION = "watch-v1"

KNOWLEDGE_MODES = {"known", "needs_summary"}
FEAR_ACTIONS = {"warn_only", "cover_video"}
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
NON_STORY_SECTION_KINDS = {"intro", "outro", "preview", "non_story"}
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


def _cleanup_expired(conn, now_iso: str) -> int:
    rows = conn.execute(
        "SELECT id FROM watch_sessions WHERE expires_at <= ?",
        (now_iso,),
    ).fetchall()
    session_ids = [str(row["id"]) for row in rows]
    for session_id in session_ids:
        conn.execute("DELETE FROM watch_risk_feedback WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_risk_events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_plot_chunks WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_timeline_sections WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM watch_sessions WHERE id = ?", (session_id,))
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
        },
        "mode": {
            "knowledge_mode": str(row["knowledge_mode"] or "known"),
            "fear_mode": bool(row["fear_mode"]),
            "fear_action": str(row["fear_action"] or "warn_only"),
            "reduce_volume": bool(row["reduce_volume"]),
            "danmaku_enabled": bool(row["danmaku_enabled"]),
            "force_unknown_analysis": bool(row["force_unknown_analysis"]),
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

    knowledge_mode = _enum(
        mode.get("knowledge_mode"), KNOWLEDGE_MODES, "known", "mode.knowledge_mode"
    )
    fear_action = _enum(mode.get("fear_action"), FEAR_ACTIONS, "warn_only", "mode.fear_action")
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
        knowledge_mode,
        _text(mode.get("analysis_model"), 160) or DEFAULT_ANALYSIS_MODEL,
        _text(mode.get("analysis_prompt_version"), 80) or DEFAULT_PROMPT_VERSION,
        int(force_unknown),
        int(_bool(mode.get("fear_mode"))),
        fear_action,
        int(_bool(mode.get("reduce_volume"))),
        int(_bool(mode.get("danmaku_enabled"), True)),
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
                    knowledge_mode, analysis_model, analysis_prompt_version,
                    force_unknown_analysis, fear_mode, fear_action, reduce_volume,
                    danmaku_enabled, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
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
            force_unknown = _bool(
                changes.get("force_unknown_analysis"), bool(row["force_unknown_analysis"])
            )
            if force_unknown:
                knowledge_mode = "needs_summary"
            conn.execute(
                """
                UPDATE watch_sessions
                   SET knowledge_mode = ?, fear_mode = ?, fear_action = ?,
                       reduce_volume = ?, danmaku_enabled = ?, force_unknown_analysis = ?,
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
                if item["kind"] in NON_STORY_SECTION_KINDS:
                    overlap = (session_id, epoch, item["end_ms"], item["start_ms"])
                    conn.execute(
                        """
                        DELETE FROM watch_plot_chunks
                         WHERE session_id = ? AND timeline_epoch = ?
                           AND start_ms < ? AND end_ms > ?
                        """,
                        overlap,
                    )
                    conn.execute(
                        """
                        DELETE FROM watch_risk_events
                         WHERE session_id = ? AND timeline_epoch = ?
                           AND start_ms < ? AND end_ms > ?
                        """,
                        overlap,
                    )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET analysis_status = 'warming_context', analysis_error = '', updated_at = ?
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
               SET analysis_familiarity = ?, analysis_identity = ?, analysis_status = ?,
                   analysis_covered_from_ms = ?, analysis_covered_until_ms = ?,
                   analysis_error = ?, story_so_far_json = ?, analysis_story_state_json = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (
                _text(changes.get("familiarity", current["familiarity"]), 80),
                _text(changes.get("identity", current["identity"]), 500),
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
    return {
        "session_id": session["session_id"],
        "media_id": session["media"]["id"],
        "status": session["playback"]["status"],
        "playback": session["playback"],
        "analysis": session["analysis"],
        "mode": session["mode"],
        "timeline_sections": get_timeline_sections(session_id, timeline_epoch=epoch),
        "upcoming_risks": get_risk_events(
            session_id,
            timeline_epoch=epoch,
            from_ms=playhead,
            until_ms=future_until,
        ),
        "updated_at": session["updated_at"],
    }
