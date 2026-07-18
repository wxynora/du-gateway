import json
import time

from flask import Response, jsonify, request, stream_with_context

from services.realtime_publish import subscribe_sumitalk_chat_events
from services.sumitalk_voice_sidecar import (
    pending_sumitalk_voice_sidecar_count,
    resume_sumitalk_voice_sidecars,
)
from services.sumitalk_chat_queue import (
    build_sumitalk_chat_job_payload,
    cancel_sumitalk_chat_job,
    get_sumitalk_chat_terminal_event,
    latest_sumitalk_chat_job_event_seq,
    list_sumitalk_chat_job_events,
    maybe_mark_sumitalk_chat_job_stale,
    read_sumitalk_chat_job_state,
    valid_sumitalk_chat_job_id,
)


_SUMITALK_CHAT_DIRECT_WAIT_MS = 2500
_SUMITALK_CHAT_EVENT_WAIT_MAX_MS = 25_000
_SUMITALK_CHAT_EVENT_POLL_SECONDS = 0.04
_SUMITALK_CHAT_EVENT_HEARTBEAT_SECONDS = 15.0
_TERMINAL_EVENT_STATUS = {
    "assistant_final": "done",
    "run_error": "error",
    "run_cancelled": "cancelled",
}


def _response_with_events(job: dict) -> dict:
    response = job.get("response") or {}
    if not isinstance(response, dict):
        return {}
    events = job.get("events") if isinstance(job.get("events"), list) else []
    if not events:
        return response
    return {
        **response,
        "sumitalk_chat_events": response.get("sumitalk_chat_events") or events,
    }


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _start_sumitalk_chat_job_from_request(body: dict):
    panel_device_id = _get_panel_device_id()
    reply_target = str(panel_device_id or body.get("reply_target") or request.headers.get("X-Reply-Target") or "").strip()
    job_id, error, _result = build_sumitalk_chat_job_payload(
        body,
        reply_target=reply_target,
        user_agent=request.headers.get("User-Agent") or "SumiTalk MiniApp",
        force_last4=str(request.headers.get("X-Force-Last4") or body.get("force_last4") or "1"),
        remote_addr=request.remote_addr or "",
    )
    if error is not None:
        return "", (jsonify(error.get("payload") or {"ok": False, "error": "请求无效"}), int(error.get("status") or 400))
    return job_id, None


def _job_payload(job_id: str, *, mode: str = "job") -> tuple[dict, int]:
    job = read_sumitalk_chat_job_state(job_id)
    if not job:
        return {"ok": False, "error": "任务不存在或已过期"}, 404
    job = maybe_mark_sumitalk_chat_job_stale(job_id, job) or job
    status = str(job.get("status") or "running").strip() or "running"
    payload = {
        "ok": status != "error",
        "status": status,
        "mode": mode,
        "job_id": job_id,
    }
    if job.get("stage"):
        payload["stage"] = job.get("stage")
    if job.get("stage_elapsed_ms") is not None:
        payload["stage_elapsed_ms"] = job.get("stage_elapsed_ms")
    if isinstance(job.get("events"), list):
        payload["events"] = job.get("events") or []
        payload["event_seq"] = int(job.get("event_seq") or 0)
    if status == "done":
        payload["response"] = _response_with_events(job)
        payload["status_code"] = int(job.get("status_code") or 200)
    elif status == "error":
        payload["error"] = str(job.get("error") or "渡回复失败")
        payload["status_code"] = int(job.get("status_code") or 500)
        payload["response"] = _response_with_events(job)
    elif status == "cancelled":
        payload["ok"] = False
        payload["error"] = str(job.get("error") or "已取消发送")
        payload["status_code"] = int(job.get("status_code") or 499)
    return payload, 200


def _wait_for_sumitalk_chat_job(job_id: str, wait_s: float) -> tuple[dict, int]:
    deadline = time.time() + max(0.0, wait_s)
    while True:
        payload, http_status = _job_payload(job_id, mode="direct")
        status = str(payload.get("status") or "").strip()
        if http_status >= 400 or status in {"done", "error", "cancelled"}:
            return payload, http_status
        remaining = deadline - time.time()
        if remaining <= 0:
            return payload, 202
        time.sleep(min(0.15, remaining))


def _public_job(job_id: str) -> tuple[dict, int]:
    job = read_sumitalk_chat_job_state(job_id)
    if not job:
        return {"ok": False, "error": "任务不存在或已过期"}, 404
    job = maybe_mark_sumitalk_chat_job_stale(job_id, job) or job
    public_job = {
        k: v
        for k, v in job.items()
        if k
        not in {
            "created_ts",
            "updated_ts",
            "request_key",
        }
    }
    public_job["ok"] = public_job.get("status") not in {"error", "cancelled"}
    return public_job, 200


def _bounded_query_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _event_page(job_id: str, *, after_seq: int, limit: int) -> tuple[dict, int]:
    job = read_sumitalk_chat_job_state(job_id)
    if not job:
        return {"ok": False, "error": "任务不存在或已过期"}, 404
    job = maybe_mark_sumitalk_chat_job_stale(job_id, job) or job
    events = list_sumitalk_chat_job_events(job_id, after_seq=after_seq, limit=limit)
    latest_seq = latest_sumitalk_chat_job_event_seq(job_id)
    terminal_event = get_sumitalk_chat_terminal_event(job_id)
    sidecars_pending = pending_sumitalk_voice_sidecar_count(job_id)
    status = str(job.get("status") or "running").strip().lower() or "running"
    if terminal_event:
        status = _TERMINAL_EVENT_STATUS.get(str(terminal_event.get("kind") or ""), status)
    last_returned_seq = after_seq
    if events:
        try:
            last_returned_seq = int(events[-1].get("seq") or after_seq)
        except Exception:
            last_returned_seq = after_seq
    has_more = latest_seq > last_returned_seq
    if terminal_event and has_more:
        status = "running"
    payload = {
        "ok": status not in {"error", "cancelled"},
        "status": status,
        "job_id": job_id,
        "run_id": job_id,
        "events": events,
        "event_seq": latest_seq,
        "has_more": has_more,
        "sidecars_pending": sidecars_pending,
    }
    if job.get("execution_mode"):
        payload["execution_mode"] = job.get("execution_mode")
    if status == "done":
        payload["response"] = _response_with_events(job)
        payload["status_code"] = int(job.get("status_code") or 200)
    elif status == "error":
        payload["error"] = str(job.get("error") or "渡回复失败")
        payload["status_code"] = int(job.get("status_code") or 500)
        payload["response"] = _response_with_events(job)
    elif status == "cancelled":
        payload["error"] = str(job.get("error") or "已取消发送")
        payload["status_code"] = int(job.get("status_code") or 499)
    return payload, 200


def _wait_for_sumitalk_chat_events(
    job_id: str,
    *,
    after_seq: int,
    limit: int,
    wait_ms: int,
) -> tuple[dict, int]:
    deadline = time.monotonic() + max(0, wait_ms) / 1000.0
    while True:
        payload, http_status = _event_page(job_id, after_seq=after_seq, limit=limit)
        if http_status >= 400 or payload.get("events"):
            return payload, http_status
        if (
            str(payload.get("status") or "") in {"done", "error", "cancelled"}
            and int(payload.get("sidecars_pending") or 0) <= 0
        ):
            return payload, http_status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return payload, http_status
        time.sleep(min(_SUMITALK_CHAT_EVENT_POLL_SECONDS, remaining))


def register_routes(bp) -> None:
    @bp.route("/sumitalk-chat", methods=["POST"])
    def miniapp_sumitalk_chat_adaptive():
        body = request.get_json(silent=True) or {}
        job_id, error_response = _start_sumitalk_chat_job_from_request(body)
        if error_response is not None:
            return error_response
        try:
            wait_ms = int(body.get("wait_ms") or request.args.get("wait_ms") or _SUMITALK_CHAT_DIRECT_WAIT_MS)
        except Exception:
            wait_ms = _SUMITALK_CHAT_DIRECT_WAIT_MS
        payload, http_status = _wait_for_sumitalk_chat_job(job_id, max(0.0, min(8.0, wait_ms / 1000.0)))
        if payload.get("status") == "cancelled":
            return jsonify(payload), 499
        return jsonify(payload), http_status

    @bp.route("/sumitalk-chat-jobs", methods=["POST"])
    def miniapp_sumitalk_chat_job_create():
        body = request.get_json(silent=True) or {}
        job_id, error_response = _start_sumitalk_chat_job_from_request(body)
        if error_response is not None:
            return error_response
        payload, _http_status = _job_payload(job_id, mode="job")
        return jsonify(payload)

    @bp.route("/sumitalk-chat-jobs/<job_id>", methods=["GET"])
    def miniapp_sumitalk_chat_job_get(job_id: str):
        payload, http_status = _public_job(job_id)
        return jsonify(payload), http_status

    @bp.route("/sumitalk-chat-jobs/<job_id>/events", methods=["GET"])
    def miniapp_sumitalk_chat_job_events(job_id: str):
        if not valid_sumitalk_chat_job_id(job_id):
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        after_seq = _bounded_query_int("after_seq", 0, 0, 2_147_483_647)
        limit = _bounded_query_int("limit", 100, 1, 500)
        wait_ms = _bounded_query_int("wait_ms", 0, 0, _SUMITALK_CHAT_EVENT_WAIT_MAX_MS)
        payload, http_status = _wait_for_sumitalk_chat_events(
            job_id,
            after_seq=after_seq,
            limit=limit,
            wait_ms=wait_ms,
        )
        return jsonify(payload), http_status

    @bp.route("/sumitalk-chat-jobs/<job_id>/events/stream", methods=["GET"])
    def miniapp_sumitalk_chat_job_event_stream(job_id: str):
        if not valid_sumitalk_chat_job_id(job_id) or not read_sumitalk_chat_job_state(job_id):
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        after_seq = _bounded_query_int("after_seq", 0, 0, 2_147_483_647)

        @stream_with_context
        def _generate():
            cursor = after_seq
            last_heartbeat = time.monotonic()
            last_state_check = 0.0
            terminal_seen = False
            resume_sumitalk_voice_sidecars(job_id)

            # First connection and reconnect recovery read the durable log once,
            # then the active stream switches to the realtime IPC broker.
            while True:
                recovery_events = list_sumitalk_chat_job_events(job_id, after_seq=cursor, limit=500)
                if not recovery_events:
                    break
                for event in recovery_events:
                    try:
                        seq = int(event.get("seq") or 0)
                    except Exception:
                        continue
                    if seq <= cursor:
                        continue
                    cursor = seq
                    yield "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"
                    if str(event.get("kind") or "") in _TERMINAL_EVENT_STATUS:
                        terminal_seen = True
                if len(recovery_events) < 500:
                    break
            if terminal_seen:
                pending = pending_sumitalk_voice_sidecar_count(job_id)
                if pending <= 0:
                    return
                resume_sumitalk_voice_sidecars(job_id)

            pending_live_event = None
            try:
                for event in subscribe_sumitalk_chat_events(job_id, cursor):
                    if event is None:
                        now = time.monotonic()
                        if now - last_heartbeat >= _SUMITALK_CHAT_EVENT_HEARTBEAT_SECONDS:
                            yield ": ping\n\n"
                            last_heartbeat = now
                        job = read_sumitalk_chat_job_state(job_id)
                        if not job:
                            return
                        if str(job.get("status") or "").strip().lower() in {"done", "error", "cancelled"}:
                            if pending_sumitalk_voice_sidecar_count(job_id) > 0:
                                resume_sumitalk_voice_sidecars(job_id)
                                continue
                            break
                        continue
                    try:
                        seq = int(event.get("seq") or 0)
                    except Exception:
                        continue
                    if seq <= cursor:
                        continue
                    if seq != cursor + 1:
                        pending_live_event = event
                        break
                    cursor = seq
                    yield "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"
                    if str(event.get("kind") or "") in _TERMINAL_EVENT_STATUS:
                        terminal_seen = True
                    if terminal_seen and pending_sumitalk_voice_sidecar_count(job_id) <= 0:
                        return
            except Exception:
                pass

            # IPC unavailable or a sequence gap: use the durable log as the
            # 40 ms compatibility fallback until terminal sidecars are drained.
            while True:
                events = list_sumitalk_chat_job_events(job_id, after_seq=cursor, limit=100)
                for event in events:
                    try:
                        seq = int(event.get("seq") or 0)
                    except Exception:
                        continue
                    if seq <= cursor:
                        continue
                    cursor = seq
                    if str(event.get("kind") or "") in _TERMINAL_EVENT_STATUS:
                        terminal_seen = True
                    yield "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"

                if pending_live_event is not None:
                    try:
                        pending_seq = int(pending_live_event.get("seq") or 0)
                    except Exception:
                        pending_seq = 0
                    if pending_seq == cursor + 1:
                        cursor = pending_seq
                        yield "data: " + json.dumps(
                            pending_live_event,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ) + "\n\n"
                        if str(pending_live_event.get("kind") or "") in _TERMINAL_EVENT_STATUS:
                            terminal_seen = True
                        pending_live_event = None

                terminal_event = get_sumitalk_chat_terminal_event(job_id) if not events else None
                if terminal_event:
                    try:
                        terminal_seq = int(terminal_event.get("seq") or 0)
                    except Exception:
                        terminal_seq = 0
                    if terminal_seq <= cursor:
                        terminal_seen = True

                if terminal_seen:
                    pending = pending_sumitalk_voice_sidecar_count(job_id)
                    if pending <= 0:
                        return
                    resume_sumitalk_voice_sidecars(job_id)

                now = time.monotonic()
                if now - last_state_check >= 2.0:
                    job = read_sumitalk_chat_job_state(job_id)
                    if not job:
                        return
                    job = maybe_mark_sumitalk_chat_job_stale(job_id, job) or job
                    if (
                        str(job.get("status") or "").strip().lower() in {"done", "error", "cancelled"}
                        and not terminal_event
                        and not events
                    ):
                        if pending_sumitalk_voice_sidecar_count(job_id) > 0:
                            resume_sumitalk_voice_sidecars(job_id)
                    last_state_check = now
                if now - last_heartbeat >= _SUMITALK_CHAT_EVENT_HEARTBEAT_SECONDS:
                    yield ": ping\n\n"
                    last_heartbeat = now
                time.sleep(_SUMITALK_CHAT_EVENT_POLL_SECONDS)

        return Response(
            _generate(),
            content_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @bp.route("/sumitalk-chat-jobs/<job_id>/cancel", methods=["POST"])
    def miniapp_sumitalk_chat_job_cancel(job_id: str):
        if not valid_sumitalk_chat_job_id(job_id):
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        job = read_sumitalk_chat_job_state(job_id)
        if not job:
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        status = str(job.get("status") or "").strip().lower()
        if status == "done":
            return jsonify({"ok": True, "status": "done", "job_id": job_id})
        body = request.get_json(silent=True) or {}
        reason = str(body.get("reason") or "client_cancelled").strip()[:160] or "client_cancelled"
        cancel_sumitalk_chat_job(job_id, reason)
        updated, _ = _public_job(job_id)
        updated_status = str(updated.get("status") or "cancelled").strip().lower() or "cancelled"
        return jsonify(
            {
                "ok": updated_status not in {"error"},
                "status": updated_status,
                "job_id": job_id,
            }
        )
