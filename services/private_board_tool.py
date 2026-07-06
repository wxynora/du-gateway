import json
from typing import List

from config import DATA_DIR
from services.game_tool_runtime import GAME_ID_PRIVATE_BOARD, execute_game_command


PRIVATE_BOARD_TOOL_NAME = "private_board"
PRIVATE_BOARD_TOOL_NAMES = (PRIVATE_BOARD_TOOL_NAME,)
SAVE_ROOT = DATA_DIR / GAME_ID_PRIVATE_BOARD


def get_private_board_tools_for_inject() -> List[dict]:
    """Return the private board-game tool schema."""
    return [
        {
            "type": "function",
            "function": {
                "name": PRIVATE_BOARD_TOOL_NAME,
                "description": (
                    "运行涩涩走格棋的一步指令，并返回棋盘、状态、待处理任务和双方视角文本。"
                    "本工具只负责规则结算；人类玩家通过前端按钮参与，AI 玩家只在被要求时使用自然语言指令推动自己的回合。"
                    "常用命令：打开/status、roll、submit 内容、approve、reject、choose 选项、pass、new_game、end_game。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的游戏命令，如 status、roll、submit 任务描述、approve、reject、choose add_prop、pass、new_game。",
                        },
                    },
                    "required": ["command"],
                },
            },
        }
    ]


def execute_private_board_tool(arguments: dict | None) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    command = str(args.get("command") or "").strip() or "打开"
    payload = execute_game_command(
        GAME_ID_PRIVATE_BOARD,
        command,
        "default",
        save_root=SAVE_ROOT,
        tool_name=PRIVATE_BOARD_TOOL_NAME,
    )
    return json.dumps(payload, ensure_ascii=False)
