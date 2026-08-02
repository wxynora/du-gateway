#!/usr/bin/env python3
"""Workday hours must preserve Xinyue's complete Pixel Home state."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pixel_home import infer_xinyue_state_from_text, maybe_update_xinyue_state_from_user_text


def test_makeup_workday_hours_lock_spot_and_activity() -> None:
    messages = (
        "我去吃饭了",
        "我在写代码",
        "我去洗澡了",
        "我准备睡觉",
        "我在刷手机",
    )
    for now_dt in (
        datetime(2026, 9, 20, 8, 0),
        datetime(2026, 9, 20, 16, 59),
    ):
        with patch("services.pixel_home._now_dt", return_value=now_dt):
            for message in messages:
                assert infer_xinyue_state_from_text(message) is None, (now_dt, message)

    with (
        patch("services.pixel_home._now_dt", return_value=datetime(2026, 9, 20, 12, 0)),
        patch("services.pixel_home.save_actor_state") as save_actor_state,
    ):
        assert maybe_update_xinyue_state_from_user_text("我去吃饭了") is None
        save_actor_state.assert_not_called()


def test_rest_days_and_outside_work_hours_keep_existing_inference() -> None:
    for now_dt in (
        datetime(2026, 2, 17, 12, 0),
        datetime(2026, 9, 20, 7, 59),
        datetime(2026, 9, 20, 17, 0),
    ):
        with patch("services.pixel_home._now_dt", return_value=now_dt):
            inferred = infer_xinyue_state_from_text("我去吃饭了")
        assert inferred is not None, now_dt
        assert inferred["spot"] == "kitchen", inferred
        assert inferred["activity"] == "吃饭", inferred


def test_finished_meal_and_shower_return_to_living_room() -> None:
    for message in ("我洗完了", "我洗好澡了", "我吃完了", "我吃饱了"):
        with patch("services.pixel_home._now_dt", return_value=datetime(2026, 2, 17, 12, 0)):
            inferred = infer_xinyue_state_from_text(message)
        assert inferred is not None, message
        assert inferred["spot"] == "sofa", inferred
        assert inferred["activity"] == "休息", inferred

    with (
        patch("services.pixel_home._now_dt", return_value=datetime(2026, 2, 17, 12, 0)),
        patch(
            "services.pixel_home.save_actor_state",
            return_value={"spot": "sofa", "activity": "休息", "source": "chat_infer"},
        ) as save_actor_state,
    ):
        updated = maybe_update_xinyue_state_from_user_text("我洗完了")
        assert updated is not None
        save_actor_state.assert_called_once_with("xinyue", "sofa", "休息", source="chat_infer")

    for question in ("你洗完了吗", "吃完饭了吗"):
        with patch("services.pixel_home._now_dt", return_value=datetime(2026, 2, 17, 12, 0)):
            assert infer_xinyue_state_from_text(question) is None, question

    with (
        patch("services.pixel_home._now_dt", return_value=datetime(2026, 9, 20, 12, 0)),
        patch("services.pixel_home.save_actor_state") as save_actor_state,
    ):
        assert maybe_update_xinyue_state_from_user_text("我洗完了") is None
        save_actor_state.assert_not_called()


if __name__ == "__main__":
    test_makeup_workday_hours_lock_spot_and_activity()
    test_rest_days_and_outside_work_hours_keep_existing_inference()
    test_finished_meal_and_shower_return_to_living_room()
    print("Pixel Home workday Xinyue state lock checks passed")
