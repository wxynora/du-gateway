# 高德逆地理编码：经纬度 → 格式化地址（需环境变量 AMAP_API_KEY）
from __future__ import annotations

import math

import requests

from config import AMAP_API_KEY
from storage.sense_store import LOCATION_NEARBY_COORDINATE_DELTA, LOCATION_RECENT_SECONDS
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

_CONVERT_URL = "https://restapi.amap.com/v3/assistant/coordinate/convert"
_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"


def convert_wgs84_to_gcj02(lat: float, lng: float) -> tuple[float, float] | None:
    """调用高德坐标转换，返回 GCJ-02 的（纬度，经度）。"""
    key = (AMAP_API_KEY or "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            _CONVERT_URL,
            params={
                "key": key,
                "locations": f"{lng},{lat}",
                "coordsys": "gps",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("status")) != "1":
            logger.warning("高德坐标转换异常 status=%s info=%s", data.get("status"), data.get("info"))
            return None
        location = str(data.get("locations") or "").split(";", 1)[0].strip()
        converted_lng, converted_lat = (float(part.strip()) for part in location.split(",", 1))
        if not math.isfinite(converted_lat) or not math.isfinite(converted_lng):
            return None
        return converted_lat, converted_lng
    except Exception as e:
        logger.warning("高德坐标转换请求失败 error=%s", e)
        return None


def reverse_geocode_formatted_address(lat: float, lng: float) -> str | None:
    """
    使用 GCJ-02 坐标逆地理并返回 formatted_address；无 key、请求失败或接口报错时返回 None。
    注意：高德 location 参数为「经度,纬度」。
    """
    key = (AMAP_API_KEY or "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            _REGEO_URL,
            params={
                "key": key,
                "location": f"{lng},{lat}",
                "extensions": "base",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("高德逆地理请求失败 error=%s", e)
        return None
    if str(data.get("status")) != "1":
        logger.warning("高德逆地理异常 status=%s info=%s", data.get("status"), data.get("info"))
        return None
    regeocode = data.get("regeocode") or {}
    addr = (regeocode.get("formatted_address") or "").strip()
    return addr or None


def _reuse_recent_address(previous: dict, lat: float, lng: float, now_iso: str) -> bool:
    address = str(previous.get("address") or "").strip()
    resolved_at = parse_iso_to_beijing(str(previous.get("address_resolved_at") or "").strip())
    now_dt = parse_iso_to_beijing(now_iso)
    if not address or not resolved_at or not now_dt:
        return False
    age_seconds = (now_dt - resolved_at).total_seconds()
    if age_seconds < 0 or age_seconds >= LOCATION_RECENT_SECONDS:
        return False
    try:
        previous_lat = float(previous.get("wgs84_lat", previous.get("lat")))
        previous_lng = float(previous.get("wgs84_lng", previous.get("lng")))
    except (TypeError, ValueError):
        return False
    return (
        abs(lat - previous_lat) < LOCATION_NEARBY_COORDINATE_DELTA
        and abs(lng - previous_lng) < LOCATION_NEARBY_COORDINATE_DELTA
    )


def _preserve_previous_address(patch: dict, previous: dict) -> None:
    address = str(previous.get("address") or "").strip()
    if address:
        patch["address"] = address
    resolved_at = str(previous.get("address_resolved_at") or "").strip()
    if resolved_at:
        patch["address_resolved_at"] = resolved_at


def enrich_location_patch_with_amap_address(
    patch: dict,
    *,
    previous_location: dict | None = None,
    current_time: str = "",
) -> dict:
    """保存原始 WGS84，并用转换后的 GCJ-02 解析地址。"""
    if not (AMAP_API_KEY or "").strip():
        return patch
    p = dict(patch)
    if p.get("lat") is None or p.get("lng") is None:
        return p
    try:
        la = float(p["lat"])
        ln = float(p["lng"])
    except (TypeError, ValueError):
        return p
    p["wgs84_lat"] = la
    p["wgs84_lng"] = ln
    previous = previous_location if isinstance(previous_location, dict) else {}
    event_time = str(current_time or "").strip() or now_beijing_iso()

    converted = convert_wgs84_to_gcj02(la, ln)
    if converted is None:
        p["gcj02_lat"] = None
        p["gcj02_lng"] = None
        _preserve_previous_address(p, previous)
        p["address_resolution_status"] = "failed"
        p["address_resolution_failed_at"] = event_time
        return p

    gcj02_lat, gcj02_lng = converted
    p["gcj02_lat"] = gcj02_lat
    p["gcj02_lng"] = gcj02_lng
    if _reuse_recent_address(previous, la, ln, event_time):
        _preserve_previous_address(p, previous)
        p["address_resolution_status"] = "cached"
        p["address_resolution_failed_at"] = ""
        return p

    addr = reverse_geocode_formatted_address(gcj02_lat, gcj02_lng)
    if addr:
        p["address"] = addr
        p["address_resolved_at"] = event_time
        p["address_resolution_status"] = "resolved"
        p["address_resolution_failed_at"] = ""
        return p

    _preserve_previous_address(p, previous)
    p["address_resolution_status"] = "failed"
    p["address_resolution_failed_at"] = event_time
    return p
