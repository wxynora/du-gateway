#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from base64 import b64encode
from datetime import datetime
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEMP_DIR = Path(tempfile.mkdtemp(prefix="watch-together-test-"))
os.environ["RUNTIME_STATE_DB"] = str(TEMP_DIR / "runtime.sqlite3")
os.environ["WATCH_CONTEXT_REPLY_LEAD_MS"] = "30000"

from flask import Blueprint, Flask  # noqa: E402
from PIL import Image  # noqa: E402

from routes.miniapp.watch import register_routes  # noqa: E402
from services.pc_command_handler import PcmdDuThoughtStreamState  # noqa: E402
from services.watch_action_flow import (  # noqa: E402
    build_watch_danmaku_event,
    split_watch_actions,
)
from services.watch_context import inject_watch_context  # noqa: E402
from storage import (  # noqa: E402
    runtime_sqlite,
    watch_analysis_store,
    watch_knowledge_store,
    watch_runtime_store,
    watch_visual_store,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _json(response) -> dict:
    payload = response.get_json(silent=True)
    _assert(isinstance(payload, dict), f"响应不是 JSON 对象: {response.data!r}")
    return payload


def _set_terminal_subtitle(session_id: str, status: str = "not_configured") -> str:
    lookup_id = f"test-subtitle-{session_id}"
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET subtitle_lookup_json = ? WHERE id = ?",
            (
                runtime_sqlite.json_dumps(
                    {
                        "lookup_id": lookup_id,
                        "status": status,
                        "provider": "subdl",
                        "message": "测试终态",
                        "can_retry": status != "found",
                    }
                ),
                session_id,
            ),
        )
    return lookup_id


def _create_client():
    app = Flask(__name__)
    bp = Blueprint("watch_test", __name__, url_prefix="/miniapp-api")
    register_routes(bp)
    app.register_blueprint(bp)
    return app.test_client()


def run() -> None:
    runtime_sqlite._SCHEMA_READY = False
    client = _create_client()

    incomplete = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:test-window",
            "media": {
                "id": "bili:BV-test:1",
                "source": "bilibili_embed",
                "title": "测试电影",
                "duration_ms": 7_200_000,
            },
        },
    )
    _assert(incomplete.status_code == 400, "创建会话必须要求前端显式选择模式")

    invalid_bounds = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:invalid-bounds",
            "media": {
                "id": "bili:BV-invalid-bounds:1",
                "source": "bilibili_embed",
                "title": "边界错误测试",
                "duration_ms": 7_200_000,
                "content_start_ms": 3_600_000,
                "content_end_ms": 3_600_000,
            },
            "mode": {"knowledge_mode": "known", "fear_mode": False},
        },
    )
    _assert(invalid_bounds.status_code == 400, "正片起止相同时仍能创建会话")

    bounded_response = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:manual-bounds",
            "media": {
                "id": "bili:BV-manual-bounds:1",
                "source": "bilibili_embed",
                "title": "人工边界测试电影",
                "duration_ms": 10_800_000,
                "content_start_ms": 3_600_000,
                "content_end_ms": 9_600_000,
            },
            "mode": {"knowledge_mode": "known", "fear_mode": False},
        },
    )
    _assert(bounded_response.status_code == 201, "带人工正片边界的会话创建失败")
    bounded = _json(bounded_response)["session"]
    bounded_id = bounded["session_id"]
    _assert(bounded["media"]["content_start_ms"] == 3_600_000, "人工正片开始没有保存")
    _assert(bounded["media"]["content_end_ms"] == 9_600_000, "人工正片结束没有保存")
    bounded_sections = watch_runtime_store.get_timeline_sections(bounded_id, timeline_epoch=0)
    _assert(
        [(item["kind"], item["start_ms"], item["end_ms"], item["source"]) for item in bounded_sections]
        == [
            ("non_story", 0, 3_600_000, "manual"),
            ("outro", 9_600_000, 10_800_000, "manual"),
        ],
        "人工正片边界没有生成最高优先级时间轴片段",
    )
    bounded_identify = watch_analysis_store.build_sample_plan(
        watch_runtime_store.get_session(bounded_id)
    )
    _assert(
        bounded_identify["target_timestamps_ms"]
        == [3_598_000, 3_600_000, 3_602_000],
        "人工正片开始没有让作品识别避开 Bilibili 前置垫片",
    )
    watch_runtime_store.update_analysis_state(
        bounded_id,
        {"status": "analyzing", "familiarity": "recognized", "identity": "人工边界测试电影"},
    )
    bounded_plan = watch_analysis_store.build_sample_plan(
        watch_runtime_store.get_session(bounded_id)
    )
    _assert(
        bounded_plan["reason"] == "waiting_for_start_confirmation",
        "人工起止边界齐全时仍创建片头片尾预扫",
    )
    watch_runtime_store.update_preparation_state(
        bounded_id,
        status="ready_to_confirm",
        knowledge_card_status="not_required",
    )
    watch_runtime_store.start_session(
        bounded_id,
        knowledge_card_action="confirm",
        subtitle_lookup_id=_set_terminal_subtitle(bounded_id),
    )
    watch_runtime_store.update_playback(
        bounded_id,
        {
            "media_id": "bili:BV-manual-bounds:1",
            "playhead_ms": 4_000_000,
            "duration_ms": 10_800_000,
            "is_playing": False,
            "playback_rate": 1.0,
            "timeline_epoch": 1,
            "snapshot_seq": 1,
        },
    )
    _assert(
        len(watch_runtime_store.get_timeline_sections(bounded_id, timeline_epoch=1)) == 2,
        "seek 后人工正片边界没有复制到新 epoch",
    )
    bounded_rolling = watch_analysis_store.build_sample_plan(
        watch_runtime_store.get_session(bounded_id)
    )
    _assert(bounded_rolling["purpose"] == "rolling", "人工边界会话没有进入滚动剧情分析")
    _assert(
        min(bounded_rolling["target_timestamps_ms"]) >= 3_600_000
        and max(bounded_rolling["target_timestamps_ms"]) <= 9_600_000,
        "滚动剧情分析越过了人工正片起止边界",
    )
    watch_runtime_store.end_session(bounded_id)

    partial_bounds_response = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:partial-bounds",
            "media": {
                "id": "bili:BV-partial-bounds:1",
                "source": "bilibili_embed",
                "title": "仅填写正片开始",
                "duration_ms": 10_800_000,
                "content_start_ms": 3_600_000,
            },
            "mode": {"knowledge_mode": "known", "fear_mode": False},
        },
    )
    partial = _json(partial_bounds_response)["session"]
    watch_runtime_store.update_analysis_state(
        partial["session_id"],
        {"status": "analyzing", "familiarity": "recognized", "identity": "仅填写正片开始"},
    )
    partial_plan = watch_analysis_store.build_sample_plan(
        watch_runtime_store.get_session(partial["session_id"])
    )
    _assert(partial_plan["purpose"] == "timeline_prepass", "只填一侧时没有扫描缺失边界")
    _assert(partial_plan["manual_content_start_ms"] == 3_600_000, "预扫计划没有携带人工开始边界")
    _assert(
        min(partial_plan["target_timestamps_ms"]) >= 7_200_000,
        "已填写正片开始后仍浪费取样扫描投稿前半段",
    )
    _assert(
        max(partial_plan["target_timestamps_ms"]) == 10_800_000,
        "缺失片尾时预扫没有覆盖媒体文件末尾",
    )
    watch_runtime_store.end_session(partial["session_id"])

    forced_response = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:force-unknown",
            "media": {
                "id": "bili:BV-force:1",
                "source": "bilibili_embed",
                "title": "降级测试电影",
                "duration_ms": 600_000,
            },
            "mode": {"knowledge_mode": "known", "fear_mode": False},
        },
    )
    forced_session = _json(forced_response)["session"]
    forced_session_id = forced_session["session_id"]
    watch_runtime_store.update_analysis_state(
        forced_session_id,
        {"status": "analyzing", "familiarity": "recognized", "identity": "降级测试电影"},
    )
    watch_runtime_store.update_preparation_state(
        forced_session_id,
        status="ready_to_confirm",
        knowledge_card_status="not_required",
    )
    forced_mode_response = client.put(
        f"/miniapp-api/watch/sessions/{forced_session_id}/mode",
        json={"mode": {"force_unknown_analysis": True}},
    )
    _assert(forced_mode_response.status_code == 200, "开播前不能手动降级识图模型")
    forced_session = _json(forced_mode_response)["session"]
    _assert(forced_session["analysis"]["familiarity"] == "unknown", "手动降级没有改写分析熟悉度")
    _assert(forced_session["mode"]["knowledge_mode"] == "needs_summary", "手动降级没有开启剧情背景")
    _assert(forced_session["preparation"]["knowledge_card_status"] == "pending", "手动降级没有重置知识卡准备")
    forced_job, forced_created = watch_knowledge_store.ensure_knowledge_job(forced_session)
    _assert(forced_created and forced_job["purpose"] == "knowledge_card", "手动降级没有创建知识卡任务")
    upgrade_response = client.put(
        f"/miniapp-api/watch/sessions/{forced_session_id}/mode",
        json={"mode": {"force_unknown_analysis": False}},
    )
    _assert(upgrade_response.status_code == 400, "手动降级后仍能直接伪造升级")
    watch_analysis_store.mark_job_cancelled(forced_job["job_id"], reason="test_complete")
    watch_runtime_store.end_session(forced_session_id)

    retry_response = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:subtitle-retry",
            "media": {
                "id": "bili:BV-subtitle-retry:1",
                "source": "bilibili_embed",
                "title": "字幕重试测试",
                "duration_ms": 600_000,
            },
            "mode": {"knowledge_mode": "known", "fear_mode": False},
        },
    )
    retry_session = _json(retry_response)["session"]
    retry_session_id = retry_session["session_id"]
    watch_runtime_store.update_analysis_state(
        retry_session_id,
        {
            "status": "analyzing",
            "familiarity": "recognized",
            "identity": "字幕重试测试",
            "original_title": "Subtitle Retry Test",
            "year": 2026,
        },
    )
    watch_runtime_store.update_preparation_state(
        retry_session_id,
        status="ready_to_confirm",
        knowledge_card_status="not_required",
    )
    old_lookup_id = _set_terminal_subtitle(retry_session_id, status="not_found")
    retry_lookup_response = client.post(
        f"/miniapp-api/watch/sessions/{retry_session_id}/subtitles/retry",
        json={},
    )
    _assert(retry_lookup_response.status_code == 202, "字幕重试接口没有重新排队")
    retry_state = watch_runtime_store.get_session(retry_session_id)
    _assert(retry_state["preparation"]["subtitle_lookup"]["status"] == "searching", "字幕重试没有进入搜索态")
    _assert(
        retry_state["preparation"]["subtitle_lookup"]["lookup_id"] != old_lookup_id,
        "字幕重试没有生成新的确认版本",
    )
    retry_job = _json(retry_lookup_response)["job"]
    watch_analysis_store.mark_job_cancelled(retry_job["job_id"], reason="test_complete")
    watch_runtime_store.end_session(retry_session_id)

    created_response = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:test-window",
            "companion": {"id": "du", "name": "渡"},
            "media": {
                "id": "bili:BV-test:1",
                "source": "bilibili_embed",
                "url": "https://player.bilibili.com/player.html?bvid=BV-test",
                "title": "测试电影",
                "part_title": "第一集",
                "duration_ms": 7_200_000,
            },
            "mode": {
                "knowledge_mode": "known",
                "fear_mode": True,
                "fear_action": "cover_video",
                "reduce_volume": False,
                "danmaku_enabled": True,
            },
        },
    )
    _assert(created_response.status_code == 201, "创建观看会话失败")
    session = _json(created_response)["session"]
    session_id = session["session_id"]
    _assert(session["mode"]["knowledge_mode"] == "known", "知识模式未保存")
    _assert(session["mode"]["reply_lead_ms"] == 30_000, "回复延迟默认值未保存")
    _assert(session["preparation"]["status"] == "identifying", "新会话不是准备态")
    created_at = datetime.fromisoformat(session["created_at"].replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
    _assert((expires_at - created_at).total_seconds() == 86_400, "一起看会话缓存 TTL 不是 24 小时")
    watch_runtime_store.update_preparation_state(
        session_id,
        status="ready_to_confirm",
        knowledge_card_key="expired-or-missing-card",
        knowledge_card_status="ready",
    )
    missing_card_status = _json(
        client.get(f"/miniapp-api/watch/sessions/{session_id}/status")
    )
    _assert(not missing_card_status["preparation"]["can_confirm"], "知识卡本体不可用时仍允许确认")
    watch_runtime_store.update_preparation_state(
        session_id,
        status="ready_to_confirm",
        knowledge_card_key="",
        knowledge_card_status="not_required",
    )
    pending_subtitle_status = _json(
        client.get(f"/miniapp-api/watch/sessions/{session_id}/status")
    )
    _assert(
        not pending_subtitle_status["preparation"]["can_confirm"],
        "字幕还未进入可见终态时仍允许确认开播",
    )

    blocked_snapshot = {
        "media_id": "bili:BV-test:1",
        "playhead_ms": 60_000,
        "duration_ms": 7_200_000,
        "is_playing": True,
        "playback_rate": 1.0,
        "timeline_epoch": 1,
        "snapshot_seq": 1,
        "captured_at": "2026-07-18T10:00:00Z",
    }
    blocked_playback = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/playback",
        json=blocked_snapshot,
    )
    _assert(blocked_playback.status_code == 400, "未确认准备资料就开始播放")
    watch_runtime_store.update_preparation_state(
        session_id,
        status="ready_to_confirm",
        knowledge_card_status="not_required",
    )
    lookup_id = _set_terminal_subtitle(session_id)
    ready_status = _json(client.get(f"/miniapp-api/watch/sessions/{session_id}/status"))
    _assert(ready_status["preparation"]["can_confirm"], "字幕终态后仍不能确认开播")
    stale_start = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/start",
        json={
            "knowledge_card_action": "confirm",
            "subtitle_lookup_id": "stale-subtitle-result",
        },
    )
    _assert(stale_start.status_code == 400, "过期字幕准备版本仍能确认开播")
    started_response = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/start",
        json={
            "knowledge_card_action": "confirm",
            "subtitle_lookup_id": lookup_id,
        },
    )
    _assert(started_response.status_code == 200, "确认准备资料后没有正式开始")
    started_payload = _json(started_response)
    _assert(started_payload["session"]["preparation"]["started_at"], "正式开始时间未保存")
    _assert(started_payload["start_gate"]["status"] == "buffering", "胆小模式没有先进入保护缓冲")
    _assert(not started_payload["start_gate"]["can_play"], "保护未就绪时错误解锁了播放器")
    regenerate_after_start = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/knowledge-card/regenerate",
        json={},
    )
    _assert(regenerate_after_start.status_code == 409, "正式开播后仍能重新生成开播前知识卡")

    snapshot = blocked_snapshot
    protected_block = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/playback",
        json=snapshot,
    )
    _assert(protected_block.status_code == 400, "胆小模式保护未就绪时仍允许播放")
    explicit_unprotected = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/start",
        json={"protection_action": "continue_unprotected"},
    )
    _assert(explicit_unprotected.status_code == 200, "明确无保护继续后没有解锁")
    unprotected_gate = _json(explicit_unprotected)["start_gate"]
    _assert(unprotected_gate["status"] == "unprotected", "没有记录显式无保护继续")
    _assert(unprotected_gate["can_play"], "显式无保护继续后播放器仍被锁住")
    playback = _json(
        client.put(f"/miniapp-api/watch/sessions/{session_id}/playback", json=snapshot)
    )
    _assert(playback["applied"] is True, "新播放快照没有应用")

    stale = dict(snapshot)
    stale["playhead_ms"] = 5_000
    stale_response = _json(
        client.put(f"/miniapp-api/watch/sessions/{session_id}/playback", json=stale)
    )
    _assert(stale_response["applied"] is False, "同 epoch 的旧 seq 覆盖了新进度")
    _assert(
        stale_response["session"]["playback"]["playhead_ms"] == 60_000,
        "旧播放快照改写了 playhead",
    )

    status_before_samples = _json(client.get(f"/miniapp-api/watch/sessions/{session_id}/status"))
    _assert(status_before_samples["sample_plan"]["purpose"] == "identify", "初始采样计划不是作品识别")
    image_buffer = BytesIO()
    Image.new("RGB", (32, 18), color=(30, 80, 120)).save(image_buffer, format="PNG")
    sample_payload = {
        "purpose": "identify",
        "timeline_epoch": 1,
        "idempotency_key": "watch-test-identify-1",
        "samples": [
            {
                "at_ms": 58_000,
                "mime_type": "image/png",
                "image_base64": b64encode(image_buffer.getvalue()).decode("ascii"),
                "subtitle": "你听见了吗？",
                "captured_at": "2026-07-18T10:00:00Z",
            }
        ],
    }
    queued_response = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/analysis/samples",
        json=sample_payload,
    )
    _assert(queued_response.status_code == 202, "分析样本没有进入队列")
    queued_job = _json(queued_response)["job"]
    _assert(queued_job["status"] == "queued", "新分析任务状态不是 queued")
    duplicate_response = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/analysis/samples",
        json=sample_payload,
    )
    _assert(duplicate_response.status_code == 200, "幂等分析样本没有复用任务")
    _assert(_json(duplicate_response)["created"] is False, "幂等分析样本重复创建任务")
    job_response = _json(
        client.get(
            f"/miniapp-api/watch/sessions/{session_id}/analysis/jobs/{queued_job['job_id']}"
        )
    )
    _assert(job_response["job"]["input_bytes"] > 0, "分析任务没有记录图片输入大小")

    watch_runtime_store.upsert_plot_chunks(
        session_id,
        [
            {
                "id": "plot-past",
                "timeline_epoch": 1,
                "start_ms": 10_000,
                "end_ms": 20_000,
                "summary": "她已经走进旧宅。",
                "tags": ["旧宅", "吓人"],
            },
            {
                "id": "plot-past-unrelated",
                "timeline_epoch": 1,
                "start_ms": 25_000,
                "end_ms": 35_000,
                "summary": "管理员在厨房准备早餐。",
                "tags": ["早餐"],
            },
            {
                "id": "plot-current",
                "timeline_epoch": 1,
                "start_ms": 45_000,
                "end_ms": 70_000,
                "summary": "她在走廊尽头停下。",
            },
            {
                "id": "plot-future",
                "timeline_epoch": 1,
                "start_ms": 75_000,
                "end_ms": 90_000,
                "summary": "门后突然传来巨响。",
            },
            {
                "id": "plot-future-far",
                "timeline_epoch": 1,
                "start_ms": 150_000,
                "end_ms": 165_000,
                "summary": "走廊的灯在更远处全部熄灭。",
            },
        ],
    )
    watch_runtime_store.update_analysis_state(
        session_id,
        {
            "status": "ready",
            "familiarity": "recognized",
            "identity": "测试电影 / 第一集",
            "covered_from_ms": 0,
            "covered_until_ms": 180_000,
            "story_so_far": {
                "through_ms": 60_000,
                "summary": "她独自进入旧宅调查。",
                "background": "林夏为了查清失踪案独自进入旧宅。",
                "characters": ["林夏"],
                "unresolved": ["失踪者在哪里"],
            },
        },
    )

    chat_body = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "这里是不是有点吓人"}],
        "watch_session_id": session_id,
        "watch_snapshot": snapshot,
    }
    injected_known, action_context = inject_watch_context(
        chat_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    _assert("watch_session_id" not in injected_known, "内部 session_id 被转发给上游")
    _assert("watch_snapshot" not in injected_known, "内部播放快照被转发给上游")
    known_prompt = injected_known["messages"][0]["content"]
    visible_prompt = known_prompt.split("【定时观看反应】", 1)[0]
    _assert("knowledge_mode" not in known_prompt, "known 模式标签不应注入主模型")
    _assert("她独自进入旧宅调查。" not in visible_prompt, "known 模式不应注入摘要卡片")
    _assert("你正在和小玥一起看《测试电影》的第一集" in visible_prompt, "一起看片名没有自然注入")
    _assert("她在走廊尽头停下。" in visible_prompt, "播放点所在片段没有作为当前剧情注入")
    _assert("她已经走进旧宅。" in visible_prompt, "当前消息没有召回相关已看片段")
    _assert("管理员在厨房准备早餐。" not in known_prompt, "召回混入无关已看片段")
    _assert("门后突然传来巨响。" in visible_prompt, "回复抵达窗口没有注入近未来片段")
    _assert("走廊的灯在更远处全部熄灭。" not in visible_prompt, "可见回复窗口超过配置提前量")
    _assert("走廊的灯在更远处全部熄灭。" in known_prompt, "两分钟弹幕窗口没有保留较远未来片段")
    _assert("VISIBLE_CONTEXT" not in known_prompt, "动态上下文仍把内部 JSON 字段暴露给主模型")
    paused_body = dict(chat_body)
    paused_body["watch_snapshot"] = {**snapshot, "is_playing": False}
    injected_paused, _ = inject_watch_context(
        paused_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    paused_visible = injected_paused["messages"][0]["content"].split("【定时观看反应】", 1)[0]
    _assert("门后突然传来巨响。" not in paused_visible, "暂停时回复抵达窗口没有收缩为零")
    lead_update = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"reply_lead_ms": 90_000}},
    )
    _assert(lead_update.status_code == 200, "每会话回复延迟窗口不能修改")
    injected_long_lead, _ = inject_watch_context(
        chat_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    long_visible = injected_long_lead["messages"][0]["content"].split("【定时观看反应】", 1)[0]
    _assert("走廊的灯在更远处全部熄灭。" in long_visible, "会话回复延迟没有扩展可见抵达窗口")
    invalid_lead = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"reply_lead_ms": 120_001}},
    )
    _assert(invalid_lead.status_code == 400, "回复延迟窗口允许超过两分钟")
    client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"reply_lead_ms": 30_000}},
    )
    visual_dir = TEMP_DIR / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    for index, at_ms in enumerate((15_000, 60_000, 75_000, 90_000)):
        frame_path = visual_dir / f"{at_ms}.webp"
        Image.new("RGB", (96, 54), color=(30 + index * 20, 80, 120)).save(
            frame_path,
            format="WEBP",
        )
        watch_visual_store.upsert_frame(
            frame_id=f"frame-{at_ms}",
            session_id=session_id,
            media_id="bili:BV-test:1",
            timeline_epoch=1,
            at_ms=at_ms,
            file_path=str(frame_path),
            width=96,
            height=54,
            sha256=f"sha-{at_ms}",
            source_sample_id=f"sample-{at_ms}",
        )
    client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"visual_context_mode": "text_plus_contact_sheet"}},
    )
    injected_with_visual, visual_action_context = inject_watch_context(
        chat_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    _assert(len(injected_with_visual["messages"]) == 3, "带图模式没有插入临时 user 视觉消息")
    visual_message = injected_with_visual["messages"][-2]
    _assert(visual_message["role"] == "user", "剧情拼图没有作为 user 内容发送")
    _assert(visual_message["content"][0]["text"] == "【剧情画面】", "剧情画面标签不正确")
    _assert(
        visual_message["content"][1]["image_url"]["url"].startswith("data:image/webp;base64,"),
        "剧情拼图不是临时 WebP data URL",
    )
    _assert(
        injected_with_visual["messages"][-1] == chat_body["messages"][-1],
        "视觉上下文改写了需要归档的原始用户消息",
    )
    _assert(
        all(int(item["at_ms"]) <= 90_000 for item in visual_action_context["visual_panels"]),
        "剧情拼图使用了回复抵达位置之后的画面",
    )
    injected_continuous, _ = inject_watch_context(
        chat_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    _assert(len(injected_continuous["messages"]) == 2, "两分钟内连续对话重复发送剧情拼图")
    client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"danmaku_enabled": False}},
    )
    injected_without_danmaku, _ = inject_watch_context(
        chat_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    prompt_without_danmaku = injected_without_danmaku["messages"][0]["content"]
    _assert("门后突然传来巨响。" in prompt_without_danmaku, "关闭弹幕错误移除了正常回复的抵达窗口")
    _assert("【定时观看反应】" not in prompt_without_danmaku, "关闭弹幕后仍注入动作窗口")
    client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"danmaku_enabled": True}},
    )
    incomplete_chat = dict(chat_body)
    incomplete_chat["watch_snapshot"] = {"media_id": "bili:BV-test:1"}
    ignored_chat, ignored_context = inject_watch_context(
        incomplete_chat,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    _assert(not ignored_context, "不完整聊天快照不应建立动作上下文")
    _assert(ignored_chat["messages"][0]["role"] == "user", "不完整快照不应注入动态 system")

    mode_response = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"force_unknown_analysis": True}},
    )
    _assert(mode_response.status_code == 400, "正式开播后仍能改写识图模型熟悉度")
    summary_mode_response = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/mode",
        json={"mode": {"knowledge_mode": "needs_summary"}},
    )
    _assert(summary_mode_response.status_code == 200, "观看中不能切换剧情背景显示")
    injected_unknown, action_context = inject_watch_context(
        chat_body,
        window_id="sumitalk:test-window",
        reply_channel="sumitalk",
    )
    unknown_prompt = injected_unknown["messages"][0]["content"]
    _assert("knowledge_mode" not in unknown_prompt, "needs_summary 模式标签不应注入主模型")
    _assert("林夏为了查清失踪案独自进入旧宅" in unknown_prompt, "needs_summary 模式没有注入已知剧情背景")
    _assert("剧情背景：" in unknown_prompt, "needs_summary 模式没有渲染剧情背景")
    _assert(
        unknown_prompt.index("剧情背景：") < unknown_prompt.index("当前剧情："),
        "剧情背景没有放在当前剧情之前",
    )

    raw_reply = (
        "我也觉得……先别往前凑。\n"
        "[du:danmaku 00:01:15 这里先别盯太紧。]"
    )
    visible, actions = split_watch_actions(raw_reply)
    _assert(visible == "我也觉得……先别往前凑。", "隐藏弹幕块泄漏到可见正文")
    event = build_watch_danmaku_event(actions[0], context=action_context)
    _assert(event is not None, "合法隐藏弹幕没有生成 typed event")
    _assert(event["type"] == "danmaku" and "channel" not in event, "弹幕事件不应选择消息 channel")
    legacy_visible, legacy_actions = split_watch_actions(
        "旧格式兼容\n<<<DU_WATCH_ACTION>>>\n"
        '{"type":"danmaku","target_ms":76000,"text":"旧格式仍可解析"}'
        "\n<<<END_DU_WATCH_ACTION>>>"
    )
    _assert(legacy_visible == "旧格式兼容" and legacy_actions, "旧弹幕长块兼容被破坏")

    stream_state = PcmdDuThoughtStreamState()
    streamed = stream_state.feed_delta("我也觉得……先别往前凑。\n[du:danmaku 00:01")
    _assert("du:danmaku" not in streamed and "00:01" not in streamed, "流式半截短隐藏标记泄漏")

    seek_frame_path = TEMP_DIR / "seek-old-epoch.webp"
    seek_frame_path.write_bytes(b"seek-old-epoch")
    watch_visual_store.upsert_frame(
        frame_id="watch-frame-before-seek",
        session_id=session_id,
        media_id="bili:BV-test:1",
        timeline_epoch=1,
        at_ms=60_000,
        file_path=str(seek_frame_path),
        width=64,
        height=36,
        sha256="seek-old-epoch",
        source_sample_id="seek-old-epoch",
    )
    seek_snapshot = dict(snapshot)
    seek_snapshot.update(
        {
            "playhead_ms": 300_000,
            "timeline_epoch": 2,
            "snapshot_seq": 1,
            "captured_at": "2026-07-18T10:04:00Z",
        }
    )
    seek_response = _json(
        client.put(f"/miniapp-api/watch/sessions/{session_id}/playback", json=seek_snapshot)
    )
    _assert(seek_response["applied"] is True, "新 epoch 的 seek 快照没有应用")
    _assert(not seek_frame_path.exists(), "seek 后旧 epoch 派生图片没有立即删除")
    _assert(
        watch_visual_store.frame_cache_status(session_id, timeline_epoch=1)["count"] == 0,
        "seek 后旧 epoch 派生帧元数据没有删除",
    )
    cancelled_job = _json(
        client.get(
            f"/miniapp-api/watch/sessions/{session_id}/analysis/jobs/{queued_job['job_id']}"
        )
    )["job"]
    _assert(cancelled_job["status"] == "cancelled", "seek 后旧 epoch 分析任务没有取消")
    _assert(
        build_watch_danmaku_event(actions[0], context=action_context) is None,
        "seek 后旧 epoch 弹幕仍然有效",
    )

    sections_response = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/timeline-sections",
        json={
            "timeline_epoch": 2,
            "sections": [
                {"kind": "intro", "start_ms": 0, "end_ms": 90_000},
                {"kind": "content", "start_ms": 90_000, "end_ms": 7_000_000},
                {"kind": "outro", "start_ms": 7_000_000, "end_ms": 7_200_000},
            ],
        },
    )
    _assert(sections_response.status_code == 200, "片头片尾人工纠正失败")
    status = _json(client.get(f"/miniapp-api/watch/sessions/{session_id}/status"))
    _assert(len(status["timeline_sections"]) == 3, "status 未返回时间轴片段")
    _assert(status["analysis"]["status"] == "warming_context", "边界纠正后没有触发分析重建状态")

    feedback_response = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/risk-feedback",
        json={
            "feedback_type": "missed",
            "playhead_ms": 320_000,
            "note": "这里漏掉了一次突然巨响",
        },
    )
    _assert(feedback_response.status_code == 201, "高能漏报反馈保存失败")

    end_frame_path = TEMP_DIR / "end-session-frame.webp"
    end_frame_path.write_bytes(b"end-session-frame")
    watch_visual_store.upsert_frame(
        frame_id="watch-frame-before-end",
        session_id=session_id,
        media_id="bili:BV-test:1",
        timeline_epoch=2,
        at_ms=320_000,
        file_path=str(end_frame_path),
        width=64,
        height=36,
        sha256="end-session-frame",
        source_sample_id="end-session-frame",
    )
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE watch_analysis_jobs
               SET usage_json = ?, input_tokens = 300, output_tokens = 120, cost_usd = 0.004
             WHERE id = ?
            """,
            (
                runtime_sqlite.json_dumps(
                    {
                        "input_tokens": 300,
                        "output_tokens": 120,
                        "total_tokens": 420,
                        "cost_usd": 0.004,
                        "provider_calls": 1,
                        "priced_calls": 1,
                        "cost_complete": True,
                        "model": "test-analysis-model",
                    }
                ),
                queued_job["job_id"],
            ),
        )
    ended = _json(client.delete(f"/miniapp-api/watch/sessions/{session_id}"))
    _assert(ended["session"]["playback"]["status"] == "ended", "观看会话没有正确结束")
    _assert(
        abs(ended["analysis_cost"]["amount_usd"] - 0.004) < 0.0000001,
        "结束接口没有返回本次剧情分析费用",
    )
    _assert(ended["analysis_cost"]["complete"] is True, "已完整返回的费用被标成未结算")
    _assert(ended["analysis_cost"]["provider_calls"] == 1, "结束接口模型调用数不正确")
    _assert(not end_frame_path.exists(), "结束会话后派生图片没有立即删除")
    _assert(
        watch_visual_store.frame_cache_status(session_id, timeline_epoch=2)["count"] == 0,
        "结束会话后派生帧元数据没有删除",
    )
    recent = _json(client.get("/miniapp-api/watch/sessions"))["sessions"]
    _assert(not any(item["session_id"] == session_id for item in recent), "默认最近观看仍返回 ended 会话")
    history = _json(client.get("/miniapp-api/watch/sessions?include_ended=true"))["sessions"]
    _assert(any(item["session_id"] == session_id for item in history), "显式历史查询没有返回 ended 会话")


if __name__ == "__main__":
    try:
        run()
        print("watch together backend tests passed")
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
