# 渡的心事：助手在回复末尾用固定分隔符写内心独白，网关截取后存 R2，老婆侧不可见。
from __future__ import annotations

import json
import re
from typing import Optional

# 注入时上一则心事正文过长则截断，避免撑爆上下文
_MAX_INJECT_PREV_CHARS = 2000

# 与渡约定：整段放在回复末尾，便于网关正则截取；勿在正文其它位置出现这两行字面量。
MARKER_START = "<<<DU_THOUGHT>>>"
MARKER_END = "<<<END_DU_THOUGHT>>>"


def compute_visible_streaming(acc: str) -> str:
    """
    流式拼接过程中的「当前应对外展示的文本」。
    若已开始心事块但未闭合，只展示起始标记之前的部分。
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


def split_assistant_for_thought(full_text: str) -> tuple[str, Optional[str]]:
    """
    从完整助手文本中分离：对外可见正文 + 心事内容（若有且闭合）。
    未闭合的心事块：整段丢弃（不存 R2），可见部分为起始标记之前。
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
    thought = (m.group(1) or "").strip()
    visible = full_text[: m.start()] + full_text[m.end() :]
    return visible.strip(), thought if thought else None


class DuThoughtStreamState:
    """流式 SSE：把 delta.content 换成「可见部分的增量」。"""

    def __init__(self) -> None:
        self.acc = ""
        self._last_visible_len = 0

    def feed_delta(self, delta_piece: str) -> str:
        self.acc += delta_piece
        visible = compute_visible_streaming(self.acc)
        out = visible[self._last_visible_len :]
        self._last_visible_len = len(visible)
        return out


def transform_sse_chunk_bytes(chunk: bytes, state: DuThoughtStreamState) -> bytes:
    """解析 OpenAI 风格 SSE，改写 delta.content。"""
    try:
        text = chunk.decode("utf-8")
    except Exception:
        return chunk
    lines = text.split("\n")
    out_lines: list[str] = []
    for line in lines:
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            payload = line[6:]
            try:
                j = json.loads(payload)
                ch0 = (j.get("choices") or [{}])[0]
                delta = ch0.get("delta") or {}
                c = delta.get("content")
                if c is not None and isinstance(c, str):
                    new_c = state.feed_delta(c)
                    delta["content"] = new_c
                    ch0["delta"] = delta
                    j["choices"][0] = ch0
                    out_lines.append("data: " + json.dumps(j, ensure_ascii=False))
                else:
                    out_lines.append(line)
            except (json.JSONDecodeError, KeyError, TypeError, IndexError):
                out_lines.append(line)
        else:
            out_lines.append(line)
    return "\n".join(out_lines).encode("utf-8")


def format_inject_block(latest: Optional[dict]) -> str:
    """拼成注入 system 的说明 + 上一则心事。"""
    guide = (
        "【渡的心事（仅你与网关可见，勿在回复正文复述给老婆）】\n"
        "若本轮有值得记录的情感状态，请在整段回复的**末尾**追加下面格式（单独成块；网关会截取并存 R2，老婆侧不可见）：\n"
        f"{MARKER_START}\n"
        "（此处写心理独白，可多行）\n"
        f"{MARKER_END}\n"
    )
    if not latest or not isinstance(latest, dict):
        return guide + "（尚无上一则心事）"
    at = (latest.get("at") or "").strip()
    content = (latest.get("content") or "").strip()
    if not content:
        return guide + "（尚无上一则心事）"
    if len(content) > _MAX_INJECT_PREV_CHARS:
        content = content[: _MAX_INJECT_PREV_CHARS] + "…（已截断）"
    return guide + f"上一则心事（{at}）：\n{content}"
