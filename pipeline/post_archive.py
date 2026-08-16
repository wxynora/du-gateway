"""Post-archive summary, body-evaluator, and memory-evolution scheduling."""

import copy
import re
import threading
from typing import Callable, Optional

from config import SUMMARY_EVERY_N_ROUNDS as _default_summary_every_n_rounds
from services import deepseek_summary as _default_deepseek_summary
from storage import r2_store as _default_r2_store
from utils.log import get_logger


_default_logger = get_logger("pipeline.pipeline")
_SUMMARY_WINDOW_LOCKS_GUARD = threading.Lock()
_SUMMARY_WINDOW_LOCKS: dict[str, threading.Lock] = {}


def _summary_window_lock(window_id: str) -> threading.Lock:
    normalized_window_id = str(window_id or "")
    with _SUMMARY_WINDOW_LOCKS_GUARD:
        lock = _SUMMARY_WINDOW_LOCKS.get(normalized_window_id)
        if lock is None:
            lock = threading.Lock()
            _SUMMARY_WINDOW_LOCKS[normalized_window_id] = lock
        return lock


def _summary_round_chunk_id(rounds: list[dict]) -> str:
    indices: list[int] = []
    for item in rounds or []:
        if not isinstance(item, dict):
            continue
        try:
            value = int(item.get("index") or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            indices.append(value)
    return f"current:{min(indices)}-{max(indices)}" if indices else ""


def _with_summary_tool_item_ids(chunks_state: dict, chunk_id: str, item_ids: list[str]) -> dict:
    updated = copy.deepcopy(chunks_state)
    for item in updated.get("chunks") or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == str(chunk_id or "").strip():
            item["tool_cache_item_ids"] = [
                str(value).strip()
                for value in item_ids or []
                if str(value or "").strip()
            ]
            break
    return updated


def _summary_existing_round_ranges(chunks_state: dict | None) -> set[tuple[int, int]]:
    chunks = (chunks_state or {}).get("chunks") if isinstance(chunks_state, dict) else []
    if not isinstance(chunks, list):
        return set()
    ranges: set[tuple[int, int]] = set()
    id_re = re.compile(r"^current:(\d+)-(\d+)$")
    for item in chunks:
        if not isinstance(item, dict):
            continue
        raw_start = item.get("round_start")
        raw_end = item.get("round_end")
        if raw_start in (None, "") or raw_end in (None, ""):
            m = id_re.match(str(item.get("id") or "").strip())
            if m:
                raw_start = raw_start or m.group(1)
                raw_end = raw_end or m.group(2)
        try:
            round_start = int(raw_start or 0)
            round_end = int(raw_end or 0)
        except Exception:
            continue
        if round_start > 0 and round_end >= round_start:
            ranges.add((round_start, round_end))
    return ranges


def _summary_read_round_group_impl(
    window_id: str,
    start: int,
    end: int,
    *,
    r2_store_module,
    logger_instance,
) -> list[dict]:
    group: list[dict] = []
    missing = 0
    for idx in range(start, end + 1):
        item = r2_store_module.get_conversation_round_by_index(window_id, idx)
        if not item:
            missing = idx
            break
        group.append(item)
    if missing:
        logger_instance.warning(
            "实时层总结读取轮次失败 window_id=%s range=%s-%s missing=%s，本组跳过",
            window_id,
            start,
            end,
            missing,
        )
        return []
    return group


def _summary_read_round_group(window_id: str, start: int, end: int) -> list[dict]:
    return _summary_read_round_group_impl(
        window_id,
        start,
        end,
        r2_store_module=_default_r2_store,
        logger_instance=_default_logger,
    )


def _summary_round_groups_to_process_impl(
    window_id: str,
    round_index: int,
    chunks_state: dict | None,
    *,
    summary_every_n_rounds: int,
    deepseek_summary_module,
    r2_store_module,
    existing_round_ranges: Callable[[dict | None], set[tuple[int, int]]],
    read_round_group: Callable[[str, int, int], list[dict]],
    logger_instance,
) -> list[list[dict]]:
    try:
        every = max(1, int(summary_every_n_rounds))
    except Exception:
        every = 4
    try:
        current_round = int(round_index or 0)
    except Exception:
        current_round = 0
    if current_round <= 0:
        return []

    current_start = current_round - every + 1
    current_range = (current_start, current_round)
    existing_ranges = existing_round_ranges(chunks_state)
    pending_ranges = deepseek_summary_module.summary_pending_round_ranges(chunks_state)
    if not existing_ranges:
        return [r2_store_module.get_conversation_rounds(window_id, last_n=every)]

    start = min(span_start for span_start, _end in existing_ranges)
    ranges_to_process: list[tuple[int, int]] = []
    while start + every - 1 <= current_round:
        end = start + every - 1
        span = (start, end)
        if span not in existing_ranges:
            ranges_to_process.append(span)
        start = end + 1

    for span in sorted(pending_ranges):
        if span[1] <= current_round and span not in ranges_to_process:
            ranges_to_process.append(span)

    if current_range not in ranges_to_process and current_range not in existing_ranges:
        ranges_to_process.append(current_range)

    deduped_ranges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for span in ranges_to_process:
        if span in seen:
            continue
        seen.add(span)
        deduped_ranges.append(span)

    if len(deduped_ranges) > 1:
        logger_instance.warning(
            "实时层总结检测到断层，本轮补缺口并继续最新组 window_id=%s ranges=%s current_round=%s",
            window_id,
            deduped_ranges,
            current_round,
        )
    return [
        group
        for start, end in deduped_ranges
        if (group := read_round_group(window_id, start, end))
    ]


def _summary_round_groups_to_process(
    window_id: str,
    round_index: int,
    chunks_state: dict | None,
) -> list[list[dict]]:
    return _summary_round_groups_to_process_impl(
        window_id,
        round_index,
        chunks_state,
        summary_every_n_rounds=_default_summary_every_n_rounds,
        deepseek_summary_module=_default_deepseek_summary,
        r2_store_module=_default_r2_store,
        existing_round_ranges=_summary_existing_round_ranges,
        read_round_group=_summary_read_round_group,
        logger_instance=_default_logger,
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
    summary_every_n_rounds: int,
    summary_groups_to_process: Callable[[str, int, dict | None], list[list[dict]]],
    summary_window_lock: Callable[[str], threading.Lock],
    summary_round_chunk_id: Callable[[list[dict]], str],
    with_summary_tool_item_ids: Callable[[dict, str, list[str]], dict],
    summary_prompt_chunk_ids: Callable[[dict], tuple[list[str], list[str]]],
    summary_generation_base_recent_ids: Callable[[dict], list[str]],
    summary_prompt_chunk_item_ids: Callable[[dict], dict[str, list[str]]],
    r2_store_module,
    deepseek_summary_module,
    thread_factory,
    logger_instance,
    dynamic_layer_evolve: Callable[..., Optional[dict]],
) -> None:
    """本轮已写入 R2 后执行实时层总结与动态层演化等慢任务。"""
    if round_index % summary_every_n_rounds == 0:
        logger_instance.info("实时层总结已调度 window_id=%s round_index=%s", window_id, round_index)

        def _run_summary_job():
            from services.deepseek_summary import fetch_new_summary_update
            from services.tool_result_cache import (
                sync_prompt_generation_after_summary,
                tool_cache_item_ids_for_rounds,
                wait_for_game_tool_loop_summaries,
            )

            def _sync_tool_prompt(chunks: dict) -> bool:
                generation = chunks.get("generation") if isinstance(chunks.get("generation"), dict) else {}
                generation_id = int(generation.get("id") or 0)
                _recent_ids, generation_chunk_ids = summary_prompt_chunk_ids(chunks)
                return sync_prompt_generation_after_summary(
                    window_id=window_id,
                    generation_id=generation_id,
                    generation_chunk_ids=generation_chunk_ids,
                    previous_generation_chunk_ids=summary_generation_base_recent_ids(chunks),
                    generation_chunk_item_ids=summary_prompt_chunk_item_ids(chunks),
                )

            current = r2_store_module.get_summary(window_id) or ""
            chunks_state = r2_store_module.get_summary_chunks(window_id)
            groups = summary_groups_to_process(window_id, round_index, chunks_state)
            for recent in groups:
                if not recent:
                    continue
                wait_for_game_tool_loop_summaries(recent, window_id=window_id)
                completed_chunk_id = summary_round_chunk_id(recent)
                tool_item_ids = tool_cache_item_ids_for_rounds(recent, window_id=window_id)
                new_summary, new_chunks = fetch_new_summary_update(
                    current,
                    recent,
                    chunks_state,
                    window_id=window_id,
                )
                if new_summary and new_chunks:
                    new_chunks = with_summary_tool_item_ids(
                        new_chunks,
                        completed_chunk_id,
                        tool_item_ids,
                    )
                    if r2_store_module.save_summary(window_id, new_summary):
                        if not r2_store_module.save_summary_chunks(window_id, new_chunks):
                            logger_instance.warning("Pipeline 保存实时层小段队列失败 window_id=%s", window_id)
                            break
                        current = new_summary
                        chunks_state = new_chunks
                        if not _sync_tool_prompt(new_chunks):
                            logger_instance.warning("Pipeline 工具摘要四轮封包失败 window_id=%s", window_id)
                            break
                        continue
                indices = [r.get("index") for r in recent if isinstance(r, dict)]
                logger_instance.warning(
                    "Pipeline 本窗口触发总结但 DeepSeek 未返回新总结 window_id=%s indices=%s，准备写入 pending 兜底",
                    window_id,
                    indices,
                )
                fallback_summary, fallback_chunks = deepseek_summary_module.build_pending_summary_update(
                    current,
                    recent,
                    chunks_state,
                    window_id=window_id,
                )
                if fallback_chunks is not None and fallback_summary is not None:
                    if r2_store_module.save_summary(window_id, fallback_summary):
                        if not r2_store_module.save_summary_chunks(window_id, fallback_chunks):
                            logger_instance.warning(
                                "Pipeline 保存实时层 pending 小段队列失败 window_id=%s",
                                window_id,
                            )
                            break
                        current = fallback_summary
                        chunks_state = fallback_chunks
                        logger_instance.warning(
                            "Pipeline 已写入实时层 pending 小段兜底 window_id=%s indices=%s",
                            window_id,
                            indices,
                        )
                        break
                    logger_instance.warning(
                        "Pipeline 保存实时层 pending 总结失败 window_id=%s indices=%s",
                        window_id,
                        indices,
                    )
                continue

        def _summarize():
            with summary_window_lock(window_id):
                _run_summary_job()

        t = thread_factory(
            target=_summarize,
            name=f"summary-window-{window_id}-{round_index}",
            daemon=False,
        )
        t.start()
    if skip_body_delta:
        logger_instance.info("身体状态 evaluator 跳过 window_id=%s round_index=%s", window_id, round_index)
    else:
        try:
            from services.du_body_evaluator import enqueue_archived_round

            queued = enqueue_archived_round(window_id, round_index, round_messages)
            logger_instance.info(
                "身体状态 evaluator 登记 window_id=%s round_index=%s queued=%s reason=%s",
                window_id,
                round_index,
                bool(queued.get("queued")),
                queued.get("reason") or "",
            )
        except Exception:
            logger_instance.warning(
                "身体状态 evaluator 登记失败 window_id=%s round_index=%s",
                window_id,
                round_index,
                exc_info=True,
            )
    if skip_dynamic_memory_write:
        logger_instance.info(
            "动态层跳过：请求要求跳过动态记忆写入 window_id=%s round_index=%s",
            window_id,
            round_index,
        )
        return None
    dynamic_layer_evolve(
        window_id,
        round_index,
        round_messages,
        skip_dynamic_memory_write=skip_dynamic_memory_write,
        skip_body_delta=skip_body_delta,
        dynamic_memory_recall_candidate_ids=dynamic_memory_recall_candidate_ids,
        query_topic_state=query_topic_state,
    )
