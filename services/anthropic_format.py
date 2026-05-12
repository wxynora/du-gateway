import base64
import copy
import json
import math
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_MAX_TOKENS = 33000
THINKING_BUDGET_TOKENS = 32000
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BETA = ",".join(
    [
        "claude-code-20250219",
        "oauth-2025-04-20",
        "interleaved-thinking-2025-05-14",
        "fine-grained-tool-streaming-2025-05-14",
        "prompt-caching-scope-2026-01-05",
        "token-efficient-tools-2025-02-19",
        "context-management-2025-06-27",
        "effort-2025-11-24",
    ]
)
CLAUDE_PROMPT_CACHE_TTL = "1h"
DYNAMIC_SYSTEM_MARKER = "__dynamic__"
SUMMARY_CACHE_SYSTEM_MARKER = "__summary_cache__"
SUMMARY_RECENT_SYSTEM_MARKER = "__summary_recent__"
GATEWAY_DYNAMIC_SYSTEM_HINTS = [
    "【渡的心事",
    "【渡的日常",
    "今日：",
    "听了老婆的话，我想起来",
    "【指代提醒】",
    "老婆当前状态",
    "【当前是在 RikkaHub 和渡聊天】",
    "【Notion 相关】",
]
SYSTEM_PROMPT_PREFIX = {
    "type": "text",
    "text": "You are Claude Code, Anthropic's official CLI for Claude.",
}
MODEL_MAP = {
    "gpt-4o": "claude-sonnet-4-6",
    "gpt-4o-mini": "claude-haiku-4-5-20251001",
    "gpt-4-turbo": "claude-sonnet-4-6",
    "gpt-4": "claude-sonnet-4-6",
    "gpt-3.5-turbo": "claude-haiku-4-5-20251001",
}
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
IMAGE_DOWNLOAD_MAX_BYTES = 10 * 1024 * 1024


def normalize_request_format(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"anthropic", "claude"}:
        return "anthropic"
    return "openai"


def is_anthropic_request_format(value: Any) -> bool:
    return normalize_request_format(value) == "anthropic"


def anthropic_messages_url(url: str) -> str:
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1/messages", "/messages"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/messages"


def anthropic_models_url(url: str) -> str:
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1/messages", "/messages"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/models"


def build_anthropic_headers(api_key: str = "", upstream_url: str = "", extra: dict | None = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": ANTHROPIC_BETA,
    }
    api_key = str(api_key or "").strip()
    host = (urlparse(str(upstream_url or "").strip()).hostname or "").lower()
    if api_key:
        if host == "api.anthropic.com":
            headers["x-api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    for key, value in (extra or {}).items():
        if value:
            headers[key] = value
    return headers


def _safe_json_parse(value: Any, fallback: Any = None) -> Any:
    if fallback is None:
        fallback = {}
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") in {"text", "input_text"}:
                text = str(part.get("text") or "")
                if text:
                    out.append(text)
        return "\n".join(out)
    return str(content)


def _infer_image_mime_type(url: str, content_type: str = "") -> str:
    clean_type = str(content_type or "").split(";")[0].strip().lower()
    if clean_type in SUPPORTED_IMAGE_MIME_TYPES:
        return clean_type
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = str(url or "").lower()
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".gif"):
        return "image/gif"
    if path.endswith(".webp"):
        return "image/webp"
    return ""


def _download_image_url(raw_url: str) -> dict:
    resp = requests.get(
        raw_url,
        headers={"Accept": "image/*,*/*;q=0.8", "User-Agent": "du-gateway-anthropic-format/1.0"},
        timeout=30,
        stream=True,
        allow_redirects=True,
    )
    resp.raise_for_status()
    media_type = _infer_image_mime_type(resp.url, resp.headers.get("content-type") or "")
    if not media_type:
        raise ValueError(f"unsupported image content-type: {resp.headers.get('content-type') or 'unknown'}")
    chunks = []
    size = 0
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > IMAGE_DOWNLOAD_MAX_BYTES:
            raise ValueError(f"image too large: {size} bytes")
        chunks.append(chunk)
    return {"media_type": media_type, "data": base64.b64encode(b"".join(chunks)).decode("ascii")}


def _openai_content_to_anthropic(content: Any) -> list[dict]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content)}]

    out = []
    for part in content:
        if isinstance(part, str):
            if part:
                out.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            continue
        if part.get("type") in {"text", "input_text"}:
            text = str(part.get("text") or "")
            if text:
                out.append({"type": "text", "text": text})
            continue
        if part.get("type") == "image_url":
            url = (((part.get("image_url") or {}) if isinstance(part.get("image_url"), dict) else {}).get("url")) or part.get("url") or ""
            match = re.match(r"^data:(image/[^;]+);base64,(.+)$", str(url or ""), re.S)
            if match:
                out.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": match.group(1), "data": match.group(2)},
                    }
                )
            elif url:
                image = _download_image_url(str(url))
                out.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": image["media_type"], "data": image["data"]},
                    }
                )
    return out


def _convert_openai_tools(tools: Any) -> list[dict] | None:
    if not isinstance(tools, list):
        return None
    out = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if tool.get("type") == "function" and fn:
            out.append(
                {
                    "name": fn.get("name"),
                    "description": fn.get("description") or "",
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
                }
            )
        elif tool.get("name") and tool.get("input_schema"):
            out.append(tool)
    return out or None


def _convert_tool_choice(choice: Any) -> dict | None:
    if not choice or choice == "auto":
        return None
    if choice == "none":
        return {"type": "none"}
    return {"type": "auto"}


def _add_tool_result(pending: list[dict], msg: dict) -> None:
    tool_use_id = msg.get("tool_call_id") or msg.get("id") or msg.get("name")
    if not tool_use_id:
        return
    pending.append(
        {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": _content_to_text(msg.get("content")),
        }
    )


def openai_to_anthropic(oai: dict) -> dict:
    oai = copy.deepcopy(oai or {})
    model = MODEL_MAP.get(oai.get("model")) or oai.get("model")
    messages = []
    system_blocks = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            messages.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for raw_msg in oai.get("messages") or []:
        if not isinstance(raw_msg, dict):
            continue
        role = raw_msg.get("role")
        if role == "system":
            text = _content_to_text(raw_msg.get("content"))
            if text:
                block = {"type": "text", "text": text}
                if raw_msg.get(DYNAMIC_SYSTEM_MARKER):
                    block[DYNAMIC_SYSTEM_MARKER] = True
                if raw_msg.get(SUMMARY_CACHE_SYSTEM_MARKER):
                    block[SUMMARY_CACHE_SYSTEM_MARKER] = True
                if raw_msg.get(SUMMARY_RECENT_SYSTEM_MARKER):
                    block[SUMMARY_RECENT_SYSTEM_MARKER] = True
                system_blocks.append(block)
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
                content = [x for x in thinking_blocks if isinstance(x, dict)] + content
            for call in raw_msg.get("tool_calls") or []:
                if not isinstance(call, dict) or call.get("type") != "function":
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else None
                if not fn or not fn.get("name"):
                    continue
                content.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id"),
                        "name": fn.get("name"),
                        "input": _safe_json_parse(fn.get("arguments"), {}),
                    }
                )
            if content:
                messages.append({"role": "assistant", "content": content})
    flush_tool_results()

    body = {
        "model": model,
        "max_tokens": oai.get("max_tokens") or oai.get("max_completion_tokens") or DEFAULT_MAX_TOKENS,
        "messages": messages,
    }
    if system_blocks:
        body["system"] = system_blocks
    if oai.get("temperature") is not None:
        body["temperature"] = oai.get("temperature")
    if oai.get("top_p") is not None:
        body["top_p"] = oai.get("top_p")
    if oai.get("stream"):
        body["stream"] = True
    if oai.get("stop"):
        body["stop_sequences"] = oai.get("stop") if isinstance(oai.get("stop"), list) else [oai.get("stop")]
    tools = _convert_openai_tools(oai.get("tools"))
    if tools:
        body["tools"] = tools
    tool_choice = _convert_tool_choice(oai.get("tool_choice"))
    if tool_choice:
        body["tool_choice"] = tool_choice
    if oai.get("parallel_tool_calls") is False:
        body["disable_parallel_tool_use"] = True

    return apply_default_thinking(body)


def apply_default_thinking(body: dict) -> dict:
    if not isinstance(body, dict) or body.get("thinking"):
        return body
    if not model_supports_thinking(body.get("model")):
        return body

    max_tokens = int(body.get("max_tokens") or DEFAULT_MAX_TOKENS)
    budget = min(THINKING_BUDGET_TOKENS, max_tokens - 1)
    if budget < 1024:
        return body

    body["max_tokens"] = max(max_tokens, budget + 1)
    body["thinking"] = {"type": "enabled", "budget_tokens": budget}
    body.pop("temperature", None)
    body.pop("top_k", None)
    return body


def model_supports_thinking(model: Any) -> bool:
    return bool(re.search(r"claude-(opus|sonnet)-4|claude-3-7-sonnet", str(model or "")))


def _strip_ttl_from_cache_control(obj: dict) -> None:
    def process(arr: Any) -> None:
        if not isinstance(arr, list):
            return
        for item in arr:
            if isinstance(item, dict) and isinstance(item.get("cache_control"), dict):
                item["cache_control"].pop("ttl", None)

    if isinstance(obj.get("system"), list):
        process(obj.get("system"))
    if isinstance(obj.get("messages"), list):
        for msg in obj.get("messages") or []:
            if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                process(msg.get("content"))


def process_anthropic_body(body: dict) -> dict:
    if body.get("system"):
        if isinstance(body.get("system"), list):
            body["system"].insert(0, static_system_prompt_block())
        else:
            body["system"] = [static_system_prompt_block(), {"type": "text", "text": str(body.get("system"))}]
    else:
        body["system"] = [static_system_prompt_block()]
    _strip_ttl_from_cache_control(body)
    apply_prompt_cache(body)
    return body


def prepare_anthropic_body(openai_body: dict) -> dict:
    return process_anthropic_body(openai_to_anthropic(openai_body))


def static_system_prompt_block() -> dict:
    return dict(SYSTEM_PROMPT_PREFIX)


def apply_prompt_cache(body: dict) -> None:
    cache_control = {"type": "ephemeral", "ttl": CLAUDE_PROMPT_CACHE_TTL} if CLAUDE_PROMPT_CACHE_TTL else {"type": "ephemeral"}

    def set_cache_control(item: dict | None) -> None:
        if isinstance(item, dict):
            item["cache_control"] = dict(cache_control)

    if isinstance(body.get("tools"), list) and body["tools"]:
        set_cache_control(body["tools"][-1])

    if isinstance(body.get("system"), list) and body["system"]:
        split_gateway_summary_blocks(body["system"])

        summary_idx = next(
            (
                idx
                for idx, item in enumerate(body["system"])
                if idx > 0
                and isinstance(item, dict)
                and (item.get(SUMMARY_CACHE_SYSTEM_MARKER) or looks_like_gateway_summary_cache_block(item))
            ),
            -1,
        )

        if summary_idx > 0:
            set_cache_control(find_cacheable_system_before(body["system"], summary_idx))
            set_cache_control(body["system"][summary_idx])
            recent_idx = next(
                (
                    idx
                    for idx, item in enumerate(body["system"])
                    if idx > summary_idx
                    and isinstance(item, dict)
                    and (item.get(SUMMARY_RECENT_SYSTEM_MARKER) or looks_like_gateway_recent_summary_block(item))
                ),
                -1,
            )
            if recent_idx > summary_idx:
                set_cache_control(body["system"][recent_idx])
        else:
            static_system = None
            for item in body["system"][1:]:
                if not isinstance(item, dict):
                    continue
                if (
                    item.get(DYNAMIC_SYSTEM_MARKER)
                    or item.get(SUMMARY_RECENT_SYSTEM_MARKER)
                    or looks_like_gateway_dynamic_system_block(item)
                    or looks_like_gateway_recent_summary_block(item)
                ):
                    break
                static_system = item
            set_cache_control(static_system)

        for item in body["system"]:
            if isinstance(item, dict):
                item.pop(DYNAMIC_SYSTEM_MARKER, None)
                item.pop(SUMMARY_CACHE_SYSTEM_MARKER, None)
                item.pop(SUMMARY_RECENT_SYSTEM_MARKER, None)


def split_gateway_summary_blocks(system_blocks: list) -> None:
    if not isinstance(system_blocks, list):
        return
    for idx in range(1, len(system_blocks)):
        item = system_blocks[idx]
        if not isinstance(item, dict):
            continue
        if not (item.get(SUMMARY_CACHE_SYSTEM_MARKER) or looks_like_gateway_summary_cache_block(item)):
            continue
        if idx + 1 < len(system_blocks):
            next_item = system_blocks[idx + 1]
            if isinstance(next_item, dict) and (
                next_item.get(SUMMARY_RECENT_SYSTEM_MARKER) or looks_like_gateway_recent_summary_block(next_item)
            ):
                return
        split = split_gateway_summary_text(item.get("text"))
        if not split["recent_text"]:
            return
        item["text"] = split["stable_text"]
        item[SUMMARY_CACHE_SYSTEM_MARKER] = True
        system_blocks.insert(
            idx + 1,
            {
                "type": "text",
                "text": split["recent_text"],
                SUMMARY_RECENT_SYSTEM_MARKER: True,
            },
        )
        return


def split_gateway_summary_text(value: Any) -> dict:
    text = str(value or "").strip()
    if not text:
        return {"stable_text": "", "recent_text": ""}
    text = re.sub(r"【以上为近期记忆】\s*$", "", text).strip()
    recent_idx = text.find("【最近】")
    if recent_idx < 0:
        return {"stable_text": str(value or ""), "recent_text": ""}
    stable_raw = text[:recent_idx].strip()
    recent_raw = text[recent_idx:].strip()
    if not recent_raw:
        return {"stable_text": str(value or ""), "recent_text": ""}
    return {
        "stable_text": f"{stable_raw}\n【以上为较稳定的近期记忆】" if stable_raw else "",
        "recent_text": f"\n\n【近期记忆（最近）】\n{recent_raw}\n【以上为最近记忆】",
    }


def find_cacheable_system_before(system_blocks: list, end_idx: int) -> dict | None:
    for idx in range(end_idx - 1, 0, -1):
        item = system_blocks[idx]
        if (
            isinstance(item, dict)
            and not item.get(DYNAMIC_SYSTEM_MARKER)
            and not item.get(SUMMARY_RECENT_SYSTEM_MARKER)
            and not looks_like_gateway_recent_summary_block(item)
        ):
            return item
    return None


def looks_like_gateway_summary_cache_block(item: dict) -> bool:
    return str((item or {}).get("text") or "").lstrip().startswith("【近期记忆】")


def looks_like_gateway_recent_summary_block(item: dict) -> bool:
    return str((item or {}).get("text") or "").lstrip().startswith("【近期记忆（最近）】")


def looks_like_gateway_dynamic_system_block(item: dict) -> bool:
    text = str((item or {}).get("text") or "").lstrip()
    return bool(text) and any(text.startswith(hint) for hint in GATEWAY_DYNAMIC_SYSTEM_HINTS)


def convert_usage(usage: dict | None) -> dict:
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_creation_input_tokens = int(usage.get("cache_creation_input_tokens") or 0)
    cache_read_input_tokens = int(usage.get("cache_read_input_tokens") or 0)
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "anthropic_created": cache_creation_input_tokens,
        "anthropic_read": cache_read_input_tokens,
        "prompt_tokens_details": {"cached_tokens": cache_read_input_tokens},
    }


def anthropic_to_openai(ant: dict, model: str, is_stream: bool = False) -> dict | None:
    if is_stream:
        return AnthropicStreamConverter(model).convert_event(ant)

    text_parts = []
    reasoning_parts = []
    thinking_blocks = []
    tool_calls = []
    for part in (ant or {}).get("content") or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            text_parts.append(str(part.get("text") or ""))
        elif part.get("type") == "thinking":
            thinking_blocks.append(part)
            thinking_text = part.get("thinking") or part.get("text") or ""
            if thinking_text:
                reasoning_parts.append(str(thinking_text))
        elif part.get("type") == "redacted_thinking":
            thinking_blocks.append(part)
        elif part.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": part.get("id"),
                    "type": "function",
                    "function": {
                        "name": part.get("name"),
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
    if tool_calls:
        message["tool_calls"] = tool_calls

    stop_reason = (ant or {}).get("stop_reason")
    return {
        "id": "chatcmpl-" + str((ant or {}).get("id") or "anthropic"),
        "object": "chat.completion",
        "created": math.floor(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if stop_reason == "tool_use" else "length" if stop_reason == "max_tokens" else "stop",
            }
        ],
        "usage": convert_usage((ant or {}).get("usage")),
    }


class AnthropicStreamConverter:
    def __init__(self, model: str):
        self.model = model
        self.message_id = "stream"
        self.created = math.floor(time.time())
        self.next_tool_index = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        self.blocks: dict[int, dict] = {}
        self.thinking_blocks: list[dict] = []

    def _chunk(self, delta: dict, finish_reason: str | None = None, extra: dict | None = None) -> dict:
        return {
            "id": "chatcmpl-" + self.message_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            **(extra or {}),
        }

    def convert_event(self, event: dict) -> dict | None:
        if not isinstance(event, dict):
            return None
        event_type = event.get("type")
        if event_type == "message_start":
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            self.message_id = message.get("id") or self.message_id
            self.input_tokens = int(usage.get("input_tokens") or 0)
            self.output_tokens = int(usage.get("output_tokens") or 0)
            self.cache_creation_input_tokens = int(usage.get("cache_creation_input_tokens") or 0)
            self.cache_read_input_tokens = int(usage.get("cache_read_input_tokens") or 0)
            return self._chunk({"role": "assistant", "content": ""})

        if event_type == "content_block_start":
            index = int(event.get("index") or 0)
            block = event.get("content_block") if isinstance(event.get("content_block"), dict) else {}
            state = {"type": block.get("type"), "block": dict(block)}
            if block.get("type") == "tool_use":
                state["tool_index"] = self.next_tool_index
                self.next_tool_index += 1
                self.blocks[index] = state
                return self._chunk(
                    {
                        "tool_calls": [
                            {
                                "index": state["tool_index"],
                                "id": block.get("id"),
                                "type": "function",
                                "function": {"name": block.get("name"), "arguments": ""},
                            }
                        ]
                    }
                )
            self.blocks[index] = state
            if block.get("type") == "thinking":
                state["block"]["thinking"] = state["block"].get("thinking") or ""
                return self._chunk({"reasoning_content": ""})
            if block.get("type") == "redacted_thinking":
                self.thinking_blocks.append(state["block"])
            return None

        if event_type == "content_block_delta":
            index = int(event.get("index") or 0)
            state = self.blocks.get(index) or {}
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            if delta.get("type") == "text_delta":
                return self._chunk({"content": delta.get("text") or ""})
            if delta.get("type") == "thinking_delta":
                text = delta.get("thinking") or delta.get("text") or ""
                if isinstance(state.get("block"), dict):
                    state["block"]["thinking"] = (state["block"].get("thinking") or "") + str(text)
                return self._chunk({"reasoning_content": text})
            if delta.get("type") == "signature_delta":
                if isinstance(state.get("block"), dict):
                    state["block"]["signature"] = (state["block"].get("signature") or "") + str(delta.get("signature") or "")
                return None
            if delta.get("type") == "input_json_delta" and state.get("tool_index") is not None:
                return self._chunk(
                    {
                        "tool_calls": [
                            {
                                "index": state["tool_index"],
                                "function": {"arguments": delta.get("partial_json") or ""},
                            }
                        ]
                    }
                )

        if event_type == "message_delta":
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            stop_reason = delta.get("stop_reason")
            self.output_tokens = int(usage.get("output_tokens") or self.output_tokens)
            self.cache_creation_input_tokens = int(
                usage.get("cache_creation_input_tokens") or self.cache_creation_input_tokens
            )
            self.cache_read_input_tokens = int(usage.get("cache_read_input_tokens") or self.cache_read_input_tokens)
            full_thinking_blocks = list(self.thinking_blocks)
            for state in self.blocks.values():
                block = state.get("block") if isinstance(state, dict) else None
                if state.get("type") == "thinking" and isinstance(block, dict) and block.get("thinking"):
                    full_thinking_blocks.append(block)
            return self._chunk(
                {"thinking_blocks": full_thinking_blocks} if full_thinking_blocks else {},
                "tool_calls" if stop_reason == "tool_use" else "length" if stop_reason == "max_tokens" else "stop",
                {
                    "usage": convert_usage(
                        {
                            "input_tokens": self.input_tokens,
                            "output_tokens": self.output_tokens,
                            "cache_creation_input_tokens": self.cache_creation_input_tokens,
                            "cache_read_input_tokens": self.cache_read_input_tokens,
                        }
                    )
                },
            )

        return None
