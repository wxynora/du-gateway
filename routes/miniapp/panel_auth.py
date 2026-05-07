from flask import jsonify, request

from storage.miniapp_panel_store import list_trusted_devices, revoke_trusted_device, upsert_trusted_device
from utils.miniapp_panel_auth import (
    issue_panel_token,
    panel_auth_enabled,
    panel_auth_error,
    panel_auth_meta,
)


def register_routes(bp) -> None:
    @bp.route("/panel-auth/meta", methods=["GET"])
    def miniapp_panel_auth_meta():
        meta = panel_auth_meta()
        return jsonify({"ok": True, **meta})

    @bp.route("/panel-auth/check-password", methods=["POST"])
    def miniapp_panel_auth_check_password():
        if not panel_auth_enabled():
            return panel_auth_error("panel_auth_misconfigured", 503)
        body = request.get_json(silent=True) or {}
        password = str(body.get("password") or "").strip()
        from config import MINIAPP_PANEL_PASSWORD

        if not password or password != MINIAPP_PANEL_PASSWORD:
            return jsonify({"ok": False, "code": "password_invalid", "error": "密码不正确"}), 401
        return jsonify({"ok": True, "password_ok": True})

    @bp.route("/panel-auth/verify", methods=["POST"])
    def miniapp_panel_auth_verify():
        if not panel_auth_enabled():
            return panel_auth_error("panel_auth_misconfigured", 503)
        body = request.get_json(silent=True) or {}
        password = str(body.get("password") or "").strip()
        second_answer = str(body.get("second_answer") or "").strip()
        device_id = str(body.get("device_id") or "").strip()
        device_name = str(body.get("device_name") or "").strip()
        from config import MINIAPP_PANEL_PASSWORD
        from config import MINIAPP_PANEL_SECOND_ANSWER

        if not password or password != MINIAPP_PANEL_PASSWORD:
            return jsonify({"ok": False, "code": "password_invalid", "error": "密码不正确"}), 401
        if MINIAPP_PANEL_SECOND_ANSWER and second_answer != MINIAPP_PANEL_SECOND_ANSWER:
            return jsonify({"ok": False, "code": "second_answer_invalid", "error": "第二道问题回答不正确"}), 401
        if not device_id:
            return jsonify({"ok": False, "code": "device_id_missing", "error": "缺少浏览器设备标识"}), 400
        item = upsert_trusted_device(device_id, note=device_name)
        token, ttl = issue_panel_token(subject=f"device:{device_id}", device_id=device_id)
        return jsonify({"ok": True, "panel_token": token, "expires_in": ttl, "device": item})

    @bp.route("/panel-auth/session", methods=["GET"])
    def miniapp_panel_auth_session():
        payload = request.environ.get("miniapp_panel_payload") or {}
        return jsonify({
            "ok": True,
            "authenticated": True,
            "subject": payload.get("sub") or "browser",
            "exp": payload.get("exp"),
            "device_id": payload.get("device_id") or "",
        })

    @bp.route("/panel-auth/list", methods=["GET"])
    def miniapp_panel_auth_list():
        payload = request.environ.get("miniapp_panel_payload") or {}
        current_device_id = str(payload.get("device_id") or "").strip()
        items = []
        for item in list_trusted_devices():
            row = dict(item)
            row["current"] = bool(current_device_id and current_device_id == str(item.get("id") or "").strip())
            items.append(row)
        return jsonify({"ok": True, "items": items, "current_device_id": current_device_id})

    @bp.route("/panel-auth/revoke", methods=["POST"])
    def miniapp_panel_auth_revoke():
        body = request.get_json(silent=True) or {}
        device_id = str(body.get("device_id") or "").strip()
        if not device_id:
            return jsonify({"ok": False, "error": "device_id 不能为空"}), 400
        ok = revoke_trusted_device(device_id)
        if not ok:
            return jsonify({"ok": False, "error": "设备不存在或已撤销"}), 404
        payload = request.environ.get("miniapp_panel_payload") or {}
        return jsonify({"ok": True, "revoked": device_id, "revoked_current": device_id == str(payload.get("device_id") or "").strip()})
