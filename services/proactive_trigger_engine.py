from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

_STATE_KEY = "global/proactive_trigger_state.json"
_STATE_MAX_FIRED = 200
_MORNING_START_HOUR = 5
_MORNING_END_HOUR = 12
_NIGHT_REAWAKE_END_HOUR = 5
_MIN_MORNING_OFF_MINUTES = 60
_MIN_NIGHT_OFF_MINUTES = 45
_SLEEP_STILL_AWAKE_AFTER_MINUTES = 30
_SLEEP_STILL_AWAKE_MAX_MINUTES = 180
_XHS_LONG_USE_MINUTES = 120
_NO_REPLY_SOFT_TRIGGER_AFTER_MINUTES = 30
_NO_REPLY_SOFT_TRIGGER_MAX_MINUTES = 360
_NO_REPLY_APP_LOOKBACK_MINUTES = 30
_RECENT_NORMAL_CHAT_SUPPRESS_MINUTES = 12
_CHAT_AFTER_SLEEP_GRACE_SECONDS = 90
_SENSE_TRIGGER_HISTORY_LIMIT = 200
_SENSE_TRIGGER_YESTERDAY_LIMIT = 80

_SLEEP_INTENT_RE = re.compile(
    r"(晚安(?:啦|了|喽|呀)?|先睡(?:了|啦)?|我(?:先|要|准备|打算|去|该|真的|马上)?睡(?:了|啦|觉了|觉|觉去)?|(?:准备|打算|马上|该)睡(?:了|啦|觉了|觉)?|去睡(?:了|啦|觉)?|困得不行.*睡|撑不住.*睡)",
    re.IGNORECASE,
)
_SLEEP_INTENT_NEGATION_OR_QUESTION_RE = re.compile(
    r"(不是|没有|没睡|还没睡|不睡|不想睡|别睡|不要睡|睡不着|睡太少|睡眠|睡醒|刚睡|睡前|睡后|睡得|睡过|睡够|睡不好|睡不够|是不是|是否|为什么|怎么|咋|多久|几个小时|吗|么|嘛|？|\?)",
    re.IGNORECASE,
)
_SLEEP_INTENT_META_RE = re.compile(
    r"(trigger|触发|规则|代码|bug|日志|网关|系统|误触发|主动硬触发|主动触发|硬触发|半小时一次|每半小时)",
    re.IGNORECASE,
)
_SLEEP_INTENT_OTHER_SUBJECT_RE = re.compile(
    r"(你|渡|笨笨|笨笨机|模型|assistant)(?:先|要|准备|打算|去|该|真的|马上)?睡",
    re.IGNORECASE,
)

_XHS_PACKAGES = {"com.xingin.xhs"}
_XHS_NAME_HINTS = ("小红书", "xiaohongshu", "xhs", "rednote")
_AWAY_INTENT_HINTS = (
    "我去洗澡",
    "去洗澡",
    "洗澡去了",
    "我去睡",
    "去睡",
    "睡觉",
    "睡了",
    "晚安",
    "我去吃饭",
    "去吃饭",
    "我去做饭",
    "去做饭",
    "我去上课",
    "去上课",
    "我去开会",
    "去开会",
    "我去忙",
    "先忙",
    "忙去了",
    "我去写代码",
    "去写代码",
    "我去工作",
    "去工作",
    "我出门",
    "要出门",
    "我去拿快递",
    "去拿快递",
    "我下楼",
    "去下楼",
    "等我一下",
    "待会聊",
    "一会儿回来",
    "回头聊",
    "先不聊",
)
_EVENT_PRIORITY = {
    "sleep_intent_still_screen_on": 10,
    "night_reawake_screen_on": 20,
    "morning_first_screen_on": 30,
    "xiaohongshu_over_2h": 40,
    "no_reply_30m_app_activity": 90,
}


@dataclass
class TriggerEvent:
    trigger_type: str
    dedupe_key: str
    fact: str
    device_id: str = ""
    event_at: str = ""

    def text(self) -> str:
        lines = [
            "[Proactive trigger fact]",
            f"trigger_type: {self.trigger_type}",
            f"fact: {self.fact}",
        ]
        if self.event_at:
            lines.append(f"event_at: {self.event_at}")
        return "\n".join(lines)


def _now_dt():
    return parse_iso_to_beijing(now_beijing_iso())


def _dt(raw: Any):
    return parse_iso_to_beijing(str(raw or "").strip())


def _minutes_between(start, end) -> int:
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() // 60))


def _event_time(data: dict) -> str:
    return str(
        data.get("occurredAt")
        or data.get("observedAt")
        or data.get("capturedAt")
        or data.get("updatedAt")
        or ""
    ).strip()


def _is_screen_on(data: dict) -> bool:
    return str((data or {}).get("event") or "").strip().lower() in {"screen_on", "user_present"}


def _is_screen_off(data: dict) -> bool:
    return str((data or {}).get("event") or "").strip().lower() == "screen_off"


def _is_screen_currently_on(doc: dict) -> bool:
    screen = doc.get("screen") if isinstance(doc.get("screen"), dict) else {}
    event = str(screen.get("event") or "").strip().lower()
    interactive = screen.get("interactive")
    if event in {"screen_on", "user_present", "app_active"}:
        return True
    return interactive is True or str(interactive).strip().lower() in {"1", "true", "yes", "on"}


def _device_id(doc: dict) -> str:
    for key in ("screen", "foreground", "app_sessions", "battery", "location"):
        bucket = doc.get(key)
        if isinstance(bucket, dict):
            did = str(bucket.get("deviceId") or "").strip()
            if did:
                return did
    return ""


def _foreground_label(doc: dict) -> str:
    fg = doc.get("foreground") if isinstance(doc.get("foreground"), dict) else {}
    app = str(fg.get("appName") or fg.get("packageName") or "").strip()
    return app


def _history_screen_events(history: list[dict]) -> list[dict]:
    out = []
    for row in history or []:
        if not isinstance(row, dict) or str(row.get("type") or "") != "screen":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        t = _dt(_event_time(data))
        if not t:
            continue
        out.append({"at": t, "data": data})
    out.sort(key=lambda x: x["at"])
    return out


def _previous_screen_off(events: list[dict], at_dt: datetime) -> dict | None:
    prev = None
    for item in events:
        if item["at"] >= at_dt:
            break
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if _is_screen_off(data):
            prev = item
    return prev


def _latest_screen_on(events: list[dict]) -> dict | None:
    for item in reversed(events):
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if _is_screen_on(data):
            return item
    return None


def _sleep_summary_minutes(on_data: dict | None, on_at: datetime) -> int:
    summary = (on_data or {}).get("sleepSummary")
    if not isinstance(summary, dict):
        return 0
    end_at = _dt(summary.get("endAt"))
    if end_at and abs((on_at - end_at).total_seconds()) > 10 * 60:
        return 0
    try:
        total_ms = int(summary.get("totalDurationMs") or 0)
    except Exception:
        total_ms = 0
    if total_ms > 0:
        return max(0, int(total_ms // 60000))
    try:
        return max(0, int(summary.get("totalMinutes") or 0))
    except Exception:
        return 0


def _screen_off_minutes(prev_off: dict | None, on_at: datetime, on_data: dict | None = None) -> int:
    summary_minutes = _sleep_summary_minutes(on_data, on_at)
    block_minutes = 0
    if not prev_off:
        block = (on_data or {}).get("lastSleepBlock")
        if isinstance(block, dict):
            try:
                duration_ms = int(block.get("durationMs") or 0)
            except Exception:
                duration_ms = 0
            if duration_ms > 0:
                block_minutes = max(0, int(duration_ms // 60000))
                return max(block_minutes, summary_minutes)
            start_at = _dt(block.get("startAt"))
            end_at = _dt(block.get("endAt")) or on_at
            block_minutes = _minutes_between(start_at, end_at)
            return max(block_minutes, summary_minutes)
        return summary_minutes
    data = prev_off.get("data") if isinstance(prev_off.get("data"), dict) else {}
    try:
        duration_ms = int(data.get("screenOffDurationMs") or 0)
    except Exception:
        duration_ms = 0
    if duration_ms > 0:
        block_minutes = max(0, int(duration_ms // 60000))
        return max(block_minutes, summary_minutes)
    off_at = _dt(data.get("screenOffSince") or data.get("occurredAt") or prev_off.get("at"))
    block_minutes = _minutes_between(off_at, on_at)
    return max(block_minutes, summary_minutes)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if str(part.get("type") or "").strip().lower() == "text":
                    parts.append(str(part.get("text") or ""))
                elif isinstance(part.get("text"), str):
                    parts.append(str(part.get("text") or ""))
        return "\n".join(parts)
    return str(content or "")


def _is_explicit_sleep_intent_text(text: str) -> bool:
    s = re.sub(r"\s+", "", str(text or "").strip())
    if not s:
        return False
    if _SLEEP_INTENT_META_RE.search(s):
        return False
    if _SLEEP_INTENT_NEGATION_OR_QUESTION_RE.search(s):
        return False
    if _SLEEP_INTENT_OTHER_SUBJECT_RE.search(s):
        return False
    return bool(_SLEEP_INTENT_RE.search(s))


def _latest_sleep_message(window_id: str) -> dict | None:
    rounds = r2_store.get_conversation_rounds(window_id, last_n=80) or []
    for row in reversed(rounds):
        if not isinstance(row, dict):
            continue
        ts = str(row.get("timestamp") or "").strip()
        idx = str(row.get("index") or "").strip()
        for msg in reversed(row.get("messages") or []):
            if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "user":
                continue
            text = _message_text(msg.get("content")).strip()
            if text and _is_explicit_sleep_intent_text(text):
                return {"timestamp": ts, "index": idx, "text": text}
    return None


def _round_user_text(row: dict) -> str:
    for msg in row.get("messages") or []:
        if not isinstance(msg, dict) or str(msg.get("role") or "").strip().lower() != "user":
            continue
        text = _message_text(msg.get("content")).strip()
        if text:
            return text
    return ""


def _round_has_assistant(row: dict) -> bool:
    for msg in row.get("messages") or []:
        if isinstance(msg, dict) and str(msg.get("role") or "").strip().lower() == "assistant":
            if _message_text(msg.get("content")).strip():
                return True
    return False


def _is_backend_event_text(text: str) -> bool:
    s = str(text or "").strip()
    return (
        s.startswith("[Proactive trigger fact]")
        or "SumiTalk 双选项弹窗收到了回应" in s
        or "弹窗结果：" in s
    )


def _latest_normal_chat_round(window_id: str) -> dict | None:
    rounds = r2_store.get_conversation_rounds(window_id, last_n=30) or []
    for row in reversed(rounds):
        if not isinstance(row, dict) or not _round_has_assistant(row):
            continue
        text = _round_user_text(row)
        if not text or _is_backend_event_text(text):
            continue
        return {
            "timestamp": str(row.get("timestamp") or "").strip(),
            "index": str(row.get("index") or "").strip(),
            "user_text": text,
        }
    return None


def _recent_normal_chat_suppress_reason(window_id: str, now_dt) -> str:
    latest = _latest_normal_chat_round(window_id)
    if not latest:
        return ""
    latest_dt = _dt(latest.get("timestamp"))
    if not latest_dt:
        return ""
    elapsed = _minutes_between(latest_dt, now_dt)
    if elapsed < _RECENT_NORMAL_CHAT_SUPPRESS_MINUTES:
        return f"recent_normal_chat:{elapsed}m:index={latest.get('index') or ''}"
    return ""


def _has_normal_user_chat_after(window_id: str, at_dt: datetime) -> bool:
    rounds = r2_store.get_conversation_rounds(window_id, last_n=80) or []
    threshold = at_dt + timedelta(seconds=_CHAT_AFTER_SLEEP_GRACE_SECONDS)
    for row in reversed(rounds):
        if not isinstance(row, dict):
            continue
        row_dt = _dt(row.get("timestamp"))
        if not row_dt:
            continue
        if row_dt <= threshold:
            break
        text = _round_user_text(row)
        if text and not _is_backend_event_text(text):
            return True
    return False


def _user_announced_away(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    return any(h in s for h in _AWAY_INTENT_HINTS)


def _has_user_reply_after(at_dt: datetime) -> bool:
    last_user_dt = _dt(r2_store.get_last_telegram_user_activity_at())
    if not last_user_dt:
        return False
    return last_user_dt > at_dt + timedelta(seconds=30)


def _is_xhs_app(item: dict) -> bool:
    pkg = str((item or {}).get("packageName") or "").strip().lower()
    app = str((item or {}).get("appName") or "").strip().lower()
    if pkg in _XHS_PACKAGES:
        return True
    return any(h in app or h in pkg for h in _XHS_NAME_HINTS)


def _active_xhs_minutes(doc: dict, now_dt) -> tuple[int, str]:
    app_sessions = doc.get("app_sessions") if isinstance(doc.get("app_sessions"), dict) else {}
    active = app_sessions.get("active") if isinstance(app_sessions.get("active"), dict) else {}
    if not active or not _is_xhs_app(active):
        return 0, ""
    started = _dt(active.get("startedAt"))
    return _minutes_between(started, now_dt), str(active.get("startedAt") or "").strip()


def _clock(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%H:%M")


def _duration_text(minutes: int) -> str:
    m = max(1, int(minutes or 0))
    if m < 60:
        return f"{m} 分钟"
    h = m // 60
    rest = m % 60
    return f"{h} 小时 {rest} 分钟" if rest else f"{h} 小时"


def _session_minutes(start_dt, end_dt, since_dt, now_dt) -> int:
    if not start_dt:
        return 0
    s = max(start_dt, since_dt)
    e = min(end_dt or now_dt, now_dt)
    return _minutes_between(s, e)


def _add_session(out: list[dict], seen: set[tuple[str, str, str]], item: dict, since_dt, now_dt, active: bool = False) -> None:
    if not isinstance(item, dict):
        return
    app = str(item.get("appName") or item.get("packageName") or "").strip()
    pkg = str(item.get("packageName") or app).strip()
    started = _dt(item.get("startedAt"))
    ended = _dt(item.get("endedAt")) if not active else now_dt
    if not app or not started:
        return
    if ended and ended < since_dt:
        return
    if started > now_dt:
        return
    key = (pkg, str(item.get("startedAt") or ""), str(item.get("endedAt") or "active"))
    if key in seen:
        return
    seen.add(key)
    minutes = _session_minutes(started, ended, since_dt, now_dt)
    if minutes <= 0:
        return
    out.append({"app": app, "started": started, "ended": ended, "minutes": minutes, "active": active})


def _recent_app_activity_lines(doc: dict, history: list[dict], now_dt) -> list[str]:
    since_dt = now_dt - timedelta(minutes=_NO_REPLY_APP_LOOKBACK_MINUTES)
    sessions: list[dict] = []
    seen_sessions: set[tuple[str, str, str]] = set()

    app_sessions = doc.get("app_sessions") if isinstance(doc.get("app_sessions"), dict) else {}
    active = app_sessions.get("active") if isinstance(app_sessions.get("active"), dict) else {}
    if active:
        _add_session(sessions, seen_sessions, active, since_dt, now_dt, active=True)
    for item in app_sessions.get("recent") or []:
        _add_session(sessions, seen_sessions, item, since_dt, now_dt)

    for row in history or []:
        if not isinstance(row, dict) or str(row.get("type") or "") != "app_sessions":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        for item in data.get("recent") or []:
            _add_session(sessions, seen_sessions, item, since_dt, now_dt)

    if sessions:
        sessions.sort(key=lambda x: x["started"])
        lines = []
        for item in sessions[-6:]:
            start = _clock(item.get("started"))
            app = item.get("app") or "未知应用"
            minutes = _duration_text(item.get("minutes") or 0)
            if item.get("active"):
                lines.append(f"{start} 打开{app}，现在还在前台，过去半小时内已用约 {minutes}")
            else:
                lines.append(f"{start} 打开{app}，用了约 {minutes}")
        return lines

    foreground_lines: list[str] = []
    seen_fg: set[tuple[str, str]] = set()
    for row in history or []:
        if not isinstance(row, dict) or str(row.get("type") or "") != "foreground":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        at = _dt(data.get("observedAt") or data.get("updatedAt") or row.get("at"))
        if not at or at < since_dt or at > now_dt:
            continue
        app = str(data.get("appName") or data.get("packageName") or "").strip()
        if not app:
            continue
        key = (app, _clock(at))
        if key in seen_fg:
            continue
        seen_fg.add(key)
        foreground_lines.append(f"{_clock(at)} 打开{app}")
    if foreground_lines:
        return foreground_lines[-6:]

    screen_lines: list[str] = []
    for item in _history_screen_events(history):
        at = item.get("at")
        if not at or at < since_dt or at > now_dt:
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if _is_screen_on(data):
            screen_lines.append(f"{_clock(at)} 亮屏")
        elif _is_screen_off(data):
            screen_lines.append(f"{_clock(at)} 熄屏")
    return screen_lines[-4:]


def _build_no_reply_soft_trigger(doc: dict, history: list[dict], window_id: str, now_dt) -> TriggerEvent | None:
    latest = _latest_normal_chat_round(window_id)
    if not latest:
        return None
    round_dt = _dt(latest.get("timestamp"))
    if not round_dt:
        return None
    elapsed = _minutes_between(round_dt, now_dt)
    if elapsed < _NO_REPLY_SOFT_TRIGGER_AFTER_MINUTES or elapsed > _NO_REPLY_SOFT_TRIGGER_MAX_MINUTES:
        return None
    if _has_user_reply_after(round_dt):
        return None
    if _user_announced_away(str(latest.get("user_text") or "")):
        return None
    activity_lines = _recent_app_activity_lines(doc, history, now_dt)
    if not activity_lines:
        return None
    fact = (
        f"她已经大约 {elapsed} 分钟没有回你了。"
        f"她刚才没有说要去做别的事。过去半小时手机活动："
        + "；".join(activity_lines)
        + "。"
    )
    key_tail = latest.get("index") or latest.get("timestamp") or round_dt.isoformat()
    return TriggerEvent(
        "no_reply_30m_app_activity",
        f"no_reply_30m_app_activity:{window_id}:{key_tail}",
        fact,
        device_id=_device_id(doc),
        event_at=now_beijing_iso(),
    )


def _read_state() -> dict:
    client = r2_store._s3_client()
    if not client:
        return {}
    data = r2_store._read_json(client, _STATE_KEY)
    return data if isinstance(data, dict) else {}


def _write_state(state: dict) -> bool:
    client = r2_store._s3_client()
    if not client:
        return False
    with r2_store._global_write_lock:
        fired = state.get("fired") if isinstance(state.get("fired"), dict) else {}
        if len(fired) > _STATE_MAX_FIRED:
            keep = sorted(fired.items(), key=lambda kv: str((kv[1] or {}).get("at") or ""))[-_STATE_MAX_FIRED:]
            state["fired"] = dict(keep)
        r2_store._write_json(client, _STATE_KEY, state)
        return True


def _already_fired(state: dict, key: str) -> bool:
    fired = state.get("fired") if isinstance(state.get("fired"), dict) else {}
    return key in fired


def _mark_fired(state: dict, event: TriggerEvent, result: dict) -> None:
    fired = state.get("fired") if isinstance(state.get("fired"), dict) else {}
    fired[event.dedupe_key] = {
        "at": now_beijing_iso(),
        "trigger_type": event.trigger_type,
        "event_at": event.event_at,
        "ok": bool((result or {}).get("ok")),
        "error": str((result or {}).get("error") or ""),
    }
    state["fired"] = fired
    _write_state(state)


def _mark_fired_if_delivered(state: dict, event: TriggerEvent, result: dict) -> bool:
    if not bool((result or {}).get("ok")):
        logger.warning(
            "主动硬触发未送达，不消耗去重 key type=%s key=%s error=%s",
            event.trigger_type,
            event.dedupe_key,
            str((result or {}).get("error") or ""),
        )
        return False
    _mark_fired(state, event, result)
    return True


def _build_events(doc: dict, history: list[dict], window_id: str, now_dt) -> list[TriggerEvent]:
    events: list[TriggerEvent] = []
    device_id = _device_id(doc)
    screen_events = _history_screen_events(history)
    latest_on = _latest_screen_on(screen_events)
    foreground = _foreground_label(doc)

    if latest_on:
        on_at = latest_on["at"]
        prev_off = _previous_screen_off(screen_events, on_at)
        latest_on_data = latest_on.get("data") if isinstance(latest_on.get("data"), dict) else {}
        off_minutes = _screen_off_minutes(prev_off, on_at, latest_on_data)
        event_at = on_at.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        if (
            on_at.strftime("%Y-%m-%d") == now_dt.strftime("%Y-%m-%d")
            and _MORNING_START_HOUR <= on_at.hour < _MORNING_END_HOUR
            and off_minutes >= _MIN_MORNING_OFF_MINUTES
        ):
            events.append(
                TriggerEvent(
                    "morning_first_screen_on",
                    f"morning_first_screen_on:{on_at.strftime('%Y-%m-%d')}",
                    "小玥刚刚屏幕亮了一下，可能是睡醒了。",
                    device_id=device_id,
                    event_at=event_at,
                )
            )
        if on_at.hour < _NIGHT_REAWAKE_END_HOUR and off_minutes >= _MIN_NIGHT_OFF_MINUTES:
            events.append(
                TriggerEvent(
                    "night_reawake_screen_on",
                    f"night_reawake_screen_on:{event_at}",
                    "小玥刚刚屏幕亮了一下，可能是半夜醒了。",
                    device_id=device_id,
                    event_at=event_at,
                )
            )

    if _is_screen_currently_on(doc):
        sleep = _latest_sleep_message(window_id)
        sleep_dt = _dt((sleep or {}).get("timestamp"))
        elapsed = _minutes_between(sleep_dt, now_dt)
        if (
            sleep
            and sleep_dt
            and _SLEEP_STILL_AWAKE_AFTER_MINUTES <= elapsed <= _SLEEP_STILL_AWAKE_MAX_MINUTES
            and not _has_normal_user_chat_after(window_id, sleep_dt)
        ):
            app_tail = f"，前台是{foreground}" if foreground else ""
            events.append(
                TriggerEvent(
                    "sleep_intent_still_screen_on",
                    f"sleep_intent_still_screen_on:{window_id}:{sleep.get('index') or sleep.get('timestamp')}",
                    f"她半小时前说了睡觉，但现在屏幕还亮着{app_tail}。",
                    device_id=device_id,
                    event_at=now_beijing_iso(),
                )
            )

    xhs_minutes, xhs_started_at = _active_xhs_minutes(doc, now_dt)
    if xhs_minutes >= _XHS_LONG_USE_MINUTES:
        events.append(
            TriggerEvent(
                "xiaohongshu_over_2h",
                f"xiaohongshu_over_2h:{xhs_started_at}",
                f"她已经连续刷小红书大约 {xhs_minutes} 分钟。",
                device_id=device_id,
                event_at=now_beijing_iso(),
            )
        )
    soft_no_reply = _build_no_reply_soft_trigger(doc, history, window_id, now_dt)
    if soft_no_reply:
        events.append(soft_no_reply)
    return events


def tick_proactive_triggers(target_user_id: int = 0) -> dict:
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id", "sent": False}
    now_dt = _now_dt()
    if not now_dt:
        return {"ok": False, "error": "time_parse_failed", "sent": False}
    window_id = f"tg_{uid}"
    doc = r2_store.get_sense_latest() or {}
    if not isinstance(doc, dict) or not doc:
        return {"ok": True, "sent": False, "skip_reason": "no_sense"}
    today = now_dt.strftime("%Y-%m-%d")
    yesterday = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    history: list[dict] = []
    if now_dt.hour < _NIGHT_REAWAKE_END_HOUR:
        history.extend(r2_store.get_sense_history_for_date(yesterday, limit=_SENSE_TRIGGER_YESTERDAY_LIMIT) or [])
    history.extend(r2_store.get_sense_history_for_date(today, limit=_SENSE_TRIGGER_HISTORY_LIMIT) or [])
    state = _read_state()
    suppress_reason = _recent_normal_chat_suppress_reason(window_id, now_dt)
    if suppress_reason:
        return {"ok": True, "sent": False, "skip_reason": "recent_normal_chat", "detail": suppress_reason}
    events = sorted(
        _build_events(doc, history, window_id, now_dt),
        key=lambda e: _EVENT_PRIORITY.get(e.trigger_type, 999),
    )
    for event in events:
        if _already_fired(state, event.dedupe_key):
            continue
        try:
            from services.conversation_followup import send_proactive_trigger_wakeup

            result = send_proactive_trigger_wakeup(
                window_id=window_id,
                target=event.device_id,
                event_text=event.text(),
                created_at=event.event_at or now_beijing_iso(),
            )
        except Exception as e:
            logger.warning("主动硬触发唤醒异常 type=%s error=%s", event.trigger_type, e, exc_info=True)
            result = {"ok": False, "error": str(e)}
        _mark_fired_if_delivered(state, event, result)
        return {
            "ok": True,
            "sent": bool(result.get("ok")),
            "trigger_type": event.trigger_type,
            "event_at": event.event_at,
            "error": str(result.get("error") or ""),
            "preview": str(result.get("reply_preview") or "")[:120],
        }
    return {"ok": True, "sent": False, "skip_reason": "no_due_trigger"}
