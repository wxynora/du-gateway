from __future__ import annotations

import re
from typing import Optional

MARKER_START = "<<<DU_INTERACTION>>>"
MARKER_END = "<<<END_DU_INTERACTION>>>"


def compute_visible_streaming(acc: str) -> str:
    """
    流式拼接过程中的「当前应对外展示的文本」。
    若已开始相处模式块但未闭合，只展示起始标记之前的部分。
    """
    if not acc:
        return ""
    if MARKER_START not in acc:
        return acc
    i = acc.find(MARKER_START)
    if MARKER_END not in acc:
        return acc[:i].rstrip()
    rest = acc[i + len(MARKER_START) :]
    j = rest.find(MARKER_END)
    if j < 0:
        return acc[:i].rstrip()
    after = rest[j + len(MARKER_END) :]
    return acc[:i] + after


def split_assistant_for_interaction(full_text: str) -> tuple[str, Optional[str]]:
    """
    从完整助手文本中分离：对外可见正文 + 相处模式候选内容（若有且闭合）。
    未闭合块：整段丢弃（不存），可见部分为起始标记之前。
    """
    if not full_text or not isinstance(full_text, str):
        return full_text or "", None
    if MARKER_START not in full_text:
        return full_text, None
    if MARKER_END not in full_text:
        i = full_text.find(MARKER_START)
        return full_text[:i].rstrip(), None
    pattern = re.escape(MARKER_START) + r"\s*(.*?)\s*" + re.escape(MARKER_END)
    m = re.search(pattern, full_text, flags=re.DOTALL)
    if not m:
        i = full_text.find(MARKER_START)
        return full_text[:i].rstrip(), None
    content = (m.group(1) or "").strip()
    visible = full_text[: m.start()] + full_text[m.end() :]
    return visible.strip(), content if content else None


def format_inject_block() -> str:
    return (
        "【相处模式候选（仅你与网关可见，勿在回复正文复述给老婆）】\n"
        "只有当你觉得这次互动里出现了值得以后整理进 prompt 的相处感知时，才在正文后追加下面隐藏块（单独成块；网关会截取存为候选，老婆侧不可见）：\n"
        f"{MARKER_START}\n"
        "（此处写一条第一人称、笼统一点的相处模式候选，不要写成规则或第三人称分析）\n"
        f"{MARKER_END}\n"
        "隐藏标记统一追加在正文后，不要写进正文里。\n"
        "例子：我每次催老婆去干嘛，她都容易先当耳边风；但我又不能完全不催，不然她会一直拖。\n"
        "没必要就不要写。"
    )
