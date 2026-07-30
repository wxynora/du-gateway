"""SQLite storage helpers for device sense snapshots and short-tail history."""
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing, today_beijing

R2_KEY_SENSE_LATEST = "sense/latest.json"
R2_KEY_SLEEP_SUMMARY_LATEST = "sense/sleep_summary/latest.json"
_SENSE_HISTORY_CAP = 200
_SENSE_HISTORY_CAP_BY_TYPE = {
    "screen": 96,
    "computer": 96,
    "foreground": 480,
    "app_sessions": 180,
    "health": 320,
    "location": 64,
    "battery": 64,
}
_SENSE_HISTORY_READ_DEFAULT_LIMIT = 200
_SENSE_HISTORY_TTL_HOURS = 24
_SLEEP_SUMMARY_TTL_HOURS = 36
_SENSE_HISTORY_LATEST_ONLY_TYPES = {"usage", "computer"}
_SENSE_HISTORY_MIN_INTERVAL_SECONDS = {
    "battery": 30 * 60,
    "foreground": 10 * 60,
    "health": 5 * 60,
    "location": 30 * 60,
}
_SLEEP_SEGMENT_KEEP = 8
_SLEEP_MIN_MINUTES = 30
_SLEEP_RELIABILITY_PASS_SCORE = 3
_SLEEP_STEPS_LOW_DELTA = 120
_SLEEP_STEPS_HIGH_DELTA = 500
_SLEEP_RESTING_HEART_RATE = 78
_SLEEP_ELEVATED_HEART_RATE = 95
_SLEEP_HIGH_HEART_RATE = 110
_WAKE_ACTIVITY_CONFIRM_SECONDS = 2 * 60
_AWAKE_FOREGROUND_BLOCKLIST_EXACT = {
    "android",
    "com.android.deskclock",
    "com.android.incallui",
    "com.android.launcher",
    "com.android.launcher3",
    "com.android.systemui",
    "com.google.android.deskclock",
    "com.google.android.apps.nexuslauncher",
    "com.miui.home",
    "com.miui.systemui",
    "com.sohu.inputmethod.sogou.xiaomi",
}
_AWAKE_FOREGROUND_BLOCKLIST_PARTS = (
    "alarm",
    "deskclock",
    "inputmethod",
    "keyboard",
    "launcher",
    "systemui",
)

_sense_write_lock = threading.Lock()
_sense_bootstrap_lock = threading.Lock()
_SENSE_BOOTSTRAPPED = False

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


def _json_dict(raw: str | None) -> dict:
    data = runtime_sqlite.json_loads(raw, {})
    return data if isinstance(data, dict) else {}


def _sense_history_expires_at(at: str) -> str:
    dt = parse_iso_to_beijing(str(at or "").strip())
    if not dt:
        dt = parse_iso_to_beijing(now_beijing_iso())
    if not dt:
        dt = datetime.now(timezone.utc)
    return (dt + timedelta(hours=_SENSE_HISTORY_TTL_HOURS)).isoformat()


def _sleep_summary_expires_at(at: str) -> str:
    dt = parse_iso_to_beijing(str(at or "").strip())
    if not dt:
        dt = parse_iso_to_beijing(now_beijing_iso())
    if not dt:
        dt = datetime.now(timezone.utc)
    return (dt + timedelta(hours=_SLEEP_SUMMARY_TTL_HOURS)).isoformat()


def _prune_sense_history(conn, day: str = "") -> None:
    conn.execute("DELETE FROM sense_history WHERE expires_at <= ?", (now_beijing_iso(),))
    clean_day = str(day or "").strip()
    if clean_day:
        rows = conn.execute(
            "SELECT DISTINCT sense_type FROM sense_history WHERE substr(at, 1, 10) = ?",
            (clean_day,),
        ).fetchall()
        for row in rows:
            sense_type = str(row["sense_type"] or "").strip()
            if not sense_type:
                continue
            cap = _SENSE_HISTORY_CAP_BY_TYPE.get(sense_type, _SENSE_HISTORY_CAP)
            conn.execute(
                """
                DELETE FROM sense_history
                WHERE substr(at, 1, 10) = ?
                  AND sense_type = ?
                  AND id NOT IN (
                    SELECT id
                    FROM sense_history
                    WHERE substr(at, 1, 10) = ?
                      AND sense_type = ?
                    ORDER BY at DESC, id DESC
                    LIMIT ?
                  )
                """,
                (clean_day, sense_type, clean_day, sense_type, cap),
            )


def _load_sense_latest_doc(conn) -> dict:
    rows = conn.execute("SELECT sense_type, data_json FROM sense_latest").fetchall()
    doc: dict[str, dict] = {}
    for row in rows:
        key = str(row["sense_type"] or "").strip()
        data = _json_dict(row["data_json"])
        if key and data:
            doc[key] = data
    return doc


def _save_sense_latest_bucket(conn, sense_type: str, bucket: dict) -> None:
    key = str(sense_type or "").strip()
    if not key:
        return
    data = bucket if isinstance(bucket, dict) else {}
    conn.execute(
        """
        INSERT OR REPLACE INTO sense_latest (sense_type, data_json, updated_at)
        VALUES (?, ?, ?)
        """,
        (key, runtime_sqlite.json_dumps(data), str(data.get("updatedAt") or now_beijing_iso())),
    )


def _sense_history_rows_for_date(conn, day: str, limit: int | None = None) -> list[dict]:
    clean_day = str(day or "").strip()
    if not clean_day:
        return []
    _prune_sense_history(conn, clean_day)
    rows = conn.execute(
        """
        SELECT sense_type, at, data_json
        FROM sense_history
        WHERE substr(at, 1, 10) = ?
        ORDER BY at ASC, id ASC
        """,
        (clean_day,),
    ).fetchall()
    out = [
        {"type": str(row["sense_type"] or ""), "at": str(row["at"] or ""), "data": _json_dict(row["data_json"])}
        for row in rows
    ]
    if limit is not None:
        try:
            n = int(limit)
        except Exception:
            n = _SENSE_HISTORY_READ_DEFAULT_LIMIT
        if n > 0 and len(out) > n:
            out = out[-n:]
    return out


def _import_r2_sense_state(latest: Any, today_history: Any) -> None:
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if isinstance(latest, dict):
                for key, value in latest.items():
                    if isinstance(value, dict):
                        _save_sense_latest_bucket(conn, str(key), value)
            exists = conn.execute("SELECT 1 FROM sense_history LIMIT 1").fetchone()
            if exists is None and isinstance(today_history, list):
                for item in today_history:
                    if not isinstance(item, dict):
                        continue
                    sense_type = str(item.get("type") or "").strip()
                    at = str(item.get("at") or "").strip() or now_beijing_iso()
                    data = item.get("data") if isinstance(item.get("data"), dict) else {}
                    if not sense_type:
                        continue
                    conn.execute(
                        """
                        INSERT INTO sense_history (sense_type, at, data_json, expires_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (sense_type, at, runtime_sqlite.json_dumps(data), _sense_history_expires_at(at)),
                    )
            _prune_sense_history(conn, today_beijing())
            conn.execute("COMMIT")
            logger.info("sense_sqlite_bootstrap imported_from_r2=True")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _ensure_sense_bootstrapped() -> None:
    global _SENSE_BOOTSTRAPPED
    if _SENSE_BOOTSTRAPPED:
        return
    with _sense_bootstrap_lock:
        if _SENSE_BOOTSTRAPPED:
            return
        try:
            with runtime_sqlite.connect() as conn:
                row = conn.execute("SELECT 1 FROM sense_latest LIMIT 1").fetchone()
                if row is not None:
                    _SENSE_BOOTSTRAPPED = True
                    return
        except Exception as e:
            logger.warning("sense_sqlite_bootstrap check failed error=%s", e)
            return
        client = _s3_client()
        if client:
            try:
                latest = _read_json(client, R2_KEY_SENSE_LATEST)
                today_history = _read_json(client, f"sense/history/{today_beijing()}.json")
                _import_r2_sense_state(latest, today_history)
            except Exception as e:
                logger.warning("sense_sqlite_bootstrap import r2 failed error=%s", e)
        _SENSE_BOOTSTRAPPED = True


def get_sense_latest() -> dict:
    """读取本地 sense latest 快照，不存在或格式异常时返回 {}。"""
    _ensure_sense_bootstrapped()
    try:
        with runtime_sqlite.connect() as conn:
            return _load_sense_latest_doc(conn)
    except Exception as e:
        logger.warning("get_sense_latest 失败 error=%s", e)
        return {}



def _duration_ms_between(started_at: str, ended_at: str) -> int:
    start = parse_iso_to_beijing(str(started_at or "").strip())
    end = parse_iso_to_beijing(str(ended_at or "").strip())
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))


def _dt(raw: Any) -> Optional[datetime]:
    return parse_iso_to_beijing(str(raw or "").strip())


def _advance_wake_activity_window(
    current: Any,
    *,
    source: str,
    device_id: str,
    activity_at: str,
) -> tuple[dict, bool]:
    activity_dt = _dt(activity_at)
    if not activity_dt:
        return {}, False
    existing = current if isinstance(current, dict) else {}
    existing_source = str(existing.get("source") or "").strip()
    existing_device = str(existing.get("deviceId") or "").strip()
    start_at = str(existing.get("startAt") or "").strip()
    last_at = str(existing.get("lastAt") or "").strip()
    start_dt = _dt(start_at)
    last_dt = _dt(last_at)
    same_window = (
        existing_source == source
        and existing_device == device_id
        and start_dt is not None
        and last_dt is not None
        and activity_dt > last_dt
        and (activity_dt - last_dt).total_seconds() <= _WAKE_ACTIVITY_CONFIRM_SECONDS
    )
    if not same_window:
        return {
            "source": source,
            "deviceId": device_id,
            "startAt": activity_at,
            "lastAt": activity_at,
            "sampleCount": 1,
        }, False
    try:
        sample_count = max(1, int(existing.get("sampleCount") or 1)) + 1
    except Exception:
        sample_count = 2
    next_window = {
        "source": source,
        "deviceId": device_id,
        "startAt": start_at,
        "lastAt": activity_at,
        "sampleCount": sample_count,
    }
    duration_seconds = (activity_dt - start_dt).total_seconds()
    return next_window, duration_seconds >= _WAKE_ACTIVITY_CONFIRM_SECONDS


def _advance_wake_activity_window_through_session(
    current: Any,
    *,
    source: str,
    device_id: str,
    started_at: str,
    ended_at: str,
) -> tuple[dict, bool]:
    session_start_dt = _dt(started_at)
    session_end_dt = _dt(ended_at)
    if not session_start_dt or not session_end_dt or session_end_dt <= session_start_dt:
        return {}, False

    existing = current if isinstance(current, dict) else {}
    existing_start_at = str(existing.get("startAt") or "").strip()
    existing_last_at = str(existing.get("lastAt") or "").strip()
    existing_start_dt = _dt(existing_start_at)
    existing_last_dt = _dt(existing_last_at)
    connects_to_existing = (
        str(existing.get("source") or "").strip() == source
        and str(existing.get("deviceId") or "").strip() == device_id
        and existing_start_dt is not None
        and existing_last_dt is not None
        and existing_start_dt <= existing_last_dt <= session_end_dt
        and (
            existing_last_dt >= session_start_dt
            or (session_start_dt - existing_last_dt).total_seconds() <= _WAKE_ACTIVITY_CONFIRM_SECONDS
        )
    )
    wake_started_at = existing_start_at if connects_to_existing else started_at
    wake_started_dt = existing_start_dt if connects_to_existing else session_start_dt
    try:
        sample_count = max(1, int(existing.get("sampleCount") or 1)) + 1 if connects_to_existing else 2
    except Exception:
        sample_count = 2
    next_window = {
        "source": source,
        "deviceId": device_id,
        "startAt": wake_started_at,
        "lastAt": ended_at,
        "sampleCount": sample_count,
    }
    duration_seconds = (session_end_dt - wake_started_dt).total_seconds()
    return next_window, duration_seconds >= _WAKE_ACTIVITY_CONFIRM_SECONDS


def _sleep_date(start_dt: datetime, end_dt: datetime) -> str:
    target = end_dt if start_dt.date() != end_dt.date() else start_dt
    return target.strftime("%Y-%m-%d")


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return None


def _health_sample_at(data: dict, fallback: str = "") -> Optional[datetime]:
    for value in (
        (data or {}).get("capturedAt"),
        (data or {}).get("observedAt"),
        (data or {}).get("occurredAt"),
        fallback,
        (data or {}).get("updatedAt"),
    ):
        at = _dt(value)
        if at:
            return at
    return None


def _sleep_health_evidence(block: dict, latest_doc: dict, history: list[dict]) -> dict:
    start_dt = _dt(block.get("startAt"))
    end_dt = _dt(block.get("endAt"))
    if not start_dt or not end_dt or end_dt <= start_dt:
        return {}
    device_id = str(block.get("deviceId") or "").strip()
    samples: list[tuple[datetime, dict]] = []
    for item in history or []:
        if not isinstance(item, dict) or str(item.get("type") or "").strip() != "health":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        sample_device_id = str(data.get("deviceId") or data.get("device_id") or "").strip()
        if device_id and sample_device_id and sample_device_id != device_id:
            continue
        at = _health_sample_at(data, str(item.get("at") or ""))
        if at and start_dt <= at <= end_dt:
            samples.append((at, data))
    latest = latest_doc.get("health") if isinstance((latest_doc or {}).get("health"), dict) else {}
    if latest:
        sample_device_id = str(latest.get("deviceId") or latest.get("device_id") or "").strip()
        at = _health_sample_at(latest)
        if (not device_id or not sample_device_id or sample_device_id == device_id) and at and start_dt <= at <= end_dt:
            samples.append((at, latest))

    deduped: list[tuple[datetime, dict]] = []
    seen: set[tuple[str, int | None, int | None]] = set()
    for at, data in sorted(samples, key=lambda row: row[0]):
        heart_rate = _int_or_none(data.get("heart_rate"))
        steps = _int_or_none(data.get("steps"))
        marker = (at.isoformat(), heart_rate, steps)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append((at, data))

    evidence: dict = {}
    heart_values = [
        value
        for _, data in deduped
        for value in [_int_or_none(data.get("heart_rate"))]
        if value is not None
    ]
    if heart_values:
        evidence["heartRate"] = {
            "sampleCount": len(heart_values),
            "min": min(heart_values),
            "max": max(heart_values),
            "average": round(sum(heart_values) / len(heart_values)),
        }

    step_points = [
        (at, value)
        for at, data in deduped
        for value in [_int_or_none(data.get("steps"))]
        if value is not None
    ]
    if step_points:
        step_evidence = {
            "sampleCount": len(step_points),
            "first": step_points[0][1],
            "last": step_points[-1][1],
        }
        if len(step_points) >= 2:
            delta = 0
            comparable_pairs = 0
            previous_at, previous_value = step_points[0]
            for current_at, current_value in step_points[1:]:
                if current_at.date() == previous_at.date() and current_value >= previous_value:
                    delta += current_value - previous_value
                    comparable_pairs += 1
                previous_at, previous_value = current_at, current_value
            if comparable_pairs:
                step_evidence["delta"] = delta
        evidence["steps"] = step_evidence
    return evidence


def _assess_sleep_reliability(block: dict, health_evidence: dict) -> dict:
    try:
        duration_ms = int(block.get("durationMs") or 0)
    except Exception:
        duration_ms = 0
    minutes = max(0, duration_ms // 60000)
    reasons: list[str] = []
    positive_signals: list[str] = []
    negative_signals: list[str] = []

    if minutes < _SLEEP_MIN_MINUTES:
        return {
            "classification": "rejected_sleep",
            "confirmed": False,
            "sleepScore": 0,
            "sleepConfidence": 0.0,
            "positiveSignals": positive_signals,
            "negativeSignals": negative_signals,
            "reasons": [f"duration_below_minimum:{minutes}m"],
            "summaryReason": "sleep_too_short",
        }

    score = 3
    reasons.append(f"duration_minimum_met:{minutes}m")
    if minutes >= 45:
        score += 1
        positive_signals.append("duration_established")
    if minutes >= 90:
        score += 1
        positive_signals.append("duration_strong")

    evidence = health_evidence if isinstance(health_evidence, dict) else {}
    heart = evidence.get("heartRate") if isinstance(evidence.get("heartRate"), dict) else {}
    heart_count = _int_or_none(heart.get("sampleCount")) or 0
    heart_average = _int_or_none(heart.get("average"))
    heart_minimum = _int_or_none(heart.get("min"))
    if heart_count >= 2 and heart_average is not None:
        if heart_average >= _SLEEP_HIGH_HEART_RATE:
            score -= 3
            negative_signals.append("heart_rate_high")
            reasons.append(f"heart_rate_high:avg{heart_average}")
        elif heart_average >= _SLEEP_ELEVATED_HEART_RATE:
            score -= 2
            negative_signals.append("heart_rate_elevated")
            reasons.append(f"heart_rate_elevated:avg{heart_average}")
        elif heart_minimum is not None and heart_minimum <= _SLEEP_RESTING_HEART_RATE:
            score += 1
            positive_signals.append("sleep_like_heart_rate")
            reasons.append(f"sleep_like_heart_rate:min{heart_minimum}_avg{heart_average}")
        else:
            reasons.append(f"heart_rate_neutral:avg{heart_average}")
    elif heart_count == 1:
        reasons.append("heart_rate_single_sample")
    else:
        reasons.append("heart_rate_missing")

    steps = evidence.get("steps") if isinstance(evidence.get("steps"), dict) else {}
    step_count = _int_or_none(steps.get("sampleCount")) or 0
    step_delta = _int_or_none(steps.get("delta"))
    if step_count >= 2 and step_delta is not None:
        if step_delta <= _SLEEP_STEPS_LOW_DELTA:
            score += 1
            positive_signals.append("low_steps")
            reasons.append(f"low_steps_delta:{step_delta}")
        elif step_delta >= _SLEEP_STEPS_HIGH_DELTA:
            score -= 3
            negative_signals.append("steps_high")
            reasons.append(f"steps_delta_high:{step_delta}")
        else:
            score -= 1
            negative_signals.append("steps_moderate")
            reasons.append(f"steps_delta_moderate:{step_delta}")
    elif step_count == 1:
        reasons.append("steps_single_sample")
    else:
        reasons.append("steps_missing")

    accepted = score >= _SLEEP_RELIABILITY_PASS_SCORE
    return {
        "classification": "sleep" if accepted else "rejected_sleep",
        "confirmed": accepted,
        "sleepScore": score,
        "sleepConfidence": round(max(0, min(5, score)) / 5.0, 2),
        "positiveSignals": list(dict.fromkeys(positive_signals)),
        "negativeSignals": list(dict.fromkeys(negative_signals)),
        "reasons": reasons,
        "summaryReason": "confirmed_session" if accepted else "sleep_low_confidence",
    }


def _aggregate_sleep_health_evidence(rows: list[dict]) -> dict:
    heart_count = 0
    heart_min = None
    heart_max = None
    heart_weighted_total = 0
    step_count = 0
    step_delta = 0
    step_delta_available = False
    step_first = None
    step_last = None
    for row in rows:
        evidence = row.get("healthEvidence") if isinstance(row.get("healthEvidence"), dict) else {}
        heart = evidence.get("heartRate") if isinstance(evidence.get("heartRate"), dict) else {}
        count = _int_or_none(heart.get("sampleCount")) or 0
        average = _int_or_none(heart.get("average"))
        minimum = _int_or_none(heart.get("min"))
        maximum = _int_or_none(heart.get("max"))
        if count > 0 and average is not None and minimum is not None and maximum is not None:
            heart_count += count
            heart_weighted_total += average * count
            heart_min = minimum if heart_min is None else min(heart_min, minimum)
            heart_max = maximum if heart_max is None else max(heart_max, maximum)
        steps = evidence.get("steps") if isinstance(evidence.get("steps"), dict) else {}
        count = _int_or_none(steps.get("sampleCount")) or 0
        if count > 0:
            step_count += count
            first = _int_or_none(steps.get("first"))
            last = _int_or_none(steps.get("last"))
            if step_first is None and first is not None:
                step_first = first
            if last is not None:
                step_last = last
            delta = _int_or_none(steps.get("delta"))
            if delta is not None:
                step_delta += max(0, delta)
                step_delta_available = True

    evidence: dict = {}
    if heart_count > 0 and heart_min is not None and heart_max is not None:
        evidence["heartRate"] = {
            "sampleCount": heart_count,
            "min": heart_min,
            "max": heart_max,
            "average": round(heart_weighted_total / heart_count),
        }
    if step_count > 0:
        steps = {
            "sampleCount": step_count,
            "first": step_first,
            "last": step_last,
        }
        if step_delta_available:
            steps["delta"] = step_delta
        evidence["steps"] = steps
    return evidence


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
        row = {
            "deviceId": str(item.get("deviceId") or device_id or "").strip(),
            "startAt": start_at,
            "endAt": end_at,
            "durationMs": duration_ms,
            "minutes": max(0, duration_ms // 60000),
        }
        health_evidence = item.get("healthEvidence")
        if isinstance(health_evidence, dict) and health_evidence:
            row["healthEvidence"] = health_evidence
        out.append(row)
    out.sort(key=lambda x: str(x.get("startAt") or ""))
    return out[-_SLEEP_SEGMENT_KEEP:]


def _sleep_summary_from_segments(device_id: str, sleep_date: str, segments: list[dict]) -> dict:
    rows = _compact_sleep_segments(segments, device_id)
    total_ms = sum(max(0, int(item.get("durationMs") or 0)) for item in rows)
    gap_ms = 0
    prev_end = None
    for item in rows:
        start_dt = _dt(item.get("startAt"))
        if prev_end and start_dt:
            gap_ms += max(0, int((start_dt - prev_end).total_seconds() * 1000))
        prev_end = _dt(item.get("endAt")) or prev_end
    summary = {
        "deviceId": device_id,
        "sleepDate": sleep_date,
        "startAt": rows[0].get("startAt") if rows else "",
        "endAt": rows[-1].get("endAt") if rows else "",
        "totalDurationMs": total_ms,
        "totalMinutes": max(0, total_ms // 60000),
        "awakeGapMs": gap_ms,
        "awakeGapMinutes": max(0, gap_ms // 60000),
        "segmentCount": len(rows),
        "segments": rows,
    }
    health_evidence = _aggregate_sleep_health_evidence(rows)
    if health_evidence:
        summary["healthEvidence"] = health_evidence
    return summary


def _persist_sleep_summary(summary: dict, updated_at: str = "") -> None:
    if not isinstance(summary, dict):
        return
    sleep_date = str(summary.get("sleepDate") or summary.get("nightDate") or "").strip()
    if not sleep_date:
        return
    client = _s3_client()
    if not client:
        return
    clean_updated_at = str(updated_at or now_beijing_iso())
    payload = {
        "ok": True,
        "updatedAt": clean_updated_at,
        "expiresAt": _sleep_summary_expires_at(clean_updated_at),
        "summary": summary,
    }
    try:
        _write_json(client, R2_KEY_SLEEP_SUMMARY_LATEST, payload)
        _write_json(client, f"sense/sleep_summary/{sleep_date}.json", payload)
    except Exception as e:
        logger.warning("sleep summary durable persist failed date=%s error=%s", sleep_date, e)


def _merge_sleep_summary(previous: dict, block: dict) -> tuple[dict | None, str]:
    start_dt = _dt(block.get("startAt"))
    end_dt = _dt(block.get("endAt"))
    try:
        duration_ms = int(block.get("durationMs") or 0)
    except Exception:
        duration_ms = 0
    if not start_dt or not end_dt or duration_ms <= 0:
        return None, "invalid_block"
    device_id = str(block.get("deviceId") or "").strip()
    sleep_date = _sleep_date(start_dt, end_dt)
    current = previous.get("sleepSummary") if isinstance(previous.get("sleepSummary"), dict) else {}
    current_date = str(current.get("sleepDate") or current.get("nightDate") or "").strip()
    segments = list(current.get("segments") or []) if current_date == sleep_date else []
    segments.append(block)
    summary = _sleep_summary_from_segments(device_id, sleep_date, segments)
    return summary, "confirmed_session"


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


def _is_explicit_foreground_wake(data: dict) -> bool:
    if str((data or {}).get("screenWakeSource") or "").strip() != "foreground_app":
        return False
    pkg = str((data or {}).get("foregroundPackageName") or (data or {}).get("packageName") or "").strip().lower()
    return _is_real_foreground_package(pkg)


def _is_real_foreground_package(pkg: str) -> bool:
    pkg = str(pkg or "").strip().lower()
    if not pkg:
        return False
    if pkg in _AWAKE_FOREGROUND_BLOCKLIST_EXACT:
        return False
    return not any(part in pkg for part in _AWAKE_FOREGROUND_BLOCKLIST_PARTS)


def _screen_logical_state(data: dict) -> str:
    event = str((data or {}).get("event") or "").strip().lower()
    if (
        event in {"app_active", "pc_active"}
        and _truthy_value((data or {}).get("interactive"))
        and str((data or {}).get("screenWakeSource") or "").strip() in {"foreground_app", "pc_activity"}
    ):
        return "on"
    if event == "screen_off" or str((data or {}).get("screenOffSince") or "").strip():
        return "off"
    return ""


def _prepare_screen_bucket_snapshot(previous: dict, patch: dict, latest_doc: dict | None = None, history: list[dict] | None = None) -> dict:
    prev = previous if isinstance(previous, dict) else {}
    incoming = patch if isinstance(patch, dict) else {}
    merged = dict(prev)
    merged.update(incoming)

    incoming_event = str(incoming.get("event") or "").strip().lower()
    event_state = _screen_logical_state(merged)
    event_at = _screen_event_time(merged, now_beijing_iso()) or now_beijing_iso()
    merged["lastSeen"] = event_at

    if incoming_event == "screen_off":
        prev_since = str(prev.get("screenOffSince") or "").strip()
        incoming_since = str(incoming.get("screenOffSince") or "").strip()
        previous_session = prev.get("sleepSession") if isinstance(prev.get("sleepSession"), dict) else {}
        previous_device = str(previous_session.get("deviceId") or prev.get("deviceId") or "").strip()
        incoming_device = str(merged.get("deviceId") or "").strip()
        continues_same_candidate = bool(
            prev_since
            and str(previous_session.get("state") or "").strip() == "candidate"
            and previous_device == incoming_device
        )
        # Repeated screen-off events continue the same candidate. A brief亮屏 without
        # subsequent app switching does not end it.
        since = prev_since or incoming_since or event_at
        merged["screenOffSince"] = since
        try:
            duration_ms = int(merged.get("screenOffDurationMs") or 0)
        except Exception:
            duration_ms = 0
        if duration_ms <= 0:
            duration_ms = _duration_ms_between(since, event_at)
        merged["screenOffDurationMs"] = duration_ms
        merged["lastScreenOffAt"] = since
        merged["sleepSession"] = {
            "state": "candidate",
            "deviceId": str(merged.get("deviceId") or prev.get("deviceId") or "").strip(),
            "startAt": since,
        }
        if not continues_same_candidate:
            merged.pop("wakeCandidateAt", None)
            merged.pop("wakeCandidatePackages", None)
            merged.pop("wakeCandidateRealPackages", None)
            merged.pop("phoneWakeActivity", None)
            merged.pop("pcWakeActivity", None)
        return merged

    if incoming_event in {"screen_on", "user_present"} and str(prev.get("screenOffSince") or "").strip():
        first_wake_at = str(prev.get("wakeCandidateAt") or "").strip() or event_at
        merged["wakeCandidateAt"] = first_wake_at
        session = prev.get("sleepSession") if isinstance(prev.get("sleepSession"), dict) else {}
        merged["sleepSession"] = {
            "state": "candidate",
            "deviceId": str(merged.get("deviceId") or prev.get("deviceId") or "").strip(),
            "startAt": str(session.get("startAt") or prev.get("screenOffSince") or "").strip(),
            "wakeCandidateAt": first_wake_at,
        }
        return merged

    if event_state == "on":
        prev_since = str(prev.get("screenOffSince") or "").strip()
        if prev_since:
            end_at = str(incoming.get("sleepEndAt") or event_at).strip() or event_at
            duration_ms = _duration_ms_between(prev_since, end_at)
            block = {
                "deviceId": str(merged.get("deviceId") or prev.get("deviceId") or "").strip(),
                "startAt": prev_since,
                "endAt": end_at,
                "durationMs": duration_ms,
                "minutes": max(0, duration_ms // 60000),
                "wakeSource": str(incoming.get("screenWakeSource") or "").strip(),
                "confirmedAt": event_at,
            }
            health_evidence = _sleep_health_evidence(block, latest_doc or {}, history or [])
            if health_evidence:
                block["healthEvidence"] = health_evidence
            block.update(_assess_sleep_reliability(block, health_evidence))
            summary = None
            summary_reason = str(block.get("summaryReason") or "")
            if block.get("confirmed") is True:
                summary, summary_reason = _merge_sleep_summary(prev, block)
            block["summaryIncluded"] = bool(summary)
            block["summaryReason"] = summary_reason
            merged["lastSleepBlock"] = block
            if summary:
                merged["sleepSummary"] = summary
            merged.pop("daySleepSummary", None)
            merged["sleepSession"] = {
                "state": "completed" if block.get("confirmed") is True else "rejected",
                "deviceId": block["deviceId"],
                "startAt": block["startAt"],
                "endAt": block["endAt"],
                "confirmedAt": block["confirmedAt"],
                "wakeSource": block["wakeSource"],
            }
            merged["lastScreenOffAt"] = prev_since
        merged["lastScreenOnAt"] = str(incoming.get("sleepEndAt") or event_at).strip() or event_at
        merged["wakeConfirmedAt"] = event_at
        merged["screenOffSince"] = ""
        merged["screenOffDurationMs"] = 0
        merged.pop("wakeCandidateAt", None)
        merged.pop("wakeCandidatePackages", None)
        merged.pop("wakeCandidateRealPackages", None)
        merged.pop("phoneWakeActivity", None)
        merged.pop("pcWakeActivity", None)

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
    _ensure_sense_bootstrapped()
    with _sense_write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    doc = _load_sense_latest_doc(conn)
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
                        _save_sense_latest_bucket(conn, "app_sessions", next_bucket)
                        conn.execute("COMMIT")
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
                    _save_sense_latest_bucket(conn, "app_sessions", next_bucket)
                    if closed:
                        _append_sense_history_event(conn, "app_sessions", dict(next_bucket))
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            return True
        except Exception as e:
            logger.error("update_app_sessions_from_foreground 失败 error=%s", e, exc_info=True)
            return False


def _closed_real_foreground_session(latest: dict, device_id: str, ended_at: str) -> dict | None:
    ended_dt = _dt(ended_at)
    if not ended_dt:
        return None
    app_sessions = latest.get("app_sessions") if isinstance(latest.get("app_sessions"), dict) else {}
    recent = app_sessions.get("recent") if isinstance(app_sessions.get("recent"), list) else []
    for item in recent:
        if not isinstance(item, dict):
            continue
        item_device = str(item.get("deviceId") or "").strip()
        if item_device and item_device != device_id:
            continue
        if _dt(item.get("endedAt")) != ended_dt:
            continue
        if not _is_real_foreground_package(str(item.get("packageName") or "")):
            continue
        return item
    return None


def mark_screen_awake_from_foreground(foreground_patch: dict) -> bool:
    """Confirm waking after two minutes of continuous real foreground activity."""
    if not isinstance(foreground_patch, dict):
        return True
    device_id = str(foreground_patch.get("deviceId") or "").strip()
    pkg = str(foreground_patch.get("packageName") or "").strip()
    app_name = str(foreground_patch.get("appName") or pkg).strip() or pkg
    if not device_id or not pkg:
        return True
    observed_at = str(foreground_patch.get("observedAt") or "").strip() or now_beijing_iso()
    screen_patch = {
        "deviceId": device_id,
        "event": "app_active",
        "interactive": True,
        "occurredAt": observed_at,
        "observedAt": observed_at,
        "snapshot": False,
        "screenWakeSource": "foreground_app",
        "foregroundPackageName": pkg[:160],
        "foregroundAppName": app_name[:80],
        "updatedAt": now_beijing_iso(),
    }
    class_name = str(foreground_patch.get("className") or "").strip()
    if class_name:
        screen_patch["foregroundClassName"] = class_name[:240]
    is_real_foreground = _is_explicit_foreground_wake(screen_patch)
    latest = get_sense_latest()
    screen_bucket = latest.get("screen") if isinstance(latest.get("screen"), dict) else {}
    sleep_started_at = str(screen_bucket.get("screenOffSince") or "").strip()
    sleep_started_dt = _dt(sleep_started_at)
    if not sleep_started_at or not sleep_started_dt:
        return True

    closed_session = _closed_real_foreground_session(latest, device_id, observed_at)
    closed_started_at = str((closed_session or {}).get("startedAt") or "").strip()
    closed_ended_at = str((closed_session or {}).get("endedAt") or "").strip()
    closed_started_dt = _dt(closed_started_at)
    if closed_started_dt and closed_started_dt < sleep_started_dt:
        closed_session = None
        closed_started_at = ""
        closed_ended_at = ""

    if closed_session:
        wake_window, confirmed = _advance_wake_activity_window_through_session(
            screen_bucket.get("phoneWakeActivity"),
            source="foreground_app",
            device_id=device_id,
            started_at=closed_started_at,
            ended_at=closed_ended_at,
        )
        if not is_real_foreground:
            closed_pkg = str(closed_session.get("packageName") or "").strip()
            closed_app_name = str(closed_session.get("appName") or closed_pkg).strip() or closed_pkg
            screen_patch["foregroundPackageName"] = closed_pkg[:160]
            screen_patch["foregroundAppName"] = closed_app_name[:80]
    elif is_real_foreground:
        wake_window, confirmed = _advance_wake_activity_window(
            screen_bucket.get("phoneWakeActivity"),
            source="foreground_app",
            device_id=device_id,
            activity_at=observed_at,
        )
    else:
        return True

    wake_started_at = str(wake_window.get("startAt") or observed_at).strip()
    if not confirmed:
        session = screen_bucket.get("sleepSession") if isinstance(screen_bucket.get("sleepSession"), dict) else {}
        pending_session = dict(session)
        pending_session["state"] = "candidate"
        pending_session["wakeCandidateAt"] = wake_started_at
        return merge_and_save_sense_bucket(
            "screen",
            {
                "wakeCandidateAt": wake_started_at,
                "phoneWakeActivity": wake_window,
                "sleepSession": pending_session,
            },
        )
    screen_patch["sleepEndAt"] = wake_started_at
    screen_patch["phoneWakeActivity"] = wake_window
    return merge_and_save_sense_bucket("screen", screen_patch)


def mark_screen_awake_from_pc_activity(activity_patch: dict) -> bool:
    """Confirm waking after two minutes of continuous new OS input."""
    if not isinstance(activity_patch, dict):
        return True
    last_input_at = str(activity_patch.get("lastInputAt") or activity_patch.get("last_input_at") or "").strip()
    input_dt = parse_iso_to_beijing(last_input_at)
    if not input_dt:
        return False
    latest = get_sense_latest()
    screen_bucket = latest.get("screen") if isinstance(latest.get("screen"), dict) else {}
    started_at = str(screen_bucket.get("screenOffSince") or "").strip()
    started_dt = parse_iso_to_beijing(started_at)
    if not started_dt or input_dt <= started_dt:
        return True
    device_id = str(activity_patch.get("deviceId") or activity_patch.get("device_id") or "pc").strip() or "pc"
    wake_window, confirmed = _advance_wake_activity_window(
        screen_bucket.get("pcWakeActivity"),
        source="pc_activity",
        device_id=device_id,
        activity_at=last_input_at,
    )
    if not confirmed:
        return merge_and_save_sense_bucket(
            "screen",
            {
                "pcWakeActivity": wake_window,
            },
        )
    wake_started_at = str(wake_window.get("startAt") or last_input_at).strip()
    return merge_and_save_sense_bucket(
        "screen",
        {
            "deviceId": str(screen_bucket.get("deviceId") or device_id).strip(),
            "event": "pc_active",
            "interactive": True,
            "occurredAt": last_input_at,
            "observedAt": str(activity_patch.get("observedAt") or activity_patch.get("observed_at") or "").strip()
            or now_beijing_iso(),
            "snapshot": False,
            "screenWakeSource": "pc_activity",
            "computerDeviceId": device_id,
            "sleepEndAt": wake_started_at,
            "pcWakeActivity": wake_window,
        },
    )


def close_app_session_for_device(device_id: str, ended_at: str = "", reason: str = "screen_off") -> bool:
    did = str(device_id or "").strip()
    if not did:
        return False
    ended = str(ended_at or "").strip() or now_beijing_iso()
    _ensure_sense_bootstrapped()
    with _sense_write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    doc = _load_sense_latest_doc(conn)
                    bucket = doc.get("app_sessions")
                    if not isinstance(bucket, dict):
                        conn.execute("COMMIT")
                        return True
                    active = bucket.get("active")
                    if not isinstance(active, dict) or not active:
                        conn.execute("COMMIT")
                        return True
                    active_device = str(active.get("deviceId") or did).strip()
                    if active_device != did:
                        conn.execute("COMMIT")
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
                    _save_sense_latest_bucket(conn, "app_sessions", next_bucket)
                    if closed:
                        _append_sense_history_event(conn, "app_sessions", dict(next_bucket))
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            return True
        except Exception as e:
            logger.error("close_app_session_for_device 失败 device_id=%s error=%s", did, e, exc_info=True)
            return False


def merge_and_save_sense_bucket(sense_type: str, patch: dict) -> bool:
    """
    按 sense_type（如 battery）将 patch 合并进对应桶，并写入 updatedAt（UTC，形如 2025-03-23T14:00:00Z）。
    其它顶层键（location、network 等）保持不变。patch 中不应含 type。
    """
    key = (sense_type or "").strip()
    if not key:
        return False
    _ensure_sense_bootstrapped()
    sleep_summary_to_persist = None
    sleep_summary_updated_at = ""
    with _sense_write_lock:
        try:
            with runtime_sqlite.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    doc = _load_sense_latest_doc(conn)
                    bucket = doc.get(key)
                    if not isinstance(bucket, dict):
                        bucket = {}
                    previous_sleep_summary = bucket.get("sleepSummary") if key == "screen" and isinstance(bucket.get("sleepSummary"), dict) else {}
                    if key == "screen":
                        history_days = {today_beijing()}
                        start_dt = _dt(bucket.get("screenOffSince"))
                        end_dt = _dt((patch or {}).get("sleepEndAt"))
                        if start_dt and end_dt and end_dt >= start_dt:
                            day = start_dt.date()
                            while day <= end_dt.date():
                                history_days.add(day.isoformat())
                                day += timedelta(days=1)
                        history = []
                        for history_day in sorted(history_days):
                            history.extend(_sense_history_rows_for_date(conn, history_day, limit=None))
                        merged = _prepare_screen_bucket_snapshot(bucket, patch, doc, history)
                    else:
                        merged = dict(bucket)
                        merged.update(patch)
                    # battery 桶不保留 power（Tasker 误传或未展开变量时污染快照）
                    if key == "battery":
                        merged.pop("power", None)
                    merged["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if key == "screen":
                        next_sleep_summary = merged.get("sleepSummary") if isinstance(merged.get("sleepSummary"), dict) else {}
                        if next_sleep_summary and next_sleep_summary != previous_sleep_summary:
                            sleep_summary_to_persist = dict(next_sleep_summary)
                            sleep_summary_updated_at = str(merged.get("updatedAt") or now_beijing_iso())
                    _save_sense_latest_bucket(conn, key, merged)
                    _append_sense_history_event(conn, key, dict(merged))
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            if sleep_summary_to_persist:
                _persist_sleep_summary(sleep_summary_to_persist, sleep_summary_updated_at)
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
        if event == "app_active" and not _is_explicit_foreground_wake(data):
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


def _append_sense_history_event(conn, sense_type: str, bucket_snapshot: dict) -> None:
    """按北京日期写入短尾 sense history，仅保留最近必要事件。"""
    try:
        d = today_beijing()
        existing = _sense_history_rows_for_date(conn, d, limit=None)
        if not _sense_history_should_append(existing, sense_type, bucket_snapshot):
            _prune_sense_history(conn, d)
            return
        at = now_beijing_iso()
        conn.execute(
            """
            INSERT INTO sense_history (sense_type, at, data_json, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(sense_type or "").strip(),
                at,
                runtime_sqlite.json_dumps(bucket_snapshot if isinstance(bucket_snapshot, dict) else {}),
                _sense_history_expires_at(at),
            ),
        )
        _prune_sense_history(conn, d)
    except Exception as e:
        logger.warning("sense 历史归档失败 type=%s error=%s", sense_type, e)


def get_sense_history_for_date(date_str: str, limit: int | None = _SENSE_HISTORY_READ_DEFAULT_LIMIT) -> list[dict]:
    """读取某日 sense history；失败返回 []。"""
    _ensure_sense_bootstrapped()
    day = str(date_str or "").strip()
    if not day:
        return []
    try:
        with runtime_sqlite.connect() as conn:
            return _sense_history_rows_for_date(conn, day, limit=limit)
    except Exception as e:
        logger.warning("get_sense_history_for_date 失败 day=%s error=%s", day, e)
        return []
