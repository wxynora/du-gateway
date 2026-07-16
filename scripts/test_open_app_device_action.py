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

DB_PATH = Path(tempfile.gettempdir()) / f"du-open-app-device-action-{os.getpid()}.sqlite3"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["RUNTIME_STATE_DB"] = str(DB_PATH)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_qq_defaults_to_du_private_chat() -> None:
    from services import device_action_tools

    captured = []
    old_get_latest = device_action_tools.r2_store.get_sense_latest
    old_append = device_action_tools.r2_store.append_app_action
    try:
        device_action_tools.r2_store.get_sense_latest = lambda: {
            "foreground": {"deviceId": "device-native-1"},
        }
        device_action_tools.r2_store.append_app_action = lambda action_type, payload, **kwargs: (
            captured.append((action_type, payload, kwargs)) or ({"id": "open-action-1"}, None)
        )
        result = json.loads(device_action_tools.execute_open_app({"app_name": "QQ"}))
    finally:
        device_action_tools.r2_store.get_sense_latest = old_get_latest
        device_action_tools.r2_store.append_app_action = old_append

    assert_true(result.get("ok") and result.get("queued"), "open_app should queue")
    action_type, payload, options = captured[0]
    assert_equal(action_type, "open_app", "tool must enqueue open_app")
    assert_equal(payload["packageName"], "com.tencent.mobileqq", "QQ must map to its Android package")
    assert_equal(payload["appName"], "QQ", "tool should preserve the friendly app name")
    assert_true(payload["url"].startswith("mqqwpa://im/chat?"), "QQ should default to the Du chat deep link")
    assert_equal(options["device_id"], "device-native-1", "tool must target the reporting phone")


def test_qq_home_explicitly_skips_the_chat_deep_link() -> None:
    from services import device_action_tools

    target, error = device_action_tools._resolve_open_app_target({"app_name": "QQ", "page": "首页"})

    assert_equal(error, "", "QQ home mapping should resolve")
    assert_equal(target["packageName"], "com.tencent.mobileqq", "QQ home keeps the package mapping")
    assert_equal(target["url"], "", "explicit QQ home must not use the Du chat deep link")


def test_open_app_is_in_the_daily_tool_surface() -> None:
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

    assert_true("open_app" in names, "open_app must be available in daily chat")


def main() -> None:
    test_qq_defaults_to_du_private_chat()
    test_qq_home_explicitly_skips_the_chat_deep_link()
    test_open_app_is_in_the_daily_tool_surface()
    print("open_app device action tests passed")


if __name__ == "__main__":
    try:
        main()
    finally:
        if DB_PATH.exists() and not os.environ.get("KEEP_OPEN_APP_TEST_DB"):
            DB_PATH.unlink()
