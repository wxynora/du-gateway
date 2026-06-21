"""Small R2 cache for recent chat activity rhythm."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing, today_beijing

R2_KEY_CHAT_ACTIVITY_CONTEXT = "global/chat_activity_context.json"
CHAT_ACTIVITY_SCHEMA_VERSION = 2
CHAT_ACTIVITY_KEEP_DAYS = 4

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Any:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _primary_window_id() -> str:
    try:
        uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    except Exception:
        uid = 0
    return f"tg_{uid}" if uid > 0 else ""


def _dt(value: Any):
    return parse_iso_to_beijing(str(value or "").strip())


def _iso(value: Any) -> str:
    dt = _dt(value) or _dt(now_beijing_iso())
    if not dt:
        return ""
    return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _date_after(day: str, delta_days: int) -> str:
    dt = _dt(f"{day}T00:00:00+08:00")
    if not dt:
        return day
    return (dt + timedelta(days=delta_days)).strftime("%Y-%m-%d")


def _has_user_turn(messages: list) -> bool:
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() == "user":
            return True
    return False


def _normalize_days(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for day, values in raw.items():
        clean_day = str(day or "").strip()
        if not clean_day:
            continue
        rows: list[str] = []
        if isinstance(values, list):
            for value in values:
                iso = _iso(value)
                if iso:
                    rows.append(iso)
        out[clean_day] = sorted(set(rows))
    return out


def _prune_days(days: dict[str, list[str]], today: str) -> dict[str, list[str]]:
    keep = {_date_after(today, -i) for i in range(CHAT_ACTIVITY_KEEP_DAYS)}
    return {day: days.get(day, []) for day in sorted(keep) if day in days}


def get_chat_activity_context() -> dict:
    """Read cached three-day chat activity context."""
    client = _s3_client()
    if not client:
        return {}
    try:
        data = _read_json(client, R2_KEY_CHAT_ACTIVITY_CONTEXT)
    except Exception as e:
        logger.warning("chat_activity_context read failed error=%s", e)
        return {}
    return data if isinstance(data, dict) else {}


def save_chat_activity_context(payload: dict) -> bool:
    """Save cached chat activity context; keep caller payload compact."""
    if not isinstance(payload, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        _write_json(client, R2_KEY_CHAT_ACTIVITY_CONTEXT, payload)
        return True
    except Exception as e:
        logger.warning("chat_activity_context save failed error=%s", e)
        return False


def append_chat_activity_round(window_id: str, timestamp: str, messages: list) -> bool:
    """Incrementally record one human chat round timestamp for the primary window."""
    primary = _primary_window_id()
    if not primary or str(window_id or "").strip() != primary:
        return False
    if not _has_user_turn(messages if isinstance(messages, list) else []):
        return False
    iso = _iso(timestamp)
    dt = _dt(iso)
    if not iso or not dt:
        return False
    day = dt.strftime("%Y-%m-%d")
    client = _s3_client()
    if not client:
        return False
    try:
        payload = get_chat_activity_context()
        days = _normalize_days(payload.get("days"))
        days.setdefault(day, [])
        if iso not in days[day]:
            days[day].append(iso)
            days[day] = sorted(days[day])
        today = today_beijing()
        payload.update(
            {
                "schema_version": CHAT_ACTIVITY_SCHEMA_VERSION,
                "window_id": primary,
                "updated_at": now_beijing_iso(),
                "days": _prune_days(days, today),
                "records": [],
                "line": "",
            }
        )
        _write_json(client, R2_KEY_CHAT_ACTIVITY_CONTEXT, payload)
        return True
    except Exception as e:
        logger.warning("chat_activity_context append failed window_id=%s error=%s", window_id, e)
        return False
