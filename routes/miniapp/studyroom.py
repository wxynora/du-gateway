from __future__ import annotations

from flask import jsonify, request

from services import codex_group_chat
from storage import r2_store


def register_routes(bp) -> None:
    @bp.route("/studyroom", methods=["GET"])
    def miniapp_studyroom_get():
        return jsonify({"ok": True, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items", methods=["POST"])
    def miniapp_studyroom_add_item():
        data = request.get_json(silent=True) or {}
        item = r2_store.add_studyroom_item(data)
        if not item:
            return jsonify({"ok": False, "error": "资料内容不能为空"}), 400
        return jsonify({"ok": True, "item": item, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>", methods=["PUT"])
    def miniapp_studyroom_update_item(item_id: str):
        data = request.get_json(silent=True) or {}
        item = r2_store.update_studyroom_item(item_id, data)
        if not item:
            return jsonify({"ok": False, "error": "未找到资料或内容无效"}), 404
        return jsonify({"ok": True, "item": item, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>", methods=["DELETE"])
    def miniapp_studyroom_delete_item(item_id: str):
        ok = r2_store.delete_studyroom_item(item_id)
        if not ok:
            return jsonify({"ok": False, "error": "未找到资料"}), 404
        return jsonify({"ok": True, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>/codex-sort", methods=["POST"])
    def miniapp_studyroom_codex_sort(item_id: str):
        data = r2_store.get_studyroom_data()
        items = data.get("items") or []
        item = next((x for x in items if str((x or {}).get("id") or "") == str(item_id or "")), None)
        if not item:
            return jsonify({"ok": False, "error": "未找到资料"}), 404
        modules = {str((m or {}).get("id") or ""): str((m or {}).get("label") or "") for m in data.get("modules") or []}
        content_parts = [
            str(item.get("content") or "").strip(),
            str(item.get("note") or "").strip(),
            str(item.get("url") or "").strip(),
        ]
        content = "\n\n".join([x for x in content_parts if x]).strip()
        if not content:
            return jsonify({"ok": False, "error": "这条资料没有可整理内容"}), 400
        task = codex_group_chat.create_task(
            {
                "mode": "studyroom",
                "window_id": "studyroom",
                "reply_target": "studyroom",
                "study_item_id": item_id,
                "study_title": item.get("title") or "",
                "study_module": modules.get(str(item.get("module_id") or ""), "待整理"),
                "study_source": item.get("source_type") or "",
                "study_url": item.get("url") or "",
                "user_message": content,
                "client_request_id": f"studyroom-{item_id}",
            }
        )
        if not task:
            return jsonify({"ok": False, "error": "创建整理任务失败"}), 500
        r2_store.update_studyroom_item(item_id, {"status": "sorting"})
        return jsonify({"ok": True, "task": task, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/study-logs", methods=["POST"])
    def miniapp_studyroom_add_study_log():
        data = request.get_json(silent=True) or {}
        entry = r2_store.add_studyroom_log(str(data.get("content") or ""))
        if not entry:
            return jsonify({"ok": False, "error": "学习记录不能为空"}), 400
        return jsonify({"ok": True, "entry": entry, "data": r2_store.get_studyroom_data()})
