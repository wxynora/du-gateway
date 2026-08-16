import copy
import re
from typing import Optional

from pipeline.prompt_layout import (
    _DU_DAILY_SYSTEM_MARKER,
    _DYNAMIC_SYSTEM_MARKER,
    _SUMMARY_CACHE_SYSTEM_MARKER,
    _SUMMARY_RECENT_SYSTEM_MARKER,
    _append_to_dynamic_system,
    _append_to_static_system,
    _append_to_temporary_dynamic_system,
    _ensure_dynamic_system,
    _is_persistent_dynamic_system,
)
from storage import r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens


logger = get_logger("pipeline.pipeline")

_PLAY_NOTE_PENDING_BODY_KEY = "__play_note_pending__"


def step_inject_current_base_model(body: dict) -> dict:
    """把当前 active model cache 写到动态 system 第一条；无缓存则跳过。"""
    try:
        from storage.upstream_store import get_cached_active_model

        model_name = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
    except Exception as e:
        logger.debug("current base model 注入跳过 error=%s", e)
        return body
    if not model_name:
        return body
    line = f"当前底座为：{model_name}"
    body = _ensure_dynamic_system(body)
    for msg in body.get("messages") or []:
        if not _is_persistent_dynamic_system(msg):
            continue
        content = str(msg.get("content") or "")
        if "当前底座为：" in content:
            return body
        msg["content"] = line if not content.strip() else f"{line}\n\n{content.lstrip()}"
        return body
    return body


def _last_user_text_for_humor_memes(body: dict) -> str:
    for msg in reversed(body.get("messages") or []):
        if (msg.get("role") or "").lower() != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content or "")
    return ""


def step_inject_humor_memes(body: dict) -> dict:
    """按用户最后一句关键词召回梗素材，不足时随机补位。"""
    try:
        from services.humor_meme_bank import format_memes_for_system, pick_context_memes

        inject = format_memes_for_system(
            pick_context_memes(_last_user_text_for_humor_memes(body), total_limit=3, keyword_limit=2)
        )
    except Exception as e:
        logger.debug("humor meme 注入跳过 error=%s", e)
        return body
    if not inject:
        return body
    return _append_to_temporary_dynamic_system(body, inject)


def _format_system_alarm_action_result(item: dict) -> str:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    try:
        hour = int(result.get("hour", payload.get("hour")))
        minute = int(result.get("minute", payload.get("minute")))
        time_text = f"{hour:02d}:{minute:02d}"
    except Exception:
        time_text = "目标时间"
    title = str(result.get("title") or payload.get("title") or "渡的提醒").strip() or "渡的提醒"
    status = str(item.get("status") or "").strip().lower()
    if status == "done":
        return f"- 系统闹钟 {time_text}「{title}」：手机 App 已回传创建成功。"
    if status in {"failed", "expired", "abandoned"}:
        error = str(item.get("error") or "").strip()
        if not error and isinstance(result, dict):
            error = str(result.get("error") or result.get("message") or "").strip()
        suffix = f"原因：{error[:120]}" if error else "没有拿到成功回执。"
        return f"- 系统闹钟 {time_text}「{title}」：创建没有成功。{suffix}"
    return f"- 系统闹钟 {time_text}「{title}」：已发送到手机，仍在等待 App 回执。"


def step_inject_system_alarm_action_result(body: dict, window_id: str) -> dict:
    """
    只在上一轮刚调用 create_system_alarm 后，下一轮注入一次安卓壳回执。
    平时不扫描其它 App action，避免动态区变重。
    """
    try:
        from storage import app_action_store, conversation_sqlite_store

        last_rounds = conversation_sqlite_store.get_rounds(window_id, last_n=1)
        last_round = last_rounds[-1] if last_rounds else {}
        action_note = str((last_round or {}).get("action_note") or "")
        if "create_system_alarm" not in action_note:
            return body
        since_iso = str((last_round or {}).get("timestamp") or "").strip()
        alarm_action_id = ""
        m = re.search(r"create_system_alarm:id=([0-9a-fA-F-]{8,})", action_note)
        if m:
            alarm_action_id = m.group(1)
        item = app_action_store.get_system_alarm_action(alarm_action_id) if alarm_action_id else None
        items = [item] if item else app_action_store.list_system_alarm_actions_since(since_iso, limit=1)
    except Exception as e:
        logger.debug("system alarm action result 注入跳过 error=%s", e)
        return body
    if not items:
        return body
    lines = [_format_system_alarm_action_result(item) for item in items if isinstance(item, dict)]
    lines = [line for line in lines if line]
    if not lines:
        return body
    inject = (
        "\n\n【手机系统闹钟回执】\n"
        + "\n".join(lines)
        + "\n如果显示成功，就按已经创建成功来回应；如果显示失败，可以告诉小玥失败了，并按她的意思决定要不要重新创建。"
    )
    return _append_to_temporary_dynamic_system(body, inject)


def step_inject_sense_snapshot(body: dict, window_id: str) -> dict:
    """
    全局注入：不区分 window_id。凡走网关 /v1/chat/completions 完整管道的请求（Rikka、Telegram、闹钟叫醒等）
    都在 system 末尾追加 sense/latest 快照；不写入 user。window_id 参数保留仅为与其它 step 签名一致。
    R2 失败或无数据则跳过。
    """
    _ = window_id  # 感知数据为全局一份，不按窗口分桶
    try:
        from services.sense_context import format_sense_snapshot_for_system

        block = format_sense_snapshot_for_system()
    except Exception as e:
        logger.debug("sense 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_dynamic_system(body, inject)
    return body


def step_inject_du_thought(body: dict, window_id: str) -> dict:
    """
    全局注入：在 system 末尾追加「心事格式说明 + 上一则心事」。
    渡在回复末尾写 <<<DU_THOUGHT>>>...<<<END_DU_THOUGHT>>>，网关截取后存 R2，老婆侧不可见。
    """
    _ = window_id
    try:
        from services.du_thought import format_inject_block

        latest = r2_store.get_du_thought_latest()
        block = format_inject_block(latest)
    except Exception as e:
        logger.debug("du_thought 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_dynamic_system(body, inject)
    return body


def step_inject_pending_thoughts(body: dict, window_id: str) -> dict:
    """动态注入：渡自己留下的待续念头，紧跟心事之后。"""
    _ = window_id
    try:
        from services.pending_thoughts import format_inject_block

        block = format_inject_block()
    except Exception as e:
        logger.debug("pending_thought 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    return _append_to_dynamic_system(body, "\n\n" + block.strip())


def step_inject_secret_drawer(body: dict, window_id: str) -> dict:
    """固定规则进入静态 system；当前抽屉统计进入常驻动态 system。"""
    _ = window_id
    try:
        from services.secret_drawer import format_rule_block, format_state_block

        rule_block = format_rule_block()
        state_block = format_state_block()
    except Exception as e:
        logger.debug("secret_drawer 注入跳过 error=%s", e)
        return body
    if (rule_block or "").strip():
        body = _append_to_static_system(body, "\n\n" + rule_block.strip())
    if (state_block or "").strip():
        body = _append_to_dynamic_system(body, "\n\n" + state_block.strip())
    return body


def step_inject_wakeup_frame(body: dict, window_id: str) -> dict:
    """动态注入：距离上次醒来后，设备感知数据发生的短变化。"""
    try:
        from services.wakeup_frame import format_wakeup_frame_for_system

        block = format_wakeup_frame_for_system(window_id)
    except Exception as e:
        logger.debug("wakeup_frame 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    return _append_to_dynamic_system(body, "\n\n" + block.strip())


def step_inject_du_vitals(body: dict, window_id: str) -> dict:
    """
    全局注入：静态 system 放稳定规则，不把上一轮实际读数注入给渡。
    渡输出内部状态参数，网关截取后换算为心率/呼吸，老婆侧正文不可见。
    """
    _ = window_id
    try:
        from services.du_vitals import format_rule_block

        rule_block = format_rule_block()
    except Exception as e:
        logger.debug("du_vitals 注入跳过 error=%s", e)
        return body
    if (rule_block or "").strip():
        body = _append_to_static_system(body, "\n\n" + rule_block.strip())
    return body


def step_inject_du_daily(
    body: dict,
    window_id: str,
    trigger: Optional[dict] = None,
    maintenance_mode: bool = False,
) -> dict:
    """
    全局注入：把「你的日常」作为独立常驻动态 system 槽位注入。
    最终位置固定在两个近期记忆块之后、其他常驻动态之前。
    网关判定命中更新时，渡只写本次新增隐藏块，网关截取后追加进 R2，老婆侧不可见。
    """
    _ = window_id
    try:
        from services.du_daily import format_inject_block, get_prepared_state

        state, _changed = get_prepared_state()
        block = format_inject_block(state, trigger=trigger, maintenance_mode=maintenance_mode)
    except Exception as e:
        logger.debug("du_daily 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = copy.deepcopy(body)
    messages = [
        msg
        for msg in (body.get("messages") or [])
        if not (isinstance(msg, dict) and msg.get(_DU_DAILY_SYSTEM_MARKER))
    ]
    insert_idx = len(messages)
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            insert_idx = i
            break
        if (
            msg.get(_SUMMARY_CACHE_SYSTEM_MARKER)
            or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER)
            or msg.get(_DYNAMIC_SYSTEM_MARKER)
        ):
            insert_idx = i
            break
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": inject,
            _DU_DAILY_SYSTEM_MARKER: True,
            _DYNAMIC_SYSTEM_MARKER: True,
        },
    )
    body["messages"] = messages
    return body


def step_inject_pixel_home(body: dict, window_id: str) -> dict:
    """Inject shared cyber home state dynamically and the PIXEL_HOME hidden marker contract statically."""
    _ = window_id
    try:
        from services.pixel_home import format_rule_block, format_state_and_private_draw_blocks

        rule_block = format_rule_block()
        state_block, private_draw_block = format_state_and_private_draw_blocks()
    except Exception as e:
        logger.debug("pixel_home 注入跳过 error=%s", e)
        return body
    if (rule_block or "").strip():
        body = _append_to_static_system(body, "\n\n" + rule_block.strip())
    if (state_block or "").strip():
        body = _append_to_dynamic_system(body, "\n\n" + state_block.strip())
    if (private_draw_block or "").strip():
        body[_PLAY_NOTE_PENDING_BODY_KEY] = private_draw_block.strip()
    return body


def step_inject_du_midterm_memory(body: dict, window_id: str) -> dict:
    """
    全局注入：最近 14 天滑窗的中期连续感，三天才刷新，放静态 system 段。
    这层独立于 dynamic_memory/current.json，只注入 latest；到期刷新走后台线程，不阻塞当前聊天。
    """
    _ = window_id
    try:
        from services.du_midterm_memory import format_inject_block, refresh_if_due_background

        refresh_if_due_background()
        block = format_inject_block()
    except Exception as e:
        logger.debug("du_midterm 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_static_system(body, inject)
    return body


def step_inject_interaction_candidate(body: dict, window_id: str) -> dict:
    """
    全局注入：在静态 system 段追加「相处模式候选写法说明」。
    渡在回复末尾写 <<<DU_INTERACTION>>>...<<<END_DU_INTERACTION>>>，网关截取后存 R2，老婆侧不可见。
    """
    _ = window_id
    try:
        from services.interaction_memory import format_inject_block

        block = format_inject_block()
    except Exception as e:
        logger.debug("interaction candidate 注入跳过 error=%s", e)
        return body
    if not (block or "").strip():
        return body
    inject = "\n\n" + block.strip()
    body = _append_to_static_system(body, inject)
    return body


def step_inject_stay_with_du(body: dict) -> dict:
    """
    固定注入：Stay with Du，位置在「渡的记事本」上方。
    """
    data = r2_store.get_stay_with_du_data() or {}
    if not any(data.get(k) for k in ("timeline", "moviesDone", "moviesTodo", "booksDone", "booksTodo")):
        return body

    def _media_line(item: dict) -> str:
        title = str((item or {}).get("title") or "").strip()
        if not title:
            return ""
        date = str((item or {}).get("date") or "").strip()
        note = str((item or {}).get("note") or "").strip()
        suffix = ""
        if date:
            suffix += f"（{date}）"
        if note:
            suffix += f"：{note}"
        return f"- {title}{suffix}"

    sections: list[str] = []
    timeline_lines = []
    for item in (data.get("timeline") or [])[:20]:
        title = str((item or {}).get("title") or "").strip()
        if not title:
            continue
        date = str((item or {}).get("date") or "").strip()
        desc = str((item or {}).get("desc") or "").strip()
        prefix = f"{date} " if date else ""
        timeline_lines.append(f"- {prefix}{title}" + (f"：{desc}" if desc else ""))
    if timeline_lines:
        sections.append("重要时间线：\n" + "\n".join(timeline_lines))

    media_specs = [
        ("一起看过的电影", data.get("moviesDone") or []),
        ("想一起看的电影", data.get("moviesTodo") or []),
        ("一起读过的书", data.get("booksDone") or []),
        ("想一起读的书", data.get("booksTodo") or []),
    ]
    for title, items in media_specs:
        lines = [_media_line(it) for it in items[:30]]
        lines = [line for line in lines if line]
        if lines:
            sections.append(f"{title}：\n" + "\n".join(lines))

    if not sections:
        return body

    budget = 700
    kept: list[str] = []
    for section in sections:
        nxt = ("\n\n".join(kept + [section])).strip()
        if estimate_tokens(nxt) > budget:
            break
        kept.append(section)
    if not kept:
        return body
    inject = "\n\n【Stay with Du】\n" + "\n\n".join(kept) + "\n【以上为 Stay with Du】"
    body = _append_to_static_system(body, inject)
    return body


def step_inject_du_notebook(body: dict) -> dict:
    """
    固定注入：你的记事本（按条目，放静态 system 区）。
    注入全部现有条目。
    """
    entries = r2_store.get_du_notebook_entries() or []
    if not entries:
        return body
    lines = []
    for it in entries:
        line = f"- {(it.get('content') or '').strip()}"
        if not line or line == "-":
            continue
        lines.append(line)
    if not lines:
        return body
    inject = "\n\n【你的记事本】\n" + "\n".join(lines) + "\n【以上为固定记事本】"
    body = _append_to_static_system(body, inject)
    return body
