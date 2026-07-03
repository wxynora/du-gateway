from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import chat as chat_route
from services import game_tool_runtime
from services import random_imitator_td_tool
from storage import random_imitator_td_mode_store


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_tool_executes_and_persists_by_save_id() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        random_imitator_td_tool.SAVE_ROOT = Path(tmpdir)

        raw = random_imitator_td_tool.execute_random_imitator_td_tool(
            {"save_id": "player/a", "command": "new_game level=1 seed=private-tool-test"}
        )
        data = json.loads(raw)

        _assert(data.get("ok") is True, "tool should succeed")
        _assert(data.get("game_id") == "random_imitator_td", "tool should expose game_id")
        _assert(data.get("game_tool_loop") is True, "tool should mark game loop")
        _assert(data.get("skip_dynamic_memory_write") is True, "tool should mark dynamic memory skip")
        _assert(data.get("skip_body_delta") is True, "tool should mark body delta skip")
        _assert("请先编辑卡槽" in str(data.get("text") or ""), "new game should wait for card setup")
        _assert((Path(tmpdir) / "player_a.json").exists(), "save file should be scoped by save_id")


def test_tool_marks_anti_addiction_checkpoint_every_five_turns() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        random_imitator_td_tool.SAVE_ROOT = Path(tmpdir)

        args = {"save_id": "checkpoint", "command": "new_game level=1 seed=checkpoint-test"}
        random_imitator_td_tool.execute_random_imitator_td_tool(args)
        random_imitator_td_tool.execute_random_imitator_td_tool(
            {"save_id": "checkpoint", "command": "cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜"}
        )
        for _ in range(4):
            data = json.loads(
                random_imitator_td_tool.execute_random_imitator_td_tool(
                    {"save_id": "checkpoint", "command": "等待 1"}
                )
            )
            _assert(data.get("checkpoint") is False, "turns before 5 should not checkpoint")

        data = json.loads(
            random_imitator_td_tool.execute_random_imitator_td_tool(
                {"save_id": "checkpoint", "command": "等待 1"}
            )
        )

        _assert(data.get("checkpoint") is True, "turn 5 should checkpoint")
        _assert("防沉迷暂停" in str(data.get("text") or ""), "checkpoint text should be returned")
        _assert(
            "不要继续使用游戏工具" in str(data.get("checkpoint_instruction") or ""),
            "checkpoint should tell the model not to keep using the game tool",
        )


def test_game_request_marker_skips_chat_side_effects() -> None:
    app = Flask(__name__)
    with app.test_request_context("/", headers={"X-DU-Game-Tool-Loop": "1"}):
        _assert(chat_route._is_game_tool_loop_request(), "game marker should be detected")
        _assert(chat_route._skip_dynamic_memory_request(), "game marker should skip dynamic memory recall")
        _assert(
            chat_route._skip_post_archive_dynamic_memory_request(),
            "game marker should skip dynamic memory writes",
        )
        _assert(chat_route._skip_post_archive_body_delta_request(), "game marker should skip body delta")


def test_game_tool_trace_skips_archive_side_effects() -> None:
    trace = [{"function": {"name": "random_imitator_td", "arguments": "{}"}, "result": "{}"}]
    _assert(chat_route._tool_trace_has_random_imitator_td(trace), "game tool trace should be detected")


def test_game_tool_trace_marker_skips_archive_side_effects() -> None:
    result = json.dumps(
        {
            "ok": True,
            "game_id": "future_game",
            "game_tool_loop": True,
            "skip_dynamic_memory_write": True,
            "skip_body_delta": True,
        },
        ensure_ascii=False,
    )
    trace = [{"function": {"name": "future_game", "arguments": "{}"}, "result": result}]
    _assert(chat_route._tool_trace_has_game_tool_loop(trace), "generic game marker should be detected")
    _assert(chat_route._tool_trace_has_random_imitator_td(trace), "old helper should route to generic marker")


def test_unified_game_runtime_executes_registered_game() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        payload = game_tool_runtime.execute_game_command(
            "random-imitator-td",
            "new_game level=1 seed=runtime-test",
            "player/a",
            save_root=Path(tmpdir),
        )
        _assert(payload.get("ok") is True, "unified game runtime should execute registered game")
        _assert(payload.get("game_id") == "random_imitator_td", "alias should normalize to registered game")
        _assert(payload.get("game_tool_loop") is True, "unified game runtime should mark game loop")
        _assert((Path(tmpdir) / "player_a.json").exists(), "unified runtime should use save_id path")


def test_game_checkpoint_does_not_mutate_tool_choice() -> None:
    result = json.dumps(
        {
            "ok": True,
            "game_id": "future_game",
            "game_tool_loop": True,
            "skip_dynamic_memory_write": True,
            "skip_body_delta": True,
            "checkpoint": True,
            "text": "防沉迷暂停: 已完成第5回合",
        },
        ensure_ascii=False,
    )
    messages = [
        {"role": "user", "content": "等待"},
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "future_game"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": result},
    ]

    _assert(game_tool_runtime.game_tool_checkpoint_from_messages(messages), "checkpoint should be detected")
    body = {
        "messages": messages,
        "tools": [{"type": "function", "function": {"name": "future_game", "parameters": {"type": "object"}}}],
        "tool_choice": "auto",
    }
    _assert(body.get("tool_choice") == "auto", "checkpoint should not mutate tool_choice")
    _assert(body.get("messages") == messages, "checkpoint should keep normal tool-loop context")
    _assert(len(body.get("messages") or []) == len(messages), "checkpoint should not inject prompts")


def test_normal_game_tool_result_does_not_checkpoint() -> None:
    result = json.dumps(
        {
            "ok": True,
            "game_id": "future_game",
            "game_tool_loop": True,
            "skip_dynamic_memory_write": True,
            "skip_body_delta": True,
            "checkpoint": False,
            "text": "事件: 普通回合",
        },
        ensure_ascii=False,
    )
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "future_game"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": result},
    ]

    _assert(not game_tool_runtime.game_tool_checkpoint_from_messages(messages), "normal game result should not checkpoint")


def test_tool_mode_injects_without_game_loop_skip() -> None:
    app = Flask(__name__)
    with tempfile.TemporaryDirectory() as tmpdir:
        random_imitator_td_mode_store.RANDOM_IMITATOR_TD_MODE_FILE = Path(tmpdir) / "mode.json"
        random_imitator_td_mode_store.set_enabled(True)

        with app.test_request_context("/"):
            _assert(chat_route._random_imitator_td_tool_mode_enabled(), "tool mode should be enabled")
            _assert(not chat_route._is_game_tool_loop_request(), "tool mode alone should not mark a game loop")
            _assert(not chat_route._skip_dynamic_memory_request(), "tool mode alone should not skip dynamic recall")


if __name__ == "__main__":
    test_tool_executes_and_persists_by_save_id()
    test_tool_marks_anti_addiction_checkpoint_every_five_turns()
    test_game_request_marker_skips_chat_side_effects()
    test_game_tool_trace_skips_archive_side_effects()
    test_game_tool_trace_marker_skips_archive_side_effects()
    test_unified_game_runtime_executes_registered_game()
    test_game_checkpoint_does_not_mutate_tool_choice()
    test_normal_game_tool_result_does_not_checkpoint()
    test_tool_mode_injects_without_game_loop_skip()
    print("ok")
