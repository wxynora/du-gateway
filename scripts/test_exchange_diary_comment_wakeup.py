#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.miniapp import exchange_diary
from services import conversation_followup
from services.prompt_cache_debug import build_prompt_cache_profile
from storage import upstream_store


class _InlineThread:
    def __init__(self, *, target, **_kwargs) -> None:
        self.target = target

    def start(self) -> None:
        self.target()


class _ToolOnlyResponse:
    status_code = 200
    content = b"{}"
    text = ""

    @staticmethod
    def json() -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_only_reply_done": True,
                    }
                }
            ]
        }


class ExchangeDiaryCommentWakeupTest(unittest.TestCase):
    def test_route_passes_comment_fields_separately(self) -> None:
        captured: dict = {}
        original_context = exchange_diary.resolve_recent_reply_context
        original_device = exchange_diary._get_panel_device_id
        original_thread = exchange_diary.threading.Thread
        original_send = conversation_followup.send_exchange_diary_comment_wakeup
        exchange_diary.resolve_recent_reply_context = lambda **_kwargs: {
            "channel": "sumitalk",
            "window_id": "tg-test",
            "target": "device-test",
            "meta": {"source": "test"},
        }
        exchange_diary._get_panel_device_id = lambda: "device-panel"
        exchange_diary.threading.Thread = _InlineThread

        def fake_send(**kwargs):
            captured.update(kwargs)
            return {"ok": True, "channel": "sumitalk"}

        conversation_followup.send_exchange_diary_comment_wakeup = fake_send
        try:
            result = exchange_diary._queue_comment_wakeup(
                {"id": "entry-1", "title": "雨夜"},
                {"id": "comment-1", "content": "原样评论\n第二行"},
            )
        finally:
            exchange_diary.resolve_recent_reply_context = original_context
            exchange_diary._get_panel_device_id = original_device
            exchange_diary.threading.Thread = original_thread
            conversation_followup.send_exchange_diary_comment_wakeup = original_send

        self.assertTrue(result["queued"])
        self.assertEqual("雨夜", captured["diary_title"])
        self.assertEqual("entry-1", captured["entry_id"])
        self.assertEqual("comment-1", captured["comment_id"])
        self.assertEqual("原样评论\n第二行", captured["comment_content"])
        self.assertNotIn("event_text", captured)

    def test_comment_is_only_in_user_and_static_cache_stays_stable(self) -> None:
        request_bodies: list[dict] = []
        original_model = upstream_store.get_cached_active_model
        original_preference = conversation_followup._choice_dialog_delivery_preference
        original_post = conversation_followup.requests.post
        upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "test-model"
        conversation_followup._choice_dialog_delivery_preference = lambda _target: (
            "sumitalk",
            "device-test",
            {},
        )

        def fake_post(_url, *, headers, json, timeout):
            request_bodies.append({"headers": dict(headers), "body": json, "timeout": timeout})
            return _ToolOnlyResponse()

        conversation_followup.requests.post = fake_post
        comments = ["第一条评论：只在 user", "第二条评论：也只在 user"]
        try:
            for index, comment in enumerate(comments, start=1):
                result = conversation_followup.send_exchange_diary_comment_wakeup(
                    window_id="tg-test",
                    target="device-test",
                    diary_title="雨夜",
                    entry_id="entry-1",
                    comment_id=f"comment-{index}",
                    comment_content=comment,
                    preferred_channel="sumitalk",
                    preferred_meta={"source": "test"},
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["tool_only"])
        finally:
            upstream_store.get_cached_active_model = original_model
            conversation_followup._choice_dialog_delivery_preference = original_preference
            conversation_followup.requests.post = original_post

        static_prefix = [
            {"role": "system", "content": "现有静态系统提示一"},
            {"role": "system", "content": "现有静态系统提示二"},
        ]
        static_snapshots: list[list[dict]] = []
        static_hashes: list[str] = []
        profiles: list[dict] = []

        for index, captured in enumerate(request_bodies, start=1):
            body = captured["body"]
            self.assertEqual("exchange_diary_comment", captured["headers"]["X-DU-WAKEUP-KIND"])
            self.assertEqual(2, len(body["messages"]))
            dynamic_system, user = body["messages"]
            comment = comments[index - 1]

            self.assertEqual("system", dynamic_system["role"])
            self.assertIs(True, dynamic_system.get("__dynamic__"))
            self.assertIn("日记标题：雨夜", dynamic_system["content"])
            self.assertIn("entry_id：entry-1", dynamic_system["content"])
            self.assertIn(f"comment_id：comment-{index}", dynamic_system["content"])
            self.assertIn("exchange_diary", dynamic_system["content"])
            self.assertIn("action=comment", dynamic_system["content"])
            self.assertNotIn("exchange_diary_comment_create", dynamic_system["content"])
            self.assertIn("entry_id=entry-1", dynamic_system["content"])
            self.assertIn(f"reply_to_comment_id=comment-{index}", dynamic_system["content"])
            self.assertIn("不是聊天正文", dynamic_system["content"])
            self.assertNotIn(comment, dynamic_system["content"])

            self.assertEqual("user", user["role"])
            self.assertEqual(f"小玥评论了你的日记：{comment}", user["content"])
            serialized = json.dumps(body["messages"], ensure_ascii=False)
            self.assertEqual(1, serialized.count(comment))
            self.assertTrue(all(comment not in str(message.get("content") or "") for message in body["messages"] if message["role"] == "system"))

            profiled_body = {**body, "messages": static_prefix + body["messages"]}
            profile = build_prompt_cache_profile(profiled_body, "https://upstream.test/v1/chat/completions")
            profiles.append(profile)
            static_snapshot = [
                message
                for message in profiled_body["messages"]
                if message.get("role") == "system" and not message.get("__dynamic__")
            ]
            static_snapshots.append(static_snapshot)
            static_hashes.append(
                hashlib.sha256(
                    json.dumps(static_snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest()
            )
            for event_value in ("雨夜", "entry-1", f"comment-{index}", comment):
                self.assertTrue(all(event_value not in str(message.get("content") or "") for message in static_snapshot))

        self.assertEqual(static_snapshots[0], static_snapshots[1])
        self.assertEqual(static_hashes[0], static_hashes[1])
        self.assertEqual(profiles[0]["static_breakdown"], profiles[1]["static_breakdown"])
        self.assertEqual(profiles[0]["static_prefix_chars"], profiles[1]["static_prefix_chars"])
        self.assertTrue(all(profile["dynamic_marker_seen"] for profile in profiles))

    def test_other_wakeup_content_is_unchanged_and_event_is_dynamic(self) -> None:
        captured: dict = {}
        original_send = conversation_followup._send_wakeup_event
        conversation_followup._send_wakeup_event = lambda **kwargs: captured.update(kwargs) or {"ok": True}
        try:
            conversation_followup.send_listen_invite_response_wakeup(
                window_id="tg-test",
                target="device-test",
                event_text="接受邀请",
                preferred_channel="sumitalk",
            )
        finally:
            conversation_followup._send_wakeup_event = original_send
        self.assertEqual("接受邀请", captured["event_text"])
        self.assertTrue(captured["system_event"])
        self.assertEqual("请以渡自己的口吻回应小玥的这次选择。", captured["system_event_user_summary"])
        self.assertTrue(captured["dynamic_system_event"])


if __name__ == "__main__":
    unittest.main()
