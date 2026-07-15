from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import claude_thinking_carryover as carryover
from storage import r2_store


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _round(*, thinking_blocks: list[dict], assistant_content: str = "上一轮回复") -> dict:
    return {
        "messages": [
            {"role": "user", "content": "上一轮消息"},
            {
                "role": "assistant",
                "content": assistant_content,
                "thinking_blocks": thinking_blocks,
            },
        ]
    }


def _inject_with_round(body: dict, round_obj: dict) -> dict:
    old_window = r2_store.get_conversation_rounds
    old_global = r2_store.get_latest_4_rounds_global
    r2_store.get_conversation_rounds = lambda *_args, **_kwargs: [round_obj]
    r2_store.get_latest_4_rounds_global = lambda: []
    try:
        return carryover.inject_previous_claude_thinking_blocks(body, "tg_test")
    finally:
        r2_store.get_conversation_rounds = old_window
        r2_store.get_latest_4_rounds_global = old_global


def test_extractor_still_preserves_full_archived_block() -> None:
    original = {
        "type": "thinking",
        "thinking": "官方转写里叫了用户，但归档仍需保留原文。",
        "signature": "sig-full",
    }
    extracted = carryover.extract_claude_thinking_blocks({"thinking_blocks": [original]})
    _assert(extracted == [original], f"archive extraction must remain lossless: {extracted}")
    _assert(extracted[0] is not original, "archive extraction must return a copy")


def test_inserted_cross_turn_block_contains_only_signature() -> None:
    result = _inject_with_round(
        {"messages": [{"role": "user", "content": "当前消息"}]},
        _round(
            thinking_blocks=[
                {
                    "type": "thinking",
                    "thinking": "这里是会影响下一轮措辞的官方转写。",
                    "signature": "sig-inserted",
                }
            ]
        ),
    )

    messages = result["messages"]
    _assert([item["role"] for item in messages] == ["user", "assistant", "user"], f"wrong order: {messages}")
    block = messages[1]["thinking_blocks"][0]
    _assert(
        block == {"type": "thinking", "thinking": "", "signature": "sig-inserted"},
        f"visible rewrite leaked into cross-turn carryover: {block}",
    )
    _assert(messages[1]["content"] == "上一轮回复", "previous visible assistant reply must stay present")


def test_matching_assistant_gets_opaque_block_without_duplicate_messages() -> None:
    result = _inject_with_round(
        {
            "messages": [
                {"role": "user", "content": "上一轮消息"},
                {"role": "assistant", "content": "上一轮回复"},
                {"role": "user", "content": "当前消息"},
            ]
        },
        _round(
            thinking_blocks=[
                {"type": "thinking", "thinking": "不能再次注入。", "signature": "sig-attached"}
            ]
        ),
    )

    _assert(len(result["messages"]) == 3, f"matching history must not be duplicated: {result['messages']}")
    _assert(
        result["messages"][1]["thinking_blocks"]
        == [{"type": "thinking", "thinking": "", "signature": "sig-attached"}],
        "matching assistant did not receive signature-only carryover",
    )


def test_existing_cross_turn_block_is_sanitized_instead_of_forwarded_verbatim() -> None:
    result = _inject_with_round(
        {
            "messages": [
                {"role": "user", "content": "更早消息"},
                {
                    "role": "assistant",
                    "content": "更早回复",
                    "reasoning_details": [
                        {"type": "thinking", "thinking": "旧 body 里的可见转写。", "signature": "sig-existing"}
                    ],
                },
                {"role": "user", "content": "当前消息"},
            ]
        },
        _round(
            thinking_blocks=[
                {"type": "thinking", "thinking": "归档里的另一段。", "signature": "sig-archive"}
            ]
        ),
    )

    assistant = result["messages"][1]
    _assert("reasoning_details" not in assistant, "legacy visible reasoning_details must be removed from the request")
    _assert(
        assistant["thinking_blocks"]
        == [{"type": "thinking", "thinking": "", "signature": "sig-existing"}],
        f"existing block was not reduced to its signature: {assistant}",
    )


def test_redacted_block_keeps_only_opaque_data() -> None:
    result = _inject_with_round(
        {"messages": [{"role": "user", "content": "当前消息"}]},
        _round(
            thinking_blocks=[
                {
                    "type": "redacted_thinking",
                    "data": "opaque-redacted-data",
                    "text": "不应跨轮携带的可见字段",
                }
            ]
        ),
    )

    block = result["messages"][1]["thinking_blocks"][0]
    _assert(
        block == {"type": "redacted_thinking", "data": "opaque-redacted-data"},
        f"redacted carryover must stay opaque: {block}",
    )


if __name__ == "__main__":
    test_extractor_still_preserves_full_archived_block()
    test_inserted_cross_turn_block_contains_only_signature()
    test_matching_assistant_gets_opaque_block_without_duplicate_messages()
    test_existing_cross_turn_block_is_sanitized_instead_of_forwarded_verbatim()
    test_redacted_block_keeps_only_opaque_data()
    print("claude_thinking_carryover tests ok")
