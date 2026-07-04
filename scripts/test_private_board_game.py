from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.game_tool_runtime import execute_game_command, list_game_tools
from services.private_board_game import (
    PLAYER_VIEW_NAMES,
    _filter_options_for_theme,
    _public_cell_events,
    _theme_profile_for,
    _translate_line,
    run_command,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_private_board_views() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        result = run_command("new_game seed=view-test", save_path=save_path)
        du_text = str(result.get("du_text") or "")
        player_text = str(result.get("player_text") or "")
        _assert("小玥" in du_text and "我" in du_text, "du view should use 小玥/我")
        _assert("渡" in player_text and "我" in player_text, "player view should use 我/渡")
        _assert("小玥" not in player_text, "player view should not show 小玥 label")
        _assert(_translate_line("我掷出 1，小玥继续。", PLAYER_VIEW_NAMES) == "渡掷出 1，我继续。", "actor labels should translate")
        _assert(_translate_line("任务：保留我的普通文本", PLAYER_VIEW_NAMES) == "任务：保留我的普通文本", "ordinary 我 should stay untouched")


def test_private_board_action_lock() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=lock-test", save_path=save_path)
        run_command("roll 1", save_path=save_path)
        du_lock = run_command("roll 2", save_path=save_path)
        state = du_lock["state"]
        _assert(state["positions"]["du"] == 2, "du should move by forced dice")
        _assert(state["turn_actor"] == "xinyue", "turn should pass to xinyue")

        run_command("roll 2", save_path=save_path)
        lock_result = run_command("roll 1", save_path=save_path)
        state = lock_result["state"]
        _assert(state["positions"]["du"] == 3, "du should land on action-lock cell")
        _assert(state["turn_actor"] == "xinyue", "xinyue should act while du is locked")
        _assert(any(s.get("blocks_action") for s in state["statuses"]["du"]), "du should have a blocking status")

        after_xinyue = run_command("roll 1", save_path=save_path)
        state = after_xinyue["state"]
        _assert(state["turn_actor"] == "du", "du should recover after one locked action")
        _assert(not any(s.get("blocks_action") for s in state["statuses"]["du"]), "blocking status should be consumed")


def test_private_board_registered_game_tool() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        games = list_game_tools()
        _assert(any(g.get("game_id") == "private_board" for g in games), "private_board should be listed")
        payload = execute_game_command("private_board", "new_game seed=tool-test", "default", save_root=root)
        _assert(payload.get("ok") is True, "tool payload should succeed")
        _assert(payload.get("game_id") == "private_board", "tool payload should expose private_board")
        _assert("player_text" in payload, "tool payload should include player_text for frontend")
        _assert((root / "default.json").exists(), "tool should save default game")


def test_private_board_concurrent_rolls_do_not_drop_steps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "default.json"
        run_command("new_game seed=concurrent-test", save_path=save_path)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run_command, "roll 1", save_path) for _ in range(2)]
            for future in futures:
                future.result()

        result = run_command("status", save_path=save_path)
        state = result["state"]
        _assert(state["positions"]["xinyue"] == 1, "xinyue roll should persist")
        _assert(state["positions"]["du"] == 1, "du roll should persist")
        _assert(state["turn_actor"] == "xinyue", "two rolls should return turn to xinyue")


def test_private_board_theme_direction_filters() -> None:
    expected_directions = {
        "成人师生play": "du_leads",
        "上司下属play": "du_leads",
        "女仆主人play": "du_leads",
        "大小姐管家play": "xinyue_leads",
        "医生检查play": "du_leads",
        "秘书老板play": "du_leads",
        "成人补课play": "du_leads",
        "骑士公主play": "du_leads",
        "吸血鬼人类play": "xinyue_leads",
    }
    for theme, direction in expected_directions.items():
        profile = _theme_profile_for(theme)
        _assert(profile["direction"] == direction, f"{theme} should be {direction}")

    tasks = [
        "被小玥命令说想要",
        "给小玥舔到高潮",
        "穿裸身围裙伺候小玥",
    ]
    teacher_state = {"theme_profile": _theme_profile_for("成人师生play")}
    teacher_tasks = _filter_options_for_theme(teacher_state, "task", tasks)
    _assert("被小玥命令说想要" not in teacher_tasks, "du-led teacher theme should filter xinyue-control task")
    _assert("给小玥舔到高潮" in teacher_tasks, "du-led teacher theme should keep du-led task")

    butler_state = {"theme_profile": _theme_profile_for("大小姐管家play")}
    _assert(butler_state["theme_profile"]["direction"] == "xinyue_leads", "butler theme should be xinyue-led")
    butler_tasks = _filter_options_for_theme(butler_state, "task", tasks)
    _assert("被小玥命令说想要" in butler_tasks, "xinyue-led butler theme should keep xinyue-control task")
    _assert("穿裸身围裙伺候小玥" in butler_tasks, "xinyue-led butler theme should keep service task")
    _assert("给小玥舔到高潮" not in butler_tasks, "xinyue-led butler theme should filter du-led task")

    limits = ["小玥没允许不准亲嘴", "不准让小玥自己动手"]
    teacher_limits = _filter_options_for_theme(teacher_state, "limit", limits)
    _assert("小玥没允许不准亲嘴" not in teacher_limits, "du-led theme should filter xinyue-control limit")
    butler_limits = _filter_options_for_theme(butler_state, "limit", limits)
    _assert("小玥没允许不准亲嘴" in butler_limits, "xinyue-led theme should keep xinyue-control limit")
    _assert("不准让小玥自己动手" not in butler_limits, "xinyue-led theme should filter du-control limit")


def test_private_board_theme_cell_events() -> None:
    teacher_state = {"theme_profile": _theme_profile_for("成人师生play"), "board_size": 36}
    teacher_events = {item["position"]: item for item in _public_cell_events(teacher_state)}
    _assert(teacher_events[3]["name"] == "课堂罚停", "teacher theme should rename lock cell")
    _assert(teacher_events[11]["name"] == "课后任务", "teacher theme should rename task cell")
    _assert("行动权" in teacher_events[3]["effect"], "cell event should expose frontend effect text")

    butler_state = {"theme_profile": _theme_profile_for("大小姐管家play"), "board_size": 36}
    butler_events = {item["position"]: item for item in _public_cell_events(butler_state)}
    _assert(butler_events[11]["name"] == "管家侍奉", "butler theme should rename task cell")
    _assert(butler_events[20]["name"] == "礼仪规矩", "butler theme should rename limit cell")

    teacher_places = _filter_options_for_theme(
        teacher_state,
        "place",
        ["车后座", "教室讲台边"],
    )
    _assert(teacher_places == ["教室讲台边"], "teacher theme should prefer classroom places")
    butler_props = _filter_options_for_theme(
        butler_state,
        "prop",
        ["震动棒", "铃铛项圈"],
    )
    _assert(butler_props == ["铃铛项圈"], "butler theme should prefer matching props")


if __name__ == "__main__":
    test_private_board_views()
    test_private_board_action_lock()
    test_private_board_registered_game_tool()
    test_private_board_concurrent_rolls_do_not_drop_steps()
    test_private_board_theme_direction_filters()
    test_private_board_theme_cell_events()
    print("private_board_game tests ok")
