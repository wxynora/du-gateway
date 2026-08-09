from __future__ import annotations

import re

from services.hidden_blocks import HiddenBlockParser


MARKER_START = "<<<DU_DRAFT>>>"
MARKER_END = "<<<END_DU_DRAFT>>>"
SHORT_MARKER = "[du:draft 草稿或内心独白]"
SCRATCHPAD_START = "<scratchpad>"
SCRATCHPAD_END = "</scratchpad>"

DRAFT_REMINDER_PROMPT = f"""<important_notice>
如果你在回复前或多轮工具调用途中输出分析、推理、计划、判断过程、自言自语、内心独白，或任何不准备直接发给小玥的文字，这些都属于思路草稿。
思路草稿必须从第一字起使用 {SCRATCHPAD_START}...{SCRATCHPAD_END} 完整包裹，不要先用普通文字写出草稿，再在最后补标签。
{SCRATCHPAD_START} 内的内容只会记入思维链日志的“草稿”块，不会作为正文发送。
真正要发给小玥的回复写在标签外；没有草稿时不要输出 {SCRATCHPAD_START}。
</important_notice>"""

_SCRATCHPAD_START_RE = re.compile(r"<\s*scratchpad\s*>", flags=re.IGNORECASE)
_SCRATCHPAD_END_RE = re.compile(r"<\s*/\s*scratchpad\s*>", flags=re.IGNORECASE)

_HIDDEN_BLOCK = HiddenBlockParser.for_markers(
    "DU_DRAFT",
    MARKER_START,
    MARKER_END,
    short_markers=("du:draft",),
)


def _normalize_scratchpad_blocks(text: str) -> str:
    """Translate XML scratchpads to the existing hidden-block parser contract."""
    if not text or not isinstance(text, str):
        return text or ""
    parts: list[str] = []
    cursor = 0
    while start := _SCRATCHPAD_START_RE.search(text, cursor):
        parts.append(text[cursor : start.start()])
        end = _SCRATCHPAD_END_RE.search(text, start.end())
        if end is None:
            parts.extend((MARKER_START, text[start.end() :], MARKER_END))
            cursor = len(text)
            break
        parts.extend((MARKER_START, text[start.end() : end.start()], MARKER_END))
        cursor = end.end()
    parts.append(text[cursor:])
    return "".join(parts)


def _strip_partial_scratchpad_start_suffix(text: str) -> str:
    """Do not stream a split `<scratchpad>` opening tag before it is complete."""
    if not text:
        return ""
    literal = SCRATCHPAD_START.lower()
    max_size = min(len(text), len(literal) - 1)
    for size in range(max_size, 0, -1):
        if literal.startswith(text[-size:].lower()):
            return text[:-size].rstrip()
    return text


def compute_visible_streaming(acc: str) -> str:
    normalized = _normalize_scratchpad_blocks(acc)
    visible = _HIDDEN_BLOCK.compute_visible_streaming(normalized)
    return _strip_partial_scratchpad_start_suffix(visible)


def split_all_assistant_drafts(full_text: str) -> tuple[str, list[str]]:
    return _HIDDEN_BLOCK.split_all(_normalize_scratchpad_blocks(full_text))


def strip_and_collect_assistant_drafts(full_text: str, draft_sink: list[str]) -> str:
    visible, drafts = split_all_assistant_drafts(full_text)
    if drafts:
        draft_sink.extend(drafts)
    return visible


def join_assistant_drafts(draft_parts: list[str]) -> str:
    return "\n\n".join(
        str(part or "").strip()
        for part in draft_parts
        if str(part or "").strip()
    )
