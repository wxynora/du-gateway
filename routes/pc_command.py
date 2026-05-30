from flask import Blueprint, jsonify, request

from config import PC_COMMAND_TOKEN
from storage import r2_store
from services import codex_group_chat
from services.pc_command_handler import process_pcmd_in_assistant_text

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


@bp.route("/api/pc_command/assistant", methods=["POST", "OPTIONS"])
def process_pc_command_from_assistant():
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
    text = str(body.get("text") or "")
    visible, queued = process_pcmd_in_assistant_text(text)
    return jsonify({"ok": True, "visible_text": visible, "queued": bool(queued)})


@bp.route("/api/codex_group_chat/tasks/claim", methods=["POST", "OPTIONS"])
def claim_codex_group_chat_task():
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    body = request.get_json(silent=True) or {}
    worker_id = str((body or {}).get("worker_id") or request.headers.get("X-Worker-Id") or "").strip()
    task = codex_group_chat.claim_next(worker_id=worker_id)
    return jsonify({"ok": True, "task": task})


@bp.route("/api/codex_group_chat/tasks/recent", methods=["GET", "OPTIONS"])
def recent_codex_group_chat_tasks():
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    try:
        limit = int(request.args.get("limit") or "20")
    except Exception:
        limit = 20
    return jsonify({"ok": True, "tasks": codex_group_chat.list_tasks(limit=limit)})


@bp.route("/api/codex_group_chat/tasks/<task_id>/finish", methods=["GET", "POST", "OPTIONS"])
def finish_codex_group_chat_task(task_id: str):
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    if request.method == "GET":
        task = codex_group_chat.get_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        return jsonify({"ok": True, "task": task})
    body = request.get_json(silent=True) or {}
    response = str((body or {}).get("response") or "")
    error = str((body or {}).get("error") or "")
    task = codex_group_chat.finish_task(task_id, response=response, error=error)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, "task": task})


@bp.route("/api/codex_group_chat/tasks/<task_id>/cancel", methods=["POST", "OPTIONS"])
def cancel_codex_group_chat_task(task_id: str):
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    body = request.get_json(silent=True) or {}
    reason = str((body or {}).get("reason") or "user_cancelled").strip()
    task = codex_group_chat.cancel_task(task_id, reason=reason)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, "task": task})
