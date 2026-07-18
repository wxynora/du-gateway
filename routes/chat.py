# 聊天代理：统一走完整管道（清洗、注入、转发、存档），无开头过滤
# 项目约定：主聊天禁止默认兜底模型。没传 model 就直接报错，不要偷偷补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
import base64
import copy
import hashlib
import json
import os
import queue
import re
import threading
import time
import uuid
from typing import Optional
import requests

from flask import Blueprint, request, jsonify, Response, stream_with_context

from config import (
    GATEWAY_MODELS,
    MAX_COMPLETION_TOKENS,
    STREAM_TIMEOUT_SECONDS,
    STREAM_SSE_HEARTBEAT_SECONDS,
    STREAM_SSE_FLUSH_MAX_MS,
    TOOL_MAX_ROUNDS,
    DATA_DIR,
    MAIN_GATEWAY_BEARER_TOKEN,
    QQ_GROUP_ACTIVITY_REPORT_TOKEN,
    QQ_PROACTIVE_PUSH_TOKEN,
    PIONEER_CLAUDE_CACHE_TTL,
    is_openrouter_url,
    is_pioneer_url,
    is_pioneer_anthropic_url,
    is_cloudflare_anthropic_url,
    cloudflare_claude_model_options,
    openrouter_models_response,
    is_siliconflow_url,
    siliconflow_models_response,
)
from pipeline.pipeline import (
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_replace_rikka_system,
    step_inject_thinking_block_rules,
    step_inject_core_behavior_rules,
    step_inject_common_knowledge,
    step_inject_pending_thought_rules,
    step_inject_du_non_retreat_rules,
    step_inject_reference_note,
    step_inject_current_base_model,
    step_inject_system_alarm_action_result,
    step_inject_pseudo_cot_inner_os,
    step_inject_humor_memes,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_tool_result_cache,
    step_inject_sumitalk_real_mode,
    step_inject_play_note,
    step_inject_sense_snapshot,
    step_inject_du_thought,
    step_inject_pending_thoughts,
    step_inject_secret_drawer,
    step_inject_wakeup_frame,
    step_inject_du_vitals,
    step_inject_du_daily,
    step_inject_pixel_home,
    step_inject_du_midterm_memory,
    step_inject_interaction_candidate,
    step_inject_rikkahub_reminder,
    step_inject_dynamic_memory,
    step_inject_stay_with_du,
    step_inject_du_notebook,
    step_inject_wenyou_player_tools,
    step_inject_gateway_tools,
    step_inject_random_imitator_td_tools,
    step_inject_chat_tools,
    step_inject_forum_tools,
    step_inject_amap_mcp_tools,
    step_inject_websearch_tools,
    step_trim_messages_if_over_limit,
    step_archive_and_maybe_summary,
    step_archive_round,
)
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.failed_response import get_assistant_content_text, is_failed_response
from storage import (
    million_plan_mode_store,
    random_imitator_td_mode_store,
    r2_store,
    recent_window_store,
    upstream_store,
    wenyou_mode_store,
)
from storage.music_bgm_state import get_active_music_bgm_context
from storage.music_melody_store import get_music_melody_entry_by_id
from services.music_lyrics import normalize_lyrics_payload
from services.listen_invite_flow import (
    build_listen_invite_event as _build_listen_invite_event,
    inject_listen_invite_protocol as _inject_listen_invite_protocol,
    split_listen_invite_actions as _split_listen_invite_actions,
)
from services.watch_action_flow import (
    build_watch_danmaku_event as _build_watch_danmaku_event,
    split_watch_actions as _split_watch_actions,
    watch_action_dedup_key as _watch_action_dedup_key,
)
from services.watch_context import inject_watch_context as _inject_watch_context
from services.qq_activity_context import (
    build_group_activity_context_for_wakeup as _build_qq_group_activity_context_for_wakeup,
    clear_group_activity_context as _clear_qq_group_activity_context,
    record_group_activity as _record_qq_group_activity,
)
from services.du_daily import (
    build_chat_trigger as build_du_daily_trigger,
)
from services.pixel_home import maybe_update_xinyue_state_from_user_text
from services.dynamic_memory_citation import (
    DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY,
    normalize_citation_map,
)
from services.dynamic_memory_recall_debug import DU_REQUEST_ID_BODY_KEY, normalize_debug_request_id
from services.conversation_followup import (
    queue_followup,
)
from services.pc_command_handler import (
    PcmdDuThoughtStreamState,
    transform_sse_chunk_bytes as transform_sse_chunk_bytes_pcmd,
)
from services.chat_content import message_content_chars as _message_content_chars
from services.claude_thinking_carryover import (
    extract_claude_thinking_blocks as _extract_claude_thinking_blocks,
    inject_previous_claude_thinking_blocks as _inject_previous_claude_thinking_blocks,
)
from services.cloudflare_anthropic import (
    anthropic_sse_to_openai_sse as _anthropic_sse_to_openai_sse,
    anthropic_to_openai_response as _anthropic_to_openai_response,
    cloudflare_anthropic_headers as _cloudflare_anthropic_headers,
    openai_to_anthropic_request as _openai_to_anthropic_request,
)
from services.chat_prompt_injections import (
    inject_channel_nsfw_system as _inject_channel_nsfw_system,
    inject_codex_oauth_prompt_system as _inject_codex_oauth_prompt_system,
    inject_entry_style_system as _inject_entry_style_system,
    inject_followup_instruction as _inject_followup_instruction,
    inject_million_plan_player_static_system as _inject_million_plan_player_static_system,
    inject_silence_mode_system as _inject_silence_mode_system,
    inject_voice_call_style_system as _inject_voice_call_style_system,
)
from services.chat_archive_helpers import (
    compact_million_plan_round_for_archive as _compact_million_plan_round_for_archive,
    compact_qq_group_context_for_archive as _compact_qq_group_context_for_archive,
    run_nonstream_post_archive_in_background as _run_nonstream_post_archive_in_background,
    strip_co_read_section_raw_text_for_archive as _strip_co_read_section_raw_text_for_archive,
    strip_wenyou_ai_player_context_for_archive as _strip_wenyou_ai_player_context_for_archive,
)
from services.chat_request_helpers import (
    build_noop_chat_response as _build_noop_chat_response,
    is_cross_platform_tg_window_user_input as _is_cross_platform_tg_window_user_input,
    is_suspected_rikkahub_phantom_one as _is_suspected_rikkahub_phantom_one,
    last_user_message as _last_user_message,
    maybe_mark_tg_window_user_activity as _maybe_mark_tg_window_user_activity,
    maybe_record_last_reply_channel as _maybe_record_last_reply_channel,
)
from services.chat_response_enrichers import (
    dedupe_stream_sumitalk_cards,
    merge_sumitalk_card_into_nonstream_response as _merge_sumitalk_card_into_nonstream_response,
    sumitalk_card_suffix_for_stream,
)
from services.chat_sidecars import (
    apply_hidden_sidecars_to_assistant_response as _apply_hidden_sidecars_to_assistant_response,
    extract_and_store_hidden_sidecars as _extract_and_store_hidden_sidecars,
)
from services.pseudo_cot import (
    PseudoCotStreamState as _PseudoCotStreamState,
    apply_pseudo_cot_state_and_fallback as _apply_pseudo_cot_state_and_fallback,
    extract_inner_os_from_response_json as _extract_inner_os_from_response_json,
    pseudo_cot_instruction_enabled as _pseudo_cot_instruction_enabled,
    replace_response_reasoning_with_inner_os as _replace_response_reasoning_with_inner_os,
    split_inner_os_from_text as _split_inner_os_from_text,
    transform_sse_chunk_bytes as _transform_pseudo_cot_sse_chunk_bytes,
)
from services.chat_tool_helpers import (
    append_visible_tool_round_content as _append_visible_tool_round_content,
    append_tool_results_and_continue as _append_tool_results_and_continue,
    collect_tool_trace_from_messages as _collect_tool_trace_from_messages,
    inject_tool_empty_final_retry_instruction as _inject_tool_empty_final_retry_instruction,
    inject_tool_midstream_retry_instruction as _inject_tool_midstream_retry_instruction,
    is_sse_done_chunk as _is_sse_done_chunk,
    merge_visible_tool_round_content as _merge_visible_tool_round_content,
    merge_visible_tool_round_content_into_response as _merge_visible_tool_round_content_into_response,
    normalize_visible_reply_text as _normalize_visible_reply_text,
    should_retry_tool_empty_final as _should_retry_tool_empty_final,
    should_retry_tool_followup as _should_retry_tool_followup,
    sse_delta_chunk_bytes as _sse_delta_chunk_bytes,
)
from services.tool_result_cache import record_tool_loop as _record_tool_result_loop
from services.prompt_cache_debug import (
    StreamCacheDebugCollector as _StreamCacheDebugCollector,
    build_cache_debug_entry as _build_cache_debug_entry,
    build_prompt_cache_profile as _build_prompt_cache_profile,
)
from services.model_token_ratio import learn_model_token_ratio as _learn_model_token_ratio
from services.reasoning_utils import (
    ReasoningStreamAccumulator as _ReasoningStreamAccumulator,
    THINK_BLOCK_RE as _THINK_BLOCK_RE,
    extract_reasoning_stream_source as _extract_reasoning_stream_source,
    extract_reasoning_text_and_details as _extract_reasoning_text_and_details,
    extract_thinking_from_content as _extract_thinking_from_content,
    normalize_reasoning_details as _normalize_reasoning_details,
    parse_stream_to_message as _parse_stream_to_message,
    strip_reasoning_from_sse_chunk as _strip_reasoning_from_sse_chunk,
    strip_thinking_from_response_json as _strip_thinking_from_response_json,
)
from services.upstream_policy import (
    apply_active_model_request_policy as _apply_active_model_request_policy,
    apply_openrouter_request_policy as _apply_openrouter_request_policy,
    build_upstream_error_hint as _build_upstream_error_hint,
    chat_url_to_models_url as _chat_url_to_models_url,
    extract_upstream_error_detail as _extract_upstream_error_detail,
    get_active_upstream_url as _get_active_upstream_url,
    get_forward_targets as _get_forward_targets,
    is_local_claude_oauth_proxy_url as _is_local_claude_oauth_proxy_url,
)
from storage.upstream_store import pioneer_claude_model_options as _pioneer_claude_model_options
from utils.log import get_logger

logger = get_logger(__name__)
sumitalk_logger = get_logger("sumitalk")
bp = Blueprint("chat", __name__)

_SUMITALK_STREAM_ARCHIVE_QUEUE: queue.Queue = queue.Queue()
_SUMITALK_STREAM_ARCHIVE_THREAD: threading.Thread | None = None
_SUMITALK_STREAM_ARCHIVE_THREAD_LOCK = threading.Lock()


def _run_sumitalk_stream_archive_queue() -> None:
    while True:
        task = _SUMITALK_STREAM_ARCHIVE_QUEUE.get()
        try:
            (
                window_id,
                request_messages,
                assistant_message,
                round_cleaned,
                skip_dynamic_memory_write,
                skip_body_delta,
            ) = task
            step_archive_and_maybe_summary(
                window_id,
                request_messages,
                assistant_message,
                round_cleaned_for_r2=round_cleaned,
                skip_dynamic_memory_write=skip_dynamic_memory_write,
                skip_body_delta=skip_body_delta,
            )
            logger.info("R2 SumiTalk 流式请求后台存档完成")
        except Exception:
            logger.exception("R2 SumiTalk 流式请求后台存档失败")
        finally:
            _SUMITALK_STREAM_ARCHIVE_QUEUE.task_done()


def _enqueue_sumitalk_stream_archive(task: tuple) -> None:
    global _SUMITALK_STREAM_ARCHIVE_THREAD
    thread = _SUMITALK_STREAM_ARCHIVE_THREAD
    if thread is None or not thread.is_alive():
        with _SUMITALK_STREAM_ARCHIVE_THREAD_LOCK:
            thread = _SUMITALK_STREAM_ARCHIVE_THREAD
            if thread is None or not thread.is_alive():
                thread = threading.Thread(
                    target=_run_sumitalk_stream_archive_queue,
                    name="sumitalk-stream-archive",
                    daemon=True,
                )
                _SUMITALK_STREAM_ARCHIVE_THREAD = thread
                thread.start()
    _SUMITALK_STREAM_ARCHIVE_QUEUE.put(task)

WINDOW_ID_DEFAULT = ""
_NONSTREAM_FAST_RETURN_CHANNELS = {"tg", "qq", "wechat", "sumitalk", "xiaoai"}


def _get_window_id_from_request(body: dict) -> str:
    """从请求获取 window_id：优先 X-Window-Id header，其次 body.window_id，缺省为空。供 Telegram 等客户端传 tg_{user_id}。"""
    if request.headers.get("X-Window-Id"):
        return (request.headers.get("X-Window-Id") or "").strip()
    if isinstance(body, dict) and body.get("window_id") is not None:
        return str(body.get("window_id", "")).strip()
    return WINDOW_ID_DEFAULT


def _move_dynamic_systems_after_static_prefix(body: dict) -> dict:
    """Keep cache-stable leading system messages before gateway dynamic system blocks."""
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    messages = list(body.get("messages") or [])
    prefix = []
    rest_start = 0
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "system":
            rest_start = idx
            break
        prefix.append(msg)
    else:
        rest_start = len(messages)
    if not prefix:
        return body
    static_systems = [msg for msg in prefix if not msg.get("__dynamic__")]
    dynamic_systems = [msg for msg in prefix if msg.get("__dynamic__")]
    if not dynamic_systems:
        return body
    reordered = static_systems + dynamic_systems + messages[rest_start:]
    if reordered == messages:
        return body
    body = dict(body)
    body["messages"] = reordered
    return body


def _is_miniapp_request() -> bool:
    return bool((request.headers.get("X-Telegram-Init-Data") or "").strip())


def _reply_channel() -> str:
    return str(request.headers.get("X-Reply-Channel") or "").strip().lower()


def _xiaoai_speaker_from_request() -> str:
    raw_b64 = str(request.headers.get("X-XiaoAI-Speaker-B64") or "").strip()
    if raw_b64:
        try:
            return base64.urlsafe_b64decode(raw_b64.encode("ascii")).decode("utf-8").strip()
        except Exception:
            logger.warning("X-XiaoAI-Speaker-B64 解码失败")
    return str(request.headers.get("X-XiaoAI-Speaker") or "").strip()


def _reply_target() -> str:
    return str(request.headers.get("X-Reply-Target") or "").strip()


def _truthy_header(name: str) -> bool:
    return (request.headers.get(name) or "").strip().lower() in ("1", "true", "yes")


def _is_million_plan_request() -> bool:
    """百万计划是外部游戏流量，不参与动态记忆召回或动态层沉淀。"""
    if _truthy_header("X-Million-Plan"):
        return True
    reply_target = _reply_target().lower().replace("_", "-")
    if reply_target.startswith("million-plan"):
        return True
    window_id = str(request.headers.get("X-Window-Id") or "").strip().lower().replace("_", "-")
    if window_id.startswith("million-plan"):
        return True
    referer = str(request.headers.get("Referer") or request.headers.get("Referrer") or "").lower()
    return "/million-plan" in referer


def _is_game_tool_loop_request() -> bool:
    """文字游戏工具循环：不参与动态记忆/身体状态等对话侧沉淀。"""
    if _truthy_header("X-DU-Game-Tool-Loop") or _truthy_header("X-Random-Imitator-TD"):
        return True
    for value in (_reply_target(), str(request.headers.get("X-Window-Id") or "")):
        normalized = str(value or "").strip().lower().replace("_", "-")
        if normalized.startswith(("random-imitator-td", "imitator-pvz")):
            return True
    referer = str(request.headers.get("Referer") or request.headers.get("Referrer") or "").lower()
    return "/random-imitator-td" in referer or "/imitator-pvz" in referer


def _random_imitator_td_tool_mode_enabled() -> bool:
    try:
        return bool(random_imitator_td_mode_store.is_enabled())
    except Exception as e:
        logger.warning("random_imitator_td_mode_check_failed error=%s", e)
        return False


def _wenyou_player_tool_mode_enabled() -> bool:
    try:
        return bool(wenyou_mode_store.is_enabled())
    except Exception as e:
        logger.warning("wenyou_mode_check_failed error=%s", e)
        return False


def _inject_million_plan_player_prompt_if_enabled(body: dict) -> dict:
    try:
        if not million_plan_mode_store.is_enabled():
            return body
    except Exception as e:
        logger.warning("million_plan_mode_check_failed error=%s", e)
        return body
    logger.info("million_plan_player_static_prompt_injected")
    return _inject_million_plan_player_static_system(body)


def _skip_dynamic_memory_request() -> bool:
    return (
        _truthy_header("X-Skip-Dynamic-Memory")
        or _is_gateway_wakeup_request()
        or _is_million_plan_request()
        or _is_game_tool_loop_request()
    )


def _force_game_checkpoint_final_response(resp_json: dict | None) -> dict:
    fallback = "由于防沉迷机制，暂时中止游戏回合。下次可以继续。"
    data = dict(resp_json or {})
    choices = list(data.get("choices") or [{}])
    if not choices:
        choices = [{}]
    choice = dict(choices[0] or {})
    msg = dict(choice.get("message") or {})
    msg.pop("tool_calls", None)
    msg["content"] = _normalize_visible_reply_text(get_assistant_content_text(msg)) or fallback
    choice["message"] = msg
    choices[0] = choice
    data["choices"] = choices
    return data


def _bearer_token_from_request() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def _verify_qq_group_activity_report() -> bool:
    allowed = {
        x.strip()
        for x in (
            QQ_GROUP_ACTIVITY_REPORT_TOKEN,
            QQ_PROACTIVE_PUSH_TOKEN,
            MAIN_GATEWAY_BEARER_TOKEN,
        )
        if x and x.strip()
    }
    if allowed:
        provided = _bearer_token_from_request() or (request.headers.get("X-QQ-Activity-Token") or "").strip()
        return provided in allowed
    return (request.remote_addr or "") in {"127.0.0.1", "::1", "localhost"}


@bp.route("/api/internal/qq-group-activity", methods=["POST"])
def qq_group_activity_report():
    if not _verify_qq_group_activity_report():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    ok = _record_qq_group_activity(body if isinstance(body, dict) else {})
    return jsonify({"ok": bool(ok)}), 200 if ok else 400


def _music_bgm_float(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _music_bgm_clip(value: object, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _music_bgm_clock(seconds: float) -> str:
    total = max(0, int(round(float(seconds or 0))))
    return f"{total // 60}:{str(total % 60).zfill(2)}"


def _music_bgm_duration(entry: dict, context: dict) -> float:
    duration = _music_bgm_float(context.get("duration_seconds") or (entry or {}).get("duration_seconds"))
    if duration > 0:
        return duration
    structured = (entry or {}).get("structured") if isinstance((entry or {}).get("structured"), dict) else {}
    segments = structured.get("segments") if isinstance(structured, dict) else []
    return max([_music_bgm_float(item.get("end")) for item in segments if isinstance(item, dict)] or [0.0])


def _music_bgm_segment_for_time(entry: dict, context: dict, current_time: float) -> dict:
    client_segment = context.get("segment") if isinstance(context.get("segment"), dict) else {}
    structured = (entry or {}).get("structured") if isinstance((entry or {}).get("structured"), dict) else {}
    segments = structured.get("segments") if isinstance(structured, dict) else []
    current = max(0.0, float(current_time or 0))
    fallback = client_segment if isinstance(client_segment, dict) else {}
    for item in segments if isinstance(segments, list) else []:
        if not isinstance(item, dict):
            continue
        start = _music_bgm_float(item.get("start"))
        end = _music_bgm_float(item.get("end"))
        if end > start:
            fallback = item
            if start <= current < end:
                return item
    return fallback or {}


def _music_bgm_format_segment(segment: dict, current_time: float) -> str:
    start = _music_bgm_float(segment.get("start"))
    end = _music_bgm_float(segment.get("end"))
    section = _music_bgm_clip(segment.get("section"), 60) or "这一段"
    current = start <= max(0.0, float(current_time or 0)) < end if end > start else False
    head = f"- {_music_bgm_clock(start)}-{_music_bgm_clock(end)} {section}" + ("（当前）" if current else "")
    details = []
    plain = _music_bgm_clip(segment.get("plain"), 260)
    melody = _music_bgm_clip(segment.get("melody_motion"), 180)
    sonic = _music_bgm_clip(segment.get("sonic_detail"), 180)
    intensity = _music_bgm_clip(segment.get("intensity"), 160)
    if plain:
        details.append(f"听感：{plain}")
    if melody:
        details.append(f"走向：{melody}")
    if sonic:
        details.append(f"声音：{sonic}")
    if intensity:
        details.append(f"推进：{intensity}")
    return head + ("：" + "；".join(details) if details else "")


def _music_bgm_segments_until_time(entry: dict, current_time: float, current_segment: dict) -> list[dict]:
    structured = (entry or {}).get("structured") if isinstance((entry or {}).get("structured"), dict) else {}
    segments = structured.get("segments") if isinstance(structured, dict) else []
    current = max(0.0, float(current_time or 0))
    out: list[dict] = []
    seen = set()
    for item in segments if isinstance(segments, list) else []:
        if not isinstance(item, dict):
            continue
        start = _music_bgm_float(item.get("start"))
        end = _music_bgm_float(item.get("end"))
        if end <= start or start > current + 0.15:
            continue
        key = (round(start, 2), round(end, 2), str(item.get("section") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    if isinstance(current_segment, dict) and current_segment:
        start = _music_bgm_float(current_segment.get("start"))
        end = _music_bgm_float(current_segment.get("end"))
        key = (round(start, 2), round(end, 2), str(current_segment.get("section") or ""))
        if end > start and start <= current + 0.15 and key not in seen:
            out.append(current_segment)
    out.sort(key=lambda item: (_music_bgm_float(item.get("start")), _music_bgm_float(item.get("end"))))
    while len("\n".join(_music_bgm_format_segment(item, current_time) for item in out)) > 2600 and len(out) > 8:
        out.pop(0)
    return out


def _music_bgm_lyrics_context(entry: dict, current_time: float) -> str:
    lyrics = normalize_lyrics_payload((entry or {}).get("lyrics")) if (entry or {}).get("lyrics") else {}
    raw_lines = lyrics.get("lines") if isinstance(lyrics, dict) else []
    plain_lines = lyrics.get("plain_lines") if isinstance(lyrics, dict) else []
    raw_lines = raw_lines if isinstance(raw_lines, list) else []
    plain_lines = plain_lines if isinstance(plain_lines, list) else []
    clean_lines = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        text = _music_bgm_clip(item.get("text"), 160)
        if not text:
            continue
        translation = _music_bgm_clip(item.get("translation"), 160)
        clean_lines.append({
            "time": _music_bgm_float(item.get("time")),
            "text": text + (f"（{translation}）" if translation else ""),
        })
    if clean_lines:
        clean_lines.sort(key=lambda item: item["time"])
        active = 0
        t = max(0.0, float(current_time or 0))
        for idx, item in enumerate(clean_lines):
            if item["time"] <= t + 0.15:
                active = idx
            else:
                break
        past = [f"- {_music_bgm_clock(item['time'])} {item['text']}" for item in clean_lines[: active + 1]]
        while len("\n".join(past)) > 2200 and len(past) > 10:
            past.pop(0)
        if past and past[0] != f"- {_music_bgm_clock(clean_lines[0]['time'])} {clean_lines[0]['text']}":
            past.insert(0, "- ...")
        upcoming = [f"- {_music_bgm_clock(item['time'])} {item['text']}" for item in clean_lines[active + 1 : active + 3]]
        parts = []
        if past:
            parts.append("从开头到当前已唱到的歌词：\n" + "\n".join(past))
        if upcoming:
            parts.append("接下来几句歌词：\n" + "\n".join(upcoming))
        return "\n".join(parts).strip()
    clean_plain = [_music_bgm_clip(item, 160) for item in plain_lines if _music_bgm_clip(item, 160)]
    if not clean_plain:
        return ""
    return "歌词文本：\n" + _music_bgm_clip("\n".join(f"- {line}" for line in clean_plain[:60]), 2600)


def _build_music_bgm_context_system(context: dict) -> str:
    if not isinstance(context, dict) or not context.get("active") or not context.get("is_playing"):
        return ""
    entry_id = str(context.get("entry_id") or context.get("id") or "").strip()
    entry = get_music_melody_entry_by_id(entry_id) if entry_id else None
    entry = entry if isinstance(entry, dict) else {}
    current_time = _music_bgm_float(context.get("current_time") or context.get("currentTime"))
    duration = _music_bgm_duration(entry, context)
    segment = _music_bgm_segment_for_time(entry, context, current_time)
    heard_segments = _music_bgm_segments_until_time(entry, current_time, segment)
    title = _music_bgm_clip((entry or {}).get("title") or context.get("title"), 80)
    artist = _music_bgm_clip((entry or {}).get("artist") or context.get("artist"), 80)
    structured = (entry or {}).get("structured") if isinstance((entry or {}).get("structured"), dict) else {}
    overall = _music_bgm_clip((entry or {}).get("overall_trend") or structured.get("overall_trend"), 500)
    lyrics_context = _music_bgm_lyrics_context(entry, current_time)

    lines = [
        "【当前背景音乐】",
        "你正在和小玥日常聊天。现在有一首歌作为背景音乐在播放；把它当成当下环境和情绪底色，像平时那样自然聊天。",
        "不要把回复写成乐评、歌词赏析或报告。除非她主动聊这首歌，否则只在合适时轻轻接住音乐、歌词或氛围。",
        f"背景音乐：{title or '未知歌曲'}" + (f" / {artist}" if artist else ""),
        f"播放位置：{_music_bgm_clock(current_time)}" + (f" / {_music_bgm_clock(duration)}" if duration > 0 else ""),
    ]
    if heard_segments:
        lines.append("从开头到当前已听到的音乐变化：")
        lines.extend(_music_bgm_format_segment(item, current_time) for item in heard_segments)
    if lyrics_context:
        lines.append(lyrics_context)
    if overall:
        lines.append(f"整首歌的大致走向：{overall}")
    return "\n".join(line for line in lines if str(line or "").strip()).strip()


def _inject_music_bgm_context(body: dict, *, reply_channel: str = "") -> dict:
    if not isinstance(body, dict):
        return body
    has_explicit_context = "music_bgm_context" in body or "listen_bgm_context" in body
    raw_context = body.get("music_bgm_context") or body.get("listen_bgm_context")
    if not has_explicit_context and str(reply_channel or "").strip().lower() in {"qq", "sumitalk"}:
        raw_context = get_active_music_bgm_context()
    body = dict(body)
    body.pop("music_bgm_context", None)
    body.pop("listen_bgm_context", None)
    system_text = _build_music_bgm_context_system(raw_context) if isinstance(raw_context, dict) else ""
    if not system_text:
        return body
    if not has_explicit_context:
        logger.info(
            "music_bgm_context_injected channel=%s entry_id=%s title=%s current_time=%.2f",
            reply_channel,
            str((raw_context or {}).get("entry_id") or ""),
            str((raw_context or {}).get("title") or "")[:80],
            _music_bgm_float((raw_context or {}).get("current_time")),
        )
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    body["messages"] = [{"role": "system", "content": system_text, "__dynamic__": True}] + list(messages)
    return body


def _last_user_for_archive(last_user: Optional[dict], *, reply_target: str, window_id: str) -> Optional[dict]:
    if not last_user:
        return last_user
    if reply_target == "co_read_section":
        return _strip_co_read_section_raw_text_for_archive(last_user)
    if reply_target == "wenyou_ai_player":
        return _strip_wenyou_ai_player_context_for_archive(last_user)
    if reply_target == "qq_group_mention":
        return _compact_qq_group_context_for_archive(last_user, window_id=window_id)
    return last_user


def _plain_message_text(msg: Optional[dict]) -> str:
    content = (msg or {}).get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return " ".join(p for p in parts if p).strip()
    return str(content or "").strip()


def _clip_archive_text(text: str, limit: int = 180) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _compact_archive_line(text: str, limit: int = 120) -> str:
    text = _clip_archive_text(str(text or "").replace("\r", "\n"), limit)
    return text.strip(" 。；;\n\t")


def _regex_group(pattern: str, text: str, default: str = "") -> str:
    try:
        m = re.search(pattern, text, flags=re.S)
        if not m:
            return default
        return str(m.group(1) or "").strip()
    except Exception:
        return default


def _compact_schedule_event_text(text: str, *, label: str) -> str:
    title = _regex_group(r"「([^」]{1,80})」", text)
    when = _regex_group(r"时间[:：]([^。；\n]{1,60})", text)
    if title:
        content = f"{label}：「{_compact_archive_line(title, 80)}」到点了。"
    else:
        content = f"这是一次{label}。"
    if when:
        content += f"时间：{_compact_archive_line(when, 60)}。"
    return content


def _compact_choice_dialog_event_text(text: str) -> str:
    title = _regex_group(r"弹窗标题[:：]([^\n。]{1,100})", text)
    result = _regex_group(r"弹窗结果[:：]([^\n]{1,160})", text)
    result = _compact_archive_line(result, 120)
    if title and result:
        return f"弹窗回执：「{_compact_archive_line(title, 80)}」{result}。"
    if result:
        return f"弹窗回执：{result}。"
    return "这是一次弹窗回执。"


def _compact_screen_check_event_text(text: str) -> str:
    title = _regex_group(r"查岗申请标题[:：]([^\n。]{1,100})", text)
    result = _regex_group(r"结果[:：]([^\n]{1,180})", text)
    captured_at = _regex_group(r"截图时间[:：]([^\n。]{1,80})", text)
    if not result:
        if "同意了，这是" in text:
            result = "她同意了，并回传了截图"
        elif "没有可用图片链接" in text:
            result = "她同意了，但截图链接不可用"
    result = _compact_archive_line(result, 140)
    if title and result:
        content = f"截图回执：「{_compact_archive_line(title, 80)}」{result}。"
    elif result:
        content = f"截图回执：{result}。"
    else:
        content = "这是一次截图回执。"
    if captured_at:
        content += f"截图时间：{_compact_archive_line(captured_at, 60)}。"
    return content


def _compact_exchange_diary_comment_event_text(text: str) -> str:
    title = _regex_group(r"日记标题[:：]([^\n]{1,120})", text)
    comment = _regex_group(r"评论内容[:：]([\s\S]{1,800})", text)
    if "\n\n" in comment:
        comment = comment.split("\n\n", 1)[0]
    comment = _compact_archive_line(comment, 160)
    if title and comment:
        return f"小玥评论了交换日记「{_compact_archive_line(title, 80)}」：{comment}。"
    if comment:
        return f"小玥评论了交换日记：{comment}。"
    return "小玥刚刚评论了你的交换日记。"


def _compact_private_board_event_text(text: str) -> str:
    if "刚掷完骰子后的自动同步" in text or "本次掷骰结果与当前棋局" in text:
        roll = _regex_group(
            r"本次掷骰[:：]\s*([\s\S]*?)(?:\n\s*\n当前棋局[:：]|\n当前棋局[:：]|\n\n这是小玥在涩涩走格棋页面内发给你的游戏交流|$)",
            text,
        )
        if roll:
            return f"小玥在涩涩走格棋中同步了掷骰结果：{_compact_archive_line(roll, 220)}。"
        return "小玥在涩涩走格棋中同步了本次掷骰结果和当前棋局。"
    message = _regex_group(
        r"小玥刚刚在局内说[:：]([\s\S]*?)(?:\n\n这是小玥在涩涩走格棋页面内发给你的游戏交流|$)",
        text,
    )
    if message:
        return f"小玥在涩涩走格棋局内说：{_compact_archive_line(message, 220)}。"
    return "小玥在涩涩走格棋局内发来一条消息。"


def _compact_captivity_simulator_event_text(text: str) -> str:
    day = _regex_group(r"进度[:：]第\s*(\d+)\s*/\s*30", text)
    phase = _regex_group(r"进度[:：]第\s*\d+\s*/\s*30\s*天[，,]\s*([^，,\n]+)", text)
    pending = _regex_group(r"待处理[:：]([^\n]{1,160})", text)
    today_completed = _regex_group(r"今日已完成[:：]([^\n]{1,500})", text)
    message = _regex_group(
        r"小玥刚刚在局内说[:：]([\s\S]*?)(?:\n\n当前游戏状态[:：]|\n当前游戏状态[:：]|$)",
        text,
    )
    bits = []
    if day:
        bits.append(f"第 {day} 天")
    if phase:
        bits.append(_compact_archive_line(phase, 40))
    if pending:
        bits.append(f"待处理：{_compact_archive_line(pending, 120)}")
    if today_completed:
        bits.append(f"今日已完成：{_compact_archive_line(today_completed, 220)}")
    if message:
        bits.append(f"局内说明：{_compact_archive_line(message, 120)}")
    suffix = "，".join(bits)
    if suffix:
        return f"小玥在囚禁模拟器中同步了状态：{suffix}。"
    return "小玥在囚禁模拟器中同步了一次游戏状态。"


def _compact_captivity_simulator_assistant_for_archive(assistant_msg: dict) -> dict:
    raw = _plain_message_text(assistant_msg)
    parsed = ""
    if raw.strip().startswith("【"):
        match = re.match(r"^【\s*([^：:】]+)", raw.strip())
        if match:
            parsed = str(match.group(1) or "").strip()
    if parsed:
        content = (
            f"渡在囚禁模拟器中回复了「{_compact_archive_line(parsed, 40)}」指令；"
            "完整行动正文只保留在游戏存档，思维链按原字段归档。"
        )
    elif raw.strip():
        content = "渡在囚禁模拟器局内回复了一段普通聊天；完整正文不写入聊天归档。"
    else:
        content = "渡在囚禁模拟器局内回复为空。"
    compacted = {"role": "assistant", "archive_label": "渡", "content": content}
    for key in (
        "reasoning",
        "reasoning_content",
        "thinking",
        "reasoning_details",
        "thinking_blocks",
        "reasoning_omitted",
        "cache_debug",
        "du_request_id",
    ):
        if key in assistant_msg:
            compacted[key] = assistant_msg[key]
    return compacted


def _captivity_simulator_channel_player_text(user_msg: dict | None) -> str:
    text = _plain_message_text(user_msg)
    prefix = "（囚禁模拟器频道）"
    if not text.startswith(prefix):
        return ""
    content = text[len(prefix):].strip()
    if not content or content.startswith("系统正在推进当前事件"):
        return ""
    if content.startswith("小玥："):
        content = content[len("小玥："):].strip()
    return _clip_archive_text(content, 220)


def _wakeup_kind_for_archive() -> str:
    return str(request.headers.get("X-DU-WAKEUP-KIND") or "").strip().lower()


def _gateway_event_source_for_archive(messages: list | None, *, wakeup_kind: str = "") -> Optional[dict]:
    kind = str(wakeup_kind or "").strip().lower()
    if kind not in {"private_board", "captivity_simulator"}:
        return None
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() != "system":
            continue
        text = _plain_message_text(msg)
        if kind == "private_board" and "涩涩走格棋" in text:
            return msg
        if kind == "captivity_simulator" and "囚禁模拟器" in text:
            return msg
    return None


def _compact_gateway_event_for_archive(user_msg: dict, *, wakeup_kind: str = "") -> dict:
    kind = str(wakeup_kind or "").strip().lower()
    text = _plain_message_text(user_msg)
    if kind in {"system_alarm", "alarm", "schedule_alarm"}:
        label = "闹钟提醒"
        content = _compact_schedule_event_text(text, label=label)
    elif kind in {"calendar_event", "calendar", "schedule_calendar"}:
        label = "日历提醒"
        content = _compact_schedule_event_text(text, label=label)
    elif kind in {"choice_dialog", "choice_dialog_result", "dialog_result"}:
        label = "弹窗回执"
        content = _compact_choice_dialog_event_text(text)
    elif kind in {"screen_check", "screen_check_result", "screenshot_result"}:
        label = "截图回执"
        content = _compact_screen_check_event_text(text)
    elif kind in {"private_draw", "private_slip"}:
        label = "私密抽签"
        content = "小玥发来一次 sex play 抽签结果。"
    elif kind == "private_board":
        label = "涩涩走格棋"
        content = _compact_private_board_event_text(text)
    elif kind == "captivity_simulator":
        label = "囚禁模拟器"
        content = _compact_captivity_simulator_event_text(text)
    elif kind in {"exchange_diary_comment", "diary_comment"}:
        label = "交换日记评论"
        content = _compact_exchange_diary_comment_event_text(text)
    elif kind in {"proactive_diary", "random_diary"}:
        label = "随机唤醒执行"
        content = "你刚才选择了写日记，现在去写。"
    elif kind in {"proactive_forum", "random_forum"}:
        label = "随机唤醒执行"
        content = "你刚才选择了逛论坛，现在去逛。"
    elif kind in {"proactive_drawer", "random_drawer"}:
        label = "随机唤醒执行"
        content = "你刚才选择了整理秘密抽屉，现在去整理/翻旧条目。"
    elif kind in {"spring_dream", "random_spring_dream"}:
        label = "随机唤醒"
        content = "睡眠期随机唤醒触发了一次春梦。"
    elif kind in {"proactive_trigger", "pixel_home"} or "[Proactive trigger fact]" in text:
        label = "后端触发"
        content = "这是一次后端触发提醒。"
    else:
        label = "网关提醒"
        content = "这是一次网关唤醒提醒。"
    return {"role": "event", "archive_label": label, "content": content}


def _compact_gateway_reminder_for_archive(user_msg: dict) -> dict:
    text = _plain_message_text(user_msg)
    if "闹钟" in text and ("到点" in text or "提醒" in text):
        label = "闹钟提醒"
        content = _compact_schedule_event_text(text, label=label)
    elif text.startswith("这是一次随机唤醒"):
        label = "随机唤醒"
        content = "这是一次随机唤醒提醒。"
    elif "[Proactive trigger fact]" in text:
        label = "后端触发"
        content = "这是一次后端触发提醒。"
    else:
        label = "网关提醒"
        content = "这是一次网关唤醒提醒。"
    return {"role": "event", "archive_label": label, "content": content}


def _compact_proactive_decision_for_archive(assistant_msg: dict) -> dict:
    raw = _plain_message_text(assistant_msg)
    decision: dict = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            decision = parsed
    except Exception:
        decision = {}

    action = str(decision.get("action") or "").strip()
    action_label = {
        "send_message": "主动发消息",
        "no_contact": "暂时不打扰",
        "diary": "去写日记/记事",
        "forum": "逛论坛",
        "surf": "随机冲浪",
        "drawer": "整理秘密抽屉",
        "other": "先做其它动作",
    }.get(action, action or "记录判断")
    lines = [f"决策：{action_label}。"]

    reason = _clip_archive_text(str(decision.get("reason") or decision.get("du_reason") or "").strip(), 180)
    if reason:
        lines.append(f"理由：{reason}")
    message = _clip_archive_text(str(decision.get("message") or "").strip(), 160)
    if message:
        lines.append(f"要发的话：{message}")
    channel = _clip_archive_text(str(decision.get("channel") or "").strip(), 40)
    if channel and action == "send_message":
        lines.append(f"渠道：{channel}")

    if len(lines) == 1 and raw:
        lines.append(_clip_archive_text(raw, 220))
    compacted = {"role": "assistant", "archive_label": "渡", "content": "\n".join(lines)}
    for key in (
        "cache_debug",
        "reasoning",
        "reasoning_content",
        "thinking",
        "reasoning_details",
        "reasoning_omitted",
        "thinking_blocks",
        "tool_calls",
    ):
        if key in assistant_msg:
            compacted[key] = assistant_msg[key]
    return compacted


def _build_round_cleaned_for_archive(
    user_msg: dict,
    assistant_msg: dict,
    *,
    reply_target: str,
    window_id: str,
    request_messages: list | None = None,
) -> list:
    archive_user = _last_user_for_archive(user_msg, reply_target=reply_target, window_id=window_id)
    archive_assistant = assistant_msg
    if _is_million_plan_request():
        archive_user, archive_assistant = _compact_million_plan_round_for_archive(
            user_msg,
            assistant_msg,
            turn_id=_million_plan_turn_id_from_request(),
        )
    elif _is_proactive_decision_request():
        archive_user = _compact_gateway_reminder_for_archive(archive_user or user_msg)
        archive_assistant = _compact_proactive_decision_for_archive(assistant_msg)
    elif _is_gateway_wakeup_request():
        wakeup_kind = _wakeup_kind_for_archive()
        if wakeup_kind:
            event_msg = _gateway_event_source_for_archive(request_messages, wakeup_kind=wakeup_kind)
            archive_user = _compact_gateway_event_for_archive(event_msg or archive_user or user_msg, wakeup_kind=wakeup_kind)
            if wakeup_kind == "captivity_simulator":
                game_summary = str(archive_user.get("content") or "").strip()
                player_text = _captivity_simulator_channel_player_text(user_msg)
                if not player_text:
                    for request_msg in reversed(request_messages or []):
                        if isinstance(request_msg, dict) and str(request_msg.get("role") or "").strip().lower() == "user":
                            player_text = _captivity_simulator_channel_player_text(request_msg)
                            if player_text:
                                break
                if player_text:
                    archive_user = {
                        "role": "user",
                        "content": (
                            f"（囚禁模拟器频道）\n小玥：{player_text}\n\n"
                            f"（游戏状态摘要）\n{game_summary}"
                        ),
                    }
                archive_assistant = _compact_captivity_simulator_assistant_for_archive(assistant_msg)
    return build_round_cleaned_for_r2(archive_user, archive_assistant)


def _is_followup_generation_request() -> bool:
    return (request.headers.get("X-DU-FOLLOWUP-GEN") or "").strip().lower() in ("1", "true", "yes")


def _is_gateway_wakeup_request() -> bool:
    """后端自行唤醒渡的请求：保留完整静态/短程上下文，但不做动态记忆召回。"""
    truthy = ("1", "true", "yes")
    for name in (
        "X-DU-GATEWAY-WAKEUP",
        "X-DU-FOLLOWUP-GEN",
        "X-DU-DAILY-MAINTAIN",
        "X-DU-PROACTIVE-DECISION",
    ):
        if (request.headers.get(name) or "").strip().lower() in truthy:
            return True
    return False


def _skip_post_archive_dynamic_memory_request() -> bool:
    return (
        _truthy_header("X-Skip-Post-Archive-Dynamic-Memory")
        or _is_million_plan_request()
        or _is_game_tool_loop_request()
    )


def _skip_post_archive_body_delta_request() -> bool:
    return (
        _truthy_header("X-Skip-Post-Archive-Body-Delta")
        or _is_million_plan_request()
        or _is_game_tool_loop_request()
    )


def _million_plan_turn_id_from_request() -> str:
    raw = str(request.headers.get("X-Million-Plan-Turn-Id") or "").strip()
    if not raw:
        return ""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", raw)[:160]


def _million_plan_replay_response(content: str, *, model: str = "") -> dict:
    now = int(time.time())
    return {
        "id": f"chatcmpl-million-plan-replay-{now}",
        "object": "chat.completion",
        "created": now,
        "model": model or "million-plan-replay",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "million_plan_replay": True,
    }


def _million_plan_archived_content(window_id: str, turn_id: str) -> str:
    if not turn_id:
        return ""
    try:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=24) or []
    except Exception:
        logger.warning("million_plan_replay_lookup_failed window_id=%s turn_id=%s", window_id, turn_id, exc_info=True)
        return ""
    for round_obj in reversed(rounds):
        for msg in reversed((round_obj or {}).get("messages") or []):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("million_plan_turn_id") or "") != turn_id:
                continue
            if str(msg.get("role") or "").strip().lower() != "assistant":
                continue
            raw = str(msg.get("million_plan_raw_content") or "").strip()
            if raw:
                return raw
            content = msg.get("content")
            if isinstance(content, str):
                return content
    return ""


def _should_archive_followup_generation_request() -> bool:
    return (request.headers.get("X-DU-FOLLOWUP-ARCHIVE") or "").strip().lower() in ("1", "true", "yes")


def _disable_followup_request() -> bool:
    return (request.headers.get("X-DU-DISABLE-FOLLOWUP") or "").strip().lower() in ("1", "true", "yes")


def _allow_tool_only_reply_request() -> bool:
    return (request.headers.get("X-Allow-Tool-Only-Reply") or "").strip().lower() in ("1", "true", "yes")


def _is_delayed_followup_generation_request() -> bool:
    if not _is_followup_generation_request():
        return False
    for name in ("X-DU-FOLLOWUP-COUNT", "X-DU-FOLLOWUP-CHAIN-ID", "X-DU-FOLLOWUP-ROOT-AT"):
        if (request.headers.get(name) or "").strip():
            return True
    return False


def _inject_qq_group_activity_context(body: dict) -> dict:
    if _is_du_daily_maintenance_request() or not _is_gateway_wakeup_request():
        return body
    if (request.headers.get("X-Skip-QQ-Group-Activity") or "").strip().lower() in ("1", "true", "yes"):
        return body
    group_context = _build_qq_group_activity_context_for_wakeup()
    if not group_context:
        return body
    if isinstance(group_context, list):
        context_parts = [dict(part) for part in group_context if isinstance(part, dict)]
        context_text = "\n".join(str(part.get("text") or "") for part in context_parts if part.get("type") == "text")
    else:
        context_text = str(group_context or "")
        context_parts = [{"type": "text", "text": context_text}] if context_text else []
    if not context_parts:
        return body
    body = dict(body)
    messages = list(body.get("messages") if isinstance(body.get("messages"), list) else [])
    target_idx = -1
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], dict) and str(messages[idx].get("role") or "").strip().lower() == "user":
            target_idx = idx
            break
    append_parts = [dict(part) for part in context_parts]
    if append_parts and append_parts[0].get("type") == "text":
        append_parts[0]["text"] = "\n\n" + str(append_parts[0].get("text") or "")
    if target_idx < 0:
        messages.append({"role": "user", "content": append_parts})
    else:
        msg = dict(messages[target_idx])
        original = msg.get("content")
        has_images = any(part.get("type") == "image_url" for part in append_parts)
        if isinstance(original, list):
            msg["content"] = [dict(part) if isinstance(part, dict) else part for part in original] + append_parts
        elif has_images:
            original_text = str(original or "").strip()
            original_parts = [{"type": "text", "text": original_text}] if original_text else []
            msg["content"] = original_parts + append_parts
        else:
            msg["content"] = (str(original or "").rstrip() + "\n\n" + context_text).strip()
        messages[target_idx] = msg
    body["messages"] = messages
    logger.info(
        "qq_group_activity_context_appended_to_user chars=%s images=%s",
        len(context_text),
        sum(1 for part in context_parts if part.get("type") == "image_url"),
    )
    return body


def _tool_trace_has_function(tool_trace: list, name: str) -> bool:
    expected = str(name or "").strip()
    if not expected:
        return False
    for item in tool_trace or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if isinstance(fn, dict) and str(fn.get("name") or "").strip() == expected:
            return True
        if str(item.get("name") or "").strip() == expected:
            return True
    return False


def _executed_tool_names_from_messages(messages: list) -> list[str]:
    names: list[str] = []
    for item in _collect_tool_trace_from_messages(messages or []):
        function = item.get("function") or {} if isinstance(item, dict) else {}
        name = str(function.get("name") or "").strip() if isinstance(function, dict) else ""
        if name and name not in names:
            names.append(name)
    return names


def _tool_trace_has_game_tool_loop(tool_trace: list) -> bool:
    try:
        from services.game_tool_runtime import tool_trace_has_game_marker

        if tool_trace_has_game_marker(tool_trace):
            return True
    except Exception as e:
        logger.debug("game tool trace marker check failed error=%s", e)
    return _tool_trace_has_function(tool_trace, "random_imitator_td")


def _tool_trace_has_random_imitator_td(tool_trace: list) -> bool:
    return _tool_trace_has_game_tool_loop(tool_trace)


def _game_tool_checkpoint_from_messages(messages: list) -> bool:
    try:
        from services.game_tool_runtime import game_tool_checkpoint_from_messages

        return game_tool_checkpoint_from_messages(messages)
    except Exception as e:
        logger.debug("game tool checkpoint extraction failed error=%s", e)
        return False


def _maybe_clear_qq_group_activity_context_for_private_reply(
    body: dict,
    *,
    reply_channel: str,
    reply_target: str,
) -> None:
    if _is_gateway_wakeup_request() or _is_du_daily_maintenance_request() or _is_followup_generation_request():
        return
    if str(reply_target or "").strip() == "qq_group_mention":
        return
    if str(reply_channel or "").strip().lower() not in {"tg", "qq", "wechat", "sumitalk"}:
        return
    last_user = _last_user_message((body or {}).get("messages") or [])
    if not isinstance(last_user, dict) or _message_content_chars(last_user.get("content")) <= 0:
        return
    if _clear_qq_group_activity_context("user_private_reply"):
        logger.info("qq_group_activity_context_cleared channel=%s target=%s", reply_channel, reply_target)


def _skip_claude_thinking_carryover_request() -> bool:
    return (request.headers.get("X-Skip-Claude-Thinking-Carryover") or "").strip().lower() in ("1", "true", "yes")


def _pioneer_session_component(value: object, limit: int) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text).strip("._:-")
    if not text:
        text = "default"
    return text[:limit]


def _build_pioneer_session_id(body: dict, headers: dict) -> str:
    salt = os.getenv("PIONEER_SESSION_ID_SALT", "v2").strip() or "v2"
    model = str((body or {}).get("model") or "").strip() or "model"
    window_id = str((headers or {}).get("X-Window-Id") or (body or {}).get("window_id") or "__default__").strip()
    channel = str((headers or {}).get("X-Reply-Channel") or "chat").strip().lower()
    digest_src = f"{salt}\n{channel}\n{model}\n{window_id}"
    digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:16]
    return "du-gateway:{salt}:{channel}:{model}:{window}:{digest}".format(
        salt=_pioneer_session_component(salt, 32),
        channel=_pioneer_session_component(channel, 32),
        model=_pioneer_session_component(model, 64),
        window=_pioneer_session_component(window_id, 96),
        digest=digest,
    )[:240]


def _attach_pioneer_session_id_header(req_headers: dict, body: dict, headers: dict, target_url: str) -> None:
    if not is_pioneer_url(target_url):
        return
    req_headers["X-Session-Id"] = _build_pioneer_session_id(body, headers)


def _stream_forward_to_ai(
    body: dict,
    headers: dict,
    *,
    prompt_cache_profile: Optional[dict] = None,
    cache_debug_sink=None,
):
    """流式转发：上游 SSE 原样逐行 yield；不再自动 fallback。"""
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        yield (
            "data: "
            + json.dumps({"error": _build_upstream_error_hint("当前 active 上游未配置")})
            + "\n\n"
        ).encode("utf-8")
        return
    req_headers = {"Content-Type": "application/json"}
    # 上游尽量禁用压缩：避免 gzip/deflate 造成上游缓冲、攒包后才吐，降低流式不确定性
    req_headers["Accept-Encoding"] = "identity"
    accept = str((headers or {}).get("Accept") or "").strip()
    if accept:
        req_headers["Accept"] = accept
    last_err = None
    for url, api_key in targets:
        body_send = dict(body)
        body_send.pop(DU_REQUEST_ID_BODY_KEY, None)
        body_send["stream"] = True
        # 若未带 max_tokens 或过小，则设下限，避免中转站默认截断
        if MAX_COMPLETION_TOKENS > 0:
            cur = body_send.get("max_tokens")
            if cur is None or (isinstance(cur, (int, float)) and int(cur) < MAX_COMPLETION_TOKENS):
                body_send["max_tokens"] = MAX_COMPLETION_TOKENS
                logger.info("转发已设 max_tokens=%s（原=%s）", MAX_COMPLETION_TOKENS, cur)
        # 经网关时请求体因注入会变大，便于排查「经网关截断、直连不截断」：打一条预估长度
        try:
            msg_len = sum(
                len(str(m.get("content") or "")) for m in (body_send.get("messages") or [])
            )
            logger.info("转发前 messages 总字符数约 %s（过大时上游可能因 input+output 超限截断输出）", msg_len)
        except Exception:
            pass
        h = dict(req_headers)
        if api_key:
            h["Authorization"] = f"Bearer {api_key}"
            if is_pioneer_url(url):
                h["X-API-Key"] = api_key
        try:
            body_send = _apply_active_model_request_policy(body_send, url)
            target_url = url
            body_send = _apply_openrouter_request_policy(body_send, url)
            is_cf_anthropic = is_cloudflare_anthropic_url(target_url)
            is_pioneer_anthropic = is_pioneer_anthropic_url(target_url)
            if not (is_cf_anthropic or is_pioneer_anthropic):
                stream_options = body_send.get("stream_options")
                stream_options = dict(stream_options) if isinstance(stream_options, dict) else {}
                stream_options["include_usage"] = True
                body_send["stream_options"] = stream_options
            if is_cf_anthropic or is_pioneer_anthropic:
                body_send = _openai_to_anthropic_request(
                    body_send,
                    target_url,
                    PIONEER_CLAUDE_CACHE_TTL if is_pioneer_anthropic else None,
                )
            if is_cf_anthropic:
                h = _cloudflare_anthropic_headers(h, target_url, api_key)
            _attach_pioneer_session_id_header(h, body_send, headers, target_url)
            # timeout 同时作 connect/read：流式时若超过该秒数未收到数据会 ReadTimeout 断流，过短会导致回复中途截断
            r = requests.post(target_url, headers=h, json=body_send, timeout=STREAM_TIMEOUT_SECONDS, stream=True)
            if r.status_code == 200:
                cache_debug_collector = _StreamCacheDebugCollector(
                    body_send,
                    target_url,
                    prompt_cache_profile,
                )
                if is_cf_anthropic or is_pioneer_anthropic:
                    for chunk in _anthropic_sse_to_openai_sse(r.iter_lines(), str(body_send.get("model") or request_model)):
                        cache_debug_collector.feed(chunk)
                        yield chunk
                    cache_debug = cache_debug_collector.build()
                    _learn_model_token_ratio(cache_debug)
                    if cache_debug_sink:
                        cache_debug_sink(cache_debug)
                    return
                last_data_line = None
                first_chunk_logged = False
                for line in r.iter_lines():
                    if line is not None:
                        if not first_chunk_logged and line.startswith(b"data:") and len(line) > 5:
                            logger.debug("流式收到首包（上游已开始推流）")
                            first_chunk_logged = True
                        if line.startswith(b"data: ") and b"[DONE]" not in line:
                            last_data_line = line
                        chunk = line + b"\n"
                        cache_debug_collector.feed(chunk)
                        yield chunk
                    else:
                        yield b"\n"
                # 流正常读完时打一条：stop=正常结束，length=被 max_tokens 截断，null/没有=异常中断
                if last_data_line:
                    try:
                        j = json.loads(last_data_line[6:].strip().decode("utf-8", errors="ignore"))
                        fr = (j.get("choices") or [{}])[0].get("finish_reason")
                        if fr is not None and fr != "":
                            logger.debug("流式上游结束 finish_reason=%s（stop=正常 length=max_tokens截断）", fr)
                        else:
                            logger.debug("流式上游结束 finish_reason=null或未提供（可能异常中断）")
                    except Exception:
                        logger.debug("流式上游结束 末包解析失败，无法读取 finish_reason")
                cache_debug = cache_debug_collector.build()
                _learn_model_token_ratio(cache_debug)
                if cache_debug_sink:
                    cache_debug_sink(cache_debug)
                return
            last_err = f"上游 HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
            logger.warning("流式转发异常 %s %s", url[:50], e)
    yield ("data: " + json.dumps({"error": _build_upstream_error_hint(last_err or "")}) + "\n\n").encode("utf-8")


def _stream_with_r2_archive(
    body: dict,
    headers: dict,
    window_id: str = "",
    reply_channel: str = "",
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
    skip_post_archive_dynamic_memory_write: bool = False,
    skip_post_archive_body_delta: bool = False,
    du_request_id: str = "",
    prompt_cache_profile: Optional[dict] = None,
    tool_executor=None,
    sumitalk_event_sink=None,
    watch_action_context: Optional[dict] = None,
):
    """
    包装流式响应：原样转发 SSE，同时在流结束后用收集到的 content 写 R2。
    当请求带 tools 时：先缓冲整段流，解析 message；若有 tool_calls 则执行工具并继续请求（循环），
    最后把「无 tool_calls」那一轮的流发给客户端，实现与 RikkaHub 类似的流式+工具行为。
    无 tools 时：边收边发，不缓冲，保持原有实时流式。
    """
    content_parts = []
    reasoning_parts = []
    archive_reasoning_stream = _ReasoningStreamAccumulator()
    reasoning_details_parts: list[dict] = []
    thinking_blocks_parts: list[dict] = []
    cache_debug_entries: list[dict] = []
    reasoning_omitted = False
    reply_channel = str(reply_channel or _reply_channel() or "").strip().lower()
    du_request_id = normalize_debug_request_id(du_request_id or (body or {}).get(DU_REQUEST_ID_BODY_KEY))
    last_user = _last_user_message(body.get("messages") or [])
    du_daily_maintenance = _is_du_daily_maintenance_request()
    pseudo_cot_stream_enabled = _pseudo_cot_instruction_enabled(body)
    emitted_listen_invite_actions: set[str] = set()
    emitted_watch_actions: set[str] = set()

    def _archive_completed_stream(
        request_messages: list,
        assistant_message: dict,
        round_cleaned: list | None,
        *,
        skip_dynamic_memory_write: bool,
        skip_body_delta: bool,
    ) -> None:
        if not sumitalk_event_sink:
            step_archive_and_maybe_summary(
                window_id,
                request_messages,
                assistant_message,
                round_cleaned_for_r2=round_cleaned,
                skip_dynamic_memory_write=skip_dynamic_memory_write,
                skip_body_delta=skip_body_delta,
            )
            logger.info("R2 流式请求已存档")
            return

        messages_snapshot = copy.deepcopy(request_messages)
        assistant_snapshot = copy.deepcopy(assistant_message)
        round_snapshot = copy.deepcopy(round_cleaned)
        _enqueue_sumitalk_stream_archive(
            (
                window_id,
                messages_snapshot,
                assistant_snapshot,
                round_snapshot,
                skip_dynamic_memory_write,
                skip_body_delta,
            )
        )
        logger.info("R2 SumiTalk 流式请求已交后台存档")

    def _emit_stream_event(kind: str, payload: dict | None = None) -> None:
        if not sumitalk_event_sink:
            return
        try:
            sumitalk_event_sink(kind, payload or {})
        except Exception:
            logger.debug("SumiTalk 流式事件回调失败 kind=%s", kind, exc_info=True)

    def _emit_listen_invite_actions(raw_text: str, messages: list[dict] | None) -> None:
        if not sumitalk_event_sink:
            return
        _visible, actions = _split_listen_invite_actions(raw_text)
        for action in actions:
            if action in emitted_listen_invite_actions:
                continue
            payload = _build_listen_invite_event(action, messages=messages)
            if not payload:
                continue
            emitted_listen_invite_actions.add(action)
            _emit_stream_event("listen_invite_action", payload)

    def _emit_watch_actions(raw_text: str) -> None:
        if not sumitalk_event_sink or not watch_action_context:
            return
        _visible, actions = _split_watch_actions(raw_text)
        for action in actions:
            payload = _build_watch_danmaku_event(action, context=watch_action_context)
            if not payload:
                continue
            dedup_key = _watch_action_dedup_key(payload)
            if dedup_key in emitted_watch_actions:
                continue
            emitted_watch_actions.add(dedup_key)
            _emit_stream_event("watch_danmaku_action", payload)
            break

    def _stream_event_text_chunks(text: str):
        value = str(text or "")
        for start in range(0, len(value), 1600):
            yield value[start : start + 1600]

    def _start_reasoning_stream_event(
        round_no: int,
        part_id: str,
        state: dict,
        mode: str,
    ) -> None:
        if state.get("started") or state.get("finished"):
            return
        _emit_stream_event(
            "reasoning_started",
            {"part_id": part_id, "round": round_no, "mode": mode},
        )
        state["started"] = True

    def _emit_reasoning_update(
        update: tuple[str, str] | None,
        round_no: int,
        part_id: str,
        state: dict,
    ) -> None:
        if not update or state.get("finished"):
            return
        mode, text = update
        _start_reasoning_stream_event(round_no, part_id, state, mode)
        if mode == "snapshot":
            _emit_stream_event(
                "reasoning_delta",
                {
                    "part_id": part_id,
                    "round": round_no,
                    "mode": "snapshot",
                    "text": text,
                },
            )
            state["snapshot"] = True
            return
        for event_text in _stream_event_text_chunks(text):
            _emit_stream_event(
                "reasoning_delta",
                {
                    "part_id": part_id,
                    "round": round_no,
                    "mode": "delta",
                    "text": event_text,
                },
            )

    def _finish_reasoning_stream_event(round_no: int, part_id: str, state: dict) -> None:
        if not state.get("started") or state.get("finished"):
            return
        _emit_stream_event(
            "reasoning_finished",
            {
                "part_id": part_id,
                "round": round_no,
                "mode": "snapshot" if state.get("snapshot") else "delta",
                "omitted": bool(state.get("omitted")),
            },
        )
        state["finished"] = True

    def _emit_reasoning_snapshot(
        text: str,
        round_no: int,
        state: dict,
        *,
        omitted: bool = False,
        part_id: str = "",
    ) -> None:
        if state.get("finished"):
            return
        reasoning_text = str(text or "")
        if not reasoning_text and not omitted:
            return
        reasoning_part_id = part_id or f"reasoning-{round_no}"
        if omitted:
            state["omitted"] = True
        update = state["stream"].apply("structured", reasoning_text)
        _emit_reasoning_update(update, round_no, reasoning_part_id, state)
        if omitted and not state.get("started"):
            _start_reasoning_stream_event(round_no, reasoning_part_id, state, "snapshot")
        _finish_reasoning_stream_event(round_no, reasoning_part_id, state)

    def _emit_reasoning_chunk(chunk, round_no: int, part_id: str, state: dict) -> None:
        try:
            if state.get("finished"):
                return
            if not chunk.startswith(b"data: "):
                return
            raw = chunk[6:].strip()
            if not raw or raw == b"[DONE]":
                return
            packet = json.loads(raw.decode("utf-8", errors="ignore"))
            delta = ((packet.get("choices") or [{}])[0] or {}).get("delta") or {}
            source, reasoning_text, _details, omitted = _extract_reasoning_stream_source(delta)
            if omitted:
                state["omitted"] = True
            if not source:
                return
            update = state["stream"].apply(source, reasoning_text)
            _emit_reasoning_update(update, round_no, part_id, state)
            if source == "structured":
                if omitted and not state.get("started"):
                    _start_reasoning_stream_event(round_no, part_id, state, "snapshot")
                _finish_reasoning_stream_event(round_no, part_id, state)
        except Exception:
            return

    def _emit_assistant_text_value(
        text: str,
        round_no: int,
        part_id: str,
        state: dict,
    ) -> None:
        if not text:
            return
        if not state.get("started"):
            _emit_stream_event(
                "assistant_text_started",
                {"part_id": part_id, "round": round_no, "mode": "delta", "role": "assistant"},
            )
            state["started"] = True
        for event_text in _stream_event_text_chunks(text):
            _emit_stream_event(
                "assistant_delta",
                {
                    "part_id": part_id,
                    "round": round_no,
                    "mode": "delta",
                    "role": "assistant",
                    "text": event_text,
                },
            )

    def _emit_assistant_sse_chunk(
        chunk,
        round_no: int,
        part_id: str,
        state: dict,
        *,
        reasoning_part_id: str = "",
        reasoning_state: dict | None = None,
    ) -> None:
        try:
            text = chunk.decode("utf-8") if isinstance(chunk, (bytes, bytearray)) else str(chunk or "")
            for line in text.splitlines():
                if not line.startswith("data: ") or line[6:].strip() == "[DONE]":
                    continue
                packet = json.loads(line[6:])
                delta = (((packet.get("choices") or [{}])[0] or {}).get("delta") or {})
                content = delta.get("content")
                if isinstance(content, str) and content:
                    _emit_assistant_text_value(content, round_no, part_id, state)
        except Exception:
            return

    def _finish_assistant_stream_event(round_no: int, part_id: str, state: dict) -> None:
        if not state.get("started") or state.get("finished"):
            return
        _emit_stream_event(
            "assistant_text_finished",
            {"part_id": part_id, "round": round_no, "mode": "delta", "role": "assistant"},
        )
        state["finished"] = True

    def _emit_assistant_snapshot(text: str, round_no: int, *, part_id: str = "") -> None:
        visible_text = _normalize_visible_reply_text(text)
        if not visible_text:
            return
        snapshot_part_id = part_id or f"assistant-text-{round_no}"
        state = {"started": False, "finished": False}
        _emit_assistant_text_value(visible_text, round_no, snapshot_part_id, state)
        _finish_assistant_stream_event(round_no, snapshot_part_id, state)

    def _emit_stream_tool_event(kind: str, payload: dict, round_no: int) -> None:
        event_payload = dict(payload or {})
        tool_call_id = str(event_payload.get("tool_call_id") or "").strip()
        if tool_call_id:
            event_payload["part_id"] = f"tool-{tool_call_id}"
        if event_payload.get("result_preview") is not None and event_payload.get("output") is None:
            event_payload["output"] = event_payload.get("result_preview")
        event_payload["round"] = round_no
        event_payload["mode"] = "snapshot"
        if kind == "tool_call_started":
            _emit_stream_event(kind, event_payload)
            if event_payload.get("arguments"):
                _emit_stream_event(
                    "tool_arguments_delta",
                    {
                        **event_payload,
                        "arguments_delta": event_payload.get("arguments"),
                    },
                )
            return
        if kind == "tool_call_finished" and event_payload.get("output"):
            _emit_stream_event("tool_output_delta", event_payload)
        _emit_stream_event(kind, event_payload)

    def _collect_content_from_chunk(chunk):
        nonlocal reasoning_omitted
        try:
            if chunk.startswith(b"data: "):
                payload = chunk[6:].strip()
                if payload != b"[DONE]" and payload:
                    j = json.loads(payload.decode("utf-8", errors="ignore"))
                    delta = (j.get("choices") or [{}])[0].get("delta") or {}
                    raw_content = delta.get("content") or ""
                    if isinstance(raw_content, str) and raw_content:
                        # 如果 delta.content 里含有 <think> 块，提取到 reasoning_parts，
                        # 只把干净的正文放入 content_parts（对应 _strip_reasoning_from_sse_chunk 的客户端过滤）
                        if _THINK_BLOCK_RE.search(raw_content):
                            clean, _in_content_thinking = _extract_thinking_from_content(raw_content)
                            if clean:
                                content_parts.append(clean)
                        else:
                            content_parts.append(raw_content)
                    source, text, details, omitted = _extract_reasoning_stream_source(delta)
                    archive_reasoning_stream.apply(source, text)
                    if details:
                        reasoning_details_parts.extend(details)
                    for block in delta.get("thinking_blocks") or []:
                        if isinstance(block, dict):
                            thinking_blocks_parts.append(block)
                    if omitted:
                        reasoning_omitted = True
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    if not body.get("tools"):
        # 无工具：用「生产者线程+队列」解耦「读上游」和「发客户端」，避免发客户端慢拖累读上游导致上游断流
        data_chunk_count = 0
        stream_start = time.time()
        chunk_queue = queue.Queue()

        def _producer():
            try:
                for chunk in _stream_forward_to_ai(
                    body,
                    headers,
                    prompt_cache_profile=prompt_cache_profile,
                    cache_debug_sink=cache_debug_entries.append,
                ):
                    chunk_queue.put(chunk)
                chunk_queue.put(None)
            except Exception as e:
                logger.warning("流式生产异常 %s", e)
                chunk_queue.put(None)

        t = threading.Thread(target=_producer, daemon=True)
        t.start()
        heartbeat_s = max(0, int(STREAM_SSE_HEARTBEAT_SECONDS or 0))
        flush_ms = max(0, int(STREAM_SSE_FLUSH_MAX_MS or 0))
        flush_window_s = flush_ms / 1000.0
        last_send_ts = time.time()
        du_state = PcmdDuThoughtStreamState(dynamic_memory_citation_map)
        pseudo_cot_state = _PseudoCotStreamState() if pseudo_cot_stream_enabled else None
        assistant_part_id = "assistant-text-1"
        assistant_event_state = {"started": False, "finished": False}
        reasoning_part_id = "reasoning-1"
        reasoning_event_state = {
            "started": False,
            "finished": False,
            "omitted": False,
            "snapshot": False,
            "stream": _ReasoningStreamAccumulator(),
        }

        def _prepare_no_tool_chunk(raw_chunk):
            _collect_content_from_chunk(raw_chunk)
            _emit_reasoning_chunk(raw_chunk, 1, reasoning_part_id, reasoning_event_state)
            outgoing_chunk = _strip_reasoning_from_sse_chunk(raw_chunk)
            if pseudo_cot_state:
                outgoing_chunk = _transform_pseudo_cot_sse_chunk_bytes(
                    outgoing_chunk,
                    pseudo_cot_state,
                )
            outgoing_chunk = transform_sse_chunk_bytes_pcmd(outgoing_chunk, du_state)
            _emit_assistant_sse_chunk(
                outgoing_chunk,
                1,
                assistant_part_id,
                assistant_event_state,
                reasoning_part_id=reasoning_part_id,
                reasoning_state=reasoning_event_state,
            )
            return outgoing_chunk

        try:
            while True:
                buf = []
                # 第一次阻塞等待：用心跳间隔作为超时，避免下游长时间无任何数据
                try:
                    chunk = chunk_queue.get(timeout=heartbeat_s if heartbeat_s > 0 else None)
                except queue.Empty:
                    # 心跳：SSE comment，不影响客户端拼接内容
                    yield b": ping\n\n"
                    last_send_ts = time.time()
                    continue

                if chunk is None:
                    break

                chunk = _prepare_no_tool_chunk(chunk)
                buf.append(chunk)
                if chunk.startswith(b"data:") and len(chunk) > 5:
                    data_chunk_count += 1

                # 合并 flush：短窗口内尽量多取几块再发，减少小包抖动
                if flush_window_s > 0:
                    deadline = time.time() + flush_window_s
                    while True:
                        remaining = deadline - time.time()
                        if remaining <= 0:
                            break
                        try:
                            nxt = chunk_queue.get(timeout=remaining)
                        except queue.Empty:
                            break
                        if nxt is None:
                            chunk = None
                            break
                        nxt = _prepare_no_tool_chunk(nxt)
                        buf.append(nxt)
                        if nxt.startswith(b"data:") and len(nxt) > 5:
                            data_chunk_count += 1
                    if chunk is None:
                        # 先把缓冲发完再结束
                        yield b"".join(buf)
                        break

                yield b"".join(buf)
                last_send_ts = time.time()
        finally:
            _finish_reasoning_stream_event(1, reasoning_part_id, reasoning_event_state)
            _finish_assistant_stream_event(1, assistant_part_id, assistant_event_state)
            full_content = "".join(content_parts)
            visible_source, inner_os = _split_inner_os_from_text(full_content)
            _emit_listen_invite_actions(visible_source, body.get("messages") or [])
            _emit_watch_actions(visible_source)
            visible = _extract_and_store_hidden_sidecars(
                visible_source,
                window_id=window_id,
                du_daily_trigger=du_daily_trigger,
                dynamic_memory_citation_map=dynamic_memory_citation_map,
                source_messages=body.get("messages") or [],
                reply_channel=reply_channel,
                du_request_id=du_request_id,
            )
            full_reasoning = archive_reasoning_stream.text.strip()
            stream_sec = time.time() - stream_start
            # 若「流式持续时长」总是差不多（如 10–20s）而字数越来越短，可能是上游按时长限流
            logger.debug("本轮流式回复收集长度约 %s 字符，共转发 %s 个 data 块，流式持续约 %.1f 秒", len(full_content), data_chunk_count, stream_sec)
            if du_daily_maintenance:
                logger.info("R2 未存档：du_daily 内部维护请求跳过会话存档")
            elif not is_failed_response(visible) and visible.strip():
                msg = {"role": "assistant", "content": visible}
                msg["du_request_id"] = du_request_id
                if full_reasoning:
                    msg["reasoning"] = full_reasoning
                if reasoning_details_parts:
                    msg["reasoning_details"] = reasoning_details_parts
                if thinking_blocks_parts:
                    msg["thinking_blocks"] = thinking_blocks_parts
                if reasoning_omitted:
                    msg["reasoning_omitted"] = True
                if cache_debug_entries:
                    msg["cache_debug"] = list(cache_debug_entries)
                _apply_pseudo_cot_state_and_fallback(
                    window_id,
                    msg,
                    inner_os,
                    force_inner_os=pseudo_cot_stream_enabled,
                )
                round_cleaned = (
                    _build_round_cleaned_for_archive(
                        last_user,
                        msg,
                        reply_target=_reply_target(),
                        window_id=window_id,
                        request_messages=body.get("messages") or [],
                    )
                    if last_user
                    else None
                )
                logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
                _archive_completed_stream(
                    body.get("messages") or [],
                    msg,
                    round_cleaned,
                    skip_dynamic_memory_write=skip_post_archive_dynamic_memory_write,
                    skip_body_delta=skip_post_archive_body_delta,
                )
            elif is_failed_response(visible):
                logger.info("R2 未存档：流式回复被判为失败，跳过")
            elif not visible.strip():
                logger.info("R2 未存档：流式回复为空，跳过")
        return

    # 有 tools：缓冲 + 工具循环；保留中间轮可见正文，再与最终轮一起发给客户端。
    current_body = body
    max_tool_rounds = TOOL_MAX_ROUNDS
    max_processed_tool_rounds = max(0, int(max_tool_rounds))
    tool_rounds_used = 0
    tool_empty_final_retry_used = False
    tool_midstream_retry_used = False
    game_checkpoint_finalizing = False
    stream_attempt_no = 0
    reasoning_event_states: dict[int, dict] = {}
    tool_visible_content_parts: list[str] = []
    completed_tool_results: list[dict] = []
    tool_loop_finished = False
    final_thinking_blocks: list[dict] = []
    stream_inner_os_parts: list[str] = []
    try:
        while True:
            stream_attempt_no += 1
            event_round = tool_rounds_used + 1
            reasoning_part_id = f"reasoning-{event_round}"
            round_event_state = reasoning_event_states.setdefault(
                event_round,
                {
                    "started": False,
                    "finished": False,
                    "omitted": False,
                    "snapshot": False,
                    "stream": _ReasoningStreamAccumulator(),
                },
            )
            assistant_part_id = f"assistant-text-{event_round}-{stream_attempt_no}"
            assistant_event_state = {"started": False, "finished": False}
            assistant_du_state = PcmdDuThoughtStreamState(dynamic_memory_citation_map)
            assistant_pseudo_state = _PseudoCotStreamState() if pseudo_cot_stream_enabled else None
            chunks = []
            chunk_queue = queue.Queue()

            def _producer():
                try:
                    for chunk in _stream_forward_to_ai(
                        current_body,
                        headers,
                        prompt_cache_profile=prompt_cache_profile,
                        cache_debug_sink=cache_debug_entries.append,
                    ):
                        chunk_queue.put(chunk)
                except Exception as e:
                    logger.warning("工具流式生产异常 %s", e)
                finally:
                    chunk_queue.put(None)

            threading.Thread(target=_producer, daemon=True).start()
            heartbeat_s = max(0, int(STREAM_SSE_HEARTBEAT_SECONDS or 0))
            while True:
                try:
                    chunk = chunk_queue.get(timeout=heartbeat_s if heartbeat_s > 0 else None)
                except queue.Empty:
                    yield b": ping\n\n"
                    continue
                if chunk is None:
                    break
                chunks.append(chunk)
                _emit_reasoning_chunk(chunk, event_round, reasoning_part_id, round_event_state)
                assistant_chunk = _strip_reasoning_from_sse_chunk(chunk)
                if assistant_pseudo_state:
                    assistant_chunk = _transform_pseudo_cot_sse_chunk_bytes(
                        assistant_chunk,
                        assistant_pseudo_state,
                    )
                assistant_chunk = transform_sse_chunk_bytes_pcmd(assistant_chunk, assistant_du_state)
                _emit_assistant_sse_chunk(
                    assistant_chunk,
                    event_round,
                    assistant_part_id,
                    assistant_event_state,
                    reasoning_part_id=reasoning_part_id,
                    reasoning_state=round_event_state,
                )
            if len(chunks) == 1 and chunks[0].startswith(b"data: ") and b"error" in chunks[0]:
                _finish_reasoning_stream_event(
                    event_round,
                    reasoning_part_id,
                    round_event_state,
                )
                _finish_assistant_stream_event(
                    event_round,
                    assistant_part_id,
                    assistant_event_state,
                )
                yield chunks[0]
                return
            parsed = _parse_stream_to_message(chunks)
            if not round_event_state.get("started"):
                _emit_reasoning_snapshot(
                    str(parsed.get("reasoning") or ""),
                    event_round,
                    round_event_state,
                    omitted=bool(parsed.get("reasoning_omitted")),
                    part_id=reasoning_part_id,
                )
            else:
                _finish_reasoning_stream_event(
                    event_round,
                    reasoning_part_id,
                    round_event_state,
                )
            tool_calls = parsed.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                _finish_assistant_stream_event(
                    event_round,
                    assistant_part_id,
                    assistant_event_state,
                )
                if game_checkpoint_finalizing:
                    logger.warning(
                        "game tool checkpoint 收口时上游仍请求工具，已阻止继续执行 window_id=%s tool_calls=%s",
                        window_id,
                        len(tool_calls),
                    )
                    fallback = "由于防沉迷机制，暂时中止游戏回合。下次可以继续。"
                    archived_fallback = _merge_visible_tool_round_content(tool_visible_content_parts, fallback)
                    content_parts.append(archived_fallback)
                    _emit_assistant_snapshot(
                        fallback,
                        event_round,
                        part_id=f"assistant-fallback-{stream_attempt_no}",
                    )
                    tool_loop_finished = True
                    yield _sse_delta_chunk_bytes(fallback if sumitalk_event_sink else archived_fallback)
                    yield b"data: [DONE]\n\n"
                    break
                if tool_rounds_used >= max_processed_tool_rounds:
                    logger.warning(
                        "工具调用达到轮数上限(%s)，停止继续请求上游以控制费用；当前工具数=%s",
                        max_tool_rounds,
                        len(tool_calls),
                    )
                    cap_hint = "（已达到工具调用轮数上限，为控制费用已停止继续自动调工具。你可以让我基于现有结果继续回答。）"
                    archived_cap_hint = _merge_visible_tool_round_content(tool_visible_content_parts, cap_hint)
                    content_parts.append(archived_cap_hint)
                    _emit_assistant_snapshot(
                        cap_hint,
                        event_round,
                        part_id=f"assistant-cap-{stream_attempt_no}",
                    )
                    tool_loop_finished = True
                    yield _sse_delta_chunk_bytes(cap_hint if sumitalk_event_sink else archived_cap_hint)
                    yield b"data: [DONE]\n\n"
                    break
                execute_tool_func = tool_executor
                if execute_tool_func is None:
                    from services.chat_tools import execute_tool as execute_tool_func
                _append_visible_tool_round_content(tool_visible_content_parts, parsed.get("content") or "")
                msg = {"content": parsed.get("content") or None, "tool_calls": tool_calls}
                if parsed.get("reasoning"):
                    msg["reasoning"] = parsed.get("reasoning")
                    reasoning_parts.append(parsed.get("reasoning") or "")
                if parsed.get("reasoning_details"):
                    msg["reasoning_details"] = parsed.get("reasoning_details")
                    reasoning_details_parts.extend(parsed.get("reasoning_details") or [])
                if parsed.get("thinking_blocks"):
                    msg["thinking_blocks"] = parsed.get("thinking_blocks")
                if parsed.get("reasoning_omitted"):
                    msg["reasoning_omitted"] = True
                    reasoning_omitted = True
                current_round = tool_rounds_used + 1
                current_body = _append_tool_results_and_continue(
                    current_body,
                    msg,
                    tool_calls,
                    execute_tool_func,
                    on_tool_event=lambda kind, payload, round_no=current_round: _emit_stream_tool_event(
                        kind,
                        payload or {},
                        round_no,
                    ),
                    completed_tool_results=completed_tool_results,
                )
                tool_rounds_used += 1
                if _game_tool_checkpoint_from_messages(current_body.get("messages") or []):
                    logger.info("game tool checkpoint 流式回合转普通收口 window_id=%s round=%s", window_id, tool_rounds_used)
                    game_checkpoint_finalizing = True
                    continue
                continue
            if (
                tool_rounds_used > 0
                and (not tool_empty_final_retry_used)
                and (not game_checkpoint_finalizing)
                and _should_retry_tool_empty_final(parsed.get("content") or "")
            ):
                _finish_assistant_stream_event(
                    event_round,
                    assistant_part_id,
                    assistant_event_state,
                )
                logger.warning("工具续轮最终正文为空，流式路径触发一次强制收口补问")
                current_body = _inject_tool_empty_final_retry_instruction(current_body)
                tool_empty_final_retry_used = True
                continue
            if (
                tool_rounds_used > 0
                and (not tool_midstream_retry_used)
                and (not game_checkpoint_finalizing)
                and _should_retry_tool_followup(
                    parsed.get("content") or "",
                    parsed.get("reasoning") or "",
                )
            ):
                _finish_assistant_stream_event(
                    event_round,
                    assistant_part_id,
                    assistant_event_state,
                )
                logger.info("工具续轮命中中间态文本，流式路径触发一次内部补问重试")
                current_body = _inject_tool_midstream_retry_instruction(current_body)
                tool_midstream_retry_used = True
                continue
            du_state = PcmdDuThoughtStreamState(dynamic_memory_citation_map)
            pseudo_cot_state = _PseudoCotStreamState() if pseudo_cot_stream_enabled else None
            done_chunks = []
            raw_parsed_content = parsed.get("content") or ""
            final_parsed_content = dedupe_stream_sumitalk_cards(raw_parsed_content)
            archived_content = _merge_visible_tool_round_content(tool_visible_content_parts, final_parsed_content)
            archived_content, parsed_inner_os = _split_inner_os_from_text(archived_content)
            if parsed_inner_os:
                stream_inner_os_parts.append(parsed_inner_os)
            outgoing_content = final_parsed_content if sumitalk_event_sink else archived_content
            outgoing_content, _outgoing_inner_os = _split_inner_os_from_text(outgoing_content)
            if outgoing_content != raw_parsed_content:
                visible_content = du_state.feed_delta(outgoing_content)
                if visible_content:
                    yield _sse_delta_chunk_bytes(visible_content)
            else:
                for ch in chunks:
                    if _is_sse_done_chunk(ch):
                        done_chunks.append(ch)
                        continue
                    safe_chunk = _strip_reasoning_from_sse_chunk(ch)
                    if pseudo_cot_state:
                        safe_chunk = _transform_pseudo_cot_sse_chunk_bytes(safe_chunk, pseudo_cot_state)
                    yield transform_sse_chunk_bytes_pcmd(safe_chunk, du_state)
            content_parts.append(archived_content)
            if _reply_channel() == "sumitalk":
                extra_card = sumitalk_card_suffix_for_stream(archived_content, current_body.get("messages") or [])
                if extra_card:
                    _emit_assistant_text_value(
                        extra_card,
                        event_round,
                        assistant_part_id,
                        assistant_event_state,
                    )
                    yield _sse_delta_chunk_bytes(extra_card)
                    content_parts.append(extra_card)
            if parsed.get("reasoning"):
                reasoning_parts.append(parsed.get("reasoning") or "")
            if parsed.get("reasoning_details"):
                reasoning_details_parts.extend(parsed.get("reasoning_details") or [])
            if parsed.get("thinking_blocks"):
                final_thinking_blocks = [b for b in (parsed.get("thinking_blocks") or []) if isinstance(b, dict)]
            if parsed.get("reasoning_omitted"):
                reasoning_omitted = True
            _finish_assistant_stream_event(
                event_round,
                assistant_part_id,
                assistant_event_state,
            )
            tool_loop_finished = True
            if done_chunks:
                yield b"data: [DONE]\n\n"
            else:
                yield b"data: [DONE]\n\n"
            break
    finally:
        full_content = "".join(content_parts)
        visible_source, inner_os = _split_inner_os_from_text(full_content)
        _emit_listen_invite_actions(visible_source, current_body.get("messages") or [])
        _emit_watch_actions(visible_source)
        if not inner_os and stream_inner_os_parts:
            inner_os = "\n\n".join(part for part in stream_inner_os_parts if part).strip()
        visible = _extract_and_store_hidden_sidecars(
            visible_source,
            window_id=window_id,
            du_daily_trigger=du_daily_trigger,
            dynamic_memory_citation_map=dynamic_memory_citation_map,
            source_messages=body.get("messages") or [],
            reply_channel=reply_channel,
            du_request_id=du_request_id,
        )
        if not _disable_followup_request():
            try:
                cleaned_visible, queued = queue_followup(window_id=window_id, headers=headers, assistant_text=visible)
                if queued or cleaned_visible != visible:
                    visible = cleaned_visible
            except Exception:
                logger.warning("处理延迟续话标记失败 window_id=%s", window_id, exc_info=True)
        if tool_rounds_used > 0 and not visible.strip():
            logger.error("工具续轮结束但最终正文仍为空（流式路径） window_id=%s tool_rounds_used=%s", window_id, tool_rounds_used)
        full_reasoning = "".join(reasoning_parts).strip()
        logger.info("本轮流式回复收集长度约 %s 字符", len(full_content))
        if tool_loop_finished and completed_tool_results and visible.strip() and not is_failed_response(visible):
            inserted = _record_tool_result_loop(
                completed_tool_results,
                window_id=window_id,
                reply_channel=reply_channel,
                model=str(current_body.get("model") or body.get("model") or ""),
            )
            logger.info(
                "工具摘要缓存整轮写入 window_id=%s tools=%s inserted=%s",
                window_id,
                len(completed_tool_results),
                inserted,
            )
        if du_daily_maintenance:
            logger.info("R2 未存档：du_daily 内部维护请求跳过会话存档")
        elif is_failed_response(visible):
            logger.info("R2 未存档：流式回复被判为失败，跳过")
        elif not visible.strip():
            logger.info("R2 未存档：流式回复为空，跳过")
        else:
            msg = {"role": "assistant", "content": visible}
            msg["du_request_id"] = du_request_id
            if full_reasoning:
                msg["reasoning"] = full_reasoning
            if reasoning_details_parts:
                msg["reasoning_details"] = reasoning_details_parts
            if final_thinking_blocks:
                msg["thinking_blocks"] = final_thinking_blocks
            if reasoning_omitted:
                msg["reasoning_omitted"] = True
            if cache_debug_entries:
                msg["cache_debug"] = list(cache_debug_entries)
            _apply_pseudo_cot_state_and_fallback(
                window_id,
                msg,
                inner_os,
                force_inner_os=pseudo_cot_stream_enabled,
            )
            tc_trace = _collect_tool_trace_from_messages(current_body.get("messages") or [])
            if tc_trace:
                msg["tool_calls"] = tc_trace
            game_tool_used = _tool_trace_has_game_tool_loop(tc_trace)
            archive_skip_dynamic_memory_write = skip_post_archive_dynamic_memory_write or game_tool_used
            archive_skip_body_delta = skip_post_archive_body_delta or game_tool_used
            if game_tool_used:
                logger.info("game tool 回合命中，归档后动态记忆与 BODY delta 跳过 window_id=%s", window_id)
            round_cleaned = (
                _build_round_cleaned_for_archive(
                    last_user,
                    msg,
                    reply_target=_reply_target(),
                    window_id=window_id,
                    request_messages=current_body.get("messages") or [],
                )
                if last_user
                else None
            )
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            _archive_completed_stream(
                current_body.get("messages") or [],
                msg,
                round_cleaned,
                skip_dynamic_memory_write=archive_skip_dynamic_memory_write,
                skip_body_delta=archive_skip_body_delta,
            )


def _forward_to_ai(body: dict, headers: dict, prompt_cache_profile: Optional[dict] = None):
    """将请求体转发到配置的 AI 接口：仅一个 active 上游（不再自动 fallback）。
    返回 (response_json, status_code, error, cache_debug)。非流式。
    """
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        return None, 502, _build_upstream_error_hint("当前 active 上游未配置"), None
    last_err = None
    last_status = 502
    for i, (url, api_key) in enumerate(targets):
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"
            if is_pioneer_url(url):
                req_headers["X-API-Key"] = api_key
        for h in ("Accept", "Accept-Encoding"):
            if request.headers.get(h):
                req_headers[h] = request.headers.get(h)
        try:
            # 非流式：上游返回单 JSON，便于解析和存档。
            body_send = dict(body)
            body_send.pop(DU_REQUEST_ID_BODY_KEY, None)
            body_send["stream"] = False
            if MAX_COMPLETION_TOKENS > 0:
                cur = body_send.get("max_tokens")
                if cur is None or (isinstance(cur, (int, float)) and int(cur) < MAX_COMPLETION_TOKENS):
                    body_send["max_tokens"] = MAX_COMPLETION_TOKENS
                    logger.info("转发已设 max_tokens=%s（原=%s）", MAX_COMPLETION_TOKENS, cur)
            body_send = _apply_active_model_request_policy(body_send, url)
            target_url = url
            body_send = _apply_openrouter_request_policy(body_send, url)
            is_cf_anthropic = is_cloudflare_anthropic_url(target_url)
            is_pioneer_anthropic = is_pioneer_anthropic_url(target_url)
            if is_cf_anthropic or is_pioneer_anthropic:
                body_send = _openai_to_anthropic_request(
                    body_send,
                    target_url,
                    PIONEER_CLAUDE_CACHE_TTL if is_pioneer_anthropic else None,
                )
            if is_cf_anthropic:
                req_headers = _cloudflare_anthropic_headers(req_headers, target_url, api_key)
            _attach_pioneer_session_id_header(req_headers, body_send, headers, target_url)
            is_sumitalk_forward = str(headers.get("X-Reply-Channel") or request.headers.get("X-Reply-Channel") or "").strip().lower() == "sumitalk"
            upstream_started = time.time()
            if is_sumitalk_forward:
                sumitalk_logger.info(
                    "[SumiTalk] upstream_post_start url=%s model=%s messages=%s timeout=%s",
                    (target_url or "")[:80],
                    body_send.get("model") or "",
                    len(body_send.get("messages") or []) if isinstance(body_send.get("messages"), list) else 0,
                    STREAM_TIMEOUT_SECONDS,
                )
            r = requests.post(target_url, headers=req_headers, json=body_send, timeout=STREAM_TIMEOUT_SECONDS)
            upstream_elapsed_ms = int((time.time() - upstream_started) * 1000)
            if is_sumitalk_forward:
                sumitalk_logger.info(
                    "[SumiTalk] upstream_post_returned status=%s elapsed_ms=%s bytes=%s",
                    getattr(r, "status_code", None),
                    upstream_elapsed_ms,
                    len(getattr(r, "content", b"") or b""),
                )
            # 为排查上游 403：记录鉴权是否携带（不泄露 key），以及响应正文前缀
            try:
                api_key_len = len(api_key or "")
            except Exception:
                api_key_len = -1
            try:
                resp_text_preview = (r.text or "")[:300]
            except Exception:
                resp_text_preview = ""
            logger.warning(
                "Upstream resp hint: status=%s url=%s hasAuth=%s apiKeyLen=%s model=%s preview=%s",
                getattr(r, "status_code", None),
                (target_url or "")[:60],
                bool(api_key),
                api_key_len,
                (body_send.get("model") or ""),
                resp_text_preview,
            )
            try:
                data = r.json() if r.content else None
            except (ValueError, requests.exceptions.JSONDecodeError):
                # 上游返回了非 JSON（如 HTML 错误页、空 body、纯文本）
                preview = (r.text or "")[:200]
                if len((r.text or "")) > 200:
                    preview += "..."
                logger.warning(
                    "转发目标 %s 返回非 JSON status=%s body_preview=%s",
                    target_url[:50], r.status_code, preview,
                )
                last_status = r.status_code
                last_err = f"HTTP {r.status_code} 上游返回非 JSON：{preview}"
                continue
            # 只有 2xx 算成功，其余（4xx/5xx/429 等）直接失败（不再自动 fallback）
            if 200 <= r.status_code < 300:
                if is_cf_anthropic or is_pioneer_anthropic:
                    data = _anthropic_to_openai_response(data or {}, str(body_send.get("model") or request_model))
                cache_debug = _build_cache_debug_entry(body_send, target_url, prompt_cache_profile, data or {})
                _learn_model_token_ratio(cache_debug)
                usage_debug = cache_debug.get("usage") or {}
                profile_debug = cache_debug.get("request") or {}
                dynamic_breakdown_debug = ",".join(
                    f"{part.get('label') or '动态区'}≈{part.get('est_tokens')}"
                    for part in (profile_debug.get("dynamic_breakdown") or [])[:10]
                    if isinstance(part, dict)
                )
                logger.info(
                    "prompt_cache_debug host=%s model=%s static_est_tokens=%s dynamic_est_tokens=%s leading_est_tokens=%s cached_tokens=%s usage_returned=%s prompt_cache_key=%s dynamic_breakdown=%s",
                    profile_debug.get("upstream_host") or "",
                    profile_debug.get("model") or "",
                    profile_debug.get("static_prefix_est_tokens"),
                    profile_debug.get("dynamic_system_est_tokens"),
                    profile_debug.get("leading_system_est_tokens"),
                    usage_debug.get("cached_tokens"),
                    usage_debug.get("usage_returned"),
                    bool(profile_debug.get("prompt_cache_key")),
                    dynamic_breakdown_debug,
                )
                # DEBUG 时打出上游原始响应的结构与内容摘要，便于核对格式
                if data is not None and logger.isEnabledFor(10):  # DEBUG=10
                    try:
                        keys = list(data.keys()) if isinstance(data, dict) else []
                        choices = (data or {}).get("choices") or []
                        msg = (choices[0] or {}).get("message") if choices else None
                        msg_keys = list(msg.keys()) if isinstance(msg, dict) else []
                        content_preview = ""
                        if isinstance(msg, dict) and "content" in msg:
                            c = msg["content"]
                            content_preview = (c[:200] + "…") if isinstance(c, str) and len(c) > 200 else str(c)[:200]
                        logger.debug(
                            "上游原始响应 top_keys=%s choices[0].message keys=%s content_preview=%s full_sample=%s",
                            keys, msg_keys, content_preview,
                            json.dumps(data, ensure_ascii=False)[:2500],
                        )
                    except Exception:
                        pass
                return data, r.status_code, None, cache_debug
            last_status = r.status_code
            last_err = _extract_upstream_error_detail(data, r.status_code) or f"HTTP {r.status_code}"
            logger.warning("转发目标 %s 失败 %s（不再自动 fallback）", target_url[:50], r.status_code)
        except Exception as e:
            last_err = str(e)
            logger.warning("转发目标 %s 异常 %s（不再自动 fallback）", url[:50], e)
    return None, last_status, _build_upstream_error_hint(last_err or ""), None


def _is_du_daily_maintenance_request() -> bool:
    return str(request.headers.get("X-DU-DAILY-MAINTAIN") or "").strip().lower() in ("1", "true", "yes")


def _is_proactive_decision_request() -> bool:
    return str(request.headers.get("X-DU-PROACTIVE-DECISION") or "").strip().lower() in ("1", "true", "yes")


def _should_record_user_interaction_side_effects() -> bool:
    return not _is_du_daily_maintenance_request() and not _is_gateway_wakeup_request()


def _is_real_user_input_request(window_id: str, body: dict, *, reply_channel: str) -> bool:
    if not _should_record_user_interaction_side_effects():
        return False
    if (request.headers.get("X-TG-User-Input") or "").strip().lower() in ("1", "true", "yes"):
        return True
    return _is_cross_platform_tg_window_user_input(
        window_id,
        body,
        reply_channel=reply_channel,
        is_followup_generation=_is_followup_generation_request(),
    )


def _static_models_response():
    """用 GATEWAY_MODELS 拼成 OpenAI 风格的 /v1/models 响应。"""
    if not GATEWAY_MODELS:
        return None
    data = [
        {"id": mid, "object": "model", "created": 0}
        for mid in GATEWAY_MODELS
    ]
    return {"object": "list", "data": data}


@bp.route("/v1/models", methods=["GET"])
@bp.route("/models", methods=["GET"])
def list_models():
    """
    代理到中转站的 GET /v1/models，这样 RikkaHub 填网关地址时也能拉取到模型列表。
    禁止静态默认模型兜底：拉不到当前 active upstream 的真实模型列表时，直接报错。
    """
    targets = _get_forward_targets(None)
    if not targets:
        return jsonify({"error": _build_upstream_error_hint("当前 active 上游未配置")}), 502
    url, api_key = targets[0]
    if is_openrouter_url(url):
        data = openrouter_models_response()
        if data:
            return jsonify(data), 200
        return jsonify({"error": "OPENROUTER_FIXED_MODEL 未配置"}), 502
    if is_siliconflow_url(url):
        data = siliconflow_models_response()
        if data:
            return jsonify(data), 200
    if is_cloudflare_anthropic_url(url):
        models = cloudflare_claude_model_options(url)
        if not models:
            return jsonify({"error": "CLOUDFLARE_CLAUDE_MODELS 未配置"}), 502
        return jsonify({
            "object": "list",
            "data": [{"id": model, "object": "model", "created": 0} for model in models],
        }), 200
    models_url = _chat_url_to_models_url(url)
    if not models_url:
        return jsonify({"error": "无法解析模型列表地址"}), 502
    req_headers = {"Content-Type": "application/json"}
    if api_key:
        req_headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = requests.get(models_url, headers=req_headers, timeout=30)
        data = r.json() if r.content else None
        # 上游返回 2xx 且带 data 列表则直接用
        if r.status_code == 200 and data and isinstance(data.get("data"), list) and len(data.get("data", [])) > 0:
            if is_pioneer_url(url):
                raw_ids = [
                    str(item.get("id") or "").strip()
                    for item in data.get("data", [])
                    if isinstance(item, dict) and str(item.get("id") or "").strip()
                ]
                claude_ids = _pioneer_claude_model_options(raw_ids)
                if not claude_ids:
                    return jsonify({"error": "Pioneer 未返回 Claude 短模型名"}), 502
                data = {
                    "object": "list",
                    "data": [{"id": model, "object": "model", "created": 0} for model in claude_ids],
                }
            return jsonify(data), 200
        return jsonify(data or {"error": "上游未返回模型列表"}), r.status_code if r.status_code != 200 else 502
    except Exception as e:
        logger.warning("拉取模型列表失败 %s error=%s", models_url, e)
        return jsonify({"error": str(e)}), 502


@bp.route("/v1/chat/completions", methods=["POST"])
@bp.route("/chat/completions", methods=["POST"])
def chat_completions():
    """统一入口：所有请求走完整管道（清洗、注入、转发、存档），无开头过滤。支持 X-Window-Id / body.window_id（如 Telegram 用 tg_{user_id}）。"""
    body = request.get_json(silent=True) or {}
    body.pop(DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY, None)
    active_upstream_url = _get_active_upstream_url()
    reply_channel = _reply_channel()
    reply_target = _reply_target()
    is_sumitalk_request = reply_channel == "sumitalk"
    wenyou_player_tools_enabled = _wenyou_player_tool_mode_enabled()
    app_mode = str(body.pop("app_mode", "") or "").strip().lower()
    sumitalk_real_mode = bool(
        is_sumitalk_request
        and app_mode == "real"
    )
    req_model = str(upstream_store.get_cached_active_model(refresh_if_missing=False) or "").strip()
    if not req_model:
        if is_sumitalk_request:
            raw_messages = body.get("messages") if isinstance(body, dict) else []
            sumitalk_logger.warning(
                "chat_request_reject reason=missing_model target=%s messages=%s remote=%s ua=%s",
                reply_target,
                len(raw_messages or []) if isinstance(raw_messages, list) else 0,
                request.remote_addr,
                (request.headers.get("User-Agent") or "")[:120],
            )
        return jsonify({"error": "当前未设置全局模型"}), 400
    body["model"] = req_model
    body = _apply_openrouter_request_policy(body, active_upstream_url)
    headers = dict(request.headers) if request.headers else {}
    window_id = _get_window_id_from_request(body)
    # 未传 id 的客户端（如 RikkaHub）与 R2 主存 __default__ 对齐，否则轮次恒为 1、总结永不触发
    window_id = r2_store.normalize_window_id(window_id)
    headers["X-Window-Id"] = window_id
    du_request_id = normalize_debug_request_id(body.get(DU_REQUEST_ID_BODY_KEY)) or f"du-{uuid.uuid4().hex}"
    body[DU_REQUEST_ID_BODY_KEY] = du_request_id
    sumitalk_job_id = (
        str(request.headers.get("X-SumiTalk-Job-Id") or "").strip()
        if is_sumitalk_request
        else ""
    )
    sumitalk_client_request_id = str((body or {}).get("client_request_id") or "").strip() if is_sumitalk_request else ""
    if is_sumitalk_request:
        try:
            from services.recall_message_targets import consume_recall_targets_from_body

            consume_recall_targets_from_body(
                body,
                window_id=window_id,
                client_request_id=sumitalk_client_request_id,
            )
        except Exception:
            sumitalk_logger.debug(
                "recall_targets_consume_failed window_id=%s client_request_id=%s",
                window_id,
                sumitalk_client_request_id,
                exc_info=True,
            )
    elif isinstance(body, dict):
        body.pop("recall_targets", None)
        body.pop("recallTargets", None)

    def _emit_sumitalk_chat_event(kind: str, payload: dict | None = None) -> None:
        if not (is_sumitalk_request and sumitalk_job_id):
            return
        try:
            from services.sumitalk_chat_queue import emit_live_sumitalk_chat_job_event

            normalized_payload = dict(payload or {})
            if str(kind or "").startswith("tool_"):
                tool_call_id = str(normalized_payload.get("tool_call_id") or "").strip()
                if tool_call_id and not normalized_payload.get("part_id"):
                    normalized_payload["part_id"] = f"tool-{tool_call_id}"
                if normalized_payload.get("result_preview") is not None and normalized_payload.get("output") is None:
                    normalized_payload["output"] = normalized_payload.get("result_preview")
            event = emit_live_sumitalk_chat_job_event(
                sumitalk_job_id,
                kind,
                {
                    "job_id": sumitalk_job_id,
                    "client_request_id": sumitalk_client_request_id,
                    "window_id": window_id,
                    **normalized_payload,
                },
            )
            if event:
                event_log = sumitalk_logger.debug if str(kind or "").endswith("_delta") else sumitalk_logger.info
                event_log(
                    "sumitalk_chat_event_emitted job_id=%s kind=%s seq=%s round=%s name=%s text_chars=%s",
                    sumitalk_job_id,
                    kind,
                    event.get("seq"),
                    event.get("round"),
                    event.get("name") or "",
                    len(str(event.get("text") or "")),
                )
        except Exception:
            sumitalk_logger.debug(
                "sumitalk_chat_event_emit_failed job_id=%s kind=%s",
                sumitalk_job_id,
                kind,
                exc_info=True,
            )

    def _execute_tool_with_chat_context(name: str, arguments: dict) -> str:
        from services.chat_tools import execute_tool

        return execute_tool(
            name,
            arguments if isinstance(arguments, dict) else {},
            context={
                "reply_target": reply_target,
                "reply_channel": reply_channel,
                "window_id": window_id,
                "client_request_id": sumitalk_client_request_id,
            },
        )

    # 记录最近窗口，供 MiniApp 思维链面板展示可选窗口列表
    try:
        wid_for_recent = window_id if (window_id or "").strip() else "__default__"
        recent_window_store.record_recent_window(wid_for_recent)
    except Exception:
        pass

    if is_sumitalk_request:
        raw_messages = body.get("messages") if isinstance(body, dict) else []
        last_user = _last_user_message(raw_messages if isinstance(raw_messages, list) else [])
        sumitalk_logger.info(
            "chat_request_received window_id=%s target=%s model=%s stream=%s messages=%s last_user_chars=%s force_last4=%s remote=%s ua=%s",
            window_id,
            reply_target,
            req_model,
            bool(body.get("stream")),
            len(raw_messages or []) if isinstance(raw_messages, list) else 0,
            _message_content_chars((last_user or {}).get("content")),
            (request.headers.get("X-Force-Last4") or "").strip(),
            request.remote_addr,
            (request.headers.get("User-Agent") or "")[:120],
        )

    def _stream_response(gen, *, sumitalk_rich_events: bool = False, degraded_reason: str = ""):
        response_headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        if sumitalk_rich_events and is_sumitalk_request and sumitalk_job_id:
            response_headers["X-SumiTalk-Rich-Events"] = "1"
        if str(degraded_reason or "").strip():
            response_headers["X-Du-Stream-Degraded"] = str(degraded_reason).strip()
        return Response(
            stream_with_context(gen),
            mimetype="text/event-stream",
            headers=response_headers,
        )

    def _sse_from_nonstream_response(resp: dict):
        msg = (((resp or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        content_text = get_assistant_content_text(msg) if isinstance(msg, dict) else ""
        if content_text:
            visible_text = _extract_and_store_hidden_sidecars(
                content_text,
                window_id=window_id,
                du_daily_trigger=du_daily_trigger,
                dynamic_memory_citation_map=dynamic_memory_citation_map,
                source_messages=body.get("messages") or [],
                reply_channel=reply_channel,
                du_request_id=du_request_id,
            )
            if visible_text:
                yield _sse_delta_chunk_bytes(visible_text)
        yield b"data: [DONE]\n\n"

    def _sse_error(message: str):
        yield ("data: " + json.dumps({"error": message or "upstream error"}, ensure_ascii=False) + "\n\n").encode("utf-8")
        yield b"data: [DONE]\n\n"

    million_plan_turn_id = _million_plan_turn_id_from_request() if _is_million_plan_request() else ""
    if million_plan_turn_id:
        archived_content = _million_plan_archived_content(window_id, million_plan_turn_id)
        if archived_content:
            logger.info(
                "million_plan_replay_hit window_id=%s turn_id=%s chars=%s",
                window_id,
                million_plan_turn_id,
                len(archived_content),
            )
            if body.get("stream"):
                def _million_plan_replay_stream():
                    yield _sse_delta_chunk_bytes(archived_content)
                    yield b"data: [DONE]\n\n"

                return _stream_response(_million_plan_replay_stream())
            return jsonify(_million_plan_replay_response(archived_content, model=req_model)), 200
        if _truthy_header("X-Million-Plan-Replay-Only"):
            logger.info("million_plan_replay_pending window_id=%s turn_id=%s", window_id, million_plan_turn_id)
            return jsonify({"million_plan_replay_pending": True, "turn_id": million_plan_turn_id}), 202

    if _is_suspected_rikkahub_phantom_one(body, window_id, headers):
        logger.warning("命中 RikkaHub 幽灵1保护：window_id=%s ua=%s", window_id, (headers.get("User-Agent") or "")[:80])
        if body.get("stream"):
            def _ghost_noop_stream():
                yield _sse_delta_chunk_bytes("（检测到客户端误触发，已忽略本次空输入）")
                yield b"data: [DONE]\n\n"

            return _stream_response(_ghost_noop_stream())
        return jsonify(_build_noop_chat_response(body)), 200

    if _should_record_user_interaction_side_effects():
        _maybe_mark_tg_window_user_activity(
            window_id,
            body,
            reply_channel=reply_channel,
            is_followup_generation=_is_followup_generation_request(),
        )
        _maybe_record_last_reply_channel(
            window_id,
            body,
            reply_channel=reply_channel,
            reply_target=reply_target,
            is_followup_generation=_is_followup_generation_request(),
            is_du_daily_maintenance=_is_du_daily_maintenance_request(),
        )
        _maybe_clear_qq_group_activity_context_for_private_reply(
            body,
            reply_channel=reply_channel,
            reply_target=reply_target,
        )

    # QQ 群活动图片先进入消息体，随后统一走 base64 压缩；该类上下文图不生成图片描述。
    body = _inject_qq_group_activity_context(body)
    # 走完整管道（清洗、注入记忆/总结、转发、存档）
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_replace_rikka_system(body)
    body = step_inject_thinking_block_rules(body)
    body = step_inject_core_behavior_rules(body)
    body = step_inject_du_non_retreat_rules(body)
    body = step_inject_common_knowledge(body)
    body = step_inject_pending_thought_rules(body)
    body = _inject_entry_style_system(
        body,
        reply_channel=reply_channel,
        is_miniapp=_is_miniapp_request(),
        speaker=_xiaoai_speaker_from_request(),
    )
    body = _inject_million_plan_player_prompt_if_enabled(body)
    body = _inject_codex_oauth_prompt_system(body, upstream_url=_get_active_upstream_url())
    body = _inject_channel_nsfw_system(body, reply_channel=reply_channel)
    if reply_channel != "xiaoai" and not _disable_followup_request():
        body = _inject_followup_instruction(
            body,
            is_followup_generation=_is_followup_generation_request(),
            should_archive=_should_archive_followup_generation_request(),
        )
    force_last4 = (request.headers.get("X-Force-Last4") or "").strip().lower() in ("1", "true", "yes")
    tg_user_input = _is_real_user_input_request(
        window_id,
        body,
        reply_channel=reply_channel,
    )
    slim_voice_call = (request.headers.get("X-Voice-Call-Slim") or "").strip().lower() in ("1", "true", "yes")
    if slim_voice_call:
        body = _inject_voice_call_style_system(body)
    skip_dynamic_memory = _skip_dynamic_memory_request() or slim_voice_call
    skip_post_archive_dynamic_memory_write = _skip_post_archive_dynamic_memory_request()
    skip_post_archive_body_delta = _skip_post_archive_body_delta_request()
    game_tool_loop = _is_game_tool_loop_request()
    random_imitator_td_tool_mode = _random_imitator_td_tool_mode_enabled()
    du_daily_maintenance = _is_du_daily_maintenance_request()
    du_daily_trigger = build_du_daily_trigger(window_id, body, headers)
    if not du_daily_maintenance and not _is_gateway_wakeup_request() and not game_tool_loop:
        try:
            last_user_for_home = _last_user_message(body.get("messages") or [])
            maybe_update_xinyue_state_from_user_text(_plain_message_text(last_user_for_home))
        except Exception as e:
            logger.debug("pixel_home user state inference skipped error=%s", e)
    body = step_inject_current_base_model(body)
    body = step_inject_system_alarm_action_result(body, window_id)
    body = step_inject_pseudo_cot_inner_os(body, window_id)
    body = step_inject_du_thought(body, window_id)
    body = step_inject_pending_thoughts(body, window_id)
    body = step_inject_secret_drawer(body, window_id)
    body = step_inject_wakeup_frame(body, window_id)
    body = step_inject_du_vitals(body, window_id)
    body = step_inject_du_daily(body, window_id, trigger=du_daily_trigger, maintenance_mode=du_daily_maintenance)
    body = step_inject_pixel_home(body, window_id)
    if not skip_dynamic_memory:
        body = step_inject_dynamic_memory(body, window_id)
    body = step_inject_humor_memes(body)
    body = step_inject_sumitalk_real_mode(
        body,
        enabled=sumitalk_real_mode,
        app_request=is_sumitalk_request,
    )
    body = step_inject_play_note(body)
    body = step_inject_summary(body, window_id, is_user_input=tg_user_input)
    body = step_inject_sense_snapshot(body, window_id)
    body = step_inject_latest_4_rounds_for_new_window(body, window_id, force_last4=force_last4)
    body = step_inject_interaction_candidate(body, window_id)
    if not du_daily_maintenance:
        body = step_inject_rikkahub_reminder(body, window_id)
    body = step_inject_stay_with_du(body)
    body = step_inject_du_notebook(body)
    body = step_inject_wenyou_player_tools(body, enabled=wenyou_player_tools_enabled)
    body = step_inject_gateway_tools(body)
    if game_tool_loop or random_imitator_td_tool_mode:
        body = step_inject_random_imitator_td_tools(body)
    body = step_inject_chat_tools(body)
    body = step_inject_forum_tools(body)
    body = step_inject_amap_mcp_tools(body)
    body = step_inject_websearch_tools(body)
    body = step_inject_reference_note(body)
    body = step_inject_du_midterm_memory(body, window_id)
    body = _inject_music_bgm_context(body, reply_channel=reply_channel)
    body = _inject_listen_invite_protocol(body, reply_channel=reply_channel)
    body, watch_action_context = _inject_watch_context(
        body,
        window_id=window_id,
        reply_channel=reply_channel,
    )
    active_upstream_url = _get_active_upstream_url()
    body = _inject_silence_mode_system(body, is_du_daily_maintenance=du_daily_maintenance)
    if (
        _is_local_claude_oauth_proxy_url(active_upstream_url) or is_cloudflare_anthropic_url(active_upstream_url)
    ) and not _skip_claude_thinking_carryover_request():
        body = _inject_previous_claude_thinking_blocks(body, window_id)
    body = step_inject_tool_result_cache(body)
    body = step_trim_messages_if_over_limit(body)
    body = _move_dynamic_systems_after_static_prefix(body)
    dynamic_memory_citation_map = normalize_citation_map(body.pop(DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY, None))
    prompt_cache_profile = _build_prompt_cache_profile(body, active_upstream_url)
    client_requested_stream = bool(body.get("stream"))
    openrouter_forced_nonstream = client_requested_stream and is_openrouter_url(active_upstream_url)
    if openrouter_forced_nonstream:
        body["stream"] = False
        logger.info(
            "OpenRouter 上游强制非流式转发，稍后按 SSE 回给客户端 window_id=%s model=%s",
            window_id,
            body.get("model") or "",
        )
    # Claude OAuth / Pioneer / Cloudflare Anthropic 会处理缓存断点；普通 OpenAI 上游继续清掉网关内部标记。
    preserve_dynamic_marker = (
        _is_local_claude_oauth_proxy_url(active_upstream_url)
        or is_pioneer_url(active_upstream_url)
        or is_cloudflare_anthropic_url(active_upstream_url)
    )
    for msg in body.get("messages") or []:
        if not preserve_dynamic_marker:
            msg.pop("__dynamic__", None)
            msg.pop("__summary_cache__", None)
            msg.pop("__summary_recent__", None)
            msg.pop("__tool_result_cache__", None)
            msg.pop("__sumitalk_real_mode__", None)
            msg.pop("__play_note__", None)
    if body.get("stream"):
        if is_sumitalk_request:
            sumitalk_logger.info(
                "chat_stream_start window_id=%s target=%s model=%s messages=%s",
                window_id,
                reply_target,
                req_model,
                len(body.get("messages") or []) if isinstance(body.get("messages"), list) else 0,
            )
        return _stream_response(
            _stream_with_r2_archive(
                body,
                headers,
                window_id,
                reply_channel=reply_channel,
                du_daily_trigger=du_daily_trigger,
                dynamic_memory_citation_map=dynamic_memory_citation_map,
                skip_post_archive_dynamic_memory_write=skip_post_archive_dynamic_memory_write,
                skip_post_archive_body_delta=skip_post_archive_body_delta,
                du_request_id=du_request_id,
                prompt_cache_profile=prompt_cache_profile,
                tool_executor=_execute_tool_with_chat_context,
                sumitalk_event_sink=_emit_sumitalk_chat_event if is_sumitalk_request else None,
                watch_action_context=watch_action_context,
            ),
            sumitalk_rich_events=True,
        )
    resp_json, status, err, cache_debug = _forward_to_ai(body, headers, prompt_cache_profile)
    cache_debug_entries = [cache_debug] if cache_debug else []
    if err:
        if is_sumitalk_request:
            sumitalk_logger.error(
                "chat_forward_failed window_id=%s target=%s status=%s error=%s",
                window_id,
                reply_target,
                status,
                err,
            )
        logger.error("Chat 转发失败 error=%s", err, exc_info=True)
        if openrouter_forced_nonstream:
            return _stream_response(_sse_error(err), degraded_reason="upstream_nonstream")
        return jsonify({"error": err}), status
    if status >= 400:
        if is_sumitalk_request:
            sumitalk_logger.warning(
                "chat_upstream_status_error window_id=%s target=%s status=%s body_keys=%s",
                window_id,
                reply_target,
                status,
                list(resp_json.keys()) if isinstance(resp_json, dict) else [],
            )
        logger.warning("Chat 上游返回异常 status=%s", status)
        if openrouter_forced_nonstream:
            return _stream_response(
                _sse_error(_extract_upstream_error_detail(resp_json, status) or "upstream error"),
                degraded_reason="upstream_nonstream",
            )
        return jsonify(resp_json or {"error": "upstream error"}), status
    # 非流式工具循环：执行 tool_calls 并继续请求，直到无 tool_calls 或达到最大轮数
    # 收集中间轮次 reasoning 供 MiniApp 思维链面板使用，但不回填到返回给客户端的 resp_json，
    # 避免客户端（RikkaHub 等）把 reasoning 渲染成对话内容。
    accumulated_reasoning_parts: list[str] = []
    accumulated_reasoning_details: list[dict] = []
    accumulated_reasoning_details_seen: set[str] = set()
    accumulated_reasoning_omitted = False
    accumulated_tool_visible_parts: list[str] = []

    def _reasoning_text_fingerprint(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    def _append_unique_reasoning_text(parts: list[str], text: str) -> None:
        text = str(text or "").strip()
        key = _reasoning_text_fingerprint(text)
        if not key:
            return
        for idx, existing in enumerate(parts):
            existing_key = _reasoning_text_fingerprint(existing)
            if key == existing_key or key in existing_key:
                return
            if existing_key and existing_key in key:
                parts[idx] = text
                return
        parts.append(text)

    def _reasoning_detail_fingerprint(item: dict) -> str:
        try:
            return json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(item)

    def _extend_unique_reasoning_details(target: list[dict], details: list[dict]) -> None:
        for detail in details or []:
            if not isinstance(detail, dict):
                continue
            key = _reasoning_detail_fingerprint(detail)
            if key in accumulated_reasoning_details_seen:
                continue
            accumulated_reasoning_details_seen.add(key)
            target.append(detail)

    def _accumulate_nonstream_reasoning(msg_obj: dict) -> None:
        nonlocal accumulated_reasoning_omitted
        if not isinstance(msg_obj, dict):
            return
        text, details, omitted = _extract_reasoning_text_and_details(msg_obj)
        if text:
            _append_unique_reasoning_text(accumulated_reasoning_parts, text)
        if details:
            _extend_unique_reasoning_details(accumulated_reasoning_details, details)
        if omitted:
            accumulated_reasoning_omitted = True

    def _merged_nonstream_reasoning_text(existing_reasoning_text: str = "") -> str:
        merged_parts = list(accumulated_reasoning_parts)
        _append_unique_reasoning_text(merged_parts, existing_reasoning_text)
        return "\n\n".join(merged_parts).strip()

    def _emit_sumitalk_reasoning_event(msg_obj: dict, round_no: int) -> None:
        if not isinstance(msg_obj, dict):
            return
        try:
            reasoning_event_text, _reasoning_event_details, reasoning_event_omitted = _extract_reasoning_text_and_details(msg_obj)
            if reasoning_event_text or reasoning_event_omitted:
                _emit_sumitalk_chat_event(
                    "assistant_reasoning",
                    {
                        "round": round_no,
                        "text": reasoning_event_text,
                        "omitted": bool(reasoning_event_omitted),
                    },
                )
        except Exception:
            sumitalk_logger.debug(
                "sumitalk_reasoning_event_emit_failed job_id=%s round=%s",
                sumitalk_job_id,
                round_no,
                exc_info=True,
            )

    max_tool_rounds = TOOL_MAX_ROUNDS
    max_processed_tool_rounds = max(0, int(max_tool_rounds))
    tool_rounds_used = 0
    completed_tool_results: list[dict] = []
    tool_loop_finished = False
    tool_empty_final_retry_used = False
    tool_midstream_retry_used = False
    game_checkpoint_finalizing = False
    allow_tool_only_reply = _allow_tool_only_reply_request()
    tool_only_reply_done = False
    while True:
        msg = (resp_json or {}).get("choices") and (resp_json.get("choices") or [{}])[0].get("message")
        tool_calls = (msg or {}).get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            if game_checkpoint_finalizing:
                logger.warning(
                    "game tool checkpoint 收口时上游仍请求工具，已阻止继续执行 window_id=%s tool_calls=%s",
                    window_id,
                    len(tool_calls),
                )
                resp_json = _force_game_checkpoint_final_response(resp_json)
                tool_loop_finished = True
                break
            if tool_rounds_used >= max_processed_tool_rounds:
                tool_loop_finished = True
                break
            if isinstance(msg, dict):
                _accumulate_nonstream_reasoning(msg)
                _emit_sumitalk_reasoning_event(msg, tool_rounds_used + 1)
                _append_visible_tool_round_content(accumulated_tool_visible_parts, msg.get("content"))
                visible_tool_content = _normalize_visible_reply_text(get_assistant_content_text(msg))
                if visible_tool_content:
                    _emit_sumitalk_chat_event(
                        "assistant_text",
                        {
                            "round": tool_rounds_used + 1,
                            "text": visible_tool_content,
                        },
                    )
            current_round = tool_rounds_used + 1
            body = _append_tool_results_and_continue(
                body,
                msg,
                tool_calls,
                _execute_tool_with_chat_context,
                on_tool_event=lambda kind, payload, round_no=current_round: _emit_sumitalk_chat_event(
                    kind,
                    {
                        "round": round_no,
                        **(payload or {}),
                    },
                ),
                completed_tool_results=completed_tool_results,
            )
            tool_rounds_used += 1
            if _game_tool_checkpoint_from_messages(body.get("messages") or []):
                logger.info("game tool checkpoint 非流式回合转普通收口 window_id=%s round=%s", window_id, tool_rounds_used)
                game_checkpoint_finalizing = True
                resp_json, status, err, cache_debug = _forward_to_ai(body, headers, prompt_cache_profile)
                if cache_debug:
                    cache_debug_entries.append(cache_debug)
                if err or status >= 400:
                    break
                continue
            resp_json, status, err, cache_debug = _forward_to_ai(body, headers, prompt_cache_profile)
            if cache_debug:
                cache_debug_entries.append(cache_debug)
            if err or status >= 400:
                break
            continue
        visible_content_text = _normalize_visible_reply_text(
            get_assistant_content_text(msg or {}) if isinstance(msg, dict) else ""
        )
        if (
            tool_rounds_used > 0
            and (not tool_empty_final_retry_used)
            and (not game_checkpoint_finalizing)
            and (not allow_tool_only_reply)
            and _should_retry_tool_empty_final(visible_content_text)
        ):
            logger.warning("工具续轮最终正文为空，非流式路径触发一次强制收口补问")
            body = _inject_tool_empty_final_retry_instruction(body)
            tool_empty_final_retry_used = True
            resp_json, status, err, cache_debug = _forward_to_ai(body, headers, prompt_cache_profile)
            if cache_debug:
                cache_debug_entries.append(cache_debug)
            if err or status >= 400:
                break
            continue
        if (
            tool_rounds_used > 0
            and (not tool_midstream_retry_used)
            and (not game_checkpoint_finalizing)
            and _should_retry_tool_followup(
                visible_content_text,
                str((msg or {}).get("reasoning") or (msg or {}).get("reasoning_content") or (msg or {}).get("thinking") or ""),
            )
        ):
            logger.info("工具续轮命中中间态文本，非流式路径触发一次内部补问重试")
            body = _inject_tool_midstream_retry_instruction(body)
            tool_midstream_retry_used = True
            resp_json, status, err, cache_debug = _forward_to_ai(body, headers, prompt_cache_profile)
            if cache_debug:
                cache_debug_entries.append(cache_debug)
            if err or status >= 400:
                break
            continue
        if isinstance(msg, dict):
            _accumulate_nonstream_reasoning(msg)
            if tool_rounds_used > 0:
                _emit_sumitalk_reasoning_event(msg, tool_rounds_used + 1)
            tool_loop_finished = True
            break
    if allow_tool_only_reply and resp_json and tool_rounds_used > 0:
        tool_trace_for_tool_only = _collect_tool_trace_from_messages(body.get("messages") or [])
        if _tool_trace_has_function(tool_trace_for_tool_only, "exchange_diary_comment_create"):
            try:
                choices = resp_json.get("choices") or []
                if choices:
                    final_msg = dict((choices[0] or {}).get("message") or {})
                    final_msg["content"] = "（已回复交换日记评论）"
                    final_msg["tool_only_reply_done"] = True
                    choices[0]["message"] = final_msg
                    resp_json["choices"] = choices
                    tool_only_reply_done = True
            except Exception:
                logger.warning("标记交换日记评论工具-only 回复失败 window_id=%s", window_id, exc_info=True)
    if resp_json and not tool_only_reply_done:
        resp_json = _merge_visible_tool_round_content_into_response(resp_json, accumulated_tool_visible_parts)
    if resp_json and tool_rounds_used > 0:
        final_msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        final_visible = _normalize_visible_reply_text(
            get_assistant_content_text(final_msg) if isinstance(final_msg, dict) else ""
        )
        if not final_visible:
            logger.error("工具续轮结束但最终正文仍为空（非流式路径） window_id=%s tool_rounds_used=%s", window_id, tool_rounds_used)
    archive_thinking_blocks_for_r2: list[dict] = []
    if resp_json:
        resp_json, inner_os = _extract_inner_os_from_response_json(resp_json)
        pseudo_cot_response_enabled = _pseudo_cot_instruction_enabled(body)
        if pseudo_cot_response_enabled and inner_os:
            resp_json = _replace_response_reasoning_with_inner_os(resp_json, inner_os)
        if is_sumitalk_request:
            raw_assistant = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
            raw_assistant_text = get_assistant_content_text(raw_assistant) if isinstance(raw_assistant, dict) else ""
            _ignored_visible, listen_invite_actions = _split_listen_invite_actions(raw_assistant_text)
            for action in listen_invite_actions:
                payload = _build_listen_invite_event(action, messages=body.get("messages") or [])
                if payload:
                    _emit_sumitalk_chat_event("listen_invite_action", payload)
            _ignored_visible, watch_actions = _split_watch_actions(raw_assistant_text)
            emitted_watch_actions: set[str] = set()
            for action in watch_actions:
                payload = _build_watch_danmaku_event(action, context=watch_action_context)
                if not payload:
                    continue
                dedup_key = _watch_action_dedup_key(payload)
                if dedup_key in emitted_watch_actions:
                    continue
                emitted_watch_actions.add(dedup_key)
                _emit_sumitalk_chat_event("watch_danmaku_action", payload)
                break
        resp_json = _apply_hidden_sidecars_to_assistant_response(
            resp_json,
            window_id=window_id,
            du_daily_trigger=du_daily_trigger,
            dynamic_memory_citation_map=dynamic_memory_citation_map,
            source_messages=body.get("messages") or [],
            reply_channel=reply_channel,
            du_request_id=du_request_id,
        )
        if is_sumitalk_request:
            resp_json = _merge_sumitalk_card_into_nonstream_response(resp_json, body.get("messages") or [])
        sumitalk_final_reasoning_text = ""
        sumitalk_final_reasoning_omitted = False
        try:
            raw_msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
            archive_thinking_blocks_for_r2 = _extract_claude_thinking_blocks(raw_msg)
            if is_sumitalk_request and tool_rounds_used == 0 and isinstance(raw_msg, dict):
                existing_reasoning_text, _existing_reasoning_details, existing_reasoning_omitted = _extract_reasoning_text_and_details(raw_msg)
                sumitalk_final_reasoning_text = _merged_nonstream_reasoning_text(existing_reasoning_text)
                sumitalk_final_reasoning_omitted = bool(accumulated_reasoning_omitted or existing_reasoning_omitted)
        except Exception:
            archive_thinking_blocks_for_r2 = []
        # 剥离 content / 结构化 delta 里的 thinking 块，避免泄漏给客户端（RikkaHub / Telegram 等）；
        # R2 存档会从 archive_thinking_blocks_for_r2 回填原始 thinking_blocks。
        resp_json = _strip_thinking_from_response_json(resp_json)
        if is_sumitalk_request and tool_rounds_used == 0:
            try:
                response_msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
                if isinstance(response_msg, dict):
                    if sumitalk_final_reasoning_text:
                        response_msg["reasoning"] = sumitalk_final_reasoning_text
                        (resp_json.get("choices") or [{}])[0]["message"] = response_msg
                    elif sumitalk_final_reasoning_omitted:
                        response_msg["reasoning"] = "（本轮 adaptive thinking 未返回可展示正文）"
                        (resp_json.get("choices") or [{}])[0]["message"] = response_msg
            except Exception:
                logger.warning("合并 SumiTalk 非工具轮 thinking 失败 window_id=%s", window_id, exc_info=True)
        if not _disable_followup_request():
            try:
                msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
                content = msg.get("content")
                if isinstance(content, str):
                    cleaned_content, queued = queue_followup(window_id=window_id, headers=headers, assistant_text=content)
                    if queued or cleaned_content != content:
                        msg["content"] = cleaned_content
                        (resp_json.get("choices") or [{}])[0]["message"] = msg
                elif isinstance(content, list):
                    merged_text = []
                    changed = False
                    for part in content:
                        if not isinstance(part, dict):
                            merged_text.append(part)
                            continue
                        if str(part.get("type") or "").strip() != "text":
                            merged_text.append(part)
                            continue
                        text = str(part.get("text") or "")
                        cleaned_text, queued = queue_followup(window_id=window_id, headers=headers, assistant_text=text)
                        if queued or cleaned_text != text:
                            changed = True
                            merged_text.append({**part, "text": cleaned_text})
                        else:
                            merged_text.append(part)
                    if changed:
                        msg["content"] = merged_text
                        (resp_json.get("choices") or [{}])[0]["message"] = msg
            except Exception:
                logger.warning("处理延迟续话标记失败 window_id=%s", window_id, exc_info=True)
        if reply_channel == "tg":
            try:
                response_msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
                if isinstance(response_msg, dict):
                    existing_response_reasoning = str(
                        response_msg.get("reasoning")
                        or response_msg.get("reasoning_content")
                        or response_msg.get("thinking")
                        or ""
                    ).strip()
                    merged_response_reasoning = _merged_nonstream_reasoning_text(existing_response_reasoning)
                    if merged_response_reasoning:
                        response_msg["reasoning"] = merged_response_reasoning
                        (resp_json.get("choices") or [{}])[0]["message"] = response_msg
            except Exception:
                logger.warning("合并 TG thinking 失败 window_id=%s", window_id, exc_info=True)
    if resp_json and (resp_json or {}).get("choices"):
        msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
        content_text = get_assistant_content_text(msg)
        if tool_loop_finished and completed_tool_results and content_text.strip() and not is_failed_response(content_text):
            inserted = _record_tool_result_loop(
                completed_tool_results,
                window_id=window_id,
                reply_channel=reply_channel,
                model=str(body.get("model") or ""),
            )
            logger.info(
                "工具摘要缓存整轮写入 window_id=%s tools=%s inserted=%s",
                window_id,
                len(completed_tool_results),
                inserted,
            )
        if is_failed_response(content_text):
            logger.info("R2 未存档：上游回复被判为失败（长度/关键词），跳过")
        elif (
            _is_followup_generation_request()
            and not _should_archive_followup_generation_request()
            and not _is_delayed_followup_generation_request()
        ):
            logger.info("R2 未存档：延迟续话内部生成请求跳过存档")
        elif du_daily_maintenance:
            logger.info("R2 未存档：du_daily 内部维护请求跳过会话存档")
        else:
            # 构造仅用于 R2 存档的 msg 副本，不修改 resp_json（避免 reasoning 回传给客户端）
            import copy as _copy
            msg_for_r2 = _copy.deepcopy(msg)
            msg_for_r2["du_request_id"] = du_request_id
            if archive_thinking_blocks_for_r2 and not msg_for_r2.get("thinking_blocks"):
                msg_for_r2["thinking_blocks"] = archive_thinking_blocks_for_r2
            # reasoning 兼容字段：优先取最终轮次自带的，再合并工具中间轮次累计的
            if not msg_for_r2.get("reasoning"):
                for rk in ("reasoning_content", "thinking"):
                    if msg_for_r2.get(rk):
                        msg_for_r2["reasoning"] = msg_for_r2.get(rk)
                        break
            existing_reasoning_text = str(msg_for_r2.get("reasoning") or "").strip()
            merged_reasoning_text = _merged_nonstream_reasoning_text(existing_reasoning_text)
            if merged_reasoning_text:
                msg_for_r2["reasoning"] = merged_reasoning_text

            existing_reasoning_details = _normalize_reasoning_details(msg_for_r2.get("reasoning_details"))
            merged_reasoning_details = list(accumulated_reasoning_details)
            _extend_unique_reasoning_details(merged_reasoning_details, existing_reasoning_details)
            if merged_reasoning_details:
                msg_for_r2["reasoning_details"] = merged_reasoning_details
            if accumulated_reasoning_omitted or (tool_rounds_used > 0 and not msg_for_r2.get("reasoning")):
                msg_for_r2["reasoning_omitted"] = True
            if msg_for_r2.get("reasoning_details") and not msg_for_r2.get("reasoning_omitted"):
                msg_for_r2["reasoning_omitted"] = True
            if cache_debug_entries:
                msg_for_r2["cache_debug"] = cache_debug_entries
            _apply_pseudo_cot_state_and_fallback(
                window_id,
                msg_for_r2,
                inner_os,
                force_inner_os=pseudo_cot_response_enabled,
            )
            tc_trace = _collect_tool_trace_from_messages(body.get("messages") or [])
            if tc_trace and not msg_for_r2.get("tool_calls"):
                msg_for_r2["tool_calls"] = tc_trace
            game_tool_used = _tool_trace_has_game_tool_loop(tc_trace)
            archive_skip_dynamic_memory_write = skip_post_archive_dynamic_memory_write or game_tool_used
            archive_skip_body_delta = skip_post_archive_body_delta or game_tool_used
            if game_tool_used:
                logger.info("game tool 回合命中，归档后动态记忆与 BODY delta 跳过 window_id=%s", window_id)
            last_user = _last_user_message(body.get("messages"))
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            archive_messages = _copy.deepcopy(body.get("messages") or [])
            if last_user:
                round_cleaned = _build_round_cleaned_for_archive(
                    last_user,
                    msg_for_r2,
                    reply_target=reply_target,
                    window_id=window_id,
                    request_messages=body.get("messages") or [],
                )
                if reply_channel in _NONSTREAM_FAST_RETURN_CHANNELS:
                    archived = step_archive_round(
                        window_id, archive_messages, msg_for_r2, round_cleaned_for_r2=round_cleaned
                    )
                    if archived:
                        _run_nonstream_post_archive_in_background(
                            window_id=window_id,
                            round_index=int(archived.get("round_index") or 0),
                            round_messages=archived.get("round_messages") or round_cleaned,
                            reply_channel=reply_channel,
                            skip_dynamic_memory_write=archive_skip_dynamic_memory_write,
                            skip_body_delta=archive_skip_body_delta,
                        )
                else:
                    step_archive_and_maybe_summary(
                        window_id,
                        archive_messages,
                        msg_for_r2,
                        round_cleaned_for_r2=round_cleaned,
                        skip_dynamic_memory_write=archive_skip_dynamic_memory_write,
                        skip_body_delta=archive_skip_body_delta,
                    )
            else:
                if reply_channel in _NONSTREAM_FAST_RETURN_CHANNELS:
                    archived = step_archive_round(window_id, archive_messages, msg_for_r2)
                    if archived:
                        _run_nonstream_post_archive_in_background(
                            window_id=window_id,
                            round_index=int(archived.get("round_index") or 0),
                            round_messages=archived.get("round_messages") or [],
                            reply_channel=reply_channel,
                            skip_dynamic_memory_write=archive_skip_dynamic_memory_write,
                            skip_body_delta=archive_skip_body_delta,
                        )
                else:
                    step_archive_and_maybe_summary(
                        window_id,
                        archive_messages,
                        msg_for_r2,
                        skip_dynamic_memory_write=archive_skip_dynamic_memory_write,
                        skip_body_delta=archive_skip_body_delta,
                    )
    else:
        logger.info("R2 未存档：上游无 choices 或响应为空")
    if _is_proactive_decision_request() and isinstance(resp_json, dict):
        resp_json["du_gateway_executed_tools"] = _executed_tool_names_from_messages(body.get("messages") or [])

    if is_sumitalk_request:
        msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        reasoning_text = ""
        if isinstance(msg, dict):
            reasoning_text = str(msg.get("reasoning") or msg.get("reasoning_content") or msg.get("thinking") or "")
        finish_reason = ""
        try:
            finish_reason = str((((resp_json or {}).get("choices") or [{}])[0] or {}).get("finish_reason") or "")
        except Exception:
            finish_reason = ""
        sumitalk_logger.info(
            "chat_response_ok window_id=%s target=%s status=%s reply_chars=%s reasoning_chars=%s choices=%s finish_reason=%s tool_rounds=%s",
            window_id,
            reply_target,
            200,
            _message_content_chars(get_assistant_content_text(msg)),
            len(reasoning_text),
            len((resp_json or {}).get("choices") or []),
            finish_reason,
            tool_rounds_used,
        )
    if openrouter_forced_nonstream:
        return _stream_response(
            _sse_from_nonstream_response(resp_json),
            degraded_reason="upstream_nonstream",
        )
    return jsonify(resp_json), 200
