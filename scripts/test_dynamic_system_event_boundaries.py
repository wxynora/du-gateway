#!/usr/bin/env python3
"""Regression checks for transient system messages that must stay out of static cache."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.co_read_api import _co_read_card_system_message  # noqa: E402
from routes.chat import _inject_music_bgm_context  # noqa: E402
from services import conversation_followup as followup  # noqa: E402
from services import watch_context  # noqa: E402
from services.chat_tool_helpers import (  # noqa: E402
    inject_tool_empty_final_retry_instruction,
    inject_tool_midstream_retry_instruction,
)
from services.listen_invite_flow import inject_listen_invite_protocol  # noqa: E402
from services.voice_call_pipeline import _build_voice_user_messages  # noqa: E402
from storage import upstream_store  # noqa: E402


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _assert_temporary_dynamic(message: dict, label: str) -> None:
    _assert(message.get("__dynamic__") is True, f"{label} lost dynamic marker: {message}")
    _assert(message.get("__temporary_dynamic__") is True, f"{label} missed temporary slot: {message}")


def test_event_wrappers_request_dynamic_system() -> None:
    captured: list[dict] = []
    original = followup._send_wakeup_event
    followup._send_wakeup_event = lambda **kwargs: captured.append(kwargs) or {"ok": True}
    try:
        followup.send_private_draw_wakeup("w", "t", "draw")
        followup.send_listen_invite_response_wakeup("w", "t", "accept")
        followup.send_exchange_diary_comment_wakeup("w", "t", "title", "entry", "comment", "text")
        followup.send_spring_dream_wakeup("w", "t", "dream")
        followup.send_post_spring_dream_wakeup("w", "t", "after dream")
    finally:
        followup._send_wakeup_event = original

    _assert(len(captured) == 5, f"unexpected event wrapper count: {len(captured)}")
    for item in captured:
        _assert(item.get("system_event") is True, f"event stopped using system role: {item}")
        _assert(item.get("dynamic_system_event") is True, f"event leaked into static: {item}")


def test_gateway_event_builder_keeps_dynamic_marker() -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        content = b"{}"
        text = ""

        @staticmethod
        def json() -> dict:
            return {"choices": [{"message": {"role": "assistant", "content": "收到"}}]}

    original_model = upstream_store.get_cached_active_model
    original_preference = followup._choice_dialog_delivery_preference
    original_post = followup.requests.post
    upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "test-model"
    followup._choice_dialog_delivery_preference = lambda target: ("sumitalk", target, {})

    def fake_post(url, *, headers, json, timeout):
        captured["body"] = json
        captured["headers"] = headers
        return FakeResponse()

    followup.requests.post = fake_post
    try:
        result = followup._send_wakeup_event(
            window_id="window",
            target="target",
            event_text="一次性事件",
            wakeup_kind="test_event",
            system_event=True,
            dynamic_system_event=True,
            system_event_user_summary="根据事件回应",
            return_only=True,
        )
    finally:
        upstream_store.get_cached_active_model = original_model
        followup._choice_dialog_delivery_preference = original_preference
        followup.requests.post = original_post

    _assert(result.get("ok") is True, f"event builder failed: {result}")
    messages = (captured.get("body") or {}).get("messages") or []
    _assert(messages[0].get("role") == "system", f"event role changed: {messages}")
    _assert_temporary_dynamic(messages[0], "gateway event")
    _assert(messages[1] == {"role": "user", "content": "根据事件回应"}, f"user summary changed: {messages}")


def test_voice_and_co_read_runtime_contexts_are_dynamic() -> None:
    voice_messages = _build_voice_user_messages("你好", "背景里有持续雨声")
    _assert_temporary_dynamic(voice_messages[0], "voice observation")
    _assert(not voice_messages[-1].get("__dynamic__"), f"real user message was marked dynamic: {voice_messages}")

    card_message = _co_read_card_system_message("当前读到第三章")
    _assert(card_message.get("role") == "system", f"co-read card role changed: {card_message}")
    _assert_temporary_dynamic(card_message, "co-read card")


def test_tool_retry_instructions_are_dynamic() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "稳定规则"},
            {"role": "user", "content": "继续"},
        ]
    }
    for inject in (inject_tool_empty_final_retry_instruction, inject_tool_midstream_retry_instruction):
        updated = inject(body)
        retry_message = updated["messages"][1]
        _assert(retry_message.get("role") == "system", f"retry role changed: {updated}")
        _assert_temporary_dynamic(retry_message, "tool retry instruction")


def test_watch_listen_and_music_contexts_use_temporary_slot() -> None:
    listen_body = inject_listen_invite_protocol(
        {"messages": [{"role": "user", "content": "一起听"}]},
        reply_channel="sumitalk",
    )
    _assert_temporary_dynamic(listen_body["messages"][0], "listen invite protocol")

    music_body = _inject_music_bgm_context(
        {
            "messages": [{"role": "user", "content": "继续聊"}],
            "music_bgm_context": {
                "active": True,
                "is_playing": True,
                "title": "测试歌曲",
                "artist": "测试歌手",
                "current_time": 12,
                "duration_seconds": 180,
            },
        },
        reply_channel="sumitalk",
    )
    _assert_temporary_dynamic(music_body["messages"][0], "current music context")

    snapshot = {
        "media_id": "media",
        "playhead_ms": 1000,
        "is_playing": True,
        "playback_rate": 1.0,
        "timeline_epoch": 1,
        "snapshot_seq": 1,
        "captured_at": "2026-07-22T10:00:00+08:00",
    }
    original_build = watch_context.build_watch_context
    original_get_session = watch_context.watch_runtime_store.get_session
    watch_context.build_watch_context = lambda **kwargs: ("当前剧情", {})
    watch_context.watch_runtime_store.get_session = lambda session_id: {}
    try:
        watch_body, _ = watch_context.inject_watch_context(
            {
                watch_context.WATCH_SESSION_BODY_KEY: "session",
                watch_context.WATCH_SNAPSHOT_BODY_KEY: snapshot,
                "messages": [{"role": "user", "content": "看到这里"}],
            },
            window_id="window",
            reply_channel="sumitalk",
        )
    finally:
        watch_context.build_watch_context = original_build
        watch_context.watch_runtime_store.get_session = original_get_session
    _assert_temporary_dynamic(watch_body["messages"][0], "watch context")


if __name__ == "__main__":
    test_event_wrappers_request_dynamic_system()
    test_gateway_event_builder_keeps_dynamic_marker()
    test_voice_and_co_read_runtime_contexts_are_dynamic()
    test_tool_retry_instructions_are_dynamic()
    test_watch_listen_and_music_contexts_use_temporary_slot()
    print("dynamic system event boundary checks passed")
