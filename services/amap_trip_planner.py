from __future__ import annotations

import json
import math
import re
from typing import Any

from mcp import ClientSession

from services.amap_mcp_client import call_tool_with_session, run_in_session
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)

TOOL_AMAP_TRIP_PLAN_NAME = "amap_trip_plan"
SYSTEM_CARD_PREFIX = "<<<SUMITALK_CARD "
SYSTEM_CARD_SUFFIX = ">>>"

TOOL_AMAP_TRIP_PLAN = {
    "type": "function",
    "function": {
        "name": TOOL_AMAP_TRIP_PLAN_NAME,
        "description": (
            "网关高级出行规划工具。一次调用内自动串联高德官方 MCP：搜索/解析地点、查 POI 详情、"
            "规划公交地铁、规划驾车/打车参考，并尽量生成高德导航/打车/专属地图链接。"
            "当老婆说想去某个地方、要求规划路线、比较地铁公交和打车时优先调用它。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destinations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "目的地列表，例如 [\"上海迪士尼\", \"武康路\"]。至少一个。",
                },
                "origin": {"type": "string", "description": "可选起点名称/地址；不传则尝试用最近定位。"},
                "origin_lnglat": {"type": "string", "description": "可选起点坐标，格式 lng,lat，优先级高于 origin。"},
                "city": {"type": "string", "description": "可选城市，用于缩小地点搜索范围，例如 上海。"},
                "prefer": {"type": "string", "description": "可选：auto / transit / taxi，默认 auto。"},
                "optimize_order": {
                    "type": "boolean",
                    "description": "多个目的地时是否做简单顺路排序，默认 true。",
                },
                "include_links": {
                    "type": "boolean",
                    "description": "是否生成高德导航/打车/专属地图链接，默认 true。",
                },
                "org_name": {"type": "string", "description": "专属地图名称，默认「渡的出行规划」。"},
            },
            "required": ["destinations"],
        },
    },
}


def execute_amap_trip_plan(arguments: dict) -> str:
    try:
        result = run_in_session(
            lambda session: _plan_trip_async(session, arguments if isinstance(arguments, dict) else {}),
            timeout_seconds=90,
        )
        card = _build_trip_result_card(result)
        if card:
            result = {**result, "sumitalk_card": card}
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning("amap_trip_plan failed error=%s", e)
        return json.dumps({"ok": False, "error": str(e), "source": "amap_trip_plan"}, ensure_ascii=False)


async def _mcp(session: ClientSession, name: str, args: dict) -> dict:
    try:
        return await call_tool_with_session(session, name, args)
    except Exception as e:
        logger.warning("amap_trip_plan mcp call failed tool=%s error=%s", name, e)
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


async def _resolve_place(session: ClientSession, query: str, city: str = "", role: str = "destination", origin_lnglat: str = "") -> tuple[dict | None, str]:
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
    if not transit.get("ok") and driving.get("ok"):
        return {"mode": "taxi", "reason": "没有查到稳定的公交/地铁方案。"}
    if transit.get("ok") and not driving.get("ok"):
        return {"mode": "transit", "reason": "驾车方案不可用，优先公交/地铁。"}
    if not transit.get("ok"):
        return {"mode": "unknown", "reason": "没有拿到可比较的路线。"}

    transit_sec = _safe_int(transit.get("duration_seconds"))
    driving_sec = _safe_int(driving.get("duration_seconds"))
    walk_m = _safe_int(transit.get("walking_distance_meters"))
    if walk_m >= 1800:
        return {"mode": "taxi", "reason": f"公交/地铁步行约{_format_distance(walk_m)}，比较折腾。"}
    if transit_sec and driving_sec and driving_sec <= transit_sec * 0.6:
        return {"mode": "taxi", "reason": "打车耗时明显更短。"}
    return {"mode": "transit", "reason": "公交/地铁耗时和步行距离都还可以。"}


async def _links_for_leg(session: ClientSession, start: dict, end: dict, include_links: bool) -> dict:
    if not include_links:
        return {}
    links: dict[str, str] = {}
    end_pair = _split_lnglat(_text(end.get("location")))
    start_pair = _split_lnglat(_text(start.get("location")))
    if end_pair:
        navi = await _mcp(session, "maps_schema_navi", {"lon": str(end_pair[0]), "lat": str(end_pair[1])})
        navi_data = _json_content(navi)
        links["navi"] = _extract_url(navi_data)
    if start_pair and end_pair:
        taxi = await _mcp(
            session,
            "maps_schema_take_taxi",
            {
                "slon": str(start_pair[0]),
                "slat": str(start_pair[1]),
                "sname": _text(start.get("name")) or "起点",
                "dlon": str(end_pair[0]),
                "dlat": str(end_pair[1]),
                "dname": _text(end.get("name")) or "终点",
            },
        )
        taxi_data = _json_content(taxi)
        links["taxi"] = _extract_url(taxi_data)
    return {k: v for k, v in links.items() if v}


def _extract_url(data: Any) -> str:
    if isinstance(data, str):
        m = re.search(r"https?://\\S+|amapuri://\\S+", data)
        return (m.group(0) if m else data).strip()
    if isinstance(data, dict):
        for key in ("url", "uri", "link", "schema", "scheme"):
            val = _text(data.get(key))
            if val:
                return val
        for val in data.values():
            found = _extract_url(val)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = _extract_url(item)
            if found:
                return found
    return ""


async def _personal_map(session: ClientSession, org_name: str, destinations: list[dict], include_links: bool) -> str:
    if not include_links or not destinations:
        return ""
    point_list = []
    for place in destinations:
        pair = _split_lnglat(_text(place.get("location")))
        if not pair:
            continue
        point_list.append(
            {
                "name": _text(place.get("name")) or _text(place.get("input")),
                "lon": pair[0],
                "lat": pair[1],
                "poiId": _text(place.get("id")),
            }
        )
    if not point_list:
        return ""
    res = await _mcp(
        session,
        "maps_schema_personal_map",
        {"orgName": org_name or "渡的出行规划", "lineList": [{"title": "行程路线", "pointInfoList": point_list}]},
    )
    return _extract_url(_json_content(res))


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
    else:
        lines.append(f"打车/驾车：{driving.get('error') or '无结果'}")
    lines.append(f"建议：{rec.get('mode')}，{rec.get('reason')}")
    return lines


def _build_trip_result_card(result: dict) -> str:
    if not isinstance(result, dict) or not result.get("ok"):
        return ""
    legs = []
    for leg in _as_list(result.get("legs"))[:6]:
        if not isinstance(leg, dict):
            continue
        transit = leg.get("transit") if isinstance(leg.get("transit"), dict) else {}
        driving = leg.get("driving") if isinstance(leg.get("driving"), dict) else {}
        rec = leg.get("recommendation") if isinstance(leg.get("recommendation"), dict) else {}
        links = leg.get("links") if isinstance(leg.get("links"), dict) else {}
        from_place = leg.get("from") if isinstance(leg.get("from"), dict) else {}
        to_place = leg.get("to") if isinstance(leg.get("to"), dict) else {}
        legs.append(
            {
                "from": _text(from_place.get("name") or from_place.get("input") or "起点"),
                "to": _text(to_place.get("name") or to_place.get("input") or "终点"),
                "mode": _text(rec.get("mode")),
                "reason": _text(rec.get("reason")),
                "transit": {
                    "ok": bool(transit.get("ok")),
                    "duration": _text(transit.get("duration")),
                    "walking": _text(transit.get("walking_distance")),
                    "costYuan": _safe_float(transit.get("cost_yuan")),
                    "taxiCostYuan": _safe_float(transit.get("taxi_cost_yuan")),
                    "steps": [_text(x) for x in _as_list(transit.get("steps")) if _text(x)][:4],
                    "error": _text(transit.get("error")),
                },
                "driving": {
                    "ok": bool(driving.get("ok")),
                    "duration": _text(driving.get("duration")),
                    "distance": _text(driving.get("distance")),
                    "steps": [_text(x) for x in _as_list(driving.get("steps")) if _text(x)][:3],
                    "error": _text(driving.get("error")),
                },
                "links": {
                    "navi": _text(links.get("navi")),
                    "taxi": _text(links.get("taxi")),
                },
                "summary": [_text(x) for x in _as_list(leg.get("summary")) if _text(x)][:4],
            }
        )
    destinations = []
    for place in _as_list(result.get("destinations"))[:6]:
        if isinstance(place, dict):
            name = _text(place.get("name") or place.get("input"))
            if name:
                destinations.append(name)
    origin = result.get("origin") if isinstance(result.get("origin"), dict) else {}
    card = {
        "type": "travel_plan_result",
        "title": "渡安排好了",
        "origin": _text(origin.get("name") or origin.get("input") or "起点"),
        "destinations": destinations,
        "optimized": bool(result.get("optimized_order")),
        "legs": legs,
        "personalMapUrl": _text(result.get("personal_map_url")),
        "note": _text(result.get("note")),
    }
    return f"{SYSTEM_CARD_PREFIX}{json.dumps(card, ensure_ascii=False, separators=(',', ':'))}{SYSTEM_CARD_SUFFIX}"


async def _plan_trip_async(session: ClientSession, args: dict) -> dict:
    destinations_raw = _split_destinations(args.get("destinations") or args.get("destination") or args.get("places"))
    if not destinations_raw:
        return {"ok": False, "error": "destinations 不能为空", "source": "amap_trip_plan"}

    city = _text(args.get("city") or args.get("region"))
    origin_raw = _text(args.get("origin"))
    origin_lnglat = _text(args.get("origin_lnglat") or args.get("originLocation") or args.get("origin_location"))
    prefer = _text(args.get("prefer") or "auto")
    optimize_order = bool(args.get("optimize_order", True))
    include_links = bool(args.get("include_links", True))
    org_name = _text(args.get("org_name") or "渡的出行规划")

    origin, origin_err = await _resolve_place(session, origin_raw, city=city, role="origin", origin_lnglat=origin_lnglat)
    if not origin:
        return {"ok": False, "error": origin_err or "起点解析失败", "source": "amap_trip_plan"}

    route_city = city or _text(origin.get("city"))
    places: list[dict] = []
    place_errors: list[dict] = []
    for item in destinations_raw:
        place, err = await _resolve_place(session, item, city=route_city, role="destination")
        if place:
            places.append(place)
        else:
            place_errors.append({"input": item, "error": err})
    if not places:
        return {"ok": False, "error": "目的地都没解析成功", "place_errors": place_errors, "source": "amap_trip_plan"}

    ordered = _order_places(origin, places, optimize=optimize_order)
    legs: list[dict] = []
    current = origin
    for place in ordered:
        transit_res = await _mcp(
            session,
            "maps_direction_transit_integrated",
            {
                "origin": _text(current.get("location")),
                "destination": _text(place.get("location")),
                "city": _text(current.get("city") or route_city),
                "cityd": _text(place.get("city") or route_city),
            },
        )
        driving_res = await _mcp(
            session,
            "maps_direction_driving",
            {"origin": _text(current.get("location")), "destination": _text(place.get("location"))},
        )
        transit = _summarize_transit(_json_content(transit_res))
        driving = _summarize_driving(_json_content(driving_res))
        rec = _recommend(prefer, transit, driving)
        links = await _links_for_leg(session, current, place, include_links)
        legs.append(
            {
                "from": _public_place(current),
                "to": _public_place(place),
                "transit": transit,
                "driving": driving,
                "recommendation": rec,
                "links": links,
                "summary": _leg_summary(current, place, transit, driving, rec),
            }
        )
        current = place

    personal_map_url = await _personal_map(session, org_name, ordered, include_links)
    return {
        "ok": True,
        "source": "amap_trip_plan",
        "origin": _public_place(origin),
        "destinations": [_public_place(x) for x in ordered],
        "optimized_order": bool(optimize_order and len(places) > 1),
        "place_errors": place_errors,
        "legs": legs,
        "personal_map_url": personal_map_url,
        "note": "地点、路线、耗时、费用和链接来自高德官方 MCP；实际以出发时高德地图为准。",
    }
