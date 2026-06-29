import time

from flask import jsonify, request

from services.sumitalk_chat_queue import (
    build_sumitalk_chat_job_payload,
    cancel_sumitalk_chat_job,
    maybe_mark_sumitalk_chat_job_stale,
    read_sumitalk_chat_job_state,
    valid_sumitalk_chat_job_id,
)


_SUMITALK_CHAT_DIRECT_WAIT_MS = 2500


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
        return jsonify({"ok": True, "status": "cancelled", "job_id": job_id})
