from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import qq_activity_context as activity
from storage import r2_store


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _row(index: int, *, owner: bool = False) -> dict:
    return {
        "timestamp": 1_750_000_000 + index,
        "group_id": "123",
        "user_id": "1" if owner else str(index + 10),
        "sender_name": "辛玥" if owner else f"群友{index}",
        "is_owner": owner,
        "text": f"消息{index}",
        "message_id": f"msg-{index}",
    }


def test_latest_twenty_rows_are_kept() -> None:
    current = activity._row_from_payload(_row(25, owner=True))
    normalized = activity._normalize_context_rows([_row(index) for index in range(25)], current)

    _assert(len(normalized) == 20, f"expected 20 recent rows, got {len(normalized)}")
    _assert(normalized[0]["message_id"] == "msg-6", f"old rows were not trimmed: {normalized[0]}")
    _assert(normalized[-1]["message_id"] == "msg-25", "current owner message must be the newest row")


def test_wakeup_wording_allows_natural_group_context_use() -> None:
    original_load = activity._load_state
    original_last_contact = r2_store.get_last_proactive_contact_at
    activity._load_state = lambda: {
        "items": [
            {
                "latest_owner_at": "2026-07-16T20:10:00+08:00",
                "recorded_at": "2026-07-16T20:10:00+08:00",
                "context": [activity._row_from_payload(_row(1)), activity._row_from_payload(_row(2, owner=True))],
            }
        ]
    }
    r2_store.get_last_proactive_contact_at = lambda: "2026-07-16T19:00:00+08:00"
    try:
        prompt = activity.build_group_activity_context_for_wakeup()
    finally:
        activity._load_state = original_load
        r2_store.get_last_proactive_contact_at = original_last_contact

    expected = (
        "上次你发信息后，小玥还没有在私聊回复你，但她期间在QQ群里有过发言。"
        "这些是近期群聊上下文，区分不同发言人，不要把群友的话当成小玥说的。"
    )
    _assert(expected in prompt, "wakeup context does not use the requested wording")
    for forbidden in ("为什么没回", "旁路上下文", "注意力在哪里", "不要逐条复述", "可以自然承接"):
        _assert(forbidden not in prompt, f"old restrictive wording remains: {forbidden}")


if __name__ == "__main__":
    test_latest_twenty_rows_are_kept()
    test_wakeup_wording_allows_natural_group_context_use()
    print("qq group activity context tests passed")
