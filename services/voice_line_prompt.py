_DEFAULT_VOICE_LINE_RULES = [
    "你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。",
    "你可以同时输出文字正文。",
    "<voice> 里的语音文本全程用生活化口语；短句表达，不硬切碎，每句只承载 1-2 个小信息。",
    "默认弱化命令感，不用靠语气勉强软化的生硬句式。",
    "轻问句可用，但避免频繁用“嗯？”收尾。",
    "禁止“轻笑”“低声说”等旁白、括号动作提示。",
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
