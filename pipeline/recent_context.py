"""Short-lived conversation context and prompt-cache injection helpers."""

import copy

from config import (
    ASSISTANT_LUNAR_KEYWORDS,
    ASSISTANT_TIME_KEYWORDS,
    REPLY_GAP_THRESHOLD_MINUTES,
)
from pipeline.prompt_layout import (
    _DRAFT_REMINDER_SYSTEM_MARKER,
    _DU_DAILY_SYSTEM_MARKER,
    _DYNAMIC_SYSTEM_MARKER,
    _ENTRY_STYLE_SYSTEM_MARKER,
    _FROZEN_TOOL_SUMMARY_SYSTEM_MARKER,
    _HOT_TOOL_RESULT_SYSTEM_MARKER,
    _LAST4_SYSTEM_MARKER,
    _PROMPT_CACHE_LAYOUT_BODY_KEY,
    _RECENT_TOOL_BATCH_SYSTEM_MARKER,
    _STATIC_CACHE_ANCHOR_SYSTEM_MARKER,
    _SUMITALK_REAL_MODE_SYSTEM_MARKER,
    _SUMMARY_CACHE_SYSTEM_MARKER,
    _SUMMARY_RECENT_SYSTEM_MARKER,
    _SYSTEM_PROMPT_CACHE_GROUPS,
    _SYSTEM_PROMPT_REGION_ORDER,
    _TEMPORARY_DYNAMIC_SYSTEM_MARKER,
    _THINKING_RULES_SYSTEM_MARKER,
    _VOICE_RULES_SYSTEM_MARKER,
    _append_to_dynamic_system,
    _append_to_last4_system,
    _merge_system_region,
    _system_prompt_region,
    _upsert_summary_cache_system,
)
from services import deepseek_summary, image_desc
from services.user_activity_context import (
    capture_previous_interaction_and_mark_chat,
    elapsed_seconds as user_activity_elapsed_seconds,
    render_incoming_gap_prompt,
)
from storage import r2_store
from utils.log import get_logger


logger = get_logger("pipeline.pipeline")


def _summary_prompt_chunk_ids(chunks_state: dict) -> tuple[list[str], list[str]]:
    generation = chunks_state.get("generation") if isinstance(chunks_state.get("generation"), dict) else {}
    base_recent_ids = {
        str(value)
        for value in generation.get("base_recent_ids") or []
        if str(value or "").strip()
    }
    recent_ids: list[str] = []
    for item in sorted(
        [row for row in chunks_state.get("chunks") or [] if isinstance(row, dict)],
        key=lambda row: int(row.get("sequence") or 0),
    ):
        if str(item.get("level") or "") != "recent":
            continue
        if item.get("summary_pending") or str(item.get("status") or "") == "pending":
            continue
        if not str(item.get("text") or "").strip():
            continue
        chunk_id = str(item.get("id") or "").strip()
        if chunk_id:
            recent_ids.append(chunk_id)
    generation_chunk_ids = [chunk_id for chunk_id in recent_ids if chunk_id not in base_recent_ids]
    return recent_ids, generation_chunk_ids


def _summary_generation_base_recent_ids(chunks_state: dict) -> list[str]:
    generation = chunks_state.get("generation") if isinstance(chunks_state.get("generation"), dict) else {}
    return [
        str(value).strip()
        for value in generation.get("base_recent_ids") or []
        if str(value or "").strip()
    ]


def _summary_prompt_chunk_item_ids(chunks_state: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in chunks_state.get("chunks") or []:
        if not isinstance(item, dict) or "tool_cache_item_ids" not in item:
            continue
        chunk_id = str(item.get("id") or "").strip()
        if not chunk_id:
            continue
        out[chunk_id] = [
            str(value).strip()
            for value in item.get("tool_cache_item_ids") or []
            if str(value or "").strip()
        ]
    return out


def step_inject_tool_result_cache(body: dict, window_id: str = "") -> dict:
    """Place leading system blocks into the one explicit cache-region order."""
    from services.tool_result_cache import prompt_generation_contents

    body = copy.deepcopy(body)
    generation_meta = body.get(_PROMPT_CACHE_LAYOUT_BODY_KEY)
    if not isinstance(generation_meta, dict):
        current_summary = r2_store.get_summary(window_id) or ""
        chunks_state = r2_store.get_summary_chunks(window_id)
        _stable, _recent, normalized_state = deepseek_summary.render_summary_prompt_blocks(
            chunks_state,
            current_summary,
        )
        generation = normalized_state.get("generation") if isinstance(normalized_state.get("generation"), dict) else {}
        recent_chunk_ids, generation_chunk_ids = _summary_prompt_chunk_ids(normalized_state)
        generation_meta = {
            "window_id": str(window_id or ""),
            "generation_id": int(generation.get("id") or 0),
            "generation_updates_done": int(generation.get("updates_done") or 0),
            "recent_chunk_ids": recent_chunk_ids,
            "generation_chunk_ids": generation_chunk_ids,
            "generation_base_recent_ids": _summary_generation_base_recent_ids(normalized_state),
            "generation_chunk_item_ids": _summary_prompt_chunk_item_ids(normalized_state),
        }
    tool_generation = prompt_generation_contents(
        window_id=str(window_id or generation_meta.get("window_id") or ""),
        generation_id=int(generation_meta.get("generation_id") or 0),
        generation_chunk_ids=list(generation_meta.get("generation_chunk_ids") or []),
        previous_generation_chunk_ids=list(generation_meta.get("generation_base_recent_ids") or []),
        generation_chunk_item_ids=dict(generation_meta.get("generation_chunk_item_ids") or {}),
    )
    messages = list(body.get("messages") or [])
    leading_systems: list[dict] = []
    rest_start = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            rest_start = i
            break
        leading_systems.append(msg)
    else:
        rest_start = len(messages)

    region_blocks: dict[str, list[dict]] = {region: [] for region in _SYSTEM_PROMPT_REGION_ORDER}
    for msg in leading_systems:
        region = _system_prompt_region(msg)
        if region in {"frozen_tool_summary", "recent_tool_batches", "hot_tool_results"}:
            continue
        region_blocks[region].append(msg)
    frozen_text = str(tool_generation.get("frozen_text") or "").strip()
    if frozen_text:
        region_blocks["frozen_tool_summary"].append(
            {
                "role": "system",
                "content": frozen_text,
                _FROZEN_TOOL_SUMMARY_SYSTEM_MARKER: True,
            }
        )
    recent_tool_messages_by_chunk_id: dict[str, dict] = {}
    for batch in tool_generation.get("recent_batches") or []:
        if not isinstance(batch, dict):
            continue
        content = str(batch.get("text") or "").strip()
        summary_chunk_id = str(batch.get("summary_chunk_id") or "").strip()
        if not content or not summary_chunk_id:
            continue
        message = {
            "role": "system",
            "content": content,
            _RECENT_TOOL_BATCH_SYSTEM_MARKER: True,
        }
        region_blocks["recent_tool_batches"].append(message)
        recent_tool_messages_by_chunk_id[summary_chunk_id] = message
    for content in tool_generation.get("hot_blocks") or []:
        if str(content or "").strip():
            region_blocks["hot_tool_results"].append(
                {
                    "role": "system",
                    "content": str(content),
                    _HOT_TOOL_RESULT_SYSTEM_MARKER: True,
                }
            )
    cache_group_markers = {
        "static": _STATIC_CACHE_ANCHOR_SYSTEM_MARKER,
        "voice_rules": _VOICE_RULES_SYSTEM_MARKER,
        "frozen_tool_summary": _FROZEN_TOOL_SUMMARY_SYSTEM_MARKER,
        "entry_style": _ENTRY_STYLE_SYSTEM_MARKER,
        "sumitalk_mode": _SUMITALK_REAL_MODE_SYSTEM_MARKER,
        "du_daily": _DYNAMIC_SYSTEM_MARKER,
        "summary_cache": _SUMMARY_CACHE_SYSTEM_MARKER,
        "summary_recent": _SUMMARY_RECENT_SYSTEM_MARKER,
        "recent_tool_batches": _RECENT_TOOL_BATCH_SYSTEM_MARKER,
        "hot_tool_results": _HOT_TOOL_RESULT_SYSTEM_MARKER,
        "dynamic": _DYNAMIC_SYSTEM_MARKER,
        "temporary_dynamic": _DYNAMIC_SYSTEM_MARKER,
        "draft_reminder": _DRAFT_REMINDER_SYSTEM_MARKER,
        "thinking_rules": _THINKING_RULES_SYSTEM_MARKER,
        "last4": _DYNAMIC_SYSTEM_MARKER,
    }
    ordered_regions = []
    for group in _SYSTEM_PROMPT_CACHE_GROUPS:
        group_messages = [
            msg
            for region in group
            for msg in region_blocks[region]
        ]
        if group == ("summary_recent", "recent_tool_batches"):
            recent_chunk_ids = [str(value or "") for value in generation_meta.get("recent_chunk_ids") or []]
            for index, message in enumerate(region_blocks["summary_recent"]):
                ordered_regions.append(copy.deepcopy(message))
                chunk_id = recent_chunk_ids[index] if index < len(recent_chunk_ids) else ""
                tool_message = recent_tool_messages_by_chunk_id.get(chunk_id)
                if tool_message:
                    ordered_regions.append(copy.deepcopy(tool_message))
            continue
        if group == ("hot_tool_results",):
            ordered_regions.extend(copy.deepcopy(group_messages))
            continue
        merged = _merge_system_region(group_messages, cache_group_markers[group[0]])
        if merged:
            if group == ("frozen_tool_summary", "summary_cache"):
                merged[_FROZEN_TOOL_SUMMARY_SYSTEM_MARKER] = True
                merged[_SUMMARY_CACHE_SYSTEM_MARKER] = True
            elif group == ("du_daily",):
                merged[_DU_DAILY_SYSTEM_MARKER] = True
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("dynamic",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("temporary_dynamic",):
                merged[_TEMPORARY_DYNAMIC_SYSTEM_MARKER] = True
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("draft_reminder",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("sumitalk_mode",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("thinking_rules",):
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            elif group == ("last4",):
                merged[_LAST4_SYSTEM_MARKER] = True
                merged[_DYNAMIC_SYSTEM_MARKER] = True
            ordered_regions.append(merged)
    voice_blocks = [msg for msg in ordered_regions if msg.get(_VOICE_RULES_SYSTEM_MARKER)]
    if voice_blocks:
        for msg in ordered_regions:
            msg.pop(_STATIC_CACHE_ANCHOR_SYSTEM_MARKER, None)
        voice_blocks[-1][_STATIC_CACHE_ANCHOR_SYSTEM_MARKER] = True
    body["messages"] = [*ordered_regions, *messages[rest_start:]]
    body[_PROMPT_CACHE_LAYOUT_BODY_KEY] = {
        "window_id": str(window_id or generation_meta.get("window_id") or ""),
        "generation_id": int(generation_meta.get("generation_id") or 0),
        "generation_updates_done": int(generation_meta.get("generation_updates_done") or 0),
        "recent_blocks": len(region_blocks["summary_recent"]),
        "recent_tool_batches": len(region_blocks["recent_tool_batches"]),
        "hot_tool_blocks": len(region_blocks["hot_tool_results"]),
        "tool_lifecycle_mode": str(tool_generation.get("lifecycle_mode") or ""),
    }
    return body


def _message_content_text_for_recent_context(msg: dict) -> str:
    content = (msg or {}).get("content", "")
    if isinstance(content, list):
        return " ".join(
            c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
        )
    return str(content or "")


def _recent_context_round_time_label(round_obj: dict) -> str:
    raw = str((round_obj or {}).get("timestamp") or "").strip()
    if not raw:
        return ""
    try:
        from utils.time_aware import parse_iso_to_beijing

        dt = parse_iso_to_beijing(raw)
        return dt.strftime("%H:%M") if dt else ""
    except Exception:
        return ""


def _last_recent_context_message_position(rounds: list) -> tuple[int, int] | None:
    last_pos = None
    for ri, r in enumerate(rounds or []):
        for mi, m in enumerate((r or {}).get("messages") or []):
            if isinstance(m, dict):
                last_pos = (ri, mi)
    return last_pos


def _format_recent_context_message_line(
    round_obj: dict,
    msg: dict,
    role: str,
    *,
    is_last_message: bool = False,
    src_tag: str = "",
) -> str:
    content = _message_content_text_for_recent_context(msg)
    if str((msg or {}).get("archive_label") or "").strip() == "日记评论互动":
        return f"【日记评论互动】{content}"
    if is_last_message:
        time_label = _recent_context_round_time_label(round_obj)
        if time_label:
            role_label = _recent_context_role_label(msg, role)
            return f"{src_tag}[{time_label}][{role_label}]: {content}"
    role_label = _recent_context_role_label(msg, role)
    return f"{src_tag}[{role_label}]: {content}"


def _rounds_to_context_text(rounds: list) -> str:
    """把 rounds（含 messages 的列表）拼成一段可读的上下文文本。"""
    lines = []
    last_pos = _last_recent_context_message_position(rounds)
    for ri, r in enumerate(rounds):
        for mi, m in enumerate(r.get("messages", [])):
            role = str(m.get("role", "") or "").strip().lower()
            lines.append(
                _format_recent_context_message_line(
                    r,
                    m,
                    role,
                    is_last_message=last_pos == (ri, mi),
                )
            )
        action_note = str((r or {}).get("action_note") or "").strip()
        if action_note:
            lines.append(f"[action_note]: {action_note}")
    return "\n".join(lines) if lines else ""


def _recent_context_role_label(msg: dict, role: str) -> str:
    if role == "user":
        return "辛玥"
    if role == "assistant":
        label = str((msg or {}).get("archive_label") or "").strip()
        if label:
            return label
        return "我"
    if role == "event":
        label = str((msg or {}).get("archive_label") or "").strip()
        return label or "网关提醒"
    return role or "unknown"


_PROACTIVE_DECISION_PROMPT_PREFIX = "这是一次随机唤醒，你现在要不要做点什么"


def _message_plain_text_for_context(msg: dict) -> str:
    content = (msg or {}).get("content", "")
    if isinstance(content, list):
        return " ".join(c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content)
    return str(content or "")


def _is_internal_proactive_decision_round(round_obj: dict) -> bool:
    if not isinstance(round_obj, dict):
        return False
    user_text = ""
    assistant_text = ""
    for msg in round_obj.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        if role == "user" and not user_text:
            user_text = _message_plain_text_for_context(msg).strip()
        elif role == "assistant" and not assistant_text:
            assistant_text = _message_plain_text_for_context(msg).strip()
    if not user_text.startswith(_PROACTIVE_DECISION_PROMPT_PREFIX):
        return False
    return '"action"' in assistant_text or "'action'" in assistant_text


def _filter_rounds_for_recent_context(rounds: list) -> list[dict]:
    return [r for r in (rounds or []) if isinstance(r, dict) and not _is_internal_proactive_decision_round(r)]


def step_inject_latest_4_rounds_for_new_window(
    body: dict,
    window_id: str,
    force_last4: bool = False,
    exclude_claude_carryover_round: bool = False,
) -> dict:
    """
    新窗口：从 R2 读取全局「最新四轮」注入。
    Telegram 窗口优先注入该窗口自己的最近四轮，不混入全局 latest_4_rounds。
    已有历史但请求里消息很少（如主动发消息只发一条）：注入该窗口自己的最近四轮（如 Telegram 侧 Last4）。
    """
    if not window_id:
        return body
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    inject_label = ""
    rounds = []
    desc_scope_window_id: str | None = None
    is_telegram_window = window_id.startswith("tg_")
    excluded_round_index = 0
    if exclude_claude_carryover_round:
        from services.claude_thinking_carryover import previous_claude_thinking_carryover_round_index

        excluded_round_index = previous_claude_thinking_carryover_round_index(window_id, body=body)

    def _recent_rounds_without_carryover(items: list) -> list[dict]:
        filtered = _filter_rounds_for_recent_context(items)
        if excluded_round_index <= 0:
            return filtered
        return [
            item
            for item in filtered
            if int((item or {}).get("index") or (item or {}).get("round_index") or 0) != excluded_round_index
        ]

    if is_telegram_window:
        # Telegram 只按“本窗口 Last4”注入；文游已迁出 TG，不再混入群窗口上下文。
        if force_last4 or len(messages) <= 2 or r2_store.has_window_history(window_id):
            private_rounds = _recent_rounds_without_carryover(
                r2_store.get_conversation_rounds(window_id, last_n=12) or []
            )
            merged = []

            def _with_src(arr: list, src: str) -> list:
                out = []
                for r in arr:
                    if isinstance(r, dict):
                        rr = dict(r)
                        rr["_inject_src"] = src
                        out.append(rr)
                return out

            merged.extend(_with_src(private_rounds, "私聊"))

            merged.sort(key=lambda x: str(x.get("timestamp") or ""))
            rounds = merged[-4:]
            inject_label = "最近的对话"
            desc_scope_window_id = window_id
    else:
        if not r2_store.has_window_history(window_id):
            rounds = _recent_rounds_without_carryover(r2_store.get_latest_4_rounds_global() or [])[-4:]
            inject_label = "最近的对话"
            desc_scope_window_id = None
        else:
            # 已有历史且当前请求消息很少（如 proactive 只发 1 条 user）→ 注入本窗口最近 4 轮
            # force_last4=True 时即使 messages 较多也强制注入。
            if force_last4 or len(messages) <= 2:
                rounds = _recent_rounds_without_carryover(
                    r2_store.get_conversation_rounds(window_id, last_n=12) or []
                )[-4:]
                inject_label = "最近的对话"
                desc_scope_window_id = window_id

    if not rounds:
        return body
    desc_map = r2_store.get_recent_image_description_map(desc_scope_window_id)
    rounds = image_desc.replace_image_placeholders_in_obj(rounds, desc_map)
    try:
        from services.recall_message_markers import apply_recall_markers_to_rounds

        marker_window_id = desc_scope_window_id if desc_scope_window_id is not None else ""
        rounds = apply_recall_markers_to_rounds(rounds, marker_window_id)
    except Exception:
        logger.debug("recall_message_markers_apply_failed window_id=%s", window_id, exc_info=True)
    # Telegram 注入时保留来源标签，便于后续扩展其它入口时区分上下文。
    if is_telegram_window:
        lines = []
        last_pos = _last_recent_context_message_position(rounds)
        for ri, r in enumerate(rounds):
            src = str((r or {}).get("_inject_src") or "").strip()
            src_tag = f"【{src}】" if src else ""
            for mi, m in enumerate(r.get("messages") or []):
                role = str(m.get("role", "") or "").strip().lower()
                lines.append(
                    _format_recent_context_message_line(
                        r,
                        m,
                        role,
                        is_last_message=last_pos == (ri, mi),
                        src_tag=src_tag,
                    )
                )
            action_note = str((r or {}).get("action_note") or "").strip()
            if action_note:
                lines.append(f"{src_tag}[action_note]: {action_note}")
        context = "\n".join(lines) if lines else ""
    else:
        context = _rounds_to_context_text(rounds)
    if not context:
        return body
    inject = f"\n\n【{inject_label}】\n{context}\n【以上为最近的对话】"
    return _append_to_last4_system(body, inject)


def _last_assistant_text(body: dict) -> str:
    """取 body 中最后一条 assistant（渡）消息的纯文本（用于按需注入判断）。只拼 type=text 的 part，忽略图片等，避免 [image_url] 等导致误判。"""
    messages = body.get("messages") or []
    for m in reversed(messages):
        if (m.get("role") or "").lower() != "assistant":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
            return " ".join(parts).strip()
        return str(content) if content else ""
    return ""


def _is_question_like(text: str) -> bool:
    """简单判断是否像问句：结尾有？或含 吗/呢/啊/呀 等。"""
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if t.endswith("?") or t.endswith("？"):
        return True
    for q in ("吗", "呢", "啊", "呀"):
        if q in t:
            return True
    return False


def step_inject_summary(body: dict, window_id: str, is_user_input: bool = False) -> dict:
    """
    常驻注入：今日日期（北京时间）+ 当前大概时段 + get_time_info 提示；有 R2 总结时再追加【窗口记忆总结】。
    兜底：渡的上一轮是问句且含「几点/时间/现在」→ 本轮注入具体时间。
    农历：渡的上一轮含「农历/节气/宜忌/黄历」→ 本轮注入农历节气宜忌。
    """
    from utils.time_aware import (
        get_date_only,
        get_weekday_cn,
        get_time_period,
        get_exact_time,
        get_lunar_and_terms,
        now_beijing_iso,
        _now_beijing,
    )

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    now = None  # time_aware 内用北京时间
    today = get_date_only(now)
    weekday = get_weekday_cn(now)
    period = get_time_period(now)
    head = (
        f"\n\n今日：{today}（{weekday}），当前大概：{period}\n"
        f"如需知道当前几点，可使用网关提供的 get_time_info 时间工具；"
        f"如需查询天气，可使用专门的天气查询工具。\n"
        f"想写东西的时候就去写日记！顺便可以翻翻列表，说不定能看到老婆新写的日记？"
    )

    # 老婆多久没回：Telegram 窗口只在“真实用户输入”时触发，避免网关内部请求误判
    try:
        has_user_message = any((m.get("role") or "").lower() == "user" for m in messages if isinstance(m, dict))
        is_tg_window = str(window_id or "").startswith("tg_")
        should_track_reply_gap = is_user_input if is_tg_window else has_user_message
        if should_track_reply_gap:
            previous = capture_previous_interaction_and_mark_chat(now_beijing_iso())
            delta_sec = user_activity_elapsed_seconds(previous, _now_beijing())
            if (
                delta_sec is not None
                and REPLY_GAP_THRESHOLD_MINUTES
                and delta_sec >= REPLY_GAP_THRESHOLD_MINUTES * 60
            ):
                gap_prompt = render_incoming_gap_prompt(previous, delta_sec)
                if gap_prompt:
                    head += f"\n{gap_prompt}"
    except Exception as e:
        logger.debug("reply_gap 注入失败（忽略） error=%s", e)
    last_assistant = _last_assistant_text(body)
    last_lower = (last_assistant or "").lower()
    if ASSISTANT_TIME_KEYWORDS and _is_question_like(last_assistant):
        if any(kw in last_lower for kw in ASSISTANT_TIME_KEYWORDS):
            head += f"\n当前时间：{get_exact_time(now)}"
    if ASSISTANT_LUNAR_KEYWORDS and any(kw in last_lower for kw in ASSISTANT_LUNAR_KEYWORDS):
        head += f"\n{get_lunar_and_terms(now)}"

    summary = r2_store.get_summary(window_id) or ""
    chunks_state = r2_store.get_summary_chunks(window_id)
    stable_summary, recent_summaries, normalized_state = deepseek_summary.render_summary_prompt_blocks(
        chunks_state,
        summary,
    )
    generation = normalized_state.get("generation") if isinstance(normalized_state.get("generation"), dict) else {}
    recent_chunk_ids, generation_chunk_ids = _summary_prompt_chunk_ids(normalized_state)
    body[_PROMPT_CACHE_LAYOUT_BODY_KEY] = {
        "window_id": str(window_id or ""),
        "generation_id": int(generation.get("id") or 0),
        "generation_updates_done": int(generation.get("updates_done") or 0),
        "recent_blocks": len(recent_summaries),
        "recent_chunk_ids": recent_chunk_ids,
        "generation_chunk_ids": generation_chunk_ids,
        "generation_base_recent_ids": _summary_generation_base_recent_ids(normalized_state),
        "generation_chunk_item_ids": _summary_prompt_chunk_item_ids(normalized_state),
        "hot_tool_blocks": 0,
    }
    if stable_summary or recent_summaries:
        body = _upsert_summary_cache_system(body, stable_summary, recent_summaries)
    inject = head
    body = _append_to_dynamic_system(body, inject)
    return body
