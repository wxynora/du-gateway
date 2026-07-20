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
    WATCH_KNOWLEDGE_ENABLED,
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
from services.watch_subtitles import SubtitleLookupError  # noqa: E402
from services.watch_knowledge import (  # noqa: E402
    build_work_knowledge_card,
    source_digest,
)
from services.watch_visual_context import cache_analysis_frames  # noqa: E402
from storage import (  # noqa: E402
    watch_analysis_store,
    watch_knowledge_store,
    watch_runtime_store,
    watch_subtitle_store,
    watch_visual_store,
)
from utils.log import get_logger, setup_logging  # noqa: E402

setup_logging()
logger = get_logger("services.watch_analysis_worker")


class WatchJobCancelled(RuntimeError):
    def __init__(self, reason: str, stage: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


def _schedule_allowed(session: dict, *, scheduler: str) -> bool:
    allowed, reason = watch_runtime_store.schedule_eligibility(session)
    if not allowed:
        logger.info(
            "跳过一起看调度 scheduler=%s session_id=%s skip_reason=%s",
            scheduler,
            session.get("session_id"),
            reason,
        )
    return allowed


def _next_budget_window() -> datetime:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).date()
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc) + timedelta(minutes=5)


def cleanup_abandoned_sessions() -> dict:
    cleanup = watch_runtime_store.expire_abandoned_sessions()
    samples_purged = 0
    visual_rows_deleted = 0
    for session_id in cleanup.get("session_ids") or []:
        samples_purged += watch_analysis_store.purge_session_samples(str(session_id))
        visual_rows_deleted += int(
            watch_visual_store.delete_session_frames(str(session_id)).get("rows_deleted") or 0
        )
    cleanup["samples_purged"] = samples_purged
    cleanup["visual_rows_deleted"] = visual_rows_deleted
    return cleanup


def _require_job_live(job: dict, *, stage: str) -> dict:
    reason = watch_analysis_store.execution_skip_reason(job)
    if reason:
        cancelled = watch_analysis_store.cancel_claimed_job(job, reason=reason)
        if cancelled and reason != "lease_lost":
            watch_analysis_store.purge_job_samples(job)
        logger.info(
            "跳过一起看任务 job_id=%s session_id=%s stage=%s skip_reason=%s",
            job.get("job_id"),
            job.get("session_id"),
            stage,
            reason,
        )
        raise WatchJobCancelled(reason, stage)
    session = watch_runtime_store.get_session(str(job.get("session_id") or ""))
    if session is None:
        reason = "session_ended"
        watch_analysis_store.cancel_claimed_job(job, reason=reason)
        watch_analysis_store.purge_job_samples(job)
        logger.info(
            "跳过一起看任务 job_id=%s session_id=%s stage=%s skip_reason=%s",
            job.get("job_id"),
            job.get("session_id"),
            stage,
            reason,
        )
        raise WatchJobCancelled(reason, stage)
    return session


def _session_with_prepared_subtitles(session: dict) -> dict:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    lookup = preparation.get("subtitle_lookup") if isinstance(preparation.get("subtitle_lookup"), dict) else {}
    asset = watch_subtitle_store.get_asset_for_session(session)
    return {
        **session,
        "media": {
            **media,
            "prepared_subtitle_cues": asset.get("cues") if asset else [],
            "prepared_subtitle_provider": asset.get("provider") if asset else "",
            "subtitle_cache_key": asset.get("asset_id") or lookup.get("lookup_id") or "none",
        },
    }


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
        if not _schedule_allowed(session, scheduler="source"):
            continue
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


def schedule_knowledge_jobs(*, limit: int = 4) -> dict:
    checked = 0
    created = 0
    errors = 0
    for session in watch_runtime_store.list_sessions(limit=100):
        if created >= max(1, int(limit or 1)):
            break
        if not _schedule_allowed(session, scheduler="knowledge"):
            continue
        familiarity = str((session.get("analysis") or {}).get("familiarity") or "pending")
        if str((session.get("preparation") or {}).get("started_at") or "").strip():
            continue
        if familiarity == "pending":
            continue
        checked += 1
        try:
            if familiarity == "recognized" and not bool(
                (session.get("mode") or {}).get("force_unknown_analysis")
            ):
                watch_knowledge_store.ensure_knowledge_job(session)
                continue
            if not WATCH_KNOWLEDGE_ENABLED:
                watch_runtime_store.update_preparation_state(
                    str(session.get("session_id") or ""),
                    status="knowledge_failed",
                    knowledge_card_status="failed",
                    knowledge_card_error="作品知识卡功能未启用",
                )
                continue
            _job, was_created = watch_knowledge_store.ensure_knowledge_job(session)
            if was_created:
                created += 1
        except (KeyError, ValueError) as exc:
            errors += 1
            logger.warning(
                "一起看知识卡任务未入队 session_id=%s reason=%s",
                session.get("session_id"),
                exc,
            )
    return {"sessions_checked": checked, "jobs_created": created, "errors": errors}


def schedule_subtitle_jobs(*, limit: int = 4) -> dict:
    checked = 0
    created = 0
    errors = 0
    for session in watch_runtime_store.list_sessions(limit=100):
        if created >= max(1, int(limit or 1)):
            break
        if not _schedule_allowed(session, scheduler="subtitle"):
            continue
        preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
        if str(preparation.get("started_at") or "").strip():
            continue
        familiarity = str((session.get("analysis") or {}).get("familiarity") or "pending")
        if familiarity == "pending":
            continue
        card_status = str(preparation.get("knowledge_card_status") or "pending")
        if card_status not in {"ready", "not_required", "failed"}:
            continue
        checked += 1
        try:
            _job, was_created = watch_subtitle_store.ensure_lookup_job(session)
            if was_created:
                created += 1
        except (KeyError, ValueError) as exc:
            errors += 1
            logger.warning(
                "一起看字幕准备任务未入队 session_id=%s reason=%s",
                session.get("session_id"),
                exc,
            )
    return {"sessions_checked": checked, "jobs_created": created, "errors": errors}


def process_claimed_job(
    job: dict,
    *,
    post: Callable[..., Any] | None = None,
    source: Any | None = None,
    knowledge_search_post: Callable[..., Any] | None = None,
    knowledge_model_post: Callable[..., Any] | None = None,
) -> dict:
    job_id = str(job.get("job_id") or "")
    session_id = str(job.get("session_id") or "")
    try:
        session = _require_job_live(job, stage="claimed")
    except WatchJobCancelled as exc:
        return {"status": "cancelled", "reason": exc.reason, "stage": exc.stage}

    purpose = str(job.get("purpose") or "")
    if purpose == "subtitle_lookup":
        try:
            session = _require_job_live(job, stage="before_subtitle_provider")
            source_client = source or get_watch_analysis_source()
            original_title, year = watch_subtitle_store.identity_for_session(session)
            result = source_client.prepare_subtitles(
                session,
                original_title=original_title,
                year=year,
            )
            _require_job_live(job, stage="after_subtitle_provider")
            committed = watch_subtitle_store.commit_lookup_result(job, result)
            return {
                "status": "done" if committed.get("applied") else "cancelled",
                **committed,
            }
        except WatchJobCancelled as exc:
            return {"status": "cancelled", "reason": exc.reason, "stage": exc.stage}
        except SubtitleLookupError as exc:
            status = watch_subtitle_store.fail_lookup_job(job, str(exc), retryable=True)
            return {"status": status, "reason": "subtitle_provider_error", "retryable": True}
        except WatchAnalysisSourceError as exc:
            status = watch_subtitle_store.fail_lookup_job(job, str(exc), retryable=exc.retryable)
            return {"status": status, "reason": "subtitle_source_error", "retryable": exc.retryable}
        except Exception as exc:
            status = watch_subtitle_store.fail_lookup_job(job, str(exc), retryable=True)
            logger.exception("一起看字幕准备任务异常 job_id=%s: %s", job_id, exc)
            return {"status": status, "reason": "subtitle_worker_error"}

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
        if str(job.get("purpose") or "") == "knowledge_card":
            kwargs: dict[str, Any] = {
                "on_sources_ready": lambda: watch_knowledge_store.mark_building(session_id),
                "checkpoint": lambda stage: _require_job_live(job, stage=stage),
            }
            if knowledge_search_post is not None:
                kwargs["search_post"] = knowledge_search_post
            if knowledge_model_post is not None:
                kwargs["model_post"] = knowledge_model_post
            elif post is not None:
                kwargs["model_post"] = post
            card, sources, usage = build_work_knowledge_card(session, **kwargs)
            _require_job_live(job, stage="before_knowledge_commit")
            committed = watch_knowledge_store.commit_knowledge_result(
                job,
                card=card,
                sources=sources,
                usage=usage,
                source_digest=source_digest(sources),
            )
            return {
                "status": "done" if committed.get("applied") else "cancelled",
                **committed,
            }
        samples = watch_analysis_store.load_job_samples(job)
        if not samples and str(job.get("input_origin") or "") == "backend_source":
            session = _require_job_live(job, stage="before_source_acquire")
            source_client = source or get_watch_analysis_source()
            raw_samples = source_client.acquire(
                _session_with_prepared_subtitles(session),
                purpose=str(job.get("purpose") or "rolling"),
                timestamps_ms=[
                    int(value)
                    for value in (job.get("planned_timestamps_ms") or [])
                ],
            )
            session = _require_job_live(job, stage="after_source_acquire")
            prepared_from_source = prepare_samples(
                session_id=session_id,
                media_id=str((session.get("media") or {}).get("id") or ""),
                timeline_epoch=int((session.get("playback") or {}).get("timeline_epoch") or 0),
                duration_ms=int((session.get("media") or {}).get("duration_ms") or 0),
                purpose=str(job.get("purpose") or "rolling"),
                raw_samples=raw_samples,
            )
            _require_job_live(job, stage="after_source_prepare")
            refreshed, attached = watch_analysis_store.attach_source_samples(
                job,
                prepared_from_source,
            )
            if not attached:
                purge_prepared_samples(prepared_from_source)
                if refreshed is None:
                    latest = watch_analysis_store.get_job(job_id, public=True) or {}
                    reason = str(latest.get("cancel_reason") or "stale_timeline")
                    logger.info(
                        "跳过一起看任务 job_id=%s session_id=%s stage=attach_source_samples skip_reason=%s",
                        job_id,
                        session_id,
                        reason,
                    )
                    return {"status": "cancelled", "reason": reason}
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
        samples = watch_subtitle_store.enrich_samples_with_subtitles(
            session,
            job,
            samples,
        )

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
                "provider_called": False,
                "cost_reported": True,
                "elapsed_ms": 0,
                "model": "local-fingerprint-reuse",
            }
        elif post is None:
            session = _require_job_live(job, stage="before_gemini")
            result, usage = analyze_watch_samples(session, job, samples)
            _require_job_live(job, stage="after_gemini")
        else:
            session = _require_job_live(job, stage="before_gemini")
            result, usage = analyze_watch_samples(session, job, samples, post=post)
            _require_job_live(job, stage="after_gemini")

        _require_job_live(job, stage="before_result_commit")
        committed = watch_analysis_store.commit_analysis_result(
            job,
            result=result,
            usage=usage,
            samples=samples,
        )
        if committed.get("applied") and str(job.get("purpose") or "") == "rolling":
            try:
                cached_frames = cache_analysis_frames(session, samples)
                if cached_frames:
                    latest_session = watch_runtime_store.get_session(session_id) or session
                    latest_playback = (
                        latest_session.get("playback")
                        if isinstance(latest_session.get("playback"), dict)
                        else {}
                    )
                    retention = watch_visual_store.prune_session_frames(
                        session_id,
                        timeline_epoch=int(latest_playback.get("timeline_epoch") or 0),
                        playhead_ms=int(latest_playback.get("playhead_ms") or 0),
                    )
                    logger.info(
                        "一起看派生帧已缓存 session_id=%s epoch=%s count=%s retained=%s deleted=%s",
                        session_id,
                        latest_playback.get("timeline_epoch"),
                        len(cached_frames),
                        retention.get("retained"),
                        retention.get("rows_deleted"),
                    )
            except Exception as exc:
                logger.warning("一起看派生帧缓存失败 session_id=%s: %s", session_id, exc)
        if committed.get("applied") or committed.get("reason") in {
            "stale_timeline",
            "lease_lost",
        }:
            watch_analysis_store.purge_job_samples(job)
        return {
            "status": "done" if committed.get("applied") else "cancelled",
            **committed,
        }
    except WatchJobCancelled as exc:
        purge_prepared_samples(prepared_from_source)
        return {"status": "cancelled", "reason": exc.reason, "stage": exc.stage}
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
        status = watch_analysis_store.fail_job(
            job,
            str(exc),
            retryable=exc.retryable,
            usage=exc.usage,
        )
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
    knowledge_search_post: Callable[..., Any] | None = None,
    knowledge_model_post: Callable[..., Any] | None = None,
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
    outcome = process_claimed_job(
        job,
        post=post,
        source=source,
        knowledge_search_post=knowledge_search_post,
        knowledge_model_post=knowledge_model_post,
    )
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
    abandoned = cleanup_abandoned_sessions()
    if abandoned.get("sessions_ended"):
        logger.info(
            "结束一起看遗留会话 skip_reason=client_lease_expired stats=%s",
            abandoned,
        )
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
            visual_cleanup = watch_visual_store.cleanup_expired_frames()
            if visual_cleanup.get("rows_deleted"):
                logger.info("清理一起看过期派生帧 stats=%s", visual_cleanup)
            subtitle_deleted = watch_subtitle_store.cleanup_expired_assets()
            if subtitle_deleted:
                logger.info("清理一起看过期字幕资产 count=%s", subtitle_deleted)
            abandoned = cleanup_abandoned_sessions()
            if abandoned.get("sessions_ended"):
                logger.info(
                    "结束一起看失联会话 skip_reason=client_lease_expired stats=%s",
                    abandoned,
                )
            watch_runtime_store.cleanup_expired_sessions()
            last_cleanup = now
        knowledge_scheduled = schedule_knowledge_jobs()
        if knowledge_scheduled.get("jobs_created"):
            logger.info("一起看知识卡任务已入队 stats=%s", knowledge_scheduled)
        subtitle_scheduled = schedule_subtitle_jobs()
        if subtitle_scheduled.get("jobs_created"):
            logger.info("一起看字幕准备任务已入队 stats=%s", subtitle_scheduled)
        scheduled = schedule_source_jobs()
        if scheduled.get("jobs_created"):
            logger.info("一起看后端取材任务已入队 stats=%s", scheduled)
        outcome = process_next_job()
        if outcome is None:
            time.sleep(idle)


if __name__ == "__main__":
    run_worker_loop()
