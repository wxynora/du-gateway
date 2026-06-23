from __future__ import annotations

from flask import jsonify, request

from storage import secret_drawer_store


def _bool_arg(name: str, default: bool = False) -> bool:
    raw = str(request.args.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _json_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _optional_bool_arg(name: str) -> bool | None:
    if name not in request.args:
        return None
    return _bool_arg(name)


def _int_arg(name: str, default: int, *, min_value: int = 1, max_value: int = 500) -> int:
    try:
        value = int(float(str(request.args.get(name) or default).strip()))
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def register_routes(bp) -> None:
    @bp.route("/secret-drawer/stats", methods=["GET"])
    def miniapp_secret_drawer_stats():
        return jsonify({"ok": True, "stats": secret_drawer_store.stats(include_sealed_details=_bool_arg("include_sealed_details"))})

    @bp.route("/secret-drawer/config", methods=["GET"])
    def miniapp_secret_drawer_config():
        config = secret_drawer_store.get_config()
        if config.get("read_error"):
            return jsonify({"ok": False, "error": "PIN 配置读取失败"}), 503
        return jsonify(
            {
                "ok": True,
                "configured": {
                    "box": bool(config.get("box_pin")),
                    "sealed": bool(config.get("sealed_pin")),
                },
                "updated_at": config.get("updated_at") or "",
            }
        )

    @bp.route("/secret-drawer/unlock", methods=["POST"])
    def miniapp_secret_drawer_unlock():
        body = request.get_json(silent=True) or {}
        layer = str(body.get("layer") or "box").strip().lower()
        pin = body.get("pin")
        return jsonify({"ok": True, "unlocked": secret_drawer_store.verify_pin(layer, pin), "layer": layer})

    @bp.route("/secret-drawer/items", methods=["GET"])
    def miniapp_secret_drawer_items():
        items = secret_drawer_store.list_items(
            include_deleted=_bool_arg("include_deleted"),
            include_sealed=_bool_arg("include_sealed"),
            sealed_only=_bool_arg("sealed_only"),
            type_filter=str(request.args.get("type") or ""),
            tag=str(request.args.get("tag") or ""),
            query=str(request.args.get("q") or request.args.get("query") or ""),
            needs_organize_only=_bool_arg("needs_organize"),
            pinned_only=_optional_bool_arg("pinned"),
            limit=_int_arg("limit", 100),
        )
        return jsonify({"ok": True, "items": items, "count": len(items)})

    @bp.route("/secret-drawer/items", methods=["POST"])
    def miniapp_secret_drawer_create():
        body = request.get_json(silent=True) or {}
        item = secret_drawer_store.save_item(body)
        if not item:
            return jsonify({"ok": False, "error": "写入失败"}), 500
        return jsonify({"ok": True, "item": item})

    @bp.route("/secret-drawer/items/<item_id>", methods=["GET"])
    def miniapp_secret_drawer_item(item_id: str):
        item = secret_drawer_store.get_item(item_id, include_deleted=_bool_arg("include_deleted"))
        if not item:
            return jsonify({"ok": False, "error": "未找到"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/secret-drawer/items/<item_id>", methods=["PATCH", "PUT"])
    def miniapp_secret_drawer_update(item_id: str):
        body = request.get_json(silent=True) or {}
        item = secret_drawer_store.update_item(item_id, body)
        if not item:
            return jsonify({"ok": False, "error": "未找到或更新失败"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/secret-drawer/items/<item_id>", methods=["DELETE"])
    def miniapp_secret_drawer_delete(item_id: str):
        item = secret_drawer_store.soft_delete_item(item_id)
        if not item:
            return jsonify({"ok": False, "error": "未找到或删除失败"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/secret-drawer/items/<item_id>/restore", methods=["POST"])
    def miniapp_secret_drawer_restore(item_id: str):
        item = secret_drawer_store.restore_item(item_id)
        if not item:
            return jsonify({"ok": False, "error": "未找到或恢复失败"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/secret-drawer/random", methods=["POST"])
    def miniapp_secret_drawer_random():
        body = request.get_json(silent=True) or {}
        item = secret_drawer_store.random_item(
            include_sealed=_json_bool(body.get("include_sealed")),
            sealed_only=_json_bool(body.get("sealed_only")),
            type_filter=str(body.get("type") or ""),
            tag=str(body.get("tag") or ""),
            needs_organize_only=_json_bool(body.get("needs_organize")),
        )
        if not item:
            return jsonify({"ok": False, "error": "没有可抽的条目"}), 404
        return jsonify({"ok": True, "item": item})
