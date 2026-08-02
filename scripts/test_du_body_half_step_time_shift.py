from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import pixel_home, spring_dream


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected={expected!r} actual={actual!r}")


def assert_close(actual, expected, label):
    if abs(float(actual) - float(expected)) > 1e-9:
        raise AssertionError(f"{label}: expected={expected!r} actual={actual!r}")


def main():
    for hour in (23, 0, 3, 6, 9):
        assert_close(
            pixel_home._du_body_time_shift(datetime(2026, 7, 28, hour, 0)),
            1.5,
            f"weighted hour {hour}",
        )
    for hour in (4, 5, 10, 22):
        assert_close(
            pixel_home._du_body_time_shift(datetime(2026, 7, 28, hour, 0)),
            0,
            f"unweighted hour {hour}",
        )

    desire, self_control, has_desire = pixel_home._apply_du_body_time_shift(
        2,
        4,
        has_desire_value=True,
        now_dt=datetime(2026, 7, 28, 23, 0),
    )
    assert_equal((desire, self_control, has_desire), (3.5, 2.5, True), "half-step effective levels")

    desire, self_control, has_desire = pixel_home._apply_du_body_time_shift(
        4,
        1,
        has_desire_value=True,
        now_dt=datetime(2026, 7, 28, 6, 0),
    )
    assert_equal((desire, self_control, has_desire), (5, 0, True), "half-step clamping")

    assert_equal(pixel_home._format_du_body_level(1.5), "1.5", "half-step display")
    assert_equal(pixel_home._format_du_body_level(2), "2", "whole-level display")
    assert_equal(pixel_home._du_body_prompt_level_key(1.5), 2, "desire prompt nearest level")
    assert_equal(pixel_home._du_body_prompt_level_key(3.5), 4, "self-control prompt nearest level")
    assert_equal(pixel_home._du_penis_state_from_desire_level(1.5), "放松状态", "half-step physical state")
    prompt_text = pixel_home._du_body_prompt_current_state_text({}, 1.5, 3.5, True)
    if pixel_home.DU_BODY_DESIRE_PROMPT_TEXT[2] not in prompt_text:
        raise AssertionError("half-step desire did not reuse nearest prompt text")
    if pixel_home.DU_BODY_SELF_CONTROL_PROMPT_TEXT[4] not in prompt_text:
        raise AssertionError("half-step self-control did not reuse nearest prompt text")

    expected_probability = (
        0.1
        + 2.5 * spring_dream.SPRING_DREAM_DESIRE_PROBABILITY_STEP
        + spring_dream.SPRING_DREAM_SLEEP_PROBABILITY_BONUS
    )
    assert_close(
        spring_dream._spring_dream_probability(
            0.1,
            desire_level=2.5,
            is_sleeping=True,
            miss_count=0,
        ),
        expected_probability,
        "spring dream probability keeps half-step",
    )

    print("du body half-step time shift regression: PASS")


if __name__ == "__main__":
    main()
