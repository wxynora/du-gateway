from __future__ import annotations

from flask import jsonify, request

from config import WENYOU_SESSION_ID
from storage import r2_store


def _wenyou_session_id() -> int:
    return int(WENYOU_SESSION_ID or 0)


def _missing_wenyou_session_response():
    return jsonify({"ok": False, "error": "未配置 WENYOU_SESSION_ID"}), 400


def register_routes(bp) -> None:
    @bp.route("/wenyou/last-archive", methods=["GET"])
    def miniapp_wenyou_last_archive():
        """
        文游：最近一次最终结算后的归档快照（R2 wenyou/last_archive/{user_id}.json）。
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

    @bp.route("/wenyou/session", methods=["GET"])
    def miniapp_wenyou_session():
        """文游：结构化 session 面板（任务、背包、状态、线索、历史）。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import get_session_view

        return jsonify({"ok": True, **get_session_view(uid)})

    @bp.route("/wenyou/candidates", methods=["GET", "POST"])
    def miniapp_wenyou_candidates():
        """文游：副本大厅候选设定池。优先读缓存，刷新时才调用 DS。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        force = request.method == "POST" or str(request.args.get("refresh") or "").lower() in ("1", "true", "yes")
        data = request.get_json(silent=True) or {}
        try:
            count = int(data.get("count") or request.args.get("count", type=int, default=6) or 6)
        except Exception:
            count = 6
        keywords = str(data.get("keywords") or request.args.get("keywords") or "").strip()
        cached = r2_store.get_wenyou_candidates(uid)
        if isinstance(cached, dict) and isinstance(cached.get("items"), list) and cached.get("items") and not force:
            return jsonify({"ok": True, "generated": False, **cached})

        from services.wenyou_service import generate_instance_candidates

        payload, err = generate_instance_candidates(uid, count=count, keywords=keywords)
        if err or not payload:
            if isinstance(cached, dict) and isinstance(cached.get("items"), list) and cached.get("items"):
                return jsonify({"ok": True, "generated": False, "warning": err or "候选生成失败，已返回旧缓存", **cached})
            return jsonify({"ok": False, "error": err or "候选生成失败"}), 502
        r2_store.save_wenyou_candidates(uid, payload)
        return jsonify({"ok": True, "generated": True, **payload})

    @bp.route("/wenyou/story", methods=["POST"])
    def miniapp_wenyou_story():
        """文游开局：系统空间可选随机或自定义长描述（keywords）。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode") or "random").strip().lower()
        keywords = str(data.get("keywords") or "").strip()
        candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else None
        if candidate and not keywords:
            from services.wenyou_service import format_candidate_expansion_prompt

            keywords = format_candidate_expansion_prompt(candidate)
            mode = "custom"
        if mode not in ("random", "custom"):
            return jsonify({"ok": False, "error": "mode 须为 random 或 custom"}), 400
        if mode == "custom" and not keywords:
            return jsonify({"ok": False, "error": "自定义任务请输入描述"}), 400
        from services.wenyou_service import cmd_story

        text = cmd_story(uid, keywords if mode == "custom" else None)
        need_confirm = "若确定要开新局" in (text or "")
        return jsonify({"ok": True, "text": text, "need_confirm_new_game": bool(need_confirm)})

    @bp.route("/wenyou/action", methods=["POST"])
    def miniapp_wenyou_action():
        """文游：记录玩家行动并默认推进一轮 GM。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        player = str(data.get("player") or "player1").strip()
        auto_go = data.get("auto_go", True)
        if not text:
            return jsonify({"ok": False, "error": "行动内容不能为空"}), 400
        from services.wenyou_service import cmd_action, cmd_action_with_du, cmd_record_action, get_session_view

        if auto_go is False:
            ok, msg = cmd_record_action(uid, text, player)
            if not ok:
                return jsonify({"ok": False, "error": msg}), 400
            return jsonify({"ok": True, "queued": True, "text": msg, **get_session_view(uid)})
        du_action = ""
        player_key = player.lower()
        if player_key in ("player1", "p1") or player in ("辛玥", ""):
            out, du_action = cmd_action_with_du(uid, text)
        else:
            out = cmd_action(uid, text, player)
        failed = out.startswith("文游：当前没有") or out.startswith("文游：GM 调用失败") or out.startswith("文游：当前处于")
        payload = {"ok": not failed, "text": out, **get_session_view(uid)}
        if du_action:
            payload["du_action"] = du_action
        return jsonify(payload), (400 if failed else 200)

    @bp.route("/wenyou/go", methods=["POST"])
    def miniapp_wenyou_go():
        """文游：推进当前 pending_round。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import cmd_go, get_session_view

        out = cmd_go(uid)
        failed = out.startswith("文游：当前没有") or out.startswith("文游：GM 调用失败") or out.startswith("文游：当前处于")
        return jsonify({"ok": not failed, "text": out, **get_session_view(uid)}), (400 if failed else 200)

    @bp.route("/wenyou/item/use", methods=["POST"])
    def miniapp_wenyou_use_item():
        """文游：使用背包道具，交给 GM 判定效果/消耗。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item = str(data.get("item") or "").strip()
        action = str(data.get("action") or "").strip()
        if not item:
            return jsonify({"ok": False, "error": "请选择道具"}), 400
        from services.wenyou_service import cmd_use_item_with_du, get_session_view

        out, du_action = cmd_use_item_with_du(uid, item, action)
        failed = out.startswith("文游：请选择") or out.startswith("文游：背包里没有") or out.startswith("文游：当前没有") or out.startswith("文游：GM 调用失败")
        payload = {"ok": not failed, "text": out, **get_session_view(uid)}
        if du_action:
            payload["du_action"] = du_action
        return jsonify(payload), (400 if failed else 200)

    @bp.route("/wenyou/end", methods=["POST"])
    def miniapp_wenyou_end():
        """文游：进入系统空间结算阶段。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import cmd_end, get_session_view

        out = cmd_end(uid)
        failed = out.startswith("文游：当前没有")
        return jsonify({"ok": not failed, "text": out, **get_session_view(uid)}), (400 if failed else 200)

    @bp.route("/wenyou/settle", methods=["POST"])
    def miniapp_wenyou_settle():
        """文游：最终结算并归档。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import cmd_settle

        out = cmd_settle(uid)
        failed = out.startswith("文游：当前没有") or out.startswith("文游：当前不在")
        return jsonify({"ok": not failed, "text": out}), (400 if failed else 200)
