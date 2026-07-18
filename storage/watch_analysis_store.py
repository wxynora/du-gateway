from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import (
    WATCH_ANALYSIS_DAILY_MAX_COST_USD,
    WATCH_ANALYSIS_FEAR_READY_BUFFER_MS,
    WATCH_ANALYSIS_FORWARD_WINDOW_MS,
    WATCH_ANALYSIS_JOB_MAX_ATTEMPTS,
    WATCH_ANALYSIS_MAX_FRAMES_PER_JOB,
    WATCH_ANALYSIS_MAX_JOBS_PER_SESSION,
    WATCH_ANALYSIS_PREPASS_EDGE_MS,
    WATCH_ANALYSIS_PROMPT_VERSION,
    WATCH_ANALYSIS_RECOGNIZED_INTERVAL_MS,
    WATCH_ANALYSIS_SAMPLE_TTL_SECONDS,
    WATCH_ANALYSIS_UNKNOWN_INTERVAL_MS,
)
from storage import runtime_sqlite


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
    range_start = min(int(item.get("at_ms") or 0) for item in samples)
    range_end = max(int(item.get("at_ms") or 0) for item in samples)
    input_bytes = sum(int(item.get("byte_size") or 0) for item in samples)
    job_id = f"watch_analysis_{uuid4().hex}"
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute(
                "SELECT media_id, timeline_epoch, status FROM watch_sessions WHERE id = ? AND expires_at > ?",
                (session_id, now_iso),
            ).fetchone()
            if current is None or str(current["status"] or "") == "ended":
                raise ValueError("观看会话不可分析")
            if str(current["media_id"] or "") != media_id or int(current["timeline_epoch"] or 0) != timeline_epoch:
                raise ValueError("播放时间轴已经变化，请重新采样")
            count = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()["n"]
                or 0
            )
            if count >= int(WATCH_ANALYSIS_MAX_JOBS_PER_SESSION):
                raise ValueError("本次观看的分析任务已达到上限")
            duplicate = conn.execute(
                "SELECT * FROM watch_analysis_jobs WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if duplicate is not None:
                conn.execute("COMMIT")
                return _row_to_job(duplicate, public=True), False
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
    timestamps_ms = sorted(
        {
            min(duration_ms, _int(value, 0)) if duration_ms > 0 else _int(value, 0)
            for value in (plan.get("target_timestamps_ms") or [])
        }
    )[: int(WATCH_ANALYSIS_MAX_FRAMES_PER_JOB)]
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
                "SELECT media_id, timeline_epoch, status FROM watch_sessions WHERE id = ? AND expires_at > ?",
                (session_id, now_iso),
            ).fetchone()
            if current is None or str(current["status"] or "") == "ended":
                raise ValueError("观看会话不可分析")
            if (
                str(current["media_id"] or "") != media_id
                or int(current["timeline_epoch"] or 0) != timeline_epoch
            ):
                raise ValueError("播放时间轴已经变化，请重新生成分析计划")
            count = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()["n"]
                or 0
            )
            if count >= int(WATCH_ANALYSIS_MAX_JOBS_PER_SESSION):
                raise ValueError("本次观看的分析任务已达到上限")
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
                "SELECT media_id, timeline_epoch, status FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            stale = (
                job_row is None
                or session_row is None
                or str(session_row["status"] or "") == "ended"
                or str(session_row["media_id"] or "") != media_id
                or int(session_row["timeline_epoch"] or 0) != timeline_epoch
            )
            if stale:
                if job_row is not None:
                    conn.execute(
                        """
                        UPDATE watch_analysis_jobs
                           SET status = 'cancelled', error = 'stale_timeline',
                               finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                         WHERE id = ? AND status = 'running' AND lease_token = ?
                        """,
                        (now_iso, now_iso, job_id, lease_token),
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
                SELECT * FROM watch_analysis_jobs
                 WHERE attempts < max_attempts
                   AND (
                        (status = 'queued' AND available_at <= ?)
                        OR (status = 'running' AND leased_until != '' AND leased_until <= ?)
                   )
                 ORDER BY priority DESC, created_at, id
                 LIMIT 1
                """,
                (now_iso, now_iso),
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
                 WHERE id = ?
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
            """,
            (_iso(now + timedelta(seconds=max(30, lease_seconds))), _iso(now), job_id, lease_token),
        )
    return bool(result.rowcount)


def mark_job_cancelled(job_id: str, *, reason: str = "") -> bool:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        result = conn.execute(
            """
            UPDATE watch_analysis_jobs
               SET status = 'cancelled', error = ?, finished_at = ?, updated_at = ?,
                   leased_until = '', lease_token = ''
             WHERE id = ? AND status IN ('queued', 'running')
            """,
            (_text(reason, 1000), now_iso, now_iso, job_id),
        )
    return bool(result.rowcount)


def cancel_stale_jobs(session_id: str, *, current_epoch: int | None = None, reason: str) -> int:
    clauses = ["session_id = ?", "status IN ('queued', 'running')"]
    where_params: list[Any] = [_text(session_id, 160)]
    if current_epoch is not None:
        clauses.append("timeline_epoch != ?")
        where_params.append(_int(current_epoch, 0))
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
               SET status = 'cancelled', error = ?, finished_at = ?, updated_at = ?,
                   leased_until = '', lease_token = ''
             WHERE {' AND '.join(clauses)}
            """,
            (_text(reason, 1000), now_iso, now_iso, *where_params),
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
    return int(result.rowcount or 0)


def fail_job(job: dict, error: str, *, retryable: bool) -> str:
    job_id = str(job.get("job_id") or "")
    lease_token = str(job.get("lease_token") or "")
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or WATCH_ANALYSIS_JOB_MAX_ATTEMPTS)
    terminal = not retryable or attempts >= max_attempts
    now = _now()
    status = "failed" if terminal else "queued"
    available_at = _iso(now + timedelta(seconds=min(120, 2 ** max(1, attempts))))
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current_job = conn.execute(
                "SELECT status, lease_token FROM watch_analysis_jobs WHERE id = ?",
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
                SELECT media_id, timeline_epoch, status, analysis_covered_until_ms
                  FROM watch_sessions WHERE id = ?
                """,
                (job.get("session_id"),),
            ).fetchone()
            stale = (
                session is None
                or str(session["status"] or "") == "ended"
                or str(session["media_id"] or "") != str(job.get("media_id") or "")
                or int(session["timeline_epoch"] or 0) != int(job.get("timeline_epoch") or 0)
            )
            if stale:
                conn.execute(
                    """
                    UPDATE watch_analysis_jobs
                       SET status = 'cancelled', error = 'stale_timeline',
                           finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                     WHERE id = ? AND status = 'running' AND lease_token = ?
                    """,
                    (_iso(now), _iso(now), job_id, lease_token),
                )
                conn.execute("COMMIT")
                return "cancelled"
            result = conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = ?, available_at = ?, leased_until = '', lease_token = '',
                       error = ?, finished_at = ?, updated_at = ?
                 WHERE id = ? AND status = 'running' AND lease_token = ?
                """,
                (
                    status,
                    available_at,
                    _text(error, 2000),
                    _iso(now) if terminal else "",
                    _iso(now),
                    job_id,
                    lease_token,
                ),
            )
            if terminal and result.rowcount:
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
            """,
            (_iso(available_at), _text(reason, 1000), now_iso, job_id, lease_token),
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
    return f"{source}:{title}" if title else ""


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


def _overlaps_skipped(start_ms: int, end_ms: int, sections: list[dict]) -> bool:
    skipped = {"intro", "outro", "preview", "non_story"}
    return any(
        str(section.get("kind") or "") in skipped
        and start_ms < int(section.get("end_ms") or 0)
        and end_ms > int(section.get("start_ms") or 0)
        for section in sections
    )


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
            stale = (
                session_row is None
                or str(session_row["status"] or "") == "ended"
                or str(session_row["media_id"] or "") != media_id
                or int(session_row["timeline_epoch"] or 0) != timeline_epoch
            )
            if stale:
                conn.execute(
                    """
                    UPDATE watch_analysis_jobs
                       SET status = 'cancelled', error = 'stale_timeline', finished_at = ?, updated_at = ?,
                           leased_until = '', lease_token = ''
                     WHERE id = ?
                    """,
                    (now_iso, now_iso, job_id),
                )
                conn.execute("COMMIT")
                return {"applied": False, "reason": "stale_timeline"}

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

            story_so_far = result.get("story_so_far") if isinstance(result.get("story_so_far"), dict) else {}
            story_state = result.get("story_state") if isinstance(result.get("story_state"), dict) else {}
            if purpose == "rolling" and story_so_far and _text(story_so_far.get("summary"), 8000):
                through_ms = int(story_so_far.get("through_ms") or result.get("covered_until_ms") or 0)
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
                        through_ms, runtime_sqlite.json_dumps(story_so_far),
                        runtime_sqlite.json_dumps(story_state), analysis_version, now_iso,
                    ),
                )

            if purpose == "timeline_prepass" and incoming_sections:
                series_key = _series_key({
                    "media": {
                        "source": session_row["source"],
                        "title": session_row["title"],
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
            if purpose == "identify":
                familiarity = _text(result.get("familiarity"), 80) or "unknown"
                identity = _text(result.get("identity"), 500)
                if bool(session_row["force_unknown_analysis"]):
                    familiarity = "unknown"
            covered_from = int(session_row["analysis_covered_from_ms"] or 0)
            covered_until = int(session_row["analysis_covered_until_ms"] or 0)
            if purpose == "rolling":
                incoming_from = int(result.get("covered_from_ms") or 0)
                incoming_until = int(result.get("covered_until_ms") or 0)
                covered_from = incoming_from if covered_until <= 0 else min(covered_from, incoming_from)
                covered_until = max(covered_until, incoming_until)
            playhead_ms = int(session_row["playhead_ms"] or 0)
            duration_ms = int(session_row["duration_ms"] or 0)
            required_buffer = int(WATCH_ANALYSIS_FEAR_READY_BUFFER_MS) if bool(session_row["fear_mode"]) else 0
            ready_until = playhead_ms + required_buffer
            if duration_ms > 0:
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
            ready = completed_rolling and covered_until >= ready_until
            analysis_status = "ready" if ready else "analyzing"
            persisted_story_so_far = runtime_sqlite.json_loads(
                session_row["story_so_far_json"], {}
            )
            persisted_story_state = runtime_sqlite.json_loads(
                session_row["analysis_story_state_json"], {}
            )
            if purpose == "rolling" and _text(story_so_far.get("summary"), 8000):
                persisted_story_so_far = story_so_far
                persisted_story_state = story_state
            conn.execute(
                """
                UPDATE watch_sessions
                   SET analysis_familiarity = ?, analysis_identity = ?, analysis_status = ?,
                       analysis_covered_from_ms = ?, analysis_covered_until_ms = ?,
                       analysis_error = '', story_so_far_json = ?, analysis_story_state_json = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    familiarity, identity, analysis_status, covered_from, covered_until,
                    runtime_sqlite.json_dumps(persisted_story_so_far),
                    runtime_sqlite.json_dumps(persisted_story_state),
                    now_iso, session_id,
                ),
            )
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            cost_usd = max(0.0, float(usage.get("cost_usd") or 0))
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'done', leased_until = '', lease_token = '', finished_at = ?,
                       updated_at = ?, error = '', result_json = ?, usage_json = ?,
                       input_tokens = ?, output_tokens = ?, cost_usd = ?
                 WHERE id = ?
                """,
                (
                    now_iso, now_iso, runtime_sqlite.json_dumps(result), runtime_sqlite.json_dumps(usage),
                    input_tokens, output_tokens, cost_usd, job_id,
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


def _in_flight_plan(job: dict) -> dict:
    return _gateway_plan({
        "purpose": "idle",
        "reason": "analysis_in_flight",
        "target_timestamps_ms": [],
        "active_job": job,
    })


def _gateway_plan(plan: dict) -> dict:
    return {
        "managed_by": "gateway",
        "input_origin": "backend_source",
        "client_upload_required": False,
        **plan,
    }


def build_sample_plan(session: dict) -> dict:
    session_id = str(session.get("session_id") or "")
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    playback = session.get("playback") if isinstance(session.get("playback"), dict) else {}
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    duration_ms = int(media.get("duration_ms") or 0)
    playhead_ms = int(playback.get("playhead_ms") or 0)
    timeline_epoch = int(playback.get("timeline_epoch") or 0)
    familiarity = str(analysis.get("familiarity") or "pending")
    max_frames = int(WATCH_ANALYSIS_MAX_FRAMES_PER_JOB)
    if session.get("ended_at"):
        return _gateway_plan(
            {"purpose": "idle", "reason": "session_ended", "target_timestamps_ms": []}
        )
    if familiarity == "pending":
        active = _active_job(session_id, "identify", timeline_epoch)
        if active:
            return _in_flight_plan(active)
        targets = sorted(
            {
                max(0, playhead_ms - 2000),
                playhead_ms,
                min(duration_ms, playhead_ms + 2000) if duration_ms else playhead_ms + 2000,
            }
        )
        return _gateway_plan({
            "purpose": "identify",
            "reason": "identify_media",
            "target_timestamps_ms": targets[:max_frames],
            "max_frames": max_frames,
        })
    if not _has_completed_job(session_id, "timeline_prepass", timeline_epoch) and duration_ms > 0:
        active = _active_job(session_id, "timeline_prepass", timeline_epoch)
        if active:
            return _in_flight_plan(active)
        edge = min(duration_ms // 2, int(WATCH_ANALYSIS_PREPASS_EDGE_MS))
        front = [int(edge * idx / 3) for idx in range(4)]
        back_start = max(edge, duration_ms - edge)
        back = [int(back_start + (duration_ms - back_start) * idx / 3) for idx in range(4)]
        return _gateway_plan({
            "purpose": "timeline_prepass",
            "reason": "detect_intro_outro",
            "target_timestamps_ms": sorted(set(front + back))[:max_frames],
            "max_frames": max_frames,
        })
    covered_until = int(analysis.get("covered_until_ms") or 0)
    target_until = min(duration_ms, playhead_ms + int(WATCH_ANALYSIS_FORWARD_WINDOW_MS)) if duration_ms else playhead_ms + int(WATCH_ANALYSIS_FORWARD_WINDOW_MS)
    if covered_until >= target_until:
        return _gateway_plan({
            "purpose": "idle",
            "reason": "coverage_ready",
            "target_timestamps_ms": [],
            "covered_until_ms": covered_until,
            "target_until_ms": target_until,
        })
    active = _active_job(session_id, "rolling", timeline_epoch)
    if active:
        return _in_flight_plan(active)
    interval = (
        int(WATCH_ANALYSIS_RECOGNIZED_INTERVAL_MS)
        if familiarity == "recognized"
        else int(WATCH_ANALYSIS_UNKNOWN_INTERVAL_MS)
    )
    knowledge_mode = str((session.get("mode") or {}).get("knowledge_mode") or "known")
    start = covered_until if knowledge_mode == "needs_summary" else max(playhead_ms, covered_until)
    targets = list(range(start, target_until + 1, max(1000, interval)))[:max_frames]
    return _gateway_plan({
        "purpose": "rolling",
        "reason": "extend_future_coverage",
        "target_timestamps_ms": targets,
        "max_frames": max_frames,
        "covered_until_ms": covered_until,
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
        conn.execute("COMMIT")
    return {
        "samples_deleted": len(rows),
        "orphan_jobs_deleted": int(jobs_deleted or 0),
        "orphan_checkpoints_deleted": int(checkpoints_deleted or 0),
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
