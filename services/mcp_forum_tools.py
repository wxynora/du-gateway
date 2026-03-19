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
    MCP_FORUM_POST_CREATE_PATH,
    MCP_FORUM_POST_LIST_PATH,
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
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "title": {"type": "string", "description": "可选：发帖标题，不传则用默认值"},
                "category_id": {},
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


def get_forum_tools_for_inject() -> list[dict]:
    """返回给模型的论坛工具列表。"""
    if not MCP_ENABLED:
        return []
    # 与你提供的流程一致：verify-uid -> register -> 发报到帖 -> 浏览帖子
    return [
        TOOL_FORUM_HTTP,
        TOOL_FORUM_UID_HTTP,
        TOOL_FORUM_LOGIN,
        {
            "type": "function",
            "function": {
                "name": "forum_verify_uid",
                "description": "verify-uid：确认 UID 对应的成员身份（默认 POST + MCP_FORUM_VERIFY_UID_PATH）。不需要手动输入 uid/auth。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "description": "可选：默认 POST"},
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
                "description": "register：注册你的账号（默认 POST + MCP_FORUM_REGISTER_PATH）。不需要手动输入 uid/auth。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "description": "可选：默认 POST"},
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
                "description": "浏览帖子列表（默认 GET + MCP_FORUM_POST_LIST_PATH）。不需要手动输入 uid/auth。",
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
                "description": "浏览帖子详情（GET + MCP_FORUM_POST_DETAIL_PATH_TEMPLATE，需要 post_id）。不需要手动输入 uid/auth。",
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
        TOOL_FORUM_POST,
        TOOL_FORUM_COMMENT,
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
            }
            if is_json:
                out["data"] = data
            else:
                text, truncated = _truncate_text(resp.text or "", max_chars)
                out["text"] = text
                out["truncated"] = truncated
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

    if name == "forum_login":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_VERIFY_UID_PATH, MCP_FORUM_VERIFY_UID_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        result, _ = invoke_forum_http("POST", url, headers, None, payload, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_post":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_POST_CREATE_PATH, MCP_FORUM_POST_CREATE_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        title = (args.get("title") or "报到帖").strip()
        content = (args.get("content") or "").strip()
        if not content:
            return "content 不能为空"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if not auth_token:
            auth_token = MCP_FORUM_DEFAULT_UID
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            return "缺少 auth_token：请在工具参数传 auth_token，或在 env 配置 MCP_FORUM_DEFAULT_UID"
        body = {"title": title, "content": content}
        if args.get("category_id") is not None:
            body["category_id"] = args.get("category_id")
        result, _ = invoke_forum_http("POST", url, headers, None, body, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

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
        url = _build_url_from_base(args.get("path") or MCP_FORUM_VERIFY_UID_PATH, MCP_FORUM_VERIFY_UID_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        method = (args.get("method") or "POST").strip().upper()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        result, _ = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_register":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_REGISTER_PATH, MCP_FORUM_REGISTER_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        method = (args.get("method") or "POST").strip().upper()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        result, _ = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

    if name == "forum_list_posts":
        url = _build_url_from_base(args.get("path") or MCP_FORUM_POST_LIST_PATH, MCP_FORUM_POST_LIST_PATH)
        if not url:
            return "未配置 MCP_FORUM_BASE_URL"
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        params = {}
        if args.get("limit") is not None:
            params["limit"] = args.get("limit")
        if args.get("offset") is not None:
            params["offset"] = args.get("offset")
        params = params or None
        result, _ = invoke_forum_http("GET", url, headers, params, None, args.get("timeout"))
        return json.dumps(result, ensure_ascii=False)

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
