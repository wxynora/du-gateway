from flask import Blueprint, jsonify, request

from config import PC_COMMAND_TOKEN
from storage import r2_store

bp = Blueprint("pc_command", __name__)


def _require_pc_token():
    """校验电脑端 token（单设备轮询/回执使用）。"""
    if not PC_COMMAND_TOKEN:
        return jsonify({"ok": False, "error": "PC_COMMAND_TOKEN 未配置"}), 503
    token = (request.headers.get("X-PC-Token") or "").strip()
    if token != PC_COMMAND_TOKEN:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return None


@bp.route("/api/pc_command", methods=["POST", "OPTIONS"])
def create_pc_command():
    if request.method == "OPTIONS":
        return "", 204
    # 入队接口也使用 token，避免被外部误调用
    token_err = _require_pc_token()
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
    item = r2_store.append_pc_command(cmd)
    if not item:
        return jsonify({"ok": False, "error": "入队失败"}), 503
    return jsonify({"ok": True, "item": item})


@bp.route("/api/pc_command", methods=["GET"])
def list_pc_commands():
    token_err = _require_pc_token()
    if token_err:
        return token_err
    queue = r2_store.get_pc_command_queue()
    return jsonify(queue)


@bp.route("/api/pc_command/done", methods=["POST", "OPTIONS"])
def done_pc_commands():
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400
    done_ids = body.get("doneIds")
    if not isinstance(done_ids, list):
        return jsonify({"ok": False, "error": "doneIds 必须是数组"}), 400
    removed = r2_store.mark_pc_commands_done(done_ids)
    return jsonify({"ok": True, "removedCount": int(removed)})
