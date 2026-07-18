from __future__ import annotations

import json
import math
import re
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from mcp import ClientSession

from services.amap_mcp_client import call_tool_with_session, run_in_session
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, today_beijing

logger = get_logger(__name__)

TOOL_TRIP_PREPARE_FACTS_NAME = "trip_prepare_facts"
TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME = "trip_get_transport_detail"
TOOL_TRIP_GET_FOOD_DETAIL_NAME = "trip_get_food_detail"
TOOL_TRIP_UPDATE_PLAN_STATE_NAME = "trip_update_plan_state"
TOOL_TRIP_FINALIZE_PLAN_NAME = "trip_finalize_plan"
SYSTEM_CARD_PREFIX = "<<<SUMITALK_CARD "
SYSTEM_CARD_SUFFIX = ">>>"


_TRIP_BASE_PROPERTIES = {
    "destinations": {
        "type": "array",
        "items": {"type": "string"},
        "description": "目的地列表，例如 [\"上海迪士尼\", \"武康路\"]。至少一个。",
    },
    "origin": {"type": "string", "description": "可选起点名称/地址；不传则尝试用最近定位。"},
    "origin_lnglat": {"type": "string", "description": "可选起点坐标，格式 lng,lat，优先级高于 origin。"},
    "city": {"type": "string", "description": "可选城市，用于缩小地点搜索范围，例如 上海。"},
    "prefer": {"type": "string", "description": "可选：auto / transit / taxi，默认 auto。"},
    "walk": {"type": "string", "description": "步行接受度：low / medium / high，默认 medium。"},
    "food": {"type": "string", "description": "想吃的东西或口味偏好，可为空。"},
    "budget": {"type": "string", "description": "预算偏好，可为空。"},
    "travel_time": {"type": "string", "description": "计划出行时间，可为空。"},
    "optimize_order": {
        "type": "boolean",
        "description": "是否给出基于距离的候选顺序，默认 true。最终顺序仍由渡判断。",
    },
    "prefetch": {"type": "boolean", "description": "是否启动后台交通/吃喝预取，默认 true。"},
}


TOOL_TRIP_PREPARE_FACTS = {
    "type": "function",
    "function": {
        "name": TOOL_TRIP_PREPARE_FACTS_NAME,
        "description": (
            "出行规划首轮事实准备工具。只负责查准地点、基础事实和候选摘要，创建 plan_id，"
            "并在后台预取交通/吃喝细节；最终怎么排、赶不赶、要不要调整由渡判断。"
        ),
        "parameters": {
            "type": "object",
            "properties": _TRIP_BASE_PROPERTIES,
            "required": ["destinations"],
        },
    },
}


TOOL_TRIP_GET_TRANSPORT_DETAIL = {
    "type": "function",
    "function": {
        "name": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME,
        "description": (
            "读取或补查某个 plan_id 下单段交通详情。用户追问某段怎么坐、是否打车、少走路时使用，"
            "不要重新生成整天攻略。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "trip_prepare_facts 返回的 plan_id。"},
                "leg_id": {"type": "string", "description": "可选路段 id，例如 leg_1。"},
                "from_place_id": {"type": "string", "description": "可选起点 place_id，例如 origin 或 p_1。"},
                "to_place_id": {"type": "string", "description": "可选终点 place_id，例如 p_2。"},
                "prefer": {"type": "string", "description": "可选：auto / transit / taxi。"},
                "refresh": {"type": "boolean", "description": "是否强制刷新缓存，默认 false。"},
            },
            "required": ["plan_id"],
        },
    },
}


TOOL_TRIP_GET_FOOD_DETAIL = {
    "type": "function",
    "function": {
        "name": TOOL_TRIP_GET_FOOD_DETAIL_NAME,
        "description": (
            "读取或补查某个 plan_id 下某地点附近吃喝候选。用户追问吃什么、附近有什么时使用，"
            "口味如果只是推断，需要在回复里轻确认。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "trip_prepare_facts 返回的 plan_id。"},
                "place_id": {"type": "string", "description": "地点 id，例如 p_1；不传则优先用当前/第一个地点。"},
                "keywords": {"type": "string", "description": "想吃的关键词，例如 甜品/火锅/咖啡。"},
                "budget": {"type": "string", "description": "预算偏好，可为空。"},
                "radius": {"type": "integer", "description": "搜索半径米，默认 1200。"},
                "refresh": {"type": "boolean", "description": "是否强制刷新缓存，默认 false。"},
            },
            "required": ["plan_id"],
        },
    },
}


TOOL_TRIP_UPDATE_PLAN_STATE = {
    "type": "function",
    "function": {
        "name": TOOL_TRIP_UPDATE_PLAN_STATE_NAME,
        "description": (
            "写回出行计划状态，不查地图。用于保存用户明确偏好、已确认状态、渡的推断，"
            "避免多轮对话里丢失上下文。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "trip_prepare_facts 返回的 plan_id。"},
                "user_overrides": {"type": "array", "items": {"type": "object"}, "description": "用户明确选择，优先级最高。"},
                "confirmed_state": {"type": "array", "items": {"type": "object"}, "description": "用户确认过的状态。"},
                "assistant_assumptions": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "渡的推断，必须带 confidence；>=0.85 可直接用，0.5-0.85 轻确认，<0.5 当 unknown。",
                },
            },
            "required": ["plan_id"],
        },
    },
}


TOOL_TRIP_FINALIZE_PLAN = {
    "type": "function",
    "function": {
        "name": TOOL_TRIP_FINALIZE_PLAN_NAME,
        "description": (
            "旅行结束、取消或过期时收尾 plan_id：停止活跃使用，清掉临时 facts/state，保留轻量归档和记忆候选。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "trip_prepare_facts 返回的 plan_id。"},
                "status": {"type": "string", "description": "completed / expired / cancelled，默认 completed。"},
                "summary": {"type": "string", "description": "旅行结果轻量摘要，可为空。"},
                "visited_place_ids": {"type": "array", "items": {"type": "string"}, "description": "实际去了哪些 place_id。"},
                "skipped_place_ids": {"type": "array", "items": {"type": "string"}, "description": "最后没去哪些 place_id。"},
                "useful_conclusions": {"type": "array", "items": {"type": "string"}, "description": "有复用价值的结论。"},
                "memory_candidates": {"type": "array", "items": {"type": "object"}, "description": "可能进入动态层的长期偏好候选。"},
            },
            "required": ["plan_id"],
        },
    },
}

TRIP_LAYERED_TOOLS = [
    TOOL_TRIP_PREPARE_FACTS,
    TOOL_TRIP_GET_TRANSPORT_DETAIL,
    TOOL_TRIP_GET_FOOD_DETAIL,
    TOOL_TRIP_UPDATE_PLAN_STATE,
    TOOL_TRIP_FINALIZE_PLAN,
]

TRIP_LAYERED_TOOL_NAMES = frozenset(
    {
        TOOL_TRIP_PREPARE_FACTS_NAME,
        TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME,
        TOOL_TRIP_GET_FOOD_DETAIL_NAME,
        TOOL_TRIP_UPDATE_PLAN_STATE_NAME,
        TOOL_TRIP_FINALIZE_PLAN_NAME,
    }
)

def execute_trip_prepare_facts(arguments: dict) -> str:
    try:
        result = run_in_session(
            lambda session: _prepare_facts_async(session, arguments if isinstance(arguments, dict) else {}),
            timeout_seconds=45,
        )
        card = _build_trip_prepare_card(result)
        if card:
            result = {**result, "sumitalk_card": card}
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning("trip_prepare_facts failed error=%s", e)
        return json.dumps({"ok": False, "error": str(e), "source": TOOL_TRIP_PREPARE_FACTS_NAME}, ensure_ascii=False)


def execute_trip_get_transport_detail(arguments: dict) -> str:
    try:
        result = run_in_session(
            lambda session: _get_transport_detail_async(session, arguments if isinstance(arguments, dict) else {}),
            timeout_seconds=60,
        )
        card = _build_transport_detail_card(result)
        if card:
            result = {**result, "sumitalk_card": card}
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning("trip_get_transport_detail failed error=%s", e)
        return json.dumps({"ok": False, "error": str(e), "source": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME}, ensure_ascii=False)


def execute_trip_get_food_detail(arguments: dict) -> str:
    try:
        result = run_in_session(
            lambda session: _get_food_detail_async(session, arguments if isinstance(arguments, dict) else {}),
            timeout_seconds=45,
        )
        card = _build_food_detail_card(result)
        if card:
            result = {**result, "sumitalk_card": card}
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning("trip_get_food_detail failed error=%s", e)
        return json.dumps({"ok": False, "error": str(e), "source": TOOL_TRIP_GET_FOOD_DETAIL_NAME}, ensure_ascii=False)


def execute_trip_update_plan_state(arguments: dict) -> str:
    return json.dumps(_update_plan_state(arguments if isinstance(arguments, dict) else {}), ensure_ascii=False)


def execute_trip_finalize_plan(arguments: dict) -> str:
    return json.dumps(_finalize_plan(arguments if isinstance(arguments, dict) else {}), ensure_ascii=False)


async def _mcp(session: ClientSession, name: str, args: dict) -> dict:
    try:
        return await call_tool_with_session(session, name, args)
    except Exception as e:
        logger.warning("amap trip planner mcp call failed tool=%s error=%s", name, e)
        return {"ok": False, "tool": name, "arguments": args, "error": str(e), "source": "amap_mcp"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def _json_content(result: dict) -> Any:
    if not isinstance(result, dict):
        return None
    structured = result.get("structured_content")
    if structured is not None:
        return structured
    content = _text(result.get("content"))
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        return content


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _bool_arg(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = _text(value).lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _now_iso() -> str:
    return now_beijing_iso()


def _field(data: Any, stale_after_minutes: int, source: str, fetched_at: str | None = None, **extra: Any) -> dict:
    out = {
        "data": data,
        "fetched_at": fetched_at or _now_iso(),
        "stale_after_minutes": stale_after_minutes,
        "source": source,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _empty_field(stale_after_minutes: int, source: str, data: Any = None, **extra: Any) -> dict:
    out = {
        "data": [] if data is None else data,
        "fetched_at": "",
        "stale_after_minutes": stale_after_minutes,
        "source": source,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _new_plan_id() -> str:
    return f"trip_{today_beijing().replace('-', '')}_{uuid4().hex[:8]}"


def _expires_at_for_today() -> str:
    now = datetime.now(BEIJING_TZ)
    end = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=BEIJING_TZ)
    return end.isoformat()


def _parse_place_time(value: str) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(BEIJING_TZ) if parsed.tzinfo else parsed.replace(tzinfo=BEIJING_TZ)
    except Exception:
        return None


def _field_is_stale(field: dict, default_minutes: int = 30) -> bool:
    if not isinstance(field, dict):
        return True
    fetched_at = _text(field.get("fetched_at"))
    if not fetched_at:
        return True
    fetched = _parse_place_time(fetched_at)
    if not fetched:
        return True
    stale_after = _safe_int(field.get("stale_after_minutes")) or default_minutes
    return datetime.now(BEIJING_TZ) - fetched > timedelta(minutes=stale_after)


def _plan_id_from_args(args: dict) -> str:
    return _text(args.get("plan_id") or args.get("planId"))


def _normalize_prefer(value: Any) -> str:
    raw = _text(value).lower()
    if raw in {"transit", "bus", "metro", "subway"}:
        return "transit"
    if raw in {"taxi", "drive", "driving"}:
        return "taxi"
    return "auto"


def _normalize_walk(value: Any) -> str:
    raw = _text(value).lower()
    if raw in {"low", "少走路", "少走", "不想走"}:
        return "low"
    if raw in {"high", "多走", "可以多走"}:
        return "high"
    return "medium"


def _quality_empty() -> dict:
    return {"stale_fields": [], "failed_fields": [], "unknown_fields": []}


def _quality_add_failed(quality: dict, field_path: str, reason: str, retryable: bool = True, item_id: str = "", subfield: str = "") -> None:
    if not isinstance(quality, dict):
        return
    item = {
        "field_path": field_path,
        "reason": _text(reason) or "unknown_error",
        "retryable": bool(retryable),
    }
    if item_id:
        item["item_id"] = item_id
    if subfield:
        item["subfield"] = subfield
    quality.setdefault("failed_fields", []).append(item)


def _quality_add_unknown(
    quality: dict,
    field_path: str,
    reason: str,
    queryable: bool = True,
    retryable: bool = True,
    item_id: str = "",
    subfield: str = "",
) -> None:
    if not isinstance(quality, dict):
        return
    item = {
        "field_path": field_path,
        "reason": _text(reason) or "not_queried_yet",
        "queryable": bool(queryable),
        "retryable": bool(retryable),
    }
    if item_id:
        item["item_id"] = item_id
    if subfield:
        item["subfield"] = subfield
    quality.setdefault("unknown_fields", []).append(item)


def _quality_add_stale(
    quality: dict,
    field_path: str,
    age_minutes: int,
    stale_after_minutes: int,
    should_refresh: bool,
    item_id: str = "",
    subfield: str = "",
) -> None:
    if not isinstance(quality, dict):
        return
    item = {
        "field_path": field_path,
        "age_minutes": int(age_minutes),
        "stale_after_minutes": int(stale_after_minutes),
        "should_refresh": bool(should_refresh),
    }
    if item_id:
        item["item_id"] = item_id
    if subfield:
        item["subfield"] = subfield
    quality.setdefault("stale_fields", []).append(item)


def _quality_remove_refs(quality: dict, field_paths: set[str]) -> None:
    if not isinstance(quality, dict) or not field_paths:
        return
    for key in ("stale_fields", "failed_fields", "unknown_fields"):
        values = quality.get(key)
        if not isinstance(values, list):
            continue
        quality[key] = [
            item for item in values
            if not (isinstance(item, dict) and _text(item.get("field_path")) in field_paths)
        ]


def _place_by_id(plan: dict, place_id: str) -> dict:
    pid = _text(place_id)
    facts = plan.get("facts") if isinstance(plan.get("facts"), dict) else {}
    origin_field = facts.get("origin") if isinstance(facts.get("origin"), dict) else {}
    origin = origin_field.get("data") if isinstance(origin_field.get("data"), dict) else {}
    if pid == "origin":
        return origin
    places_field = facts.get("places") if isinstance(facts.get("places"), dict) else {}
    for place in _as_list(places_field.get("data")):
        if isinstance(place, dict) and _text(place.get("place_id")) == pid:
            return place
    return {}


def _route_leg_id(index: int) -> str:
    return f"leg_{index + 1}"


def _route_places_from_plan(plan: dict) -> list[dict]:
    facts = plan.get("facts") if isinstance(plan.get("facts"), dict) else {}
    order_field = facts.get("candidate_order") if isinstance(facts.get("candidate_order"), dict) else {}
    order = _as_list(order_field.get("data"))
    places = []
    for item in order:
        if not isinstance(item, dict):
            continue
        place = _place_by_id(plan, _text(item.get("place_id")))
        if place:
            places.append(place)
    if places:
        return places
    places_field = facts.get("places") if isinstance(facts.get("places"), dict) else {}
    return [x for x in _as_list(places_field.get("data")) if isinstance(x, dict)]


def _save_plan(plan: dict) -> bool:
    meta = plan.setdefault("plan_meta", {})
    meta["updated_at"] = _now_iso()
    return r2_store.save_trip_plan(plan)


def _lnglat(value: Any) -> str:
    raw = _text(value)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)", raw)
    if not m:
        return ""
    lng = _safe_float(m.group(1))
    lat = _safe_float(m.group(2))
    if lng < -180 or lng > 180 or lat < -90 or lat > 90:
        return ""
    return f"{lng:.6f},{lat:.6f}"


def _split_lnglat(value: str) -> tuple[float, float] | None:
    loc = _lnglat(value)
    if not loc:
        return None
    lng, lat = loc.split(",", 1)
    return _safe_float(lng), _safe_float(lat)


def _split_destinations(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[、,，;；\n]+", _text(value)) if _text(value) else []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        s = _text(item)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:6]


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes}分钟"
    h, m = divmod(minutes, 60)
    return f"{h}小时{m}分钟" if m else f"{h}小时"


def _format_distance(meters: int) -> str:
    if meters <= 0:
        return ""
    if meters < 1000:
        return f"{meters}米"
    return f"{meters / 1000:.1f}公里"


def _city_from_regeocode(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    comp = data.get("addressComponent") or data.get("regeocode", {}).get("addressComponent") or {}
    if not isinstance(comp, dict):
        return ""
    city = _text(comp.get("city"))
    province = _text(comp.get("province"))
    return city or province


def _public_place(place: dict) -> dict:
    return {
        "input": _text(place.get("input")),
        "id": _text(place.get("id")),
        "name": _text(place.get("name")),
        "address": _text(place.get("address")),
        "location": _text(place.get("location")),
        "city": _text(place.get("city")),
        "type": _text(place.get("type")),
        "rating": _text(place.get("rating")),
        "open_time": _text(place.get("opentime2") or place.get("open_time")),
        "candidates": place.get("candidates") or [],
    }


async def _resolve_from_location(session: ClientSession, location: str, label: str) -> dict:
    loc = _lnglat(location)
    place = {"input": label, "name": label or "当前位置", "location": loc, "city": "", "address": "", "source": "coordinate"}
    if not loc:
        return place
    res = await _mcp(session, "maps_regeocode", {"location": loc})
    data = _json_content(res)
    if isinstance(data, dict):
        place["city"] = _city_from_regeocode(data)
        address = _text(data.get("formatted_address") or data.get("address") or data.get("formattedAddress"))
        if not address:
            regeocode = data.get("regeocode") if isinstance(data.get("regeocode"), dict) else {}
            address = _text(regeocode.get("formatted_address"))
        if address:
            place["address"] = address
            place["name"] = address
    return place


def _latest_origin_lnglat() -> tuple[str, str]:
    try:
        sense = r2_store.get_sense_latest() or {}
    except Exception:
        return "", ""
    loc = sense.get("location") if isinstance(sense.get("location"), dict) else {}
    lng = loc.get("lng")
    lat = loc.get("lat")
    lnglat = _lnglat(f"{lng},{lat}")
    label = _text(loc.get("address")) or "最近定位"
    return lnglat, label


async def _resolve_place(
    session: ClientSession,
    query: str,
    city: str = "",
    role: str = "destination",
    origin_lnglat: str = "",
    fast: bool = False,
) -> tuple[dict | None, str]:
    coord = _lnglat(origin_lnglat or query)
    if coord:
        place = await _resolve_from_location(session, coord, query or "坐标点")
        place["input"] = query or coord
        return place, ""

    if role == "origin" and not _text(query):
        loc, label = _latest_origin_lnglat()
        if not loc:
            return None, "缺少起点：请给 origin，或让手机先上报定位。"
        place = await _resolve_from_location(session, loc, label)
        place["input"] = "最近定位"
        place["source"] = "latest_location"
        return place, ""

    keyword = _text(query)
    if not keyword:
        return None, "地点为空"

    search = await _mcp(session, "maps_text_search", {"keywords": keyword, "city": city, "citylimit": bool(city)})
    search_data = _json_content(search)
    pois = _as_list((search_data or {}).get("pois") if isinstance(search_data, dict) else [])
    candidates: list[dict] = []
    for poi in pois[:3]:
        if not isinstance(poi, dict):
            continue
        candidates.append(
            {
                "id": _text(poi.get("id")),
                "name": _text(poi.get("name")),
                "address": _text(poi.get("address")),
                "type": _text(poi.get("type") or poi.get("typecode")),
            }
        )
    first = next((x for x in pois if isinstance(x, dict) and _text(x.get("id"))), None)
    first_with_location = next((x for x in pois if isinstance(x, dict) and _lnglat(x.get("location"))), None)
    if fast and first_with_location:
        place = dict(first_with_location)
        place["input"] = keyword
        place["location"] = _lnglat(place.get("location"))
        place["candidates"] = candidates
        return place, ""
    if first:
        detail_res = await _mcp(session, "maps_search_detail", {"id": _text(first.get("id"))})
        detail = _json_content(detail_res)
        if isinstance(detail, dict) and _lnglat(detail.get("location")):
            detail = dict(detail)
            detail["input"] = keyword
            detail["location"] = _lnglat(detail.get("location"))
            detail["candidates"] = candidates
            return detail, ""

    geo = await _mcp(session, "maps_geo", {"address": keyword, "city": city})
    geo_data = _json_content(geo)
    rows = _as_list((geo_data or {}).get("results") or (geo_data or {}).get("geocodes") if isinstance(geo_data, dict) else [])
    first_geo = next((x for x in rows if isinstance(x, dict) and _lnglat(x.get("location"))), None)
    if first_geo:
        place = {
            "input": keyword,
            "id": "",
            "name": _text(first_geo.get("formatted_address") or first_geo.get("address") or keyword),
            "address": _text(first_geo.get("formatted_address") or first_geo.get("address")),
            "location": _lnglat(first_geo.get("location")),
            "city": _text(first_geo.get("city") or first_geo.get("province") or city),
            "type": "",
            "candidates": candidates,
        }
        return place, ""
    return None, "地点解析失败"


def _haversine_m(a: dict, b: dict) -> float:
    ca = _split_lnglat(_text(a.get("location")))
    cb = _split_lnglat(_text(b.get("location")))
    if not ca or not cb:
        return float("inf")
    lng1, lat1 = ca
    lng2, lat2 = cb
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    x = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def _order_places(origin: dict, places: list[dict], optimize: bool) -> list[dict]:
    if not optimize or len(places) <= 1:
        return places
    current = origin
    remaining = list(places)
    ordered: list[dict] = []
    while remaining:
        idx = min(range(len(remaining)), key=lambda i: _haversine_m(current, remaining[i]))
        nxt = remaining.pop(idx)
        ordered.append(nxt)
        current = nxt
    return ordered


def _summarize_transit(data: Any) -> dict:
    route = data.get("route") if isinstance(data, dict) and isinstance(data.get("route"), dict) else data
    if not isinstance(route, dict):
        return {"ok": False, "error": "公交/地铁结果为空"}
    transits = _as_list(route.get("transits"))
    first = next((x for x in transits if isinstance(x, dict)), None)
    if not first:
        return {"ok": False, "error": "没有查到公交/地铁方案", "taxi_cost_yuan": _safe_float(route.get("taxi_cost"))}

    steps: list[str] = []
    ride_count = 0
    for seg in _as_list(first.get("segments")):
        if not isinstance(seg, dict):
            continue
        walking = seg.get("walking") if isinstance(seg.get("walking"), dict) else {}
        walk_m = _safe_int(walking.get("distance"))
        if walk_m:
            steps.append(f"步行{_format_distance(walk_m)}")
        bus = seg.get("bus") if isinstance(seg.get("bus"), dict) else {}
        for line in _as_list(bus.get("buslines")):
            if not isinstance(line, dict):
                continue
            name = _text(line.get("name"))
            dep = line.get("departure_stop") if isinstance(line.get("departure_stop"), dict) else {}
            arr = line.get("arrival_stop") if isinstance(line.get("arrival_stop"), dict) else {}
            via = _safe_int(line.get("via_num"))
            duration = _format_duration(_safe_int(line.get("duration")))
            if name:
                piece = f"{_text(dep.get('name'))} 上车，乘 {name} 到 {_text(arr.get('name'))} 下车"
                extra = "，".join(x for x in [f"{via}站" if via else "", f"约{duration}" if duration else ""] if x)
                if extra:
                    piece += f"（{extra}）"
                steps.append(piece)
                ride_count += 1
    return {
        "ok": True,
        "duration_seconds": _safe_int(first.get("duration")),
        "duration": _format_duration(_safe_int(first.get("duration"))),
        "distance_meters": _safe_int(first.get("distance")),
        "distance": _format_distance(_safe_int(first.get("distance"))),
        "walking_distance_meters": _safe_int(first.get("walking_distance")),
        "walking_distance": _format_distance(_safe_int(first.get("walking_distance"))),
        "cost_yuan": _safe_float(first.get("cost")),
        "transfer_count": max(0, ride_count - 1),
        "taxi_cost_yuan": _safe_float(route.get("taxi_cost")),
        "steps": steps[:10],
    }


def _summarize_driving(data: Any) -> dict:
    route = data.get("route") if isinstance(data, dict) and isinstance(data.get("route"), dict) else data
    if not isinstance(route, dict):
        return {"ok": False, "error": "驾车结果为空"}
    paths = _as_list(route.get("paths"))
    first = next((x for x in paths if isinstance(x, dict)), None)
    if not first:
        return {"ok": False, "error": "没有查到驾车路线"}
    steps = []
    for step in _as_list(first.get("steps"))[:5]:
        if isinstance(step, dict) and _text(step.get("instruction")):
            steps.append(_text(step.get("instruction")))
    return {
        "ok": True,
        "duration_seconds": _safe_int(first.get("duration")),
        "duration": _format_duration(_safe_int(first.get("duration"))),
        "distance_meters": _safe_int(first.get("distance")),
        "distance": _format_distance(_safe_int(first.get("distance"))),
        "tolls_yuan": _safe_float(first.get("tolls")),
        "strategy": _text(first.get("strategy")),
        "steps": steps,
    }


def _recommend(prefer: str, transit: dict, driving: dict) -> dict:
    pref = _text(prefer).lower()
    if pref in {"taxi", "drive", "driving"}:
        return {"mode": "taxi", "reason": "按偏好优先推荐打车。"}
    if pref in {"transit", "bus", "metro", "subway"} and transit.get("ok"):
        return {"mode": "transit", "reason": "按偏好优先推荐地铁/公交。"}
    if not transit.get("ok"):
        if driving.get("ok"):
            return {"mode": "taxi", "reason": "没有查到稳定的公交/地铁方案。"}
        return {"mode": "unknown", "reason": "没有拿到可比较的路线。"}

    transit_sec = _safe_int(transit.get("duration_seconds"))
    driving_sec = _safe_int(driving.get("duration_seconds"))
    walk_m = _safe_int(transit.get("walking_distance_meters"))
    if walk_m >= 1800:
        return {"mode": "taxi", "reason": f"公交/地铁步行约{_format_distance(walk_m)}，比较折腾。"}
    if not driving.get("ok"):
        return {"mode": "transit", "reason": "公交/地铁步行距离还可以。"}
    if transit_sec and driving_sec and driving_sec <= transit_sec * 0.6:
        return {"mode": "taxi", "reason": "打车耗时明显更短。"}
    return {"mode": "transit", "reason": "公交/地铁耗时和步行距离都还可以。"}


def _leg_summary(start: dict, end: dict, transit: dict, driving: dict, rec: dict) -> list[str]:
    lines = [f"{_text(start.get('name')) or '起点'} -> {_text(end.get('name')) or '终点'}"]
    if transit.get("ok"):
        cost = _safe_float(transit.get("cost_yuan"))
        lines.append(
            f"公交/地铁：约{transit.get('duration')}，步行{transit.get('walking_distance') or '0米'}"
            + (f"，费用约{cost:g}元" if cost else "")
        )
    else:
        lines.append(f"公交/地铁：{transit.get('error') or '无结果'}")
    if driving.get("ok"):
        taxi_cost = _safe_float(transit.get("taxi_cost_yuan"))
        lines.append(
            f"打车/驾车：约{driving.get('duration')}，{driving.get('distance')}"
            + (f"，高德预估打车约{taxi_cost:g}元" if taxi_cost else "")
        )
    elif driving.get("error"):
        lines.append(f"打车/驾车：{driving.get('error') or '无结果'}")
    elif _safe_float(transit.get("taxi_cost_yuan")):
        lines.append(f"打车参考：高德预估约{_safe_float(transit.get('taxi_cost_yuan')):g}元")
    lines.append(f"建议：{rec.get('mode')}，{rec.get('reason')}")
    return lines


def _public_place_with_id(place: dict, place_id: str) -> dict:
    out = _public_place(place)
    out["place_id"] = place_id
    open_hours = _text(place.get("open_hours") or place.get("opentime2") or place.get("open_time"))
    if open_hours:
        out["open_hours"] = {
            "data": open_hours,
            "fetched_at": _now_iso(),
            "stale_after_minutes": 1440,
            "source": "maps_search_detail" if _text(place.get("id")) else "maps_text_search",
        }
    return out


def _summarize_weather(data: Any) -> dict:
    if not isinstance(data, dict):
        return {}
    lives = _as_list(data.get("lives") or data.get("forecasts"))
    first = next((x for x in lives if isinstance(x, dict)), None)
    if not first:
        return {}
    return {
        "province": _text(first.get("province")),
        "city": _text(first.get("city")),
        "weather": _text(first.get("weather") or first.get("dayweather")),
        "temperature": _text(first.get("temperature") or first.get("daytemp")),
        "winddirection": _text(first.get("winddirection") or first.get("daywind")),
        "windpower": _text(first.get("windpower") or first.get("daypower")),
        "reporttime": _text(first.get("reporttime")),
    }


def _summarize_food_candidates(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    pois = _as_list(data.get("pois"))
    out = []
    for poi in pois[:8]:
        if not isinstance(poi, dict):
            continue
        biz_ext = poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {}
        out.append(
            {
                "id": _text(poi.get("id")),
                "name": _text(poi.get("name")),
                "address": _text(poi.get("address")),
                "type": _text(poi.get("type") or poi.get("typecode")),
                "location": _lnglat(poi.get("location")),
                "distance_meters": _safe_int(poi.get("distance")),
                "rating": _text(biz_ext.get("rating") or poi.get("rating")),
                "cost": _text(biz_ext.get("cost") or poi.get("cost")),
            }
        )
    return [x for x in out if x.get("name")]


def _build_candidate_order(origin: dict, places: list[dict], optimize_order: bool) -> list[dict]:
    ordered = _order_places(origin, places, optimize=optimize_order)
    out = []
    for idx, place in enumerate(ordered):
        out.append(
            {
                "place_id": _text(place.get("place_id")) or f"p_{idx + 1}",
                "name": _text(place.get("name") or place.get("input")),
                "basis": "distance_greedy" if optimize_order and len(places) > 1 else "user_input_order",
            }
        )
    return out


def _plan_public_payload(plan: dict) -> dict:
    meta = plan.get("plan_meta") if isinstance(plan.get("plan_meta"), dict) else {}
    facts = plan.get("facts") if isinstance(plan.get("facts"), dict) else {}
    return {
        "plan_meta": meta,
        "facts": facts,
        "plan_state": plan.get("plan_state") if isinstance(plan.get("plan_state"), dict) else {},
        "quality": plan.get("quality") if isinstance(plan.get("quality"), dict) else _quality_empty(),
    }


async def _gather_limited(items: list[Any], limit: int, worker) -> list[Any]:
    semaphore = asyncio.Semaphore(max(1, int(limit or 1)))

    async def _run(item: Any) -> Any:
        async with semaphore:
            return await worker(item)

    return await asyncio.gather(*[_run(item) for item in items], return_exceptions=True)


def _start_background_prefetch(plan_id: str) -> None:
    pid = _text(plan_id)
    if not pid:
        return

    def _runner() -> None:
        try:
            run_in_session(lambda session: _background_prefetch_async(session, pid), timeout_seconds=120)
        except Exception as e:
            logger.warning("trip background_prefetch failed plan_id=%s error=%s", pid, e)
            plan = r2_store.get_trip_plan(pid)
            if isinstance(plan, dict) and plan:
                quality = plan.setdefault("quality", _quality_empty())
                _quality_add_failed(quality, "facts.route_matrix", str(e), retryable=True)
                _quality_add_failed(quality, "facts.food_candidates", str(e), retryable=True)
                _save_plan(plan)

    threading.Thread(target=_runner, name=f"trip-prefetch-{pid}", daemon=True).start()


async def _fetch_weather(session: ClientSession, city: str, quality: dict) -> dict:
    if not _text(city):
        _quality_add_unknown(quality, "facts.weather", "not_queried_yet", queryable=True)
        return _empty_field(60, "amap_weather", {})
    res = await _mcp(session, "maps_weather", {"city": _text(city)})
    data = _summarize_weather(_json_content(res))
    if data:
        return _field(data, 60, "amap_weather")
    _quality_add_failed(quality, "facts.weather", _text(res.get("error")) or "weather_empty", retryable=True)
    return _empty_field(60, "amap_weather", {})


async def _fetch_leg_routes(session: ClientSession, start: dict, end: dict, prefer: str, route_city: str, compare_modes: bool = True) -> dict:
    pref = _normalize_prefer(prefer)
    need_transit = compare_modes or pref != "taxi"
    need_driving = compare_modes or pref == "taxi"
    transit: dict = {}
    driving: dict = {}
    if need_transit:
        transit_res = await _mcp(
            session,
            "maps_direction_transit_integrated",
            {
                "origin": _text(start.get("location")),
                "destination": _text(end.get("location")),
                "city": _text(start.get("city") or route_city),
                "cityd": _text(end.get("city") or route_city),
            },
        )
        transit = _summarize_transit(_json_content(transit_res))
    if need_driving:
        driving_res = await _mcp(
            session,
            "maps_direction_driving",
            {"origin": _text(start.get("location")), "destination": _text(end.get("location"))},
        )
        driving = _summarize_driving(_json_content(driving_res))
    rec = _recommend(pref, transit, driving)
    return {
        "from_place_id": _text(start.get("place_id")) or "origin",
        "to_place_id": _text(end.get("place_id")),
        "from": _public_place(start),
        "to": _public_place(end),
        "transit": transit,
        "driving": driving,
        "recommendation": rec,
        "summary": _leg_summary(start, end, transit, driving, rec),
        "fetched_at": _now_iso(),
        "stale_after_minutes": 10,
        "source": "amap_route",
    }


async def _fetch_food_for_place(
    session: ClientSession,
    place: dict,
    keywords: str = "",
    radius: int = 1200,
) -> dict:
    loc = _text(place.get("location"))
    keyword = _text(keywords) or "美食"
    res = await _mcp(
        session,
        "maps_around_search",
        {
            "location": loc,
            "keywords": keyword,
            "radius": str(max(300, min(5000, _safe_int(radius) or 1200))),
        },
    )
    return {
        "place_id": _text(place.get("place_id")),
        "place_name": _text(place.get("name") or place.get("input")),
        "keywords": keyword,
        "items": _summarize_food_candidates(_json_content(res)),
        "fetched_at": _now_iso(),
        "stale_after_minutes": 60,
        "source": "amap_around_search",
    }


def _estimated_cost_from_legs(legs: list[dict]) -> dict:
    transit_total = 0.0
    taxi_total = 0.0
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        transit = leg.get("transit") if isinstance(leg.get("transit"), dict) else {}
        transit_total += _safe_float(transit.get("cost_yuan"))
        taxi_total += _safe_float(transit.get("taxi_cost_yuan"))
    out = {}
    if transit_total:
        out["transit_total_yuan"] = round(transit_total, 1)
    if taxi_total:
        out["taxi_total_yuan"] = round(taxi_total, 1)
    return out


async def _background_prefetch_async(session: ClientSession, plan_id: str) -> dict:
    plan = r2_store.get_trip_plan(plan_id)
    if not isinstance(plan, dict) or not plan:
        return {"ok": False, "error": "plan not found"}
    meta = plan.get("plan_meta") if isinstance(plan.get("plan_meta"), dict) else {}
    if _text(meta.get("status")) not in {"", "active"}:
        return {"ok": False, "error": "plan not active"}

    facts = plan.setdefault("facts", {})
    state = plan.setdefault("plan_state", {})
    quality = plan.setdefault("quality", _quality_empty())
    origin = _place_by_id(plan, "origin")
    places = _route_places_from_plan(plan)
    route_city = _text(meta.get("city") or origin.get("city"))
    prefer = _text((state.get("preferences") or {}).get("prefer")) or "auto"
    food_keyword = _text((state.get("preferences") or {}).get("food")) or "美食"

    legs: list[dict] = []
    route_pairs: list[tuple[int, dict, dict]] = []
    if origin and places:
        current = origin
        for idx, place in enumerate(places):
            route_pairs.append((idx, current, place))
            current = place
    if route_pairs:
        async def _route_worker(item: tuple[int, dict, dict]) -> dict:
            idx, start, end = item
            leg = await _fetch_leg_routes(session, start, end, prefer, route_city, compare_modes=True)
            leg["leg_id"] = _route_leg_id(idx)
            return leg

        route_results = await _gather_limited(route_pairs, 3, _route_worker)
        for item, result in zip(route_pairs, route_results):
            idx = item[0]
            if isinstance(result, Exception):
                _quality_add_failed(quality, "facts.route_matrix", str(result), retryable=True, item_id=_route_leg_id(idx))
                continue
            if isinstance(result, dict):
                legs.append(result)
        legs.sort(key=lambda x: _safe_int(_text(x.get("leg_id")).replace("leg_", "")))
    facts["route_matrix"] = _field(legs, 10, "amap_route") if legs else _empty_field(10, "amap_route")
    if legs:
        _quality_remove_refs(quality, {"facts.route_matrix", "facts.estimated_cost"})

    foods: list[dict] = []
    food_places = places[:4]
    if food_places:
        async def _food_worker(place: dict) -> dict:
            return await _fetch_food_for_place(session, place, food_keyword, radius=1200)

        food_results = await _gather_limited(food_places, 3, _food_worker)
        for place, result in zip(food_places, food_results):
            if isinstance(result, Exception):
                _quality_add_failed(quality, "facts.food_candidates", str(result), retryable=True, item_id=_text(place.get("place_id")))
                continue
            if isinstance(result, dict):
                foods.append(result)
    facts["food_candidates"] = _field(foods, 60, "amap_around_search") if foods else _empty_field(60, "amap_around_search")
    if foods:
        _quality_remove_refs(quality, {"facts.food_candidates", "facts.estimated_cost"})

    facts["estimated_cost"] = _field(
        _estimated_cost_from_legs(legs),
        10,
        "computed_from_routes_and_poi",
        depends_on=["facts.route_matrix", "facts.food_candidates"],
    )
    has_failures = any(
        isinstance(item, dict) and _text(item.get("field_path")) in {"facts.route_matrix", "facts.food_candidates"}
        for item in _as_list(quality.get("failed_fields"))
    )
    meta["prefetch_status"] = "partial" if has_failures and (legs or foods) else "failed" if has_failures else "completed"
    _save_plan(plan)
    return {"ok": True, "plan_id": plan_id, "route_legs": len(legs), "food_places": len(foods)}


def _build_trip_prepare_card(result: dict) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return ""
    facts = result.get("facts") if isinstance(result.get("facts"), dict) else {}
    origin_field = facts.get("origin") if isinstance(facts.get("origin"), dict) else {}
    origin = origin_field.get("data") if isinstance(origin_field.get("data"), dict) else {}
    places_field = facts.get("places") if isinstance(facts.get("places"), dict) else {}
    names = [
        _text(item.get("name") or item.get("input"))
        for item in _as_list(places_field.get("data"))
        if isinstance(item, dict) and _text(item.get("name") or item.get("input"))
    ]
    card = {
        "type": "travel_plan_result",
        "title": "地点先看好了",
        "origin": _text(origin.get("name") or origin.get("input") or "起点"),
        "destinations": names[:8],
        "optimized": False,
        "legs": [],
        "personalMapUrl": "",
        "note": "地点和基础事实已准备，交通和吃喝会在后台继续查；这不是最终游玩顺序。",
    }
    return f"{SYSTEM_CARD_PREFIX}{json.dumps(card, ensure_ascii=False, separators=(',', ':'))}{SYSTEM_CARD_SUFFIX}"


def _route_card_summary(route: dict) -> dict:
    if not isinstance(route, dict):
        return {}
    return {
        "ok": bool(route.get("ok")),
        "duration": _text(route.get("duration")),
        "distance": _text(route.get("distance")),
        "walking": _text(route.get("walking_distance") or route.get("walking")),
        "costYuan": _safe_float(route.get("cost_yuan") or route.get("costYuan")),
        "taxiCostYuan": _safe_float(route.get("taxi_cost_yuan") or route.get("taxiCostYuan")),
        "steps": [_text(x) for x in _as_list(route.get("steps")) if _text(x)][:6],
        "error": _text(route.get("error")),
    }


def _build_transport_detail_card(result: dict) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return ""
    leg = result.get("leg") if isinstance(result.get("leg"), dict) else {}
    if not leg:
        return ""
    rec = leg.get("recommendation") if isinstance(leg.get("recommendation"), dict) else {}
    from_place = leg.get("from") if isinstance(leg.get("from"), dict) else {}
    to_place = leg.get("to") if isinstance(leg.get("to"), dict) else {}
    card = {
        "type": "travel_transport_detail",
        "title": "这段怎么走",
        "planId": _text(result.get("plan_id")),
        "legId": _text(leg.get("leg_id")),
        "from": _text(from_place.get("name") or from_place.get("input") or "起点"),
        "to": _text(to_place.get("name") or to_place.get("input") or "终点"),
        "mode": _text(rec.get("mode")),
        "reason": _text(rec.get("reason")),
        "transit": _route_card_summary(leg.get("transit") if isinstance(leg.get("transit"), dict) else {}),
        "driving": _route_card_summary(leg.get("driving") if isinstance(leg.get("driving"), dict) else {}),
        "cacheHit": bool(result.get("cache_hit")),
        "note": "只展示这一段路线，整天安排继续按同一个 plan_id 调整。",
    }
    return f"{SYSTEM_CARD_PREFIX}{json.dumps(card, ensure_ascii=False, separators=(',', ':'))}{SYSTEM_CARD_SUFFIX}"


def _build_food_detail_card(result: dict) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return ""
    food = result.get("food") if isinstance(result.get("food"), dict) else {}
    if not food:
        return ""
    items = []
    for item in _as_list(food.get("items"))[:8]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "name": _text(item.get("name")),
                "type": _text(item.get("type")),
                "address": _text(item.get("address")),
                "distanceMeters": _safe_int(item.get("distance_meters") or item.get("distanceMeters")),
                "rating": _text(item.get("rating")),
                "cost": _text(item.get("cost")),
            }
        )
    card = {
        "type": "travel_food_detail",
        "title": "附近吃这些",
        "planId": _text(result.get("plan_id")),
        "placeId": _text(food.get("place_id")),
        "placeName": _text(food.get("place_name")),
        "keywords": _text(food.get("keywords")),
        "items": [x for x in items if x.get("name")],
        "cacheHit": bool(result.get("cache_hit")),
        "note": "店铺候选来自高德周边搜索，具体营业和排队以出发时为准。",
    }
    return f"{SYSTEM_CARD_PREFIX}{json.dumps(card, ensure_ascii=False, separators=(',', ':'))}{SYSTEM_CARD_SUFFIX}"


async def _prepare_facts_async(session: ClientSession, args: dict) -> dict:
    destinations_raw = _split_destinations(args.get("destinations") or args.get("destination") or args.get("places"))
    if not destinations_raw:
        return {"ok": False, "error": "destinations 不能为空", "source": TOOL_TRIP_PREPARE_FACTS_NAME}

    city = _text(args.get("city") or args.get("region"))
    origin_raw = _text(args.get("origin"))
    origin_lnglat = _text(args.get("origin_lnglat") or args.get("originLocation") or args.get("origin_location"))
    prefer = _normalize_prefer(args.get("prefer") or "auto")
    walk = _normalize_walk(args.get("walk") or "medium")
    food = _text(args.get("food"))
    budget = _text(args.get("budget"))
    travel_time = _text(args.get("travel_time") or args.get("travelTime") or args.get("time"))
    optimize_order = _bool_arg(args.get("optimize_order", True), True)
    prefetch = _bool_arg(args.get("prefetch", True), True)
    quality = _quality_empty()

    origin, origin_err = await _resolve_place(
        session,
        origin_raw,
        city=city,
        role="origin",
        origin_lnglat=origin_lnglat,
        fast=True,
    )
    if not origin:
        return {"ok": False, "error": origin_err or "起点解析失败", "source": TOOL_TRIP_PREPARE_FACTS_NAME}
    origin["place_id"] = "origin"

    route_city = city or _text(origin.get("city"))
    places: list[dict] = []
    place_errors: list[dict] = []
    for idx, item in enumerate(destinations_raw):
        place, err = await _resolve_place(session, item, city=route_city, role="destination", fast=True)
        if place:
            place["place_id"] = f"p_{idx + 1}"
            places.append(place)
        else:
            place_errors.append({"input": item, "error": err})
            _quality_add_failed(quality, "facts.places", err or "place_resolve_failed", retryable=True)
    if not places:
        return {
            "ok": False,
            "error": "目的地都没解析成功",
            "place_errors": place_errors,
            "source": TOOL_TRIP_PREPARE_FACTS_NAME,
        }

    candidate_order = _build_candidate_order(origin, places, optimize_order)
    weather_field = await _fetch_weather(session, route_city, quality)
    plan_id = _text(args.get("plan_id") or args.get("planId")) or _new_plan_id()
    now = _now_iso()
    plan = {
        "plan_meta": {
            "plan_id": plan_id,
            "date": today_beijing(),
            "created_at": now,
            "updated_at": now,
            "expires_at": _expires_at_for_today(),
            "status": "active",
            "city": route_city,
            "prefetch_status": "queued" if prefetch else "disabled",
        },
        "facts": {
            "origin": _field(_public_place_with_id(origin, "origin"), 30, _text(origin.get("source")) or "amap_place"),
            "places": _field([_public_place_with_id(p, _text(p.get("place_id"))) for p in places], 1440, "amap_place"),
            "candidate_order": _field(candidate_order, 1440, "computed_distance_candidate"),
            "weather": weather_field,
            "route_matrix": _empty_field(10, "amap_route"),
            "food_candidates": _empty_field(60, "amap_around_search"),
            "estimated_cost": _empty_field(10, "computed_from_routes_and_poi", data={}, depends_on=["facts.route_matrix", "facts.food_candidates"]),
        },
        "plan_state": {
            "preferences": {
                "prefer": prefer,
                "walk": walk,
                "food": food,
                "budget": budget,
                "travel_time": travel_time,
            },
            "user_overrides": [],
            "confirmed_state": [],
            "assistant_assumptions": [],
            "priority_rule": "user_overrides > confirmed_state > hard_facts > assistant_assumptions > defaults",
            "confidence_rule": {
                "direct_use_min": 0.85,
                "light_confirm_min": 0.5,
                "below_0_5": "unknown_or_ask_user",
            },
        },
        "quality": quality,
    }
    _quality_add_unknown(plan["quality"], "facts.route_matrix", "not_queried_yet", queryable=True, retryable=True)
    _quality_add_unknown(plan["quality"], "facts.food_candidates", "not_queried_yet", queryable=True, retryable=True)
    if place_errors:
        plan["quality"]["place_errors"] = place_errors

    saved = _save_plan(plan)
    if prefetch and saved:
        _start_background_prefetch(plan_id)

    payload = _plan_public_payload(plan)
    return {
        "ok": True,
        "source": TOOL_TRIP_PREPARE_FACTS_NAME,
        "plan_id": plan_id,
        "saved": bool(saved),
        "candidate_order_optimized": bool(optimize_order and len(places) > 1),
        "place_errors": place_errors,
        "prefetch_started": bool(prefetch and saved),
        "instruction_for_du": (
            "请基于 facts 和 plan_state 给第一版简短安排。候选顺序只是算法参考，最终怎么排由你判断；"
            "不要逐站展开，后续交通/吃喝细节可用 plan_id 继续查。"
        ),
        **payload,
    }


async def _get_transport_detail_async(session: ClientSession, args: dict) -> dict:
    plan_id = _plan_id_from_args(args)
    if not plan_id:
        return {"ok": False, "error": "缺少 plan_id", "source": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME}
    plan = r2_store.get_trip_plan(plan_id)
    if not plan:
        return {"ok": False, "error": "plan_id 不存在或缓存不可用", "plan_id": plan_id, "source": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME}
    facts = plan.setdefault("facts", {})
    route_field = facts.get("route_matrix") if isinstance(facts.get("route_matrix"), dict) else {}
    legs = [x for x in _as_list(route_field.get("data")) if isinstance(x, dict)]
    leg_id = _text(args.get("leg_id") or args.get("legId"))
    from_pid = _text(args.get("from_place_id") or args.get("fromPlaceId"))
    to_pid = _text(args.get("to_place_id") or args.get("toPlaceId"))
    refresh = _bool_arg(args.get("refresh"), False) or _field_is_stale(route_field, 10)

    selected = None
    for leg in legs:
        if leg_id and _text(leg.get("leg_id")) == leg_id:
            selected = leg
            break
        if from_pid and to_pid and _text(leg.get("from_place_id")) == from_pid and _text(leg.get("to_place_id")) == to_pid:
            selected = leg
            break
    if selected and not refresh:
        return {
            "ok": True,
            "source": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME,
            "plan_id": plan_id,
            "cache_hit": True,
            "leg": selected,
            "quality": plan.get("quality") if isinstance(plan.get("quality"), dict) else _quality_empty(),
        }

    places = _route_places_from_plan(plan)
    origin = _place_by_id(plan, "origin")
    if leg_id:
        try:
            idx = max(0, int(leg_id.replace("leg_", "")) - 1)
        except Exception:
            idx = 0
    elif to_pid:
        idx = next((i for i, p in enumerate(places) if _text(p.get("place_id")) == to_pid), 0)
    else:
        idx = 0
    if idx >= len(places):
        return {"ok": False, "error": "没有找到这段路线", "plan_id": plan_id, "source": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME}
    start = origin if idx == 0 else places[idx - 1]
    end = places[idx]
    route_city = _text((plan.get("plan_meta") or {}).get("city") or origin.get("city"))
    prefer = _normalize_prefer(args.get("prefer") or ((plan.get("plan_state") or {}).get("preferences") or {}).get("prefer"))
    leg = await _fetch_leg_routes(session, start, end, prefer, route_city, compare_modes=True)
    leg["leg_id"] = _route_leg_id(idx)

    replaced = False
    for i, old in enumerate(legs):
        if _text(old.get("leg_id")) == leg["leg_id"]:
            legs[i] = leg
            replaced = True
            break
    if not replaced:
        legs.append(leg)
        legs.sort(key=lambda x: _safe_int(_text(x.get("leg_id")).replace("leg_", "")))
    facts["route_matrix"] = _field(legs, 10, "amap_route")
    _quality_remove_refs(plan.setdefault("quality", _quality_empty()), {"facts.route_matrix", "facts.estimated_cost"})
    facts["estimated_cost"] = _field(
        _estimated_cost_from_legs(legs),
        10,
        "computed_from_routes_and_poi",
        depends_on=["facts.route_matrix", "facts.food_candidates"],
    )
    _save_plan(plan)
    return {
        "ok": True,
        "source": TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME,
        "plan_id": plan_id,
        "cache_hit": False,
        "leg": leg,
        "quality": plan.get("quality") if isinstance(plan.get("quality"), dict) else _quality_empty(),
    }


async def _get_food_detail_async(session: ClientSession, args: dict) -> dict:
    plan_id = _plan_id_from_args(args)
    if not plan_id:
        return {"ok": False, "error": "缺少 plan_id", "source": TOOL_TRIP_GET_FOOD_DETAIL_NAME}
    plan = r2_store.get_trip_plan(plan_id)
    if not plan:
        return {"ok": False, "error": "plan_id 不存在或缓存不可用", "plan_id": plan_id, "source": TOOL_TRIP_GET_FOOD_DETAIL_NAME}
    facts = plan.setdefault("facts", {})
    food_field = facts.get("food_candidates") if isinstance(facts.get("food_candidates"), dict) else {}
    foods = [x for x in _as_list(food_field.get("data")) if isinstance(x, dict)]
    place_id = _text(args.get("place_id") or args.get("placeId"))
    if not place_id:
        places = _route_places_from_plan(plan)
        place_id = _text((places[0] if places else {}).get("place_id"))
    keywords = _text(args.get("keywords") or args.get("food") or ((plan.get("plan_state") or {}).get("preferences") or {}).get("food") or "美食")
    radius = _safe_int(args.get("radius")) or 1200
    refresh = _bool_arg(args.get("refresh"), False) or _field_is_stale(food_field, 60)
    selected = next((x for x in foods if _text(x.get("place_id")) == place_id and _text(x.get("keywords")) == keywords), None)
    if selected and not refresh:
        return {
            "ok": True,
            "source": TOOL_TRIP_GET_FOOD_DETAIL_NAME,
            "plan_id": plan_id,
            "cache_hit": True,
            "food": selected,
            "quality": plan.get("quality") if isinstance(plan.get("quality"), dict) else _quality_empty(),
        }
    place = _place_by_id(plan, place_id)
    if not place:
        return {"ok": False, "error": "没有找到这个地点", "plan_id": plan_id, "source": TOOL_TRIP_GET_FOOD_DETAIL_NAME}
    item = await _fetch_food_for_place(session, place, keywords, radius=radius)
    replaced = False
    for i, old in enumerate(foods):
        if _text(old.get("place_id")) == place_id and _text(old.get("keywords")) == keywords:
            foods[i] = item
            replaced = True
            break
    if not replaced:
        foods.append(item)
    facts["food_candidates"] = _field(foods, 60, "amap_around_search")
    _quality_remove_refs(plan.setdefault("quality", _quality_empty()), {"facts.food_candidates", "facts.estimated_cost"})
    _save_plan(plan)
    return {
        "ok": True,
        "source": TOOL_TRIP_GET_FOOD_DETAIL_NAME,
        "plan_id": plan_id,
        "cache_hit": False,
        "food": item,
        "quality": plan.get("quality") if isinstance(plan.get("quality"), dict) else _quality_empty(),
    }


def _merge_state_list(existing: Any, incoming: Any) -> list:
    items = [x for x in _as_list(existing) if isinstance(x, dict)]
    for item in _as_list(incoming):
        if not isinstance(item, dict):
            continue
        key = _text(item.get("id") or item.get("type") or item.get("field") or item.get("content"))
        if key:
            items = [
                old for old in items
                if _text(old.get("id") or old.get("type") or old.get("field") or old.get("content")) != key
            ]
        merged = dict(item)
        merged.setdefault("updated_at", _now_iso())
        items.append(merged)
    return items


def _update_plan_state(args: dict) -> dict:
    plan_id = _plan_id_from_args(args)
    if not plan_id:
        return {"ok": False, "error": "缺少 plan_id", "source": TOOL_TRIP_UPDATE_PLAN_STATE_NAME}
    plan = r2_store.get_trip_plan(plan_id)
    if not plan:
        return {"ok": False, "error": "plan_id 不存在或缓存不可用", "plan_id": plan_id, "source": TOOL_TRIP_UPDATE_PLAN_STATE_NAME}
    state = plan.setdefault("plan_state", {})
    for key in ("user_overrides", "confirmed_state", "assistant_assumptions"):
        if key in args:
            state[key] = _merge_state_list(state.get(key), args.get(key))
    _save_plan(plan)
    return {
        "ok": True,
        "source": TOOL_TRIP_UPDATE_PLAN_STATE_NAME,
        "plan_id": plan_id,
        "plan_state": state,
        "rule": "user_overrides 永远优先；assistant_assumptions 只能影响建议和措辞，不能覆盖用户明确选择。",
    }


def _finalize_plan(args: dict) -> dict:
    plan_id = _plan_id_from_args(args)
    if not plan_id:
        return {"ok": False, "error": "缺少 plan_id", "source": TOOL_TRIP_FINALIZE_PLAN_NAME}
    plan = r2_store.get_trip_plan(plan_id)
    if not plan:
        return {"ok": False, "error": "plan_id 不存在或缓存不可用", "plan_id": plan_id, "source": TOOL_TRIP_FINALIZE_PLAN_NAME}
    status = _text(args.get("status") or "completed").lower()
    if status not in {"completed", "expired", "cancelled"}:
        status = "completed"
    meta = plan.setdefault("plan_meta", {})
    meta["status"] = status
    meta["finalized_at"] = _now_iso()
    meta["prefetch_status"] = "stopped"
    archive = {
        "plan_id": plan_id,
        "date": _text(meta.get("date")) or today_beijing(),
        "status": status,
        "summary": _text(args.get("summary")),
        "visited_places": [_text(x) for x in _as_list(args.get("visited_place_ids") or args.get("visitedPlaces")) if _text(x)],
        "skipped_places": [_text(x) for x in _as_list(args.get("skipped_place_ids") or args.get("skippedPlaces")) if _text(x)],
        "useful_conclusions": [_text(x) for x in _as_list(args.get("useful_conclusions") or args.get("usefulConclusions")) if _text(x)],
        "memory_candidates": [x for x in _as_list(args.get("memory_candidates") or args.get("memoryCandidates")) if isinstance(x, dict)],
        "finalized_at": meta["finalized_at"],
    }
    plan["archive"] = archive
    state = plan.get("plan_state") if isinstance(plan.get("plan_state"), dict) else {}
    plan["plan_state"] = {
        "preferences": state.get("preferences") if isinstance(state.get("preferences"), dict) else {},
        "user_overrides": state.get("user_overrides") if isinstance(state.get("user_overrides"), list) else [],
        "confirmed_state": state.get("confirmed_state") if isinstance(state.get("confirmed_state"), list) else [],
        "assistant_assumptions": [],
        "finalized": True,
    }
    plan["active_facts_cleared"] = True
    _save_plan(plan)
    return {
        "ok": True,
        "source": TOOL_TRIP_FINALIZE_PLAN_NAME,
        "plan_id": plan_id,
        "status": status,
        "archive": archive,
        "note": "该 plan 已退出活跃上下文；后续只使用轻量归档和可沉淀偏好候选。",
    }
