#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.text = self.content.decode("utf-8")

    def json(self) -> dict:
        return self._payload


class QqGroupDeliveryTests(unittest.TestCase):
    def test_wakeup_context_carries_group_target_and_marker_instruction(self):
        from services import qq_activity_context
        from services.qq_group_delivery import QQ_GROUP_CONTENT_MARKER

        state = {
            "items": [
                {
                    "id": "m1",
                    "recorded_at": "2026-07-28T07:40:00+08:00",
                    "latest_owner_at": "2026-07-28T07:40:00+08:00",
                    "group_id": "778899",
                    "context": [
                        {
                            "at": "2026-07-28T07:39:00+08:00",
                            "sender_name": "群友甲",
                            "is_owner": False,
                            "text": "人呢",
                            "images": [],
                        },
                        {
                            "at": "2026-07-28T07:40:00+08:00",
                            "sender_name": "辛玥",
                            "is_owner": True,
                            "text": "在这儿",
                            "images": [],
                        },
                    ],
                }
            ]
        }
        with (
            mock.patch.object(qq_activity_context, "_load_state", return_value=state),
            mock.patch.object(
                qq_activity_context.r2_store,
                "get_last_proactive_contact_at",
                return_value="2026-07-28T07:00:00+08:00",
            ),
            mock.patch.object(
                qq_activity_context,
                "now_beijing_iso",
                return_value="2026-07-28T08:00:00+08:00",
            ),
        ):
            payload = qq_activity_context.build_group_activity_delivery_for_wakeup()

        self.assertEqual(payload["group_id"], "778899")
        text = payload["content"]
        if isinstance(text, list):
            text = "\n".join(
                str(part.get("text") or "")
                for part in text
                if isinstance(part, dict) and part.get("type") == "text"
            )
        self.assertIn(QQ_GROUP_CONTENT_MARKER, text)
        self.assertIn("回复正文开头", text)
        self.assertIn("message 字段正文的开头", text)
        self.assertIn("私下找她时不要写这个标记", text)

    def test_marker_is_stripped_and_group_id_is_backend_metadata(self):
        from services.qq_group_delivery import (
            QQ_GROUP_CONTENT_MARKER,
            apply_qq_group_delivery_marker,
        )

        message = {"role": "assistant", "content": f"{QQ_GROUP_CONTENT_MARKER}群里逮你。"}
        changed = apply_qq_group_delivery_marker(message, group_id="778899", enabled=True)

        self.assertTrue(changed)
        self.assertEqual(message["content"], "群里逮你。")
        self.assertEqual(message["du_qq_group_delivery"], {"group_id": "778899"})

        ordinary = {
            "role": "assistant",
            "content": f"先私聊，后面才有 {QQ_GROUP_CONTENT_MARKER}",
            "du_qq_group_delivery": {"group_id": "123456"},
        }
        self.assertFalse(apply_qq_group_delivery_marker(ordinary, group_id="778899", enabled=True))
        self.assertNotIn("du_qq_group_delivery", ordinary)

    def test_wakeup_group_delivery_uses_connector_and_does_not_choose_group_in_model_text(self):
        from services import conversation_followup

        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            if str(url).endswith("/v1/chat/completions"):
                return _FakeResponse(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "群里逮你。",
                                    "du_qq_group_delivery": {"group_id": "778899"},
                                }
                            }
                        ]
                    },
                )
            if str(url).endswith("/push/group"):
                return _FakeResponse(200, {"ok": True})
            raise AssertionError(f"unexpected URL: {url}")

        with (
            mock.patch(
                "storage.upstream_store.get_cached_active_model",
                return_value="test-model",
            ),
            mock.patch.object(
                conversation_followup,
                "_choice_dialog_delivery_preference",
                return_value=("sumitalk", "device-1", {"at": "2026-07-28T07:30:00+08:00"}),
            ),
            mock.patch.object(conversation_followup.requests, "post", side_effect=fake_post),
            mock.patch.object(
                conversation_followup,
                "QQ_PROACTIVE_PUSH_URL",
                "http://127.0.0.1:8092/push",
            ),
        ):
            result = conversation_followup._send_wakeup_event(
                window_id="tg_1",
                target="device-1",
                event_text="后台唤醒",
                archive=False,
                wakeup_kind="proactive_trigger",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["channel"], "qq_group")
        self.assertEqual(result["attempted_channels"], ["qq_group"])
        group_call = next(item for item in calls if item[0].endswith("/push/group"))
        posted = json.loads(group_call[1]["data"].decode("utf-8"))
        self.assertEqual(posted, {"text": "群里逮你。", "group_id": "778899", "split": True})

    def test_failed_group_delivery_falls_back_without_marker(self):
        from services import conversation_followup

        dispatched = []

        def fake_post(url, **kwargs):
            if str(url).endswith("/v1/chat/completions"):
                return _FakeResponse(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "群里逮你。",
                                    "du_qq_group_delivery": {"group_id": "778899"},
                                }
                            }
                        ]
                    },
                )
            if str(url).endswith("/push/group"):
                return _FakeResponse(500, {"ok": False, "error": "offline"})
            raise AssertionError(f"unexpected URL: {url}")

        def fake_dispatch(channel, target, text, **kwargs):
            dispatched.append((channel, target, text))
            return True

        with (
            mock.patch(
                "storage.upstream_store.get_cached_active_model",
                return_value="test-model",
            ),
            mock.patch.object(
                conversation_followup,
                "_choice_dialog_delivery_preference",
                return_value=("sumitalk", "device-1", {"at": "2026-07-28T07:30:00+08:00"}),
            ),
            mock.patch.object(
                conversation_followup,
                "_choice_dialog_delivery_channels",
                return_value=["sumitalk"],
            ),
            mock.patch.object(
                conversation_followup,
                "_dispatch_choice_dialog_reply",
                side_effect=fake_dispatch,
            ),
            mock.patch.object(conversation_followup.requests, "post", side_effect=fake_post),
            mock.patch.object(
                conversation_followup,
                "QQ_PROACTIVE_PUSH_URL",
                "http://127.0.0.1:8092/push",
            ),
        ):
            result = conversation_followup._send_wakeup_event(
                window_id="tg_1",
                target="device-1",
                event_text="后台唤醒",
                archive=False,
                wakeup_kind="proactive_trigger",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["channel"], "sumitalk")
        self.assertEqual(result["attempted_channels"], ["qq_group", "sumitalk"])
        self.assertEqual(dispatched, [("sumitalk", "device-1", "群里逮你。")])

    def test_random_proactive_json_uses_marker_inside_message(self):
        from services import telegram_proactive
        from services.qq_group_delivery import QQ_GROUP_CONTENT_MARKER

        decision = telegram_proactive._parse_proactive_model_reply(
            json.dumps(
                {
                    "action": "send_message",
                    "reason": "去群里找她",
                    "message": f"{QQ_GROUP_CONTENT_MARKER}出来，逮到你了。",
                    "channel": "sumitalk",
                },
                ensure_ascii=False,
            ),
            "NO_CONTACT",
            default_channel="sumitalk",
            channels=["sumitalk"],
        )
        decision = telegram_proactive._apply_qq_group_delivery_to_decision(
            decision,
            {"du_qq_group_delivery_target": "778899"},
        )

        self.assertTrue(decision.should_send)
        self.assertEqual(decision.text, "出来，逮到你了。")
        self.assertEqual(decision.qq_group_id, "778899")
        self.assertEqual(decision.channel, "sumitalk")

    def test_random_proactive_group_failure_falls_back_to_original_channel(self):
        from services import telegram_proactive

        decision = telegram_proactive.ProactiveDecision(
            should_send=True,
            text="出来，逮到你了。",
            action="send_message",
            channel="sumitalk",
            qq_group_id="778899",
        )
        with (
            mock.patch.object(telegram_proactive, "_send_via_qq_group", return_value=False),
            mock.patch.object(telegram_proactive, "_dispatch_send", return_value=True) as fallback,
        ):
            ok, channel, attempted = telegram_proactive._dispatch_proactive_decision_message(
                decision,
                decision.text,
                fallback_channel="sumitalk",
                target_user_id=1,
            )

        self.assertTrue(ok)
        self.assertEqual(channel, "sumitalk")
        self.assertEqual(attempted, ["qq_group", "sumitalk"])
        fallback.assert_called_once_with("sumitalk", "出来，逮到你了。", target_user_id=1)

    def test_schedule_wakeup_keeps_backend_group_target(self):
        from services import telegram_proactive

        response = _FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "群里提醒你一下。",
                            "du_qq_group_delivery": {"group_id": "778899"},
                        }
                    }
                ]
            },
        )
        with (
            mock.patch.object(telegram_proactive, "_get_chat_model", return_value="test-model"),
            mock.patch.object(telegram_proactive.requests, "post", return_value=response),
        ):
            result = telegram_proactive._generate_schedule_reply(
                window_id="tg_1",
                user_id=1,
                prompt="日历提醒",
                preferred_channel="sumitalk",
                reply_target="device-1",
                wakeup_kind="calendar_event",
            )

        self.assertEqual(
            result,
            {"text": "群里提醒你一下。", "qq_group_id": "778899"},
        )


if __name__ == "__main__":
    unittest.main()
