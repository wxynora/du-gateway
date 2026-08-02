#!/usr/bin/env python3
"""Regression tests for morning wakeups after recognized main sleep."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RecognizedMainSleepWakeupTests(unittest.TestCase):
    def _events(self, off_at: str, on_at: str, block: dict):
        from services import proactive_trigger_engine as engine
        from utils.time_aware import parse_iso_to_beijing

        on_data = {
            "deviceId": "device-test",
            "event": "app_active",
            "interactive": True,
            "occurredAt": on_at,
            "observedAt": on_at,
            "screenWakeSource": "foreground_app",
            "foregroundPackageName": "com.example.realapp",
            "lastSleepBlock": block,
        }
        history = [
            {
                "type": "screen",
                "at": off_at,
                "data": {
                    "deviceId": "device-test",
                    "event": "screen_off",
                    "occurredAt": off_at,
                    "screenOffSince": off_at,
                },
            },
            {"type": "screen", "at": on_at, "data": on_data},
        ]
        now_dt = parse_iso_to_beijing("2026-07-24T06:30:34+08:00")
        self.assertIsNotNone(now_dt)
        with (
            patch.object(engine, "_has_normal_user_chat_after", return_value=False),
            patch.object(engine, "_latest_sleep_message", return_value=None),
            patch.object(engine, "_build_no_reply_soft_trigger", return_value=None),
        ):
            return engine._build_events({"screen": on_data}, history, "tg_test", now_dt)

    def test_recognized_fifty_minute_main_sleep_triggers_morning_wakeup(self) -> None:
        events = self._events(
            "2026-07-24T05:39:40+08:00",
            "2026-07-24T06:30:15+08:00",
            {
                "startAt": "2026-07-24T05:39:40+08:00",
                "endAt": "2026-07-24T06:30:15+08:00",
                "durationMs": 3035000,
                "minutes": 50,
                "summaryIncluded": True,
                "classification": "main_sleep",
            },
        )

        self.assertIn("morning_first_screen_on", [event.trigger_type for event in events])

    def test_rejected_short_screen_off_does_not_trigger_morning_wakeup(self) -> None:
        events = self._events(
            "2026-07-24T06:16:00+08:00",
            "2026-07-24T06:30:15+08:00",
            {
                "startAt": "2026-07-24T06:16:00+08:00",
                "endAt": "2026-07-24T06:30:15+08:00",
                "durationMs": 855000,
                "minutes": 14,
                "summaryIncluded": False,
                "classification": "rejected_day_sleep",
            },
        )

        self.assertNotIn("morning_first_screen_on", [event.trigger_type for event in events])


if __name__ == "__main__":
    unittest.main(verbosity=2)
