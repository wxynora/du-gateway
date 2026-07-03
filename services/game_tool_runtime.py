import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config import DATA_DIR
from utils.log import get_logger


logger = get_logger(__name__)

GAME_ID_RANDOM_IMITATOR_TD = "random_imitator_td"
GAME_TOOL_LOOP_MARKER = "game_tool_loop"
GAME_TOOL_SKIP_DYNAMIC_MEMORY_WRITE = "skip_dynamic_memory_write"
GAME_TOOL_SKIP_BODY_DELTA = "skip_body_delta"

GameExecutor = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class GameRegistration:
    game_id: str
    title: str
    tool: str
    commands: list[str]
    executor: GameExecutor
    save_root: Path


GAME_SAVE_ROOTS: dict[str, Path] = {GAME_ID_RANDOM_IMITATOR_TD: DATA_DIR / "random_imitator_td"}
_GAME_REGISTRY: dict[str, GameRegistration] = {}
_BUILTIN_GAMES_REGISTERED = False

_GAME_ALIASES = {
    "random-imitator-td": GAME_ID_RANDOM_IMITATOR_TD,
    "imitator-pvz": GAME_ID_RANDOM_IMITATOR_TD,
    "plants-vs-zombies": GAME_ID_RANDOM_IMITATOR_TD,
    "植物大战丧尸": GAME_ID_RANDOM_IMITATOR_TD,
}


def normalize_game_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().replace("_", "-")
    return _GAME_ALIASES.get(lowered, raw.lower().replace("-", "_"))


def register_game(
    *,
    game_id: str,
    title: str,
    tool: str,
    commands: list[str],
    executor: GameExecutor,
    save_root: Path,
    aliases: tuple[str, ...] = (),
) -> GameRegistration:
    normalized = normalize_game_id(game_id)
    if not normalized:
        raise ValueError("game_id is required")
    entry = GameRegistration(
        game_id=normalized,
        title=str(title or normalized).strip() or normalized,
        tool=str(tool or normalized).strip() or normalized,
        commands=list(commands or []),
        executor=executor,
        save_root=Path(save_root),
    )
    _GAME_REGISTRY[normalized] = entry
    for alias in aliases:
        key = str(alias or "").strip().lower().replace("_", "-")
        if key:
            _GAME_ALIASES[key] = normalized
    return entry


def _ensure_builtin_games_registered() -> None:
    global _BUILTIN_GAMES_REGISTERED
    if _BUILTIN_GAMES_REGISTERED:
        return
    _BUILTIN_GAMES_REGISTERED = True
    register_game(
        game_id=GAME_ID_RANDOM_IMITATOR_TD,
        title="植物大战丧尸随机版",
        tool="random_imitator_td",
        commands=["打开", "继续", "new_game", "cards", "种", "等待", "铲", "结束本局"],
        executor=_execute_random_imitator_td,
        save_root=GAME_SAVE_ROOTS[GAME_ID_RANDOM_IMITATOR_TD],
        aliases=("random-imitator-td", "imitator-pvz", "plants-vs-zombies", "植物大战丧尸"),
    )


def safe_save_id(save_id: str) -> str:
    raw = str(save_id or "default").strip() or "default"
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)[:80].strip("._-")
    return clean or "default"


def list_game_tools() -> list[dict[str, Any]]:
    _ensure_builtin_games_registered()
    return [
        {
            "game_id": entry.game_id,
            "title": entry.title,
            "tool": entry.tool,
            "commands": entry.commands,
        }
        for entry in sorted(_GAME_REGISTRY.values(), key=lambda item: item.game_id)
    ]


def execute_game_command(
    game_id: str,
    command: str,
    save_id: str = "default",
    *,
    save_root: Path | None = None,
    tool_name: str = "",
) -> dict[str, Any]:
    _ensure_builtin_games_registered()
    normalized = normalize_game_id(game_id)
    entry = _GAME_REGISTRY.get(normalized)
    if entry:
        return entry.executor(
            command=str(command or "").strip() or "打开",
            save_id=save_id,
            save_root=save_root if save_root is not None else entry.save_root,
            tool_name=tool_name or entry.tool,
        )
    return {
        "ok": False,
        "game_id": normalized or str(game_id or ""),
        "save_id": safe_save_id(save_id),
        "error": "UNKNOWN_GAME",
        "message": f"未知游戏: {game_id}",
    }


def game_tool_success_payload(
    *,
    game_id: str,
    tool_name: str,
    save_id: str,
    text: str,
    checkpoint: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool_name,
        "game_id": game_id,
        "save_id": safe_save_id(save_id),
        "text": text,
        "checkpoint": bool(checkpoint),
        GAME_TOOL_LOOP_MARKER: True,
        GAME_TOOL_SKIP_DYNAMIC_MEMORY_WRITE: True,
        GAME_TOOL_SKIP_BODY_DELTA: True,
    }


def game_tool_error_payload(
    *,
    game_id: str,
    tool_name: str,
    save_id: str,
    error: str,
    message: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool_name,
        "game_id": game_id,
        "save_id": safe_save_id(save_id),
        "error": error,
        "message": message,
        GAME_TOOL_LOOP_MARKER: True,
        GAME_TOOL_SKIP_DYNAMIC_MEMORY_WRITE: True,
        GAME_TOOL_SKIP_BODY_DELTA: True,
    }


def tool_result_has_game_marker(result: Any) -> bool:
    data = _coerce_result_dict(result)
    if not isinstance(data, dict):
        return False
    if data.get(GAME_TOOL_LOOP_MARKER) is True:
        return True
    return bool(data.get("game_id") and data.get(GAME_TOOL_SKIP_DYNAMIC_MEMORY_WRITE) and data.get(GAME_TOOL_SKIP_BODY_DELTA))


def game_tool_reply_text_from_result(result: Any) -> str:
    data = _coerce_result_dict(result)
    if not isinstance(data, dict) or not tool_result_has_game_marker(data):
        return ""
    if data.get("ok") is False:
        message = str(data.get("message") or data.get("error") or "游戏工具执行失败").strip()
        return f"游戏工具执行失败: {message}" if message else "游戏工具执行失败。"
    return str(data.get("text") or data.get("message") or "").strip()


def game_tool_reply_text_from_messages(messages: list) -> str:
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() != "tool":
            continue
        text = game_tool_reply_text_from_result(msg.get("content"))
        if text:
            return text
    return ""


def game_tool_checkpoint_from_result(result: Any) -> bool:
    data = _coerce_result_dict(result)
    if not isinstance(data, dict) or not tool_result_has_game_marker(data):
        return False
    checkpoint = data.get("checkpoint")
    if isinstance(checkpoint, str):
        return checkpoint.strip().lower() in {"1", "true", "yes", "y", "on"}
    return checkpoint is True


def game_tool_checkpoint_from_messages(messages: list) -> bool:
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() != "tool":
            continue
        if tool_result_has_game_marker(msg.get("content")):
            return game_tool_checkpoint_from_result(msg.get("content"))
    return False


def tool_trace_has_game_marker(tool_trace: list) -> bool:
    for item in tool_trace or []:
        if isinstance(item, dict) and tool_result_has_game_marker(item.get("result")):
            return True
    return False


def _coerce_result_dict(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except Exception:
            return None
        return data if isinstance(data, dict) else None
    return None


def _execute_random_imitator_td(
    *,
    command: str,
    save_id: str,
    save_root: Path | None,
    tool_name: str,
) -> dict[str, Any]:
    root = Path(save_root) if save_root is not None else GAME_SAVE_ROOTS[GAME_ID_RANDOM_IMITATOR_TD]
    save_path = root / f"{safe_save_id(save_id)}.json"
    try:
        from du_imitator_pvz.engine import ANTI_ADDICTION_PAUSE_PREFIX, cmd

        text = cmd(command, save_path=save_path)
        return game_tool_success_payload(
            game_id=GAME_ID_RANDOM_IMITATOR_TD,
            tool_name=tool_name,
            save_id=save_id,
            text=text,
            checkpoint=ANTI_ADDICTION_PAUSE_PREFIX in text,
        )
    except Exception as exc:
        logger.exception("game tool failed game_id=%s save_id=%s", GAME_ID_RANDOM_IMITATOR_TD, save_id)
        return game_tool_error_payload(
            game_id=GAME_ID_RANDOM_IMITATOR_TD,
            tool_name=tool_name,
            save_id=save_id,
            error="EXECUTION_FAILED",
            message=str(exc),
        )
