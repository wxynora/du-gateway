from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from config import (
    WATCH_ANALYSIS_JOB_MAX_ATTEMPTS,
    WATCH_KNOWLEDGE_MODEL,
    WATCH_KNOWLEDGE_PROMPT_VERSION,
    WATCH_KNOWLEDGE_TTL_SECONDS,
)
from storage import runtime_sqlite, watch_runtime_store


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def cache_key_for_session(session: dict) -> str:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    local_media = media.get("local_media") if isinstance(media.get("local_media"), dict) else {}
    identity = "|".join(
        [
            _text(media.get("source"), 80).casefold(),
            _text(media.get("id"), 240).casefold(),
            _text(media.get("title"), 300).casefold(),
            _text(media.get("part_title"), 300).casefold(),
            _text(analysis.get("identity"), 500).casefold(),
            str(int(media.get("duration_ms") or 0)),
            str(local_media.get("media_revision") or ""),
            WATCH_KNOWLEDGE_PROMPT_VERSION,
        ]
    )
    return "watch_card_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def get_card(cache_key: str) -> dict:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_knowledge_cards WHERE cache_key = ? AND expires_at > ?",
            (_text(cache_key, 160), now_iso),
        ).fetchone()
    if row is None:
        return {}
    card = runtime_sqlite.json_loads(row["card_json"], {})
    if not isinstance(card, dict):
        return {}
    return {
        **card,
        "cache_key": str(row["cache_key"] or ""),
        "sources": runtime_sqlite.json_loads(row["sources_json"], []),
        "created_at": str(row["created_at"] or ""),
        "expires_at": str(row["expires_at"] or ""),
    }


def get_card_for_session(session: dict) -> dict:
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    if str(preparation.get("knowledge_card_status") or "") != "ready":
        return {}
    return get_card(str(preparation.get("knowledge_card_key") or ""))


def _active_job(session_id: str, cache_key: str) -> dict:
    idempotency_key = f"knowledge:{session_id}:{cache_key}"
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_analysis_jobs
             WHERE session_id = ? AND purpose = 'knowledge_card'
               AND idempotency_key = ? AND status IN ('queued', 'running')
             ORDER BY created_at DESC LIMIT 1
            """,
            (_text(session_id, 160), idempotency_key),
        ).fetchone()
    if row is None:
        return {}
    from storage import watch_analysis_store

    return watch_analysis_store.get_job(str(row["id"] or ""), public=True) or {}


def ensure_knowledge_job(session: dict) -> tuple[dict, bool]:
    session_id = str(session.get("session_id") or "")
    if not session_id:
        raise ValueError("session_id 不能为空")
    familiarity = str((session.get("analysis") or {}).get("familiarity") or "pending")
    force_unknown = bool((session.get("mode") or {}).get("force_unknown_analysis"))
    if force_unknown:
        familiarity = "unknown"
    if familiarity == "recognized":
        watch_runtime_store.update_preparation_state(
            session_id,
            status="searching_subtitles",
            knowledge_card_status="not_required",
            knowledge_card_error="",
        )
        return {}, False
    if familiarity not in {"partial", "unknown"}:
        return {}, False

    cache_key = cache_key_for_session(session)
    cached = get_card(cache_key)
    if cached:
        watch_runtime_store.update_preparation_state(
            session_id,
            status="searching_subtitles",
            knowledge_card_key=cache_key,
            knowledge_card_status="ready",
            knowledge_card_error="",
        )
        return {"cache_key": cache_key, "status": "done", "cached": True}, False
    active = _active_job(session_id, cache_key)
    if active:
        return active, False
    from storage import watch_analysis_store

    existing = watch_analysis_store.get_job_by_idempotency(
        f"knowledge:{session_id}:{cache_key}",
        public=True,
    )
    if existing:
        if str(existing.get("status") or "") == "failed":
            watch_runtime_store.update_preparation_state(
                session_id,
                status="knowledge_failed",
                knowledge_card_key=cache_key,
                knowledge_card_status="failed",
                knowledge_card_error=str(existing.get("error") or "知识卡生成失败"),
            )
        return existing, False

    now = _now()
    now_iso = _iso(now)
    job_id = f"watch_job_{uuid4().hex}"
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    timeline_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            session_row = conn.execute(
                "SELECT status, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None or str(session_row["status"] or "") == "ended":
                raise ValueError("观看会话已经结束")
            if (
                not str(session_row["client_lease_expires_at"] or "")
                or str(session_row["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能新建知识卡任务")
            conn.execute(
                """
                INSERT INTO watch_analysis_jobs (
                    id, idempotency_key, session_id, media_id, timeline_epoch,
                    purpose, input_origin, planned_timestamps_json, range_start_ms,
                    range_end_ms, status, priority, attempts, max_attempts,
                    available_at, sample_ids_json, analysis_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'knowledge_card', 'knowledge_provider', '[]',
                          0, 0, 'queued', 25, 0, ?, ?, '[]', ?, ?, ?)
                """,
                (
                    job_id,
                    f"knowledge:{session_id}:{cache_key}",
                    session_id,
                    _text(media.get("id"), 240),
                    timeline_epoch,
                    int(WATCH_ANALYSIS_JOB_MAX_ATTEMPTS),
                    now_iso,
                    f"{WATCH_KNOWLEDGE_MODEL}:{WATCH_KNOWLEDGE_PROMPT_VERSION}",
                    now_iso,
                    now_iso,
                ),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = 'collecting_sources', knowledge_card_key = ?,
                       knowledge_card_status = 'queued', knowledge_card_error = '',
                       updated_at = ?, expires_at = ?
                 WHERE id = ? AND status != 'ended'
                """,
                (
                    cache_key,
                    now_iso,
                    _iso(now + timedelta(hours=24)),
                    session_id,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return watch_analysis_store.get_job(job_id, public=True) or {}, True


def retry_knowledge_job(session: dict) -> dict:
    session_id = str(session.get("session_id") or "")
    familiarity = str((session.get("analysis") or {}).get("familiarity") or "pending")
    if bool((session.get("mode") or {}).get("force_unknown_analysis")):
        familiarity = "unknown"
    if familiarity not in {"partial", "unknown"}:
        raise ValueError("当前作品识别状态不需要生成知识卡")
    cache_key = cache_key_for_session(session)
    from storage import watch_analysis_store

    existing = watch_analysis_store.get_job_by_idempotency(
        f"knowledge:{session_id}:{cache_key}",
        public=True,
    )
    if not existing:
        job, _created = ensure_knowledge_job(session)
        return job
    status = str(existing.get("status") or "")
    if status in {"queued", "running"}:
        return existing
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            session_row = conn.execute(
                "SELECT status, started_at, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None or str(session_row["status"] or "") == "ended":
                raise ValueError("观看会话已经结束")
            if str(session_row["started_at"] or ""):
                raise ValueError("作品知识卡只能在正式开始前重新生成")
            if (
                not str(session_row["client_lease_expires_at"] or "")
                or str(session_row["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能重建知识卡任务")
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'queued', attempts = 0, available_at = ?,
                       leased_until = '', lease_token = '', started_at = '', finished_at = '',
                       cancel_requested = 0, cancel_requested_at = '', cancel_reason = '',
                       error = '', result_json = '{}', usage_json = '{}', updated_at = ?
                 WHERE id = ? AND purpose = 'knowledge_card'
                """,
                (now_iso, now_iso, existing.get("job_id")),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = 'collecting_sources', knowledge_card_key = ?,
                       knowledge_card_status = 'queued', knowledge_card_error = '', updated_at = ?
                 WHERE id = ? AND status != 'ended'
                """,
                (cache_key, now_iso, session_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return watch_analysis_store.get_job(str(existing.get("job_id") or ""), public=True) or {}


def mark_building(session_id: str) -> None:
    watch_runtime_store.update_preparation_state(
        session_id,
        status="building_card",
        knowledge_card_status="building",
        knowledge_card_error="",
    )


def commit_knowledge_result(
    job: dict,
    *,
    card: dict,
    sources: list[dict],
    usage: dict,
    source_digest: str,
) -> dict:
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    session_id = str(job.get("session_id") or "")
    cache_key = ""
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(now + timedelta(seconds=int(WATCH_KNOWLEDGE_TTL_SECONDS)))
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            running = conn.execute(
                "SELECT cancel_requested, usage_json FROM watch_analysis_jobs WHERE id = ? AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).fetchone()
            session_row = conn.execute(
                "SELECT status, media_id, knowledge_card_key, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            cache_key = str(session_row["knowledge_card_key"] or "") if session_row is not None else ""
            if running is None:
                conn.execute("ROLLBACK")
                return {"applied": False, "reason": "lease_lost"}
            if bool(running["cancel_requested"]):
                rejection_reason = "cancel_requested"
            elif session_row is None or str(session_row["status"] or "") == "ended":
                rejection_reason = "session_ended"
            elif (
                not str(session_row["client_lease_expires_at"] or "")
                or str(session_row["client_lease_expires_at"] or "") <= now_iso
            ):
                rejection_reason = "client_lease_expired"
            elif str(session_row["media_id"] or "") != str(job.get("media_id") or "") or not cache_key:
                rejection_reason = "stale_media"
            else:
                rejection_reason = ""
            if rejection_reason:
                conn.execute(
                    "UPDATE watch_analysis_jobs SET status = 'cancelled', cancel_requested = 1, cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END, cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?, lease_token = '', leased_until = '' WHERE id = ?",
                    (now_iso, rejection_reason, rejection_reason, now_iso, now_iso, job_id),
                )
                conn.execute("COMMIT")
                return {"applied": False, "reason": rejection_reason}
            conn.execute(
                """
                INSERT INTO watch_knowledge_cards (
                    cache_key, media_identity_json, card_json, sources_json, source_digest,
                    model, prompt_version, confidence, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    media_identity_json = excluded.media_identity_json,
                    card_json = excluded.card_json, sources_json = excluded.sources_json,
                    source_digest = excluded.source_digest, model = excluded.model,
                    prompt_version = excluded.prompt_version, confidence = excluded.confidence,
                    updated_at = excluded.updated_at, expires_at = excluded.expires_at
                """,
                (
                    cache_key,
                    runtime_sqlite.json_dumps(card.get("canonical_identity") or {}),
                    runtime_sqlite.json_dumps(card),
                    runtime_sqlite.json_dumps(
                        [
                            {
                                "source_id": item.get("source_id"),
                                "title": item.get("title"),
                                "url": item.get("url"),
                                "published_at": item.get("published_at"),
                            }
                            for item in sources
                        ]
                    ),
                    _text(source_digest, 80),
                    _text(card.get("model") or WATCH_KNOWLEDGE_MODEL, 160),
                    _text(card.get("prompt_version") or WATCH_KNOWLEDGE_PROMPT_VERSION, 80),
                    float(card.get("confidence") or 0),
                    now_iso,
                    now_iso,
                    expires_at,
                ),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = 'searching_subtitles', knowledge_card_key = ?,
                       knowledge_card_status = 'ready', knowledge_card_error = '',
                       updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (cache_key, now_iso, _iso(now + timedelta(hours=24)), session_id),
            )
            from storage import watch_analysis_store

            merged_usage = watch_analysis_store.merge_usage(
                runtime_sqlite.json_loads(running["usage_json"], {}),
                usage,
            )
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'done', leased_until = '', lease_token = '', finished_at = ?,
                       updated_at = ?, error = '', result_json = ?, usage_json = ?,
                       input_tokens = ?, output_tokens = ?, cost_usd = ?
                 WHERE id = ?
                """,
                (
                    now_iso,
                    now_iso,
                    runtime_sqlite.json_dumps({"cache_key": cache_key, "card": card}),
                    runtime_sqlite.json_dumps(merged_usage),
                    int(merged_usage.get("input_tokens") or 0),
                    int(merged_usage.get("output_tokens") or 0),
                    max(0.0, float(merged_usage.get("cost_usd") or 0)),
                    job_id,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"applied": True, "cache_key": cache_key}
