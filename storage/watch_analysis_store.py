from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import (
    WATCH_ANALYSIS_CLIENT_PLAN_TTL_SECONDS,
    WATCH_ANALYSIS_DAILY_MAX_COST_USD,
    WATCH_ANALYSIS_FORWARD_WINDOW_MS,
    WATCH_ANALYSIS_INITIAL_READY_BUFFER_MS,
    WATCH_ANALYSIS_JOB_MAX_ATTEMPTS,
    WATCH_ANALYSIS_MAX_AUDIO_DURATION_MS,
    WATCH_ANALYSIS_MAX_FRAMES_PER_JOB,
    WATCH_ANALYSIS_PREPASS_EDGE_MS,
    WATCH_ANALYSIS_PROMPT_VERSION,
    WATCH_ANALYSIS_RECOGNIZED_INTERVAL_MS,
    WATCH_ANALYSIS_SAMPLE_TTL_SECONDS,
    WATCH_ANALYSIS_UNKNOWN_INTERVAL_MS,
)
from storage import runtime_sqlite


ANALYSIS_MODEL_PURPOSES = {"identify", "timeline_prepass", "rolling"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _row_to_job(row: Any, *, public: bool = False) -> dict:
    if row is None:
        return {}
    out = {
        "job_id": str(row["id"] or ""),
        "session_id": str(row["session_id"] or ""),
        "media_id": str(row["media_id"] or ""),
        "timeline_epoch": int(row["timeline_epoch"] or 0),
        "purpose": str(row["purpose"] or "rolling"),
        "input_origin": str(row["input_origin"] or "client_upload"),
        "planned_timestamps_ms": runtime_sqlite.json_loads(
            row["planned_timestamps_json"], []
        ),
        "range_start_ms": int(row["range_start_ms"] or 0),
        "range_end_ms": int(row["range_end_ms"] or 0),
        "status": str(row["status"] or "queued"),
        "priority": int(row["priority"] or 0),
        "attempts": int(row["attempts"] or 0),
        "max_attempts": int(row["max_attempts"] or 0),
        "sample_ids": runtime_sqlite.json_loads(row["sample_ids_json"], []),
        "analysis_version": str(row["analysis_version"] or ""),
        "input_bytes": int(row["input_bytes"] or 0),
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "cost_usd": float(row["cost_usd"] or 0),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
        "cancel_requested": bool(row["cancel_requested"]),
        "cancel_requested_at": str(row["cancel_requested_at"] or ""),
        "cancel_reason": str(row["cancel_reason"] or ""),
        "error": str(row["error"] or ""),
    }
    if not public:
        out.update(
            {
                "idempotency_key": str(row["idempotency_key"] or ""),
                "available_at": str(row["available_at"] or ""),
                "leased_until": str(row["leased_until"] or ""),
                "lease_token": str(row["lease_token"] or ""),
                "result": runtime_sqlite.json_loads(row["result_json"], {}),
                "usage": runtime_sqlite.json_loads(row["usage_json"], {}),
            }
        )
    return out


def _usage_totals(value: Any) -> dict:
    usage = value if isinstance(value, dict) else {}
    model = str(usage.get("model") or "").strip()
    input_tokens = _int(usage.get("input_tokens"), 0)
    output_tokens = _int(usage.get("output_tokens"), 0)
    total_tokens = _int(usage.get("total_tokens"), input_tokens + output_tokens)
    cost_usd = _float(usage.get("cost_usd"), 0.0)
    if "provider_calls" in usage:
        provider_calls = _int(usage.get("provider_calls"), 0)
    else:
        provider_called = usage.get("provider_called")
        if isinstance(provider_called, bool):
            provider_calls = int(provider_called)
        else:
            provider_calls = int(
                bool(input_tokens or output_tokens or total_tokens or cost_usd)
                and not model.startswith("local-")
            )
    if "priced_calls" in usage:
        priced_calls = _int(usage.get("priced_calls"), 0)
    else:
        cost_reported = usage.get("cost_reported")
        if isinstance(cost_reported, bool):
            priced_calls = int(cost_reported and provider_calls > 0)
        else:
            priced_calls = int(cost_usd > 0 and provider_calls > 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "elapsed_ms": _int(usage.get("elapsed_ms"), 0),
        "provider_calls": provider_calls,
        "priced_calls": min(provider_calls, priced_calls),
        "model": model,
    }


def _merge_usage(existing: Any, incoming: Any) -> dict:
    before = _usage_totals(existing)
    delta = _usage_totals(incoming)
    provider_calls = before["provider_calls"] + delta["provider_calls"]
    priced_calls = before["priced_calls"] + delta["priced_calls"]
    return {
        "input_tokens": before["input_tokens"] + delta["input_tokens"],
        "output_tokens": before["output_tokens"] + delta["output_tokens"],
        "total_tokens": before["total_tokens"] + delta["total_tokens"],
        "cost_usd": before["cost_usd"] + delta["cost_usd"],
        "elapsed_ms": before["elapsed_ms"] + delta["elapsed_ms"],
        "provider_calls": provider_calls,
        "priced_calls": priced_calls,
        "cost_complete": priced_calls >= provider_calls,
        "model": delta["model"] or before["model"],
    }


def _row_to_sample(row: Any) -> dict:
    return {
        "id": str(row["id"] or ""),
        "session_id": str(row["session_id"] or ""),
        "media_id": str(row["media_id"] or ""),
        "timeline_epoch": int(row["timeline_epoch"] or 0),
        "purpose": str(row["purpose"] or "rolling"),
        "at_ms": int(row["at_ms"] or 0),
        "mime_type": str(row["mime_type"] or ""),
        "file_path": str(row["file_path"] or ""),
        "text_content": str(row["text_content"] or ""),
        "subtitle": str(row["subtitle"] or ""),
        "sha256": str(row["sha256"] or ""),
        "perceptual_hash": str(row["perceptual_hash"] or ""),
        "width": int(row["width"] or 0),
        "height": int(row["height"] or 0),
        "byte_size": int(row["byte_size"] or 0),
        "captured_at": str(row["captured_at"] or ""),
        "created_at": str(row["created_at"] or ""),
        "expires_at": str(row["expires_at"] or ""),
        "consumed_at": str(row["consumed_at"] or ""),
        "purged_at": str(row["purged_at"] or ""),
    }


def get_job(job_id: str, *, public: bool = True) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_analysis_jobs WHERE id = ?",
            (_text(job_id, 160),),
        ).fetchone()
    return _row_to_job(row, public=public) if row is not None else None


def get_job_by_idempotency(idempotency_key: str, *, public: bool = True) -> dict | None:
    key = _text(idempotency_key, 240)
    if not key:
        return None
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_analysis_jobs WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
    return _row_to_job(row, public=public) if row is not None else None


def _derived_idempotency_key(
    session_id: str,
    timeline_epoch: int,
    purpose: str,
    samples: list[dict],
) -> str:
    signatures = [
        f"{int(item.get('at_ms') or 0)}:{item.get('sha256') or ''}:{item.get('subtitle') or ''}:{item.get('text_content') or ''}"
        for item in samples
    ]
    digest = hashlib.sha256("|".join(signatures).encode("utf-8")).hexdigest()
    return f"watch-analysis:{session_id}:{timeline_epoch}:{purpose}:{digest}"


def _source_idempotency_key(
    session_id: str,
    media_id: str,
    timeline_epoch: int,
    purpose: str,
    timestamps_ms: list[int],
) -> str:
    raw = ":".join(str(value) for value in timestamps_ms)
    digest = hashlib.sha256(
        f"{media_id}|{WATCH_ANALYSIS_PROMPT_VERSION}|{raw}".encode("utf-8")
    ).hexdigest()
    return f"watch-analysis-source:{session_id}:{timeline_epoch}:{purpose}:{digest}"


def enqueue_samples(
    *,
    session: dict,
    purpose: str,
    samples: list[dict],
    idempotency_key: str = "",
    priority: int = 0,
    range_start_ms: int | None = None,
    range_end_ms: int | None = None,
    client_plan_id: str = "",
) -> tuple[dict, bool]:
    session_id = str(session.get("session_id") or "").strip()
    media_id = str((session.get("media") or {}).get("id") or "").strip()
    timeline_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
    if not session_id or not media_id or session.get("ended_at"):
        raise ValueError("观看会话不可分析")
    if not samples:
        raise ValueError("samples 不能为空")
    key = _text(idempotency_key, 240) or _derived_idempotency_key(
        session_id,
        timeline_epoch,
        purpose,
        samples,
    )
    existing = get_job_by_idempotency(key, public=True)
    if existing:
        return existing, False
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(now + timedelta(seconds=int(WATCH_ANALYSIS_SAMPLE_TTL_SECONDS)))
    sample_ids = [str(item.get("id") or "") for item in samples]
    sample_range_start = min(int(item.get("at_ms") or 0) for item in samples)
    sample_range_end = max(int(item.get("at_ms") or 0) for item in samples)
    range_start = sample_range_start if range_start_ms is None else _int(range_start_ms, 0)
    range_end = sample_range_end if range_end_ms is None else _int(range_end_ms, 0)
    if range_end < range_start:
        raise ValueError("分析任务结束时间不能早于开始时间")
    input_bytes = sum(int(item.get("byte_size") or 0) for item in samples)
    job_id = f"watch_analysis_{uuid4().hex}"
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute(
                "SELECT media_id, timeline_epoch, status, client_lease_expires_at FROM watch_sessions WHERE id = ? AND expires_at > ?",
                (session_id, now_iso),
            ).fetchone()
            if current is None or str(current["status"] or "") == "ended":
                raise ValueError("观看会话不可分析")
            if (
                not str(current["client_lease_expires_at"] or "")
                or str(current["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能新建分析任务")
            if str(current["media_id"] or "") != media_id or int(current["timeline_epoch"] or 0) != timeline_epoch:
                raise ValueError("播放时间轴已经变化，请重新采样")
            duplicate = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if duplicate is not None:
                conn.execute("COMMIT")
                return _row_to_job(duplicate, public=True), False
            if client_plan_id:
                consumed = conn.execute(
                    """
                    UPDATE watch_client_sample_plans
                       SET status = 'consumed', job_id = ?, consumed_at = ?
                     WHERE id = ? AND session_id = ? AND media_id = ?
                       AND timeline_epoch = ? AND status = 'open' AND expires_at > ?
                    """,
                    (
                        job_id,
                        now_iso,
                        _text(client_plan_id, 160),
                        session_id,
                        media_id,
                        timeline_epoch,
                        now_iso,
                    ),
                )
                if not consumed.rowcount:
                    raise ValueError("本地取材计划已经失效或被使用")
            for item in samples:
                conn.execute(
                    """
                    INSERT INTO watch_analysis_samples (
                        id, session_id, media_id, timeline_epoch, purpose, at_ms,
                        mime_type, file_path, text_content, subtitle, sha256,
                        perceptual_hash, width, height, byte_size, captured_at,
                        created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"], session_id, media_id, timeline_epoch, purpose,
                        int(item.get("at_ms") or 0), item.get("mime_type") or "",
                        item.get("file_path") or "", item.get("text_content") or "",
                        item.get("subtitle") or "", item.get("sha256") or "",
                        item.get("perceptual_hash") or "", int(item.get("width") or 0),
                        int(item.get("height") or 0), int(item.get("byte_size") or 0),
                        item.get("captured_at") or "", now_iso, expires_at,
                    ),
                )
            conn.execute(
                """
                INSERT INTO watch_analysis_jobs (
                    id, idempotency_key, session_id, media_id, timeline_epoch,
                    purpose, input_origin, planned_timestamps_json,
                    range_start_ms, range_end_ms, status, priority,
                    max_attempts, available_at, sample_ids_json, analysis_version,
                    input_bytes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'client_upload', '[]', ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id, key, session_id, media_id, timeline_epoch, purpose,
                    range_start, range_end, max(-100, min(100, int(priority or 0))),
                    int(WATCH_ANALYSIS_JOB_MAX_ATTEMPTS), now_iso,
                    runtime_sqlite.json_dumps(sample_ids), WATCH_ANALYSIS_PROMPT_VERSION,
                    input_bytes, now_iso, now_iso,
                ),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET analysis_status = 'analyzing', analysis_error = '', updated_at = ?
                 WHERE id = ?
                """,
                (now_iso, session_id),
            )
            row = conn.execute("SELECT * FROM watch_analysis_jobs WHERE id = ?", (job_id,)).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_job(row, public=True), True


def enqueue_source_plan(
    *,
    session: dict,
    plan: dict,
    priority: int = 0,
) -> tuple[dict, bool]:
    session_id = str(session.get("session_id") or "").strip()
    media_id = str((session.get("media") or {}).get("id") or "").strip()
    timeline_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
    purpose = _text(plan.get("purpose"), 80).lower()
    if not session_id or not media_id or session.get("ended_at"):
        raise ValueError("观看会话不可分析")
    if purpose not in {"identify", "timeline_prepass", "rolling"}:
        raise ValueError("后端分析计划 purpose 无效")
    duration_ms = int((session.get("media") or {}).get("duration_ms") or 0)
    timestamps_ms = _source_plan_timestamps(
        plan.get("target_timestamps_ms") or [],
        duration_ms=duration_ms,
        purpose=purpose,
    )
    if not timestamps_ms:
        raise ValueError("后端分析计划没有目标时间")
    key = _source_idempotency_key(
        session_id,
        media_id,
        timeline_epoch,
        purpose,
        timestamps_ms,
    )
    existing = get_job_by_idempotency(key, public=True)
    if existing:
        return existing, False

    now_iso = _iso(_now())
    job_id = f"watch_analysis_{uuid4().hex}"
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute(
                "SELECT media_id, timeline_epoch, status, client_lease_expires_at FROM watch_sessions WHERE id = ? AND expires_at > ?",
                (session_id, now_iso),
            ).fetchone()
            if current is None or str(current["status"] or "") == "ended":
                raise ValueError("观看会话不可分析")
            if (
                not str(current["client_lease_expires_at"] or "")
                or str(current["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能新建分析任务")
            if (
                str(current["media_id"] or "") != media_id
                or int(current["timeline_epoch"] or 0) != timeline_epoch
            ):
                raise ValueError("播放时间轴已经变化，请重新生成分析计划")
            duplicate = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if duplicate is not None:
                conn.execute("COMMIT")
                return _row_to_job(duplicate, public=True), False
            conn.execute(
                """
                INSERT INTO watch_analysis_jobs (
                    id, idempotency_key, session_id, media_id, timeline_epoch,
                    purpose, input_origin, planned_timestamps_json,
                    range_start_ms, range_end_ms, status, priority,
                    max_attempts, available_at, sample_ids_json, analysis_version,
                    input_bytes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'backend_source', ?, ?, ?, 'queued', ?, ?, ?, '[]', ?, 0, ?, ?)
                """,
                (
                    job_id,
                    key,
                    session_id,
                    media_id,
                    timeline_epoch,
                    purpose,
                    runtime_sqlite.json_dumps(timestamps_ms),
                    min(timestamps_ms),
                    max(timestamps_ms),
                    max(-100, min(100, int(priority or 0))),
                    int(WATCH_ANALYSIS_JOB_MAX_ATTEMPTS),
                    now_iso,
                    WATCH_ANALYSIS_PROMPT_VERSION,
                    now_iso,
                    now_iso,
                ),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET analysis_status = 'analyzing', analysis_error = '', updated_at = ?
                 WHERE id = ?
                """,
                (now_iso, session_id),
            )
            row = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_job(row, public=True), True


def attach_source_samples(job: dict, samples: list[dict]) -> tuple[dict | None, bool]:
    if not samples:
        raise ValueError("后端分析源没有返回样本")
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    session_id = str(job.get("session_id") or "")
    media_id = str(job.get("media_id") or "")
    timeline_epoch = int(job.get("timeline_epoch") or 0)
    purpose = str(job.get("purpose") or "rolling")
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(now + timedelta(seconds=int(WATCH_ANALYSIS_SAMPLE_TTL_SECONDS)))
    sample_ids = [str(item.get("id") or "") for item in samples]
    input_bytes = sum(int(item.get("byte_size") or 0) for item in samples)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            job_row = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE id = ? AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).fetchone()
            session_row = conn.execute(
                "SELECT media_id, timeline_epoch, status, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if job_row is None:
                rejection_reason = "lease_lost"
            elif bool(job_row["cancel_requested"]):
                rejection_reason = "cancel_requested"
            elif session_row is None or str(session_row["status"] or "") == "ended":
                rejection_reason = "session_ended"
            elif (
                not str(session_row["client_lease_expires_at"] or "")
                or str(session_row["client_lease_expires_at"] or "") <= now_iso
            ):
                rejection_reason = "client_lease_expired"
            elif (
                str(session_row["media_id"] or "") != media_id
                or int(session_row["timeline_epoch"] or 0) != timeline_epoch
            ):
                rejection_reason = "stale_timeline"
            else:
                rejection_reason = ""
            if rejection_reason:
                if job_row is not None:
                    conn.execute(
                        """
                        UPDATE watch_analysis_jobs
                           SET status = 'cancelled', cancel_requested = 1,
                               cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END,
                               cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?,
                               leased_until = '', lease_token = ''
                         WHERE id = ? AND status = 'running' AND lease_token = ?
                        """,
                        (
                            now_iso,
                            rejection_reason,
                            rejection_reason,
                            now_iso,
                            now_iso,
                            job_id,
                            lease_token,
                        ),
                    )
                conn.execute("COMMIT")
                return None, False
            existing_ids = runtime_sqlite.json_loads(job_row["sample_ids_json"], [])
            if existing_ids:
                placeholders = ",".join("?" for _ in existing_ids)
                existing_count = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS n FROM watch_analysis_samples WHERE id IN ({placeholders})",
                        existing_ids,
                    ).fetchone()["n"]
                    or 0
                )
                if existing_count:
                    conn.execute("COMMIT")
                    return _row_to_job(job_row, public=False), False
            for item in samples:
                conn.execute(
                    """
                    INSERT INTO watch_analysis_samples (
                        id, session_id, media_id, timeline_epoch, purpose, at_ms,
                        mime_type, file_path, text_content, subtitle, sha256,
                        perceptual_hash, width, height, byte_size, captured_at,
                        created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"], session_id, media_id, timeline_epoch, purpose,
                        int(item.get("at_ms") or 0), item.get("mime_type") or "",
                        item.get("file_path") or "", item.get("text_content") or "",
                        item.get("subtitle") or "", item.get("sha256") or "",
                        item.get("perceptual_hash") or "", int(item.get("width") or 0),
                        int(item.get("height") or 0), int(item.get("byte_size") or 0),
                        item.get("captured_at") or "", now_iso, expires_at,
                    ),
                )
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET sample_ids_json = ?, input_bytes = ?, range_start_ms = ?,
                       range_end_ms = ?, updated_at = ?
                 WHERE id = ? AND status = 'running' AND lease_token = ?
                """,
                (
                    runtime_sqlite.json_dumps(sample_ids),
                    input_bytes,
                    min(int(item.get("at_ms") or 0) for item in samples),
                    max(int(item.get("at_ms") or 0) for item in samples),
                    now_iso,
                    job_id,
                    lease_token,
                ),
            )
            refreshed = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_job(refreshed, public=False), True


def load_job_samples(job: dict) -> list[dict]:
    ids = [str(value or "").strip() for value in (job.get("sample_ids") or []) if str(value or "").strip()]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM watch_analysis_samples WHERE id IN ({placeholders}) ORDER BY at_ms, id",
            ids,
        ).fetchall()
    by_id = {str(row["id"]): _row_to_sample(row) for row in rows}
    return [by_id[value] for value in ids if value in by_id]


def claim_next_job(*, stale_after_seconds: int) -> dict | None:
    now = _now()
    now_iso = _iso(now)
    lease_until = _iso(now + timedelta(seconds=max(30, int(stale_after_seconds or 300))))
    lease_token = uuid4().hex
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT j.* FROM watch_analysis_jobs j
                JOIN watch_sessions s ON s.id = j.session_id
                 WHERE j.attempts < j.max_attempts
                   AND j.cancel_requested = 0
                   AND s.status != 'ended'
                   AND s.client_lease_expires_at != ''
                   AND s.client_lease_expires_at > ?
                   AND (
                        (j.status = 'queued' AND j.available_at <= ?)
                        OR (j.status = 'running' AND j.leased_until != '' AND j.leased_until <= ?)
                   )
                 ORDER BY j.priority DESC, j.created_at, j.id
                 LIMIT 1
                """,
                (now_iso, now_iso, now_iso),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            job_id = str(row["id"])
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'running', attempts = attempts + 1,
                       lease_token = ?, leased_until = ?, started_at = CASE WHEN started_at = '' THEN ? ELSE started_at END,
                       updated_at = ?, error = ''
                 WHERE id = ? AND cancel_requested = 0
                """,
                (lease_token, lease_until, now_iso, now_iso, job_id),
            )
            claimed = conn.execute("SELECT * FROM watch_analysis_jobs WHERE id = ?", (job_id,)).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_job(claimed, public=False)


def heartbeat_job(job_id: str, lease_token: str, *, lease_seconds: int) -> bool:
    now = _now()
    with runtime_sqlite.connect() as conn:
        result = conn.execute(
            """
            UPDATE watch_analysis_jobs
               SET leased_until = ?, updated_at = ?
             WHERE id = ? AND status = 'running' AND lease_token = ?
               AND cancel_requested = 0
            """,
            (_iso(now + timedelta(seconds=max(30, lease_seconds))), _iso(now), job_id, lease_token),
        )
    return bool(result.rowcount)


def execution_skip_reason(job: dict) -> str:
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT j.status AS job_status, j.cancel_requested, j.lease_token,
                   j.media_id AS job_media_id, j.timeline_epoch AS job_epoch,
                   j.purpose, s.status AS session_status, s.ended_at,
                   s.client_lease_expires_at, s.media_id AS session_media_id,
                   s.timeline_epoch AS session_epoch
              FROM watch_analysis_jobs j
              LEFT JOIN watch_sessions s ON s.id = j.session_id
             WHERE j.id = ?
            """,
            (_text(job_id, 160),),
        ).fetchone()
    if row is None:
        return "cancel_requested"
    if bool(row["cancel_requested"]):
        return "cancel_requested"
    if str(row["job_status"] or "") != "running" or str(row["lease_token"] or "") != lease_token:
        return "lease_lost"
    if not str(row["session_status"] or "") or str(row["session_status"] or "") == "ended" or str(row["ended_at"] or ""):
        return "session_ended"
    client_lease_expires_at = str(row["client_lease_expires_at"] or "")
    if not client_lease_expires_at or client_lease_expires_at <= now_iso:
        return "client_lease_expired"
    if str(row["job_media_id"] or "") != str(row["session_media_id"] or ""):
        return "stale_timeline"
    if str(row["purpose"] or "") not in {"knowledge_card", "subtitle_lookup"} and int(
        row["job_epoch"] or 0
    ) != int(row["session_epoch"] or 0):
        return "stale_timeline"
    return ""


def cancel_claimed_job(job: dict, *, reason: str) -> bool:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        result = conn.execute(
            """
            UPDATE watch_analysis_jobs
               SET status = 'cancelled', cancel_requested = 1,
                   cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END,
                   cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?,
                   leased_until = '', lease_token = ''
             WHERE id = ? AND status = 'running' AND lease_token = ?
            """,
            (
                now_iso,
                _text(reason, 1000),
                _text(reason, 1000),
                now_iso,
                now_iso,
                _text(job.get("job_id"), 160),
                _text(job.get("lease_token"), 200),
            ),
        )
    return bool(result.rowcount)


def purge_session_samples(session_id: str) -> int:
    now_iso = _iso(_now())
    purged = 0
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, file_path FROM watch_analysis_samples
             WHERE session_id = ? AND purged_at = ''
            """,
            (_text(session_id, 160),),
        ).fetchall()
        for row in rows:
            path = str(row["file_path"] or "")
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
            conn.execute(
                "UPDATE watch_analysis_samples SET file_path = '', purged_at = ? WHERE id = ?",
                (now_iso, str(row["id"] or "")),
            )
            purged += 1
    return purged


def mark_job_cancelled(job_id: str, *, reason: str = "") -> bool:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        result = conn.execute(
            """
            UPDATE watch_analysis_jobs
               SET status = 'cancelled', cancel_requested = 1,
                   cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END,
                   cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?,
                   leased_until = '', lease_token = ''
             WHERE id = ? AND status IN ('queued', 'running')
            """,
            (
                now_iso,
                _text(reason, 1000),
                _text(reason, 1000),
                now_iso,
                now_iso,
                job_id,
            ),
        )
    return bool(result.rowcount)


def cancel_stale_jobs(session_id: str, *, current_epoch: int | None = None, reason: str) -> int:
    clauses = ["session_id = ?", "status IN ('queued', 'running')"]
    where_params: list[Any] = [_text(session_id, 160)]
    if current_epoch is not None:
        clauses.append("timeline_epoch != ?")
        where_params.append(_int(current_epoch, 0))
        clauses.append("purpose != 'knowledge_card'")
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT sample_ids_json FROM watch_analysis_jobs WHERE {' AND '.join(clauses)}",
            where_params,
        ).fetchall()
        sample_ids: list[str] = []
        for row in rows:
            for value in runtime_sqlite.json_loads(row["sample_ids_json"], []):
                sample_id = str(value or "").strip()
                if sample_id and sample_id not in sample_ids:
                    sample_ids.append(sample_id)
        result = conn.execute(
            f"""
            UPDATE watch_analysis_jobs
               SET status = 'cancelled', cancel_requested = 1,
                   cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END,
                   cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?,
                   leased_until = '', lease_token = ''
             WHERE {' AND '.join(clauses)}
            """,
            (
                now_iso,
                _text(reason, 1000),
                _text(reason, 1000),
                now_iso,
                now_iso,
                *where_params,
            ),
        )
        if sample_ids:
            placeholders = ",".join("?" for _ in sample_ids)
            sample_rows = conn.execute(
                f"SELECT id, file_path FROM watch_analysis_samples WHERE id IN ({placeholders})",
                sample_ids,
            ).fetchall()
            for sample_row in sample_rows:
                file_path = str(sample_row["file_path"] or "").strip()
                if file_path:
                    try:
                        Path(file_path).unlink(missing_ok=True)
                    except Exception:
                        pass
            conn.execute(
                f"""
                UPDATE watch_analysis_samples
                   SET file_path = '', purged_at = ?
                 WHERE id IN ({placeholders})
                """,
                (now_iso, *sample_ids),
            )
        if current_epoch is None:
            conn.execute(
                """
                UPDATE watch_client_sample_plans
                   SET status = 'cancelled', cancelled_at = ?
                 WHERE session_id = ? AND status = 'open'
                """,
                (now_iso, _text(session_id, 160)),
            )
        else:
            conn.execute(
                """
                UPDATE watch_client_sample_plans
                   SET status = 'cancelled', cancelled_at = ?
                 WHERE session_id = ? AND timeline_epoch != ? AND status = 'open'
                """,
                (now_iso, _text(session_id, 160), _int(current_epoch, 0)),
            )
    return int(result.rowcount or 0)


def fail_job(
    job: dict,
    error: str,
    *,
    retryable: bool,
    usage: dict | None = None,
) -> str:
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or WATCH_ANALYSIS_JOB_MAX_ATTEMPTS)
    terminal = not retryable or attempts >= max_attempts
    now = _now()
    status = "failed" if terminal else "queued"
    purpose = str(job.get("purpose") or "")
    available_at = _iso(now + timedelta(seconds=min(120, 2 ** max(1, attempts))))
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current_job = conn.execute(
                """
                SELECT status, lease_token, cancel_requested, usage_json
                  FROM watch_analysis_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if current_job is None:
                conn.execute("COMMIT")
                return "cancelled"
            if (
                str(current_job["status"] or "") != "running"
                or str(current_job["lease_token"] or "") != lease_token
            ):
                current_status = str(current_job["status"] or "cancelled")
                conn.execute("COMMIT")
                return current_status
            session = conn.execute(
                """
                SELECT media_id, timeline_epoch, status, analysis_covered_until_ms,
                       client_lease_expires_at
                  FROM watch_sessions WHERE id = ?
                """,
                (job.get("session_id"),),
            ).fetchone()
            if bool(current_job["cancel_requested"]):
                cancellation_reason = "cancel_requested"
            elif session is None or str(session["status"] or "") == "ended":
                cancellation_reason = "session_ended"
            elif (
                not str(session["client_lease_expires_at"] or "")
                or str(session["client_lease_expires_at"] or "") <= _iso(now)
            ):
                cancellation_reason = "client_lease_expired"
            elif str(session["media_id"] or "") != str(job.get("media_id") or "") or (
                purpose not in {"knowledge_card", "subtitle_lookup"}
                and int(session["timeline_epoch"] or 0) != int(job.get("timeline_epoch") or 0)
            ):
                cancellation_reason = "stale_timeline"
            else:
                cancellation_reason = ""
            if cancellation_reason:
                conn.execute(
                    """
                    UPDATE watch_analysis_jobs
                       SET status = 'cancelled', cancel_requested = 1,
                           cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END,
                           cancel_reason = ?, error = ?,
                           finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                     WHERE id = ? AND status = 'running' AND lease_token = ?
                    """,
                    (
                        _iso(now),
                        cancellation_reason,
                        cancellation_reason,
                        _iso(now),
                        _iso(now),
                        job_id,
                        lease_token,
                    ),
                )
                conn.execute("COMMIT")
                return "cancelled"
            merged_usage = _merge_usage(
                runtime_sqlite.json_loads(current_job["usage_json"], {}),
                usage or {},
            )
            result = conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = ?, available_at = ?, leased_until = '', lease_token = '',
                       error = ?, finished_at = ?, updated_at = ?, usage_json = ?,
                       input_tokens = ?, output_tokens = ?, cost_usd = ?
                 WHERE id = ? AND status = 'running' AND lease_token = ?
                """,
                (
                    status,
                    available_at,
                    _text(error, 2000),
                    _iso(now) if terminal else "",
                    _iso(now),
                    runtime_sqlite.json_dumps(merged_usage),
                    merged_usage["input_tokens"],
                    merged_usage["output_tokens"],
                    merged_usage["cost_usd"],
                    job_id,
                    lease_token,
                ),
            )
            if result.rowcount and purpose == "knowledge_card":
                preparation_status = "knowledge_failed" if terminal else "collecting_sources"
                knowledge_status = "failed" if terminal else "queued"
                conn.execute(
                    """
                    UPDATE watch_sessions
                       SET preparation_status = ?, knowledge_card_status = ?,
                           knowledge_card_error = ?, updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        preparation_status,
                        knowledge_status,
                        _text(error, 2000),
                        _iso(now),
                        job.get("session_id"),
                    ),
                )
            elif terminal and result.rowcount:
                analysis_status = "degraded" if session and int(session["analysis_covered_until_ms"] or 0) > 0 else "failed"
                conn.execute(
                    "UPDATE watch_sessions SET analysis_status = ?, analysis_error = ?, updated_at = ? WHERE id = ?",
                    (analysis_status, _text(error, 2000), _iso(now), job.get("session_id")),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return status


def defer_job(job: dict, *, available_at: datetime, reason: str) -> bool:
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        result = conn.execute(
            """
            UPDATE watch_analysis_jobs
               SET status = 'queued', attempts = CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END,
                   available_at = ?, leased_until = '', lease_token = '', error = ?, updated_at = ?
             WHERE id = ? AND status = 'running' AND lease_token = ?
               AND cancel_requested = 0
               AND EXISTS (
                    SELECT 1 FROM watch_sessions s
                     WHERE s.id = watch_analysis_jobs.session_id
                       AND s.status != 'ended'
                       AND s.client_lease_expires_at != ''
                       AND s.client_lease_expires_at > ?
               )
            """,
            (
                _iso(available_at),
                _text(reason, 1000),
                now_iso,
                job_id,
                lease_token,
                now_iso,
            ),
        )
    return bool(result.rowcount)


def reset_for_epoch(session_id: str, *, timeline_epoch: int) -> None:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE watch_sessions
               SET analysis_status = 'pending', analysis_covered_from_ms = 0,
                   analysis_covered_until_ms = 0, analysis_error = '',
                   story_so_far_json = '{}', analysis_story_state_json = '{}',
                   updated_at = ?
             WHERE id = ? AND timeline_epoch = ? AND status != 'ended'
            """,
            (now_iso, _text(session_id, 160), _int(timeline_epoch, 0)),
        )
        conn.execute(
            """
            UPDATE watch_client_sample_plans
               SET status = 'cancelled', cancelled_at = ?
             WHERE session_id = ? AND timeline_epoch != ? AND status = 'open'
            """,
            (now_iso, _text(session_id, 160), _int(timeline_epoch, 0)),
        )


def get_story_checkpoint(session_id: str, *, timeline_epoch: int, through_ms: int) -> dict:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_story_checkpoints
             WHERE session_id = ? AND timeline_epoch = ? AND through_ms <= ?
             ORDER BY through_ms DESC, created_at DESC
             LIMIT 1
            """,
            (_text(session_id, 160), _int(timeline_epoch, 0), _int(through_ms, 0)),
        ).fetchone()
    if row is None:
        return {}
    summary = runtime_sqlite.json_loads(row["summary_json"], {})
    return summary if isinstance(summary, dict) else {}


def _series_key(session: dict) -> str:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    source = _text(media.get("source"), 80).lower()
    title = " ".join(_text(media.get("title"), 300).lower().split())
    if not title:
        return ""
    if source == "local_file":
        local_media = media.get("local_media") if isinstance(media.get("local_media"), dict) else {}
        revision = str(local_media.get("media_revision") or "").strip()
        return f"{source}:{title}:{revision}"
    return f"{source}:{title}"


def _hamming_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except Exception:
        return 65


def reusable_timeline_sections(session: dict, samples: list[dict], *, max_distance: int = 8) -> list[dict]:
    series_key = _series_key(session)
    duration_ms = int((session.get("media") or {}).get("duration_ms") or 0)
    if not series_key:
        return []
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watch_timeline_fingerprints
             WHERE series_key = ?
             ORDER BY created_at DESC
             LIMIT 1000
            """,
            (series_key,),
        ).fetchall()
    matches: dict[tuple, int] = {}
    confidence_by_key: dict[tuple, float] = {}
    for sample in samples:
        sample_hash = str(sample.get("perceptual_hash") or "")
        if not sample_hash:
            continue
        for row in rows:
            source_duration = int(row["duration_ms"] or 0)
            duration_tolerance = max(15_000, int(duration_ms * 0.1))
            if duration_ms > 0 and source_duration > 0 and abs(duration_ms - source_duration) > duration_tolerance:
                continue
            if _hamming_distance(sample_hash, str(row["perceptual_hash"] or "")) > max_distance:
                continue
            key = (
                str(row["source_media_id"] or ""),
                str(row["kind"] or ""),
                int(row["section_start_ms"] or 0),
                int(row["section_end_ms"] or 0),
            )
            matches[key] = matches.get(key, 0) + 1
            confidence_by_key[key] = max(confidence_by_key.get(key, 0), float(row["confidence"] or 0))
    out: list[dict] = []
    seen: set[tuple] = set()
    for key, count in sorted(matches.items(), key=lambda item: (-item[1], item[0])):
        _source_media_id, kind, start_ms, end_ms = key
        section_key = (kind, start_ms, end_ms)
        if count < 2 or section_key in seen:
            continue
        seen.add(section_key)
        out.append(
            {
                "kind": kind,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": min(0.98, max(0.7, confidence_by_key[key] * 0.9)),
                "source": "fingerprint_reuse",
            }
        )
    return out


SKIPPED_TIMELINE_KINDS = {"recap", "intro", "outro", "preview", "non_story"}
TIMELINE_BOUNDARY_TOLERANCE_MS = 1000


def _overlaps_skipped(start_ms: int, end_ms: int, sections: list[dict]) -> bool:
    return any(
        str(section.get("kind") or "") in SKIPPED_TIMELINE_KINDS
        and start_ms < int(section.get("end_ms") or 0)
        and end_ms > int(section.get("start_ms") or 0)
        for section in sections
    )


def _advance_past_skipped(position_ms: int, sections: list[dict]) -> int:
    position = max(0, int(position_ms))
    ordered = sorted(
        sections,
        key=lambda item: (int(item.get("start_ms") or 0), int(item.get("end_ms") or 0)),
    )
    advanced = True
    while advanced:
        advanced = False
        for section in ordered:
            if str(section.get("kind") or "") not in SKIPPED_TIMELINE_KINDS:
                continue
            start_ms = int(section.get("start_ms") or 0)
            end_ms = int(section.get("end_ms") or 0)
            if end_ms <= position:
                continue
            if start_ms <= position + TIMELINE_BOUNDARY_TOLERANCE_MS:
                position = end_ms
                advanced = True
    return position


def _next_skipped_start(position_ms: int, sections: list[dict]) -> int | None:
    position = max(0, int(position_ms))
    candidates = [
        int(section.get("start_ms") or 0)
        for section in sections
        if str(section.get("kind") or "") in SKIPPED_TIMELINE_KINDS
        and int(section.get("end_ms") or 0) > position
        and int(section.get("start_ms") or 0) > position + TIMELINE_BOUNDARY_TOLERANCE_MS
    ]
    return min(candidates) if candidates else None


def commit_analysis_result(
    job: dict,
    *,
    result: dict,
    usage: dict,
    samples: list[dict],
) -> dict:
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    session_id = str(job.get("session_id") or "")
    media_id = str(job.get("media_id") or "")
    timeline_epoch = int(job.get("timeline_epoch") or 0)
    purpose = str(job.get("purpose") or "rolling")
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            job_row = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE id = ? AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).fetchone()
            if job_row is None:
                conn.execute("ROLLBACK")
                return {"applied": False, "reason": "lease_lost"}
            session_row = conn.execute(
                "SELECT * FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if bool(job_row["cancel_requested"]):
                rejection_reason = "cancel_requested"
            elif session_row is None or str(session_row["status"] or "") == "ended":
                rejection_reason = "session_ended"
            elif (
                not str(session_row["client_lease_expires_at"] or "")
                or str(session_row["client_lease_expires_at"] or "") <= now_iso
            ):
                rejection_reason = "client_lease_expired"
            elif (
                str(session_row["media_id"] or "") != media_id
                or int(session_row["timeline_epoch"] or 0) != timeline_epoch
            ):
                rejection_reason = "stale_timeline"
            else:
                rejection_reason = ""
            if rejection_reason:
                conn.execute(
                    """
                    UPDATE watch_analysis_jobs
                       SET status = 'cancelled', cancel_requested = 1,
                           cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END,
                           cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?,
                           leased_until = '', lease_token = ''
                     WHERE id = ?
                    """,
                    (
                        now_iso,
                        rejection_reason,
                        rejection_reason,
                        now_iso,
                        now_iso,
                        job_id,
                    ),
                )
                conn.execute("COMMIT")
                return {"applied": False, "reason": rejection_reason}

            current_sections = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM watch_timeline_sections WHERE session_id = ? AND timeline_epoch = ?",
                    (session_id, timeline_epoch),
                ).fetchall()
            ]
            incoming_sections = result.get("timeline_sections") if isinstance(result.get("timeline_sections"), list) else []
            if purpose == "timeline_prepass" and incoming_sections:
                conn.execute(
                    """
                    DELETE FROM watch_timeline_sections
                     WHERE session_id = ? AND timeline_epoch = ? AND source != 'manual'
                    """,
                    (session_id, timeline_epoch),
                )
                current_sections = [section for section in current_sections if str(section.get("source") or "") == "manual"]
                for section in incoming_sections:
                    digest = hashlib.sha256(
                        f"{session_id}:{timeline_epoch}:{section.get('kind')}:{section.get('start_ms')}:{section.get('end_ms')}".encode()
                    ).hexdigest()[:20]
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO watch_timeline_sections (
                            id, session_id, timeline_epoch, kind, start_ms, end_ms,
                            source, confidence, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"watch_section_{digest}", session_id, timeline_epoch,
                            section.get("kind") or "unknown", int(section.get("start_ms") or 0),
                            int(section.get("end_ms") or 0), section.get("source") or "vision_prepass",
                            float(section.get("confidence") or 0), now_iso, now_iso,
                        ),
                    )
                    current_sections.append(section)

            analysis_version = _text(result.get("analysis_version"), 160)
            for chunk in result.get("plot_chunks") if isinstance(result.get("plot_chunks"), list) else []:
                start_ms = int(chunk.get("start_ms") or 0)
                end_ms = int(chunk.get("end_ms") or 0)
                if end_ms <= start_ms or _overlaps_skipped(start_ms, end_ms, current_sections):
                    continue
                digest = hashlib.sha256(
                    f"{session_id}:{timeline_epoch}:{start_ms}:{end_ms}:{analysis_version}".encode()
                ).hexdigest()[:20]
                conn.execute(
                    """
                    INSERT INTO watch_plot_chunks (
                        id, session_id, media_id, timeline_epoch, start_ms, end_ms,
                        summary, visual_description, dialogue_summary, characters_json,
                        tags_json, confidence, analysis_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        summary = excluded.summary, visual_description = excluded.visual_description,
                        dialogue_summary = excluded.dialogue_summary, characters_json = excluded.characters_json,
                        tags_json = excluded.tags_json, confidence = excluded.confidence,
                        analysis_version = excluded.analysis_version, updated_at = excluded.updated_at
                    """,
                    (
                        f"watch_plot_{digest}", session_id, media_id, timeline_epoch, start_ms, end_ms,
                        _text(chunk.get("summary"), 6000), _text(chunk.get("visual_description"), 6000),
                        _text(chunk.get("dialogue_summary"), 6000),
                        runtime_sqlite.json_dumps(chunk.get("characters") if isinstance(chunk.get("characters"), list) else []),
                        runtime_sqlite.json_dumps(chunk.get("tags") if isinstance(chunk.get("tags"), list) else []),
                        float(chunk.get("confidence") or 0), analysis_version, now_iso, now_iso,
                    ),
                )

            if bool(session_row["fear_mode"]):
                for event in result.get("risk_events") if isinstance(result.get("risk_events"), list) else []:
                    start_ms = int(event.get("start_ms") or 0)
                    end_ms = int(event.get("end_ms") or 0)
                    if end_ms <= start_ms or _overlaps_skipped(start_ms, end_ms, current_sections):
                        continue
                    digest = hashlib.sha256(
                        f"{session_id}:{timeline_epoch}:{event.get('risk_type')}:{start_ms}:{end_ms}:{analysis_version}".encode()
                    ).hexdigest()[:20]
                    conn.execute(
                        """
                        INSERT INTO watch_risk_events (
                            id, session_id, media_id, timeline_epoch, risk_type, severity,
                            start_ms, end_ms, warn_at_ms, label, companion_hint, confidence,
                            status, analysis_version, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            severity = excluded.severity, warn_at_ms = excluded.warn_at_ms,
                            label = excluded.label, companion_hint = excluded.companion_hint,
                            confidence = excluded.confidence, status = excluded.status,
                            analysis_version = excluded.analysis_version, updated_at = excluded.updated_at
                        """,
                        (
                            f"watch_risk_{digest}", session_id, media_id, timeline_epoch,
                            event.get("risk_type") or "other", event.get("severity") or "1",
                            start_ms, end_ms, int(event.get("warn_at_ms") or start_ms),
                            _text(event.get("label"), 300), _text(event.get("companion_hint"), 1000),
                            float(event.get("confidence") or 0), analysis_version, now_iso, now_iso,
                        ),
                    )

            story_background = (
                result.get("story_background")
                if isinstance(result.get("story_background"), dict)
                else {}
            )
            has_story_background = bool(
                _text(story_background.get("background"), 5000)
                or (
                    story_background.get("characters")
                    if isinstance(story_background.get("characters"), list)
                    else []
                )
            )
            if purpose == "rolling" and has_story_background:
                through_ms = int(story_background.get("through_ms") or result.get("covered_until_ms") or 0)
                checkpoint_digest = hashlib.sha256(
                    f"{session_id}:{timeline_epoch}:{through_ms}:{analysis_version}".encode()
                ).hexdigest()[:20]
                conn.execute(
                    """
                    INSERT OR REPLACE INTO watch_story_checkpoints (
                        id, session_id, media_id, timeline_epoch, through_ms,
                        summary_json, story_state_json, analysis_version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"watch_story_{checkpoint_digest}", session_id, media_id, timeline_epoch,
                        through_ms, runtime_sqlite.json_dumps(story_background),
                        "{}", analysis_version, now_iso,
                    ),
                )

            if purpose == "timeline_prepass" and incoming_sections:
                series_key = _series_key({
                    "media": {
                        "source": session_row["source"],
                        "title": session_row["title"],
                        "local_media": runtime_sqlite.json_loads(
                            session_row["local_media_json"], {}
                        ),
                    }
                })
                if series_key:
                    for sample in samples:
                        sample_at = int(sample.get("at_ms") or 0)
                        sample_hash = str(sample.get("perceptual_hash") or "")
                        if not sample_hash:
                            continue
                        for section in incoming_sections:
                            if not (
                                str(section.get("kind") or "") in {"intro", "outro", "non_story"}
                                and int(section.get("start_ms") or 0) <= sample_at <= int(section.get("end_ms") or 0)
                            ):
                                continue
                            digest = hashlib.sha256(
                                f"{series_key}:{media_id}:{section.get('kind')}:{sample_at}:{sample_hash}".encode()
                            ).hexdigest()[:20]
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO watch_timeline_fingerprints (
                                    id, series_key, source_media_id, kind, section_start_ms,
                                    section_end_ms, sample_at_ms, perceptual_hash, duration_ms,
                                    confidence, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    f"watch_fp_{digest}", series_key, media_id, section.get("kind"),
                                    int(section.get("start_ms") or 0), int(section.get("end_ms") or 0),
                                    sample_at, sample_hash, int(session_row["duration_ms"] or 0),
                                    float(section.get("confidence") or 0), now_iso,
                                ),
                            )

            familiarity = str(session_row["analysis_familiarity"] or "pending")
            identity = str(session_row["analysis_identity"] or "")
            original_title = str(session_row["analysis_original_title"] or "")
            identity_year = int(session_row["analysis_year"] or 0)
            if purpose == "identify":
                familiarity = _text(result.get("familiarity"), 80) or "unknown"
                identity = _text(result.get("identity"), 500)
                original_title = _text(result.get("original_title"), 300)
                identity_year = max(0, int(result.get("identity_year") or 0))
                if bool(session_row["force_unknown_analysis"]):
                    familiarity = "unknown"
            covered_from = int(session_row["analysis_covered_from_ms"] or 0)
            covered_until = int(session_row["analysis_covered_until_ms"] or 0)
            if purpose == "rolling":
                incoming_from = int(result.get("covered_from_ms") or 0)
                incoming_until = int(result.get("covered_until_ms") or 0)
                covered_from = incoming_from if covered_until <= 0 else min(covered_from, incoming_from)
                covered_until = max(covered_until, incoming_until)
            covered_until = _advance_past_skipped(covered_until, current_sections)
            if int(session_row["duration_ms"] or 0) > 0:
                covered_until = min(covered_until, int(session_row["duration_ms"] or 0))
            playhead_ms = int(session_row["playhead_ms"] or 0)
            duration_ms = int(session_row["duration_ms"] or 0)
            required_buffer = int(WATCH_ANALYSIS_INITIAL_READY_BUFFER_MS)
            ready_until = playhead_ms + required_buffer
            content_end_ms = int(session_row["content_end_ms"] or -1)
            if content_end_ms >= 0:
                ready_until = min(content_end_ms, ready_until)
            elif duration_ms > 0:
                ready_until = min(duration_ms, ready_until)
            completed_rolling = purpose == "rolling" or conn.execute(
                """
                SELECT 1 FROM watch_analysis_jobs
                 WHERE session_id = ? AND timeline_epoch = ?
                   AND purpose = 'rolling' AND status = 'done'
                 LIMIT 1
                """,
                (session_id, timeline_epoch),
            ).fetchone() is not None
            if duration_ms > 0 and covered_until >= duration_ms and current_sections:
                completed_rolling = True
            ready = completed_rolling and covered_until >= ready_until
            analysis_status = "ready" if ready else "analyzing"
            should_unlock_playback = bool(
                str(session_row["started_at"] or "").strip()
                and not str(session_row["playback_unlocked_at"] or "").strip()
                and ready
            )
            persisted_story_background = runtime_sqlite.json_loads(
                session_row["story_so_far_json"], {}
            )
            persisted_story_state = runtime_sqlite.json_loads(session_row["analysis_story_state_json"], {})
            if purpose == "rolling":
                persisted_story_background = story_background if has_story_background else {}
                persisted_story_state = {}
            conn.execute(
                """
                UPDATE watch_sessions
                   SET analysis_familiarity = ?, analysis_identity = ?,
                       analysis_original_title = ?, analysis_year = ?, analysis_status = ?,
                       analysis_covered_from_ms = ?, analysis_covered_until_ms = ?,
                       analysis_error = '', story_so_far_json = ?, analysis_story_state_json = ?,
                       playback_unlocked_at = CASE WHEN ? THEN ? ELSE playback_unlocked_at END,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    familiarity, identity, original_title, identity_year, analysis_status,
                    covered_from, covered_until,
                    runtime_sqlite.json_dumps(persisted_story_background),
                    runtime_sqlite.json_dumps(persisted_story_state),
                    int(should_unlock_playback), now_iso,
                    now_iso, session_id,
                ),
            )
            merged_usage = _merge_usage(
                runtime_sqlite.json_loads(job_row["usage_json"], {}),
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
                    runtime_sqlite.json_dumps(result),
                    runtime_sqlite.json_dumps(merged_usage),
                    merged_usage["input_tokens"],
                    merged_usage["output_tokens"],
                    merged_usage["cost_usd"],
                    job_id,
                ),
            )
            sample_ids = [str(sample.get("id") or "") for sample in samples]
            if sample_ids:
                placeholders = ",".join("?" for _ in sample_ids)
                conn.execute(
                    f"UPDATE watch_analysis_samples SET consumed_at = ? WHERE id IN ({placeholders})",
                    (now_iso, *sample_ids),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"applied": True, "analysis_status": analysis_status}


def daily_cost_usd(now: datetime | None = None) -> float:
    current = now or _now()
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0) AS total
              FROM watch_analysis_jobs
             WHERE status = 'done' AND finished_at >= ?
            """,
            (_iso(day_start),),
        ).fetchone()
    return float(row["total"] or 0)


def session_analysis_cost(session_id: str) -> dict:
    placeholders = ",".join("?" for _ in ANALYSIS_MODEL_PURPOSES)
    params = [_text(session_id, 160), *sorted(ANALYSIS_MODEL_PURPOSES)]
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT status, usage_json
              FROM watch_analysis_jobs
             WHERE session_id = ? AND purpose IN ({placeholders})
             ORDER BY created_at, id
            """,
            params,
        ).fetchall()
    totals = _usage_totals({})
    pending_jobs = 0
    for row in rows:
        usage = _usage_totals(runtime_sqlite.json_loads(row["usage_json"], {}))
        totals = _usage_totals(_merge_usage(totals, usage))
        if str(row["status"] or "") in {"queued", "running"}:
            pending_jobs += 1
    return {
        "currency": "USD",
        "amount_usd": totals["cost_usd"],
        "complete": pending_jobs == 0 and totals["priced_calls"] >= totals["provider_calls"],
        "provider_calls": totals["provider_calls"],
        "priced_calls": totals["priced_calls"],
        "pending_jobs": pending_jobs,
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
    }


def cost_budget_available() -> bool:
    limit = float(WATCH_ANALYSIS_DAILY_MAX_COST_USD or 0)
    return limit <= 0 or daily_cost_usd() < limit


def session_job_runtime(session_id: str) -> dict:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ? GROUP BY status",
            (_text(session_id, 160),),
        ).fetchall()
        latest = conn.execute(
            "SELECT * FROM watch_analysis_jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (_text(session_id, 160),),
        ).fetchone()
    return {
        "counts": {str(row["status"]): int(row["n"] or 0) for row in rows},
        "latest_job": _row_to_job(latest, public=True) if latest is not None else {},
        "daily_cost_usd": daily_cost_usd(),
        "daily_cost_limit_usd": float(WATCH_ANALYSIS_DAILY_MAX_COST_USD or 0),
    }


def _has_completed_job(session_id: str, purpose: str, timeline_epoch: int) -> bool:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM watch_analysis_jobs
             WHERE session_id = ? AND purpose = ? AND timeline_epoch = ? AND status = 'done'
             LIMIT 1
            """,
            (_text(session_id, 160), purpose, _int(timeline_epoch, 0)),
        ).fetchone()
    return row is not None


def _active_job(session_id: str, purpose: str, timeline_epoch: int) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_analysis_jobs
             WHERE session_id = ? AND purpose = ? AND timeline_epoch = ?
               AND status IN ('queued', 'running')
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (_text(session_id, 160), purpose, _int(timeline_epoch, 0)),
        ).fetchone()
    return _row_to_job(row, public=True) if row is not None else None


def _gateway_plan(plan: dict) -> dict:
    return {
        "managed_by": "gateway",
        "input_origin": "backend_source",
        "client_upload_required": False,
        "audio_required": False,
        **plan,
    }


def _local_media_state(session: dict) -> dict:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    local_media = media.get("local_media")
    return local_media if isinstance(local_media, dict) else {}


def _row_to_client_plan(row: Any) -> dict:
    return {
        "plan_id": str(row["id"] or ""),
        "session_id": str(row["session_id"] or ""),
        "media_id": str(row["media_id"] or ""),
        "media_revision": str(row["media_revision"] or ""),
        "timeline_epoch": int(row["timeline_epoch"] or 0),
        "purpose": str(row["purpose"] or ""),
        "target_timestamps_ms": runtime_sqlite.json_loads(
            row["target_timestamps_json"], []
        ),
        "allowed_start_ms": int(row["allowed_start_ms"] or 0),
        "allowed_end_ms": int(row["allowed_end_ms"] or 0),
        "status": str(row["status"] or ""),
        "job_id": str(row["job_id"] or ""),
        "issued_at": str(row["created_at"] or ""),
        "expires_at": str(row["expires_at"] or ""),
        "consumed_at": str(row["consumed_at"] or ""),
    }


def _issue_client_plan(session: dict, plan: dict) -> dict:
    session_id = str(session.get("session_id") or "")
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    playback = session.get("playback") if isinstance(session.get("playback"), dict) else {}
    local_media = _local_media_state(session)
    media_id = str(media.get("id") or "")
    media_revision = str(local_media.get("media_revision") or "")
    timeline_epoch = int(playback.get("timeline_epoch") or 0)
    purpose = str(plan.get("purpose") or "")
    targets = sorted({_int(value, 0) for value in plan.get("target_timestamps_ms") or []})
    allowed_start_ms = _int(
        plan.get("audio_range_start_ms"),
        min(targets) if targets else 0,
    )
    allowed_end_ms = _int(
        plan.get("audio_range_end_ms"),
        max(targets) if targets else allowed_start_ms,
    )
    if allowed_end_ms < allowed_start_ms:
        allowed_end_ms = allowed_start_ms
    digest_payload = "|".join(
        [
            session_id,
            media_id,
            media_revision,
            str(timeline_epoch),
            purpose,
            ",".join(str(value) for value in targets),
            str(allowed_start_ms),
            str(allowed_end_ms),
        ]
    )
    plan_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(
        now + timedelta(seconds=int(WATCH_ANALYSIS_CLIENT_PLAN_TTL_SECONDS))
    )
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute(
                """
                SELECT status, media_id, timeline_epoch, client_lease_expires_at
                  FROM watch_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if current is None or str(current["status"] or "") == "ended":
                raise ValueError("观看会话已经结束")
            if (
                not str(current["client_lease_expires_at"] or "")
                or str(current["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能签发取材计划")
            if (
                str(current["media_id"] or "") != media_id
                or int(current["timeline_epoch"] or 0) != timeline_epoch
            ):
                raise ValueError("播放时间轴已经变化，请重新获取取材计划")
            conn.execute(
                """
                UPDATE watch_client_sample_plans
                   SET status = 'expired', cancelled_at = ?
                 WHERE status = 'open' AND expires_at <= ?
                """,
                (now_iso, now_iso),
            )
            existing = conn.execute(
                """
                SELECT * FROM watch_client_sample_plans
                 WHERE session_id = ? AND timeline_epoch = ? AND plan_digest = ?
                   AND status = 'open' AND expires_at > ?
                 ORDER BY created_at DESC LIMIT 1
                """,
                (session_id, timeline_epoch, plan_digest, now_iso),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    UPDATE watch_client_sample_plans
                       SET status = 'cancelled', cancelled_at = ?
                     WHERE session_id = ? AND status = 'open'
                    """,
                    (now_iso, session_id),
                )
                plan_id = f"watch_plan_{uuid4().hex}"
                conn.execute(
                    """
                    INSERT INTO watch_client_sample_plans (
                        id, session_id, media_id, media_revision, timeline_epoch,
                        purpose, plan_digest, target_timestamps_json,
                        allowed_start_ms, allowed_end_ms, status,
                        created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                    """,
                    (
                        plan_id,
                        session_id,
                        media_id,
                        media_revision,
                        timeline_epoch,
                        purpose,
                        plan_digest,
                        runtime_sqlite.json_dumps(targets),
                        allowed_start_ms,
                        allowed_end_ms,
                        now_iso,
                        expires_at,
                    ),
                )
                existing = conn.execute(
                    "SELECT * FROM watch_client_sample_plans WHERE id = ?",
                    (plan_id,),
                ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_client_plan(existing)


def validate_client_sample_plan(
    session: dict,
    *,
    plan_id: str,
    purpose: str,
    media_revision: str,
    actual_range_start_ms: int,
    actual_range_end_ms: int,
    sample_timestamps_ms: list[int],
) -> dict:
    session_id = str(session.get("session_id") or "")
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    playback = session.get("playback") if isinstance(session.get("playback"), dict) else {}
    local_media = _local_media_state(session)
    if str(media.get("source") or "") != "local_file":
        raise ValueError("客户端取材计划只适用于本地视频")
    expected_revision = str(local_media.get("media_revision") or "")
    if not media_revision or media_revision != expected_revision:
        raise ValueError("本地文件版本已经变化，请重新选择文件并创建会话")
    range_start_ms = _int(actual_range_start_ms, 0)
    range_end_ms = _int(actual_range_end_ms, 0)
    if range_end_ms < range_start_ms:
        raise ValueError("actual_range_end_ms 必须不早于 actual_range_start_ms")
    if range_end_ms - range_start_ms > int(WATCH_ANALYSIS_MAX_AUDIO_DURATION_MS):
        raise ValueError("本地取材实际区间超过单批分析时长")
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                UPDATE watch_client_sample_plans
                   SET status = 'expired', cancelled_at = ?
                 WHERE status = 'open' AND expires_at <= ?
                """,
                (now_iso, now_iso),
            )
            row = conn.execute(
                "SELECT * FROM watch_client_sample_plans WHERE id = ?",
                (_text(plan_id, 160),),
            ).fetchone()
            if row is None:
                raise ValueError("本地取材计划不存在或已经过期")
            if str(row["status"] or "") != "open":
                raise ValueError("本地取材计划已经失效或被使用")
            if (
                str(row["session_id"] or "") != session_id
                or str(row["media_id"] or "") != str(media.get("id") or "")
                or str(row["media_revision"] or "") != expected_revision
                or int(row["timeline_epoch"] or 0)
                != int(playback.get("timeline_epoch") or 0)
                or str(row["purpose"] or "") != str(purpose or "")
            ):
                raise ValueError("本地取材计划与当前媒体时间轴不一致")
            allowed_start_ms = int(row["allowed_start_ms"] or 0)
            allowed_end_ms = int(row["allowed_end_ms"] or 0)
            if range_start_ms < allowed_start_ms or range_end_ms > allowed_end_ms:
                raise ValueError("本地取材实际区间超出计划允许范围")
            for timestamp_ms in sample_timestamps_ms:
                normalized = _int(timestamp_ms, 0)
                if normalized < allowed_start_ms or normalized > allowed_end_ms:
                    raise ValueError("本地样本时间戳超出计划允许范围")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _row_to_client_plan(row)


def cancel_client_sample_plans(
    session_id: str,
    *,
    current_epoch: int | None,
) -> int:
    clauses = ["session_id = ?", "status = 'open'"]
    params: list[Any] = [_text(session_id, 160)]
    if current_epoch is not None:
        clauses.append("timeline_epoch != ?")
        params.append(_int(current_epoch, 0))
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        result = conn.execute(
            f"UPDATE watch_client_sample_plans SET status = 'cancelled', cancelled_at = ? WHERE {' AND '.join(clauses)}",
            (now_iso, *params),
        )
    return int(result.rowcount or 0)


def _client_plan(session: dict, plan: dict) -> dict:
    local_media = _local_media_state(session)
    sampling = local_media.get("sampling") if isinstance(local_media.get("sampling"), dict) else {}
    base = {
        "managed_by": "client",
        "input_origin": "local_device_window",
        "client_upload_required": False,
        "audio_required": False,
        "local_sampling": sampling,
        **plan,
    }
    if str(plan.get("purpose") or "") == "idle":
        return base
    if not bool(sampling.get("analysis_available")):
        return {
            **base,
            "purpose": "idle",
            "reason": "local_sampling_unavailable",
            "target_timestamps_ms": [],
        }
    issued = _issue_client_plan(session, plan)
    selected_audio = local_media.get("selected_audio") if isinstance(local_media.get("selected_audio"), dict) else {}
    selected_subtitle = local_media.get("selected_subtitle") if isinstance(local_media.get("selected_subtitle"), dict) else {}
    audio_required = bool(plan.get("audio_required") and sampling.get("audio_available"))
    return {
        **base,
        **issued,
        "client_upload_required": True,
        "audio_required": audio_required,
        "audio_degraded_reason": "" if audio_required else str(sampling.get("audio_degraded_reason") or ""),
        "selected_audio_track_id": str(selected_audio.get("track_id") or ""),
        "selected_subtitle_kind": str(selected_subtitle.get("kind") or "none"),
        "accepted_image_mime_types": ["image/jpeg", "image/png", "image/webp"],
        "accepted_audio_mime_types": ["audio/mpeg", "audio/aac", "audio/mp4"],
        "max_audio_duration_ms": int(WATCH_ANALYSIS_MAX_AUDIO_DURATION_MS),
    }


def _delivery_plan(session: dict, plan: dict) -> dict:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    if str(media.get("source") or "") == "local_file":
        return _client_plan(session, plan)
    return _gateway_plan(plan)


def _in_flight_delivery_plan(session: dict, job: dict) -> dict:
    return _delivery_plan(
        session,
        {
            "purpose": "idle",
            "reason": "analysis_in_flight",
            "target_timestamps_ms": [],
            "active_job": job,
        },
    )


def _rolling_targets(start_ms: int, end_ms: int, *, interval_ms: int, max_frames: int) -> list[int]:
    start = max(0, int(start_ms))
    end = max(start, int(end_ms))
    limit = max(1, int(max_frames))
    interval = max(1000, int(interval_ms))
    if end <= start or limit == 1:
        return [start]
    targets = list(range(start, end + 1, interval))[:limit]
    if targets[-1] != end and len(targets) < limit:
        targets.append(end)
    return targets


def _last_frame_timestamp_ms(duration_ms: int) -> int:
    # Bilibili reports rounded durations; seeking at the exact EOF can return no frame.
    return max(0, int(duration_ms) - 1000)


def _source_plan_timestamps(
    timestamps_ms: list[int],
    *,
    duration_ms: int,
    purpose: str,
) -> list[int]:
    max_timestamp = int(duration_ms)
    if duration_ms > 0 and purpose in {"identify", "timeline_prepass"}:
        max_timestamp = _last_frame_timestamp_ms(duration_ms)
    return sorted(
        {
            min(max_timestamp, _int(value, 0)) if duration_ms > 0 else _int(value, 0)
            for value in timestamps_ms
        }
    )[: int(WATCH_ANALYSIS_MAX_FRAMES_PER_JOB)]


def build_sample_plan(session: dict) -> dict:
    session_id = str(session.get("session_id") or "")
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    playback = session.get("playback") if isinstance(session.get("playback"), dict) else {}
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    duration_ms = int(media.get("duration_ms") or 0)
    content_start_ms = (
        int(media["content_start_ms"])
        if media.get("content_start_ms") is not None
        else None
    )
    content_end_ms = (
        int(media["content_end_ms"])
        if media.get("content_end_ms") is not None
        else None
    )
    playhead_ms = int(playback.get("playhead_ms") or 0)
    timeline_epoch = int(playback.get("timeline_epoch") or 0)
    familiarity = str(analysis.get("familiarity") or "pending")
    max_frames = int(WATCH_ANALYSIS_MAX_FRAMES_PER_JOB)
    if session.get("ended_at"):
        return _delivery_plan(session,
            {"purpose": "idle", "reason": "session_ended", "target_timestamps_ms": []}
        )
    if familiarity == "pending":
        active = _active_job(session_id, "identify", timeline_epoch)
        if active:
            return _in_flight_delivery_plan(session, active)
        identify_anchor = playhead_ms
        if content_start_ms is not None and playhead_ms < content_start_ms:
            identify_anchor = content_start_ms
        targets = sorted(
            {
                max(0, identify_anchor - 2000),
                identify_anchor,
                min(duration_ms, identify_anchor + 2000)
                if duration_ms
                else identify_anchor + 2000,
            }
        )
        return _delivery_plan(session, {
            "purpose": "identify",
            "reason": "identify_media",
            "target_timestamps_ms": targets[:max_frames],
            "max_frames": max_frames,
        })
    needs_timeline_prepass = content_start_ms is None or content_end_ms is None
    if (
        needs_timeline_prepass
        and not _has_completed_job(session_id, "timeline_prepass", timeline_epoch)
        and duration_ms > 0
    ):
        active = _active_job(session_id, "timeline_prepass", timeline_epoch)
        if active:
            return _in_flight_delivery_plan(session, active)
        edge = min(duration_ms // 2, int(WATCH_ANALYSIS_PREPASS_EDGE_MS))
        front_count = max_frames if content_end_ms is not None else max(1, max_frames // 2)
        back_count = max_frames if content_start_ms is not None else max(1, max_frames - front_count)
        front: list[int] = []
        if content_start_ms is None:
            front_end = min(edge, content_end_ms if content_end_ms is not None else duration_ms)
            front = [
                int(front_end * idx / max(1, front_count - 1))
                for idx in range(front_count)
            ]
        back: list[int] = []
        if content_end_ms is None:
            known_start = max(0, content_start_ms or 0)
            back_start = known_start + max(0, duration_ms - known_start) // 2
            back = [
                int(back_start + (duration_ms - back_start) * idx / max(1, back_count - 1))
                for idx in range(back_count)
            ]
        return _delivery_plan(session, {
            "purpose": "timeline_prepass",
            "reason": "detect_missing_content_bounds",
            "target_timestamps_ms": sorted(set(front + back))[:max_frames],
            "max_frames": max_frames,
            "manual_content_start_ms": content_start_ms,
            "manual_content_end_ms": content_end_ms,
        })
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    knowledge_status = str(preparation.get("knowledge_card_status") or "pending")
    if familiarity in {"partial", "unknown"} and knowledge_status in {
        "pending",
        "queued",
        "collecting",
        "building",
    }:
        return _delivery_plan(session, {
            "purpose": "idle",
            "reason": "knowledge_card_pending",
            "target_timestamps_ms": [],
        })
    if not str(preparation.get("started_at") or "").strip():
        return _delivery_plan(session, {
            "purpose": "idle",
            "reason": "waiting_for_start_confirmation",
            "target_timestamps_ms": [],
        })
    covered_until = int(analysis.get("covered_until_ms") or 0)
    target_until = min(duration_ms, playhead_ms + int(WATCH_ANALYSIS_FORWARD_WINDOW_MS)) if duration_ms else playhead_ms + int(WATCH_ANALYSIS_FORWARD_WINDOW_MS)
    if content_end_ms is not None:
        target_until = min(target_until, content_end_ms)
    if covered_until >= target_until:
        return _delivery_plan(session, {
            "purpose": "idle",
            "reason": "coverage_ready",
            "target_timestamps_ms": [],
            "covered_until_ms": covered_until,
            "target_until_ms": target_until,
        })
    active = _active_job(session_id, "rolling", timeline_epoch)
    if active:
        return _in_flight_delivery_plan(session, active)
    interval = (
        int(WATCH_ANALYSIS_RECOGNIZED_INTERVAL_MS)
        if familiarity == "recognized"
        else int(WATCH_ANALYSIS_UNKNOWN_INTERVAL_MS)
    )
    knowledge_mode = str((session.get("mode") or {}).get("knowledge_mode") or "known")
    start = covered_until if knowledge_mode == "needs_summary" else max(playhead_ms, covered_until)
    if content_start_ms is not None:
        start = max(start, content_start_ms)
    with runtime_sqlite.connect() as conn:
        timeline_sections = [
            dict(row)
            for row in conn.execute(
                "SELECT kind, start_ms, end_ms FROM watch_timeline_sections WHERE session_id = ? AND timeline_epoch = ? ORDER BY start_ms, end_ms",
                (_text(session_id, 160), _int(timeline_epoch, 0)),
            ).fetchall()
        ]
    start = _advance_past_skipped(start, timeline_sections)
    if duration_ms > 0:
        start = min(start, duration_ms)
    if start >= target_until:
        return _delivery_plan(session, {
            "purpose": "idle",
            "reason": "coverage_ready",
            "target_timestamps_ms": [],
            "covered_until_ms": covered_until,
            "effective_covered_until_ms": start,
            "target_until_ms": target_until,
        })
    batch_span = min(
        max(0, interval * max(0, max_frames - 1)),
        int(WATCH_ANALYSIS_MAX_AUDIO_DURATION_MS),
    )
    batch_end = min(target_until, start + batch_span)
    next_skipped_start = _next_skipped_start(start, timeline_sections)
    if next_skipped_start is not None and next_skipped_start <= batch_end:
        batch_end = max(start, next_skipped_start - 1)
    targets = _rolling_targets(
        start,
        batch_end,
        interval_ms=interval,
        max_frames=max_frames,
    )
    return _delivery_plan(session, {
        "purpose": "rolling",
        "reason": "extend_future_coverage",
        "target_timestamps_ms": targets,
        "max_frames": max_frames,
        "audio_required": len(targets) >= 2,
        "audio_range_start_ms": targets[0] if targets else start,
        "audio_range_end_ms": targets[-1] if targets else start,
        "covered_until_ms": covered_until,
        "effective_start_ms": start,
        "target_until_ms": target_until,
        "suggested_interval_ms": interval,
    })


def purge_job_samples(job: dict) -> int:
    samples = load_job_samples(job)
    purged = 0
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        for sample in samples:
            file_path = str(sample.get("file_path") or "")
            if file_path:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except Exception:
                    pass
            conn.execute(
                "UPDATE watch_analysis_samples SET file_path = '', purged_at = ? WHERE id = ?",
                (now_iso, sample["id"]),
            )
            purged += 1
    return purged


def cleanup_expired_samples() -> dict:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT * FROM watch_analysis_samples
             WHERE expires_at <= ?
                OR NOT EXISTS (
                    SELECT 1 FROM watch_sessions WHERE watch_sessions.id = watch_analysis_samples.session_id
                )
            """,
            (now_iso,),
        ).fetchall()
        for row in rows:
            path = str(row["file_path"] or "")
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
        sample_ids = [str(row["id"]) for row in rows]
        if sample_ids:
            placeholders = ",".join("?" for _ in sample_ids)
            conn.execute(
                f"DELETE FROM watch_analysis_samples WHERE id IN ({placeholders})",
                sample_ids,
            )
        jobs_deleted = conn.execute(
            """
            DELETE FROM watch_analysis_jobs
             WHERE NOT EXISTS (
                SELECT 1 FROM watch_sessions WHERE watch_sessions.id = watch_analysis_jobs.session_id
             )
            """
        ).rowcount
        checkpoints_deleted = conn.execute(
            """
            DELETE FROM watch_story_checkpoints
             WHERE NOT EXISTS (
                SELECT 1 FROM watch_sessions WHERE watch_sessions.id = watch_story_checkpoints.session_id
             )
            """
        ).rowcount
        plans_deleted = conn.execute(
            """
            DELETE FROM watch_client_sample_plans
             WHERE expires_at <= ?
                OR NOT EXISTS (
                    SELECT 1 FROM watch_sessions WHERE watch_sessions.id = watch_client_sample_plans.session_id
                )
            """,
            (now_iso,),
        ).rowcount
        conn.execute("COMMIT")
    return {
        "samples_deleted": len(rows),
        "orphan_jobs_deleted": int(jobs_deleted or 0),
        "orphan_checkpoints_deleted": int(checkpoints_deleted or 0),
        "client_plans_deleted": int(plans_deleted or 0),
    }


def queue_stats() -> dict:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM watch_analysis_jobs GROUP BY status"
        ).fetchall()
        oldest_queued = conn.execute(
            "SELECT MIN(created_at) AS value FROM watch_analysis_jobs WHERE status = 'queued'"
        ).fetchone()
        stale_running = conn.execute(
            """
            SELECT COUNT(*) AS n FROM watch_analysis_jobs
             WHERE status = 'running' AND leased_until != '' AND leased_until <= ?
            """,
            (_iso(_now()),),
        ).fetchone()
        sample_totals = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(byte_size), 0) AS bytes
              FROM watch_analysis_samples WHERE purged_at = ''
            """
        ).fetchone()
    return {
        "counts": {str(row["status"]): int(row["n"] or 0) for row in rows},
        "oldest_queued_at": str(oldest_queued["value"] or ""),
        "stale_running": int(stale_running["n"] or 0),
        "sample_count": int(sample_totals["n"] or 0),
        "sample_bytes": int(sample_totals["bytes"] or 0),
        "daily_cost_usd": daily_cost_usd(),
        "daily_cost_limit_usd": float(WATCH_ANALYSIS_DAILY_MAX_COST_USD or 0),
    }
