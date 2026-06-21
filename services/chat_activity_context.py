"""Conversation rhythm facts for dynamic system sense context."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from storage import chat_activity_store, r2_store
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing, today_beijing

logger = get_logger(__name__)

_LOOKBACK_DAYS = 4
_KEEP_RECORDS = 3
_MAX_ROUNDS_SCAN = 300
_CACHE_TTL_SECONDS = 5 * 60
_DROP_RATIO = 0.68
_DROP_MIN_DIFF = 12
_RISE_RATIO = 1.35
_RISE_MIN_DIFF = 12
_SCHEMA_VERSION = chat_activity_store.CHAT_ACTIVITY_SCHEMA_VERSION


def _primary_window_id() -> str:
    try:
        uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    except Exception:
        uid = 0
    return f"tg_{uid}" if uid > 0 else ""


def _date_start(day: str) -> datetime | None:
    try:
        return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
    except Exception:
        return None


def _date_after(day: str, delta_days: int) -> str:
    start = _date_start(day)
    if not start:
        return day
    return (start + timedelta(days=delta_days)).strftime("%Y-%m-%d")


def _dt(value: Any) -> datetime | None:
    return parse_iso_to_beijing(str(value or "").strip())


def _int_minutes(value: Any, fallback_ms: Any = None) -> int:
    try:
        n = int(value or 0)
    except Exception:
        n = 0
    if n > 0:
        return n
    try:
        ms = int(fallback_ms or 0)
    except Exception:
        ms = 0
    return max(0, ms // 60000)


def _add_sleep_summary(out: dict[str, dict], raw: Any) -> None:
    if not isinstance(raw, dict):
        return
    start = _dt(raw.get("startAt"))
    end = _dt(raw.get("endAt"))
    if not start or not end or end <= start:
        return
    total_minutes = _int_minutes(raw.get("totalMinutes"), raw.get("totalDurationMs"))
    if total_minutes <= 0:
        total_minutes = max(0, int((end - start).total_seconds() // 60))
    if total_minutes < 45:
        return
    night_date = str(raw.get("nightDate") or end.strftime("%Y-%m-%d")).strip()
    if not night_date:
        return
    prev = out.get(night_date)
    # Keep the newest summary for a night; sense snapshots often repeat the same summary.
    if prev and _dt(prev.get("end_at")) and (_dt(prev.get("end_at")) or end) >= end:
        return
    out[night_date] = {
        "night_date": night_date,
        "start_at": start.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "end_at": end.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "total_minutes": total_minutes,
    }


def _collect_sleep_summaries(latest_sense: dict | None, today: str) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    screen = (latest_sense or {}).get("screen") if isinstance(latest_sense, dict) else {}
    if isinstance(screen, dict):
        _add_sleep_summary(summaries, screen.get("sleepSummary"))

    for i in range(_LOOKBACK_DAYS + 1):
        day = _date_after(today, -i)
        try:
            history = r2_store.get_sense_history_for_date(day, limit=240) or []
        except Exception as e:
            logger.debug("chat_activity sense history skipped day=%s error=%s", day, e)
            history = []
        for row in history:
            if not isinstance(row, dict):
                continue
            if str(row.get("type") or "").strip() != "screen":
                continue
            data = row.get("data")
            if isinstance(data, dict):
                _add_sleep_summary(summaries, data.get("sleepSummary"))
    return summaries


def _has_human_user_turn(round_row: dict) -> bool:
    for msg in (round_row.get("messages") or []):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() == "user":
            return True
    return False


def _round_timestamp(round_row: dict) -> datetime | None:
    if not isinstance(round_row, dict):
        return None
    return _dt(round_row.get("timestamp"))


def _count_rounds_between(rounds: list[dict], start: datetime, end: datetime) -> int:
    count = 0
    for row in rounds or []:
        if not isinstance(row, dict) or not _has_human_user_turn(row):
            continue
        ts = _round_timestamp(row)
        if ts and start <= ts < end:
            count += 1
    return count


def _event_datetimes_from_days(days: Any) -> list[datetime]:
    if not isinstance(days, dict):
        return []
    out: list[datetime] = []
    for values in days.values():
        if not isinstance(values, list):
            continue
        for value in values:
            dt = _dt(value)
            if dt:
                out.append(dt)
    return sorted(out)


def _count_events_between(events: list[datetime], start: datetime, end: datetime) -> int:
    return sum(1 for dt in events if start <= dt < end)


def _cycle_bounds(day: str, today: str, summaries: dict[str, dict], now_dt: datetime) -> tuple[datetime, datetime, str]:
    day_start = _date_start(day)
    if not day_start:
        day_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    source = "calendar_day"

    summary = summaries.get(day)
    if summary:
        wake = _dt(summary.get("end_at"))
        if wake and day_start - timedelta(hours=8) <= wake < day_end:
            day_start = wake
            source = "sleep_cycle"

    next_summary = summaries.get(_date_after(day, 1))
    if next_summary:
        sleep_start = _dt(next_summary.get("start_at"))
        if sleep_start and day_start < sleep_start <= day_end + timedelta(hours=8):
            day_end = sleep_start
            source = "sleep_cycle"

    if day == today:
        day_end = min(day_end, now_dt)
    if day_end <= day_start:
        fallback_start = _date_start(day) or day_start
        day_start = fallback_start
        day_end = min(fallback_start + timedelta(days=1), now_dt) if day == today else fallback_start + timedelta(days=1)
        source = "calendar_day"
    return day_start, day_end, source


def _record_label(day: str, today: str) -> str:
    if day == today:
        return "今天"
    if day == _date_after(today, -1):
        return "昨天"
    if day == _date_after(today, -2):
        return "前天"
    return day


def _build_records(rounds: list[dict], summaries: dict[str, dict], today: str, now_dt: datetime) -> list[dict]:
    records: list[dict] = []
    for offset in range(_KEEP_RECORDS - 1, -1, -1):
        day = _date_after(today, -offset)
        start, end, source = _cycle_bounds(day, today, summaries, now_dt)
        records.append(
            {
                "date": day,
                "label": _record_label(day, today),
                "start_at": start.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "end_at": end.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "rounds": _count_rounds_between(rounds, start, end),
                "source": source,
            }
        )
    return records[-_KEEP_RECORDS:]


def _build_records_from_events(events: list[datetime], summaries: dict[str, dict], today: str, now_dt: datetime) -> list[dict]:
    records: list[dict] = []
    for offset in range(_KEEP_RECORDS - 1, -1, -1):
        day = _date_after(today, -offset)
        start, end, source = _cycle_bounds(day, today, summaries, now_dt)
        records.append(
            {
                "date": day,
                "label": _record_label(day, today),
                "start_at": start.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "end_at": end.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "rounds": _count_events_between(events, start, end),
                "source": source,
            }
        )
    return records[-_KEEP_RECORDS:]


def _format_change(today_count: int, previous_count: int) -> str:
    if previous_count <= 0:
        return ""
    diff = today_count - previous_count
    if diff <= -_DROP_MIN_DIFF and today_count <= int(previous_count * _DROP_RATIO):
        return "今天明显少一些"
    if diff >= _RISE_MIN_DIFF and today_count >= int(previous_count * _RISE_RATIO):
        return "今天明显多一些"
    return ""


def _current_record_text(record: dict) -> str:
    label = str(record.get("label") or "今天")
    count = int(record.get("rounds") or 0)
    if str(record.get("source") or "") == "sleep_cycle":
        return f"{label}从醒来到现在对话约 {count} 轮"
    return f"{label}到现在对话约 {count} 轮"


def _previous_record_text(record: dict) -> str:
    label = str(record.get("label") or "昨天")
    count = int(record.get("rounds") or 0)
    if str(record.get("source") or "") == "sleep_cycle":
        return f"{label}醒来到睡前对话约 {count} 轮"
    return f"{label}全天对话约 {count} 轮"


def _format_line(records: list[dict]) -> str:
    if not records:
        return ""
    current = records[-1]
    previous = records[-2] if len(records) >= 2 else None
    current_count = int(current.get("rounds") or 0)
    parts = [_current_record_text(current)]
    if previous:
        previous_count = int(previous.get("rounds") or 0)
        change = _format_change(current_count, previous_count)
        if change:
            parts.append(_previous_record_text(previous))
            parts.append(change)
    return "对话节律：" + "；".join(parts) + "。"


def _cached_line_if_fresh(window_id: str, today: str, now_dt: datetime) -> str:
    try:
        cached = chat_activity_store.get_chat_activity_context()
    except Exception as e:
        logger.debug("chat_activity cache read skipped error=%s", e)
        return ""
    if not isinstance(cached, dict):
        return ""
    if int(cached.get("schema_version") or 0) != _SCHEMA_VERSION:
        return ""
    if str(cached.get("window_id") or "").strip() != window_id:
        return ""
    line = str(cached.get("line") or "").strip()
    if not line:
        return ""
    records = cached.get("records")
    if not isinstance(records, list) or not records:
        return ""
    latest = records[-1] if isinstance(records[-1], dict) else {}
    if str(latest.get("date") or "").strip() != today:
        return ""
    updated = _dt(cached.get("updated_at"))
    if not updated:
        return ""
    age_seconds = (now_dt - updated).total_seconds()
    if 0 <= age_seconds <= _CACHE_TTL_SECONDS:
        return line
    return ""


def _required_recent_days(today: str) -> set[str]:
    # Keep one extra calendar day because sleep-cycle days can cross midnight.
    return {_date_after(today, -i) for i in range(_KEEP_RECORDS + 1)}


def _days_cover_recent_window(days: Any, today: str) -> bool:
    if not isinstance(days, dict):
        return False
    return _required_recent_days(today).issubset({str(k or "").strip() for k in days.keys()})


def _days_from_rounds(rounds: list[dict], today: str) -> dict[str, list[str]]:
    required = _required_recent_days(today)
    days: dict[str, list[str]] = {day: [] for day in required}
    for row in rounds or []:
        if not isinstance(row, dict) or not _has_human_user_turn(row):
            continue
        ts = _round_timestamp(row)
        if not ts:
            continue
        day = ts.strftime("%Y-%m-%d")
        if day not in required:
            continue
        days.setdefault(day, [])
        iso = ts.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        if iso not in days[day]:
            days[day].append(iso)
    return {day: sorted(values) for day, values in days.items()}


def build_chat_activity_context_line(latest_sense: dict | None = None) -> str:
    """Build and cache a concise objective chat-rhythm line for sense context."""
    window_id = _primary_window_id()
    if not window_id:
        return ""
    now_dt = _dt(now_beijing_iso())
    if not now_dt:
        return ""
    today = today_beijing()
    cached_line = _cached_line_if_fresh(window_id, today, now_dt)
    if cached_line:
        return cached_line
    try:
        cached = chat_activity_store.get_chat_activity_context()
    except Exception as e:
        logger.debug("chat_activity cache load skipped error=%s", e)
        cached = {}
    days = cached.get("days") if isinstance(cached, dict) else {}
    if int((cached or {}).get("schema_version") or 0) != _SCHEMA_VERSION or str((cached or {}).get("window_id") or "").strip() != window_id:
        days = {}
    try:
        if not _days_cover_recent_window(days, today):
            rounds = r2_store.get_conversation_rounds(window_id, last_n=_MAX_ROUNDS_SCAN) or []
            days = _days_from_rounds(rounds, today)
    except Exception as e:
        logger.debug("chat_activity bootstrap rounds skipped window_id=%s error=%s", window_id, e)
    summaries = _collect_sleep_summaries(latest_sense, today)
    events = _event_datetimes_from_days(days)
    records = _build_records_from_events(events, summaries, today, now_dt)
    line = _format_line(records)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "window_id": window_id,
        "updated_at": now_beijing_iso(),
        "days": days,
        "records": records[-_KEEP_RECORDS:],
        "line": line,
    }
    try:
        chat_activity_store.save_chat_activity_context(payload)
    except Exception as e:
        logger.debug("chat_activity cache save skipped error=%s", e)
    return line
