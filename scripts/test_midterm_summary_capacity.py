from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from services import du_midterm_memory


class MidtermSummaryCapacityTest(unittest.TestCase):
    def test_ds_request_does_not_set_a_token_limit(self) -> None:
        captured_payload = {}

        class FakeResponse:
            status_code = 200
            text = ""

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"period_start":"2026-07-14","period_end":"2026-07-27",'
                                    '"source_archive_days":1,"source_portrait_items":0,"content":"测试正文"}'
                                )
                            }
                        }
                    ]
                }

        def fake_post(*args, **kwargs):
            captured_payload.update(kwargs["json"])
            return FakeResponse()

        with (
            patch.object(du_midterm_memory, "DEEPSEEK_API_KEY", "test-key"),
            patch.object(du_midterm_memory, "DEEPSEEK_API_URL", "https://example.invalid"),
            patch.object(du_midterm_memory.requests, "post", side_effect=fake_post),
        ):
            result = du_midterm_memory._call_ds("测试提示词")

        self.assertIsInstance(result, dict)
        self.assertNotIn("max_tokens", captured_payload)

    def test_daily_events_are_forwarded_in_full_without_count_or_text_truncation(self) -> None:
        long_event = "渡写的长事件：" + ("很长" * 120) + "，最后还写了接住。"
        events = ["事件一", "事件二", long_event, "事件四", "事件五", "事件六"]
        archive = [
            {
                "day": "2026-07-14",
                "yesterday_summary": "较早摘要",
                "today_events": ["较早事件"],
            },
            {
                "day": "2026-07-27",
                "yesterday_summary": "当天摘要",
                "today_events": events,
            }
        ]

        with (
            patch.object(du_midterm_memory.du_state_store, "get_du_daily_archive", return_value=archive),
            patch.object(du_midterm_memory.du_state_store, "get_du_daily_state", return_value={}),
        ):
            recent_archive, _, _, _, _ = du_midterm_memory._collect_recent_daily(date(2026, 7, 27))

        self.assertEqual([item["day"] for item in recent_archive], ["2026-07-14", "2026-07-27"])
        self.assertEqual(recent_archive[1]["events"], events)

    def test_prompt_and_validation_use_only_the_1000_character_output_cap(self) -> None:
        prompt = du_midterm_memory._build_prompt(
            period_start="2026-07-14",
            period_end="2026-07-27",
            source_archive_days=1,
            source_portrait_items=0,
            daily_archive=[],
            current_daily={},
            portrait_candidates=[],
            previous_content="",
        )
        self.assertIn("不超过 1000 个中文字符", prompt)
        self.assertIn("严格按时间先后从较早写到较晚", prompt)
        self.assertIn("禁止使用破折号", prompt)
        self.assertNotIn("180-420", prompt)
        self.assertNotIn("宁可漏掉旧细节", prompt)

        expected = {
            "period_start": "2026-07-14",
            "period_end": "2026-07-27",
            "source_archive_days": 1,
            "source_portrait_items": 0,
        }
        at_limit = {**expected, "content": "啊" * 1000}
        over_limit = {**expected, "content": "啊" * 1001}

        self.assertEqual(du_midterm_memory._validate_generated(at_limit, expected), (True, ""))
        self.assertEqual(
            du_midterm_memory._validate_generated(over_limit, expected),
            (False, "content_too_long"),
        )
        with_em_dash = {**expected, "content": ("这段正文按顺序写清楚。" * 8) + "不能突然折返—也不能用破折号。"}
        self.assertEqual(
            du_midterm_memory._validate_generated(with_em_dash, expected),
            (False, "em_dash"),
        )


if __name__ == "__main__":
    unittest.main()
