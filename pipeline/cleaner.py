# 两条数据流用的清洗逻辑
# 发给渡：只清 Rikka 预设，不替换表情包（让渡看到 (表情包:名字) 格式并按此输出）
# 存 R2：完整清洗 = 清 Rikka + 表情包→文字 + 图片→占位符（描述在 images/）
import copy
import json
import re
from pathlib import Path

from config import RIKKA_PRESET_PATTERNS, EMOJI_MAPPING_FILE

# 表情包格式：(表情包:xxx) → [表情:描述]（对照表在 data/emoji_mapping.json）
EMOJI_PACK_PATTERN = re.compile(r"\(表情包:([^)]*)\)", re.IGNORECASE)

# RikkaHub 时间工具 / time_reminder：整块删掉，不保留
_TIME_REMINDER_PATTERN = re.compile(r"<time_reminder>.*?</time_reminder>", re.DOTALL | re.IGNORECASE)


def _strip_rikkahub_time_artifacts(text: str) -> str:
    """
    去掉 RikkaHub 自带时间相关块，只保留我们自己的时间格式。
    - <time_reminder>Current time: ...</time_reminder>
    - 整段 JSON：{"year":2026,"month":3,"day":13,"weekday":"星期五",...,"time":"10:45:05"...}
    """
    if not text or not isinstance(text, str):
        return text
    out = text
    # 1. 去掉 <time_reminder>...</time_reminder>
    out = _TIME_REMINDER_PATTERN.sub("", out)
    # 2. 去掉 {"year":...} 这种 RikkaHub 时间 JSON（按括号匹配整段）
    idx = 0
    while True:
        start = out.find('{"year":', idx)
        if start == -1:
            start = out.find('{"year"', idx)
        if start == -1:
            break
        depth = 0
        end = -1
        for i in range(start, len(out)):
            if out[i] == "{":
                depth += 1
            elif out[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            out = out[:start] + out[end:]
            idx = start
        else:
            idx = start + 1
    return out.strip()


def _normalize_rikkahub_time_tool_result(text: str) -> str:
    """
    渡调用 RikkaHub 时间工具时，工具结果经过网关：只保留当前时间 HH:mm，去掉 year/month/weekday/date 等我们 system 里已有的，避免重复。
    """
    if not text or not isinstance(text, str):
        return text
    text = text.strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return text
        t = data.get("time") or data.get("time_hm")
        if not t:
            return text
        # "10:45:05" -> "10:45"；已是 "10:45" 则不变
        if isinstance(t, str) and ":" in t:
            parts = t.split(":")
            if len(parts) >= 2:
                return f"{parts[0]}:{parts[1]}"
            return t
        return text
    except (json.JSONDecodeError, TypeError):
        # 可能是 time_reminder 文本，尝试抽时间
        m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", text)
        if m:
            raw = m.group(1)
            parts = raw.split(":")
            return f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else raw
        return text


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


def apply_text_cleaning_for_forward(text: str, strip_rikkahub_time: bool = True) -> str:
    """发给渡用的文本清洗：可选去掉 RikkaHub 时间块/JSON + Rikka 预设，不替换表情包。渡自己调时间工具时 strip_rikkahub_time=False 保留结果。"""
    if not text:
        return text
    if strip_rikkahub_time:
        text = _strip_rikkahub_time_artifacts(text)
    return clean_rikka_from_text(text)


def apply_text_cleaning_for_r2(text: str, strip_rikkahub_time: bool = True) -> str:
    """存 R2 用的文本清洗：可选去掉 RikkaHub 时间块/JSON + Rikka 预设 + 表情包→文字。渡自己调时间工具时 strip_rikkahub_time=False 保留结果。"""
    if not text:
        return text
    if strip_rikkahub_time:
        text = _strip_rikkahub_time_artifacts(text)
    t = replace_emoji_with_text(text)
    return clean_rikka_from_text(t)


def clean_message_content_for_forward(content, msg: dict | None = None) -> str | list:
    """
    对单条 message 的 content 做「发给渡」清洗。
    content 可能是 str 或 list（多模态）。图片保留原样。
    msg 为当前消息；若 role 为 tool（渡自己调了 RikkaHub 时间工具的结果），只保留时间 HH:mm，去掉日期/星期等已有信息，避免重复。
    """
    strip_time = True
    if msg and (msg.get("role") or "").lower() == "tool":
        strip_time = False
    if content is None:
        return content
    if isinstance(content, str):
        if not strip_time:
            content = _normalize_rikkahub_time_tool_result(content)
        return apply_text_cleaning_for_forward(content, strip_rikkahub_time=strip_time)
    if isinstance(content, list):
        out = []
        for part in content:
            if not isinstance(part, dict):
                out.append(part)
                continue
            if part.get("type") == "text":
                raw = part.get("text") or part.get("content") or ""
                if not strip_time:
                    raw = _normalize_rikkahub_time_tool_result(raw)
                out.append({"type": "text", "text": apply_text_cleaning_for_forward(raw, strip_rikkahub_time=strip_time)})
            else:
                out.append(part)
        return out
    return content


def clean_message_for_r2(msg: dict) -> dict:
    """
    对单条 message 做「存 R2」完整清洗：Rikka + 表情包→文字 + 图片→占位符。
    若 role 为 tool（渡自己调时间工具的结果），只保留时间 HH:mm 再存。
    返回新 message，不修改原对象。
    """
    msg = copy.deepcopy(msg)
    strip_time = (msg.get("role") or "").lower() != "tool"
    content = msg.get("content")
    if content is None:
        return msg
    if isinstance(content, str):
        if not strip_time:
            content = _normalize_rikkahub_time_tool_result(content)
        msg["content"] = apply_text_cleaning_for_r2(content, strip_rikkahub_time=strip_time)
        return msg
    if isinstance(content, list):
        out = []
        for part in content:
            if not isinstance(part, dict):
                out.append(part)
                continue
            if part.get("type") == "text":
                raw = part.get("text") or part.get("content") or ""
                if not strip_time:
                    raw = _normalize_rikkahub_time_tool_result(raw)
                out.append({"type": "text", "text": apply_text_cleaning_for_r2(raw, strip_rikkahub_time=strip_time)})
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
