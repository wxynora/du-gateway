from __future__ import annotations

import json
from typing import Any

from services.travel_mcp_client import (
    TravelMcpUnavailable,
    call_travel_mcp_tool,
    result_text,
    travel_mcp_enabled,
)
from utils.log import get_logger


logger = get_logger(__name__)

TRAVEL_TOOL_NAME = "travel"
TRAVEL_ACTION_TO_UPSTREAM_TOOL = {
    "plan": "trip_plan",
    "start": "trip_start",
    "here": "trip_here",
    "go": "trip_go",
    "collect": "trip_collect",
    "postcard": "trip_postcard",
    "diary": "trip_diary",
    "return": "trip_return",
    "care_checkin": "care_checkin",
    "wallet_status": "wallet_status",
    "shelf": "trip_shelf",
}
_ACTION_ARGUMENTS = {
    "plan": ("dest", "style", "party"),
    "start": ("dest", "party", "style", "restart"),
    "here": (),
    "go": (),
    "collect": ("name", "line", "default_id", "image"),
    "postcard": ("line", "spot_id"),
    "diary": ("text", "title"),
    "return": (),
    "care_checkin": ("item", "note"),
    "wallet_status": (),
    "shelf": ("read_diary",),
}


def get_travel_tools_for_inject() -> list[dict[str, Any]]:
    if not travel_mcp_enabled():
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": TRAVEL_TOOL_NAME,
                "description": (
                    "旅行MCP。action 与上游工具一一对应："
                    "plan=trip_plan，start=trip_start，here=trip_here，go=trip_go，"
                    "collect=trip_collect，postcard=trip_postcard，diary=trip_diary，"
                    "return=trip_return，care_checkin=care_checkin，"
                    "wallet_status=wallet_status，shelf=trip_shelf。"
                    "工具返回中的游戏文案和状态按原文使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": list(TRAVEL_ACTION_TO_UPSTREAM_TOOL),
                        },
                        "dest": {"type": "string"},
                        "style": {
                            "type": "string",
                            "enum": ["青旅背包", "舒适", "轻奢", "豪奢"],
                        },
                        "party": {
                            "type": "string",
                            "enum": ["together", "solo"],
                        },
                        "restart": {"type": "boolean"},
                        "name": {"type": "string"},
                        "line": {"type": "string"},
                        "default_id": {"type": "string"},
                        "image": {"type": "string"},
                        "spot_id": {"type": "string"},
                        "text": {"type": "string"},
                        "title": {"type": "string"},
                        "item": {
                            "type": "string",
                            "enum": ["喝水", "吃药", "运动", "早睡", "吃得健康", "其他"],
                        },
                        "note": {"type": "string"},
                        "read_diary": {"type": "string"},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def _forced_party(context: dict | None) -> str:
    wakeup_kind = str((context or {}).get("wakeup_kind") or "").strip().lower()
    if wakeup_kind == "travel":
        return "together"
    if wakeup_kind == "proactive_game":
        return "solo"
    return ""


def execute_travel_tool(arguments: dict[str, Any] | None, *, context: dict | None = None) -> str:
    incoming = dict(arguments) if isinstance(arguments, dict) else {}
    action = str(incoming.get("action") or "").strip().lower()
    upstream_tool = TRAVEL_ACTION_TO_UPSTREAM_TOOL.get(action)
    if not upstream_tool:
        return json.dumps({"ok": False, "error": "TRAVEL_ACTION_INVALID"}, ensure_ascii=False)
    upstream_arguments = {
        key: incoming[key]
        for key in _ACTION_ARGUMENTS[action]
        if key in incoming
    }
    forced_party = _forced_party(context)
    if forced_party and action in {"plan", "start"}:
        upstream_arguments["party"] = forced_party
    try:
        result = call_travel_mcp_tool(upstream_tool, upstream_arguments)
        return result_text(result)
    except TravelMcpUnavailable:
        return json.dumps({"ok": False, "error": "TRAVEL_MCP_UNAVAILABLE"}, ensure_ascii=False)
    except Exception:
        logger.warning("travel_mcp_call_failed action=%s", action, exc_info=True)
        return json.dumps({"ok": False, "error": "TRAVEL_MCP_CALL_FAILED"}, ensure_ascii=False)
