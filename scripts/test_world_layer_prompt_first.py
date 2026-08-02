#!/usr/bin/env python3
"""Focused regression checks for the world-layer static first slot."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from services import chat_prompt_injections, prompt_manager


WORLD_TEXT = "你与小玥的互动分为三个层级。"
CODEX_TEXT = "Codex OAuth 专用 Prompt"


def test_prompt_manager_title_is_not_in_default_body() -> None:
    section = prompt_manager.prompt_section_def("world_layer_prompt")
    assert section is not None
    assert prompt_manager.PROMPT_SECTIONS[0].id == "world_layer_prompt"
    assert section.label == "世界层级"

    content = prompt_manager.default_prompt_content("world_layer_prompt")
    assert content
    assert content.startswith("你与小玥")
    assert section.label not in content
    assert "SumiTalk" in content


def test_world_layer_is_static_first_and_idempotent() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "核心 Prompt"},
            {"role": "system", "content": "其他静态规则"},
            {"role": "user", "content": "你好"},
        ]
    }
    with patch(
        "services.prompt_manager.get_managed_prompt_text",
        return_value=WORLD_TEXT,
    ):
        body = chat_prompt_injections.inject_world_layer_prompt_system(body)
        body = chat_prompt_injections.inject_world_layer_prompt_system(body)

    assert [message["content"] for message in body["messages"][:3]] == [
        WORLD_TEXT,
        "核心 Prompt",
        "其他静态规则",
    ]
    assert sum(message.get("content") == WORLD_TEXT for message in body["messages"]) == 1
    assert not body["messages"][0].get("__dynamic__")


def test_world_layer_stays_before_codex_and_core_after_final_merge() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "核心 Prompt"},
            {"role": "user", "content": "你好"},
        ]
    }

    def managed_prompt(section_id: str, fallback: str = "") -> str:
        if section_id == "codex_oauth_prompt":
            return CODEX_TEXT
        if section_id == "world_layer_prompt":
            return WORLD_TEXT
        return str(fallback or "")

    with (
        patch.object(chat_prompt_injections, "is_local_cliproxyapi_url", return_value=True),
        patch("services.prompt_manager.get_managed_prompt_text", side_effect=managed_prompt),
        patch("services.tool_result_cache.prompt_system_contents", return_value=[]),
    ):
        body = chat_prompt_injections.inject_codex_oauth_prompt_system(
            body,
            upstream_url="http://127.0.0.1:8317/v1/chat/completions",
        )
        body = chat_prompt_injections.inject_world_layer_prompt_system(body)
        body = pipeline.step_inject_tool_result_cache(body)

    assert body["messages"][0]["content"] == (
        f"{WORLD_TEXT}\n\n{CODEX_TEXT}\n\n核心 Prompt"
    )


def test_chat_pipeline_injects_world_after_existing_static_mutators() -> None:
    source = (ROOT / "routes" / "chat.py").read_text(encoding="utf-8")
    codex_pos = source.index("body = _inject_codex_oauth_prompt_system(")
    silence_pos = source.index("body = _inject_silence_mode_system(")
    custom_pos = source.index("body = step_inject_custom_static_systems(")
    world_pos = source.index("body = _inject_world_layer_prompt_system(")
    merge_pos = source.index("body = step_inject_tool_result_cache(")
    assert codex_pos < silence_pos < custom_pos < world_pos < merge_pos


if __name__ == "__main__":
    test_prompt_manager_title_is_not_in_default_body()
    test_world_layer_is_static_first_and_idempotent()
    test_world_layer_stays_before_codex_and_core_after_final_merge()
    test_chat_pipeline_injects_world_after_existing_static_mutators()
    print("world-layer static first-slot checks passed")
