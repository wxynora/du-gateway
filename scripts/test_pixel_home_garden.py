from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from services import pixel_home
from services.pixel_home_garden import build_garden_state, record_garden_actions
from pipeline import pipeline
from utils.time_aware import BEIJING_TZ


CLEAR_SUMMER_WEATHER = {
    "key": "clear",
    "label": "晴天",
    "description": "阳光正落在花圃上",
    "season": "summer",
}


class PixelHomeGardenTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 15, 10, 0, tzinfo=BEIJING_TZ)

    def test_du_watering_records_existing_home_state_without_external_write(self):
        state, actions = record_garden_actions(
            {"du": {"spot": "study"}},
            actor="du",
            spot="garden",
            activity="给绣球浇花",
            now=self.now,
        )

        self.assertEqual(("water",), actions)
        self.assertEqual("2026-07-15T10:00:00+08:00", state["garden"]["last_watered_at"])
        self.assertEqual("du", state["garden"]["last_watered_by"])

    def test_seasonal_habit_drives_flower_and_watering_state(self):
        stored = {
            "last_watered_at": "2026-07-15T09:00:00+08:00",
            "last_watered_by": "du",
            "last_loosened_at": "2026-07-15T08:00:00+08:00",
            "last_loosened_by": "du",
        }
        with patch(
            "services.pixel_home_garden.build_virtual_home_weather",
            return_value=CLEAR_SUMMER_WEATHER,
        ):
            garden = build_garden_state(stored, CLEAR_SUMMER_WEATHER, now=self.now)

        self.assertEqual("绣球", garden["plant_name"])
        self.assertIn("夏天缺水会很快打蔫", garden["plant_habit"])
        self.assertTrue(garden["watered_today"])
        self.assertEqual("今日已浇水", garden["watering_label"])
        self.assertEqual("今日已松土", garden["loosen_label"])
        self.assertFalse(garden["needs_watering"])

    def test_unwatered_hydrangea_becomes_thirsty_but_rain_counts_as_water(self):
        with patch(
            "services.pixel_home_garden.build_virtual_home_weather",
            return_value=CLEAR_SUMMER_WEATHER,
        ):
            dry = build_garden_state({}, CLEAR_SUMMER_WEATHER, now=self.now)
        self.assertEqual("有点缺水", dry["flower_status"])
        self.assertTrue(dry["needs_watering"])
        self.assertEqual("今日还未浇水", dry["watering_label"])

        rain = {**CLEAR_SUMMER_WEATHER, "key": "rain", "label": "下雨"}
        with patch("services.pixel_home_garden.build_virtual_home_weather", return_value=rain):
            wet = build_garden_state({}, rain, now=self.now)
        self.assertEqual("今日有雨水补给", wet["watering_label"])
        self.assertFalse(wet["needs_watering"])
        self.assertEqual("正在听雨", wet["flower_status"])

    def test_hidden_du_garden_action_persists_through_existing_save_path(self):
        saved_payloads: list[dict] = []
        with patch.object(pixel_home, "_stored_state", return_value={}), patch.object(
            pixel_home,
            "save_pixel_home_state",
            side_effect=lambda payload: saved_payloads.append(payload) or True,
        ):
            actor = pixel_home.save_actor_state("du", "garden", "松土", source="du_marker")

        self.assertTrue(actor["ok"])
        self.assertEqual("du", saved_payloads[0]["garden"]["last_loosened_by"])
        self.assertTrue(saved_payloads[0]["garden"]["last_loosened_at"])

    def test_garden_state_reaches_dynamic_system_while_rules_stay_static(self):
        body = {
            "messages": [
                {"role": "system", "content": "核心规则"},
                {"role": "user", "content": "早"},
            ]
        }
        with patch.object(pixel_home, "format_rule_block", return_value="【小家状态写入规则】花园习性"), patch.object(
            pixel_home,
            "format_state_block",
            return_value="【小家状态】花园：绣球，长势很好；今日已浇水，土壤湿润。",
        ):
            result = pipeline.step_inject_pixel_home(body, "tg_test")

        dynamic = next(item for item in result["messages"] if item.get("__dynamic__"))
        plain_system = next(item for item in result["messages"] if item.get("role") == "system" and not item.get("__dynamic__"))
        self.assertIn("今日已浇水", dynamic["content"])
        self.assertNotIn("小家状态写入规则", dynamic["content"])
        self.assertIn("小家状态写入规则", plain_system["content"])


if __name__ == "__main__":
    unittest.main()
