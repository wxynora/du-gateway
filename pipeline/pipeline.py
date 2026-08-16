# 管道主流程：清洗(图片) → 新窗口注入 → 记忆注入 → 转发 → 存档/总结（不再按窗口 ID 判定）
import copy
import threading
import requests
from typing import Optional

from config import (
    SUMMARY_EVERY_N_ROUNDS,
    DYNAMIC_MEMORY_BEDROOM_DAYS_VALID,
    DYNAMIC_MEMORY_TOP_N,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
    DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED,
    DYNAMIC_MEMORY_REVIEW_ALL_MERGES,
    DEEPSEEK_API_URL,
    DEEPSEEK_API_KEY,
    DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED,
)
from storage import r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_dynamic_budget

logger = get_logger(__name__)
from services import deepseek_summary
from services.dynamic_memory_citation import DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY
from pipeline.prompt_layout import (
    _DU_DAILY_SYSTEM_MARKER,
    _DYNAMIC_SYSTEM_MARKER,
    _ENTRY_STYLE_SYSTEM_MARKER,
    _LAST4_SYSTEM_MARKER,
    _PLAY_NOTE_SYSTEM_MARKER,
    _PROMPT_CACHE_LAYOUT_BODY_KEY,
    _STATIC_CACHE_ANCHOR_SYSTEM_MARKER,
    _SUMITALK_REAL_MODE_SYSTEM_MARKER,
    _SUMMARY_CACHE_SYSTEM_MARKER,
    _SUMMARY_RECENT_SYSTEM_MARKER,
    _TEMPORARY_DYNAMIC_SYSTEM_MARKER,
    _THINKING_RULES_SYSTEM_MARKER,
    _TOOL_RESULT_CACHE_SYSTEM_MARKER,
    _VOICE_RULES_SYSTEM_MARKER,
    _append_to_dynamic_system,
    _append_to_static_system,
    _system_prompt_region,
    _upsert_summary_cache_system,
)
import pipeline.prompt_content as _prompt_content
from pipeline.prompt_content import (
    OPUS46_REALITY_MESSAGE_PROMPT,
    SUMITALK_APP_PROMPT,
    SUMITALK_REAL_MODE_PROMPT,
    _CORE_BEHAVIOR_RULES,
    _DU_NON_RETREAT_RULES,
    _MID_CONVERSATION_SYSTEM_MARKER,
    _THINKING_BLOCK_RULES,
    _load_du_core_prompt,
    _load_managed_static_prompt,
    step_inject_common_knowledge,
    step_inject_custom_static_systems,
    step_inject_draft_reminder,
    step_inject_pending_thought_rules,
    step_inject_reference_note,
    step_replace_rikka_system,
)
from pipeline.request_prepare import (
    step_clean_for_forward,
    step_clean_images_and_save_desc,
    step_trim_messages_if_over_limit,
)
from pipeline.request_context import PipelineRequestContext
from pipeline.context_injections import (
    _PLAY_NOTE_PENDING_BODY_KEY,
    step_inject_current_base_model,
    step_inject_du_daily,
    step_inject_du_midterm_memory,
    step_inject_du_notebook,
    step_inject_du_thought,
    step_inject_du_vitals,
    step_inject_humor_memes,
    step_inject_interaction_candidate,
    step_inject_pending_thoughts,
    step_inject_pixel_home,
    step_inject_secret_drawer,
    step_inject_sense_snapshot,
    step_inject_stay_with_du,
    step_inject_system_alarm_action_result,
    step_inject_wakeup_frame,
)
from pipeline.recent_context import (
    _filter_rounds_for_recent_context,
    _format_recent_context_message_line,
    _rounds_to_context_text,
    _summary_generation_base_recent_ids,
    _summary_prompt_chunk_ids,
    _summary_prompt_chunk_item_ids,
    step_inject_latest_4_rounds_for_new_window,
    step_inject_summary,
    step_inject_tool_result_cache,
)
import pipeline.archive as _archive
import pipeline.memory_evolution as _memory_evolution
import pipeline.memory_recall as _memory_recall
import pipeline.post_archive as _post_archive
from pipeline.archive import (
    _build_round_action_note,
)
from pipeline.post_archive import (
    _summary_existing_round_ranges,
    _summary_round_chunk_id,
    _summary_window_lock,
    _with_summary_tool_item_ids,
)
from pipeline.memory_recall import (
    RecallResult,
    _MEMORY_QUERY_REWRITE_MODEL,
    _bm25_recall_scores,
    _build_retrieval_text,
    _dedupe_recalled_memories,
    _dynamic_memory_rerank_document,
    _dynamic_memory_rerank_query,
    _extract_keyword_candidates,
    _filter_dynamic_memory_timeout_fallback,
    _invalidate_recall_cache as _memory_recall_invalidate_recall_cache,
    _is_memory_meta_query,
    _is_trivial_user_message,
    _last_4_turns_text_for_rewrite,
    _memory_event_timestamp,
    _memory_recall_prior,
    _memory_recall_sort_score,
    _memory_retrieval_text,
    _memory_weight,
    _normalize_bm25_score,
    _normalized_memory_prior,
    _parse_memory_query_rewrite_output,
    _parse_memory_query_state_output,
    _recall_cache_hit,
    _recall_cache_set,
    _select_dynamic_memory_rerank_candidates,
    _strip_memory_query_media_placeholders,
    _topic_state_anchor_candidates,
)
from pipeline.memory_evolution import (
    _core_protected_dynamic_memory_ids,
    _normalize_memory_labels,
    _round_messages_to_raw_text,
    _wenyou_round_skip_dynamic,
)


__all__ = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_URL",
    "DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY",
    "DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED",
    "DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT",
    "DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS",
    "DYNAMIC_MEMORY_REVIEW_ALL_MERGES",
    "DYNAMIC_MEMORY_TOP_N",
    "OPUS46_REALITY_MESSAGE_PROMPT",
    "PipelineRequestContext",
    "RecallResult",
    "SUMITALK_APP_PROMPT",
    "SUMITALK_REAL_MODE_PROMPT",
    "SUMMARY_EVERY_N_ROUNDS",
    "_CORE_BEHAVIOR_RULES",
    "_DU_DAILY_SYSTEM_MARKER",
    "_DU_NON_RETREAT_RULES",
    "_DYNAMIC_SYSTEM_MARKER",
    "_ENTRY_STYLE_SYSTEM_MARKER",
    "_LAST4_SYSTEM_MARKER",
    "_MID_CONVERSATION_SYSTEM_MARKER",
    "_PROMPT_CACHE_LAYOUT_BODY_KEY",
    "_STATIC_CACHE_ANCHOR_SYSTEM_MARKER",
    "_SUMITALK_REAL_MODE_SYSTEM_MARKER",
    "_SUMMARY_CACHE_SYSTEM_MARKER",
    "_SUMMARY_RECENT_SYSTEM_MARKER",
    "_TEMPORARY_DYNAMIC_SYSTEM_MARKER",
    "_THINKING_BLOCK_RULES",
    "_THINKING_RULES_SYSTEM_MARKER",
    "_TOOL_RESULT_CACHE_SYSTEM_MARKER",
    "_VOICE_RULES_SYSTEM_MARKER",
    "_append_dynamic_recall_debug_event_safe",
    "_append_to_static_system",
    "_apply_external_dynamic_memory_rerank",
    "_apply_one_decision",
    "_bm25_recall_scores",
    "_build_retrieval_text",
    "_build_round_action_note",
    "_build_sqlite_shadow_compare",
    "_core_protected_dynamic_memory_ids",
    "_dynamic_memory_rerank_query",
    "_extract_keyword_candidates",
    "_format_recent_context_message_line",
    "_invalidate_recall_cache",
    "_is_marginal_dynamic_memory_for_prune",
    "_is_memory_meta_query",
    "_is_trivial_user_message",
    "_last_4_turns_text_for_rewrite",
    "_load_du_core_prompt",
    "_load_managed_static_prompt",
    "_memory_recall_sort_score",
    "_memory_weight",
    "_merge_vector_and_bm25_recall",
    "_multi_query_recall_and_rerank",
    "_normalize_bm25_score",
    "_normalized_memory_prior",
    "_parse_memory_query_rewrite_output",
    "_previous_4_rounds_text_for_rewrite",
    "_recall_cache_hit",
    "_rewrite_memory_queries_with_ds",
    "_rewrite_memory_query_state_with_ds",
    "_rounds_to_context_text",
    "_should_prune_dynamic_memory",
    "_step_dynamic_layer_evolve",
    "_summary_prompt_chunk_ids",
    "_summary_read_round_group",
    "_summary_round_groups_to_process",
    "_system_prompt_region",
    "_topic_state_anchor_candidates",
    "_upsert_dynamic_memory_index",
    "_upsert_summary_cache_system",
    "estimate_tokens",
    "memory_dynamic_budget",
    "recall_dynamic_memory",
    "r2_store",
    "requests",
    "step_archive_and_maybe_summary",
    "step_archive_round",
    "step_clean_for_forward",
    "step_clean_images_and_save_desc",
    "step_inject_amap_mcp_tools",
    "step_inject_chat_tools",
    "step_inject_common_knowledge",
    "step_inject_core_behavior_rules",
    "step_inject_current_base_model",
    "step_inject_custom_static_systems",
    "step_inject_draft_reminder",
    "step_inject_du_daily",
    "step_inject_du_midterm_memory",
    "step_inject_du_non_retreat_rules",
    "step_inject_du_notebook",
    "step_inject_du_thought",
    "step_inject_du_vitals",
    "step_inject_dynamic_memory",
    "step_inject_forum_tools",
    "step_inject_gateway_tools",
    "step_inject_humor_memes",
    "step_inject_interaction_candidate",
    "step_inject_latest_4_rounds_for_new_window",
    "step_inject_pending_thought_rules",
    "step_inject_pending_thoughts",
    "step_inject_pixel_home",
    "step_inject_play_note",
    "step_inject_random_imitator_td_tools",
    "step_inject_reference_note",
    "step_inject_rikkahub_reminder",
    "step_inject_secret_drawer",
    "step_inject_sense_snapshot",
    "step_inject_stay_with_du",
    "step_inject_sumitalk_real_mode",
    "step_inject_summary",
    "step_inject_system_alarm_action_result",
    "step_inject_thinking_block_rules",
    "step_inject_tool_result_cache",
    "step_inject_voice_rules",
    "step_inject_wakeup_frame",
    "step_inject_websearch_tools",
    "step_inject_wenyou_player_tools",
    "step_replace_rikka_system",
    "step_run_post_archive_tasks",
    "step_trim_messages_if_over_limit",
    "threading",
)


def step_inject_voice_rules(body: dict, *, reply_channel: str = "") -> dict:
    return _prompt_content.step_inject_voice_rules(
        body,
        reply_channel=reply_channel,
        _managed_prompt_loader=_load_managed_static_prompt,
    )


def step_inject_sumitalk_real_mode(
    body: dict,
    enabled: bool = False,
    *,
    app_request: bool = False,
    reply_channel: str = "",
    reply_target: str = "",
    model: str = "",
    anthropic_messages: bool = False,
    wakeup_kind: str = "",
) -> dict:
    return _prompt_content.step_inject_sumitalk_real_mode(
        body,
        enabled,
        app_request=app_request,
        reply_channel=reply_channel,
        reply_target=reply_target,
        model=model,
        anthropic_messages=anthropic_messages,
        wakeup_kind=wakeup_kind,
        _managed_prompt_loader=_load_managed_static_prompt,
    )


def step_inject_du_non_retreat_rules(body: dict) -> dict:
    return _prompt_content.step_inject_du_non_retreat_rules(
        body,
        _managed_prompt_loader=_load_managed_static_prompt,
    )


def step_inject_thinking_block_rules(
    body: dict,
    *,
    model: str = "",
    anthropic_messages: bool = False,
) -> dict:
    return _prompt_content.step_inject_thinking_block_rules(
        body,
        model=model,
        anthropic_messages=anthropic_messages,
        _managed_prompt_loader=_load_managed_static_prompt,
    )


def step_inject_core_behavior_rules(body: dict) -> dict:
    return _prompt_content.step_inject_core_behavior_rules(
        body,
        _managed_prompt_loader=_load_managed_static_prompt,
    )

# ---------------------------------------------------------------------------
# Prompt-cache 友好：静态 system 在前（可被缓存），动态 system 在后（每轮变化）。
# 动态注入统一追加到带 _dynamic_system 标记的 system 消息，避免污染静态前缀。
# ---------------------------------------------------------------------------

def step_inject_play_note(body: dict) -> dict:
    """Place the current play note in the temporary dynamic region."""
    pending = str((body or {}).get(_PLAY_NOTE_PENDING_BODY_KEY) or "").strip()
    if not pending:
        return body

    body = copy.deepcopy(body)
    body.pop(_PLAY_NOTE_PENDING_BODY_KEY, None)
    messages = [
        msg for msg in (body.get("messages") or [])
        if not (isinstance(msg, dict) and msg.get(_PLAY_NOTE_SYSTEM_MARKER))
    ]
    body["messages"] = messages

    first_boundary_idx = len(messages)
    real_mode_idx = -1
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or (msg.get("role") or "").lower() != "system":
            first_boundary_idx = i
            break
        if msg.get(_SUMITALK_REAL_MODE_SYSTEM_MARKER):
            real_mode_idx = i
        if (
            msg.get(_SUMMARY_CACHE_SYSTEM_MARKER)
            or msg.get(_SUMMARY_RECENT_SYSTEM_MARKER)
            or msg.get(_DYNAMIC_SYSTEM_MARKER)
        ):
            first_boundary_idx = i
            break
    insert_idx = min(real_mode_idx + 1, first_boundary_idx) if real_mode_idx >= 0 else first_boundary_idx
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": pending,
            _PLAY_NOTE_SYSTEM_MARKER: True,
        },
    )
    return body


def step_inject_rikkahub_reminder(body: dict, window_id: str) -> dict:
    """
    当请求不是来自 Telegram（window_id 为空或不以 tg_ 开头）时，注入「当前是在 RikkaHub」提醒。
    一直提醒，实现简单。
    """
    if not body or not isinstance(body.get("messages"), list):
        return body
    if window_id and str(window_id).strip().startswith("tg_"):
        return body
    inject = "\n\n【你当前正在 RikkaHub 和小玥聊天】\n【小提醒】无聊时可以逛逛 AI 论坛哦。"
    body = _append_to_dynamic_system(body, inject)
    return body


def _previous_4_rounds_text_for_rewrite(window_id: str) -> str:
    return _memory_recall._previous_4_rounds_text_for_rewrite(
        window_id,
        r2_store_module=r2_store,
        filter_rounds=lambda rounds: _filter_rounds_for_recent_context(rounds),
        last_4_turns_text=lambda messages: _last_4_turns_text_for_rewrite(messages),
    )


def _rewrite_memory_query_state_with_ds(
    previous_four_rounds: str,
    user_message: str,
    previous_topic_state: dict | None = None,
) -> dict:
    return _memory_recall._rewrite_memory_query_state_with_ds(
        previous_four_rounds,
        user_message,
        previous_topic_state,
        deepseek_api_key=DEEPSEEK_API_KEY,
        deepseek_api_url=DEEPSEEK_API_URL,
        requests_module=requests,
        logger_instance=logger,
        model=_MEMORY_QUERY_REWRITE_MODEL,
        parse_output=lambda content, state: _parse_memory_query_state_output(content, state),
    )


def _rewrite_memory_queries_with_ds(last_4_turns: str, user_message: str) -> list[str]:
    return _memory_recall._rewrite_memory_queries_with_ds(
        last_4_turns,
        user_message,
        rewrite_query_state=lambda *args, **kwargs: _rewrite_memory_query_state_with_ds(*args, **kwargs),
    )


def _dynamic_recall_pool_limit() -> int:
    return _memory_recall._dynamic_recall_pool_limit(dynamic_memory_top_n=DYNAMIC_MEMORY_TOP_N)


def _multi_query_recall_and_rerank(base_query: str, expanded_queries: list[str]) -> list[dict]:
    return _memory_recall._multi_query_recall_and_rerank(
        base_query,
        expanded_queries,
        pool_limit=lambda: _dynamic_recall_pool_limit(),
        logger_instance=logger,
    )


def _merge_vector_and_bm25_recall(
    vector_recalled: list[dict],
    bm25_scores: dict[str, dict],
) -> list[dict]:
    return _memory_recall._merge_vector_and_bm25_recall(
        vector_recalled,
        bm25_scores,
        pool_limit=lambda: _dynamic_recall_pool_limit(),
        memory_weight=lambda mem, now=None: _memory_weight(mem, now=now),
    )


def _apply_external_dynamic_memory_rerank(
    recalled: list[dict],
    last_user_text: str,
    retrieval_query: str,
    messages: list[dict],
    resolved_query: str,
    expanded_queries: list[str],
    recall_source: str,
    keyword_candidates: list[dict] | None = None,
    previous_four_rounds: str = "",
    topic_state: dict | None = None,
) -> tuple[list[dict], str, dict]:
    return _memory_recall._apply_external_dynamic_memory_rerank(
        recalled,
        last_user_text,
        retrieval_query,
        messages,
        resolved_query,
        expanded_queries,
        recall_source,
        keyword_candidates,
        previous_four_rounds,
        topic_state,
        rerank_query_builder=lambda *args, **kwargs: _dynamic_memory_rerank_query(*args, **kwargs),
        rerank_document_builder=lambda mem: _dynamic_memory_rerank_document(mem),
        select_candidates=lambda *args, **kwargs: _select_dynamic_memory_rerank_candidates(*args, **kwargs),
        timeout_fallback=lambda *args, **kwargs: _filter_dynamic_memory_timeout_fallback(*args, **kwargs),
        logger_instance=logger,
    )


def _append_dynamic_recall_debug_event_safe(event: dict) -> None:
    return _memory_recall._append_dynamic_recall_debug_event_safe(
        event,
        r2_store_module=r2_store,
        logger_instance=logger,
    )


def _invalidate_recall_cache() -> None:
    return _memory_recall_invalidate_recall_cache()


def _build_sqlite_shadow_compare(
    *,
    query: str,
    retrieval_query: str,
    keywords: list[str],
    actual_ids: list[str],
    valid_memory_ids: set[str],
) -> dict:
    return _memory_recall._build_sqlite_shadow_compare(
        query=query,
        retrieval_query=retrieval_query,
        keywords=keywords,
        actual_ids=actual_ids,
        valid_memory_ids=valid_memory_ids,
        enabled=DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED,
        dynamic_memory_top_n=DYNAMIC_MEMORY_TOP_N,
    )


def _is_tag_expired_dynamic_memory_for_prune(mem: dict, now) -> bool:
    return _memory_evolution._is_tag_expired_dynamic_memory_for_prune(
        mem,
        now,
        bedroom_days_valid=DYNAMIC_MEMORY_BEDROOM_DAYS_VALID,
    )


def _is_marginal_dynamic_memory_for_prune(mem: dict, now) -> bool:
    return _memory_evolution._is_marginal_dynamic_memory_for_prune(
        mem,
        now,
        marginal_prune_enabled=DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
        marginal_prune_max_weight=DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
        marginal_prune_min_days=DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
        tag_expired=lambda item, current: _is_tag_expired_dynamic_memory_for_prune(item, current),
        memory_weight=lambda item, current=None: _memory_weight(item, now=current),
    )


def _should_prune_dynamic_memory(mem: dict, now, protected_ids: set[str]) -> bool:
    return _memory_evolution._should_prune_dynamic_memory(
        mem,
        now,
        protected_ids,
        is_marginal=lambda item, current: _is_marginal_dynamic_memory_for_prune(item, current),
    )


def _prune_dynamic_memories_before_recall(memories: list, core_pending: list) -> list:
    return _memory_evolution.prune_dynamic_memories_before_recall(
        memories,
        core_pending,
        r2_store_module=r2_store,
        protected_ids_for_core=lambda items: _core_protected_dynamic_memory_ids(items),
        should_prune=lambda mem, now, protected: _should_prune_dynamic_memory(mem, now, protected),
        marginal_prune_max_weight=DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
        marginal_prune_min_days=DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
        logger_instance=logger,
    )


def _upsert_dynamic_memory_index(mem: dict) -> None:
    return _memory_evolution._upsert_dynamic_memory_index(
        mem,
        retrieval_text_builder=lambda item: _memory_retrieval_text(item),
        event_timestamp=lambda item: _memory_event_timestamp(item),
        logger_instance=logger,
    )


def _move_promoted_memories_out_of_dynamic(
    current_memories: list,
    promoted_ids: set[str],
    *,
    expected_snapshot: list,
) -> bool:
    return _memory_evolution._move_promoted_memories_out_of_dynamic(
        current_memories,
        promoted_ids,
        expected_snapshot=expected_snapshot,
        r2_store_module=r2_store,
        invalidate_recall_cache=lambda: _invalidate_recall_cache(),
        logger_instance=logger,
    )


def recall_dynamic_memory(
    body: dict,
    window_id: str,
    *,
    use_recall_cache: bool = True,
) -> RecallResult:
    return _memory_recall.recall_dynamic_memory(
        body,
        window_id,
        use_recall_cache=use_recall_cache,
        dynamic_memory_top_n=DYNAMIC_MEMORY_TOP_N,
        r2_store_module=r2_store,
        prune_dynamic_memories=lambda memories, core_pending: _prune_dynamic_memories_before_recall(
            memories,
            core_pending,
        ),
        is_memory_meta_query=lambda text: _is_memory_meta_query(text),
        is_trivial_user_message=lambda text: _is_trivial_user_message(text),
        extract_keyword_candidates=lambda text: _extract_keyword_candidates(text),
        previous_four_rounds_text=lambda target_window_id: _previous_4_rounds_text_for_rewrite(
            target_window_id
        ),
        rewrite_query_state=lambda *args, **kwargs: _rewrite_memory_query_state_with_ds(*args, **kwargs),
        topic_anchor_candidates=lambda state, evidence: _topic_state_anchor_candidates(state, evidence),
        build_retrieval_text=lambda text: _build_retrieval_text(text),
        strip_memory_query_media_placeholders=lambda text: _strip_memory_query_media_placeholders(text),
        recall_cache_hit=lambda target_window_id, keywords: _recall_cache_hit(target_window_id, keywords),
        recall_cache_set=lambda target_window_id, keywords, results, source: _recall_cache_set(
            target_window_id,
            keywords,
            results,
            source=source,
        ),
        dedupe_recalled_memories=lambda memories: _dedupe_recalled_memories(memories),
        multi_query_recall_and_rerank=lambda query, expansions: _multi_query_recall_and_rerank(
            query,
            expansions,
        ),
        bm25_recall_scores=lambda query, candidates, memories: _bm25_recall_scores(
            query,
            candidates,
            memories,
        ),
        merge_vector_and_bm25_recall=lambda vector, bm25: _merge_vector_and_bm25_recall(
            vector,
            bm25,
        ),
        external_rerank=lambda *args, **kwargs: _apply_external_dynamic_memory_rerank(*args, **kwargs),
        memory_recall_sort_score=lambda mem: _memory_recall_sort_score(mem),
        memory_recall_prior=lambda mem: _memory_recall_prior(mem),
        append_recall_debug_event=lambda event: _append_dynamic_recall_debug_event_safe(event),
        build_sqlite_shadow_compare=lambda **kwargs: _build_sqlite_shadow_compare(**kwargs),
        dynamic_budget=lambda: memory_dynamic_budget(),
        token_estimator=lambda text: estimate_tokens(text),
        append_dynamic_system=lambda request_body, text: _append_to_dynamic_system(request_body, text),
        logger_instance=logger,
    )


def step_inject_dynamic_memory(
    body: dict,
    window_id: str,
    *,
    use_recall_cache: bool = True,
    recall_candidate_ids_out: Optional[list[str]] = None,
    recall_topic_state_out: Optional[dict] = None,
) -> dict:
    if recall_candidate_ids_out is not None:
        recall_candidate_ids_out[:] = []
    if recall_topic_state_out is not None:
        recall_topic_state_out.clear()
    result = recall_dynamic_memory(
        body,
        window_id,
        use_recall_cache=use_recall_cache,
    )
    if recall_candidate_ids_out is not None:
        recall_candidate_ids_out[:] = result.candidate_ids
    if recall_topic_state_out is not None:
        recall_topic_state_out.clear()
        recall_topic_state_out.update(result.topic_state)
    return result.body


def _apply_one_decision(
    window_id: str,
    round_index: int,
    round_messages: list,
    decision: dict,
    current_memories: list,
) -> Optional[dict]:
    return _memory_evolution._apply_one_decision(
        window_id,
        round_index,
        round_messages,
        decision,
        current_memories,
        r2_store_module=r2_store,
        normalize_memory_labels=lambda item: _normalize_memory_labels(item),
        build_retrieval_text=lambda text: _build_retrieval_text(text),
        round_messages_to_raw_text=lambda messages: _round_messages_to_raw_text(messages),
        move_promoted_memories=lambda memories, ids, **kwargs: _move_promoted_memories_out_of_dynamic(
            memories,
            ids,
            **kwargs,
        ),
        upsert_dynamic_memory_index=lambda mem: _upsert_dynamic_memory_index(mem),
        review_all_merges=DYNAMIC_MEMORY_REVIEW_ALL_MERGES,
        logger_instance=logger,
    )


def _apply_dynamic_body_delta(decision: dict, *, window_id: str, round_index: int) -> None:
    return _memory_evolution._apply_dynamic_body_delta(
        decision,
        window_id=window_id,
        round_index=round_index,
        logger_instance=logger,
    )


def _step_dynamic_layer_evolve(
    window_id: str,
    round_index: int,
    round_messages: list,
    *,
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
    query_topic_state: Optional[dict] = None,
) -> Optional[dict]:
    return _memory_evolution._step_dynamic_layer_evolve(
        window_id,
        round_index,
        round_messages,
        skip_dynamic_memory_write=skip_dynamic_memory_write,
        skip_body_delta=skip_body_delta,
        dynamic_memory_recall_candidate_ids=dynamic_memory_recall_candidate_ids,
        query_topic_state=query_topic_state,
        r2_store_module=r2_store,
        wenyou_round_skip_dynamic=lambda messages: _wenyou_round_skip_dynamic(messages),
        apply_one_decision=lambda *args, **kwargs: _apply_one_decision(*args, **kwargs),
        apply_dynamic_body_delta=lambda *args, **kwargs: _apply_dynamic_body_delta(*args, **kwargs),
        body_delta_enabled=DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED,
        logger_instance=logger,
    )


def _tool_schema_name(tool: dict) -> str:
    if not isinstance(tool, dict):
        return ""
    fn = tool.get("function") or {}
    if not isinstance(fn, dict):
        return ""
    return str(fn.get("name") or "").strip()


def _append_tool_schemas(body: dict, tools: list[dict]) -> dict:
    if not tools:
        return body
    body = copy.deepcopy(body)
    existing = body.get("tools")
    if not isinstance(existing, list):
        existing = []
        body["tools"] = existing
    existing_names = {_tool_schema_name(t) for t in existing if isinstance(t, dict)}
    for tool in tools:
        name = _tool_schema_name(tool)
        if not name or name in existing_names:
            continue
        existing.append(tool)
        existing_names.add(name)
    body["tool_choice"] = body.get("tool_choice") or "auto"
    return body


def step_inject_wenyou_player_tools(body: dict, *, enabled: bool = False) -> dict:
    """仅在全局无限流游戏模式开启时注入文游玩家工具。"""
    if not enabled:
        return body
    try:
        from services.wenyou_service import get_player_tool_schemas

        tools = get_player_tool_schemas()
    except Exception as e:
        logger.debug("wenyou player tools 注入跳过 error=%s", e)
        return body
    return _append_tool_schemas(body, tools)


def step_inject_gateway_tools(body: dict) -> dict:
    """注入不依赖外部开关的网关工具，例如小爱音箱外放。"""
    try:
        from services.gateway_tools import get_gateway_tools_for_inject

        tools = get_gateway_tools_for_inject()
    except Exception as e:
        logger.debug("gateway tools 注入跳过 error=%s", e)
        return body
    return _append_tool_schemas(body, tools)


def step_inject_random_imitator_td_tools(body: dict) -> dict:
    """注入随机塔防工具；是否调用本 step 由聊天入口的专用标记或后端模式开关决定。"""
    try:
        from services.random_imitator_td_tool import get_random_imitator_td_tools_for_inject

        tools = get_random_imitator_td_tools_for_inject()
    except Exception as e:
        logger.debug("random_imitator_td tools 注入跳过 error=%s", e)
        return body
    return _append_tool_schemas(body, tools)


def step_inject_chat_tools(body: dict) -> dict:
    """注入聊天工具集合。"""
    from services.chat_tools import get_chat_tools_for_inject

    tools = get_chat_tools_for_inject()
    if not tools:
        return body
    return _append_tool_schemas(body, tools)


def step_inject_forum_tools(body: dict) -> dict:
    """
    当 MCP_ENABLED=1 时，向 body 注入论坛复合工具和远端原始工具（forum_read_feed/forum_open_thread/cli/get_guide）。
    """
    from config import MCP_ENABLED

    if not MCP_ENABLED:
        return body

    from services.mcp_forum_tools import get_forum_tools_for_inject

    tools = get_forum_tools_for_inject()
    if not tools:
        return body

    body = copy.deepcopy(body)
    existing = body.get("tools")
    if isinstance(existing, list):
        existing_names = set()
        for t in existing:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict):
                    name = fn.get("name")
                    if name:
                        existing_names.add(name)
        # 追加缺失的工具定义，避免重复
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name")
                if name and name not in existing_names:
                    existing.append(t)
    else:
        body["tools"] = tools

    body["tool_choice"] = body.get("tool_choice") or "auto"
    schedule_hint = (
        "\n\n【提醒工具优先级】"
        "如果是提醒辛玥本人，优先使用手机系统能力："
        "单纯到点叫醒或提醒用 create_system_alarm，默认 skip_ui=true 直接创建；"
        "带具体日期、行程、地点或提前提醒用 create_calendar_event。"
        "du_schedule(action=create) 只用于提醒你自己、重复提醒暂时无法落系统能力、或系统能力不可用时的内部兜底。"
        "也可以用 du_schedule(action=list/enable/disable/delete) 管理已有提醒。"
    )
    screen_check_hint = (
        "\n\n【查岗截图工具】"
        "request_screen_check 是经她确认的查岗申请，不是偷偷读屏；"
        "你惦记她、想知道她现在在忙什么、她突然安静，或想带一点玩笑地查岗时，可以主动用。"
        "不必等她先说“你可以看”，因为工具本身会让她选择同意或拒绝。"
        "不要短时间连续发起；她拒绝或没理时先停一停。"
    )
    forum_hint = (
        "\n\n【论坛工具省费规则】"
        "看帖优先用 forum_read_feed / forum_open_thread；"
        "发帖、私信、资料、规则或论坛新功能优先直接用 cli / get_guide。"
        "第一次用 cli 时，先用 get_guide(section=\"cli\") 或 cli(command=\"help\") 看命令格式；"
        "cli 的 command 不要带 lutopia 前缀；"
        "长内容用 --content-stdin，并把正文放进 stdin。"
        "若需要多个论坛信息，请在同一轮并行调用所需工具后再统一总结；"
        "不要串行试探式一轮只调一个工具。"
        "若已有同参数工具结果且用户未要求刷新，不要重复调用。"
    )
    body = _append_to_static_system(body, schedule_hint + screen_check_hint + forum_hint)
    return body


def step_inject_amap_mcp_tools(body: dict) -> dict:
    """
    按最近用户消息关键词注入高德官方 MCP 出行工具。
    """
    from services.amap_mcp_tools import get_amap_mcp_tools_for_inject, should_inject_amap_mcp_tools

    messages = body.get("messages") or []
    last_user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            last_user_text = content
        elif isinstance(content, list):
            last_user_text = " ".join(
                c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content
            )
        break
    if not should_inject_amap_mcp_tools(last_user_text):
        return body

    tools = get_amap_mcp_tools_for_inject()
    if not tools:
        return body

    body = copy.deepcopy(body)
    existing = body.get("tools")
    if isinstance(existing, list):
        existing_names = set()
        for t in existing:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict):
                    name = fn.get("name")
                    if name:
                        existing_names.add(name)
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name")
                if name and name not in existing_names:
                    existing.append(t)
    else:
        body["tools"] = tools

    body["tool_choice"] = body.get("tool_choice") or "auto"
    hint = (
        "\n\n【高德官方 MCP 出行工具规则】"
        "如果老婆只是想让你规划旅游/路线，但地点、吃饭、步行接受度等信息还不完整，先调用 open_travel_plan_form 弹出 SumiTalk 固定表单；"
        "老婆提交表单或问想去哪里、怎么规划路线时，优先调用 trip_prepare_facts；这个工具只查硬事实、创建 plan_id、启动后台预取，不代表最终顺序。"
        "你负责判断怎么排：user_overrides 永远优先；confirmed_state 其次；assistant_assumptions 只能影响建议和措辞，不能覆盖用户明确选择。"
        "confidence >= 0.85 的推断可直接用；0.5 到 0.85 需要轻确认；低于 0.5 当 unknown 或问用户。"
        "第一次回复只给短安排：先结论，再顺序/主要交通建议，最后必要提醒；不要写长篇分析，不要逐站展开，不要一次查一堆餐厅。"
        "用户后续追问某段怎么坐、能不能少走路、打车怎样，用 trip_get_transport_detail(plan_id, ...)；"
        "追问吃什么、附近有什么，用 trip_get_food_detail(plan_id, ...)；"
        "用户确认偏好、状态，或你做了后续要继续用的推断，用 trip_update_plan_state 写回；"
        "旅行结束、取消或过期时，用 trip_finalize_plan 收尾。"
        "只有需要补查单个地点/天气/链接，或分层工具缺的高德能力时，再调用 maps_*。"
        "交通路线、换乘站、耗时、营业和费用必须基于工具结果，不要凭空编。"
        "如果用户没说起点，优先结合已注入的最近定位；没有定位再追问起点。"
    )
    return _append_to_static_system(body, hint)


def step_inject_websearch_tools(body: dict) -> dict:
    """
    当 WEBSEARCH_ENABLED=1 时，向 body 注入 web_search 工具。
    """
    from config import WEBSEARCH_ENABLED

    if not WEBSEARCH_ENABLED:
        return body

    from services.web_search_tools import get_web_search_tools_for_inject

    tools = get_web_search_tools_for_inject()
    if not tools:
        return body

    body = copy.deepcopy(body)
    existing = body.get("tools")
    if isinstance(existing, list):
        existing_names = set()
        for t in existing:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict):
                    name = fn.get("name")
                    if name:
                        existing_names.add(name)
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name")
                if name and name not in existing_names:
                    existing.append(t)
    else:
        body["tools"] = tools

    body["tool_choice"] = body.get("tool_choice") or "auto"
    return body


def step_archive_and_maybe_summary(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
    reply_channel: str = "",
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
    query_topic_state: Optional[dict] = None,
) -> Optional[dict]:
    """
    存档本轮对话到 R2（完整清洗版）；每 4 轮异步更新实时层「渡的回忆」；动态层演化占位。
    与文档三数据流程一致：① 原文存档（windows/ + conversations/）② 满 4 轮更新实时层 ③ 动态层处理占位。
    存记忆只存对话（user + assistant），不含 system / RikkaHub 说明；内容必走 R2 清洗（Rikka 预设、表情包→文字）。
    round_cleaned_for_r2: 可选，[user_msg_cleaned, assistant_msg_cleaned]。
    """
    archived = step_archive_round(
        window_id,
        request_messages,
        assistant_message,
        round_cleaned_for_r2=round_cleaned_for_r2,
        reply_channel=reply_channel,
    )
    if not archived:
        return None
    step_run_post_archive_tasks(
        window_id,
        archived["round_index"],
        archived["round_messages"],
        skip_dynamic_memory_write=skip_dynamic_memory_write,
        skip_body_delta=skip_body_delta,
        dynamic_memory_recall_candidate_ids=dynamic_memory_recall_candidate_ids,
        query_topic_state=query_topic_state,
    )
    return archived


def step_archive_round(
    window_id: str,
    request_messages: list,
    assistant_message: dict,
    round_cleaned_for_r2: Optional[list] = None,
    reply_channel: str = "",
) -> Optional[dict]:
    """同步写入本轮对话存档与 latest4，返回后续慢任务需要的 round_index/round_messages。"""
    return _archive._step_archive_round(
        window_id,
        request_messages,
        assistant_message,
        round_cleaned_for_r2=round_cleaned_for_r2,
        reply_channel=reply_channel,
        r2_store_module=r2_store,
        logger_instance=logger,
        action_note_builder=_build_round_action_note,
    )


def _summary_read_round_group(window_id: str, start: int, end: int) -> list[dict]:
    return _post_archive._summary_read_round_group_impl(
        window_id,
        start,
        end,
        r2_store_module=r2_store,
        logger_instance=logger,
    )


def _summary_round_groups_to_process(
    window_id: str,
    round_index: int,
    chunks_state: dict | None,
) -> list[list[dict]]:
    return _post_archive._summary_round_groups_to_process_impl(
        window_id,
        round_index,
        chunks_state,
        summary_every_n_rounds=SUMMARY_EVERY_N_ROUNDS,
        deepseek_summary_module=deepseek_summary,
        r2_store_module=r2_store,
        existing_round_ranges=lambda state: _summary_existing_round_ranges(state),
        read_round_group=lambda target_window_id, start, end: _summary_read_round_group(
            target_window_id,
            start,
            end,
        ),
        logger_instance=logger,
    )


def step_run_post_archive_tasks(
    window_id: str,
    round_index: int,
    round_messages: list,
    *,
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
    query_topic_state: Optional[dict] = None,
) -> None:
    """本轮已写入 R2 后执行实时层总结与动态层演化等慢任务。"""
    return _post_archive.step_run_post_archive_tasks(
        window_id,
        round_index,
        round_messages,
        skip_dynamic_memory_write=skip_dynamic_memory_write,
        skip_body_delta=skip_body_delta,
        dynamic_memory_recall_candidate_ids=dynamic_memory_recall_candidate_ids,
        query_topic_state=query_topic_state,
        summary_every_n_rounds=SUMMARY_EVERY_N_ROUNDS,
        summary_groups_to_process=lambda target_window_id, target_round_index, chunks_state: (
            _summary_round_groups_to_process(target_window_id, target_round_index, chunks_state)
        ),
        summary_window_lock=lambda target_window_id: _summary_window_lock(target_window_id),
        summary_round_chunk_id=lambda rounds: _summary_round_chunk_id(rounds),
        with_summary_tool_item_ids=lambda chunks, chunk_id, item_ids: _with_summary_tool_item_ids(
            chunks,
            chunk_id,
            item_ids,
        ),
        summary_prompt_chunk_ids=lambda chunks: _summary_prompt_chunk_ids(chunks),
        summary_generation_base_recent_ids=lambda chunks: _summary_generation_base_recent_ids(chunks),
        summary_prompt_chunk_item_ids=lambda chunks: _summary_prompt_chunk_item_ids(chunks),
        r2_store_module=r2_store,
        deepseek_summary_module=deepseek_summary,
        thread_factory=threading.Thread,
        logger_instance=logger,
        dynamic_layer_evolve=lambda *args, **kwargs: _step_dynamic_layer_evolve(*args, **kwargs),
    )
