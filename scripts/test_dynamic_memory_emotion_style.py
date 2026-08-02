#!/usr/bin/env python3
"""Dynamic notes must preserve real emotion without forcing stock paired adjectives."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.dynamic_layer_ds import _DYNAMIC_LAYER_PROMPT, _dynamic_layer_retry_instruction


def main() -> None:
    required = (
        "每条尽量同时带「事实 + 情绪」：至少包含一件发生了什么，以及一句当下感受/语气。",
        "情绪表达禁止使用“又 X 又 Y”的写法。",
    )
    for contract in required:
        assert contract in _DYNAMIC_LAYER_PROMPT, f"missing emotion style contract: {contract}"

    retry = _dynamic_layer_retry_instruction("content_incomplete", "老婆说她今天没吃饭")
    assert "必须同时交代发生了什么和当时的感受/语气" in retry
    assert "不能使用“又 X 又 Y”的情绪写法" in retry
    assert "得意" not in _DYNAMIC_LAYER_PROMPT
    assert "发烫" not in _DYNAMIC_LAYER_PROMPT
    print("dynamic memory emotion style contract passed")


if __name__ == "__main__":
    main()
