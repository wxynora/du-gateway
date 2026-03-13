# 聊天代理：统一走完整管道（清洗、注入、转发、存档），无开头过滤
import json
import requests

from flask import Blueprint, request, jsonify, Response, stream_with_context

from config import (
    TARGET_AI_URL,
    TARGET_AI_API_KEY,
    TARGET_AI_URLS,
    TARGET_AI_API_KEYS,
    GATEWAY_MODELS,
)
from pipeline.pipeline import (
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_replace_rikka_system,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_dynamic_memory,
    step_archive_and_maybe_summary,
)
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.failed_response import get_assistant_content_text, is_failed_response
from utils.log import get_logger

logger = get_logger(__name__)
bp = Blueprint("chat", __name__)

WINDOW_ID_DEFAULT = ""


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


def _stream_with_r2_archive(body: dict, headers: dict):
    """
    包装流式响应：原样转发 SSE，同时在流结束后用收集到的 content 写 R2。
    这样流式请求也会落库，与非流式行为一致。
    """
    content_parts = []
    last_user = _last_user_message(body.get("messages") or [])
    try:
        for chunk in _stream_forward_to_ai(body, headers):
            # 顺带解析 SSE 收集 assistant content（data: {...} 中 choices[0].delta.content）
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
            yield chunk
    finally:
        full_content = "".join(content_parts)
        if is_failed_response(full_content):
            logger.info("R2 未存档：流式回复被判为失败（长度/关键词），跳过")
        elif not full_content.strip():
            logger.info("R2 未存档：流式回复为空，跳过")
        else:
            msg = {"role": "assistant", "content": full_content}
            round_cleaned = build_round_cleaned_for_r2(last_user, msg) if last_user else None
            step_archive_and_maybe_summary(
                WINDOW_ID_DEFAULT,
                body.get("messages") or [],
                msg,
                round_cleaned_for_r2=round_cleaned,
            )
            logger.info("R2 流式请求已存档")


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
    """统一入口：所有请求走完整管道（清洗、注入、转发、存档），无开头过滤。"""
    body = request.get_json(silent=True) or {}
    headers = dict(request.headers) if request.headers else {}
    def _stream_response(gen):
        return Response(
            stream_with_context(gen),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 走完整管道（清洗、注入记忆/总结、转发、存档）
    body = step_clean_images_and_save_desc(body, WINDOW_ID_DEFAULT)
    body = step_clean_for_forward(body)
    body = step_replace_rikka_system(body)
    body = step_inject_latest_4_rounds_for_new_window(body, WINDOW_ID_DEFAULT)
    body = step_inject_summary(body, WINDOW_ID_DEFAULT)
    body = step_inject_dynamic_memory(body, WINDOW_ID_DEFAULT)
    if body.get("stream"):
        return _stream_response(_stream_with_r2_archive(body, headers))
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
    if status == 200 and resp_json:
        cache_set(cache_key, resp_json, status)
    if resp_json and (resp_json or {}).get("choices"):
        msg = (resp_json.get("choices") or [{}])[0].get("message") or {}
        content_text = get_assistant_content_text(msg)
        if is_failed_response(content_text):
            logger.info("R2 未存档：上游回复被判为失败（长度/关键词），跳过")
        else:
            last_user = _last_user_message(body.get("messages"))
            if last_user:
                round_cleaned = build_round_cleaned_for_r2(last_user, msg)
                step_archive_and_maybe_summary(
                    WINDOW_ID_DEFAULT, body.get("messages") or [], msg, round_cleaned_for_r2=round_cleaned
                )
            else:
                step_archive_and_maybe_summary(WINDOW_ID_DEFAULT, body.get("messages") or [], msg)
    else:
        logger.info("R2 未存档：上游无 choices 或响应为空")
    return jsonify(resp_json), 200
