from __future__ import annotations

from flask import jsonify, request

from storage import exchange_diary_store


def _int_arg(name: str, default: int, *, min_value: int = 1, max_value: int = 200) -> int:
    try:
        value = int(float(str(request.args.get(name) or default).strip()))
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def register_routes(bp) -> None:
    @bp.route("/exchange-diary", methods=["GET"])
    def miniapp_exchange_diary_list():
        data = exchange_diary_store.list_entries(
            limit=_int_arg("limit", 30),
            cursor=str(request.args.get("cursor") or ""),
            month=str(request.args.get("month") or ""),
            author=str(request.args.get("author") or ""),
            include_deleted=False,
        )
        return jsonify({"ok": True, **data})

    @bp.route("/exchange-diary/<entry_id>", methods=["GET"])
    def miniapp_exchange_diary_get(entry_id: str):
        item = exchange_diary_store.get_entry(entry_id, include_deleted=False)
        if not item:
            return jsonify({"ok": False, "error": "未找到日记"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary", methods=["POST"])
    def miniapp_exchange_diary_create():
        body = request.get_json(silent=True) or {}
        item = exchange_diary_store.create_entry({**body, "author": "xy", "source": "app"})
        if not item:
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary/<entry_id>", methods=["PATCH", "PUT"])
    def miniapp_exchange_diary_update(entry_id: str):
        body = request.get_json(silent=True) or {}
        item, status = exchange_diary_store.update_entry(
            entry_id,
            body,
            base_updated_at=str(body.get("base_updated_at") or body.get("baseUpdatedAt") or ""),
        )
        if status == "conflict":
            return jsonify({"ok": False, "error": "conflict", "server_item": item}), 409
        if status == "sync_failed":
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        if not item:
            return jsonify({"ok": False, "error": "未找到日记或更新失败"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary/<entry_id>", methods=["DELETE"])
    def miniapp_exchange_diary_delete(entry_id: str):
        if not exchange_diary_store.get_entry(entry_id, include_deleted=True):
            return jsonify({"ok": False, "error": "未找到日记"}), 404
        item = exchange_diary_store.soft_delete_entry(entry_id)
        if not item:
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary/<entry_id>/comments", methods=["POST"])
    def miniapp_exchange_diary_comment_create(entry_id: str):
        body = request.get_json(silent=True) or {}
        if not str(body.get("content") or "").strip():
            return jsonify({"ok": False, "error": "评论内容不能为空"}), 400
        current = exchange_diary_store.get_entry(entry_id, include_deleted=False)
        if not current:
            return jsonify({"ok": False, "error": "未找到日记"}), 404
        reply_to = str(
            body.get("reply_to_comment_id")
            or body.get("replyToCommentId")
            or body.get("parent_comment_id")
            or body.get("parentCommentId")
            or ""
        ).strip()
        if reply_to:
            active_comment_ids = {
                str(c.get("id") or "").strip()
                for c in (current.get("comments") or [])
                if isinstance(c, dict)
                and str(c.get("id") or "").strip()
                and not str(c.get("deleted_at") or "").strip()
            }
            if reply_to not in active_comment_ids:
                return jsonify({"ok": False, "error": "reply_to_comment_id 无效"}), 400
        item = exchange_diary_store.add_comment(entry_id, {**body, "author": "xy"})
        if not item:
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        return jsonify({"ok": True, "item": item})
