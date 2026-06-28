import json
import re
import time
from urllib.parse import urlparse, urlunparse

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
)

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


def should_route_pioneer_claude_via_anthropic(body: dict, upstream_url: str) -> bool:
    if not is_pioneer_url(upstream_url):
        return False
    return _is_claude_proxy_model((body or {}).get("model") or "")


def pioneer_anthropic_messages_url(upstream_url: str) -> str:
    parsed = urlparse(str(upstream_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return upstream_url
    path = parsed.path or ""
    if path.startswith("/v1/") or path == "/v1":
        path = "/v1/messages"
    else:
        path = "/v1/messages"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, parsed.fragment))


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


def _set_cache_control_on_last_tool(body: dict, ttl: str) -> None:
    tools = (body or {}).get("tools")
    if not isinstance(tools, list) or not tools:
        return
    copied_tools = [dict(tool) if isinstance(tool, dict) else tool for tool in tools]
    for idx in range(len(copied_tools) - 1, -1, -1):
        tool = copied_tools[idx]
        if isinstance(tool, dict):
            tool["cache_control"] = _cache_control(ttl)
            copied_tools[idx] = tool
            body["tools"] = copied_tools
            return


def _apply_pioneer_claude_prompt_cache(body: dict, ttl: str) -> dict:
    _set_cache_control_on_last_tool(body, ttl)
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


def _safe_json_loads(value, default=None):
    if default is None:
        default = {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def _content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                typ = str(item.get("type") or "").strip().lower()
                if typ in {"text", "input_text"}:
                    parts.append(str(item.get("text") or ""))
                elif typ == "tool_result":
                    parts.append(str(item.get("content") or ""))
        return "\n".join(part for part in parts if part)
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        return str(content)


def _openai_content_to_anthropic_blocks(content) -> list[dict]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content)}]
    out: list[dict] = []
    for part in content:
        if isinstance(part, str):
            if part:
                out.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            continue
        typ = str(part.get("type") or "").strip().lower()
        if typ in {"text", "input_text"}:
            block = {"type": "text", "text": str(part.get("text") or "")}
            if isinstance(part.get("cache_control"), dict):
                block["cache_control"] = dict(part.get("cache_control") or {})
            out.append(block)
        elif typ in {"thinking", "redacted_thinking", "tool_use", "tool_result"}:
            out.append(dict(part))
        elif typ == "image":
            out.append(dict(part))
        elif typ == "image_url":
            url = ""
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = str(image_url.get("url") or "")
            else:
                url = str(part.get("url") or "")
            match = re.match(r"^data:(image/[^;]+);base64,(.+)$", url)
            if match:
                out.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": match.group(1), "data": match.group(2)},
                    }
                )
            elif url:
                out.append({"type": "text", "text": f"[图片：{url}]"})
    return out


def _openai_tools_to_anthropic(tools) -> list[dict] | None:
    if not isinstance(tools, list):
        return None
    out: list[dict] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            fn = tool.get("function") or {}
            item = {
                "name": str(fn.get("name") or ""),
                "description": str(fn.get("description") or ""),
                "input_schema": fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {"type": "object", "properties": {}},
            }
            if isinstance(tool.get("cache_control"), dict):
                item["cache_control"] = dict(tool.get("cache_control") or {})
            if item["name"]:
                out.append(item)
        elif tool.get("name") and isinstance(tool.get("input_schema"), dict):
            out.append(dict(tool))
    return out or None


def _openai_tool_choice_to_anthropic(choice):
    if not choice or choice == "auto":
        return None
    if choice == "none":
        return {"type": "none"}
    if isinstance(choice, dict):
        fn = choice.get("function") if isinstance(choice.get("function"), dict) else {}
        name = str(fn.get("name") or choice.get("name") or "").strip()
        if name:
            return {"type": "tool", "name": name}
    return {"type": "auto"}


def _append_anthropic_message(messages: list[dict], role: str, content: list[dict]) -> None:
    blocks = [block for block in (content or []) if isinstance(block, dict)]
    if not blocks:
        blocks = [{"type": "text", "text": ""}]
    if messages and messages[-1].get("role") == role:
        prev = messages[-1].get("content")
        if isinstance(prev, list):
            prev.extend(blocks)
            return
    messages.append({"role": role, "content": blocks})


def pioneer_openai_to_anthropic_request(body: dict) -> dict:
    oai = dict(body or {})
    messages: list[dict] = []
    system_blocks: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            _append_anthropic_message(messages, "user", pending_tool_results)
            pending_tool_results = []

    for msg in oai.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        if role == "system":
            blocks = _openai_content_to_anthropic_blocks(msg.get("content"))
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    system_blocks.append(block)
            continue
        if role in {"tool", "function"}:
            tool_use_id = str(msg.get("tool_call_id") or msg.get("id") or msg.get("name") or "").strip()
            if tool_use_id:
                pending_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": _content_to_text(msg.get("content")),
                    }
                )
            continue
        if role == "user":
            flush_tool_results()
            _append_anthropic_message(messages, "user", _openai_content_to_anthropic_blocks(msg.get("content")))
            continue
        if role == "assistant":
            flush_tool_results()
            content = _openai_content_to_anthropic_blocks(msg.get("content"))
            if isinstance(msg.get("thinking_blocks"), list):
                content = [dict(x) for x in msg.get("thinking_blocks") if isinstance(x, dict)] + content
            for call in msg.get("tool_calls") or []:
                if not isinstance(call, dict) or call.get("type") != "function":
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                name = str(fn.get("name") or "").strip()
                if not name:
                    continue
                content.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or name),
                        "name": name,
                        "input": _safe_json_loads(fn.get("arguments"), {}),
                    }
                )
            if content:
                _append_anthropic_message(messages, "assistant", content)
    flush_tool_results()

    out = {
        "model": oai.get("model"),
        "max_tokens": oai.get("max_tokens") or oai.get("max_completion_tokens") or 8192,
        "messages": messages,
    }
    if system_blocks:
        out["system"] = system_blocks
    if isinstance(oai.get("thinking"), dict):
        out["thinking"] = dict(oai.get("thinking") or {})
    if isinstance(oai.get("output_config"), dict):
        out["output_config"] = dict(oai.get("output_config") or {})
    elif oai.get("reasoning_effort"):
        out["output_config"] = {"effort": oai.get("reasoning_effort")}
    for key in ("temperature", "top_p"):
        if oai.get(key) is not None:
            out[key] = oai.get(key)
    if oai.get("stream"):
        out["stream"] = True
    if oai.get("stop") is not None:
        stop = oai.get("stop")
        out["stop_sequences"] = stop if isinstance(stop, list) else [stop]
    tools = _openai_tools_to_anthropic(oai.get("tools"))
    if tools:
        out["tools"] = tools
    tool_choice = _openai_tool_choice_to_anthropic(oai.get("tool_choice"))
    if tool_choice:
        out["tool_choice"] = tool_choice
    if oai.get("parallel_tool_calls") is False:
        out["disable_parallel_tool_use"] = True
    return out


def _convert_anthropic_usage(usage) -> dict:
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    out = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "anthropic_created": cache_creation,
        "anthropic_read": cache_read,
        "prompt_tokens_details": {"cached_tokens": cache_read},
    }
    if isinstance(usage.get("output_tokens_details"), dict):
        out["output_tokens_details"] = usage.get("output_tokens_details")
    if isinstance(usage.get("iterations"), list):
        out["iterations"] = usage.get("iterations")
        out["anthropic_iterations"] = usage.get("iterations")
    return out


def pioneer_anthropic_to_openai_response(data: dict, request_model: str = "") -> dict:
    if not isinstance(data, dict):
        return data
    if isinstance(data.get("choices"), list):
        return data
    actual_model = str(data.get("model") or "").strip() or str(request_model or "").strip()
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    thinking_blocks: list[dict] = []
    fallback_blocks: list[dict] = []
    tool_calls: list[dict] = []
    for part in data.get("content") or []:
        if not isinstance(part, dict):
            continue
        typ = str(part.get("type") or "").strip()
        if typ == "text":
            text_parts.append(str(part.get("text") or ""))
        elif typ == "thinking":
            thinking_blocks.append(dict(part))
            text = str(part.get("thinking") or part.get("text") or "").strip()
            if text:
                reasoning_parts.append(text)
        elif typ == "redacted_thinking":
            thinking_blocks.append(dict(part))
        elif typ == "fallback":
            fallback_blocks.append(dict(part))
        elif typ == "tool_use":
            tool_calls.append(
                {
                    "id": str(part.get("id") or part.get("name") or ""),
                    "type": "function",
                    "function": {
                        "name": str(part.get("name") or ""),
                        "arguments": json.dumps(part.get("input") or {}, ensure_ascii=False),
                    },
                }
            )
    message = {
        "role": "assistant",
        "content": "".join(text_parts) if text_parts else (None if tool_calls else ""),
    }
    if reasoning_parts:
        message["reasoning_content"] = "\n\n".join(reasoning_parts)
    if thinking_blocks:
        message["thinking_blocks"] = thinking_blocks
    if fallback_blocks:
        message["anthropic_fallback_blocks"] = fallback_blocks
    if tool_calls:
        message["tool_calls"] = tool_calls
    stop_reason = str(data.get("stop_reason") or "").strip()
    if stop_reason == "tool_use":
        finish_reason = "tool_calls"
    elif stop_reason == "max_tokens":
        finish_reason = "length"
    else:
        finish_reason = "stop"
    resp = {
        "id": "chatcmpl-" + str(data.get("id") or int(time.time() * 1000)),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": actual_model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": _convert_anthropic_usage(data.get("usage") or data.get("token_usage")),
    }
    if request_model and actual_model and actual_model != request_model:
        resp["requested_model"] = request_model
    resp["anthropic_model"] = actual_model
    for key in ("pioneer_inference_id", "pioneer_routed_model", "pioneer_savings"):
        if data.get(key) is not None:
            resp[key] = data.get(key)
    if fallback_blocks:
        resp["anthropic_fallback_blocks"] = fallback_blocks
    return resp


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
                request_model = str(body.get("model") or "").strip()
                effective_model = model or request_model
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
