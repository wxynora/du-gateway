#!/usr/bin/env python3
"""Regression checks for the SumiTalk Real-mode prompt boundary."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.pipeline import (  # noqa: E402
    SUMITALK_REAL_MODE_PROMPT,
    step_inject_sumitalk_real_mode,
)
from services.upstream_policy import _normalize_pioneer_chat_system_cache_messages  # noqa: E402


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def make_body() -> dict:
    return {
        "messages": [
            {"role": "system", "content": "static"},
            {"role": "system", "content": "stable recent memory", "__summary_cache__": True},
            {"role": "system", "content": "latest recent memory", "__summary_recent__": True},
            {"role": "system", "content": "dynamic", "__dynamic__": True},
            {"role": "user", "content": "hello"},
        ]
    }


def test_mode_gate_and_source_order() -> None:
    disabled = step_inject_sumitalk_real_mode(make_body(), enabled=False)
    assert_true(
        all(SUMITALK_REAL_MODE_PROMPT not in str(msg.get("content") or "") for msg in disabled["messages"]),
        "normal App mode must not receive the Real-mode prompt",
    )

    enabled = step_inject_sumitalk_real_mode(make_body(), enabled=True)
    contents = [str(msg.get("content") or "") for msg in enabled["messages"]]
    assert_true(
        contents == [
            "static",
            "stable recent memory",
            "latest recent memory",
            SUMITALK_REAL_MODE_PROMPT,
            "dynamic",
            "hello",
        ],
        "Real-mode prompt must follow all recent-memory blocks and precede dynamic context",
    )

    repeated = step_inject_sumitalk_real_mode(enabled, enabled=True)
    assert_true(
        sum(SUMITALK_REAL_MODE_PROMPT in str(msg.get("content") or "") for msg in repeated["messages"]) == 1,
        "Real-mode injection must be idempotent",
    )


def test_pioneer_final_breakpoint_order() -> None:
    enabled = step_inject_sumitalk_real_mode(make_body(), enabled=True)
    normalized = _normalize_pioneer_chat_system_cache_messages(enabled["messages"], "1h")
    system_blocks = normalized[0]["content"]
    system_texts = [str(block.get("text") or "") for block in system_blocks]
    assert_true(
        system_texts[-3:] == ["stable recent memory", "latest recent memory", SUMITALK_REAL_MODE_PROMPT],
        "Pioneer system prefix must keep Real mode after the complete recent memory",
    )
    assert_true(
        system_blocks[-1].get("cache_control") == {"type": "ephemeral", "ttl": "1h"},
        "the final cache breakpoint must sit after the Real-mode prompt",
    )
    assert_true(
        "__sumitalk_real_mode__" not in system_blocks[-1],
        "gateway-only Real-mode markers must not leak upstream",
    )


if __name__ == "__main__":
    test_mode_gate_and_source_order()
    test_pioneer_final_breakpoint_order()
    print("sumitalk real-mode prompt checks passed")
