"""Pure prompt-system layout primitives shared by the pipeline facade."""

import copy


_DYNAMIC_SYSTEM_MARKER = "__dynamic__"
_TEMPORARY_DYNAMIC_SYSTEM_MARKER = "__temporary_dynamic__"
_LAST4_SYSTEM_MARKER = "__last4__"
_SUMMARY_CACHE_SYSTEM_MARKER = "__summary_cache__"
_SUMMARY_RECENT_SYSTEM_MARKER = "__summary_recent__"
_TOOL_RESULT_CACHE_SYSTEM_MARKER = "__tool_result_cache__"
_STATIC_CACHE_ANCHOR_SYSTEM_MARKER = "__static_cache_anchor__"
_FROZEN_TOOL_SUMMARY_SYSTEM_MARKER = "__frozen_tool_summary__"
_RECENT_TOOL_BATCH_SYSTEM_MARKER = "__recent_tool_batch__"
_HOT_TOOL_RESULT_SYSTEM_MARKER = "__hot_tool_result__"
_PROMPT_CACHE_LAYOUT_BODY_KEY = "__prompt_cache_layout__"
_DRAFT_REMINDER_SYSTEM_MARKER = "__draft_reminder__"
_THINKING_RULES_SYSTEM_MARKER = "__thinking_rules__"
_ENTRY_STYLE_SYSTEM_MARKER = "__entry_style__"
_SUMITALK_REAL_MODE_SYSTEM_MARKER = "__sumitalk_real_mode__"
_VOICE_RULES_SYSTEM_MARKER = "__voice_rules__"
_DU_DAILY_SYSTEM_MARKER = "__du_daily__"
_PLAY_NOTE_SYSTEM_MARKER = "__play_note__"

# Keep logical prompt regions explicit. Dynamic context is ordered by injection slot:
# normal runtime context, temporary scene/event context, Thinking rules, then recent conversation.
_SYSTEM_PROMPT_REGION_ORDER = (
    "static",
    "voice_rules",
    "entry_style",
    "frozen_tool_summary",
    "summary_cache",
    "summary_recent",
    "recent_tool_batches",
    "hot_tool_results",
    "du_daily",
    "dynamic",
    "temporary_dynamic",
    "draft_reminder",
    "thinking_rules",
    "sumitalk_mode",
    "last4",
)
_SYSTEM_PROMPT_CACHE_GROUPS = (
    ("static",),
    ("voice_rules",),
    ("entry_style",),
    ("frozen_tool_summary", "summary_cache"),
    ("summary_recent", "recent_tool_batches"),
    ("hot_tool_results",),
    ("du_daily",),
    ("dynamic",),
    ("temporary_dynamic",),
    ("draft_reminder",),
    ("thinking_rules",),
    ("sumitalk_mode",),
    ("last4",),
)


def _is_persistent_dynamic_system(msg: dict) -> bool:
    return bool(
        isinstance(msg, dict)
        and msg.get(_DYNAMIC_SYSTEM_MARKER)
        and not msg.get(_TEMPORARY_DYNAMIC_SYSTEM_MARKER)
        and not msg.get(_LAST4_SYSTEM_MARKER)
    )


def _ensure_dynamic_region(body: dict, marker: str | None = None) -> dict:
    """
    Ensure one dedicated dynamic system message for the requested prompt slot.

    位置：所有连续 system 消息之后、第一条非 system 消息之前。
    返回 body（可能 deepcopy 过）。
    """
    messages = body.get("messages") or []
    for msg in messages:
        if marker and msg.get(marker):
            return body
        if marker is None and _is_persistent_dynamic_system(msg):
            return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    # 找第一条非 system 的位置
    insert_idx = 0
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() == "system":
            insert_idx = i + 1
        else:
            break
    dyn_msg = {"role": "system", "content": "", _DYNAMIC_SYSTEM_MARKER: True}
    if marker:
        dyn_msg[marker] = True
    messages.insert(insert_idx, dyn_msg)
    body["messages"] = messages
    return body


def _ensure_dynamic_system(body: dict) -> dict:
    return _ensure_dynamic_region(body)


def _append_to_dynamic_system(body: dict, text: str) -> dict:
    """Append normal runtime context to the persistent dynamic system."""
    body = _ensure_dynamic_system(body)
    for msg in body["messages"]:
        if _is_persistent_dynamic_system(msg):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def _append_to_temporary_dynamic_system(body: dict, text: str) -> dict:
    """Append context assigned to the temporary dynamic prompt slot."""
    body = _ensure_dynamic_region(body, _TEMPORARY_DYNAMIC_SYSTEM_MARKER)
    for msg in body["messages"]:
        if msg.get(_TEMPORARY_DYNAMIC_SYSTEM_MARKER):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def _append_to_last4_system(body: dict, text: str) -> dict:
    """Append the recent-conversation block after all temporary context."""
    body = _ensure_dynamic_region(body, _LAST4_SYSTEM_MARKER)
    for msg in body["messages"]:
        if msg.get(_LAST4_SYSTEM_MARKER):
            msg["content"] = (msg.get("content") or "") + text
            return body
    return body


def _append_to_static_system(body: dict, text: str) -> dict:
    """
    在固定静态区末尾插入一个独立 system block。

    不能把新内容追加到某条已有 system 的正文里，否则后续移动某个区域时
    会把不属于它的内容一起带走，破坏缓存断点和区域顺序。
    """
    messages = body.get("messages") or []
    if not messages:
        body = copy.deepcopy(body)
        body["messages"] = [{"role": "system", "content": text}]
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
        if _system_prompt_region(msg) != "static":
            insert_idx = i
            break
    messages.insert(insert_idx, {"role": "system", "content": text})
    return body


def _system_prompt_region(msg: dict) -> str:
    """Return the logical static/dynamic sub-block for one system message."""
    if msg.get(_VOICE_RULES_SYSTEM_MARKER):
        return "voice_rules"
    if msg.get(_FROZEN_TOOL_SUMMARY_SYSTEM_MARKER) or msg.get(_TOOL_RESULT_CACHE_SYSTEM_MARKER):
        return "frozen_tool_summary"
    if msg.get(_RECENT_TOOL_BATCH_SYSTEM_MARKER):
        return "recent_tool_batches"
    if msg.get(_HOT_TOOL_RESULT_SYSTEM_MARKER):
        return "hot_tool_results"
    if msg.get(_DRAFT_REMINDER_SYSTEM_MARKER):
        return "draft_reminder"
    if msg.get(_THINKING_RULES_SYSTEM_MARKER):
        return "thinking_rules"
    if msg.get(_ENTRY_STYLE_SYSTEM_MARKER):
        return "entry_style"
    if msg.get(_SUMITALK_REAL_MODE_SYSTEM_MARKER):
        return "sumitalk_mode"
    if msg.get(_DU_DAILY_SYSTEM_MARKER):
        return "du_daily"
    if msg.get(_SUMMARY_CACHE_SYSTEM_MARKER):
        return "summary_cache"
    if msg.get(_SUMMARY_RECENT_SYSTEM_MARKER):
        return "summary_recent"
    if msg.get(_LAST4_SYSTEM_MARKER):
        return "last4"
    if msg.get(_TEMPORARY_DYNAMIC_SYSTEM_MARKER) or msg.get(_PLAY_NOTE_SYSTEM_MARKER):
        return "temporary_dynamic"
    if msg.get(_DYNAMIC_SYSTEM_MARKER):
        return "dynamic"
    return "static"


def _merge_system_region(messages: list[dict], marker: str | None = None) -> dict | None:
    """Join one cache segment into a single system message at the final boundary."""
    contents = [
        msg.get("content")
        for msg in messages
        if isinstance(msg, dict) and msg.get("content") is not None
    ]
    contents = [content for content in contents if not (isinstance(content, str) and not content.strip())]
    if not contents:
        return None

    if all(isinstance(content, str) for content in contents):
        content = "\n\n".join(contents)
    else:
        content_blocks: list[dict] = []
        for content in contents:
            if isinstance(content, list):
                content_blocks.extend(copy.deepcopy(content))
            elif isinstance(content, str):
                content_blocks.append({"type": "text", "text": content})
            else:
                content_blocks.append({"type": "text", "text": str(content)})
        content = content_blocks

    merged = {"role": "system", "content": content}
    if marker:
        merged[marker] = True
    return merged


def _upsert_summary_cache_system(body: dict, stable_text: str, recent_texts: list[str] | str | None = None) -> dict:
    """
    把近期记忆放在静态 system 之后、动态 system 之前。
    stable_text 只包含「更早/稍早」，Claude proxy 在它末尾放缓存断点；
    每个 recent chunk 单独成块，保证尾部 append 时旧块逐字节不变。
    """
    if isinstance(recent_texts, str):
        recent_blocks = [recent_texts] if recent_texts.strip() else []
    else:
        recent_blocks = [str(text) for text in (recent_texts or []) if str(text or "").strip()]
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    if not messages:
        body["messages"] = []
        if stable_text:
            body["messages"].append({"role": "system", "content": stable_text, _SUMMARY_CACHE_SYSTEM_MARKER: True})
        body["messages"].extend(
            {"role": "system", "content": text, _SUMMARY_RECENT_SYSTEM_MARKER: True}
            for text in recent_blocks
        )
        return body

    messages = [
        msg for msg in messages
        if not (msg.get(_SUMMARY_CACHE_SYSTEM_MARKER) or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER))
    ]
    first_dynamic_idx = -1
    first_non_system_idx = len(messages)
    for i, msg in enumerate(messages):
        if (msg.get("role") or "").lower() != "system":
            first_non_system_idx = i
            break
        if first_dynamic_idx == -1 and msg.get(_DYNAMIC_SYSTEM_MARKER):
            first_dynamic_idx = i

    insert_idx = first_dynamic_idx if first_dynamic_idx >= 0 else first_non_system_idx
    new_blocks = []
    if stable_text:
        new_blocks.append({"role": "system", "content": stable_text, _SUMMARY_CACHE_SYSTEM_MARKER: True})
    new_blocks.extend(
        {"role": "system", "content": text, _SUMMARY_RECENT_SYSTEM_MARKER: True}
        for text in recent_blocks
    )
    messages[insert_idx:insert_idx] = new_blocks
    body["messages"] = messages
    return body
