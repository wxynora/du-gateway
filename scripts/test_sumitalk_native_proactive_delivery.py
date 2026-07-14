#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path(tempfile.gettempdir()) / f"du-native-proactive-delivery-{os.getpid()}.sqlite3"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["RUNTIME_STATE_DB"] = str(DB_PATH)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_persistent_action_contract() -> None:
    from storage import app_action_store

    app_action_store._APP_ACTION_BOOTSTRAPPED = True
    app_action_store._publish_app_action = lambda item: None
    payload = {
        "message_id": "assistant-followup-stable-1",
        "text": "第一段\n\n第二段，正文必须完整保留。",
        "conversation_id": "du-private",
        "window_id": "sumitalk-main",
        "role": "assistant",
        "sender": "渡",
        "created_at": "2026-07-14T12:00:00+08:00",
    }
    first, error = app_action_store.append_app_action(
        "deliver_chat_message",
        payload,
        device_id="device_native_001",
        expires_in_sec=30 * 24 * 60 * 60,
        source="test",
        idempotency_key="chat-message:device_native_001:assistant-followup-stable-1",
    )
    assert_true(first and not error, f"chat action should enqueue: {error}")
    duplicate, error = app_action_store.append_app_action(
        "deliver_chat_message",
        payload,
        device_id="device_native_001",
        expires_in_sec=30 * 24 * 60 * 60,
        source="test",
        idempotency_key="chat-message:device_native_001:assistant-followup-stable-1",
    )
    assert_true(duplicate and duplicate.get("duplicate") and not error, "pending retry should reuse action")
    assert_equal(duplicate["id"], first["id"], "idempotency must retain action id")

    wrong_device = app_action_store.poll_app_actions(device_id="device_other", surface="native")
    assert_equal(wrong_device.get("actions"), [], "another device must not lease the message")
    polled = app_action_store.poll_app_actions(device_id="device_native_001", surface="native")
    actions = polled.get("actions") or []
    assert_equal(len(actions), 1, "target device should lease one persistent message")
    assert_equal(actions[0]["payload"], payload, "action payload must preserve the full message")


def test_followup_producer_uses_one_stable_message_id() -> None:
    from routes.miniapp import sumitalk_history
    from services import conversation_followup, realtime_publish
    from storage import r2_store

    saved = {}
    queued = []
    published = []
    old_resolve = conversation_followup._resolve_sumitalk_target_device_id
    old_load = sumitalk_history._load_sumitalk_histories
    old_save = sumitalk_history._save_sumitalk_histories
    old_append = r2_store.append_app_action
    old_publish = realtime_publish.publish_assistant_message
    try:
        conversation_followup._resolve_sumitalk_target_device_id = lambda preferred: "device_native_001"
        sumitalk_history._load_sumitalk_histories = lambda: {}
        sumitalk_history._save_sumitalk_histories = lambda data: saved.update(data) or True
        r2_store.append_app_action = lambda action_type, payload, **kwargs: (
            queued.append((action_type, payload, kwargs)) or ({"id": "action-1"}, None)
        )
        realtime_publish.publish_assistant_message = lambda device_id, message, window_id="": (
            published.append((device_id, message, window_id)) or True
        )

        ok = conversation_followup._append_sumitalk_assistant_message_to_device(
            "device_native_001",
            "主动发来的完整正文",
            created_at="2026-07-14T12:00:00+08:00",
        )
    finally:
        conversation_followup._resolve_sumitalk_target_device_id = old_resolve
        sumitalk_history._load_sumitalk_histories = old_load
        sumitalk_history._save_sumitalk_histories = old_save
        r2_store.append_app_action = old_append
        realtime_publish.publish_assistant_message = old_publish

    assert_true(ok, "followup producer should report success after history and action persist")
    history_message = saved["device_native_001"]["messages"][-1]
    action_type, action_payload, action_options = queued[0]
    assert_equal(action_type, "deliver_chat_message", "producer must use persistent device action")
    assert_equal(action_payload["message_id"], history_message["id"], "history and action must share message id")
    assert_equal(published[0][1]["id"], history_message["id"], "realtime hint must share message id")
    assert_equal(action_payload["text"], "主动发来的完整正文", "producer must not truncate message text")
    assert_equal(action_options["device_id"], "device_native_001", "action must target the paired device")


def main() -> None:
    test_persistent_action_contract()
    test_followup_producer_uses_one_stable_message_id()
    print("SumiTalk native proactive delivery tests passed")


if __name__ == "__main__":
    try:
        main()
    finally:
        if DB_PATH.exists() and not os.environ.get("KEEP_NATIVE_PROACTIVE_TEST_DB"):
            DB_PATH.unlink()
