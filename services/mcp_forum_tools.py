import ipaddress
import json
from urllib.parse import urlparse

import requests

from config import (
    MCP_ENABLED,
    MCP_FORUM_ALLOWED_HOSTS,
    MCP_FORUM_BASE_URL,
    MCP_FORUM_DEFAULT_UID,
    MCP_FORUM_VERIFY_UID_PATH,
    MCP_FORUM_REGISTER_PATH,
    MCP_FORUM_VERIFY_UID_METHOD,
    MCP_FORUM_REGISTER_METHOD,
    MCP_FORUM_VERIFY_UID_PATHS,
    MCP_FORUM_POST_CREATE_PATH,
    MCP_FORUM_POST_LIST_PATH,
    MCP_FORUM_POST_LIST_PATHS,
    MCP_FORUM_POST_DETAIL_PATH_TEMPLATE,
    MCP_FORUM_COMMENT_CREATE_PATH_TEMPLATE,
    MCP_HTTP_MAX_RESPONSE_CHARS,
    MCP_HTTP_MAX_TIMEOUT_SECONDS,
    MCP_HTTP_RETRIES,
    MCP_HTTP_TIMEOUT_SECONDS,
)
from utils.log import get_logger

logger = get_logger(__name__)

TOOL_FORUM_HTTP = {
    "type": "function",
    "function": {
        "name": "forum_http",
        "description": (
            "论坛 HTTP 工具：可调用论坛 API 完成 verify-uid、register、发帖、评论等。"
            "建议只填 path（不要填域名）或保证 url 域名在白名单；若域名不在白名单，会自动尝试用 MCP_FORUM_BASE_URL 替换。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "GET/POST/PUT/DELETE"},
                "url": {"type": "string", "description": "完整 URL，必须是白名单域名"},
                "headers": {"type": "object", "description": "可选请求头"},
                "params": {"type": "object", "description": "可选 query 参数"},
                "body": {"description": "可选请求体（JSON 对象或字符串）"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 20"},
            },
            "required": ["method", "url"],
        },
    },
}

TOOL_FORUM_LOGIN = {
    "type": "function",
    "function": {
        "name": "forum_login",
        "description": (
            "论坛认证（forum_login）：默认调用 verify-uid 接口。\n"
            "你不需要手动输入 uid/auth；会自动使用 MCP_FORUM_DEFAULT_UID 并注入 Bearer。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "可选：默认 MCP_FORUM_VERIFY_UID_PATH"},
                "payload": {"description": "可选请求体（JSON）"},
                "timeout": {"type": "integer"},
                "headers": {"type": "object"},
            },
            "required": [],
        },
    },
}

TOOL_FORUM_POST = {
    "type": "function",
    "function": {
        "name": "forum_post",
        "description": (
            "论坛发帖：默认调用 MCP_FORUM_POST_CREATE_PATH。\n"
            "提醒：你不需要手动输入 auth_token，只要服务器已配置 `MCP_FORUM_DEFAULT_UID`，会自动使用默认 Bearer。\n"
            "发帖时请填写 submolt（板块分类），必须从以下值中选择一个：general/tech/diary/relationship/night_dark。\n"
            "如果你没填，系统会默认使用 general。\n"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "title": {"type": "string", "description": "可选：发帖标题，不传则用默认值"},
                "category_id": {},
                "submolt": {
                    "type": "string",
                    "description": "板块分类（建议必填）：general/tech/diary/relationship/night_dark",
                },
                "path": {"type": "string", "description": "可选：默认 MCP_FORUM_POST_CREATE_PATH"},
                "auth_token": {
                    "type": "string",
                    "description": "Bearer token（不传则使用 MCP_FORUM_DEFAULT_UID）",
                },
                "headers": {"type": "object"},
                "timeout": {"type": "integer"},
            },
            "required": ["content"],
        },
    },
}

TOOL_FORUM_COMMENT = {
    "type": "function",
    "function": {
        "name": "forum_comment",
        "description": (
            "论坛评论：默认调用 MCP_FORUM_COMMENT_CREATE_PATH_TEMPLATE。\n"
            "提醒：你不需要手动输入 auth_token，只要服务器已配置 `MCP_FORUM_DEFAULT_UID`，会自动使用默认 Bearer。\n"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string"},
                "content": {"type": "string"},
                "path_template": {"type": "string", "description": "可选：默认 MCP_FORUM_COMMENT_CREATE_PATH_TEMPLATE"},
                "auth_token": {
                    "type": "string",
                    "description": "Bearer token（不传则使用 MCP_FORUM_DEFAULT_UID）",
                },
                "headers": {"type": "object"},
                "timeout": {"type": "integer"},
            },
            "required": ["post_id", "content"],
        },
    },
}

TOOL_FORUM_DELETE_POST = {
    "type": "function",
    "function": {
        "name": "forum_delete_post",
        "description": (
            "论坛删帖：默认对 MCP_FORUM_POST_DETAIL_PATH_TEMPLATE 对应的帖子详情地址发 DELETE。\n"
            "你只需要传 post_id；如果服务器已配置 `MCP_FORUM_DEFAULT_UID`，会自动带默认 Bearer。\n"
            "如论坛删帖接口不是帖子详情地址，可用 path_template 覆盖，例如 /posts/{post_id} 或 /api/posts/{post_id}。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string", "description": "必填：要删除的帖子 ID"},
                "path_template": {"type": "string", "description": "可选：默认 MCP_FORUM_POST_DETAIL_PATH_TEMPLATE"},
                "auth_token": {
                    "type": "string",
                    "description": "Bearer token（不传则使用 MCP_FORUM_DEFAULT_UID）",
                },
                "headers": {"type": "object"},
                "timeout": {"type": "integer"},
            },
            "required": ["post_id"],
        },
    },
}


TOOL_FORUM_UID_HTTP = {
    "type": "function",
    "function": {
        "name": "forum_uid_http",
        "description": (
            "论坛 UID 鉴权 HTTP 工具（forum_uid_http）：会自动在请求头注入 Authorization: Bearer <uid>。\n"
            "适合用于 verify-uid、register、浏览帖子列表/详情、发帖、评论等需要同一 Bearer 的场景。\n"
            "提醒：你不需要手动输入 uid（以及不需要手动带 Authorization）。只要服务器已配置 `MCP_FORUM_DEFAULT_UID`，会自动使用默认 Bearer。\n"
            "建议只填 path 或正确 url；若 url 域名不在白名单，会自动尝试替换为 MCP_FORUM_BASE_URL 的域名。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "小红书 UID（作为 Bearer token 注入 Authorization；不传则使用 MCP_FORUM_DEFAULT_UID）",
                },
                "method": {"type": "string", "description": "GET/POST/PUT/DELETE"},
                "url": {"type": "string", "description": "完整 URL（可选：与 path 二选一）"},
                "path": {"type": "string", "description": "相对 MCP_FORUM_BASE_URL 的接口路径（可选：与 url 二选一）"},
                "headers": {"type": "object", "description": "可选额外请求头（会保留你传入的 Authorization，但默认会注入）"},
                "params": {"type": "object", "description": "可选 query 参数"},
                "body": {"description": "可选请求体（JSON 对象或字符串）"},
                "timeout": {"type": "integer", "description": "超时秒数"},
            },
            "required": ["method"],
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
    - debug: 全量（含底层 HTTP/鉴权工具）
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
    forum_tools = [
        {
            "type": "function",
            "function": {
                "name": "forum_verify_uid",
                "description": (
                    "verify-uid：确认 UID 对应的成员身份（默认 MCP_FORUM_VERIFY_UID_PATH）。\n"
                    "建议仅在首次接入或出现 401/403 鉴权失败时调用，平时不要每次都调用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "description": "可选：默认 MCP_FORUM_VERIFY_UID_METHOD"},
                        "path": {"type": "string", "description": "可选：默认 MCP_FORUM_VERIFY_UID_PATH"},
                        "payload": {"description": "可选请求体（JSON）"},
                        "headers": {"type": "object"},
                        "timeout": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "forum_register",
                "description": (
                    "register：注册你的账号（默认 MCP_FORUM_REGISTER_PATH）。\n"
                    "建议仅在首次接入或出现 401/403 鉴权失败时调用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "description": "可选：默认 MCP_FORUM_REGISTER_METHOD"},
                        "path": {"type": "string", "description": "可选：默认 MCP_FORUM_REGISTER_PATH"},
                        "payload": {"description": "可选请求体（JSON）"},
                        "headers": {"type": "object"},
                        "timeout": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "forum_list_posts",
                "description": (
                    "浏览帖子列表（默认 GET + MCP_FORUM_POST_LIST_PATH）。不需要手动输入 uid/auth。\n"
                    "建议优先调用这个工具；只有返回 401/403 时再调用 verify/register。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                        "offset": {"type": "integer"},
                        "path": {"type": "string", "description": "可选：默认 MCP_FORUM_POST_LIST_PATH"},
                        "headers": {"type": "object"},
                        "timeout": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "forum_get_post",
                "description": (
                    "浏览帖子详情（GET + MCP_FORUM_POST_DETAIL_PATH_TEMPLATE，需要 post_id）。不需要手动输入 uid/auth。\n"
                    "建议优先调用；只有返回 401/403 时再调用 verify/register。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "post_id": {"type": "string"},
                        "path_template": {"type": "string", "description": "可选：默认 MCP_FORUM_POST_DETAIL_PATH_TEMPLATE"},
                        "headers": {"type": "object"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["post_id"],
                },
            },
        },
    ]
    # forum 场景：只给高频论坛工具，不给底层易混淆工具
    high_level = [
        t for t in forum_tools
        if ((t.get("function") or {}).get("name") in ("forum_list_posts", "forum_get_post"))
    ] + [TOOL_FORUM_POST, TOOL_FORUM_COMMENT, TOOL_FORUM_DELETE_POST]
    if mode == "forum":
        return schedule_tools + high_level + [TOOL_SEARCH_MEMORY]
    # debug 场景：全量工具
    return [
        TOOL_FORUM_HTTP,
        TOOL_FORUM_UID_HTTP,
        TOOL_FORUM_LOGIN,
        *forum_tools,
        TOOL_FORUM_POST,
        TOOL_FORUM_COMMENT,
        TOOL_FORUM_DELETE_POST,
        *schedule_tools,
        TOOL_SEARCH_MEMORY,
    ]


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    remain = len(text) - max_chars
    return text[:max_chars] + f"\n\n[truncated: {remain} chars]", True


def _host_allowed(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host or host == "localhost":
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass
    # 如果 MCP_FORUM_ALLOWED_HOSTS 没配全，则至少允许 MCP_FORUM_BASE_URL 对应的 hostname
    if not MCP_FORUM_ALLOWED_HOSTS:
        base = (MCP_FORUM_BASE_URL or "").strip()
        if base:
            bh = (urlparse(base).hostname or "").strip().lower()
            if bh:
                return host == bh
        return False
    return host in set(MCP_FORUM_ALLOWED_HOSTS)


def _normalize_path(path: str, default_path: str) -> str:
    p = (path or "").strip() or default_path
    if not p.startswith("/"):
        p = "/" + p
    return p


def _build_url_from_base(path: str, default_path: str) -> str:
    base = (MCP_FORUM_BASE_URL or "").strip().rstrip("/")
    if not base:
        return ""
    return base + _normalize_path(path, default_path)


def invoke_forum_http(method: str, url: str, headers: dict | None, params: dict | None, body, timeout_override=None) -> tuple[dict, int]:
    method = (method or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return {"ok": False, "error": "method 仅支持 GET/POST/PUT/DELETE"}, 400
    if not url:
        return {"ok": False, "error": "缺少 url"}, 400
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return {"ok": False, "error": "url 仅支持 http/https"}, 400
    # 若 AI 提供了错误域名（但 path/query 正确），可自动替换成 MCP_FORUM_BASE_URL 的域名
    if not _host_allowed(u.hostname or ""):
        base = (MCP_FORUM_BASE_URL or "").strip()
        if base:
            bu = urlparse(base)
            if bu.scheme in ("http", "https") and _host_allowed(bu.hostname or ""):
                normalized_url = f"{bu.scheme}://{bu.netloc}{u.path or ''}"
                if u.query:
                    normalized_url += f"?{u.query}"
                url = normalized_url
                u = urlparse(url)

    timeout = int(timeout_override or MCP_HTTP_TIMEOUT_SECONDS)
    timeout = max(1, min(timeout, MCP_HTTP_MAX_TIMEOUT_SECONDS))
    retries = max(0, int(MCP_HTTP_RETRIES))
    max_chars = max(200, int(MCP_HTTP_MAX_RESPONSE_CHARS))
    safe_headers = {k: v for k, v in (headers or {}).items() if str(k).lower() not in ("x-mcp-token",)}

    last_error = ""
    requested_url = url
    method_used = method
    for attempt in range(retries + 1):
        try:
            kwargs = {
                "method": method,
                "url": url,
                "headers": safe_headers,
                "params": params,
                "timeout": timeout,
            }
            if method in ("POST", "PUT", "DELETE"):
                if isinstance(body, dict):
                    kwargs["json"] = body
                elif body is not None:
                    kwargs["data"] = str(body)
            resp = requests.request(**kwargs)
            # 常见接口方法不匹配：自动在 GET/POST 间切换一次（405 -> retry）
            if resp.status_code == 405 and method in ("GET", "POST"):
                alt_method = "POST" if method == "GET" else "GET"
                kwargs["method"] = alt_method
                method_used = alt_method
                if alt_method == "GET":
                    # GET 时避免带 json/data
                    kwargs.pop("json", None)
                    kwargs.pop("data", None)
                resp = requests.request(**kwargs)
            try:
                data = resp.json()
                is_json = True
            except Exception:
                data = None
                is_json = False

            out = {
                "ok": 200 <= resp.status_code < 300,
                "status": resp.status_code,
                "headers": {"content_type": resp.headers.get("Content-Type", "")},
                "truncated": False,
                "request": {
                    "method": method_used,
                    "url": kwargs.get("url") or requested_url,
                },
            }
            if is_json:
                out["data"] = data
            else:
                text, truncated = _truncate_text(resp.text or "", max_chars)
                out["text"] = text
                out["truncated"] = truncated
            if not out["ok"]:
                logger.warning(
                    "forum_http 返回非2xx method=%s url=%s status=%s",
                    out["request"]["method"],
                    out["request"]["url"],
                    out["status"],
                )
            else:
                logger.info(
                    "forum_http 请求成功 method=%s url=%s status=%s",
                    out["request"]["method"],
                    out["request"]["url"],
                    out["status"],
                )
            return out, 200
        except requests.RequestException as e:
            last_error = str(e)
            if attempt >= retries:
                logger.warning("forum_http 调用失败 method=%s url=%s error=%s", method, url[:120], last_error)
                return {"ok": False, "error": f"请求失败: {last_error}"}, 502
    return {"ok": False, "error": last_error or "未知错误"}, 502


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

    if name == "forum_http":
        result, _ = invoke_forum_http(
            method=(args.get("method") or "GET"),
            url=(args.get("url") or "").strip(),
            headers=args.get("headers") if isinstance(args.get("headers"), dict) else {},
            params=args.get("params") if isinstance(args.get("params"), dict) else None,
            body=args.get("body"),
            timeout_override=args.get("timeout"),
        )
        return json.dumps(result, ensure_ascii=False)

    if name == "search_memory":
        from services.dynamic_memory_search import execute_search_memory_tool

        return execute_search_memory_tool(args if isinstance(args, dict) else {})

    if name == "forum_login":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_VERIFY_UID_PATH, MCP_FORUM_VERIFY_UID_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        method = (args.get("method") or MCP_FORUM_VERIFY_UID_METHOD).strip().upper()
        result, _ = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_post":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_POST_CREATE_PATH, MCP_FORUM_POST_CREATE_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        title = (args.get("title") or "报到帖").strip()
        content = (args.get("content") or "").strip()
        submolt = (args.get("submolt") or "").strip().lower()
        allowed_submolt = {"general", "tech", "diary", "relationship", "night_dark"}
        if not content:
            return "content 不能为空"
        if not submolt:
            submolt = "general"
        if submolt not in allowed_submolt:
            return "submolt 无效，请填写：general/tech/diary/relationship/night_dark"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if not auth_token:
            auth_token = MCP_FORUM_DEFAULT_UID
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            return "缺少 auth_token：请在工具参数传 auth_token，或在 env 配置 MCP_FORUM_DEFAULT_UID"
        if "Content-Type" not in headers and "content-type" not in headers:
            headers["Content-Type"] = "application/json"
        core_payload = {
            "title": title or "报到帖",
            "content": content,
            "submolt": submolt,
            "text": content,
            "body": content,
            "type": "text",
            "post_type": "text",
            "postType": "text",
            "content_type": "text",
            "contentType": "text",
            "format": "markdown",
            "visibility": "public",
        }
        if args.get("category_id") is not None:
            cid = args.get("category_id")
            core_payload["category_id"] = cid
            core_payload["categoryId"] = cid
            core_payload["category"] = cid

        def _is_js_undefined_error(res: dict) -> bool:
            text = str((res or {}).get("text") or "").lower()
            try:
                data_text = json.dumps((res or {}).get("data") or {}, ensure_ascii=False).lower()
            except Exception:
                data_text = ""
            return (
                ("tolowercase" in text)
                or ("cannot read properties of undefined" in text)
                or ("tolowercase" in data_text)
                or ("cannot read properties of undefined" in data_text)
            )

        # 多种常见后端入参结构自动兜底，避免上游按固定结构取值时报 undefined.toLowerCase
        attempt_bodies = [
            core_payload,
            {"data": core_payload},
            {"post": core_payload},
            {"input": core_payload},
            {
                "title": core_payload["title"],
                "content": core_payload["content"],
                "submolt": submolt,
                "type": "text",
            },
        ]
        attempts_meta = []
        final_result = {"ok": False, "error": "forum_post 未执行"}
        for idx, one_body in enumerate(attempt_bodies):
            result, _ = invoke_forum_http("POST", url, headers, None, one_body, args.get("timeout"))
            final_result = result
            attempts_meta.append({"attempt": idx + 1, "keys": list(one_body.keys())})
            if bool(result.get("ok")):
                final_result["fallback_used"] = idx > 0
                if idx > 0:
                    final_result["attempts_tried"] = attempts_meta
                return json.dumps(final_result, ensure_ascii=False)
            if not _is_js_undefined_error(result):
                # 不是 undefined.toLowerCase 类错误，直接返回首个真实错误，避免无意义重试
                if idx == 0:
                    return json.dumps(result, ensure_ascii=False)
                break

        if isinstance(final_result, dict):
            final_result["fallback_used"] = True
            final_result["attempts_tried"] = attempts_meta
        return json.dumps(final_result, ensure_ascii=False)

    if name == "forum_comment":
        post_id = str(args.get("post_id") or "").strip()
        content = (args.get("content") or "").strip()
        if not post_id or not content:
            return "缺少 post_id 或 content"
        template = _normalize_path(
            args.get("path_template") or MCP_FORUM_COMMENT_CREATE_PATH_TEMPLATE,
            MCP_FORUM_COMMENT_CREATE_PATH_TEMPLATE,
        )
        url = _build_url_from_base(template.replace("{post_id}", post_id), MCP_FORUM_COMMENT_CREATE_PATH_TEMPLATE)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if not auth_token:
            auth_token = MCP_FORUM_DEFAULT_UID
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            return "缺少 auth_token：请在工具参数传 auth_token，或在 env 配置 MCP_FORUM_DEFAULT_UID"
        result, _ = invoke_forum_http("POST", url, headers, None, {"content": content}, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_delete_post":
        post_id = str(args.get("post_id") or "").strip()
        if not post_id:
            return "post_id 不能为空"
        template = _normalize_path(
            args.get("path_template") or MCP_FORUM_POST_DETAIL_PATH_TEMPLATE,
            MCP_FORUM_POST_DETAIL_PATH_TEMPLATE,
        )
        url = _build_url_from_base(template.replace("{post_id}", post_id), MCP_FORUM_POST_DETAIL_PATH_TEMPLATE)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if not auth_token:
            auth_token = MCP_FORUM_DEFAULT_UID
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            return "缺少 auth_token：请在工具参数传 auth_token，或在 env 配置 MCP_FORUM_DEFAULT_UID"
        result, _ = invoke_forum_http("DELETE", url, headers, None, None, args.get("timeout"))
        if isinstance(result, dict):
            result.setdefault("post_id", post_id)
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_uid_http":
        uid = (args.get("uid") or "").strip() or MCP_FORUM_DEFAULT_UID
        if not uid:
            return "缺少 uid：请在工具参数传 uid，或在 env 配置 MCP_FORUM_DEFAULT_UID"
        method = (args.get("method") or "GET").strip().upper()
        url = (args.get("url") or "").strip()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        # 若你没传 Authorization，就用 uid 作为 Bearer
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {uid}"
        if not url:
            path = (args.get("path") or "").strip()
            if not path:
                return "缺少 url 或 path"
            url = _build_url_from_base(path, path)
        result, _ = invoke_forum_http(
            method=method,
            url=url,
            headers=headers,
            params=args.get("params") if isinstance(args.get("params"), dict) else None,
            body=args.get("body"),
            timeout_override=args.get("timeout"),
        )
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_verify_uid":
        # 先用主路径，再按候选路径自动探测，减少 404
        primary = (args.get("path") or MCP_FORUM_VERIFY_UID_PATH).strip()
        candidates = [primary] + [p for p in (MCP_FORUM_VERIFY_UID_PATHS or []) if p != primary]
        method = (args.get("method") or MCP_FORUM_VERIFY_UID_METHOD).strip().upper()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        attempted = []
        last = {"ok": False, "status": 404, "error": "未找到 verify-uid 路径"}
        for p in candidates:
            url = _build_url_from_base(p, p)
            if not url:
                continue
            attempted.append({"path": p, "url": url, "method": method})
            result, _ = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
            last = result
            if int(result.get("status") or 0) != 404:
                return json.dumps(result, ensure_ascii=False)
        last["probe_paths"] = attempted
        return json.dumps(last, ensure_ascii=False)

    if name == "forum_register":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_REGISTER_PATH, MCP_FORUM_REGISTER_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        method = (args.get("method") or MCP_FORUM_REGISTER_METHOD).strip().upper()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        result, _ = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_list_posts":
        primary = (args.get("path") or MCP_FORUM_POST_LIST_PATH).strip()
        candidates = [primary] + [p for p in (MCP_FORUM_POST_LIST_PATHS or []) if p != primary]
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        params = {}
        if args.get("limit") is not None:
            params["limit"] = args.get("limit")
        if args.get("offset") is not None:
            params["offset"] = args.get("offset")
        params = params or None
        attempted = []
        last = {"ok": False, "status": 404, "error": "未找到帖子列表路径"}
        for p in candidates:
            url = _build_url_from_base(p, p)
            if not url:
                continue
            attempted.append({"path": p, "url": url, "method": "GET"})
            result, _ = invoke_forum_http("GET", url, headers, params, None, args.get("timeout"))
            last = result
            if int(result.get("status") or 0) != 404:
                return json.dumps(result, ensure_ascii=False)
        last["probe_paths"] = attempted
        return json.dumps(last, ensure_ascii=False)

    if name == "forum_get_post":
        post_id = str(args.get("post_id") or "").strip()
        if not post_id:
            return "post_id 不能为空"
        template = (args.get("path_template") or MCP_FORUM_POST_DETAIL_PATH_TEMPLATE).strip()
        template = _normalize_path(template, MCP_FORUM_POST_DETAIL_PATH_TEMPLATE)
        url = _build_url_from_base(template.replace("{post_id}", post_id), MCP_FORUM_POST_DETAIL_PATH_TEMPLATE)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        result, _ = invoke_forum_http("GET", url, headers, None, None, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({"ok": False, "error": f"未知论坛工具: {name}"}, ensure_ascii=False)
