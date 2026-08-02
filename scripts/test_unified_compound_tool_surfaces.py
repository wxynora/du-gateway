from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _tool_map(tools: list[dict]) -> dict[str, dict]:
    return {
        str((tool.get("function") or {}).get("name") or ""): tool
        for tool in tools
        if isinstance(tool, dict)
    }


def _action_enum(tool: dict) -> list[str]:
    function = tool.get("function") or {}
    parameters = function.get("parameters") or {}
    properties = parameters.get("properties") or {}
    action = properties.get("action") or {}
    return list(action.get("enum") or [])


def test_compound_tool_declarations_replace_old_surfaces() -> None:
    from services import chat_tools
    from services import mcp_forum_tools

    old_enabled = mcp_forum_tools.MCP_ENABLED
    try:
        mcp_forum_tools.MCP_ENABLED = True
        chat = _tool_map(chat_tools.get_chat_tools_for_inject())
        device_schedule = _tool_map(mcp_forum_tools.get_forum_tools_for_inject(mode="chat"))
    finally:
        mcp_forum_tools.MCP_ENABLED = old_enabled

    assert "exchange_diary" in chat, chat.keys()
    assert "stay_with_du" in chat, chat.keys()
    assert not {
        "exchange_diary_create",
        "exchange_diary_list",
        "exchange_diary_read",
        "exchange_diary_comment_create",
        "stay_with_du_write",
        "stay_with_du_delete",
    }.intersection(chat), chat.keys()
    assert _action_enum(chat["exchange_diary"]) == ["create", "list", "read", "comment"]
    assert _action_enum(chat["stay_with_du"]) == ["write", "delete"]

    assert "du_schedule" in device_schedule, device_schedule.keys()
    assert not {
        "schedule_list",
        "schedule_create",
        "schedule_enable",
        "schedule_disable",
        "schedule_delete",
    }.intersection(device_schedule), device_schedule.keys()
    assert _action_enum(device_schedule["du_schedule"]) == ["list", "create", "enable", "disable", "delete"]
    assert {"create_system_alarm", "create_calendar_event", "open_app"}.issubset(device_schedule)


def test_normal_chat_surface_drops_from_38_to_30_tools() -> None:
    import config
    from pipeline import pipeline
    from services import mcp_forum_tools

    old_mcp_config = config.MCP_ENABLED
    old_websearch = config.WEBSEARCH_ENABLED
    old_mcp_module = mcp_forum_tools.MCP_ENABLED
    try:
        config.MCP_ENABLED = True
        config.WEBSEARCH_ENABLED = True
        mcp_forum_tools.MCP_ENABLED = True
        body = {"messages": [{"role": "user", "content": "你好"}]}
        body = pipeline.step_inject_gateway_tools(body)
        body = pipeline.step_inject_chat_tools(body)
        body = pipeline.step_inject_forum_tools(body)
        body = pipeline.step_inject_amap_mcp_tools(body)
        body = pipeline.step_inject_websearch_tools(body)
    finally:
        config.MCP_ENABLED = old_mcp_config
        config.WEBSEARCH_ENABLED = old_websearch
        mcp_forum_tools.MCP_ENABLED = old_mcp_module

    tools = _tool_map(body.get("tools") or [])
    assert len(tools) == 30, tools.keys()
    assert {"exchange_diary", "stay_with_du", "du_schedule", "search_memory", "open_app", "web_search"}.issubset(tools)


def test_exchange_diary_new_actions_reuse_old_execution_paths() -> None:
    from services import chat_tools

    mapping = {
        "create": "_execute_exchange_diary_create",
        "list": "_execute_exchange_diary_list",
        "read": "_execute_exchange_diary_read",
        "comment": "_execute_exchange_diary_comment_create",
    }
    originals = {attr: getattr(chat_tools, attr) for attr in mapping.values()}
    calls: list[tuple[str, dict]] = []
    try:
        for action, attr in mapping.items():
            setattr(
                chat_tools,
                attr,
                lambda args, action=action: calls.append((action, dict(args))) or f"{action}:ok",
            )
        for action in mapping:
            result = chat_tools.execute_tool(
                "exchange_diary",
                {"action": action, "content": "正文", "entry_id": "entry-1", "id": "entry-1"},
            )
            assert result == f"{action}:ok", (action, result)
    finally:
        for attr, value in originals.items():
            setattr(chat_tools, attr, value)

    assert [action for action, _args in calls] == list(mapping)
    assert all("action" not in args for _action, args in calls), calls


def test_stay_with_du_new_actions_and_old_names_share_storage_paths() -> None:
    from services import chat_tools
    from storage import r2_store

    old_add = r2_store.add_stay_with_du_entry
    old_delete = r2_store.delete_stay_with_du_entry
    calls: list[tuple[str, dict]] = []
    try:
        r2_store.add_stay_with_du_entry = lambda **kwargs: calls.append(("write", dict(kwargs))) or {"id": "stay-1"}
        r2_store.delete_stay_with_du_entry = lambda **kwargs: calls.append(("delete", dict(kwargs))) or {
            "id": "stay-1",
            "title": "电影",
        }
        assert chat_tools.execute_tool(
            "stay_with_du",
            {"action": "write", "kind": "movie_want", "title": "电影"},
        ).startswith("写入成功")
        assert chat_tools.execute_tool(
            "stay_with_du",
            {"action": "delete", "kind": "movie_want", "id": "stay-1"},
        ).startswith("删除成功")
        assert chat_tools.execute_tool(
            "stay_with_du_write",
            {"kind": "movie_want", "title": "旧名仍兼容"},
        ).startswith("写入成功")
    finally:
        r2_store.add_stay_with_du_entry = old_add
        r2_store.delete_stay_with_du_entry = old_delete

    assert [name for name, _args in calls] == ["write", "delete", "write"]


def test_du_schedule_new_actions_and_old_names_share_storage_paths() -> None:
    from services import mcp_forum_tools
    from services import schedule_runtime
    from storage import r2_store

    originals = {
        "get": r2_store.get_schedule_items,
        "create": r2_store.create_schedule_item,
        "enable": r2_store.enable_schedule_item,
        "disable": r2_store.disable_schedule_item,
        "delete": r2_store.delete_schedule_item,
        "notify": schedule_runtime.notify_schedule_changed,
    }
    calls: list[str] = []
    try:
        r2_store.get_schedule_items = lambda: [{"id": "schedule-1", "enabled": True}]
        r2_store.create_schedule_item = lambda **_kwargs: calls.append("create") or {"id": "schedule-1"}
        r2_store.enable_schedule_item = lambda _id: calls.append("enable") or True
        r2_store.disable_schedule_item = lambda _id: calls.append("disable") or True
        r2_store.delete_schedule_item = lambda _id: calls.append("delete") or True
        schedule_runtime.notify_schedule_changed = lambda: None

        listed = json.loads(mcp_forum_tools.execute_forum_tool("du_schedule", {"action": "list"}))
        created = json.loads(
            mcp_forum_tools.execute_forum_tool(
                "du_schedule",
                {"action": "create", "title": "渡的提醒", "target_role": "du"},
            )
        )
        enabled = json.loads(mcp_forum_tools.execute_forum_tool("du_schedule", {"action": "enable", "id": "schedule-1"}))
        disabled = json.loads(mcp_forum_tools.execute_forum_tool("du_schedule", {"action": "disable", "id": "schedule-1"}))
        deleted = json.loads(mcp_forum_tools.execute_forum_tool("du_schedule", {"action": "delete", "id": "schedule-1"}))
        old_deleted = json.loads(mcp_forum_tools.execute_forum_tool("schedule_delete", {"id": "schedule-1"}))
    finally:
        r2_store.get_schedule_items = originals["get"]
        r2_store.create_schedule_item = originals["create"]
        r2_store.enable_schedule_item = originals["enable"]
        r2_store.disable_schedule_item = originals["disable"]
        r2_store.delete_schedule_item = originals["delete"]
        schedule_runtime.notify_schedule_changed = originals["notify"]

    assert listed["ok"] and created["ok"] and enabled["ok"] and disabled["ok"] and deleted["ok"] and old_deleted["ok"]
    assert calls == ["create", "enable", "disable", "delete", "delete"], calls


def test_schedule_hint_uses_only_the_unified_name() -> None:
    import config
    from pipeline import pipeline
    from services import mcp_forum_tools

    old_config = config.MCP_ENABLED
    old_module = mcp_forum_tools.MCP_ENABLED
    try:
        config.MCP_ENABLED = True
        mcp_forum_tools.MCP_ENABLED = True
        body = pipeline.step_inject_forum_tools({"messages": [{"role": "user", "content": "你好"}]})
    finally:
        config.MCP_ENABLED = old_config
        mcp_forum_tools.MCP_ENABLED = old_module

    system_text = "\n".join(
        str(message.get("content") or "")
        for message in body.get("messages") or []
        if message.get("role") == "system"
    )
    assert "du_schedule(action=" in system_text, system_text
    assert "schedule_create" not in system_text, system_text
    assert "schedule_list" not in system_text, system_text


if __name__ == "__main__":
    test_compound_tool_declarations_replace_old_surfaces()
    test_normal_chat_surface_drops_from_38_to_30_tools()
    test_exchange_diary_new_actions_reuse_old_execution_paths()
    test_stay_with_du_new_actions_and_old_names_share_storage_paths()
    test_du_schedule_new_actions_and_old_names_share_storage_paths()
    test_schedule_hint_uses_only_the_unified_name()
    print("unified compound tool surface tests ok")
