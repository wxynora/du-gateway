import json

from flask import Blueprint, jsonify, request

from config import MCP_ENABLED
from services.mcp_forum_tools import execute_forum_tool, get_forum_tools_for_inject
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
    tools = get_forum_tools_for_inject()
    supported = {
        str((t.get("function") or {}).get("name") or "").strip()
        for t in (tools or [])
        if isinstance(t, dict)
    }
    supported = {name for name in supported if name}
    if tool not in supported:
        return jsonify({"ok": False, "error": "不支持的 tool，请用 /mcp/tools 查看"}), 400

    out = execute_forum_tool(tool, args if isinstance(args, dict) else {})
    try:
        payload_obj = json.loads(out)
    except Exception:
        payload_obj = {"ok": True, "result": out}
    return jsonify(payload_obj), 200
