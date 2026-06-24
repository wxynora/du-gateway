import logging

from flask import jsonify, request

from services.reply_channel_context import resolve_recent_reply_context


logger = logging.getLogger("sumitalk")


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


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

    header = "小玥刚在 sex play 抽签页抽出一张小纸条发给你。"
    if entry:
        header += f"\nEntry #{entry}"
    return (
        f"{header}\n"
        + "\n".join(lines)
        + "\n\n"
        "系统提示：以上是小玥抽出来发给你看的结果，不是小玥的聊天正文。"
        "不要代替小玥说话，不要写成「我抽到了/发你看看」之类的用户口吻。"
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

            active_payload = {**body, "source": "private_draw_page", "drawn_by": "xinyue"}
            active_saved = bool((save_active_private_draw(active_payload) or {}).get("ok"))
        except Exception as e:
            logger.warning("private_draw_active_save_failed error=%s", e)

        panel_target = str(body.get("reply_target") or _get_panel_device_id()).strip()
        context = resolve_recent_reply_context(default_target=panel_target)
        channel = str(context.get("channel") or "").strip().lower()
        window_id = str(context.get("window_id") or "").strip()
        target = str(context.get("target") or "").strip() or panel_target
        meta = context.get("meta") if isinstance(context.get("meta"), dict) else {}
        if not window_id:
            return jsonify({"ok": False, "error": "缺少最近聊天窗口"}), 400

        from services.conversation_followup import send_private_draw_wakeup

        result = send_private_draw_wakeup(
            window_id=window_id,
            target=target,
            event_text=system_prompt,
            preferred_channel=channel,
            preferred_meta=meta,
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
