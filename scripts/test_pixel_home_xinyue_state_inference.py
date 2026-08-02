import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pixel_home import infer_xinyue_state_from_text, maybe_update_xinyue_state_from_user_text


def _assert_none(text: str) -> None:
    assert infer_xinyue_state_from_text(text) is None, text


def _assert_kitchen(text: str) -> None:
    inferred = infer_xinyue_state_from_text(text)
    assert inferred is not None, text
    assert inferred["spot"] == "kitchen", inferred
    assert inferred["activity"] == "吃饭", inferred


def _assert_bath(text: str) -> None:
    inferred = infer_xinyue_state_from_text(text)
    assert inferred is not None, text
    assert inferred["spot"] == "bath", inferred
    assert inferred["activity"] == "洗澡", inferred


def test_meal_questions_do_not_move_xinyue_to_kitchen() -> None:
    _assert_none("吃没吃饭")
    _assert_none("你吃没吃饭呀")
    _assert_none("我只是问他吃饭了吗")
    _assert_none("有没有吃饭这个状态别乱改")


def test_explicit_meal_actions_still_move_xinyue_to_kitchen() -> None:
    _assert_kitchen("我去吃饭了")
    _assert_kitchen("我在做饭")
    _assert_kitchen("我点外卖了")


def test_makeup_workday_daytime_shower_intent_keeps_current_state() -> None:
    for now_dt in (
        datetime(2026, 9, 20, 8, 0),
        datetime(2026, 9, 20, 16, 59),
    ):
        with patch("services.pixel_home._now_dt", return_value=now_dt):
            _assert_none("我去洗澡了")

    with (
        patch("services.pixel_home._now_dt", return_value=datetime(2026, 9, 20, 10, 0)),
        patch("services.pixel_home.save_actor_state") as save_actor_state,
    ):
        assert maybe_update_xinyue_state_from_user_text("我准备洗澡") is None
        save_actor_state.assert_not_called()

    with patch("services.pixel_home._now_dt", return_value=datetime(2026, 9, 20, 10, 0)):
        _assert_kitchen("我去吃饭了")


def test_holiday_and_outside_work_hours_still_update_shower_state() -> None:
    for now_dt in (
        datetime(2026, 2, 17, 12, 0),
        datetime(2026, 9, 20, 7, 59),
        datetime(2026, 9, 20, 17, 0),
    ):
        with patch("services.pixel_home._now_dt", return_value=now_dt):
            _assert_bath("我去洗澡了")


if __name__ == "__main__":
    test_meal_questions_do_not_move_xinyue_to_kitchen()
    test_explicit_meal_actions_still_move_xinyue_to_kitchen()
    test_makeup_workday_daytime_shower_intent_keeps_current_state()
    test_holiday_and_outside_work_hours_still_update_shower_state()
