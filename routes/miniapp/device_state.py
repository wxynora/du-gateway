import base64
import logging
import math
from urllib.parse import quote

from flask import Response, jsonify, request

from storage import r2_store
from utils.time_aware import now_beijing_iso


logger = logging.getLogger(__name__)


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


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


def register_routes(bp) -> None:
    @bp.route("/device-state/screen", methods=["POST"])
    def miniapp_device_screen_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
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
        elif event in {"screen_on", "user_present"} or (event == "app_active" and interactive):
            patch["screenOffSince"] = ""
            patch["screenOffDurationMs"] = 0
        ok = r2_store.merge_and_save_sense_bucket("screen", patch)
        sessions_ok = True
        if event == "screen_off":
            sessions_ok = r2_store.close_app_session_for_device(device_id, patch.get("occurredAt") or patch.get("observedAt") or "", reason="screen_off")
        return jsonify({"ok": bool(ok and sessions_ok), "bucket": "screen", "device_id": device_id, "event": event})

    @bp.route("/device-state/battery", methods=["POST"])
    def miniapp_device_battery_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
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
        ok = r2_store.merge_and_save_sense_bucket("battery", patch)
        return jsonify({"ok": bool(ok), "bucket": "battery", "device_id": device_id})

    @bp.route("/device-state/usage-stats", methods=["POST"])
    def miniapp_device_usage_stats():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        apps = _sanitize_usage_apps(body.get("apps") or [], limit=20)
        patch = {
            "deviceId": device_id,
            "range": str(body.get("range") or "24h").strip() or "24h",
            "capturedAt": str(body.get("captured_at") or "").strip() or now_beijing_iso(),
            "apps": apps,
            "updatedAt": now_beijing_iso(),
        }
        ok = r2_store.merge_and_save_sense_bucket("usage", patch)
        return jsonify({"ok": bool(ok), "bucket": "usage", "device_id": device_id, "count": len(apps)})

    @bp.route("/device-state/foreground-app", methods=["POST"])
    def miniapp_device_foreground_app():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        patch, err = _sanitize_foreground_app_patch(body, device_id)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        ok = r2_store.merge_and_save_sense_bucket("foreground", patch or {})
        sessions_ok = r2_store.update_app_sessions_from_foreground(patch or {})
        return jsonify({"ok": bool(ok and sessions_ok), "bucket": "foreground", "device_id": device_id})

    @bp.route("/device-state/location", methods=["POST"])
    def miniapp_device_location_state():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        patch, err = _sanitize_location_patch(body, device_id)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        try:
            from services.amap_geocode import enrich_location_patch_with_amap_address

            patch = enrich_location_patch_with_amap_address(patch or {})
        except Exception:
            logger.exception("miniapp location reverse geocode failed")
        ok = r2_store.merge_and_save_sense_bucket("location", patch or {})
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
        from services.html_preview_store import resolve_preview_base_url_for_http_request

        base = resolve_preview_base_url_for_http_request(request.url_root or "")
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
