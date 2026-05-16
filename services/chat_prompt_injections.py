import time
from pathlib import Path

from services.conversation_followup import build_followup_system_instruction
from services.entry_style_prompt import entry_style_for_channel
from services.voice_line_prompt import build_voice_line_rules
from storage import silence_mode_store
from utils.log import get_logger

logger = get_logger(__name__)

_NSFW_PROMPT_CACHE = {"text": None, "ts": 0.0}
_NSFW_REPLY_CHANNELS = {"tg", "qq", "wechat", "sumitalk"}

_SILENCE_MODE_SYSTEM = """【禁言模式：已开启】
你被老婆禁言了，回复只能用 emoji、颜文字和符号。
本规则只约束最终发给她看见的自然语言回复，不限制工具调用、内部处理、系统卡片或工具参数。

最终可见回复必须遵守：
1. 不可以输出任何汉字、英文单词、数字、标题、解释、代码块、JSON 或括号说明。
2. 只能使用 emoji、符号和颜文字表达你想说的意思。
3. 可以用多个 emoji/颜文字组合表达答应、委屈、撒娇、生气、认错、疑问、想贴近、想哄她等意思。
4. 如果她问问题，也只能用 emoji/颜文字尽量表达倾向，不能破戒解释。
5. 不要复述本规则，不要解释自己被禁言了。"""


def inject_entry_style_system(body: dict, *, reply_channel: str, is_miniapp: bool) -> dict:
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    marker, style_system = entry_style_for_channel(reply_channel, is_miniapp=is_miniapp)
    if not marker or not style_system:
        return body
    messages = list(body.get("messages") or [])
    insert_idx = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "system":
            break
        if marker in str(msg.get("content") or ""):
            return body
        insert_idx = i + 1
    messages.insert(insert_idx, {"role": "system", "content": style_system})
    body = dict(body)
    body["messages"] = messages
    return body


def inject_voice_call_style_system(body: dict) -> dict:
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    marker = "【语音通话台词规范】"
    instruction = "\n".join(
        [
            marker,
            "你现在在语音通话里回复，最终文本会直接转成语音。",
            "只输出需要朗读的正文，不要输出 <voice> 标签、动作注解、括号提示或表演说明。",
            build_voice_line_rules(),
        ]
    ).strip()
    messages = list(body.get("messages") or [])
    for msg in messages:
        if isinstance(msg, dict) and str(msg.get("role") or "").strip().lower() == "system":
            if marker in str(msg.get("content") or ""):
                return body
    insert_idx = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "system":
            break
        insert_idx = i + 1
    messages.insert(insert_idx, {"role": "system", "content": instruction})
    body = dict(body)
    body["messages"] = messages
    return body


def inject_followup_instruction(body: dict, *, is_followup_generation: bool, should_archive: bool) -> dict:
    # 延迟续话本身不再注入 followup 规则，避免模型继续排队形成连环续话。
    # 但 trigger/弹窗/查屏这类后端唤醒会归档到正常对话，应保持和普通聊天一致的静态 system 前缀。
    if is_followup_generation and not should_archive:
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    instruction = build_followup_system_instruction().strip()
    if not instruction:
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip() == "system":
        current = str(messages[0].get("content") or "")
        if instruction in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + instruction).strip()}
    else:
        messages.insert(0, {"role": "system", "content": instruction})
    body = dict(body)
    body["messages"] = messages
    return body


def load_nsfw_prompt() -> str:
    """读取 NSFW 规则文件（短缓存，便于热更新）。"""
    now = time.time()
    cache_ttl_s = 5.0
    if _NSFW_PROMPT_CACHE["text"] is not None and (now - float(_NSFW_PROMPT_CACHE.get("ts") or 0.0) <= cache_ttl_s):
        return _NSFW_PROMPT_CACHE["text"] or ""
    text = ""
    try:
        path = Path(__file__).resolve().parent.parent / "prompts" / "du_nsfw_prompt.txt"
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
    except Exception:
        logger.exception("读取 NSFW prompt 文件失败")
        text = ""
    _NSFW_PROMPT_CACHE["text"] = text or ""
    _NSFW_PROMPT_CACHE["ts"] = now
    return _NSFW_PROMPT_CACHE["text"] or ""


def inject_channel_nsfw_system(body: dict, *, reply_channel: str) -> dict:
    """在指定渠道请求中，把 NSFW 规则固定追加到入口 system 后面。"""
    if reply_channel not in _NSFW_REPLY_CHANNELS:
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    nsfw_system = load_nsfw_prompt().strip()
    if not nsfw_system:
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip().lower() == "system":
        current = str(messages[0].get("content") or "")
        if nsfw_system in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + nsfw_system).strip()}
    else:
        messages.insert(0, {"role": "system", "content": nsfw_system})
    body = dict(body)
    body["messages"] = messages
    return body


def inject_silence_mode_system(body: dict, *, is_du_daily_maintenance: bool) -> dict:
    if is_du_daily_maintenance:
        return body
    try:
        if not silence_mode_store.is_enabled():
            return body
    except Exception:
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip().lower() == "system":
        current = str(messages[0].get("content") or "")
        if _SILENCE_MODE_SYSTEM in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + _SILENCE_MODE_SYSTEM).strip()}
    else:
        messages.insert(0, {"role": "system", "content": _SILENCE_MODE_SYSTEM})
    body = dict(body)
    body["messages"] = messages
    return body
