from flask import Blueprint, jsonify, request

from config import (
    MCP_ENABLED,
    MCP_FORUM_DEFAULT_UID,
    MCP_FORUM_VERIFY_UID_PATH,
    MCP_FORUM_VERIFY_UID_METHOD,
    MCP_FORUM_VERIFY_UID_PATHS,
    MCP_FORUM_REGISTER_PATH,
    MCP_FORUM_REGISTER_METHOD,
    MCP_FORUM_POST_LIST_PATH,
    MCP_FORUM_POST_LIST_PATHS,
    MCP_FORUM_POST_DETAIL_PATH_TEMPLATE,
)
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
        from services.mcp_forum_tools import execute_forum_tool
        import json

        out = execute_forum_tool("forum_post", args)
        try:
            payload_obj = json.loads(out)
        except Exception:
            payload_obj = {"ok": False, "error": out}
        return jsonify(payload_obj), 200

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
        if not auth_token:
            auth_token = MCP_FORUM_DEFAULT_UID
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            return jsonify({"ok": False, "error": "缺少 auth_token：请在工具参数传 auth_token，或在 env 配置 MCP_FORUM_DEFAULT_UID"}), 400
        body = {"content": content}
        result, status = invoke_forum_http("POST", url, headers, None, body, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_uid_http":
        uid = (args.get("uid") or "").strip() or MCP_FORUM_DEFAULT_UID
        if not uid:
            return jsonify({"ok": False, "error": "缺少 uid：请在工具参数传 uid，或在 env 配置 MCP_FORUM_DEFAULT_UID"}), 400
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

    if tool == "forum_verify_uid":
        method = (args.get("method") or MCP_FORUM_VERIFY_UID_METHOD).strip().upper()
        from services.mcp_forum_tools import _build_url_from_base

        primary = (args.get("path") or MCP_FORUM_VERIFY_UID_PATH).strip()
        candidates = [primary] + [p for p in (MCP_FORUM_VERIFY_UID_PATHS or []) if p != primary]
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        last = {"ok": False, "status": 404, "error": "未找到 verify-uid 路径"}
        for p in candidates:
            url = _build_url_from_base(p, p)
            if not url:
                continue
            result, status = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
            last = result
            if int(result.get("status") or 0) != 404:
                return jsonify(result), status
        return jsonify(last), 200

    if tool == "forum_register":
        method = (args.get("method") or MCP_FORUM_REGISTER_METHOD).strip().upper()
        from services.mcp_forum_tools import _build_url_from_base

        url = _build_url_from_base(args.get("path") or MCP_FORUM_REGISTER_PATH, MCP_FORUM_REGISTER_PATH)
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        result, status = invoke_forum_http(method, url, headers, None, payload, args.get("timeout"))
        return jsonify(result), status

    if tool == "forum_list_posts":
        from services.mcp_forum_tools import _build_url_from_base

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
        last = {"ok": False, "status": 404, "error": "未找到帖子列表路径"}
        for p in candidates:
            url = _build_url_from_base(p, p)
            if not url:
                continue
            result, status = invoke_forum_http("GET", url, headers, params, None, args.get("timeout"))
            last = result
            if int(result.get("status") or 0) != 404:
                return jsonify(result), status
        return jsonify(last), 200

    if tool == "forum_get_post":
        post_id = str(args.get("post_id") or "").strip()
        if not post_id:
            return jsonify({"ok": False, "error": "缺少 post_id"}), 400
        from services.mcp_forum_tools import _build_url_from_base, _normalize_path

        template = _normalize_path(
            args.get("path_template") or MCP_FORUM_POST_DETAIL_PATH_TEMPLATE,
            MCP_FORUM_POST_DETAIL_PATH_TEMPLATE,
        )
        url = _build_url_from_base(template.replace("{post_id}", post_id), MCP_FORUM_POST_DETAIL_PATH_TEMPLATE)
        if not url:
            return jsonify({"ok": False, "error": "未配置 MCP_FORUM_BASE_URL"}), 400
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {MCP_FORUM_DEFAULT_UID}"
        result, status = invoke_forum_http("GET", url, headers, None, None, args.get("timeout"))
        return jsonify(result), status

    if tool == "schedule_list":
        from services.mcp_forum_tools import execute_forum_tool
        out = execute_forum_tool("schedule_list", args)
        return jsonify({"ok": True, "result": out}), 200

    if tool == "schedule_create":
        from services.mcp_forum_tools import execute_forum_tool
        out = execute_forum_tool("schedule_create", args)
        return jsonify({"ok": True, "result": out}), 200

    if tool == "schedule_enable":
        from services.mcp_forum_tools import execute_forum_tool
        out = execute_forum_tool("schedule_enable", args)
        return jsonify({"ok": True, "result": out}), 200

    if tool == "schedule_disable":
        from services.mcp_forum_tools import execute_forum_tool
        out = execute_forum_tool("schedule_disable", args)
        return jsonify({"ok": True, "result": out}), 200

    if tool == "schedule_delete":
        from services.mcp_forum_tools import execute_forum_tool
        out = execute_forum_tool("schedule_delete", args)
        return jsonify({"ok": True, "result": out}), 200

    return jsonify({"ok": False, "error": "不支持的 tool，请用 /mcp/tools 查看"}), 400
