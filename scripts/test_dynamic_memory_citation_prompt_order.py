import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from services.dynamic_memory_citation import DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY


def run() -> None:
    memories = [
        {
            "id": "memory-a",
            "content": "第一条召回记忆",
            "created_at": "2026-07-28T10:00:00+08:00",
        },
        {
            "id": "memory-b",
            "content": "第二条召回记忆",
            "created_at": "2026-07-29T15:00:00+08:00",
        },
    ]
    cached = {"results": [dict(item) for item in memories], "source": "hybrid"}
    body = {"messages": [{"role": "user", "content": "继续聊之前那件重要的事"}]}

    with (
        patch.object(pipeline.r2_store, "get_dynamic_memory_list", return_value=memories),
        patch.object(pipeline.r2_store, "get_core_cache_pending", return_value=[]),
        patch.object(pipeline, "_core_protected_dynamic_memory_ids", return_value=set()),
        patch.object(pipeline, "_should_prune_dynamic_memory", return_value=False),
        patch.object(pipeline, "_is_memory_meta_query", return_value=False),
        patch.object(pipeline, "_is_trivial_user_message", return_value=False),
        patch.object(
            pipeline,
            "_extract_keyword_candidates",
            return_value=[{"text": "重要的事", "is_phrase": True}],
        ),
        patch.object(pipeline, "_build_retrieval_text", return_value="继续聊之前那件重要的事"),
        patch.object(pipeline, "_recall_cache_hit", return_value=cached),
        patch.object(
            pipeline,
            "_memory_recall_sort_score",
            side_effect=lambda item: 2.0 if item.get("id") == "memory-a" else 1.0,
        ),
        patch.object(pipeline, "_memory_weight", return_value=1.0),
        patch.object(pipeline, "memory_dynamic_budget", return_value=10_000),
        patch.object(pipeline, "estimate_tokens", return_value=1),
        patch.object(pipeline, "_append_dynamic_recall_debug_event_safe"),
        patch.object(pipeline, "_build_sqlite_shadow_compare", return_value={"enabled": False}),
    ):
        result = pipeline.step_inject_dynamic_memory(body, "citation-order-test")

    system_text = "\n".join(
        str(message.get("content") or "")
        for message in result.get("messages") or []
        if str(message.get("role") or "").lower() == "system"
    )
    rule = "如果回复实际参考了某条记忆，请在相关句尾写对应标记（如 [memory 1]）；"
    first_pos = system_text.index("第一条召回记忆")
    second_pos = system_text.index("第二条召回记忆")
    closing_pos = system_text.index("【以上为可召回记忆】")
    rule_pos = system_text.index(rule)

    assert first_pos < second_pos < closing_pos < rule_pos, system_text
    assert system_text.count(rule) == 1, system_text
    assert result[DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY] == {
        "1": "memory-a",
        "2": "memory-b",
    }


if __name__ == "__main__":
    run()
