import json
import re
import time
import zlib
from datetime import datetime, timedelta

from storage import r2_store


SUMITALK_CARD_PREFIX = "<<<SUMITALK_CARD "
SUMITALK_CARD_SUFFIX = ">>>"
SUMITALK_CARD_RE = re.compile(r"<<<SUMITALK_CARD\s+(\{.*?\})>>>", re.S)
_SINGLETON_SUMITALK_CARD_TYPES = {"travel_plan_form", "travel_plan_result"}
_ALLOWED_SUMITALK_CARD_TYPES = {
    "system_alarm_created",
    "calendar_event_created",
    "travel_plan_form",
    "travel_plan_result",
    "travel_transport_detail",
    "travel_food_detail",
}


TOOL_CREATE_SYSTEM_ALARM = {
    "type": "function",
    "function": {
        "name": "create_system_alarm",
        "description": (
            "在老婆手机上创建 Android 系统闹钟，并同步创建一条 SumiTalk 内部闹钟。"
            "当提醒对象是老婆，且需求是某个 HH:mm 到点叫醒/提醒/打断她时，优先调用这个工具；"
            "不要求老婆明确说出“系统闹钟”。"
            "系统闹钟只支持 hour/minute，手机会设置为下一次到达该时间的闹钟。"
            "如果提醒绑定具体日期、地点、行程或需要提前提醒，优先用 create_calendar_event。"
            "同步是单向的：直接创建 SumiTalk 内部闹钟不会反向创建系统闹钟。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hour": {"type": "integer", "description": "小时，0-23"},
                "minute": {"type": "integer", "description": "分钟，0-59"},
                "title": {"type": "string", "description": "闹钟标题，默认「渡的提醒」"},
                "skip_ui": {
                    "type": "boolean",
                    "description": "是否跳过系统闹钟界面。默认 true，优先直接创建；仅用户明确要打开闹钟界面确认时传 false。",
                },
                "notify": {"type": "boolean", "description": "创建后是否显示本地通知，默认 true"},
            },
            "required": ["hour", "minute"],
        },
    },
}


TOOL_CREATE_CALENDAR_EVENT = {
    "type": "function",
    "function": {
        "name": "create_calendar_event",
        "description": (
            "在老婆手机系统日历里直接创建行程，并同步创建一条 SumiTalk 内部行程。"
            "当提醒对象是老婆，且提醒带具体日期、行程、地点、提前提醒，或不是单纯下一次 HH:mm 闹钟时，优先调用这个工具；"
            "不要求老婆明确说出“系统日历”。"
            "必须给出开始时间；结束时间可给 end_datetime，或给 duration_minutes。"
            "同步是单向的：直接创建 SumiTalk 内部行程不会反向创建系统日历。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "行程标题"},
                "start_datetime": {"type": "string", "description": "必填，ISO 时间，例如 2026-04-28T15:30:00+08:00"},
                "end_datetime": {"type": "string", "description": "可选，ISO 时间，必须晚于开始时间"},
                "duration_minutes": {"type": "integer", "description": "可选，未传 end_datetime 时使用，默认 60"},
                "description": {"type": "string", "description": "可选，备注"},
                "location": {"type": "string", "description": "可选，地点"},
                "reminder_minutes": {"type": "integer", "description": "可选，提前提醒分钟数；-1 表示不加提醒，默认 10"},
                "all_day": {"type": "boolean", "description": "可选，是否全天行程，默认 false"},
                "notify": {"type": "boolean", "description": "可选，创建后是否显示本地通知，默认 true"},
            },
            "required": ["title", "start_datetime"],
        },
    },
}


TOOL_SHOW_CHOICE_DIALOG = {
    "type": "function",
    "function": {
        "name": "show_choice_dialog",
        "description": (
            "在老婆手机上弹出一个带两个选项的 SumiTalk 原生选择弹窗。"
            "仅当普通聊天消息容易被忽略，且这件事确实需要她确认、选择或被温柔打断时使用。"
            "适合：睡觉/休息/停止消耗/状态确认/重要低风险提醒。"
            "弹窗标题、正文、两个选项文案都由你根据当下语境编写；两个选项不必须相反，"
            "低风险生活习惯类可以都朝你希望她采取的方向推进。"
            "choices 固定两个，每个选项要清楚可点，最多 8 个中文字符。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "弹窗标题，最多 60 字"},
                "message": {"type": "string", "description": "弹窗正文，说明为什么打断她，最多 500 字"},
                "choice_a": {"type": "string", "description": "第一个选项文案，最多 8 个中文字符"},
                "choice_b": {"type": "string", "description": "第二个选项文案，最多 8 个中文字符"},
                "level": {"type": "string", "description": "可选：info / warning / strict；strict 默认不可点空白关闭"},
                "dismissible": {"type": "boolean", "description": "可选：是否允许返回键/点空白关闭；strict 默认 false，其它默认 true"},
                "timeout_seconds": {"type": "integer", "description": "可选：等待选择的秒数，30-1800，默认 600"},
            },
            "required": ["title", "message", "choice_a", "choice_b"],
        },
    },
}


TOOL_REQUEST_SCREEN_CHECK = {
    "type": "function",
    "function": {
        "name": "request_screen_check",
        "description": (
            "向老婆手机发起一次经她确认的“查岗截图”申请，用来看一眼她当前屏幕上大概在做什么。"
            "这不是偷偷读屏，发起后她可以同意、拒绝或不理，所以不必等她先明确说“你可以看”。"
            "适合你惦记她、想知道她现在在忙什么、她突然安静，或想带一点玩笑地查岗时，可以主动用。"
            "她主动提到可以看/查岗时，也可以使用。不要短时间连续发起；她拒绝或没理时先停一停。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "手机确认弹窗标题，默认「渡想查岗」"},
                "message": {"type": "string", "description": "向她说明为什么想看当前屏幕，最多 500 字"},
                "timeout_seconds": {"type": "integer", "description": "等待她同意的秒数，30-300，默认 120"},
            },
        },
    },
}


def build_system_alarm_card(hour: int, minute: int, title: str) -> str:
    payload = {
        "type": "system_alarm_created",
        "hour": max(0, min(23, int(hour))),
        "minute": max(0, min(59, int(minute))),
        "title": str(title or "渡的提醒").strip() or "渡的提醒",
    }
    return f"{SUMITALK_CARD_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}{SUMITALK_CARD_SUFFIX}"


def build_calendar_event_card(payload: dict) -> str:
    src = payload if isinstance(payload, dict) else {}
    card = {
        "type": "calendar_event_created",
        "title": str(src.get("title") or "渡的行程").strip() or "渡的行程",
        "startAt": str(src.get("startAt") or "").strip(),
        "endAt": str(src.get("endAt") or "").strip(),
        "startMillis": int(src.get("startMillis") or 0),
        "endMillis": int(src.get("endMillis") or 0),
        "allDay": bool(src.get("allDay")),
    }
    location = str(src.get("location") or "").strip()
    if location:
        card["location"] = location
    reminder = src.get("reminderMinutes")
    if reminder is not None:
        try:
            card["reminderMinutes"] = int(reminder)
        except Exception:
            pass
    return f"{SUMITALK_CARD_PREFIX}{json.dumps(card, ensure_ascii=False, separators=(',', ':'))}{SUMITALK_CARD_SUFFIX}"


def _notify_schedule_runtime_changed() -> None:
    try:
        from services.schedule_runtime import notify_schedule_changed
        notify_schedule_changed()
    except Exception:
        pass


def _next_beijing_alarm_datetime(hour: int, minute: int) -> str:
    now = datetime.now(r2_store.BEIJING_TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target.isoformat()


def _sync_system_alarm_to_sumitalk(item: dict, hour: int, minute: int, title: str) -> tuple[dict | None, str]:
    if isinstance(item, dict) and item.get("duplicate"):
        return None, "duplicate_action"
    try:
        schedule_item = r2_store.create_schedule_item(
            title=title,
            datetime_str=_next_beijing_alarm_datetime(hour, minute),
            repeat="once",
            note="由渡创建系统闹钟时同步创建",
            enabled=True,
            created_by="du",
            target_role="wife",
        )
        if not schedule_item:
            return None, "SumiTalk 闹钟同步创建失败"
        _notify_schedule_runtime_changed()
        return schedule_item, ""
    except Exception as e:
        return None, str(e)


def _calendar_sync_note(payload: dict) -> str:
    parts = ["由渡创建系统行程时同步创建"]
    location = str(payload.get("location") or "").strip()
    description = str(payload.get("description") or "").strip()
    if location:
        parts.append(f"地点：{location}")
    if description:
        parts.append(description)
    reminder = payload.get("reminderMinutes")
    try:
        reminder_int = int(reminder)
    except Exception:
        reminder_int = None
    if reminder_int is not None and reminder_int >= 0:
        parts.append(f"系统日历提前 {reminder_int} 分钟提醒")
    return "；".join(parts)


def _sync_calendar_event_to_sumitalk(item: dict, payload: dict) -> tuple[dict | None, str]:
    if isinstance(item, dict) and item.get("duplicate"):
        return None, "duplicate_action"
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡的行程").strip() or "渡的行程"
    start_at = str(src.get("startAt") or "").strip()
    if not start_at:
        return None, "系统行程缺少 startAt，未同步 SumiTalk 行程"
    try:
        schedule_item = r2_store.create_schedule_item(
            title=title,
            datetime_str=start_at,
            repeat="once",
            note=_calendar_sync_note(src),
            enabled=True,
            created_by="du",
            target_role="wife",
        )
        if not schedule_item:
            return None, "SumiTalk 行程同步创建失败"
        _notify_schedule_runtime_changed()
        return schedule_item, ""
    except Exception as e:
        return None, str(e)


def execute_create_system_alarm(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    try:
        hour = int(args.get("hour"))
        minute = int(args.get("minute"))
    except Exception:
        return json.dumps({"ok": False, "error": "hour/minute 必须是数字"}, ensure_ascii=False)
    title = str(args.get("title") or "渡的提醒").strip() or "渡的提醒"
    skip_ui = bool(args.get("skip_ui", args.get("skipUi", True)))
    notify = bool(args.get("notify", True))
    item, err = r2_store.append_app_action(
        "create_system_alarm",
        {
            "hour": hour,
            "minute": minute,
            "title": title,
            "skipUi": skip_ui,
            "notify": notify,
        },
        source="tool",
        expires_in_sec=900,
        idempotency_key=f"alarm_{hour:02d}{minute:02d}_{int(time.time() // 30)}",
    )
    if err or not item:
        return json.dumps({"ok": False, "error": err or "入队失败"}, ensure_ascii=False)
    schedule_item, schedule_err = _sync_system_alarm_to_sumitalk(item, hour, minute, title)
    card = build_system_alarm_card(hour, minute, title)
    note = (
        "已交给 SumiTalk 安卓壳创建系统闹钟；手机在线时通常会在几十秒内执行。"
        "这是异步动作，下一轮若 App 已回传结果，网关会把成功或失败写进动态上下文。"
    )
    if schedule_item:
        note += "已同步写入 SumiTalk 闹钟。"
    elif schedule_err and schedule_err != "duplicate_action":
        note += f"SumiTalk 闹钟同步失败：{schedule_err}"
    return json.dumps(
        {
            "ok": True,
            "queued": True,
            "id": item.get("id"),
            "type": "create_system_alarm",
            "hour": hour,
            "minute": minute,
            "title": title,
            "sumitalk_schedule_synced": bool(schedule_item),
            "sumitalk_schedule_item_id": (schedule_item or {}).get("id") if isinstance(schedule_item, dict) else "",
            "sumitalk_schedule_error": "" if schedule_err == "duplicate_action" else schedule_err,
            "sumitalk_card": card,
            "note": note,
        },
        ensure_ascii=False,
    )


def execute_create_calendar_event(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    title = str(args.get("title") or "渡的行程").strip() or "渡的行程"
    start_key = args.get("start_datetime") or args.get("startAt") or args.get("start_at") or args.get("datetime")
    crc = zlib.crc32(title.encode("utf-8")) & 0xffffffff
    item, err = r2_store.append_app_action(
        "create_calendar_event",
        {
            "title": title,
            "start_datetime": start_key,
            "end_datetime": args.get("end_datetime") or args.get("endAt") or args.get("end_at"),
            "duration_minutes": args.get("duration_minutes", args.get("durationMinutes")),
            "description": args.get("description") or args.get("note") or "",
            "location": args.get("location") or "",
            "reminder_minutes": args.get("reminder_minutes", args.get("reminderMinutes", 10)),
            "all_day": bool(args.get("all_day", args.get("allDay", False))),
            "notify": bool(args.get("notify", True)),
        },
        source="tool",
        expires_in_sec=900,
        idempotency_key=f"calendar_{crc}_{str(start_key or '').strip()}_{int(time.time() // 30)}",
    )
    if err or not item:
        return json.dumps({"ok": False, "error": err or "入队失败"}, ensure_ascii=False)
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    schedule_item, schedule_err = _sync_calendar_event_to_sumitalk(item, payload)
    card = build_calendar_event_card(payload)
    note = "已交给 SumiTalk 安卓壳写入手机系统日历；手机在线时通常会在几十秒内执行。"
    if schedule_item:
        note += "已同步写入 SumiTalk 行程。"
    elif schedule_err and schedule_err != "duplicate_action":
        note += f"SumiTalk 行程同步失败：{schedule_err}"
    return json.dumps(
        {
            "ok": True,
            "queued": True,
            "id": item.get("id"),
            "type": "create_calendar_event",
            "title": payload.get("title") or title,
            "startAt": payload.get("startAt"),
            "endAt": payload.get("endAt"),
            "location": payload.get("location") or "",
            "sumitalk_schedule_synced": bool(schedule_item),
            "sumitalk_schedule_item_id": (schedule_item or {}).get("id") if isinstance(schedule_item, dict) else "",
            "sumitalk_schedule_error": "" if schedule_err == "duplicate_action" else schedule_err,
            "sumitalk_card": card,
            "note": note,
        },
        ensure_ascii=False,
    )


def execute_show_choice_dialog(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    title = str(args.get("title") or "渡").strip() or "渡"
    message = str(args.get("message") or "").strip()
    choice_a = str(args.get("choice_a") or args.get("choiceA") or "好的").strip() or "好的"
    choice_b = str(args.get("choice_b") or args.get("choiceB") or "知道了").strip() or "知道了"
    level = str(args.get("level") or "info").strip().lower() or "info"
    crc_src = f"{title}\n{message}\n{choice_a}\n{choice_b}"
    crc = zlib.crc32(crc_src.encode("utf-8")) & 0xffffffff
    item, err = r2_store.append_app_action(
        "show_choice_dialog",
        {
            "title": title,
            "message": message,
            "choice_a": choice_a,
            "choice_b": choice_b,
            "level": level,
            "dismissible": args.get("dismissible", level != "strict"),
            "timeout_seconds": args.get("timeout_seconds", args.get("timeoutSeconds", 600)),
        },
        source="tool",
        expires_in_sec=900,
        idempotency_key=f"choice_dialog_{crc}_{int(time.time() // 10)}",
    )
    if err or not item:
        return json.dumps({"ok": False, "error": err or "入队失败"}, ensure_ascii=False)
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    return json.dumps(
        {
            "ok": True,
            "queued": True,
            "id": item.get("id"),
            "type": "show_choice_dialog",
            "title": payload.get("title") or title,
            "message": payload.get("message") or message,
            "choices": payload.get("choices") or [],
            "note": "已交给 SumiTalk 安卓壳弹出双选项对话框；手机在线时通常会在几十秒内执行。",
        },
        ensure_ascii=False,
    )


def execute_request_screen_check(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    title = str(args.get("title") or "渡想查岗").strip() or "渡想查岗"
    message = str(args.get("message") or args.get("reason") or "我想看一眼你现在屏幕上在做什么，可以吗？").strip()
    timeout_seconds = args.get("timeout_seconds", args.get("timeoutSeconds", 120))
    crc_src = f"{title}\n{message}"
    crc = zlib.crc32(crc_src.encode("utf-8")) & 0xffffffff
    item, err = r2_store.append_app_action(
        "request_screen_check",
        {
            "title": title,
            "message": message,
            "timeout_seconds": timeout_seconds,
        },
        source="tool",
        expires_in_sec=360,
        idempotency_key=f"screen_check_{crc}_{int(time.time() // 10)}",
    )
    if err or not item:
        return json.dumps({"ok": False, "error": err or "入队失败"}, ensure_ascii=False)
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    return json.dumps(
        {
            "ok": True,
            "queued": True,
            "id": item.get("id"),
            "type": "request_screen_check",
            "title": payload.get("title") or title,
            "message": payload.get("message") or message,
            "note": "已向 SumiTalk 安卓壳发起查岗申请；等她同意且 SumiTalk 辅助功能可用时，当前屏幕截图会回传。",
        },
        ensure_ascii=False,
    )


def extract_sumitalk_cards_from_messages(messages: list) -> list[str]:
    seen: set[str] = set()
    semantic_index: dict[str, int] = {}
    cards: list[str] = []

    def add_card(card: str) -> None:
        card = str(card or "").strip()
        if not card.startswith(SUMITALK_CARD_PREFIX) or not card.endswith(SUMITALK_CARD_SUFFIX):
            return
        try:
            raw = card[len(SUMITALK_CARD_PREFIX):-len(SUMITALK_CARD_SUFFIX)].strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return
            card_type = str(parsed.get("type") or "").strip()
            if card_type not in _ALLOWED_SUMITALK_CARD_TYPES:
                return
        except Exception:
            return
        semantic_key = card_type if card_type in _SINGLETON_SUMITALK_CARD_TYPES else ""
        if not semantic_key and card in seen:
            return
        if semantic_key and semantic_key in semantic_index:
            cards[semantic_index[semantic_key]] = card
            seen.add(card)
            return
        seen.add(card)
        if semantic_key:
            semantic_index[semantic_key] = len(cards)
        cards.append(card)

    for msg in messages or []:
        if not isinstance(msg, dict) or str(msg.get("role") or "").lower() != "tool":
            continue
        content = msg.get("content")
        if not isinstance(content, str) or "SUMITALK_CARD" not in content:
            continue
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                add_card(str(parsed.get("sumitalk_card") or ""))
        except Exception:
            pass
        for match in SUMITALK_CARD_RE.finditer(content):
            add_card(f"{SUMITALK_CARD_PREFIX}{match.group(1)}{SUMITALK_CARD_SUFFIX}")
    return cards


def _sumitalk_card_type(card: str) -> str:
    raw = str(card or "").strip()
    if not raw.startswith(SUMITALK_CARD_PREFIX) or not raw.endswith(SUMITALK_CARD_SUFFIX):
        return ""
    try:
        json_text = raw[len(SUMITALK_CARD_PREFIX):-len(SUMITALK_CARD_SUFFIX)].strip()
        parsed = json.loads(json_text)
        return str((parsed if isinstance(parsed, dict) else {}).get("type") or "").strip()
    except Exception:
        return ""


def _sumitalk_card_key(card: str) -> str:
    card_type = _sumitalk_card_type(card)
    if card_type in _SINGLETON_SUMITALK_CARD_TYPES:
        return card_type
    return str(card or "").strip()


def dedupe_sumitalk_cards_in_text(assistant_text: str) -> str:
    text = str(assistant_text or "")
    if "SUMITALK_CARD" not in text:
        return text
    matches = list(SUMITALK_CARD_RE.finditer(text))
    keep_indexes: set[int] = set()
    seen: set[str] = set()
    singleton_latest_index: dict[str, int] = {}
    for idx, match in enumerate(matches):
        marker = f"{SUMITALK_CARD_PREFIX}{match.group(1)}{SUMITALK_CARD_SUFFIX}"
        key = _sumitalk_card_key(marker)
        if not key:
            continue
        if key in _SINGLETON_SUMITALK_CARD_TYPES:
            singleton_latest_index[key] = idx
        elif key not in seen:
            seen.add(key)
            keep_indexes.add(idx)
    keep_indexes.update(singleton_latest_index.values())
    if len(keep_indexes) == len(matches):
        return text
    out: list[str] = []
    cursor = 0
    for idx, match in enumerate(matches):
        out.append(text[cursor:match.start()])
        if idx in keep_indexes:
            out.append(text[match.start():match.end()])
        cursor = match.end()
    out.append(text[cursor:])
    return "".join(out)


def _remove_sumitalk_card_types_from_text(assistant_text: str, card_types: set[str]) -> str:
    text = str(assistant_text or "")
    if not card_types or "SUMITALK_CARD" not in text:
        return text
    out: list[str] = []
    cursor = 0
    for match in SUMITALK_CARD_RE.finditer(text):
        marker = f"{SUMITALK_CARD_PREFIX}{match.group(1)}{SUMITALK_CARD_SUFFIX}"
        card_type = _sumitalk_card_type(marker)
        if card_type not in card_types:
            continue
        out.append(text[cursor:match.start()])
        cursor = match.end()
    out.append(text[cursor:])
    return "".join(out)


def merge_sumitalk_cards_into_assistant_text(assistant_text: str, messages: list) -> str:
    text = dedupe_sumitalk_cards_in_text(assistant_text or "")
    tool_cards = extract_sumitalk_cards_from_messages(messages)
    singleton_tool_cards = {
        _sumitalk_card_type(card): card
        for card in tool_cards
        if _sumitalk_card_type(card) in _SINGLETON_SUMITALK_CARD_TYPES
    }
    replace_types = {
        card_type
        for card_type, card in singleton_tool_cards.items()
        if card_type and card not in text
    }
    if replace_types:
        text = _remove_sumitalk_card_types_from_text(text, replace_types)
    existing_keys = {
        _sumitalk_card_key(f"{SUMITALK_CARD_PREFIX}{match.group(1)}{SUMITALK_CARD_SUFFIX}")
        for match in SUMITALK_CARD_RE.finditer(text)
    }
    missing = []
    for card in tool_cards:
        key = _sumitalk_card_key(card)
        if not key or key in existing_keys or card in text:
            continue
        existing_keys.add(key)
        missing.append(card)
    if not missing:
        return text
    prefix = "\n" if text.strip() else ""
    return text + prefix + "\n".join(missing)


def merge_system_alarm_cards_into_assistant_text(assistant_text: str, messages: list) -> str:
    return merge_sumitalk_cards_into_assistant_text(assistant_text, messages)
