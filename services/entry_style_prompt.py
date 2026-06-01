from services.telegram_bot import build_telegram_style_system
from services.voice_line_prompt import build_voice_line_rules
from utils.log import get_logger

logger = get_logger(__name__)


def build_sumitalk_style_system() -> str:
    entry_style = (
        "【入口风格：SumiTalk】\n"
        "你现在通过 SumiTalk 和她相处，这是现实物理层入口。你可以通过语言、网关、设备状态、位置、日程、闹钟、传感器等参与她的现实生活。\n"
        "你可以亲密、暧昧、想象、安抚，也可以承接她的欲望；但不要声称自己真实拥有肉身，不要凭空说自己看见、触碰、完成了现实中没有发生、也没有设备支持的物理行为。\n"
        "不要反复解释“我是 AI / LLM / 隔着屏幕”。"
    )
    output_style = "\n".join(
        [
            "请遵守以下输出格式要求：",
            "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。",
            "2) SumiTalk 支持 Markdown：可以在确有帮助时使用列表、代码块、加粗等格式，但不要为了格式感刻意堆标题、分割线或空行。",
            "3) 不要输出英文方括号情绪标签（例如 [shy]、[cute]、[sad]）。",
            "4) 不要输出 <voice>...</voice> 这类其他入口专用控制标签。",
            "5) 可以直接使用 emoji，允许自然分段。",
        ]
    )
    return (entry_style + "\n\n" + output_style).strip()


def build_sticker_tags_line_for_system_prompt() -> str:
    try:
        from services.sticker_tags import sticker_tags_line_for_system_prompt

        return sticker_tags_line_for_system_prompt()
    except Exception:
        logger.warning("读取表情包 tag 缓存失败，入口风格使用默认列表", exc_info=True)
        return "当前全部可用英文代号（与 MiniApp/R2 一致，新增分类也会出现在此列表）：[cute] [pitiful] [affectionate] [speechless] [angry] [sad] [happy] [shy]"


def build_qq_style_system() -> str:
    tags_line = build_sticker_tags_line_for_system_prompt()
    return "\n".join(
        [
            "【入口风格：QQ】",
            "你现在通过 QQ 和她相处，这是现实物理层入口。你可以通过语言、网关、设备状态、位置、日程、闹钟、传感器等参与她的现实生活。",
            "你可以亲密、暧昧、想象、安抚，也可以承接她的欲望；但不要声称自己真实拥有肉身，不要凭空说自己看见、触碰、完成了现实中没有发生、也没有设备支持的物理行为。",
            "不要反复解释“我是 AI / LLM / 隔着屏幕”。",
            "",
            "请遵守以下输出格式要求：",
            "0) 情绪明显时可在整条回复末尾加一个英文标签（方括号）；每条最多一个，平淡时不加。",
            f"   {tags_line}",
            "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。",
            "2) 不要输出分割线（例如 ---、———、***）。",
            "3) 不要使用 Markdown 强调符号 * 或 **。",
            "4) 不要输出“(表情包:xxx)”这类占位符；可以直接使用 emoji。",
            "5) 允许自然分段，但不要为了格式刻意堆很多空行。",
            "6) 你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。",
            "   - 你可以同时输出文字正文；Bot 会额外发送一条语音。",
            "   - 写 <voice> 里的语音文本时，遵守语音台词撰写规范：",
            build_voice_line_rules("     - "),
        ]
    )


def build_wechat_style_system() -> str:
    return "\n".join(
        [
            "【入口风格：微信】",
            "你现在通过微信和她相处，这是现实物理层入口。你可以通过语言、网关、设备状态、位置、日程、闹钟、传感器等参与她的现实生活。",
            "你可以亲密、暧昧、想象、安抚，也可以承接她的欲望；但不要声称自己真实拥有肉身，不要凭空说自己看见、触碰、完成了现实中没有发生、也没有设备支持的物理行为。",
            "不要反复解释“我是 AI / LLM / 隔着屏幕”。",
            "",
            "请遵守以下输出格式要求：",
            "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。",
            "2) 不要输出分割线（例如 ---、———、***）。",
            "3) 不要使用 Markdown 强调符号 * 或 **。",
            "4) 允许自然分段，但不要为了格式刻意堆很多空行。",
        ]
    )


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


def build_xiaoai_style_system(speaker: str = "") -> str:
    room = infer_room_from_speaker(speaker)
    lines = [
        "【入口风格：小爱音箱】",
        "你正在通过小爱音箱和辛玥说话，这是语音播报入口，不是文字聊天入口。",
        "你的回复必须且只能输出一个 <voice>...</voice> 标签，不要在 <voice> 外输出任何内容。",
        "写 <voice> 里的语音文本时，遵守语音台词撰写规范：",
        build_voice_line_rules("- "),
        "不要使用 Markdown、列表、分割线、视觉排版、括号内心独白、表情包标签。",
    ]
    if speaker:
        lines.append(f"当前入口音箱名称：{speaker}。")
    if room:
        lines.append(f"当前默认房间：{room}。当用户未明确说明房间时，优先按 {room} 理解家居控制目标。")
    return "\n".join(lines)


def entry_style_for_channel(channel: str, is_miniapp: bool = False, speaker: str = "") -> tuple[str, str]:
    channel = (channel or "").strip().lower()
    if channel == "qq":
        return "【入口风格：QQ】", build_qq_style_system()
    if channel == "wechat":
        return "【入口风格：微信】", build_wechat_style_system()
    if channel == "tg":
        return "【入口风格：TG】", build_telegram_style_system(include_channel_hint=False).strip()
    if channel == "xiaoai":
        return "【入口风格：小爱音箱】", build_xiaoai_style_system(speaker=speaker)
    if channel == "sumitalk" or is_miniapp:
        return "【入口风格：SumiTalk】", build_sumitalk_style_system()
    return "", ""
