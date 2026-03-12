# 聊天代理：黑名单只转发且响应末尾加「（黑名单）」；新窗默认白名单，新窗+user含「测试」→黑名单
import requests

from flask import Blueprint, request, jsonify

from config import (
    TARGET_AI_URL,
    TARGET_AI_API_KEY,
    TARGET_AI_URLS,
    TARGET_AI_API_KEYS,
    WINDOW_ID_HEADER,
    TEST_BLACKLIST_KEYWORD,
)
from pipeline.pipeline import (
    get_window_id,
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

BLACKLIST_SUFFIX = "\n\n（黑名单）"


def _user_message_contains_keyword(messages, keyword: str) -> bool:
    """最后一条 user 消息的纯文本是否包含 keyword。"""
    if not (keyword and keyword.strip()):
        return False
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return keyword in content
        if isinstance(content, list):
            text = " ".join(
                c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
            )
            return keyword in text
        return False
    return False


def _append_blacklist_suffix_to_response(resp_json: dict) -> None:
    """在响应体里 assistant 内容末尾追加「（黑名单）」；就地修改。"""
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
        msg["content"] = content.rstrip() + BLACKLIST_SUFFIX
        return
    if isinstance(content, list):
        last_text_idx = -1
        for i in range(len(content) - 1, -1, -1):
            if (content[i] or {}).get("type") == "text":
                last_text_idx = i
                break
        if last_text_idx >= 0:
            content[last_text_idx]["text"] = (
                (content[last_text_idx].get("text") or "").rstrip() + BLACKLIST_SUFFIX
            )
        else:
            content.append({"type": "text", "text": BLACKLIST_SUFFIX.strip()})


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


def _forward_to_ai(body: dict, headers: dict):
    """将请求体转发到配置的 AI 接口，支持多目标 fallback：一个失败试下一个。返回 (response_json, status_code, error)。"""
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
            r = requests.post(url, headers=req_headers, json=body, timeout=120)
            data = r.json() if r.content else None
            # 只有 2xx 算成功，其余（4xx/5xx/429 等）都 fallback 到下一个
            if 200 <= r.status_code < 300:
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


@bp.route("/v1/models", methods=["GET"])
@bp.route("/models", methods=["GET"])
def list_models():
    """
    代理到中转站的 GET /v1/models，这样 RikkaHub 填网关地址时也能拉取到模型列表。
    用第一个转发目标的地址和 Key。
    """
    targets = _get_forward_targets()
    if not targets:
        return jsonify({"error": "TARGET_AI_URL 或 TARGET_AI_URLS 未配置"}), 502
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
        return jsonify(data or {}), r.status_code
    except Exception as e:
        logger.warning("拉取模型列表失败 %s error=%s", models_url, e)
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
    window_id = get_window_id(headers, body)

    # 1) 黑名单：只转发，响应末尾加「（黑名单）」提示
    if blacklist_store.is_blacklisted(window_id):
        whitelist_store.record_recent_window(window_id)
        body_forward = step_clean_for_forward(body)
        resp_json, status, err = _forward_to_ai(body_forward, headers)
        if err:
            return jsonify({"error": err}), status
        if status >= 400:
            return jsonify(resp_json or {"error": "upstream error"}), status
        _append_blacklist_suffix_to_response(resp_json)
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
        resp_json, status, err = _forward_to_ai(body_forward, headers)
        if err:
            return jsonify({"error": err}), status
        if status >= 400:
            return jsonify(resp_json or {"error": "upstream error"}), status
        _append_blacklist_suffix_to_response(resp_json)
        logger.info("新窗含「测试」，已加入黑名单 window_id=%s", window_id)
        return jsonify(resp_json), 200

    whitelist_store.add_to_whitelist(window_id)
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_inject_latest_4_rounds_for_new_window(body, window_id)
    body = step_inject_summary(body, window_id)
    body = step_inject_dynamic_memory(body, window_id)
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
