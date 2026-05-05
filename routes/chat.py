# 聊天代理：统一走完整管道（清洗、注入、转发、存档），无开头过滤
# 项目约定：主聊天禁止默认兜底模型。没传 model 就直接报错，不要偷偷补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
import json
import queue
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from difflib import unified_diff
from urllib.parse import urlparse
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
    TOOL_MAX_ROUNDS,
    RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED,
    RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS,
    DATA_DIR,
    SILICONFLOW_BASE_HOST,
    SILICONFLOW_DEFAULT_MODEL,
    OPENROUTER_FIXED_MODEL,
    OPENROUTER_REASONING_MAX_TOKENS,
    OPENROUTER_VERBOSITY,
    OPENROUTER_ULTRA_THINK_ENABLED,
    OPENROUTER_ULTRA_THINK_PROMPT,
    OPENROUTER_PROVIDER_ORDER,
    OPENROUTER_ALLOW_FALLBACKS,
    OPENROUTER_CACHE_CONTROL_TYPE,
    is_openrouter_url,
    openrouter_models_response,
)
from pipeline.pipeline import (
    step_clean_images_and_save_desc,
    step_clean_for_forward,
    step_replace_rikka_system,
    step_inject_thinking_block_rules,
    step_inject_core_behavior_rules,
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
    step_inject_notion_search,
    step_inject_notion_tools,
    step_inject_forum_tools,
    step_inject_amap_mcp_tools,
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
from services.du_daily import (
    build_chat_trigger as build_du_daily_trigger,
    looks_like_plain_maintenance_daily,
    save_hidden_block as save_du_daily_hidden_block,
    split_assistant_for_daily,
)
from services.interaction_memory import split_assistant_for_interaction
from services.dynamic_memory_citation import (
    DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY,
    normalize_citation_map,
    strip_assistant_memory_citations,
)
from services.html_preview_tools import (
    merge_html_preview_urls_into_assistant_text,
    missing_html_preview_url_suffix,
)
from services.device_action_tools import (
    dedupe_sumitalk_cards_in_text,
    merge_sumitalk_cards_into_assistant_text,
)
from services.conversation_followup import (
    build_followup_system_instruction,
    queue_followup,
)
from services.pc_command_handler import (
    PcmdDuThoughtStreamState,
    process_pcmd_in_assistant_text,
    transform_sse_chunk_bytes as transform_sse_chunk_bytes_pcmd,
)
from services.telegram_bot import build_telegram_style_system
from utils.log import get_logger
from utils.time_aware import now_beijing_iso
from utils.tokens import estimate_tokens

logger = get_logger(__name__)
sumitalk_logger = get_logger("sumitalk")
bp = Blueprint("chat", __name__)

WINDOW_ID_DEFAULT = ""
_NSFW_PROMPT_CACHE = {"text": None, "ts": 0.0}
_NSFW_REPLY_CHANNELS = {"tg", "qq", "wechat", "sumitalk"}


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


def _build_sumitalk_style_system() -> str:
    entry_style = (
        "【入口风格：SumiTalk】\n"
        "你现在通过 SumiTalk 和她相处，这是现实物理层入口。你可以通过语言、网关、设备状态、位置、日程、闹钟、传感器等参与她的现实生活。\n"
        "你可以亲密、暧昧、想象、安抚，也可以承接她的欲望；但不要声称自己真实拥有肉身，不要凭空说自己看见、触碰、完成了现实中没有发生、也没有设备支持的物理行为。\n"
        "除非她主动问身份、现实能力或边界，或者可能误导现实判断，否则不要反复解释“我是 AI / LLM / 隔着屏幕”。"
    )
    output_style = build_telegram_style_system(include_channel_hint=False).strip()
    return (entry_style + "\n\n" + output_style).strip()


def _inject_miniapp_style_system(body: dict) -> dict:
    if not _is_miniapp_request():
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    style_system = _build_sumitalk_style_system()
    if not style_system:
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip() == "system":
        current = str(messages[0].get("content") or "")
        if style_system in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + style_system).strip()}
    else:
        messages.insert(0, {"role": "system", "content": style_system})
    body = dict(body)
    body["messages"] = messages
    return body


def _inject_followup_instruction(body: dict) -> dict:
    if (request.headers.get("X-DU-FOLLOWUP-GEN") or "").strip().lower() in ("1", "true", "yes"):
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    instruction = build_followup_system_instruction().strip()
    if not instruction:
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip() == "system":
        current = str(messages[0].get("content") or "")
        if instruction in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + instruction).strip()}
    else:
        messages.insert(0, {"role": "system", "content": instruction})
    body = dict(body)
    body["messages"] = messages
    return body


def _load_nsfw_prompt() -> str:
    """读取 NSFW 规则文件（短缓存，便于热更新）。"""
    now = time.time()
    cache_ttl_s = 5.0
    if _NSFW_PROMPT_CACHE["text"] is not None and (now - float(_NSFW_PROMPT_CACHE.get("ts") or 0.0) <= cache_ttl_s):
        return _NSFW_PROMPT_CACHE["text"] or ""
    text = ""
    try:
        path = Path(__file__).resolve().parent.parent / "prompts" / "du_nsfw_prompt.txt"
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
    except Exception:
        logger.exception("读取 NSFW prompt 文件失败")
        text = ""
    _NSFW_PROMPT_CACHE["text"] = text or ""
    _NSFW_PROMPT_CACHE["ts"] = now
    return _NSFW_PROMPT_CACHE["text"] or ""


def _inject_channel_nsfw_system(body: dict) -> dict:
    """在指定渠道请求中，把 NSFW 规则固定追加到入口 system 后面。"""
    if _reply_channel() not in _NSFW_REPLY_CHANNELS:
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    nsfw_system = _load_nsfw_prompt().strip()
    if not nsfw_system:
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip().lower() == "system":
        current = str(messages[0].get("content") or "")
        if nsfw_system in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + nsfw_system).strip()}
    else:
        messages.insert(0, {"role": "system", "content": nsfw_system})
    body = dict(body)
    body["messages"] = messages
    return body


def _is_followup_generation_request() -> bool:
    return (request.headers.get("X-DU-FOLLOWUP-GEN") or "").strip().lower() in ("1", "true", "yes")


def _should_archive_followup_generation_request() -> bool:
    return (request.headers.get("X-DU-FOLLOWUP-ARCHIVE") or "").strip().lower() in ("1", "true", "yes")


def _normalize_request_model(body: dict) -> dict:
    """
    特例处理：
    - 若当前 active 上游指向硅基流动（hostname 匹配 SILICONFLOW_BASE_HOST），
      则无条件固定为 SILICONFLOW_DEFAULT_MODEL（忽略客户端传入 model）。
    - 其他上游保持项目约定：未传 model 时直接报错，不做默认兜底。
    """
    body = dict(body or {})

    # 若未配置硅基流动默认模型，保持原行为
    if not (SILICONFLOW_BASE_HOST and SILICONFLOW_DEFAULT_MODEL):
        # 非硅基路径：已显式传 model 则不改
        m = body.get("model")
        if isinstance(m, str) and m.strip():
            return body
        return body

    # 获取当前 active 上游 URL；失败时退回环境变量中的首个 URL
    url = ""
    try:
        from storage.upstream_store import get_active_item

        active = get_active_item() or {}
        url = (active.get("url") or "").strip()
    except Exception:
        url = ""
    if not url:
        if TARGET_AI_URL and TARGET_AI_URL.strip():
            url = TARGET_AI_URL.strip()
        elif TARGET_AI_URLS:
            url = (TARGET_AI_URLS[0] or "").strip()

    host = (urlparse(url).hostname or "").lower()
    # 仅当当前上游指向硅基流动时，无条件固定 model 为默认 GLM
    if host and host.endswith(SILICONFLOW_BASE_HOST):
        body["model"] = SILICONFLOW_DEFAULT_MODEL

    return body


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


def _get_active_upstream_url() -> str:
    try:
        from storage.upstream_store import get_active_item

        active = get_active_item() or {}
        url = (active.get("url") or "").strip()
        if url:
            return url
    except Exception:
        pass

    if TARGET_AI_URL and TARGET_AI_URL.strip():
        return TARGET_AI_URL.strip()
    if TARGET_AI_URLS:
        return (TARGET_AI_URLS[0] or "").strip()
    return ""


def _is_local_cliproxyapi_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in ("127.0.0.1", "localhost") and parsed.port == 8317


def _is_local_claude_oauth_proxy_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in ("127.0.0.1", "localhost") and parsed.port == 8082


def _apply_active_model_request_policy(body: dict, upstream_url: str) -> dict:
    body = dict(body or {})
    try:
        from storage.upstream_store import get_active_item, get_cached_active_model

        active = get_active_item() or {}
        active_url = str(active.get("url") or "").strip()
        if active_url and active_url == str(upstream_url or "").strip():
            model = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
            if model:
                body["model"] = model
            if _is_local_cliproxyapi_url(upstream_url):
                body.pop("reasoning", None)
                body["reasoning_effort"] = "high"
    except Exception:
        pass
    return body


def _apply_openrouter_request_policy(body: dict, upstream_url: str) -> dict:
    body = dict(body or {})
    if not is_openrouter_url(upstream_url):
        return body
    if OPENROUTER_FIXED_MODEL:
        body["model"] = OPENROUTER_FIXED_MODEL
    reasoning = body.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}
    reasoning["enabled"] = True
    if OPENROUTER_REASONING_MAX_TOKENS > 0:
        reasoning["max_tokens"] = OPENROUTER_REASONING_MAX_TOKENS
    body["reasoning"] = reasoning
    if OPENROUTER_VERBOSITY:
        body["verbosity"] = OPENROUTER_VERBOSITY
    if OPENROUTER_PROVIDER_ORDER:
        body["provider"] = {
            "order": OPENROUTER_PROVIDER_ORDER,
            "allow_fallbacks": OPENROUTER_ALLOW_FALLBACKS,
        }
    if OPENROUTER_CACHE_CONTROL_TYPE:
        body["cache_control"] = {"type": OPENROUTER_CACHE_CONTROL_TYPE}
    if OPENROUTER_ULTRA_THINK_ENABLED and OPENROUTER_ULTRA_THINK_PROMPT:
        body["messages"] = _inject_openrouter_ultra_think_prompt(body.get("messages") or [])
    return body


_OPENROUTER_REASONING_OMITTED_HINT = "（模型已进行 adaptive thinking，但当前上游未返回可展示的思维链正文）"


def _inject_openrouter_ultra_think_prompt(messages: list) -> list:
    items = [dict(m) for m in (messages or []) if isinstance(m, dict)]
    if not OPENROUTER_ULTRA_THINK_PROMPT:
        return items
    hint = OPENROUTER_ULTRA_THINK_PROMPT.strip()
    for idx, msg in enumerate(items):
        if str(msg.get("role") or "").strip().lower() != "system":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            if content.lstrip().startswith(hint):
                msg["content"] = content.lstrip()
                items[idx] = msg
                return items
            msg["content"] = hint + "\n\n" + content.lstrip()
            items[idx] = msg
            return items
        if isinstance(content, list):
            blocks = [dict(x) for x in content if isinstance(x, dict)]
            first = blocks[0] if blocks else None
            if isinstance(first, dict) and str(first.get("type") or "").strip().lower() == "text":
                text = str(first.get("text") or "")
                if text.lstrip().startswith(hint):
                    msg["content"] = blocks
                    items[idx] = msg
                    return items
            msg["content"] = [{"type": "text", "text": hint}, *blocks]
            items[idx] = msg
            return items
        msg["content"] = hint
        items[idx] = msg
        return items
    if items:
        return [{"role": "system", "content": hint}, *items]
    return [{"role": "system", "content": hint}]


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


_THINK_BLOCK_RE = re.compile(r"<(think|thinking)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
_TOOL_MIDSTREAM_TEXT_RE = re.compile(
    r"(let me (check|look|see|read|inspect)"
    r"|i(?:'|’)ll (check|look|see|read|inspect)"
    r"|guide doesn.?t mention"
    r"|tool description"
    r"|我(?:先|再)?(?:去)?(?:看一下|看看|看一眼|查一下|查查|再看|再查|看下)"
    r"|先看一下"
    r"|先查一下"
    r"|工具说明"
    r"|命令说明)",
    re.IGNORECASE,
)
_TOOL_MIDSTREAM_RETRY_INSTRUCTION = (
    "如果还需要信息，直接继续调用工具；不知道该调用什么工具就直接进行最终回复。\n"
    "如果已经够了，直接给最终答复。"
)
_TOOL_EMPTY_FINAL_RETRY_INSTRUCTION = (
    "前面的工具已经执行过了。\n"
    "如果还需要信息，直接继续调用工具；如果已经够了，必须直接给用户一条可见的最终回复。\n"
    "不要返回空 content，不要只给 reasoning / thinking。"
)


def _build_prompt_cache_profile(body: dict, upstream_url: str = "") -> dict:
    messages = (body or {}).get("messages") or []
    tools = (body or {}).get("tools") or []
    static_chars = 0
    dynamic_chars = 0
    leading_system_chars = 0
    total_message_chars = 0
    dynamic_marker_seen = False
    for m in messages:
        if not isinstance(m, dict):
            continue
        chars = _message_content_chars(m.get("content"))
        total_message_chars += chars
    for m in messages:
        if not isinstance(m, dict):
            break
        if str(m.get("role") or "").strip().lower() != "system":
            break
        chars = _message_content_chars(m.get("content"))
        leading_system_chars += chars
        if m.get("__dynamic__"):
            dynamic_marker_seen = True
            dynamic_chars += chars
        elif dynamic_marker_seen:
            dynamic_chars += chars
        else:
            static_chars += chars
    try:
        tools_chars = sum(len(json.dumps(t, ensure_ascii=False, default=str)) for t in tools if isinstance(t, dict))
    except Exception:
        tools_chars = 0
    parsed = urlparse(str(upstream_url or "").strip())
    return {
        "upstream_host": parsed.hostname or "",
        "upstream_path": parsed.path or "",
        "model": str((body or {}).get("model") or ""),
        "messages_count": len(messages) if isinstance(messages, list) else 0,
        "tools_count": len(tools) if isinstance(tools, list) else 0,
        "static_prefix_chars": static_chars,
        "static_prefix_est_tokens": estimate_tokens("x" * static_chars),
        "dynamic_system_chars": dynamic_chars,
        "dynamic_system_est_tokens": estimate_tokens("x" * dynamic_chars),
        "leading_system_chars": leading_system_chars,
        "leading_system_est_tokens": estimate_tokens("x" * leading_system_chars),
        "message_chars": total_message_chars,
        "message_est_tokens": estimate_tokens("x" * total_message_chars),
        "tools_chars": tools_chars,
        "tools_est_tokens": estimate_tokens("x" * tools_chars),
        "dynamic_marker_seen": dynamic_marker_seen,
        "prompt_cache_key": str((body or {}).get("prompt_cache_key") or ""),
        "prompt_cache_retention": str((body or {}).get("prompt_cache_retention") or ""),
    }


def _extract_prompt_cache_usage(data: dict) -> dict:
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return {"usage_returned": False}
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached_tokens = prompt_details.get("cached_tokens")
    if cached_tokens is None:
        cached_tokens = input_details.get("cached_tokens")
    return {
        "usage_returned": True,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cached_tokens": cached_tokens,
        "prompt_cached_tokens": prompt_details.get("cached_tokens"),
        "input_cached_tokens": input_details.get("cached_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
    }


def _build_cache_debug_entry(body_send: dict, upstream_url: str, prompt_cache_profile: Optional[dict], data: dict) -> dict:
    profile = dict(prompt_cache_profile or _build_prompt_cache_profile(body_send, upstream_url))
    parsed = urlparse(str(upstream_url or "").strip())
    profile["upstream_host"] = parsed.hostname or profile.get("upstream_host") or ""
    profile["upstream_path"] = parsed.path or profile.get("upstream_path") or ""
    profile["model"] = str((body_send or {}).get("model") or profile.get("model") or "")
    profile["prompt_cache_key"] = str((body_send or {}).get("prompt_cache_key") or profile.get("prompt_cache_key") or "")
    profile["prompt_cache_retention"] = str((body_send or {}).get("prompt_cache_retention") or profile.get("prompt_cache_retention") or "")
    return {
        "request": profile,
        "usage": _extract_prompt_cache_usage(data),
    }


def _extract_thinking_from_content(content: str) -> tuple[str, str]:
    """
    把 content 里的 <think>...</think> / <thinking>...</thinking> 块提取出来。
    返回 (stripped_content, extracted_thinking)。
    若无匹配则 extracted_thinking 为空串，content 原样返回。
    """
    if not content or not isinstance(content, str):
        return content or "", ""
    thinking_parts: list[str] = []

    def _repl(m: re.Match) -> str:
        thinking_parts.append(m.group(2).strip())
        return ""

    stripped = _THINK_BLOCK_RE.sub(_repl, content).strip()
    return stripped, "\n\n".join(thinking_parts)


def _looks_like_tool_midstream_text(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    visible, thinking = _extract_thinking_from_content(raw)
    merged = "\n".join(x for x in (visible.strip(), thinking.strip()) if x).strip() or raw
    merged = " ".join(merged.split()).strip()
    if not merged or len(merged) > 400:
        return False
    if _TOOL_MIDSTREAM_TEXT_RE.search(merged):
        return True
    lower = merged.lower()
    if merged.endswith(("...", "…", "-")) and any(k in lower for k in ("check", "look", "guide", "看看", "查", "说明")):
        return True
    return False


def _should_retry_tool_followup(content_text: str, reasoning_text: str = "") -> bool:
    if _looks_like_tool_midstream_text(content_text):
        return True
    if not str(content_text or "").strip() and _looks_like_tool_midstream_text(reasoning_text):
        return True
    return False


def _normalize_visible_reply_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    visible, _thinking = _extract_thinking_from_content(raw)
    return visible.strip()


def _should_retry_tool_empty_final(content_text: str) -> bool:
    return not _normalize_visible_reply_text(content_text)


def _inject_tool_retry_instruction(body: dict, instruction: str) -> dict:
    body = copy.deepcopy(body)
    messages = list(body.get("messages") or [])
    insert_idx = 0
    while insert_idx < len(messages) and str((messages[insert_idx] or {}).get("role") or "").strip().lower() == "system":
        if str((messages[insert_idx] or {}).get("content") or "").strip() == instruction:
            body["messages"] = messages
            return body
        insert_idx += 1
    messages.insert(insert_idx, {"role": "system", "content": instruction})
    body["messages"] = messages
    return body


def _inject_tool_midstream_retry_instruction(body: dict) -> dict:
    return _inject_tool_retry_instruction(body, _TOOL_MIDSTREAM_RETRY_INSTRUCTION)


def _inject_tool_empty_final_retry_instruction(body: dict) -> dict:
    return _inject_tool_retry_instruction(body, _TOOL_EMPTY_FINAL_RETRY_INSTRUCTION)


def _normalize_reasoning_details(value) -> list:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _extract_reasoning_text_and_details(obj: dict) -> tuple[str, list, bool]:
    reasoning_parts: list[str] = []
    details = _normalize_reasoning_details(obj.get("reasoning_details")) if isinstance(obj, dict) else []
    omitted = False
    if isinstance(obj, dict):
        for rk in ("reasoning", "reasoning_content", "thinking"):
            val = obj.get(rk)
            if isinstance(val, str) and val.strip():
                reasoning_parts.append(val.strip())
        for item in details:
            for key in ("type", "display", "format"):
                val = str(item.get(key) or "").strip().lower()
                if val == "omitted":
                    omitted = True
            if item.get("omitted") is True:
                omitted = True
    return "\n\n".join([x for x in reasoning_parts if x]).strip(), details, omitted


def _apply_reasoning_metadata(msg: dict) -> dict:
    if not isinstance(msg, dict):
        return msg
    text, details, omitted = _extract_reasoning_text_and_details(msg)
    if text:
        existing = str(msg.get("reasoning") or "").strip()
        msg["reasoning"] = (existing + "\n\n" + text).strip() if existing and text not in existing else (existing or text)
    if details:
        msg["reasoning_details"] = details
    if omitted:
        msg["reasoning_omitted"] = True
    return msg


def _strip_thinking_from_response_json(resp_json: dict) -> dict:
    """
    从非流式上游响应中剥离 content 里的 <think> 块，
    同时把提取到的 thinking 合并进 message.reasoning（已有则追加），
    避免 thinking 泄漏给客户端（RikkaHub / Telegram 等）。
    就地修改 resp_json 并返回；若无 choices 则原样返回。
    """
    if not isinstance(resp_json, dict):
        return resp_json
    choices = resp_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return resp_json
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return resp_json
    content = msg.get("content")
    if not isinstance(content, str):
        return resp_json
    stripped, thinking = _extract_thinking_from_content(content)
    msg["content"] = stripped
    if thinking:
        existing = str(msg.get("reasoning") or "").strip()
        msg["reasoning"] = (existing + "\n\n" + thinking).strip() if existing else thinking
    return resp_json


def _strip_reasoning_from_sse_chunk(chunk: bytes) -> bytes:
    """
    从单条 SSE chunk 中：
    1. 删除 delta 里的 reasoning/reasoning_content/thinking 字段
    2. 剥离 delta.content 里的 <think>/<thinking> 块
    避免客户端（RikkaHub 等）把思维链渲染成对话内容。
    非 data: 行或解析失败时原样返回。
    """
    if not chunk.startswith(b"data: "):
        return chunk
    payload = chunk[6:].strip()
    if payload == b"[DONE]" or not payload:
        return chunk
    try:
        j = json.loads(payload.decode("utf-8", errors="ignore"))
        delta = (j.get("choices") or [{}])[0].get("delta") if isinstance(j, dict) else None
        if not isinstance(delta, dict):
            return chunk
        changed = False
        for rk in ("reasoning", "reasoning_content", "thinking", "reasoning_details"):
            if rk in delta:
                del delta[rk]
                changed = True
        # 剥离 delta.content 里的 <think> 块
        if isinstance(delta.get("content"), str) and _THINK_BLOCK_RE.search(delta["content"]):
            stripped, _ = _extract_thinking_from_content(delta["content"])
            delta["content"] = stripped
            changed = True
        if not changed:
            return chunk
        return b"data: " + json.dumps(j, ensure_ascii=False).encode("utf-8") + b"\n"
    except Exception:
        return chunk


def _parse_stream_to_message(chunks: list) -> dict:
    """
    从流式 SSE chunks 解析出完整 assistant message（content + tool_calls）。
    返回 {"content": str, "tool_calls": list or None, "reasoning": str|None, ...}。
    """
    content_parts = []
    reasoning_parts = []
    reasoning_details: list[dict] = []
    reasoning_omitted = False
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
        text, details, omitted = _extract_reasoning_text_and_details(delta)
        if text:
            reasoning_parts.append(text)
        if details:
            reasoning_details.extend(details)
        if omitted:
            reasoning_omitted = True
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
        "reasoning_details": reasoning_details or None,
        "reasoning_omitted": reasoning_omitted,
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
    accept = str((headers or {}).get("Accept") or "").strip()
    if accept:
        req_headers["Accept"] = accept
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
            body_send = _apply_active_model_request_policy(body_send, url)
            body_send = _apply_openrouter_request_policy(body_send, url)
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


def _stream_with_r2_archive(
    body: dict,
    headers: dict,
    window_id: str = "",
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
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
    max_tool_rounds = TOOL_MAX_ROUNDS
    max_processed_tool_rounds = max(0, int(max_tool_rounds))
    tool_rounds_used = 0
    tool_empty_final_retry_used = False
    tool_midstream_retry_used = False
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
                    yield _sse_delta_chunk_bytes(cap_hint)
                    content_parts.append(cap_hint)
                    break
                from services.notion_tools import execute_tool
                msg = {"content": parsed.get("content") or None, "tool_calls": tool_calls}
                if parsed.get("reasoning"):
                    msg["reasoning"] = parsed.get("reasoning")
                    reasoning_parts.append(parsed.get("reasoning") or "")
                if parsed.get("reasoning_details"):
                    msg["reasoning_details"] = parsed.get("reasoning_details")
                    reasoning_details_parts.extend(parsed.get("reasoning_details") or [])
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
            parsed_content = dedupe_sumitalk_cards_in_text(raw_parsed_content)
            if parsed_content != raw_parsed_content:
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
            suf = missing_html_preview_url_suffix(
                parsed_content, current_body.get("messages") or []
            )
            if suf:
                extra_vis = du_state.feed_delta(suf)
                if extra_vis:
                    yield _sse_delta_chunk_bytes(extra_vis)
                    content_parts.append(extra_vis)
            if _reply_channel() == "sumitalk":
                merged = merge_sumitalk_cards_into_assistant_text(parsed_content, current_body.get("messages") or [])
                if merged != parsed_content:
                    extra_card = merged[len(parsed_content):] if merged.startswith(parsed_content) else ("\n" + merged)
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
            body_send = _apply_openrouter_request_policy(body_send, url)
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
                cache_debug = _build_cache_debug_entry(body_send, url, prompt_cache_profile, data or {})
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
    return None, last_status, _build_upstream_error_hint(last_err or ""), None


def _last_user_message(messages):
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() == "user":
            return m
    return None


def _message_content_chars(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if not isinstance(part, dict):
                total += len(str(part or ""))
                continue
            if str(part.get("type") or "").strip().lower() == "text":
                total += len(str(part.get("text") or ""))
            elif part.get("image_url") is not None:
                total += 1
        return total
    return len(str(content or ""))


def _is_cross_platform_tg_window_user_input(window_id: str, body: dict) -> bool:
    wid = str(window_id or "").strip()
    if not wid.startswith("tg_"):
        return False
    if _is_followup_generation_request():
        return False
    reply_channel = _reply_channel()
    if reply_channel not in {"sumitalk", "wechat", "qq"}:
        return False
    last_user = _last_user_message((body or {}).get("messages") or [])
    if not isinstance(last_user, dict):
        return False
    content = last_user.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(
            isinstance(part, dict) and str(part.get("type") or "").strip().lower() in {"text", "image_url", "input_audio"}
            for part in content
        )
    return bool(str(content or "").strip())


def _maybe_mark_tg_window_user_activity(window_id: str, body: dict) -> None:
    if not _is_cross_platform_tg_window_user_input(window_id, body):
        return
    try:
        r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
        logger.info(
            "按 tg 窗口更新最近用户回复时间 window_id=%s reply_channel=%s",
            window_id,
            str(request.headers.get("X-Reply-Channel") or "").strip().lower(),
        )
    except Exception as e:
        logger.warning("按 tg 窗口更新最近用户回复时间失败 window_id=%s error=%s", window_id, e)


def _maybe_record_last_reply_channel(window_id: str, body: dict) -> None:
    if _is_followup_generation_request() or _is_du_daily_maintenance_request():
        return
    reply_channel = _reply_channel()
    if reply_channel not in {"tg", "sumitalk", "wechat", "qq"}:
        return
    last_user = _last_user_message((body or {}).get("messages") or [])
    if not isinstance(last_user, dict) or _message_content_chars(last_user.get("content")) <= 0:
        return
    target = str(request.headers.get("X-Reply-Target") or "").strip()
    if not target and reply_channel == "tg":
        wid = str(window_id or "").strip()
        if wid.startswith("tg_"):
            target = wid[3:]
    try:
        r2_store.save_last_reply_channel(
            channel=reply_channel,
            window_id=window_id,
            target=target,
            at_iso=now_beijing_iso(),
        )
        logger.info("已更新最近对话入口 window_id=%s channel=%s target=%s", window_id, reply_channel, target)
    except Exception as e:
        logger.warning("更新最近对话入口失败 window_id=%s channel=%s error=%s", window_id, reply_channel, e)


def _archive_nonstream_in_background(
    *,
    window_id: str,
    messages: list,
    msg: dict,
    round_cleaned_for_r2=None,
    reply_channel: str = "",
) -> None:
    """非流式入口先回包，R2 存档/动态层后台补做，避免 QQ/微信等待过久误判失败。"""

    def _runner():
        try:
            step_archive_and_maybe_summary(
                window_id,
                messages,
                msg,
                round_cleaned_for_r2=round_cleaned_for_r2,
            )
            logger.info("非流式后台存档完成 window_id=%s channel=%s", window_id, reply_channel)
        except Exception:
            logger.warning("非流式后台存档失败 window_id=%s channel=%s", window_id, reply_channel, exc_info=True)

    threading.Thread(target=_runner, name=f"nonstream-archive-{window_id}", daemon=True).start()


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


def _is_du_daily_maintenance_request() -> bool:
    return str(request.headers.get("X-DU-DAILY-MAINTAIN") or "").strip().lower() in ("1", "true", "yes")


def _strip_co_read_section_raw_text_for_archive(msg: dict) -> dict:
    import copy as _copy

    def _strip_text(text: str) -> str:
        raw = str(text or "")
        start_marker = "[CO-READ SECTION]"
        end_marker = "[/CO-READ SECTION]"
        raw_marker = "本小节原文："
        next_marker = "辛玥的粉色标记："
        if start_marker not in raw or raw_marker not in raw:
            return raw
        out = []
        pos = 0
        while True:
            start = raw.find(start_marker, pos)
            if start < 0:
                out.append(raw[pos:])
                break
            end = raw.find(end_marker, start)
            if end < 0:
                out.append(raw[pos:])
                break
            block_end = end + len(end_marker)
            block = raw[start:block_end]
            raw_idx = block.find(raw_marker)
            next_idx = block.find(next_marker, raw_idx + len(raw_marker)) if raw_idx >= 0 else -1
            if raw_idx >= 0 and next_idx >= 0:
                block = (
                    block[:raw_idx]
                    + "本小节原文：\n（已从会话存档删除；原书正文仅保留在 co_read/books）\n\n"
                    + block[next_idx:]
                )
            out.append(raw[pos:start])
            out.append(block)
            pos = block_end
        return "".join(out)

    clean = _copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean


def _extract_and_store_hidden_sidecars(
    full_text: str,
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
) -> str:
    visible_after_pcmd, _ = process_pcmd_in_assistant_text(full_text or "")
    visible, thought = split_assistant_for_thought(visible_after_pcmd)
    visible, interaction = split_assistant_for_interaction(visible)
    visible, du_daily = split_assistant_for_daily(visible)
    visible, referenced_memory_ids = strip_assistant_memory_citations(visible, dynamic_memory_citation_map)
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
    if du_daily:
        try:
            save_du_daily_hidden_block(du_daily, trigger=du_daily_trigger)
        except Exception as e:
            logger.warning("save_du_daily_hidden_block 失败 error=%s", e)
    elif looks_like_plain_maintenance_daily(visible, du_daily_trigger):
        try:
            save_du_daily_hidden_block(visible, trigger=du_daily_trigger)
            visible = ""
        except Exception as e:
            logger.warning("save_du_daily_hidden_block plain 失败 error=%s", e)
    if referenced_memory_ids:
        try:
            touched = r2_store.touch_dynamic_memory_mentions(referenced_memory_ids)
            logger.info("动态记忆引用命中 ids=%s touched=%s", referenced_memory_ids[:10], touched)
        except Exception as e:
            logger.warning("动态记忆引用回写失败 ids=%s error=%s", referenced_memory_ids[:10], e)
    return visible


def _apply_hidden_sidecars_to_assistant_response(
    resp_json: dict,
    du_daily_trigger: Optional[dict] = None,
    dynamic_memory_citation_map: Optional[dict] = None,
) -> dict:
    """
    剥离助手回复中的隐藏块（老婆侧不可见）；若存在闭合块则写入 R2。
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
    visible = _extract_and_store_hidden_sidecars(
        content_text,
        du_daily_trigger=du_daily_trigger,
        dynamic_memory_citation_map=dynamic_memory_citation_map,
    )
    if visible != content_text:
        msg["content"] = visible
    return resp_json


def _append_tool_results_and_continue(body: dict, assistant_message: dict, tool_calls: list, execute_tool) -> dict:
    """执行 tool_calls，将 assistant 消息与各 tool 结果追加到 body["messages"]，返回新 body 供继续请求。"""
    import copy as _copy
    body = _copy.deepcopy(body)
    messages = body.get("messages") or []
    # 保留 assistant 消息（含 tool_calls）
    assistant_trace = {
        "role": "assistant",
        "content": assistant_message.get("content") or None,
        "tool_calls": assistant_message.get("tool_calls"),
    }
    for rk in ("reasoning", "reasoning_content", "thinking", "reasoning_details", "reasoning_omitted"):
        if assistant_message.get(rk):
            assistant_trace[rk] = assistant_message.get(rk)
    messages.append(assistant_trace)
    for tc in tool_calls:
        tid = (tc or {}).get("id") or ""
        fn = (tc or {}).get("function") or {}
        name = fn.get("name") or ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        try:
            result = execute_tool(name, args)
        except Exception as _tool_exc:
            logger.warning("execute_tool 异常 name=%s error=%s", name, _tool_exc)
            result = json.dumps({"ok": False, "error": f"工具执行异常: {_tool_exc}"}, ensure_ascii=False)
        messages.append({"role": "tool", "tool_call_id": tid, "content": result})
    body["messages"] = messages
    return body


def _collect_tool_trace_from_messages(messages: list) -> list[dict]:
    """
    从消息链提取工具调用与结果，供存档后 MiniApp 展示。
    返回项结构：{id,type,function:{name,arguments},result}
    """
    def _tool_content_to_str(msg: dict) -> str:
        c = msg.get("content")
        if isinstance(c, str):
            return c
        try:
            return json.dumps(c, ensure_ascii=False)
        except Exception:
            return str(c)

    def _following_tool_message_indices(start_idx: int) -> list[int]:
        indices: list[int] = []
        for j in range(start_idx + 1, len(messages or [])):
            mm = messages[j]
            if not isinstance(mm, dict):
                continue
            role = str(mm.get("role") or "").strip().lower()
            if role == "tool":
                indices.append(j)
                continue
            if role in {"assistant", "user"}:
                break
        return indices

    out: list[dict] = []
    used_tool_indices: set[int] = set()
    for i, m in enumerate(messages or []):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        following_tool_indices = _following_tool_message_indices(i)
        for pos, tc in enumerate(tcs):
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            row = dict(tc)
            result_idx = None
            if tid:
                for idx in following_tool_indices:
                    if idx in used_tool_indices:
                        continue
                    tm = messages[idx]
                    if str(tm.get("tool_call_id") or "").strip() == tid:
                        result_idx = idx
                        break
            if result_idx is None:
                remaining = [idx for idx in following_tool_indices if idx not in used_tool_indices]
                if pos < len(remaining):
                    result_idx = remaining[pos]
                elif remaining:
                    result_idx = remaining[0]
            if result_idx is not None:
                used_tool_indices.add(result_idx)
                row["result"] = _tool_content_to_str(messages[result_idx])
            else:
                row["result"] = ""
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


def _is_sse_done_chunk(chunk: bytes) -> bool:
    if not isinstance(chunk, (bytes, bytearray)) or not bytes(chunk).startswith(b"data: "):
        return False
    return bytes(chunk)[6:].strip() == b"[DONE]"


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


def _merge_sumitalk_card_into_nonstream_response(resp_json: dict, messages: list) -> dict:
    """非流式 Sumitalk：若调用了 app 原生动作工具，补入可渲染的卡片 marker。"""
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
    merged = merge_sumitalk_cards_into_assistant_text(ct, messages)
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
    reply_target = str(request.headers.get("X-Reply-Target") or "").strip()
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
        _maybe_mark_tg_window_user_activity(window_id, body)
        _maybe_record_last_reply_channel(window_id, body)

    # 走完整管道（清洗、注入记忆/总结、转发、存档）
    body = step_clean_images_and_save_desc(body, window_id)
    body = step_clean_for_forward(body)
    body = step_replace_rikka_system(body)
    body = step_inject_thinking_block_rules(body)
    body = step_inject_core_behavior_rules(body)
    body = _inject_miniapp_style_system(body)
    body = _inject_channel_nsfw_system(body)
    body = _inject_followup_instruction(body)
    force_last4 = (request.headers.get("X-Force-Last4") or "").strip().lower() in ("1", "true", "yes")
    tg_user_input = (request.headers.get("X-TG-User-Input") or "").strip().lower() in ("1", "true", "yes")
    slim_voice_call = (request.headers.get("X-Voice-Call-Slim") or "").strip().lower() in ("1", "true", "yes")
    skip_dynamic_memory = (request.headers.get("X-Skip-Dynamic-Memory") or "").strip().lower() in ("1", "true", "yes")
    du_daily_maintenance = _is_du_daily_maintenance_request()
    du_daily_trigger = build_du_daily_trigger(window_id, body, headers)
    if not slim_voice_call:
        body = step_inject_du_thought(body, window_id)
        body = step_inject_du_daily(body, window_id, trigger=du_daily_trigger, maintenance_mode=du_daily_maintenance)
        if not skip_dynamic_memory:
            body = step_inject_dynamic_memory(body, window_id)
        body = step_inject_summary(body, window_id, is_user_input=tg_user_input)
        body = step_inject_sense_snapshot(body, window_id)
        body = step_inject_latest_4_rounds_for_new_window(body, window_id, force_last4=force_last4)
        body = step_inject_interaction_candidate(body, window_id)
        body = step_inject_wenyou_gm(body, window_id)
        if not du_daily_maintenance:
            body = step_inject_rikkahub_reminder(body, window_id)
        body = step_inject_stay_with_du(body)
        body = step_inject_du_notebook(body)
        if not du_daily_maintenance:
            body = step_inject_notion_search(body, window_id)
            body = step_inject_notion_tools(body)
            body = step_inject_forum_tools(body)
            body = step_inject_amap_mcp_tools(body)
            body = step_inject_websearch_tools(body)
            body = step_inject_html_preview_tool(body, request.headers.get("User-Agent") or "")
    body = step_trim_messages_if_over_limit(body)
    dynamic_memory_citation_map = normalize_citation_map(body.pop(DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY, None))
    # 注入快照：每次请求后把完整 body 存一份，方便对比 token 变化
    try:
        _snap = {
            "messages": body.get("messages") or [],
            "tools": body.get("tools") or [],
            "tool_choice": body.get("tool_choice"),
        }
        _snap_chars = sum(len(str(m.get("content") or "")) for m in _snap["messages"])
        _snap_tool_chars = sum(len(json.dumps(t, ensure_ascii=False)) for t in _snap["tools"])
        _snap["_meta"] = {
            "messages_chars": _snap_chars,
            "tools_chars": _snap_tool_chars,
            "tools_count": len(_snap["tools"]),
            "tool_names": [((t.get("function") or {}).get("name") or "") for t in _snap["tools"] if isinstance(t, dict)],
        }
        (DATA_DIR / "last_inject_snapshot.json").write_text(
            json.dumps(_snap, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    active_upstream_url = _get_active_upstream_url()
    prompt_cache_profile = _build_prompt_cache_profile(body, active_upstream_url)
    # 本机 Claude OAuth 代理需要这个标记把缓存断点打在静态 system 末尾；其他上游继续清掉。
    preserve_dynamic_marker = _is_local_claude_oauth_proxy_url(active_upstream_url)
    for msg in body.get("messages") or []:
        if not preserve_dynamic_marker:
            msg.pop("__dynamic__", None)
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
                if reply_target == "co_read_section":
                    last_user = _strip_co_read_section_raw_text_for_archive(last_user)
                round_cleaned = build_round_cleaned_for_r2(last_user, msg_for_r2)
                if reply_channel in {"qq", "wechat"}:
                    _archive_nonstream_in_background(
                        window_id=window_id,
                        messages=archive_messages,
                        msg=msg_for_r2,
                        round_cleaned_for_r2=round_cleaned,
                        reply_channel=reply_channel,
                    )
                else:
                    step_archive_and_maybe_summary(
                        window_id, archive_messages, msg_for_r2, round_cleaned_for_r2=round_cleaned
                    )
            else:
                if reply_channel in {"qq", "wechat"}:
                    _archive_nonstream_in_background(
                        window_id=window_id,
                        messages=archive_messages,
                        msg=msg_for_r2,
                        reply_channel=reply_channel,
                    )
                else:
                    step_archive_and_maybe_summary(window_id, archive_messages, msg_for_r2)
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
