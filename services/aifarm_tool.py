from __future__ import annotations

import json
from typing import Any

from services.aifarm_bridge import AIFarmBridgeError, run_agent_action


AIFARM_TOOL_NAME = "farm"
AIFARM_TOOL_NAMES = (AIFARM_TOOL_NAME,)


def get_aifarm_tools_for_inject() -> list[dict[str, Any]]:
    """Mirror aifarm-oss's one-tool MCP contract without exposing its private play URL."""
    return [
        {
            "type": "function",
            "function": {
                "name": AIFARM_TOOL_NAME,
                "description": (
                    "在你和辛玥的 AI 农场里执行一个动作，身份已由网关绑定，不要索要或输出链接、key、token。"
                    "动作名放 action，其余参数平铺在同级，例如 "
                    '{"action":"plant","common":3,"fantasy":3}、'
                    '{"action":"run","plant":{"common":3,"fantasy":3}}、'
                    '{"action":"harvest"}。串门时加 to:"对方门牌号"。'
                    "不知道动作或参数时先调 action=help；巡视用 action=status。"
                    "返回 text 末尾的 HUD 用于继续决策，需要结构化状态时加 detail=true。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": (
                                "动作名，如 help/status/run/plant/water/harvest/use/shop/bag/craft/"
                                "upgrade-land/explore/choose/roll/retreat/wander/visit/steal/message。"
                            ),
                        },
                    },
                    "required": ["action"],
                    "additionalProperties": True,
                },
            },
        }
    ]


def execute_aifarm_tool(arguments: dict[str, Any] | None) -> str:
    try:
        result = run_agent_action(arguments)
    except AIFarmBridgeError as exc:
        result = {"ok": False, "text": str(exc)}
    return json.dumps(result, ensure_ascii=False)
