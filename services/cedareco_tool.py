from __future__ import annotations

import json
from typing import Any

from services.cedareco_bridge import CedarEcoBridgeError, run_command


CEDARECO_TOOL_NAME = "cedareco"


def get_cedareco_tools_for_inject() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": CEDARECO_TOOL_NAME,
                "description": (
                    "经营你和辛玥共享的《瓶中生态》池塘。把完整游戏指令放进 command，"
                    "例如 new、help、observe、gaze、status、summon 水藻 50、wait 3；"
                    "支持用分号连续执行多条指令。先盲玩和观察，不要索要、读取或推测引擎参数。"
                    "辛玥在 App 观察窗完成灾害协作后，你下一次操作会收到一次协作通知。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "原样交给瓶中生态的完整指令；不知道可用指令时使用 help。",
                        },
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def execute_cedareco_tool(arguments: dict[str, Any] | None) -> str:
    command = arguments.get("command") if isinstance(arguments, dict) else ""
    try:
        result = run_command(command)
    except CedarEcoBridgeError as exc:
        result = {"ok": False, "text": str(exc)}
    return json.dumps(result, ensure_ascii=False)
