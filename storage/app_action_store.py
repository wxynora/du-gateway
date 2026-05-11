"""R2 storage helpers for SumiTalk native app actions."""
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

from utils.log import get_logger
from utils.time_aware import BEIJING_TZ

R2_KEY_APP_ACTION_QUEUE = "sumitalk/app_actions.json"

_APP_ACTION_ALLOWLIST = {
    "create_system_alarm",
    "create_calendar_event",
    "show_choice_dialog",
    "show_system_notification",
    "request_screen_check",
}
_APP_ACTION_HISTORY_MAX = 100
_APP_ACTION_EXPIRES_DEFAULT = 900
_APP_ACTION_EXPIRES_MIN = 30
_APP_ACTION_EXPIRES_MAX = 3600
_APP_ACTION_LEASE_SECONDS = 90
_APP_ACTION_MAX_RETRY = 3

_app_action_write_lock = threading.Lock()

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_iso(value: str) -> Optional[datetime]:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _app_action_queue_raw(client) -> dict:
    data = _read_json(client, R2_KEY_APP_ACTION_QUEUE)
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("pending"), list):
        data["pending"] = []
    if not isinstance(data.get("history"), list):
        data["history"] = []
    if not isinstance(data.get("idempotencyKeys"), dict):
        data["idempotencyKeys"] = {}
    return data


def _trim_app_action_history(history: list) -> list:
    rows = [x for x in (history or []) if isinstance(x, dict)]
    rows.sort(key=lambda x: str(x.get("finishedAt") or x.get("createdAt") or ""), reverse=True)
    return rows[:_APP_ACTION_HISTORY_MAX]


def _parse_app_action_datetime(value) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    return dt


def _normalize_calendar_event_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or src.get("summary") or "渡的行程").strip() or "渡的行程"
    if len(title) > 120:
        title = title[:120]
    all_day = bool(src.get("allDay") if "allDay" in src else src.get("all_day", False))
    start = _parse_app_action_datetime(src.get("startAt") or src.get("start_at") or src.get("start_datetime") or src.get("datetime"))
    if not start:
        return None, "start_datetime/startAt 必须是 ISO 时间"

    end = _parse_app_action_datetime(src.get("endAt") or src.get("end_at") or src.get("end_datetime"))
    if not end:
        try:
            duration_minutes = int(src.get("durationMinutes") if "durationMinutes" in src else src.get("duration_minutes", 1440 if all_day else 60))
        except Exception:
            duration_minutes = 1440 if all_day else 60
        if duration_minutes <= 0:
            return None, "duration_minutes 必须大于 0"
        end = start + timedelta(minutes=duration_minutes)
    if end <= start:
        return None, "end_datetime 必须晚于 start_datetime"

    description = str(src.get("description") or src.get("note") or "").strip()
    if len(description) > 1000:
        description = description[:1000]
    location = str(src.get("location") or "").strip()
    if len(location) > 200:
        location = location[:200]
    try:
        reminder_minutes = int(src.get("reminderMinutes") if "reminderMinutes" in src else src.get("reminder_minutes", 10))
    except Exception:
        reminder_minutes = 10
    reminder_minutes = max(-1, min(10080, reminder_minutes))
    notify = bool(src.get("notify", True))

    start_bj = start.astimezone(BEIJING_TZ)
    end_bj = end.astimezone(BEIJING_TZ)
    return {
        "title": title,
        "startAt": start_bj.isoformat(),
        "endAt": end_bj.isoformat(),
        "startMillis": int(start.timestamp() * 1000),
        "endMillis": int(end.timestamp() * 1000),
        "allDay": all_day,
        "description": description,
        "location": location,
        "reminderMinutes": reminder_minutes,
        "notify": notify,
    }, None


def _normalize_app_action_payload(action_type: str, payload: dict) -> tuple[Optional[dict], Optional[str]]:
    if action_type == "create_calendar_event":
        return _normalize_calendar_event_payload(payload)
    if action_type == "show_choice_dialog":
        return _normalize_choice_dialog_payload(payload)
    if action_type == "show_system_notification":
        return _normalize_system_notification_payload(payload)
    if action_type == "request_screen_check":
        return _normalize_screen_check_payload(payload)
    if action_type != "create_system_alarm":
        return None, f"不支持的 app action: {action_type}"
    src = payload if isinstance(payload, dict) else {}
    try:
        hour = int(src.get("hour"))
    except Exception:
        return None, "hour 必须是 0-23"
    try:
        minute = int(src.get("minute"))
    except Exception:
        return None, "minute 必须是 0-59"
    if hour < 0 or hour > 23:
        return None, "hour 必须是 0-23"
    if minute < 0 or minute > 59:
        return None, "minute 必须是 0-59"
    title = str(src.get("title") or "渡的提醒").strip() or "渡的提醒"
    if len(title) > 80:
        title = title[:80]
    skip_ui = bool(src.get("skipUi") if "skipUi" in src else src.get("skip_ui", False))
    notify = bool(src.get("notify", True))
    return {
        "hour": hour,
        "minute": minute,
        "title": title,
        "skipUi": skip_ui,
        "notify": notify,
    }, None


def _normalize_choice_label(value, fallback: str) -> str:
    label = str(value or "").strip() or fallback
    if len(label) > 8:
        label = label[:8]
    return label


def _normalize_choice_dialog_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡").strip() or "渡"
    if len(title) > 60:
        title = title[:60]
    message = str(src.get("message") or src.get("content") or "").strip()
    if not message:
        return None, "message 不能为空"
    if len(message) > 500:
        message = message[:500]

    choice_a = src.get("choice_a") or src.get("choiceA") or src.get("positive")
    choice_b = src.get("choice_b") or src.get("choiceB") or src.get("negative")
    raw_choices = src.get("choices")
    if isinstance(raw_choices, list):
        if len(raw_choices) > 0:
            first = raw_choices[0]
            choice_a = first.get("label") if isinstance(first, dict) else first
        if len(raw_choices) > 1:
            second = raw_choices[1]
            choice_b = second.get("label") if isinstance(second, dict) else second
    label_a = _normalize_choice_label(choice_a, "好的")
    label_b = _normalize_choice_label(choice_b, "知道了")

    level = str(src.get("level") or "info").strip().lower()
    if level not in {"info", "warning", "strict"}:
        level = "info"
    dismissible = bool(src.get("dismissible", level != "strict"))
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 600))
    except Exception:
        timeout_seconds = 600
    timeout_seconds = max(30, min(1800, timeout_seconds))
    notify_du = bool(src.get("notifyDu") if "notifyDu" in src else src.get("notify_du", True))
    return {
        "title": title,
        "message": message,
        "level": level,
        "dismissible": dismissible,
        "timeoutSeconds": timeout_seconds,
        "notifyDu": notify_du,
        "choices": [
            {"id": "choice_a", "label": label_a},
            {"id": "choice_b", "label": label_b},
        ],
    }, None


def _normalize_system_notification_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "SumiTalk").strip() or "SumiTalk"
    if len(title) > 80:
        title = title[:80]
    message = str(src.get("message") or src.get("content") or "").strip()
    if not message:
        return None, "message 不能为空"
    if len(message) > 800:
        message = message[:800]
    level = str(src.get("level") or "info").strip().lower()
    if level not in {"info", "message", "success", "warning", "error"}:
        level = "info"
    category = str(src.get("category") or "").strip().lower()
    if category not in {"", "message", "status", "reminder", "event", "error"}:
        category = ""
    open_app = bool(src.get("openApp") if "openApp" in src else src.get("open_app", True))
    return {
        "title": title,
        "message": message,
        "level": level,
        "category": category,
        "openApp": open_app,
    }, None


def _normalize_screen_check_payload(payload: dict) -> tuple[Optional[dict], Optional[str]]:
    src = payload if isinstance(payload, dict) else {}
    title = str(src.get("title") or "渡想查岗").strip() or "渡想查岗"
    if len(title) > 60:
        title = title[:60]
    message = str(src.get("message") or src.get("reason") or "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。").strip()
    if not message:
        message = "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。"
    if len(message) > 500:
        message = message[:500]
    try:
        timeout_seconds = int(src.get("timeout_seconds") if "timeout_seconds" in src else src.get("timeoutSeconds", 120))
    except Exception:
        timeout_seconds = 120
    timeout_seconds = max(30, min(300, timeout_seconds))
    return {
        "title": title,
        "message": message,
        "timeoutSeconds": timeout_seconds,
    }, None


def _public_app_action(item: dict) -> dict:
    return {
        "id": str((item or {}).get("id") or ""),
        "type": str((item or {}).get("type") or ""),
        "payload": (item or {}).get("payload") if isinstance((item or {}).get("payload"), dict) else {},
    }


def _publish_app_action(item: dict) -> None:
    try:
        from services.realtime_publish import publish_device_actions

        publish_device_actions(
            device_id=str((item or {}).get("deviceId") or "").strip(),
            actions=[_public_app_action(item)],
        )
    except Exception as e:
        logger.debug("publish_app_action failed id=%s error=%s", str((item or {}).get("id") or ""), e)


def append_app_action(
    action_type: str,
    payload: dict,
    device_id: str = "",
    expires_in_sec: int = _APP_ACTION_EXPIRES_DEFAULT,
    source: str = "tool",
    idempotency_key: str = "",
) -> tuple[Optional[dict], Optional[str]]:
    """向 SumiTalk app 原生命令队列追加一条动作。"""
    action = str(action_type or "").strip()
    if action not in _APP_ACTION_ALLOWLIST:
        return None, f"不允许的 app action: {action}"
    normalized_payload, err = _normalize_app_action_payload(action, payload if isinstance(payload, dict) else {})
    if err:
        return None, err
    try:
        ttl = int(expires_in_sec or _APP_ACTION_EXPIRES_DEFAULT)
    except Exception:
        ttl = _APP_ACTION_EXPIRES_DEFAULT
    ttl = max(_APP_ACTION_EXPIRES_MIN, min(_APP_ACTION_EXPIRES_MAX, ttl))
    client = _s3_client()
    if not client:
        return None, "R2 不可用"

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")
    idem = str(idempotency_key or "").strip()
    item = {
        "id": str(uuid4()),
        "type": action,
        "payload": normalized_payload,
        "deviceId": str(device_id or "").strip(),
        "source": str(source or "tool").strip()[:40] or "tool",
        "createdAt": now_iso,
        "expiresAt": expires_at,
        "leasedUntil": "",
        "retryCount": 0,
    }
    with _app_action_write_lock:
        try:
            data = _app_action_queue_raw(client)
            idem_keys = data.get("idempotencyKeys") or {}
            if isinstance(idem_keys, dict):
                idem_keys = {
                    k: v for k, v in idem_keys.items()
                    if isinstance(v, dict) and _parse_utc_iso(str(v.get("expiresAt") or "")) and _parse_utc_iso(str(v.get("expiresAt") or "")) > now
                }
                data["idempotencyKeys"] = idem_keys
            if idem and isinstance(idem_keys, dict):
                existing_id = str((idem_keys.get(idem) or {}).get("id") or "").strip()
                if existing_id:
                    for old in data.get("pending") or []:
                        if isinstance(old, dict) and str(old.get("id") or "") == existing_id:
                            return {**old, "duplicate": True}, None
            pending = data.get("pending") if isinstance(data.get("pending"), list) else []
            pending.append(item)
            data["pending"] = pending
            if idem:
                idem_keys[idem] = {"id": item["id"], "expiresAt": expires_at}
                data["idempotencyKeys"] = idem_keys
            _write_json(client, R2_KEY_APP_ACTION_QUEUE, data)
            _publish_app_action(item)
            return item, None
        except Exception as e:
            logger.error("append_app_action 失败 type=%s error=%s", action, e, exc_info=True)
            return None, str(e)


def poll_app_actions(device_id: str = "", limit: int = 10) -> dict:
    """安卓壳轮询待执行 app 原生命令。"""
    device = str(device_id or "").strip()
    client = _s3_client()
    if not client:
        return {"ok": False, "actions": [], "pollAfterSec": 20, "error": "R2 不可用"}
    try:
        max_items = max(1, min(20, int(limit or 10)))
    except Exception:
        max_items = 10
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=_APP_ACTION_LEASE_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    with _app_action_write_lock:
        try:
            data = _app_action_queue_raw(client)
            pending = data.get("pending") if isinstance(data.get("pending"), list) else []
            history = data.get("history") if isinstance(data.get("history"), list) else []
            out = []
            next_pending = []
            changed = False
            for item in pending:
                if not isinstance(item, dict):
                    changed = True
                    continue
                exp = _parse_utc_iso(str(item.get("expiresAt") or ""))
                if exp and exp <= now:
                    history.append({**item, "status": "expired", "finishedAt": now_iso})
                    changed = True
                    continue
                target_device = str(item.get("deviceId") or "").strip()
                if target_device and device and target_device != device:
                    next_pending.append(item)
                    continue
                leased = _parse_utc_iso(str(item.get("leasedUntil") or ""))
                if leased and leased > now:
                    next_pending.append(item)
                    continue
                retry_count = int(item.get("retryCount") or 0)
                if leased and leased <= now:
                    retry_count += 1
                    item["retryCount"] = retry_count
                    changed = True
                if retry_count >= _APP_ACTION_MAX_RETRY:
                    history.append({**item, "status": "abandoned", "finishedAt": now_iso})
                    changed = True
                    continue
                if len(out) < max_items:
                    item["leasedUntil"] = lease_until
                    item["retryCount"] = retry_count
                    out.append(_public_app_action(item))
                    changed = True
                next_pending.append(item)
            if changed:
                data["pending"] = next_pending
                data["history"] = _trim_app_action_history(history)
                _write_json(client, R2_KEY_APP_ACTION_QUEUE, data)
            return {"ok": True, "actions": out, "pollAfterSec": 20}
        except Exception as e:
            logger.error("poll_app_actions 失败 device_id=%s error=%s", device, e, exc_info=True)
            return {"ok": False, "actions": [], "pollAfterSec": 20, "error": str(e)}


def report_app_actions(results: list, device_id: str = "") -> dict:
    """安卓壳回执 app 原生命令执行结果。"""
    if not isinstance(results, list):
        return {"ok": False, "error": "results 必须是数组", "processed": 0}
    device = str(device_id or "").strip()
    client = _s3_client()
    if not client:
        return {"ok": False, "error": "R2 不可用", "processed": 0}
    now_iso = _utc_now_iso()
    result_map = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        if item_id:
            result_map[item_id] = row
    if not result_map:
        return {"ok": True, "processed": 0, "items": []}

    with _app_action_write_lock:
        try:
            data = _app_action_queue_raw(client)
            pending = data.get("pending") if isinstance(data.get("pending"), list) else []
            history = data.get("history") if isinstance(data.get("history"), list) else []
            next_pending = []
            processed_items = []
            for item in pending:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                result = result_map.get(item_id)
                if not result:
                    next_pending.append(item)
                    continue
                target_device = str(item.get("deviceId") or "").strip()
                if target_device and device and target_device != device:
                    next_pending.append(item)
                    continue
                status = str(result.get("status") or "").strip().lower()
                if status not in {"done", "failed"}:
                    status = "failed"
                finished = {
                    **item,
                    "status": status,
                    "finishedAt": now_iso,
                    "deviceId": device or target_device,
                    "result": result.get("detail") if isinstance(result.get("detail"), dict) else {},
                    "error": str(result.get("error") or "").strip(),
                }
                history.append(finished)
                processed_items.append(finished)
            data["pending"] = next_pending
            data["history"] = _trim_app_action_history(history)
            _write_json(client, R2_KEY_APP_ACTION_QUEUE, data)
            return {"ok": True, "processed": len(processed_items), "items": processed_items}
        except Exception as e:
            logger.error("report_app_actions 失败 device_id=%s error=%s", device, e, exc_info=True)
            return {"ok": False, "error": str(e), "processed": 0}
