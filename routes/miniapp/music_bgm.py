from __future__ import annotations

from flask import jsonify, request

from storage.music_bgm_state import get_music_bgm_context, save_music_bgm_context


def register_routes(bp):
    @bp.route("/music/listen/bgm-context", methods=["GET"])
    def miniapp_music_bgm_context_get():
        return jsonify({"ok": True, "context": get_music_bgm_context() or {}})

    @bp.route("/music/listen/bgm-context", methods=["POST"])
    def miniapp_music_bgm_context_post():
        if not request.is_json:
            return jsonify({"ok": False, "error": "需要 application/json"}), 400
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "JSON 无效"}), 400
        context = save_music_bgm_context(body)
        if context is None:
            return jsonify({"ok": False, "error": "保存一起听状态失败"}), 500
        return jsonify({"ok": True, "context": context})
