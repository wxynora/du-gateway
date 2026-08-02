#!/usr/bin/env python3
"""Regression contract for nuanced intimacy-memory grading prompts."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.dynamic_layer_ds import _DYNAMIC_LAYER_BATCH_PROMPT, _DYNAMIC_LAYER_PROMPT


REQUIRED_RULES = (
    "tag 只决定放进哪个房间，不决定是否值得记，也不能因此提高 importance",
    "普通但具体、有一点独特画面或当下感受的亲密瞬间，可以记为 importance 2",
    "同一段互动里重复的抱抱、亲亲、贴贴",
    "没有新增画面、感受或关系信息时应 skip",
    "importance 3 需要有明显、具体且之后仍值得回想的情绪分量",
    "importance 4 只用于重要偏好、边界、承诺或关系变化",
    "同一段连续亲密互动优先 merge",
)


def assert_contract(prompt: str, *, label: str) -> None:
    missing = [rule for rule in REQUIRED_RULES if rule not in prompt]
    assert not missing, f"{label} missing calibrated intimacy rules: {missing}"


def main() -> None:
    assert_contract(_DYNAMIC_LAYER_PROMPT, label="single prompt")
    assert_contract(_DYNAMIC_LAYER_BATCH_PROMPT, label="batch prompt")
    print("PASS nuanced intimacy grading is present in single and batch prompts")


if __name__ == "__main__":
    main()
