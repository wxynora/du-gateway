#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from utils.time_aware import _now_beijing


def main() -> None:
    now = _now_beijing()
    old_at = (now - timedelta(days=30)).isoformat()
    ordinary = {
        "id": "ordinary-old-but-retained",
        "content": "那次一起旅行的细节",
        "tag": "客厅",
        "importance": 5,
        "mention_count": 0,
        "created_at": old_at,
        "last_mentioned": old_at,
    }
    protected_bedroom = {
        "id": "bedroom-old-but-protected",
        "content": "仍受核心候选保护的亲密记忆",
        "tag": "卧室",
        "importance": 1,
        "mention_count": 0,
        "created_at": old_at,
        "last_mentioned": old_at,
    }
    core_pending = [{"id": "core-candidate", "source_memory_id": protected_bedroom["id"]}]

    protected_ids = pipeline._core_protected_dynamic_memory_ids(core_pending)
    assert not pipeline._should_prune_dynamic_memory(ordinary, now, protected_ids)
    assert not pipeline._should_prune_dynamic_memory(protected_bedroom, now, protected_ids)

    seen: dict[str, list[str]] = {}

    def fake_bm25(_query: str, _terms: list[dict], memories: list[dict]) -> dict:
        seen["bm25"] = [str(item.get("id") or "") for item in memories]
        return {}

    def fake_merge(vector_memories: list[dict], _bm25: dict) -> list[dict]:
        seen["vector"] = [str(item.get("id") or "") for item in vector_memories]
        return []

    with (
        patch.object(pipeline.r2_store, "get_dynamic_memory_list", return_value=[ordinary, protected_bedroom]),
        patch.object(pipeline.r2_store, "get_core_cache_pending", return_value=core_pending),
        patch.object(pipeline, "_is_memory_meta_query", return_value=False),
        patch.object(pipeline, "_is_trivial_user_message", return_value=False),
        patch.object(pipeline, "_extract_keyword_candidates", return_value=[{"text": "旅行", "is_phrase": False}]),
        patch.object(pipeline, "_build_retrieval_text", return_value="旅行"),
        patch.object(pipeline, "_last_4_turns_text_for_rewrite", return_value=""),
        patch.object(pipeline, "_rewrite_memory_queries_with_ds", return_value=[]),
        patch.object(
            pipeline,
            "_multi_query_recall_and_rerank",
            return_value=[dict(ordinary), dict(protected_bedroom)],
        ),
        patch.object(pipeline, "_bm25_recall_scores", side_effect=fake_bm25),
        patch.object(pipeline, "_merge_vector_and_bm25_recall", side_effect=fake_merge),
        patch.object(
            pipeline,
            "_apply_external_dynamic_memory_rerank",
            side_effect=lambda recalled, *_args: (recalled, "hybrid", {"enabled": False}),
        ),
        patch.object(pipeline, "_append_dynamic_recall_debug_event_safe", return_value=None),
    ):
        pipeline.step_inject_dynamic_memory(
            {"messages": [{"role": "user", "content": "还记得那次旅行吗"}]},
            "recall-lifetime-test",
            use_recall_cache=False,
        )

    expected = {ordinary["id"], protected_bedroom["id"]}
    assert set(seen.get("bm25") or []) == expected, seen
    assert set(seen.get("vector") or []) == expected, seen
    print("PASS every retained dynamic memory participates in recall")


if __name__ == "__main__":
    main()
