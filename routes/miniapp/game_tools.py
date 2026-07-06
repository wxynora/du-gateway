from __future__ import annotations

from flask import jsonify, request

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from services.game_tool_runtime import execute_game_command, list_game_tools
from utils.time_aware import now_beijing_iso


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _primary_tg_window_id() -> str:
    try:
        uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    except Exception:
        uid = 0
    return f"tg_{uid}" if uid > 0 else ""


def _mark_private_board_tg_activity(window_id: str, target: str) -> None:
    primary = _primary_tg_window_id()
    target_s = str(target or "").strip()
    window_s = str(window_id or "").strip()
    if not primary or (window_s != primary and target_s != primary.removeprefix("tg_")):
        return
    try:
        from storage import r2_store

        r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
    except Exception:
        return


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
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else {}
    pending_type = str((pending or {}).get("type") or "").strip()
    pending_actor = str((pending or {}).get("actor") or "").strip()
    pending_reviewer = str((pending or {}).get("reviewer") or "").strip()
    pending_current_actor = str((pending or {}).get("current_actor") or "").strip()
    pending_phase = str((pending or {}).get("phase") or "").strip()
    pending_name = str((pending or {}).get("name") or "").strip()
    pending_choices = [
        str(item.get("label") or item.get("id") or "").strip()
        for item in ((pending or {}).get("choices") or [])
        if isinstance(item, dict) and str(item.get("label") or item.get("id") or "").strip()
    ]
    long_description_review_tasks = {"反向诱惑", "全部暴露！", "羞耻台词大放送", "自慰陈述"}
    description_task_list = (
        "需要写长篇正文的任务只有："
        "提交类惩罚「反向诱惑」「全部暴露！」「羞耻台词大放送」「自慰陈述」直接用「【描述：...】」；"
        "真心话「真心话点名」用「【真心话出题：...】」或「【真心话回答：...】」；"
        "其他掷骰、Pass、出拳、通过/打回、普通聊天都保持原格式，不要额外套描述。"
    )
    if pending_reviewer == "du" and pending_type == "review" and pending_phase == "questioning":
        rule_lines = [
            "当前有真心话/提问类惩罚需要你先出题。",
            "如果你要提交题目，回复第一行必须单独写「【真心话出题：题目内容】」。",
            description_task_list,
            "没有第一行「【真心话出题：...】」时，只算局内聊天，不会触发出题。",
        ]
    elif pending_actor == "du" and pending_type == "review" and pending_phase != "submitted":
        if pending_name == "真心话点名":
            submit_rule = "如果你要回答真心话，回复第一行必须单独写「【真心话回答：回答内容】」。"
        elif pending_name in long_description_review_tasks:
            submit_rule = "如果你要提交这个惩罚任务，回复第一行必须单独写「【描述：提交内容】」。"
        else:
            submit_rule = "如果你要提交这个惩罚任务，回复第一行必须单独写「【提交】」，正文写在后面。"
        rule_lines = [
            "当前有惩罚任务需要你提交。",
            submit_rule,
            description_task_list,
            "没有第一行对应格式时，只算局内聊天，不会触发提交。",
        ]
    elif pending_actor == "du" and pending_type == "choice":
        choices_text = " / ".join(pending_choices) if pending_choices else "可选项见棋局文本"
        rule_lines = [
            "当前有选择惩罚需要你决定。",
            f"可选项：{choices_text}。",
            "如果你要选择，回复第一行必须单独写精确指令「【选择：选项名】」，选项名必须和可选项完全一致。",
            "如果你要使用Pass卡，第一行必须单独写「【Pass】」。",
            "选择只需要第一行选择指令，不要额外套「【描述：...】」。",
            description_task_list,
            "没有第一行精确指令时，只算局内聊天，不会触发选择。",
        ]
    elif pending_type == "duel" and pending_current_actor == "du":
        choices_text = " / ".join(pending_choices) if pending_choices else "石头 / 剪刀 / 布"
        rule_lines = [
            "当前正在等待你完成剪刀石头布对抗。",
            f"可选项：{choices_text}。",
            "回复第一行必须单独写精确指令「【剪刀石头布：石头】」「【剪刀石头布：剪刀】」或「【剪刀石头布：布】」。",
            "不需要额外说明时保持原来的单行出拳格式。普通聊天不要用「【描述：...】」。",
            "没有第一行精确指令时，只算局内聊天，不会触发出拳。",
        ]
    elif pending_reviewer == "du" and pending_type == "review" and pending_phase == "submitted":
        rule_lines = [
            "当前有小玥提交的惩罚任务需要你验收。",
            "验收按选项来：如果打回，第一行只写「【打回】」。",
            "如果通过，第一行写「【通过】」，第二行必须写「【掷骰】」；通过后立刻轮到你掷骰，不要等下一次同步。",
            "如果可选项以后扩展成别的词，也同样第一行只写「【选项名】」。",
            "没有第一行精确选项时，只算局内聊天，不会触发验收。",
        ]
    else:
        rule_lines = [
            f"当前行动方：{turn_label}。",
            "如果现在轮到你，并且你决定行动，回复第一行必须单独写精确指令「【掷骰】」。",
            "掷骰保持原来的单行格式即可。普通聊天不要用「【描述：...】」。",
            "普通说「掷骰子」「我来投一下」，或者把「【掷骰】」写在句子中间，都只算聊天，不会触发行动。",
        ]
    if mode == "final_note":
        final_note = state.get("final_note") if isinstance(state.get("final_note"), dict) else {}
        note_text = _clean_private_board_text(str((final_note or {}).get("du_text") or message or "").strip())
        if not note_text:
            return ""
        return "\n".join([
            "小玥正在和你玩「涩涩走格棋」。这是终局小纸条，不是普通主聊天正文。",
            "请自然接住终局结果，不要解释工具、接口或系统流程。",
            "",
            "终局小纸条：",
            note_text,
        ]).strip()

    if mode == "roll_result":
        board_lines: list[str] = []
        if roll_result:
            board_lines.extend(["本次掷骰：", roll_result])
        if du_text and du_text != roll_result:
            if board_lines:
                board_lines.append("")
            board_lines.extend(["当前棋局：", du_text])
        note_text = _clean_private_board_text(message)
        parts = [
            "小玥正在和你玩「涩涩走格棋」。这是她刚掷完骰子后的自动同步，不是主聊天正文。",
            "你会看到本次掷骰结果和当前棋局；你只需要自然回应，不要解释工具、接口或系统流程。",
            *rule_lines,
        ]
        if note_text:
            parts.extend(["", "顺带说明：", note_text])
        parts.extend([
            "",
            "本次掷骰结果与当前棋局：",
            "\n".join(board_lines).strip(),
        ])
        return "\n".join(parts).strip()

    if mode == "state_update":
        parts = [
            "小玥正在和你玩「涩涩走格棋」。这是棋局状态同步，不是主聊天正文。",
            "你会看到当前棋局；请按下面规则决定是否行动或处理待处理任务，不要解释工具、接口或系统流程。",
            *rule_lines,
            "",
            "当前棋局：",
            du_text,
        ]
        return "\n".join(parts).strip()

    parts = [
        "小玥正在和你玩「涩涩走格棋」。这是局内普通交流，不是棋局同步，也不是主聊天正文。",
        "这次只处理小玥刚刚说的话；前后文会由同一个聊天窗口的最近对话提供，不要额外复述整盘棋局。",
        "普通聊天直接自然回复，别套「【描述：...】」，也不要为了聊天写棋局精确指令。",
        "只有当小玥明确让你处理当前棋局任务，或者你确实要处理当前待办任务时，才按对应任务规则使用精确指令：真心话用「【真心话出题：...】」「【真心话回答：...】」，四个长篇提交任务用「【描述：...】」，验收按选项写「【通过】」「【打回】」，选择惩罚用「【选择：...】」。",
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
        if mode not in {"chat", "roll_result", "state_update", "final_note"}:
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
        if ok:
            _mark_private_board_tg_activity(window_id, target)
        reply_text = str((wakeup or {}).get("reply_text") or (wakeup or {}).get("reply_preview") or "")
        if ok and mode == "final_note":
            payload = execute_game_command("private_board", "final_note_sent", save_id)
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
