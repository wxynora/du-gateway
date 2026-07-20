#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEMP_DIR = Path(tempfile.mkdtemp(prefix="watch-analysis-phase2-test-"))
os.environ["RUNTIME_STATE_DB"] = str(TEMP_DIR / "runtime.sqlite3")
os.environ["WATCH_ANALYSIS_SAMPLE_DIR"] = str(TEMP_DIR / "samples")
os.environ["WATCH_VISUAL_CACHE_DIR"] = str(TEMP_DIR / "visual-cache")
os.environ["OPENROUTER_API_KEY"] = "test-watch-analysis-key"
os.environ["WATCH_KNOWLEDGE_API_KEY"] = "test-watch-knowledge-key"
os.environ["TAVILY_API_KEY"] = "test-tavily-key"
os.environ["WATCH_VISUAL_FRAME_PAST_WINDOW_MS"] = "600000"
os.environ["WATCH_VISUAL_FRAME_FUTURE_WINDOW_MS"] = "300000"
os.environ["WATCH_VISUAL_FRAME_MAX_PER_SESSION"] = "48"

from PIL import Image  # noqa: E402

from config import (  # noqa: E402
    WATCH_SUBTITLE_JOB_MAX_ATTEMPTS,
    WATCH_SUBTITLE_REQUEST_TIMEOUT_SECONDS,
)
from services.watch_analysis import (  # noqa: E402
    ANALYSIS_SYSTEM_PROMPT,
    WatchAnalysisProviderError,
    analyze_watch_samples,
    build_watch_analysis_request,
    normalize_watch_analysis_result,
)
from services.watch_knowledge import normalize_knowledge_card  # noqa: E402
from scripts.run_watch_analysis_worker import (  # noqa: E402
    _session_with_prepared_subtitles,
    process_next_job,
    schedule_knowledge_jobs,
    schedule_source_jobs,
    schedule_subtitle_jobs,
)
from services.watch_analysis_samples import (  # noqa: E402
    WatchAnalysisSampleError,
    prepare_samples,
    purge_prepared_samples,
)
from services.watch_analysis_source import (  # noqa: E402
    BILIBILI_PLAYER_API,
    BILIBILI_PLAYURL_API,
    BILIBILI_VIEW_API,
    BilibiliApiAnalysisSource,
    canonical_bilibili_url,
)
from services.watch_subtitles import SubtitleLookupError  # noqa: E402
from services.watch_context import build_watch_context  # noqa: E402
from storage import (  # noqa: E402
    runtime_sqlite,
    watch_analysis_store,
    watch_knowledge_store,
    watch_runtime_store,
    watch_subtitle_store,
    watch_visual_store,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _set_terminal_subtitle(session_id: str, status: str = "not_configured") -> str:
    lookup_id = f"test-subtitle-{session_id}"
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET subtitle_lookup_json = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "lookup_id": lookup_id,
                        "status": status,
                        "provider": "subdl",
                        "message": "测试终态",
                        "can_retry": status != "found",
                    },
                    ensure_ascii=False,
                ),
                session_id,
            ),
        )
    return lookup_id


def _frame_bytes(color: tuple[int, int, int] = (38, 82, 118)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 36), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(color: tuple[int, int, int] = (38, 82, 118)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 36), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _audio_bytes() -> bytes:
    return b"ID3" + (b"\x00" * 256)


def _samples(session: dict, purpose: str, timestamps: list[int]) -> list[dict]:
    media = session["media"]
    playback = session["playback"]
    return prepare_samples(
        session_id=session["session_id"],
        media_id=media["id"],
        timeline_epoch=playback["timeline_epoch"],
        duration_ms=media["duration_ms"],
        purpose=purpose,
        raw_samples=[
            {
                "at_ms": at_ms,
                "mime_type": "image/png",
                "image_bytes": _frame_bytes((38 + index, 82, 118)),
                "subtitle": f"字幕 {at_ms}",
                "captured_at": "2026-07-18T10:00:00Z",
            }
            for index, at_ms in enumerate(timestamps)
        ],
    )


def _enqueue(session_id: str, purpose: str, timestamps: list[int]) -> tuple[dict, list[dict]]:
    session = watch_runtime_store.get_session(session_id)
    _assert(session is not None, "测试观看会话不存在")
    prepared = _samples(session, purpose, timestamps)
    job, created = watch_analysis_store.enqueue_samples(
        session=session,
        purpose=purpose,
        samples=prepared,
        idempotency_key=f"phase2:{session_id}:{session['playback']['timeline_epoch']}:{purpose}:{timestamps}",
    )
    _assert(created, f"{purpose} 分析任务没有创建")
    return job, prepared


def _raw_result(
    *,
    identity: str = "测试电影 / 第一集",
    sections: list[dict] | None = None,
    chunks: list[dict] | None = None,
    story_through_ms: int = 0,
    story_summary: str = "",
    story_background: str = "",
    risks: list[dict] | None = None,
) -> dict:
    return {
        "familiarity": {
            "status": "recognized",
            "identity": identity,
            "confidence": 0.96,
        },
        "canonical_identity": {
            "title": identity.split(" / ", 1)[0],
            "original_title": "Test Movie",
            "year": 2025,
        },
        "timeline_sections": sections or [],
        "plot_chunks": chunks or [],
        "story_background": {
            "through_ms": story_through_ms,
            "background": story_background or story_summary,
            "characters": ["林夏"] if story_summary else [],
        },
        "risk_events": risks or [],
        "analysis_notes": "test",
    }


class _FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200, cost: Any = 0.002) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)
        self._payload = {
            "model": "google/gemini-2.5-flash",
            "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
                "cost": cost,
            },
        }

    def json(self) -> dict:
        return self._payload


class _RawHttpResponse:
    def __init__(self, payload: dict, *, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _KnowledgeSearchResponse:
    def __init__(self, sources: list[dict]) -> None:
        self.status_code = 200
        self._payload = {"results": sources}
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


class _KnowledgeHttpResponse:
    def __init__(self, card: dict) -> None:
        self.status_code = 200
        self._payload = {
            "model": "deepseek-v4-flash",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(card, ensure_ascii=False),
                    "citations": [],
                },
            ],
            "usage": {"input_tokens": 320, "output_tokens": 180},
        }
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


def _post_for(payload: dict, captured: list[dict] | None = None, *, cost: Any = 0.002):
    def _post(_url: str, **kwargs):
        if captured is not None:
            captured.append(kwargs)
        return _FakeResponse(payload, cost=cost)

    return _post


def _failing_post(_url: str, **_kwargs):
    return _FakeResponse({}, status_code=503)


def _analysis_message_post(message: dict):
    def _post(_url: str, **_kwargs):
        return _RawHttpResponse(
            {
                "model": "google/gemini-2.5-flash",
                "choices": [{"message": message}],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                    "cost": 0.002,
                },
            }
        )

    return _post


def _test_analysis_response_adapter() -> None:
    session = {
        "mode": {"knowledge_mode": "known"},
        "media": {"id": "local:response-adapter", "title": "测试作品", "duration_ms": 60_000},
        "analysis": {},
    }
    job = {"purpose": "rolling", "range_start_ms": 10_000, "range_end_ms": 20_000}
    samples = [
        {"at_ms": 10_000, "mime_type": "text/plain", "text_content": "片段开始"},
        {"at_ms": 20_000, "mime_type": "text/plain", "text_content": "片段结束"},
    ]
    raw = _raw_result(
        chunks=[
            {
                "start_ms": 10_000,
                "end_ms": 20_000,
                "description": "林夏推开门，走进旧宅。",
                "characters": ["林夏"],
                "tags": ["进入旧宅"],
                "confidence": 0.92,
            }
        ],
        story_through_ms=20_000,
        story_summary="林夏已经进入旧宅。",
    )
    raw_text = json.dumps(raw, ensure_ascii=False)
    trailing_comma_text = raw_text[:-1] + ",\n}"
    wrapped_result, wrapped_usage = analyze_watch_samples(
        session,
        job,
        samples,
        post=_analysis_message_post(
            {
                "content": "前面是一个无关示例：{}。\n```json\n" + trailing_comma_text + "\n```\n以上为分析结果。"
            }
        ),
    )
    _assert(
        wrapped_result["plot_chunks"][0]["summary"] == "林夏推开门，走进旧宅。",
        "围栏、前后说明和尾逗号导致有效分析结果丢失",
    )
    _assert(wrapped_usage["total_tokens"] == 200, "宽松解析成功后没有保留上游 usage")

    split_at = len(raw_text) // 2
    blocked_result, _usage = analyze_watch_samples(
        session,
        job,
        samples,
        post=_analysis_message_post(
            {
                "content": [
                    {"type": "text", "text": raw_text[:split_at]},
                    {"type": "text", "text": raw_text[split_at:]},
                ]
            }
        ),
    )
    _assert(blocked_result["story_background"]["through_ms"] == 20_000, "分块 content 没有重新拼接解析")

    parsed_result, _usage = analyze_watch_samples(
        session,
        job,
        samples,
        post=_analysis_message_post({"content": "", "parsed": raw}),
    )
    _assert(parsed_result["plot_chunks"][0]["summary"] == "林夏推开门，走进旧宅。", "message.parsed 结构化结果没有被接受")

    truncated_content = raw_text[:-40]
    log_stream = StringIO()
    log_handler = logging.StreamHandler(log_stream)
    analysis_logger = logging.getLogger("services.watch_analysis")
    previous_level = analysis_logger.level
    analysis_logger.setLevel(logging.WARNING)
    analysis_logger.addHandler(log_handler)
    try:
        try:
            analyze_watch_samples(
                session,
                {**job, "job_id": "watch_job_response_adapter"},
                samples,
                post=_analysis_message_post({"content": truncated_content}),
            )
        except WatchAnalysisProviderError as exc:
            _assert("JSON 不完整" in str(exc), "截断响应仍被报告成笼统解析错误")
            _assert(exc.usage.get("cost_usd") == 0.002, "解析失败丢失了已产生的模型费用")
            _assert(exc.usage.get("cost_reported") is True, "解析失败费用没有标记为上游已返回")
        else:
            raise AssertionError("截断 JSON 被错误当作完整风险分析")
    finally:
        analysis_logger.removeHandler(log_handler)
        analysis_logger.setLevel(previous_level)
    failure_log = log_stream.getvalue()
    _assert("job_id=watch_job_response_adapter" in failure_log, "解析失败日志没有任务定位字段")
    _assert("raw_response=" in failure_log, "解析失败日志没有保存上游原文")
    escaped_content = json.dumps(truncated_content, ensure_ascii=False)[1:-1]
    _assert(escaped_content in failure_log, "解析失败日志截断或丢失了模型原始内容")


def _test_session_analysis_cost_accumulates_retry_usage() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-session-cost",
        window_id="sumitalk:session-cost",
        companion={"id": "companion", "name": "Companion"},
        media={
            "id": "bili:BV-session-cost:p1",
            "source": "bilibili_embed",
            "title": "费用累计测试",
            "duration_ms": 60_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": False},
    )
    job, samples = _enqueue(session["session_id"], "rolling", [10_000, 20_000])
    claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(claimed is not None and claimed["job_id"] == job["job_id"], "费用测试任务没有领取")
    retry_status = watch_analysis_store.fail_job(
        claimed,
        "模型已计费但结果解析失败",
        retryable=True,
        usage={
            "input_tokens": 100,
            "output_tokens": 40,
            "total_tokens": 140,
            "cost_usd": 0.001,
            "provider_called": True,
            "cost_reported": True,
            "model": "test-analysis-model",
        },
    )
    _assert(retry_status == "queued", "已计费的解析失败没有进入正常重试")
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_analysis_jobs SET available_at = '2000-01-01T00:00:00Z' WHERE id = ?",
            (job["job_id"],),
        )
    retried = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(retried is not None and retried["job_id"] == job["job_id"], "费用测试重试任务没有领取")
    committed = watch_analysis_store.commit_analysis_result(
        retried,
        result={
            "timeline_sections": [],
            "plot_chunks": [],
            "story_background": {},
            "risk_events": [],
            "covered_from_ms": 10_000,
            "covered_until_ms": 20_000,
            "analysis_version": "session-cost-test",
        },
        usage={
            "input_tokens": 120,
            "output_tokens": 60,
            "total_tokens": 180,
            "cost_usd": 0.002,
            "provider_called": True,
            "cost_reported": True,
            "model": "test-analysis-model",
        },
        samples=samples,
    )
    _assert(committed.get("applied"), "费用测试重试结果没有提交")
    cost = watch_analysis_store.session_analysis_cost(session["session_id"])
    _assert(abs(cost["amount_usd"] - 0.003) < 0.0000001, "重试产生的两次费用没有累计")
    _assert(cost["provider_calls"] == 2 and cost["priced_calls"] == 2, "模型调用计数不正确")
    _assert(cost["complete"] is True and cost["pending_jobs"] == 0, "完整费用被错误标成未结算")
    _assert(cost["input_tokens"] == 220 and cost["output_tokens"] == 100, "会话 token 没有累计")
    watch_runtime_store.end_session(session["session_id"])


def _test_paid_usage_survives_end_race_and_is_idempotent() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-usage-race",
        window_id="sumitalk:usage-race",
        companion={"id": "companion", "name": "Companion"},
        media={
            "id": "bili:BV-usage-race:p1",
            "source": "bilibili_embed",
            "title": "费用竞态测试",
            "duration_ms": 180_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": False},
    )
    job, samples = _enqueue(session["session_id"], "rolling", [0, 20_000])
    claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(claimed and claimed["job_id"] == job["job_id"], "费用竞态任务未领取")
    usage = {
        "input_tokens": 120,
        "output_tokens": 40,
        "total_tokens": 160,
        "cost_usd": 0.0123,
        "provider_calls": 1,
        "priced_calls": 1,
        "cost_reported": True,
        "model": "test-provider",
    }
    _assert(
        watch_analysis_store.record_job_usage(claimed, usage, event_key="analysis:1:provider"),
        "供应商调用费用没有先行落账",
    )
    watch_runtime_store.end_session(session["session_id"])
    _assert(
        watch_analysis_store.cancel_claimed_job(claimed, reason="session_ended"),
        "结束竞态中的已领取任务没有进入取消终态",
    )
    _assert(
        watch_analysis_store.record_job_usage(claimed, usage, event_key="analysis:1:provider"),
        "结束后重复确认费用事件失败",
    )
    cost = watch_analysis_store.session_analysis_cost(session["session_id"])
    _assert(abs(cost["amount_usd"] - 0.0123) < 0.0000001, "结束竞态丢失或重复累计费用")
    _assert(cost["provider_calls"] == 1 and cost["pricing_complete"], "费用事件幂等状态不正确")
    _assert(cost["complete"], "会话结束后费用仍被错误标记为处理中")
    watch_analysis_store.purge_job_samples(claimed)


def _test_seek_reuses_paid_coverage_without_reanalysis() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-seek-cache",
        window_id="sumitalk:seek-cache",
        companion={"id": "companion", "name": "Companion"},
        media={
            "id": "bili:BV-seek-cache:p1",
            "source": "bilibili_embed",
            "title": "Seek 缓存测试",
            "duration_ms": 180_000,
            "content_start_ms": 0,
            "content_end_ms": 180_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": True},
    )
    session_id = session["session_id"]
    watch_runtime_store.update_analysis_state(
        session_id,
        {"status": "analyzing", "familiarity": "recognized", "identity": "Seek 缓存测试"},
    )
    watch_runtime_store.update_preparation_state(
        session_id,
        status="ready_to_confirm",
        knowledge_card_status="not_required",
    )
    watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="confirm",
        subtitle_lookup_id=_set_terminal_subtitle(session_id),
        protection_action="continue_unprotected",
    )
    job, samples = _enqueue(session_id, "rolling", [0, 70_000, 140_000])
    claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(claimed and claimed["job_id"] == job["job_id"], "Seek 缓存任务未领取")
    committed = watch_analysis_store.commit_analysis_result(
        claimed,
        result={
            "timeline_sections": [],
            "plot_chunks": [
                {
                    "start_ms": 10_000,
                    "end_ms": 120_000,
                    "summary": "这段剧情已经付费解析。",
                    "characters": ["林夏"],
                    "tags": ["缓存"],
                    "confidence": 0.9,
                }
            ],
            "story_background": {
                "through_ms": 140_000,
                "background": "",
                "characters": [],
            },
            "risk_events": [
                {
                    "risk_type": "jumpscare",
                    "severity": "2",
                    "start_ms": 80_000,
                    "end_ms": 82_000,
                    "warn_at_ms": 73_000,
                    "label": "前方有突然惊吓。",
                    "companion_hint": "前方有突然惊吓。",
                    "confidence": 0.9,
                }
            ],
            "covered_from_ms": 0,
            "covered_until_ms": 140_000,
            "analysis_version": "seek-cache-test",
        },
        usage={
            "cost_usd": 0.02,
            "provider_calls": 1,
            "priced_calls": 1,
            "cost_reported": True,
        },
        samples=samples,
    )
    _assert(committed.get("applied"), "Seek 缓存基础剧情没有落库")
    before_cost = watch_analysis_store.session_analysis_cost(session_id)
    _updated, applied, _ignored = watch_runtime_store.update_playback(
        session_id,
        {
            "media_id": "bili:BV-seek-cache:p1",
            "playhead_ms": 30_000,
            "is_playing": False,
            "playback_rate": 1.0,
            "timeline_epoch": 1,
            "snapshot_seq": 1,
            "captured_at": "2026-07-21T00:00:00Z",
        },
    )
    _assert(applied, "Seek 缓存测试没有切换 epoch")
    watch_analysis_store.reset_for_epoch(session_id, timeline_epoch=1)
    plan = watch_analysis_store.build_sample_plan(watch_runtime_store.get_session(session_id))
    refreshed = watch_runtime_store.get_session(session_id)
    _assert(refreshed["analysis"]["covered_until_ms"] == 140_000, "Seek 后没有恢复已付费覆盖")
    _assert(plan["purpose"] == "rolling", "Seek 后错误重跑作品识别或时间轴预扫")
    _assert(plan["audio_range_start_ms"] >= 140_000, "Seek 后重新取材了已付费剧情区间")
    copied_chunks = watch_runtime_store.get_plot_chunks(
        session_id,
        timeline_epoch=1,
        start_before_ms=140_000,
        end_after_ms=0,
        limit=20,
    )
    copied_risks = watch_runtime_store.get_risk_events(
        session_id,
        timeline_epoch=1,
        from_ms=0,
        until_ms=140_000,
        limit=20,
    )
    _assert(copied_chunks and copied_risks, "Seek 后只恢复覆盖游标，没有恢复剧情或高能结果")
    after_cost = watch_analysis_store.session_analysis_cost(session_id)
    _assert(after_cost["amount_usd"] == before_cost["amount_usd"], "复用缓存额外增加了费用")
    watch_runtime_store.end_session(session_id)


def _test_normal_mode_waits_for_five_minute_initial_coverage() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-normal-initial-gate",
        window_id="sumitalk:normal-initial-gate",
        companion={"id": "companion", "name": "Companion"},
        media={
            "id": "bili:BV-normal-initial-gate:p1",
            "source": "bilibili_embed",
            "title": "普通模式首段门禁测试",
            "part_title": "P1",
            "duration_ms": 600_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": False},
    )
    session_id = session["session_id"]
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET analysis_familiarity = 'recognized', "
            "knowledge_card_status = 'not_required', preparation_status = 'ready_to_confirm' "
            "WHERE id = ?",
            (session_id,),
        )
    started = watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="confirm",
        subtitle_lookup_id=_set_terminal_subtitle(session_id),
    )
    gate = watch_runtime_store.get_start_gate(started)
    _assert(gate["status"] == "buffering" and not gate["can_play"], "普通模式确认后直接解锁")
    _assert(gate["required_until_ms"] == 300_000, "普通模式首段门禁不是五分钟")
    _assert(not gate["can_continue_unprotected"], "普通模式错误暴露了无保护继续")

    first_job, first_samples = _enqueue(session_id, "rolling", [0, 299_999])
    first_claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(first_claimed and first_claimed["job_id"] == first_job["job_id"], "普通模式首批任务未领取")
    watch_analysis_store.commit_analysis_result(
        first_claimed,
        result={
            "timeline_sections": [],
            "plot_chunks": [],
            "story_background": {},
            "risk_events": [],
            "covered_from_ms": 0,
            "covered_until_ms": 299_999,
            "analysis_version": "normal-initial-gate-test",
        },
        usage={"cost_usd": 0},
        samples=first_samples,
    )
    almost_ready = watch_runtime_store.get_session(session_id)
    _assert(
        not watch_runtime_store.get_start_gate(almost_ready)["can_play"],
        "普通模式不足五分钟时提前解锁",
    )

    final_job, final_samples = _enqueue(session_id, "rolling", [299_999, 300_000])
    final_claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(final_claimed and final_claimed["job_id"] == final_job["job_id"], "普通模式补齐任务未领取")
    watch_analysis_store.commit_analysis_result(
        final_claimed,
        result={
            "timeline_sections": [],
            "plot_chunks": [],
            "story_background": {},
            "risk_events": [],
            "covered_from_ms": 299_999,
            "covered_until_ms": 300_000,
            "analysis_version": "normal-initial-gate-test",
        },
        usage={"cost_usd": 0},
        samples=final_samples,
    )
    ready = watch_runtime_store.get_session(session_id)
    ready_gate = watch_runtime_store.get_start_gate(ready)
    _assert(ready_gate["status"] == "ready" and ready_gate["can_play"], "普通模式满五分钟后未自动解锁")
    _assert(ready["preparation"]["playback_unlocked_at"], "普通模式解锁没有原子持久化")
    watch_runtime_store.end_session(session_id)


def _test_initial_fear_coverage_unlocks_playback() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-initial-gate",
        window_id="sumitalk:initial-gate",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-initial-gate:p1",
            "source": "bilibili_embed",
            "title": "首段门禁测试",
            "part_title": "P1",
            "duration_ms": 600_000,
        },
        mode={
            "knowledge_mode": "known",
            "fear_mode": True,
            "fear_action": "cover_video",
            "danmaku_enabled": True,
        },
    )
    session_id = session["session_id"]
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET analysis_familiarity = 'recognized', "
            "knowledge_card_status = 'not_required', preparation_status = 'ready_to_confirm' "
            "WHERE id = ?",
            (session_id,),
        )
    started = watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="confirm",
        subtitle_lookup_id=_set_terminal_subtitle(session_id),
    )
    _assert(
        watch_runtime_store.get_start_gate(started)["status"] == "buffering",
        "首段分析前没有保持播放器锁定",
    )

    _job, samples = _enqueue(session_id, "rolling", [0, 300_000])
    claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(claimed is not None and claimed["job_id"] == _job["job_id"], "首段分析任务没有领取")
    committed = watch_analysis_store.commit_analysis_result(
        claimed,
        result={
            "timeline_sections": [],
            "plot_chunks": [],
            "story_background": {},
            "risk_events": [],
            "covered_from_ms": 0,
            "covered_until_ms": 300_000,
            "analysis_version": "initial-gate-test",
        },
        usage={"cost_usd": 0},
        samples=samples,
    )
    _assert(committed.get("applied"), "首段分析结果没有提交")
    unlocked = watch_runtime_store.get_session(session_id)
    _assert(unlocked is not None, "首段门禁测试会话意外消失")
    gate = watch_runtime_store.get_start_gate(unlocked)
    _assert(gate["covered_until_ms"] == 300_000, "首段分析覆盖范围没有保存")
    _assert(gate["status"] == "ready" and gate["can_play"], "首段覆盖达标后播放器没有自动解锁")
    _assert(
        bool(unlocked["preparation"]["playback_unlocked_at"]),
        "首段覆盖达标后没有原子写入 playback_unlocked_at",
    )
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET analysis_status = 'analyzing' WHERE id = ?",
            (session_id,),
        )
    continuing_gate = watch_runtime_store.get_start_gate(
        watch_runtime_store.get_session(session_id)
    )
    _assert(
        continuing_gate["status"] == "ready" and continuing_gate["can_play"],
        "后续预解析开始后重新锁住了已经放行的播放器",
    )
    watch_runtime_store.end_session(session_id)


def _test_knowledge_preparation_flow() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-knowledge",
        window_id="sumitalk:knowledge",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-knowledge:p1",
            "source": "bilibili_embed",
            "title": "陌生作品",
            "part_title": "第一集",
            "duration_ms": 1_200_000,
        },
        mode={
            "knowledge_mode": "needs_summary",
            "fear_mode": False,
            "fear_action": "warn_only",
            "danmaku_enabled": True,
        },
    )
    session_id = session["session_id"]
    watch_runtime_store.update_analysis_state(
        session_id,
        {
            "familiarity": "unknown",
            "identity": "陌生作品 / 第一集",
            "status": "analyzing",
        },
    )
    scheduled = schedule_knowledge_jobs(limit=1)
    _assert(scheduled["jobs_created"] == 1, "陌生作品没有创建开播前知识卡任务")
    preparing = watch_runtime_store.get_session(session_id)
    _assert(
        preparing["preparation"]["status"] == "collecting_sources",
        "知识卡任务没有进入搜集资料状态",
    )

    search_calls: list[dict] = []
    model_calls: list[dict] = []

    card_raw = {
        "canonical_identity": {
            "title": "陌生作品",
            "original_title": "",
            "year": 2026,
            "work_type": "series",
            "season": "第一季",
            "episode": "第一集",
            "version_notes": "测试版本",
            "aliases": [],
        },
        "setting": {
            "time_period": "现代",
            "locations": ["城郊旧宅"],
            "premise": "林夏为了调查失踪案进入旧宅。",
        },
        "characters": [
            {
                "name": "林夏",
                "aliases": [],
                "identity": "调查者",
                "visual_cues": ["短发"],
                "relationships": [{"relation": "朋友", "target": "周岚"}],
            },
            {
                "name": "周岚",
                "aliases": [],
                "identity": "外部接应者",
                "visual_cues": [],
                "relationships": [{"relation": "朋友", "target": "林夏"}],
            },
            {
                "name": "无证人",
                "aliases": [],
                "identity": "没有任何来源证据的角色",
                "visual_cues": [],
                "relationships": [],
            },
        ],
        "terminology": [{"term": "旧宅", "meaning": "失踪案的调查地点"}],
        "pre_story": "失踪案发生后，林夏决定亲自调查。",
        "story_outline": ["林夏进入旧宅调查失踪案。", "她逐步发现旧宅中的异常线索。"],
        "source_notes": [
            {
                "title": "不会采用模型改写的标题",
                "url": "https://example.com/work-background",
                "scope": "target_work",
                "supports": ["setting.premise", "characters.林夏.identity"],
            },
            {
                "title": "人物资料",
                "url": "https://example.org/work-characters",
                "scope": "target_work",
                "supports": ["characters"],
            },
        ],
        "limitations": [],
        "confidence": 0.88,
    }

    def _search_post(_url: str, **kwargs):
        search_calls.append(kwargs)
        return _KnowledgeSearchResponse(
            [
                {
                    "title": "陌生作品背景资料",
                    "url": "https://example.com/work-background",
                    "content": "陌生作品讲述林夏进入旧宅调查失踪案。",
                },
                {
                    "title": "陌生作品人物资料",
                    "url": "https://example.org/work-characters",
                    "content": "林夏是调查者，周岚负责在外接应。",
                },
                {
                    "title": "陌生作品世界观资料",
                    "url": "https://example.net/work-setting",
                    "content": "旧宅是故事中的主要调查地点。",
                },
            ]
        )

    def _model_post(_url: str, **kwargs):
        model_calls.append(kwargs)
        return _KnowledgeHttpResponse(card_raw)

    outcome = process_next_job(
        knowledge_search_post=_search_post,
        knowledge_model_post=_model_post,
    )
    _assert(outcome and outcome["status"] == "done", "知识卡任务没有完成")
    _assert(len(search_calls) == 1, "知识卡没有收敛为一次搜索")
    search_payload = search_calls[0]["json"]
    _assert(
        search_payload["query"] == "《陌生作品》第一集剧情简介 主要人物 人物关系 世界观",
        "知识卡没有使用确认后的自然搜索词",
    )
    _assert(search_payload["max_results"] == 3, "知识卡单次搜索没有限制为三条结果")
    _assert(search_payload["search_depth"] == "basic", "知识卡单次搜索仍在使用不必要的 advanced")
    _assert(search_payload["include_raw_content"] is False, "知识卡搜索仍在抓取整页正文")
    _assert("include_domains" not in search_payload, "知识卡搜索仍限制角色目录站点")
    knowledge_request = model_calls[0]["json"]
    knowledge_prompt = knowledge_request["system"]
    _assert(knowledge_request["model"] == "deepseek-v4-flash", "知识卡没有使用 DS V4 Flash")
    _assert("max_tokens" not in knowledge_request, "知识卡请求仍携带显式输出上限")
    _assert(knowledge_request["thinking"] == {"type": "disabled"}, "知识卡没有关闭 thinking")
    _assert("tools" not in knowledge_request, "知识卡整理阶段仍允许模型自行搜索")
    _assert("SEARCH_SOURCES=" in knowledge_request["messages"][0]["content"], "受控搜索摘要没有传给知识卡模型")
    _assert("Bangumi 结构化角色目录" not in knowledge_request["messages"][0]["content"], "知识卡仍混入结构化角色目录")
    _assert("完整剧情数据库" in knowledge_prompt and "不得写结局、反转" in knowledge_prompt, "知识卡没有限制粗剧情大纲边界")
    _assert("ordered_plot_outline" not in knowledge_request["messages"][0]["content"], "知识卡请求仍包含完整剧情大纲字段")
    _assert("plot_chunks" not in knowledge_prompt and "story_so_far" not in knowledge_prompt, "开播前知识卡混入滚动剧情提示词")
    _assert("小玥" not in knowledge_prompt and "渡" not in knowledge_prompt, "知识卡提示词写入宿主私有名字")
    _assert("未受信" in knowledge_prompt, "知识卡提示词没有隔离公开网页中的提示注入")
    _assert("严格区分发行顺序与故事内时间线" in knowledge_prompt, "知识卡提示词没有约束系列时间线")
    ready = watch_runtime_store.get_session(session_id)
    _assert(ready["preparation"]["status"] == "searching_subtitles", "知识卡完成后没有进入字幕准备")
    _assert(ready["preparation"]["knowledge_card_status"] == "ready", "知识卡状态没有变为 ready")
    card = watch_knowledge_store.get_card_for_session(ready)
    _assert(card["canonical_identity"]["title"] == "陌生作品", "知识卡没有按固定结构落库")
    _assert([item["name"] for item in card["characters"]] == ["林夏", "周岚"], "知识卡仍在模型结果之外硬补角色")
    _assert(card["characters"][0]["relationships"] == ["朋友：周岚"], "对象形式的人物关系没有转成可读文字")
    _assert(card["characters"][1]["relationships"] == [], "同一人物关系的反向表达没有全局去重")
    _assert("无证人" in "".join(card["limitations"]), "无来源证据的人物没有被门禁记录")
    _assert(
        any(note["url"] == "https://example.com/work-background" for note in card["source_notes"]),
        "模型来源没有匹配受控搜索结果",
    )
    _assert("ordered_plot_outline" not in card, "知识卡仍保存完整剧情大纲")
    _assert(len(card["story_outline"]) == 2, "知识卡没有保存简短粗剧情大纲")
    subtitle_scheduled = schedule_subtitle_jobs(limit=1)
    _assert(subtitle_scheduled["jobs_created"] == 1, "知识卡完成后没有创建字幕准备任务")
    subtitle_outcome = process_next_job(source=_FakeSubtitlePreparationSource())
    _assert(subtitle_outcome and subtitle_outcome["status"] == "done", "字幕准备任务没有完成")
    ready = watch_runtime_store.get_session(session_id)
    subtitle_lookup = ready["preparation"]["subtitle_lookup"]
    _assert(subtitle_lookup["status"] == "found", "字幕命中没有进入可见终态")
    _assert(subtitle_lookup["cue_count"] == 2, "字幕命中元数据没有返回条目数")
    _assert("cues" not in subtitle_lookup, "字幕正文被错误返回给前端")
    _assert(ready["preparation"]["status"] == "ready_to_confirm", "字幕准备完成后没有等待确认")
    preparation_cost = watch_analysis_store.session_analysis_cost(session_id)
    _assert(preparation_cost["complete"], "知识卡和字幕任务完成后费用仍显示处理中")
    _assert(not preparation_cost["pricing_complete"], "未报价的搜索和字幕调用被错误标成已计价")
    _assert(preparation_cost["provider_calls"] == 3, "知识卡搜索、整理模型或字幕调用没有完整入账")
    _assert(preparation_cost["unpriced_calls"] == 3, "未报价供应商调用数不正确")
    _assert(
        set(preparation_cost["breakdown"]) == {"knowledge_card", "subtitle_lookup"},
        "准备阶段费用没有按用途拆分",
    )
    prepared_session = _session_with_prepared_subtitles(ready)
    _assert(
        prepared_session["media"]["prepared_subtitle_cues"][0]["text"] == "Xin chao",
        "滚动分析没有读取已准备的本地字幕资产",
    )
    with runtime_sqlite.connect() as conn:
        asset_row = conn.execute(
            "SELECT created_at, expires_at FROM watch_subtitle_assets WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    _assert(asset_row is not None, "命中的字幕没有保存到本地资产表")
    asset_created = datetime.fromisoformat(str(asset_row["created_at"]).replace("Z", "+00:00"))
    asset_expires = datetime.fromisoformat(str(asset_row["expires_at"]).replace("Z", "+00:00"))
    _assert((asset_expires - asset_created).total_seconds() == 86_400, "字幕资产 TTL 不是 24 小时")
    prepass_scheduled = schedule_source_jobs(limit=1)
    _assert(prepass_scheduled["jobs_created"] == 1, "开播前没有创建片头片尾预处理任务")
    prepass_outcome = process_next_job(
        source=_FakeBackendSource(),
        post=_post_for(_raw_result(identity="陌生作品 / 第一集")),
    )
    _assert(prepass_outcome and prepass_outcome["status"] == "done", "开播前片头片尾预处理未完成")
    waiting_plan = watch_analysis_store.build_sample_plan(
        watch_runtime_store.get_session(session_id)
    )
    _assert(
        waiting_plan["reason"] == "waiting_for_start_confirmation",
        "知识卡待确认时滚动剧情解析仍会抢跑",
    )
    knowledge_samples = _samples(ready, "rolling", [0, 20_000])
    rolling_request = build_watch_analysis_request(
        ready,
        {"purpose": "rolling", "range_start_ms": 0, "range_end_ms": 20_000},
        knowledge_samples,
    )
    rolling_context = rolling_request["messages"][1]["content"][0]["text"]
    _assert("work_knowledge_card" in rolling_context, "滚动解析没有复用已确认的固定知识卡")
    purge_prepared_samples(knowledge_samples)
    try:
        watch_runtime_store.start_session(
            session_id,
            knowledge_card_action="confirm",
            knowledge_card_key="old-card-key",
            subtitle_lookup_id=subtitle_lookup["lookup_id"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("过期知识卡 key 仍能确认开播")
    started = watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="confirm",
        knowledge_card_key=ready["preparation"]["knowledge_card_key"],
        subtitle_lookup_id=subtitle_lookup["lookup_id"],
    )
    _assert(started["preparation"]["started_at"], "知识卡确认后没有正式开始")
    started_plan = watch_analysis_store.build_sample_plan(started)
    _assert(started_plan["purpose"] == "rolling", "确认开播后滚动剧情解析没有解锁")
    reused_session = watch_runtime_store.create_session(
        device_id="test-device-knowledge-reuse",
        window_id="sumitalk:knowledge-reuse",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-knowledge:p1",
            "source": "bilibili_embed",
            "title": "陌生作品",
            "part_title": "第一集",
            "duration_ms": 1_200_000,
        },
        mode={
            "knowledge_mode": "needs_summary",
            "fear_mode": False,
            "fear_action": "warn_only",
        },
    )
    watch_runtime_store.update_analysis_state(
        reused_session["session_id"],
        {"familiarity": "unknown", "identity": "陌生作品 / 第一集", "status": "analyzing"},
    )
    reused_job, reused_created = watch_knowledge_store.ensure_knowledge_job(
        watch_runtime_store.get_session(reused_session["session_id"])
    )
    _assert(not reused_created and reused_job.get("cached"), "24 小时知识卡缓存没有跨会话复用")
    reused_ready = watch_runtime_store.get_session(reused_session["session_id"])
    _assert(reused_ready["preparation"]["knowledge_card_status"] == "ready", "缓存知识卡没有进入待确认态")
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_knowledge_cards SET expires_at = '2000-01-01T00:00:00Z' WHERE cache_key = ?",
            (reused_ready["preparation"]["knowledge_card_key"],),
        )
    try:
        watch_runtime_store.start_session(
            reused_session["session_id"],
            knowledge_card_action="confirm",
            knowledge_card_key=reused_ready["preparation"]["knowledge_card_key"],
            subtitle_lookup_id=_set_terminal_subtitle(reused_session["session_id"]),
        )
    except ValueError as exc:
        _assert("已过期" in str(exc), "过期知识卡返回了错误原因")
    else:
        raise AssertionError("过期知识卡仍能确认开播")
    watch_runtime_store.end_session(reused_session["session_id"])
    watch_runtime_store.end_session(session_id)


def _test_knowledge_source_and_timeline_gates() -> None:
    session = {
        "media": {
            "id": "manual:luoxiaohei2",
            "source": "manual_title",
            "title": "罗小黑战记2",
            "part_title": "2025年中国动画电影",
        },
        "analysis": {
            "identity": "2025年中国动画电影《罗小黑战记2》",
            "familiarity": "unknown",
        },
    }
    sources = [
        {
            "source_id": "source_1",
            "title": "罗小黑战记2",
            "url": "https://zh.wikipedia.org/wiki/%E7%BD%97%E5%B0%8F%E9%BB%91%E6%88%98%E8%AE%B02",
            "content": "目标作品资料",
        },
        {
            "source_id": "source_2",
            "title": "罗小黑战记2剧情资料",
            "url": "https://movie.example/luoxiaohei-2",
            "content": "目标作品剧情资料",
        },
        {
            "source_id": "source_3",
            "title": "罗小黑战记动画剧集",
            "url": "https://series.example/luoxiaohei",
            "content": "故事时间发生在电影之后的剧集资料",
        },
    ]
    raw = {
        "canonical_identity": {
            "title": "罗小黑战记2",
            "original_title": "The Legend of Hei 2",
            "year": 2025,
            "work_type": "movie",
            "season": "",
            "episode": "",
            "version_notes": "中国大陆动画电影",
            "aliases": [],
        },
        "setting": {"time_period": "现代", "locations": ["会馆"], "premise": "会馆遇袭。"},
        "characters": [
            {
                "name": "罗小黑",
                "aliases": ["小黑"],
                "identity": "目标作品主角",
                "visual_cues": ["黑色猫妖"],
                "relationships": ["无限的徒弟"],
            },
            {
                "name": "罗小白",
                "aliases": ["小白"],
                "identity": "后续剧集人物",
                "visual_cues": [],
                "relationships": [],
            },
        ],
        "terminology": [],
        "pre_story": "只保留故事时间早于目标作品的前情。",
        "story_outline": [
            "会馆遇袭后，主角们开始调查事件原因。",
            "调查过程让人类与妖精之间的矛盾逐渐显现。",
        ],
        "source_notes": [
            {
                "title": "ignored",
                "url": "https://zh.wikipedia.org/wiki/%E7%BD%97%E5%B0%8F%E9%BB%91%E6%88%98%E8%AE%B02",
                "scope": "target_work",
                "supports": ["canonical_identity", "characters.罗小黑.identity"],
            },
            {
                "title": "ignored",
                "url": "https://movie.example/luoxiaohei-2",
                "scope": "target_work",
                "supports": ["setting.premise", "characters.罗小黑.relationships"],
            },
            {
                "title": "ignored",
                "url": "https://series.example/luoxiaohei",
                "scope": "continuity_reference",
                "supports": ["characters.罗小白.identity"],
            },
        ],
        "limitations": [],
        "confidence": 1.0,
    }
    normalized = normalize_knowledge_card(raw, session=session, sources=sources)
    _assert(
        [item["name"] for item in normalized["characters"]] == ["罗小黑"],
        "仅由后续剧集资料支持的人物仍进入目标作品人物卡",
    )
    _assert(normalized["confidence"] <= 0.78, "两站背景卡仍获得虚高置信度")
    _assert(
        any("罗小白" in item for item in normalized["limitations"]),
        "被时间线来源门禁移除的人物没有进入 limitations",
    )
    _assert("ordered_plot_outline" not in normalized, "简短背景卡仍包含完整剧情大纲")
    _assert(len(normalized["story_outline"]) == 2, "粗剧情大纲被错误移除")

    single_domain_sources = [dict(sources[0]), dict(sources[1])]
    single_domain_sources[1]["url"] = "https://en.wikipedia.org/wiki/Another_Page"
    single_source_card = normalize_knowledge_card(raw, session=session, sources=single_domain_sources)
    _assert(single_source_card["confidence"] <= 0.68, "单一来源背景卡仍获得虚高置信度")


class _FakeBackendSource:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def acquire(self, session: dict, *, purpose: str, timestamps_ms: list[int]) -> list[dict]:
        self.calls.append(
            {
                "media_id": session["media"]["id"],
                "purpose": purpose,
                "timestamps_ms": list(timestamps_ms),
            }
        )
        images = [
            {
                "at_ms": at_ms,
                "mime_type": "image/jpeg",
                "image_bytes": _jpeg_bytes((40 + index, 82, 118)),
                "subtitle": f"后端字幕 {at_ms}",
                "captured_at": "2026-07-18T09:59:00Z",
            }
            for index, at_ms in enumerate(timestamps_ms)
        ]
        if purpose != "rolling" or len(timestamps_ms) < 2:
            return images
        return [
            {
                "at_ms": timestamps_ms[0],
                "mime_type": "audio/mpeg",
                "audio_bytes": _audio_bytes(),
                "text_content": f"完整音频覆盖 {timestamps_ms[0]}ms 至 {timestamps_ms[-1]}ms",
                "captured_at": "2026-07-18T09:59:00Z",
            },
            *images,
        ]


class _FakeSubtitlePreparationSource:
    def prepare_subtitles(self, session: dict, *, original_title: str, year: int) -> dict:
        return {
            "status": "found",
            "provider": "subdl",
            "query_title": original_title,
            "year": year,
            "language_codes": ["VI"],
            "release_name": "Test.Release.2025",
            "format": "srt",
            "cues": [
                {"start_ms": 60_000, "end_ms": 61_500, "text": "Xin chao"},
                {"start_ms": 61_500, "end_ms": 63_000, "text": "Di theo toi"},
            ],
            "coverage_start_ms": 60_000,
            "coverage_end_ms": 63_000,
            "message": "已找到外部字幕",
            "provider_called": True,
        }


class _FailingSubtitlePreparationSource:
    def prepare_subtitles(self, session: dict, *, original_title: str, year: int) -> dict:
        raise SubtitleLookupError("test subtitle provider timeout")


class _FakeHttpResponse:
    def __init__(self, payload: dict, *, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeRawHttpResponse:
    def __init__(self, content: bytes, *, status_code: int = 200) -> None:
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", errors="replace")

    def json(self) -> dict:
        raise ValueError("raw response")


class _FakeBilibiliHttp:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, url: str, **kwargs) -> _FakeHttpResponse:
        self.calls.append({"url": url, **kwargs})
        params = kwargs.get("params") or {}
        if url == BILIBILI_VIEW_API:
            _assert(params == {"bvid": "BV1xx411c7mD"}, "视频信息接口参数错误")
            return _FakeHttpResponse(
                {
                    "code": 0,
                    "data": {
                        "bvid": "BV1xx411c7mD",
                        "title": "测试视频",
                        "pages": [
                            {"cid": 1001, "page": 1, "duration": 30, "part": "上"},
                            {"cid": 1002, "page": 2, "duration": 60, "part": "下"},
                        ],
                    },
                }
            )
        if url == BILIBILI_PLAYURL_API:
            _assert(params.get("bvid") == "BV1xx411c7mD", "播放地址接口 BVID 错误")
            _assert(params.get("cid") == 1002, "播放地址接口没有使用目标分 P 的 CID")
            return _FakeHttpResponse(
                {
                    "code": 0,
                    "data": {
                        "dash": {
                            "video": [
                                {
                                    "width": 1280,
                                    "height": 720,
                                    "codecs": "hvc1.1.6.L120.90",
                                    "bandwidth": 500000,
                                    "baseUrl": "https://media.example/high-hevc.m4s",
                                },
                                {
                                    "width": 854,
                                    "height": 480,
                                    "codecs": "avc1.64001F",
                                    "bandwidth": 400000,
                                    "baseUrl": "https://media.example/primary-avc.m4s",
                                    "backupUrl": ["https://backup.example/backup-avc.m4s"],
                                },
                            ],
                            "audio": [
                                {
                                    "bandwidth": 65000,
                                    "baseUrl": "https://media.example/audio.m4s",
                                }
                            ],
                        }
                    },
                }
            )
        if url == BILIBILI_PLAYER_API:
            _assert(params == {"bvid": "BV1xx411c7mD", "cid": 1002}, "字幕接口参数错误")
            return _FakeHttpResponse(
                {
                    "code": 0,
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {
                                    "lan": "zh-CN",
                                    "lan_doc": "中文",
                                    "subtitle_url": "//subtitle.example/track.json",
                                }
                            ]
                        }
                    },
                }
            )
        if url == "https://subtitle.example/track.json":
            return _FakeHttpResponse(
                {
                    "body": [
                        {"from": 0.5, "to": 1.5, "content": "测试字幕"},
                        {"from": 2.0, "to": 3.0, "content": "第二句台词"},
                    ]
                }
            )
        raise AssertionError(f"出现未预期的 HTTP 请求: {url}")


class _FakeCookieFallbackHttp:
    def __init__(self, *, play_requires_auth: bool) -> None:
        self.play_requires_auth = play_requires_auth
        self.calls: list[dict] = []

    def __call__(self, url: str, **kwargs) -> _FakeHttpResponse:
        headers = kwargs.get("headers") or {}
        authenticated = headers.get("Cookie") == "SESSDATA=test-session"
        self.calls.append({"url": url, "authenticated": authenticated})
        if url == BILIBILI_VIEW_API:
            return _FakeHttpResponse(
                {
                    "code": 0,
                    "data": {
                        "pages": [{"cid": 2001, "page": 1, "duration": 60, "part": "正片"}],
                    },
                }
            )
        if url == BILIBILI_PLAYURL_API:
            if self.play_requires_auth and not authenticated:
                return _FakeHttpResponse({"code": -101, "message": "账号未登录"})
            return _FakeHttpResponse(
                {
                    "code": 0,
                    "data": {
                        "dash": {
                            "video": [
                                {
                                    "width": 854,
                                    "height": 480,
                                    "codecs": "avc1.64001F",
                                    "baseUrl": "https://media.example/auth-fallback.m4s",
                                }
                            ],
                            "audio": [
                                {
                                    "bandwidth": 65000,
                                    "baseUrl": "https://media.example/auth-audio.m4s",
                                }
                            ],
                        }
                    },
                }
            )
        if url == BILIBILI_PLAYER_API:
            tracks = []
            if authenticated:
                tracks = [
                    {
                        "lan": "zh-CN",
                        "subtitle_url": "https://subtitle.example/auth-track.json",
                    }
                ]
            return _FakeHttpResponse(
                {"code": 0, "data": {"subtitle": {"subtitles": tracks}}}
            )
        if url == "https://subtitle.example/auth-track.json":
            _assert(authenticated, "登录字幕文件请求没有携带专用 Cookie")
            return _FakeHttpResponse(
                {"body": [{"from": 0.5, "to": 1.5, "content": "登录字幕"}]}
            )
        raise AssertionError(f"出现未预期的 HTTP 请求: {url}")


def _test_backend_source_adapter() -> None:
    canonical, bvid, page = canonical_bilibili_url(
        {"id": "bili:BV1xx411c7mD:p2", "source": "bilibili_embed"}
    )
    _assert(canonical.endswith("/BV1xx411c7mD?p=2"), "B 站地址没有规范化")
    _assert((bvid, page) == ("BV1xx411c7mD", 2), "BVID 或分 P 解析错误")

    http = _FakeBilibiliHttp()
    commands: list[list[str]] = []

    def _run(command: list[str], **kwargs):
        commands.append(command)
        _assert("shell" not in kwargs, "ffmpeg 不得通过 shell 执行")
        if "0:a:0" in command:
            return SimpleNamespace(returncode=0, stdout=_audio_bytes(), stderr=b"")
        stream_url = command[command.index("-i") + 1]
        if stream_url == "https://media.example/primary-avc.m4s":
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"primary unavailable")
        return SimpleNamespace(returncode=0, stdout=_jpeg_bytes(), stderr=b"")

    source = BilibiliApiAnalysisSource(
        command_runner=_run,
        http_get=http,
        ffmpeg_bin="/test/ffmpeg",
        max_workers=1,
    )
    samples = source.acquire(
        {
            "media": {
                "id": "bili:BV1xx411c7mD:p2",
                "source": "bilibili_embed",
                "duration_ms": 60_000,
            }
        },
        purpose="rolling",
        timestamps_ms=[1000, 5000],
    )
    _assert(
        [item["url"] for item in http.calls]
        == [BILIBILI_VIEW_API, BILIBILI_PLAYURL_API, BILIBILI_PLAYER_API, "https://subtitle.example/track.json"],
        "公开接口解析或字幕请求顺序错误",
    )
    frame_commands = [command for command in commands if "0:v:0" in command]
    audio_commands = [command for command in commands if "0:a:0" in command]
    _assert(len(frame_commands) == 4, "主流失败后没有为每个时间点切换备用流")
    _assert(len(audio_commands) == 1, "rolling 任务没有提取一段完整音频")
    _assert(all(command[0] == "/test/ffmpeg" for command in commands), "ffmpeg 路径错误")
    _assert(all("-ss" in command and "-frames:v" in command for command in frame_commands), "取帧参数不完整")
    _assert("-t" in audio_commands[0] and "-f" in audio_commands[0], "音频区间或输出格式参数不完整")
    _assert(audio_commands[0][audio_commands[0].index("-b:a") + 1] == "32k", "音频码率错误")
    _assert(audio_commands[0][audio_commands[0].index("-ar") + 1] == "16000", "音频采样率错误")
    _assert(
        all(command[command.index("-i") + 1] != "https://media.example/high-hevc.m4s" for command in commands),
        "没有优先选择上限内的 AVC 视频流",
    )
    header_blobs = [command[command.index("-headers") + 1] for command in commands]
    _assert(all(value.endswith("\r\n\r\n") for value in header_blobs), "ffmpeg 请求头缺少终止空行")
    _assert(all("Origin: https://www.bilibili.com" in value for value in header_blobs), "ffmpeg 请求头缺少 Origin")
    _assert(samples[0]["mime_type"] == "audio/mpeg", "完整音频没有放进滚动样本")
    _assert(samples[0]["at_ms"] == 1000, "完整音频没有从批次起点开始")
    _assert(
        samples[1]["subtitle"] == "测试字幕 第二句台词",
        "没有聚合当前画面到下一采样点之间的完整字幕",
    )
    _assert(samples[2]["subtitle"] == "", "无关字幕被错误附加")


def _test_authenticated_api_fallback() -> None:
    session = {
        "media": {
            "id": "bili:BV1xx411c7mD:p1",
            "source": "bilibili_embed",
            "duration_ms": 60_000,
        }
    }

    play_http = _FakeCookieFallbackHttp(play_requires_auth=True)
    play_commands: list[list[str]] = []

    def _play_run(command: list[str], **_kwargs):
        play_commands.append(command)
        return SimpleNamespace(returncode=0, stdout=_jpeg_bytes(), stderr=b"")

    play_source = BilibiliApiAnalysisSource(
        command_runner=_play_run,
        http_get=play_http,
        ffmpeg_bin="/test/ffmpeg",
        max_workers=1,
        cookie="SESSDATA=test-session",
    )
    play_source.acquire(session, purpose="rolling", timestamps_ms=[1000])
    play_calls = [item for item in play_http.calls if item["url"] == BILIBILI_PLAYURL_API]
    _assert(
        [item["authenticated"] for item in play_calls] == [False, True],
        "播放地址没有先公开请求、失败后再使用登录态",
    )
    play_header = play_commands[0][play_commands[0].index("-headers") + 1]
    _assert("Cookie: SESSDATA=test-session" in play_header, "受限视频取帧没有继承登录态")

    subtitle_http = _FakeCookieFallbackHttp(play_requires_auth=False)
    subtitle_commands: list[list[str]] = []

    def _subtitle_run(command: list[str], **_kwargs):
        subtitle_commands.append(command)
        return SimpleNamespace(returncode=0, stdout=_jpeg_bytes(), stderr=b"")

    subtitle_source = BilibiliApiAnalysisSource(
        command_runner=_subtitle_run,
        http_get=subtitle_http,
        ffmpeg_bin="/test/ffmpeg",
        max_workers=1,
        cookie="SESSDATA=test-session",
    )
    samples = subtitle_source.acquire(session, purpose="rolling", timestamps_ms=[1000])
    player_calls = [item for item in subtitle_http.calls if item["url"] == BILIBILI_PLAYER_API]
    _assert(
        [item["authenticated"] for item in player_calls] == [False, True],
        "公开字幕为空后没有使用登录态重试",
    )
    _assert(samples[0]["subtitle"] == "登录字幕", "登录态字幕没有进入样本")
    subtitle_header = subtitle_commands[0][subtitle_commands[0].index("-headers") + 1]
    _assert("Cookie:" not in subtitle_header, "公开片源取帧不应因字幕兜底携带 Cookie")


def _test_optional_subdl_subtitles() -> None:
    session = {
        "media": {
            "id": "bili:BV1xx411c7mD:p1",
            "source": "bilibili_embed",
            "title": "测试电影",
            "part_title": "2025 国语版",
            "duration_ms": 180_000,
            "content_start_ms": 60_000,
        }
    }
    bilibili_http = _FakeCookieFallbackHttp(play_requires_auth=False)
    subdl_calls: list[dict] = []

    def _subdl_get(url: str, **kwargs):
        subdl_calls.append({"url": url, **kwargs})
        if url == "https://api.subdl.com/api/v1/subtitles":
            params = kwargs.get("params") or {}
            _assert(params.get("year") == 2025, "SubDL 没有带上已知年份")
            _assert("languages" not in params, "SubDL 不应限定字幕语言")
            _assert(params.get("unpack") == 1, "SubDL 没有请求可直接解析的字幕文件")
            _assert(params.get("film_name") == "Test Movie", "SubDL 没有只使用作品原名查询")
            return _FakeHttpResponse(
                {
                    "status": True,
                    "results": [{"name": "Test Movie", "year": 2025, "type": "movie"}],
                    "subtitles": [
                        {
                            "release_name": "Test.Movie.2025.Bad",
                            "url": "/subtitle/sub-bad/file-bad",
                            "unpack_files": [
                                {
                                    "name": "Test.Movie.2025.bad.srt",
                                    "format": "srt",
                                    "language": "VI",
                                    "url": "/subtitle/sub-bad/file-bad",
                                }
                            ],
                        },
                        {
                            "release_name": "Test.Movie.2025",
                            "unpack_files": [
                                {
                                    "name": "Test.Movie.2025.vi.srt",
                                    "format": "srt",
                                    "language": "VI",
                                    "url": "/subtitle/sub-1/file-1",
                                }
                            ],
                        }
                    ],
                }
            )
        if url == "https://dl.subdl.com/subtitle/sub-bad/file-bad":
            return _FakeRawHttpResponse(b"", status_code=503)
        if url == "https://dl.subdl.com/subtitle/sub-1/file-1":
            return _FakeRawHttpResponse(
                b"1\n00:00:00,000 --> 00:00:01,500\nXin chao\n\n"
                b"2\n00:00:01,500 --> 00:00:03,000\nDi theo toi\n\n"
            )
        raise AssertionError(f"出现未预期的 SubDL 请求: {url}")

    def _run(_command: list[str], **_kwargs):
        return SimpleNamespace(returncode=0, stdout=_jpeg_bytes(), stderr=b"")

    source = BilibiliApiAnalysisSource(
        command_runner=_run,
        http_get=bilibili_http,
        ffmpeg_bin="/test/ffmpeg",
        max_workers=1,
        cookie="",
        subdl_api_key="test-subdl-key",
        subdl_get=_subdl_get,
    )
    prepared = source.prepare_subtitles(
        session,
        original_title="Test Movie",
        year=2025,
    )
    _assert(prepared["status"] == "found", "准备阶段没有保存 SubDL 字幕")
    _assert(prepared["query_title"] == "Test Movie", "准备结果没有保留实际查询原名")
    _assert(prepared["language_codes"] == ["VI"], "准备结果没有保留字幕语言")
    _assert(len(prepared["cues"]) == 2, "准备结果没有保留字幕条目")
    _assert(len(subdl_calls) == 3, "字幕候选没有按 URL 去重后依次尝试")
    _assert(
        all(call.get("timeout", 0) <= WATCH_SUBTITLE_REQUEST_TIMEOUT_SECONDS for call in subdl_calls),
        "字幕查询仍复用了视频取材的长超时",
    )
    session["media"].update(
        {
            "prepared_subtitle_cues": prepared["cues"],
            "prepared_subtitle_provider": prepared["provider"],
            "subtitle_cache_key": "prepared-test-asset",
        }
    )
    samples = source.acquire(
        session,
        purpose="identify",
        timestamps_ms=[60_500, 62_000],
    )
    _assert(len(subdl_calls) == 3, "滚动分析阶段重复请求了 SubDL")
    _assert(
        samples[0]["subtitle"] == "Xin chao Di theo toi",
        "外语字幕没有按人工正片起点偏移后进入样本",
    )
    _assert(samples[1]["subtitle"] == "Di theo toi", "外部字幕窗口与媒体时间没有对齐")


def _test_subtitle_provider_failure_is_visible_without_automatic_retry() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-subtitle-failure",
        window_id="sumitalk:subtitle-failure",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-subtitle-failure:p1",
            "source": "bilibili_embed",
            "title": "字幕失败测试",
            "duration_ms": 120_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": False},
    )
    session_id = session["session_id"]
    watch_runtime_store.update_analysis_state(
        session_id,
        {
            "status": "analyzing",
            "familiarity": "recognized",
            "identity": "字幕失败测试",
            "original_title": "Subtitle Failure Test",
            "year": 2026,
        },
    )
    schedule_knowledge_jobs(limit=1)
    scheduled = schedule_subtitle_jobs(limit=1)
    _assert(scheduled["jobs_created"] == 1, "认识作品后没有建立字幕任务")
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT max_attempts FROM watch_analysis_jobs WHERE session_id = ? AND purpose = 'subtitle_lookup'",
            (session_id,),
        ).fetchone()
    _assert(
        row is not None and int(row["max_attempts"] or 0) == WATCH_SUBTITLE_JOB_MAX_ATTEMPTS == 1,
        "字幕任务仍会在准备页背后自动重复慢请求",
    )
    outcome = process_next_job(source=_FailingSubtitlePreparationSource())
    _assert(outcome and outcome["status"] == "failed", "字幕 provider 失败后没有进入可见终态")
    failed = watch_runtime_store.get_session(session_id)
    _assert(
        failed["preparation"]["subtitle_lookup"]["status"] == "failed",
        "字幕 provider 失败仍停留在搜索态",
    )
    _assert(
        failed["preparation"]["subtitle_lookup"]["can_retry"],
        "字幕 provider 失败后没有保留显式重试入口",
    )
    watch_runtime_store.end_session(session_id)


def _test_knowledge_card_subtitle_identity() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-subtitle-titles",
        window_id="sumitalk:subtitle-titles",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-subtitle-titles:p1",
            "source": "bilibili_embed",
            "title": "中文片名",
            "duration_ms": 120_000,
        },
        mode={"knowledge_mode": "needs_summary"},
    )
    cache_key = watch_knowledge_store.cache_key_for_session(session)
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_knowledge_cards (
                cache_key, media_identity_json, card_json, sources_json, source_digest,
                model, prompt_version, confidence, created_at, updated_at, expires_at
            ) VALUES (?, '{}', ?, '[]', '', 'test', 'test', 1,
                      '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                      '2099-01-01T00:00:00Z')
            """,
            (
                cache_key,
                json.dumps(
                    {
                        "canonical_identity": {
                            "title": "中文片名",
                            "original_title": "Original Title",
                            "year": 2025,
                            "aliases": ["Alias Title", "中文片名"],
                        }
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    watch_runtime_store.update_preparation_state(
        session["session_id"],
        status="ready_to_confirm",
        knowledge_card_key=cache_key,
        knowledge_card_status="ready",
    )
    current = watch_runtime_store.get_session(session["session_id"])
    original_title, year = watch_subtitle_store.identity_for_session(current)
    _assert(original_title == "Original Title", "字幕准备没有使用知识卡原名")
    _assert(year == 2025, "字幕准备没有使用知识卡年份")
    enriched = _session_with_prepared_subtitles(current)
    _assert(enriched["media"]["prepared_subtitle_cues"] == [], "未准备字幕时伪造了字幕资产")
    watch_runtime_store.end_session(session["session_id"])


def _test_gateway_managed_source_flow() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-source",
        window_id="sumitalk:backend-source",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV1xx411c7mD:p1",
            "source": "bilibili_embed",
            "title": "后端取材测试",
            "part_title": "第一集",
            "duration_ms": 120_000,
        },
        mode={
            "knowledge_mode": "known",
            "fear_mode": False,
            "fear_action": "warn_only",
            "danmaku_enabled": True,
        },
    )
    session_id = session["session_id"]
    watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="skip",
        subtitle_lookup_id=_set_terminal_subtitle(session_id),
    )
    _updated, applied, _ignored = watch_runtime_store.update_playback(
        session_id,
        {
            "media_id": "bili:BV1xx411c7mD:p1",
            "playhead_ms": 15_000,
            "is_playing": False,
            "playback_rate": 1.0,
            "timeline_epoch": 1,
            "snapshot_seq": 1,
            "captured_at": "2026-07-18T09:59:00Z",
        },
    )
    _assert(applied, "锁定期间的暂停位置没有同步给后端取材")
    plan = watch_analysis_store.build_sample_plan(watch_runtime_store.get_session(session_id))
    _assert(plan["managed_by"] == "gateway", "分析计划没有标记由网关管理")
    _assert(plan["client_upload_required"] is False, "分析主链仍要求客户端截图")
    scheduled = schedule_source_jobs(limit=1)
    _assert(scheduled["jobs_created"] == 1, "worker 没有自动创建后端取材任务")
    runtime = watch_analysis_store.session_job_runtime(session_id)
    job = runtime["latest_job"]
    _assert(job["input_origin"] == "backend_source", "自动任务来源不是后端取材")
    _assert(job["planned_timestamps_ms"] == plan["target_timestamps_ms"], "计划时间点没有入队")

    source = _FakeBackendSource()
    outcome = process_next_job(
        source=source,
        post=_post_for(_raw_result(identity="后端取材测试 / 第一集")),
    )
    _assert(outcome and outcome["status"] == "done", "后端自动取材任务未完成")
    _assert(source.calls and source.calls[0]["media_id"] == "bili:BV1xx411c7mD:p1", "worker 取错媒体")
    finished = watch_analysis_store.get_job(job["job_id"], public=False)
    _assert(finished and finished["status"] == "done", "后端取材任务状态未落库")
    stored_samples = watch_analysis_store.load_job_samples(finished)
    _assert(stored_samples, "后端取材样本没有进入统一分析链")
    _assert(all(not item["file_path"] for item in stored_samples), "完成后仍保留后端截图文件")
    watch_runtime_store.end_session(session_id)


def _test_background_output_modes() -> None:
    job = {"purpose": "rolling", "range_start_ms": 10_000, "range_end_ms": 20_000}
    samples = [
        {"at_ms": 10_000, "mime_type": "text/plain", "text_content": "片段开始"},
        {"at_ms": 20_000, "mime_type": "text/plain", "text_content": "片段结束"},
    ]
    base_session = {
        "media": {"id": "local:test", "title": "测试作品", "duration_ms": 120_000},
        "analysis": {},
    }
    known_session = {**base_session, "mode": {"knowledge_mode": "known"}}
    summary_session = {**base_session, "mode": {"knowledge_mode": "needs_summary"}}

    known_request = build_watch_analysis_request(known_session, job, samples)
    summary_request = build_watch_analysis_request(summary_session, job, samples)
    known_system = known_request["messages"][0]["content"]
    summary_system = summary_request["messages"][0]["content"]
    _assert("【剧情背景输出模式：不产出】" in known_system, "known 模式没有使用不产出背景的 Gemini system 提示词")
    _assert("必须输出空字符串" in known_system, "known 模式没有明确禁止 Gemini 产出剧情背景")
    _assert("【剧情背景输出模式：产出】" in summary_system, "needs_summary 模式没有使用产出背景的 Gemini system 提示词")
    _assert("截至 through_ms" in summary_system, "needs_summary 模式没有限制剧情背景的时间边界")
    _assert(known_system != summary_system, "两种知识模式仍共用完全相同的 Gemini system 提示词")
    _assert("max_tokens" not in known_request, "一起看 Gemini 请求仍携带显式输出上限")

    known_prompt = known_request["messages"][1]["content"][0]["text"]
    summary_prompt = summary_request["messages"][1]["content"][0]["text"]
    known_context = json.loads(known_prompt.split("INPUT_CONTEXT=", 1)[1])
    summary_context = json.loads(summary_prompt.split("INPUT_CONTEXT=", 1)[1])
    _assert(
        known_context["previous_adjacent_plot_chunks"] == [],
        "没有相邻剧情时错误生成了跨批次上下文",
    )
    _assert(
        "previous_story_so_far" not in known_context and "previous_story_state" not in known_context,
        "known 模式仍把累计剧情或事件状态送回 Gemini",
    )
    _assert(
        "previous_story_so_far" not in summary_context and "previous_story_state" not in summary_context,
        "needs_summary 模式仍把累计剧情或事件状态送回 Gemini",
    )
    schema = known_request["response_format"]["json_schema"]["schema"]
    _assert("story_background" in schema["properties"], "解析 schema 缺少按模式产出的剧情背景")
    _assert("story_so_far" not in schema["properties"], "解析 schema 仍要求累计剧情")
    _assert("story_state" not in schema["properties"], "解析 schema 仍要求累计事件状态")

    raw = _raw_result(
        story_through_ms=20_000,
        story_summary="林夏继续探索旧宅。",
        story_background="林夏此前为了寻找失踪的同伴进入旧宅。",
    )
    known_result = normalize_watch_analysis_result(
        raw,
        session=known_session,
        job=job,
        samples=samples,
    )
    summary_result = normalize_watch_analysis_result(
        raw,
        session=summary_session,
        job=job,
        samples=samples,
    )
    _assert(known_result["story_background"]["background"] == "", "known 模式接受了模型违规返回的剧情背景")
    _assert(
        known_result["story_background"]["characters"] == [],
        "known 模式接受了模型违规返回的剧情人物背景",
    )
    _assert(
        summary_result["story_background"]["background"] == "林夏此前为了寻找失踪的同伴进入旧宅。",
        "needs_summary 模式丢失了 Gemini 生成的剧情背景",
    )


def _test_visual_frame_retention() -> None:
    session_id = "watch_visual_retention_test"
    epoch = 3
    playhead_ms = 1_000_000
    frame_dir = TEMP_DIR / "retention-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    def _add_frame(frame_id: str, frame_epoch: int, at_ms: int) -> Path:
        path = frame_dir / f"{frame_id}.webp"
        path.write_bytes(b"test-frame")
        watch_visual_store.upsert_frame(
            frame_id=frame_id,
            session_id=session_id,
            media_id="bili:retention",
            timeline_epoch=frame_epoch,
            at_ms=at_ms,
            file_path=str(path),
            width=64,
            height=36,
            sha256=frame_id,
            source_sample_id=frame_id,
        )
        return path

    old_epoch_path = _add_frame("old-epoch", 2, playhead_ms)
    too_old_path = _add_frame("too-old", epoch, 399_999)
    too_future_path = _add_frame("too-future", epoch, 1_300_001)
    in_window_paths = [
        _add_frame(f"in-window-{index}", epoch, 750_000 + index * 10_000)
        for index in range(52)
    ]
    pruned = watch_visual_store.prune_session_frames(
        session_id,
        timeline_epoch=epoch,
        playhead_ms=playhead_ms,
    )
    _assert(pruned["retained"] == 48, "派生帧没有按每会话上限裁剪")
    _assert(pruned["rows_deleted"] == 7, "窗口外、旧 epoch 和超量派生帧删除数量不正确")
    _assert(
        not old_epoch_path.exists() and not too_old_path.exists() and not too_future_path.exists(),
        "旧 epoch 或播放窗口外的派生图片仍留在磁盘",
    )
    retained = watch_visual_store.list_frames(
        session_id,
        timeline_epoch=epoch,
        through_ms=2_000_000,
        limit=100,
    )
    _assert(len(retained) == 48, "裁剪后的 SQLite 派生帧数量不正确")
    retained_paths = [Path(item["file_path"]) for item in retained]
    _assert(all(path.exists() for path in retained_paths), "裁剪误删了仍在窗口内的派生图片")
    removed = watch_visual_store.delete_session_frames(session_id)
    _assert(removed["rows_deleted"] == 48, "结束清理没有删除全部派生帧元数据")
    _assert(not any(path.exists() for path in in_window_paths), "结束清理后仍有派生图片文件残留")
    _assert(
        watch_visual_store.frame_cache_status(session_id, timeline_epoch=epoch)["count"] == 0,
        "结束清理后仍有派生帧 SQLite 记录",
    )


def _test_session_job_count_does_not_stop_long_media() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device-no-job-cap",
        window_id="sumitalk:no-job-cap",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-no-job-cap:p1",
            "source": "bilibili_embed",
            "title": "长片任务计数测试",
            "part_title": "第一集",
            "duration_ms": 1_000_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": False},
    )
    session_id = session["session_id"]
    for index in range(241):
        _job, created = watch_analysis_store.enqueue_source_plan(
            session=watch_runtime_store.get_session(session_id),
            plan={"purpose": "rolling", "target_timestamps_ms": [index * 1000]},
        )
        _assert(created, f"第 {index + 1} 个分析任务被错误拦截")
    watch_runtime_store.end_session(session_id)


def _test_rolling_prefetch_uses_full_batches_to_thirty_minutes() -> None:
    base_session = {
        "session_id": "watch_rolling_prefetch_test",
        "media": {
            "id": "bili:rolling-prefetch:p1",
            "source": "bilibili_embed",
            "duration_ms": 3_600_000,
            "content_start_ms": 0,
            "content_end_ms": 3_500_000,
        },
        "mode": {"knowledge_mode": "known"},
        "playback": {"playhead_ms": 0, "timeline_epoch": 0},
        "analysis": {"familiarity": "recognized", "covered_until_ms": 0},
        "preparation": {"started_at": "2026-07-20T16:00:00Z"},
        "ended_at": "",
    }
    first = watch_analysis_store.build_sample_plan(base_session)
    _assert(first["purpose"] == "rolling", "30 分钟预取没有开始首个滚动批次")
    _assert(first["target_until_ms"] == 1_800_000, "滚动预取目标不是最多领先 30 分钟")
    _assert(first["audio_range_end_ms"] == 140_000, "首个滚动任务没有使用完整 140 秒批次")

    waiting = watch_analysis_store.build_sample_plan(
        {
            **base_session,
            "analysis": {"familiarity": "recognized", "covered_until_ms": 1_680_000},
        }
    )
    _assert(waiting["purpose"] == "idle", "不足一个完整批次的播放头差值仍触发了模型请求")
    _assert(waiting["reason"] == "coverage_refill_wait", "滚动预取没有进入完整批次等待状态")

    refill = watch_analysis_store.build_sample_plan(
        {
            **base_session,
            "playback": {"playhead_ms": 20_000, "timeline_epoch": 0},
            "analysis": {"familiarity": "recognized", "covered_until_ms": 1_680_000},
        }
    )
    _assert(refill["purpose"] == "rolling", "领先量消耗一个完整批次后没有恢复预取")
    _assert(refill["audio_range_end_ms"] == 1_820_000, "恢复预取仍生成了不足 140 秒的追赶批次")

    final_chunk = watch_analysis_store.build_sample_plan(
        {
            **base_session,
            "media": {**base_session["media"], "content_end_ms": 1_800_000},
            "analysis": {"familiarity": "recognized", "covered_until_ms": 1_760_000},
        }
    )
    _assert(final_chunk["purpose"] == "rolling", "正片结尾前的最后一段没有收尾")
    _assert(final_chunk["audio_range_end_ms"] == 1_800_000, "最后一批越过了正常正片结尾")


def run() -> None:
    runtime_sqlite._SCHEMA_READY = False
    _assert("静态风景照" in ANALYSIS_SYSTEM_PROMPT, "时间轴预扫没有识别 Bilibili 静态垫片")
    _assert("片尾曲" in ANALYSIS_SYSTEM_PROMPT, "时间轴预扫没有把片尾曲作为正文结束信号")
    _assert("content_start_ms/content_end_ms" in ANALYSIS_SYSTEM_PROMPT, "人工正片边界没有进入分析约束")
    _assert("输入字幕无论使用哪种语言" in ANALYSIS_SYSTEM_PROMPT, "外语字幕没有被限制为中文剧情辅助材料")
    _assert("忽略冲突字幕" in ANALYSIS_SYSTEM_PROMPT, "字幕错位时没有要求以实际音画为准")
    _assert("它不是累计剧情" in ANALYSIS_SYSTEM_PROMPT, "剧情背景仍可能被当成累计剧情")
    _test_analysis_response_adapter()
    _test_session_analysis_cost_accumulates_retry_usage()
    _test_paid_usage_survives_end_race_and_is_idempotent()
    _test_seek_reuses_paid_coverage_without_reanalysis()
    _test_normal_mode_waits_for_five_minute_initial_coverage()
    _test_initial_fear_coverage_unlocks_playback()
    _test_background_output_modes()
    _test_visual_frame_retention()
    _test_session_job_count_does_not_stop_long_media()
    _test_rolling_prefetch_uses_full_batches_to_thirty_minutes()
    _test_backend_source_adapter()
    _test_authenticated_api_fallback()
    _test_optional_subdl_subtitles()
    _test_subtitle_provider_failure_is_visible_without_automatic_retry()
    _test_knowledge_card_subtitle_identity()
    _test_knowledge_source_and_timeline_gates()
    _test_knowledge_preparation_flow()
    _test_gateway_managed_source_flow()
    session = watch_runtime_store.create_session(
        device_id="test-device",
        window_id="sumitalk:phase2",
        companion={"id": "du", "name": "渡"},
        media={
            "id": "bili:BV-phase2:1",
            "source": "bilibili_embed",
            "title": "测试电影",
            "part_title": "第一集",
            "duration_ms": 180_000,
        },
        mode={
            "knowledge_mode": "needs_summary",
            "fear_mode": True,
            "fear_action": "cover_video",
            "danmaku_enabled": True,
        },
    )
    session_id = session["session_id"]
    started = watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="skip",
        subtitle_lookup_id=_set_terminal_subtitle(session_id),
    )
    _assert(
        watch_runtime_store.get_start_gate(started)["status"] == "buffering",
        "胆小模式初始保护未就绪时没有进入等待状态",
    )
    unlocked = watch_runtime_store.start_session(
        session_id,
        knowledge_card_action="",
        protection_action="continue_unprotected",
    )
    _assert(
        watch_runtime_store.get_start_gate(unlocked)["status"] == "unprotected",
        "明确无保护继续后没有解锁播放",
    )
    session, applied, _ignored = watch_runtime_store.update_playback(
        session_id,
        {
            "media_id": "bili:BV-phase2:1",
            "playhead_ms": 30_000,
            "is_playing": True,
            "playback_rate": 1.0,
            "timeline_epoch": 1,
            "snapshot_seq": 1,
            "captured_at": "2026-07-18T10:00:00Z",
        },
    )
    _assert(applied, "测试播放快照没有应用")

    _identify_job, identify_samples = _enqueue(session_id, "identify", [28_000, 30_000, 32_000])
    identify_paths = [Path(item["file_path"]) for item in identify_samples]
    in_flight_plan = watch_analysis_store.build_sample_plan(
        watch_runtime_store.get_session(session_id)
    )
    _assert(
        in_flight_plan["reason"] == "analysis_in_flight",
        "进行中的识别任务仍要求客户端重复上传样本",
    )
    captured_requests: list[dict] = []
    identify_outcome = process_next_job(
        post=_post_for(_raw_result(story_through_ms=32_000), captured_requests, cost="not-a-number")
    )
    _assert(identify_outcome and identify_outcome["status"] == "done", "作品识别任务未完成")
    request_json = captured_requests[0]["json"]
    _assert(request_json["reasoning"] == {"effort": "none"}, "视觉分析没有关闭 thinking")
    _assert(
        request_json["response_format"]["json_schema"]["strict"] is True,
        "视觉分析没有使用严格 JSON schema",
    )
    _assert(request_json["messages"][0]["role"] == "system", "视觉分析约束没有放在 system 消息")
    system_prompt = request_json["messages"][0]["content"]
    _assert("不要写成逐帧罗列动作的流水账" in system_prompt, "提示词没有禁止流水账式描述")
    _assert("神情、目光、姿态与身体变化" in system_prompt, "提示词没有要求描述角色神情")
    _assert("加入少量氛围和情绪渲染" in system_prompt, "提示词错误禁止了氛围和情绪表达")
    _assert("必须把‘谁说了什么’自然嵌入动作和神情" in system_prompt, "提示词没有要求台词归属")
    _assert("输入字幕无论使用哪种语言" in system_prompt, "提示词没有把外语字幕限制为剧情辅助材料")
    _assert("最终始终使用中文叙述" in system_prompt, "提示词没有固定剧情输出语言")
    _assert("主剧情中禁止写‘字幕显示’" in system_prompt, "提示词仍允许把台词写成字幕清单")
    _assert("清晰台词必须保留" in system_prompt, "提示词仍允许省略关键台词")
    _assert("称呼类台词必须保留原称呼" in system_prompt, "提示词仍允许概括掉人物称呼")
    _assert("写法接近克制的小说叙事" in system_prompt, "提示词没有要求连贯叙事")
    _assert("人物遇到的问题或目标" in system_prompt, "提示词没有要求先提炼剧情目标")
    _assert("必须把这些证据合成一个故事层面的事件" in system_prompt, "提示词没有要求跨帧提炼剧情事件")
    _assert("接受委托并完成了任务" in system_prompt, "提示词没有说明如何连接任务与结果")
    _assert("只按真实剧情单元切分，不按样本数量切分" in system_prompt, "提示词仍按截图数量硬切剧情")
    _assert("道具能力、计划目的、任务内容或规则" in system_prompt, "提示词没有要求说清关键剧情机制")
    _assert("previous_adjacent_plot_chunks 只用于接住批次边界" in system_prompt, "提示词没有限制跨批次上下文用途")
    _assert("未在 previous_adjacent_plot_chunks 中出现的新配角" in system_prompt, "提示词没有限制新配角的身份推断")
    _assert("description 和 characters 都必须先使用可见特征或泛称" in system_prompt, "提示词没有把新配角限制落实到输出字段")
    _assert("以当前对白为准" in system_prompt, "提示词没有处理称呼与候选关系冲突")
    _assert("输出前静默核对" in system_prompt, "提示词没有要求输出前校验关键约束")
    _assert("不得输出你自己的喜恶" in system_prompt, "提示词没有排除模型主观看法")
    _assert("不替角色编内心戏" in system_prompt, "提示词没有限制无依据的心理脑补")
    _assert("音频是对白、声音事件和剧情连续性的主要证据" in system_prompt, "提示词没有定义音频职责")
    _assert("截图里出现的人也不一定就是同时刻音频的说话者" in system_prompt, "提示词没有限制稀疏截图的台词归属")
    chunk_properties = request_json["response_format"]["json_schema"]["schema"]["properties"]["plot_chunks"]["items"]["properties"]
    _assert("核心剧情事件" in chunk_properties["description"]["description"], "schema 没有把主剧情要求落到 description 字段")
    _assert("visual_description" not in chunk_properties, "schema 仍要求重复输出视觉描述")
    _assert("dialogue_summary" not in chunk_properties, "schema 仍要求重复输出对白摘要")
    story_required = request_json["response_format"]["json_schema"]["schema"]["properties"]["story_background"]["required"]
    _assert("background" in story_required, "解析输出没有要求当前已知剧情背景")
    _assert("max_tokens" not in request_json, "视觉分析请求仍携带显式输出上限")
    _assert(request_json["messages"][1]["role"] == "user", "视觉样本没有作为 user 消息发送")
    _assert(
        all(item.get("type") != "input_audio" for item in request_json["messages"][1]["content"]),
        "identify 任务错误携带了音频",
    )
    _assert(all(not path.exists() for path in identify_paths), "已完成识别任务仍保留原始截图")
    identified = watch_runtime_store.get_session(session_id)
    _assert(identified["analysis"]["familiarity"] == "recognized", "识别熟悉度没有落库")
    _assert(identified["analysis"]["original_title"] == "Test Movie", "作品原名没有由 identify 落库")
    _assert(identified["analysis"]["year"] == 2025, "作品年份没有由 identify 落库")
    _assert(identified["analysis"]["story_so_far"] == {}, "identify 任务清空或写入了剧情摘要")
    batch_samples = _samples(identified, "rolling", [index * 1000 for index in range(8)])
    _assert(len(batch_samples) == 8, "单批 8 帧没有通过正式样本限制")
    purge_prepared_samples(batch_samples)
    try:
        _samples(identified, "rolling", [index * 1000 for index in range(9)])
    except WatchAnalysisSampleError as exc:
        _assert("图片数量超过限制" in str(exc), "超过 8 帧时返回了错误原因")
    else:
        raise AssertionError("单批超过 8 帧仍被接受")

    _enqueue(session_id, "timeline_prepass", [0, 10_000, 30_000, 150_000, 175_000])
    timeline_outcome = process_next_job(
        post=_post_for(
            _raw_result(
                sections=[
                    {"kind": "intro", "start_ms": 0, "end_ms": 30_000, "confidence": 0.94},
                    {"kind": "content", "start_ms": 30_000, "end_ms": 170_000, "confidence": 0.91},
                    {"kind": "preview", "start_ms": 170_000, "end_ms": 180_000, "confidence": 0.93},
                ],
                story_through_ms=175_000,
                story_summary="这个摘要不应由时间轴任务写入。",
            )
        )
    )
    _assert(timeline_outcome and timeline_outcome["status"] == "done", "时间轴预分析未完成")
    after_timeline = watch_runtime_store.get_session(session_id)
    _assert(after_timeline["analysis"]["story_so_far"] == {}, "时间轴任务覆盖了剧情摘要")
    rolling_plan = watch_analysis_store.build_sample_plan(after_timeline)
    _assert(rolling_plan["purpose"] == "rolling", "时间轴预扫后没有进入滚动分析")
    _assert(rolling_plan["suggested_interval_ms"] == 20_000, "已识别作品没有使用 20 秒采样间隔")
    _assert(
        int(watch_analysis_store.WATCH_ANALYSIS_UNKNOWN_INTERVAL_MS) == 20_000,
        "未知作品默认采样间隔不是 20 秒",
    )
    _assert(
        rolling_plan["target_timestamps_ms"] == [
            30_000,
            50_000,
            70_000,
            90_000,
            110_000,
            130_000,
            150_000,
            169_999,
        ],
        "滚动任务没有跨过片头并在预告前停止取材",
    )
    _assert(rolling_plan["audio_required"] is True, "滚动任务没有要求完整音频")
    _assert(
        (rolling_plan["audio_range_start_ms"], rolling_plan["audio_range_end_ms"])
        == (30_000, 169_999),
        "滚动任务音频范围没有排除片头和预告",
    )

    mixed_samples = prepare_samples(
        session_id=session_id,
        media_id=after_timeline["media"]["id"],
        timeline_epoch=after_timeline["playback"]["timeline_epoch"],
        duration_ms=after_timeline["media"]["duration_ms"],
        purpose="rolling",
        raw_samples=[
            {
                "at_ms": 0,
                "mime_type": "audio/mpeg",
                "audio_bytes": _audio_bytes(),
                "text_content": "完整音频覆盖 0ms 至 140000ms",
            },
            *[
                {
                    "at_ms": at_ms,
                    "mime_type": "image/jpeg",
                    "image_bytes": _jpeg_bytes((60 + index, 82, 118)),
                }
                for index, at_ms in enumerate(rolling_plan["target_timestamps_ms"])
            ],
        ],
    )
    mixed_request = build_watch_analysis_request(
        after_timeline,
        {
            "purpose": "rolling",
            "range_start_ms": 0,
            "range_end_ms": 140_000,
        },
        mixed_samples,
    )
    mixed_content = mixed_request["messages"][1]["content"]
    mixed_paths = [Path(item["file_path"]) for item in mixed_samples]
    _assert(
        sum(item.get("type") == "input_audio" for item in mixed_content) == 1,
        "滚动请求没有且仅有一段 input_audio",
    )
    audio_part = next(item for item in mixed_content if item.get("type") == "input_audio")
    _assert(audio_part["input_audio"]["format"] == "mp3", "滚动请求音频格式不是 MP3")
    _assert(
        sum(item.get("type") == "image_url" for item in mixed_content) == 8,
        "滚动请求没有且仅有 8 张图片",
    )
    _assert(
        mixed_request["model"] == "google/gemini-2.5-flash",
        "滚动剧情没有使用确认后的 Gemini 2.5 Flash",
    )
    _assert(
        any(
            item.get("type") == "text" and "完整音频覆盖绝对媒体时间 0ms 至 140000ms" in item.get("text", "")
            for item in mixed_content
        ),
        "混合请求没有声明音频绝对媒体时间",
    )
    purge_prepared_samples(mixed_samples)
    _assert(all(not path.exists() for path in mixed_paths), "混合任务清理后仍保留 MP3 或截图")

    _enqueue(session_id, "rolling", [10_000, 30_000, 40_000])
    first_rolling = process_next_job(
        post=_post_for(
            _raw_result(
                chunks=[
                    {
                        "start_ms": 10_000,
                        "end_ms": 20_000,
                        "description": "片头中的旧宅画面。",
                        "visual_description": "片头蒙太奇。",
                        "dialogue_summary": "无。",
                        "characters": [],
                        "tags": ["片头"],
                        "confidence": 0.92,
                    },
                    {
                        "start_ms": 30_000,
                        "end_ms": 40_000,
                        "description": "林夏走进旧宅。",
                        "visual_description": "她推开木门。",
                        "dialogue_summary": "她喊了一声有人吗。",
                        "characters": ["林夏"],
                        "tags": ["调查"],
                        "confidence": 0.9,
                    },
                ],
                story_through_ms=40_000,
                story_summary="林夏刚走进旧宅。",
            )
        )
    )
    _assert(first_rolling and first_rolling["status"] == "done", "第一段剧情分析未完成")

    _enqueue(session_id, "rolling", [60_000, 100_000, 175_000])
    second_rolling_requests: list[dict] = []
    second_rolling = process_next_job(
        post=_post_for(
            _raw_result(
                chunks=[
                    {
                        "start_ms": 60_000,
                        "end_ms": 100_000,
                        "description": "林夏沿走廊寻找声音来源。",
                        "visual_description": "手电扫过墙面。",
                        "dialogue_summary": "她听见门后有响动。",
                        "characters": ["林夏"],
                        "tags": ["走廊"],
                        "confidence": 0.91,
                    },
                    {
                        "start_ms": 171_000,
                        "end_ms": 175_000,
                        "description": "下集预告画面。",
                        "visual_description": "快速剪辑。",
                        "dialogue_summary": "预告旁白。",
                        "characters": ["林夏"],
                        "tags": ["预告"],
                        "confidence": 0.95,
                    },
                ],
                story_through_ms=175_000,
                story_summary="林夏进入旧宅，并沿走廊寻找门后的声音。",
                risks=[
                    {
                        "risk_type": "jumpscare",
                        "severity": 2,
                        "start_ms": 80_000,
                        "end_ms": 82_000,
                        "confidence": 0.9,
                        "spoiler_free_hint": "前方有一次突然惊吓。",
                    },
                    {
                        "risk_type": "loud_noise",
                        "severity": 2,
                        "start_ms": 172_000,
                        "end_ms": 174_000,
                        "confidence": 0.95,
                        "spoiler_free_hint": "预告中有突然声响。",
                    },
                    {
                        "risk_type": "other",
                        "severity": 1,
                        "start_ms": 90_000,
                        "end_ms": 91_000,
                        "confidence": 0.4,
                        "spoiler_free_hint": "低置信度事件。",
                    },
                ],
            ),
            second_rolling_requests,
        )
    )
    _assert(second_rolling and second_rolling["status"] == "done", "第二段剧情分析未完成")
    second_request = second_rolling_requests[0]["json"]
    second_context = json.loads(
        second_request["messages"][1]["content"][0]["text"].split("INPUT_CONTEXT=", 1)[1]
    )
    _assert("max_tokens" not in second_request, "第二批 Gemini 请求仍携带显式输出上限")
    _assert(
        any(
            item.get("description") == "林夏走进旧宅。"
            for item in second_context["previous_adjacent_plot_chunks"]
        ),
        "第二批没有收到上一批边界附近的已解析剧情",
    )
    _assert(
        "previous_story_so_far" not in second_context and "previous_story_state" not in second_context,
        "第二批仍收到累计剧情或事件状态",
    )

    visual_status = watch_visual_store.frame_cache_status(session_id, timeline_epoch=1)
    _assert(visual_status["count"] >= 5, "滚动分析完成后没有生成派生帧缓存")
    cached_visual_frames = watch_visual_store.list_frames(
        session_id,
        timeline_epoch=1,
        through_ms=180_000,
    )
    visual_paths = [Path(item["file_path"]) for item in cached_visual_frames]
    _assert(visual_paths and all(path.exists() for path in visual_paths), "派生 WebP 文件没有落到本地缓存")

    completed = watch_runtime_store.get_session(session_id)
    _assert(completed["analysis"]["status"] == "ready", "高能前向覆盖完成后状态不是 ready")
    chunks = watch_runtime_store.get_plot_chunks(
        session_id,
        timeline_epoch=1,
        start_before_ms=180_000,
        end_after_ms=0,
        limit=20,
    )
    summaries = [item["summary"] for item in chunks]
    _assert("林夏走进旧宅。" in summaries, "有效剧情片段没有落库")
    _assert("片头中的旧宅画面。" not in summaries, "片头内容被写入剧情片段")
    _assert("下集预告画面。" not in summaries, "预告内容被写入剧情片段")
    risks = watch_runtime_store.get_risk_events(
        session_id,
        timeline_epoch=1,
        from_ms=0,
        until_ms=180_000,
        limit=20,
    )
    _assert(len(risks) == 1 and risks[0]["start_ms"] == 80_000, "高能过滤结果不正确")
    _assert(risks[0]["warn_at_ms"] == 73_000, "跳吓预警提前量不正确")

    built = build_watch_context(
        session_id=session_id,
        snapshot={
            "media_id": "bili:BV-phase2:1",
            "playhead_ms": 50_000,
            "is_playing": True,
            "playback_rate": 1.0,
            "timeline_epoch": 1,
            "snapshot_seq": 2,
            "captured_at": "2026-07-18T10:00:20Z",
        },
        window_id="sumitalk:phase2",
    )
    _assert(built is not None, "剧情检查点上下文没有构建")
    prompt, _action_context = built
    _assert("林夏刚走进旧宅。" in prompt, "没有选中播放点之前最近的剧情检查点")
    _assert("并沿走廊寻找" not in prompt, "播放点之后的累计摘要泄漏到可见上下文")
    _assert("visual_description" not in prompt, "动态上下文仍重复注入视觉描述")
    _assert("dialogue_summary" not in prompt, "动态上下文仍重复注入对白摘要")

    correction_job, correction_samples = _enqueue(session_id, "rolling", [110_000, 120_000])
    correction_paths = [Path(item["file_path"]) for item in correction_samples]
    analysis_before_correction = watch_runtime_store.get_session(session_id)["analysis"]
    watch_runtime_store.replace_timeline_sections(
        session_id,
        [
            {"kind": "intro", "start_ms": 0, "end_ms": 30_000},
            {"kind": "content", "start_ms": 30_000, "end_ms": 170_000},
            {"kind": "preview", "start_ms": 170_000, "end_ms": 180_000},
        ],
        timeline_epoch=1,
    )
    corrected = watch_runtime_store.get_session(session_id)
    _assert(
        corrected["analysis"]["status"] == analysis_before_correction["status"],
        "人工参考范围不应改变分析状态或凭空解锁",
    )
    _assert(
        corrected["analysis"]["covered_until_ms"]
        == analysis_before_correction["covered_until_ms"],
        "人工参考范围不应清空或凭空推进已付费覆盖",
    )
    _assert(
        watch_analysis_store.get_job(correction_job["job_id"])["status"] == "cancelled",
        "人工边界纠正没有取消进行中的分析任务",
    )
    _assert(all(not path.exists() for path in correction_paths), "人工边界纠正没有删除待分析截图")
    _assert(
        watch_runtime_store.get_plot_chunks(
            session_id,
            timeline_epoch=1,
            start_before_ms=180_000,
            end_after_ms=0,
            limit=20,
        ),
        "人工参考范围错误清除了已付费剧情片段",
    )
    _assert(
        watch_runtime_store.get_risk_events(
            session_id,
            timeline_epoch=1,
            from_ms=0,
            until_ms=180_000,
            limit=20,
        ),
        "人工参考范围错误清除了已付费高能事件",
    )

    _enqueue(session_id, "rolling", [120_000, 130_000])
    claimed = watch_analysis_store.claim_next_job(stale_after_seconds=300)
    _assert(claimed is not None, "stale epoch 测试任务没有领取")
    claimed_samples = watch_analysis_store.load_job_samples(claimed)
    _updated, applied, _ignored = watch_runtime_store.update_playback(
        session_id,
        {
            "media_id": "bili:BV-phase2:1",
            "playhead_ms": 130_000,
            "is_playing": True,
            "playback_rate": 1.0,
            "timeline_epoch": 2,
            "snapshot_seq": 1,
            "captured_at": "2026-07-18T10:02:00Z",
        },
    )
    _assert(applied, "stale epoch 测试没有切换时间轴")
    watch_analysis_store.reset_for_epoch(session_id, timeline_epoch=2)
    stale_commit = watch_analysis_store.commit_analysis_result(
        claimed,
        result={
            "plot_chunks": [
                {
                    "start_ms": 120_000,
                    "end_ms": 130_000,
                    "summary": "这段旧结果不应落库。",
                    "visual_description": "",
                    "dialogue_summary": "",
                    "characters": [],
                    "tags": [],
                    "confidence": 1.0,
                }
            ],
            "timeline_sections": [],
            "story_background": {},
            "risk_events": [],
            "analysis_version": "stale-test",
        },
        usage={"cost_usd": 0},
        samples=claimed_samples,
    )
    _assert(stale_commit == {"applied": False, "reason": "stale_timeline"}, "旧 epoch 结果没有拒绝")
    watch_analysis_store.purge_job_samples(claimed)
    stale_chunks = watch_runtime_store.get_plot_chunks(
        session_id,
        timeline_epoch=2,
        start_before_ms=180_000,
        end_after_ms=0,
        limit=20,
    )
    _assert(not stale_chunks, "旧 epoch 分析结果写进了新时间轴")
    epoch_plan = watch_analysis_store.build_sample_plan(watch_runtime_store.get_session(session_id))
    epoch_session = watch_runtime_store.get_session(session_id)
    _assert(
        epoch_session["analysis"]["covered_until_ms"] == 175_000,
        "seek 后没有复用人工参考范围内的已付费剧情覆盖",
    )
    _assert(
        epoch_plan["purpose"] == "idle",
        "seek 后仍准备重复分析已付费剧情范围",
    )

    _retry_job, retry_samples = _enqueue(session_id, "rolling", [130_000, 140_000])
    retry_paths = [Path(item["file_path"]) for item in retry_samples]
    retry_outcome = process_next_job(post=_failing_post)
    _assert(retry_outcome and retry_outcome["status"] == "queued", "503 没有进入重试队列")
    _assert(all(path.exists() for path in retry_paths), "可重试任务提前删除了样本")
    _assert(watch_analysis_store.daily_cost_usd() > 0, "成功任务费用没有累计")
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
            (session_id,),
        )
    _assert(watch_runtime_store.cleanup_expired_sessions() == 1, "过期观看会话没有清理")
    _assert(all(not path.exists() for path in retry_paths), "会话过期后原始截图仍留在磁盘")
    _assert(all(not path.exists() for path in visual_paths), "会话过期后派生剧情帧仍留在磁盘")
    _assert(
        watch_analysis_store.get_job(_retry_job["job_id"]) is None,
        "会话过期后分析任务仍留在运行库",
    )


if __name__ == "__main__":
    try:
        run()
        print("watch analysis phase2 tests passed")
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
