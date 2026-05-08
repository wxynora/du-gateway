from __future__ import annotations

from flask import jsonify, request

from storage import r2_store


def register_routes(bp) -> None:
    @bp.route("/core_cache", methods=["GET"])
    def miniapp_core_cache():
        pending = r2_store.get_core_cache_pending() or []
        return jsonify({"pending": pending, "count": len(pending)})

    @bp.route("/core_cache/<entry_id>", methods=["DELETE"])
    def miniapp_delete_core_cache(entry_id: str):
        if not entry_id:
            return jsonify({"error": "缺少 entry_id"}), 400
        ok = r2_store.delete_core_cache_by_id(entry_id)
        return jsonify({"ok": ok, "id": entry_id})

    @bp.route("/notebook", methods=["GET"])
    def miniapp_notebook_list():
        entries = r2_store.get_notebook_entries() or []
        return jsonify({"entries": entries, "count": len(entries)})

    @bp.route("/notebook", methods=["POST"])
    def miniapp_notebook_add():
        data = request.get_json(silent=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "缺少 content"}), 400
        ok = r2_store.notebook_append_entry(content)
        return jsonify({"ok": ok})

    @bp.route("/notebook/<ts>", methods=["DELETE"])
    def miniapp_notebook_delete(ts: str):
        ts = (ts or "").strip()
        if not ts:
            return jsonify({"error": "缺少 timestamp"}), 400
        ok = r2_store.notebook_delete_entry_by_timestamp(ts)
        return jsonify({"ok": ok, "timestamp": ts})

    @bp.route("/du-notebook", methods=["GET"])
    def miniapp_du_notebook_list():
        items = r2_store.get_du_notebook_entries() or []
        return jsonify({"ok": True, "items": items, "count": len(items)})

    @bp.route("/du-notebook", methods=["POST"])
    def miniapp_du_notebook_add():
        data = request.get_json(silent=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"ok": False, "error": "content 不能为空"}), 400
        entry = r2_store.add_du_notebook_entry(content)
        if not entry:
            return jsonify({"ok": False, "error": "新增失败"}), 500
        return jsonify({"ok": True, "entry": entry})

    @bp.route("/du-notebook/<entry_id>", methods=["PUT"])
    def miniapp_du_notebook_update(entry_id: str):
        eid = (entry_id or "").strip()
        if not eid:
            return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
        data = request.get_json(silent=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"ok": False, "error": "content 不能为空"}), 400
        ok = r2_store.update_du_notebook_entry(eid, content)
        if not ok:
            return jsonify({"ok": False, "error": "未找到条目或更新失败"}), 404
        return jsonify({"ok": True, "id": eid})

    @bp.route("/du-notebook/<entry_id>", methods=["DELETE"])
    def miniapp_du_notebook_delete(entry_id: str):
        eid = (entry_id or "").strip()
        if not eid:
            return jsonify({"ok": False, "error": "缺少 entry_id"}), 400
        ok = r2_store.delete_du_notebook_entry(eid)
        if not ok:
            return jsonify({"ok": False, "error": "未找到该条目"}), 404
        return jsonify({"ok": True, "id": eid})

    @bp.route("/stay-with-du", methods=["GET"])
    def miniapp_stay_with_du_get():
        data = r2_store.get_stay_with_du_data()
        return jsonify({"ok": True, "data": data})

    @bp.route("/stay-with-du", methods=["PUT", "POST"])
    def miniapp_stay_with_du_save():
        body = request.get_json(silent=True) or {}
        raw = body.get("data") if isinstance(body.get("data"), dict) else body
        data = r2_store.normalize_stay_with_du_data(raw)
        ok = r2_store.save_stay_with_du_data(data)
        if not ok:
            return jsonify({"ok": False, "error": "保存失败"}), 500
        return jsonify({"ok": True, "data": r2_store.get_stay_with_du_data()})
