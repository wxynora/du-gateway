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
    if stripped.startswith("【核心XP与互动逻辑】"):
        return "NSFW规则"
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


def build_prompt_cache_profile(body: dict, upstream_url: str = "") -> dict:
    messages = (body or {}).get("messages") or []
    tools = (body or {}).get("tools") or []
    static_chars = 0
    dynamic_chars = 0
    leading_system_chars = 0
    total_message_chars = 0
    dynamic_marker_seen = False
    static_breakdown: list[dict] = []
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
        elif dynamic_marker_seen:
            dynamic_chars += chars
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
    }
