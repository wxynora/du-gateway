def _managed_entry_style(section_id: str, fallback: str, *, use_prompt_manager: bool) -> str:
    text = fallback.strip()
    if use_prompt_manager:
        try:
            from services.prompt_manager import get_managed_prompt_text

            text = get_managed_prompt_text(section_id, fallback).strip()
        except Exception:
            text = fallback.strip()
    return text


_ROOM_HINTS = (
    ("主卧", "主卧"),
    ("次卧", "次卧"),
    ("卧室", "卧室"),
    ("客厅", "客厅"),
    ("书房", "书房"),
    ("厨房", "厨房"),
    ("餐厅", "餐厅"),
    ("卫生间", "卫生间"),
    ("浴室", "浴室"),
    ("阳台", "阳台"),
    ("玄关", "玄关"),
    ("儿童房", "儿童房"),
)


def infer_room_from_speaker(speaker: str) -> str:
    text = str(speaker or "").strip()
    if not text:
        return ""
    for keyword, room in _ROOM_HINTS:
        if keyword in text:
            return room
    return ""


def build_xiaoai_style_system(speaker: str = "", *, use_prompt_manager: bool = True) -> str:
    room = infer_room_from_speaker(speaker)
    fallback = "\n".join(
        [
            "【入口风格：小爱音箱】",
            "你正在通过小爱音箱和辛玥说话，这是语音播报入口，不是文字聊天入口。",
            "你的回复必须且只能输出一个 <voice>...</voice> 标签，不要在 <voice> 外输出任何内容。",
            "<voice> 里的语音文本全程用生活化口语；短句表达，不硬切碎，每句只承载 1-2 个小信息。",
            "默认弱化命令感，不用靠语气勉强软化的生硬句式。",
            "轻问句可用，但避免频繁用“嗯？”收尾。",
            "禁止“轻笑”“低声说”等旁白、括号动作提示。",
            "不要使用 Markdown、列表、分割线、视觉排版、括号内心独白、表情包标签，也不要发送黄豆表情。",
        ]
    )
    text = _managed_entry_style("entry_style_xiaoai", fallback, use_prompt_manager=use_prompt_manager)
    lines = [text]
    if speaker:
        lines.append(f"当前入口音箱名称：{speaker}。")
    if room:
        lines.append(f"当前默认房间：{room}。当用户未明确说明房间时，优先按 {room} 理解家居控制目标。")
    return "\n".join(lines)


def entry_style_for_channel(channel: str, is_miniapp: bool = False, speaker: str = "") -> tuple[str, str]:
    channel = (channel or "").strip().lower()
    if channel == "xiaoai":
        return "【入口风格：小爱音箱】", build_xiaoai_style_system(speaker=speaker)
    if channel in {"qq", "tg", "sumitalk"} or is_miniapp:
        return "", ""
    return "", ""
