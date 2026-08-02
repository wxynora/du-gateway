#!/usr/bin/env python3
"""QQ group context images must keep their original sender attribution."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import qq_activity_context as activity
from storage import r2_store


def main() -> None:
    friend_image = "data:image/png;base64,ZmFrZS1mcmllbmQ="
    owner_image = "data:image/png;base64,ZmFrZS1vd25lcg=="
    rows = [
        {
            "at": "2026-07-27T10:10:00+08:00",
            "sender_name": "群友甲",
            "is_owner": False,
            "text": "",
            "images": [friend_image],
        },
        {
            "at": "2026-07-27T10:11:00+08:00",
            "sender_name": "错误昵称不应使用",
            "is_owner": True,
            "text": "",
            "images": [owner_image],
        },
    ]
    original_load = activity._load_state
    original_last_contact = r2_store.get_last_proactive_contact_at
    original_now = activity.now_beijing_iso
    activity._load_state = lambda: {
        "items": [
            {
                "latest_owner_at": "2026-07-27T10:11:00+08:00",
                "recorded_at": "2026-07-27T10:11:00+08:00",
                "context": rows,
            }
        ]
    }
    r2_store.get_last_proactive_contact_at = lambda: "2026-07-27T09:00:00+08:00"
    activity.now_beijing_iso = lambda: "2026-07-27T10:15:00+08:00"
    try:
        content = activity.build_group_activity_context_for_wakeup()
    finally:
        activity._load_state = original_load
        r2_store.get_last_proactive_contact_at = original_last_contact
        activity.now_beijing_iso = original_now

    assert isinstance(content, list), f"expected multimodal content, got: {content!r}"
    assert [part.get("type") for part in content] == [
        "text",
        "text",
        "image_url",
        "text",
        "image_url",
    ], f"each image must be immediately preceded by its sender label: {content!r}"
    assert content[1]["text"] == "10:10 群友甲发的群聊图片："
    assert content[2]["image_url"]["url"] == friend_image
    assert content[3]["text"] == "10:11 辛玥发的群聊图片："
    assert content[4]["image_url"]["url"] == owner_image
    assert content[2]["__skip_image_description"] is True
    assert content[4]["__skip_image_description"] is True
    print("qq group image sender attribution contract passed")


if __name__ == "__main__":
    main()
