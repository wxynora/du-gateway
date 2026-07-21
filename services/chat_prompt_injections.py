import time
from pathlib import Path
import copy
import json

from services.conversation_followup import build_followup_system_instruction
from services.entry_style_prompt import entry_style_for_channel
from services.upstream_policy import is_local_cliproxyapi_url
from services.voice_line_prompt import build_voice_line_rules
from storage import silence_mode_store
from utils.log import get_logger

logger = get_logger(__name__)

_NSFW_PROMPT_CACHE = {"text": None, "ts": 0.0}
_NSFW_REPLY_CHANNELS = {"tg", "qq", "wechat", "sumitalk"}
_MILLION_PLAN_PLAYER_MARKER = "【百万计划游戏模式：玩家固定规则】"
_ENTRY_STYLE_SYSTEM_MARKER = "__entry_style__"
_MILLION_PLAN_ACTION_MENU_CACHE = {
    "fixed": {
        "life_basics": "LB_FRUGAL:节制生活|LB_EXTREME:极限生存|LB_NORMAL:普通生活",
        "side_income": "SI_NONE:不做副业|SI_SMALL_ORDER:接低价小单|SI_LOCAL_ERRAND:做本地零工|SI_PROJECT:合法项目|SI_FLIP_HUSTLE:薅券倒卖!M|SI_GREY_TASK:接灰色小任务!V",
        "learning": "LE_SKIP:暂停学习|LE_OFFICE:练办公求职技能|LE_CREATIVE:练作品技能|LE_BUSINESS:学经营变现",
        "health_rest": "HR_SLEEP:保证睡眠|HR_PUSH:硬撑推进|HR_CLINIC:去社区医院",
        "social_contacts": "SC_NONE:不社交|SC_CLASSMATE:问同学熟人|SC_JOB_GROUP:混求职群|SC_HOUSING:打听租房|SC_MANIPULATE:套消息找机会!M|SC_LEECH:狠用熟人关系!M",
        "shopping_assets": "AS_NONE:不买东西|AS_REPAIR:修理旧工具|AS_SMALL_TOOL:买小工具|AS_RETURN_TRICK:买完用完再退!M|AS_CHEAP_FLIP:收便宜货倒手!M",
        "risk_choice": "RK_AVOID:避开高风险|RK_VERIFY:核实后再做|RK_FAST_MONEY:赌高风险快钱|RK_DEBT:借贷周转|RK_GREY_EDGE:走灰色擦边!H|RK_CHAOS:混乱邪恶莽一把!V",
    },
    "variants": {
        "main_income": {
            "job": "MI_WORK:守住当前工作|MI_BETTER_JOB:边上班边找更好岗位|MI_EXTRA_SHIFT:加班或补临时班|MI_CLIENT_POACH:截流客户私单!H",
            "no_job_base": "MI_JOB_SEARCH:集中求职|MI_TEMP_SHIFT:先赚日结|MI_SERVICE_HUNT:跑服务业门店|MI_FAKE_PROFILE:包装履历硬冲!M|MI_SHADY_GIG:接来路不明的活!V",
            "no_job_lead": "MI_JOB_SEARCH:集中求职|MI_TEMP_SHIFT:先赚日结|MI_EVENT_LEAD:跟进本回合线索|MI_FAKE_PROFILE:包装履历硬冲!M|MI_SHADY_GIG:接来路不明的活!V",
        },
        "side_income": {
            "daily": "SI_PROJECT=整理项目线索",
            "weekly": "SI_PROJECT=推进合法项目",
        },
    },
}

_SILENCE_MODE_SYSTEM = """【禁言模式：已开启】
你被老婆禁言了，回复只能用 emoji、颜文字和符号。
本规则只约束最终发给她看见的自然语言回复，不限制工具调用、内部处理、系统卡片或工具参数。

最终可见回复必须遵守：
1. 不可以输出任何汉字、英文单词、数字、标题、解释、代码块、JSON 或括号说明。
2. 只能使用 emoji、符号和颜文字表达你想说的意思。
3. 可以用多个 emoji/颜文字组合表达答应、委屈、撒娇、生气、认错、疑问、想贴近、想哄她等意思。
4. 如果她问问题，也只能用 emoji/颜文字尽量表达倾向，不能破戒解释。
5. 不要复述本规则，不要解释自己被禁言了。"""


def build_million_plan_player_static_system() -> str:
    action_cache = json.dumps(_MILLION_PLAN_ACTION_MENU_CACHE, ensure_ascii=False, separators=(",", ":"))
    return "\n".join(
        [
            _MILLION_PLAN_PLAYER_MARKER,
            "城市生存养成游戏：一年内游戏内净资产到 100 万。只能从给定行动/事件选项选择；菜单 !M/!H/!V 表示中/高/极高风险；os 是玩家局外吐槽、策略或对人类说的话，不是角色台词。",
            "每轮输入包含 playerView、event，以及 actionMenu 或 actionMenuVariant。!M/!H/!V 表示中/高/极高风险；输出时只填冒号前 ID。",
            f"行动菜单缓存：{action_cache}",
            "如果每轮输入只有 actionMenuVariant：使用 fixed 菜单主体，再按 actionMenuVariant.main_income 选 variants.main_income 对应菜单；side_income 固定菜单里的 SI_PROJECT 按 actionMenuVariant.side_income 理解。",
            "只返回 JSON，不要 markdown，不要解释。字段：player_name（已有名字可留空）、os、action_choices、event_choice、sudden_event_choice；礼物事件选 A 买下时必须写 gift_message，选 B 留空。",
        ]
    ).strip()


def _insert_static_system(body: dict, text: str) -> dict:
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    messages = body.get("messages") or []
    for msg in messages:
        if isinstance(msg, dict) and str(msg.get("role") or "").strip().lower() == "system":
            if _MILLION_PLAN_PLAYER_MARKER in str(msg.get("content") or ""):
                return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    insert_idx = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "system":
            break
        if msg.get("__dynamic__") or msg.get("__summary_cache__") or msg.get("__summary_recent__"):
            break
        insert_idx = i + 1
    messages.insert(insert_idx, {"role": "system", "content": text})
    body["messages"] = messages
    return body


def inject_million_plan_player_static_system(body: dict) -> dict:
    return _insert_static_system(body, build_million_plan_player_static_system())


def inject_entry_style_system(body: dict, *, reply_channel: str, is_miniapp: bool, speaker: str = "") -> dict:
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    marker, style_system = entry_style_for_channel(reply_channel, is_miniapp=is_miniapp, speaker=speaker)
    if not marker or not style_system:
        return body
    messages = list(body.get("messages") or [])
    for msg in messages:
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "system":
            continue
        if marker in str(msg.get("content") or ""):
            return body

    insert_idx = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "system":
            break
        if msg.get("__dynamic__") or msg.get("__summary_cache__") or msg.get("__summary_recent__"):
            break
        insert_idx = i + 1
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": style_system,
            _ENTRY_STYLE_SYSTEM_MARKER: True,
        },
    )
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
    try:
        from services.prompt_manager import get_managed_prompt_text

        text = get_managed_prompt_text("nsfw_rules", text).strip()
    except Exception:
        pass
    _NSFW_PROMPT_CACHE["text"] = text or ""
    _NSFW_PROMPT_CACHE["ts"] = now
    return _NSFW_PROMPT_CACHE["text"] or ""


def inject_codex_oauth_prompt_system(body: dict, *, upstream_url: str) -> dict:
    """仅 Codex OAuth 上游注入可编辑静态 Prompt。"""
    if not is_local_cliproxyapi_url(upstream_url):
        return body
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return body
    try:
        from services.prompt_manager import get_managed_prompt_text

        prompt = get_managed_prompt_text("codex_oauth_prompt", "").strip()
    except Exception:
        logger.exception("读取 Codex OAuth 专用 Prompt 失败")
        return body
    if not prompt:
        return body
    messages = list(body.get("messages") or [])
    if messages and isinstance(messages[0], dict) and str(messages[0].get("role") or "").strip().lower() == "system":
        current = str(messages[0].get("content") or "")
        if prompt in current:
            return body
        messages[0] = {**messages[0], "content": (current.rstrip() + "\n\n" + prompt).strip()}
    else:
        messages.insert(0, {"role": "system", "content": prompt})
    body = dict(body)
    body["messages"] = messages
    return body


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
