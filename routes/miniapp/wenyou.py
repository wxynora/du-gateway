from __future__ import annotations

from flask import jsonify, request

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID, TELEGRAM_WENYOU_OWNER_USER_ID, WENYOU_GROUP_CHAT_ID
from storage import r2_store


def _wenyou_session_id() -> int:
    return int(WENYOU_GROUP_CHAT_ID or TELEGRAM_WENYOU_OWNER_USER_ID or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)


def _missing_wenyou_session_response():
    return jsonify({"ok": False, "error": "未配置 WENYOU_GROUP_CHAT_ID（或文游会话 ID）"}), 400


def register_routes(bp) -> None:
    @bp.route("/wenyou/last-archive", methods=["GET"])
    def miniapp_wenyou_last_archive():
        """
        文游：最近一次 /end 后的归档快照（R2 wenyou/last_archive/{user_id}.json）。
        前端可在结局页拉一次展示框架与历史。
        """
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        arch = r2_store.get_wenyou_last_archive(uid)
        return jsonify({"ok": True, "archive": arch})

    @bp.route("/wenyou/archives", methods=["GET"])
    def miniapp_wenyou_archives():
        """文游：已通关副本历史列表（按 endedAt 倒序）。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        limit = request.args.get("limit", type=int, default=20)
        items = r2_store.list_wenyou_archives(uid, limit=limit)
        return jsonify({"ok": True, "items": items, "count": len(items)})

    @bp.route("/wenyou/archive/<game_id>", methods=["GET"])
    def miniapp_wenyou_archive_detail(game_id: str):
        """文游：单个已通关副本详情。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        gid = (game_id or "").strip()
        if not gid:
            return jsonify({"ok": False, "error": "game_id 不能为空"}), 400
        data = r2_store.get_wenyou_archive_by_game_id(uid, gid)
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "未找到该归档"}), 404
        fw = data.get("framework") if isinstance(data.get("framework"), dict) else {}
        return jsonify(
            {
                "ok": True,
                "archive": {
                    "gameId": str(data.get("gameId") or ""),
                    "endedAt": str(data.get("endedAt") or ""),
                    "framework": {
                        "instance_code": str(fw.get("instance_code") or ""),
                        "instance_name": str(fw.get("instance_name") or ""),
                        "instance_genre": str(fw.get("instance_genre") or ""),
                        "difficulty": str(fw.get("difficulty") or ""),
                        "world": str(fw.get("world") or ""),
                        "conflict": str(fw.get("conflict") or ""),
                        "failure_hint": str(fw.get("failure_hint") or ""),
                        "reward_hint": str(fw.get("reward_hint") or ""),
                    },
                    "history_count": len(data.get("history") or []) if isinstance(data.get("history"), list) else 0,
                },
            }
        )

    @bp.route("/wenyou/status", methods=["GET"])
    def miniapp_wenyou_status():
        """文游：进行中状态（系统空间用于开局前提示）。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        session = r2_store.get_wenyou_session(uid)
        if not session or not session.get("gameId"):
            return jsonify({"ok": True, "active": False, "session": None})
        fw = (session.get("framework") or {}) if isinstance(session.get("framework"), dict) else {}
        return jsonify(
            {
                "ok": True,
                "active": True,
                "session": {
                    "gameId": str(session.get("gameId") or ""),
                    "startedAt": str(session.get("startedAt") or ""),
                    "instance_code": str(fw.get("instance_code") or ""),
                    "instance_name": str(fw.get("instance_name") or ""),
                    "instance_genre": str(fw.get("instance_genre") or ""),
                    "difficulty": str(fw.get("difficulty") or ""),
                },
            }
        )

    @bp.route("/wenyou/story", methods=["POST"])
    def miniapp_wenyou_story():
        """文游开局：系统空间可选随机或自定义长描述（keywords）。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode") or "random").strip().lower()
        keywords = str(data.get("keywords") or "").strip()
        if mode not in ("random", "custom"):
            return jsonify({"ok": False, "error": "mode 须为 random 或 custom"}), 400
        if mode == "custom" and not keywords:
            return jsonify({"ok": False, "error": "自定义任务请输入描述"}), 400
        from services.wenyou_service import cmd_story

        text = cmd_story(uid, keywords if mode == "custom" else None)
        need_confirm = ("若确定要开新局" in (text or "")) and ("再发一次" in (text or ""))
        return jsonify({"ok": True, "text": text, "need_confirm_new_game": bool(need_confirm)})
