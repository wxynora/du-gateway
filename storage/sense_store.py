"""R2 storage helpers for device sense snapshots and short-tail history."""
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing, today_beijing

R2_KEY_SENSE_LATEST = "sense/latest.json"
_SENSE_HISTORY_CAP = 200
_SENSE_HISTORY_READ_DEFAULT_LIMIT = 200
_SENSE_HISTORY_LATEST_ONLY_TYPES = {"usage"}
_SENSE_HISTORY_MIN_INTERVAL_SECONDS = {
    "battery": 30 * 60,
    "foreground": 10 * 60,
    "health": 5 * 60,
    "location": 30 * 60,
}
_SLEEP_BLOCK_MIN_MINUTES = 20
_SLEEP_BLOCK_MERGE_GAP_MINUTES = 180
_SLEEP_SEGMENT_KEEP = 8

_sense_write_lock = threading.Lock()

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


def get_sense_latest() -> dict:
    """读取 sense/latest.json，不存在或格式异常时返回 {}。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_SENSE_LATEST)
    if not isinstance(data, dict):
        return {}
    return data


def _duration_ms_between(started_at: str, ended_at: str) -> int:
    start = parse_iso_to_beijing(str(started_at or "").strip())
    end = parse_iso_to_beijing(str(ended_at or "").strip())
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))


def _dt(raw: Any) -> Optional[datetime]:
    return parse_iso_to_beijing(str(raw or "").strip())


def _sleep_night_date(start_dt: datetime, end_dt: datetime) -> str:
    if end_dt.hour < 12:
        return end_dt.strftime("%Y-%m-%d")
    if start_dt.hour >= 18:
        return (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    return start_dt.strftime("%Y-%m-%d")


def _is_sleep_like_screen_off_block(start_dt: datetime, end_dt: datetime, duration_ms: int) -> bool:
    minutes = max(0, duration_ms // 60000)
    if minutes < _SLEEP_BLOCK_MIN_MINUTES:
        return False
    if minutes >= 4 * 60:
        return True
    return start_dt.hour >= 18 or start_dt.hour < 11 or end_dt.hour < 12


def _compact_sleep_segments(items: list, device_id: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        start_at = str(item.get("startAt") or "").strip()
        end_at = str(item.get("endAt") or "").strip()
        if not start_at or not end_at:
            continue
        try:
            duration_ms = int(item.get("durationMs") or 0)
        except Exception:
            duration_ms = 0
        if duration_ms <= 0:
            duration_ms = _duration_ms_between(start_at, end_at)
        if duration_ms <= 0:
            continue
        dedupe_key = (start_at, end_at)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        out.append(
            {
                "deviceId": str(item.get("deviceId") or device_id or "").strip(),
                "startAt": start_at,
                "endAt": end_at,
                "durationMs": duration_ms,
                "minutes": max(0, duration_ms // 60000),
            }
        )
    out.sort(key=lambda x: str(x.get("startAt") or ""))
    return out[-_SLEEP_SEGMENT_KEEP:]


def _sleep_summary_from_segments(device_id: str, night_date: str, segments: list[dict]) -> dict:
    rows = _compact_sleep_segments(segments, device_id)
    total_ms = sum(max(0, int(item.get("durationMs") or 0)) for item in rows)
    gap_ms = 0
    prev_end = None
    for item in rows:
        start_dt = _dt(item.get("startAt"))
        if prev_end and start_dt:
            gap_ms += max(0, int((start_dt - prev_end).total_seconds() * 1000))
        prev_end = _dt(item.get("endAt")) or prev_end
    return {
        "deviceId": device_id,
        "nightDate": night_date,
        "startAt": rows[0].get("startAt") if rows else "",
        "endAt": rows[-1].get("endAt") if rows else "",
        "totalDurationMs": total_ms,
        "totalMinutes": max(0, total_ms // 60000),
        "awakeGapMs": gap_ms,
        "awakeGapMinutes": max(0, gap_ms // 60000),
        "segmentCount": len(rows),
        "segments": rows,
    }


def _merge_sleep_summary(previous: dict, block: dict) -> dict | None:
    start_dt = _dt(block.get("startAt"))
    end_dt = _dt(block.get("endAt"))
    try:
        duration_ms = int(block.get("durationMs") or 0)
    except Exception:
        duration_ms = 0
    if not start_dt or not end_dt or duration_ms <= 0:
        return None
    if not _is_sleep_like_screen_off_block(start_dt, end_dt, duration_ms):
        return None

    device_id = str(block.get("deviceId") or previous.get("deviceId") or "").strip()
    night_date = _sleep_night_date(start_dt, end_dt)
    current = previous.get("sleepSummary") if isinstance(previous.get("sleepSummary"), dict) else {}
    segments = []
    if current.get("nightDate") == night_date:
        prev_segments = current.get("segments") if isinstance(current.get("segments"), list) else []
        last_end = _dt((prev_segments[-1] if prev_segments else {}).get("endAt"))
        if not last_end or (start_dt - last_end).total_seconds() / 60.0 <= _SLEEP_BLOCK_MERGE_GAP_MINUTES:
            segments = list(prev_segments)
    segments.append(block)
    return _sleep_summary_from_segments(device_id, night_date, segments)


def _screen_event_time(data: dict, fallback: str = "") -> str:
    return str(
        (data or {}).get("occurredAt")
        or (data or {}).get("observedAt")
        or (data or {}).get("updatedAt")
        or fallback
        or ""
    ).strip()


def _truthy_value(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _screen_logical_state(data: dict) -> str:
    event = str((data or {}).get("event") or "").strip().lower()
    if event == "screen_off":
        return "off"
    if event in {"screen_on", "user_present"}:
        return "on"
    if event == "app_active" and _truthy_value((data or {}).get("interactive")):
        return "on"
    return ""


def _prepare_screen_bucket_snapshot(previous: dict, patch: dict) -> dict:
    prev = previous if isinstance(previous, dict) else {}
    incoming = patch if isinstance(patch, dict) else {}
    merged = dict(prev)
    merged.update(incoming)

    event_state = _screen_logical_state(merged)
    prev_state = _screen_logical_state(prev)
    event_at = _screen_event_time(merged, now_beijing_iso()) or now_beijing_iso()
    merged["lastSeen"] = event_at

    if event_state == "off":
        prev_since = str(prev.get("screenOffSince") or "").strip()
        incoming_since = str(incoming.get("screenOffSince") or "").strip()
        since = incoming_since or (prev_since if prev_state == "off" else "") or event_at
        merged["screenOffSince"] = since
        try:
            duration_ms = int(merged.get("screenOffDurationMs") or 0)
        except Exception:
            duration_ms = 0
        if duration_ms <= 0:
            duration_ms = _duration_ms_between(since, event_at)
        merged["screenOffDurationMs"] = duration_ms
        merged["lastScreenOffAt"] = since
        return merged

    if event_state == "on":
        prev_since = str(prev.get("screenOffSince") or "").strip()
        if prev_state == "off" and prev_since:
            duration_ms = _duration_ms_between(prev_since, event_at)
            block = {
                "deviceId": str(merged.get("deviceId") or prev.get("deviceId") or "").strip(),
                "startAt": prev_since,
                "endAt": event_at,
                "durationMs": duration_ms,
                "minutes": max(0, duration_ms // 60000),
            }
            merged["lastSleepBlock"] = block
            summary = _merge_sleep_summary(prev, block)
            if summary:
                merged["sleepSummary"] = summary
            merged["lastScreenOffAt"] = prev_since
        merged["lastScreenOnAt"] = event_at
        merged["screenOffSince"] = ""
        merged["screenOffDurationMs"] = 0

    return merged


def _closed_app_session(active: dict, ended_at: str, reason: str) -> dict | None:
    if not isinstance(active, dict):
        return None
    pkg = str(active.get("packageName") or "").strip()
    started_at = str(active.get("startedAt") or "").strip()
    if not pkg or not started_at:
        return None
    duration_ms = _duration_ms_between(started_at, ended_at)
    if duration_ms < 1000:
        return None
    item = {
        "deviceId": str(active.get("deviceId") or "").strip(),
        "packageName": pkg,
        "appName": str(active.get("appName") or pkg).strip() or pkg,
        "startedAt": started_at,
        "endedAt": str(ended_at or "").strip(),
        "durationMs": duration_ms,
        "endReason": str(reason or "").strip()[:40] or "unknown",
    }
    class_name = str(active.get("className") or "").strip()
    if class_name:
        item["className"] = class_name
    source = str(active.get("source") or "").strip()
    if source:
        item["source"] = source
    return item


def _compact_app_sessions(items: list, device_id: str, limit: int = 5) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_device = str(item.get("deviceId") or device_id or "").strip()
        if device_id and item_device and item_device != device_id:
            continue
        pkg = str(item.get("packageName") or "").strip()
        started_at = str(item.get("startedAt") or "").strip()
        ended_at = str(item.get("endedAt") or "").strip()
        if not pkg or not started_at or not ended_at:
            continue
        try:
            duration_ms = int(item.get("durationMs") or 0)
        except Exception:
            duration_ms = 0
        if duration_ms <= 0:
            duration_ms = _duration_ms_between(started_at, ended_at)
        if duration_ms <= 0:
            continue
        dedupe_key = (pkg, started_at, ended_at)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned = {
            "deviceId": item_device,
            "packageName": pkg,
            "appName": str(item.get("appName") or pkg).strip() or pkg,
            "startedAt": started_at,
            "endedAt": ended_at,
            "durationMs": duration_ms,
        }
        class_name = str(item.get("className") or "").strip()
        if class_name:
            cleaned["className"] = class_name
        source = str(item.get("source") or "").strip()
        if source:
            cleaned["source"] = source
        end_reason = str(item.get("endReason") or "").strip()
        if end_reason:
            cleaned["endReason"] = end_reason[:40]
        out.append(cleaned)
        if len(out) >= max(1, int(limit or 5)):
            break
    return out


def update_app_sessions_from_foreground(foreground_patch: dict) -> bool:
    """
    用前台 app 切换事件维护最近应用会话。
    不替代 usage 24h 快照：这里只记录“几点打开了什么 app、这次看了多久”。
    """
    if not isinstance(foreground_patch, dict):
        return False
    device_id = str(foreground_patch.get("deviceId") or "").strip()
    pkg = str(foreground_patch.get("packageName") or "").strip()
    if not device_id or not pkg:
        return False
    observed_at = str(foreground_patch.get("observedAt") or "").strip() or now_beijing_iso()
    app_name = str(foreground_patch.get("appName") or pkg).strip() or pkg
    client = _s3_client()
    if not client:
        return False
    with _sense_write_lock:
        try:
            doc = _read_json(client, R2_KEY_SENSE_LATEST)
            if doc is None or not isinstance(doc, dict):
                doc = {}
            bucket = doc.get("app_sessions")
            if not isinstance(bucket, dict):
                bucket = {}
            active = bucket.get("active")
            if not isinstance(active, dict):
                active = {}
            active_device = str(active.get("deviceId") or device_id).strip()
            active_pkg = str(active.get("packageName") or "").strip()
            if active_device == device_id and active_pkg == pkg:
                next_active = dict(active)
                next_active["deviceId"] = device_id
                next_active["packageName"] = pkg
                next_active["appName"] = app_name[:80]
                next_active.setdefault("startedAt", observed_at)
                next_active["lastSeenAt"] = observed_at
                next_active["lastActivityAt"] = observed_at
                source = str(foreground_patch.get("source") or next_active.get("source") or "accessibility").strip()
                if source:
                    next_active["source"] = source[:40]
                class_name = str(foreground_patch.get("className") or "").strip()
                if class_name:
                    next_active["className"] = class_name[:240]
                next_bucket = {
                    "deviceId": device_id,
                    "active": next_active,
                    "recent": _compact_app_sessions(bucket.get("recent") if isinstance(bucket.get("recent"), list) else [], device_id, limit=5),
                    "updatedAt": now_beijing_iso(),
                }
                doc["app_sessions"] = next_bucket
                _write_json(client, R2_KEY_SENSE_LATEST, doc)
                return True

            old_recent = bucket.get("recent")
            recent = old_recent if isinstance(old_recent, list) else []
            closed = _closed_app_session(active, observed_at, "app_switch") if active_device == device_id else None
            if closed:
                recent = [closed, *recent]

            next_active = {
                "deviceId": device_id,
                "packageName": pkg,
                "appName": app_name[:80],
                "startedAt": observed_at,
                "lastSeenAt": observed_at,
                "lastActivityAt": observed_at,
                "source": str(foreground_patch.get("source") or "accessibility").strip()[:40] or "accessibility",
            }
            class_name = str(foreground_patch.get("className") or "").strip()
            if class_name:
                next_active["className"] = class_name[:240]

            next_bucket = {
                "deviceId": device_id,
                "active": next_active,
                "recent": _compact_app_sessions(recent, device_id, limit=5),
                "updatedAt": now_beijing_iso(),
            }
            doc["app_sessions"] = next_bucket
            _write_json(client, R2_KEY_SENSE_LATEST, doc)
            if closed:
                _append_sense_history_event(client, "app_sessions", dict(next_bucket))
            return True
        except Exception as e:
            logger.error("update_app_sessions_from_foreground 失败 error=%s", e, exc_info=True)
            return False


def close_app_session_for_device(device_id: str, ended_at: str = "", reason: str = "screen_off") -> bool:
    did = str(device_id or "").strip()
    if not did:
        return False
    ended = str(ended_at or "").strip() or now_beijing_iso()
    client = _s3_client()
    if not client:
        return False
    with _sense_write_lock:
        try:
            doc = _read_json(client, R2_KEY_SENSE_LATEST)
            if doc is None or not isinstance(doc, dict):
                doc = {}
            bucket = doc.get("app_sessions")
            if not isinstance(bucket, dict):
                return True
            active = bucket.get("active")
            if not isinstance(active, dict) or not active:
                return True
            active_device = str(active.get("deviceId") or did).strip()
            if active_device != did:
                return True
            recent_raw = bucket.get("recent")
            recent = recent_raw if isinstance(recent_raw, list) else []
            closed = _closed_app_session(active, ended, reason)
            if closed:
                recent = [closed, *recent]
            next_bucket = {
                "deviceId": did,
                "active": None,
                "recent": _compact_app_sessions(recent, did, limit=5),
                "updatedAt": now_beijing_iso(),
            }
            doc["app_sessions"] = next_bucket
            _write_json(client, R2_KEY_SENSE_LATEST, doc)
            if closed:
                _append_sense_history_event(client, "app_sessions", dict(next_bucket))
            return True
        except Exception as e:
            logger.error("close_app_session_for_device 失败 device_id=%s error=%s", did, e, exc_info=True)
            return False


def merge_and_save_sense_bucket(sense_type: str, patch: dict) -> bool:
    """
    按 sense_type（如 battery）将 patch 合并进对应桶，并写入 updatedAt（UTC，形如 2025-03-23T14:00:00Z）。
    其它顶层键（location、network 等）保持不变。patch 中不应含 type。
    """
    client = _s3_client()
    if not client:
        return False
    key = (sense_type or "").strip()
    if not key:
        return False
    with _sense_write_lock:
        try:
            doc = _read_json(client, R2_KEY_SENSE_LATEST)
            if doc is None or not isinstance(doc, dict):
                doc = {}
            bucket = doc.get(key)
            if not isinstance(bucket, dict):
                bucket = {}
            if key == "screen":
                merged = _prepare_screen_bucket_snapshot(bucket, patch)
            else:
                merged = dict(bucket)
                merged.update(patch)
            # battery 桶不保留 power（Tasker 误传或未展开变量时污染快照）
            if key == "battery":
                merged.pop("power", None)
            merged["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            doc[key] = merged
            _write_json(client, R2_KEY_SENSE_LATEST, doc)
            _append_sense_history_event(client, key, dict(merged))
            return True
        except Exception as e:
            logger.error("merge_and_save_sense_bucket 失败 type=%s error=%s", key, e, exc_info=True)
            return False


def _last_sense_history_item(existing: list, sense_type: str) -> dict | None:
    for item in reversed(existing or []):
        if isinstance(item, dict) and str(item.get("type") or "").strip() == sense_type:
            return item
    return None


def _history_item_data(item: dict | None) -> dict:
    if not isinstance(item, dict):
        return {}
    data = item.get("data")
    return data if isinstance(data, dict) else {}


def _history_item_age_seconds(item: dict | None) -> float:
    at = parse_iso_to_beijing(str((item or {}).get("at") or "").strip())
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not at or not now_dt:
        return 10**9
    return max(0.0, (now_dt - at).total_seconds())


def _same_str_field(a: dict, b: dict, field: str) -> bool:
    return str((a or {}).get(field) or "").strip() == str((b or {}).get(field) or "").strip()


def _sense_history_should_append(existing: list, sense_type: str, bucket_snapshot: dict) -> bool:
    key = str(sense_type or "").strip()
    if key in _SENSE_HISTORY_LATEST_ONLY_TYPES:
        return False
    last = _last_sense_history_item(existing, key)
    if not last:
        return True
    last_data = _history_item_data(last)
    data = bucket_snapshot if isinstance(bucket_snapshot, dict) else {}

    if key == "screen":
        event = str(data.get("event") or "").strip().lower()
        if event == "app_active":
            return False
        state = _screen_logical_state(data)
        last_state = _screen_logical_state(last_data)
        return state in {"on", "off"} and state != last_state

    if key == "foreground":
        same_foreground = (
            _same_str_field(data, last_data, "deviceId")
            and _same_str_field(data, last_data, "packageName")
            and _same_str_field(data, last_data, "className")
        )
        if not same_foreground:
            return True
        return _history_item_age_seconds(last) >= _SENSE_HISTORY_MIN_INTERVAL_SECONDS["foreground"]

    if key == "app_sessions":
        return True

    if key == "battery":
        try:
            level = int(data.get("level"))
            last_level = int(last_data.get("level"))
        except Exception:
            level = last_level = -1
        charging_changed = bool(data.get("charging")) != bool(last_data.get("charging"))
        return charging_changed or abs(level - last_level) >= 5 or _history_item_age_seconds(last) >= _SENSE_HISTORY_MIN_INTERVAL_SECONDS["battery"]

    if key == "health":
        return _history_item_age_seconds(last) >= _SENSE_HISTORY_MIN_INTERVAL_SECONDS["health"] and (
            not _same_str_field(data, last_data, "heart_rate")
            or not _same_str_field(data, last_data, "steps")
        )

    if key == "location":
        if _history_item_age_seconds(last) >= _SENSE_HISTORY_MIN_INTERVAL_SECONDS["location"]:
            return True
        try:
            lat_delta = abs(float(data.get("lat")) - float(last_data.get("lat")))
            lng_delta = abs(float(data.get("lng")) - float(last_data.get("lng")))
            return lat_delta >= 0.001 or lng_delta >= 0.001
        except Exception:
            return False

    return _history_item_age_seconds(last) >= 5 * 60


def _append_sense_history_event(client, sense_type: str, bucket_snapshot: dict) -> None:
    """按北京日期写入短尾 sense/history/YYYY-MM-DD.json，仅保留最近必要事件。"""
    try:
        d = today_beijing()
        hk = f"sense/history/{d}.json"
        existing = _read_json(client, hk)
        if not isinstance(existing, list):
            existing = []
        if not _sense_history_should_append(existing, sense_type, bucket_snapshot):
            if len(existing) > _SENSE_HISTORY_CAP:
                _write_json(client, hk, existing[-_SENSE_HISTORY_CAP:])
            return
        existing.append({"type": sense_type, "at": now_beijing_iso(), "data": bucket_snapshot})
        if len(existing) > _SENSE_HISTORY_CAP:
            existing = existing[-_SENSE_HISTORY_CAP:]
        _write_json(client, hk, existing)
    except Exception as e:
        logger.warning("sense 历史归档失败 type=%s error=%s", sense_type, e)


def get_sense_history_for_date(date_str: str, limit: int | None = _SENSE_HISTORY_READ_DEFAULT_LIMIT) -> list[dict]:
    """读取某日 sense/history/YYYY-MM-DD.json；失败返回 []。"""
    client = _s3_client()
    if not client:
        return []
    day = str(date_str or "").strip()
    if not day:
        return []
    key = f"sense/history/{day}.json"
    data = _read_json(client, key)
    if not isinstance(data, list):
        return []
    rows = [dict(x) for x in data if isinstance(x, dict)]
    if limit is not None:
        try:
            n = int(limit)
        except Exception:
            n = _SENSE_HISTORY_READ_DEFAULT_LIMIT
        if n > 0 and len(rows) > n:
            rows = rows[-n:]
    return rows
