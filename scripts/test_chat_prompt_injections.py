#!/usr/bin/env python3
"""Focused contract for the Thinking prompt's dynamic slot."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from services import tool_result_cache


def test_thinking_rules_are_dynamic_and_immediately_before_last4() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "STATIC"},
            {
                "role": "system",
                "content": "ENTRY",
                pipeline._ENTRY_STYLE_SYSTEM_MARKER: True,
            },
            {
                "role": "system",
                "content": "PERSISTENT_DYNAMIC",
                pipeline._DYNAMIC_SYSTEM_MARKER: True,
            },
            {
                "role": "system",
                "content": "TEMPORARY_DYNAMIC",
                pipeline._DYNAMIC_SYSTEM_MARKER: True,
                pipeline._TEMPORARY_DYNAMIC_SYSTEM_MARKER: True,
            },
            {
                "role": "system",
                "content": "LAST4",
                pipeline._DYNAMIC_SYSTEM_MARKER: True,
                pipeline._LAST4_SYSTEM_MARKER: True,
            },
            {"role": "user", "content": "hello"},
        ]
    }

    with (
        patch.object(pipeline, "_load_managed_static_prompt", return_value="THINKING"),
        patch.object(tool_result_cache, "prompt_system_contents", return_value=["TOOL_CACHE"]),
    ):
        body = pipeline.step_inject_thinking_block_rules(body)
        body = pipeline.step_inject_tool_result_cache(body)

    systems = [msg for msg in body["messages"] if msg.get("role") == "system"]
    assert [msg["content"] for msg in systems] == [
        "STATIC",
        "TOOL_CACHE",
        "ENTRY",
        "PERSISTENT_DYNAMIC",
        "TEMPORARY_DYNAMIC",
        "THINKING",
        "LAST4",
    ]
    thinking = systems[-2]
    assert thinking[pipeline._THINKING_RULES_SYSTEM_MARKER] is True
    assert thinking[pipeline._DYNAMIC_SYSTEM_MARKER] is True
    assert not thinking.get(pipeline._TEMPORARY_DYNAMIC_SYSTEM_MARKER)
    assert not thinking.get(pipeline._LAST4_SYSTEM_MARKER)


if __name__ == "__main__":
    test_thinking_rules_are_dynamic_and_immediately_before_last4()
    print("PASS test_thinking_rules_are_dynamic_and_immediately_before_last4")
