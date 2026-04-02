from flask import Blueprint, jsonify, request

from config import MOBILE_COMMAND_TOKEN
from storage import r2_store

bp = Blueprint("mobile_command", __name__)


def _require_mobile_token():
    """校验手机端 token（X-Mobile-Token header）。"""
    if not MOBILE_COMMAND_TOKEN:
        return jsonify({"ok": False, "error": "MOBILE_COMMAND_TOKEN 未配置"}), 503
    token = (request.headers.get("X-Mobile-Token") or "").strip()
    if token != MOBILE_COMMAND_TOKEN:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return None


def _require_mobile_or_mcp_token():
    """校验 X-Mobile-Token 或 MCP Bearer token（POST/status 给 MCP 工具用）。"""
    if not MOBILE_COMMAND_TOKEN:
        return jsonify({"ok": False, "error": "MOBILE_COMMAND_TOKEN 未配置"}), 503
    # 先试 X-Mobile-Token（Tasker 用）
    mobile_token = (request.headers.get("X-Mobile-Token") or "").strip()
    if mobile_token == MOBILE_COMMAND_TOKEN:
        return None
    # 再试 MCP auth
    try:
        from utils.mcp_auth import enforce_mcp_auth
        enforce_mcp_auth()
        return None
    except Exception:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401


@bp.route("/api/mobile_command", methods=["POST", "OPTIONS"])
def create_mobile_command():
    """入队手机命令（MCP 工具调用）。"""
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_mobile_or_mcp_token()
    if token_err:
        return token_err
    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400

    cmd = (body.get("cmd") or "").strip()
    if not cmd:
        return jsonify({"ok": False, "error": "缺少 cmd"}), 400

    payload = body.get("payload") or {}
    expires_in_sec = body.get("expires_in_sec", 300)
    idempotency_key = (body.get("idempotency_key") or "").strip()
    if not idempotency_key:
        return jsonify({"ok": False, "error": "idempotency_key 必填"}), 400

    item, err = r2_store.append_mobile_command(
        cmd=cmd,
        payload=payload,
        expires_in_sec=expires_in_sec,
        idempotency_key=idempotency_key,
    )
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "id": item.get("id", ""),
                     "expires_at": item.get("expires_at", ""),
                     "duplicate": item.get("duplicate", False)})


@bp.route("/api/mobile_command", methods=["GET"])
def poll_mobile_commands():
    """Tasker 轮询拉取待执行命令。"""
    token_err = _require_mobile_token()
    if token_err:
        return token_err
    result = r2_store.poll_mobile_commands()
    return jsonify(result)


@bp.route("/api/mobile_command/done", methods=["POST", "OPTIONS"])
def done_mobile_commands():
    """Tasker 回执已执行/失败的命令。"""
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_mobile_token()
    if token_err:
        return token_err
    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400
    results = body.get("results")
    if not isinstance(results, list):
        return jsonify({"ok": False, "error": "results 必须是数组"}), 400
    result = r2_store.report_mobile_commands(results)
    return jsonify(result)


@bp.route("/api/mobile_command/status", methods=["GET"])
def mobile_command_status():
    """查询命令执行状态（MCP check_phone_command 使用）。"""
    token_err = _require_mobile_or_mcp_token()
    if token_err:
        return token_err
    command_id = (request.args.get("command_id") or "").strip()
    limit = min(int(request.args.get("limit", 10)), 50)
    offset = max(int(request.args.get("offset", 0)), 0)
    result = r2_store.get_mobile_command_status(command_id=command_id, limit=limit, offset=offset)
    return jsonify(result)
