# Notion 读写删改：通过网关对 Notion 的 CRUD
from flask import Blueprint, request, jsonify

from services import notion_client

bp = Blueprint("notion", __name__, url_prefix="/notion")


@bp.route("/search", methods=["POST"])
def search():
    """Notion 关键词检索。"""
    data = request.get_json(silent=True) or {}
    query = data.get("query") or request.args.get("query") or ""
    result, err = notion_client.search(query=query if query else None)
    if err:
        return jsonify(err), 400
    return jsonify(result or {})


@bp.route("/pages/<page_id>", methods=["GET"])
def read_page(page_id):
    """读取 Notion 页面。"""
    result, err = notion_client.read_page(page_id)
    if err:
        return jsonify(err), 400
    return jsonify(result or {})


@bp.route("/blocks/<block_id>/children", methods=["GET"])
def read_block_children(block_id):
    """读取块下子块。"""
    result, err = notion_client.read_block_children(block_id)
    if err:
        return jsonify(err), 400
    return jsonify(result or {})


@bp.route("/pages", methods=["POST"])
def create_page():
    """创建 Notion 页面。"""
    data = request.get_json(silent=True) or {}
    parent = data.get("parent")
    properties = data.get("properties", {})
    children = data.get("children")
    if not parent or not properties:
        return jsonify({"error": "缺少 parent 或 properties"}), 400
    result, err = notion_client.create_page(parent, properties, children)
    if err:
        return jsonify(err), 400
    return jsonify(result or {})


@bp.route("/pages/<page_id>", methods=["PATCH"])
def update_page(page_id):
    """更新 Notion 页面属性。"""
    data = request.get_json(silent=True) or {}
    properties = data.get("properties", {})
    if not properties:
        return jsonify({"error": "缺少 properties"}), 400
    result, err = notion_client.update_page(page_id, properties)
    if err:
        return jsonify(err), 400
    return jsonify(result or {})


@bp.route("/blocks/<block_id>", methods=["PATCH"])
def update_block(block_id):
    """更新块。"""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "缺少 body"}), 400
    result, err = notion_client.update_block(block_id, data)
    if err:
        return jsonify(err), 400
    return jsonify(result or {})


@bp.route("/blocks/<block_id>", methods=["DELETE"])
def delete_block(block_id):
    """删除（归档）块。"""
    result, err = notion_client.delete_block(block_id)
    if err:
        return jsonify(err), 400
    return jsonify(result or {"ok": True})
