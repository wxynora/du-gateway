import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

from flask import current_app, jsonify, request

from config import DATA_DIR, STREAM_TIMEOUT_SECONDS
from services.upstream_policy import extract_upstream_error_detail
from utils.time_aware import now_beijing_iso


sumitalk_logger = logging.getLogger("sumitalk")
_SUMITALK_CHAT_JOB_DIR = DATA_DIR / "sumitalk_chat_jobs"
_SUMITALK_CHAT_JOB_LOCK = threading.Lock()
_SUMITALK_CHAT_JOB_EVENTS: dict[str, threading.Event] = {}
_SUMITALK_CHAT_JOB_TTL_SECONDS = 30 * 60
_SUMITALK_CHAT_DIRECT_WAIT_MS = 2500
_SUMITALK_CHAT_JOB_STALE_SECONDS = max(60, int(STREAM_TIMEOUT_SECONDS or 300) + 60)


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _sumitalk_chat_job_path(job_id: str) -> Path:
    return _SUMITALK_CHAT_JOB_DIR / f"{job_id}.json"


def _valid_sumitalk_chat_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{32}", str(job_id or "").strip()))


def _safe_sumitalk_client_request_id(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9_.:-]", "", text)[:120]


def _find_sumitalk_chat_job_by_client_request_id(client_request_id: str, window_id: str, reply_target: str) -> dict | None:
    cid = _safe_sumitalk_client_request_id(client_request_id)
    if not cid or not _SUMITALK_CHAT_JOB_DIR.exists():
        return None
    best: dict | None = None
    best_ts = 0.0
    for path in _SUMITALK_CHAT_JOB_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            if not isinstance(data, dict):
                continue
            if _safe_sumitalk_client_request_id(data.get("client_request_id")) != cid:
                continue
            if str(data.get("window_id") or "").strip() != str(window_id or "").strip():
                continue
            if str(data.get("reply_target") or "").strip() != str(reply_target or "").strip():
                continue
            job_id = str(data.get("id") or "").strip()
            if not _valid_sumitalk_chat_job_id(job_id):
                continue
            ts = float(data.get("created_ts") or 0)
            if best is None or ts >= best_ts:
                best = data
                best_ts = ts
        except Exception:
            continue
    return best


def _write_sumitalk_chat_job_state(state: dict) -> None:
    job_id = str((state or {}).get("id") or "").strip()
    if not _valid_sumitalk_chat_job_id(job_id):
        raise ValueError("invalid job id")
    _SUMITALK_CHAT_JOB_DIR.mkdir(parents=True, exist_ok=True)
    path = _sumitalk_chat_job_path(job_id)
    tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(state or {}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_sumitalk_chat_job_state(job_id: str) -> dict | None:
    job_id = str(job_id or "").strip()
    if not _valid_sumitalk_chat_job_id(job_id):
        return None
    path = _sumitalk_chat_job_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _patch_sumitalk_chat_job_state(job_id: str, patch: dict) -> None:
    with _SUMITALK_CHAT_JOB_LOCK:
        current = _read_sumitalk_chat_job_state(job_id) or {"id": job_id, "created_ts": time.time(), "created_at": now_beijing_iso()}
        current.update(patch or {})
        current["updated_ts"] = time.time()
        current["updated_at"] = now_beijing_iso()
        _write_sumitalk_chat_job_state(current)


def _signal_sumitalk_chat_job(job_id: str) -> None:
    with _SUMITALK_CHAT_JOB_LOCK:
        event = _SUMITALK_CHAT_JOB_EVENTS.pop(str(job_id or "").strip(), None)
    if event is not None:
        event.set()


def _cleanup_sumitalk_chat_jobs() -> None:
    try:
        if not _SUMITALK_CHAT_JOB_DIR.exists():
            return
        cutoff = time.time() - max(60, int(_SUMITALK_CHAT_JOB_TTL_SECONDS))
        for path in _SUMITALK_CHAT_JOB_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
                updated_ts = float(data.get("updated_ts") or data.get("created_ts") or 0)
                if updated_ts and updated_ts < cutoff:
                    path.unlink(missing_ok=True)
            except Exception:
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
                except Exception:
                    pass
        with _SUMITALK_CHAT_JOB_LOCK:
            for job_id in list(_SUMITALK_CHAT_JOB_EVENTS.keys()):
                if not _sumitalk_chat_job_path(job_id).exists():
                    _SUMITALK_CHAT_JOB_EVENTS.pop(job_id, None)
    except Exception:
        pass


def _safe_job_log_value(value) -> str:
    text = str(value if value is not None else "").replace("\n", " ").replace("\r", " ").strip()
    return text[:160]


def _format_job_log_fields(fields: dict) -> str:
    parts = []
    for key, value in (fields or {}).items():
        k = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(key or "").strip())[:50]
        if not k:
            continue
        parts.append(f"{k}={_safe_job_log_value(value)}")
    return " ".join(parts)


def _sumitalk_chat_job_elapsed_ms(state: dict | None) -> int:
    try:
        created_ts = float((state or {}).get("created_ts") or time.time())
        return max(0, int((time.time() - created_ts) * 1000))
    except Exception:
        return 0


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True


def _maybe_mark_sumitalk_chat_job_stale(job_id: str, state: dict | None = None) -> dict | None:
    state = state if isinstance(state, dict) else _read_sumitalk_chat_job_state(job_id)
    if not isinstance(state, dict):
        return state
    status = str(state.get("status") or "").strip().lower()
    if status not in {"running", "queued", "pending"}:
        return state

    worker_pid = 0
    try:
        worker_pid = int(state.get("worker_pid") or 0)
    except Exception:
        worker_pid = 0
    updated_ts = 0.0
    try:
        updated_ts = float(state.get("updated_ts") or state.get("created_ts") or 0)
    except Exception:
        updated_ts = 0.0

    reason = ""
    stage = "job_stale"
    if worker_pid and not _pid_exists(worker_pid):
        reason = f"任务所在 worker 已结束，请重发（pid={worker_pid}）"
        stage = "worker_lost"
    elif updated_ts and time.time() - updated_ts > _SUMITALK_CHAT_JOB_STALE_SECONDS:
        reason = "任务长时间没有更新，请重发"
    if not reason:
        return state

    elapsed_ms = _sumitalk_chat_job_elapsed_ms(state)
    _patch_sumitalk_chat_job_state(
        job_id,
        {
            "status": "error",
            "status_code": 504,
            "stage": stage,
            "stage_elapsed_ms": elapsed_ms,
            "stage_updated_at": now_beijing_iso(),
            "error": reason,
            "stale_detected_at": now_beijing_iso(),
        },
    )
    _signal_sumitalk_chat_job(job_id)
    sumitalk_logger.warning(
        "[SumiTalk] chat_job_marked_stale job_id=%s status=%s stage=%s elapsed_ms=%s worker_pid=%s reason=%s",
        job_id,
        status,
        stage,
        elapsed_ms,
        worker_pid,
        reason,
    )
    return _read_sumitalk_chat_job_state(job_id)


def _is_sumitalk_chat_job_cancelled(job_id: str) -> bool:
    state = _maybe_mark_sumitalk_chat_job_stale(job_id) or {}
    return str(state.get("status") or "").strip().lower() == "cancelled"


def _set_sumitalk_chat_job_stage(job_id: str, stage: str, **fields) -> None:
    stage_text = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(stage or "").strip())[:80] or "unknown"
    state = _read_sumitalk_chat_job_state(job_id) or {}
    elapsed_ms = _sumitalk_chat_job_elapsed_ms(state)
    patch = {
        "stage": stage_text,
        "stage_elapsed_ms": elapsed_ms,
        "stage_updated_at": now_beijing_iso(),
    }
    _patch_sumitalk_chat_job_state(job_id, patch)
    sumitalk_logger.info(
        "[SumiTalk] chat_job_stage job_id=%s status=%s stage=%s elapsed_ms=%s %s",
        job_id,
        str(state.get("status") or "").strip() or "unknown",
        stage_text,
        elapsed_ms,
        _format_job_log_fields(fields),
    )


def _extract_chat_completion_result(result) -> tuple[int, dict]:
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


def _run_sumitalk_chat_job(app, job_id: str, chat_body: dict, headers: dict, remote_addr: str) -> None:
    _patch_sumitalk_chat_job_state(
        job_id,
        {
            "status": "running",
            "worker_pid": os.getpid(),
            "worker_started_at": now_beijing_iso(),
        },
    )
    _set_sumitalk_chat_job_stage(
        job_id,
        "worker_started",
        model=chat_body.get("model") or "",
        messages=len(chat_body.get("messages") or []) if isinstance(chat_body.get("messages"), list) else 0,
        window_id=chat_body.get("window_id") or "",
    )
    try:
        if _is_sumitalk_chat_job_cancelled(job_id):
            _set_sumitalk_chat_job_stage(job_id, "cancelled_before_gateway_call")
            return
        from routes.chat import chat_completions

        environ_base = {"REMOTE_ADDR": remote_addr or "127.0.0.1"}
        _set_sumitalk_chat_job_stage(job_id, "gateway_call_start")
        call_started = time.time()
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base=environ_base,
        ):
            result = chat_completions()
            status_code, data = _extract_chat_completion_result(result)
        gateway_ms = int((time.time() - call_started) * 1000)
        _set_sumitalk_chat_job_stage(
            job_id,
            "gateway_call_returned",
            status_code=status_code,
            gateway_ms=gateway_ms,
            response_keys=",".join(list(data.keys())[:8]) if isinstance(data, dict) else "",
        )
        if _is_sumitalk_chat_job_cancelled(job_id):
            _set_sumitalk_chat_job_stage(job_id, "cancelled_after_gateway_return")
            return
        if status_code >= 400:
            err = extract_upstream_error_detail(data, status_code) or f"HTTP {status_code}"
            _set_sumitalk_chat_job_stage(job_id, "gateway_call_error", status_code=status_code, error=err)
            _patch_sumitalk_chat_job_state(
                job_id,
                {
                    "status": "error",
                    "status_code": status_code,
                    "error": str(err),
                    "response": data,
                },
            )
            return
        _set_sumitalk_chat_job_stage(job_id, "reply_ready", status_code=status_code)
        _patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "done",
                "status_code": status_code,
                "response": data,
            },
        )
    except Exception as e:
        sumitalk_logger.exception("[SumiTalk] chat_job_failed job_id=%s", job_id)
        try:
            _set_sumitalk_chat_job_stage(job_id, "worker_exception", error=e)
        except Exception:
            pass
        _patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "error",
                "status_code": 500,
                "error": str(e),
            },
        )
    finally:
        _signal_sumitalk_chat_job(job_id)


def _start_sumitalk_chat_job_from_request(body: dict, waitable: bool = False):
    model = str(body.get("model") or "").strip()
    messages = body.get("messages") or []
    window_id = str(body.get("window_id") or "").strip()
    reply_target = str(body.get("reply_target") or request.headers.get("X-Reply-Target") or _get_panel_device_id()).strip()
    client_request_id = _safe_sumitalk_client_request_id(body.get("client_request_id"))
    if not model:
        return "", None, (jsonify({"ok": False, "error": "缺少 model"}), 400)
    if not isinstance(messages, list) or not messages:
        return "", None, (jsonify({"ok": False, "error": "缺少 messages"}), 400)
    if not window_id:
        return "", None, (jsonify({"ok": False, "error": "缺少 window_id"}), 400)
    _cleanup_sumitalk_chat_jobs()
    existing = _find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
    if existing:
        existing_job_id = str(existing.get("id") or "").strip()
        existing = _maybe_mark_sumitalk_chat_job_stale(existing_job_id, existing) or existing
        event = None
        if waitable:
            with _SUMITALK_CHAT_JOB_LOCK:
                event = _SUMITALK_CHAT_JOB_EVENTS.get(existing_job_id)
        sumitalk_logger.info(
            "chat_job_reused job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
            existing_job_id,
            client_request_id,
            window_id,
            reply_target,
            str(existing.get("status") or ""),
        )
        return existing_job_id, event, None
    with _SUMITALK_CHAT_JOB_LOCK:
        existing = _find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
        if existing:
            existing_job_id = str(existing.get("id") or "").strip()
            event = _SUMITALK_CHAT_JOB_EVENTS.get(existing_job_id) if waitable else None
            sumitalk_logger.info(
                "chat_job_reused job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
                existing_job_id,
                client_request_id,
                window_id,
                reply_target,
                str(existing.get("status") or ""),
            )
            return existing_job_id, event, None
        job_id = uuid4().hex
    chat_body = dict(body)
    chat_body["model"] = model
    chat_body["messages"] = messages
    chat_body["window_id"] = window_id
    chat_body["stream"] = False
    chat_body.pop("reply_target", None)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": request.headers.get("User-Agent") or "SumiTalk MiniApp",
        "X-Force-Last4": str(request.headers.get("X-Force-Last4") or body.get("force_last4") or "1"),
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": reply_target,
        "X-Window-Id": window_id,
    }
    state = {
        "id": job_id,
        "ok": True,
        "status": "running",
        "stage": "created",
        "stage_elapsed_ms": 0,
        "created_ts": time.time(),
        "updated_ts": time.time(),
        "created_at": now_beijing_iso(),
        "updated_at": now_beijing_iso(),
        "client_request_id": client_request_id,
        "window_id": window_id,
        "reply_target": reply_target,
    }
    event = threading.Event() if waitable else None
    with _SUMITALK_CHAT_JOB_LOCK:
        existing = _find_sumitalk_chat_job_by_client_request_id(client_request_id, window_id, reply_target)
        if existing:
            existing_job_id = str(existing.get("id") or "").strip()
            existing_event = _SUMITALK_CHAT_JOB_EVENTS.get(existing_job_id) if waitable else None
            sumitalk_logger.info(
                "chat_job_reused_after_race job_id=%s client_request_id=%s window_id=%s target=%s status=%s",
                existing_job_id,
                client_request_id,
                window_id,
                reply_target,
                str(existing.get("status") or ""),
            )
            return existing_job_id, existing_event, None
        if event is not None:
            _SUMITALK_CHAT_JOB_EVENTS[job_id] = event
        _write_sumitalk_chat_job_state(state)
    app = current_app._get_current_object()
    remote_addr = request.remote_addr or ""
    threading.Thread(
        target=_run_sumitalk_chat_job,
        args=(app, job_id, chat_body, headers, remote_addr),
        name=f"sumitalk-chat-job-{job_id[:8]}",
        daemon=False,
    ).start()
    sumitalk_logger.info(
        "[SumiTalk] chat_job_created job_id=%s window_id=%s target=%s messages=%s client_request_id=%s",
        job_id,
        window_id,
        reply_target,
        len(messages),
        client_request_id,
    )
    return job_id, event, None


def register_routes(bp) -> None:
    @bp.route("/sumitalk-chat", methods=["POST"])
    def miniapp_sumitalk_chat_adaptive():
        body = request.get_json(silent=True) or {}
        job_id, event, error_response = _start_sumitalk_chat_job_from_request(body, waitable=True)
        if error_response is not None:
            return error_response
        try:
            wait_ms = int(body.get("wait_ms") or request.args.get("wait_ms") or _SUMITALK_CHAT_DIRECT_WAIT_MS)
        except Exception:
            wait_ms = _SUMITALK_CHAT_DIRECT_WAIT_MS
        wait_s = max(0.0, min(8.0, wait_ms / 1000.0))
        job = _read_sumitalk_chat_job_state(job_id) or {}
        status = str(job.get("status") or "").strip()
        if status == "done":
            return jsonify({
                "ok": True,
                "status": "done",
                "mode": "direct",
                "job_id": job_id,
                "status_code": int(job.get("status_code") or 200),
                "response": job.get("response") or {},
            })
        if status == "error":
            return jsonify({
                "ok": False,
                "status": "error",
                "mode": "direct",
                "job_id": job_id,
                "status_code": int(job.get("status_code") or 500),
                "error": str(job.get("error") or "渡回复失败"),
                "response": job.get("response") or {},
            })
        if status == "cancelled":
            return jsonify({
                "ok": False,
                "status": "cancelled",
                "mode": "direct",
                "job_id": job_id,
                "status_code": int(job.get("status_code") or 499),
                "error": str(job.get("error") or "已取消发送"),
            }), 499
        if event is not None and event.wait(wait_s):
            job = _read_sumitalk_chat_job_state(job_id) or {}
            status = str(job.get("status") or "").strip()
            if status == "done":
                return jsonify({
                    "ok": True,
                    "status": "done",
                    "mode": "direct",
                    "job_id": job_id,
                    "status_code": int(job.get("status_code") or 200),
                    "response": job.get("response") or {},
                })
            if status == "cancelled":
                return jsonify({
                    "ok": False,
                    "status": "cancelled",
                    "mode": "direct",
                    "job_id": job_id,
                    "status_code": int(job.get("status_code") or 499),
                    "error": str(job.get("error") or "已取消发送"),
                }), 499
            if status == "error":
                return jsonify({
                    "ok": False,
                    "status": "error",
                    "mode": "direct",
                    "job_id": job_id,
                    "status_code": int(job.get("status_code") or 500),
                    "error": str(job.get("error") or "渡回复失败"),
                    "response": job.get("response") or {},
                })
        return jsonify({"ok": True, "status": "running", "mode": "job", "job_id": job_id}), 202

    @bp.route("/sumitalk-chat-jobs", methods=["POST"])
    def miniapp_sumitalk_chat_job_create():
        body = request.get_json(silent=True) or {}
        job_id, _event, error_response = _start_sumitalk_chat_job_from_request(body, waitable=False)
        if error_response is not None:
            return error_response
        job = _maybe_mark_sumitalk_chat_job_stale(job_id) or {}
        status = str(job.get("status") or "running").strip() or "running"
        payload = {"ok": status != "error", "job_id": job_id, "status": status}
        if status == "done":
            payload["response"] = job.get("response") or {}
            payload["status_code"] = int(job.get("status_code") or 200)
        elif status == "error":
            payload["error"] = str(job.get("error") or "渡回复失败")
            payload["status_code"] = int(job.get("status_code") or 500)
            payload["response"] = job.get("response") or {}
        return jsonify(payload)

    @bp.route("/sumitalk-chat-jobs/<job_id>", methods=["GET"])
    def miniapp_sumitalk_chat_job_get(job_id: str):
        job = _read_sumitalk_chat_job_state(job_id)
        if not job:
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        job = _maybe_mark_sumitalk_chat_job_stale(job_id, job) or job
        public_job = {k: v for k, v in job.items() if k not in {"created_ts", "updated_ts"}}
        public_job["ok"] = public_job.get("status") != "error"
        return jsonify(public_job)

    @bp.route("/sumitalk-chat-jobs/<job_id>/cancel", methods=["POST"])
    def miniapp_sumitalk_chat_job_cancel(job_id: str):
        if not _valid_sumitalk_chat_job_id(job_id):
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        job = _read_sumitalk_chat_job_state(job_id)
        if not job:
            return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
        status = str(job.get("status") or "").strip().lower()
        if status == "done":
            return jsonify({"ok": True, "status": "done", "job_id": job_id})
        body = request.get_json(silent=True) or {}
        reason = str(body.get("reason") or "client_cancelled").strip()[:160] or "client_cancelled"
        elapsed_ms = _sumitalk_chat_job_elapsed_ms(job)
        _patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "cancelled",
                "stage": "client_cancelled",
                "stage_elapsed_ms": elapsed_ms,
                "stage_updated_at": now_beijing_iso(),
                "error": reason,
                "cancelled_at": now_beijing_iso(),
            },
        )
        _signal_sumitalk_chat_job(job_id)
        sumitalk_logger.warning(
            "[SumiTalk] chat_job_cancelled job_id=%s previous_status=%s elapsed_ms=%s reason=%s",
            job_id,
            status or "unknown",
            elapsed_ms,
            reason,
        )
        return jsonify({"ok": True, "status": "cancelled", "job_id": job_id})
