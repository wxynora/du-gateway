import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config import DATA_DIR
from utils.log import get_logger


logger = get_logger(__name__)

GAME_ID_RANDOM_IMITATOR_TD = "random_imitator_td"
GAME_ID_PRIVATE_BOARD = "private_board"
GAME_ID_CAPTIVITY_SIMULATOR = "captivity_simulator"
GAME_TOOL_LOOP_MARKER = "game_tool_loop"
GAME_TOOL_SKIP_DYNAMIC_MEMORY_WRITE = "skip_dynamic_memory_write"
GAME_TOOL_SKIP_BODY_DELTA = "skip_body_delta"
GAME_TOOL_CHECKPOINT_INSTRUCTION = "由于防沉迷机制，暂时中止游戏回合。不要继续使用游戏工具，正常回复信息。"
GAME_TOOL_GAME_OVER_INSTRUCTION = "本局游戏已经结束。不要继续使用游戏工具，也不要立刻 new_game 或重开；正常回复本局结果。"
GAME_ACTIVE_SAVE_FILE = "_active_save.json"
RANDOM_IMITATOR_SINGLE_SAVE_ID = "default"
RANDOM_IMITATOR_PENDING_KEY = "anti_addiction_pause_pending_turn"

GameExecutor = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class GameRegistration:
    game_id: str
    title: str
    tool: str
    commands: list[str]
    executor: GameExecutor
    save_root: Path


GAME_SAVE_ROOTS: dict[str, Path] = {
    GAME_ID_RANDOM_IMITATOR_TD: DATA_DIR / "random_imitator_td",
    GAME_ID_PRIVATE_BOARD: DATA_DIR / GAME_ID_PRIVATE_BOARD,
    GAME_ID_CAPTIVITY_SIMULATOR: DATA_DIR / GAME_ID_CAPTIVITY_SIMULATOR,
}
_GAME_REGISTRY: dict[str, GameRegistration] = {}
_BUILTIN_GAMES_REGISTERED = False

_GAME_ALIASES = {
    "random-imitator-td": GAME_ID_RANDOM_IMITATOR_TD,
    "imitator-pvz": GAME_ID_RANDOM_IMITATOR_TD,
    "plants-vs-zombies": GAME_ID_RANDOM_IMITATOR_TD,
    "植物大战丧尸": GAME_ID_RANDOM_IMITATOR_TD,
    "private-board": GAME_ID_PRIVATE_BOARD,
    "sex-board": GAME_ID_PRIVATE_BOARD,
    "涩涩走格棋": GAME_ID_PRIVATE_BOARD,
    "私密走格棋": GAME_ID_PRIVATE_BOARD,
    "瑟瑟桌游": GAME_ID_PRIVATE_BOARD,
    "captivity-simulator": GAME_ID_CAPTIVITY_SIMULATOR,
    "囚禁模拟器": GAME_ID_CAPTIVITY_SIMULATOR,
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
    register_game(
        game_id=GAME_ID_PRIVATE_BOARD,
        title="涩涩走格棋",
        tool="private_board",
        commands=["打开", "继续", "status", "new_game", "roll", "roll 3", "end_game"],
        executor=_execute_private_board,
        save_root=GAME_SAVE_ROOTS[GAME_ID_PRIVATE_BOARD],
        aliases=("private-board", "sex-board", "涩涩走格棋", "私密走格棋", "瑟瑟桌游"),
    )
    register_game(
        game_id=GAME_ID_CAPTIVITY_SIMULATOR,
        title="囚禁模拟器",
        tool="captivity_simulator",
        commands=[
            "打开",
            "继续",
            "status",
            "new_game",
            "plan_day",
            "respond_action",
            "choose_mood",
            "submit_process",
            "submit_process_reaction",
            "advance_day_action",
            "night_action",
            "view_monitor",
            "monitor_action",
            "schedule_escape_window",
            "resolve_escape_choice",
            "build_ending_seed",
            "submit_ending_materials",
            "submit_ending_text",
            "set_config",
            "export_log",
            "end_game",
        ],
        executor=_execute_captivity_simulator,
        save_root=GAME_SAVE_ROOTS[GAME_ID_CAPTIVITY_SIMULATOR],
        aliases=("captivity-simulator", "囚禁模拟器"),
    )


def safe_save_id(save_id: str) -> str:
    raw = str(save_id or "default").strip() or "default"
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)[:80].strip("._-")
    return clean or "default"


def _save_path(root: Path, save_id: str) -> Path:
    return root / f"{safe_save_id(save_id)}.json"


def _active_save_path(root: Path) -> Path:
    return root / GAME_ACTIVE_SAVE_FILE


def _read_active_save_id(root: Path) -> str:
    path = _active_save_path(root)
    if not path.exists():
        default_path = _save_path(root, "default")
        return "default" if default_path.exists() else ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "default" if _save_path(root, "default").exists() else ""
    active = safe_save_id(str(data.get("save_id") or ""))
    if _save_path(root, active).exists():
        return active
    return "default" if _save_path(root, "default").exists() else ""


def _read_save_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _random_imitator_has_pending_pause(path: Path) -> bool:
    data = _read_save_payload(path)
    return bool(data.get(RANDOM_IMITATOR_PENDING_KEY))


def _random_imitator_game_over(path: Path) -> tuple[bool, str]:
    data = _read_save_payload(path)
    engine = data.get("engine") if isinstance(data, dict) else None
    state = engine.get("state") if isinstance(engine, dict) else None
    if not isinstance(state, dict):
        return False, ""
    return bool(state.get("game_over")), str(state.get("result") or "").strip()


def _random_imitator_single_save_path(root: Path) -> Path:
    target = _save_path(root, RANDOM_IMITATOR_SINGLE_SAVE_ID)
    if target.exists():
        return target
    legacy_save_id = _read_active_save_id(root)
    if legacy_save_id and legacy_save_id != RANDOM_IMITATOR_SINGLE_SAVE_ID:
        legacy_path = _save_path(root, legacy_save_id)
        if legacy_path.exists():
            root.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(legacy_path, target)
            except Exception:
                logger.exception("failed to migrate random imitator active save save_id=%s", legacy_save_id)
    return target


def _random_imitator_single_save_id() -> str:
    return RANDOM_IMITATOR_SINGLE_SAVE_ID


def get_random_imitator_td_spectator_view(*, save_root: Path | None = None) -> dict[str, Any]:
    root = Path(save_root) if save_root is not None else GAME_SAVE_ROOTS[GAME_ID_RANDOM_IMITATOR_TD]
    save_path = _save_path(root, RANDOM_IMITATOR_SINGLE_SAVE_ID)
    from services.random_imitator_td_spectator import build_random_imitator_td_spectator_view

    return build_random_imitator_td_spectator_view(save_path)


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
    checkpoint_instruction: str = "",
    checkpoint_reason: str = "",
    game_over: bool = False,
    result: str = "",
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "tool": tool_name,
        "game_id": game_id,
        "save_id": safe_save_id(save_id),
        "text": text,
        "checkpoint": bool(checkpoint),
        "game_over": bool(game_over),
        "result": str(result or "").strip(),
        GAME_TOOL_LOOP_MARKER: True,
        GAME_TOOL_SKIP_DYNAMIC_MEMORY_WRITE: True,
        GAME_TOOL_SKIP_BODY_DELTA: True,
    }
    if checkpoint:
        payload["checkpoint_instruction"] = checkpoint_instruction or GAME_TOOL_CHECKPOINT_INSTRUCTION
    if checkpoint_reason:
        payload["checkpoint_reason"] = checkpoint_reason
    return payload


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
    resolved_save_id = _random_imitator_single_save_id()
    save_path = _random_imitator_single_save_path(root)
    try:
        from du_imitator_pvz.engine import ANTI_ADDICTION_PAUSE_PREFIX, cmd

        text = cmd(command, save_path=save_path)
        anti_addiction_checkpoint = ANTI_ADDICTION_PAUSE_PREFIX in text
        game_over, result = _random_imitator_game_over(save_path)
        checkpoint = anti_addiction_checkpoint or game_over
        checkpoint_instruction = GAME_TOOL_CHECKPOINT_INSTRUCTION if anti_addiction_checkpoint else GAME_TOOL_GAME_OVER_INSTRUCTION
        checkpoint_reason = "anti_addiction" if anti_addiction_checkpoint else "game_over" if game_over else ""
        return game_tool_success_payload(
            game_id=GAME_ID_RANDOM_IMITATOR_TD,
            tool_name=tool_name,
            save_id=resolved_save_id,
            text=text,
            checkpoint=checkpoint,
            checkpoint_instruction=checkpoint_instruction,
            checkpoint_reason=checkpoint_reason,
            game_over=game_over,
            result=result,
        )
    except Exception as exc:
        logger.exception("game tool failed game_id=%s save_id=%s", GAME_ID_RANDOM_IMITATOR_TD, resolved_save_id)
        return game_tool_error_payload(
            game_id=GAME_ID_RANDOM_IMITATOR_TD,
            tool_name=tool_name,
            save_id=resolved_save_id,
            error="EXECUTION_FAILED",
            message=str(exc),
        )


def _execute_private_board(
    *,
    command: str,
    save_id: str,
    save_root: Path | None,
    tool_name: str,
) -> dict[str, Any]:
    root = Path(save_root) if save_root is not None else GAME_SAVE_ROOTS[GAME_ID_PRIVATE_BOARD]
    resolved_save_id = safe_save_id(save_id)
    save_path = _save_path(root, resolved_save_id)
    try:
        from services.private_board_game import run_command

        result = run_command(command, save_path=save_path)
        payload = game_tool_success_payload(
            game_id=GAME_ID_PRIVATE_BOARD,
            tool_name=tool_name,
            save_id=resolved_save_id,
            text=str(result.get("du_text") or result.get("text") or ""),
            checkpoint=bool(result.get("game_over")),
            checkpoint_instruction=GAME_TOOL_GAME_OVER_INSTRUCTION if result.get("game_over") else "",
            checkpoint_reason="game_over" if result.get("game_over") else "",
            game_over=bool(result.get("game_over")),
            result=str(result.get("result") or ""),
        )
        payload.update(
            {
                "player_text": result.get("player_text") or "",
                "board": result.get("board") or {},
                "state": result.get("state") or {},
                "winner": result.get("winner") or "",
                "commands": result.get("commands") or [],
            }
        )
        return payload
    except Exception as exc:
        logger.exception("game tool failed game_id=%s save_id=%s", GAME_ID_PRIVATE_BOARD, resolved_save_id)
        return game_tool_error_payload(
            game_id=GAME_ID_PRIVATE_BOARD,
            tool_name=tool_name,
            save_id=resolved_save_id,
            error="EXECUTION_FAILED",
            message=str(exc),
        )


def _execute_captivity_simulator(
    *,
    command: str,
    save_id: str,
    save_root: Path | None,
    tool_name: str,
) -> dict[str, Any]:
    root = Path(save_root) if save_root is not None else GAME_SAVE_ROOTS[GAME_ID_CAPTIVITY_SIMULATOR]
    resolved_save_id = safe_save_id(save_id)
    save_path = _save_path(root, resolved_save_id)
    try:
        from services.captivity_simulator_game import run_command

        result = run_command(command, save_path=save_path)
        payload = game_tool_success_payload(
            game_id=GAME_ID_CAPTIVITY_SIMULATOR,
            tool_name=tool_name,
            save_id=resolved_save_id,
            text=str(result.get("text") or ""),
            checkpoint=bool(result.get("game_over")),
            checkpoint_instruction=GAME_TOOL_GAME_OVER_INSTRUCTION if result.get("game_over") else "",
            checkpoint_reason="game_over" if result.get("game_over") else "",
            game_over=bool(result.get("game_over")),
            result=str(result.get("result") or ""),
        )
        payload.update(
            {
                "player_text": result.get("player_text") or result.get("text") or "",
                "state": result.get("state") or {},
                "captive_view": result.get("captive_view") or {},
                "captor_view": result.get("captor_view") or {},
                "commands": result.get("commands") or [],
            }
        )
        if not result.get("ok", True):
            payload["ok"] = False
            payload["error"] = "COMMAND_FAILED"
        return payload
    except Exception as exc:
        logger.exception("game tool failed game_id=%s save_id=%s", GAME_ID_CAPTIVITY_SIMULATOR, resolved_save_id)
        return game_tool_error_payload(
            game_id=GAME_ID_CAPTIVITY_SIMULATOR,
            tool_name=tool_name,
            save_id=resolved_save_id,
            error="EXECUTION_FAILED",
            message=str(exc),
        )
