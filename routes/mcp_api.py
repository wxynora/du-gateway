import ipaddress
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request

from config import (
    MCP_ENABLED,
    MCP_FORUM_ALLOWED_HOSTS,
    MCP_FORUM_BASE_URL,
    MCP_HTTP_MAX_RESPONSE_CHARS,
    MCP_HTTP_MAX_TIMEOUT_SECONDS,
    MCP_HTTP_RETRIES,
    MCP_HTTP_TIMEOUT_SECONDS,
)
from utils.log import get_logger
from utils.mcp_auth import enforce_mcp_auth

logger = get_logger(__name__)
bp = Blueprint("mcp_api", __name__, url_prefix="/mcp")


TOOL_DESCRIPTION = """论坛 HTTP 工具（forum_http）

用途：
- 访问论坛相关 HTTP 接口，完成注册、登录、发帖、评论、点赞、查询帖子等操作。
- 这是 AI 与论坛交互的主要通道。

可执行操作：
- GET/POST/PUT/DELETE 请求
- 发送 JSON 或表单
- 携带认证头（如 Authorization/Cookie）
- 读取并返回接口响应（优先 JSON）

使用约束：
- 仅允许访问论坛白名单域名（禁止任意外网）
- 默认超时 20 秒，最大 60 秒
- 默认最多重试 2 次（仅网络错误或 5xx）
- 响应内容超过上限会截断并标注
- 禁止访问本机/内网地址（127.0.0.1、localhost、10.x、172.16-31.x、192.168.x）

参数：
- method: HTTP 方法（GET/POST/PUT/DELETE）
- url: 完整接口地址（必须在白名单域名内）
- headers: 可选，请求头
- params: 可选，Query 参数
- body: 可选，请求体（JSON 对象或字符串）
- timeout: 可选，秒，默认 20

返回：
- status: HTTP 状态码
- ok: 是否成功（2xx）
- data: JSON 响应（可解析时）
- text: 文本响应（非 JSON 时）
- error: 错误信息（失败时）
"""

TOOL_PRESET_LOGIN = """论坛登录工具（forum_login）

用途：
- 使用论坛账号密码调用登录接口，拿到会话信息（如 token/cookie）。

参数：
- username: 用户名
- password: 密码
- path: 登录接口路径（默认 /api/login）
- timeout: 可选，秒
- headers: 可选，额外请求头

说明：
- 该工具会自动使用 MCP_FORUM_BASE_URL 拼接请求地址。
- 仅能访问白名单域名。
"""

TOOL_PRESET_POST = """论坛发帖工具（forum_post）

用途：
- 通过论坛接口发布帖子。

参数：
- title: 帖子标题
- content: 帖子内容
- category_id: 可选，分区 ID
- path: 发帖接口路径（默认 /api/posts）
- auth_token: 可选，Bearer token（会自动注入 Authorization）
- headers: 可选，额外请求头
- timeout: 可选，秒
"""

TOOL_PRESET_COMMENT = """论坛评论工具（forum_comment）

用途：
- 给指定帖子发表评论。

参数：
- post_id: 帖子 ID（必填）
- content: 评论内容（必填）
- path_template: 评论路径模板（默认 /api/posts/{post_id}/comments）
- auth_token: 可选，Bearer token
- headers: 可选，额外请求头
- timeout: 可选，秒
"""


@bp.before_request
def _mcp_guard():
    if not MCP_ENABLED:
        return jsonify({"ok": False, "error": "MCP 未启用"}), 404
    enforce_mcp_auth()


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _host_allowed(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host in ("localhost",):
        return False

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass

    if not MCP_FORUM_ALLOWED_HOSTS:
        return False
    return host in set(MCP_FORUM_ALLOWED_HOSTS)


def _try_parse_json(r: requests.Response):
    try:
        return r.json(), True
    except Exception:
        return None, False


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


def _invoke_http(method: str, url: str, headers: dict, params: dict | None, body, timeout_override=None):
    method = (method or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return {"ok": False, "error": "method 仅支持 GET/POST/PUT/DELETE"}, 400
    if not url:
        return {"ok": False, "error": "缺少 url"}, 400

    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return {"ok": False, "error": "url 仅支持 http/https"}, 400
    if not _host_allowed(u.hostname or ""):
        return {"ok": False, "error": "目标域名不在白名单或属于内网地址"}, 403

    timeout = int(timeout_override or MCP_HTTP_TIMEOUT_SECONDS)
    timeout = max(1, min(timeout, MCP_HTTP_MAX_TIMEOUT_SECONDS))
    retries = max(0, int(MCP_HTTP_RETRIES))
    max_chars = max(200, int(MCP_HTTP_MAX_RESPONSE_CHARS))
    safe_headers = {k: v for k, v in (headers or {}).items() if str(k).lower() not in ("x-mcp-token",)}

    last_error = ""
    for attempt in range(retries + 1):
        try:
            req_kwargs = {
                "method": method,
                "url": url,
                "headers": safe_headers,
                "params": params,
                "timeout": timeout,
            }
            if method in ("POST", "PUT", "DELETE"):
                if isinstance(body, dict):
                    req_kwargs["json"] = body
                elif body is not None:
                    req_kwargs["data"] = str(body)
            resp = requests.request(**req_kwargs)
            data, is_json = _try_parse_json(resp)
            text = ""
            truncated = False
            if not is_json:
                text, truncated = _truncate_text(resp.text or "", max_chars)
            result = {
                "ok": 200 <= resp.status_code < 300,
                "status": resp.status_code,
                "headers": {"content_type": resp.headers.get("Content-Type", "")},
                "truncated": truncated,
            }
            if is_json:
                result["data"] = data
            else:
                result["text"] = text
            return result, 200
        except requests.RequestException as e:
            last_error = str(e)
            if attempt >= retries:
                logger.warning("forum_http 调用失败 method=%s url=%s error=%s", method, url[:120], last_error)
                return {"ok": False, "error": f"请求失败: {last_error}"}, 502
    return {"ok": False, "error": last_error or "未知错误"}, 502


@bp.route("/health", methods=["GET"])
def mcp_health():
    return jsonify({"ok": True, "service": "mcp_api", "tools": ["forum_http", "forum_login", "forum_post", "forum_comment"]})


@bp.route("/tools", methods=["GET"])
def mcp_tools():
    return jsonify(
        {
            "ok": True,
            "tools": [
                {
                    "name": "forum_http",
                    "description": TOOL_DESCRIPTION.strip(),
                },
                {"name": "forum_login", "description": TOOL_PRESET_LOGIN.strip()},
                {"name": "forum_post", "description": TOOL_PRESET_POST.strip()},
                {"name": "forum_comment", "description": TOOL_PRESET_COMMENT.strip()},
            ],
        }
    )


@bp.route("/invoke", methods=["POST"])
def mcp_invoke():
    payload = request.get_json(silent=True) or {}
    tool = (payload.get("tool") or "").strip()

    args = payload.get("args") or {}
    if tool == "forum_http":
        method = (args.get("method") or "GET").strip().upper()
        url = (args.get("url") or "").strip()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        params = args.get("params") if isinstance(args.get("params"), dict) else None
        body = args.get("body")
        result, status = _invoke_http(method, url, headers, params, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_login":
        url = _build_url_from_base(args.get("path") or "", "/api/login")
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        username = (args.get("username") or "").strip()
        password = (args.get("password") or "").strip()
        if not username or not password:
            return jsonify({"ok": False, "error": "缺少 username 或 password"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        body = {"username": username, "password": password}
        result, status = _invoke_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_post":
        url = _build_url_from_base(args.get("path") or "", "/api/posts")
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        title = (args.get("title") or "").strip()
        content = (args.get("content") or "").strip()
        if not title or not content:
            return jsonify({"ok": False, "error": "缺少 title 或 content"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        body = {"title": title, "content": content}
        if args.get("category_id") is not None:
            body["category_id"] = args.get("category_id")
        result, status = _invoke_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_comment":
        post_id = str(args.get("post_id") or "").strip()
        content = (args.get("content") or "").strip()
        if not post_id or not content:
            return jsonify({"ok": False, "error": "缺少 post_id 或 content"}), 400
        template = _normalize_path(args.get("path_template") or "", "/api/posts/{post_id}/comments")
        url = _build_url_from_base(template.replace("{post_id}", post_id), "")
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        body = {"content": content}
        result, status = _invoke_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    return jsonify({"ok": False, "error": "不支持的 tool，请用 /mcp/tools 查看"}), 400
