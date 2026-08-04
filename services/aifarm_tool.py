from __future__ import annotations

import json
from typing import Any

from services.aifarm_bridge import AIFarmBridgeError, get_agent_mcp_tools, run_agent_action


AIFARM_TOOL_NAME = "farm"
AIFARM_TOOL_NAMES = (AIFARM_TOOL_NAME,)


def get_aifarm_tools_for_inject() -> list[dict[str, Any]]:
    """Read the bound public farm's current MCP schema without exposing its URL or key."""
    return [
        {
            "type": "function",
            "function": {
                "name": str(tool["name"]),
                "description": str(tool["description"]),
                "parameters": tool["inputSchema"],
            },
        }
        for tool in get_agent_mcp_tools()
    ]


def execute_aifarm_tool(arguments: dict[str, Any] | None) -> str:
    try:
        result = run_agent_action(arguments)
    except AIFarmBridgeError as exc:
        result = {"ok": False, "text": str(exc)}
    return json.dumps(result, ensure_ascii=False)
