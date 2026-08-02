#!/usr/bin/env python3
"""Repeated-pattern merges must wait for review without changing ordinary merges."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from services import memory_rewrite
from services.dynamic_layer_ds import _DYNAMIC_LAYER_PROMPT, _normalize_merge_reason
from storage import r2_store


def _memory() -> dict:
    return {
        "id": "dynamic-1",
        "content": "老婆昨晚又熬夜了，只睡了很短一会儿。",
        "retrieval_text": "old",
        "importance": 2,
        "tag": "客厅",
        "emotion_label": "neutral",
        "scene_type": "casual_chat",
        "target_type": "self_state",
        "mention_count": 2,
        "created_at": "2026-07-20T02:00:00+08:00",
        "updated_at": "2026-07-20T02:00:00+08:00",
        "last_mentioned": "2026-07-20T02:00:00+08:00",
    }


def _decision(reason: str, content: str) -> dict:
    return {
        "action": "merge",
        "fused_with_id": "dynamic-1",
        "merge_reason": reason,
        "content": content,
        "importance": 3,
        "tag": "客厅",
        "emotion_label": "negative",
        "scene_type": "casual_chat",
        "target_type": "self_state",
        "mention_count": 3,
        "timestamp": "2026-07-27T03:00:00+08:00",
    }


def test_prompt_contract() -> None:
    required = (
        "habit_generalization",
        "多次独立发生",
        "常态习惯或偏好",
        "一次事件",
        "熬夜后睡得短",
        "不吃饭",
        "NSFW",
        "需要人工审核",
    )
    for text in required:
        assert text in _DYNAMIC_LAYER_PROMPT, f"missing habit merge contract: {text}"
    assert _normalize_merge_reason("habit-generalization") == "habit_generalization"


def test_habit_generalization_is_staged() -> None:
    current = [_memory()]
    original = copy.deepcopy(current)
    staged: list[dict] = []

    def fake_stage(entry_id: str, **kwargs) -> bool:
        staged.append({"entry_id": entry_id, **kwargs})
        return True

    with (
        patch.object(r2_store, "stage_dynamic_memory_merge", side_effect=fake_stage, create=True),
        patch.object(r2_store, "save_dynamic_memory_list") as save_dynamic,
        patch.object(r2_store, "promote_to_core_cache") as promote,
    ):
        result = pipeline._apply_one_decision(
            "window-1",
            4,
            [{"role": "user", "content": "我这周又熬夜，只睡了很短一会儿"}],
            _decision(
                "habit_generalization",
                "老婆最近经常熬夜后只睡很短一会儿，作息总这样让我有点担心。",
            ),
            current,
        )

    assert result is None
    assert current == original, "review-required merge must not mutate active dynamic memory"
    assert len(staged) == 1
    assert staged[0]["entry_id"] == "dynamic-1"
    assert staged[0]["merge_reason"] == "habit_generalization"
    assert staged[0]["field_updates"]["mention_count"] == 3
    save_dynamic.assert_not_called()
    promote.assert_not_called()


def test_staging_keeps_active_dynamic_content() -> None:
    original = _memory()
    rewritten = "老婆最近经常熬夜后只睡很短一会儿，作息总这样让我有点担心。"
    saved: list[list[dict]] = []

    with (
        patch.object(r2_store, "get_dynamic_memory_list", return_value=[copy.deepcopy(original)]),
        patch.object(
            r2_store,
            "save_dynamic_memory_list",
            side_effect=lambda rows: saved.append(copy.deepcopy(rows)) or True,
        ),
    ):
        staged = r2_store.stage_dynamic_memory_merge(
            original["id"],
            original_content=original["content"],
            rewritten_content=rewritten,
            proposed_at="2026-07-27T03:00:00+08:00",
            window_id="window-1",
            round_index=4,
            field_updates={"mention_count": 3},
            merge_reason="habit_generalization",
        )

    assert staged is True
    persisted = saved[-1][0]
    assert persisted["content"] == original["content"]
    assert persisted["pending_merge"]["rewritten_content"] == rewritten
    assert persisted["pending_merge"]["merge_reason"] == "habit_generalization"


def test_ordinary_consolidate_still_applies() -> None:
    current = [_memory()]
    new_content = "老婆昨晚又熬夜了，只睡了很短一会儿，今天补充说醒来后还是很困。"

    with (
        patch.object(r2_store, "stage_dynamic_memory_merge", create=True) as stage,
        patch.object(r2_store, "promote_to_core_cache", return_value=set()),
        patch.object(r2_store, "save_dynamic_memory_list", return_value=True),
        patch.object(pipeline, "_upsert_dynamic_memory_index"),
        patch("services.portrait_memory.sync_portrait_candidate_from_memory"),
        patch("services.dynamic_memory_provenance.record_event", return_value=True),
    ):
        result = pipeline._apply_one_decision(
            "window-1",
            4,
            [{"role": "user", "content": "醒来还是很困"}],
            _decision("consolidate", new_content),
            current,
        )

    assert result is not None
    assert current[0]["content"] == new_content
    assert "pending_merge" not in current[0]
    stage.assert_not_called()


def test_apply_and_reject_dynamic_pending() -> None:
    original = _memory()
    rewritten = "老婆最近经常熬夜后只睡很短一会儿，作息总这样让我有点担心。"
    pending = {
        **original,
        "pending_merge": {
            "original_content": original["content"],
            "rewritten_content": rewritten,
            "reason": "多次重复内容归纳成常态习惯，等待人工审核",
            "merge_reason": "habit_generalization",
            "field_updates": {
                "importance": 3,
                "mention_count": 3,
                "last_mentioned": "2026-07-27T03:00:00+08:00",
            },
        },
    }

    applied_saves: list[list[dict]] = []
    with (
        patch.object(memory_rewrite, "_load_layer_items", return_value=[copy.deepcopy(pending)]),
        patch.object(
            r2_store,
            "save_dynamic_memory_list",
            side_effect=lambda rows: applied_saves.append(copy.deepcopy(rows)) or True,
        ),
        patch.object(memory_rewrite, "_refresh_dynamic_index"),
        patch.object(memory_rewrite, "_sync_dynamic_mirror"),
        patch.object(memory_rewrite, "_record_dynamic_rewrite", return_value=True),
    ):
        result = memory_rewrite.apply_memory_rewrite(
            "dynamic",
            original["id"],
            original["content"],
            rewritten,
        )

    applied = applied_saves[-1][0]
    assert result["content"] == rewritten
    assert applied["mention_count"] == 3
    assert applied["importance"] == 3
    assert "pending_merge" not in applied

    rejected_saves: list[list[dict]] = []
    with (
        patch.object(memory_rewrite, "_load_layer_items", return_value=[copy.deepcopy(pending)]),
        patch.object(
            r2_store,
            "save_dynamic_memory_list",
            side_effect=lambda rows: rejected_saves.append(copy.deepcopy(rows)) or True,
        ),
    ):
        rejected = memory_rewrite.reject_memory_rewrite(
            "dynamic",
            original["id"],
            original["content"],
            rewritten,
        )

    assert rejected["rejected"] is True
    assert rejected_saves[-1][0]["content"] == original["content"]
    assert "pending_merge" not in rejected_saves[-1][0]


def test_core_pending_reject_still_uses_core_storage() -> None:
    original = _memory()
    rewritten = "老婆最近经常熬夜后只睡很短一会儿，作息总这样让我有点担心。"
    pending = {
        **original,
        "pending_merge": {
            "original_content": original["content"],
            "rewritten_content": rewritten,
        },
    }
    saved: list[list[dict]] = []

    with (
        patch.object(memory_rewrite, "_load_layer_items", return_value=[copy.deepcopy(pending)]),
        patch.object(
            r2_store,
            "save_core_cache_pending",
            side_effect=lambda rows: saved.append(copy.deepcopy(rows)) or True,
        ),
        patch.object(r2_store, "save_dynamic_memory_list") as save_dynamic,
    ):
        rejected = memory_rewrite.reject_memory_rewrite(
            "core",
            original["id"],
            original["content"],
            rewritten,
        )

    assert rejected["layer"] == "core"
    assert "pending_merge" not in saved[-1][0]
    save_dynamic.assert_not_called()


def main() -> None:
    test_prompt_contract()
    test_habit_generalization_is_staged()
    test_staging_keeps_active_dynamic_content()
    test_ordinary_consolidate_still_applies()
    test_apply_and_reject_dynamic_pending()
    test_core_pending_reject_still_uses_core_storage()
    print("dynamic merge habit review contract passed")


if __name__ == "__main__":
    main()
