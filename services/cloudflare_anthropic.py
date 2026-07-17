import json
import time
from copy import deepcopy
from typing import Iterable

from config import (
    CLOUDFLARE_AIG_GATEWAY_ID,
    CLOUDFLARE_ANTHROPIC_API_KEY,
    CLOUDFLARE_ANTHROPIC_BETA,
    CLOUDFLARE_CLAUDE_CACHE_TTL,
    is_cloudflare_provider_native_anthropic_url,
    is_cloudflare_rest_anthropic_url,
)

DYNAMIC_SYSTEM_MARKER = "__dynamic__"
SUMMARY_CACHE_SYSTEM_MARKER = "__summary_cache__"
SUMMARY_RECENT_SYSTEM_MARKER = "__summary_recent__"
GATEWAY_DYNAMIC_SYSTEM_HINTS = (
    "【渡的心事",
    "【渡的日常",
    "今日：",
    "听了老婆的话，我想起来",
    "【指代提醒】",
    "老婆当前状态",
    "【当前是在 RikkaHub 和渡聊天】",
)


def normalize_model_for_cloudflare(model: str, url: str) -> str:
    value = str(model or "").strip()
    if not value:
        return value
    if is_cloudflare_rest_anthropic_url(url):
        return value if value.startswith("anthropic/") else f"anthropic/{value}"
    return value.replace("anthropic/", "", 1) if value.startswith("anthropic/") else value


def cloudflare_anthropic_headers(base_headers: dict, url: str, api_key: str) -> dict:
    headers = dict(base_headers or {})
    headers["Content-Type"] = "application/json"
    headers["anthropic-version"] = "2023-06-01"
    headers["cf-aig-skip-cache"] = "true"
    if CLOUDFLARE_ANTHROPIC_BETA:
        headers["anthropic-beta"] = CLOUDFLARE_ANTHROPIC_BETA

    key = str(api_key or "").strip()
    if is_cloudflare_provider_native_anthropic_url(url):
        headers.pop("Authorization", None)
        if key.startswith("sk-ant-"):
            headers["x-api-key"] = key
        elif key:
            headers["cf-aig-authorization"] = f"Bearer {key}"
        if CLOUDFLARE_ANTHROPIC_API_KEY:
            headers["x-api-key"] = CLOUDFLARE_ANTHROPIC_API_KEY
    elif is_cloudflare_rest_anthropic_url(url):
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if CLOUDFLARE_AIG_GATEWAY_ID:
            headers["cf-aig-gateway-id"] = CLOUDFLARE_AIG_GATEWAY_ID
    return headers


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
            elif isinstance(item, dict) and str(item.get("type") or "").lower() in {"text", "input_text"}:
                parts.append(str(item.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return str(content)


def _image_block_from_url(url: str) -> dict | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    prefix = "data:"
    if raw.startswith(prefix) and ";base64," in raw:
        media_type = raw[len(prefix): raw.find(";base64,")]
        data = raw.split(";base64,", 1)[1]
        if media_type and data:
            return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    return {"type": "image", "source": {"type": "url", "url": raw}}


def _openai_content_to_anthropic(content) -> list[dict]:
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
        ptype = str(part.get("type") or "").strip().lower()
        if ptype in {"text", "input_text"}:
            text = str(part.get("text") or "")
            if text:
                block = {"type": "text", "text": text}
                if isinstance(part.get("cache_control"), dict):
                    block["cache_control"] = deepcopy(part["cache_control"])
                out.append(block)
        elif ptype == "image_url":
            url = ""
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = str(image_url.get("url") or "")
            url = url or str(part.get("url") or "")
            block = _image_block_from_url(url)
            if block:
                out.append(block)
        elif ptype in {"thinking", "redacted_thinking", "tool_use", "tool_result"}:
            out.append(deepcopy(part))
    return out


def _system_blocks_from_message(msg: dict) -> list[dict]:
    blocks = _openai_content_to_anthropic((msg or {}).get("content"))
    text_blocks = [block for block in blocks if str(block.get("type") or "") == "text"]
    if not text_blocks:
        text = _content_to_text((msg or {}).get("content"))
        text_blocks = [{"type": "text", "text": text}] if text else []
    for block in text_blocks:
        if msg.get(DYNAMIC_SYSTEM_MARKER):
            block[DYNAMIC_SYSTEM_MARKER] = True
        if msg.get(SUMMARY_CACHE_SYSTEM_MARKER):
            block[SUMMARY_CACHE_SYSTEM_MARKER] = True
        if msg.get(SUMMARY_RECENT_SYSTEM_MARKER):
            block[SUMMARY_RECENT_SYSTEM_MARKER] = True
    return text_blocks


def _safe_json_loads(value, default):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def _add_tool_result(pending: list[dict], msg: dict) -> None:
    tool_use_id = str((msg or {}).get("tool_call_id") or (msg or {}).get("id") or (msg or {}).get("name") or "").strip()
    if not tool_use_id:
        return
    pending.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": _content_to_text((msg or {}).get("content"))})


def _convert_tools(tools) -> list[dict] | None:
    if not isinstance(tools, list):
        return None
    out: list[dict] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if str(tool.get("type") or "") == "function" and fn:
            out.append(
                {
                    "name": str(fn.get("name") or ""),
                    "description": str(fn.get("description") or ""),
                    "input_schema": fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {"type": "object", "properties": {}},
                }
            )
        elif tool.get("name") and isinstance(tool.get("input_schema"), dict):
            out.append(deepcopy(tool))
    return out or None


def _convert_tool_choice(choice):
    if not choice or choice == "auto":
        return None
    if choice == "none":
        return {"type": "none"}
    return {"type": "auto"}


def openai_to_anthropic_request(body: dict, url: str, cache_ttl: str | None = None) -> dict:
    src = dict(body or {})
    messages: list[dict] = []
    system_blocks: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            messages.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for raw_msg in src.get("messages") or []:
        if not isinstance(raw_msg, dict):
            continue
        role = str(raw_msg.get("role") or "").strip().lower()
        if role == "system":
            system_blocks.extend(_system_blocks_from_message(raw_msg))
        elif role in {"tool", "function"}:
            _add_tool_result(pending_tool_results, raw_msg)
        elif role == "user":
            flush_tool_results()
            content = _openai_content_to_anthropic(raw_msg.get("content"))
            messages.append({"role": "user", "content": content or [{"type": "text", "text": ""}]})
        elif role == "assistant":
            flush_tool_results()
            content = _openai_content_to_anthropic(raw_msg.get("content"))
            thinking_blocks = raw_msg.get("thinking_blocks")
            if isinstance(thinking_blocks, list):
                content = [deepcopy(x) for x in thinking_blocks if isinstance(x, dict)] + content
            for call in raw_msg.get("tool_calls") or []:
                if not isinstance(call, dict) or str(call.get("type") or "") != "function":
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                name = str(fn.get("name") or "").strip()
                if not name:
                    continue
                content.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": name,
                        "input": _safe_json_loads(fn.get("arguments"), {}),
                    }
                )
            if content:
                messages.append({"role": "assistant", "content": content})
    flush_tool_results()

    out: dict = {
        "model": normalize_model_for_cloudflare(str(src.get("model") or ""), url),
        "max_tokens": int(src.get("max_tokens") or src.get("max_completion_tokens") or 8192),
        "messages": messages,
    }
    if system_blocks:
        out["system"] = system_blocks
    for key in ("thinking", "output_config"):
        if isinstance(src.get(key), dict):
            out[key] = deepcopy(src[key])
    if "reasoning_effort" in src and "output_config" not in out:
        out["output_config"] = {"effort": str(src.get("reasoning_effort") or "")}
    for key in ("temperature", "top_p"):
        if src.get(key) is not None:
            out[key] = src[key]
    if src.get("stream"):
        out["stream"] = True
    if src.get("stop"):
        out["stop_sequences"] = src["stop"] if isinstance(src["stop"], list) else [src["stop"]]
    tools = _convert_tools(src.get("tools"))
    if tools:
        out["tools"] = tools
    tool_choice = _convert_tool_choice(src.get("tool_choice"))
    if tool_choice:
        out["tool_choice"] = tool_choice
    if src.get("parallel_tool_calls") is False:
        out["disable_parallel_tool_use"] = True

    apply_prompt_cache(out, cache_ttl or CLOUDFLARE_CLAUDE_CACHE_TTL)
    return out


def _cache_control(ttl: str) -> dict:
    out = {"type": "ephemeral"}
    if ttl:
        out["ttl"] = ttl
    return out


def _set_cache_control(item: dict | None, ttl: str) -> None:
    if isinstance(item, dict):
        item["cache_control"] = _cache_control(ttl)


def _looks_like_summary_cache_block(item: dict) -> bool:
    return str((item or {}).get("text") or "").lstrip().startswith("【近期记忆】")


def _looks_like_recent_summary_block(item: dict) -> bool:
    return str((item or {}).get("text") or "").lstrip().startswith("【近期记忆（最近）】")


def _looks_like_dynamic_block(item: dict) -> bool:
    text = str((item or {}).get("text") or "").lstrip()
    return any(text.startswith(hint) for hint in GATEWAY_DYNAMIC_SYSTEM_HINTS)


def _split_summary_text(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    if text.endswith("【以上为近期记忆】"):
        text = text[: -len("【以上为近期记忆】")].strip()
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


def _split_gateway_summary_blocks(system_blocks: list[dict]) -> None:
    for idx, item in enumerate(system_blocks):
        if not (item.get(SUMMARY_CACHE_SYSTEM_MARKER) or _looks_like_summary_cache_block(item)):
            continue
        if idx + 1 < len(system_blocks) and (
            system_blocks[idx + 1].get(SUMMARY_RECENT_SYSTEM_MARKER) or _looks_like_recent_summary_block(system_blocks[idx + 1])
        ):
            return
        stable_text, recent_text = _split_summary_text(str(item.get("text") or ""))
        if not recent_text:
            return
        item["text"] = stable_text
        item[SUMMARY_CACHE_SYSTEM_MARKER] = True
        system_blocks.insert(idx + 1, {"type": "text", "text": recent_text, SUMMARY_RECENT_SYSTEM_MARKER: True})
        return


def _find_cacheable_system_before(system_blocks: list[dict], end_idx: int) -> dict | None:
    for idx in range(end_idx - 1, -1, -1):
        item = system_blocks[idx]
        if (
            isinstance(item, dict)
            and not item.get(DYNAMIC_SYSTEM_MARKER)
            and not item.get(SUMMARY_RECENT_SYSTEM_MARKER)
            and not _looks_like_recent_summary_block(item)
        ):
            return item
    return None


def apply_prompt_cache(body: dict, ttl: str) -> None:
    if isinstance(body.get("tools"), list) and body["tools"]:
        _set_cache_control(body["tools"][-1], ttl)

    system_blocks = body.get("system") if isinstance(body.get("system"), list) else []
    if system_blocks:
        _split_gateway_summary_blocks(system_blocks)
        summary_idx = -1
        for idx, item in enumerate(system_blocks):
            if idx > 0 and (item.get(SUMMARY_CACHE_SYSTEM_MARKER) or _looks_like_summary_cache_block(item)):
                summary_idx = idx
                break
        if summary_idx > 0:
            _set_cache_control(_find_cacheable_system_before(system_blocks, summary_idx), ttl)
            _set_cache_control(system_blocks[summary_idx], ttl)
            for idx, item in enumerate(system_blocks[summary_idx + 1 :], start=summary_idx + 1):
                if item.get(SUMMARY_RECENT_SYSTEM_MARKER) or _looks_like_recent_summary_block(item):
                    _set_cache_control(item, ttl)
                    break
        else:
            static_system = None
            for item in system_blocks:
                if item.get(DYNAMIC_SYSTEM_MARKER) or item.get(SUMMARY_RECENT_SYSTEM_MARKER) or _looks_like_dynamic_block(item) or _looks_like_recent_summary_block(item):
                    break
                static_system = item
            _set_cache_control(static_system, ttl)
        for item in system_blocks:
            if isinstance(item, dict):
                item.pop(DYNAMIC_SYSTEM_MARKER, None)
                item.pop(SUMMARY_CACHE_SYSTEM_MARKER, None)
                item.pop(SUMMARY_RECENT_SYSTEM_MARKER, None)


def _int_value(value) -> int:
    try:
        return max(0, int(float(value or 0)))
    except Exception:
        return 0


def convert_usage(usage: dict | None) -> dict:
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _int_value(usage.get("input_tokens"))
    output_tokens = _int_value(usage.get("output_tokens"))
    cache_creation_input_tokens = _int_value(usage.get("cache_creation_input_tokens"))
    cache_read_input_tokens = _int_value(usage.get("cache_read_input_tokens"))
    total_prompt_tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    out = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_prompt_tokens + output_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "anthropic_created": cache_creation_input_tokens,
        "anthropic_read": cache_read_input_tokens,
        "prompt_tokens_details": {"cached_tokens": cache_read_input_tokens},
    }
    if isinstance(usage.get("cache_creation"), dict):
        out["cache_creation"] = usage["cache_creation"]
    if isinstance(usage.get("output_tokens_details"), dict):
        out["output_tokens_details"] = usage["output_tokens_details"]
    if isinstance(usage.get("iterations"), list):
        out["iterations"] = usage["iterations"]
        out["anthropic_iterations"] = usage["iterations"]
    return out


def anthropic_to_openai_response(data: dict, requested_model: str = "") -> dict:
    ant = data if isinstance(data, dict) else {}
    actual_model = str(ant.get("model") or "").strip() or str(requested_model or "").strip()
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    thinking_blocks: list[dict] = []
    fallback_blocks: list[dict] = []
    tool_calls: list[dict] = []
    for part in ant.get("content") or []:
        if not isinstance(part, dict):
            continue
        ptype = str(part.get("type") or "")
        if ptype == "text":
            text_parts.append(str(part.get("text") or ""))
        elif ptype == "thinking":
            thinking_blocks.append(deepcopy(part))
            thinking_text = str(part.get("thinking") or part.get("text") or "")
            if thinking_text:
                reasoning_parts.append(thinking_text)
        elif ptype == "redacted_thinking":
            thinking_blocks.append(deepcopy(part))
        elif ptype == "fallback":
            fallback_blocks.append(deepcopy(part))
        elif ptype == "tool_use":
            tool_calls.append(
                {
                    "id": str(part.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(part.get("name") or ""),
                        "arguments": json.dumps(part.get("input") or {}, ensure_ascii=False),
                    },
                }
            )
    message = {"role": "assistant", "content": "".join(text_parts) if text_parts else (None if tool_calls else "")}
    if reasoning_parts:
        message["reasoning_content"] = "\n\n".join(reasoning_parts)
    if thinking_blocks:
        message["thinking_blocks"] = thinking_blocks
    if fallback_blocks:
        message["anthropic_fallback_blocks"] = fallback_blocks
    if tool_calls:
        message["tool_calls"] = tool_calls
    stop_reason = str(ant.get("stop_reason") or "")
    response = {
        "id": "chatcmpl-" + str(ant.get("id") or int(time.time())),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": actual_model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if stop_reason == "tool_use" else ("length" if stop_reason == "max_tokens" else "stop"),
            }
        ],
        "usage": convert_usage(ant.get("usage") if isinstance(ant.get("usage"), dict) else {}),
        "anthropic_model": actual_model,
    }
    if requested_model and actual_model and actual_model != requested_model:
        response["requested_model"] = requested_model
    if fallback_blocks:
        response["anthropic_fallback_blocks"] = fallback_blocks
    return response


class AnthropicStreamConverter:
    def __init__(self, model: str):
        self.message_id = "stream"
        self.created = int(time.time())
        self.requested_model = str(model or "")
        self.serving_model = self.requested_model
        self.next_tool_index = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        self.output_tokens_details = None
        self.usage_iterations = None
        self.blocks: dict[int, dict] = {}
        self.thinking_blocks: list[dict] = []
        self.fallback_blocks: list[dict] = []

    def _chunk(self, delta: dict, finish_reason=None, extra: dict | None = None) -> dict:
        out = {
            "id": "chatcmpl-" + self.message_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.serving_model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            **(extra or {}),
        }
        if self.serving_model != self.requested_model:
            out["requested_model"] = self.requested_model
        out["anthropic_model"] = self.serving_model
        return out

    def process_event(self, event: dict) -> dict | None:
        etype = str((event or {}).get("type") or "")
        if etype == "message_start":
            msg = event.get("message") if isinstance(event.get("message"), dict) else {}
            usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
            self.message_id = str(msg.get("id") or self.message_id)
            self.serving_model = str(msg.get("model") or "").strip() or self.serving_model
            self.input_tokens = _int_value(usage.get("input_tokens"))
            self.output_tokens = _int_value(usage.get("output_tokens"))
            self.cache_creation_input_tokens = _int_value(usage.get("cache_creation_input_tokens"))
            self.cache_read_input_tokens = _int_value(usage.get("cache_read_input_tokens"))
            self.output_tokens_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else None
            self.usage_iterations = usage.get("iterations") if isinstance(usage.get("iterations"), list) else None
            return self._chunk({"role": "assistant", "content": ""})
        if etype == "content_block_start":
            index = _int_value(event.get("index"))
            block = event.get("content_block") if isinstance(event.get("content_block"), dict) else {}
            if block.get("type") == "fallback":
                self.fallback_blocks.append(deepcopy(block))
                to = block.get("to") if isinstance(block.get("to"), dict) else {}
                self.serving_model = str(to.get("model") or "").strip() or self.serving_model
                return None
            state = {"type": block.get("type"), "block": deepcopy(block)}
            if block.get("type") == "tool_use":
                state["tool_index"] = self.next_tool_index
                self.next_tool_index += 1
                self.blocks[index] = state
                return self._chunk(
                    {
                        "tool_calls": [
                            {
                                "index": state["tool_index"],
                                "id": str(block.get("id") or ""),
                                "type": "function",
                                "function": {"name": str(block.get("name") or ""), "arguments": ""},
                            }
                        ]
                    }
                )
            self.blocks[index] = state
            if block.get("type") == "thinking":
                state["block"]["thinking"] = state["block"].get("thinking") or ""
                return self._chunk({"reasoning_content": ""})
            if block.get("type") == "redacted_thinking":
                self.thinking_blocks.append(deepcopy(state["block"]))
            return None
        if etype == "content_block_delta":
            index = _int_value(event.get("index"))
            state = self.blocks.get(index) or {}
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            dtype = str(delta.get("type") or "")
            if dtype == "text_delta":
                return self._chunk({"content": str(delta.get("text") or "")})
            if dtype == "thinking_delta":
                text = str(delta.get("thinking") or delta.get("text") or "")
                if isinstance(state.get("block"), dict):
                    state["block"]["thinking"] = str(state["block"].get("thinking") or "") + text
                return self._chunk({"reasoning_content": text})
            if dtype == "signature_delta":
                if isinstance(state.get("block"), dict):
                    state["block"]["signature"] = str(state["block"].get("signature") or "") + str(delta.get("signature") or "")
                return None
            if dtype == "input_json_delta" and state.get("tool_index") is not None:
                return self._chunk({"tool_calls": [{"index": state["tool_index"], "function": {"arguments": str(delta.get("partial_json") or "")}}]})
        if etype == "message_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            stop_reason = str(delta.get("stop_reason") or "")
            self.output_tokens = _int_value(usage.get("output_tokens")) or self.output_tokens
            self.cache_creation_input_tokens = _int_value(usage.get("cache_creation_input_tokens")) or self.cache_creation_input_tokens
            self.cache_read_input_tokens = _int_value(usage.get("cache_read_input_tokens")) or self.cache_read_input_tokens
            if isinstance(usage.get("output_tokens_details"), dict):
                self.output_tokens_details = usage.get("output_tokens_details")
            if isinstance(usage.get("iterations"), list):
                self.usage_iterations = usage.get("iterations")
            full_thinking_blocks = list(self.thinking_blocks)
            for state in self.blocks.values():
                block = state.get("block") if isinstance(state, dict) else None
                if state.get("type") == "thinking" and isinstance(block, dict) and block.get("thinking"):
                    full_thinking_blocks.append(deepcopy(block))
            extra = {
                "usage": convert_usage(
                    {
                        "input_tokens": self.input_tokens,
                        "output_tokens": self.output_tokens,
                        "cache_creation_input_tokens": self.cache_creation_input_tokens,
                        "cache_read_input_tokens": self.cache_read_input_tokens,
                        "output_tokens_details": self.output_tokens_details,
                        "iterations": self.usage_iterations,
                    }
                )
            }
            if self.fallback_blocks:
                extra["anthropic_fallback_blocks"] = self.fallback_blocks
            return self._chunk(
                {"thinking_blocks": full_thinking_blocks} if full_thinking_blocks else {},
                "tool_calls" if stop_reason == "tool_use" else ("length" if stop_reason == "max_tokens" else "stop"),
                extra,
            )
        return None


def anthropic_sse_to_openai_sse(lines: Iterable[bytes], model: str) -> Iterable[bytes]:
    converter = AnthropicStreamConverter(model)
    for raw in lines:
        if raw is None:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        if not line.startswith("data:"):
            continue
        data = line.split(":", 1)[1].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except Exception:
            continue
        if isinstance(event, dict) and event.get("type") == "error":
            err = event.get("error")
            payload = {"error": err if isinstance(err, dict) else {"message": str(err or data)}}
            yield ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
            yield b"data: [DONE]\n\n"
            return
        if isinstance(event, dict) and event.get("type") == "message_stop":
            yield b"data: [DONE]\n\n"
            return
        out = converter.process_event(event if isinstance(event, dict) else {})
        if out:
            yield ("data: " + json.dumps(out, ensure_ascii=False) + "\n\n").encode("utf-8")
    yield b"data: [DONE]\n\n"
