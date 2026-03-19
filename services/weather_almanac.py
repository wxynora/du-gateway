# 天气与黄历：聚合数据等 API，供渡查天气、查黄历工具调用
import requests
from typing import Optional

from config import (
    WEATHER_API_URL,
    WEATHER_API_KEY,
    ALMANAC_API_URL,
    ALMANAC_API_KEY,
)
from utils.log import get_logger
from utils.time_aware import today_beijing, get_exact_time

logger = get_logger(__name__)


def fetch_weather(city: str) -> str:
    """根据城市查天气，返回给人看的一段话。未配置或失败返回错误说明。"""
    city = (city or "").strip()
    if not city:
        return "请提供城市名，例如：北京、铜陵。"
    if not WEATHER_API_URL or not WEATHER_API_KEY:
        return "未配置天气 API（WEATHER_API_URL、WEATHER_API_KEY）。"
    try:
        r = requests.get(
            WEATHER_API_URL,
            params={"key": WEATHER_API_KEY, "city": city},
            timeout=10,
        )
        if r.status_code != 200:
            return f"天气接口请求异常，状态码 {r.status_code}。"
        data = r.json()
        # 聚合数据：成功以 error_code==0 为准（reason 可能为「查询成功」等）
        if data.get("error_code") != 0:
            return (data.get("reason") or data.get("message") or "接口返回失败") + "。"
        res = data.get("result") or {}
        realtime = res.get("realtime") or res
        temp = realtime.get("temperature") or res.get("temperature") or ""
        info = realtime.get("info") or res.get("weather") or "—"
        humidity = realtime.get("humidity") or res.get("humidity") or ""
        direct = (realtime.get("direct") or "").strip()
        power = (realtime.get("power") or "").strip()
        wind = f"{direct} {power}".strip() if (direct or power) else ""
        parts = [f"{city}：{info}"]
        if temp:
            parts.append(f"{temp}℃")
        if humidity:
            parts.append(f"湿度{humidity}%")
        if wind:
            parts.append(wind)
        aqi = realtime.get("aqi")
        if aqi:
            parts.append(f"空气质量{aqi}")
        return "，".join(parts) if parts else "暂无天气数据。"
    except Exception as e:
        logger.exception("天气 API 请求异常 city=%s", city)
        return f"查天气时出错：{e}。"


def fetch_almanac(date: Optional[str] = None) -> str:
    """查黄历（宜忌等），date 为 YYYY-MM-DD，默认今天北京时间。"""
    if not ALMANAC_API_URL or not ALMANAC_API_KEY:
        return "未配置黄历 API（ALMANAC_API_URL、ALMANAC_API_KEY）。"
    day = (date or "").strip() or today_beijing()
    try:
        r = requests.get(
            ALMANAC_API_URL,
            params={"key": ALMANAC_API_KEY, "date": day},
            timeout=10,
        )
        if r.status_code != 200:
            return f"黄历接口请求异常，状态码 {r.status_code}。"
        data = r.json()
        # 成功以 error_code==0 为准（reason 可能为 "successed" 等）
        if data.get("error_code") != 0:
            return (data.get("reason") or data.get("message") or "接口返回失败") + "。"
        res = data.get("result") or {}
        # 聚合黄历：阳历 yangli，农历 yinli，宜 yi，忌 ji
        date_str = res.get("yangli") or res.get("date") or day
        week = res.get("week") or ""
        lunar = res.get("yinli") or res.get("lunar") or res.get("lunarYear") or ""
        suit = res.get("yi") or res.get("suit") or "—"
        avoid = res.get("ji") or res.get("avoid") or "—"
        lines = [f"{date_str} {week} 农历 {lunar}", f"宜：{suit}", f"忌：{avoid}"]
        return "\n".join(lines)
    except Exception as e:
        logger.exception("黄历 API 请求异常 date=%s", day)
        return f"查黄历时出错：{e}。"


def get_weather_almanac_tools() -> list:
    """返回天气、黄历工具定义，供注入到 chat；未配置则不返回。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_time_info",
                "description": "获取当前北京时间（仅 HH:mm）。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
    ]
    if WEATHER_API_URL and WEATHER_API_KEY:
        tools.append({
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "根据城市名查询当前天气（温度、天气、湿度等），用于关心对方穿衣、出行、要不要带伞等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名，如北京、铜陵、上海"},
                    },
                    "required": ["city"],
                },
            },
        })
    if ALMANAC_API_URL and ALMANAC_API_KEY:
        tools.append({
            "type": "function",
            "function": {
                "name": "get_almanac",
                "description": "查询某日黄历（农历、宜忌）。不传 date 则查今天。用于回应当天宜忌、农历日期等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "日期 YYYY-MM-DD，不传则查今天"},
                    },
                    "required": [],
                },
            },
        })
    return tools


def execute_weather_almanac_tool(name: str, arguments: dict) -> str:
    """执行天气/黄历工具，返回给渡的字符串。"""
    if name == "get_time_info":
        # 仅返回当前北京时间 HH:mm（用户明确不需要日期/农历等）
        return get_exact_time()
    if name == "get_weather":
        return fetch_weather(arguments.get("city"))
    if name == "get_almanac":
        return fetch_almanac(arguments.get("date"))
    return "未知工具"
