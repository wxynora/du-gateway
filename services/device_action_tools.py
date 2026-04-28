import json
import re
import time
import zlib

from storage import r2_store


SUMITALK_CARD_PREFIX = "<<<SUMITALK_CARD "
SUMITALK_CARD_SUFFIX = ">>>"
SUMITALK_CARD_RE = re.compile(r"<<<SUMITALK_CARD\s+(\{.*?\})>>>", re.S)


TOOL_CREATE_SYSTEM_ALARM = {
    "type": "function",
    "function": {
        "name": "create_system_alarm",
        "description": (
            "在老婆手机上创建 Android 系统闹钟，不是网关日历提醒。"
            "只有老婆明确要求设置手机系统闹钟/叫醒闹钟时调用；普通提醒仍用 schedule_create。"
            "系统闹钟只支持 hour/minute，手机会设置为下一次到达该时间的闹钟。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hour": {"type": "integer", "description": "小时，0-23"},
                "minute": {"type": "integer", "description": "分钟，0-59"},
                "title": {"type": "string", "description": "闹钟标题，默认「渡的提醒」"},
                "skip_ui": {
                    "type": "boolean",
                    "description": "是否跳过系统闹钟界面。默认 false，会让手机弹出系统闹钟创建界面。",
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
            "在老婆手机系统日历里直接创建行程，不是网关提醒。"
            "只有老婆明确要求把某件事加入手机日历/系统行程时调用；普通到点提醒仍用 schedule_create。"
            "必须给出开始时间；结束时间可给 end_datetime，或给 duration_minutes。"
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


def execute_create_system_alarm(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    try:
        hour = int(args.get("hour"))
        minute = int(args.get("minute"))
    except Exception:
        return json.dumps({"ok": False, "error": "hour/minute 必须是数字"}, ensure_ascii=False)
    title = str(args.get("title") or "渡的提醒").strip() or "渡的提醒"
    skip_ui = bool(args.get("skip_ui", args.get("skipUi", False)))
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
    card = build_system_alarm_card(hour, minute, title)
    return json.dumps(
        {
            "ok": True,
            "queued": True,
            "id": item.get("id"),
            "type": "create_system_alarm",
            "hour": hour,
            "minute": minute,
            "title": title,
            "sumitalk_card": card,
            "note": "已交给 SumiTalk 安卓壳创建系统闹钟；手机在线时通常会在几十秒内执行。",
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
    card = build_calendar_event_card(payload)
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
            "sumitalk_card": card,
            "note": "已交给 SumiTalk 安卓壳写入手机系统日历；手机在线时通常会在几十秒内执行。",
        },
        ensure_ascii=False,
    )


def extract_sumitalk_cards_from_messages(messages: list) -> list[str]:
    seen: set[str] = set()
    cards: list[str] = []

    def add_card(card: str) -> None:
        card = str(card or "").strip()
        if not card.startswith(SUMITALK_CARD_PREFIX) or not card.endswith(SUMITALK_CARD_SUFFIX):
            return
        if card in seen:
            return
        try:
            raw = card[len(SUMITALK_CARD_PREFIX):-len(SUMITALK_CARD_SUFFIX)].strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return
            if str(parsed.get("type") or "").strip() not in {"system_alarm_created", "calendar_event_created"}:
                return
        except Exception:
            return
        seen.add(card)
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


def merge_sumitalk_cards_into_assistant_text(assistant_text: str, messages: list) -> str:
    text = assistant_text or ""
    missing = [card for card in extract_sumitalk_cards_from_messages(messages) if card not in text]
    if not missing:
        return text
    prefix = "\n" if text.strip() else ""
    return text + prefix + "\n".join(missing)


def merge_system_alarm_cards_into_assistant_text(assistant_text: str, messages: list) -> str:
    return merge_sumitalk_cards_into_assistant_text(assistant_text, messages)
