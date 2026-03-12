# 两条数据流用的清洗逻辑
# 发给渡：只清 Rikka 预设 + 表情包→文字
# 存 R2：完整清洗 = 清 Rikka + 表情包→文字 + 图片→占位符（描述在 images/）
import copy
import json
import re
from pathlib import Path

from config import RIKKA_PRESET_PATTERNS, EMOJI_MAPPING_FILE

# 表情包格式：(表情包:code) → [表情:描述] 或 [表情]（对照表在 data/emoji_mapping.json，老婆可编辑）
EMOJI_PACK_PATTERN = re.compile(r"\(表情包:([^)]*)\)", re.IGNORECASE)


def _load_emoji_mapping() -> dict:
    """从 data/emoji_mapping.json 读取对照表，无文件或 key 为 _comment 的忽略。"""
    if not EMOJI_MAPPING_FILE.exists():
        return {}
    try:
        with open(EMOJI_MAPPING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in (data or {}).items() if isinstance(v, str) and k != "_comment"}
    except Exception:
        return {}


def replace_emoji_with_text(text: str) -> str:
    """(表情包:code) → [表情:描述]（对照表有则用描述，无则 [表情]）。"""
    if not text or not isinstance(text, str):
        return text
    mapping = _load_emoji_mapping()

    def _repl(match):
        code = match.group(1).strip()
        desc = mapping.get(code) or mapping.get(code.upper()) or mapping.get(code.lower())
        return f"[表情:{desc}]" if desc else "[表情]"

    return EMOJI_PACK_PATTERN.sub(_repl, text)


def clean_rikka_from_text(text: str) -> str:
    """从文本中移除 Rikka 等前端的无用预设（配置的短语）。"""
    if not text or not isinstance(text, str):
        return text
    out = text
    for phrase in RIKKA_PRESET_PATTERNS:
        if phrase:
            out = out.replace(phrase, "")
    return out.strip()


def apply_text_cleaning_for_forward(text: str) -> str:
    """发给渡用的文本清洗：Rikka + 表情包→文字。"""
    if not text:
        return text
    t = replace_emoji_with_text(text)
    t = clean_rikka_from_text(t)
    return t


def apply_text_cleaning_for_r2(text: str) -> str:
    """存 R2 用的文本清洗：与发给渡相同（Rikka + 表情包→文字）。"""
    return apply_text_cleaning_for_forward(text)


def clean_message_content_for_forward(content) -> str | list:
    """
    对单条 message 的 content 做「发给渡」清洗。
    content 可能是 str 或 list（多模态）。图片保留原样。
    """
    if content is None:
        return content
    if isinstance(content, str):
        return apply_text_cleaning_for_forward(content)
    if isinstance(content, list):
        out = []
        for part in content:
            if not isinstance(part, dict):
                out.append(part)
                continue
            if part.get("type") == "text":
                # 兼容 part 用 text 或 content 存文案（如部分前端/API）
                raw = part.get("text") or part.get("content") or ""
                out.append({"type": "text", "text": apply_text_cleaning_for_forward(raw)})
            else:
                out.append(part)  # 图片等保留
        return out
    return content


def clean_message_for_r2(msg: dict) -> dict:
    """
    对单条 message 做「存 R2」完整清洗：Rikka + 表情包→文字 + 图片→占位符。
    返回新 message，不修改原对象。
    """
    msg = copy.deepcopy(msg)
    content = msg.get("content")
    if content is None:
        return msg
    if isinstance(content, str):
        msg["content"] = apply_text_cleaning_for_r2(content)
        return msg
    if isinstance(content, list):
        out = []
        for part in content:
            if not isinstance(part, dict):
                out.append(part)
                continue
            if part.get("type") == "text":
                raw = part.get("text") or part.get("content") or ""
                out.append({"type": "text", "text": apply_text_cleaning_for_r2(raw)})
            elif part.get("type") in ("image_url", "image"):
                out.append({"type": "text", "text": "[图片]"})
            else:
                out.append(part)
        msg["content"] = out
        return msg
    return msg


def build_round_cleaned_for_r2(user_msg: dict, assistant_msg: dict) -> list:
    """
    构建「存 R2」用的一轮：老婆问 + 渡的回复，完整清洗（Rikka、表情包→文字、图片→[图片]）。
    整轮作废时不调用，故这里只处理通过初筛的轮。
    """
    return [
        clean_message_for_r2(user_msg),
        clean_message_for_r2(assistant_msg),
    ]
