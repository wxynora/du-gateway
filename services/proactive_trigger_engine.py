from __future__ import annotations

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

_SLEEP_PATTERNS = (
    "我要睡",
    "我去睡",
    "准备睡",
    "先睡",
    "睡觉",
    "睡了",
    "睡啦",
    "晚安",
)

_XHS_PACKAGES = {"com.xingin.xhs"}
_XHS_NAME_HINTS = ("小红书", "xiaohongshu", "xhs", "rednote")
_EVENT_PRIORITY = {
    "sleep_intent_still_screen_on": 10,
    "night_reawake_screen_on": 20,
    "morning_first_screen_on": 30,
    "xiaohongshu_over_2h": 40,
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


def _screen_off_minutes(prev_off: dict | None, on_at: datetime) -> int:
    if not prev_off:
        return 0
    data = prev_off.get("data") if isinstance(prev_off.get("data"), dict) else {}
    try:
        duration_ms = int(data.get("screenOffDurationMs") or 0)
    except Exception:
        duration_ms = 0
    if duration_ms > 0:
        return max(0, int(duration_ms // 60000))
    off_at = _dt(data.get("screenOffSince") or data.get("occurredAt") or prev_off.get("at"))
    return _minutes_between(off_at, on_at)


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
            if text and any(p in text for p in _SLEEP_PATTERNS):
                return {"timestamp": ts, "index": idx, "text": text}
    return None


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


def _build_events(doc: dict, history: list[dict], window_id: str, now_dt) -> list[TriggerEvent]:
    events: list[TriggerEvent] = []
    device_id = _device_id(doc)
    screen_events = _history_screen_events(history)
    latest_on = _latest_screen_on(screen_events)
    foreground = _foreground_label(doc)

    if latest_on:
        on_at = latest_on["at"]
        prev_off = _previous_screen_off(screen_events, on_at)
        off_minutes = _screen_off_minutes(prev_off, on_at)
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
                    "她刚刚醒来，第一次打开手机。",
                    device_id=device_id,
                    event_at=event_at,
                )
            )
        if on_at.hour < _NIGHT_REAWAKE_END_HOUR and off_minutes >= _MIN_NIGHT_OFF_MINUTES:
            events.append(
                TriggerEvent(
                    "night_reawake_screen_on",
                    f"night_reawake_screen_on:{event_at}",
                    "她熄屏很久后半夜又点亮了手机。",
                    device_id=device_id,
                    event_at=event_at,
                )
            )

    if _is_screen_currently_on(doc):
        sleep = _latest_sleep_message(window_id)
        sleep_dt = _dt((sleep or {}).get("timestamp"))
        elapsed = _minutes_between(sleep_dt, now_dt)
        if sleep and _SLEEP_STILL_AWAKE_AFTER_MINUTES <= elapsed <= _SLEEP_STILL_AWAKE_MAX_MINUTES:
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
    history = (r2_store.get_sense_history_for_date(yesterday) or []) + (r2_store.get_sense_history_for_date(today) or [])
    state = _read_state()
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
        _mark_fired(state, event, result)
        return {
            "ok": True,
            "sent": bool(result.get("ok")),
            "trigger_type": event.trigger_type,
            "event_at": event.event_at,
            "error": str(result.get("error") or ""),
            "preview": str(result.get("reply_preview") or "")[:120],
        }
    return {"ok": True, "sent": False, "skip_reason": "no_due_trigger"}
