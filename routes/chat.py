# 聊天代理：统一走完整管道（清洗、注入、转发、存档），无开头过滤
# 项目约定：主聊天禁止默认兜底模型。没传 model 就直接报错，不要偷偷补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
import json
import queue
import threading
import time
from datetime import datetime, timezone
import requests

from flask import Blueprint, request, jsonify, Response, stream_with_context

from config import (
    TARGET_AI_URL,
    TARGET_AI_API_KEY,
    TARGET_AI_URLS,
    TARGET_AI_API_KEYS,
    GATEWAY_MODELS,
    model_matches_gateway_keywords,
    MAX_COMPLETION_TOKENS,
    STREAM_TIMEOUT_SECONDS,
    STREAM_SSE_HEARTBEAT_SECONDS,
    STREAM_SSE_FLUSH_MAX_MS,
    RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED,
    RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS,
)
from pipeline.pipeline import (
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_replace_rikka_system,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_sense_snapshot,
    step_inject_du_thought,
    step_inject_interaction_candidate,
    step_inject_rikkahub_reminder,
    step_inject_dynamic_memory,
    step_inject_du_notebook,
    step_inject_notion_search,
    step_inject_notion_tools,
    step_inject_forum_tools,
    step_inject_websearch_tools,
    step_inject_html_preview_tool,
    step_trim_messages_if_over_limit,
    step_archive_and_maybe_summary,
)
from services.wenyou_service import step_inject_wenyou_gm
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.failed_response import get_assistant_content_text, is_failed_response
from storage import r2_store, whitelist_store
from services.du_thought import split_assistant_for_thought
from services.interaction_memory import split_assistant_for_interaction
from services.html_preview_tools import (
    merge_html_preview_urls_into_assistant_text,
    missing_html_preview_url_suffix,
)
from services.pc_command_handler import (
    PcmdDuThoughtStreamState,
    process_pcmd_in_assistant_text,
    transform_sse_chunk_bytes as transform_sse_chunk_bytes_pcmd,
)
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)
bp = Blueprint("chat", __name__)

WINDOW_ID_DEFAULT = ""


def _get_window_id_from_request(body: dict) -> str:
    """从请求获取 window_id：优先 X-Window-Id header，其次 body.window_id，缺省为空。供 Telegram 等客户端传 tg_{user_id}。"""
    if request.headers.get("X-Window-Id"):
        return (request.headers.get("X-Window-Id") or "").strip()
    if isinstance(body, dict) and body.get("window_id") is not None:
        return str(body.get("window_id", "")).strip()
    return WINDOW_ID_DEFAULT


# 注意：主聊天与语音通话都禁止再写“默认兜底模型”逻辑。
# 没传 model 或拿不到当前可用模型时，直接报错，不要偷偷补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
def _normalize_request_model(body: dict) -> dict:
    return dict(body or {})


def _get_forward_targets(request_model: str = None):
    """
    仅返回一个转发目标：当前 active 上游。
    设计目的：关闭自动 fallback，多上游不可用时让你手动在 MiniApp 切换。
    """
    try:
        from storage.upstream_store import get_active_item

        active = get_active_item()
    except Exception:
        active = None

    if active and active.get("url"):
        u = (active.get("url") or "").strip()
        k = (active.get("api_key") or "").strip()
        if u:
            return [(u, k)]

    # active 不存在时：退回环境变量“第一个”配置（仍不做 fallback 链式重试）
    if TARGET_AI_URL and TARGET_AI_URL.strip():
        return [(TARGET_AI_URL.strip(), TARGET_AI_API_KEY or "")]

    if TARGET_AI_URLS:
        u = (TARGET_AI_URLS[0] or "").strip()
        if u:
            keys = list(TARGET_AI_API_KEYS or [])
            if not keys:
                k0 = TARGET_AI_API_KEY or ""
            else:
                k0 = keys[0] or ""
            return [(u, k0)]

    return []


def _active_upstream_label() -> str:
    """用于错误提示：展示当前 active 上游（不返回 api_key）。"""
    try:
        from storage.upstream_store import get_active_item

        active = get_active_item()
        if not active:
            return "未配置"
        name = (active.get("name") or "active").strip()
        url = (active.get("url") or "").strip()
        return f"{name}{' (' + url + ')' if url else ''}"
    except Exception:
        return "未配置"


def _build_upstream_error_hint(last_err: str) -> str:
    """把上游错误改造成“像 rikkahub 一样清楚”的可读提示。"""
    active_label = _active_upstream_label()
    detail = (last_err or "").strip() or "未知错误"
    return (
        "【上游不可用】请先在 MiniApp -> 上游中转站切换后重试。\n"
        f"当前 active：{active_label}\n"
        f"错误详情：{detail}"
    )


def _claude_prompt_cache_enabled() -> bool:
    try:
        from storage.upstream_store import load_upstreams

        data = load_upstreams() or {}
        return bool(data.get("anthropic_prompt_caching_enabled", False))
    except Exception:
        return False


def _is_claude_model(model_name: str) -> bool:
    return "claude" in str(model_name or "").strip().lower()


def _apply_claude_prompt_caching(body: dict) -> dict:
    """
    仅当手动开关开启且当前模型看起来是 Claude 时，
    按 Anthropic 官方格式打显式断点：
    1) tools 最后一个工具定义
    2) 静态前缀最后一条普通 system 的最后一个文本内容块
    """
    body = dict(body or {})
    body.pop("cache_control", None)
    if not _claude_prompt_cache_enabled():
        return body
    if not _is_claude_model(body.get("model") or ""):
        return body

    tools = []
    for tool in body.get("tools") or []:
        if isinstance(tool, dict):
            tt = dict(tool)
            tt.pop("cache_control", None)
            tools.append(tt)
        else:
            tools.append(tool)
    if tools:
        last_tool = tools[-1]
        if isinstance(last_tool, dict):
            last_tool["cache_control"] = {"type": "ephemeral"}
    body["tools"] = tools

    messages = []
    for msg in body.get("messages") or []:
        if isinstance(msg, dict):
            mm = dict(msg)
            mm.pop("cache_control", None)
            content = mm.get("content")
            if isinstance(content, list):
                cleaned = []
                for part in content:
                    if isinstance(part, dict):
                        pp = dict(part)
                        pp.pop("cache_control", None)
                        cleaned.append(pp)
                    elif isinstance(part, str):
                        cleaned.append({"type": "text", "text": part})
                    else:
                        cleaned.append(part)
                mm["content"] = cleaned
            messages.append(mm)
        else:
            messages.append(msg)
    body["messages"] = messages

    last_plain_system_idx = -1
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        if (msg.get("role") or "").lower() != "system":
            break
        if not msg.get("__dynamic__"):
            last_plain_system_idx = i
    if last_plain_system_idx >= 0:
        target = messages[last_plain_system_idx]
        content = target.get("content")
        if isinstance(content, str):
            target["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        elif isinstance(content, list):
            last_text_idx = -1
            converted = []
            for idx, part in enumerate(content):
                if isinstance(part, dict):
                    pp = dict(part)
                    if pp.get("type") == "text":
                        last_text_idx = idx
                    converted.append(pp)
                elif isinstance(part, str):
                    converted.append({"type": "text", "text": part})
                    last_text_idx = idx
                else:
                    converted.append(part)
            if last_text_idx >= 0 and isinstance(converted[last_text_idx], dict):
                converted[last_text_idx]["cache_control"] = {"type": "ephemeral"}
            target["content"] = converted
    return body


def _chat_url_to_models_url(chat_url: str) -> str:
    """从 chat completions URL 推出 /v1/models 的 URL。"""
    if not chat_url:
        return ""
    base = chat_url.rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/models"


def _parse_stream_to_message(chunks: list) -> dict:
    """
    从流式 SSE chunks 解析出完整 assistant message（content + tool_calls）。
    返回 {"content": str, "tool_calls": list or None, "reasoning": str|None}。
    reasoning 兼容不同上游字段：reasoning / reasoning_content / thinking。
    """
    content_parts = []
    reasoning_parts = []
    # tool_calls 按 index 聚合，arguments 可能多 delta 拼接
    tool_calls_by_index = {}
    for chunk in chunks:
        if not chunk.startswith(b"data: "):
            continue
        payload = chunk[6:].strip()
        if payload == b"[DONE]" or not payload:
            continue
        try:
            j = json.loads(payload.decode("utf-8", errors="ignore"))
            delta = (j.get("choices") or [{}])[0].get("delta") or {}
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if delta.get("content"):
            content_parts.append(delta["content"])
        # 兼容常见字段名（不同中转/供应商可能不同）
        for rk in ("reasoning", "reasoning_content", "thinking"):
            if delta.get(rk):
                reasoning_parts.append(str(delta.get(rk)))
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index")
            if idx is None:
                continue
            if idx not in tool_calls_by_index:
                tool_calls_by_index[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            if tc.get("id"):
                tool_calls_by_index[idx]["id"] = tc["id"]
            if tc.get("type"):
                tool_calls_by_index[idx]["type"] = tc["type"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                tool_calls_by_index[idx]["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                tool_calls_by_index[idx]["function"]["arguments"] += fn["arguments"]
    # 按 index 排序成列表
    sorted_tcs = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index) if tool_calls_by_index[i].get("id")]
    return {
        "content": "".join(content_parts),
        "tool_calls": sorted_tcs if sorted_tcs else None,
        "reasoning": "".join(reasoning_parts).strip() or None,
    }


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
    if request.headers.get("Accept"):
        req_headers["Accept"] = request.headers.get("Accept")
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
    last_err = None
    for url, api_key in targets:
        h = dict(req_headers)
        if api_key:
            h["Authorization"] = f"Bearer {api_key}"
        try:
            # timeout 同时作 connect/read：流式时若超过该秒数未收到数据会 ReadTimeout 断流，过短会导致回复中途截断
            r = requests.post(url, headers=h, json=body_send, timeout=STREAM_TIMEOUT_SECONDS, stream=True)
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


def _stream_with_r2_archive(body: dict, headers: dict, window_id: str = ""):
    """
    包装流式响应：原样转发 SSE，同时在流结束后用收集到的 content 写 R2。
    当请求带 tools 时：先缓冲整段流，解析 message；若有 tool_calls 则执行工具并继续请求（循环），
    最后把「无 tool_calls」那一轮的流发给客户端，实现与 RikkaHub 类似的流式+工具行为。
    无 tools 时：边收边发，不缓冲，保持原有实时流式。
    """
    content_parts = []
    reasoning_parts = []
    last_user = _last_user_message(body.get("messages") or [])

    def _collect_content_from_chunk(chunk):
        try:
            if chunk.startswith(b"data: "):
                payload = chunk[6:].strip()
                if payload != b"[DONE]" and payload:
                    j = json.loads(payload.decode("utf-8", errors="ignore"))
                    delta = (j.get("choices") or [{}])[0].get("delta") or {}
                    if delta.get("content"):
                        content_parts.append(delta["content"])
                    for rk in ("reasoning", "reasoning_content", "thinking"):
                        if delta.get(rk):
                            reasoning_parts.append(str(delta.get(rk)))
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
        du_state = PcmdDuThoughtStreamState()
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
            visible_after_pcmd, _ = process_pcmd_in_assistant_text(full_content)
            visible, thought = split_assistant_for_thought(visible_after_pcmd)
            visible, interaction = split_assistant_for_interaction(visible)
            if thought:
                try:
                    r2_store.save_du_thought_latest(now_beijing_iso(), thought)
                except Exception as e:
                    logger.warning("save_du_thought_latest 失败 error=%s", e)
            if interaction:
                try:
                    r2_store.append_interaction_candidate(interaction)
                except Exception as e:
                    logger.warning("append_interaction_candidate 失败 error=%s", e)
            full_reasoning = "".join(reasoning_parts).strip()
            stream_sec = time.time() - stream_start
            # 若「流式持续时长」总是差不多（如 10–20s）而字数越来越短，可能是上游按时长限流
            logger.debug("本轮流式回复收集长度约 %s 字符，共转发 %s 个 data 块，流式持续约 %.1f 秒", len(full_content), data_chunk_count, stream_sec)
            if not is_failed_response(visible) and visible.strip():
                msg = {"role": "assistant", "content": visible}
                if full_reasoning:
                    msg["reasoning"] = full_reasoning
                round_cleaned = build_round_cleaned_for_r2(last_user, msg) if last_user else None
                logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
                step_archive_and_maybe_summary(
                    window_id, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned,
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

    # 有 tools：缓冲 + 工具循环，最后把最后一轮流发给客户端
    current_body = body
    max_tool_rounds = 5
    try:
        for _ in range(max_tool_rounds):
            chunks = []
            for chunk in _stream_forward_to_ai(current_body, headers):
                chunks.append(chunk)
            if len(chunks) == 1 and chunks[0].startswith(b"data: ") and b"error" in chunks[0]:
                yield chunks[0]
                return
            parsed = _parse_stream_to_message(chunks)
            tool_calls = parsed.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                from services.notion_tools import execute_tool
                msg = {"content": parsed.get("content") or None, "tool_calls": tool_calls}
                if parsed.get("reasoning"):
                    msg["reasoning"] = parsed.get("reasoning")
                    reasoning_parts.append(parsed.get("reasoning") or "")
                current_body = _append_tool_results_and_continue(current_body, msg, tool_calls, execute_tool)
                continue
            du_state = PcmdDuThoughtStreamState()
            for ch in chunks:
                yield transform_sse_chunk_bytes_pcmd(ch, du_state)
            content_parts.append(parsed.get("content") or "")
            # 模型常不在正文复述预览链接：从 tool 结果补发 SSE + 存档拼接
            suf = missing_html_preview_url_suffix(
                parsed.get("content") or "", current_body.get("messages") or []
            )
            if suf:
                extra_vis = du_state.feed_delta(suf)
                if extra_vis:
                    yield _sse_delta_chunk_bytes(extra_vis)
                    content_parts.append(extra_vis)
            if parsed.get("reasoning"):
                reasoning_parts.append(parsed.get("reasoning") or "")
            break
    finally:
        full_content = "".join(content_parts)
        visible_after_pcmd, _ = process_pcmd_in_assistant_text(full_content)
        visible, thought = split_assistant_for_thought(visible_after_pcmd)
        visible, interaction = split_assistant_for_interaction(visible)
        if thought:
            try:
                r2_store.save_du_thought_latest(now_beijing_iso(), thought)
            except Exception as e:
                logger.warning("save_du_thought_latest 失败 error=%s", e)
        if interaction:
            try:
                r2_store.append_interaction_candidate(interaction)
            except Exception as e:
                logger.warning("append_interaction_candidate 失败 error=%s", e)
        full_reasoning = "".join(reasoning_parts).strip()
        logger.info("本轮流式回复收集长度约 %s 字符", len(full_content))
        if is_failed_response(visible):
            logger.info("R2 未存档：流式回复被判为失败，跳过")
        elif not visible.strip():
            logger.info("R2 未存档：流式回复为空，跳过")
        else:
            msg = {"role": "assistant", "content": visible}
            if full_reasoning:
                msg["reasoning"] = full_reasoning
            tc_trace = _collect_tool_trace_from_messages(current_body.get("messages") or [])
            if tc_trace:
                msg["tool_calls"] = tc_trace
            round_cleaned = build_round_cleaned_for_r2(last_user, msg) if last_user else None
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            step_archive_and_maybe_summary(
                window_id, current_body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned,
            )
            try:
                from services.notion_write_from_assistant import process_assistant_content_for_notion_write
                process_assistant_content_for_notion_write(visible)
            except Exception:
                pass
            logger.info("R2 流式请求已存档")


def _forward_to_ai(body: dict, headers: dict):
    """将请求体转发到配置的 AI 接口：仅一个 active 上游（不再自动 fallback）。
    返回 (response_json, status_code, error)。非流式。
    """
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        return None, 502, _build_upstream_error_hint("TARGET_AI_URL 或 TARGET_AI_URLS 未配置")
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
            r = requests.post(url, headers=req_headers, json=body_send, timeout=120)
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
                (url or "")[:60],
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
                    url[:50], r.status_code, preview,
                )
                last_status = r.status_code
                last_err = "上游返回非 JSON"
                continue
            # 只有 2xx 算成功，其余（4xx/5xx/429 等）直接失败（不再自动 fallback）
            if 200 <= r.status_code < 300:
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
                return data, r.status_code, None
            last_status = r.status_code
            try:
                if isinstance(data, dict):
                    msg = (data.get("error") or data.get("message") or "").strip()
                    last_err = msg if msg else f"HTTP {r.status_code}"
                else:
                    last_err = f"HTTP {r.status_code}"
            except Exception:
                last_err = f"HTTP {r.status_code}"
            logger.warning("转发目标 %s 失败 %s（不再自动 fallback）", url[:50], r.status_code)
        except Exception as e:
            last_err = str(e)
            logger.warning("转发目标 %s 异常 %s（不再自动 fallback）", url[:50], e)
    return None, last_status, _build_upstream_error_hint(last_err or "")


def _last_user_message(messages):
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() == "user":
            return m
    return None


def _extract_last_user_text(messages) -> str:
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return (content or "").strip().lower()
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and (c.get("type") or "").lower() == "text":
                    parts.append(str(c.get("text") or ""))
            return " ".join(parts).strip().lower()
        return str(content or "").strip().lower()
    return ""


def _parse_iso_ts(ts: str):
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_suspected_rikkahub_phantom_one(body: dict, window_id: str, headers: dict) -> bool:
    """拦截 RikkaHub 偶发误发的单独 '1'（短时间内紧跟上一轮）。"""
    if not RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED:
        return False
    ua = (headers.get("User-Agent") or "").lower()
    if "rikkahub" not in ua:
        return False
    cur_user = (_extract_last_user_text(body.get("messages") or []) or "").strip()
    if cur_user not in ("1", "１"):
        return False
    try:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=1) or []
        if not rounds:
            return False
        last_round = rounds[-1] if isinstance(rounds[-1], dict) else {}
        last_ts = _parse_iso_ts(str(last_round.get("timestamp") or ""))
        if not last_ts:
            return False
        gap_s = (datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)).total_seconds()
        if gap_s < 0 or gap_s > max(1, int(RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS or 90)):
            return False
        prev_user = (_extract_last_user_text(last_round.get("messages") or []) or "").strip()
        if prev_user in ("1", "１"):
            return False
        return True
    except Exception:
        return False


def _build_noop_chat_response(body: dict) -> dict:
    model = (body.get("model") or "noop")
    return {
        "id": f"chatcmpl_noop_{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "（检测到客户端误触发，已忽略本次空输入）"},
                "finish_reason": "stop",
            }
        ],
    }


def _apply_du_thought_to_assistant_response(resp_json: dict) -> dict:
    """
    剥离助手回复中的心事块（老婆侧不可见）；若存在闭合块则写入 R2。
    就地修改 choices[0].message.content。
    """
    if not resp_json or not isinstance(resp_json, dict):
        return resp_json
    choices = resp_json.get("choices") or []
    if not choices:
        return resp_json
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        return resp_json
    content_text = get_assistant_content_text(msg)
    if not content_text:
        return resp_json
    visible_after_pcmd, _ = process_pcmd_in_assistant_text(content_text)
    visible, thought = split_assistant_for_thought(visible_after_pcmd)
    visible, interaction = split_assistant_for_interaction(visible)
    if thought or interaction or visible != content_text:
        msg["content"] = visible
    if thought:
        try:
            r2_store.save_du_thought_latest(now_beijing_iso(), thought)
        except Exception as e:
            logger.warning("save_du_thought_latest 失败 error=%s", e)
    if interaction:
        try:
            r2_store.append_interaction_candidate(interaction)
        except Exception as e:
            logger.warning("append_interaction_candidate 失败 error=%s", e)
    return resp_json


def _append_tool_results_and_continue(body: dict, assistant_message: dict, tool_calls: list, execute_tool) -> dict:
    """执行 tool_calls，将 assistant 消息与各 tool 结果追加到 body["messages"]，返回新 body 供继续请求。"""
    import copy as _copy
    body = _copy.deepcopy(body)
    messages = body.get("messages") or []
    # 保留 assistant 消息（含 tool_calls）
    messages.append({
        "role": "assistant",
        "content": assistant_message.get("content") or None,
        "tool_calls": assistant_message.get("tool_calls"),
    })
    for tc in tool_calls:
        tid = (tc or {}).get("id") or ""
        fn = (tc or {}).get("function") or {}
        name = fn.get("name") or ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        result = execute_tool(name, args)
        messages.append({"role": "tool", "tool_call_id": tid, "content": result})
    body["messages"] = messages
    return body


def _collect_tool_trace_from_messages(messages: list) -> list[dict]:
    """
    从消息链提取工具调用与结果，供存档后 MiniApp 展示。
    返回项结构：{id,type,function:{name,arguments},result}
    """
    out: list[dict] = []
    tool_result_by_id: dict[str, str] = {}
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "tool":
            continue
        tid = str(m.get("tool_call_id") or "").strip()
        if not tid:
            continue
        c = m.get("content")
        if isinstance(c, str):
            tool_result_by_id[tid] = c
        else:
            try:
                tool_result_by_id[tid] = json.dumps(c, ensure_ascii=False)
            except Exception:
                tool_result_by_id[tid] = str(c)
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            row = dict(tc)
            row["result"] = tool_result_by_id.get(tid, "")
            out.append(row)
    return out


def _sse_delta_chunk_bytes(delta_text: str) -> bytes:
    """补发一段 OpenAI 风格 SSE，仅含 delta.content（用于工具后自动附带预览链接）。"""
    payload = {
        "choices": [
            {"index": 0, "delta": {"content": delta_text}, "finish_reason": None},
        ]
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


def _merge_html_preview_into_nonstream_response(resp_json: dict, messages: list) -> dict:
    """非流式：若调用了 publish_html_preview 但正文未含链接，写入 message.content。"""
    if not resp_json or not isinstance(resp_json, dict):
        return resp_json
    choices = resp_json.get("choices") or []
    if not choices:
        return resp_json
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        return resp_json
    ct = msg.get("content")
    if not isinstance(ct, str):
        return resp_json
    merged = merge_html_preview_urls_into_assistant_text(ct, messages)
    if merged != ct:
        msg["content"] = merged
    return resp_json


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
    body = _normalize_request_model(body)
    req_model = (body.get("model") or "").strip() if isinstance(body.get("model"), str) else ""
    if not req_model:
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

    # 走完整管道（清洗、注入记忆/总结、转发、存档）
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_replace_rikka_system(body)
    force_last4 = (request.headers.get("X-Force-Last4") or "").strip().lower() in ("1", "true", "yes")
    tg_user_input = (request.headers.get("X-TG-User-Input") or "").strip().lower() in ("1", "true", "yes")
    slim_voice_call = (request.headers.get("X-Voice-Call-Slim") or "").strip().lower() in ("1", "true", "yes")
    body = step_inject_summary(body, window_id, is_user_input=tg_user_input)
    if not slim_voice_call:
        body = step_inject_sense_snapshot(body, window_id)
        body = step_inject_du_thought(body, window_id)
        body = step_inject_interaction_candidate(body, window_id)
        body = step_inject_wenyou_gm(body, window_id)
        body = step_inject_rikkahub_reminder(body, window_id)
        body = step_inject_dynamic_memory(body, window_id)
        # 口径：窗口总结 + 动态层记忆优先注入，再补 last4
        body = step_inject_latest_4_rounds_for_new_window(body, window_id, force_last4=force_last4)
        body = step_inject_du_notebook(body)
        body = step_inject_notion_search(body, window_id)
        body = step_inject_notion_tools(body)
        body = step_inject_forum_tools(body)
        body = step_inject_websearch_tools(body)
        body = step_inject_html_preview_tool(body, request.headers.get("User-Agent") or "")
    body = _apply_claude_prompt_caching(body)
    body = step_trim_messages_if_over_limit(body)
    # 清理动态 system 标记，避免上游 API 报未知字段错误
    for msg in body.get("messages") or []:
        msg.pop("__dynamic__", None)
    if body.get("stream"):
        return _stream_response(_stream_with_r2_archive(body, headers, window_id))
    # 非流式：命中响应缓存则直接返回，不调上游
    from services.chat_response_cache import get_cache_key, get as cache_get, set as cache_set
    cache_key = get_cache_key(body)
    cached = cache_get(cache_key)
    if cached:
        resp_json, status = cached
        logger.info("Chat 命中响应缓存，未调上游")
        return jsonify(resp_json), status
    resp_json, status, err = _forward_to_ai(body, headers)
    if err:
        logger.error("Chat 转发失败 error=%s", err, exc_info=True)
        return jsonify({"error": err}), status
    if status >= 400:
        logger.warning("Chat 上游返回异常 status=%s", status)
        return jsonify(resp_json or {"error": "upstream error"}), status
    # 非流式 + 有 Notion 工具时：若上游返回 tool_calls，执行工具并继续请求，直到无 tool_calls 或达到最大轮数
    # 工具中间轮次的 reasoning 只留给独立 reasoning 面板，不回填到最终用户可见消息，避免工具 thinking 混入正文轮次。
    max_tool_rounds = 5
    for _ in range(max_tool_rounds - 1):
        msg = (resp_json or {}).get("choices") and (resp_json.get("choices") or [{}])[0].get("message")
        tool_calls = (msg or {}).get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list):
            break
        from services.notion_tools import execute_tool
        body = _append_tool_results_and_continue(body, msg, tool_calls, execute_tool)
        resp_json, status, err = _forward_to_ai(body, headers)
        if err or status >= 400:
            break
    if resp_json:
        resp_json = _apply_du_thought_to_assistant_response(resp_json)
        resp_json = _merge_html_preview_into_nonstream_response(resp_json, body.get("messages") or [])
    if status == 200 and resp_json:
        cache_set(cache_key, resp_json, status)
    if resp_json and (resp_json or {}).get("choices"):
        msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
        content_text = get_assistant_content_text(msg)
        if is_failed_response(content_text):
            logger.info("R2 未存档：上游回复被判为失败（长度/关键词），跳过")
        else:
            # reasoning 兼容字段：尽量保存到 message 里，供手机端折叠查看
            try:
                if isinstance(msg, dict) and not msg.get("reasoning"):
                    for rk in ("reasoning", "reasoning_content", "thinking"):
                        if msg.get(rk):
                            msg["reasoning"] = msg.get(rk)
                            break
            except Exception:
                pass
            tc_trace = _collect_tool_trace_from_messages(body.get("messages") or [])
            if tc_trace and isinstance(msg, dict) and not msg.get("tool_calls"):
                msg["tool_calls"] = tc_trace
            last_user = _last_user_message(body.get("messages"))
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            if last_user:
                round_cleaned = build_round_cleaned_for_r2(last_user, msg)
                step_archive_and_maybe_summary(
                    window_id, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned
                )
            else:
                step_archive_and_maybe_summary(window_id, body.get("messages") or [], msg)
    else:
        logger.info("R2 未存档：上游无 choices 或响应为空")
    return jsonify(resp_json), 200
