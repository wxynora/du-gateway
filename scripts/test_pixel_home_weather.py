from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from services import pixel_home
from services.pixel_home_weather import build_virtual_home_weather
from utils.time_aware import BEIJING_TZ


class PixelHomeWeatherTest(unittest.TestCase):
    def test_weather_is_stable_inside_one_virtual_slot(self):
        first = build_virtual_home_weather(datetime(2026, 7, 15, 9, 1, tzinfo=BEIJING_TZ))
        second = build_virtual_home_weather(datetime(2026, 7, 15, 11, 59, tzinfo=BEIJING_TZ))

        self.assertEqual(first, second)
        self.assertTrue(first["is_virtual"])
        self.assertEqual("pixel_home_virtual_engine", first["source"])
        self.assertEqual("2026-07-15T12:00:00+08:00", first["changes_at"])
        self.assertEqual("summer", first["season"])

    def test_real_calendar_selects_season_but_weather_stays_virtual(self):
        expected = {
            1: "winter",
            4: "spring",
            7: "summer",
            10: "autumn",
        }
        for month, season in expected.items():
            weather = build_virtual_home_weather(datetime(2026, month, 15, 10, tzinfo=BEIJING_TZ))
            self.assertEqual(season, weather["season"])
            self.assertTrue(weather["is_virtual"])
            self.assertNotIn("location", weather)

    def test_garden_is_a_real_pixel_home_spot(self):
        self.assertEqual("garden", pixel_home.normalize_spot("花园"))
        self.assertEqual("garden", pixel_home.normalize_spot("院子"))
        self.assertEqual("花园", pixel_home.spot_label("garden"))
        self.assertIn({"key": "garden", "label": "花园"}, pixel_home.SPOT_OPTIONS)

    def test_prompt_exposes_virtual_weather_and_du_garden_actions_without_r2(self):
        state = {
            "mode": "day",
            "weather": {
                "key": "drizzle",
                "label": "细雨",
                "description": "细雨落在花叶和石径上",
            },
            "garden": {
                "plant_name": "绣球",
                "flower_status": "长势很好",
                "watering_label": "今日已浇水",
                "soil_status": "湿润",
                "loosen_label": "近期已松土",
            },
            "du": {"spot": "garden", "activity": "松土"},
            "xinyue": {"spot": "sofa", "activity": "休息"},
            "du_vitals": {},
        }
        with patch.object(pixel_home, "build_pixel_home_state", return_value=state), patch.object(
            pixel_home,
            "_stored_state",
            return_value={},
        ):
            state_block = pixel_home.format_state_block()
            rule_block = pixel_home.format_rule_block()

        self.assertIn("小家天气：细雨，细雨落在花叶和石径上。", state_block)
        self.assertIn("花园：绣球，长势很好；今日已浇水，土壤湿润，近期已松土。", state_block)
        self.assertIn("你的位置：花园，正在松土。", state_block)
        self.assertIn("与现实城市、定位和真实天气无关", rule_block)
        self.assertIn("花园里的花有自己的季节和养护习性", rule_block)
        self.assertIn("你想去浇花、松土时可以主动行动", rule_block)


if __name__ == "__main__":
    unittest.main()
