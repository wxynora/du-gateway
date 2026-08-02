#!/usr/bin/env python3
"""Regression contract for automatic three-day long-term memory updates."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import du_longterm_memory, du_midterm_memory


class DuLongtermMemoryAutoUpdateTest(unittest.TestCase):
    def test_version_id_keeps_same_second_multi_segment_backups_distinct(self) -> None:
        first = du_longterm_memory._version_id(
            {"updated_at": "2026-07-29T01:12:00+08:00", "covered_through": "2026-07-15"}
        )
        second = du_longterm_memory._version_id(
            {"updated_at": "2026-07-29T01:12:00+08:00", "covered_through": "2026-07-18"}
        )

        self.assertNotEqual(first, second)

    def test_next_window_only_contains_days_outside_active_midterm(self) -> None:
        latest = {"covered_through": "2026-07-12"}

        self.assertIsNone(
            du_longterm_memory._next_segment_window(
                latest,
                {"period_start": "2026-07-13"},
            )
        )
        self.assertEqual(
            du_longterm_memory._next_segment_window(
                latest,
                {"period_start": "2026-07-16"},
            ),
            (date(2026, 7, 13), date(2026, 7, 15)),
        )

    def test_collect_sources_reports_missing_day_and_keeps_all_matching_portraits(self) -> None:
        daily = [
            {"day": "2026-07-13", "today_events": ["a"]},
            {"day": "2026-07-14", "today_events": ["b"]},
            {"day": "2026-07-16", "today_events": ["outside"]},
        ]
        du_portraits = [
            {
                "id": "du-1",
                "created_at": "2026-07-12T08:00:00+08:00",
                "updated_at": "2026-07-13T08:00:00+08:00",
                "summary": "渡画像",
            },
        ]
        xinyue_portraits = [
            {"id": "x-1", "created_at": "2026-07-15T09:00:00+08:00", "summary": "辛玥画像"},
            {"id": "x-2", "created_at": "2026-07-16T09:00:00+08:00", "summary": "窗口外"},
        ]
        with (
            patch.object(du_longterm_memory.du_state_store, "get_du_daily_archive", return_value=daily),
            patch.object(
                du_longterm_memory.du_state_store,
                "get_du_portrait_candidates",
                return_value=du_portraits,
            ),
            patch.object(
                du_longterm_memory.du_state_store,
                "get_xinyue_portrait_candidates",
                return_value=xinyue_portraits,
            ),
        ):
            selected_daily, missing_days, portraits = du_longterm_memory._collect_segment_sources(
                date(2026, 7, 13),
                date(2026, 7, 15),
            )

        self.assertEqual([item["day"] for item in selected_daily], ["2026-07-13", "2026-07-14"])
        self.assertEqual(missing_days, ["2026-07-15"])
        self.assertEqual([item["id"] for item in portraits], ["du-1", "x-1"])

    def test_apply_segment_saves_old_version_before_advancing_latest(self) -> None:
        current = {
            "schema_version": 1,
            "content": "旧长期",
            "covered_through": "2026-07-12",
            "updated_at": "2026-07-28T13:40:50+08:00",
        }
        segment = {
            "segment_id": "2026-07-13_2026-07-15",
            "end_date": "2026-07-15",
            "content": "中期增量",
            "portrait_items": [],
        }
        parent = MagicMock()
        parent.attach_mock(
            MagicMock(return_value=True),
            "save_version",
        )
        parent.attach_mock(
            MagicMock(return_value=True),
            "save_latest",
        )
        with (
            patch.object(
                du_longterm_memory,
                "_generate_updated_content",
                return_value=("新长期", ""),
            ),
            patch.object(
                du_longterm_memory.du_state_store,
                "save_du_longterm_version",
                parent.save_version,
            ),
            patch.object(
                du_longterm_memory.du_state_store,
                "save_du_longterm_memory",
                parent.save_latest,
            ),
            patch.object(
                du_longterm_memory,
                "now_beijing_iso",
                return_value="2026-07-29T01:12:00+08:00",
            ),
        ):
            result = du_longterm_memory._apply_segment(current, segment)

        self.assertTrue(result["ok"])
        self.assertEqual(
            [call[0] for call in parent.mock_calls],
            ["save_version", "save_latest"],
        )
        saved_latest = parent.save_latest.call_args.args[0]
        self.assertEqual(saved_latest["content"], "新长期")
        self.assertEqual(saved_latest["covered_through"], "2026-07-15")
        self.assertEqual(saved_latest["source_increment_ids"], ["2026-07-13_2026-07-15"])

    def test_failed_latest_save_does_not_report_update(self) -> None:
        current = {
            "content": "旧长期",
            "covered_through": "2026-07-12",
            "updated_at": "2026-07-28T13:40:50+08:00",
        }
        segment = {
            "segment_id": "2026-07-13_2026-07-15",
            "end_date": "2026-07-15",
        }
        with (
            patch.object(
                du_longterm_memory,
                "_generate_updated_content",
                return_value=("新长期", ""),
            ),
            patch.object(
                du_longterm_memory.du_state_store,
                "save_du_longterm_version",
                return_value=True,
            ),
            patch.object(
                du_longterm_memory.du_state_store,
                "save_du_longterm_memory",
                return_value=False,
            ),
        ):
            result = du_longterm_memory._apply_segment(current, segment)

        self.assertFalse(result["ok"])
        self.assertFalse(result["updated"])
        self.assertEqual(result["error"], "latest_save_failed")

    def test_midterm_success_starts_longterm_refresh_with_new_window(self) -> None:
        daily_archive = [{"day": "2026-07-16", "summary": "素材", "age_days": 0, "bucket": "daily"}]
        candidate = {
            "period_start": "2026-07-16",
            "period_end": "2026-07-29",
            "source_archive_days": 1,
            "source_portrait_items": 0,
            "content": "新中期",
        }
        with (
            patch.object(
                du_midterm_memory,
                "_collect_recent_daily",
                return_value=(daily_archive, {}, 1, "2026-07-16", "2026-07-29"),
            ),
            patch.object(du_midterm_memory, "_collect_portrait_candidates", return_value=[]),
            patch.object(du_midterm_memory, "get_latest_midterm_memory", return_value={}),
            patch.object(du_midterm_memory, "_call_ds", return_value=candidate),
            patch.object(du_midterm_memory, "_validate_generated", return_value=(True, "")),
            patch.object(du_midterm_memory.du_state_store, "get_du_midterm_memory", return_value={}),
            patch.object(du_midterm_memory.du_state_store, "save_du_midterm_memory", return_value=True),
            patch(
                "services.du_longterm_memory.refresh_if_due_background",
                return_value=True,
            ) as refresh,
        ):
            result = du_midterm_memory.generate_midterm_memory(save=True, force=True)

        self.assertTrue(result["saved"])
        self.assertTrue(result["longterm_refresh_started"])
        refresh.assert_called_once()
        self.assertEqual(refresh.call_args.kwargs["midterm"]["period_start"], "2026-07-16")


if __name__ == "__main__":
    unittest.main()
