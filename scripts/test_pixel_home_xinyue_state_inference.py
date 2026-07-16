import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pixel_home import infer_xinyue_state_from_text


def _assert_none(text: str) -> None:
    assert infer_xinyue_state_from_text(text) is None, text


def _assert_kitchen(text: str) -> None:
    inferred = infer_xinyue_state_from_text(text)
    assert inferred is not None, text
    assert inferred["spot"] == "kitchen", inferred
    assert inferred["activity"] == "吃饭", inferred


def test_meal_questions_do_not_move_xinyue_to_kitchen() -> None:
    _assert_none("吃没吃饭")
    _assert_none("你吃没吃饭呀")
    _assert_none("我只是问他吃饭了吗")
    _assert_none("有没有吃饭这个状态别乱改")


def test_explicit_meal_actions_still_move_xinyue_to_kitchen() -> None:
    _assert_kitchen("我去吃饭了")
    _assert_kitchen("我在做饭")
    _assert_kitchen("我点外卖了")


if __name__ == "__main__":
    test_meal_questions_do_not_move_xinyue_to_kitchen()
    test_explicit_meal_actions_still_move_xinyue_to_kitchen()
