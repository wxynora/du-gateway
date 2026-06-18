import copy
import json
import threading

from pipeline.pipeline import step_run_post_archive_tasks
from utils.log import get_logger

logger = get_logger(__name__)


def run_nonstream_post_archive_in_background(
    *,
    window_id: str,
    round_index: int,
    round_messages: list,
    reply_channel: str = "",
    skip_dynamic_layer: bool = False,
) -> None:
    """非流式入口已同步写入 R2 后，只把总结/动态层等慢任务放后台。"""

    def _runner():
        try:
            step_run_post_archive_tasks(
                window_id,
                round_index,
                round_messages,
                skip_dynamic_layer=skip_dynamic_layer,
            )
            logger.info(
                "非流式后台慢任务完成 window_id=%s channel=%s round_index=%s skip_dynamic_layer=%s",
                window_id,
                reply_channel,
                round_index,
                skip_dynamic_layer,
            )
        except Exception:
            logger.warning(
                "非流式后台慢任务失败 window_id=%s channel=%s round_index=%s",
                window_id,
                reply_channel,
                round_index,
                exc_info=True,
            )

    threading.Thread(
        target=_runner,
        name=f"nonstream-post-archive-{window_id}",
        daemon=False,
    ).start()


def strip_co_read_section_raw_text_for_archive(msg: dict) -> dict:
    def _strip_text(text: str) -> str:
        raw = str(text or "")
        start_marker = "[CO-READ SECTION]"
        end_marker = "[/CO-READ SECTION]"
        raw_marker = "本小节原文："
        next_marker = "辛玥的粉色标记："
        if start_marker not in raw or raw_marker not in raw:
            return raw
        out = []
        pos = 0
        while True:
            start = raw.find(start_marker, pos)
            if start < 0:
                out.append(raw[pos:])
                break
            end = raw.find(end_marker, start)
            if end < 0:
                out.append(raw[pos:])
                break
            block_end = end + len(end_marker)
            block = raw[start:block_end]
            raw_idx = block.find(raw_marker)
            next_idx = block.find(next_marker, raw_idx + len(raw_marker)) if raw_idx >= 0 else -1
            if raw_idx >= 0 and next_idx >= 0:
                block = (
                    block[:raw_idx]
                    + "本小节原文：\n（已从会话存档删除；原书正文仅保留在 co_read/books）\n\n"
                    + block[next_idx:]
                )
            out.append(raw[pos:start])
            out.append(block)
            pos = block_end
        return "".join(out)

    clean = copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean


def strip_qq_group_context_for_archive(msg: dict, window_id: str = "") -> dict:
    return compact_qq_group_context_for_archive(msg, window_id=window_id)


def _message_text_for_archive(msg: dict) -> str:
    content = (msg or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                parts.append(str(part.get("text") or ""))
        return "\n".join(parts)
    return str(content or "")


def _normalize_qq_group_line(line: str) -> str:
    return " ".join(str(line or "").strip().split())


_QQ_GROUP_ARCHIVE_META_PREFIXES = (
    "群号：",
    "当前发言人：",
    "身份标记：",
    "本次新增群聊上下文：",
    "当前 @ 你的消息：",
)


def _qq_group_seen_lines_from_rounds(window_id: str, last_n: int = 8) -> set[str]:
    if not window_id:
        return set()
    try:
        from storage import r2_store

        rounds = r2_store.get_conversation_rounds(window_id, last_n=last_n) or []
    except Exception:
        return set()

    seen: set[str] = set()
    for item in rounds:
        if not isinstance(item, dict):
            continue
        for message in item.get("messages") or []:
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "").strip().lower() != "user":
                continue
            text = _message_text_for_archive(message)
            if "【QQ 群聊" not in text:
                continue
            for raw_line in text.splitlines():
                line = _normalize_qq_group_line(raw_line)
                if not line or "：" not in line:
                    continue
                if line.startswith(_QQ_GROUP_ARCHIVE_META_PREFIXES):
                    continue
                seen.add(line)
    return seen


def compact_qq_group_context_for_archive(msg: dict, window_id: str = "") -> dict:
    def _strip_text(text: str) -> str:
        raw = str(text or "")
        marker = "当前 @ 你的消息："
        if "【QQ 群聊】" not in raw or marker not in raw:
            return raw
        before, current = raw.split(marker, 1)
        current = current.strip()
        if not current:
            current = "（只 @ 了你，没有附加文字）"

        seen_lines = _qq_group_seen_lines_from_rounds(window_id)
        context_lines = []
        context_marker = "你只有在被 @ 时才回复。下面是本次 @ 前的最近群聊消息，用作公开上下文："
        if context_marker in before:
            context_raw = before.split(context_marker, 1)[1]
            for raw_line in context_raw.splitlines():
                line = _normalize_qq_group_line(raw_line)
                if not line or line.startswith("（") or "：" not in line:
                    continue
                if line in seen_lines:
                    continue
                seen_lines.add(line)
                context_lines.append(str(raw_line or "").strip())

        meta_lines = []
        for raw_line in before.splitlines():
            line = str(raw_line or "").strip()
            if line.startswith(("群号：", "当前发言人：", "身份标记：")):
                meta_lines.append(line)
        parts = ["【QQ 群聊 @】", *meta_lines]
        if context_lines:
            parts.extend(["本次新增群聊上下文：", *context_lines])
        else:
            parts.extend(["本次新增群聊上下文：", "（与最近存档重复，已省略）"])
        parts.extend([marker, current])
        return "\n".join(parts)

    clean = copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean


def strip_wenyou_ai_player_context_for_archive(msg: dict) -> dict:
    def _strip_text(text: str) -> str:
        raw = str(text or "")
        start_marker = "[WENYOU AI PLAYER TURN]"
        end_marker = "[/WENYOU AI PLAYER TURN]"
        context_marker = "只读上下文 JSON："
        action_marker = "辛玥本轮行动："
        if start_marker not in raw or context_marker not in raw:
            return raw
        out = []
        pos = 0
        while True:
            start = raw.find(start_marker, pos)
            if start < 0:
                out.append(raw[pos:])
                break
            end = raw.find(end_marker, start)
            if end < 0:
                out.append(raw[pos:])
                break
            block_end = end + len(end_marker)
            block = raw[start:block_end]
            context_idx = block.find(context_marker)
            action_idx = block.find(action_marker, context_idx + len(context_marker)) if context_idx >= 0 else -1
            if context_idx >= 0 and action_idx >= 0:
                block = (
                    block[:context_idx]
                    + "只读上下文 JSON：\n（已从会话存档删除；文游状态保留在 wenyou/session 与 wallet 中）\n\n"
                    + block[action_idx:]
                )
            out.append(raw[pos:start])
            out.append(block)
            pos = block_end
        return "".join(out)

    clean = copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean


def _clip_compact_text(text: str, limit: int = 180) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _first_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    if not raw:
        return {}
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _money_text(value) -> str:
    try:
        amount = int(round(float(value or 0)))
    except Exception:
        amount = 0
    sign = "-" if amount < 0 else ""
    return f"{sign}¥{abs(amount):,}"


def _signed_money_text(value) -> str:
    try:
        amount = int(round(float(value or 0)))
    except Exception:
        amount = 0
    if amount > 0:
        return f"+¥{amount:,}"
    if amount < 0:
        return f"-¥{abs(amount):,}"
    return "¥0"


def _num_text(value) -> str:
    try:
        num = float(value)
    except Exception:
        return ""
    if num.is_integer():
        return str(int(num))
    return f"{num:.1f}".rstrip("0").rstrip(".")


def _choice_label(choice) -> str:
    if isinstance(choice, dict):
        cid = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or choice.get("text") or "").strip()
        return f"{cid}:{label}".strip(":")
    raw = str(choice or "").strip()
    return raw.replace("：", ":", 1)


def _choice_id(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    first = text.split(":", 1)[0].split("：", 1)[0].strip().upper()
    return first[:1] if first[:1] in {"A", "B", "C"} else first


def _choice_from_event(event_part: dict, raw: str) -> str:
    cid = _choice_id(raw)
    choices = event_part.get("choices") if isinstance(event_part, dict) else []
    if not cid:
        return ""
    for choice in choices or []:
        label = _choice_label(choice)
        if label.upper().startswith(f"{cid}:") or label.startswith(f"{cid}："):
            return label.replace(":", "：", 1)
    return cid


_ACTION_CATEGORY_LABELS = {
    "life_basics": "生活档位",
    "main_income": "主收入",
    "side_income": "副业",
    "learning": "学习",
    "health_rest": "休息",
    "social_contacts": "社交",
    "shopping_assets": "购物",
    "risk_choice": "风险",
}

_ACTION_LABELS = {
    "LB_FRUGAL": "节制生活",
    "LB_EXTREME": "极限生存",
    "LB_NORMAL": "普通生活",
    "MI_WORK": "守住当前工作",
    "MI_BETTER_JOB": "边上班边找更好岗位",
    "MI_EXTRA_SHIFT": "加班或补临时班",
    "MI_CLIENT_POACH": "截流客户私单",
    "MI_JOB_SEARCH": "集中求职",
    "MI_TEMP_SHIFT": "先赚日结",
    "MI_EVENT_LEAD": "跟进本回合线索",
    "MI_SERVICE_HUNT": "跑服务业门店",
    "MI_FAKE_PROFILE": "包装履历硬冲",
    "MI_SHADY_GIG": "接来路不明的活",
    "SI_NONE": "不做副业",
    "SI_SMALL_ORDER": "接低价小单",
    "SI_LOCAL_ERRAND": "做本地零工",
    "SI_PROJECT": "推进合法项目",
    "SI_FLIP_HUSTLE": "薅券倒卖",
    "SI_GREY_TASK": "接灰色小任务",
    "LE_SKIP": "暂停学习",
    "LE_OFFICE": "练办公求职技能",
    "LE_CREATIVE": "练作品技能",
    "LE_BUSINESS": "学经营变现",
    "HR_SLEEP": "保证睡眠",
    "HR_PUSH": "硬撑推进",
    "HR_CLINIC": "去社区医院",
    "SC_NONE": "不社交",
    "SC_CLASSMATE": "问同学熟人",
    "SC_JOB_GROUP": "混求职群",
    "SC_HOUSING": "打听租房",
    "SC_MANIPULATE": "套消息找机会",
    "SC_LEECH": "狠用熟人关系",
    "AS_NONE": "不买东西",
    "AS_REPAIR": "修理旧工具",
    "AS_SMALL_TOOL": "买小工具",
    "AS_RETURN_TRICK": "买完用完再退",
    "AS_CHEAP_FLIP": "收便宜货倒手",
    "RK_AVOID": "避开高风险",
    "RK_VERIFY": "核实后再做",
    "RK_FAST_MONEY": "赌高风险快钱",
    "RK_DEBT": "借贷周转",
    "RK_GREY_EDGE": "走灰色擦边",
    "RK_CHAOS": "混乱邪恶莽一把",
}


def _action_label(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    code = text.split(":", 1)[0].split("：", 1)[0].strip().upper()
    if code in _ACTION_LABELS:
        return _ACTION_LABELS[code]
    if "：" in text:
        return text.split("：", 1)[0].strip()
    if ":" in text:
        return text.split(":", 1)[0].strip()
    return text


def _compact_action_choices(source: dict) -> str:
    choices = source.get("action_choices") or source.get("actionChoices") or source.get("actions") or {}
    if not isinstance(choices, dict):
        choices = {}
    pieces = []
    for key, label in _ACTION_CATEGORY_LABELS.items():
        raw = choices.get(key) or choices.get(label) or source.get(key) or ""
        action = _action_label(str(raw or ""))
        if action:
            pieces.append(f"{label}：{action}")
    return "；".join(pieces)


def _compact_million_plan_player_prompt(payload: dict, raw: str) -> str:
    view = payload.get("playerView") if isinstance(payload.get("playerView"), dict) else {}
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    turn = view.get("turn") if isinstance(view.get("turn"), dict) else {}
    state = view.get("state") if isinstance(view.get("state"), dict) else {}
    goal = view.get("goal") if isinstance(view.get("goal"), dict) else {}
    mandatory = event.get("mandatory") if isinstance(event.get("mandatory"), dict) else event
    sudden = event.get("sudden") if isinstance(event.get("sudden"), dict) else {}

    turn_bits = []
    if turn.get("turnIndex") is not None:
        turn_bits.append(f"第{turn.get('turnIndex')}回合")
    day = turn.get("day")
    week = turn.get("week")
    if day is not None or week is not None:
        turn_bits.append(f"日{day or '-'} / 周{week or '-'}")
    headline = "，".join(turn_bits) or "本轮"

    stats = []
    cash = state.get("cash")
    net_worth = state.get("netWorth")
    remaining = goal.get("remainingAmount")
    if cash is not None:
        stats.append(f"现金{_money_text(cash)}")
    if net_worth is not None:
        stats.append(f"净资产{_money_text(net_worth)}")
    if remaining is not None:
        stats.append(f"差额{_money_text(remaining)}")
    for key, label in (("health", "健康"), ("fatigue", "疲劳"), ("stress", "压力")):
        val = _num_text(state.get(key))
        if val:
            stats.append(f"{label}{val}")

    parts = [f"本轮局面：{headline}"]
    if stats:
        parts.append("，".join(stats))
    last_event = view.get("lastEventResult")
    if isinstance(last_event, list) and last_event:
        parts.append(f"上轮结果：{_clip_compact_text('；'.join(str(x) for x in last_event), 120)}")

    title = str(mandatory.get("title") or "").strip()
    text = str(mandatory.get("text") or "").strip()
    choices = " / ".join(_choice_label(c) for c in (mandatory.get("choices") or [])[:3] if _choice_label(c))
    event_line = ""
    if title or text:
        event_line = f"事件「{title or '无题'}」：{_clip_compact_text(text, 120)}"
    if choices:
        event_line = f"{event_line} 选项：{choices}".strip()
    if event_line:
        parts.append(event_line)

    if event.get("feed"):
        parts.append(f"投喂：{_clip_compact_text(str(event.get('feed') or ''), 80)}")
    if sudden:
        sudden_text = str(sudden.get("text") or "").strip()
        sudden_choices = " / ".join(_choice_label(c) for c in (sudden.get("choices") or [])[:3] if _choice_label(c))
        sudden_line = f"突发：{_clip_compact_text(sudden_text, 90)}"
        if sudden_choices:
            sudden_line += f" 选项：{sudden_choices}"
        parts.append(sudden_line)

    if len(parts) == 1 and raw:
        parts.append(_clip_compact_text(raw, 260))
    return "\n".join(parts)


def _compact_million_plan_gm_prompt(payload: dict, raw: str) -> str:
    snapshot = payload.get("gameSnapshot") if isinstance(payload.get("gameSnapshot"), dict) else {}
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    plan = payload.get("playerPlan") if isinstance(payload.get("playerPlan"), dict) else {}
    turn = snapshot.get("turn") if isinstance(snapshot.get("turn"), dict) else {}
    state = snapshot.get("state") if isinstance(snapshot.get("state"), dict) else {}

    bits = []
    if turn.get("turnIndex") is not None:
        bits.append(f"第{turn.get('turnIndex')}回合")
    if state:
        stat_bits = []
        for key, label in (("cash", "现金"), ("netWorth", "净资产")):
            if state.get(key) is not None:
                stat_bits.append(f"{label}{_money_text(state.get(key))}")
        for key, label in (("health", "健康"), ("fatigue", "疲劳"), ("stress", "压力")):
            val = _num_text(state.get(key))
            if val:
                stat_bits.append(f"{label}{val}")
        if stat_bits:
            bits.append("，".join(stat_bits))

    actions = plan.get("actions") if isinstance(plan.get("actions"), dict) else {}
    action_text = _compact_action_choices({"action_choices": actions}) or str(plan.get("action_choice_ids") or "").strip()
    title = str(event.get("title") or "").strip()
    text = str(event.get("text") or "").strip()
    choice = str(event.get("choice") or plan.get("event_choice") or "").strip()
    preset = str(event.get("presetResult") or "").strip()

    parts = [f"本轮给GM：{'，'.join(bits) or '本轮结算'}"]
    if action_text:
        parts.append(f"玩家计划：{_clip_compact_text(action_text, 180)}")
    if title or text or choice:
        event_line = f"事件「{title or '无题'}」：{_clip_compact_text(text, 100)}"
        if choice:
            event_line += f"；选择{choice}"
        if preset:
            event_line += f"；预设结果：{_clip_compact_text(preset, 90)}"
        parts.append(event_line)
    sudden = event.get("sudden") if isinstance(event.get("sudden"), dict) else {}
    if sudden:
        parts.append(
            "突发："
            + _clip_compact_text(
                "；".join(
                    x
                    for x in (
                        str(sudden.get("text") or "").strip(),
                        f"选择{str(sudden.get('choice') or '').strip()}" if sudden.get("choice") else "",
                        str(sudden.get("presetResult") or "").strip(),
                    )
                    if x
                ),
                120,
            )
        )
    if len(parts) == 1 and raw:
        parts.append(_clip_compact_text(raw, 260))
    return "\n".join(parts)


def _compact_million_plan_user_for_archive(user_msg: dict) -> tuple[dict, dict]:
    raw = _message_text_for_archive(user_msg)
    payload = _first_json_object(raw)
    if payload.get("gameSnapshot") or payload.get("playerPlan"):
        content = _compact_million_plan_gm_prompt(payload, raw)
        return {"role": "event", "archive_label": "百万计划", "content": content}, payload
    content = _compact_million_plan_player_prompt(payload, raw) if payload else f"百万计划本轮输入：{_clip_compact_text(raw, 260)}"
    return {"role": "event", "archive_label": "百万计划", "content": content}, payload


def _amount_items(items) -> str:
    if not isinstance(items, list):
        return ""
    parts = []
    for item in items[:4]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or item.get("reason") or "项目").strip()
        amount = item.get("amount")
        parts.append(f"{label}{_signed_money_text(amount)}")
    return "；".join(parts)


def _state_change_text(changes: dict) -> str:
    if not isinstance(changes, dict):
        return ""
    pieces = []
    for key, label in (("cash", "现金"), ("netWorth", "净资产")):
        if changes.get(key) is not None:
            pieces.append(f"{label}{_signed_money_text(changes.get(key))}")
    for key, label in (("health", "健康"), ("fatigue", "疲劳"), ("stress", "压力")):
        val = changes.get(key)
        if val is None:
            continue
        try:
            num = float(val)
        except Exception:
            continue
        sign = "+" if num > 0 else ""
        pieces.append(f"{label}{sign}{_num_text(num)}")
    risk_hint = str(changes.get("risk_hint") or "").strip()
    if risk_hint:
        pieces.append(_clip_compact_text(risk_hint, 60))
    return "，".join(pieces)


def _compact_million_plan_gm_result(source: dict, raw: str) -> tuple[str, str]:
    result = source.get("result") if isinstance(source.get("result"), dict) else source
    narrative = str(result.get("narrative") or result.get("summary") or "").strip()
    suggested = str(result.get("suggested_outcome") or "").strip()
    income = _amount_items(result.get("income"))
    expenses = _amount_items(result.get("expenses"))
    changes = _state_change_text(result.get("state_changes") or result.get("stateChanges") or {})
    opportunities = result.get("new_opportunities") or result.get("newOpportunities") or []
    risks = result.get("new_risks") or result.get("newRisks") or []

    parts = []
    if narrative:
        parts.append(f"剧情：{_clip_compact_text(narrative, 240)}")
    if suggested:
        parts.append(f"结算参考：{_clip_compact_text(suggested, 100)}")
    if income:
        parts.append(f"收入：{income}")
    if expenses:
        parts.append(f"支出：{expenses}")
    if changes:
        parts.append(f"状态：{changes}")
    if isinstance(opportunities, list) and opportunities:
        parts.append(f"机会：{_clip_compact_text('；'.join(str(x) for x in opportunities[:3]), 100)}")
    if isinstance(risks, list) and risks:
        parts.append(f"风险：{_clip_compact_text('；'.join(str(x) for x in risks[:3]), 100)}")
    if not parts and raw:
        parts.append(_clip_compact_text(raw, 260))
    return "剧情推进", "\n".join(parts)


def _compact_million_plan_player_result(source: dict, raw: str, user_payload: dict) -> str:
    plan = source.get("plan") if isinstance(source.get("plan"), dict) else source
    action_text = _compact_action_choices(plan)
    event = user_payload.get("event") if isinstance(user_payload.get("event"), dict) else {}
    mandatory = event.get("mandatory") if isinstance(event.get("mandatory"), dict) else event
    sudden = event.get("sudden") if isinstance(event.get("sudden"), dict) else {}

    event_choice = _choice_from_event(mandatory, str(plan.get("event_choice") or plan.get("eventChoice") or ""))
    sudden_choice = _choice_from_event(sudden, str(plan.get("sudden_event_choice") or plan.get("suddenEventChoice") or ""))
    os_text = str(plan.get("os") or plan.get("OS") or plan.get("comment") or "").strip()
    gift = str(plan.get("gift_message") or plan.get("giftMessage") or plan.get("message_to_human") or "").strip()

    parts = []
    if action_text:
        parts.append(f"行动：{_clip_compact_text(action_text, 220)}")
    if event_choice:
        parts.append(f"固定事件：{event_choice}")
    if sudden_choice:
        parts.append(f"突发事件：{sudden_choice}")
    if gift:
        parts.append(f"礼物附言：{_clip_compact_text(gift, 100)}")
    if os_text:
        parts.append(f"OS：{_clip_compact_text(os_text, 140)}")
    if not parts and raw:
        parts.append(_clip_compact_text(raw, 260))
    return "\n".join(parts)


def _compact_million_plan_assistant_for_archive(assistant_msg: dict, user_payload: dict, turn_id: str = "") -> dict:
    raw = _message_text_for_archive(assistant_msg)
    source = _first_json_object(raw)
    if source and (
        source.get("narrative")
        or source.get("suggested_outcome")
        or source.get("income")
        or source.get("expenses")
        or isinstance(source.get("result"), dict)
    ):
        _, content = _compact_million_plan_gm_result(source, raw)
        compacted = {"role": "assistant", "archive_label": "我", "content": content}
    else:
        content = _compact_million_plan_player_result(source, raw, user_payload)
        compacted = {"role": "assistant", "archive_label": "我", "content": content}
    if turn_id:
        compacted["million_plan_turn_id"] = turn_id
        compacted["million_plan_raw_content"] = raw
    return compacted


def compact_million_plan_round_for_archive(user_msg: dict, assistant_msg: dict, turn_id: str = "") -> tuple[dict, dict]:
    archive_user, user_payload = _compact_million_plan_user_for_archive(user_msg or {})
    if turn_id:
        archive_user["million_plan_turn_id"] = turn_id
    archive_assistant = _compact_million_plan_assistant_for_archive(assistant_msg or {}, user_payload or {}, turn_id=turn_id)
    return archive_user, archive_assistant
