# 聊天代理：黑名单只转发且响应末尾加「（黑名单）」；新窗默认白名单，新窗+user含「测试」→黑名单
import json
import requests

from flask import Blueprint, request, jsonify, Response, stream_with_context

from config import (
    TARGET_AI_URL,
    TARGET_AI_API_KEY,
    TARGET_AI_URLS,
    TARGET_AI_API_KEYS,
    GATEWAY_MODELS,
    WINDOW_ID_HEADER,
    TEST_BLACKLIST_KEYWORD,
    ALLOWED_ASSISTANT_IDS,
)
from pipeline.pipeline import (
    get_window_id,
    get_assistant_id,
    step_whitelist_and_record,
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_dynamic_memory,
    step_archive_and_maybe_summary,
)
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.failed_response import get_assistant_content_text, is_failed_response
from storage import whitelist_store, blacklist_store
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)
bp = Blueprint("chat", __name__)

BLACKLIST_PREFIX = "（黑名单）\n\n"


def _user_message_contains_keyword(messages, keyword: str) -> bool:
    """最后一条 user 消息的纯文本是否包含 keyword。兼容 content 为 list 时 part 用 text 或 content 字段。"""
    if not (keyword and keyword.strip()):
        return False
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return keyword in content
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(c.get("text") or c.get("content") or "")
                else:
                    parts.append(str(c))
            text = " ".join(parts)
            return keyword in text
        return False
    return False


def _prepend_blacklist_prefix_to_response(resp_json: dict) -> None:
    """在响应体里 assistant 内容开头加「（黑名单）」标识；就地修改。"""
    if not resp_json:
        return
    choices = resp_json.get("choices")
    if not choices:
        return
    msg = (choices[0] or {}).get("message")
    if not msg:
        return
    content = msg.get("content")
    if isinstance(content, str):
        msg["content"] = BLACKLIST_PREFIX + content.lstrip()
        return
    if isinstance(content, list):
        first_text_idx = -1
        for i, part in enumerate(content):
            if (part or {}).get("type") == "text":
                first_text_idx = i
                break
        if first_text_idx >= 0:
            content[first_text_idx]["text"] = (
                BLACKLIST_PREFIX + (content[first_text_idx].get("text") or "").lstrip()
            )
        else:
            content.insert(0, {"type": "text", "text": BLACKLIST_PREFIX.strip()})


def _get_forward_targets():
    """返回 [(url, api_key), ...]，按顺序尝试；未配置多目标时用 TARGET_AI_URL + TARGET_AI_API_KEY。"""
    if TARGET_AI_URLS:
        urls = TARGET_AI_URLS
        keys = TARGET_AI_API_KEYS
        while len(keys) < len(urls):
            keys.append(TARGET_AI_API_KEY)
        return list(zip(urls, keys[: len(urls)]))
    if TARGET_AI_URL:
        return [(TARGET_AI_URL, TARGET_AI_API_KEY)]
    return []


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


def _stream_forward_to_ai(body: dict, headers: dict):
    """流式转发：上游 SSE 原样逐行 yield，供 Flask 以 text/event-stream 返回。RikkaHub 等客户端要流式才正常显示。"""
    targets = _get_forward_targets()
    if not targets:
        yield ("data: " + json.dumps({"error": "TARGET_AI_URL 或 TARGET_AI_URLS 未配置"}) + "\n\n").encode("utf-8")
        return
    url, api_key = targets[0]
    req_headers = {"Content-Type": "application/json"}
    if api_key:
        req_headers["Authorization"] = f"Bearer {api_key}"
    for h in ("Accept", "Accept-Encoding"):
        if request.headers.get(h):
            req_headers[h] = request.headers.get(h)
    body_send = dict(body)
    body_send["stream"] = True
    try:
        r = requests.post(url, headers=req_headers, json=body_send, timeout=120, stream=True)
        if r.status_code != 200:
            yield ("data: " + json.dumps({"error": f"上游 HTTP {r.status_code}"}) + "\n\n").encode("utf-8")
            return
        for line in r.iter_lines():
            if line is not None:
                yield line + b"\n"
            else:
                yield b"\n"
    except Exception as e:
        logger.warning("流式转发异常 %s %s", url[:50], e)
        yield ("data: " + json.dumps({"error": str(e)}) + "\n\n").encode("utf-8")


def _forward_to_ai(body: dict, headers: dict):
    """将请求体转发到配置的 AI 接口，支持多目标 fallback：一个失败试下一个。返回 (response_json, status_code, error)。非流式。"""
    targets = _get_forward_targets()
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
    targets = _get_forward_targets()
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
    """
    统一入口：黑名单只转发；新窗观察期前 N 轮只转发并缓存，满 N 轮判定测试窗→黑名单否则进白名单并回放缓存；
    已有白名单窗口走完整管道。
    """
    body = request.get_json(silent=True) or {}
    headers = dict(request.headers) if request.headers else {}
    # DEBUG：打出 RikkaHub 发来的原始请求（未做任何清洗/注入），便于看结构、做关键字段提取
    if logger.isEnabledFor(10):
        try:
            h = {k: v for k, v in (headers or {}).items() if k.lower() in ("x-window-id", "x-assistant-id", "content-type")}
            msgs = body.get("messages") or []
            msg_preview = []
            for i, m in enumerate(msgs[:3]):
                role = (m or {}).get("role")
                content = (m or {}).get("content")
                if isinstance(content, str):
                    preview = content[:80] + ("..." if len(content) > 80 else "")
                    msg_preview.append(f"#{i} role={role} content_len={len(content)} content_preview={preview}")
                else:
                    msg_preview.append(f"#{i} role={role} content_type={type(content).__name__}")
            if len(msgs) > 3:
                msg_preview.append(f"... 共 {len(msgs)} 条")
            raw_sample = json.dumps(body, ensure_ascii=False)[:3000]
            logger.debug(
                "收到原始请求 body_keys=%s body_id=%s body_assistant_id=%s body_window_id=%s headers=%s messages=%s raw_body_sample=%s",
                list(body.keys()),
                body.get("id"),
                body.get("assistant_id"),
                body.get("window_id"),
                h,
                msg_preview,
                raw_sample,
            )
        except Exception:
            pass
    window_id = get_window_id(headers, body)
    assistant_id = get_assistant_id(headers, body)
    # 每条请求打一行，便于确认 RikkaHub 自定义请求头是否带到网关；若 id 一直为空，看 all_x_headers 里有没有
    all_x_headers = {k: v for k, v in (headers or {}).items() if k.upper().startswith("X-")}
    logger.info(
        "chat 收到 window_id=%s assistant_id=%s all_x_headers=%s body_id=%s body_assistant_id=%s",
        repr(window_id),
        repr(assistant_id),
        all_x_headers,
        repr(body.get("id")),
        repr(body.get("assistant_id")),
    )

    def _stream_response(gen):
        return Response(
            stream_with_context(gen),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 1) 黑名单：只转发，响应加「（黑名单）」前缀
    if blacklist_store.is_blacklisted(window_id):
        whitelist_store.record_recent_window(window_id)
        body_forward = step_clean_for_forward(body)
        if body.get("stream"):
            return _stream_response(_stream_forward_to_ai(body_forward, headers))
        resp_json, status, err = _forward_to_ai(body_forward, headers)
        if err:
            return jsonify({"error": err}), status
        if status >= 400:
            return jsonify(resp_json or {"error": "upstream error"}), status
        _prepend_blacklist_prefix_to_response(resp_json)
        return jsonify(resp_json), 200

    # 1.5) 配置了 ALLOWED_ASSISTANT_IDS 时：只允许列表内的 assistant_id 走后续进程，其余仅转发
    if ALLOWED_ASSISTANT_IDS and assistant_id not in ALLOWED_ASSISTANT_IDS:
        body_forward = step_clean_for_forward(body)
        if body.get("stream"):
            return _stream_response(_stream_forward_to_ai(body_forward, headers))
        resp_json, status, err = _forward_to_ai(body_forward, headers)
        if err:
            return jsonify({"error": err}), status
        if status >= 400:
            return jsonify(resp_json or {"error": "upstream error"}), status
        return jsonify(resp_json), 200

    # 2) 已有历史窗口：白名单内走完整管道，否则只转发
    has_history = r2_store.has_window_history(window_id)
    if has_history:
        in_whitelist, err = step_whitelist_and_record(window_id, headers)
        if err:
            return jsonify({"error": err}), 400
        if in_whitelist:
            body = step_clean_images_and_save_desc(body, window_id)
            body = step_clean_for_forward(body)
            body = step_inject_latest_4_rounds_for_new_window(body, window_id)
            body = step_inject_summary(body, window_id)
            body = step_inject_dynamic_memory(body, window_id)
        if body.get("stream"):
            return _stream_response(_stream_forward_to_ai(body, headers))
        resp_json, status, err = _forward_to_ai(body, headers)
        if err:
            logger.error("Chat 转发失败 window_id=%s error=%s", window_id, err, exc_info=True)
            return jsonify({"error": err}), status
        if status >= 400:
            logger.warning("Chat 上游返回异常 window_id=%s status=%s", window_id, status)
            return jsonify(resp_json or {"error": "upstream error"}), status
        if in_whitelist and window_id and resp_json and (resp_json or {}).get("choices"):
            msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
            if not is_failed_response(get_assistant_content_text(msg)):
                last_user = _last_user_message(body.get("messages"))
                if last_user:
                    round_cleaned = build_round_cleaned_for_r2(last_user, msg)
                    step_archive_and_maybe_summary(
                        window_id, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned
                    )
                else:
                    step_archive_and_maybe_summary(window_id, body.get("messages") or [], msg)
        return jsonify(resp_json), 200

    # 3) 新窗口：本条 user 含「测试」→黑名单（只转发+末尾提示）；否则进白名单并走完整管道
    whitelist_store.record_recent_window(window_id)
    last_user_text_contains_test = _user_message_contains_keyword(
        body.get("messages"), TEST_BLACKLIST_KEYWORD
    )
    if last_user_text_contains_test:
        blacklist_store.add_to_blacklist(window_id)
        body_forward = step_clean_for_forward(body)
        if body.get("stream"):
            return _stream_response(_stream_forward_to_ai(body_forward, headers))
        resp_json, status, err = _forward_to_ai(body_forward, headers)
        if err:
            return jsonify({"error": err}), status
        if status >= 400:
            return jsonify(resp_json or {"error": "upstream error"}), status
        _prepend_blacklist_prefix_to_response(resp_json)
        logger.info("新窗含「测试」，已加入黑名单 window_id=%s", window_id)
        return jsonify(resp_json), 200

    whitelist_store.add_to_whitelist(window_id)
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_inject_latest_4_rounds_for_new_window(body, window_id)
    body = step_inject_summary(body, window_id)
    body = step_inject_dynamic_memory(body, window_id)
    if body.get("stream"):
        return _stream_response(_stream_forward_to_ai(body, headers))
    resp_json, status, err = _forward_to_ai(body, headers)
    if err:
        logger.error("Chat 转发失败 window_id=%s error=%s", window_id, err, exc_info=True)
        return jsonify({"error": err}), status
    if status >= 400:
        logger.warning("Chat 上游返回异常 window_id=%s status=%s", window_id, status)
        return jsonify(resp_json or {"error": "upstream error"}), status
    if window_id and resp_json and (resp_json or {}).get("choices"):
        msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
        if not is_failed_response(get_assistant_content_text(msg)):
            last_user = _last_user_message(body.get("messages"))
            if last_user:
                round_cleaned = build_round_cleaned_for_r2(last_user, msg)
                step_archive_and_maybe_summary(
                    window_id, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned
                )
            else:
                step_archive_and_maybe_summary(window_id, body.get("messages") or [], msg)
    return jsonify(resp_json), 200
