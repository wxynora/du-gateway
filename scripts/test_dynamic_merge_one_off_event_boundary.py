#!/usr/bin/env python3
"""Different-date one-off events must remain separate dynamic memories."""

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
        "明确发生在不同日期的一次性事件",
        "也不是同一个具体事项，禁止 merge",
        "有独立记忆价值时用 new，没有则 skip",
        "三天前老婆拖延洗澡",
        "老婆今天又拖延洗澡",
        "不能 merge 成“老婆今天拖延洗澡”",
        "只有当前内容明确表示这是不同日期发生的另一次事件时",
        "其余情况继续按“是否同一个具体事项”的原有标准判断",
        "不要仅因本轮正在谈它就把事件时间改成今天或现在",
        "本轮明确纠正事件时间时可以更新",
    )
    for contract in required_contracts:
        assert contract in prompt, f"missing one-off event merge boundary: {contract}"

    print("dynamic merge one-off event boundary contract passed")


if __name__ == "__main__":
    main()
