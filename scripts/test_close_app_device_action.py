#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path(tempfile.gettempdir()) / f"du-close-app-device-action-{os.getpid()}.sqlite3"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["RUNTIME_STATE_DB"] = str(DB_PATH)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_tool_resolves_and_targets_the_reported_foreground_app() -> None:
    from services import device_action_tools

    captured = []
    old_get_latest = device_action_tools.r2_store.get_sense_latest
    old_append = device_action_tools.r2_store.append_app_action
    try:
        device_action_tools.r2_store.get_sense_latest = lambda: {
            "foreground": {
                "deviceId": "device-native-1",
                "packageName": "com.xingin.xhs",
                "appName": "小红书",
            },
        }
        device_action_tools.r2_store.append_app_action = lambda action_type, payload, **kwargs: (
            captured.append((action_type, payload, kwargs)) or ({"id": "close-action-1"}, None)
        )

        result = json.loads(device_action_tools.execute_close_app({"app_name": "小红书"}))
    finally:
        device_action_tools.r2_store.get_sense_latest = old_get_latest
        device_action_tools.r2_store.append_app_action = old_append

    assert_true(result.get("ok") and result.get("queued"), "close_app tool should queue the action")
    action_type, payload, options = captured[0]
    assert_equal(action_type, "close_app", "tool must enqueue close_app")
    assert_equal(payload["packageName"], "com.xingin.xhs", "tool must lock the exact foreground package")
    assert_equal(options["device_id"], "device-native-1", "tool must target the reporting phone")


def test_tool_rejects_a_different_expected_app() -> None:
    from services import device_action_tools

    appended = []
    old_get_latest = device_action_tools.r2_store.get_sense_latest
    old_append = device_action_tools.r2_store.append_app_action
    try:
        device_action_tools.r2_store.get_sense_latest = lambda: {
            "foreground": {"packageName": "com.sumitalk.nativeapp", "appName": "SumiTalk"},
        }
        device_action_tools.r2_store.append_app_action = lambda *args, **kwargs: appended.append((args, kwargs))
        result = json.loads(device_action_tools.execute_close_app({"app_name": "小红书"}))
    finally:
        device_action_tools.r2_store.get_sense_latest = old_get_latest
        device_action_tools.r2_store.append_app_action = old_append

    assert_true(not result.get("ok") and not result.get("queued"), "mismatched target must not queue")
    assert_equal(appended, [], "mismatched target must not reach the action store")


def test_action_store_keeps_close_app_on_the_target_device() -> None:
    from storage import app_action_store

    app_action_store._APP_ACTION_BOOTSTRAPPED = True
    app_action_store._publish_app_action = lambda item: None
    item, error = app_action_store.append_app_action(
        "close_app",
        {"package_name": "com.xingin.xhs", "app_name": "小红书"},
        device_id="device-native-1",
        source="test",
        idempotency_key="close-app-contract-1",
    )
    assert_true(item and not error, f"close_app should enter the native queue: {error}")
    assert_equal(
        app_action_store.poll_app_actions(device_id="device-other", surface="native").get("actions"),
        [],
        "another phone must not receive close_app",
    )
    actions = app_action_store.poll_app_actions(device_id="device-native-1", surface="native").get("actions") or []
    assert_equal(len(actions), 1, "target phone should receive one close_app")
    assert_equal(actions[0]["payload"]["packageName"], "com.xingin.xhs", "normalized package must survive polling")


def test_close_app_is_in_the_daily_tool_surface() -> None:
    from services import mcp_forum_tools

    old_enabled = mcp_forum_tools.MCP_ENABLED
    try:
        mcp_forum_tools.MCP_ENABLED = True
        names = {
            str((tool.get("function") or {}).get("name") or "")
            for tool in mcp_forum_tools.get_forum_tools_for_inject(mode="daily")
        }
    finally:
        mcp_forum_tools.MCP_ENABLED = old_enabled
    assert_true("close_app" in names, "Du must receive close_app in the daily tool surface")


def test_chat_tool_dispatches_close_app_with_context() -> None:
    from services import chat_tools

    captured = []
    old_execute = chat_tools.execute_forum_tool
    try:
        chat_tools.execute_forum_tool = lambda name, args: (
            captured.append((name, args)) or json.dumps({"ok": True}, ensure_ascii=False)
        )
        result = json.loads(
            chat_tools.execute_tool(
                "close_app",
                {"app_name": "小红书"},
                context={"reply_target": "device-native-1", "reply_channel": "sumitalk"},
            ),
        )
    finally:
        chat_tools.execute_forum_tool = old_execute

    assert_true(result.get("ok"), "chat dispatch should return the close_app tool result")
    assert_equal(captured[0][0], "close_app", "chat dispatch must preserve the tool name")
    assert_equal(
        captured[0][1]["_context"]["reply_target"],
        "device-native-1",
        "chat dispatch must preserve the target context",
    )


def main() -> None:
    test_tool_resolves_and_targets_the_reported_foreground_app()
    test_tool_rejects_a_different_expected_app()
    test_action_store_keeps_close_app_on_the_target_device()
    test_close_app_is_in_the_daily_tool_surface()
    test_chat_tool_dispatches_close_app_with_context()
    print("close_app device action tests passed")


if __name__ == "__main__":
    try:
        main()
    finally:
        if DB_PATH.exists() and not os.environ.get("KEEP_CLOSE_APP_TEST_DB"):
            DB_PATH.unlink()
