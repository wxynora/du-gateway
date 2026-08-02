#!/usr/bin/env python3
"""Focused backend contract for editable SumiTalk Real/App mode prompts."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from services import prompt_manager


def make_body() -> dict:
    return {
        "messages": [
            {"role": "system", "content": "STATIC"},
            {
                "role": "system",
                "content": "ENTRY",
                pipeline._ENTRY_STYLE_SYSTEM_MARKER: True,
            },
            {
                "role": "system",
                "content": "STABLE",
                pipeline._SUMMARY_CACHE_SYSTEM_MARKER: True,
            },
            {"role": "user", "content": "hello"},
        ]
    }


def mode_prompt(result: dict) -> dict | None:
    for message in result.get("messages") or []:
        if isinstance(message, dict) and message.get(pipeline._SUMITALK_REAL_MODE_SYSTEM_MARKER):
            return message
    return None


def test_prompt_manager_exposes_both_mode_sections_with_existing_defaults() -> None:
    section_ids = [section.id for section in prompt_manager.PROMPT_SECTIONS]
    sumitalk_style_index = section_ids.index("entry_style_sumitalk")
    assert section_ids[sumitalk_style_index + 1 : sumitalk_style_index + 3] == [
        "sumitalk_real_mode_prompt",
        "sumitalk_app_mode_prompt",
    ]
    assert prompt_manager.prompt_section_def("sumitalk_real_mode_prompt").label == "SumiTalk Real 模式"
    assert prompt_manager.prompt_section_def("sumitalk_app_mode_prompt").label == "SumiTalk 普通模式"
    assert (
        prompt_manager.default_prompt_content("sumitalk_real_mode_prompt")
        == pipeline.SUMITALK_REAL_MODE_PROMPT
    )
    assert (
        prompt_manager.default_prompt_content("sumitalk_app_mode_prompt")
        == pipeline.SUMITALK_APP_PROMPT
    )


def test_real_mode_reads_only_real_override() -> None:
    calls: list[tuple[str, str]] = []

    def managed(section_id: str, fallback: str) -> str:
        calls.append((section_id, fallback))
        return "REAL OVERRIDE"

    with patch.object(pipeline, "_load_managed_static_prompt", side_effect=managed):
        result = pipeline.step_inject_sumitalk_real_mode(
            make_body(),
            enabled=True,
            app_request=True,
        )

    assert mode_prompt(result)["content"] == "REAL OVERRIDE"
    assert calls == [("sumitalk_real_mode_prompt", pipeline.SUMITALK_REAL_MODE_PROMPT)]
    assert [message["content"] for message in result["messages"]] == [
        "STATIC",
        "ENTRY",
        "REAL OVERRIDE",
        "STABLE",
        "hello",
    ]


def test_app_mode_reads_only_app_override() -> None:
    calls: list[tuple[str, str]] = []

    def managed(section_id: str, fallback: str) -> str:
        calls.append((section_id, fallback))
        return "APP OVERRIDE"

    with patch.object(pipeline, "_load_managed_static_prompt", side_effect=managed):
        result = pipeline.step_inject_sumitalk_real_mode(
            make_body(),
            enabled=False,
            app_request=True,
        )

    assert mode_prompt(result)["content"] == "APP OVERRIDE"
    assert calls == [("sumitalk_app_mode_prompt", pipeline.SUMITALK_APP_PROMPT)]
    assert [message["content"] for message in result["messages"]] == [
        "STATIC",
        "ENTRY",
        "APP OVERRIDE",
        "STABLE",
        "hello",
    ]


def test_non_sumitalk_request_does_not_read_or_inject_mode_prompt() -> None:
    with patch.object(
        pipeline,
        "_load_managed_static_prompt",
        side_effect=AssertionError("non-SumiTalk request must not load mode prompts"),
    ):
        result = pipeline.step_inject_sumitalk_real_mode(
            make_body(),
            enabled=False,
            app_request=False,
        )

    assert mode_prompt(result) is None


if __name__ == "__main__":
    test_prompt_manager_exposes_both_mode_sections_with_existing_defaults()
    test_real_mode_reads_only_real_override()
    test_app_mode_reads_only_app_override()
    test_non_sumitalk_request_does_not_read_or_inject_mode_prompt()
    print("editable SumiTalk mode prompt checks passed")
