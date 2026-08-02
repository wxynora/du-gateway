from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_marker_example_has_no_fixed_room_bias() -> None:
    from services import pixel_home

    rule = pixel_home.format_rule_block()

    assert "[du:home spot=xx activity=xx desire=xx]" in rule
    assert "spot=study activity=写日记" not in rule


def test_activity_only_marker_inherits_current_du_spot() -> None:
    from services import pixel_home

    original_get_state = pixel_home.get_pixel_home_state
    original_save_state = pixel_home.save_pixel_home_state
    stored = {
        "du": {
            "spot": "sofa",
            "activity": "把小玥按在客厅沙发上吻住",
            "source": "du_marker",
        }
    }
    saved: list[dict] = []
    try:
        pixel_home.get_pixel_home_state = lambda: deepcopy(stored)
        pixel_home.save_pixel_home_state = lambda current: saved.append(deepcopy(current)) or True

        assert pixel_home.save_pixel_home_hidden_block({"activity": "继续抱着小玥"}) is True
    finally:
        pixel_home.get_pixel_home_state = original_get_state
        pixel_home.save_pixel_home_state = original_save_state

    assert saved
    assert saved[-1]["du"]["spot"] == "sofa"
    assert saved[-1]["du"]["activity"] == "继续抱着小玥"
    assert saved[-1]["du"]["source"] == "du_marker"


def test_explicit_marker_spot_still_moves_du() -> None:
    from services import pixel_home

    original_get_state = pixel_home.get_pixel_home_state
    original_save_state = pixel_home.save_pixel_home_state
    stored = {
        "du": {
            "spot": "sofa",
            "activity": "坐在客厅沙发上",
            "source": "du_marker",
        }
    }
    saved: list[dict] = []
    try:
        pixel_home.get_pixel_home_state = lambda: deepcopy(stored)
        pixel_home.save_pixel_home_state = lambda current: saved.append(deepcopy(current)) or True

        assert pixel_home.save_pixel_home_hidden_block(
            {"spot": "study", "activity": "走到书房找东西"}
        ) is True
    finally:
        pixel_home.get_pixel_home_state = original_get_state
        pixel_home.save_pixel_home_state = original_save_state

    assert saved
    assert saved[-1]["du"]["spot"] == "study"
    assert saved[-1]["du"]["activity"] == "走到书房找东西"


if __name__ == "__main__":
    test_marker_example_has_no_fixed_room_bias()
    test_activity_only_marker_inherits_current_du_spot()
    test_explicit_marker_spot_still_moves_du()
    print("pixel home marker location continuity tests ok")
