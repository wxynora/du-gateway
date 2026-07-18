"""Together-watch visual analysis queue worker.

Run from the repository root:
    python scripts/run_watch_analysis_worker.py
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)

from config import (  # noqa: E402
    DATA_DIR,
    WATCH_ANALYSIS_ENABLED,
    WATCH_ANALYSIS_JOB_STALE_SECONDS,
    WATCH_ANALYSIS_SOURCE_ENABLED,
    WATCH_ANALYSIS_WORKER_IDLE_SECONDS,
)
from services.watch_analysis import (  # noqa: E402
    WatchAnalysisProviderError,
    analyze_watch_samples,
)
from services.watch_analysis_samples import (  # noqa: E402
    prepare_samples,
    purge_prepared_samples,
)
from services.watch_analysis_source import (  # noqa: E402
    WatchAnalysisSourceError,
    get_watch_analysis_source,
    watch_analysis_source_health,
)
from storage import watch_analysis_store, watch_runtime_store  # noqa: E402
from utils.log import get_logger, setup_logging  # noqa: E402

setup_logging()
logger = get_logger("services.watch_analysis_worker")


def _next_budget_window() -> datetime:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).date()
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc) + timedelta(minutes=5)


def _job_matches_session(job: dict, session: dict | None) -> bool:
    if not session or session.get("ended_at"):
        return False
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    playback = session.get("playback") if isinstance(session.get("playback"), dict) else {}
    return (
        str(media.get("id") or "") == str(job.get("media_id") or "")
        and int(playback.get("timeline_epoch") or 0) == int(job.get("timeline_epoch") or 0)
    )


def _fingerprint_reuse_result(session: dict, sections: list[dict]) -> dict:
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    return {
        "familiarity": str(analysis.get("familiarity") or "pending"),
        "identity": str(analysis.get("identity") or ""),
        "familiarity_confidence": 0.0,
        "timeline_sections": sections,
        "plot_chunks": [],
        "story_so_far": {},
        "story_state": {},
        "risk_events": [],
        "covered_from_ms": 0,
        "covered_until_ms": 0,
        "analysis_notes": "reused_timeline_fingerprints",
        "analysis_version": "fingerprint-reuse-v1",
    }


def schedule_source_jobs(*, limit: int = 4) -> dict:
    if not WATCH_ANALYSIS_SOURCE_ENABLED:
        return {"sessions_checked": 0, "jobs_created": 0, "disabled": True}
    checked = 0
    created = 0
    errors = 0
    for session in watch_runtime_store.list_sessions(limit=100):
        if created >= max(1, int(limit or 1)):
            break
        media = session.get("media") if isinstance(session.get("media"), dict) else {}
        if str(media.get("source") or "") != "bilibili_embed":
            continue
        checked += 1
        plan = watch_analysis_store.build_sample_plan(session)
        if str(plan.get("purpose") or "") == "idle":
            continue
        try:
            _job, was_created = watch_analysis_store.enqueue_source_plan(
                session=session,
                plan=plan,
                priority={"identify": 30, "timeline_prepass": 20, "rolling": 10}.get(
                    str(plan.get("purpose") or ""),
                    0,
                ),
            )
            if was_created:
                created += 1
        except ValueError as exc:
            errors += 1
            logger.warning(
                "一起看后端取材计划未入队 session_id=%s reason=%s",
                session.get("session_id"),
                exc,
            )
    return {"sessions_checked": checked, "jobs_created": created, "errors": errors}


def process_claimed_job(
    job: dict,
    *,
    post: Callable[..., Any] | None = None,
    source: Any | None = None,
) -> dict:
    job_id = str(job.get("job_id") or "")
    session_id = str(job.get("session_id") or "")
    session = watch_runtime_store.get_session(session_id)
    if not _job_matches_session(job, session):
        watch_analysis_store.mark_job_cancelled(job_id, reason="stale_timeline")
        watch_analysis_store.purge_job_samples(job)
        return {"status": "cancelled", "reason": "stale_timeline"}

    if not watch_analysis_store.cost_budget_available():
        deferred = watch_analysis_store.defer_job(
            job,
            available_at=_next_budget_window(),
            reason="daily_cost_budget_exhausted",
        )
        return {
            "status": "deferred" if deferred else "cancelled",
            "reason": "daily_cost_budget_exhausted" if deferred else "lease_lost",
        }

    prepared_from_source: list[dict] = []
    try:
        samples = watch_analysis_store.load_job_samples(job)
        if not samples and str(job.get("input_origin") or "") == "backend_source":
            source_client = source or get_watch_analysis_source()
            raw_samples = source_client.acquire(
                session,
                purpose=str(job.get("purpose") or "rolling"),
                timestamps_ms=[
                    int(value)
                    for value in (job.get("planned_timestamps_ms") or [])
                ],
            )
            prepared_from_source = prepare_samples(
                session_id=session_id,
                media_id=str((session.get("media") or {}).get("id") or ""),
                timeline_epoch=int((session.get("playback") or {}).get("timeline_epoch") or 0),
                duration_ms=int((session.get("media") or {}).get("duration_ms") or 0),
                purpose=str(job.get("purpose") or "rolling"),
                raw_samples=raw_samples,
            )
            refreshed, attached = watch_analysis_store.attach_source_samples(
                job,
                prepared_from_source,
            )
            if not attached:
                purge_prepared_samples(prepared_from_source)
                if refreshed is None:
                    return {"status": "cancelled", "reason": "stale_timeline"}
                job = refreshed
                samples = watch_analysis_store.load_job_samples(job)
            else:
                job = refreshed or job
                samples = watch_analysis_store.load_job_samples(job)
        if not samples:
            status = watch_analysis_store.fail_job(
                job,
                "分析样本不存在或已经过期",
                retryable=False,
            )
            watch_analysis_store.purge_job_samples(job)
            return {"status": status, "reason": "samples_missing"}

        result: dict
        usage: dict
        reusable_sections = []
        if str(job.get("purpose") or "") == "timeline_prepass":
            reusable_sections = watch_analysis_store.reusable_timeline_sections(session, samples)
        if reusable_sections:
            result = _fingerprint_reuse_result(session, reusable_sections)
            usage = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "elapsed_ms": 0,
                "model": "local-fingerprint-reuse",
            }
        elif post is None:
            result, usage = analyze_watch_samples(session, job, samples)
        else:
            result, usage = analyze_watch_samples(session, job, samples, post=post)

        committed = watch_analysis_store.commit_analysis_result(
            job,
            result=result,
            usage=usage,
            samples=samples,
        )
        if committed.get("applied") or committed.get("reason") in {
            "stale_timeline",
            "lease_lost",
        }:
            watch_analysis_store.purge_job_samples(job)
        return {
            "status": "done" if committed.get("applied") else "cancelled",
            **committed,
        }
    except WatchAnalysisSourceError as exc:
        purge_prepared_samples(prepared_from_source)
        status = watch_analysis_store.fail_job(job, str(exc), retryable=exc.retryable)
        if status in {"failed", "cancelled"}:
            watch_analysis_store.purge_job_samples(job)
        return {
            "status": status,
            "reason": "source_error",
            "retryable": exc.retryable,
        }
    except WatchAnalysisProviderError as exc:
        status = watch_analysis_store.fail_job(job, str(exc), retryable=exc.retryable)
        if status in {"failed", "cancelled"}:
            watch_analysis_store.purge_job_samples(job)
        return {
            "status": status,
            "reason": "provider_error",
            "retryable": exc.retryable,
        }
    except Exception as exc:
        if not (job.get("sample_ids") or []):
            purge_prepared_samples(prepared_from_source)
        status = watch_analysis_store.fail_job(job, str(exc), retryable=True)
        if status in {"failed", "cancelled"}:
            watch_analysis_store.purge_job_samples(job)
        logger.exception("一起看分析任务异常 job_id=%s: %s", job_id, exc)
        return {"status": status, "reason": "worker_error"}


def process_next_job(
    *,
    post: Callable[..., Any] | None = None,
    source: Any | None = None,
) -> dict | None:
    job = watch_analysis_store.claim_next_job(
        stale_after_seconds=int(WATCH_ANALYSIS_JOB_STALE_SECONDS),
    )
    if job is None:
        return None
    logger.info(
        "领取一起看分析任务 job_id=%s session_id=%s purpose=%s attempt=%s",
        job.get("job_id"),
        job.get("session_id"),
        job.get("purpose"),
        job.get("attempts"),
    )
    outcome = process_claimed_job(job, post=post, source=source)
    logger.info(
        "完成一起看分析任务 job_id=%s status=%s reason=%s",
        job.get("job_id"),
        outcome.get("status"),
        outcome.get("reason") or "",
    )
    return outcome


def run_worker_loop() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    idle = max(float(WATCH_ANALYSIS_WORKER_IDLE_SECONDS or 0.5), 0.1)
    if not WATCH_ANALYSIS_ENABLED:
        logger.error("一起看分析 worker 未启动：WATCH_ANALYSIS_ENABLED=0")
        return
    logger.info(
        "一起看分析 worker 已启动 idle=%.1f stale_after=%s source=%s stats=%s",
        idle,
        WATCH_ANALYSIS_JOB_STALE_SECONDS,
        watch_analysis_source_health(),
        watch_analysis_store.queue_stats(),
    )
    last_cleanup = 0.0
    while True:
        now = time.monotonic()
        if now - last_cleanup >= 60:
            cleanup = watch_analysis_store.cleanup_expired_samples()
            if cleanup.get("samples_deleted"):
                logger.info("清理一起看过期样本 stats=%s", cleanup)
            last_cleanup = now
        scheduled = schedule_source_jobs()
        if scheduled.get("jobs_created"):
            logger.info("一起看后端取材任务已入队 stats=%s", scheduled)
        outcome = process_next_job()
        if outcome is None:
            time.sleep(idle)


if __name__ == "__main__":
    run_worker_loop()
