# 聊天代理：统一走完整管道（清洗、注入、转发、存档），无开头过滤
# 项目约定：主聊天禁止默认兜底模型。没传 model 就直接报错，不要偷偷补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
import json
import queue
import threading
import time
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
    is_openrouter_url,
    openrouter_models_response,
)
from pipeline.pipeline import (
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_replace_rikka_system,
    step_inject_thinking_block_rules,
    step_inject_core_behavior_rules,
    step_inject_common_knowledge,
    step_inject_du_non_retreat_rules,
    step_inject_current_base_model,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_sense_snapshot,
    step_inject_du_thought,
    step_inject_du_daily,
    step_inject_interaction_candidate,
    step_inject_rikkahub_reminder,
    step_inject_dynamic_memory,
    step_inject_stay_with_du,
    step_inject_du_notebook,
    step_inject_wenyou_player_tools,
    step_inject_notion_search,
    step_inject_notion_tools,
    step_inject_forum_tools,
    step_inject_amap_mcp_tools,
    step_inject_websearch_tools,
    step_inject_html_preview_tool,
    step_trim_messages_if_over_limit,
    step_archive_and_maybe_summary,
    step_archive_round,
)
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.failed_response import get_assistant_content_text, is_failed_response
from storage import r2_store, whitelist_store
from services.du_daily import (
    build_chat_trigger as build_du_daily_trigger,
)
from services.dynamic_memory_citation import (
    DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY,
    normalize_citation_map,
)
from services.conversation_followup import (
    queue_followup,
)
from services.pc_command_handler import (
    PcmdDuThoughtStreamState,
    transform_sse_chunk_bytes as transform_sse_chunk_bytes_pcmd,
)
from services.chat_content import message_content_chars as _message_content_chars
from services.chat_prompt_injections import (
    inject_channel_nsfw_system as _inject_channel_nsfw_system,
    inject_entry_style_system as _inject_entry_style_system,
    inject_followup_instruction as _inject_followup_instruction,
    inject_silence_mode_system as _inject_silence_mode_system,
    inject_voice_call_style_system as _inject_voice_call_style_system,
)
from services.chat_archive_helpers import (
    compact_qq_group_context_for_archive as _compact_qq_group_context_for_archive,
    run_nonstream_post_archive_in_background as _run_nonstream_post_archive_in_background,
    strip_co_read_section_raw_text_for_archive as _strip_co_read_section_raw_text_for_archive,
    strip_wenyou_ai_player_context_for_archive as _strip_wenyou_ai_player_context_for_archive,
)
from services.chat_request_helpers import (
    build_noop_chat_response as _build_noop_chat_response,
    is_suspected_rikkahub_phantom_one as _is_suspected_rikkahub_phantom_one,
    last_user_message as _last_user_message,
    maybe_mark_tg_window_user_activity as _maybe_mark_tg_window_user_activity,
    maybe_record_last_reply_channel as _maybe_record_last_reply_channel,
)
from services.chat_response_enrichers import (
    dedupe_stream_sumitalk_cards,
    html_preview_suffix_for_stream,
    merge_html_preview_into_nonstream_response as _merge_html_preview_into_nonstream_response,
    merge_sumitalk_card_into_nonstream_response as _merge_sumitalk_card_into_nonstream_response,
    sumitalk_card_suffix_for_stream,
)
from services.chat_sidecars import (
    apply_hidden_sidecars_to_assistant_response as _apply_hidden_sidecars_to_assistant_response,
    extract_and_store_hidden_sidecars as _extract_and_store_hidden_sidecars,
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
from services.prompt_cache_debug import (
    build_cache_debug_entry as _build_cache_debug_entry,
    build_prompt_cache_profile as _build_prompt_cache_profile,
)
from services.reasoning_utils import (
    THINK_BLOCK_RE as _THINK_BLOCK_RE,
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
    normalize_request_model as _normalize_request_model,
)
from utils.log import get_logger

logger = get_logger(__name__)
sumitalk_logger = get_logger("sumitalk")
bp = Blueprint("chat", __name__)

WINDOW_ID_DEFAULT = ""
_NONSTREAM_FAST_RETURN_CHANNELS = {"tg", "qq", "wechat", "sumitalk"}


def _get_window_id_from_request(body: dict) -> str:
    """从请求获取 window_id：优先 X-Window-Id header，其次 body.window_id，缺省为空。供 Telegram 等客户端传 tg_{user_id}。"""
    if request.headers.get("X-Window-Id"):
        return (request.headers.get("X-Window-Id") or "").strip()
    if isinstance(body, dict) and body.get("window_id") is not None:
        return str(body.get("window_id", "")).strip()
    return WINDOW_ID_DEFAULT


def _is_miniapp_request() -> bool:
    return bool((request.headers.get("X-Telegram-Init-Data") or "").strip())


def _reply_channel() -> str:
    return str(request.headers.get("X-Reply-Channel") or "").strip().lower()


def _reply_target() -> str:
    return str(request.headers.get("X-Reply-Target") or "").strip()


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
    return (request.headers.get("X-Skip-Post-Archive-Dynamic-Memory") or "").strip().lower() in ("1", "true", "yes")


def _should_archive_followup_generation_request() -> bool:
    return (request.headers.get("X-DU-FOLLOWUP-ARCHIVE") or "").strip().lower() in ("1", "true", "yes")


def _stream_forward_to_ai(body: dict, headers: dict):
    """流式转发：上游 SSE 原样逐行 yield；不再自动 fallback。"""
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        yield (
            "data: "
            + json.dumps({"error": _build_upstream_error_hint("TARGET_AI_URL 或 TARGET_AI_URLS 未配置")})
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
        try:
            body_send = _apply_active_model_request_policy(body_send, url)
            target_url = url
            body_send = _apply_openrouter_request_policy(body_send, url)
            # timeout 同时作 connect/read：流式时若超过该秒数未收到数据会 ReadTimeout 断流，过短会导致回复中途截断
            r = requests.post(target_url, headers=h, json=body_send, timeout=STREAM_TIMEOUT_SECONDS, stream=True)
            if r.status_code == 200:
                last_data_line = None
                first_chunk_logged = False
                for line in r.iter_lines():
                    if line is not None:
                        if not first_chunk_logged and line.startswith(b"data:") and len(line) > 5:
                            logger.debug("流式收到首包（上游已开始推流）")
                            first_chunk_logged = True
                        if line.startswith(b"data: ") and b"[DONE]" not in line:
                            last_data_line = line
                        yield line + b"\n"
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
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
    skip_post_archive_dynamic_memory: bool = False,
):
    """
    包装流式响应：原样转发 SSE，同时在流结束后用收集到的 content 写 R2。
    当请求带 tools 时：先缓冲整段流，解析 message；若有 tool_calls 则执行工具并继续请求（循环），
    最后把「无 tool_calls」那一轮的流发给客户端，实现与 RikkaHub 类似的流式+工具行为。
    无 tools 时：边收边发，不缓冲，保持原有实时流式。
    """
    content_parts = []
    reasoning_parts = []
    reasoning_details_parts: list[dict] = []
    reasoning_omitted = False
    last_user = _last_user_message(body.get("messages") or [])
    du_daily_maintenance = _is_du_daily_maintenance_request()

    def _collect_content_from_chunk(chunk):
        try:
            if chunk.startswith(b"data: "):
                payload = chunk[6:].strip()
                if payload != b"[DONE]" and payload:
                    j = json.loads(payload.decode("utf-8", errors="ignore"))
                    delta = (j.get("choices") or [{}])[0].get("delta") or {}
                    raw_content = delta.get("content") or ""
                    if raw_content:
                        # 如果 delta.content 里含有 <think> 块，提取到 reasoning_parts，
                        # 只把干净的正文放入 content_parts（对应 _strip_reasoning_from_sse_chunk 的客户端过滤）
                        if _THINK_BLOCK_RE.search(raw_content):
                            clean, in_content_thinking = _extract_thinking_from_content(raw_content)
                            if clean:
                                content_parts.append(clean)
                            if in_content_thinking:
                                reasoning_parts.append(in_content_thinking)
                        else:
                            content_parts.append(raw_content)
                    text, details, omitted = _extract_reasoning_text_and_details(delta)
                    if text:
                        reasoning_parts.append(text)
                    if details:
                        reasoning_details_parts.extend(details)
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
                for chunk in _stream_forward_to_ai(body, headers):
                    _collect_content_from_chunk(chunk)
                    # 先收集 reasoning 用于存档，再过滤掉发给客户端的 chunk 里的 reasoning delta
                    chunk_queue.put(_strip_reasoning_from_sse_chunk(chunk))
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
                        buf.append(nxt)
                        if nxt.startswith(b"data:") and len(nxt) > 5:
                            data_chunk_count += 1
                    if chunk is None:
                        # 先把缓冲发完再结束
                        yield b"".join([transform_sse_chunk_bytes_pcmd(c, du_state) for c in buf])
                        break

                yield b"".join([transform_sse_chunk_bytes_pcmd(c, du_state) for c in buf])
                last_send_ts = time.time()
        finally:
            full_content = "".join(content_parts)
            visible = _extract_and_store_hidden_sidecars(
                full_content,
                window_id=window_id,
                du_daily_trigger=du_daily_trigger,
                dynamic_memory_citation_map=dynamic_memory_citation_map,
            )
            full_reasoning = "".join(reasoning_parts).strip()
            stream_sec = time.time() - stream_start
            # 若「流式持续时长」总是差不多（如 10–20s）而字数越来越短，可能是上游按时长限流
            logger.debug("本轮流式回复收集长度约 %s 字符，共转发 %s 个 data 块，流式持续约 %.1f 秒", len(full_content), data_chunk_count, stream_sec)
            if du_daily_maintenance:
                logger.info("R2 未存档：du_daily 内部维护请求跳过会话存档")
            elif not is_failed_response(visible) and visible.strip():
                msg = {"role": "assistant", "content": visible}
                if full_reasoning:
                    msg["reasoning"] = full_reasoning
                if reasoning_details_parts:
                    msg["reasoning_details"] = reasoning_details_parts
                if reasoning_omitted:
                    msg["reasoning_omitted"] = True
                archive_last_user = _last_user_for_archive(
                    last_user,
                    reply_target=_reply_target(),
                    window_id=window_id,
                )
                round_cleaned = build_round_cleaned_for_r2(archive_last_user, msg) if archive_last_user else None
                logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
                step_archive_and_maybe_summary(
                    window_id,
                    body.get("messages") or [],
                    msg,
                    round_cleaned_for_r2=round_cleaned,
                    skip_dynamic_layer=skip_post_archive_dynamic_memory,
                )
                try:
                    from services.notion_write_from_assistant import process_assistant_content_for_notion_write
                    process_assistant_content_for_notion_write(visible)
                except Exception:
                    pass
                logger.info("R2 流式请求已存档")
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
    tool_visible_content_parts: list[str] = []
    try:
        while True:
            chunks = []
            chunk_queue = queue.Queue()

            def _producer():
                try:
                    for chunk in _stream_forward_to_ai(current_body, headers):
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
            if len(chunks) == 1 and chunks[0].startswith(b"data: ") and b"error" in chunks[0]:
                yield chunks[0]
                return
            parsed = _parse_stream_to_message(chunks)
            tool_calls = parsed.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                if tool_rounds_used >= max_processed_tool_rounds:
                    logger.warning(
                        "工具调用达到轮数上限(%s)，停止继续请求上游以控制费用；当前工具数=%s",
                        max_tool_rounds,
                        len(tool_calls),
                    )
                    cap_hint = "（已达到工具调用轮数上限，为控制费用已停止继续自动调工具。你可以让我基于现有结果继续回答。）"
                    cap_hint = _merge_visible_tool_round_content(tool_visible_content_parts, cap_hint)
                    yield _sse_delta_chunk_bytes(cap_hint)
                    content_parts.append(cap_hint)
                    break
                from services.notion_tools import execute_tool
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
                current_body = _append_tool_results_and_continue(current_body, msg, tool_calls, execute_tool)
                tool_rounds_used += 1
                continue
            if (
                tool_rounds_used > 0
                and (not tool_empty_final_retry_used)
                and _should_retry_tool_empty_final(parsed.get("content") or "")
            ):
                logger.warning("工具续轮最终正文为空，流式路径触发一次强制收口补问")
                current_body = _inject_tool_empty_final_retry_instruction(current_body)
                tool_empty_final_retry_used = True
                continue
            if (
                tool_rounds_used > 0
                and (not tool_midstream_retry_used)
                and _should_retry_tool_followup(
                    parsed.get("content") or "",
                    parsed.get("reasoning") or "",
                )
            ):
                logger.info("工具续轮命中中间态文本，流式路径触发一次内部补问重试")
                current_body = _inject_tool_midstream_retry_instruction(current_body)
                tool_midstream_retry_used = True
                continue
            du_state = PcmdDuThoughtStreamState(dynamic_memory_citation_map)
            done_chunks = []
            raw_parsed_content = parsed.get("content") or ""
            parsed_content = dedupe_stream_sumitalk_cards(raw_parsed_content)
            merged_parsed_content = _merge_visible_tool_round_content(tool_visible_content_parts, parsed_content)
            if merged_parsed_content != raw_parsed_content:
                parsed_content = merged_parsed_content
                visible_content = du_state.feed_delta(parsed_content)
                if visible_content:
                    yield _sse_delta_chunk_bytes(visible_content)
            else:
                for ch in chunks:
                    if _is_sse_done_chunk(ch):
                        done_chunks.append(ch)
                        continue
                    yield transform_sse_chunk_bytes_pcmd(_strip_reasoning_from_sse_chunk(ch), du_state)
            content_parts.append(parsed_content)
            # 模型常不在正文复述预览链接：从 tool 结果补发 SSE + 存档拼接
            suf = html_preview_suffix_for_stream(
                parsed_content, current_body.get("messages") or []
            )
            if suf:
                extra_vis = du_state.feed_delta(suf)
                if extra_vis:
                    yield _sse_delta_chunk_bytes(extra_vis)
                    content_parts.append(extra_vis)
            if _reply_channel() == "sumitalk":
                extra_card = sumitalk_card_suffix_for_stream(parsed_content, current_body.get("messages") or [])
                if extra_card:
                    yield _sse_delta_chunk_bytes(extra_card)
                    content_parts.append(extra_card)
            if done_chunks:
                yield b"data: [DONE]\n\n"
            else:
                yield b"data: [DONE]\n\n"
            if parsed.get("reasoning"):
                reasoning_parts.append(parsed.get("reasoning") or "")
            if parsed.get("reasoning_details"):
                reasoning_details_parts.extend(parsed.get("reasoning_details") or [])
            if parsed.get("reasoning_omitted"):
                reasoning_omitted = True
            break
    finally:
        full_content = "".join(content_parts)
        visible = _extract_and_store_hidden_sidecars(
            full_content,
            window_id=window_id,
            du_daily_trigger=du_daily_trigger,
            dynamic_memory_citation_map=dynamic_memory_citation_map,
        )
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
        if du_daily_maintenance:
            logger.info("R2 未存档：du_daily 内部维护请求跳过会话存档")
        elif is_failed_response(visible):
            logger.info("R2 未存档：流式回复被判为失败，跳过")
        elif not visible.strip():
            logger.info("R2 未存档：流式回复为空，跳过")
        else:
            msg = {"role": "assistant", "content": visible}
            if full_reasoning:
                msg["reasoning"] = full_reasoning
            if reasoning_details_parts:
                msg["reasoning_details"] = reasoning_details_parts
            if reasoning_omitted:
                msg["reasoning_omitted"] = True
            tc_trace = _collect_tool_trace_from_messages(current_body.get("messages") or [])
            if tc_trace:
                msg["tool_calls"] = tc_trace
            archive_last_user = _last_user_for_archive(
                last_user,
                reply_target=_reply_target(),
                window_id=window_id,
            )
            round_cleaned = build_round_cleaned_for_r2(archive_last_user, msg) if archive_last_user else None
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            step_archive_and_maybe_summary(
                window_id,
                current_body.get("messages") or [],
                msg,
                round_cleaned_for_r2=round_cleaned,
                skip_dynamic_layer=skip_post_archive_dynamic_memory,
            )
            try:
                from services.notion_write_from_assistant import process_assistant_content_for_notion_write
                process_assistant_content_for_notion_write(visible)
            except Exception:
                pass
            logger.info("R2 流式请求已存档")


def _forward_to_ai(body: dict, headers: dict, prompt_cache_profile: Optional[dict] = None):
    """将请求体转发到配置的 AI 接口：仅一个 active 上游（不再自动 fallback）。
    返回 (response_json, status_code, error, cache_debug)。非流式。
    """
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        return None, 502, _build_upstream_error_hint("TARGET_AI_URL 或 TARGET_AI_URLS 未配置"), None
    last_err = None
    last_status = 502
    for i, (url, api_key) in enumerate(targets):
        req_headers = {"Content-Type": "application/json"}
        if api_key:
            req_headers["Authorization"] = f"Bearer {api_key}"
        for h in ("Accept", "Accept-Encoding"):
            if request.headers.get(h):
                req_headers[h] = request.headers.get(h)
        try:
            # 非流式：上游返回单 JSON，便于解析、存档、追加黑名单后缀等
            body_send = dict(body)
            body_send["stream"] = False
            if MAX_COMPLETION_TOKENS > 0:
                cur = body_send.get("max_tokens")
                if cur is None or (isinstance(cur, (int, float)) and int(cur) < MAX_COMPLETION_TOKENS):
                    body_send["max_tokens"] = MAX_COMPLETION_TOKENS
                    logger.info("转发已设 max_tokens=%s（原=%s）", MAX_COMPLETION_TOKENS, cur)
            body_send = _apply_active_model_request_policy(body_send, url)
            target_url = url
            body_send = _apply_openrouter_request_policy(body_send, url)
            r = requests.post(target_url, headers=req_headers, json=body_send, timeout=120)
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
                cache_debug = _build_cache_debug_entry(body_send, target_url, prompt_cache_profile, data or {})
                usage_debug = cache_debug.get("usage") or {}
                profile_debug = cache_debug.get("request") or {}
                logger.info(
                    "prompt_cache_debug host=%s model=%s static_est_tokens=%s dynamic_est_tokens=%s leading_est_tokens=%s cached_tokens=%s usage_returned=%s prompt_cache_key=%s",
                    profile_debug.get("upstream_host") or "",
                    profile_debug.get("model") or "",
                    profile_debug.get("static_prefix_est_tokens"),
                    profile_debug.get("dynamic_system_est_tokens"),
                    profile_debug.get("leading_system_est_tokens"),
                    usage_debug.get("cached_tokens"),
                    usage_debug.get("usage_returned"),
                    bool(profile_debug.get("prompt_cache_key")),
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
        return jsonify({"error": _build_upstream_error_hint("TARGET_AI_URL 或 TARGET_AI_URLS 未配置")}), 502
    url, api_key = targets[0]
    if is_openrouter_url(url):
        data = openrouter_models_response()
        if data:
            return jsonify(data), 200
        return jsonify({"error": "OPENROUTER_FIXED_MODEL 未配置"}), 502
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
    body = _normalize_request_model(body)
    body = _apply_openrouter_request_policy(body, _get_active_upstream_url())
    reply_channel = _reply_channel()
    reply_target = _reply_target()
    is_sumitalk_request = reply_channel == "sumitalk"
    req_model = (body.get("model") or "").strip() if isinstance(body.get("model"), str) else ""
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
        return jsonify({"error": "缺少 model"}), 400
    headers = dict(request.headers) if request.headers else {}
    window_id = _get_window_id_from_request(body)
    # 未传 id 的客户端（如 RikkaHub）与 R2 主存 __default__ 对齐，否则轮次恒为 1、总结永不触发
    window_id = r2_store.normalize_window_id(window_id)
    # 记录最近窗口，供 MiniApp 思维链面板展示可选窗口列表
    try:
        wid_for_recent = window_id if (window_id or "").strip() else "__default__"
        whitelist_store.record_recent_window(wid_for_recent)
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

    def _stream_response(gen):
        return Response(
            stream_with_context(gen),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if _is_suspected_rikkahub_phantom_one(body, window_id, headers):
        logger.warning("命中 RikkaHub 幽灵1保护：window_id=%s ua=%s", window_id, (headers.get("User-Agent") or "")[:80])
        if body.get("stream"):
            def _ghost_noop_stream():
                yield _sse_delta_chunk_bytes("（检测到客户端误触发，已忽略本次空输入）")
                yield b"data: [DONE]\n\n"

            return _stream_response(_ghost_noop_stream())
        return jsonify(_build_noop_chat_response(body)), 200

    if not _is_du_daily_maintenance_request():
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

    # 走完整管道（清洗、注入记忆/总结、转发、存档）
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_replace_rikka_system(body)
    body = step_inject_thinking_block_rules(body)
    body = step_inject_core_behavior_rules(body)
    body = step_inject_du_non_retreat_rules(body)
    body = step_inject_common_knowledge(body)
    body = _inject_entry_style_system(body, reply_channel=reply_channel, is_miniapp=_is_miniapp_request())
    body = _inject_channel_nsfw_system(body, reply_channel=reply_channel)
    body = _inject_followup_instruction(
        body,
        is_followup_generation=_is_followup_generation_request(),
        should_archive=_should_archive_followup_generation_request(),
    )
    force_last4 = (request.headers.get("X-Force-Last4") or "").strip().lower() in ("1", "true", "yes")
    tg_user_input = (request.headers.get("X-TG-User-Input") or "").strip().lower() in ("1", "true", "yes")
    slim_voice_call = (request.headers.get("X-Voice-Call-Slim") or "").strip().lower() in ("1", "true", "yes")
    if slim_voice_call:
        body = _inject_voice_call_style_system(body)
    skip_dynamic_memory = (
        (request.headers.get("X-Skip-Dynamic-Memory") or "").strip().lower() in ("1", "true", "yes")
        or _is_gateway_wakeup_request()
    )
    skip_post_archive_dynamic_memory = _skip_post_archive_dynamic_memory_request()
    du_daily_maintenance = _is_du_daily_maintenance_request()
    du_daily_trigger = build_du_daily_trigger(window_id, body, headers)
    if not slim_voice_call:
        body = step_inject_current_base_model(body)
        body = step_inject_du_thought(body, window_id)
        body = step_inject_du_daily(body, window_id, trigger=du_daily_trigger, maintenance_mode=du_daily_maintenance)
        if not skip_dynamic_memory:
            body = step_inject_dynamic_memory(body, window_id)
        body = step_inject_summary(body, window_id, is_user_input=tg_user_input)
        body = step_inject_sense_snapshot(body, window_id)
        body = step_inject_latest_4_rounds_for_new_window(body, window_id, force_last4=force_last4)
        body = step_inject_interaction_candidate(body, window_id)
        if not du_daily_maintenance:
            body = step_inject_rikkahub_reminder(body, window_id)
        body = step_inject_stay_with_du(body)
        body = step_inject_du_notebook(body)
        body = step_inject_wenyou_player_tools(body)
        if not du_daily_maintenance:
            body = step_inject_notion_search(body, window_id)
            body = step_inject_notion_tools(body)
            body = step_inject_forum_tools(body)
            body = step_inject_amap_mcp_tools(body)
            body = step_inject_websearch_tools(body)
            body = step_inject_html_preview_tool(body, request.headers.get("User-Agent") or "")
    body = _inject_silence_mode_system(body, is_du_daily_maintenance=du_daily_maintenance)
    body = step_trim_messages_if_over_limit(body)
    dynamic_memory_citation_map = normalize_citation_map(body.pop(DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY, None))
    active_upstream_url = _get_active_upstream_url()
    prompt_cache_profile = _build_prompt_cache_profile(body, active_upstream_url)
    # Claude OAuth 代理自己会处理缓存断点；普通 OpenAI 上游继续清掉网关内部标记。
    preserve_dynamic_marker = _is_local_claude_oauth_proxy_url(active_upstream_url)
    for msg in body.get("messages") or []:
        if not preserve_dynamic_marker:
            msg.pop("__dynamic__", None)
            msg.pop("__summary_cache__", None)
            msg.pop("__summary_recent__", None)
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
                du_daily_trigger=du_daily_trigger,
                dynamic_memory_citation_map=dynamic_memory_citation_map,
                skip_post_archive_dynamic_memory=skip_post_archive_dynamic_memory,
            )
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
        return jsonify(resp_json or {"error": "upstream error"}), status
    # 非流式 + 有 Notion 工具时：若上游返回 tool_calls，执行工具并继续请求，直到无 tool_calls 或达到最大轮数
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
    max_tool_rounds = TOOL_MAX_ROUNDS
    max_processed_tool_rounds = max(0, int(max_tool_rounds))
    tool_rounds_used = 0
    tool_empty_final_retry_used = False
    tool_midstream_retry_used = False
    while True:
        msg = (resp_json or {}).get("choices") and (resp_json.get("choices") or [{}])[0].get("message")
        tool_calls = (msg or {}).get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            if tool_rounds_used >= max_processed_tool_rounds:
                break
            if isinstance(msg, dict):
                _accumulate_nonstream_reasoning(msg)
                _append_visible_tool_round_content(accumulated_tool_visible_parts, msg.get("content"))
            from services.notion_tools import execute_tool
            body = _append_tool_results_and_continue(body, msg, tool_calls, execute_tool)
            tool_rounds_used += 1
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
            break
    if resp_json:
        resp_json = _merge_visible_tool_round_content_into_response(resp_json, accumulated_tool_visible_parts)
    if resp_json and tool_rounds_used > 0:
        final_msg = (((resp_json or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        final_visible = _normalize_visible_reply_text(
            get_assistant_content_text(final_msg) if isinstance(final_msg, dict) else ""
        )
        if not final_visible:
            logger.error("工具续轮结束但最终正文仍为空（非流式路径） window_id=%s tool_rounds_used=%s", window_id, tool_rounds_used)
    if resp_json:
        resp_json = _apply_hidden_sidecars_to_assistant_response(
            resp_json,
            window_id=window_id,
            du_daily_trigger=du_daily_trigger,
            dynamic_memory_citation_map=dynamic_memory_citation_map,
        )
        resp_json = _merge_html_preview_into_nonstream_response(resp_json, body.get("messages") or [])
        if is_sumitalk_request:
            resp_json = _merge_sumitalk_card_into_nonstream_response(resp_json, body.get("messages") or [])
        # 剥离 content 里的 <think>/<thinking> 块，避免泄漏给客户端（RikkaHub / Telegram 等）；
        # thinking 已合并入 message.reasoning，R2 存档的 msg_for_r2 独立 deepcopy，不受此影响。
        resp_json = _strip_thinking_from_response_json(resp_json)
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
    if resp_json and (resp_json or {}).get("choices"):
        msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
        content_text = get_assistant_content_text(msg)
        if is_failed_response(content_text):
            logger.info("R2 未存档：上游回复被判为失败（长度/关键词），跳过")
        elif _is_followup_generation_request() and not _should_archive_followup_generation_request():
            logger.info("R2 未存档：延迟续话内部生成请求跳过存档")
        elif du_daily_maintenance:
            logger.info("R2 未存档：du_daily 内部维护请求跳过会话存档")
        else:
            # 构造仅用于 R2 存档的 msg 副本，不修改 resp_json（避免 reasoning 回传给客户端）
            import copy as _copy
            msg_for_r2 = _copy.deepcopy(msg)
            # reasoning 兼容字段：优先取最终轮次自带的，再合并工具中间轮次累计的
            if not msg_for_r2.get("reasoning"):
                for rk in ("reasoning_content", "thinking"):
                    if msg_for_r2.get(rk):
                        msg_for_r2["reasoning"] = msg_for_r2.get(rk)
                        break
            merged_reasoning_parts = list(accumulated_reasoning_parts)
            existing_reasoning_text = str(msg_for_r2.get("reasoning") or "").strip()
            _append_unique_reasoning_text(merged_reasoning_parts, existing_reasoning_text)
            merged_reasoning_text = "\n\n".join(merged_reasoning_parts).strip()
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
            tc_trace = _collect_tool_trace_from_messages(body.get("messages") or [])
            if tc_trace and not msg_for_r2.get("tool_calls"):
                msg_for_r2["tool_calls"] = tc_trace
            last_user = _last_user_message(body.get("messages"))
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            archive_messages = _copy.deepcopy(body.get("messages") or [])
            if last_user:
                archive_last_user = _last_user_for_archive(
                    last_user,
                    reply_target=reply_target,
                    window_id=window_id,
                )
                round_cleaned = build_round_cleaned_for_r2(archive_last_user, msg_for_r2)
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
                            skip_dynamic_layer=skip_post_archive_dynamic_memory,
                        )
                else:
                    step_archive_and_maybe_summary(
                        window_id,
                        archive_messages,
                        msg_for_r2,
                        round_cleaned_for_r2=round_cleaned,
                        skip_dynamic_layer=skip_post_archive_dynamic_memory,
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
                            skip_dynamic_layer=skip_post_archive_dynamic_memory,
                        )
                else:
                    step_archive_and_maybe_summary(
                        window_id,
                        archive_messages,
                        msg_for_r2,
                        skip_dynamic_layer=skip_post_archive_dynamic_memory,
                    )
    else:
        logger.info("R2 未存档：上游无 choices 或响应为空")
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
    return jsonify(resp_json), 200
