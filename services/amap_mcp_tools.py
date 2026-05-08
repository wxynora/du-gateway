from __future__ import annotations

import copy
import json
from typing import Any

from services.amap_mcp_client import amap_mcp_enabled, call_tool, list_tools
from services.amap_trip_planner import (
    TOOL_AMAP_TRIP_PLAN_NAME,
    TOOL_TRIP_FINALIZE_PLAN_NAME,
    TOOL_TRIP_GET_FOOD_DETAIL_NAME,
    TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME,
    TOOL_TRIP_PREPARE_FACTS_NAME,
    TOOL_TRIP_UPDATE_PLAN_STATE_NAME,
    TRIP_LAYERED_TOOL_NAMES,
    TRIP_LAYERED_TOOLS,
    execute_amap_trip_plan,
    execute_trip_finalize_plan,
    execute_trip_get_food_detail,
    execute_trip_get_transport_detail,
    execute_trip_prepare_facts,
    execute_trip_update_plan_state,
)
from utils.log import get_logger

logger = get_logger(__name__)

AMAP_MCP_TOOL_PREFIX = "maps_"
TOOL_OPEN_TRAVEL_PLAN_FORM_NAME = "open_travel_plan_form"
SYSTEM_CARD_PREFIX = "<<<SUMITALK_CARD "
SYSTEM_CARD_SUFFIX = ">>>"

TOOL_OPEN_TRAVEL_PLAN_FORM = {
    "type": "function",
    "function": {
        "name": TOOL_OPEN_TRAVEL_PLAN_FORM_NAME,
        "description": (
            "在 SumiTalk 聊天界面弹出固定的出行规划表单，让老婆填写想去的地方、想吃的东西、"
            "步行接受度、交通偏好等信息。用户只是表达想让渡规划旅游/路线但信息还不完整时，优先调用这个。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "表单标题，默认「出行规划」"},
                "prompt": {"type": "string", "description": "表单上方的一句话提示，可不传"},
                "city": {"type": "string", "description": "可预填城市"},
                "destinations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可预填想去的地点",
                },
                "food": {"type": "string", "description": "可预填想吃的东西"},
                "prefer": {"type": "string", "description": "可预填交通偏好：auto / transit / taxi"},
                "walk": {"type": "string", "description": "可预填步行接受度：low / medium / high"},
            },
        },
    },
}

_TRAVEL_KEYWORDS = (
    "去哪",
    "哪里玩",
    "路线",
    "导航",
    "怎么去",
    "怎么走",
    "地铁",
    "公交",
    "打车",
    "出租车",
    "网约车",
    "换乘",
    "出行",
    "旅游",
    "旅行",
    "景点",
    "攻略",
    "poi",
    "高德",
)

_NON_TRAVEL_GO_KEYWORDS = (
    "去睡",
    "去睡觉",
    "睡觉",
    "睡了",
    "睡啦",
    "去洗澡",
    "去休息",
    "去躺",
)

_TRAVEL_GO_HINTS = (
    "玩",
    "逛",
    "吃",
    "旅游",
    "旅行",
    "景点",
    "公园",
    "商场",
    "餐厅",
    "酒店",
    "民宿",
    "机场",
    "车站",
    "火车站",
    "高铁站",
    "地铁站",
    "博物馆",
    "展览",
    "迪士尼",
    "环球",
)

_TRAVEL_TOOL_NAMES = frozenset(
    {
        "maps_geo",
        "maps_regeocode",
        "maps_ip_location",
        "maps_weather",
        "maps_direction_bicycling",
        "maps_direction_walking",
        "maps_direction_driving",
        "maps_direction_transit_integrated",
        "maps_distance",
        "maps_text_search",
        "maps_around_search",
        "maps_search_detail",
        "maps_schema_navi",
        "maps_schema_take_taxi",
        "maps_schema_personal_map",
    }
)


def should_inject_amap_mcp_tools(text: str) -> bool:
    if not amap_mcp_enabled():
        return False
    raw = str(text or "").strip()
    if "[Proactive trigger fact]" in raw:
        return False
    q = raw.lower()
    if not q:
        return False
    if any(k in q for k in _TRAVEL_KEYWORDS):
        return True
    if any(k in q for k in _NON_TRAVEL_GO_KEYWORDS):
        return False
    has_go_intent = any(k in q for k in ("想去", "要去", "打算去", "准备去", "计划去"))
    if has_go_intent and any(k in q for k in _TRAVEL_GO_HINTS):
        return True
    return False


def _sanitize_schema(input_schema: dict | None) -> dict:
    schema = copy.deepcopy(input_schema if isinstance(input_schema, dict) else {})
    if not isinstance(schema, dict):
        schema = {}
    props = schema.get("properties")
    if not isinstance(props, dict):
        props = {}
    schema["type"] = "object"
    schema["properties"] = props
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [str(x) for x in required if str(x).strip()]
    return schema


def _tool_description(name: str, remote_desc: str) -> str:
    prefix = "高德官方 MCP 工具。"
    if name == "maps_direction_transit_integrated":
        prefix += "查询地铁/公交/火车等公共交通换乘方案；路线不要凭空编。"
    elif name == "maps_direction_driving":
        prefix += "查询驾车路线，可作为打车耗时参考。"
    elif name == "maps_text_search":
        prefix += "按关键词搜索 POI 地点，用于把用户说的地点解析成高德地点。"
    elif name == "maps_schema_take_taxi":
        prefix += "生成高德打车唤端链接。"
    elif name == "maps_schema_personal_map":
        prefix += "把规划点位导入高德地图，生成专属地图唤端链接。"
    desc = str(remote_desc or "").strip()
    return f"{prefix}\n{desc}".strip()


def get_amap_mcp_tools_for_inject() -> list[dict]:
    if not amap_mcp_enabled():
        return []
    out: list[dict] = [TOOL_OPEN_TRAVEL_PLAN_FORM, *TRIP_LAYERED_TOOLS]
    try:
        remote_tools = list_tools()
    except Exception as e:
        logger.warning("amap_mcp list_tools failed while building inject tools: %s", e)
        return out

    for name in sorted(_TRAVEL_TOOL_NAMES):
        meta = remote_tools.get(name) or {}
        tool_name = str(meta.get("name") or "").strip()
        if not tool_name:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": _tool_description(tool_name, str(meta.get("description") or "").strip()),
                    "parameters": _sanitize_schema(meta.get("input_schema") or {}),
                },
            }
        )
    return out


def is_amap_mcp_tool(name: str) -> bool:
    tool_name = str(name or "").strip()
    return tool_name in (TOOL_OPEN_TRAVEL_PLAN_FORM_NAME, TOOL_AMAP_TRIP_PLAN_NAME) or tool_name in TRIP_LAYERED_TOOL_NAMES or (
        bool(tool_name) and tool_name.startswith(AMAP_MCP_TOOL_PREFIX)
    )


def _split_prefill_destinations(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("，", ",").replace("、", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        s = str(item or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:6]


def execute_open_travel_plan_form(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    card = {
        "type": "travel_plan_form",
        "title": str(args.get("title") or "出行规划").strip() or "出行规划",
        "prompt": str(args.get("prompt") or "把想去哪里、想吃什么、能不能走路填一下，渡再帮你排顺序和路线。").strip(),
        "city": str(args.get("city") or "").strip(),
        "destinations": _split_prefill_destinations(args.get("destinations")),
        "food": str(args.get("food") or "").strip(),
        "prefer": str(args.get("prefer") or "auto").strip() or "auto",
        "walk": str(args.get("walk") or "medium").strip() or "medium",
    }
    marker = f"{SYSTEM_CARD_PREFIX}{json.dumps(card, ensure_ascii=False)}{SYSTEM_CARD_SUFFIX}"
    return json.dumps(
        {
            "ok": True,
            "source": "sumitalk_travel_form",
            "sumitalk_card": marker,
            "card": card,
            "note": "已弹出 SumiTalk 出行规划表单，等老婆填完后再规划路线。",
        },
        ensure_ascii=False,
    )


def execute_amap_mcp_tool(name: str, arguments: dict) -> str:
    tool_name = str(name or "").strip()
    if not is_amap_mcp_tool(tool_name):
        return json.dumps({"ok": False, "error": f"未知高德 MCP 工具: {tool_name}"}, ensure_ascii=False)
    if tool_name == TOOL_OPEN_TRAVEL_PLAN_FORM_NAME:
        return execute_open_travel_plan_form(arguments if isinstance(arguments, dict) else {})
    if tool_name == TOOL_TRIP_PREPARE_FACTS_NAME:
        return execute_trip_prepare_facts(arguments if isinstance(arguments, dict) else {})
    if tool_name == TOOL_TRIP_GET_TRANSPORT_DETAIL_NAME:
        return execute_trip_get_transport_detail(arguments if isinstance(arguments, dict) else {})
    if tool_name == TOOL_TRIP_GET_FOOD_DETAIL_NAME:
        return execute_trip_get_food_detail(arguments if isinstance(arguments, dict) else {})
    if tool_name == TOOL_TRIP_UPDATE_PLAN_STATE_NAME:
        return execute_trip_update_plan_state(arguments if isinstance(arguments, dict) else {})
    if tool_name == TOOL_TRIP_FINALIZE_PLAN_NAME:
        return execute_trip_finalize_plan(arguments if isinstance(arguments, dict) else {})
    if tool_name == TOOL_AMAP_TRIP_PLAN_NAME:
        return execute_amap_trip_plan(arguments if isinstance(arguments, dict) else {})
    try:
        result = call_tool(tool_name, arguments if isinstance(arguments, dict) else {})
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning("amap_mcp call failed tool=%s error=%s", tool_name, e)
        return json.dumps({"ok": False, "tool": tool_name, "error": str(e), "source": "amap_mcp"}, ensure_ascii=False)
