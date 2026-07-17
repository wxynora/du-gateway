import json
from urllib.parse import urlparse

from services.chat_content import message_content_chars
from utils.tokens import estimate_tokens


def _static_system_base_label(msg: dict, idx: int, content: str) -> str:
    stripped = content.lstrip()
    if msg.get("__summary_cache__") or msg.get("__summary_recent__") or "【近期记忆】" in content:
        return "近期记忆"
    if stripped.startswith("【入口风格：QQ】"):
        return "QQ入口风格"
    if stripped.startswith("【入口风格：微信】"):
        return "微信入口风格"
    if stripped.startswith("【入口风格：SumiTalk】"):
        return "SumiTalk入口风格"
    if stripped.startswith("【入口风格：TG】"):
        return "TG入口风格"
    if stripped.startswith("### thinking block 约束"):
        return "thinking规则"
    if stripped.startswith("### 核心行为与前置判断规则"):
        return "核心行为规则"
    if stripped.startswith("### 常识"):
        return "常识"
    if stripped.startswith("### 待续念头维护"):
        return "待续念头规则"
    if stripped.startswith("【核心XP与互动逻辑】"):
        return "NSFW规则"
    if stripped.startswith("【渡的拟态心跳"):
        return "拟态心跳规则"
    if stripped.startswith("【小家状态写入规则】"):
        return "小家规则"
    if stripped.startswith("【最近一段时间"):
        return "中期记忆"
    if stripped.startswith("【相处模式候选"):
        return "相处模式候选"
    if stripped.startswith("【Stay with Du】"):
        return "Stay with Du"
    if stripped.startswith("【渡的记事本】"):
        return "渡的记事本"
    if stripped.startswith("【提醒工具优先级】"):
        return "提醒工具规则"
    if stripped.startswith("【论坛工具省费规则】"):
        return "论坛工具规则"
    if stripped.startswith("【高德官方 MCP 出行工具规则】"):
        return "高德出行工具规则"
    if stripped.startswith("如果你这句话说完，心里还是惦记着她"):
        return "followup规则"
    if idx == 0:
        return "核心prompt"
    return f"system#{idx + 1}"


def _static_system_breakdown_parts(msg: dict, idx: int) -> list[dict]:
    content = str(msg.get("content") or "")
    if not content:
        return []
    marker_labels = [
        ("【核心XP与互动逻辑】", "NSFW规则"),
        ("【渡的拟态心跳", "拟态心跳规则"),
        ("【小家状态写入规则】", "小家规则"),
        ("【最近一段时间", "中期记忆"),
        ("【相处模式候选", "相处模式候选"),
        ("【Stay with Du】", "Stay with Du"),
        ("【渡的记事本】", "渡的记事本"),
        ("【提醒工具优先级】", "提醒工具规则"),
        ("【论坛工具省费规则】", "论坛工具规则"),
        ("【高德官方 MCP 出行工具规则】", "高德出行工具规则"),
        ("### 待续念头维护", "待续念头规则"),
        ("如果你这句话说完，心里还是惦记着她", "followup规则"),
    ]
    markers: dict[int, str] = {}
    for marker, label in marker_labels:
        pos = content.find(marker)
        if pos >= 0:
            markers[pos] = label
    base_label = _static_system_base_label(msg, idx, content)
    boundaries: list[tuple[int, str]] = []
    if 0 in markers:
        boundaries.append((0, markers.pop(0)))
    else:
        boundaries.append((0, base_label))
    for pos in sorted(markers):
        boundaries.append((pos, markers[pos]))

    out: list[dict] = []
    for i, (start, label) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(content)
        chars = max(0, end - start)
        if chars <= 0:
            continue
        out.append(
            {
                "index": idx,
                "label": label,
                "chars": chars,
                "est_tokens": estimate_tokens("x" * chars),
            }
        )
    return out


def _dynamic_system_label_for_marker(marker: str) -> str:
    if marker.startswith("当前底座为："):
        return "当前底座"
    marker_map = {
        "【本轮可选梗素材】": "热梗素材",
        "【指代提醒】": "最近对话",
        "今日：": "时间/日期",
        "老婆当前状态": "感知快照",
        "【小家状态】": "小家状态",
        "【渡的心事": "渡的心事",
        "【你的待续念头": "待续念头",
        "【醒来补帧": "醒来补帧",
        "【渡的拟态心跳/呼吸当前读数】": "拟态心跳读数",
        "【渡的拟态心跳": "拟态心跳规则",
        "【渡的日常": "渡的日常",
        "你正在和小玥一起听歌。": "一起听上下文",
        "【一起听上下文】": "一起听上下文",
        "【当前背景音乐】": "背景音乐上下文",
        "【当前是在 RikkaHub": "RikkaHub提醒",
        "听了老婆的话，我想起来了一些之前的事": "可召回记忆",
    }
    for prefix, label in marker_map.items():
        if marker.startswith(prefix):
            return label
    return "动态区"


def _dynamic_system_breakdown_parts(msg: dict, idx: int) -> list[dict]:
    content = str(msg.get("content") or "")
    if not content:
        return []

    markers = [
        "当前底座为：",
        "【本轮可选梗素材】",
        "【指代提醒】",
        "今日：",
        "老婆当前状态",
        "【小家状态】",
        "【渡的心事",
        "【你的待续念头",
        "【醒来补帧",
        "【渡的拟态心跳/呼吸当前读数】",
        "【渡的日常",
        "你正在和小玥一起听歌。",
        "【一起听上下文】",
        "【当前背景音乐】",
        "【当前是在 RikkaHub",
        "听了老婆的话，我想起来了一些之前的事",
    ]
    boundaries: list[tuple[int, str]] = []
    for marker in markers:
        start = 0
        while True:
            pos = content.find(marker, start)
            if pos < 0:
                break
            boundaries.append((pos, _dynamic_system_label_for_marker(marker)))
            start = pos + max(1, len(marker))
    boundaries.sort(key=lambda x: x[0])

    out: list[dict] = []
    if not boundaries:
        chars = len(content)
        return [
            {
                "index": idx,
                "label": "动态区未识别",
                "chars": chars,
                "est_tokens": estimate_tokens("x" * chars),
            }
        ] if content.strip() else []

    if boundaries[0][0] > 0 and content[: boundaries[0][0]].strip():
        boundaries.insert(0, (0, "动态区未识别"))

    for i, (start, label) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(content)
        piece = content[start:end]
        if not piece.strip():
            continue
        chars = max(0, end - start)
        if chars <= 0:
            continue
        out.append(
            {
                "index": idx,
                "label": label,
                "chars": chars,
                "est_tokens": estimate_tokens("x" * chars),
            }
        )
    return out


def build_prompt_cache_profile(body: dict, upstream_url: str = "") -> dict:
    messages = (body or {}).get("messages") or []
    tools = (body or {}).get("tools") or []
    static_chars = 0
    dynamic_chars = 0
    leading_system_chars = 0
    total_message_chars = 0
    dynamic_marker_seen = False
    static_breakdown: list[dict] = []
    dynamic_breakdown: list[dict] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        chars = message_content_chars(m.get("content"))
        total_message_chars += chars
    for msg_idx, m in enumerate(messages):
        if not isinstance(m, dict):
            break
        if str(m.get("role") or "").strip().lower() != "system":
            break
        chars = message_content_chars(m.get("content"))
        leading_system_chars += chars
        if m.get("__dynamic__"):
            dynamic_marker_seen = True
            dynamic_chars += chars
            dynamic_breakdown.extend(_dynamic_system_breakdown_parts(m, msg_idx))
        elif dynamic_marker_seen:
            dynamic_chars += chars
            dynamic_breakdown.extend(_dynamic_system_breakdown_parts(m, msg_idx))
        else:
            static_chars += chars
            static_breakdown.extend(_static_system_breakdown_parts(m, msg_idx))
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
        "static_breakdown": static_breakdown,
        "dynamic_breakdown": dynamic_breakdown,
        "dynamic_marker_seen": dynamic_marker_seen,
        "prompt_cache_key": str((body or {}).get("prompt_cache_key") or ""),
        "prompt_cache_retention": str((body or {}).get("prompt_cache_retention") or ""),
    }


def extract_prompt_cache_usage(data: dict) -> dict:
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return {"usage_returned": False}
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    output_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    iterations = usage.get("iterations")
    if not isinstance(iterations, list):
        iterations = usage.get("anthropic_iterations")
    if not isinstance(iterations, list):
        iterations = []
    fallback_iterations = [
        item for item in iterations if isinstance(item, dict) and str(item.get("type") or "") == "fallback_message"
    ]
    cached_tokens = prompt_details.get("cached_tokens")
    if cached_tokens is None:
        cached_tokens = input_details.get("cached_tokens")
    out = {
        "usage_returned": True,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "output_tokens_details": output_details or None,
        "thinking_tokens": output_details.get("thinking_tokens"),
        "cached_tokens": cached_tokens,
        "prompt_cached_tokens": prompt_details.get("cached_tokens"),
        "input_cached_tokens": input_details.get("cached_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
    }
    if iterations:
        out["iterations"] = iterations
        out["fallback_message_count"] = len(fallback_iterations)
        if fallback_iterations:
            out["fallback_model"] = str(fallback_iterations[-1].get("model") or "")
    return out


def extract_upstream_response_debug(data: dict, request_model: str = "") -> dict:
    if not isinstance(data, dict):
        return {}
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    msg = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    actual_model = str(data.get("anthropic_model") or data.get("model") or "").strip()
    requested_model = str(data.get("requested_model") or request_model or "").strip()
    fallback_blocks = data.get("anthropic_fallback_blocks")
    if not isinstance(fallback_blocks, list):
        fallback_blocks = msg.get("anthropic_fallback_blocks")
    if not isinstance(fallback_blocks, list):
        fallback_blocks = []
    out = {
        "requested_model": requested_model,
        "actual_model": actual_model,
        "model_changed": bool(requested_model and actual_model and requested_model != actual_model),
        "finish_reason": str(first_choice.get("finish_reason") or "").strip(),
    }
    if fallback_blocks:
        out["fallback_blocks"] = fallback_blocks
        out["served_by_fallback"] = True
    return out


def build_cache_debug_entry(body_send: dict, upstream_url: str, prompt_cache_profile: dict | None, data: dict) -> dict:
    profile = dict(prompt_cache_profile or build_prompt_cache_profile(body_send, upstream_url))
    parsed = urlparse(str(upstream_url or "").strip())
    profile["upstream_host"] = parsed.hostname or profile.get("upstream_host") or ""
    profile["upstream_path"] = parsed.path or profile.get("upstream_path") or ""
    profile["model"] = str((body_send or {}).get("model") or profile.get("model") or "")
    profile["prompt_cache_key"] = str((body_send or {}).get("prompt_cache_key") or profile.get("prompt_cache_key") or "")
    profile["prompt_cache_retention"] = str((body_send or {}).get("prompt_cache_retention") or profile.get("prompt_cache_retention") or "")
    return {
        "request": profile,
        "usage": extract_prompt_cache_usage(data),
        "response": extract_upstream_response_debug(data, profile.get("model") or ""),
    }


class StreamCacheDebugCollector:
    """Collect the final usage/model fields from OpenAI-compatible SSE packets."""

    def __init__(self, body_send: dict, upstream_url: str, prompt_cache_profile: dict | None = None):
        self.body_send = body_send
        self.upstream_url = upstream_url
        self.prompt_cache_profile = prompt_cache_profile
        self.usage: dict = {}
        self.response: dict = {}
        self.finish_reason = ""

    @staticmethod
    def _merge_dict(target: dict, incoming: dict) -> None:
        for key, value in incoming.items():
            if value is None:
                continue
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                StreamCacheDebugCollector._merge_dict(target[key], value)
            else:
                target[key] = value

    def feed(self, chunk: bytes | bytearray | str) -> None:
        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk or "")
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line.split(":", 1)[1].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                packet = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(packet, dict):
                continue
            usage = packet.get("usage")
            if isinstance(usage, dict):
                self._merge_dict(self.usage, usage)
            for key in (
                "model",
                "anthropic_model",
                "requested_model",
                "anthropic_fallback_blocks",
            ):
                value = packet.get(key)
                if value is not None:
                    self.response[key] = value
            choices = packet.get("choices") if isinstance(packet.get("choices"), list) else []
            first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            finish_reason = str(first_choice.get("finish_reason") or "").strip()
            if finish_reason:
                self.finish_reason = finish_reason

    def build(self) -> dict:
        data = dict(self.response)
        if self.usage:
            data["usage"] = self.usage
        if self.finish_reason:
            data["choices"] = [{"finish_reason": self.finish_reason}]
        return build_cache_debug_entry(
            self.body_send,
            self.upstream_url,
            self.prompt_cache_profile,
            data,
        )
