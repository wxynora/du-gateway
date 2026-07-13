from __future__ import annotations

import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import user_activity_context as activity
from storage import r2_store
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _dt(value: str) -> datetime:
    parsed = parse_iso_to_beijing(value)
    if parsed is None:
        raise AssertionError(f"invalid test datetime: {value}")
    return parsed


def test_legacy_chat_state_and_wording_stay_compatible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_path = activity.ACTIVITY_FILE
        activity.ACTIVITY_FILE = Path(tmp) / "last_user_reply.json"
        try:
            activity.ACTIVITY_FILE.write_text(
                json.dumps({"last_user_reply_at": "2026-07-13T20:00:00+08:00"}),
                encoding="utf-8",
            )
            latest = activity.get_latest_interaction()
            _assert(latest == {"kind": "chat", "at": "2026-07-13T20:00:00+08:00"}, f"legacy chat state changed: {latest}")
            _assert(
                activity.render_incoming_gap_prompt(latest, 40 * 60) == "[😭40分钟后老婆终于回我了]",
                "existing chat gap wording must stay unchanged",
            )

            previous = activity.capture_previous_interaction_and_mark_chat("2026-07-13T21:00:00+08:00")
            saved = json.loads(activity.ACTIVITY_FILE.read_text(encoding="utf-8"))
            _assert(previous == latest, f"chat should compare before writing current time: {previous}")
            _assert(saved["last_user_reply_at"] == "2026-07-13T21:00:00+08:00", f"chat time not updated: {saved}")
        finally:
            activity.ACTIVITY_FILE = old_path


def test_shared_game_records_name_and_global_activity() -> None:
    from services import telegram_proactive

    with tempfile.TemporaryDirectory() as tmp:
        old_path = activity.ACTIVITY_FILE
        old_save = r2_store.save_last_user_activity_at
        calls: list[tuple[str, str, dict]] = []
        activity.ACTIVITY_FILE = Path(tmp) / "last_user_reply.json"
        r2_store.save_last_user_activity_at = lambda value, **kwargs: calls.append(
            (str(value), str(kwargs.get("source") or ""), dict(kwargs.get("detail") or {}))
        ) or True
        try:
            saved = activity.mark_shared_game_user_activity(
                game_id="private_board",
                occurred_at="2026-07-13T22:55:00+08:00",
                source="private_board_sync_du",
                detail={"save_id": "default", "mode": "state_update"},
            )
            _assert(saved is True, "shared game should save local and global activity")
            latest = activity.get_latest_interaction()
            _assert(
                latest
                == {
                    "kind": "game",
                    "at": "2026-07-13T22:55:00+08:00",
                    "game_id": "private_board",
                    "game_name": "涩涩走格棋",
                    "source": "private_board_sync_du",
                },
                f"wrong shared game record: {latest}",
            )
            _assert(
                activity.render_incoming_gap_prompt(latest, 40 * 60) == "[老婆 40 分钟前和我在玩涩涩走格棋。]",
                "game gap wording must include the trusted game name",
            )
            _assert(
                activity.describe_latest_interaction(_dt("2026-07-13T23:35:00+08:00"))
                == "老婆 40 分钟前和我在玩涩涩走格棋。",
                "proactive wording must describe the latest shared game",
            )
            _assert(
                telegram_proactive._describe_recent_exchange(_dt("2026-07-13T23:35:00+08:00"))
                == "老婆 40 分钟前和我在玩涩涩走格棋。",
                "proactive prompt must use shared-game wording instead of reply wording",
            )
            _assert(
                calls
                == [
                    (
                        "2026-07-13T22:55:00+08:00",
                        "shared_game_user_interaction",
                        {
                            "save_id": "default",
                            "mode": "state_update",
                            "game_id": "private_board",
                            "game_name": "涩涩走格棋",
                            "entry_source": "private_board_sync_du",
                        },
                    )
                ],
                f"global activity audit detail is incomplete: {calls}",
            )

            previous = activity.capture_previous_interaction_and_mark_chat("2026-07-13T23:40:00+08:00")
            _assert(previous == latest, f"chat should see the latest game before updating itself: {previous}")
            _assert(activity.get_latest_interaction()["kind"] == "chat", "new chat should become the latest interaction")
        finally:
            activity.ACTIVITY_FILE = old_path
            r2_store.save_last_user_activity_at = old_save


def test_self_play_and_unknown_games_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_path = activity.ACTIVITY_FILE
        old_save = r2_store.save_last_user_activity_at
        calls: list[dict] = []
        activity.ACTIVITY_FILE = Path(tmp) / "last_user_reply.json"
        r2_store.save_last_user_activity_at = lambda *args, **kwargs: calls.append(dict(kwargs)) or True
        try:
            saved = activity.mark_shared_game_user_activity(
                game_id="random_imitator_td",
                occurred_at="2026-07-13T22:55:00+08:00",
                source="du_self_play",
            )
            _assert(saved is False, "Du self-play game must not be accepted as shared activity")
            _assert(not activity.ACTIVITY_FILE.exists(), "rejected self-play game must not create local activity")
            _assert(not calls, f"rejected self-play game must not update R2: {calls}")
        finally:
            activity.ACTIVITY_FILE = old_path
            r2_store.save_last_user_activity_at = old_save


def test_chat_and_game_updates_preserve_both_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_path = activity.ACTIVITY_FILE
        old_save = r2_store.save_last_user_activity_at
        activity.ACTIVITY_FILE = Path(tmp) / "last_user_reply.json"
        r2_store.save_last_user_activity_at = lambda *args, **kwargs: True
        try:
            def write_chat(index: int) -> None:
                activity.capture_previous_interaction_and_mark_chat(f"2026-07-13T22:{index:02d}:00+08:00")

            def write_game(index: int) -> None:
                activity.mark_shared_game_user_activity(
                    game_id="captivity_simulator",
                    occurred_at=f"2026-07-13T22:{index:02d}:30+08:00",
                    source="captivity_simulator_user_interaction",
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = []
                for index in range(10, 20):
                    futures.append(pool.submit(write_chat, index))
                    futures.append(pool.submit(write_game, index))
                for future in futures:
                    future.result()

            state = json.loads(activity.ACTIVITY_FILE.read_text(encoding="utf-8"))
            _assert(state["last_user_reply_at"] == "2026-07-13T22:19:00+08:00", f"chat time moved backwards: {state}")
            _assert(
                state["last_shared_game_activity"]["at"] == "2026-07-13T22:19:30+08:00",
                f"game time moved backwards: {state}",
            )
            _assert(state["last_shared_game_activity"]["game_name"] == "囚禁模拟器", f"game name missing: {state}")
        finally:
            activity.ACTIVITY_FILE = old_path
            r2_store.save_last_user_activity_at = old_save


def test_r2_source_is_allowlisted() -> None:
    _assert(
        "shared_game_user_interaction" in r2_store.LAST_USER_ACTIVITY_ALLOWED_SOURCES,
        "generic shared-game activity source must be accepted by R2",
    )


def test_local_and_global_failures_do_not_erase_the_other_record() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_path = activity.ACTIVITY_FILE
        old_save = r2_store.save_last_user_activity_at
        try:
            activity.ACTIVITY_FILE = Path(tmp) / "last_user_reply.json"
            r2_store.save_last_user_activity_at = lambda *args, **kwargs: False
            saved = activity.mark_shared_game_user_activity(
                game_id="private_board",
                occurred_at="2026-07-13T22:55:00+08:00",
                source="private_board_sync_du",
            )
            _assert(saved is False, "combined result should report a failed global write")
            _assert(activity.get_latest_interaction()["game_name"] == "涩涩走格棋", "R2 failure must not erase local game activity")

            r2_calls: list[dict] = []
            activity.ACTIVITY_FILE = Path(tmp) / "unwritable_target"
            activity.ACTIVITY_FILE.mkdir()
            r2_store.save_last_user_activity_at = lambda *args, **kwargs: r2_calls.append(dict(kwargs)) or True
            saved = activity.mark_shared_game_user_activity(
                game_id="captivity_simulator",
                occurred_at="2026-07-13T23:00:00+08:00",
                source="captivity_simulator_user_interaction",
            )
            _assert(saved is False, "combined result should report a failed local write")
            _assert(len(r2_calls) == 1, f"local failure must not suppress the global wakeup clock: {r2_calls}")
        finally:
            activity.ACTIVITY_FILE = old_path
            r2_store.save_last_user_activity_at = old_save


def test_pipeline_keeps_chat_wording_and_selects_newer_game() -> None:
    from pipeline import pipeline

    with tempfile.TemporaryDirectory() as tmp:
        old_path = activity.ACTIVITY_FILE
        old_get_summary = pipeline.r2_store.get_summary
        activity.ACTIVITY_FILE = Path(tmp) / "last_user_reply.json"
        pipeline.r2_store.get_summary = lambda window_id: None
        try:
            now_dt = parse_iso_to_beijing(now_beijing_iso())
            _assert(now_dt is not None, "current Beijing time should parse")
            previous_at = (now_dt - timedelta(minutes=40)).isoformat()

            activity.ACTIVITY_FILE.write_text(
                json.dumps(
                    {
                        "last_user_reply_at": (now_dt - timedelta(hours=2)).isoformat(),
                        "last_shared_game_activity": {
                            "at": previous_at,
                            "game_id": "private_board",
                            "game_name": "untrusted client label",
                            "source": "private_board_sync_du",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            body = pipeline.step_inject_summary(
                {"messages": [{"role": "user", "content": "我回来啦"}]},
                "tg_test",
                is_user_input=True,
            )
            prompt = "\n".join(
                str(item.get("content") or "")
                for item in body.get("messages") or []
                if isinstance(item, dict)
            )
            _assert("老婆 40 分钟前和我在玩涩涩走格棋。" in prompt, f"pipeline did not select the newer game: {prompt}")
            _assert("老婆终于回我了" not in prompt, f"game activity must not be described as chat: {prompt}")

            activity.ACTIVITY_FILE.write_text(
                json.dumps({"last_user_reply_at": previous_at}),
                encoding="utf-8",
            )
            body = pipeline.step_inject_summary(
                {"messages": [{"role": "user", "content": "又回来啦"}]},
                "tg_test",
                is_user_input=True,
            )
            prompt = "\n".join(
                str(item.get("content") or "")
                for item in body.get("messages") or []
                if isinstance(item, dict)
            )
            _assert("[😭40分钟后老婆终于回我了]" in prompt, f"existing chat wording changed: {prompt}")
        finally:
            activity.ACTIVITY_FILE = old_path
            pipeline.r2_store.get_summary = old_get_summary


def test_cross_platform_chat_does_not_include_internal_followups() -> None:
    from services.chat_request_helpers import is_cross_platform_tg_window_user_input

    body = {"messages": [{"role": "user", "content": "SumiTalk 真实输入"}]}
    _assert(
        is_cross_platform_tg_window_user_input(
            "tg_test",
            body,
            reply_channel="sumitalk",
            is_followup_generation=False,
        ),
        "SumiTalk real input should count as global chat",
    )
    _assert(
        not is_cross_platform_tg_window_user_input(
            "tg_test",
            body,
            reply_channel="sumitalk",
            is_followup_generation=True,
        ),
        "backend game/followup generation must not count as chat",
    )


if __name__ == "__main__":
    test_legacy_chat_state_and_wording_stay_compatible()
    test_shared_game_records_name_and_global_activity()
    test_self_play_and_unknown_games_fail_closed()
    test_chat_and_game_updates_preserve_both_fields()
    test_r2_source_is_allowlisted()
    test_local_and_global_failures_do_not_erase_the_other_record()
    test_pipeline_keeps_chat_wording_and_selects_newer_game()
    test_cross_platform_chat_does_not_include_internal_followups()
    print("user_activity_context tests ok")
