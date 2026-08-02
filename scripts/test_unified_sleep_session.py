#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys
from unittest.mock import ANY, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask

from routes import pc_command
from services import du_daily, pixel_home, proactive_trigger_engine, sense_context
from storage import runtime_sqlite, sense_store
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing


class UnifiedSleepSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = runtime_sqlite.RUNTIME_STATE_DB
        self._old_schema_ready = runtime_sqlite._SCHEMA_READY
        self._old_bootstrapped = sense_store._SENSE_BOOTSTRAPPED
        runtime_sqlite.RUNTIME_STATE_DB = str(Path(self._tmp.name) / "runtime.db")
        runtime_sqlite._SCHEMA_READY = False
        sense_store._SENSE_BOOTSTRAPPED = True
        self._persist = patch.object(sense_store, "_persist_sleep_summary")
        self._persist.start()

    def tearDown(self) -> None:
        self._persist.stop()
        runtime_sqlite.RUNTIME_STATE_DB = self._old_db
        runtime_sqlite._SCHEMA_READY = self._old_schema_ready
        sense_store._SENSE_BOOTSTRAPPED = self._old_bootstrapped
        self._tmp.cleanup()

    def _screen(self, event: str, at: str) -> None:
        self.assertTrue(
            sense_store.merge_and_save_sense_bucket(
                "screen",
                {
                    "deviceId": "phone-1",
                    "event": event,
                    "interactive": event != "screen_off",
                    "occurredAt": at,
                    "observedAt": at,
                },
            )
        )

    def _foreground(self, package_name: str, at: str) -> None:
        self.assertTrue(
            sense_store.mark_screen_awake_from_foreground(
                {
                    "deviceId": "phone-1",
                    "packageName": package_name,
                    "appName": package_name,
                    "observedAt": at,
                }
            )
        )

    def _health(self, at: str, *, steps: int, heart_rate: int) -> None:
        self.assertTrue(
            sense_store.merge_and_save_sense_bucket(
                "health",
                {
                    "deviceId": "phone-1",
                    "steps": steps,
                    "heart_rate": heart_rate,
                    "capturedAt": at,
                },
            )
        )

    def _confirmed_phone_sleep(self, start_at: str, wake_at: str) -> dict:
        self._screen("screen_off", start_at)
        self._screen("screen_on", wake_at)
        self._foreground("com.example.same", wake_at)
        pending = sense_store.get_sense_latest()["screen"]
        self.assertEqual("candidate", pending["sleepSession"]["state"])
        self.assertEqual(start_at, pending["sleepSession"]["startAt"])
        confirmed_at = (parse_iso_to_beijing(wake_at) + timedelta(minutes=3)).isoformat()
        self._foreground("com.example.same", confirmed_at)
        return sense_store.get_sense_latest()["screen"]

    def test_yesterday_afternoon_stays_on_start_date(self) -> None:
        screen = self._confirmed_phone_sleep(
            "2026-07-25T14:00:00+08:00",
            "2026-07-25T17:30:00+08:00",
        )
        block = screen["lastSleepBlock"]
        self.assertEqual("sleep", block["classification"])
        self.assertEqual("2026-07-25T14:00:00+08:00", block["startAt"])
        self.assertEqual("2026-07-25T17:30:00+08:00", block["endAt"])
        self.assertEqual(210, block["minutes"])
        self.assertEqual("2026-07-25", screen["sleepSummary"]["sleepDate"])
        with patch.object(sense_context, "now_beijing_iso", return_value="2026-07-26T18:00:00+08:00"):
            line = sense_context._format_last_sleep_summary_line(screen)
        self.assertIn("昨天（7月25日）睡眠：14:00–17:30", line or "")
        self.assertNotIn("主睡眠", line or "")
        self.assertNotIn("午睡", line or "")

    def test_cross_midnight_sleep_belongs_to_wake_date(self) -> None:
        screen = self._confirmed_phone_sleep(
            "2026-07-25T23:30:00+08:00",
            "2026-07-26T00:20:00+08:00",
        )
        self.assertEqual("2026-07-26", screen["sleepSummary"]["sleepDate"])
        with patch.object(sense_context, "now_beijing_iso", return_value="2026-07-26T01:00:00+08:00"):
            line = sense_context._format_last_sleep_summary_line(screen)
        self.assertIn("今天（7月26日）睡眠：7月25日 23:30–7月26日 00:20", line or "")

    def test_ten_minutes_with_high_heart_rate_is_rejected_and_cannot_wake_du(self) -> None:
        self._screen("screen_off", "2026-07-28T07:32:08+08:00")
        self._health("2026-07-28T07:34:00+08:00", steps=22, heart_rate=113)
        self._health("2026-07-28T07:40:00+08:00", steps=22, heart_rate=114)
        self._screen("screen_on", "2026-07-28T07:42:18+08:00")
        self._foreground("com.tencent.mobileqq", "2026-07-28T07:42:20+08:00")
        self._foreground("com.tencent.mobileqq", "2026-07-28T07:45:20+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        block = screen["lastSleepBlock"]
        self.assertEqual("rejected_sleep", block["classification"])
        self.assertFalse(block["confirmed"])
        self.assertEqual("sleep_too_short", block["summaryReason"])
        self.assertFalse(block["summaryIncluded"])
        self.assertEqual("rejected", screen["sleepSession"]["state"])
        self.assertNotIn("sleepSummary", screen)

        history = [{"type": "screen", "at": "2026-07-28T07:45:20+08:00", "data": screen}]
        with (
            patch.object(proactive_trigger_engine, "_has_normal_user_chat_after", return_value=False),
            patch.object(proactive_trigger_engine, "_latest_sleep_message", return_value=None),
            patch.object(proactive_trigger_engine, "_build_no_reply_soft_trigger", return_value=None),
        ):
            events = proactive_trigger_engine._build_events(
                {"screen": screen},
                history,
                "tg_1",
                datetime(2026, 7, 28, 7, 46, tzinfo=BEIJING_TZ),
            )
        self.assertFalse(any(event.trigger_type == "morning_first_screen_on" for event in events))

    def test_thirty_minutes_with_sleep_like_health_is_accepted(self) -> None:
        self._screen("screen_off", "2026-07-26T13:00:00+08:00")
        self._health("2026-07-26T13:05:00+08:00", steps=1000, heart_rate=76)
        self._health("2026-07-26T13:25:00+08:00", steps=1008, heart_rate=69)
        self._screen("screen_on", "2026-07-26T13:30:00+08:00")
        self._foreground("com.example.first", "2026-07-26T13:30:10+08:00")
        self._foreground("com.example.first", "2026-07-26T13:33:10+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        block = screen["lastSleepBlock"]
        self.assertEqual("sleep", block["classification"])
        self.assertTrue(block["confirmed"])
        self.assertEqual(30, block["minutes"])
        self.assertEqual(1.0, block["sleepConfidence"])
        self.assertTrue(block["summaryIncluded"])

    def test_fifty_minutes_is_not_filtered(self) -> None:
        screen = self._confirmed_phone_sleep(
            "2026-07-26T14:00:00+08:00",
            "2026-07-26T14:50:00+08:00",
        )
        self.assertTrue(screen["lastSleepBlock"]["summaryIncluded"])
        self.assertEqual(50, screen["sleepSummary"]["totalMinutes"])

    def test_low_heart_rate_and_steps_support_sleep_and_are_exposed(self) -> None:
        self._screen("screen_off", "2026-07-26T14:00:00+08:00")
        self._health("2026-07-26T14:05:00+08:00", steps=1000, heart_rate=76)
        self._health("2026-07-26T14:45:00+08:00", steps=1012, heart_rate=68)
        self._screen("screen_on", "2026-07-26T14:50:00+08:00")
        self._foreground("com.example.first", "2026-07-26T14:50:10+08:00")
        self._foreground("com.example.first", "2026-07-26T14:53:10+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        evidence = screen["lastSleepBlock"]["healthEvidence"]
        self.assertEqual(
            {"sampleCount": 2, "first": 1000, "last": 1012, "delta": 12},
            evidence["steps"],
        )
        self.assertEqual(
            {"sampleCount": 2, "min": 68, "max": 76, "average": 72},
            evidence["heartRate"],
        )
        self.assertEqual(evidence, screen["sleepSummary"]["healthEvidence"])
        with patch.object(sense_context, "now_beijing_iso", return_value="2026-07-26T15:00:00+08:00"):
            line = sense_context._format_last_sleep_summary_line(screen)
        self.assertIn("区间佐证：步数变化 12 步（2 个样本）", line or "")
        self.assertIn("心率 68–76，平均 72（2 个样本）", line or "")

    def test_fifty_minutes_with_high_heart_rate_is_rejected_despite_still_steps(self) -> None:
        self._screen("screen_off", "2026-07-26T14:00:00+08:00")
        self._health("2026-07-26T14:05:00+08:00", steps=1000, heart_rate=111)
        self._health("2026-07-26T14:45:00+08:00", steps=1000, heart_rate=112)
        self._screen("screen_on", "2026-07-26T14:50:00+08:00")
        self._foreground("com.example.first", "2026-07-26T14:50:10+08:00")
        self._foreground("com.example.first", "2026-07-26T14:53:10+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        block = screen["lastSleepBlock"]
        self.assertEqual("rejected_sleep", block["classification"])
        self.assertFalse(block["confirmed"])
        self.assertEqual("sleep_low_confidence", block["summaryReason"])
        self.assertIn("heart_rate_high", block["negativeSignals"])
        self.assertIn("low_steps", block["positiveSignals"])
        self.assertFalse(block["summaryIncluded"])
        self.assertNotIn("sleepSummary", screen)

    def test_fifty_minutes_with_high_steps_is_rejected_despite_sleep_like_heart_rate(self) -> None:
        self._screen("screen_off", "2026-07-26T14:00:00+08:00")
        self._health("2026-07-26T14:05:00+08:00", steps=1000, heart_rate=72)
        self._health("2026-07-26T14:45:00+08:00", steps=1700, heart_rate=68)
        self._screen("screen_on", "2026-07-26T14:50:00+08:00")
        self._foreground("com.example.first", "2026-07-26T14:50:10+08:00")
        self._foreground("com.example.first", "2026-07-26T14:53:10+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        block = screen["lastSleepBlock"]
        self.assertEqual("rejected_sleep", block["classification"])
        self.assertFalse(block["confirmed"])
        self.assertIn("sleep_like_heart_rate", block["positiveSignals"])
        self.assertIn("steps_high", block["negativeSignals"])
        self.assertFalse(block["summaryIncluded"])
        self.assertNotIn("sleepSummary", screen)

    def test_cross_midnight_evidence_reads_both_calendar_days(self) -> None:
        self._screen("screen_off", "2026-07-25T23:30:00+08:00")
        self._health("2026-07-25T23:40:00+08:00", steps=9000, heart_rate=70)
        self._health("2026-07-26T00:10:00+08:00", steps=10, heart_rate=65)
        self._screen("screen_on", "2026-07-26T00:20:00+08:00")
        self._foreground("com.example.first", "2026-07-26T00:20:10+08:00")
        self._foreground("com.example.first", "2026-07-26T00:23:10+08:00")
        evidence = sense_store.get_sense_latest()["screen"]["lastSleepBlock"]["healthEvidence"]
        self.assertEqual(2, evidence["steps"]["sampleCount"])
        self.assertNotIn("delta", evidence["steps"])
        self.assertEqual(2, evidence["heartRate"]["sampleCount"])

    def test_same_app_continuous_three_minutes_confirms_and_backfills_activity_start(self) -> None:
        self._screen("screen_off", "2026-07-26T16:00:00+08:00")
        self._screen("screen_on", "2026-07-26T16:50:00+08:00")
        self._foreground("com.example.same", "2026-07-26T16:51:00+08:00")
        self._foreground("com.example.same", "2026-07-26T16:52:00+08:00")
        pending = sense_store.get_sense_latest()["screen"]
        self.assertEqual("candidate", pending["sleepSession"]["state"])
        self._foreground("com.example.same", "2026-07-26T16:54:00+08:00")
        completed = sense_store.get_sense_latest()["screen"]
        self.assertEqual("2026-07-26T16:51:00+08:00", completed["lastSleepBlock"]["endAt"])
        self.assertEqual("2026-07-26T16:54:00+08:00", completed["lastSleepBlock"]["confirmedAt"])

    def test_launcher_does_not_start_phone_activity_window(self) -> None:
        self._screen("screen_off", "2026-07-26T16:00:00+08:00")
        self._screen("screen_on", "2026-07-26T16:50:00+08:00")
        self._foreground("com.miui.home", "2026-07-26T16:50:10+08:00")
        self.assertEqual("candidate", sense_store.get_sense_latest()["screen"]["sleepSession"]["state"])
        self._foreground("com.example.real", "2026-07-26T16:50:20+08:00")
        self._foreground("com.example.real", "2026-07-26T16:53:20+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("completed", screen["sleepSession"]["state"])
        self.assertEqual("2026-07-26T16:50:20+08:00", screen["lastSleepBlock"]["endAt"])

    def test_pc_continuous_three_minutes_closes_at_activity_start(self) -> None:
        self._screen("screen_off", "2026-07-26T18:00:00+08:00")
        for minute in (50, 51, 52):
            self.assertTrue(
                sense_store.mark_screen_awake_from_pc_activity(
                    {
                        "deviceId": "mac-1",
                        "lastInputAt": f"2026-07-26T18:{minute:02d}:00+08:00",
                        "observedAt": f"2026-07-26T18:{minute:02d}:20+08:00",
                    }
                )
            )
            self.assertEqual("candidate", sense_store.get_sense_latest()["screen"]["sleepSession"]["state"])
        self.assertTrue(
            sense_store.mark_screen_awake_from_pc_activity(
                {
                    "deviceId": "mac-1",
                    "lastInputAt": "2026-07-26T18:53:00+08:00",
                    "observedAt": "2026-07-26T18:53:20+08:00",
                }
            )
        )
        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("completed", screen["sleepSession"]["state"])
        self.assertEqual("2026-07-26T18:50:00+08:00", screen["lastSleepBlock"]["endAt"])
        self.assertEqual("pc_activity", screen["lastSleepBlock"]["wakeSource"])

    def test_single_delayed_pc_input_does_not_close_candidate(self) -> None:
        self._screen("screen_off", "2026-07-26T17:09:44+08:00")
        self.assertTrue(
            sense_store.mark_screen_awake_from_pc_activity(
                {
                    "deviceId": "mac-1",
                    "lastInputAt": "2026-07-26T18:38:56+08:00",
                    "observedAt": "2026-07-27T00:23:45+08:00",
                }
            )
        )
        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("candidate", screen["sleepSession"]["state"])
        self.assertNotIn("lastSleepBlock", screen)

    def test_computer_sense_keeps_latest_without_history(self) -> None:
        self.assertTrue(
            sense_store.merge_and_save_sense_bucket(
                "computer",
                {
                    "deviceId": "mac-1",
                    "lastInputAt": "2026-07-26T18:50:00+08:00",
                },
            )
        )
        self.assertTrue(
            sense_store.merge_and_save_sense_bucket(
                "computer",
                {
                    "deviceId": "mac-1",
                    "lastInputAt": "2026-07-26T18:51:00+08:00",
                },
            )
        )
        computer = sense_store.get_sense_latest()["computer"]
        self.assertEqual("2026-07-26T18:51:00+08:00", computer["lastInputAt"])
        history = sense_store.get_sense_history_for_date("2026-07-26", limit=None)
        self.assertFalse(any(item.get("type") == "computer" for item in history))

    def test_same_date_sessions_are_aggregated_only_by_date(self) -> None:
        self._confirmed_phone_sleep(
            "2026-07-26T14:00:00+08:00",
            "2026-07-26T14:50:00+08:00",
        )
        screen = self._confirmed_phone_sleep(
            "2026-07-26T19:00:00+08:00",
            "2026-07-26T19:30:00+08:00",
        )
        summary = screen["sleepSummary"]
        self.assertEqual("2026-07-26", summary["sleepDate"])
        self.assertEqual(2, summary["segmentCount"])
        self.assertEqual(80, summary["totalMinutes"])

    def test_confirmed_daytime_sleep_creates_wakeup_event_without_main_sleep(self) -> None:
        screen = self._confirmed_phone_sleep(
            "2026-07-26T14:00:00+08:00",
            "2026-07-26T14:50:00+08:00",
        )
        history = [
            {
                "type": "screen",
                "at": "2026-07-26T14:51:00+08:00",
                "data": screen,
            }
        ]
        now_dt = datetime(2026, 7, 26, 14, 52, tzinfo=BEIJING_TZ)
        with (
            patch.object(proactive_trigger_engine, "_has_normal_user_chat_after", return_value=False),
            patch.object(proactive_trigger_engine, "_latest_sleep_message", return_value=None),
            patch.object(proactive_trigger_engine, "_build_no_reply_soft_trigger", return_value=None),
        ):
            events = proactive_trigger_engine._build_events(
                {"screen": screen},
                history,
                "tg_1",
                now_dt,
            )
        wakeups = [event for event in events if event.trigger_type == "sleep_wakeup"]
        self.assertEqual(1, len(wakeups))
        self.assertIn("50 分钟", wakeups[0].fact)

    def test_daily_and_pixel_home_consume_the_unified_candidate(self) -> None:
        now_dt = parse_iso_to_beijing(now_beijing_iso())
        self.assertIsNotNone(now_dt)
        started_at = (now_dt - timedelta(minutes=61)).isoformat()
        sense = {
            "screen": {
                "sleepSession": {
                    "state": "candidate",
                    "startAt": started_at,
                }
            }
        }
        state = {
            "today_summary": "",
            "today_events": ["今天发生过一件事"],
            "today_finalized_for_date": "",
            "sleep_closed_for_date": "",
        }
        with (
            patch.object(du_daily, "get_prepared_state", return_value=(state, False)),
            patch.object(du_daily.r2_store, "get_sense_latest", return_value=sense),
            patch.object(
                du_daily.r2_store,
                "get_last_user_activity_at",
                return_value=(now_dt - timedelta(minutes=70)).isoformat(),
            ),
        ):
            trigger = du_daily.infer_sleep_rollover_trigger()
        self.assertEqual("sleep_inferred", (trigger or {}).get("kind"))
        with patch.object(pixel_home.r2_store, "get_sense_latest", return_value=sense):
            sleeping, source = pixel_home._sleeping_state(now_dt.replace(hour=23), True)
        self.assertTrue(sleeping)
        self.assertEqual("sleep_candidate", source)
        with patch.object(pixel_home.r2_store, "get_sense_latest", return_value=sense):
            daytime_sleeping, daytime_source = pixel_home._sleeping_state(now_dt.replace(hour=15), False)
        self.assertTrue(daytime_sleeping)
        self.assertEqual("sleep_candidate", daytime_source)

    def test_pc_activity_route_uses_pc_token_and_explicit_input_time(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(pc_command.bp)
        client = app.test_client()
        with (
            patch.object(pc_command, "PC_COMMAND_TOKEN", "test-token"),
            patch.object(pc_command, "mark_screen_awake_from_pc_activity", return_value=True) as awake,
            patch.object(pc_command.r2_store, "get_sense_latest", return_value={}),
            patch.object(pc_command.r2_store, "merge_and_save_sense_bucket", return_value=True) as save,
        ):
            response = client.post(
                "/api/pc_activity",
                headers={"X-PC-Token": "test-token"},
                json={
                    "device_id": "mac-1",
                    "platform": "darwin",
                    "last_input_at": "2026-07-26T18:50:00+08:00",
                    "idle_seconds": 0.4,
                },
            )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["ok"])
        awake.assert_called_once()
        save.assert_called_once_with(
            "computer",
            ANY,
        )

    def test_pc_activity_route_does_not_replay_unchanged_input_into_sleep(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(pc_command.bp)
        client = app.test_client()
        current = {
            "computer": {
                "deviceId": "mac-1",
                "lastInputAt": "2026-07-26T18:38:56+08:00",
            }
        }
        with (
            patch.object(pc_command, "PC_COMMAND_TOKEN", "test-token"),
            patch.object(pc_command, "mark_screen_awake_from_pc_activity", return_value=True) as awake,
            patch.object(pc_command.r2_store, "get_sense_latest", return_value=current),
            patch.object(pc_command.r2_store, "merge_and_save_sense_bucket", return_value=True) as save,
        ):
            response = client.post(
                "/api/pc_activity",
                headers={"X-PC-Token": "test-token"},
                json={
                    "device_id": "mac-1",
                    "platform": "darwin",
                    "last_input_at": "2026-07-26T18:38:56+08:00",
                    "idle_seconds": 20700,
                },
            )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["skipped"])
        awake.assert_not_called()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
