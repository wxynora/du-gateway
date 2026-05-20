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
        try:
            from services.wenyou_service import get_session_view

            view = get_session_view(uid).get("session") or {}
        except Exception:
            view = {}
        return jsonify(
            {
                "ok": True,
                "active": True,
                "session": {
                    "gameId": str(session.get("gameId") or ""),
                    "startedAt": str(session.get("startedAt") or ""),
                    "phase": str(view.get("phase") or ""),
                    "phase_label": str(view.get("phase_label") or ""),
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

    @bp.route("/wenyou/shop", methods=["GET"])
    def miniapp_wenyou_shop():
        """文游：系统商店。每日随机商品，购买写入当前文游背包。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import get_shop_view

        return jsonify({"ok": True, **get_shop_view(uid)})

    @bp.route("/wenyou/shop/buy", methods=["POST"])
    def miniapp_wenyou_shop_buy():
        """文游：购买系统商店道具，扣当前 session 积分。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item_id = str(data.get("item_id") or data.get("id") or "").strip()
        from services.wenyou_service import buy_shop_item

        ok, message, view = buy_shop_item(uid, item_id)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/shop/refresh", methods=["POST"])
    def miniapp_wenyou_shop_refresh():
        """文游：刷新普通商店，扣刷新积分并遵守每日次数。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import refresh_shop_items

        ok, message, view = refresh_shop_items(uid)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/gacha/roll", methods=["POST"])
    def miniapp_wenyou_gacha_roll():
        """文游：命运裂隙抽卡。后端扣积分、写背包、记录保底。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        pool_id = str(data.get("pool_id") or data.get("pool") or "mixed").strip()
        count = data.get("count") or 1
        from services.wenyou_service import roll_gacha

        ok, message, view = roll_gacha(uid, pool_id=pool_id, count=count)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/player/attributes", methods=["POST"])
    def miniapp_wenyou_allocate_attributes():
        """文游：固定规则分配六基础属性点，不交给 GM 判定。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        deltas = data.get("deltas") if isinstance(data.get("deltas"), dict) else {}
        from services.wenyou_service import allocate_attribute_points

        ok, message, view = allocate_attribute_points(uid, player_id=player, deltas=deltas)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/player/promote", methods=["POST"])
    def miniapp_wenyou_promote_rank():
        """文游：固定规则晋升阶位，扣积分并解封可用道具。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        target_rank = str(data.get("target_rank") or data.get("rank") or "").strip()
        from services.wenyou_service import promote_player_rank

        ok, message, view = promote_player_rank(uid, player_id=player, target_rank=target_rank)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/player/revive", methods=["POST"])
    def miniapp_wenyou_revive_player():
        """文游：固定规则复活角色，扣积分/写债务并添加复活疲惫。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        from services.wenyou_service import revive_player

        ok, message, view = revive_player(uid, player_id=player)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/player/ability/learn", methods=["POST"])
    def miniapp_wenyou_learn_ability():
        """文游：学习或升级能力，系统检查能力槽、阶位和碎片。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        ability = str(data.get("ability") or data.get("ability_id") or data.get("id") or "").strip()
        if not ability:
            return jsonify({"ok": False, "error": "请选择能力"}), 400
        from services.wenyou_service import learn_or_upgrade_ability

        ok, message, view = learn_or_upgrade_ability(uid, ability, player_id=player)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/player/ability/use", methods=["POST"])
    def miniapp_wenyou_use_ability():
        """文游：使用能力，系统检查次数、封印和代价。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        ability = str(data.get("ability") or data.get("ability_id") or data.get("id") or "").strip()
        detail = str(data.get("detail") or data.get("action") or "").strip()
        if not ability:
            return jsonify({"ok": False, "error": "请选择能力"}), 400
        from services.wenyou_service import use_player_ability

        ok, message, view = use_player_ability(uid, ability, player_id=player, detail=detail)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/player/evolution/apply", methods=["POST"])
    def miniapp_wenyou_apply_evolution():
        """文游：进化升级，系统扣积分和进化碎片。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        route = str(data.get("route") or data.get("route_id") or "human_stable").strip()
        target_rank = str(data.get("target_rank") or data.get("rank") or "").strip()
        from services.wenyou_service import apply_evolution_effect

        ok, message, view = apply_evolution_effect(uid, route_id=route, player_id=player, target_rank=target_rank)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

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
            from services.wenyou_service import apply_forced_instance_candidates

            cached = apply_forced_instance_candidates(uid, cached)
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
            from services.wenyou_service import start_story_candidate_expansion_job

            job, err = start_story_candidate_expansion_job(uid, candidate)
            if err or not job:
                return jsonify({"ok": False, "error": err or "候选扩展任务创建失败"}), 400
            return jsonify({"ok": True, "expanding": True, **job}), 202
        if mode not in ("random", "custom"):
            return jsonify({"ok": False, "error": "mode 须为 random 或 custom"}), 400
        if mode == "custom" and not keywords:
            return jsonify({"ok": False, "error": "自定义任务请输入描述"}), 400
        from services.wenyou_service import cmd_story

        text = cmd_story(uid, keywords if mode == "custom" else None)
        need_confirm = "若确定要开新局" in (text or "")
        return jsonify({"ok": True, "text": text, "need_confirm_new_game": bool(need_confirm)})

    @bp.route("/wenyou/story-job/<job_id>", methods=["GET"])
    def miniapp_wenyou_story_job(job_id: str):
        """文游：查询候选副本后台扩展任务。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import get_session_view, get_story_expansion_job

        job = get_story_expansion_job(uid, job_id)
        if not job:
            return jsonify({"ok": False, "error": "未找到扩展任务"}), 404
        payload = {"ok": True, **job}
        if job.get("status") == "done":
            payload.update(get_session_view(uid))
        return jsonify(payload)

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
        from services.wenyou_service import (
            classify_wenyou_action_text,
            cmd_action,
            cmd_action_with_du,
            cmd_encounter_action_with_du,
            cmd_record_action,
            get_session_view,
        )

        action_intent = classify_wenyou_action_text(text)
        if action_intent.get("action_type") == "system_action":
            return jsonify({"ok": False, "error": "这是系统操作，请使用对应面板入口。", "action_intent": action_intent, **get_session_view(uid)}), 400
        if action_intent.get("action_type") == "use_item":
            return jsonify({"ok": False, "error": "道具使用请从背包选择物品，走系统判定。", "action_intent": action_intent, **get_session_view(uid)}), 400
        if auto_go is False:
            ok, msg = cmd_record_action(uid, text, player)
            if not ok:
                return jsonify({"ok": False, "error": msg}), 400
            return jsonify({"ok": True, "queued": True, "text": msg, "action_intent": action_intent, **get_session_view(uid)})
        if action_intent.get("action_type") in {"attack", "flee", "evade", "weaken", "seal"}:
            out, du_action = cmd_encounter_action_with_du(
                uid,
                str(action_intent.get("action_type") or ""),
                target=str(action_intent.get("target") or ""),
                detail=text,
            )
            failed = out.startswith("文游：")
            payload = {"ok": not failed, "text": out, "action_intent": action_intent, **get_session_view(uid)}
            if du_action:
                payload["du_action"] = du_action
            return jsonify(payload), (400 if failed else 200)
        du_action = ""
        player_key = player.lower()
        if player_key in ("player1", "p1") or player in ("辛玥", ""):
            out, du_action = cmd_action_with_du(uid, text)
        else:
            out = cmd_action(uid, text, player)
        failed = out.startswith("文游：当前没有") or out.startswith("文游：GM 调用失败") or out.startswith("文游：当前处于")
        payload = {"ok": not failed, "text": out, "action_intent": action_intent, **get_session_view(uid)}
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
        """文游：使用背包道具，系统判定效果/消耗后交给 GM 叙事。"""
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
        failed = out.startswith("文游：")
        payload = {"ok": not failed, "text": out, **get_session_view(uid)}
        if du_action:
            payload["du_action"] = du_action
        return jsonify(payload), (400 if failed else 200)

    @bp.route("/wenyou/item/equip", methods=["POST"])
    def miniapp_wenyou_equip_item():
        """文游：装备武器/防具/饰品/工具，系统判定槽位和门槛。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item = str(data.get("item") or data.get("item_ref") or data.get("uid") or data.get("id") or "").strip()
        player = str(data.get("player") or data.get("player_id") or "player1").strip()
        slot = str(data.get("slot") or "").strip()
        if not item:
            return jsonify({"ok": False, "error": "请选择装备"}), 400
        from services.wenyou_service import equip_inventory_item

        ok, message, view = equip_inventory_item(uid, item, player_id=player, slot=slot)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/item/repair", methods=["POST"])
    def miniapp_wenyou_repair_item():
        """文游：维修装备耐久，系统扣积分。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item = str(data.get("item") or data.get("item_ref") or data.get("uid") or data.get("id") or "").strip()
        if not item:
            return jsonify({"ok": False, "error": "请选择维修物品"}), 400
        from services.wenyou_service import repair_inventory_item

        ok, message, view = repair_inventory_item(uid, item)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/item/sell", methods=["POST"])
    def miniapp_wenyou_sell_item():
        """文游：出售回收背包物品，绑定/任务/唯一物禁止。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item = str(data.get("item") or data.get("item_ref") or data.get("uid") or data.get("id") or "").strip()
        if not item:
            return jsonify({"ok": False, "error": "请选择出售物品"}), 400
        from services.wenyou_service import sell_inventory_item

        ok, message, view = sell_inventory_item(uid, item)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/encounter/action", methods=["POST"])
    def miniapp_wenyou_encounter_action():
        """文游：战斗/逃跑等遭遇动作先由系统规则裁判，再交给 GM 叙事。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        action = str(data.get("action") or data.get("type") or "").strip()
        target = str(data.get("target") or "").strip()
        detail = str(data.get("detail") or "").strip()
        if not action:
            return jsonify({"ok": False, "error": "请选择遭遇动作"}), 400
        from services.wenyou_service import cmd_encounter_action_with_du, get_session_view

        out, du_action = cmd_encounter_action_with_du(uid, action, target=target, detail=detail)
        failed = out.startswith("文游：")
        payload = {"ok": not failed, "text": out, **get_session_view(uid)}
        if du_action:
            payload["du_action"] = du_action
        return jsonify(payload), (400 if failed else 200)

    @bp.route("/wenyou/settlement/preview", methods=["GET", "POST"])
    def miniapp_wenyou_settlement_preview():
        """文游：预览最终结算建议，不发奖。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import get_settlement_preview

        data = request.get_json(silent=True) or {}
        result = str(data.get("result") or request.args.get("result") or "")
        rating = str(data.get("rating") or request.args.get("rating") or "")
        payload = get_settlement_preview(uid, result=result, rating=rating)
        failed = not payload.get("active")
        return jsonify({"ok": not failed, **payload}), (400 if failed else 200)

    @bp.route("/wenyou/end", methods=["POST"])
    def miniapp_wenyou_end():
        """文游：最终结算并立即归档。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import cmd_end, get_session_view

        data = request.get_json(silent=True) or {}
        result = str(data.get("result") or "")
        rating = str(data.get("rating") or "")
        out = cmd_end(uid, result=result, rating=rating)
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
        return jsonify({"ok": not failed, "text": out, "active": False, "session": None}), (400 if failed else 200)
