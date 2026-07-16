from __future__ import annotations

import logging

from flask import jsonify, request

from services.reply_channel_context import resolve_recent_reply_context
from storage.music_bgm_state import get_music_bgm_context, save_music_bgm_context


logger = logging.getLogger("sumitalk")


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def register_routes(bp):
    @bp.route("/music/listen/bgm-context", methods=["GET"])
    def miniapp_music_bgm_context_get():
        return jsonify({"ok": True, "context": get_music_bgm_context() or {}})

    @bp.route("/music/listen/bgm-context", methods=["POST"])
    def miniapp_music_bgm_context_post():
        if not request.is_json:
            return jsonify({"ok": False, "error": "需要 application/json"}), 400
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "JSON 无效"}), 400
        context = save_music_bgm_context(body)
        if context is None:
            return jsonify({"ok": False, "error": "保存一起听状态失败"}), 500
        return jsonify({"ok": True, "context": context})

    @bp.route("/music/listen/invite/respond", methods=["POST"])
    def miniapp_music_listen_invite_respond():
        if not request.is_json:
            return jsonify({"ok": False, "error": "需要 application/json"}), 400
        body = request.get_json(silent=True) or {}
        action = str(body.get("action") or "").strip().lower()
        if action not in {"accept", "refuse"}:
            return jsonify({"ok": False, "error": "action 只能是 accept/refuse"}), 400

        panel_target = str(body.get("reply_target") or _get_panel_device_id()).strip()
        context = resolve_recent_reply_context(default_target=panel_target)
        channel = str(context.get("channel") or "").strip().lower()
        window_id = str(context.get("window_id") or "").strip()
        target = str(context.get("target") or "").strip() or panel_target
        meta = context.get("meta") if isinstance(context.get("meta"), dict) else {}
        if not window_id:
            return jsonify({"ok": False, "error": "缺少最近聊天窗口"}), 400

        event_text = "小玥接受了你的一起听邀请。" if action == "accept" else "小玥拒绝了你的一起听邀请。"
        from services.conversation_followup import send_listen_invite_response_wakeup

        result = send_listen_invite_response_wakeup(
            window_id=window_id,
            target=target,
            event_text=event_text,
            preferred_channel=channel,
            preferred_meta=meta,
        )
        ok = bool((result or {}).get("ok"))
        logger.info(
            "listen_invite_response_done ok=%s action=%s invite_id=%s window_id=%s channel=%s target=%s error=%s",
            ok,
            action,
            str(body.get("invite_id") or ""),
            window_id,
            str((result or {}).get("channel") or channel),
            target,
            str((result or {}).get("error") or ""),
        )
        return jsonify({"ok": ok, **(result or {})}), 200 if ok else 502
