from flask import jsonify, request

from services import codex_group_chat


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def register_routes(bp) -> None:
    @bp.route("/codex-group-chat-tasks", methods=["POST"])
    def miniapp_codex_group_chat_task_create():
        body = request.get_json(silent=True) or {}
        task = codex_group_chat.create_task(body, device_id=_get_panel_device_id())
        if not task:
            return jsonify({"ok": False, "error": "缺少 window_id / user_message / du_reply，无法创建笨笨群聊任务"}), 400
        return jsonify({"ok": True, "task": task})

    @bp.route("/codex-group-chat-tasks/<task_id>", methods=["GET"])
    def miniapp_codex_group_chat_task_get(task_id: str):
        task = codex_group_chat.get_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "笨笨群聊任务不存在或已过期"}), 404
        return jsonify({"ok": True, "task": task})
