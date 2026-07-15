"""Deterministic fictional weather for the shared PixelHome scene."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from utils.time_aware import BEIJING_TZ

VIRTUAL_WEATHER_SLOT_HOURS = 4

_WEATHER_PROFILES: dict[str, dict[str, str]] = {
    "clear": {
        "label": "晴天",
        "description": "阳光正落在屋顶和花圃上",
    },
    "cloudy": {
        "label": "多云",
        "description": "云影慢慢掠过院子",
    },
    "breeze": {
        "label": "微风",
        "description": "风正从花架和树梢间穿过去",
    },
    "light_rain": {
        "label": "小雨",
        "description": "细雨落在花叶和石径上",
    },
    "rain": {
        "label": "下雨",
        "description": "雨点敲着屋檐，花圃湿漉漉的",
    },
    "heavy_rain": {
        "label": "暴雨",
        "description": "密雨压过院子，水沿着屋檐成串落下",
    },
    "mist": {
        "label": "轻雾",
        "description": "院角浮着一层很浅的雾",
    },
    "light_snow": {
        "label": "小雪",
        "description": "细雪落在屋顶、花枝和石径上",
    },
}

# 日期和四季跟随现实日历；具体天气只由小家引擎生成，不读取现实天气。
# 每条是一整天的自然天气轨迹，避免页面刷新乱跳，也避免相邻时段突兀跳变。
_SEASONAL_WEATHER_CYCLES: dict[str, tuple[tuple[str, ...], ...]] = {
    "spring": (
        ("mist", "cloudy", "light_rain", "rain", "cloudy", "breeze"),
        ("cloudy", "light_rain", "cloudy", "clear", "breeze", "cloudy"),
        ("mist", "cloudy", "clear", "breeze", "cloudy", "light_rain"),
        ("light_rain", "rain", "cloudy", "breeze", "clear", "cloudy"),
    ),
    "summer": (
        ("clear", "clear", "cloudy", "heavy_rain", "rain", "cloudy"),
        ("cloudy", "clear", "clear", "breeze", "cloudy", "rain"),
        ("clear", "breeze", "clear", "cloudy", "light_rain", "cloudy"),
        ("cloudy", "light_rain", "cloudy", "clear", "clear", "breeze"),
        ("clear", "cloudy", "rain", "heavy_rain", "cloudy", "breeze"),
    ),
    "autumn": (
        ("mist", "cloudy", "clear", "breeze", "clear", "cloudy"),
        ("cloudy", "light_rain", "cloudy", "breeze", "clear", "clear"),
        ("clear", "clear", "breeze", "cloudy", "light_rain", "cloudy"),
        ("mist", "breeze", "clear", "clear", "cloudy", "breeze"),
    ),
    "winter": (
        ("cloudy", "light_snow", "cloudy", "clear", "clear", "cloudy"),
        ("mist", "cloudy", "breeze", "clear", "cloudy", "light_snow"),
        ("clear", "clear", "cloudy", "breeze", "cloudy", "mist"),
        ("cloudy", "light_snow", "cloudy", "breeze", "clear", "clear"),
    ),
}

_SEASON_LABELS = {
    "spring": "春季",
    "summer": "夏季",
    "autumn": "秋季",
    "winter": "冬季",
}


def _beijing_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(BEIJING_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def virtual_weather_season(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def build_virtual_home_weather(now: datetime | None = None) -> dict[str, Any]:
    """Return the current fictional PixelHome weather without consulting reality."""
    current = _beijing_datetime(now)
    day_key = current.strftime("%Y-%m-%d")
    season = virtual_weather_season(current.month)
    digest = hashlib.sha256(f"pixel-home-weather-v1:{day_key}".encode("utf-8")).hexdigest()
    seasonal_cycles = _SEASONAL_WEATHER_CYCLES[season]
    cycle = seasonal_cycles[int(digest[:8], 16) % len(seasonal_cycles)]
    slot = current.hour // VIRTUAL_WEATHER_SLOT_HOURS
    weather_key = cycle[slot]
    profile = _WEATHER_PROFILES[weather_key]
    slot_started_at = current.replace(
        hour=slot * VIRTUAL_WEATHER_SLOT_HOURS,
        minute=0,
        second=0,
        microsecond=0,
    )
    changes_at = slot_started_at + timedelta(hours=VIRTUAL_WEATHER_SLOT_HOURS)
    return {
        "key": weather_key,
        "label": profile["label"],
        "description": profile["description"],
        "season": season,
        "season_label": _SEASON_LABELS[season],
        "changes_at": changes_at.isoformat(timespec="seconds"),
        "source": "pixel_home_virtual_engine",
        "is_virtual": True,
    }
