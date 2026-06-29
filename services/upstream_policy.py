import re
from urllib.parse import urlparse

from config import (
    TARGET_AI_URL,
    TARGET_AI_API_KEY,
    TARGET_AI_URLS,
    TARGET_AI_API_KEYS,
    OPENROUTER_REASONING_MAX_TOKENS,
    OPENROUTER_VERBOSITY,
    OPENROUTER_ULTRA_THINK_ENABLED,
    OPENROUTER_ULTRA_THINK_PROMPT,
    OPENROUTER_CACHE_CONTROL_TYPE,
    PIONEER_CLAUDE_CACHE_TTL,
    is_openrouter_url,
    is_pioneer_url,
    is_cloudflare_anthropic_url,
)
from services.cloudflare_anthropic import normalize_model_for_cloudflare

_CLAUDE_ADAPTIVE_THINKING_RE = re.compile(r"claude-opus-4-(?:6|7|8)(?:\b|-|$)", re.IGNORECASE)
_CLAUDE_OPUS_46_RE = re.compile(r"claude-opus-4-6(?:\b|-|$)", re.IGNORECASE)
_DYNAMIC_SYSTEM_MARKER = "__dynamic__"
_SUMMARY_CACHE_SYSTEM_MARKER = "__summary_cache__"
_SUMMARY_RECENT_SYSTEM_MARKER = "__summary_recent__"


def get_forward_targets(request_model: str = None):
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


def active_upstream_label() -> str:
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


def build_upstream_error_hint(last_err: str) -> str:
    """把上游错误改造成“像 rikkahub 一样清楚”的可读提示。"""
    active_label = active_upstream_label()
    detail = (last_err or "").strip() or "未知错误"
    return (
        "【上游不可用】请先在 MiniApp -> 上游中转站切换后重试。\n"
        f"当前 active：{active_label}\n"
        f"错误详情：{detail}"
    )


def extract_upstream_error_detail(data, status_code: int | None = None) -> str:
    """从 OpenAI/Anthropic 兼容错误响应里提取可读详情。"""
    fallback = f"HTTP {status_code}" if status_code else ""
    if not isinstance(data, dict):
        return fallback
    err = data.get("error")
    parts: list[str] = []
    if isinstance(err, dict):
        for key in ("type", "code", "message"):
            val = err.get(key)
            if val is None:
                continue
            text = str(val).strip()
            if text and text not in parts:
                parts.append(text)
    elif err is not None:
        text = str(err).strip()
        if text:
            parts.append(text)
    for key in ("message", "detail"):
        val = data.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text and text not in parts:
            parts.append(text)
    return " · ".join(parts).strip() or fallback


def get_active_upstream_url() -> str:
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


def is_local_cliproxyapi_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in ("127.0.0.1", "localhost") and parsed.port == 8317


def is_local_claude_oauth_proxy_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in ("127.0.0.1", "localhost") and parsed.port == 8082


def _is_claude_adaptive_thinking_model(model: str) -> bool:
    return bool(_CLAUDE_ADAPTIVE_THINKING_RE.search(str(model or "").strip()))


def _is_claude_proxy_model(model: str) -> bool:
    return str(model or "").strip().lower().startswith("claude-")


def _message_content_text(msg: dict) -> str:
    content = (msg or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and str(item.get("type") or "").strip().lower() in {"text", "input_text"}:
                parts.append(str(item.get("text") or ""))
        return "\n".join(x for x in parts if x)
    return str(content or "")


def _looks_like_summary_cache_message(msg: dict) -> bool:
    text = _message_content_text(msg).strip()
    return bool((msg or {}).get(_SUMMARY_CACHE_SYSTEM_MARKER) or text.startswith("【近期记忆】"))


def _looks_like_recent_summary_message(msg: dict) -> bool:
    text = _message_content_text(msg).strip()
    return bool((msg or {}).get(_SUMMARY_RECENT_SYSTEM_MARKER) or text.startswith("【近期记忆（最近）】"))


def _looks_like_dynamic_message(msg: dict) -> bool:
    return bool((msg or {}).get(_DYNAMIC_SYSTEM_MARKER) or _looks_like_recent_summary_message(msg))


def _cache_control(ttl: str) -> dict:
    out = {"type": "ephemeral"}
    if ttl:
        out["ttl"] = ttl
    return out


def _split_summary_text(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    text = re.sub(r"【以上为近期记忆】\s*$", "", text).strip()
    recent_idx = text.find("【最近】")
    if recent_idx < 0:
        return str(value or ""), ""
    stable_raw = text[:recent_idx].strip()
    recent_raw = text[recent_idx:].strip()
    if not recent_raw:
        return str(value or ""), ""
    stable_text = f"{stable_raw}\n【以上为较稳定的近期记忆】" if stable_raw else ""
    recent_text = f"\n\n【近期记忆（最近）】\n{recent_raw}\n【以上为最近记忆】"
    return stable_text, recent_text


def _text_blocks_from_content(content) -> list:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, str):
                out.append({"type": "text", "text": item})
            elif isinstance(item, dict):
                out.append(dict(item))
        return out
    return [{"type": "text", "text": str(content or "")}]


def _set_cache_control_on_message(msg: dict, ttl: str) -> None:
    blocks = _text_blocks_from_content((msg or {}).get("content"))
    for block in reversed(blocks):
        if isinstance(block, dict) and str(block.get("type") or "").strip().lower() in {"text", "input_text"}:
            block["cache_control"] = _cache_control(ttl)
            break
    msg["content"] = blocks


def _set_summary_cache_control_on_message(msg: dict, ttl: str) -> None:
    content = (msg or {}).get("content")
    if isinstance(content, str):
        stable_text, recent_text = _split_summary_text(content)
        if recent_text:
            blocks = []
            if stable_text:
                blocks.append({"type": "text", "text": stable_text, "cache_control": _cache_control(ttl)})
            blocks.append({"type": "text", "text": recent_text, "cache_control": _cache_control(ttl)})
            msg["content"] = blocks
            return
    _set_cache_control_on_message(msg, ttl)


def _strip_gateway_cache_markers(messages: list[dict]) -> None:
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        msg.pop(_DYNAMIC_SYSTEM_MARKER, None)
        msg.pop(_SUMMARY_CACHE_SYSTEM_MARKER, None)
        msg.pop(_SUMMARY_RECENT_SYSTEM_MARKER, None)


def _apply_pioneer_claude_prompt_cache(body: dict, ttl: str) -> dict:
    messages = [dict(m) for m in ((body or {}).get("messages") or []) if isinstance(m, dict)]
    if not messages:
        return body
    leading_system_indexes: list[int] = []
    for idx, msg in enumerate(messages):
        if str(msg.get("role") or "").strip().lower() != "system":
            break
        leading_system_indexes.append(idx)
    if not leading_system_indexes:
        body["messages"] = messages
        return body

    summary_idx = -1
    for idx in leading_system_indexes[1:]:
        if _looks_like_summary_cache_message(messages[idx]):
            summary_idx = idx
            break

    if summary_idx > 0:
        cacheable_idx = -1
        for idx in reversed([x for x in leading_system_indexes if x < summary_idx]):
            msg = messages[idx]
            if not _looks_like_dynamic_message(msg):
                cacheable_idx = idx
                break
        if cacheable_idx >= 0:
            _set_cache_control_on_message(messages[cacheable_idx], ttl)
        _set_summary_cache_control_on_message(messages[summary_idx], ttl)
        recent_idx = -1
        for idx in [x for x in leading_system_indexes if x > summary_idx]:
            if _looks_like_recent_summary_message(messages[idx]):
                recent_idx = idx
                break
        if recent_idx > summary_idx:
            _set_cache_control_on_message(messages[recent_idx], ttl)
    else:
        cacheable_idx = -1
        for idx in leading_system_indexes:
            msg = messages[idx]
            if _looks_like_dynamic_message(msg):
                break
            cacheable_idx = idx
        if cacheable_idx >= 0:
            _set_cache_control_on_message(messages[cacheable_idx], ttl)

    _strip_gateway_cache_markers(messages)
    body["messages"] = messages
    return body


def _normalize_claude_adaptive_effort(model: str, effort: str) -> str:
    value = str(effort or "").strip().lower() or "high"
    if value == "xhigh" and _CLAUDE_OPUS_46_RE.search(str(model or "").strip()):
        return "high"
    return value


def apply_active_model_request_policy(body: dict, upstream_url: str) -> dict:
    body = dict(body or {})
    try:
        from storage.upstream_store import get_active_claude_thinking_effort, get_active_item, get_cached_active_model

        active = get_active_item() or {}
        active_url = str(active.get("url") or "").strip()
        if active_url and active_url == str(upstream_url or "").strip():
            model = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
            if model:
                body["model"] = model
            if is_local_cliproxyapi_url(upstream_url):
                body.pop("reasoning", None)
                body["reasoning_effort"] = "high"
            if is_local_claude_oauth_proxy_url(upstream_url) and _is_claude_adaptive_thinking_model(model):
                body["thinking"] = {"type": "adaptive", "display": "summarized"}
                output_config = body.get("output_config") if isinstance(body.get("output_config"), dict) else {}
                output_config = dict(output_config)
                output_config["effort"] = _normalize_claude_adaptive_effort(model, get_active_claude_thinking_effort())
                body["output_config"] = output_config
            if is_pioneer_url(upstream_url):
                effective_model = model
                if _is_claude_proxy_model(effective_model):
                    body["model"] = effective_model
                    body = _apply_pioneer_claude_prompt_cache(body, PIONEER_CLAUDE_CACHE_TTL)
                else:
                    _strip_gateway_cache_markers(body.get("messages") or [])
                if _is_claude_adaptive_thinking_model(effective_model):
                    body["thinking"] = {"type": "adaptive", "display": "summarized"}
                    output_config = body.get("output_config") if isinstance(body.get("output_config"), dict) else {}
                    output_config = dict(output_config)
                    output_config["effort"] = _normalize_claude_adaptive_effort(effective_model, get_active_claude_thinking_effort())
                    body["output_config"] = output_config
            if is_cloudflare_anthropic_url(upstream_url):
                effective_model = model
                if effective_model:
                    body["model"] = normalize_model_for_cloudflare(effective_model, upstream_url)
                if _is_claude_adaptive_thinking_model(effective_model):
                    body["thinking"] = {"type": "adaptive", "display": "summarized"}
                    output_config = body.get("output_config") if isinstance(body.get("output_config"), dict) else {}
                    output_config = dict(output_config)
                    output_config["effort"] = _normalize_claude_adaptive_effort(effective_model, get_active_claude_thinking_effort())
                    body["output_config"] = output_config
    except Exception:
        pass
    return body


def apply_openrouter_request_policy(body: dict, upstream_url: str) -> dict:
    body = dict(body or {})
    if not is_openrouter_url(upstream_url):
        return body
    reasoning = body.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}
    reasoning["enabled"] = True
    if OPENROUTER_REASONING_MAX_TOKENS > 0:
        reasoning["max_tokens"] = OPENROUTER_REASONING_MAX_TOKENS
    body["reasoning"] = reasoning
    if OPENROUTER_VERBOSITY:
        body["verbosity"] = OPENROUTER_VERBOSITY
    if OPENROUTER_CACHE_CONTROL_TYPE:
        body["cache_control"] = {"type": OPENROUTER_CACHE_CONTROL_TYPE}
    if OPENROUTER_ULTRA_THINK_ENABLED and OPENROUTER_ULTRA_THINK_PROMPT:
        body["messages"] = inject_openrouter_ultra_think_prompt(body.get("messages") or [])
    return body


def inject_openrouter_ultra_think_prompt(messages: list) -> list:
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


def chat_url_to_models_url(chat_url: str) -> str:
    """从 chat completions URL 推出 /v1/models 的 URL。"""
    base = str(chat_url or "").strip().rstrip("/")
    if not base:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/models"
