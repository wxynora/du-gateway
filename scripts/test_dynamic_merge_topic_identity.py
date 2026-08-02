#!/usr/bin/env python3
"""Dynamic merge must reject keyword overlap when the actual topics differ."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.dynamic_layer_ds import _DYNAMIC_LAYER_PROMPT


def main() -> None:
    prompt = _DYNAMIC_LAYER_PROMPT
    required_contracts = (
        "merge 的前提是同一个具体事项",
        "主体是谁、对象是谁、关系或行为是什么、具体在说什么",
        "关键词、标签、房间或宽泛语义相近",
        "不能证明是同一件事",
        "重复、补充、纠正或状态变化",
        "两个独立事实",
        "小玥有名字羞耻症",
        "渡的名字相关记忆",
        "只有“名字”这个词重合",
        "主体和具体事项不同，禁止 merge",
        "有独立记忆价值时用 new，没有则 skip",
    )
    for contract in required_contracts:
        assert contract in prompt, f"missing topic-identity merge gate: {contract}"
    print("dynamic merge topic identity contract passed")


if __name__ == "__main__":
    main()
