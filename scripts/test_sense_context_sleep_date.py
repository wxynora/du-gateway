from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.sense_context import _format_last_sleep_summary_line, _format_sleep_summary_piece
from utils.time_aware import parse_iso_to_beijing


def _dt(value: str):
    parsed = parse_iso_to_beijing(value)
    assert parsed is not None
    return parsed


def test_yesterday_day_sleep_keeps_calendar_date() -> None:
    with patch("services.sense_context.now_beijing_iso", return_value="2026-07-21T10:00:00+08:00"):
        text = _format_sleep_summary_piece(
            "午睡",
            {"segmentCount": 1},
            210,
            _dt("2026-07-20T14:00:00+08:00"),
            _dt("2026-07-20T17:30:00+08:00"),
        )

    assert text == "昨天（7月20日） 14:00–17:30 午睡，累计 3小时30分钟"


def test_cross_day_sleep_shows_both_calendar_dates() -> None:
    with patch("services.sense_context.now_beijing_iso", return_value="2026-07-21T10:00:00+08:00"):
        text = _format_sleep_summary_piece(
            "主睡眠",
            {"segmentCount": 1},
            510,
            _dt("2026-07-20T23:40:00+08:00"),
            _dt("2026-07-21T08:10:00+08:00"),
        )

    assert text == "7月20日 23:40–7月21日 08:10 主睡眠，累计 8小时30分钟"


def test_short_valid_main_sleep_is_not_filtered_by_display_layer() -> None:
    with patch("services.sense_context.now_beijing_iso", return_value="2026-07-24T07:10:00+08:00"):
        text = _format_last_sleep_summary_line(
            {
                "sleepSummary": {
                    "nightDate": "2026-07-24",
                    "startAt": "2026-07-24T05:39:40+08:00",
                    "endAt": "2026-07-23T22:30:15.868Z",
                    "totalDurationMs": 3035868,
                    "totalMinutes": 50,
                    "segmentCount": 1,
                }
            }
        )

    assert text == "最近睡眠推断：今天（7月24日） 05:39–06:30 主睡眠，累计 50分钟；24h合计 50分钟。"


if __name__ == "__main__":
    test_yesterday_day_sleep_keeps_calendar_date()
    test_cross_day_sleep_shows_both_calendar_dates()
    test_short_valid_main_sleep_is_not_filtered_by_display_layer()
    print("sense_context sleep date tests passed")
