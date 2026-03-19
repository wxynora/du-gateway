from flask import Blueprint, jsonify, request

from config import MCP_ENABLED
from services.mcp_forum_tools import get_forum_tools_for_inject, invoke_forum_http
from utils.log import get_logger
from utils.mcp_auth import enforce_mcp_auth

logger = get_logger(__name__)
bp = Blueprint("mcp_api", __name__, url_prefix="/mcp")


@bp.before_request
def _mcp_guard():
    if not MCP_ENABLED:
        return jsonify({"ok": False, "error": "MCP 未启用"}), 404
    enforce_mcp_auth()


@bp.route("/health", methods=["GET"])
def mcp_health():
    tools = get_forum_tools_for_inject()
    names = [(t.get("function") or {}).get("name") for t in (tools or [])]
    return jsonify({"ok": True, "service": "mcp_api", "tools": [n for n in names if n]})


@bp.route("/tools", methods=["GET"])
def mcp_tools():
    tools = get_forum_tools_for_inject()
    return jsonify(
        {
            "ok": True,
            "tools": [{"name": (t.get("function") or {}).get("name"), "description": (t.get("function") or {}).get("description")} for t in tools],
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
        result, status = invoke_forum_http(method, url, headers, params, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_login":
        from services.mcp_forum_tools import _build_url_from_base
        url = _build_url_from_base(args.get("path") or "", "/api/login")
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        username = (args.get("username") or "").strip()
        password = (args.get("password") or "").strip()
        if not username or not password:
            return jsonify({"ok": False, "error": "缺少 username 或 password"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        body = {"username": username, "password": password}
        result, status = invoke_forum_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_post":
        from services.mcp_forum_tools import _build_url_from_base
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
        result, status = invoke_forum_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_comment":
        post_id = str(args.get("post_id") or "").strip()
        content = (args.get("content") or "").strip()
        if not post_id or not content:
            return jsonify({"ok": False, "error": "缺少 post_id 或 content"}), 400
        from services.mcp_forum_tools import _build_url_from_base, _normalize_path
        template = _normalize_path(args.get("path_template") or "", "/api/posts/{post_id}/comments")
        url = _build_url_from_base(template.replace("{post_id}", post_id), "")
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        auth_token = (args.get("auth_token") or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        body = {"content": content}
        result, status = invoke_forum_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_uid_http":
        uid = (args.get("uid") or "").strip()
        if not uid:
            return jsonify({"ok": False, "error": "uid 不能为空"}), 400
        method = (args.get("method") or "GET").strip().upper()
        url = (args.get("url") or "").strip()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {uid}"
        if not url:
            from services.mcp_forum_tools import _build_url_from_base

            path = (args.get("path") or "").strip()
            if not path:
                return jsonify({"ok": False, "error": "缺少 url 或 path"}), 400
            url = _build_url_from_base(path, path)
        result, status = invoke_forum_http(
            method, url, headers, args.get("params") if isinstance(args.get("params"), dict) else None, args.get("body"), args.get("timeout")
        )
        return jsonify(result), status

    return jsonify({"ok": False, "error": "不支持的 tool，请用 /mcp/tools 查看"}), 400
