from __future__ import annotations

from flask import jsonify, request

from storage import du_pages_store


def _bool_arg(name: str, default: bool = False) -> bool:
    raw = str(request.args.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_arg(name: str, default: int, *, min_value: int = 1, max_value: int = 500) -> int:
    try:
        value = int(float(str(request.args.get(name) or default).strip()))
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def register_routes(bp) -> None:
    @bp.route("/du-pages/stats", methods=["GET"])
    def miniapp_du_pages_stats():
        return jsonify({"ok": True, "stats": du_pages_store.stats()})

    @bp.route("/du-pages", methods=["GET"])
    def miniapp_du_pages_list():
        pages = du_pages_store.list_pages(
            include_deleted=_bool_arg("include_deleted"),
            query=str(request.args.get("q") or request.args.get("query") or ""),
            tag=str(request.args.get("tag") or ""),
            limit=_int_arg("limit", 100),
        )
        return jsonify({"ok": True, "pages": pages, "count": len(pages)})

    @bp.route("/du-pages", methods=["POST"])
    def miniapp_du_pages_create():
        body = request.get_json(silent=True) or {}
        try:
            item = du_pages_store.save_page(body)
        except ValueError as exc:
            return _error(str(exc))
        except Exception:
            return _error("写入失败", 500)
        return jsonify({"ok": True, "item": item})

    @bp.route("/du-pages/<page_id>", methods=["GET"])
    def miniapp_du_pages_get(page_id: str):
        item = du_pages_store.get_page(
            page_id,
            include_html=_bool_arg("include_html", True),
            include_deleted=_bool_arg("include_deleted"),
        )
        if not item:
            return _error("未找到", 404)
        return jsonify({"ok": True, "item": item})

    @bp.route("/du-pages/<page_id>", methods=["PATCH", "PUT"])
    def miniapp_du_pages_update(page_id: str):
        body = request.get_json(silent=True) or {}
        try:
            item = du_pages_store.update_page(page_id, body)
        except ValueError as exc:
            return _error(str(exc))
        except Exception:
            return _error("更新失败", 500)
        if not item:
            return _error("未找到或更新失败", 404)
        return jsonify({"ok": True, "item": item})

    @bp.route("/du-pages/<page_id>", methods=["DELETE"])
    def miniapp_du_pages_delete(page_id: str):
        item = du_pages_store.soft_delete_page(page_id)
        if not item:
            return _error("未找到或删除失败", 404)
        return jsonify({"ok": True, "item": item})

    @bp.route("/du-pages/<page_id>/restore", methods=["POST"])
    def miniapp_du_pages_restore(page_id: str):
        item = du_pages_store.restore_page(page_id)
        if not item:
            return _error("未找到或恢复失败", 404)
        return jsonify({"ok": True, "item": item})
