import json
import re
import time

from storage import r2_store


SUMITALK_CARD_PREFIX = "<<<SUMITALK_CARD "
SUMITALK_CARD_SUFFIX = ">>>"
SYSTEM_ALARM_CARD_RE = re.compile(r"<<<SUMITALK_CARD\s+(\{.*?\"system_alarm_created\".*?\})>>>", re.S)


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


def build_system_alarm_card(hour: int, minute: int, title: str) -> str:
    payload = {
        "type": "system_alarm_created",
        "hour": max(0, min(23, int(hour))),
        "minute": max(0, min(59, int(minute))),
        "title": str(title or "渡的提醒").strip() or "渡的提醒",
    }
    return f"{SUMITALK_CARD_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}{SUMITALK_CARD_SUFFIX}"


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


def extract_system_alarm_cards_from_messages(messages: list) -> list[str]:
    seen: set[str] = set()
    cards: list[str] = []

    def add_card(card: str) -> None:
        card = str(card or "").strip()
        if not card.startswith(SUMITALK_CARD_PREFIX) or not card.endswith(SUMITALK_CARD_SUFFIX):
            return
        if "system_alarm_created" not in card or card in seen:
            return
        seen.add(card)
        cards.append(card)

    for msg in messages or []:
        if not isinstance(msg, dict) or str(msg.get("role") or "").lower() != "tool":
            continue
        content = msg.get("content")
        if not isinstance(content, str) or "system_alarm_created" not in content:
            continue
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                add_card(str(parsed.get("sumitalk_card") or ""))
        except Exception:
            pass
        for match in SYSTEM_ALARM_CARD_RE.finditer(content):
            add_card(f"{SUMITALK_CARD_PREFIX}{match.group(1)}{SUMITALK_CARD_SUFFIX}")
    return cards


def merge_system_alarm_cards_into_assistant_text(assistant_text: str, messages: list) -> str:
    text = assistant_text or ""
    missing = [card for card in extract_system_alarm_cards_from_messages(messages) if card not in text]
    if not missing:
        return text
    prefix = "\n" if text.strip() else ""
    return text + prefix + "\n".join(missing)
