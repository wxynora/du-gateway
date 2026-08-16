"""Synchronous conversation-round archive helpers."""

import json
from typing import Callable, Optional

from storage import r2_store as _default_r2_store
from utils.log import get_logger


_default_logger = get_logger("pipeline.pipeline")


def _build_action_note_from_tool_calls(tool_calls: list) -> str:
    """把本轮工具调用压成一条很短的动作印象，供后续 Last4 短程上下文使用。"""
    if not isinstance(tool_calls, list) or not tool_calls:
        return ""

    has_success = False

    def _summarize_one_tool(tc: dict) -> str:
        nonlocal has_success
        if not isinstance(tc, dict):
            return ""
        fn = (tc.get("function") or {}) if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name:
            return ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        result_text = str(tc.get("result") or "").strip()
        if name == "create_system_alarm":
            result_obj = {}
            try:
                parsed = json.loads(result_text or "{}")
                if isinstance(parsed, dict):
                    result_obj = parsed
            except Exception:
                result_obj = {}
            ok = bool(result_obj.get("ok")) if result_obj else bool(result_text)
            try:
                hour = int(result_obj.get("hour", args.get("hour")))
                minute = int(result_obj.get("minute", args.get("minute")))
                alarm_time = f"{hour:02d}:{minute:02d}"
            except Exception:
                alarm_time = "目标时间"
            if ok:
                action_id = str(result_obj.get("id") or "").strip()
                id_part = f":id={action_id}" if action_id else ""
                return f"create_system_alarm{id_part}（{alarm_time} 系统闹钟已发送到手机，等待 App 回执）"
            return f"create_system_alarm（{alarm_time} 调用未成功）"
        target = ""
        for key in ("url", "query", "keyword", "page_id", "title", "content", "window_id"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                target = val.strip()
                break
        if len(target) > 48:
            target = target[:48] + "..."
        if result_text:
            result_kind = "已拿到结果"
            lower = result_text.lower()
            if name == "read_url":
                result_kind = "已拿到页面内容"
                has_success = True
            elif "未找到" in result_text or "没有找到" in result_text or "not found" in lower:
                result_kind = "未找到有效结果"
            elif "error" in lower or "失败" in result_text:
                result_kind = "调用未成功"
            elif "http" in result_text or "https" in result_text:
                result_kind = "已拿到链接结果"
                has_success = True
            elif "[" in result_text and "]" in result_text:
                result_kind = "已拿到候选列表"
                has_success = True
            else:
                has_success = True
        else:
            result_kind = "已执行"
        if target:
            return f"{name}（{target}，{result_kind}）"
        return f"{name}（{result_kind}）"

    parts: list[str] = []
    seen: set[str] = set()
    for tc in tool_calls[:4]:
        piece = _summarize_one_tool(tc)
        if not piece or piece in seen:
            continue
        seen.add(piece)
        parts.append(piece)
    if not parts:
        return ""
    if has_success:
        return f"上一轮工具结果：{'、'.join(parts)}；这些结果已经拿到，除非参数变化或用户明确要求刷新，否则不要重复调用相同工具。"
    return f"上一轮工具记录：{'、'.join(parts)}；若还是同一目标，先基于上面结果继续，不要立刻原样重调。"


def _build_round_action_note(assistant_message: dict, round_messages: list[dict]) -> str:
    has_diary_reply = any(
        isinstance(message, dict)
        and str(message.get("role") or "").strip().lower() == "assistant"
        and str(message.get("archive_label") or "").strip() == "日记评论互动"
        for message in (round_messages or [])
    )
    if has_diary_reply:
        return ""
    return _build_action_note_from_tool_calls((assistant_message or {}).get("tool_calls"))


def _step_archive_round(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
    reply_channel: str = "",
    *,
    r2_store_module,
    logger_instance,
    action_note_builder: Callable[[dict, list[dict]], str],
) -> Optional[dict]:
    last_user = None
    for m in request_messages:
        if (m.get("role") or "").lower() == "user":
            last_user = m
    if not last_user or not assistant_message:
        return None

    # 只存对话两条（user + assistant），且一律清洗，不存 system / Rikka 自带说明
    from pipeline.cleaner import build_round_cleaned_for_r2

    round_messages = (
        round_cleaned_for_r2
        if round_cleaned_for_r2
        else build_round_cleaned_for_r2(last_user, assistant_message)
    )
    action_note = action_note_builder(assistant_message, round_messages)
    from services.reply_channel_context import normalize_reply_channel
    from utils.time_aware import now_beijing_iso

    round_index = r2_store_module.get_next_round_index(window_id)
    ts = now_beijing_iso()
    channel = normalize_reply_channel(reply_channel, default="", allow_tg=True)
    ok = r2_store_module.append_conversation_round(
        window_id,
        round_index,
        round_messages,
        timestamp=ts,
        action_note=action_note,
        channel=channel,
    )
    if not ok:
        logger_instance.warning(
            "本轮对话 R2 存档失败 window_id=%s round_index=%s",
            window_id,
            round_index,
        )
        return None
    # 全局 Last4 只需最近四轮：append 后读即可，不必拉 last_n=1000 再拼（省内存、也避免误用 len 当总轮数）
    tail4 = r2_store_module.get_conversation_rounds(window_id, last_n=4)
    r2_store_module.update_latest_4_rounds_global(tail4)
    return {"round_index": round_index, "round_messages": round_messages}


def step_archive_round(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
    reply_channel: str = "",
) -> Optional[dict]:
    """同步写入本轮对话存档与 latest4，返回后续慢任务需要的 round_index/round_messages。"""
    return _step_archive_round(
        window_id,
        request_messages,
        assistant_message,
        round_cleaned_for_r2=round_cleaned_for_r2,
        reply_channel=reply_channel,
        r2_store_module=_default_r2_store,
        logger_instance=_default_logger,
        action_note_builder=_build_round_action_note,
    )
