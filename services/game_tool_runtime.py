import json
import re
import shlex
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
GAME_TOOL_CHECKPOINT_INSTRUCTION = "由于防沉迷机制，暂时中止游戏回合。不要继续使用游戏工具，正常回复信息。"
GAME_TOOL_GAME_OVER_INSTRUCTION = "本局游戏已经结束。不要继续使用游戏工具，也不要立刻 new_game 或重开；正常回复本局结果。"
GAME_ACTIVE_SAVE_FILE = "_active_save.json"
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


def _write_active_save_id(root: Path, save_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _active_save_path(root).write_text(json.dumps({"save_id": safe_save_id(save_id)}, ensure_ascii=False), encoding="utf-8")


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


def _first_command_word(command: str) -> str:
    raw = str(command or "").strip()
    if not raw:
        return ""
    try:
        words = shlex.split(raw.replace("\n", " ", 1))
    except ValueError:
        return raw.split(maxsplit=1)[0].strip().lower()
    return str(words[0] if words else "").strip().lower()


def _is_new_game_command(command: str) -> bool:
    return _first_command_word(command) in {"new", "new_game", "newgame", "restart", "reset", "重开", "新游戏"}


def _find_pending_random_imitator_save_id(root: Path, preferred: list[str]) -> str:
    seen: set[str] = set()
    for save_id in preferred:
        safe_id = safe_save_id(save_id)
        if safe_id in seen:
            continue
        seen.add(safe_id)
        path = _save_path(root, safe_id)
        if path.exists() and _random_imitator_has_pending_pause(path):
            return safe_id
    if not root.exists():
        return ""
    candidates = []
    for path in root.glob("*.json"):
        if path.name == GAME_ACTIVE_SAVE_FILE:
            continue
        if _random_imitator_has_pending_pause(path):
            candidates.append(path)
    if not candidates:
        return ""
    newest = max(candidates, key=lambda item: item.stat().st_mtime)
    return newest.stem


def _resolve_random_imitator_save_id(root: Path, command: str, requested_save_id: str) -> str:
    requested = safe_save_id(requested_save_id)
    active = _read_active_save_id(root)
    if _is_new_game_command(command):
        return requested

    if active and active != requested:
        return active

    pending = _find_pending_random_imitator_save_id(root, [active, requested])
    if pending:
        return pending

    requested_path = _save_path(root, requested)
    if active and active != requested and not requested_path.exists():
        return active
    return requested


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
    resolved_save_id = _resolve_random_imitator_save_id(root, command, save_id)
    save_path = _save_path(root, resolved_save_id)
    try:
        from du_imitator_pvz.engine import ANTI_ADDICTION_PAUSE_PREFIX, cmd

        text = cmd(command, save_path=save_path)
        _write_active_save_id(root, resolved_save_id)
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
