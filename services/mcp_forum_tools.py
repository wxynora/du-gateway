import copy
import json
import shlex

from config import (
    MCP_ENABLED,
)
from services.forum_mcp_client import call_cli, call_tool, forum_mcp_enabled, list_tools
from utils.log import get_logger

logger = get_logger(__name__)

FORUM_HIGH_LEVEL_TOOLS = {
    "forum_read_feed",
    "forum_open_thread",
}

LEGACY_SUBMOLT_MAP = {
    "night_dark": "nighttalk",
}

TOOL_FORUM_READ_FEED = {
    "type": "function",
    "function": {
        "name": "forum_read_feed",
        "description": (
            "高层看帖工具：读取帖子信息流并返回适合直接浏览的帖子卡片摘要。\n"
            "日常刷帖、随便看看论坛时优先用这个，不要自己拆底层列表接口。\n"
            "它返回的是精简卡片，不是一整坨原始 JSON。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "可选：返回条数，默认 10，最大 30"},
                "submolt": {"type": "string", "description": "可选：子版块名称或 ID"},
            },
        },
    },
}

TOOL_FORUM_OPEN_THREAD = {
    "type": "function",
    "function": {
        "name": "forum_open_thread",
        "description": (
            "高层开帖工具：一次返回帖子正文摘要和评论摘要。\n"
            "想看某个帖子、理解讨论、准备回帖时优先用这个，不要自己拆底层详情和评论接口。\n"
            "适合日常进帖查看。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string", "description": "必填：帖子 ID"},
            },
            "required": ["post_id"],
        },
    },
}

TOOL_SCHEDULE_LIST = {
    "type": "function",
    "function": {
        "name": "schedule_list",
        "description": "查看当前提醒列表（可按启用状态筛选）。",
        "parameters": {
            "type": "object",
            "properties": {
                "enabled_only": {"type": "boolean", "description": "可选：true 仅返回启用项"},
                "limit": {"type": "integer", "description": "可选：返回条数上限，默认 50"},
            },
        },
    },
}

TOOL_SCHEDULE_CREATE = {
    "type": "function",
    "function": {
        "name": "schedule_create",
        "description": "创建提醒。repeat 支持 once/daily/weekly；weekly 可传 weekly_weekdays（0-6，周一=0）一次创建多天。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "提醒标题"},
                "repeat": {"type": "string", "description": "once/daily/weekly"},
                "datetime": {"type": "string", "description": "once 模式必填：ISO 时间，例如 2026-03-20T21:30:00+08:00"},
                "daily_time": {"type": "string", "description": "daily 模式必填：HH:mm"},
                "weekly_time": {"type": "string", "description": "weekly 模式必填：HH:mm"},
                "weekly_weekday": {"type": "integer", "description": "weekly 可选：0-6（周一=0）"},
                "weekly_weekdays": {"type": "array", "items": {"type": "integer"}},
                "note": {"type": "string", "description": "可选备注"},
                "enabled": {"type": "boolean", "description": "可选，默认 true"},
                "created_by": {"type": "string", "description": "可选：wife 或 du；不传默认 wife"},
                "target_role": {"type": "string", "description": "可选：wife 或 du；表示提醒对象，不传默认 wife"},
            },
            "required": ["title"],
        },
    },
}

TOOL_SCHEDULE_ENABLE = {
    "type": "function",
    "function": {
        "name": "schedule_enable",
        "description": "启用一条提醒。",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
}

TOOL_SCHEDULE_DISABLE = {
    "type": "function",
    "function": {
        "name": "schedule_disable",
        "description": "禁用一条提醒。",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
}

TOOL_SCHEDULE_DELETE = {
    "type": "function",
    "function": {
        "name": "schedule_delete",
        "description": "删除一条提醒。",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
}

TOOL_SEARCH_MEMORY = {
    "type": "function",
    "function": {
        "name": "search_memory",
        "description": (
            "当你怀疑当前自动召回的动态记忆不够准或漏了熟悉话题时，主动补检动态记忆层。\n"
            "要求：query 必填，且只能基于用户当前原始消息；scene_type/target_type/time_range 只是辅助筛选。\n"
            "限制：suspicion_level=low 时禁止调用。第一版只查动态层，不查核心缓存层。\n"
            "触发条件：只有当当前召回明显和用户这句话对不上，或你强烈怀疑用户在提一个熟悉主题但召回缺失时才调用。\n"
            "禁止：不要把已召回记忆内容反过来拼成 query，不要为了“多搜一遍看看”而调用，不要在当前召回已经够用时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "必填，只能基于用户当前原始消息"},
                "scene_type": {"type": "string", "description": "可选：problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict"},
                "target_type": {"type": "string", "description": "可选：external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic"},
                "time_range": {"type": "string", "description": "可选：recent_7d / recent_15d / recent_30d / all / between:YYYY-MM-DD,YYYY-MM-DD"},
                "reason": {"type": "string", "description": "一句话说明为什么怀疑当前召回不够"},
                "suspicion_level": {"type": "string", "description": "必填：high / medium / low"},
            },
            "required": ["query", "reason", "suspicion_level"],
        },
    },
}


def get_forum_tools_for_inject(mode: str = "forum") -> list[dict]:
    """
    返回给模型的论坛/日程工具列表。
    mode:
    - daily: 仅日常高频（闹钟相关）
    - forum: 日常 + 论坛高频（发帖/评论/看帖）
    """
    if not MCP_ENABLED:
        return []
    schedule_tools = [
        TOOL_SCHEDULE_LIST,
        TOOL_SCHEDULE_CREATE,
        TOOL_SCHEDULE_ENABLE,
        TOOL_SCHEDULE_DISABLE,
        TOOL_SCHEDULE_DELETE,
    ]
    if mode == "daily":
        return schedule_tools
    high_level = [
        TOOL_FORUM_READ_FEED,
        TOOL_FORUM_OPEN_THREAD,
    ]
    return schedule_tools + high_level + _get_remote_forum_tools_for_inject() + [TOOL_SEARCH_MEMORY]

def _sanitize_remote_schema(input_schema: dict | None) -> dict:
    schema = copy.deepcopy(input_schema if isinstance(input_schema, dict) else {})
    if not isinstance(schema, dict):
        schema = {}
    props = schema.get("properties")
    if not isinstance(props, dict):
        props = {}
    else:
        props = dict(props)
    props.pop("token", None)
    schema["type"] = "object"
    schema["properties"] = props
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [x for x in required if str(x).strip() != "token"]
    return schema


def _get_remote_forum_tools_for_inject() -> list[dict]:
    if not forum_mcp_enabled():
        return []
    try:
        remote_tools = list_tools()
    except Exception as e:
        logger.warning("forum_mcp list_tools failed while building inject tools: %s", e)
        return []

    out: list[dict] = []
    for name in ("cli", "get_guide"):
        meta = remote_tools.get(name) or {}
        tool_name = str(meta.get("name") or "").strip()
        if not tool_name:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": str(meta.get("description") or "").strip(),
                    "parameters": _sanitize_remote_schema(meta.get("input_schema") or {}),
                },
            }
        )
    return out


def _quote_cli_arg(value) -> str:
    return shlex.quote(str(value or "").strip())


def _normalize_submolt(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "general"
    return LEGACY_SUBMOLT_MAP.get(raw, raw)


def _build_forum_cli_command(name: str, args: dict) -> tuple[str, str | None]:
    if name == "forum_read_feed":
        parts = ["list"]
        limit = args.get("limit")
        submolt = str(args.get("submolt") or "").strip()
        if limit is not None:
            parts.extend(["--limit", str(limit)])
        if submolt:
            parts.extend(["--submolt", _normalize_submolt(submolt)])
        return " ".join(parts), None

    if name == "forum_open_thread":
        post_id = str(args.get("post_id") or "").strip()
        if not post_id:
            raise ValueError("post_id 不能为空")
        return f"show {_quote_cli_arg(post_id)}", None

    raise ValueError(f"未支持的论坛 MCP 工具: {name}")


def _execute_forum_mcp_tool(name: str, args: dict) -> dict:
    if not forum_mcp_enabled():
        return {"ok": False, "error": "未配置 FORUM_MCP_SSE_URL"}
    try:
        command, stdin = _build_forum_cli_command(name, args)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    result = call_cli(command, stdin=stdin)
    result["local_tool"] = name
    result["command"] = command
    result["stdin_used"] = stdin is not None
    result["source"] = "forum_mcp"
    return result


def _execute_remote_forum_tool(name: str, args: dict) -> dict:
    if not forum_mcp_enabled():
        return {"ok": False, "error": "未配置 FORUM_MCP_SSE_URL"}

    if name == "cli":
        command = str(args.get("command") or "").strip()
        if not command:
            return {"ok": False, "error": "command 不能为空"}
        stdin = args.get("stdin")
        result = call_cli(command, stdin=None if stdin is None else str(stdin))
    elif name == "get_guide":
        section = str(args.get("section") or "").strip()
        payload = {"section": section} if section else {}
        result = call_tool("get_guide", payload)
    else:
        return {"ok": False, "error": f"未支持的远端论坛工具: {name}"}

    result["source"] = "forum_mcp"
    return result


def execute_forum_tool(name: str, arguments: dict) -> str:
    """在聊天工具链里执行论坛工具，返回字符串。"""
    args = arguments if isinstance(arguments, dict) else {}

    if name.startswith("schedule_"):
        from storage import r2_store
        from utils.time_aware import now_beijing_iso

        def _notify_schedule_changed():
            try:
                from services.schedule_runtime import notify_schedule_changed
                notify_schedule_changed()
            except Exception:
                pass

        if name == "schedule_list":
            enabled_only = bool(args.get("enabled_only", False))
            limit = int(args.get("limit") or 50)
            if limit < 1:
                limit = 1
            if limit > 200:
                limit = 200
            items = r2_store.get_schedule_items() or []
            if enabled_only:
                items = [x for x in items if bool((x or {}).get("enabled", True))]
            items = items[:limit]
            return json.dumps({"ok": True, "count": len(items), "items": items, "now": now_beijing_iso()}, ensure_ascii=False)

        if name == "schedule_create":
            title = (args.get("title") or "").strip()
            repeat = (args.get("repeat") or "once").strip().lower() or "once"
            datetime_str = (args.get("datetime") or "").strip()
            note = (args.get("note") or "").strip()
            enabled = bool(args.get("enabled", True))
            daily_time = (
                args.get("daily_time")
                or args.get("dailyTime")
                or args.get("time")
                or ""
            )
            weekly_time = (
                args.get("weekly_time")
                or args.get("weeklyTime")
                or args.get("time")
                or ""
            )
            daily_time = str(daily_time).strip()
            weekly_time = str(weekly_time).strip()
            created_by = (args.get("created_by") or "wife").strip().lower() or "wife"
            if created_by not in ("wife", "du"):
                created_by = "wife"
            target_role = (args.get("target_role") or "wife").strip().lower() or "wife"
            if target_role not in ("wife", "du"):
                target_role = "wife"
            weekly_weekday = args.get("weekly_weekday")
            weekly_weekdays = args.get("weekly_weekdays")
            if not title:
                return json.dumps({"ok": False, "error": "title 不能为空"}, ensure_ascii=False)
            if repeat not in ("once", "daily", "weekly"):
                repeat = "once"

            if repeat == "weekly":
                days = []
                if isinstance(weekly_weekdays, list):
                    for x in weekly_weekdays:
                        try:
                            v = int(x)
                        except Exception:
                            continue
                        if 0 <= v <= 6:
                            days.append(v)
                elif weekly_weekday is not None:
                    try:
                        v = int(weekly_weekday)
                        if 0 <= v <= 6:
                            days.append(v)
                    except Exception:
                        pass
                days = sorted(set(days))
                if not days:
                    return json.dumps({"ok": False, "error": "weekly_weekdays 无效（0-6，周一=0）"}, ensure_ascii=False)
                created = []
                for w in days:
                    it = r2_store.create_schedule_item(
                        title=title,
                        datetime_str="",
                        repeat="weekly",
                        note=note,
                        enabled=enabled,
                        weekly_weekday=w,
                        weekly_time=weekly_time,
                        created_by=created_by,
                        target_role=target_role,
                    )
                    if it:
                        created.append(it)
                if not created:
                    return json.dumps({"ok": False, "error": "创建失败"}, ensure_ascii=False)
                _notify_schedule_changed()
                return json.dumps({"ok": True, "count": len(created), "items": created}, ensure_ascii=False)

            item = r2_store.create_schedule_item(
                title=title,
                datetime_str=datetime_str,
                repeat=repeat,
                note=note,
                enabled=enabled,
                daily_time=daily_time,
                weekly_time=weekly_time,
                created_by=created_by,
                target_role=target_role,
            )
            if not item:
                return json.dumps({"ok": False, "error": "创建失败，请检查时间参数"}, ensure_ascii=False)
            _notify_schedule_changed()
            return json.dumps({"ok": True, "item": item}, ensure_ascii=False)

        if name == "schedule_enable":
            iid = (args.get("id") or "").strip()
            if not iid:
                return json.dumps({"ok": False, "error": "id 不能为空"}, ensure_ascii=False)
            ok = r2_store.enable_schedule_item(iid)
            if ok:
                _notify_schedule_changed()
            return json.dumps({"ok": bool(ok), "id": iid, "action": "enable"}, ensure_ascii=False)

        if name == "schedule_disable":
            iid = (args.get("id") or "").strip()
            if not iid:
                return json.dumps({"ok": False, "error": "id 不能为空"}, ensure_ascii=False)
            ok = r2_store.disable_schedule_item(iid)
            if ok:
                _notify_schedule_changed()
            return json.dumps({"ok": bool(ok), "id": iid, "action": "disable"}, ensure_ascii=False)

        if name == "schedule_delete":
            iid = (args.get("id") or "").strip()
            if not iid:
                return json.dumps({"ok": False, "error": "id 不能为空"}, ensure_ascii=False)
            ok = r2_store.delete_schedule_item(iid)
            if ok:
                _notify_schedule_changed()
            return json.dumps({"ok": bool(ok), "id": iid, "action": "delete"}, ensure_ascii=False)

        return json.dumps({"ok": False, "error": f"未知 schedule 工具: {name}"}, ensure_ascii=False)

    if name == "search_memory":
        from services.dynamic_memory_search import execute_search_memory_tool

        return execute_search_memory_tool(args if isinstance(args, dict) else {})

    if name in FORUM_HIGH_LEVEL_TOOLS:
        return json.dumps(_execute_forum_mcp_tool(name, args), ensure_ascii=False)

    if name in {"cli", "get_guide"}:
        return json.dumps(_execute_remote_forum_tool(name, args), ensure_ascii=False)

    if name.startswith("forum_"):
        return json.dumps(
            {"ok": False, "error": f"论坛作者公开 MCP 暂未接这个动作：{name}"},
            ensure_ascii=False,
        )

    return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
