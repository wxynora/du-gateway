import json
from typing import Any, List

from config import DATA_DIR
from services.game_tool_runtime import GAME_ID_RANDOM_IMITATOR_TD, execute_game_command


RANDOM_IMITATOR_TD_TOOL_NAME = "random_imitator_td"
RANDOM_IMITATOR_TD_TOOL_NAMES = (RANDOM_IMITATOR_TD_TOOL_NAME,)
SAVE_ROOT = DATA_DIR / "random_imitator_td"


def get_random_imitator_td_tools_for_inject() -> List[dict]:
    """Return the private random imitator tower-defense tool schema."""
    return [
        {
            "type": "function",
            "function": {
                "name": RANDOM_IMITATOR_TD_TOOL_NAME,
                "description": (
                    "运行随机模仿者文字塔防的一步指令，并返回当前事件、棋盘和状态。"
                    "每次只传玩家本轮决定；打开或继续时传 打开/继续/look，会优先读取当前存档。"
                    "只有玩家明确要重开时才用 new_game，随后用 cards 配置卡槽，再用种/等待/铲/结束本局等命令推进。"
                    "本工具固定使用单存档；不要尝试切换存档。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的游戏命令，如 打开、继续、look、new_game level=1 seed=demo、cards 模仿者 模仿者 向日葵、种 模仿者 3-4、等待 200。",
                        },
                    },
                    "required": ["command"],
                },
            },
        }
    ]


def execute_random_imitator_td_tool(arguments: dict | None) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    command = str(args.get("command") or "").strip() or "打开"
    payload = execute_game_command(
        GAME_ID_RANDOM_IMITATOR_TD,
        command,
        "default",
        save_root=SAVE_ROOT,
        tool_name=RANDOM_IMITATOR_TD_TOOL_NAME,
    )
    return json.dumps(payload, ensure_ascii=False)
