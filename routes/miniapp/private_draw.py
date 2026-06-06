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


def _private_draw_system_prompt(body: dict) -> str:
    entry = str(body.get("entry_number") or body.get("entry") or "").strip()
    result = body.get("result") if isinstance(body.get("result"), list) else body.get("rows")
    lines: list[str] = []
    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            if label and value:
                lines.append(f"{label}：{value}")
    elif isinstance(result, dict):
        for key, value in result.items():
            label = str(key or "").strip()
            text = str(value or "").strip()
            if label and text:
                lines.append(f"{label}：{text}")

    if not lines:
        legacy_text = str(body.get("event_text") or body.get("text") or "").strip()
        if legacy_text:
            lines.append(legacy_text)
    if not lines:
        return ""

    header = "小家私密抽签页刚抽出一张情侣情趣小纸条。"
    if entry:
        header += f"\nEntry #{entry}"
    return (
        f"{header}\n"
        + "\n".join(lines)
        + "\n\n"
        "系统提示：以上只是给你看的抽签结果，不是她发出的聊天文本。"
        "不要代替她说话，不要写成「我抽到了/发你看看」之类的用户口吻。"
        "你只需要按最近聊天入口的语气，以渡自己的口吻自然回应一两句；"
        "不要写开场白，不要旁白，不要扩成角色扮演剧情，也不要解释工具或系统流程。"
    )


def register_routes(bp) -> None:
    @bp.route("/private-draw/active", methods=["GET", "DELETE"])
    def miniapp_private_draw_active():
        from services.pixel_home import clear_active_private_draw, get_active_private_draw

        if request.method == "GET":
            return jsonify(get_active_private_draw())

        if request.method == "DELETE":
            result = clear_active_private_draw()
            status = 200 if result.get("ok") else 502
            return jsonify(result), status

    @bp.route("/private-draw/send", methods=["POST"])
    def miniapp_private_draw_send():
        body = request.get_json(silent=True) or {}
        system_prompt = _private_draw_system_prompt(body)
        if not system_prompt:
            return jsonify({"ok": False, "error": "缺少抽签内容"}), 400

        active_saved = False
        try:
            from services.pixel_home import save_active_private_draw

            active_saved = bool((save_active_private_draw(body) or {}).get("ok"))
        except Exception as e:
            logger.warning("private_draw_active_save_failed error=%s", e)

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
            event_text=system_prompt,
        )
        ok = bool((result or {}).get("ok"))
        logger.info(
            "private_draw_send_done ok=%s active_saved=%s window_id=%s channel=%s preferred=%s target=%s error=%s",
            ok,
            active_saved,
            window_id,
            str((result or {}).get("channel") or ""),
            str((result or {}).get("preferred_channel") or channel),
            target,
            str((result or {}).get("error") or ""),
        )
        status = 200 if ok else 502
        return jsonify({"ok": ok, **(result or {})}), status
