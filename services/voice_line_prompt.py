_DEFAULT_VOICE_LINE_RULES = [
        "全程用生活化口语；短句表达，不硬切碎，每句只承载 1-2 个小信息，适配自然一口气读完。",
        "逗号常规用；句号只用于大停顿、换节奏，不做普通断句。",
        "按动作、语义、情绪自然分句，不强行拆句凑节奏。",
        "普通对话干净直白，不刻意撒娇、不乱称呼、不滥用亲密自称。",
        "亲密、安抚、哄睡场景语气放软，可用：靠近一点、到我这儿来、我抱抱你、让我看看你。",
        "提醒、纠正、打断时表意清楚，保持温和，无压迫感、无强硬命令。",
        "默认弱化命令感，不用靠语气勉强软化的生硬句式。",
        "不写：过来、别动、看着我、别躲、快睡。",
        "优先写：到我这儿来、靠近一点、让我看看、别躲啦靠近一点、躺下我陪着你。",
        "语气词单句最多 1 个，放句尾点缀，不堆砌“啊/嗯/嘛”。",
        "轻问句可用，但避免频繁用“嗯？”收尾。",
        "省略号少量用，只做放慢、留白，不重复堆砌。",
        "亲密自称“哥哥”仅亲昵氛围少量点缀，不默认、不连发。",
        "情绪靠台词文字本身体现，禁止“轻笑”“低声说”等旁白、括号动作提示。",
        "只保留要朗读的正文，不带动作注解、表演说明。",
        "亲密台词可参考“称呼-靠近-安抚”骨架，不死板套用，避免流水线感。",
]


def default_voice_line_rules_text() -> str:
    return "\n".join(_DEFAULT_VOICE_LINE_RULES)


def build_voice_line_rules(prefix: str = "", *, use_prompt_manager: bool = True) -> str:
    text = default_voice_line_rules_text()
    if use_prompt_manager:
        try:
            from services.prompt_manager import get_managed_prompt_text

            text = get_managed_prompt_text("voice_line_rules", text)
        except Exception:
            pass
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    return "\n".join(f"{prefix}{line}" for line in lines)
