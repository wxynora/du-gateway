import copy
from typing import Any

from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)

_THINKING_BLOCK_TYPES = {"thinking", "redacted_thinking"}


def _role(msg: dict) -> str:
    return str((msg or {}).get("role") or "").strip().lower()


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if str(item.get("type") or "").strip().lower() == "text":
                    parts.append(str(item.get("text") or item.get("content") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _content_fingerprint(content: Any) -> str:
    return " ".join(_content_text(content).split()).strip()


def _normalized_thinking_blocks(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    blocks: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        btype = str(item.get("type") or "").strip()
        if btype not in _THINKING_BLOCK_TYPES:
            continue
        if btype == "thinking" and not item.get("signature"):
            continue
        if btype == "redacted_thinking" and not (
            item.get("data") or item.get("signature") or item.get("redacted_thinking")
        ):
            continue
        blocks.append(copy.deepcopy(item))
    return blocks


def extract_claude_thinking_blocks(msg: dict) -> list[dict]:
    """取 Claude 可回传的原始 thinking blocks；优先使用显式字段，旧归档才兜底 reasoning_details。"""
    if not isinstance(msg, dict):
        return []
    blocks = _normalized_thinking_blocks(msg.get("thinking_blocks"))
    if blocks:
        return blocks
    # 旧流式归档可能只保留在 reasoning_details。带 tool trace 的轮次不从 details 兜底，
    # 避免把中间工具轮 thinking block 错挂到最终 assistant 回复上。
    if msg.get("tool_calls"):
        return []
    return _normalized_thinking_blocks(msg.get("reasoning_details"))


def _opaque_thinking_blocks(value: Any) -> list[dict]:
    """把跨轮 thinking 压成仅含验证材料的结构，不把可见转写带入下一轮。"""
    opaque: list[dict] = []
    for block in _normalized_thinking_blocks(value):
        btype = block.get("type")
        if btype == "thinking":
            opaque.append(
                {
                    "type": "thinking",
                    "thinking": "",
                    "signature": copy.deepcopy(block.get("signature")),
                }
            )
            continue

        redacted = {"type": "redacted_thinking"}
        for key in ("data", "signature", "redacted_thinking"):
            if block.get(key):
                redacted[key] = copy.deepcopy(block.get(key))
                break
        opaque.append(redacted)
    return opaque


def _latest_round_for_carryover(window_id: str) -> tuple[dict | None, str]:
    window = str(window_id or "").strip()
    rounds = r2_store.get_conversation_rounds(window, last_n=1) or []
    if rounds:
        return rounds[-1], "window"
    if window.startswith("tg_"):
        return None, ""
    rounds = r2_store.get_latest_4_rounds_global() or []
    if rounds:
        return rounds[-1], "global_latest4"
    return None, ""


def _round_user_and_assistant(round_obj: dict) -> tuple[dict | None, dict | None]:
    user_msg = None
    assistant_msg = None
    for msg in (round_obj or {}).get("messages") or []:
        if not isinstance(msg, dict):
            continue
        role = _role(msg)
        if role == "user":
            user_msg = msg
        elif role == "assistant":
            assistant_msg = msg
    return user_msg, assistant_msg


def _last_user_index(messages: list[dict]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], dict) and _role(messages[idx]) == "user":
            return idx
    return None


def _make_existing_thinking_opaque_before(messages: list[dict], idx: int) -> bool:
    found = False
    for msg in messages[:idx]:
        if not isinstance(msg, dict) or _role(msg) != "assistant":
            continue
        blocks = extract_claude_thinking_blocks(msg)
        if not blocks:
            continue
        msg["thinking_blocks"] = _opaque_thinking_blocks(blocks)
        msg.pop("reasoning_details", None)
        found = True
    return found


def _attach_to_matching_assistant(messages: list[dict], idx: int, assistant_msg: dict, blocks: list[dict]) -> bool:
    target_key = _content_fingerprint((assistant_msg or {}).get("content"))
    if not target_key:
        return False
    for msg in reversed(messages[:idx]):
        if not isinstance(msg, dict) or _role(msg) != "assistant":
            continue
        if _content_fingerprint(msg.get("content")) != target_key:
            continue
        if not extract_claude_thinking_blocks(msg):
            msg["thinking_blocks"] = copy.deepcopy(blocks)
        return True
    return False


def inject_previous_claude_thinking_blocks(body: dict, window_id: str) -> dict:
    """
    普通跨轮请求只把上一轮 assistant thinking 的 opaque signature/data 随上一轮消息回传。

    可见的官方摘要/转写不会进入下一轮；同一轮工具续跑使用完整原始 block 的链路不在这里。
    """
    if not isinstance(body, dict):
        return body
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return body
    round_obj, source = _latest_round_for_carryover(window_id)
    if not round_obj:
        return body
    prev_user, prev_assistant = _round_user_and_assistant(round_obj)
    if not prev_user or not prev_assistant:
        return body
    archived_blocks = extract_claude_thinking_blocks(prev_assistant)
    if not archived_blocks:
        return body
    blocks = _opaque_thinking_blocks(archived_blocks)
    body = copy.deepcopy(body)
    messages = list(body.get("messages") or [])
    idx = _last_user_index(messages)
    if idx is None:
        return body
    if _make_existing_thinking_opaque_before(messages, idx):
        body["messages"] = messages
        return body
    if _attach_to_matching_assistant(messages, idx, prev_assistant, blocks):
        body["messages"] = messages
        logger.info("Claude thinking carryover attached window_id=%s blocks=%s source=%s", window_id, len(blocks), source)
        return body
    carry_user = {
        "role": "user",
        "content": copy.deepcopy(prev_user.get("content") if prev_user.get("content") is not None else ""),
    }
    carry_assistant = {
        "role": "assistant",
        "content": copy.deepcopy(prev_assistant.get("content") if prev_assistant.get("content") is not None else ""),
        "thinking_blocks": copy.deepcopy(blocks),
    }
    messages[idx:idx] = [carry_user, carry_assistant]
    body["messages"] = messages
    logger.info("Claude thinking carryover inserted window_id=%s blocks=%s source=%s", window_id, len(blocks), source)
    return body
