import os
import time

from flask import Blueprint, jsonify, request

from config import PC_COMMAND_TOKEN
from storage import r2_store
from services import codex_group_chat
from services.pc_command_handler import process_pcmd_in_assistant_text

bp = Blueprint("pc_command", __name__)


def _bounded_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        n = float(value if value is not None and value != "" else default)
    except Exception:
        n = default
    if n < minimum:
        return minimum
    if n > maximum:
        return maximum
    return n


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
    if not isinstance(body, dict):
        body = {}
    worker_id = str((body or {}).get("worker_id") or request.headers.get("X-Worker-Id") or "").strip()
    worker_meta = {
        "version": (body or {}).get("worker_version"),
        "status": (body or {}).get("worker_status"),
        "last_error": (body or {}).get("last_error"),
        "gateway_url": (body or {}).get("gateway_url"),
        "outbox_count": (body or {}).get("outbox_count"),
    }
    wait_raw = body.get("wait_seconds")
    if wait_raw is None:
        wait_raw = request.args.get("wait_seconds")
    if wait_raw is None:
        wait_raw = os.environ.get("CODEX_GROUP_CHAT_SERVER_CLAIM_WAIT_SECONDS", "0")
    wait_seconds = _bounded_float(wait_raw, 0.0, 0.0, 25.0)
    poll_seconds = _bounded_float(os.environ.get("CODEX_GROUP_CHAT_SERVER_CLAIM_POLL_SECONDS"), 0.75, 0.2, 2.0)
    deadline = time.monotonic() + wait_seconds
    record_worker = True
    task = None
    while True:
        task = codex_group_chat.claim_next(worker_id=worker_id, worker_meta=worker_meta, record_worker=record_worker)
        if task or wait_seconds <= 0 or time.monotonic() >= deadline:
            break
        record_worker = False
        time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))
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


@bp.route("/api/codex_group_chat/workers/status", methods=["GET", "OPTIONS"])
def codex_group_chat_worker_status():
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    try:
        limit = int(request.args.get("limit") or "20")
    except Exception:
        limit = 20
    return jsonify({"ok": True, "workers": codex_group_chat.list_workers(limit=limit)})


@bp.route("/api/codex_group_chat/tasks/<task_id>/heartbeat", methods=["POST", "OPTIONS"])
def heartbeat_codex_group_chat_task(task_id: str):
    if request.method == "OPTIONS":
        return "", 204
    token_err = _require_pc_token()
    if token_err:
        return token_err
    body = request.get_json(silent=True) or {}
    worker_id = str((body or {}).get("worker_id") or request.headers.get("X-Worker-Id") or "").strip()
    worker_meta = {
        "version": (body or {}).get("worker_version"),
        "status": (body or {}).get("worker_status"),
        "last_error": (body or {}).get("last_error"),
        "gateway_url": (body or {}).get("gateway_url"),
        "outbox_count": (body or {}).get("outbox_count"),
    }
    lease_token = str((body or {}).get("lease_token") or "").strip()
    task = codex_group_chat.heartbeat_task(
        task_id,
        lease_token=lease_token,
        worker_id=worker_id,
        worker_meta=worker_meta,
    )
    if not task:
        return jsonify({"ok": False, "error": "任务 lease 已失效或不存在"}), 409
    return jsonify({"ok": True, "task": task})


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
    worker_id = str((body or {}).get("worker_id") or request.headers.get("X-Worker-Id") or "").strip()
    lease_token = str((body or {}).get("lease_token") or "").strip()
    task = codex_group_chat.finish_task(
        task_id,
        response=response,
        error=error,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    if task.get("finish_rejected"):
        return jsonify({"ok": False, "error": task.get("error") or "lease_conflict", "task": task}), 409
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
