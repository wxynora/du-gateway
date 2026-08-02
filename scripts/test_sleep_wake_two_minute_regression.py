#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import chat_activity_context, sense_context
from storage import runtime_sqlite, sense_store


class SleepWakeTwoMinuteRegressionTest(unittest.TestCase):
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
        patch_data = {
            "deviceId": "phone-1",
            "packageName": package_name,
            "appName": package_name,
            "observedAt": at,
            "source": "accessibility",
        }
        self.assertTrue(sense_store.update_app_sessions_from_foreground(patch_data))
        self.assertTrue(sense_store.mark_screen_awake_from_foreground(patch_data))

    def test_stable_real_app_session_confirms_after_two_minutes(self) -> None:
        self._screen("screen_off", "2026-07-30T06:00:00+08:00")
        self._foreground("com.android.chrome", "2026-07-30T07:40:57+08:00")
        self._foreground("com.android.systemui", "2026-07-30T07:43:07+08:00")

        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("completed", screen["sleepSession"]["state"])
        self.assertEqual("2026-07-30T07:40:57+08:00", screen["lastSleepBlock"]["endAt"])
        self.assertEqual("foreground_app", screen["lastSleepBlock"]["wakeSource"])

    def test_repeated_screen_off_preserves_same_candidate_activity_window(self) -> None:
        self._screen("screen_off", "2026-07-30T06:00:00+08:00")
        self._foreground("com.example.reader", "2026-07-30T07:40:00+08:00")
        self._screen("screen_off", "2026-07-30T07:41:00+08:00")

        pending = sense_store.get_sense_latest()["screen"]
        self.assertEqual("2026-07-30T07:40:00+08:00", pending["phoneWakeActivity"]["startAt"])

        self._foreground("com.example.reader", "2026-07-30T07:42:00+08:00")
        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("completed", screen["sleepSession"]["state"])
        self.assertEqual("2026-07-30T07:40:00+08:00", screen["lastSleepBlock"]["endAt"])

    def test_short_real_app_session_does_not_confirm(self) -> None:
        self._screen("screen_off", "2026-07-30T06:00:00+08:00")
        self._foreground("com.android.chrome", "2026-07-30T07:40:00+08:00")
        self._foreground("com.android.systemui", "2026-07-30T07:41:59+08:00")

        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("candidate", screen["sleepSession"]["state"])
        self.assertNotIn("lastSleepBlock", screen)

    def test_pc_activity_confirms_after_two_minutes(self) -> None:
        self._screen("screen_off", "2026-07-30T06:00:00+08:00")
        for at in ("2026-07-30T07:40:00+08:00", "2026-07-30T07:42:00+08:00"):
            self.assertTrue(
                sense_store.mark_screen_awake_from_pc_activity(
                    {
                        "deviceId": "mac-1",
                        "lastInputAt": at,
                        "observedAt": at,
                    }
                )
            )

        screen = sense_store.get_sense_latest()["screen"]
        self.assertEqual("completed", screen["sleepSession"]["state"])
        self.assertEqual("2026-07-30T07:40:00+08:00", screen["lastSleepBlock"]["endAt"])
        self.assertEqual("pc_activity", screen["lastSleepBlock"]["wakeSource"])

    def test_confirmed_summary_remains_visible_while_new_candidate_exists(self) -> None:
        sense = {
            "screen": {
                "sleepSession": {
                    "state": "candidate",
                    "startAt": "2026-07-30T05:40:57+08:00",
                },
                "screenOffSince": "2026-07-30T05:40:57+08:00",
                "sleepSummary": {
                    "sleepDate": "2026-07-30",
                    "startAt": "2026-07-29T21:54:24+08:00",
                    "endAt": "2026-07-30T08:17:24+08:00",
                    "totalMinutes": 530,
                    "segmentCount": 2,
                    "awakeGapMinutes": 92,
                },
            }
        }
        with (
            patch.object(sense_context.r2_store, "get_sense_latest", return_value=sense),
            patch.object(chat_activity_context, "build_chat_activity_context_line", return_value=""),
            patch.object(sense_context, "now_beijing_iso", return_value="2026-07-30T08:30:00+08:00"),
        ):
            snapshot = sense_context.format_sense_snapshot_for_system()

        self.assertIn("累计 8小时50分钟", snapshot)
        self.assertIn("分 2 段", snapshot)
        self.assertIn("睡眠候选：手机从 7月30日 05:40 起熄屏", snapshot)


if __name__ == "__main__":
    unittest.main()
