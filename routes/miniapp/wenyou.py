from __future__ import annotations

import json
from typing import Any

from flask import current_app, jsonify, request

from config import WENYOU_SESSION_ID
from storage import r2_store, upstream_store


def _wenyou_session_id() -> int:
    return int(WENYOU_SESSION_ID or 0)


def _missing_wenyou_session_response():
    return jsonify({"ok": False, "error": "未配置 WENYOU_SESSION_ID"}), 400


def _extract_chat_completion_result(result) -> tuple[int, dict[str, Any]]:
    response = result
    status = 200
    if isinstance(result, tuple):
        response = result[0] if result else None
        for item in result[1:]:
            if isinstance(item, int):
                status = item
                break
    if hasattr(response, "status_code"):
        try:
            status = int(response.status_code)
        except Exception:
            pass
    data = None
    if hasattr(response, "get_json"):
        try:
            data = response.get_json(silent=True)
        except Exception:
            data = None
    if data is None and hasattr(response, "get_data"):
        try:
            text = response.get_data(as_text=True)
            data = json.loads(text) if text else {}
        except Exception:
            data = {"raw": response.get_data(as_text=True) if hasattr(response, "get_data") else ""}
    if not isinstance(data, dict):
        data = {"content": data}
    return status, data


def _extract_assistant_content(resp_json: dict[str, Any]) -> str:
    if not isinstance(resp_json, dict):
        return ""
    choices = resp_json.get("choices")
    if not (isinstance(choices, list) and choices and isinstance(choices[0], dict)):
        return ""
    msg = ((choices[0] or {}).get("message") or {})
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return ""


def _clean_ai_player_action_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in ("ai_player_action", "action", "text", "content", "message"):
                value = str(parsed.get(key) or "").strip()
                if value:
                    raw = value
                    break
    except Exception:
        pass
    for marker in ("[WENYOU_AI_PLAYER_ACTION]", "[/WENYOU_AI_PLAYER_ACTION]"):
        raw = raw.replace(marker, "")
    return " ".join(raw.split())[:500]


def _generate_wenyou_ai_player_action(
    uid: int,
    player_action: str,
    action_intent: dict[str, Any] | None,
    *,
    window_id: str,
    actor_id: str = "player2",
) -> tuple[str, str]:
    clean_window_id = str(window_id or "").strip()
    if not clean_window_id:
        return "", "缺少 window_id，跳过 AI 玩家行动生成"
    try:
        from routes.chat import chat_completions
        from services.wenyou_service import build_ai_player_chat_messages, get_player_tool_schemas

        messages = build_ai_player_chat_messages(
            uid,
            player_action,
            actor_id=actor_id,
            action_intent=action_intent if isinstance(action_intent, dict) else None,
        )
        if not messages:
            return "", "当前没有可注入的文游 AI 玩家上下文"
        model = upstream_store.get_cached_active_model(refresh_if_missing=False)
        chat_body = {
            "model": model,
            "stream": False,
            "window_id": clean_window_id,
            "messages": messages,
            "tools": get_player_tool_schemas(),
            "tool_choice": "auto",
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": request.headers.get("User-Agent") or "SumiTalk Wenyou",
            "X-Force-Last4": str(request.headers.get("X-Force-Last4") or "1"),
            "X-Reply-Channel": "sumitalk",
            "X-Reply-Target": "wenyou_ai_player",
            "X-Skip-Dynamic-Memory": "1",
            "X-Window-Id": clean_window_id,
        }
        with current_app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base={"REMOTE_ADDR": request.remote_addr or "127.0.0.1"},
        ):
            result = chat_completions()
            status_code, resp_json = _extract_chat_completion_result(result)
        if status_code >= 400:
            err = resp_json.get("error") or resp_json.get("message") or "upstream error"
            return "", f"AI 玩家聊天管道失败：{err}"
        action_text = _clean_ai_player_action_text(_extract_assistant_content(resp_json))
        if not action_text:
            return "", "AI 玩家没有返回行动文本"
        return action_text, ""
    except Exception as e:
        return "", f"AI 玩家聊天管道异常：{e}"


def _maybe_generate_ai_player_action(
    uid: int,
    *,
    external_action: str,
    player_action: str,
    action_intent: dict[str, Any] | None,
    data: dict[str, Any],
) -> tuple[str, str]:
    action = str(external_action or "").strip()
    if action:
        return action, ""
    window_id = str(data.get("window_id") or request.headers.get("X-Window-Id") or "").strip()
    return _generate_wenyou_ai_player_action(uid, player_action, action_intent, window_id=window_id)


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
            try:
                from services.wenyou_service import get_wenyou_entry_state

                entry = get_wenyou_entry_state(uid)
            except Exception:
                entry = {}
            return jsonify({"ok": True, "active": False, "session": None, "entry": entry})
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
        actor_id = str(request.args.get("actor_id") or request.args.get("player_id") or "player1").strip()
        from services.wenyou_service import get_shop_view

        return jsonify({"ok": True, **get_shop_view(uid, actor_id=actor_id)})

    @bp.route("/wenyou/shop/buy", methods=["POST"])
    def miniapp_wenyou_shop_buy():
        """文游：购买系统商店道具，扣当前 session 积分。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item_id = str(data.get("item_id") or data.get("id") or "").strip()
        offer_ref = str(data.get("offer_ref") or "").strip()
        actor_id = str(data.get("actor_id") or data.get("player_id") or "player1").strip()
        reason = str(data.get("reason") or "").strip()
        from services.wenyou_service import buy_shop_item

        ok, message, view = buy_shop_item(uid, item_id=item_id, actor_id=actor_id, offer_ref=offer_ref, reason=reason)
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
        actor_id = str(data.get("actor_id") or data.get("player_id") or "player1").strip()
        reason = str(data.get("reason") or "").strip()
        from services.wenyou_service import roll_gacha

        ok, message, view = roll_gacha(uid, pool_id=pool_id, count=count, actor_id=actor_id, reason=reason)
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

    @bp.route("/wenyou/forced-instance", methods=["GET"])
    def miniapp_wenyou_forced_instance():
        """文游：主神空间强制副本弹窗，不生成普通候选。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        from services.wenyou_service import get_forced_instance_prompt

        return jsonify({"ok": True, **get_forced_instance_prompt(uid)})

    @bp.route("/wenyou/story", methods=["POST"])
    def miniapp_wenyou_story():
        """文游开局：系统空间可选随机或自定义长描述（keywords）。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode") or "random").strip().lower()
        keywords = str(data.get("keywords") or "").strip()
        player_name = str(data.get("player_name") or data.get("playerName") or "").strip()
        player2_name = str(data.get("player2_name") or data.get("player2Name") or "").strip()
        candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else None
        if player_name or player2_name:
            from services.wenyou_service import set_wenyou_player_display_name

            if player_name:
                set_wenyou_player_display_name(uid, player_name, "player1")
            if player2_name:
                set_wenyou_player_display_name(uid, player2_name, "player2")
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
        external_ai_player_action = str(data.get("ai_player_action") or data.get("companion_action") or data.get("player2_action") or "").strip()
        auto_go = data.get("auto_go", True)
        if not text:
            return jsonify({"ok": False, "error": "行动内容不能为空"}), 400
        from services.wenyou_service import (
            classify_wenyou_action_text,
            cmd_action,
            cmd_action_with_ai_player,
            cmd_encounter_action_with_ai_player,
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
        ai_player_error = ""
        player_key = player.lower()
        if player_key in ("player1", "p1") or player in ("玩家一", ""):
            external_ai_player_action, ai_player_error = _maybe_generate_ai_player_action(
                uid,
                external_action=external_ai_player_action,
                player_action=text,
                action_intent=action_intent,
                data=data,
            )
        if action_intent.get("action_type") in {"attack", "flee", "evade", "weaken", "seal"}:
            out, ai_player_action = cmd_encounter_action_with_ai_player(
                uid,
                str(action_intent.get("action_type") or ""),
                target=str(action_intent.get("target") or ""),
                detail=text,
                ai_player_action=external_ai_player_action,
            )
            failed = out.startswith("文游：")
            payload = {"ok": not failed, "text": out, "action_intent": action_intent, **get_session_view(uid)}
            if ai_player_action:
                payload["ai_player_action"] = ai_player_action
            if ai_player_error:
                payload["ai_player_error"] = ai_player_error
            return jsonify(payload), (400 if failed else 200)
        ai_player_action = ""
        if player_key in ("player1", "p1") or player in ("玩家一", ""):
            out, ai_player_action = cmd_action_with_ai_player(uid, text, ai_player_action=external_ai_player_action)
        else:
            out = cmd_action(uid, text, player)
        failed = out.startswith("文游：当前没有") or out.startswith("文游：GM 调用失败") or out.startswith("文游：当前处于")
        payload = {"ok": not failed, "text": out, "action_intent": action_intent, **get_session_view(uid)}
        if ai_player_action:
            payload["ai_player_action"] = ai_player_action
        if ai_player_error:
            payload["ai_player_error"] = ai_player_error
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
        external_ai_player_action = str(data.get("ai_player_action") or data.get("companion_action") or data.get("player2_action") or "").strip()
        actor_id = str(data.get("actor_id") or data.get("player_id") or "player1").strip()
        target_id = str(data.get("target_id") or actor_id).strip()
        if not item:
            return jsonify({"ok": False, "error": "请选择道具"}), 400
        if actor_id and actor_id not in {"player1", "p1", "玩家一"}:
            from services.wenyou_service import player_tool_use_item

            ok, message, view = player_tool_use_item(uid, actor_id=actor_id, item_ref=item, target_id=target_id, context=action)
            return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)
        from services.wenyou_service import cmd_use_item_with_ai_player, get_session_view

        player_action = f"使用道具【{item}】{f'：{action}' if action else ''}"
        external_ai_player_action, ai_player_error = _maybe_generate_ai_player_action(
            uid,
            external_action=external_ai_player_action,
            player_action=player_action,
            action_intent={"action_type": "use_item", "item": item, "target_id": target_id},
            data=data,
        )
        out, ai_player_action = cmd_use_item_with_ai_player(uid, item, action, ai_player_action=external_ai_player_action)
        failed = out.startswith("文游：")
        payload = {"ok": not failed, "text": out, **get_session_view(uid)}
        if ai_player_action:
            payload["ai_player_action"] = ai_player_action
        if ai_player_error:
            payload["ai_player_error"] = ai_player_error
        return jsonify(payload), (400 if failed else 200)

    @bp.route("/wenyou/item/sell", methods=["POST"])
    def miniapp_wenyou_sell_item():
        """文游：出售回收背包物品，绑定/任务/唯一物禁止。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        item = str(data.get("item") or data.get("item_ref") or data.get("uid") or data.get("id") or "").strip()
        player = str(data.get("player") or data.get("player_id") or data.get("actor_id") or "player1").strip()
        if not item:
            return jsonify({"ok": False, "error": "请选择出售物品"}), 400
        from services.wenyou_service import sell_inventory_item

        ok, message, view = sell_inventory_item(uid, item, player_id=player)
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/ai-player/context", methods=["GET"])
    def miniapp_wenyou_player_tool_context():
        """文游：AI 玩家只读上下文。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        actor_id = str(request.args.get("actor_id") or "player2").strip()
        from services.wenyou_service import get_player_tool_context

        context = get_player_tool_context(uid, actor_id=actor_id)
        if not context:
            return jsonify({"ok": False, "error": "当前没有进行中的文游存档"}), 400
        return jsonify({"ok": True, **context})

    @bp.route("/wenyou/ai-player/buy", methods=["POST"])
    def miniapp_wenyou_player_tool_buy():
        """文游：AI 玩家购买系统商店物品。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        from services.wenyou_service import player_tool_buy_item

        ok, message, view = player_tool_buy_item(
            uid,
            actor_id=str(data.get("actor_id") or "player2"),
            offer_ref=str(data.get("offer_ref") or ""),
            item_id=str(data.get("item_id") or data.get("id") or ""),
            quantity=int(data.get("quantity") or 1),
            reason=str(data.get("reason") or ""),
        )
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/ai-player/gacha", methods=["POST"])
    def miniapp_wenyou_player_tool_gacha():
        """文游：AI 玩家使用自己的积分抽卡。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        from services.wenyou_service import player_tool_roll_gacha

        ok, message, view = player_tool_roll_gacha(
            uid,
            actor_id=str(data.get("actor_id") or "player2"),
            pool_id=str(data.get("pool_id") or data.get("pool") or "mixed"),
            count=int(data.get("count") or 1),
            reason=str(data.get("reason") or ""),
        )
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/ai-player/inventory-action", methods=["POST"])
    def miniapp_wenyou_player_tool_inventory_action():
        """文游：AI 玩家背包动作 use/sell。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        from services.wenyou_service import player_tool_inventory_action

        ok, message, view = player_tool_inventory_action(
            uid,
            actor_id=str(data.get("actor_id") or "player2"),
            action=str(data.get("action") or "use"),
            item_ref=str(data.get("item_ref") or data.get("item") or data.get("uid") or data.get("id") or ""),
            target_id=str(data.get("target_id") or data.get("actor_id") or "player2"),
            context=str(data.get("context") or data.get("reason") or ""),
        )
        return jsonify({"ok": ok, "message": message, **view}), (200 if ok else 400)

    @bp.route("/wenyou/ai-player/transfer", methods=["POST"])
    def miniapp_wenyou_player_tool_transfer():
        """文游：AI 玩家转交积分或物品。"""
        uid = _wenyou_session_id()
        if uid == 0:
            return _missing_wenyou_session_response()
        data = request.get_json(silent=True) or {}
        from services.wenyou_service import player_tool_transfer

        ok, message, view = player_tool_transfer(
            uid,
            actor_id=str(data.get("actor_id") or "player2"),
            target_id=str(data.get("target_id") or "player1"),
            transfer_type=str(data.get("transfer_type") or "item"),
            item_ref=str(data.get("item_ref") or data.get("item") or ""),
            quantity=int(data.get("quantity") or 1),
            amount=int(data.get("amount") or 0),
            message=str(data.get("message") or ""),
        )
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
        external_ai_player_action = str(data.get("ai_player_action") or data.get("companion_action") or data.get("player2_action") or "").strip()
        if not action:
            return jsonify({"ok": False, "error": "请选择遭遇动作"}), 400
        from services.wenyou_service import cmd_encounter_action_with_ai_player, get_session_view

        player_action = detail or f"执行遭遇动作：{action}"
        external_ai_player_action, ai_player_error = _maybe_generate_ai_player_action(
            uid,
            external_action=external_ai_player_action,
            player_action=player_action,
            action_intent={"action_type": action, "target": target, "detail": detail},
            data=data,
        )
        out, ai_player_action = cmd_encounter_action_with_ai_player(
            uid,
            action,
            target=target,
            detail=detail,
            ai_player_action=external_ai_player_action,
        )
        failed = out.startswith("文游：")
        payload = {"ok": not failed, "text": out, **get_session_view(uid)}
        if ai_player_action:
            payload["ai_player_action"] = ai_player_action
        if ai_player_error:
            payload["ai_player_error"] = ai_player_error
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
