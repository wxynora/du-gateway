# 管理端：最近窗口列表、白名单/黑名单、删除某一轮对话、一键清空
from flask import Blueprint, request, jsonify

from storage import whitelist_store, blacklist_store
from storage import r2_store
from storage.wipe_local import wipe_local_data

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/windows", methods=["GET"])
def list_windows():
    """返回最近出现过的窗口列表；whitelisted / blacklisted 供管理端展示与一键解除黑名单。"""
    limit = request.args.get("limit", type=int, default=50)
    if limit > 200:
        limit = 200
    items = whitelist_store.list_recent_windows(limit=limit)
    whitelist = set(whitelist_store.list_whitelist())
    blacklist = set(blacklist_store.list_blacklist())
    for w in items:
        w["whitelisted"] = w.get("id") in whitelist
        w["blacklisted"] = w.get("id") in blacklist
    return jsonify({"windows": items})


@bp.route("/whitelist", methods=["GET"])
def get_whitelist():
    """返回当前白名单列表。"""
    return jsonify({"whitelist": whitelist_store.list_whitelist()})


@bp.route("/whitelist", methods=["POST"])
def add_whitelist():
    """将指定窗口 ID 加入白名单（B：管理端一键加）。"""
    data = request.get_json(silent=True) or {}
    window_id = (data.get("window_id") or data.get("id") or "").strip()
    if not window_id:
        return jsonify({"error": "缺少 window_id 或 id"}), 400
    whitelist_store.add_to_whitelist(window_id)
    return jsonify({"ok": True, "window_id": window_id})


@bp.route("/whitelist/<window_id>", methods=["DELETE"])
def remove_whitelist(window_id):
    """从白名单移除指定窗口。"""
    if not window_id:
        return jsonify({"error": "缺少 window_id"}), 400
    ok = whitelist_store.remove_from_whitelist(window_id)
    return jsonify({"ok": ok, "window_id": window_id})


@bp.route("/blacklist", methods=["GET"])
def get_blacklist():
    """返回当前黑名单窗口 ID 列表。"""
    return jsonify({"blacklist": blacklist_store.list_blacklist()})


@bp.route("/blacklist/<window_id>", methods=["DELETE"])
def remove_blacklist(window_id):
    """解除黑名单（误判时用）。"""
    if not window_id:
        return jsonify({"error": "缺少 window_id"}), 400
    ok = blacklist_store.remove_from_blacklist(window_id)
    return jsonify({"ok": ok, "window_id": window_id})


@bp.route("/windows/<window_id>/rounds/<int:round_index>", methods=["DELETE"])
def delete_round(window_id, round_index):
    """
    删除该窗口下指定轮次的对话（老婆在 RikkaHub 删掉这一轮后，可调此接口同步从记忆里删掉）。
    round_index 为存档中的轮次序号（从 1 开始）。
    """
    if not window_id or round_index < 1:
        return jsonify({"error": "window_id 或 round_index 无效"}), 400
    ok = r2_store.delete_conversation_round(window_id, round_index)
    return jsonify({"ok": ok, "window_id": window_id, "round_index": round_index})


@bp.route("/summary", methods=["GET"])
def get_summary_preview():
    """
    查看当前是否有总结记忆（全局一份，白名单窗口共享）。
    返回 has_summary、长度、全文，方便确认「有没有总结」。
    """
    summary = r2_store.get_summary("")
    if not summary or not summary.strip():
        return jsonify({"has_summary": False, "summary": None, "length": 0})
    return jsonify({
        "has_summary": True,
        "summary": summary.strip(),
        "length": len(summary.strip()),
    })


@bp.route("/windows/<window_id>/rounds", methods=["GET"])
def list_rounds(window_id):
    """
    返回该窗口每一轮的序号 + 前几个字预览，便于管理端定位 round_index。
    GET /admin/windows/<window_id>/rounds?preview_chars=24
    """
    if not window_id:
        return jsonify({"error": "缺少 window_id"}), 400
    preview_chars = request.args.get("preview_chars", type=int, default=24)
    if preview_chars < 0:
        preview_chars = 0
    if preview_chars > 200:
        preview_chars = 200
    rounds = r2_store.list_conversation_rounds_preview(window_id, preview_chars=preview_chars)
    return jsonify({"window_id": window_id, "rounds": rounds, "count": len(rounds)})


@bp.route("/core_cache", methods=["GET"])
def get_core_cache():
    """返回 core_cache pending 里所有待审条目。"""
    pending = r2_store.get_core_cache_pending()
    return jsonify({"pending": pending, "count": len(pending)})


@bp.route("/core_cache/<entry_id>", methods=["DELETE"])
def delete_core_cache_entry(entry_id):
    """删除指定待审条目（人工审完后调用）。entry_id 为 pending 项的 id。"""
    if not entry_id:
        return jsonify({"error": "缺少 entry_id"}), 400
    ok = r2_store.delete_core_cache_by_id(entry_id)
    return jsonify({"ok": ok, "id": entry_id})


@bp.route("/core_cache/sync_to_notion", methods=["POST"])
def core_cache_sync_to_notion():
    """把当前 pending 全量推到 Notion 核心缓存 database；审阅前调用。"""
    from services.core_cache_notion_sync import sync_to_notion
    ok, err = sync_to_notion()
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True})


@bp.route("/core_cache/sync_from_notion", methods=["POST"])
def core_cache_sync_from_notion():
    """从 Notion 核心缓存 database 读回当前所有条目，完全覆盖 R2 pending；审阅/删减后调用。"""
    from services.core_cache_notion_sync import sync_from_notion
    ok, err = sync_from_notion()
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True})


@bp.route("/wipe_all", methods=["POST", "DELETE"])
def wipe_all_data():
    """
    一键清空：R2 所有记录 + 本地白名单/黑名单/最近窗口/上次回复时间。
    仅测试/重置用。必须带 confirm=wipe_all 才执行（query 或 body 均可）。
    """
    data = request.get_json(silent=True) or {}
    confirm = request.args.get("confirm") or data.get("confirm") or ""
    if confirm != "wipe_all":
        return jsonify({
            "error": "未确认：请带 confirm=wipe_all（query 或 body）再调用",
            "example_query": "POST /admin/wipe_all?confirm=wipe_all",
            "example_body": '{"confirm": "wipe_all"}',
        }), 400
    r2_ok, r2_deleted, r2_err = r2_store.delete_all_gateway_data()
    local_ok, local_cleared, local_err = wipe_local_data()
    if not r2_ok:
        return jsonify({"ok": False, "error": f"R2: {r2_err or '未知错误'}"}), 500
    if not local_ok:
        return jsonify({"ok": False, "error": f"本地: {local_err or '未知错误'}"}), 500
    return jsonify({
        "ok": True,
        "r2_deleted_keys": r2_deleted,
        "local_cleared_files": local_cleared,
    })
