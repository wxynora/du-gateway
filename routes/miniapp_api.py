import time
import os
import logging
import json
import re
import threading
from uuid import uuid4
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from config import (
    DATA_DIR,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
)
from storage import r2_store, whitelist_store
from services import codex_group_chat
from utils.ip_allowlist import enforce_ip_allowlist
from utils.miniapp_panel_auth import (
    enforce_panel_token,
)
from utils.telegram_webapp import enforce_telegram_initdata
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing
from routes.miniapp.device_actions import register_routes as register_device_actions_routes
from routes.miniapp.device_state import register_routes as register_device_state_routes
from routes.miniapp.co_read import register_routes as register_co_read_routes
from routes.miniapp.dashboard import register_routes as register_dashboard_routes
from routes.miniapp.diagnostics import register_routes as register_diagnostics_routes
from routes.miniapp.logs import register_routes as register_logs_routes
from routes.miniapp.media import register_routes as register_media_routes
from routes.miniapp.memory_panel import register_routes as register_memory_panel_routes
from routes.miniapp.notes import register_routes as register_notes_routes
from routes.miniapp.panel_auth import register_routes as register_panel_auth_routes
from routes.miniapp.reasoning import register_routes as register_reasoning_routes
from routes.miniapp.schedule import register_routes as register_schedule_routes
from routes.miniapp.settings import register_routes as register_settings_routes
from routes.miniapp.stickers import register_routes as register_stickers_routes
from routes.miniapp.sumitalk_history import register_routes as register_sumitalk_history_routes
from routes.miniapp.upstreams import register_routes as register_upstreams_routes
from routes.miniapp.wenyou import register_routes as register_wenyou_routes


bp = Blueprint("miniapp_api", __name__, url_prefix="/miniapp-api")
register_co_read_routes(bp)
register_dashboard_routes(bp)
register_device_actions_routes(bp)
register_device_state_routes(bp)
register_diagnostics_routes(bp)
register_logs_routes(bp)
register_media_routes(bp)
register_memory_panel_routes(bp)
register_notes_routes(bp)
register_panel_auth_routes(bp)
register_reasoning_routes(bp)
register_schedule_routes(bp)
register_settings_routes(bp)
register_stickers_routes(bp)
register_sumitalk_history_routes(bp)
register_upstreams_routes(bp)
register_wenyou_routes(bp)
logger = logging.getLogger(__name__)
sumitalk_logger = logging.getLogger("sumitalk")
_SUMITALK_CHAT_JOB_DIR = DATA_DIR / "sumitalk_chat_jobs"
_SUMITALK_CHAT_JOB_LOCK = threading.Lock()
_SUMITALK_CHAT_JOB_EVENTS: dict[str, threading.Event] = {}
_SUMITALK_CHAT_JOB_TTL_SECONDS = 30 * 60
_SUMITALK_CHAT_DIRECT_WAIT_MS = 2500


def _resolve_primary_chat_window_id() -> str:
    recent = whitelist_store.list_recent_windows(limit=200) or []
    for w in recent:
        wid = str((w or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


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
    _patch_sumitalk_chat_job_state(job_id, {"status": "running"})
    try:
        from routes.chat import chat_completions

        environ_base = {"REMOTE_ADDR": remote_addr or "127.0.0.1"}
        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base=environ_base,
        ):
            result = chat_completions()
            status_code, data = _extract_chat_completion_result(result)
        if status_code >= 400:
            err = data.get("error") or data.get("message") or f"HTTP {status_code}"
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
        _patch_sumitalk_chat_job_state(
            job_id,
            {
                "status": "done",
                "status_code": status_code,
                "response": data,
            },
        )
    except Exception as e:
        sumitalk_logger.exception("chat_job_failed job_id=%s", job_id)
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
        daemon=True,
    ).start()
    sumitalk_logger.info("chat_job_created job_id=%s window_id=%s target=%s messages=%s", job_id, window_id, reply_target, len(messages))
    return job_id, event, None


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


@bp.before_request
def _miniapp_auth():
    # 双保险：先 IP，再 Telegram initData（更快拒绝无效来源）
    if (
        request.path.rstrip("/").endswith("/panel-auth/meta")
        or request.path.rstrip("/").endswith("/panel-auth/check-password")
        or request.path.rstrip("/").endswith("/panel-auth/verify")
        or request.path.rstrip("/").endswith("/client-error")
        or request.path.rstrip("/").endswith("/tts-preview")
        or request.path.rstrip("/").endswith("/stickers/tags-public")
        or request.path.rstrip("/").endswith("/stickers/resolve")
        or request.path.rstrip("/").endswith("/stickers/raw-public")
        or request.path.rstrip("/").endswith("/device-screenshots/raw-public")
    ):
        enforce_ip_allowlist()
        return None
    enforce_ip_allowlist()
    panel_block = enforce_panel_token()
    if panel_block is not None:
        return panel_block
    if request.environ.get("miniapp_panel_payload"):
        return None
    enforce_telegram_initdata()


@bp.route("/chat-window", methods=["GET"])
def miniapp_chat_window():
    return jsonify({"ok": True, "window_id": _resolve_primary_chat_window_id()})


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
    return jsonify({"ok": True, "job_id": job_id, "status": "running"})


@bp.route("/sumitalk-chat-jobs/<job_id>", methods=["GET"])
def miniapp_sumitalk_chat_job_get(job_id: str):
    job = _read_sumitalk_chat_job_state(job_id)
    if not job:
        return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
    public_job = {k: v for k, v in job.items() if k not in {"created_ts", "updated_ts"}}
    public_job["ok"] = public_job.get("status") != "error"
    return jsonify(public_job)


@bp.route("/codex-group-chat-tasks", methods=["POST"])
def miniapp_codex_group_chat_task_create():
    body = request.get_json(silent=True) or {}
    task = codex_group_chat.create_task(body, device_id=_get_panel_device_id())
    if not task:
        return jsonify({"ok": False, "error": "缺少 window_id / user_message / du_reply，无法创建笨笨群聊任务"}), 400
    return jsonify({"ok": True, "task": task})


@bp.route("/codex-group-chat-tasks/<task_id>", methods=["GET"])
def miniapp_codex_group_chat_task_get(task_id: str):
    task = codex_group_chat.get_task(task_id)
    if not task:
        return jsonify({"ok": False, "error": "笨笨群聊任务不存在或已过期"}), 404
    return jsonify({"ok": True, "task": task})
