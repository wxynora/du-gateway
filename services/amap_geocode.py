# 高德逆地理编码：经纬度 → 格式化地址（需环境变量 AMAP_API_KEY）
from __future__ import annotations

import requests

from config import AMAP_API_KEY
from utils.log import get_logger

logger = get_logger(__name__)

_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"


def reverse_geocode_formatted_address(lat: float, lng: float) -> str | None:
    """
    逆地理：返回 formatted_address；无 key、请求失败或接口报错时返回 None。
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


def enrich_location_patch_with_amap_address(patch: dict) -> dict:
    """
    在 location 上报已有 lat/lng 时调用高德写入 address；已配 Key 但逆地理失败时写空串，避免与旧坐标不一致。
    未配 Key 时不改 patch。
    """
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
    addr = reverse_geocode_formatted_address(la, ln)
    p["address"] = addr if addr else ""
    return p
