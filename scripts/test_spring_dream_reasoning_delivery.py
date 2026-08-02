#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path(tempfile.gettempdir()) / f"du-spring-dream-reasoning-{os.getpid()}.sqlite3"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["RUNTIME_STATE_DB"] = str(DB_PATH)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_action_contract_preserves_display_reasoning_only() -> None:
    from storage.app_action_store import _normalize_deliver_chat_message_payload

    normalized, error = _normalize_deliver_chat_message_payload(
        {
            "message_id": "spring-dream-1",
            "text": "梦里正文",
            "conversation_id": "du-private",
            "window_id": "sumitalk-main",
            "reasoning_content": "可折叠的思考正文",
            "thinking_blocks": [{"type": "thinking", "thinking": "隐藏结构", "signature": "sig"}],
        }
    )

    assert_equal(error, None, "reasoning action should remain valid")
    assert_equal(normalized.get("reasoning"), "可折叠的思考正文", "display reasoning must survive normalization")
    assert_true("thinking_blocks" not in normalized, "signed thinking blocks must not be exposed to the App")


def test_sumitalk_producer_carries_reasoning_to_history_and_action() -> None:
    from routes.miniapp import sumitalk_history
    from services import conversation_followup, realtime_publish
    from storage import r2_store

    saved: dict = {}
    queued: list = []
    old_resolve = conversation_followup._resolve_sumitalk_target_device_id
    old_load = sumitalk_history._load_sumitalk_histories
    old_save = sumitalk_history._save_sumitalk_histories
    old_append = r2_store.append_app_action
    old_voice = conversation_followup._schedule_sumitalk_proactive_voice_actions
    old_publish = realtime_publish.publish_assistant_message
    try:
        conversation_followup._resolve_sumitalk_target_device_id = lambda _preferred: "device-1"
        sumitalk_history._load_sumitalk_histories = lambda: {}
        sumitalk_history._save_sumitalk_histories = lambda data: saved.update(data) or True
        r2_store.append_app_action = lambda action_type, payload, **kwargs: (
            queued.append((action_type, payload, kwargs)) or ({"id": "action-1"}, None)
        )
        conversation_followup._schedule_sumitalk_proactive_voice_actions = lambda *_args, **_kwargs: ()
        realtime_publish.publish_assistant_message = lambda *_args, **_kwargs: True

        ok = conversation_followup._append_sumitalk_assistant_message_to_device(
            "device-1",
            "春梦正文",
            created_at="2026-07-31T01:37:05+08:00",
            window_id="sumitalk-main",
            reasoning="春梦的思考正文",
        )
    finally:
        conversation_followup._resolve_sumitalk_target_device_id = old_resolve
        sumitalk_history._load_sumitalk_histories = old_load
        sumitalk_history._save_sumitalk_histories = old_save
        r2_store.append_app_action = old_append
        conversation_followup._schedule_sumitalk_proactive_voice_actions = old_voice
        realtime_publish.publish_assistant_message = old_publish

    assert_true(ok, "SumiTalk proactive delivery should succeed")
    storage_key = sumitalk_history._sumitalk_history_storage_key("device-1", "sumitalk-main")
    assert_equal(
        saved[storage_key]["messages"][-1].get("reasoning"),
        "春梦的思考正文",
        "history hint must retain display reasoning",
    )
    assert_equal(queued[0][1].get("reasoning"), "春梦的思考正文", "device action must retain display reasoning")


def test_delivery_archive_preserves_reasoning_sidecars() -> None:
    from pipeline import pipeline
    from services import chat_archive_helpers, conversation_followup

    captured: dict = {}
    old_archive = pipeline.step_archive_round
    old_post_archive = chat_archive_helpers.run_nonstream_post_archive_in_background
    try:
        def fake_archive(window_id, request_messages, assistant_message, round_cleaned_for_r2=None):
            captured["assistant"] = assistant_message
            captured["round"] = round_cleaned_for_r2
            return {"round_index": 7, "round_messages": round_cleaned_for_r2}

        pipeline.step_archive_round = fake_archive
        chat_archive_helpers.run_nonstream_post_archive_in_background = lambda **_kwargs: None
        source_message = {
            "role": "assistant",
            "content": "未清洗正文",
            "reasoning_content": "春梦思考",
            "reasoning_details": [{"type": "reasoning.summary", "text": "春梦思考"}],
            "thinking_blocks": [
                {"type": "thinking", "thinking": "春梦思考", "signature": "opaque-signature"}
            ],
        }

        ok = conversation_followup._archive_wakeup_after_delivery(
            window_id="sumitalk-main",
            request_messages=[{"role": "user", "content": "技术触发"}],
            assistant_text="实际送达正文",
            assistant_message=source_message,
            wakeup_kind="spring_dream",
            reply_channel="sumitalk",
        )
    finally:
        pipeline.step_archive_round = old_archive
        chat_archive_helpers.run_nonstream_post_archive_in_background = old_post_archive

    assert_true(ok, "delivery archive should succeed")
    archived = captured["assistant"]
    assert_equal(archived.get("content"), "实际送达正文", "archive must use delivered visible text")
    assert_equal(archived.get("reasoning"), "春梦思考", "archive must retain canonical reasoning text")
    assert_equal(
        archived.get("thinking_blocks"),
        source_message["thinking_blocks"],
        "archive must preserve signed thinking blocks verbatim",
    )
    assert_true(archived.get("reasoning_details"), "archive must retain structured reasoning details")


def test_spring_dream_wakeup_wires_reasoning_to_delivery_and_archive() -> None:
    from services import conversation_followup, spring_dream, sumitalk_block_mode, telegram_proactive
    from storage import upstream_store

    source_message = {
        "role": "assistant",
        "content": "春梦正文",
        "reasoning": "春梦思考",
        "reasoning_details": [{"type": "reasoning.summary", "text": "春梦思考"}],
        "thinking_blocks": [{"type": "thinking", "thinking": "春梦思考", "signature": "sig"}],
    }

    class FakeResponse:
        status_code = 200
        content = b"{}"
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": source_message, "finish_reason": "stop"}]}

    delivered: dict = {}
    archived: dict = {}
    old_model = upstream_store.get_cached_active_model
    old_post = conversation_followup.requests.post
    old_preference = conversation_followup._choice_dialog_delivery_preference
    old_channels = conversation_followup._choice_dialog_delivery_channels
    old_dispatch = conversation_followup._dispatch_choice_dialog_reply
    old_archive = conversation_followup._archive_wakeup_after_delivery
    old_available = telegram_proactive._available_channels
    old_dream_archive = spring_dream.archive_spring_dream_body
    old_block_mode = sumitalk_block_mode.maybe_auto_reply_after_sumitalk_assistant
    try:
        upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "claude-opus-5"
        conversation_followup.requests.post = lambda *_args, **_kwargs: FakeResponse()
        conversation_followup._choice_dialog_delivery_preference = (
            lambda _target: ("sumitalk", "device-1", {"at": "2026-07-31T01:00:00+08:00"})
        )
        conversation_followup._choice_dialog_delivery_channels = (
            lambda _preferred, _available, _target: ["sumitalk"]
        )
        conversation_followup._dispatch_choice_dialog_reply = lambda *args, **kwargs: (
            delivered.update({"args": args, "kwargs": kwargs}) or True
        )
        conversation_followup._archive_wakeup_after_delivery = lambda **kwargs: (
            archived.update(kwargs) or True
        )
        telegram_proactive._available_channels = lambda: ["sumitalk"]
        spring_dream.archive_spring_dream_body = lambda **_kwargs: {"ok": True, "id": "dream-1"}
        sumitalk_block_mode.maybe_auto_reply_after_sumitalk_assistant = lambda **_kwargs: None

        result = conversation_followup.send_spring_dream_wakeup(
            "sumitalk-main",
            "device-1",
            "春梦触发",
            created_at="2026-07-31T01:35:00+08:00",
        )
    finally:
        upstream_store.get_cached_active_model = old_model
        conversation_followup.requests.post = old_post
        conversation_followup._choice_dialog_delivery_preference = old_preference
        conversation_followup._choice_dialog_delivery_channels = old_channels
        conversation_followup._dispatch_choice_dialog_reply = old_dispatch
        conversation_followup._archive_wakeup_after_delivery = old_archive
        telegram_proactive._available_channels = old_available
        spring_dream.archive_spring_dream_body = old_dream_archive
        sumitalk_block_mode.maybe_auto_reply_after_sumitalk_assistant = old_block_mode

    assert_true(result.get("ok"), "spring dream wakeup should complete")
    assert_equal(delivered["kwargs"].get("reasoning"), "春梦思考", "display reasoning must reach SumiTalk delivery")
    assert_true(
        archived.get("assistant_message") is source_message,
        "the original assistant message and sidecars must reach delivery archive",
    )


def main() -> None:
    test_action_contract_preserves_display_reasoning_only()
    test_sumitalk_producer_carries_reasoning_to_history_and_action()
    test_delivery_archive_preserves_reasoning_sidecars()
    test_spring_dream_wakeup_wires_reasoning_to_delivery_and_archive()
    print("Spring dream reasoning delivery tests passed")


if __name__ == "__main__":
    try:
        main()
    finally:
        if DB_PATH.exists():
            DB_PATH.unlink()
