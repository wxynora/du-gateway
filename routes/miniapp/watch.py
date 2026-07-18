from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request

from storage import watch_runtime_store


def _json_error(error: str, code: str, status: int):
    return jsonify({"ok": False, "code": code, "error": error}), status


def _json_body() -> tuple[dict | None, Any | None]:
    if not request.is_json:
        return None, _json_error("需要 application/json", "json_required", 400)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, _json_error("JSON 必须是对象", "json_invalid", 400)
    return body, None


def _panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _owned_session(session_id: str) -> tuple[dict | None, Any | None]:
    session = watch_runtime_store.get_session(session_id)
    if session is None:
        return None, _json_error("观看会话不存在或已过期", "watch_session_not_found", 404)
    current_device_id = _panel_device_id()
    owner_device_id = str(session.get("device_id") or "").strip()
    if current_device_id and owner_device_id and current_device_id != owner_device_id:
        return None, _json_error("不能访问其他设备的观看会话", "watch_session_forbidden", 403)
    return session, None


def _handle_store_error(call: Callable[[], Any]):
    try:
        return call()
    except KeyError:
        return _json_error("观看会话不存在或已过期", "watch_session_not_found", 404)
    except ValueError as exc:
        return _json_error(str(exc), "watch_request_invalid", 400)


def register_routes(bp):
    @bp.route("/watch/sessions", methods=["POST"])
    def miniapp_watch_session_create():
        body, error = _json_body()
        if error is not None:
            return error
        media = body.get("media")
        mode = body.get("mode")
        companion = body.get("companion") or {}
        if not isinstance(media, dict):
            return _json_error("media 必须是对象", "watch_media_required", 400)
        if not isinstance(mode, dict):
            return _json_error("播放前必须明确选择 mode", "watch_mode_required", 400)
        if "knowledge_mode" not in mode or "fear_mode" not in mode:
            return _json_error(
                "播放前必须明确选择 knowledge_mode 和 fear_mode",
                "watch_mode_incomplete",
                400,
            )
        if not isinstance(companion, dict):
            return _json_error("companion 必须是对象", "watch_companion_invalid", 400)
        window_id = str(body.get("window_id") or "").strip()
        if not window_id:
            return _json_error("window_id 不能为空", "watch_window_required", 400)

        def _create():
            session = watch_runtime_store.create_session(
                device_id=_panel_device_id(),
                window_id=window_id,
                companion=companion,
                media=media,
                mode=mode,
            )
            return jsonify({"ok": True, "session": session}), 201

        return _handle_store_error(_create)

    @bp.route("/watch/sessions", methods=["GET"])
    def miniapp_watch_session_list():
        try:
            limit = int(request.args.get("limit") or 20)
        except (TypeError, ValueError):
            return _json_error("limit 无效", "watch_request_invalid", 400)
        sessions = watch_runtime_store.list_sessions(
            device_id=_panel_device_id(),
            window_id=str(request.args.get("window_id") or "").strip(),
            include_ended=str(request.args.get("include_ended") or "").strip().lower()
            in {"1", "true", "yes"},
            limit=limit,
        )
        return jsonify({"ok": True, "sessions": sessions})

    @bp.route("/watch/sessions/<session_id>", methods=["GET"])
    def miniapp_watch_session_get(session_id: str):
        session, error = _owned_session(session_id)
        if error is not None:
            return error
        return jsonify({"ok": True, "session": session})

    @bp.route("/watch/sessions/<session_id>/playback", methods=["PUT"])
    def miniapp_watch_session_playback(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        body, error = _json_body()
        if error is not None:
            return error
        required = {
            "media_id",
            "playhead_ms",
            "is_playing",
            "playback_rate",
            "timeline_epoch",
            "snapshot_seq",
            "captured_at",
        }
        missing = sorted(key for key in required if key not in body)
        if missing:
            return _json_error(
                f"缺少播放快照字段: {', '.join(missing)}",
                "watch_snapshot_incomplete",
                400,
            )

        def _update():
            session, applied, ignored_reason = watch_runtime_store.update_playback(session_id, body)
            return jsonify(
                {
                    "ok": True,
                    "applied": applied,
                    "ignored_reason": ignored_reason,
                    "session": session,
                }
            )

        return _handle_store_error(_update)

    @bp.route("/watch/sessions/<session_id>/status", methods=["GET"])
    def miniapp_watch_session_status(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        status = watch_runtime_store.get_status(session_id)
        if status is None:
            return _json_error("观看会话不存在或已过期", "watch_session_not_found", 404)
        return jsonify({"ok": True, **status})

    @bp.route("/watch/sessions/<session_id>/mode", methods=["PUT"])
    def miniapp_watch_session_mode(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        body, error = _json_body()
        if error is not None:
            return error
        mode = body.get("mode", body)
        if not isinstance(mode, dict) or not mode:
            return _json_error("mode 不能为空", "watch_mode_required", 400)

        def _update():
            session = watch_runtime_store.update_mode(session_id, mode)
            return jsonify({"ok": True, "session": session})

        return _handle_store_error(_update)

    @bp.route("/watch/sessions/<session_id>/timeline-sections", methods=["PUT"])
    def miniapp_watch_timeline_sections(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        body, error = _json_body()
        if error is not None:
            return error
        sections = body.get("sections")
        if not isinstance(sections, list):
            return _json_error("sections 必须是数组", "watch_sections_invalid", 400)

        def _replace():
            saved = watch_runtime_store.replace_timeline_sections(
                session_id,
                sections,
                timeline_epoch=body.get("timeline_epoch"),
            )
            return jsonify({"ok": True, "timeline_sections": saved})

        return _handle_store_error(_replace)

    @bp.route("/watch/sessions/<session_id>/risk-feedback", methods=["POST"])
    def miniapp_watch_risk_feedback(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        body, error = _json_body()
        if error is not None:
            return error
        feedback_type = str(body.get("feedback_type") or "").strip()
        if not feedback_type:
            return _json_error("feedback_type 不能为空", "watch_feedback_required", 400)

        def _save():
            feedback = watch_runtime_store.record_risk_feedback(
                session_id,
                device_id=_panel_device_id(),
                feedback_type=feedback_type,
                risk_event_id=str(body.get("risk_event_id") or "").strip(),
                playhead_ms=body.get("playhead_ms") or 0,
                note=str(body.get("note") or ""),
            )
            return jsonify({"ok": True, "feedback": feedback}), 201

        return _handle_store_error(_save)

    @bp.route("/watch/sessions/<session_id>", methods=["DELETE"])
    def miniapp_watch_session_end(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error

        def _end():
            session = watch_runtime_store.end_session(session_id)
            return jsonify({"ok": True, "session": session})

        return _handle_store_error(_end)
