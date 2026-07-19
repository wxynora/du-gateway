from __future__ import annotations

import json
from typing import Any, Callable

from flask import jsonify, request

from config import (
    WATCH_ANALYSIS_API_KEY,
    WATCH_ANALYSIS_ENABLED,
    WATCH_ANALYSIS_MAX_REQUEST_BYTES,
    WATCH_ANALYSIS_MODEL,
    WATCH_KNOWLEDGE_API_KEY,
    WATCH_KNOWLEDGE_ENABLED,
    WATCH_KNOWLEDGE_MODEL,
    WATCH_KNOWLEDGE_SEARCH_API_KEY,
    WATCH_VISUAL_CONTEXT_ENABLED,
)
from services.watch_analysis_samples import (
    WatchAnalysisSampleError,
    prepare_samples,
    purge_prepared_samples,
)
from services.watch_analysis_source import (
    WatchAnalysisSourceError,
    get_watch_analysis_source,
    watch_analysis_source_health,
)
from storage import (
    watch_analysis_store,
    watch_knowledge_store,
    watch_runtime_store,
    watch_subtitle_store,
    watch_visual_store,
)


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


def _analysis_upload_body() -> tuple[dict | None, Any | None]:
    if request.content_length and request.content_length > int(WATCH_ANALYSIS_MAX_REQUEST_BYTES) + 1_000_000:
        return None, _json_error("分析样本请求体超过大小限制", "watch_samples_too_large", 413)
    if request.is_json:
        return _json_body()
    raw_metadata = str(request.form.get("metadata") or "").strip()
    if not raw_metadata:
        return None, _json_error("multipart 请求缺少 metadata", "watch_samples_metadata_required", 400)
    try:
        body = json.loads(raw_metadata)
    except Exception:
        return None, _json_error("metadata JSON 无效", "watch_samples_metadata_invalid", 400)
    if not isinstance(body, dict):
        return None, _json_error("metadata 必须是对象", "watch_samples_metadata_invalid", 400)
    samples = body.get("samples")
    if not isinstance(samples, list):
        return None, _json_error("samples 必须是数组", "watch_samples_invalid", 400)
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            continue
        field = str(sample.get("file_field") or f"frame_{index}").strip()
        uploaded = request.files.get(field)
        if uploaded is None:
            continue
        sample["image_bytes"] = uploaded.stream.read(int(WATCH_ANALYSIS_MAX_REQUEST_BYTES) + 1)
        sample["mime_type"] = str(sample.get("mime_type") or uploaded.mimetype or "image/jpeg")
    return body, None


def register_routes(bp):
    @bp.route("/watch/bilibili/parts", methods=["GET"])
    def miniapp_watch_bilibili_parts():
        bvid = str(request.args.get("bvid") or "").strip()
        try:
            page = int(request.args.get("page") or 1)
        except (TypeError, ValueError):
            return _json_error("page 无效", "watch_bilibili_page_invalid", 400)
        if page <= 0:
            return _json_error("page 无效", "watch_bilibili_page_invalid", 400)
        try:
            result = get_watch_analysis_source().describe_parts(
                {"id": f"bili:{bvid}:p{page}"}
            )
        except WatchAnalysisSourceError as exc:
            return _json_error(
                str(exc),
                "watch_bilibili_parts_failed",
                502 if exc.retryable else 400,
            )
        return jsonify({"ok": True, **result})

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
        previous_session, error = _owned_session(session_id)
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
            if applied:
                previous_epoch = int(
                    (previous_session.get("playback") or {}).get("timeline_epoch") or 0
                )
                current_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
                if current_epoch != previous_epoch:
                    watch_analysis_store.reset_for_epoch(
                        session_id,
                        timeline_epoch=current_epoch,
                    )
                    watch_visual_store.delete_session_frames(session_id)
                watch_analysis_store.cancel_stale_jobs(
                    session_id,
                    current_epoch=current_epoch,
                    reason="timeline_epoch_changed",
                )
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
        status["analysis_runtime"] = watch_analysis_store.session_job_runtime(session_id)
        status["sample_plan"] = watch_analysis_store.build_sample_plan(_session)
        status["knowledge_card"] = watch_knowledge_store.get_card_for_session(_session)
        current_epoch = int((_session.get("playback") or {}).get("timeline_epoch") or 0)
        status["visual_frames"] = watch_visual_store.frame_cache_status(
            session_id,
            timeline_epoch=current_epoch,
        )
        requested_visual_mode = str((_session.get("mode") or {}).get("visual_context_mode") or "text_only")
        visual_available = bool(WATCH_VISUAL_CONTEXT_ENABLED and status["visual_frames"]["count"] >= 2)
        status["visual_context"] = {
            "requested_mode": requested_visual_mode,
            "effective_mode": (
                "text_plus_contact_sheet"
                if requested_visual_mode == "text_plus_contact_sheet" and visual_available
                else "text_only"
            ),
            "available": visual_available,
            "degraded_reason": (
                ""
                if requested_visual_mode == "text_only" or visual_available
                else "visual_context_disabled"
                if not WATCH_VISUAL_CONTEXT_ENABLED
                else "frames_not_ready"
            ),
        }
        preparation = status.get("preparation") if isinstance(status.get("preparation"), dict) else {}
        card_status = str(preparation.get("knowledge_card_status") or "pending")
        subtitle_lookup = preparation.get("subtitle_lookup") if isinstance(preparation.get("subtitle_lookup"), dict) else {}
        subtitle_status = str(subtitle_lookup.get("status") or "pending")
        subtitle_ready = subtitle_status in watch_subtitle_store.TERMINAL_STATUSES
        requires_confirmation = not bool(preparation.get("started_at"))
        preparation["can_confirm"] = requires_confirmation and subtitle_ready and (
            card_status == "not_required"
            or (card_status == "ready" and bool(status["knowledge_card"]))
        )
        preparation["can_skip"] = requires_confirmation and subtitle_ready and card_status not in {"not_required"}
        preparation["requires_confirmation"] = requires_confirmation
        status["preparation"] = preparation
        return jsonify({"ok": True, **status})

    @bp.route("/watch/sessions/<session_id>/start", methods=["POST"])
    def miniapp_watch_session_start(session_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        body, error = _json_body()
        if error is not None:
            return error
        action = str(body.get("knowledge_card_action") or "").strip().lower()
        if action not in {"confirm", "skip"}:
            return _json_error(
                "knowledge_card_action 必须是 confirm 或 skip",
                "watch_start_action_required",
                400,
            )

        def _start():
            session = watch_runtime_store.start_session(
                session_id,
                knowledge_card_action=action,
                knowledge_card_key=str(body.get("knowledge_card_key") or "").strip(),
                subtitle_lookup_id=str(body.get("subtitle_lookup_id") or "").strip(),
            )
            return jsonify({"ok": True, "session": session})

        return _handle_store_error(_start)

    @bp.route("/watch/sessions/<session_id>/knowledge-card/regenerate", methods=["POST"])
    def miniapp_watch_knowledge_regenerate(session_id: str):
        session, error = _owned_session(session_id)
        if error is not None:
            return error
        if not WATCH_KNOWLEDGE_ENABLED:
            return _json_error("作品知识卡功能未启用", "watch_knowledge_disabled", 503)
        if str((session.get("preparation") or {}).get("started_at") or "").strip():
            return _json_error(
                "作品知识卡只能在正式开始前重新生成",
                "watch_knowledge_already_started",
                409,
            )

        def _retry():
            watch_subtitle_store.reset_lookup(session_id)
            job = watch_knowledge_store.retry_knowledge_job(session)
            return jsonify({"ok": True, "job": job}), 202

        return _handle_store_error(_retry)

    @bp.route("/watch/sessions/<session_id>/subtitles/retry", methods=["POST"])
    def miniapp_watch_subtitles_retry(session_id: str):
        session, error = _owned_session(session_id)
        if error is not None:
            return error
        if str((session.get("preparation") or {}).get("started_at") or "").strip():
            return _json_error(
                "字幕只能在正式开始前重新查找",
                "watch_subtitles_already_started",
                409,
            )

        def _retry():
            job, _created = watch_subtitle_store.retry_lookup(session)
            return jsonify({"ok": True, "job": job}), 202

        return _handle_store_error(_retry)

    @bp.route("/watch/sessions/<session_id>/analysis/samples", methods=["POST"])
    def miniapp_watch_analysis_samples(session_id: str):
        session, error = _owned_session(session_id)
        if error is not None:
            return error
        if not WATCH_ANALYSIS_ENABLED:
            return _json_error("一起看分析器未启用", "watch_analysis_disabled", 503)
        body, error = _analysis_upload_body()
        if error is not None:
            return error
        purpose = str(body.get("purpose") or "rolling").strip().lower()
        idempotency_key = str(body.get("idempotency_key") or "").strip()
        if idempotency_key:
            existing = watch_analysis_store.get_job_by_idempotency(idempotency_key, public=True)
            if existing:
                if existing.get("session_id") != session_id:
                    return _json_error("idempotency_key 已被其他会话使用", "watch_idempotency_conflict", 409)
                return jsonify({"ok": True, "created": False, "job": existing})
        try:
            requested_epoch = int(body.get("timeline_epoch"))
        except (TypeError, ValueError):
            return _json_error("timeline_epoch 无效", "watch_samples_epoch_invalid", 400)
        current_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
        if requested_epoch != current_epoch:
            return _json_error("播放时间轴已经变化，请重新采样", "watch_samples_stale_epoch", 409)
        raw_samples = body.get("samples")
        if not isinstance(raw_samples, list):
            return _json_error("samples 必须是数组", "watch_samples_invalid", 400)
        prepared: list[dict] = []
        try:
            prepared = prepare_samples(
                session_id=session_id,
                media_id=str((session.get("media") or {}).get("id") or ""),
                timeline_epoch=current_epoch,
                duration_ms=int((session.get("media") or {}).get("duration_ms") or 0),
                purpose=purpose,
                raw_samples=raw_samples,
            )
            job, created = watch_analysis_store.enqueue_samples(
                session=session,
                purpose=purpose,
                samples=prepared,
                idempotency_key=idempotency_key,
                priority=int(body.get("priority") or 0),
            )
            if not created:
                purge_prepared_samples(prepared)
            return jsonify({"ok": True, "created": created, "job": job}), 202 if created else 200
        except WatchAnalysisSampleError as exc:
            purge_prepared_samples(prepared)
            return _json_error(str(exc), "watch_samples_invalid", 400)
        except ValueError as exc:
            purge_prepared_samples(prepared)
            status = 409 if "时间轴" in str(exc) else 400
            return _json_error(str(exc), "watch_analysis_enqueue_failed", status)
        except Exception:
            purge_prepared_samples(prepared)
            raise

    @bp.route("/watch/sessions/<session_id>/analysis/jobs/<job_id>", methods=["GET"])
    def miniapp_watch_analysis_job(session_id: str, job_id: str):
        _session, error = _owned_session(session_id)
        if error is not None:
            return error
        job = watch_analysis_store.get_job(job_id, public=True)
        if job is None or job.get("session_id") != session_id:
            return _json_error("分析任务不存在", "watch_analysis_job_not_found", 404)
        return jsonify({"ok": True, "job": job})

    @bp.route("/watch/analysis/health", methods=["GET"])
    def miniapp_watch_analysis_health():
        return jsonify(
            {
                "ok": True,
                "enabled": bool(WATCH_ANALYSIS_ENABLED),
                "configured": bool(WATCH_ANALYSIS_API_KEY),
                "model": WATCH_ANALYSIS_MODEL,
                "knowledge": {
                    "enabled": bool(WATCH_KNOWLEDGE_ENABLED),
                    "configured": bool(WATCH_KNOWLEDGE_API_KEY and WATCH_KNOWLEDGE_SEARCH_API_KEY),
                    "provider_supported": True,
                    "model": WATCH_KNOWLEDGE_MODEL,
                    "search_provider": "controlled_search_then_model",
                },
                "visual_context_enabled": bool(WATCH_VISUAL_CONTEXT_ENABLED),
                "source": watch_analysis_source_health(),
                "queue": watch_analysis_store.queue_stats(),
            }
        )

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
            watch_analysis_store.cancel_stale_jobs(
                session_id,
                current_epoch=None,
                reason="session_ended",
            )
            watch_visual_store.delete_session_frames(session_id)
            return jsonify({"ok": True, "session": session})

        return _handle_store_error(_end)
