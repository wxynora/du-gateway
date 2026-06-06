import logging

from flask import jsonify, request

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from storage import r2_store, whitelist_store


logger = logging.getLogger("sumitalk")


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _resolve_primary_chat_window_id() -> str:
    recent = whitelist_store.list_recent_windows(limit=200) or []
    for w in recent:
        wid = str((w or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


def _last_reply_meta() -> dict:
    try:
        meta = r2_store.get_last_reply_channel() or {}
    except Exception:
        meta = {}
    return meta if isinstance(meta, dict) else {}


def register_routes(bp) -> None:
    @bp.route("/private-draw/send", methods=["POST"])
    def miniapp_private_draw_send():
        body = request.get_json(silent=True) or {}
        event_text = str(body.get("event_text") or body.get("text") or "").strip()
        if not event_text:
            return jsonify({"ok": False, "error": "缺少抽签内容"}), 400

        panel_target = str(body.get("reply_target") or _get_panel_device_id()).strip()
        meta = _last_reply_meta()
        channel = str(meta.get("channel") or "").strip().lower()
        window_id = str(body.get("window_id") or meta.get("window_id") or "").strip() or _resolve_primary_chat_window_id()
        target = str(meta.get("target") or "").strip()
        if channel == "tg" and not target and window_id.startswith("tg_"):
            target = window_id[3:]
        if channel == "sumitalk" and not target:
            target = panel_target
        if not target:
            target = panel_target
        if not window_id:
            return jsonify({"ok": False, "error": "缺少最近聊天窗口"}), 400

        from services.conversation_followup import send_private_draw_wakeup

        result = send_private_draw_wakeup(
            window_id=window_id,
            target=target,
            event_text=event_text,
        )
        ok = bool((result or {}).get("ok"))
        logger.info(
            "private_draw_send_done ok=%s window_id=%s channel=%s preferred=%s target=%s error=%s",
            ok,
            window_id,
            str((result or {}).get("channel") or ""),
            str((result or {}).get("preferred_channel") or channel),
            target,
            str((result or {}).get("error") or ""),
        )
        status = 200 if ok else 502
        return jsonify({"ok": ok, **(result or {})}), status
