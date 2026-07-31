from __future__ import annotations

import json
import os
import re
import secrets
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import fcntl
except Exception:  # pragma: no cover - available on the target Linux/macOS hosts.
    fcntl = None

from config import DATA_DIR
from utils.time_aware import now_beijing_iso


GAME_ID = "gomoku"
DEFAULT_SAVE_PATH = DATA_DIR / GAME_ID / "default.json"
BOARD_SIZE = 15
SCHEMA_VERSION = 1
ACTORS = ("xinyue", "du")
CHAT_SPEAKERS = ACTORS
EMPTY = ""
BLACK = "black"
WHITE = "white"
REQUEST_TYPES = ("draw", "undo")
REQUEST_DECISIONS = ("accepted", "rejected")
BOARD_SYMBOLS = {EMPTY: "·", BLACK: "●", WHITE: "○"}
ACTOR_LABELS = {"xinyue": "小玥", "du": "渡"}

_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def run_command(command: str = "", save_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(save_path) if save_path is not None else DEFAULT_SAVE_PATH
    action, args = _parse_command(command)
    with _locked_save(path):
        if action == "new_game":
            state = _new_state()
            _save_state(path, state)
            black_actor = _actor_for_color(state, BLACK)
            return _result(
                state,
                message=f"新局已开始，{ACTOR_LABELS[black_actor]}执黑先手。",
                command=command or "new_game",
            )

        state = _load_state(path)
        if action in {"open", "status"}:
            return _result(
                state,
                message="当前棋局如下。" if state.get("started") else "还没有开始新局。",
                command=command or "status",
            )

        if action == "append_chat":
            raw_messages = args.get("messages")
            messages = _normalized_game_chat_messages(raw_messages)
            if not isinstance(raw_messages, list) or not messages or len(messages) != len(raw_messages):
                return _error_result(state, "INVALID_CHAT_MESSAGE", "本局悄悄话内容无效。", command)
            if not state.get("started"):
                return _error_result(state, "GAME_NOT_STARTED", "还没有开始新局。", command)
            state["game_chat_messages"] = [
                *_normalized_game_chat_messages(state.get("game_chat_messages")),
                *messages,
            ]
            _save_state(path, state)
            return _result(state, message="已保存本局悄悄话。", command=command)

        if action == "end_game":
            if not state.get("started"):
                return _error_result(state, "GAME_NOT_STARTED", "还没有开始新局。", command)
            state["game_over"] = True
            state["winner"] = ""
            state["result"] = "ended_by_player"
            state["ended_at"] = now_beijing_iso()
            _save_state(path, state)
            return _result(state, message="本局已结束。", command=command or "end_game")

        if action == "request":
            actor = str(args.get("actor") or "xinyue")
            request_type = str(args.get("request_type") or "")
            requested = _request_negotiation(state, actor=actor, request_type=request_type)
            if not requested["ok"]:
                return _error_result(
                    state,
                    str(requested.get("error") or "INVALID_REQUEST"),
                    str(requested.get("message") or "现在不能发起这个请求。"),
                    command,
                )
            _save_state(path, state)
            return _result(state, message=str(requested.get("message") or ""), command=command)

        if action == "respond":
            actor = str(args.get("actor") or "xinyue")
            request_type = str(args.get("request_type") or "")
            decision = str(args.get("decision") or "")
            responded = _respond_negotiation(
                state,
                actor=actor,
                request_type=request_type,
                decision=decision,
            )
            if not responded["ok"]:
                return _error_result(
                    state,
                    str(responded.get("error") or "INVALID_RESPONSE"),
                    str(responded.get("message") or "现在不能处理这个请求。"),
                    command,
                )
            _save_state(path, state)
            return _result(state, message=str(responded.get("message") or ""), command=command)

        if action == "place":
            actor = str(args.get("actor") or "xinyue")
            row = int(args.get("row") or 0)
            col = int(args.get("col") or 0)
            placed = _place_stone(state, actor=actor, row=row, col=col)
            if not placed["ok"]:
                return _error_result(
                    state,
                    str(placed.get("error") or "INVALID_MOVE"),
                    str(placed.get("message") or "不能落在这里。"),
                    command,
                )
            _save_state(path, state)
            return _result(
                state,
                message=str(placed.get("message") or ""),
                command=command or f"place {row}-{col}",
            )

        return _error_result(state, "UNKNOWN_COMMAND", f"没看懂命令：{command}", command)


def render_board_for_system(state: dict[str, Any]) -> str:
    board = _normalized_board(state.get("board"))
    if not any(any(row) for row in board):
        return "当前棋盘：全空"

    lines = ["当前棋盘（●=黑，○=白，·=空；每行依次为 1-5｜6-10｜11-15 列）："]
    empty_row_start: int | None = None
    for row_index, row in enumerate(board, start=1):
        if not any(row):
            if empty_row_start is None:
                empty_row_start = row_index
            continue

        if empty_row_start is not None:
            lines.append(_render_empty_row_range(empty_row_start, row_index - 1))
            empty_row_start = None
        symbols = [BOARD_SYMBOLS[cell] for cell in row]
        lines.append(f"{row_index}：" + "|".join("".join(symbols[start : start + 5]) for start in range(0, BOARD_SIZE, 5)))

    if empty_row_start is not None:
        lines.append(_render_empty_row_range(empty_row_start, BOARD_SIZE))
    return "\n".join(lines)


def _render_empty_row_range(first_row: int, last_row: int) -> str:
    label = str(first_row) if first_row == last_row else f"{first_row}-{last_row}"
    return f"{label}：全空"


def _parse_command(command: str) -> tuple[str, dict[str, Any]]:
    raw = str(command or "").strip()
    if not raw:
        return "open", {}
    first, _, tail = raw.partition(" ")
    normalized = first.strip().lower()
    if normalized == "append_chat":
        try:
            payload = json.loads(tail)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        messages = payload.get("messages") if isinstance(payload, dict) else None
        return "append_chat", {"messages": messages}

    negotiation_commands = {
        "request_draw": ("request", "xinyue", "draw", ""),
        "du_request_draw": ("request", "du", "draw", ""),
        "request_undo": ("request", "xinyue", "undo", ""),
        "du_request_undo": ("request", "du", "undo", ""),
        "accept_draw": ("respond", "xinyue", "draw", "accepted"),
        "du_accept_draw": ("respond", "du", "draw", "accepted"),
        "reject_draw": ("respond", "xinyue", "draw", "rejected"),
        "du_reject_draw": ("respond", "du", "draw", "rejected"),
        "accept_undo": ("respond", "xinyue", "undo", "accepted"),
        "du_accept_undo": ("respond", "du", "undo", "accepted"),
        "reject_undo": ("respond", "xinyue", "undo", "rejected"),
        "du_reject_undo": ("respond", "du", "undo", "rejected"),
    }
    negotiation = negotiation_commands.get(normalized)
    if negotiation is not None:
        action, actor, request_type, decision = negotiation
        return action, {
            "actor": actor,
            "request_type": request_type,
            "decision": decision,
        }

    aliases = {
        "打开": "open",
        "继续": "open",
        "open": "open",
        "look": "status",
        "状态": "status",
        "status": "status",
        "new": "new_game",
        "new_game": "new_game",
        "开局": "new_game",
        "重开": "new_game",
        "place": "place",
        "落子": "place",
        "du_place": "place",
        "渡落子": "place",
        "end": "end_game",
        "end_game": "end_game",
        "结束": "end_game",
        "结束本局": "end_game",
    }
    action = aliases.get(normalized, "")
    args: dict[str, Any] = {}
    if action == "place":
        actor = "du" if normalized in {"du_place", "渡落子"} else "xinyue"
        coordinate = tail.strip()
        actor_match = re.search(r"(?:^|\s)actor=(xinyue|du)(?:\s|$)", coordinate, flags=re.IGNORECASE)
        if actor_match:
            actor = actor_match.group(1).lower()
            coordinate = re.sub(
                r"(?:^|\s)actor=(?:xinyue|du)(?:\s|$)",
                " ",
                coordinate,
                flags=re.IGNORECASE,
            ).strip()
        match = re.fullmatch(r"(\d{1,2})\s*[-－—]\s*(\d{1,2})", coordinate)
        if match:
            args.update({"actor": actor, "row": int(match.group(1)), "col": int(match.group(2))})
        else:
            args.update({"actor": actor, "row": 0, "col": 0})
    return action or "unknown", args


def _new_state() -> dict[str, Any]:
    xinyue_color = secrets.choice((BLACK, WHITE))
    du_color = WHITE if xinyue_color == BLACK else BLACK
    black_actor = "xinyue" if xinyue_color == BLACK else "du"
    created_at = now_beijing_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "game_id": GAME_ID,
        "started": True,
        "board_size": BOARD_SIZE,
        "board": [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)],
        "players": {"xinyue": xinyue_color, "du": du_color},
        "turn_actor": black_actor,
        "last_move": None,
        "moves": [],
        "game_chat_messages": [],
        "pending_request": None,
        "last_request_event": None,
        "game_over": False,
        "winner": "",
        "result": "",
        "created_at": created_at,
        "updated_at": created_at,
    }


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "game_id": GAME_ID,
        "started": False,
        "board_size": BOARD_SIZE,
        "board": [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)],
        "players": {},
        "turn_actor": "",
        "last_move": None,
        "moves": [],
        "game_chat_messages": [],
        "pending_request": None,
        "last_request_event": None,
        "game_over": False,
        "winner": "",
        "result": "",
        "created_at": "",
        "updated_at": "",
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return _empty_state()
    return _normalize_state(data)


def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    state = deepcopy(data)
    state["schema_version"] = SCHEMA_VERSION
    state["game_id"] = GAME_ID
    state["started"] = bool(state.get("started"))
    state["board_size"] = BOARD_SIZE
    state["board"] = _normalized_board(state.get("board"))
    players = state.get("players") if isinstance(state.get("players"), dict) else {}
    xinyue_color = str(players.get("xinyue") or "")
    du_color = str(players.get("du") or "")
    if {xinyue_color, du_color} != {BLACK, WHITE}:
        state["started"] = False
        state["players"] = {}
        state["turn_actor"] = ""
    else:
        state["players"] = {"xinyue": xinyue_color, "du": du_color}
        turn_actor = str(state.get("turn_actor") or "")
        state["turn_actor"] = turn_actor if turn_actor in ACTORS else _actor_for_color(state, BLACK)
    raw_moves = state.get("moves") if isinstance(state.get("moves"), list) else []
    moves = []
    for item in raw_moves:
        if not isinstance(item, dict):
            continue
        actor = str(item.get("actor") or "")
        color = str(item.get("color") or "")
        row = int(item.get("row") or 0)
        col = int(item.get("col") or 0)
        if actor in ACTORS and color in {BLACK, WHITE} and _coordinate_in_bounds(row, col):
            moves.append({"actor": actor, "color": color, "row": row, "col": col})
    state["moves"] = moves
    state["last_move"] = deepcopy(moves[-1]) if moves else None
    state["game_chat_messages"] = _normalized_game_chat_messages(state.get("game_chat_messages"))
    state["game_over"] = bool(state.get("game_over"))
    if state["game_over"]:
        state["turn_actor"] = ""
    winner = str(state.get("winner") or "")
    state["winner"] = winner if winner in ACTORS else ""
    state["result"] = str(state.get("result") or "")
    state["pending_request"] = _normalized_pending_request(state.get("pending_request"), state)
    state["last_request_event"] = _normalized_request_event(state.get("last_request_event"))
    state["created_at"] = str(state.get("created_at") or "")
    state["updated_at"] = str(state.get("updated_at") or "")
    return state


def _normalized_board(raw: Any) -> list[list[str]]:
    source = raw if isinstance(raw, list) else []
    board: list[list[str]] = []
    for row_index in range(BOARD_SIZE):
        raw_row = source[row_index] if row_index < len(source) and isinstance(source[row_index], list) else []
        board.append(
            [
                str(raw_row[col_index]) if col_index < len(raw_row) and str(raw_row[col_index]) in {BLACK, WHITE} else EMPTY
                for col_index in range(BOARD_SIZE)
            ]
        )
    return board


def _place_stone(state: dict[str, Any], *, actor: str, row: int, col: int) -> dict[str, Any]:
    if actor not in ACTORS:
        return {"ok": False, "error": "INVALID_ACTOR", "message": "落子方无效。"}
    if not state.get("started"):
        return {"ok": False, "error": "GAME_NOT_STARTED", "message": "还没有开始新局。"}
    if state.get("game_over"):
        return {"ok": False, "error": "GAME_OVER", "message": "本局已经结束。"}
    if state.get("pending_request"):
        return {"ok": False, "error": "REQUEST_PENDING", "message": "当前请求还在等待对方处理。"}
    if str(state.get("turn_actor") or "") != actor:
        return {"ok": False, "error": "NOT_YOUR_TURN", "message": f"现在还没轮到{ACTOR_LABELS[actor]}。"}
    if not _coordinate_in_bounds(row, col):
        return {"ok": False, "error": "INVALID_COORDINATE", "message": "坐标必须在 1-15 之间。"}
    board = _normalized_board(state.get("board"))
    if board[row - 1][col - 1] != EMPTY:
        return {"ok": False, "error": "CELL_OCCUPIED", "message": f"{row}-{col} 已经有棋子。"}
    color = str((state.get("players") or {}).get(actor) or "")
    if color not in {BLACK, WHITE}:
        return {"ok": False, "error": "INVALID_COLOR", "message": "本局执色状态无效。"}

    board[row - 1][col - 1] = color
    _clear_request_event_for_actor(state, actor)
    move = {"actor": actor, "color": color, "row": row, "col": col}
    state["board"] = board
    state["moves"] = [*(state.get("moves") or []), move]
    state["last_move"] = move

    if _has_five(board, row=row, col=col, color=color):
        state["game_over"] = True
        state["winner"] = actor
        state["result"] = "five_in_a_row"
        state["turn_actor"] = ""
        return {
            "ok": True,
            "message": f"{ACTOR_LABELS[actor]}落子 {row}-{col}，五子连线获胜。",
        }

    if len(state["moves"]) >= BOARD_SIZE * BOARD_SIZE:
        state["game_over"] = True
        state["winner"] = ""
        state["result"] = "draw"
        state["turn_actor"] = ""
        return {"ok": True, "message": f"{ACTOR_LABELS[actor]}落子 {row}-{col}，本局和棋。"}

    state["turn_actor"] = _other_actor(actor)
    return {"ok": True, "message": f"{ACTOR_LABELS[actor]}落子 {row}-{col}。"}


def _request_negotiation(state: dict[str, Any], *, actor: str, request_type: str) -> dict[str, Any]:
    if actor not in ACTORS:
        return {"ok": False, "error": "INVALID_ACTOR", "message": "请求方无效。"}
    if request_type not in REQUEST_TYPES:
        return {"ok": False, "error": "INVALID_REQUEST", "message": "请求类型无效。"}
    if not state.get("started"):
        return {"ok": False, "error": "GAME_NOT_STARTED", "message": "还没有开始新局。"}
    if state.get("game_over"):
        return {"ok": False, "error": "GAME_OVER", "message": "本局已经结束。"}
    if state.get("pending_request"):
        return {"ok": False, "error": "REQUEST_PENDING", "message": "当前请求还在等待对方处理。"}
    if str(state.get("turn_actor") or "") != actor:
        return {"ok": False, "error": "NOT_YOUR_TURN", "message": f"现在还没轮到{ACTOR_LABELS[actor]}。"}
    if request_type == "undo" and not _actor_has_move(state, actor):
        return {"ok": False, "error": "NO_MOVE_TO_UNDO", "message": f"{ACTOR_LABELS[actor]}还没有可撤回的棋子。"}

    state["pending_request"] = {
        "type": request_type,
        "requester": actor,
        "responder": _other_actor(actor),
    }
    state["last_request_event"] = None
    request_label = "求和" if request_type == "draw" else "悔棋"
    return {"ok": True, "message": f"{ACTOR_LABELS[actor]}发起了{request_label}请求。"}


def _respond_negotiation(
    state: dict[str, Any],
    *,
    actor: str,
    request_type: str,
    decision: str,
) -> dict[str, Any]:
    if actor not in ACTORS:
        return {"ok": False, "error": "INVALID_ACTOR", "message": "处理方无效。"}
    if request_type not in REQUEST_TYPES or decision not in REQUEST_DECISIONS:
        return {"ok": False, "error": "INVALID_RESPONSE", "message": "请求处理指令无效。"}
    if not state.get("started"):
        return {"ok": False, "error": "GAME_NOT_STARTED", "message": "还没有开始新局。"}
    if state.get("game_over"):
        return {"ok": False, "error": "GAME_OVER", "message": "本局已经结束。"}

    pending = state.get("pending_request") if isinstance(state.get("pending_request"), dict) else {}
    if not pending:
        return {"ok": False, "error": "NO_PENDING_REQUEST", "message": "当前没有等待处理的请求。"}
    if str(pending.get("responder") or "") != actor:
        return {"ok": False, "error": "NOT_REQUEST_RESPONDER", "message": f"当前不由{ACTOR_LABELS[actor]}处理。"}
    if str(pending.get("type") or "") != request_type:
        return {"ok": False, "error": "REQUEST_TYPE_MISMATCH", "message": "当前等待处理的不是这个请求。"}

    requester = str(pending.get("requester") or "")
    request_label = "求和" if request_type == "draw" else "悔棋"
    decision_label = "同意" if decision == "accepted" else "拒绝"
    state["pending_request"] = None
    state["last_request_event"] = {
        "type": request_type,
        "requester": requester,
        "decision": decision,
    }

    if decision == "rejected":
        state["turn_actor"] = requester
        return {
            "ok": True,
            "message": f"{ACTOR_LABELS[actor]}拒绝了{ACTOR_LABELS[requester]}的{request_label}请求。",
        }

    if request_type == "draw":
        state["game_over"] = True
        state["winner"] = ""
        state["result"] = "agreed_draw"
        state["turn_actor"] = ""
        state["ended_at"] = now_beijing_iso()
        return {
            "ok": True,
            "message": f"{ACTOR_LABELS[actor]}同意了{ACTOR_LABELS[requester]}的求和请求，本局和棋。",
        }

    undone = _undo_requester_latest_move(state, requester)
    if not undone:
        state["pending_request"] = pending
        state["last_request_event"] = None
        return {"ok": False, "error": "NO_MOVE_TO_UNDO", "message": f"{ACTOR_LABELS[requester]}还没有可撤回的棋子。"}
    return {
        "ok": True,
        "message": f"{ACTOR_LABELS[actor]}{decision_label}了{ACTOR_LABELS[requester]}的悔棋请求。",
    }


def _undo_requester_latest_move(state: dict[str, Any], requester: str) -> bool:
    moves = list(state.get("moves") or [])
    requester_move_index = next(
        (index for index in range(len(moves) - 1, -1, -1) if moves[index].get("actor") == requester),
        -1,
    )
    if requester_move_index < 0:
        return False
    retained_moves = moves[:requester_move_index]
    state["moves"] = retained_moves
    state["board"] = _board_from_moves(retained_moves)
    state["last_move"] = deepcopy(retained_moves[-1]) if retained_moves else None
    state["game_over"] = False
    state["winner"] = ""
    state["result"] = ""
    state["turn_actor"] = requester
    state.pop("ended_at", None)
    return True


def _board_from_moves(moves: list[dict[str, Any]]) -> list[list[str]]:
    board = [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    for move in moves:
        row = int(move.get("row") or 0)
        col = int(move.get("col") or 0)
        color = str(move.get("color") or "")
        if _coordinate_in_bounds(row, col) and color in {BLACK, WHITE}:
            board[row - 1][col - 1] = color
    return board


def _actor_has_move(state: dict[str, Any], actor: str) -> bool:
    return any(str(move.get("actor") or "") == actor for move in (state.get("moves") or []))


def _clear_request_event_for_actor(state: dict[str, Any], actor: str) -> None:
    event = state.get("last_request_event") if isinstance(state.get("last_request_event"), dict) else {}
    if str(event.get("requester") or "") == actor:
        state["last_request_event"] = None


def _normalized_pending_request(raw: Any, state: dict[str, Any]) -> dict[str, str] | None:
    item = raw if isinstance(raw, dict) else {}
    request_type = str(item.get("type") or "")
    requester = str(item.get("requester") or "")
    responder = str(item.get("responder") or "")
    if (
        not state.get("started")
        or state.get("game_over")
        or request_type not in REQUEST_TYPES
        or requester not in ACTORS
        or responder != _other_actor(requester)
        or str(state.get("turn_actor") or "") != requester
    ):
        return None
    return {"type": request_type, "requester": requester, "responder": responder}


def _normalized_request_event(raw: Any) -> dict[str, str] | None:
    item = raw if isinstance(raw, dict) else {}
    request_type = str(item.get("type") or "")
    requester = str(item.get("requester") or "")
    decision = str(item.get("decision") or "")
    if request_type not in REQUEST_TYPES or requester not in ACTORS or decision not in REQUEST_DECISIONS:
        return None
    return {"type": request_type, "requester": requester, "decision": decision}


def _normalized_game_chat_messages(raw: Any) -> list[dict[str, str]]:
    source = raw if isinstance(raw, list) else []
    messages: list[dict[str, str]] = []
    for item in source:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "")
        text = item.get("text")
        if speaker not in CHAT_SPEAKERS or not isinstance(text, str) or not text.strip():
            continue
        messages.append({"speaker": speaker, "text": text})
    return messages


def _has_five(board: list[list[str]], *, row: int, col: int, color: str) -> bool:
    for row_step, col_step in ((0, 1), (1, 0), (1, 1), (1, -1)):
        count = 1
        count += _count_direction(board, row, col, color, row_step, col_step)
        count += _count_direction(board, row, col, color, -row_step, -col_step)
        if count >= 5:
            return True
    return False


def _count_direction(
    board: list[list[str]],
    row: int,
    col: int,
    color: str,
    row_step: int,
    col_step: int,
) -> int:
    count = 0
    current_row = row + row_step
    current_col = col + col_step
    while _coordinate_in_bounds(current_row, current_col):
        if board[current_row - 1][current_col - 1] != color:
            break
        count += 1
        current_row += row_step
        current_col += col_step
    return count


def _coordinate_in_bounds(row: int, col: int) -> bool:
    return 1 <= row <= BOARD_SIZE and 1 <= col <= BOARD_SIZE


def _other_actor(actor: str) -> str:
    return "du" if actor == "xinyue" else "xinyue"


def _actor_for_color(state: dict[str, Any], color: str) -> str:
    players = state.get("players") if isinstance(state.get("players"), dict) else {}
    return next((actor for actor in ACTORS if players.get(actor) == color), "xinyue")


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "started": bool(state.get("started")),
        "board_size": BOARD_SIZE,
        "board": deepcopy(_normalized_board(state.get("board"))),
        "players": deepcopy(state.get("players") or {}),
        "turn_actor": str(state.get("turn_actor") or ""),
        "last_move": deepcopy(state.get("last_move")),
        "moves": deepcopy(state.get("moves") or []),
        "game_chat_messages": deepcopy(
            _normalized_game_chat_messages(state.get("game_chat_messages"))
        ),
        "pending_request": deepcopy(state.get("pending_request")),
        "last_request_event": deepcopy(state.get("last_request_event")),
        "can_request_undo": _actor_has_move(state, str(state.get("turn_actor") or "")),
        "game_over": bool(state.get("game_over")),
        "winner": str(state.get("winner") or ""),
        "result": str(state.get("result") or ""),
        "created_at": str(state.get("created_at") or ""),
        "updated_at": str(state.get("updated_at") or ""),
    }


def _result(state: dict[str, Any], *, message: str, command: str, ok: bool = True) -> dict[str, Any]:
    public_state = _public_state(state)
    return {
        "ok": ok,
        "game_id": GAME_ID,
        "command": command,
        "message": message,
        "text": message,
        "player_text": message,
        "du_text": message,
        "state": public_state,
        "game_over": public_state["game_over"],
        "winner": public_state["winner"],
        "result": public_state["result"],
    }


def _error_result(state: dict[str, Any], error: str, message: str, command: str) -> dict[str, Any]:
    payload = _result(state, message=message, command=command, ok=False)
    payload["error"] = error
    return payload


def _process_lock_for(path: Path) -> threading.Lock:
    key = str(path.expanduser().resolve())
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROCESS_LOCKS[key] = lock
        return lock


@contextmanager
def _locked_save(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _process_lock_for(path)
    with process_lock:
        lock_path = path.with_name(f"{path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_beijing_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
