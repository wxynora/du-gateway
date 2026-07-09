from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing, today_beijing

logger = get_logger(__name__)

_MAX_LOOKBACK_HOURS = 24
_MIN_FRAME_GAP_MINUTES = 20
_MAX_LINES = 6


def _dt(raw: Any):
    return parse_iso_to_beijing(str(raw or "").strip())


def _clock(dt) -> str:
    return dt.strftime("%H:%M") if dt else ""


def _num(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _format_gap(minutes: int) -> str:
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}分钟"
    hours = minutes // 60
    rest = minutes % 60
    if hours < 24:
        return f"{hours}小时{rest}分钟" if rest else f"{hours}小时"
    days = hours // 24
    rest_h = hours % 24
    return f"{days}天{rest_h}小时" if rest_h else f"{days}天"


def _event_dt(row: dict) -> Optional[object]:
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    return (
        _dt(data.get("occurredAt"))
        or _dt(data.get("observedAt"))
        or _dt(data.get("capturedAt"))
        or _dt(data.get("updatedAt"))
        or _dt(row.get("at"))
    )


def _latest_previous_round_at(window_id: str) -> Optional[object]:
    try:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=1) or []
    except Exception as e:
        logger.debug("wakeup_frame previous round lookup skipped error=%s", e)
        return None
    if not rounds:
        return None
    return _dt((rounds[-1] or {}).get("timestamp"))


def _anchor_dt(window_id: str, now_dt) -> Optional[object]:
    candidates = []
    previous_round_dt = _latest_previous_round_at(window_id)
    if previous_round_dt:
        candidates.append(previous_round_dt)
    try:
        proactive_dt = _dt(r2_store.get_last_proactive_contact_at())
        if proactive_dt:
            candidates.append(proactive_dt)
    except Exception:
        pass
    try:
        user_dt = _dt(r2_store.get_last_user_activity_at())
        if user_dt and (now_dt - user_dt).total_seconds() > 5 * 60:
            candidates.append(user_dt)
    except Exception:
        pass
    if not candidates:
        return None
    anchor = max(candidates)
    if (now_dt - anchor).total_seconds() > _MAX_LOOKBACK_HOURS * 3600:
        return now_dt - timedelta(hours=_MAX_LOOKBACK_HOURS)
    return anchor


def _history_since(start_dt, now_dt) -> list[dict]:
    days = {today_beijing()}
    days.add(start_dt.strftime("%Y-%m-%d"))
    rows: list[dict] = []
    for day in sorted(days):
        try:
            rows.extend(r2_store.get_sense_history_for_date(day, limit=240) or [])
        except Exception as e:
            logger.debug("wakeup_frame sense history skipped day=%s error=%s", day, e)
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        at = _event_dt(row)
        if at and start_dt < at <= now_dt:
            copied = dict(row)
            copied["_dt"] = at
            out.append(copied)
    out.sort(key=lambda x: x.get("_dt"))
    return out


def _rows_of(rows: list[dict], sense_type: str) -> list[dict]:
    return [r for r in rows if str(r.get("type") or "").strip() == sense_type]


def _data(row: dict) -> dict:
    data = row.get("data")
    return data if isinstance(data, dict) else {}


def _format_battery(rows: list[dict], latest: dict) -> str:
    items = _rows_of(rows, "battery")
    if not items:
        return ""
    first = _data(items[0])
    last = _data(items[-1])
    first_level = _num(first.get("level"))
    last_level = _num(last.get("level"))
    if last_level is None:
        return ""
    parts = []
    if first_level is not None and first_level != last_level:
        delta = last_level - first_level
        parts.append(f"电量 {first_level}% -> {last_level}%（{delta:+d}%）")
    else:
        parts.append(f"电量现在 {last_level}%")
    first_ch = first.get("charging")
    last_ch = last.get("charging")
    if str(first_ch) != str(last_ch):
        parts.append("充电状态变过")
    return "，".join(parts)


def _format_health(rows: list[dict], latest: dict) -> list[str]:
    items = _rows_of(rows, "health")
    if not items:
        return []
    first = _data(items[0])
    last = _data(items[-1])
    lines = []
    first_steps = _num(first.get("steps"))
    last_steps = _num(last.get("steps"))
    if first_steps is not None and last_steps is not None:
        delta = max(0, last_steps - first_steps)
        if delta:
            lines.append(f"步数 +{delta}（{first_steps} -> {last_steps}）")
        else:
            lines.append(f"步数仍是 {last_steps}")
    elif last_steps is not None:
        lines.append(f"步数现在 {last_steps}")
    first_hr = _num(first.get("heart_rate"))
    last_hr = _num(last.get("heart_rate"))
    if first_hr is not None and last_hr is not None:
        if first_hr != last_hr:
            lines.append(f"心率 {first_hr} -> {last_hr}")
        else:
            lines.append(f"心率仍是 {last_hr}")
    elif last_hr is not None:
        lines.append(f"心率现在 {last_hr}")
    return lines


def _screen_label(data: dict) -> str:
    event = str(data.get("event") or "").strip().lower()
    return {
        "screen_on": "亮屏",
        "screen_off": "熄屏",
        "user_present": "解锁",
        "app_active": "打开 SumiTalk",
    }.get(event, "")


def _format_screen(rows: list[dict], latest: dict) -> str:
    items = _rows_of(rows, "screen")
    labels = []
    on_count = 0
    off_count = 0
    for row in items:
        label = _screen_label(_data(row))
        if not label:
            continue
        labels.append((row.get("_dt"), label))
        if label in {"亮屏", "解锁", "打开 SumiTalk"}:
            on_count += 1
        elif label == "熄屏":
            off_count += 1
    if not labels:
        return ""
    latest_dt, latest_label = labels[-1]
    parts = []
    if on_count:
        parts.append(f"亮屏/解锁 {on_count} 次")
    if off_count:
        parts.append(f"熄屏 {off_count} 次")
    suffix = f"最新 {_clock(latest_dt)} {latest_label}" if latest_label else ""
    if suffix:
        parts.append(suffix)
    return "，".join(parts)


def _format_foreground(rows: list[dict], latest: dict) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for row in _rows_of(rows, "foreground"):
        data = _data(row)
        name = str(data.get("appName") or data.get("packageName") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    if not names:
        return ""
    return "前台切到过：" + "、".join(names[-4:])


def _format_location(rows: list[dict], latest: dict) -> str:
    items = _rows_of(rows, "location")
    if not items:
        return ""
    last = _data(items[-1])
    addr = str(last.get("address") or "").strip()
    if addr:
        return f"位置更新到：{addr}"
    lat = last.get("lat")
    lng = last.get("lng")
    if lat is not None and lng is not None:
        return "位置有更新"
    return ""


def format_wakeup_frame_for_system(window_id: str) -> str:
    now_dt = _dt(now_beijing_iso())
    if not now_dt:
        return ""
    start_dt = _anchor_dt(window_id, now_dt)
    if not start_dt:
        return ""
    gap_minutes = int((now_dt - start_dt).total_seconds() // 60)
    if gap_minutes < _MIN_FRAME_GAP_MINUTES:
        return ""
    rows = _history_since(start_dt, now_dt)
    try:
        latest = r2_store.get_sense_latest() or {}
    except Exception:
        latest = {}
    lines: list[str] = []
    battery = _format_battery(rows, latest)
    if battery:
        lines.append(battery)
    lines.extend(_format_health(rows, latest))
    screen = _format_screen(rows, latest)
    if screen:
        lines.append(screen)
    foreground = _format_foreground(rows, latest)
    if foreground:
        lines.append(foreground)
    location = _format_location(rows, latest)
    if location:
        lines.append(location)

    header = [
        "【醒来补帧（仅你与网关可见）】",
        f"距离你上次醒来大约 {_format_gap(gap_minutes)}。",
    ]
    if lines:
        header.append("这段空白里的感知变化：")
        header.extend(f"- {line}" for line in lines[:_MAX_LINES])
    else:
        header.append("这段空白里没有记录到明显的感知变化。")
    header.append("这些只是时间感补帧，不是小玥刚刚说的话；当前状态仍以【老婆当前状态】为准。")
    return "\n".join(header).strip()
