#!/usr/bin/env python3
"""Pure-local regression checks for dynamic-memory pruning boundaries."""

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

import pipeline.pipeline as pipeline  # noqa: E402


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def _memory(*, memory_id: str = "memory-1", days: int, importance: int, mention_count: int = 0, tag: str = "客厅") -> dict:
    return {
        "id": memory_id,
        "tag": tag,
        "importance": importance,
        "mention_count": mention_count,
        "last_mentioned": (NOW - timedelta(days=days)).isoformat(),
    }


def test_time_decay_boundaries() -> None:
    _assert(pipeline._memory_weight(_memory(days=15, importance=3), NOW) == 3.0, "day 15 must have no decay")
    _assert(pipeline._memory_weight(_memory(days=16, importance=3), NOW) == 2.9, "day 16 must decay by 0.1")
    _assert(pipeline._memory_weight(_memory(days=35, importance=4), NOW) == 2.0, "time decay must cap at 2")
    _assert(pipeline._memory_weight(_memory(days=120, importance=4), NOW) == 2.0, "time decay must stay capped at 2")


def test_library_is_never_pruned() -> None:
    memory = _memory(days=120, importance=1, tag="图书馆")
    _assert(not pipeline._is_marginal_dynamic_memory_for_prune(memory, NOW), "library memory must be exempt from pruning")


def test_ordinary_prune_requires_age_and_low_weight() -> None:
    _assert(
        not pipeline._is_marginal_dynamic_memory_for_prune(_memory(days=14, importance=1), NOW),
        "memory younger than 15 days must not be pruned",
    )
    _assert(
        pipeline._is_marginal_dynamic_memory_for_prune(_memory(days=15, importance=2), NOW),
        "15-day-old memory with weight 2 must be pruned",
    )
    _assert(
        not pipeline._is_marginal_dynamic_memory_for_prune(_memory(days=16, importance=3), NOW),
        "weight above 2 must not be pruned",
    )


def test_bedroom_is_physically_pruned_after_three_days() -> None:
    _assert(
        not pipeline._is_marginal_dynamic_memory_for_prune(
            _memory(days=2, importance=4, tag="卧室"),
            NOW,
        ),
        "bedroom memory must remain before day 3",
    )
    _assert(
        pipeline._is_marginal_dynamic_memory_for_prune(
            _memory(days=3, importance=4, tag="卧室"),
            NOW,
        ),
        "bedroom memory must be physically pruned at day 3 regardless of weight",
    )


def test_core_cache_protects_source_memory() -> None:
    protected_ids = pipeline._core_protected_dynamic_memory_ids(
        [
            {"id": "imp-window-round", "source_memory_id": "important-source", "promoted_by": "importance"},
            {"id": "mention-source", "promoted_by": "mention_count"},
        ]
    )
    _assert("important-source" in protected_ids, "importance promotion must protect source_memory_id")
    _assert("mention-source" in protected_ids, "legacy same-id core memory must stay protected")
    _assert(
        not pipeline._should_prune_dynamic_memory(
            _memory(memory_id="important-source", days=120, importance=1), NOW, protected_ids
        ),
        "core source memory must not be pruned",
    )
    _assert(
        not pipeline._should_prune_dynamic_memory(
            _memory(memory_id="important-source", days=120, importance=1, tag="卧室"),
            NOW,
            protected_ids,
        ),
        "core-protected bedroom memory must not be pruned by the three-day rule",
    )


if __name__ == "__main__":
    original_enabled = pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED
    original_min_days = pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS
    original_max_weight = pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT
    try:
        pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED = True
        pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS = 15
        pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT = 2
        test_time_decay_boundaries()
        test_library_is_never_pruned()
        test_ordinary_prune_requires_age_and_low_weight()
        test_bedroom_is_physically_pruned_after_three_days()
        test_core_cache_protects_source_memory()
    finally:
        pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED = original_enabled
        pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS = original_min_days
        pipeline.DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT = original_max_weight
    print("dynamic memory prune checks passed")
