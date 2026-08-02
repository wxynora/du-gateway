#!/usr/bin/env python3
"""定向回归：动态层不再用无关候选、语义降级或本地模板兜底。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_vector import dynamic_vector_retriever
from pipeline import pipeline
from services import dynamic_layer_ds


def _decision_text(
    *,
    action: str,
    content: str,
    tag: str = "客厅",
    fused_with_id: str = "",
    merge_reason: str = "",
) -> str:
    return "\n".join(
        (
            f"ACTION: {action}",
            "IMPORTANCE: 2",
            f"TAG: {tag}",
            "EMOTION: neutral",
            "SCENE: casual_chat",
            "TARGET: our_relationship",
            f"FUSED_WITH_ID: {fused_with_id}",
            f"MERGE_REASON: {merge_reason}",
            f"CONTENT: {content}",
        )
    )


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


def _call_single_with(
    *,
    round_messages: list[dict],
    current_memories: list[dict],
    retrieval_result=None,
    retrieval_error: Exception | None = None,
    responses: list[str],
) -> tuple[dict, list[dict]]:
    captured_payloads: list[dict] = []
    queued = list(responses)
    original_key = dynamic_layer_ds.DEEPSEEK_API_KEY
    original_url = dynamic_layer_ds.DEEPSEEK_API_URL
    original_post = dynamic_layer_ds.requests.post
    original_retrieve = dynamic_vector_retriever.dynamic_vector_retrieve
    original_audit = dynamic_layer_ds._emit_dynamic_ds_audit_event
    try:
        dynamic_layer_ds.DEEPSEEK_API_KEY = "test-key"
        dynamic_layer_ds.DEEPSEEK_API_URL = "https://example.invalid/deepseek"
        dynamic_layer_ds._emit_dynamic_ds_audit_event = lambda _event: None

        def fake_retrieve(*_args, **_kwargs):
            if retrieval_error is not None:
                raise retrieval_error
            return retrieval_result

        def fake_post(_url, *, headers, json, timeout):
            _ = headers, timeout
            captured_payloads.append(json)
            assert queued, "unexpected extra DeepSeek retry"
            return _FakeResponse(queued.pop(0))

        dynamic_vector_retriever.dynamic_vector_retrieve = fake_retrieve
        dynamic_layer_ds.requests.post = fake_post
        result = dynamic_layer_ds.call_dynamic_layer_ds(
            round_messages,
            current_memories,
            window_id="test-window",
            round_index=1,
        )
    finally:
        dynamic_layer_ds.DEEPSEEK_API_KEY = original_key
        dynamic_layer_ds.DEEPSEEK_API_URL = original_url
        dynamic_layer_ds.requests.post = original_post
        dynamic_vector_retriever.dynamic_vector_retrieve = original_retrieve
        dynamic_layer_ds._emit_dynamic_ds_audit_event = original_audit
    return result, captured_payloads


def test_empty_or_failed_retrieval_never_falls_back_to_recent_memories() -> None:
    round_messages = [{"role": "user", "content": "老婆今天说想换一个新的杯子，我觉得挺可爱。"}]
    current_memories = [
        {
            "id": f"old-{index}",
            "content": f"绝不能作为无关候选出现-{index}",
            "importance": 2,
            "tag": "客厅",
        }
        for index in range(12)
    ]
    response = _decision_text(action="new", content="老婆想换一个新杯子，我觉得这个小念头很可爱。")

    for retrieval_result, retrieval_error in (([], None), (None, RuntimeError("embedding unavailable"))):
        result, payloads = _call_single_with(
            round_messages=round_messages,
            current_memories=current_memories,
            retrieval_result=retrieval_result,
            retrieval_error=retrieval_error,
            responses=[response],
        )
        prompt = payloads[0]["messages"][0]["content"]
        assert result["action"] == "new"
        assert "当前没有可用的旧记忆候选" in prompt
        assert "绝不能作为无关候选出现" not in prompt


def test_merge_requires_resolvable_ref_and_never_downgrades_to_new() -> None:
    round_messages = [{"role": "user", "content": "老婆补充了同一只杯子的颜色，我把细节记完整。"}]
    candidate = {
        "id": "memory-1",
        "content": "老婆想换一只新杯子，我觉得挺可爱。",
        "importance": 2,
        "tag": "客厅",
    }
    invalid = _decision_text(
        action="merge",
        content="老婆补充想要浅蓝色的杯子，我把这件事和原来的念头合在一起。",
        fused_with_id="M99",
        merge_reason="consolidate",
    )
    valid = _decision_text(
        action="merge",
        content="老婆想换一只浅蓝色的新杯子，我觉得这个小念头很可爱。",
        fused_with_id="M01",
        merge_reason="consolidate",
    )
    result, payloads = _call_single_with(
        round_messages=round_messages,
        current_memories=[candidate],
        retrieval_result=[candidate],
        responses=[invalid, valid],
    )
    assert len(payloads) == 2
    assert "无法对应当前记忆列表里的任何 ref" in payloads[1]["messages"][0]["content"]
    assert result["action"] == "merge"
    assert result["fused_with_id"] == "memory-1"

    result, payloads = _call_single_with(
        round_messages=round_messages,
        current_memories=[candidate],
        retrieval_result=[candidate],
        responses=[invalid] * dynamic_layer_ds._DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS,
    )
    assert len(payloads) == dynamic_layer_ds._DYNAMIC_LAYER_CONTENT_MAX_ATTEMPTS
    assert result["action"] == "skip"
    assert result["fused_with_id"] is None


def test_raw_copy_and_invalid_tag_are_retried_by_ds() -> None:
    source = "老婆今天认真说想把窗边的杯子换成浅蓝色，我听完觉得这个念头很可爱。"
    rewritten = "老婆想把窗边的杯子换成浅蓝色，我觉得这个认真挑颜色的小念头很可爱。"
    raw_copy = _decision_text(action="new", content=source)
    valid = _decision_text(action="new", content=rewritten)
    result, payloads = _call_single_with(
        round_messages=[{"role": "user", "content": source}],
        current_memories=[],
        retrieval_result=[],
        responses=[raw_copy, valid],
    )
    assert len(payloads) == 2
    assert "CONTENT 照抄了本轮原话" in payloads[1]["messages"][0]["content"]
    assert result["content"] == rewritten

    invalid_tag = _decision_text(action="new", content=rewritten, tag="厨房")
    result, payloads = _call_single_with(
        round_messages=[{"role": "user", "content": source}],
        current_memories=[],
        retrieval_result=[],
        responses=[invalid_tag, valid],
    )
    assert len(payloads) == 2
    assert "TAG 缺失或不在允许值中" in payloads[1]["messages"][0]["content"]
    assert result["tag"] == "客厅"

    batch_obj = {
        "action": "new",
        "importance": 2,
        "tag": "客厅",
        "content": source,
        "emotion_label": "neutral",
        "scene_type": "casual_chat",
        "target_type": "our_relationship",
    }
    issues = dynamic_layer_ds._batch_structural_issues(
        [batch_obj],
        1,
        [{"messages": [{"role": "user", "content": source}]}],
    )
    assert issues[0]["issue"] == "content_raw_copy"


def test_gateway_does_not_force_bedroom_tag_from_keywords() -> None:
    current_memories: list[dict] = []
    saved: list[list[dict]] = []
    original_promote = pipeline.r2_store.promote_to_core_cache
    original_save = pipeline.r2_store.save_dynamic_memory_list
    original_index = pipeline._upsert_dynamic_memory_index

    from services import dynamic_memory_provenance, portrait_memory

    original_provenance = dynamic_memory_provenance.record_event
    original_portrait = portrait_memory.sync_portrait_candidate_from_memory
    try:
        pipeline.r2_store.promote_to_core_cache = lambda *_args, **_kwargs: set()

        def fake_save(items):
            saved.append([dict(item) for item in items])
            return True

        pipeline.r2_store.save_dynamic_memory_list = fake_save
        pipeline._upsert_dynamic_memory_index = lambda _memory: None
        dynamic_memory_provenance.record_event = lambda **_kwargs: None
        portrait_memory.sync_portrait_candidate_from_memory = lambda _memory: None

        result = pipeline._apply_one_decision(
            "test-window",
            1,
            [{"role": "user", "content": "我们只是在讨论“亲密”这个词怎么分类，并没有卧室事件。"}],
            {
                "action": "new",
                "importance": 2,
                "tag": "客厅",
                "content": "老婆和我讨论了“亲密”这个词的分类边界，我把这个技术语境记清楚了。",
                "emotion_label": "neutral",
                "scene_type": "problem_solving",
                "target_type": "our_project",
            },
            current_memories,
        )
    finally:
        pipeline.r2_store.promote_to_core_cache = original_promote
        pipeline.r2_store.save_dynamic_memory_list = original_save
        pipeline._upsert_dynamic_memory_index = original_index
        dynamic_memory_provenance.record_event = original_provenance
        portrait_memory.sync_portrait_candidate_from_memory = original_portrait

    assert result is not None
    assert result["tag"] == "客厅"
    assert saved and saved[-1][0]["tag"] == "客厅"


def main() -> None:
    test_empty_or_failed_retrieval_never_falls_back_to_recent_memories()
    test_merge_requires_resolvable_ref_and_never_downgrades_to_new()
    test_raw_copy_and_invalid_tag_are_retried_by_ds()
    test_gateway_does_not_force_bedroom_tag_from_keywords()
    print("dynamic layer overdefense removal checks passed")


if __name__ == "__main__":
    main()
