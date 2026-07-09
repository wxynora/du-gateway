import base64
import json
import logging
import math
import re
import time
from urllib.parse import quote

from flask import Response, jsonify, request

from storage import r2_store
from storage.sense_store import mark_screen_awake_from_foreground
from utils.time_aware import now_beijing_iso, today_beijing


logger = logging.getLogger(__name__)

REPORTING_BUCKETS = ("battery", "screen", "foreground", "location", "usage")
REPORTING_BUCKET_LABELS = {
    "battery": "电量",
    "screen": "屏幕",
    "foreground": "前台应用",
    "location": "位置",
    "usage": "使用统计",
}
_REPORT_DEDUPE_TTL_SECONDS = {
    "battery": 10 * 60,
    "screen": 30,
    "foreground": 30,
    "location": 10 * 60,
    "usage": 30 * 60,
    "health": 60,
}
_REPORT_DEDUPE_CACHE: dict[str, tuple[str, float]] = {}


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _compact_report_payload(bucket: str, patch: dict) -> dict:
    data = patch if isinstance(patch, dict) else {}
    if bucket == "battery":
        return {
            "level": data.get("level"),
            "charging": bool(data.get("charging")),
        }
    if bucket == "screen":
        out = {
            "event": str(data.get("event") or "").strip().lower(),
            "interactive": bool(data.get("interactive")),
            "snapshot": bool(data.get("snapshot")),
        }
        if out["event"] == "screen_off":
            try:
                out["durationMinute"] = int(data.get("screenOffDurationMs") or 0) // 60000
            except Exception:
                out["durationMinute"] = 0
        return out
    if bucket == "foreground":
        return {
            "packageName": str(data.get("packageName") or "").strip(),
            "className": str(data.get("className") or "").strip(),
            "source": str(data.get("source") or "").strip(),
        }
    if bucket == "location":
        try:
            lat = round(float(data.get("lat")), 3)
            lng = round(float(data.get("lng")), 3)
        except Exception:
            lat = data.get("lat")
            lng = data.get("lng")
        return {
            "lat": lat,
            "lng": lng,
            "provider": str(data.get("provider") or "").strip(),
            "source": str(data.get("source") or "").strip(),
        }
    if bucket == "usage":
        apps = []
        for item in data.get("apps") or []:
            if not isinstance(item, dict):
                continue
            try:
                foreground_bucket = int(item.get("foregroundMs") or 0) // (5 * 60 * 1000)
            except Exception:
                foreground_bucket = 0
            try:
                last_used_bucket = int(item.get("lastTimeUsed") or 0) // (5 * 60 * 1000)
            except Exception:
                last_used_bucket = 0
            apps.append(
                [
                    str(item.get("packageName") or "").strip(),
                    foreground_bucket,
                    last_used_bucket,
                ]
            )
        return {
            "range": str(data.get("range") or "").strip(),
            "apps": apps,
        }
    if bucket == "health":
        return {
            "heart_rate": data.get("heart_rate"),
            "steps": data.get("steps"),
            "source": str(data.get("source") or "").strip(),
        }
    return data


def _report_payload_fingerprint(bucket: str, patch: dict) -> str:
    compact = _compact_report_payload(bucket, patch)
    return json.dumps(compact, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _prune_report_dedupe_cache(now: float) -> None:
    if len(_REPORT_DEDUPE_CACHE) <= 512:
        return
    cutoff = now - max(_REPORT_DEDUPE_TTL_SECONDS.values())
    for key, (_, ts) in list(_REPORT_DEDUPE_CACHE.items()):
        if ts < cutoff:
            _REPORT_DEDUPE_CACHE.pop(key, None)


def _report_dedupe_cache_key(bucket: str, device_id: str) -> str:
    return f"{bucket}|{device_id}"


def _is_duplicate_report_write(bucket: str, device_id: str, patch: dict) -> bool:
    ttl = int(_REPORT_DEDUPE_TTL_SECONDS.get(bucket, 0) or 0)
    if ttl <= 0:
        return False
    fp = _report_payload_fingerprint(bucket, patch)
    now = time.time()
    _prune_report_dedupe_cache(now)
    key = _report_dedupe_cache_key(bucket, device_id)
    last = _REPORT_DEDUPE_CACHE.get(key)
    return bool(last and last[0] == fp and now - last[1] < ttl)


def _remember_report_write(bucket: str, device_id: str, patch: dict) -> None:
    now = time.time()
    _prune_report_dedupe_cache(now)
    _REPORT_DEDUPE_CACHE[_report_dedupe_cache_key(bucket, device_id)] = (
        _report_payload_fingerprint(bucket, patch),
        now,
    )


def _reporting_deduped_response(bucket: str, device_id: str):
    return jsonify({"ok": True, "bucket": bucket, "device_id": device_id, "skipped": True, "reason": "deduped"})


def _sanitize_usage_apps(items: list[dict], limit: int = 20) -> list[dict]:
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        pkg = str(item.get("packageName") or item.get("package_name") or "").strip()
        if not pkg:
            continue
        try:
            foreground_ms = int(item.get("foregroundMs") or item.get("foreground_ms") or 0)
        except Exception:
            foreground_ms = 0
        try:
            last_time_used = int(item.get("lastTimeUsed") or item.get("last_time_used") or 0)
        except Exception:
            last_time_used = 0
        if foreground_ms <= 0:
            continue
        out.append(
            {
                "packageName": pkg,
                "foregroundMs": foreground_ms,
                "lastTimeUsed": last_time_used,
            }
        )
        if len(out) >= max(1, int(limit or 20)):
            break
    return out


def _sanitize_foreground_app_patch(body: dict, device_id: str) -> tuple[dict | None, str | None]:
    src = body.get("app") if isinstance(body.get("app"), dict) else body
    pkg = str(src.get("packageName") or src.get("package_name") or "").strip()
    if not pkg:
        return None, "packageName 必填"
    app_name = str(src.get("appName") or src.get("app_name") or pkg).strip() or pkg
    patch = {
        "deviceId": device_id,
        "packageName": pkg[:160],
        "appName": app_name[:80],
        "observedAt": str(src.get("observedAt") or src.get("observed_at") or body.get("observed_at") or "").strip() or now_beijing_iso(),
        "source": str(src.get("source") or body.get("source") or "accessibility").strip()[:40] or "accessibility",
        "updatedAt": now_beijing_iso(),
    }
    class_name = str(src.get("className") or src.get("class_name") or "").strip()
    if class_name:
        patch["className"] = class_name[:240]
    return patch, None


def _float_from_body(body: dict, *names: str) -> float | None:
    for name in names:
        value = body.get(name)
        if value in (None, ""):
            continue
        try:
            num = float(value)
        except Exception:
            continue
        if math.isfinite(num):
            return num
    return None


def _sanitize_location_patch(body: dict, device_id: str) -> tuple[dict | None, str | None]:
    lat = _float_from_body(body, "lat", "latitude")
    lng = _float_from_body(body, "lng", "lon", "longitude")
    if lat is None or lng is None:
        return None, "lat/lng 必填"
    if lat < -90 or lat > 90 or lng < -180 or lng > 180:
        return None, "lat/lng 范围无效"

    patch: dict = {
        "deviceId": device_id,
        "lat": lat,
        "lng": lng,
        "capturedAt": str(body.get("captured_at") or body.get("capturedAt") or "").strip() or now_beijing_iso(),
        "source": str(body.get("source") or "sumitalk_native").strip()[:40] or "sumitalk_native",
    }
    for src, dst in (
        ("accuracy", "accuracy"),
        ("altitude", "altitude"),
        ("speed", "speed"),
        ("bearing", "bearing"),
    ):
        val = _float_from_body(body, src)
        if val is not None:
            patch[dst] = val
    provider = str(body.get("provider") or "").strip()
    if provider:
        patch["provider"] = provider[:40]
    return patch, None


def _int_from_body(body: dict, *names: str) -> int | None:
    for name in names:
        value = body.get(name)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _int_from_text(text: str, *patterns: str) -> int | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            return None
    return None


def _sanitize_health_patch(body: dict, device_id: str) -> tuple[dict | None, str | None]:
    raw_text = " ".join(str(body.get("raw_text") or body.get("rawText") or body.get("text") or "").split()).strip()
    heart_rate = _int_from_body(body, "heart_rate", "heartRate", "hr")
    steps = _int_from_body(body, "steps", "step_count", "stepCount")
    if raw_text:
        if heart_rate is None:
            heart_rate = _int_from_text(
                raw_text,
                r"(\d{2,3})\s*(?:脉搏/分|心率|次/分|bpm|pulse|heart\s*rate|hr\b)",
                r"(?:脉搏/分|心率|pulse|heart\s*rate|hr\b|bpm)\D{0,12}(\d{2,3})",
            )
        if steps is None:
            steps = _int_from_text(
                raw_text,
                r"([0-9][0-9,]{0,7})\s*(?:步数|步|steps?|step\s*count)",
                r"(?:步数|steps?|step\s*count)\D{0,16}([0-9][0-9,]{0,7})",
            )
    patch: dict = {
        "deviceId": device_id,
        "capturedAt": str(body.get("captured_at") or body.get("capturedAt") or "").strip() or now_beijing_iso(),
        "source": str(body.get("source") or "sumitalk_notify_for_xiaomi").strip()[:40] or "sumitalk_notify_for_xiaomi",
        "updatedAt": now_beijing_iso(),
    }
    if raw_text:
        patch["raw_text"] = raw_text[:500]
    if heart_rate is not None:
        if heart_rate < 25 or heart_rate > 240:
            return None, "heart_rate 范围无效"
        patch["heart_rate"] = heart_rate
    if steps is not None:
        if steps < 0 or steps > 300000:
            return None, "steps 范围无效"
        patch["steps"] = steps
    if "heart_rate" not in patch and "steps" not in patch:
        return None, "缺少 heart_rate 或 steps"
    app_name = str(body.get("appName") or body.get("app_name") or "").strip()
    if app_name:
        patch["appName"] = app_name[:80]
    package_name = str(body.get("packageName") or body.get("package_name") or "").strip()
    if package_name:
        patch["packageName"] = package_name[:160]
    return patch, None


def _health_history_for_device(device_id: str, limit: int = 20) -> list[dict]:
    rows = r2_store.get_sense_history_for_date(today_beijing(), limit=120) or []
    out: list[dict] = []
    for row in reversed(rows):
        if not isinstance(row, dict) or str(row.get("type") or "").strip() != "health":
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        did = str(data.get("deviceId") or data.get("device_id") or "").strip()
        if device_id and did and did != device_id:
            continue
        out.append({"at": str(row.get("at") or "").strip(), "data": data})
        if len(out) >= max(1, int(limit or 20)):
            break
    return out


def _sense_payload_device_id(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("deviceId") or data.get("device_id") or "").strip()


def _sense_payload_matches_device(data: dict, device_id: str) -> bool:
    did = _sense_payload_device_id(data)
    return bool(device_id and did and did == device_id)


def _reporting_latest_for_device(device_id: str) -> dict:
    latest_doc = r2_store.get_sense_latest() or {}
    out: dict = {}
    for key in REPORTING_BUCKETS:
        data = latest_doc.get(key) if isinstance(latest_doc.get(key), dict) else {}
        if not data or not _sense_payload_matches_device(data, device_id):
            out[key] = {}
            continue
        out[key] = data
    return out


def _reporting_history_for_device(device_id: str, limit: int = 60) -> list[dict]:
    rows = r2_store.get_sense_history_for_date(today_beijing(), limit=240) or []
    out: list[dict] = []
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        typ = str(row.get("type") or "").strip()
        if typ not in REPORTING_BUCKETS:
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if not _sense_payload_matches_device(data, device_id):
            continue
        out.append(
            {
                "type": typ,
                "label": REPORTING_BUCKET_LABELS.get(typ, typ),
                "at": str(row.get("at") or "").strip(),
                "data": data,
            }
        )
        if len(out) >= max(1, int(limit or 60)):
            break
    return out


def _reporting_skip_response(bucket: str, device_id: str):
    return jsonify({"ok": True, "bucket": bucket, "device_id": device_id, "skipped": True, "reason": "disabled"})


def register_routes(bp) -> None:
    @bp.route("/device-state/reporting", methods=["GET"])
    def miniapp_device_reporting_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        return jsonify(
            {
                "ok": True,
                "device_id": device_id,
                "latest": _reporting_latest_for_device(device_id),
                "history": _reporting_history_for_device(device_id, limit=60),
                "types": [{"key": key, "label": REPORTING_BUCKET_LABELS.get(key, key)} for key in REPORTING_BUCKETS],
                "config": r2_store.get_device_reporting_config(device_id),
            }
        )

    @bp.route("/device-state/reporting/config", methods=["PUT", "POST"])
    def miniapp_device_reporting_config():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        key = str(body.get("key") or "").strip()
        if key:
            if key not in REPORTING_BUCKETS:
                return jsonify({"ok": False, "error": "上报类别无效"}), 400
            enabled_raw = body.get("enabled")
            enabled = enabled_raw is True or str(enabled_raw).strip().lower() in {"1", "true", "yes", "on"}
            config = r2_store.update_device_reporting_bucket_config(device_id, key, enabled)
        else:
            incoming = body.get("config") if isinstance(body.get("config"), dict) else {}
            config = r2_store.save_device_reporting_config(device_id, incoming)
        if config is None:
            return jsonify({"ok": False, "error": "保存失败"}), 500
        return jsonify({"ok": True, "device_id": device_id, "config": config})

    @bp.route("/device-state/screen", methods=["POST"])
    def miniapp_device_screen_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        if not r2_store.is_device_reporting_bucket_enabled(device_id, "screen"):
            return _reporting_skip_response("screen", device_id)
        body = request.get_json(silent=True) or {}
        event = str(body.get("event") or "").strip().lower()
        if event not in {"screen_on", "screen_off", "user_present", "app_active"}:
            return jsonify({"ok": False, "error": "event 无效"}), 400
        interactive_raw = body.get("interactive")
        snapshot_raw = body.get("snapshot")
        interactive = interactive_raw is True or str(interactive_raw).strip().lower() in {"1", "true", "yes", "on"}
        snapshot = snapshot_raw is True or str(snapshot_raw).strip().lower() in {"1", "true", "yes", "on"}
        patch = {
            "deviceId": device_id,
            "event": event,
            "interactive": interactive,
            "occurredAt": str(body.get("occurred_at") or "").strip() or now_beijing_iso(),
            "observedAt": str(body.get("observed_at") or "").strip() or now_beijing_iso(),
            "snapshot": snapshot,
            "updatedAt": now_beijing_iso(),
        }
        if event == "screen_off":
            screen_off_since = str(body.get("screen_off_since") or body.get("screenOffSince") or "").strip()
            if screen_off_since:
                patch["screenOffSince"] = screen_off_since
            try:
                duration_ms = int(body.get("screen_off_duration_ms") or body.get("screenOffDurationMs") or 0)
            except Exception:
                duration_ms = 0
            if duration_ms >= 0:
                patch["screenOffDurationMs"] = duration_ms
        if _is_duplicate_report_write("screen", device_id, patch):
            return _reporting_deduped_response("screen", device_id)
        ok = r2_store.merge_and_save_sense_bucket("screen", patch)
        sessions_ok = True
        if event == "screen_off":
            sessions_ok = r2_store.close_app_session_for_device(device_id, patch.get("occurredAt") or patch.get("observedAt") or "", reason="screen_off")
        if ok and sessions_ok:
            _remember_report_write("screen", device_id, patch)
        return jsonify({"ok": bool(ok and sessions_ok), "bucket": "screen", "device_id": device_id, "event": event})

    @bp.route("/device-state/battery", methods=["POST"])
    def miniapp_device_battery_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        if not r2_store.is_device_reporting_bucket_enabled(device_id, "battery"):
            return _reporting_skip_response("battery", device_id)
        body = request.get_json(silent=True) or {}
        try:
            level = int(body.get("level"))
        except Exception:
            return jsonify({"ok": False, "error": "level 必须是 0-100"}), 400
        if level < 0 or level > 100:
            return jsonify({"ok": False, "error": "level 必须是 0-100"}), 400
        patch = {
            "deviceId": device_id,
            "level": level,
            "charging": bool(body.get("charging")),
            "capturedAt": str(body.get("captured_at") or body.get("capturedAt") or "").strip() or now_beijing_iso(),
            "updatedAt": now_beijing_iso(),
        }
        if _is_duplicate_report_write("battery", device_id, patch):
            return _reporting_deduped_response("battery", device_id)
        ok = r2_store.merge_and_save_sense_bucket("battery", patch)
        if ok:
            _remember_report_write("battery", device_id, patch)
        return jsonify({"ok": bool(ok), "bucket": "battery", "device_id": device_id})

    @bp.route("/device-state/health", methods=["GET", "POST"])
    def miniapp_device_health_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        if request.method == "GET":
            latest_doc = r2_store.get_sense_latest() or {}
            latest = latest_doc.get("health") if isinstance(latest_doc.get("health"), dict) else {}
            latest_did = str((latest or {}).get("deviceId") or (latest or {}).get("device_id") or "").strip()
            if latest_did and latest_did != device_id:
                latest = {}
            return jsonify(
                {
                    "ok": True,
                    "device_id": device_id,
                    "latest": latest,
                    "history": _health_history_for_device(device_id, limit=20),
                    "du_vitals": r2_store.get_du_vitals_latest() or {},
                    "du_vitals_history": r2_store.get_du_vitals_history(limit=10) or [],
                }
            )
        body = request.get_json(silent=True) or {}
        patch, err = _sanitize_health_patch(body, device_id)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        if _is_duplicate_report_write("health", device_id, patch or {}):
            return _reporting_deduped_response("health", device_id)
        ok = r2_store.merge_and_save_sense_bucket("health", patch or {})
        if ok:
            _remember_report_write("health", device_id, patch or {})
        return jsonify({"ok": bool(ok), "bucket": "health", "device_id": device_id})

    @bp.route("/device-state/usage-stats", methods=["POST"])
    def miniapp_device_usage_stats():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        if not r2_store.is_device_reporting_bucket_enabled(device_id, "usage"):
            return _reporting_skip_response("usage", device_id)
        body = request.get_json(silent=True) or {}
        apps = _sanitize_usage_apps(body.get("apps") or [], limit=20)
        patch = {
            "deviceId": device_id,
            "range": str(body.get("range") or "24h").strip() or "24h",
            "capturedAt": str(body.get("captured_at") or "").strip() or now_beijing_iso(),
            "apps": apps,
            "updatedAt": now_beijing_iso(),
        }
        if _is_duplicate_report_write("usage", device_id, patch):
            return _reporting_deduped_response("usage", device_id)
        ok = r2_store.merge_and_save_sense_bucket("usage", patch)
        if ok:
            _remember_report_write("usage", device_id, patch)
        return jsonify({"ok": bool(ok), "bucket": "usage", "device_id": device_id, "count": len(apps)})

    @bp.route("/device-state/foreground-app", methods=["POST"])
    def miniapp_device_foreground_app():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        if not r2_store.is_device_reporting_bucket_enabled(device_id, "foreground"):
            return _reporting_skip_response("foreground", device_id)
        body = request.get_json(silent=True) or {}
        patch, err = _sanitize_foreground_app_patch(body, device_id)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        if _is_duplicate_report_write("foreground", device_id, patch or {}):
            screen_awake_ok = mark_screen_awake_from_foreground(patch or {})
            return jsonify(
                {
                    "ok": bool(screen_awake_ok),
                    "bucket": "foreground",
                    "device_id": device_id,
                    "skipped": True,
                    "reason": "deduped",
                    "screen_awake_checked": True,
                }
            )
        ok = r2_store.merge_and_save_sense_bucket("foreground", patch or {})
        sessions_ok = r2_store.update_app_sessions_from_foreground(patch or {})
        screen_awake_ok = mark_screen_awake_from_foreground(patch or {})
        if ok and sessions_ok and screen_awake_ok:
            _remember_report_write("foreground", device_id, patch or {})
        return jsonify({"ok": bool(ok and sessions_ok and screen_awake_ok), "bucket": "foreground", "device_id": device_id})

    @bp.route("/device-state/location", methods=["POST"])
    def miniapp_device_location_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        if not r2_store.is_device_reporting_bucket_enabled(device_id, "location"):
            return _reporting_skip_response("location", device_id)
        body = request.get_json(silent=True) or {}
        patch, err = _sanitize_location_patch(body, device_id)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        if _is_duplicate_report_write("location", device_id, patch or {}):
            return _reporting_deduped_response("location", device_id)
        try:
            from services.amap_geocode import enrich_location_patch_with_amap_address

            patch = enrich_location_patch_with_amap_address(patch or {})
        except Exception:
            logger.exception("miniapp location reverse geocode failed")
        ok = r2_store.merge_and_save_sense_bucket("location", patch or {})
        if ok:
            _remember_report_write("location", device_id, patch or {})
        return jsonify({"ok": bool(ok), "bucket": "location", "device_id": device_id})

    @bp.route("/device-screenshots", methods=["POST"])
    def miniapp_device_screenshot_upload():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        image_base64 = str(body.get("image_base64") or body.get("imageBase64") or "").strip()
        if not image_base64:
            return jsonify({"ok": False, "error": "缺少 image_base64"}), 400
        if "," in image_base64 and image_base64.startswith("data:"):
            image_base64 = image_base64.split(",", 1)[1].strip()
        try:
            content = base64.b64decode(image_base64, validate=False)
        except Exception:
            return jsonify({"ok": False, "error": "图片 base64 无效"}), 400
        if not content:
            return jsonify({"ok": False, "error": "图片为空"}), 400
        if len(content) > 3 * 1024 * 1024:
            return jsonify({"ok": False, "error": "截图不能超过 3MB"}), 400
        ctype = str(body.get("mime_type") or body.get("mimeType") or "image/jpeg").strip().lower()
        if ctype not in {"image/jpeg", "image/png"}:
            ctype = "image/jpeg"
        saved = r2_store.save_device_screenshot(
            content,
            ctype,
            {
                "deviceId": device_id,
                "requestId": str(body.get("request_id") or body.get("requestId") or "").strip(),
                "capturedAt": str(body.get("captured_at") or body.get("capturedAt") or "").strip() or now_beijing_iso(),
                "width": int(body.get("width") or 0),
                "height": int(body.get("height") or 0),
            },
        )
        if not saved:
            return jsonify({"ok": False, "error": "截图保存失败"}), 500
        from services.public_url import resolve_public_base_url_for_http_request

        base = resolve_public_base_url_for_http_request(request.url_root or "")
        key = str(saved.get("key") or "")
        token = str(saved.get("accessToken") or "")
        url = ""
        if base and key and token:
            url = f"{base}/miniapp-api/device-screenshots/raw-public?key={quote(key, safe='/')}&token={quote(token, safe='')}"
        return jsonify(
            {
                "ok": True,
                "key": key,
                "url": url,
                "image_url": url,
                "captured_at": saved.get("capturedAt") or "",
                "width": saved.get("width") or 0,
                "height": saved.get("height") or 0,
            }
        )

    @bp.route("/device-screenshots/raw-public", methods=["GET"])
    def miniapp_device_screenshot_raw_public():
        key = (request.args.get("key") or "").strip()
        token = (request.args.get("token") or "").strip()
        data, ctype = r2_store.get_device_screenshot(key, token)
        if not data:
            return jsonify({"ok": False, "error": "未找到或 token 无效"}), 404
        mt = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
        return Response(data, mimetype=mt, headers={"Cache-Control": "private, max-age=300"})
