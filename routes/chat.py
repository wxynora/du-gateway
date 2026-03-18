# 聊天代理：统一走完整管道（清洗、注入、转发、存档），无开头过滤
import json
import queue
import threading
import time
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
)
from pipeline.pipeline import (
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_replace_rikka_system,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_rikkahub_reminder,
    step_inject_tg_pinned_note,
    step_inject_dynamic_memory,
    step_inject_notion_search,
    step_inject_notion_tools,
    step_trim_messages_if_over_limit,
    step_archive_and_maybe_summary,
)
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.failed_response import get_assistant_content_text, is_failed_response
from utils.log import get_logger

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


def _get_forward_targets(request_model: str = None):
    """
    返回 [(url, api_key), ...]，按顺序尝试。
    先加入单独的 TARGET_AI_URL（若有），再加入 TARGET_AI_URLS 列表（同 URL 不重复）。
    多目标时：若 request_model 匹配关键词（claude/opus/4或5/thinking），返回全部用于 fallback；
    否则只返回第一个，避免非匹配模型打到所有中转站。
    """
    pairs = []
    seen_urls = set()
    if TARGET_AI_URL and TARGET_AI_URL.strip():
        u = TARGET_AI_URL.strip()
        if u not in seen_urls:
            pairs.append((u, TARGET_AI_API_KEY or ""))
            seen_urls.add(u)
    if TARGET_AI_URLS:
        urls = TARGET_AI_URLS
        keys = list(TARGET_AI_API_KEYS)
        while len(keys) < len(urls):
            keys.append(TARGET_AI_API_KEY or "")
        for u, k in zip(urls, keys[: len(urls)]):
            u = (u or "").strip()
            if u and u not in seen_urls:
                pairs.append((u, k or ""))
                seen_urls.add(u)
    if len(pairs) > 1 and request_model is not None:
        if not model_matches_gateway_keywords(request_model):
            return [pairs[0]]
    return pairs


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
    返回 {"content": str, "tool_calls": list or None}，tool_calls 为 OpenAI 格式。
    """
    content_parts = []
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
    }


def _stream_forward_to_ai(body: dict, headers: dict):
    """流式转发：上游 SSE 原样逐行 yield；多目标时按顺序 fallback，一个失败试下一个。"""
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        yield ("data: " + json.dumps({"error": "TARGET_AI_URL 或 TARGET_AI_URLS 未配置"}) + "\n\n").encode("utf-8")
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
    yield ("data: " + json.dumps({"error": last_err or "所有中转站均失败"}) + "\n\n").encode("utf-8")


def _stream_with_r2_archive(body: dict, headers: dict, window_id: str = ""):
    """
    包装流式响应：原样转发 SSE，同时在流结束后用收集到的 content 写 R2。
    当请求带 tools 时：先缓冲整段流，解析 message；若有 tool_calls 则执行工具并继续请求（循环），
    最后把「无 tool_calls」那一轮的流发给客户端，实现与 RikkaHub 类似的流式+工具行为。
    无 tools 时：边收边发，不缓冲，保持原有实时流式。
    """
    content_parts = []
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
                        yield b"".join(buf)
                        break

                yield b"".join(buf)
                last_send_ts = time.time()
        finally:
            full_content = "".join(content_parts)
            stream_sec = time.time() - stream_start
            # 若「流式持续时长」总是差不多（如 10–20s）而字数越来越短，可能是上游按时长限流
            logger.debug("本轮流式回复收集长度约 %s 字符，共转发 %s 个 data 块，流式持续约 %.1f 秒", len(full_content), data_chunk_count, stream_sec)
            if not is_failed_response(full_content) and full_content.strip():
                msg = {"role": "assistant", "content": full_content}
                round_cleaned = build_round_cleaned_for_r2(last_user, msg) if last_user else None
                logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
                step_archive_and_maybe_summary(
                    window_id, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned,
                )
                try:
                    from services.notion_write_from_assistant import process_assistant_content_for_notion_write
                    process_assistant_content_for_notion_write(full_content)
                except Exception:
                    pass
                logger.info("R2 流式请求已存档")
            elif is_failed_response(full_content):
                logger.info("R2 未存档：流式回复被判为失败，跳过")
            elif not full_content.strip():
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
                current_body = _append_tool_results_and_continue(current_body, msg, tool_calls, execute_tool)
                continue
            for ch in chunks:
                yield ch
            content_parts.append(parsed.get("content") or "")
            break
    finally:
        full_content = "".join(content_parts)
        logger.info("本轮流式回复收集长度约 %s 字符", len(full_content))
        if is_failed_response(full_content):
            logger.info("R2 未存档：流式回复被判为失败，跳过")
        elif not full_content.strip():
            logger.info("R2 未存档：流式回复为空，跳过")
        else:
            msg = {"role": "assistant", "content": full_content}
            round_cleaned = build_round_cleaned_for_r2(last_user, msg) if last_user else None
            logger.info("存档/动态层触发 remote=%s ua=%s", request.remote_addr, (request.headers.get("User-Agent") or "")[:80])
            step_archive_and_maybe_summary(
                window_id, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned,
            )
            try:
                from services.notion_write_from_assistant import process_assistant_content_for_notion_write
                process_assistant_content_for_notion_write(full_content)
            except Exception:
                pass
            logger.info("R2 流式请求已存档")


def _forward_to_ai(body: dict, headers: dict):
    """将请求体转发到配置的 AI 接口，支持多目标 fallback：一个失败试下一个。返回 (response_json, status_code, error)。非流式。"""
    request_model = (body or {}).get("model") or ""
    targets = _get_forward_targets(request_model)
    if not targets:
        return None, 502, "TARGET_AI_URL 或 TARGET_AI_URLS 未配置"
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
            # 只有 2xx 算成功，其余（4xx/5xx/429 等）都 fallback 到下一个
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
            last_err = f"HTTP {r.status_code}"
            logger.warning("转发目标 %s 失败 %s，尝试下一个", url[:50], r.status_code)
        except Exception as e:
            last_err = str(e)
            logger.warning("转发目标 %s 异常 %s，尝试下一个", url[:50], e)
    return None, last_status, last_err


def _last_user_message(messages):
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() == "user":
            return m
    return None


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
    若上游没有该接口或拉取失败，且配置了 GATEWAY_MODELS，则返回静态列表。
    """
    targets = _get_forward_targets(None)
    if not targets:
        static = _static_models_response()
        if static:
            return jsonify(static), 200
        return jsonify({"error": "TARGET_AI_URL 或 TARGET_AI_URLS 未配置"}), 502
    url, api_key = targets[0]
    models_url = _chat_url_to_models_url(url)
    if not models_url:
        static = _static_models_response()
        if static:
            return jsonify(static), 200
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
        # 否则用静态列表兜底（若配置了）
        static = _static_models_response()
        if static:
            logger.info("上游模型列表不可用或为空，使用 GATEWAY_MODELS 兜底")
            return jsonify(static), 200
        return jsonify(data or {"error": "上游未返回模型列表"}), r.status_code if r.status_code != 200 else 502
    except Exception as e:
        logger.warning("拉取模型列表失败 %s error=%s", models_url, e)
        static = _static_models_response()
        if static:
            return jsonify(static), 200
        return jsonify({"error": str(e)}), 502


@bp.route("/v1/chat/completions", methods=["POST"])
@bp.route("/chat/completions", methods=["POST"])
def chat_completions():
    """统一入口：所有请求走完整管道（清洗、注入、转发、存档），无开头过滤。支持 X-Window-Id / body.window_id（如 Telegram 用 tg_{user_id}）。"""
    body = request.get_json(silent=True) or {}
    headers = dict(request.headers) if request.headers else {}
    window_id = _get_window_id_from_request(body)

    def _stream_response(gen):
        return Response(
            stream_with_context(gen),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 走完整管道（清洗、注入记忆/总结、转发、存档）
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_replace_rikka_system(body)
    body = step_inject_latest_4_rounds_for_new_window(body, window_id)
    body = step_inject_summary(body, window_id)
    body = step_inject_rikkahub_reminder(body, window_id)
    body = step_inject_tg_pinned_note(body, window_id)
    body = step_inject_dynamic_memory(body, window_id)
    body = step_inject_notion_search(body, window_id)
    body = step_inject_notion_tools(body)
    body = step_trim_messages_if_over_limit(body)
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
    if status == 200 and resp_json:
        cache_set(cache_key, resp_json, status)
    if resp_json and (resp_json or {}).get("choices"):
        msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
        content_text = get_assistant_content_text(msg)
        if is_failed_response(content_text):
            logger.info("R2 未存档：上游回复被判为失败（长度/关键词），跳过")
        else:
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
