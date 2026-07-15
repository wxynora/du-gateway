"""Garden care rules for PixelHome.

Only explicit care actions are persisted. Plant condition, soil moisture and
care hints are derived from the real calendar, fictional home weather and the
stored action timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.pixel_home_weather import build_virtual_home_weather, virtual_weather_season
from utils.time_aware import BEIJING_TZ


PLANT_PROFILES: dict[str, dict[str, Any]] = {
    "spring": {
        "key": "cherry_blossom",
        "name": "樱花",
        "habit": "喜欢湿润、透气的土壤，但怕积水",
        "water_interval_hours": 30,
        "loosen_interval_days": 7,
        "wilt_threshold": 28,
        "soggy_threshold": 90,
        "healthy_description": "花瓣舒展，枝梢状态很好",
        "dry_description": "嫩叶微微发软，该补一点水了",
    },
    "summer": {
        "key": "hydrangea",
        "name": "绣球",
        "habit": "喜湿润、怕暴晒，夏天缺水会很快打蔫",
        "water_interval_hours": 18,
        "loosen_interval_days": 5,
        "wilt_threshold": 40,
        "soggy_threshold": 95,
        "healthy_description": "花球饱满，叶片很精神",
        "dry_description": "叶缘有点发软，已经开始想喝水了",
    },
    "autumn": {
        "key": "chrysanthemum",
        "name": "菊花",
        "habit": "喜欢疏松、微润的土壤，浇水不宜过量",
        "water_interval_hours": 32,
        "loosen_interval_days": 7,
        "wilt_threshold": 25,
        "soggy_threshold": 84,
        "healthy_description": "花瓣挺括，花苞长势稳定",
        "dry_description": "土面已经偏干，花瓣没刚才舒展了",
    },
    "winter": {
        "key": "plum_blossom",
        "name": "梅花",
        "habit": "耐寒也耐旱，冬天宜偏干养护、避免积水",
        "water_interval_hours": 48,
        "loosen_interval_days": 10,
        "wilt_threshold": 18,
        "soggy_threshold": 78,
        "healthy_description": "枝条清健，花苞安稳地缀在枝头",
        "dry_description": "盆土已经干透，可以少量补水",
    },
}

_WATER_ACTION_WORDS = ("浇花", "浇水", "给花补水")
_LOOSEN_ACTION_WORDS = ("松土", "翻土", "疏松土")
_RAIN_MOISTURE = {
    "light_rain": 64,
    "rain": 82,
    "heavy_rain": 100,
    "light_snow": 55,
}


def _beijing_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(BEIJING_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _beijing_datetime(parsed)


def _age_hours(value: Any, now: datetime) -> float | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds() / 3600)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def garden_action_keys(spot: Any, activity: Any) -> tuple[str, ...]:
    if str(spot or "").strip().lower() != "garden":
        return ()
    text = str(activity or "").strip()
    actions: list[str] = []
    if _contains_any(text, _WATER_ACTION_WORDS):
        actions.append("water")
    if _contains_any(text, _LOOSEN_ACTION_WORDS):
        actions.append("loosen")
    return tuple(actions)


def record_garden_actions(
    stored_state: dict,
    *,
    actor: str,
    spot: Any,
    activity: Any,
    now: datetime | None = None,
) -> tuple[dict, tuple[str, ...]]:
    """Record explicit care actions in the existing PixelHome state."""
    actions = garden_action_keys(spot, activity)
    current = dict(stored_state or {})
    if not actions:
        return current, ()

    timestamp = _beijing_datetime(now).isoformat(timespec="seconds")
    garden = dict(current.get("garden") or {})
    actor_key = "du" if str(actor or "").strip().lower() == "du" else "xinyue"
    if "water" in actions:
        garden["last_watered_at"] = timestamp
        garden["last_watered_by"] = actor_key
    if "loosen" in actions:
        garden["last_loosened_at"] = timestamp
        garden["last_loosened_by"] = actor_key
    garden["last_action"] = actions[-1]
    garden["last_action_at"] = timestamp
    garden["last_action_by"] = actor_key
    current["garden"] = garden
    return current, actions


def _recent_rain(now: datetime) -> tuple[int, bool]:
    """Return derived soil moisture from the previous 24 hours of home weather."""
    best = 0.0
    rained_today = False
    seen_slots: set[str] = set()
    for hours_ago in range(0, 25, 4):
        at = now - timedelta(hours=hours_ago)
        weather = build_virtual_home_weather(at)
        slot_key = str(weather.get("changes_at") or "")
        if slot_key in seen_slots:
            continue
        seen_slots.add(slot_key)
        key = str(weather.get("key") or "")
        initial = _RAIN_MOISTURE.get(key, 0)
        if initial <= 0:
            continue
        best = max(best, initial - (hours_ago * 1.35))
        if at.date() == now.date():
            rained_today = True
    return round(max(0.0, best)), rained_today


def _soil_moisture(garden: dict, profile: dict[str, Any], now: datetime) -> tuple[int, bool]:
    rain_moisture, rained_today = _recent_rain(now)
    water_age = _age_hours(garden.get("last_watered_at"), now)
    watered_moisture = 0.0
    if water_age is not None:
        interval = max(12.0, float(profile["water_interval_hours"]))
        drying_per_hour = 52.0 / interval
        watered_moisture = max(0.0, 88.0 - water_age * drying_per_hour)
    # An uninitialised garden starts slightly dry rather than pretending it was watered.
    moisture = max(24.0, watered_moisture, float(rain_moisture))
    return round(min(100.0, moisture)), rained_today


def build_garden_state(
    stored_garden: Any,
    weather: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _beijing_datetime(now)
    garden = dict(stored_garden) if isinstance(stored_garden, dict) else {}
    weather_state = weather if isinstance(weather, dict) else {}
    season = str(weather_state.get("season") or "").strip()
    if season not in PLANT_PROFILES:
        season = virtual_weather_season(current.month)
    profile = PLANT_PROFILES[season]

    moisture, rained_today = _soil_moisture(garden, profile, current)
    watered_at = _parse_datetime(garden.get("last_watered_at"))
    loosened_at = _parse_datetime(garden.get("last_loosened_at"))
    watered_today = bool(watered_at and watered_at.date() == current.date())
    loosened_today = bool(loosened_at and loosened_at.date() == current.date())
    loosen_age = _age_hours(garden.get("last_loosened_at"), current)
    loosened_recently = loosen_age is not None and loosen_age <= float(profile["loosen_interval_days"]) * 24

    if watered_today:
        watering_label = "今日已浇水"
    elif rained_today:
        watering_label = "今日有雨水补给"
    else:
        watering_label = "今日还未浇水"

    if moisture >= 82:
        soil_status = "偏湿"
    elif moisture >= 50:
        soil_status = "湿润"
    elif moisture >= 30:
        soil_status = "微干"
    else:
        soil_status = "偏干"

    if loosened_today:
        loosen_label = "今日已松土"
    elif loosened_recently:
        loosen_label = "近期已松土"
    else:
        loosen_label = "可以松松土"

    wilt_threshold = int(profile["wilt_threshold"])
    soggy_threshold = int(profile["soggy_threshold"])
    if moisture < wilt_threshold:
        flower_status = "有点缺水"
        flower_description = str(profile["dry_description"])
    elif moisture > soggy_threshold:
        flower_status = "水分有点多"
        flower_description = "根边水汽偏重，先让土壤透透气"
    elif str(weather_state.get("key") or "") in {"rain", "heavy_rain"}:
        flower_status = "正在听雨"
        flower_description = "雨水落过花叶，今天不用再浇水"
    elif loosened_today:
        flower_status = "舒展开了"
        flower_description = "新松过的土很透气，根系正慢慢舒展开"
    else:
        flower_status = "长势很好"
        flower_description = str(profile["healthy_description"])

    return {
        "plant_key": profile["key"],
        "plant_name": profile["name"],
        "plant_habit": profile["habit"],
        "season": season,
        "watered_today": watered_today,
        "watering_label": watering_label,
        "last_watered_at": str(garden.get("last_watered_at") or ""),
        "last_watered_by": str(garden.get("last_watered_by") or ""),
        "loosened_today": loosened_today,
        "loosened_recently": loosened_recently,
        "loosen_label": loosen_label,
        "last_loosened_at": str(garden.get("last_loosened_at") or ""),
        "last_loosened_by": str(garden.get("last_loosened_by") or ""),
        "soil_moisture": moisture,
        "soil_status": soil_status,
        "flower_status": flower_status,
        "flower_description": flower_description,
        "needs_watering": moisture < wilt_threshold and not rained_today,
        "needs_loosen": not loosened_recently,
        "updated_at": current.isoformat(timespec="seconds"),
    }
