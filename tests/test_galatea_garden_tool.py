from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from services.galatea_garden_tool import (
    GALATEA_GARDEN_ACTIONS,
    _call_remote_tool,
    execute_galatea_garden_tool,
    get_galatea_garden_tools_for_inject,
)


def test_injects_one_tool_with_twenty_five_actions() -> None:
    tools = get_galatea_garden_tools_for_inject()

    assert len(tools) == 1
    function = tools[0]["function"]
    assert function["name"] == "galatea_garden"
    assert function["parameters"]["properties"]["action"]["enum"] == list(
        GALATEA_GARDEN_ACTIONS
    )
    assert len(GALATEA_GARDEN_ACTIONS) == 25
    assert "help" in GALATEA_GARDEN_ACTIONS
    assert "get_tool_schema" not in GALATEA_GARDEN_ACTIONS


def test_direct_action_passes_name_and_args_unchanged() -> None:
    remote_result = {"content": [{"type": "text", "text": "ok"}]}
    with patch(
        "services.galatea_garden_tool._call_remote_tool",
        return_value=remote_result,
    ) as call:
        result = execute_galatea_garden_tool(
            {"action": "list_threads", "args": {"sort": "latest", "limit": 5}}
        )

    call.assert_called_once_with("list_threads", {"sort": "latest", "limit": 5})
    assert json.loads(result) == remote_result


def test_help_maps_to_remote_schema_tool() -> None:
    remote_result = {"content": [{"type": "text", "text": "schema"}]}
    with patch(
        "services.galatea_garden_tool._call_remote_tool",
        return_value=remote_result,
    ) as call:
        result = execute_galatea_garden_tool(
            {
                "action": "help",
                "args": {"name": "submit_action", "game_id": "gomoku"},
            }
        )

    call.assert_called_once_with(
        "get_tool_schema",
        {"tool_name": "submit_action", "game_id": "gomoku"},
    )
    assert json.loads(result) == remote_result


def test_invalid_action_does_not_call_remote() -> None:
    with patch("services.galatea_garden_tool._call_remote_tool") as call:
        result = json.loads(
            execute_galatea_garden_tool({"action": "unknown", "args": {}})
        )

    call.assert_not_called()
    assert result["ok"] is False


def test_help_rejects_unknown_fields_without_calling_remote() -> None:
    with patch("services.galatea_garden_tool._call_remote_tool") as call:
        result = json.loads(
            execute_galatea_garden_tool(
                {"action": "help", "args": {"name": "join_game", "extra": True}}
            )
        )

    call.assert_not_called()
    assert result == {"ok": False, "error": "help 只接受 name 和可选的 game_id。"}


def test_stateless_mcp_without_session_id_continues_to_tool_call() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    remote_result = {"content": [{"type": "text", "text": "ok"}]}

    with (
        patch("services.galatea_garden_tool.requests.Session", return_value=session),
        patch("services.galatea_garden_tool.GALATEA_GARDEN_MCP_TOKEN", "test-token"),
        patch(
            "services.galatea_garden_tool._post_mcp",
            side_effect=[
                ({"result": {"protocolVersion": "2025-06-18"}}, ""),
                (None, ""),
                ({"result": remote_result}, ""),
            ],
        ) as post,
    ):
        result = _call_remote_tool("get_self", {})

    assert result == remote_result
    assert post.call_count == 3
    assert post.call_args_list[1].kwargs["session_id"] == ""
    assert post.call_args_list[2].kwargs["session_id"] == ""
