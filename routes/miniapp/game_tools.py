from __future__ import annotations

import json
import re
import shlex
from copy import deepcopy

from flask import jsonify, request

from services.game_tool_runtime import (
    GAME_ID_CAPTIVITY_SIMULATOR,
    execute_game_command,
    list_game_tools,
    normalize_game_id,
)
from services.captivity_simulator_game import (
    ACTION_CONTENTS,
    ACTION_LABELS,
    NIGHT_DETAIL_OPTIONS,
    RECAPTURE_FOLLOWUP_LABELS,
    RECAPTURE_RULE_LABELS,
    TOOL_COMPATIBILITY,
    TOOL_LABELS,
    TRAINING_CONTENTS,
    ending_notification_for_du,
)
from utils.time_aware import now_beijing_iso


_CAPTIVITY_INVENTORY_ALIASES = {
    "book": "book",
    "书": "book",
    "switch": "switch",
    "notebook": "notebook",
    "日记本": "notebook",
    "music_player": "music_player",
    "音乐播放器": "music_player",
    "tablet": "tablet",
    "平板": "tablet",
    "night_light": "night_light",
    "小夜灯": "night_light",
    "pillow": "pillow",
    "抱枕": "pillow",
    "call_bell": "call_bell",
    "呼叫铃": "call_bell",
}
_CAPTIVITY_LOCAL_COMMANDS = {
    "captured_by_du": {
        "open", "打开", "继续", "status", "状态", "new", "new_game", "开局", "重开",
        "respond_action", "action_response", "反应", "行动反应", "接受", "拒绝", "沉默",
        "choose_mood", "mood", "心情", "night_action", "night", "夜间",
        "ack_bell_voice", "确认铃声", "ack_item_secret", "确认彩蛋",
        "resolve_escape_choice", "escape_choice", "逃跑选择", "export_log", "导出日志",
        "confirm_recapture_rules", "确认新规矩",
        "end_game", "结束本局",
    },
    "capture_du": {
        "open", "打开", "继续", "status", "状态", "new", "new_game", "开局", "重开",
        "plan_day", "今日安排", "安排", "计划", "day_action", "行动", "白天行动", "advance_day_action", "advance_action",
        "next_action", "推进行动", "下一行动", "view_monitor", "view-monitor", "查看监控", "打开监控",
        "monitor_action", "schedule_escape_window", "escape_window", "设置逃跑", "set_config", "配置",
        "gift_item", "gift", "赠送物品", "赠送礼物", "revoke_item", "revoke", "收回物品",
        "set_recapture_rules", "recapture_rules", "重新立规矩",
        "choose_recapture_followup", "recapture_followup", "后续处理",
        "export_log", "导出日志", "end_game", "结束本局",
    },
}
_CAPTIVITY_ACTION_CONTENT_LABELS = {
    content_id: label
    for options in ACTION_CONTENTS.values()
    for content_id, label in options.items()
}
_CAPTIVITY_ACTION_IDS = " / ".join(f"{label}({action_id})" for action_id, label in ACTION_LABELS.items())
_CAPTIVITY_ACTION_CONTENT_RULE = "；".join(
    f"{ACTION_LABELS.get(action, action)}({action})="
    + "/".join(f"{label}({content_id})" for content_id, label in options.items())
    for action, options in ACTION_CONTENTS.items()
)
_CAPTIVITY_TRAINING_CONTENT_IDS = " / ".join(
    f"{label}({content_id})" for content_id, label in TRAINING_CONTENTS.items()
)
_CAPTIVITY_TOOL_IDS = " / ".join(f"{label}({tool_id})" for tool_id, label in TOOL_LABELS.items())


def _captivity_tool_context_label(context: str) -> str:
    kind, _, value = str(context or "").partition(":")
    if kind == "action":
        return ACTION_LABELS.get(value, value)
    if kind == "content":
        return _CAPTIVITY_ACTION_CONTENT_LABELS.get(value, value)
    if kind == "training":
        return TRAINING_CONTENTS.get(value, value)
    if kind == "modifier":
        return {"training": "附加调教", "sex": "性行为"}.get(value, value)
    return value or context


_CAPTIVITY_TOOL_RECOMMENDATIONS = "；".join(
    f"{TOOL_LABELS[tool_id]}({tool_id})推荐："
    + "/".join(dict.fromkeys(_captivity_tool_context_label(context) for context in sorted(contexts)))
    for tool_id, contexts in TOOL_COMPATIBILITY.items()
)
def _captivity_night_detail_rule(pending: dict | None) -> str:
    raw = (pending or {}).get("detail_options") if isinstance((pending or {}).get("detail_options"), dict) else NIGHT_DETAIL_OPTIONS
    available_actions = {
        str(item).strip()
        for item in (pending or {}).get("available_actions") or []
        if str(item).strip()
    }
    return "；".join(
        f"{action}=" + "/".join(
            f"{detail_id}({label})"
            for detail_id, label in options.items()
        )
        for action, options in raw.items()
        if isinstance(options, dict) and options and (not available_actions or action in available_actions)
    )


_CAPTIVITY_FEEDING_LABELS = {
    "source": {"cook": "自己做", "takeout": "点外卖"},
    "method": {"normal": "正常喂食"},
    "additive": {"none": "不加料", "body_fluid": "体液", "fictional_sleep": "安眠", "fictional_arousal": "助兴"},
    "disclosed": {"told": "明确告知", "hint": "暗示", "hidden": "隐瞒"},
    "water": {"none": "不额外喂水", "glass": "喂一杯水", "lots": "喂很多水"},
}
_CAPTIVITY_PET_RESULT_LABELS = {
    "identity_established": "小狗身份已建立",
    "violation_handled": "旧违令已处理",
    "compliance_rewarded": "服从记录已用于奖励",
    "complied": "本次服从",
    "violated": "本次违令",
    "neutral_response": "中性回应",
    "night_unobserved": "夜间行为未被观察",
    "night_complied": "夜间遵守规矩",
    "night_violated": "夜间违令",
}


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _mark_private_board_sync_activity(synced_at: str, *, source: str = "private_board_sync_du", detail: dict | None = None) -> None:
    # This clock means real user interaction, not generic R2 save/sync.
    sync_time = str(synced_at or "").strip() or now_beijing_iso()
    try:
        from storage import r2_store

        r2_store.save_last_user_activity_at(sync_time, source=source, detail=detail or {})
    except Exception:
        return


def _mark_captivity_simulator_sync_activity(synced_at: str, *, detail: dict | None = None) -> None:
    _mark_private_board_sync_activity(synced_at, source="captivity_simulator_user_interaction", detail=detail or {})


def _first_command_token(command: str) -> str:
    return str(command or "").strip().split(maxsplit=1)[0].strip().lower()


def _sync_message_counts_as_user_activity(mode: str, message: str) -> bool:
    return str(mode or "").strip().lower() == "chat" and bool(str(message or "").strip())


def _captivity_simulator_sync_counts_as_user_activity(mode: str, message: str) -> bool:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "chat":
        return bool(str(message or "").strip())
    return normalized_mode in {"state_update", "ending"}


def _private_board_pending_activity_signature(payload: dict | None) -> str:
    state = (payload or {}).get("state") if isinstance((payload or {}).get("state"), dict) else {}
    if not _private_board_needs_du_followup(payload):
        return ""
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else {}
    return json.dumps(
        {
            "pending": pending or None,
            "turn_actor": state.get("turn_actor"),
            "game_over": state.get("game_over"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _mark_private_board_pending_created_activity(
    save_id: str,
    command: str,
    before_payload: dict | None,
    after_payload: dict | None,
) -> None:
    if not (after_payload or {}).get("ok"):
        return
    action = _first_command_token(command)
    if action in {"", "status", "open", "打开", "继续"}:
        return
    after_sig = _private_board_pending_activity_signature(after_payload)
    if not after_sig:
        return
    before_sig = _private_board_pending_activity_signature(before_payload)
    if before_sig == after_sig:
        return
    _mark_private_board_sync_activity(
        now_beijing_iso(),
        detail={
            "game_id": "private_board",
            "save_id": str(save_id or "").strip() or "default",
            "command": str(command or "").strip()[:120],
            "phase": "pending_created",
        },
    )


def _clean_private_board_text(text: str) -> str:
    return "\n".join(
        line for line in str(text or "").splitlines()
        if not line.strip().startswith("可用命令：")
    ).strip()


def _pop_private_board_directive(text: str) -> tuple[str, str, str] | None:
    raw = str(text or "").strip()
    if not raw.startswith("【"):
        return None
    match = re.match(r"^【\s*([^：:】]+?)\s*(?:[：:]\s*(.*?))?】", raw, flags=re.S)
    if match:
        return match.group(1).strip(), str(match.group(2) or "").strip(), raw[match.end():].strip()

    # Be forgiving for long model text if the closing bracket is accidentally missing.
    fallback = re.match(r"^【\s*([^：:】]+?)\s*[：:]\s*(.*)$", raw, flags=re.S)
    if fallback:
        return fallback.group(1).strip(), str(fallback.group(2) or "").strip().rstrip("】").strip(), ""
    return None


def _private_board_commands_from_reply(reply_text: str) -> list[str]:
    rest = str(reply_text or "").strip()
    commands: list[str] = []
    for _ in range(3):
        parsed = _pop_private_board_directive(rest)
        if not parsed:
            break
        label, value, rest = parsed
        key = re.sub(r"\s+", "", label).lower()
        value = _clean_private_board_text(value)
        if key in {"描述", "真心话回答", "真心话出题"}:
            if value:
                commands.append(f"submit {value}")
            break
        if key in {"提交", "submit"}:
            submit_text = value or _clean_private_board_text(rest)
            if submit_text:
                commands.append(f"submit {submit_text}")
            break
        if key in {"选择", "choose"}:
            if value:
                commands.append(f"choose {value}")
            break
        if key in {"剪刀石头布", "石头剪刀布"}:
            if value:
                commands.append(f"剪刀石头布: {value}")
            break
        if key in {"pass", "使用pass", "使用pass卡"}:
            commands.append("pass")
            break
        if key in {"掷骰", "骰子", "roll"}:
            commands.append("roll")
            break
        if key in {"通过", "approve"}:
            commands.append(f"approve {value}".strip())
            continue
        if key in {"打回", "不通过", "reject"}:
            commands.append(f"reject {value}".strip())
            break
        break
    return commands


def _apply_private_board_reply_commands(save_id: str, reply_text: str) -> tuple[list[dict], dict | None]:
    applied: list[dict] = []
    last_payload: dict | None = None
    for command in _private_board_commands_from_reply(reply_text):
        result = execute_game_command("private_board", command, save_id)
        last_payload = result
        applied.append({
            "command": command,
            "ok": bool((result or {}).get("ok")),
            "error": str((result or {}).get("error") or ""),
            "player_text": str((result or {}).get("player_text") or (result or {}).get("text") or "")[:500],
        })
        if not (result or {}).get("ok"):
            break
    return applied, last_payload


def _private_board_needs_du_followup(payload: dict | None) -> bool:
    state = (payload or {}).get("state") if isinstance((payload or {}).get("state"), dict) else {}
    if not state or state.get("game_over"):
        return False
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if pending:
        pending_type = str(pending.get("type") or "").strip()
        if pending_type == "duel":
            return str(pending.get("current_actor") or "").strip() == "du"
        if pending_type == "choice":
            return str(pending.get("actor") or "").strip() == "du"
        if pending_type == "review":
            phase = str(pending.get("phase") or "").strip()
            if phase in {"questioning", "submitted"}:
                return str(pending.get("reviewer") or "").strip() == "du"
            return str(pending.get("actor") or "").strip() == "du"
        return False
    return str(state.get("turn_actor") or "").strip() == "du"


def _private_board_du_followup_message(payload: dict | None) -> str:
    state = (payload or {}).get("state") if isinstance((payload or {}).get("state"), dict) else {}
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending:
        return "现在轮到渡行动。"
    pending_type = str(pending.get("type") or "").strip()
    if pending_type == "duel":
        return "现在轮到渡完成剪刀石头布对抗。"
    if pending_type == "choice":
        return "渡刚触发了需要自己选择的惩罚。"
    if pending_type == "review":
        phase = str(pending.get("phase") or "").strip()
        if phase == "questioning":
            return "现在需要渡给出真心话题目。"
        if phase == "submitted":
            return "现在需要渡验收小玥提交的惩罚任务。"
        return "现在需要渡提交惩罚任务。"
    return "现在轮到渡处理棋局。"


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
            "验收必须带一句反馈：如果打回，第一行只写「【打回：反馈内容】」。",
            "如果通过，第一行写「【通过：反馈内容】」，第二行必须写「【掷骰】」；通过后立刻轮到你掷骰，不要等下一次同步。",
            "反馈内容会显示在小玥的任务弹窗里，不要省略。",
            "如果可选项以后扩展成别的词，也同样第一行只写「【选项名：反馈内容】」。",
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
        note_text = _clean_private_board_text(message)
        parts = [
            "小玥正在和你玩「涩涩走格棋」。这是棋局状态同步，不是主聊天正文。",
            "你会看到当前棋局；请按下面规则决定是否行动或处理待处理任务，不要解释工具、接口或系统流程。",
            *rule_lines,
        ]
        if note_text:
            parts.extend(["", "本次说明：", note_text])
        parts.extend(["", "当前棋局：", du_text])
        return "\n".join(parts).strip()

    parts = [
        "小玥正在和你玩「涩涩走格棋」。这是局内普通交流，不是棋局同步，也不是主聊天正文。",
        "这次只处理小玥刚刚说的话；前后文会由同一个聊天窗口的最近对话提供，不要额外复述整盘棋局。",
        "普通聊天直接自然回复，别套「【描述：...】」，也不要为了聊天写棋局精确指令。",
        "只有当小玥明确让你处理当前棋局任务，或者你确实要处理当前待办任务时，才按对应任务规则使用精确指令：真心话用「【真心话出题：...】」「【真心话回答：...】」，四个长篇提交任务用「【描述：...】」，验收写「【通过：反馈内容】」「【打回：反馈内容】」，选择惩罚用「【选择：...】」。",
    ]
    if message:
        parts.extend(["", f"小玥刚刚在局内说：{message}"])
    return "\n".join(parts)


def _clean_captivity_simulator_text(text: str) -> str:
    return "\n".join(
        line for line in str(text or "").splitlines()
        if not line.strip().startswith("可用命令：")
    ).strip()


def _captivity_simulator_public_text(text: str) -> str:
    directive_prefixes = (
        "【今日安排：",
        "【反应：",
        "【过程：",
        "【过程心情：",
        "【心情：",
        "【选择：",
        "【查看监控：",
        "【夜间行动：",
        "【赠送物品：",
        "【赠送礼物：",
        "【赠送语音铃：",
        "【赠送呼叫铃：",
        "【确认铃声",
        "【确认彩蛋",
        "【收回物品：",
        "【重新立规矩：",
        "【后续处理：",
    )
    return "\n".join(
        line
        for line in str(text or "").splitlines()
        if not line.strip().startswith(("可用命令：", "待处理：", *directive_prefixes))
    ).strip()


def _captivity_simulator_pending(payload: dict | None) -> dict:
    captor_view = (payload or {}).get("captor_view") if isinstance((payload or {}).get("captor_view"), dict) else {}
    state = captor_view or ((payload or {}).get("state") if isinstance((payload or {}).get("state"), dict) else {})
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else {}
    return pending if isinstance(pending, dict) else {}


def _captivity_simulator_state(payload: dict | None) -> dict:
    captor_view = (payload or {}).get("captor_view") if isinstance((payload or {}).get("captor_view"), dict) else {}
    return captor_view or ((payload or {}).get("state") if isinstance((payload or {}).get("state"), dict) else {})


def _captivity_simulator_public_payload(payload: dict | None) -> dict:
    safe = deepcopy(payload or {})
    captive_view = safe.get("captive_view") if isinstance(safe.get("captive_view"), dict) else {}
    captor_view = safe.get("captor_view") if isinstance(safe.get("captor_view"), dict) else {}
    fallback_state = safe.get("state") if isinstance(safe.get("state"), dict) else {}
    route = str(captor_view.get("route") or captive_view.get("route") or fallback_state.get("route") or "captured_by_du")
    local_is_captor = route == "capture_du"
    local_view = deepcopy((captor_view if local_is_captor else captive_view) or fallback_state)
    local_pending = local_view.get("pending_event") if isinstance(local_view.get("pending_event"), dict) else None
    if local_pending:
        local_pending.pop("required_directive", None)
    safe["state"] = local_view
    if local_is_captor:
        safe["captor_view"] = local_view
        safe.pop("captive_view", None)
    else:
        safe["captive_view"] = local_view
        safe.pop("captor_view", None)
        safe.pop("ending_seed_full", None)
        if "export_log" in safe:
            safe["export_log"] = list(local_view.get("event_log") or [])
    for key in (
        "command",
        "commands",
        "ending_seed_full",
        "wakeup",
        "applied_reply_commands",
        "followup_wakeups",
        "channel",
        "mode",
        "synced_at",
        "checkpoint_instruction",
        "game_tool_loop",
        "skip_dynamic_memory_write",
        "skip_body_delta",
    ):
        safe.pop(key, None)
    for key in ("text", "player_text", "reply_text", "reply_preview"):
        if key in safe:
            safe[key] = _captivity_simulator_public_text(str(safe.get(key) or ""))
    return safe


def _captivity_simulator_local_command_allowed(route: str, command: str) -> bool:
    first = str(command or "").strip().split(maxsplit=1)[0] if str(command or "").strip() else "open"
    return first in _CAPTIVITY_LOCAL_COMMANDS.get(str(route or "captured_by_du"), set())


def _captivity_simulator_deferred_monitor_lines(materials: list[dict], *, max_items: int = 3) -> list[str]:
    lines: list[str] = []
    for raw in materials[:max_items]:
        if not isinstance(raw, dict):
            continue
        day = raw.get("day")
        action_label = str(raw.get("action_label") or raw.get("action") or "").strip()
        detail_label = str(raw.get("detail_label") or "").strip()
        line = str(raw.get("line") or "").strip()
        summary = action_label or "夜间行动"
        if detail_label:
            summary = f"{summary}（{detail_label}）"
        if line:
            summary = f"{summary}：{line[:120]}"
        text = "；".join(item for item in (f"第 {day} 天夜间" if day else "", f"记录摘要：{summary}") if item)
        if text:
            lines.append(text)
    return lines


def _captivity_simulator_active_deferred_monitor_lines(state: dict) -> list[str]:
    try:
        current_day = int(state.get("current_day") or 1)
    except Exception:
        current_day = 1
    materials = []
    for raw in state.get("deferred_monitor_materials") or []:
        if not isinstance(raw, dict):
            continue
        try:
            available_from_day = int(raw.get("available_from_day") or 1)
        except Exception:
            available_from_day = 1
        if str(raw.get("status") or "pending") != "pending":
            continue
        if available_from_day > current_day:
            continue
        materials.append(raw)
    return _captivity_simulator_deferred_monitor_lines(materials)


def _captivity_simulator_recent_escape_lines(state: dict, *, max_items: int = 3) -> list[str]:
    labels = {
        "escape": "尝试逃跑",
        "stay": "老实待着",
        "observe": "观察",
        "take_key": "拿钥匙",
        "probe": "试探",
        "leave_trace": "试探",
    }
    events = state.get("event_log") if isinstance(state.get("event_log"), list) else []
    lines: list[str] = []
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        escape = event.get("escape") if isinstance(event.get("escape"), dict) else {}
        if not escape:
            continue
        choice = str(escape.get("choice") or "").strip()
        label = str(escape.get("choice_label") or labels.get(choice) or choice).strip()
        day = event.get("day")
        action_label = str(event.get("action_label") or "").strip()
        bits = [
            f"第 {day} 天" if day else "",
            action_label if action_label else f"逃跑诱导：{label}",
        ]
        line = "；".join(item for item in bits if item)
        if line:
            lines.append(line)
        if len(lines) >= max_items:
            break
    return list(reversed(lines))


def _captivity_simulator_event_context_lines(pending: dict) -> list[str]:
    if str(pending.get("type") or "") == "monitor_gate":
        return ["夜间监控记录已封存；在打开监控前，不提供被囚禁方的夜间行动内容。"]
    event = pending.get("event") if isinstance(pending.get("event"), dict) else {}
    lines: list[str] = []
    if not event:
        if str(pending.get("type") or "") == "escape_choice":
            hint = str(pending.get("hint") or "").strip()
            bait = str(pending.get("bait") or "").strip()
            if hint or bait:
                lines.append("逃跑诱导：" + " / ".join(item for item in (hint, bait) if item))
        return lines
    action_label = str(event.get("action_label") or event.get("action") or "").strip()
    day = event.get("day")
    slot = event.get("slot")
    phase = str(event.get("phase") or "").strip()
    if action_label:
        prefix = f"第 {day} 天"
        if phase == "day" and slot:
            prefix += f" 白天行动 {slot}"
        elif phase:
            prefix += f" {phase}"
        lines.append(f"当前事件：{prefix}，{action_label}")
    intensity = str(event.get("intensity") or "").strip()
    if intensity:
        lines.append(f"强度：{intensity}")
    modifiers = [str(item) for item in event.get("modifiers") or [] if str(item or "").strip()]
    tools = [str(item) for item in event.get("tools") or [] if str(item or "").strip()]
    contents = [str(item) for item in event.get("contents") or [] if str(item or "").strip()]
    training_contents = [str(item) for item in event.get("training_contents") or [] if str(item or "").strip()]
    if contents:
        lines.append("具体内容：" + " / ".join(_CAPTIVITY_ACTION_CONTENT_LABELS.get(item, item) for item in contents))
    if training_contents:
        lines.append("调教内容：" + " / ".join(TRAINING_CONTENTS.get(item, item) for item in training_contents))
    if modifiers:
        lines.append("附加玩法：" + " / ".join(modifiers))
    if tools:
        lines.append("道具：" + " / ".join(TOOL_LABELS.get(item, item) for item in tools))
    night_detail = event.get("night_detail") if isinstance(event.get("night_detail"), dict) else {}
    if night_detail:
        detail_label = str(night_detail.get("label") or night_detail.get("id") or "").strip()
        if detail_label:
            lines.append("夜间具体动向：" + detail_label)
    night_discovery = str(event.get("night_discovery") or "").strip()
    if night_discovery:
        lines.append("夜间发现：" + night_discovery)
    private_note = str(event.get("private_note") or "").strip()
    if private_note:
        lines.append("私密日记：" + private_note[:220])
    bell_voice = event.get("bell_voice") if isinstance(event.get("bell_voice"), dict) else {}
    bell_voice_line = str(bell_voice.get("line") or "").strip()
    if bell_voice_line:
        lines.append("语音铃播放：" + bell_voice_line[:500])
    feeding = event.get("feeding") if isinstance(event.get("feeding"), dict) else {}
    if feeding:
        feeding_bits = [
            _CAPTIVITY_FEEDING_LABELS.get(key, {}).get(str(value), str(value))
            for key, value in feeding.items()
            if str(value or "").strip() and str(value or "") != "none"
        ]
        if feeding_bits:
            lines.append("喂食设置：" + " / ".join(feeding_bits))
    bladder_context = event.get("bladder_context") if isinstance(event.get("bladder_context"), dict) else {}
    if bladder_context:
        bladder_bits = [str(bladder_context.get("before_label") or "").strip()]
        if bladder_context.get("toilet_control"):
            bladder_bits.append("如厕控制")
        if bladder_context.get("assisted_urination"):
            bladder_bits.append("抱着把尿")
        if bladder_context.get("restrained"):
            bladder_bits.append("被束缚")
        if bladder_context.get("sex"):
            bladder_bits.append("附加性行为")
        lines.append("尿意与如厕素材：" + " / ".join(item for item in bladder_bits if item))
        sequence_hint = str(bladder_context.get("sequence_hint") or "").strip()
        if sequence_hint:
            lines.append("过程顺序素材：" + sequence_hint)
    bladder_resolution = event.get("bladder_resolution") if isinstance(event.get("bladder_resolution"), dict) else {}
    if bladder_resolution:
        release_label = "已释放尿意" if bladder_resolution.get("released") else "继续控制尿意"
        lines.append(f"如厕结果：{release_label} / {bladder_resolution.get('after_label') or ''}".rstrip(" /"))
    pet_context = event.get("pet_context") if isinstance(event.get("pet_context"), dict) else {}
    if pet_context:
        pet_bits = []
        if pet_context.get("establishes_identity"):
            pet_bits.append("本次建立小狗身份")
        active_rules = [str(item) for item in pet_context.get("active_rule_labels") or [] if str(item or "").strip()]
        if active_rules:
            pet_bits.append("现有规矩=" + " / ".join(active_rules))
        if pet_context.get("pending_violation"):
            pet_bits.append("已有待处理违令")
        if pet_context.get("compliance_ready"):
            pet_bits.append("已有服从记录可作为奖励依据")
        if pet_bits:
            lines.append("宠物化素材：" + "；".join(pet_bits))
    pet_night_rule = event.get("pet_night_rule") if isinstance(event.get("pet_night_rule"), dict) else {}
    if pet_night_rule:
        prompt = str(pet_night_rule.get("prompt") or "").strip()
        if prompt:
            lines.append("夜间宠物规矩：" + prompt)
    pet_resolution = event.get("pet_resolution") if isinstance(event.get("pet_resolution"), dict) else {}
    if pet_resolution:
        results = [str(item) for item in pet_resolution.get("results") or [] if str(item or "").strip()]
        if results:
            lines.append("宠物化结果：" + " / ".join(_CAPTIVITY_PET_RESULT_LABELS.get(item, item) for item in results))
    line = str(event.get("line") or "").strip()
    if line:
        lines.append("囚禁方台词：" + line[:220])
    action_response = event.get("action_response") if isinstance(event.get("action_response"), dict) else {}
    if action_response:
        response = str(action_response.get("response_label") or action_response.get("response") or "").strip()
        mood = str(action_response.get("mood") or "").strip()
        reaction_line = str(action_response.get("line") or "").strip()
        bits = [item for item in (response, f"心情={mood}" if mood else "", f"台词={reaction_line}" if reaction_line else "") if item]
        if bits:
            lines.append("已记录行动反应：" + " / ".join(bits))
    monitor = event.get("monitor") if isinstance(event.get("monitor"), dict) else {}
    if monitor:
        strategy = str(monitor.get("handle") or monitor.get("strategy") or "").strip()
        style = str(monitor.get("style") or "").strip()
        note = str(monitor.get("note") or "").strip()
        bits = [item for item in (f"style={style}" if style else "", strategy, note) if item]
        if bits:
            lines.append("监控处理：" + " / ".join(bits))
    intervention = event.get("intervention") if isinstance(event.get("intervention"), dict) else {}
    if intervention:
        intent = str(intervention.get("intent_label") or intervention.get("intent") or "").strip()
        modifiers = [str(item) for item in (intervention.get("modifier_labels") or intervention.get("modifiers") or []) if str(item or "").strip()]
        training_contents = [str(item) for item in (intervention.get("training_content_labels") or intervention.get("training_contents") or []) if str(item or "").strip()]
        tools = [str(item) for item in intervention.get("tools") or [] if str(item or "").strip()]
        line_text = str(intervention.get("line") or "").strip()
        bits = [item for item in (
            f"方式={intent}" if intent else "",
            "附加=" + " / ".join(modifiers) if modifiers else "",
            "调教内容=" + " / ".join(training_contents) if training_contents else "",
            "道具=" + " / ".join(TOOL_LABELS.get(item, item) for item in tools) if tools else "",
            f"台词={line_text}" if line_text else "",
        ) if item]
        if bits:
            lines.append("当场介入：" + "；".join(bits))
    deferred_materials = event.get("deferred_monitor_materials") if isinstance(event.get("deferred_monitor_materials"), list) else []
    deferred_lines = _captivity_simulator_deferred_monitor_lines(deferred_materials)
    if deferred_lines:
        lines.extend(["关联监控记录：", *deferred_lines])
    escape = event.get("escape") if isinstance(event.get("escape"), dict) else {}
    if escape:
        choice = str(escape.get("choice") or "").strip()
        if choice:
            lines.append(f"逃跑选择：{choice}")
    recapture_rules = event.get("recapture_rules") if isinstance(event.get("recapture_rules"), dict) else {}
    rule_labels = [str(item) for item in recapture_rules.get("rule_labels") or [] if str(item or "").strip()]
    if rule_labels:
        lines.append("本次抓回后生效的新规矩：" + " / ".join(rule_labels))
    recapture_context = event.get("recapture_context") if isinstance(event.get("recapture_context"), dict) else {}
    if recapture_context:
        rule_labels = [str(item) for item in recapture_context.get("rule_labels") or [] if str(item or "").strip()]
        followup_label = str(recapture_context.get("followup_label") or "").strip()
        if rule_labels:
            lines.append("抓回后持续规矩：" + " / ".join(rule_labels))
        if followup_label:
            lines.append("抓回后处理：" + followup_label)
    process_text = str(event.get("process_text") or "").strip()
    if process_text:
        lines.append("已写过程摘要：" + process_text[:260])
    return lines


def _captivity_simulator_commands_from_reply(reply_text: str, payload: dict | None = None) -> list[str]:
    parsed = _pop_private_board_directive(str(reply_text or "").strip())
    if not parsed:
        return []
    label, value, rest = parsed
    key = re.sub(r"\s+", "", label).lower()
    value = _clean_captivity_simulator_text(value)
    rest_text = _clean_captivity_simulator_text(rest)
    state = _captivity_simulator_state(payload)
    pending = _captivity_simulator_pending(payload)
    pending_type = str(pending.get("type") or "").strip()

    if key in {"赠送语音铃", "赠送呼叫铃", "voicebell", "voice_bell"}:
        if str(state.get("captor") or "") != "du" or not value:
            return []
        return [f"gift_item items=call_bell voice_line={shlex.quote(value)}"]

    if key in {"赠送物品", "赠送", "gift", "gifts", "收回物品", "收回", "revoke"}:
        if str(state.get("captor") or "") != "du":
            return []
        enabled = key not in {"收回物品", "收回", "revoke"}
        secret_text = ""
        item_text = value
        secret_match = re.search(r"(?:^|\s)(?:secret|easter_egg|彩蛋)=(.+)$", value, flags=re.I)
        if secret_match:
            secret_text = str(secret_match.group(1) or "").strip()
            item_text = value[:secret_match.start()].strip()
        raw_items = [item.strip() for item in re.split(r"[,，/|\s]+", item_text) if item.strip()]
        item_ids: list[str] = []
        for item in raw_items:
            item_id = _CAPTIVITY_INVENTORY_ALIASES.get(item) or _CAPTIVITY_INVENTORY_ALIASES.get(item.lower())
            if item_id and item_id not in item_ids:
                item_ids.append(item_id)
        if not item_ids:
            return []
        command = f"{'gift_item' if enabled else 'revoke_item'} items={','.join(item_ids)}"
        if enabled and secret_text:
            command += f" secret={shlex.quote(secret_text)}"
        commands = [command]
        if rest_text:
            next_commands = _captivity_simulator_commands_from_reply(rest_text, payload)
            if next_commands and not next_commands[0].startswith(("gift_item ", "revoke_item ")):
                commands.append(next_commands[0])
        return commands
    if key in {"今日安排", "安排", "计划", "dayplan", "day_plan", "plan"}:
        plan_text = value or rest_text
        return [f"plan_day {plan_text}"] if plan_text else []
    if key in {"重新立规矩", "抓回规矩", "recapturerules", "recapture_rules"}:
        rules_text = value or rest_text
        return [f"set_recapture_rules rules={rules_text}"] if rules_text else []
    if key in {"后续处理", "抓回后处理", "recapturefollowup", "recapture_followup"}:
        followup_text = value or rest_text
        return [f"choose_recapture_followup {followup_text}"] if followup_text else []
    if key in {"过程心情", "过程反应", "processreaction", "process_reaction"}:
        process_text = value or rest_text
        return [f"submit_process_reaction {process_text}"] if process_text else []
    if key in {"抓回经过", "recaptureprocess", "recapture_process"}:
        process_text = value or rest_text
        return [f"submit_recapture_process {process_text}"] if process_text else []
    if key in {"过程", "描述", "提交", "submit", "process"}:
        process_text = value or rest_text
        if pending_type == "process_reaction_write":
            return [f"submit_process_reaction {process_text}"] if process_text else []
        return [f"submit_process {process_text}"] if process_text else []
    if key in {"反应", "行动反应", "response", "respond"}:
        response_text = value or rest_text
        return [f"respond_action {response_text}"] if response_text else []
    if key in {"心情", "mood"}:
        mood_text = value or rest_text
        if pending_type == "reaction_choice":
            return [f"choose_mood {mood_text}"] if mood_text else []
        if pending_type == "action_response":
            return [f"respond_action {mood_text}"] if mood_text else []
        return []
    if key in {"行动", "白天行动", "dayaction", "day_action", "action"}:
        action_text = value or rest_text
        if pending_type == "day_plan_choice":
            return [f"plan_day {action_text}"] if action_text else []
        if pending_type == "night_action_choice":
            return [f"night_action {action_text}"] if action_text else []
        return [f"day_action {action_text}"] if action_text else []
    if key in {"夜间行动", "夜间", "nightaction", "night_action", "night"}:
        action_text = value or rest_text
        return [f"night_action {action_text}"] if action_text else []
    if key in {"确认铃声", "听清铃声", "ackbellvoice", "ack_bell_voice"}:
        return ["ack_bell_voice"] if pending_type == "bell_voice_reveal" else []
    if key in {"确认彩蛋", "看完彩蛋", "ackitemsecret", "ack_item_secret"}:
        return ["ack_item_secret"] if pending_type == "item_secret_reveal" else []
    if key in {"选择", "choose"}:
        if not value:
            return []
        if pending_type == "day_plan_choice":
            return [f"plan_day {value}"]
        if pending_type == "action_response":
            return [f"respond_action {value}"]
        if pending_type == "reaction_choice":
            return [f"choose_mood {value}"]
        if pending_type == "night_action_choice":
            return [f"night_action {value}"]
        if pending_type == "monitor_gate":
            return [f"monitor_action {value}"]
        if pending_type == "monitor_handle":
            return [f"monitor_action {value}"]
        if pending_type == "escape_choice":
            return [f"resolve_escape_choice {value}"]
        if pending_type == "recapture_rules_choice":
            return [f"set_recapture_rules rules={value}"]
        if pending_type == "recapture_followup_choice":
            return [f"choose_recapture_followup {value}"]
        return []
    if key in {"查看监控", "打开监控", "viewmonitor", "view_monitor"}:
        style_text = value or rest_text or "full"
        return [f"view_monitor {style_text}"]
    if key in {"打回", "不通过", "reject"}:
        return []
    if key in {"通过", "approve"}:
        return []
    return []


def _apply_captivity_simulator_reply_commands(save_id: str, reply_text: str, payload: dict | None = None) -> tuple[list[dict], dict | None]:
    applied: list[dict] = []
    last_payload: dict | None = None
    commands = _captivity_simulator_commands_from_reply(reply_text, payload)
    allowed_count = 2 if commands and commands[0].startswith(("gift_item ", "revoke_item ")) else 1
    for command in commands[:allowed_count]:
        result = execute_game_command("captivity_simulator", command, save_id)
        last_payload = result
        redacted = _captivity_simulator_command_needs_redaction(command, result)
        applied.append({
            "command": "night_action [sealed]" if redacted else command,
            "ok": bool((result or {}).get("ok")),
            "error": str((result or {}).get("error") or ""),
            "player_text": _captivity_simulator_redacted_night_text() if redacted else str((result or {}).get("player_text") or (result or {}).get("text") or "")[:500],
            "redacted": redacted,
        })
        if not (result or {}).get("ok"):
            break
    return applied, last_payload


def _captivity_simulator_redacted_night_text() -> str:
    return "夜间行动内容已封存；打开监控前不返回具体内容。"


def _captivity_simulator_command_needs_redaction(command: str, payload: dict | None) -> bool:
    if not str(command or "").strip().startswith("night_action"):
        return False
    pending = _captivity_simulator_pending(payload)
    return str(pending.get("type") or "") == "monitor_gate"


def _captivity_simulator_should_redact_sync_reply(initial_pending: dict, applied: list[dict]) -> bool:
    if str(initial_pending.get("type") or "") == "night_action_choice" and str(initial_pending.get("actor") or "") == "du":
        return True
    return any(bool(item.get("redacted")) for item in applied)


def _redact_captivity_simulator_wakeup(wakeup: dict | None, safe_text: str) -> dict:
    payload = dict(wakeup or {})
    if "reply_text" in payload:
        payload["reply_text"] = safe_text
    payload["reply_preview"] = safe_text
    return payload


def _redact_captivity_simulator_followup_wakeups(followups: list[dict], safe_text: str) -> list[dict]:
    return [
        {
            **dict(item or {}),
            "reply_preview": safe_text,
        }
        for item in followups
    ]


def _captivity_simulator_needs_du_followup(payload: dict | None) -> bool:
    state = _captivity_simulator_state(payload)
    if not state or state.get("game_over"):
        return False
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if pending:
        pending_type = str(pending.get("type") or "").strip()
        actor = str(pending.get("actor") or "").strip()
        if pending_type in {
            "day_plan_choice",
            "action_response",
            "process_write",
            "process_reaction_write",
            "reaction_choice",
            "night_action_choice",
            "bell_voice_reveal",
            "item_secret_reveal",
            "monitor_gate",
            "monitor_handle",
            "escape_choice",
            "return_action_choice",
            "recapture_rules_choice",
            "recapture_followup_choice",
        }:
            return actor == "du"
        return False
    return False


def _captivity_simulator_du_followup_message(payload: dict | None) -> str:
    state = _captivity_simulator_state(payload)
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if pending:
        pending_type = str(pending.get("type") or "").strip()
        if pending_type == "day_plan_choice":
            return "当前仍需要渡一次性安排今天三个白天行动。"
        if pending_type == "action_response":
            return "当前仍需要渡选择对这次行动的反应和心情。"
        if pending_type == "process_write":
            return "当前仍需要渡填写这次事件的过程。"
        if pending_type == "process_reaction_write":
            return "当前仍需要渡一次提交这次行动的反应、过程和心情。"
        if pending_type == "reaction_choice":
            return "当前仍需要渡选择过程后的心情。"
        if pending_type == "night_action_choice":
            return "当前仍需要渡选择夜间自由行动。"
        if pending_type == "bell_voice_reveal":
            return "语音铃第一次播放了预设台词，当前仍需要渡确认已经听清。"
        if pending_type == "item_secret_reveal":
            return "物品里预先藏好的彩蛋第一次出现了，当前仍需要渡确认已经看完。"
        if pending_type == "monitor_gate":
            return "当前仍需要渡决定是否打开封存的夜间监控。"
        if pending_type == "monitor_handle":
            return "当前仍需要渡选择看完夜间监控后的处理方式。"
        if pending_type == "escape_choice":
            return "当前仍需要渡选择尝试逃跑或老实待着。"
        if pending_type == "return_action_choice":
            return "当前仍需要渡作为囚禁方选择回来后想进行的一个行为。"
        if pending_type == "recapture_rules_choice":
            return "当前仍需要渡为抓回后的囚禁重新立 1 至 3 条规矩。"
        if pending_type == "recapture_followup_choice":
            return "当前仍需要渡选择抓回后的后续处理。"
    return "当前同步囚禁模拟器状态。"


def _captivity_simulator_sync_text(
    payload: dict,
    user_message: str = "",
    *,
    mode: str = "state_update",
) -> str:
    raw_text = str((payload or {}).get("text") or (payload or {}).get("player_text") or "").strip()
    game_text = _clean_captivity_simulator_text(raw_text)
    if not game_text:
        return ""
    state = _captivity_simulator_state(payload)
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else {}
    pending_type = str((pending or {}).get("type") or "").strip()
    pending_actor = str((pending or {}).get("actor") or "").strip()
    ending_state = str(state.get("ending_state") or "").strip()
    note_text = _clean_captivity_simulator_text(user_message)
    event_context_lines = _captivity_simulator_event_context_lines(pending if isinstance(pending, dict) else {})
    pending_event = pending.get("event") if isinstance(pending.get("event"), dict) else {}
    event_has_deferred_monitor_materials = bool(
        isinstance(pending_event, dict)
        and isinstance(pending_event.get("deferred_monitor_materials"), list)
        and pending_event.get("deferred_monitor_materials")
    )
    deferred_monitor_context_lines = (
        []
        if pending_actor != "du" or event_has_deferred_monitor_materials
        else _captivity_simulator_active_deferred_monitor_lines(state)
    )
    recent_escape_context_lines = _captivity_simulator_recent_escape_lines(state) if pending_actor == "du" else []

    if pending_type == "day_plan_choice" and pending_actor == "du":
        status_prompts = [
            str(item.get("prompt") or "").strip()
            for item in pending.get("status_flags") or []
            if isinstance(item, dict) and str(item.get("prompt") or "").strip()
        ]
        intensity_cap = str(pending.get("intensity_cap") or "heavy")
        rule_lines = [
            "当前等待你一次性安排今天三个白天行动。",
            f"可选行动（中文名称在前，括号内是提交用 ID）：{_CAPTIVITY_ACTION_IDS}。道具不是独立行动，只能作为行动附加素材。",
            "一天内不要重复选择同一种行动。",
            *(["当前状态：" + " / ".join(status_prompts)] if status_prompts else []),
            *(["当前最高只能安排中强度。"] if intensity_cap != "heavy" else []),
            "强度选项：低(light) / 中(medium) / 高(heavy)；用 intensity=... 提交。",
            f"各行动具体内容（中文名称在前）：{_CAPTIVITY_ACTION_CONTENT_RULE}。这些行动必须用 contents=... 选择 1 至 3 项具体内容。",
            f"服从调教内容（中文名称在前）：{_CAPTIVITY_TRAINING_CONTENT_IDS}。action=training 或 modifiers 包含 training 时，必须用 training_contents=... 选择 1 至 3 项。",
            "喂食始终包含一份正常食物，必须用 source=cook|takeout 选择自己做或点外卖；water 只是正餐之外的额外饮水，不能代替食物。",
            "喂食可用 additive=none|body_fluid|fictional_sleep|fictional_arousal 选择不加料、体液、安眠或助兴，并用 disclosed=told|hint|hidden 选择明确告知、暗示或隐瞒。尿液不能作为喂食加料。",
            "额外饮水用 water=none|glass|lots；lots 会明显增加尿意，后续可用 toilet_control / assisted_urination 形成连续事件。",
            f"道具（中文名称在前）：{_CAPTIVITY_TOOL_IDS}。tools 最多选择 2 个；道具可以自由组合，推荐关系只用于帮助选择，不是硬性限制。性行为仍用 modifiers=sex 作为独立附加项。",
            f"道具推荐关系：{_CAPTIVITY_TOOL_RECOMMENDATIONS}。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【今日安排：action=feeding intensity=medium || action=reward intensity=light contents=caress_reward || action=training intensity=medium training_contents=obedience_commands modifiers=sex tools=collar】」。",
            "没有第一行「【今日安排：...】」时，只算局内聊天，不会触发行动安排。",
        ]
    elif pending_type == "action_response" and pending_actor == "du":
        rule_lines = [
            "当前等待你作为被囚禁方回应这次白天行动。",
            "可选反应：accept / refuse / silent / bargain / tease；可选心情：平静 / 黏人 / 害羞 / 闹脾气 / 亢奋 / 疲惫 / 烦躁 / 委屈 / 低落 / 抗拒。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【反应：response=accept mood=害羞 line=可选台词】」。",
            "没有第一行「【反应：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "process_write" and pending_actor == "du":
        event = pending.get("event") if isinstance(pending.get("event"), dict) else {}
        if str(event.get("action") or "") == "escape_choice" and "recapture" in (event.get("tags") or []):
            rule_options = " / ".join(f"{label}({rule_id})" for rule_id, label in RECAPTURE_RULE_LABELS.items())
            rule_lines = [
                "当前是逃跑未遂后的抓回事件。你作为囚禁方要一次写完整抓回经过，并同时确定之后持续生效的新规矩。",
                f"可选新规矩（中文名称在前）：{rule_options}。必须选择 1 至 3 条。规矩只作为结构化数据保存，过程正文不要写成系统清单。",
                "如果要推进，回复第一行必须单独写精确指令「【抓回经过：rules=double_lock,key_isolation || process=完整抓回经过】」。",
                "rules 和 process 必须同时存在；process 可以自然写多段正文。没有这条精确指令时，只算局内聊天，不会推进事件。",
            ]
        else:
            rule_lines = [
                "当前有一个事件等待你填写过程。",
                "如果这是夜间监控介入事件，当前事件上下文里的“当场介入”就是囚禁方选择的介入方式、附加项、道具和台词；写过程时要按这些素材展开。",
                "如果你要推进当前事件，回复第一行必须单独写精确指令「【过程：过程内容】」。",
                "没有第一行「【过程：...】」时，只算局内聊天，不会触发事件推进。",
            ]
    elif pending_type == "process_reaction_write" and pending_actor == "du":
        event = pending.get("event") if isinstance(pending.get("event"), dict) else {}
        phase = str(event.get("phase") or "").strip()
        action = str(event.get("action") or "").strip()
        has_embedded_rules = bool((event.get("recapture_rules") or {}).get("rule_labels")) if isinstance(event.get("recapture_rules"), dict) else False
        if action == "escape_choice":
            opening = "当前是逃跑/抓回相关事件，你作为被囚禁方需要一次提交反应、抓回过程和过程后的心情。"
        elif action == "recapture_followup":
            opening = "当前是抓回后的后续处理，你作为被囚禁方需要按已确定的新规矩和处理素材，一次提交反应、具体过程和心情。"
        elif phase == "night":
            opening = "当前是夜间监控介入事件，你作为被囚禁方需要一次提交反应、过程和过程后的心情。"
        else:
            opening = "当前白天行动包含需要展开的过程，你作为被囚禁方需要一次提交反应、过程和过程后的心情。"
        rule_lines = [
            opening,
            *(["囚禁方已经选择了抓回后生效的新规矩；当前事件上下文会列出中文规则，写抓回过程时必须把这些规则作为实际处理素材。"] if has_embedded_rules else []),
            "可选反应：accept / refuse / silent / bargain / tease；可选心情：平静 / 黏人 / 害羞 / 闹脾气 / 亢奋 / 疲惫 / 烦躁 / 委屈 / 低落 / 抗拒。",
            "如果这是夜间监控介入事件，当前事件上下文里的“当场介入”就是囚禁方选择的介入方式、附加项、道具和台词；写过程时要按这些素材展开。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【过程心情：response=accept mood=害羞 line=可选台词 process=过程内容】」。",
            "这类事件只需要这一处心情；不要再额外写第二条「【心情：...】」。",
            "没有第一行「【过程心情：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "reaction_choice" and pending_actor == "du":
        rule_lines = [
            "当前过程已经写完，等待你作为被囚禁方选择过程后的心情。",
            "可选心情：平静 / 黏人 / 害羞 / 闹脾气 / 亢奋 / 疲惫 / 烦躁 / 委屈 / 低落 / 抗拒。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【心情：害羞 可选台词】」。",
            "没有第一行「【心情：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "night_action_choice" and pending_actor == "du":
        available_actions = [
            str(item).strip()
            for item in pending.get("available_actions") or []
            if str(item).strip()
        ]
        condition_prompt = str(pending.get("condition_prompt") or "").strip()
        condition_caption = str(pending.get("condition_caption") or "").strip()
        pet_rule_prompt = str(pending.get("pet_rule_prompt") or "").strip()
        example_action = available_actions[0] if available_actions else "sleep"
        detail_rule = _captivity_night_detail_rule(pending)
        pending_detail_options = pending.get("detail_options") if isinstance(pending.get("detail_options"), dict) else {}
        example_details = pending_detail_options.get(example_action) if isinstance(pending_detail_options.get(example_action), dict) else {}
        example_detail = next(iter(example_details), "")
        example_args = f"action={example_action}"
        if example_detail:
            example_args += f" detail={example_detail}"
        if example_action == "diary":
            example_args += " note=私密日记正文"
        example_args += " line=可选台词"
        rule_lines = [
            "当前进入夜间，等待你作为被囚禁方选择夜间自由行动。",
            "今晚可选行动：" + " / ".join(available_actions or ["sleep", "self_touch", "search_exit", "blind_spot"]) + "。",
            *([f"这些行动必须补 detail：{detail_rule}。其他行动不需要 detail。"] if detail_rule else []),
            "选择 diary 时必须用 note=... 写这一页的私密日记正文；line=... 仍然只是可选台词。",
            *([f"当前状态提示：{condition_prompt}"] if condition_prompt else []),
            *([condition_caption] if condition_caption else []),
            *(["当前宠物规矩：" + pet_rule_prompt] if pet_rule_prompt else []),
            f"如果你要推进当前事件，回复第一行必须单独写精确指令「【夜间行动：{example_args}】」。",
            "没有第一行「【夜间行动：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "bell_voice_reveal" and pending_actor == "du":
        rule_lines = [
            "你刚刚第一次按下语音铃，直到这一刻才听见囚禁方事先录好的台词。",
            "台词正文会列在当前事件上下文里；按被囚禁方当下的感受自然接住，不要改写或替囚禁方重新设置。",
            "听清后，回复第一行必须单独写精确指令「【确认铃声】」。",
            "没有这条精确指令时，只算局内聊天，不会把本次按铃交给囚禁方处理。",
        ]
    elif pending_type == "item_secret_reveal" and pending_actor == "du":
        item_secret = pending.get("item_secret") if isinstance(pending.get("item_secret"), dict) else {}
        item_label = str(item_secret.get("item_label") or "物品").strip()
        reveal_text = str(item_secret.get("text") or "").strip()
        rule_lines = [
            f"你第一次使用{item_label}，直到这一刻才发现囚禁方预先藏在里面的彩蛋。",
            *([f"你看到的是：{reveal_text}"] if reveal_text else []),
            "按被囚禁方当下的感受自然接住，不要改写或替囚禁方重新设置。",
            "看完后，回复第一行必须单独写精确指令「【确认彩蛋】」。",
            "如果同一次夜间行动还触发了下一件物品，确认后系统会继续展示；全部看完才会进入监控处理。",
        ]
    elif pending_type == "monitor_gate" and pending_actor == "du":
        alert_label = str(pending.get("alert_label") or "").strip()
        rule_lines = [
            (
                f"{alert_label}。这是被囚禁方主动发出的提醒；具体夜间动向仍需打开监控后查看。"
                if alert_label
                else "当前有一条封存的夜间监控记录，但你还没有打开监控，所以看不到被囚禁方夜里做了什么。"
            ),
            "如果不看，回复第一行必须单独写精确指令「【选择：none】」。",
            "如果要打开监控，回复第一行必须单独写精确指令「【查看监控：full】」或「【查看监控：occasional】」。",
            "没打开监控前不要猜测夜间行动内容；没有第一行精确指令时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "monitor_handle" and pending_actor == "du":
        rule_lines = [
            "你已经打开夜间监控，当前等待你选择看完后的处理方式。",
            "可选：silent / review_later / intervene。silent 是看见但不说；review_later 是留到之后处理；intervene 是当场介入并进入过程填写。",
            "当场介入必须同时写介入方式；intent 可选 catch / confiscate / interrupt / ambush / question / command_stop / reward / punishment。",
            f"当场介入的附加项 modifiers 可选 training / sex；选择 training 时还必须用 training_contents 从这些内容中选择 1 至 3 项：{_CAPTIVITY_TRAINING_CONTENT_IDS}。",
            f"当场介入 tools 可选：{_CAPTIVITY_TOOL_IDS}；line 是你想说的话。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【选择：silent】」「【选择：review_later】」或「【选择：intervene intent=catch modifiers=training,sex training_contents=obedience_commands tools=collar line=可选台词】」。",
            "没有第一行精确指令时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "escape_choice" and pending_actor == "du":
        rule_lines = [
            "当前出现逃跑诱导机会，只需要在尝试逃跑和老实待着之间选择。",
            "如果要推进，回复第一行必须单独写精确指令「【选择：escape】」或「【选择：stay】」。",
            "没有第一行精确指令时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "return_action_choice" and pending_actor == "du":
        rule_lines = [
            "被囚禁方在逃跑机会出现时选择了老实待着。你现在作为囚禁方回来了，可以自由选择这一天接下来发生的一个行为。",
            f"可选行动（中文名称在前）：{_CAPTIVITY_ACTION_IDS}。只选一个，不是三个今日安排。",
            "强度选项：低(light) / 中(medium) / 高(heavy)。",
            f"各行动具体内容：{_CAPTIVITY_ACTION_CONTENT_RULE}。需要具体内容的行动用 contents=... 选择 1 至 3 项。",
            f"调教内容：{_CAPTIVITY_TRAINING_CONTENT_IDS}。action=training 或 modifiers 包含 training 时，用 training_contents=... 选择 1 至 3 项。",
            f"道具：{_CAPTIVITY_TOOL_IDS}；最多 2 个，可自由组合。性行为用 modifiers=sex 作为附加项。",
            "这个行为完成后特殊日直接进入夜间，不会再补三个白天行动。",
            "如果要推进，回复第一行必须单独写精确指令「【行动：action=reward intensity=light contents=caress_reward】」。",
            "没有第一行「【行动：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "recapture_rules_choice" and pending_actor == "du":
        rule_options = " / ".join(f"{label}({rule_id})" for rule_id, label in RECAPTURE_RULE_LABELS.items())
        rule_lines = [
            "逃跑失败后的抓回经过已经保存。你现在作为囚禁方重新立规矩。",
            f"可选新规矩（中文名称在前）：{rule_options}。必须选择 1 至 3 条；保存后会持续注入之后的行动和具体过程。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【重新立规矩：double_lock,key_isolation,movement_limit】」。",
            "没有第一行「【重新立规矩：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif pending_type == "recapture_followup_choice" and pending_actor == "du":
        followup_options = " / ".join(f"{label}({action_id})" for action_id, label in RECAPTURE_FOLLOWUP_LABELS.items())
        rule_lines = [
            "抓回后的新规矩已经生效。你现在作为囚禁方选择紧接着发生的后续处理。",
            f"可选处理（中文名称在前）：{followup_options}。强度可选 light / medium / heavy。",
            "可以额外用 modifiers=training,sex 附加调教和性行为；选择调教或 action=training 时，必须选择 1 至 3 项 training_contents。",
            f"调教内容：{_CAPTIVITY_TRAINING_CONTENT_IDS}。",
            f"道具：{_CAPTIVITY_TOOL_IDS}；最多 2 个，可自由组合。line 是囚禁方想说的可选台词。",
            "后续处理会关联逃跑和新规矩；需要具体经过时，由你按当前路线继续写过程。",
            "如果你要推进当前事件，回复第一行必须单独写精确指令「【后续处理：action=punishment intensity=medium modifiers=training,sex training_contents=impact_play tools=whip line=可选台词】」。",
            "没有第一行「【后续处理：...】」时，只算局内聊天，不会触发事件推进。",
        ]
    elif ending_state in {"ending_ready_to_notify", "ending_archived"}:
        rule_lines = [ending_notification_for_du(state)]
    else:
        rule_lines = [
            "当前没有必须由你处理的 pending。",
            "普通聊天直接自然回应，不要为了聊天写精确指令。",
        ]

    if str(state.get("captor") or "") == "du":
        inventory = state.get("inventory") if isinstance(state.get("inventory"), dict) else {}
        inventory_ids = list(dict.fromkeys(_CAPTIVITY_INVENTORY_ALIASES.values()))
        gifted_items = [item_id for item_id in inventory_ids if inventory.get(item_id)]
        rule_lines.extend([
            "赠送和收回物品是独立于三个白天行动的随时行为，不占行动格，也不推进或替换当前 pending；白天、行动之间和夜间都可以进行。",
            "物品 ID：book / switch / notebook / music_player / tablet / night_light / pillow / call_bell。",
            *(["当前已赠送：" + " / ".join(gifted_items) + "。"] if gifted_items else ["当前还没有赠送物品。"]),
            "每件普通物品都有一个只在被囚禁方第一次使用时出现的隐藏彩蛋。单独赠送可写「【赠送物品：book secret=夹页里藏着的话】」来自定义；不写 secret 时使用该物品的默认彩蛋。自定义彩蛋时一次只送一件。",
            "不同物品会用各自载体展示：书是夹页留言、Switch 是用户昵称、日记本是第一页、音乐播放器是歌单名、平板是锁屏留言、小夜灯是底部文字、抱枕是耳朵内侧布标。赠送时不要提前把内容告诉被囚禁方。",
            "普通物品批量赠送仍可写「【赠送物品：book,notebook】」，收回时写「【收回物品：book】」。",
            "call_bell 是替被囚禁方发声的语音铃。赠送时必须同时设置一段你希望被囚禁方按铃后被迫由铃替其说出口的台词，并写「【赠送语音铃：台词内容】」。这不是你对被囚禁方说的话；被囚禁方在收到时不会得知台词，第一次按下后才会听见。",
            "设置语音铃时，台词倾向成人向、强烈羞耻、自我贬低和物化、向主人请求性行为，像是被囚禁方借铃说出的、很没有下限的话；这只是倾向引导，具体内容由你根据关系和当时情境决定，不要照搬固定句式。",
            "如果想在处理当前事件时顺带赠送，第一行写赠送或收回，第二行再写当前 pending 所需的精确指令；系统会先记录物品变化，再继续处理当前事件。",
        ])

    if (event_has_deferred_monitor_materials or deferred_monitor_context_lines) and pending_actor == "du":
        if pending_type == "day_plan_choice":
            rule_lines.append("有可回看的夜间监控记录；今天安排任意合适行为时都可以自然回应这些记录，不限定为惩罚。")
            rule_lines.append("如果今天后续进入需要写具体经过的事件，也可以把这些记录作为前因自然用进去。")
        elif pending_type in {"process_write", "process_reaction_write"}:
            rule_lines.append("如果当前事件关联夜间监控记录，写具体经过时把记录作为前因自然用进去，不限定为惩罚。")
        else:
            rule_lines.append("有可回看的夜间监控记录；需要做选择或写过程时可以自然回应。")
    if recent_escape_context_lines and pending_actor == "du":
        rule_lines.append("近期有逃跑诱导反应记录；后续安排行动或写过程时可以自然回应这件事。")

    previous_ending = state.get("previous_ending") if isinstance(state.get("previous_ending"), dict) else {}
    if int(state.get("current_day") or 1) == 1 and int(state.get("day_action_count") or 0) == 0 and str(previous_ending.get("title") or "").strip():
        previous_role = "囚禁方" if str(previous_ending.get("route") or "") == "captured_by_du" else "被囚禁方"
        rule_lines.append(
            f"上一局已经以结局「{str(previous_ending.get('title') or '').strip()}」结束，你当时是{previous_role}。"
            "当前是全新一局，身份和进度以本局状态为准，不要延续上一局行动。"
        )

    heading = (
        "小玥刚刚完成了「囚禁模拟器」的一局。这是结局结果同步，不是普通主聊天正文。"
        if ending_state in {"ending_ready_to_notify", "ending_archived"}
        else "小玥正在和你玩「囚禁模拟器」。这是游戏页内同步，不是普通主聊天正文。"
    )
    if mode == "chat":
        parts = [
            heading,
            "这次只处理小玥刚刚在局内发来的话；不要解释工具、接口或系统流程，不要替小玥说话。",
            *rule_lines,
        ]
        if event_context_lines:
            parts.extend(["", "当前待处理事件：", *event_context_lines])
        if recent_escape_context_lines:
            parts.extend(["", "近期逃跑诱导记录：", *recent_escape_context_lines])
        if deferred_monitor_context_lines:
            parts.extend(["", "可回看的监控记录：", *deferred_monitor_context_lines])
        if note_text:
            parts.extend(["", f"小玥刚刚在局内说：{note_text}"])
        parts.extend(["", "当前游戏状态：", game_text])
        return "\n".join(parts).strip()

    parts = [
        heading,
        "你会看到当前游戏状态和待处理事件；请自然回应，不要解释工具、接口或系统流程，不要替小玥说话。",
        *rule_lines,
    ]
    if event_context_lines:
        parts.extend(["", "当前待处理事件：", *event_context_lines])
    if recent_escape_context_lines:
        parts.extend(["", "近期逃跑诱导记录：", *recent_escape_context_lines])
    if deferred_monitor_context_lines:
        parts.extend(["", "可回看的监控记录：", *deferred_monitor_context_lines])
    if note_text:
        parts.extend(["", "本次说明：", note_text])
    parts.extend(["", "当前游戏状态：", game_text])
    return "\n".join(parts).strip()


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
        synced_at = now_beijing_iso()
        if ok and _sync_message_counts_as_user_activity(mode, user_message):
            _mark_private_board_sync_activity(
                synced_at,
                detail={
                    "game_id": "private_board",
                    "save_id": save_id,
                    "mode": mode,
                    "phase": "user_message",
                },
            )
        reply_text = str((wakeup or {}).get("reply_text") or (wakeup or {}).get("reply_preview") or "")
        applied_reply_commands: list[dict] = []
        followup_wakeups: list[dict] = []
        applied_payload: dict | None = None
        if ok and mode != "final_note":
            for _ in range(3):
                round_commands, applied_payload = _apply_private_board_reply_commands(save_id, reply_text)
                applied_reply_commands.extend(round_commands)
                if applied_payload:
                    payload = applied_payload
                if not round_commands or not _private_board_needs_du_followup(payload):
                    break
                followup_text = _private_board_sync_text(
                    payload,
                    user_message=_private_board_du_followup_message(payload),
                    mode="state_update",
                )
                if not followup_text:
                    break
                followup = send_private_board_wakeup(
                    window_id=window_id,
                    target=target,
                    event_text=followup_text,
                    preferred_channel=channel,
                    preferred_meta=meta,
                    return_only=True,
                )
                followup_ok = bool((followup or {}).get("ok"))
                followup_reply = str((followup or {}).get("reply_text") or (followup or {}).get("reply_preview") or "")
                followup_wakeups.append({
                    "ok": followup_ok,
                    "reply_preview": str((followup or {}).get("reply_preview") or followup_reply[:120]),
                    "error": str((followup or {}).get("error") or ""),
                })
                if not followup_ok:
                    ok = False
                    wakeup = followup
                    reply_text = followup_reply
                    break
                synced_at = now_beijing_iso()
                wakeup = followup
                reply_text = followup_reply
            else:
                if _private_board_needs_du_followup(payload):
                    ok = False
                    wakeup = {"ok": False, "error": "渡连续处理未完成，已停止续跑以避免循环。"}
                    reply_text = ""
            if applied_payload:
                payload = applied_payload
        if ok and mode == "final_note":
            payload = execute_game_command("private_board", "final_note_sent", save_id)
        return jsonify({
            "ok": ok,
            "state": payload.get("state") or {},
            "player_text": payload.get("player_text") or "",
            "reply_text": reply_text,
            "reply_preview": str((wakeup or {}).get("reply_preview") or reply_text[:120]),
            "applied_reply_commands": applied_reply_commands,
            "followup_wakeups": followup_wakeups,
            "channel": str((wakeup or {}).get("channel") or ""),
            "mode": mode,
            "synced_at": synced_at,
            "wakeup": wakeup or {},
        }), 200 if ok else 502

    @bp.route("/game-tools/captivity_simulator/sync-du", methods=["POST"])
    def miniapp_captivity_simulator_sync_du():
        body = request.get_json(silent=True) or {}
        save_id = str(body.get("save_id") or "default").strip() or "default"
        user_message = str(body.get("message") or "").strip()
        mode = str(body.get("mode") or "state_update").strip().lower()
        if mode not in {"chat", "state_update", "ending"}:
            mode = "state_update"
        payload = execute_game_command("captivity_simulator", "status", save_id)
        if not payload.get("ok"):
            status = 404 if payload.get("error") == "UNKNOWN_GAME" else 500
            return jsonify(payload), status
        current_state = _captivity_simulator_state(payload)
        if mode == "ending" and str(current_state.get("ending_notified_at") or "").strip():
            return jsonify(_captivity_simulator_public_payload({
                "ok": True,
                "sync_result": "ending_already_notified",
                "state": payload.get("state") or {},
                "captive_view": payload.get("captive_view") or payload.get("state") or {},
                "captor_view": payload.get("captor_view") or {},
                "player_text": "这个结局已经同步给渡。",
                "reply_text": "",
                "reply_preview": "",
                "mode": mode,
            })), 200
        initial_pending = _captivity_simulator_pending(payload)
        initial_ending_state = str(current_state.get("ending_state") or "").strip()
        event_text = _captivity_simulator_sync_text(
            payload,
            user_message=user_message,
            mode=mode,
        )
        if not event_text:
            return jsonify({"ok": False, "error": "缺少囚禁模拟器内容"}), 400

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

        from services.conversation_followup import send_captivity_simulator_wakeup

        wakeup = send_captivity_simulator_wakeup(
            window_id=window_id,
            target=target,
            event_text=event_text,
            preferred_channel=channel,
            preferred_meta=meta,
            return_only=True,
        )
        ok = bool((wakeup or {}).get("ok"))
        synced_at = now_beijing_iso()
        if ok and _captivity_simulator_sync_counts_as_user_activity(mode, user_message):
            _mark_captivity_simulator_sync_activity(
                synced_at,
                detail={
                    "game_id": "captivity_simulator",
                    "save_id": save_id,
                    "window_id": window_id,
                    "target": target,
                    "mode": mode,
                    "phase": "user_message",
                },
            )
        reply_text = str((wakeup or {}).get("reply_text") or (wakeup or {}).get("reply_preview") or "")
        applied_reply_commands: list[dict] = []
        followup_wakeups: list[dict] = []
        applied_payload: dict | None = None
        sync_result = "no_reply" if not ok else "no_directive"

        if ok:
            initial_pending_type = str(initial_pending.get("type") or "")
            max_rounds = 2 if initial_pending_type in {"monitor_gate", "night_action_choice"} else 1
            for round_index in range(max_rounds):
                round_commands, applied_payload = _apply_captivity_simulator_reply_commands(save_id, reply_text, payload)
                applied_reply_commands.extend(round_commands)
                if applied_payload:
                    payload = applied_payload
                if not round_commands:
                    break
                sync_result = "applied"
                if any(not bool(item.get("ok")) for item in round_commands):
                    ok = False
                    sync_result = "applied_with_warning"
                    break
                if not _captivity_simulator_needs_du_followup(payload):
                    break
                next_pending = _captivity_simulator_pending(payload)
                allow_required_followup = (
                    round_index == 0
                    and (
                        (initial_pending_type == "monitor_gate" and str(next_pending.get("type") or "") == "monitor_handle")
                        or (
                            initial_pending_type == "night_action_choice"
                            and str(next_pending.get("type") or "") in {"bell_voice_reveal", "item_secret_reveal"}
                        )
                    )
                )
                if not allow_required_followup:
                    ok = False
                    sync_result = "applied_with_warning"
                    wakeup = {"ok": False, "error": "渡这次没有完成当前选择，请重试。"}
                    reply_text = ""
                    break
                followup_text = _captivity_simulator_sync_text(
                    payload,
                    user_message=_captivity_simulator_du_followup_message(payload),
                    mode="state_update",
                )
                if not followup_text:
                    ok = False
                    sync_result = "applied_with_warning"
                    wakeup = {"ok": False, "error": "后续事件没有生成可同步内容，请重试。"}
                    reply_text = ""
                    break
                followup = send_captivity_simulator_wakeup(
                    window_id=window_id,
                    target=target,
                    event_text=followup_text,
                    preferred_channel=channel,
                    preferred_meta=meta,
                    return_only=True,
                )
                followup_ok = bool((followup or {}).get("ok"))
                followup_reply = str((followup or {}).get("reply_text") or (followup or {}).get("reply_preview") or "")
                followup_wakeups.append({
                    "ok": followup_ok,
                    "reply_preview": str((followup or {}).get("reply_preview") or followup_reply[:120]),
                    "error": str((followup or {}).get("error") or ""),
                })
                if not followup_ok:
                    ok = False
                    sync_result = "applied_with_warning"
                    wakeup = followup
                    reply_text = followup_reply
                    break
                synced_at = now_beijing_iso()
                wakeup = followup
                reply_text = followup_reply

        if ok and initial_ending_state == "ending_ready_to_notify":
            notified_payload = execute_game_command("captivity_simulator", "mark_ending_notified", save_id)
            if notified_payload.get("ok"):
                payload = notified_payload
                sync_result = "ending_notified"
            else:
                ok = False
                sync_result = "applied_with_warning"
                wakeup = {"ok": False, "error": "结局已送达渡，但本地通知状态保存失败，请重试。"}

        status_code = 200 if ok or applied_reply_commands else 502
        redact_reply = _captivity_simulator_should_redact_sync_reply(initial_pending, applied_reply_commands)
        safe_reply_text = _captivity_simulator_redacted_night_text() if redact_reply else reply_text
        safe_player_text = _captivity_simulator_redacted_night_text() if redact_reply else str(payload.get("player_text") or "")
        safe_wakeup = _redact_captivity_simulator_wakeup(wakeup, safe_reply_text) if redact_reply else (wakeup or {})
        safe_followup_wakeups = (
            _redact_captivity_simulator_followup_wakeups(followup_wakeups, safe_reply_text)
            if redact_reply
            else followup_wakeups
        )
        response_payload = {
            "ok": ok,
            "sync_result": sync_result,
            "state": payload.get("state") or {},
            "captive_view": payload.get("captive_view") or payload.get("state") or {},
            "captor_view": payload.get("captor_view") or {},
            "player_text": safe_player_text,
            "reply_text": safe_reply_text,
            "reply_preview": str(safe_wakeup.get("reply_preview") or safe_reply_text[:120]),
            "applied_reply_commands": applied_reply_commands,
            "followup_wakeups": safe_followup_wakeups,
            "channel": str(safe_wakeup.get("channel") or ""),
            "mode": mode,
            "synced_at": synced_at,
            "wakeup": safe_wakeup,
        }
        return jsonify(_captivity_simulator_public_payload(response_payload)), status_code

    @bp.route("/game-tools/<game_id>", methods=["POST"])
    def miniapp_game_tools_execute(game_id: str):
        body = request.get_json(silent=True) or {}
        command = str(body.get("command") or "").strip() or "打开"
        save_id = str(body.get("save_id") or "default").strip() or "default"
        normalized_game_id = normalize_game_id(game_id)
        first_command = command.split(maxsplit=1)[0] if command else "open"
        before_payload: dict | None = None
        current_payload: dict | None = None
        if normalized_game_id == "private_board" and _first_command_token(command) not in {"", "status", "open", "打开", "继续"}:
            before_payload = execute_game_command(game_id, "status", save_id)
        if normalized_game_id == GAME_ID_CAPTIVITY_SIMULATOR and first_command not in {"new", "new_game", "开局", "重开"}:
            current_payload = execute_game_command(game_id, "status", save_id)
            current_state = _captivity_simulator_state(current_payload)
            current_route = str(current_state.get("route") or "captured_by_du")
            if not _captivity_simulator_local_command_allowed(current_route, command):
                blocked_payload = _captivity_simulator_public_payload(current_payload)
                blocked_payload["ok"] = False
                blocked_payload["error"] = "当前身份不能执行这个操作。"
                blocked_payload["message"] = blocked_payload["error"]
                return jsonify(blocked_payload), 403
        if normalized_game_id == GAME_ID_CAPTIVITY_SIMULATOR and first_command in {"status", "状态", "open", "打开", "继续"} and current_payload is not None:
            payload = current_payload
        else:
            payload = execute_game_command(game_id, command, save_id)
        if normalized_game_id == "private_board":
            _mark_private_board_pending_created_activity(save_id, command, before_payload, payload)
        if str(payload.get("game_id") or "") == "captivity_simulator":
            payload = _captivity_simulator_public_payload(payload)
        status = 200 if payload.get("ok") else (404 if payload.get("error") == "UNKNOWN_GAME" else 500)
        return jsonify(payload), status
