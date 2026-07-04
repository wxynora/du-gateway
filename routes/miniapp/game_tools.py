from __future__ import annotations

from flask import jsonify, request

from services.game_tool_runtime import execute_game_command, list_game_tools


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _clean_private_board_text(text: str) -> str:
    return "\n".join(
        line for line in str(text or "").splitlines()
        if not line.strip().startswith("可用命令：")
    ).strip()


def _private_board_sync_text(
    payload: dict,
    user_message: str = "",
    *,
    mode: str = "chat",
    roll_text: str = "",
) -> str:
    raw_du_text = str((payload or {}).get("text") or (payload or {}).get("du_text") or "").strip()
    if not raw_du_text:
        raw_du_text = str((payload or {}).get("player_text") or "").strip()
    du_text = _clean_private_board_text(raw_du_text)
    if not du_text:
        return ""
    roll_result = _clean_private_board_text(str(roll_text or "").strip())
    message = str(user_message or "").strip()
    state = (payload or {}).get("state") if isinstance((payload or {}).get("state"), dict) else {}
    turn_actor = str((state or {}).get("turn_actor") or "").strip()
    turn_label = "你" if turn_actor == "du" else "小玥"
    rule_lines = [
        f"当前行动方：{turn_label}。",
        "如果现在轮到你，并且你决定行动，回复第一行必须单独写精确指令「【掷骰】」，第二行开始再说想对小玥说的话。",
        "普通说「掷骰子」「我来投一下」，或者把「【掷骰】」写在句子中间，都只算聊天，不会触发行动。",
    ]
    if mode == "roll_result":
        board_lines: list[str] = []
        if roll_result:
            board_lines.extend(["本次掷骰：", roll_result])
        if du_text and du_text != roll_result:
            if board_lines:
                board_lines.append("")
            board_lines.extend(["当前棋局：", du_text])
        parts = [
            "小玥正在和你玩「涩涩走格棋」。这是她刚掷完骰子后的自动同步，不是主聊天正文。",
            "你会看到本次掷骰结果和当前棋局；你只需要自然回应，不要解释工具、接口或系统流程。",
            *rule_lines,
            "",
            "本次掷骰结果与当前棋局：",
            "\n".join(board_lines).strip(),
        ]
        return "\n".join(parts).strip()

    parts = [
        "小玥正在和你玩「涩涩走格棋」。这是局内普通交流，不是棋局同步，也不是主聊天正文。",
        "这次只处理小玥刚刚说的话；前后文会由同一个聊天窗口的最近对话提供，不要额外复述整盘棋局。",
        *rule_lines,
    ]
    if message:
        parts.extend(["", f"小玥刚刚在局内说：{message}"])
    return "\n".join(parts)


def register_routes(bp) -> None:
    @bp.route("/game-tools", methods=["GET"])
    def miniapp_game_tools_list():
        return jsonify({"ok": True, "games": list_game_tools()})

    @bp.route("/game-tools/private_board/sync-du", methods=["POST"])
    def miniapp_private_board_sync_du():
        body = request.get_json(silent=True) or {}
        save_id = str(body.get("save_id") or "default").strip() or "default"
        user_message = str(body.get("message") or "").strip()
        mode = str(body.get("mode") or "chat").strip().lower()
        if mode not in {"chat", "roll_result"}:
            mode = "chat"
        roll_text = str(body.get("roll_text") or "").strip()
        payload = execute_game_command("private_board", "status", save_id)
        if not payload.get("ok"):
            status = 404 if payload.get("error") == "UNKNOWN_GAME" else 500
            return jsonify(payload), status
        event_text = _private_board_sync_text(
            payload,
            user_message=user_message,
            mode=mode,
            roll_text=roll_text,
        )
        if not event_text:
            return jsonify({"ok": False, "error": "缺少棋局内容"}), 400

        panel_target = str(body.get("reply_target") or _get_panel_device_id()).strip()
        try:
            from services.reply_channel_context import resolve_recent_reply_context

            context = resolve_recent_reply_context(default_target=panel_target)
        except Exception:
            context = {}
        channel = str(context.get("channel") or "").strip().lower()
        window_id = str(context.get("window_id") or "").strip()
        target = str(context.get("target") or "").strip() or panel_target
        meta = context.get("meta") if isinstance(context.get("meta"), dict) else {}
        if not window_id:
            return jsonify({"ok": False, "error": "缺少最近聊天窗口"}), 400

        from services.conversation_followup import send_private_board_wakeup

        wakeup = send_private_board_wakeup(
            window_id=window_id,
            target=target,
            event_text=event_text,
            preferred_channel=channel,
            preferred_meta=meta,
            return_only=True,
        )
        ok = bool((wakeup or {}).get("ok"))
        reply_text = str((wakeup or {}).get("reply_text") or (wakeup or {}).get("reply_preview") or "")
        return jsonify({
            "ok": ok,
            "state": payload.get("state") or {},
            "player_text": payload.get("player_text") or "",
            "reply_text": reply_text,
            "reply_preview": str((wakeup or {}).get("reply_preview") or reply_text[:120]),
            "channel": str((wakeup or {}).get("channel") or ""),
            "mode": mode,
            "wakeup": wakeup or {},
        }), 200 if ok else 502

    @bp.route("/game-tools/<game_id>", methods=["POST"])
    def miniapp_game_tools_execute(game_id: str):
        body = request.get_json(silent=True) or {}
        command = str(body.get("command") or "").strip() or "打开"
        save_id = str(body.get("save_id") or "default").strip() or "default"
        payload = execute_game_command(game_id, command, save_id)
        status = 200 if payload.get("ok") else (404 if payload.get("error") == "UNKNOWN_GAME" else 500)
        return jsonify(payload), status
