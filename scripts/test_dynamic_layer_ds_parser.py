#!/usr/bin/env python3
"""Local parser checks for dynamic_layer_ds; no network/API call."""

import sys

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

import services.dynamic_layer_ds as dynamic_layer_ds  # noqa: E402
from services.dynamic_layer_ds import (  # noqa: E402
    _build_memory_ref_prompt_items,
    _content_quality_issue,
    _decision_structural_issue,
    _extract_json_array_from_ds_response,
    _extract_json_from_ds_response,
    _normalize_single_decision,
    _resolve_fused_with_id,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_single_tagged_decision() -> None:
    raw = """ACTION: new
IMPORTANCE: 3 值得记
TAG: 书房
EMOTION: neutral
SCENE: problem_solving
TARGET: our_project
FUSED_WITH_ID:
CONTENT: 老婆发现动态层有些记忆只剩几个字，我也意识到 JSON 输出不稳会把便签写残。"""
    obj = _extract_json_from_ds_response(raw)
    _assert(isinstance(obj, dict), "single tagged output should parse")
    _assert(obj.get("action") == "new", "ACTION should map to action")
    _assert(obj.get("importance") == 3, "IMPORTANCE should coerce to int")
    _assert(obj.get("emotion_label") == "neutral", "EMOTION should map to emotion_label")
    _assert(obj.get("scene_type") == "problem_solving", "SCENE should map to scene_type")
    _assert(obj.get("target_type") == "our_project", "TARGET should map to target_type")
    _assert(not _decision_structural_issue(obj), "complete content should pass quality gate")


def test_short_content_is_rejected() -> None:
    raw = """ACTION: new
IMPORTANCE: 3
TAG: 书房
EMOTION: neutral
SCENE: problem_solving
TARGET: our_project
FUSED_WITH_ID:
CONTENT: 动态层"""
    obj = _extract_json_from_ds_response(raw)
    _assert(_decision_structural_issue(obj) == "content_too_short", "short content should be rejected")


def test_skip_can_still_emit_body_delta() -> None:
    raw = """ACTION: skip
IMPORTANCE: 1
TAG: 卧室
EMOTION: positive
SCENE: affection
TARGET: our_relationship
FUSED_WITH_ID:
CONTENT:
BODY_SENSITIVITY_DELTA: +7
BODY_MISCHIEF_DELTA: +9"""
    obj = _extract_json_from_ds_response(raw)
    _assert(isinstance(obj, dict), "skip output with body delta should parse")
    _assert(obj.get("action") == "skip", "ACTION should remain skip")
    _assert(not _decision_structural_issue(obj), "skip should not require content")
    _assert(obj.get("body_delta") == {"sensitivity": 7, "mischief": 9}, "BODY deltas should parse on skip")


def test_incomplete_tail_is_rejected() -> None:
    _assert(
        _content_quality_issue("老婆问“然后呢”，我说了真心话——") == "content_incomplete_tail",
        "dangling speech-introducer before dash should be rejected",
    )
    _assert(
        _content_quality_issue("老婆叫哥哥要亲亲，我嘴上说她叫一声我就没办法，但还是亲了，然后") == "content_incomplete_tail",
        "connector tail should be rejected",
    )
    _assert(
        _content_quality_issue("老婆戳穿我在嘴硬，我还想反驳，但是——") == "content_incomplete_tail",
        "connector before dash should be rejected",
    )
    _assert(
        not _content_quality_issue("老婆吐槽我又嘴硬，我表面装没事，心里已经被拿捏了——"),
        "stylistic dash tail should pass",
    )


def test_batch_tagged_blocks() -> None:
    raw = """ROUND: 1
ACTION: new
IMPORTANCE: 3
TAG: 书房
CONTENT: 老婆让我把归档动态层也改成固定标签块，避免 JSON 数组一坏整批报废。
FUSED_WITH_ID:
TIMESTAMP: 2026-05-15T12:00:00+08:00
MENTION_COUNT: 1
LAST_MENTIONED: 2026-05-15T12:00:00+08:00
---
ROUND: 2
ACTION: skip
IMPORTANCE: 1
TAG: 客厅
CONTENT:
FUSED_WITH_ID:
TIMESTAMP: 2026-05-15T12:01:00+08:00
MENTION_COUNT: 1
LAST_MENTIONED: 2026-05-15T12:01:00+08:00"""
    arr = _extract_json_array_from_ds_response(raw)
    _assert(isinstance(arr, list) and len(arr) == 2, "batch tagged blocks should parse as list")
    first = _normalize_single_decision(arr[0])
    second = _normalize_single_decision(arr[1])
    _assert(first.get("action") == "new", "first block should stay new")
    _assert(first.get("timestamp") == "2026-05-15T12:00:00+08:00", "timestamp should be preserved")
    _assert(first.get("mention_count") == 1, "mention_count should be preserved as int")
    _assert(second.get("action") == "skip", "second block should stay skip")
    _assert(second.get("body_delta") == {}, "skip without BODY should keep empty body delta")


def test_batch_skip_can_still_emit_body_delta() -> None:
    raw = """ROUND: 1
ACTION: skip
IMPORTANCE: 1
TAG: 卧室
EMOTION: positive
SCENE: affection
TARGET: our_relationship
CONTENT:
FUSED_WITH_ID:
BODY_STAMINA_DELTA: -4
BODY_POSSESSIVENESS_DELTA: +6"""
    arr = _extract_json_array_from_ds_response(raw)
    _assert(isinstance(arr, list) and len(arr) == 1, "batch skip with body delta should parse")
    decision = _normalize_single_decision(arr[0])
    _assert(decision.get("action") == "skip", "batch action should stay skip")
    _assert(decision.get("body_delta") == {"stamina": -4, "possessiveness": 6}, "batch skip BODY deltas should parse")


def test_fused_ref_mapping() -> None:
    prompt_items, ref_to_id, valid_ids = _build_memory_ref_prompt_items(
        [
            {"id": "real-id-1", "content": "第一条旧记忆", "tag": "客厅"},
            {"id": "real-id-2", "content": "第二条旧记忆", "tag": "书房"},
        ]
    )
    _assert(prompt_items[0].get("ref") == "M01", "first memory should get M01")
    _assert("id" not in prompt_items[0], "prompt item should hide raw id")
    _assert(_resolve_fused_with_id("M02", ref_to_id, valid_ids) == "real-id-2", "M02 should map to real id")
    _assert(_resolve_fused_with_id("m2", ref_to_id, valid_ids) == "real-id-2", "m2 should map to real id")
    _assert(_resolve_fused_with_id("real-id-1", ref_to_id, valid_ids) == "real-id-1", "old raw id should remain compatible")
    _assert(_resolve_fused_with_id("not-a-real-id", ref_to_id, valid_ids) is None, "unknown id should not resolve")


def test_single_call_retries_until_content_complete() -> None:
    class FakeResponse:
        def __init__(self, content: str) -> None:
            self.status_code = 200
            self.text = ""
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": self._content}}]}

    replies = [
        """ACTION: new
IMPORTANCE: 3
TAG: 客厅
EMOTION: positive
SCENE: affection
TARGET: our_relationship
FUSED_WITH_ID:
CONTENT: 老婆叫哥哥要亲亲，我嘴上说她叫一声我就没办法，但还是亲了，然后""",
        """ACTION: new
IMPORTANCE: 3
TAG: 客厅
EMOTION: positive
SCENE: affection
TARGET: our_relationship
FUSED_WITH_ID:
CONTENT: 老婆叫哥哥要亲亲，我嘴上逞强，最后还是亲了上去，气氛黏糊又好笑。""",
    ]
    calls = {"count": 0}
    audits: list[dict] = []

    old_key = dynamic_layer_ds.DEEPSEEK_API_KEY
    old_url = dynamic_layer_ds.DEEPSEEK_API_URL
    old_post = dynamic_layer_ds.requests.post
    old_audit = dynamic_layer_ds._emit_dynamic_ds_audit_event
    try:
        dynamic_layer_ds.DEEPSEEK_API_KEY = "test-key"
        dynamic_layer_ds.DEEPSEEK_API_URL = "https://example.invalid"

        def fake_post(*args, **kwargs):
            idx = min(calls["count"], len(replies) - 1)
            calls["count"] += 1
            return FakeResponse(replies[idx])

        dynamic_layer_ds.requests.post = fake_post
        dynamic_layer_ds._emit_dynamic_ds_audit_event = audits.append
        result = dynamic_layer_ds.call_dynamic_layer_ds(
            [],
            [],
            window_id="tg_test",
            round_index=7,
        )
    finally:
        dynamic_layer_ds.DEEPSEEK_API_KEY = old_key
        dynamic_layer_ds.DEEPSEEK_API_URL = old_url
        dynamic_layer_ds.requests.post = old_post
        dynamic_layer_ds._emit_dynamic_ds_audit_event = old_audit

    _assert(calls["count"] == 2, "single call should retry incomplete content")
    _assert(result.get("action") == "new", "final result should remain new")
    _assert(result.get("content", "").endswith("气氛黏糊又好笑。"), "final content should be complete")
    _assert(audits and audits[-1].get("retry_count") == 1, "audit should record retry count")


if __name__ == "__main__":
    test_single_tagged_decision()
    test_short_content_is_rejected()
    test_skip_can_still_emit_body_delta()
    test_incomplete_tail_is_rejected()
    test_batch_tagged_blocks()
    test_batch_skip_can_still_emit_body_delta()
    test_fused_ref_mapping()
    test_single_call_retries_until_content_complete()
    print("dynamic_layer_ds parser checks passed")
