#!/usr/bin/env python3
"""Pure-local regression checks for the final gateway system prompt order."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_entry_style_stays_isolated_from_later_static_injections() -> None:
    from pipeline import pipeline
    from services import tool_result_cache

    original = tool_result_cache.prompt_system_contents
    tool_result_cache.prompt_system_contents = lambda: ["TOOL-A", "TOOL-B"]
    try:
        body = {
            "messages": [
                {"role": "system", "content": "CORE"},
                {"role": "system", "content": "ENTRY", "__entry_style__": True},
                {"role": "system", "content": "REAL", "__sumitalk_real_mode__": True},
                {"role": "system", "content": "PLAY", "__play_note__": True},
                {"role": "system", "content": "STABLE", "__summary_cache__": True},
                {"role": "system", "content": "RECENT", "__summary_recent__": True},
                {"role": "system", "content": "DYNAMIC", "__dynamic__": True},
                {
                    "role": "system",
                    "content": "TEMPORARY",
                    "__dynamic__": True,
                    "__temporary_dynamic__": True,
                },
                {"role": "system", "content": "LAST4", "__dynamic__": True, "__last4__": True},
                {"role": "user", "content": "hello"},
            ],
            "feature_state": {"unchanged": True},
        }
        body = pipeline._append_to_static_system(body, "\nRULES")
        body = pipeline._append_to_static_system(body, "\nNOTEBOOK")
        result = pipeline.step_inject_tool_result_cache(body)
    finally:
        tool_result_cache.prompt_system_contents = original

    assert [m["content"] for m in result["messages"]] == [
        "CORE\n\n\nRULES\n\n\nNOTEBOOK",
        "TOOL-A\n\nTOOL-B",
        "ENTRY\n\nREAL\n\nSTABLE\n\nRECENT",
        "DYNAMIC",
        "PLAY\n\nTEMPORARY",
        "LAST4",
        "hello",
    ]
    assert result["messages"][1].get("__tool_result_cache__") is True
    assert result["messages"][2].get("__summary_recent__") is True
    assert result["messages"][3].get("__dynamic__") is True
    assert result["messages"][4].get("__temporary_dynamic__") is True
    assert result["messages"][5].get("__last4__") is True
    assert result["feature_state"] == {"unchanged": True}


def test_gateway_marker_cleanup_removes_internal_region_markers() -> None:
    from services import upstream_policy

    internal_messages = [
        {
            "role": "system",
            "content": "TEMPORARY",
            "__dynamic__": True,
            "__temporary_dynamic__": True,
            "__last4__": True,
        }
    ]
    upstream_policy.strip_internal_prompt_region_markers(internal_messages)
    assert internal_messages[0].get("__dynamic__") is True
    assert "__temporary_dynamic__" not in internal_messages[0]
    assert "__last4__" not in internal_messages[0]

    messages = [
        {
            "role": "system",
            "content": "TEMPORARY",
            "__dynamic__": True,
            "__temporary_dynamic__": True,
            "__last4__": True,
        }
    ]
    upstream_policy._strip_gateway_cache_markers(messages)
    assert "__dynamic__" not in messages[0]
    assert "__temporary_dynamic__" not in messages[0]
    assert "__last4__" not in messages[0]


if __name__ == "__main__":
    test_entry_style_stays_isolated_from_later_static_injections()
    test_gateway_marker_cleanup_removes_internal_region_markers()
    print("entry style isolation and prompt order checks passed")
