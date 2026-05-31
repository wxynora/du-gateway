from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

from config import DATA_DIR
from utils.log import get_logger
from utils.time_aware import now_beijing_iso


_TASK_FILE = DATA_DIR / "codex_group_chat_tasks.json"
_LOCK = threading.Lock()
_MAX_TASKS = 200
_TASK_TTL_SECONDS = 2 * 24 * 60 * 60
_RUNNING_RECLAIM_SECONDS = max(
    60,
    int(float(os.environ.get("CODEX_GROUP_CHAT_RUNNING_RECLAIM_SECONDS") or "120")),
)
logger = get_logger(__name__)


def _load_state() -> dict:
    try:
        if not _TASK_FILE.exists():
            return {"tasks": []}
        data = json.loads(_TASK_FILE.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return {"tasks": []}
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            data["tasks"] = []
        return data
    except Exception:
        return {"tasks": []}


def _save_state(data: dict) -> bool:
    try:
        _TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _TASK_FILE.with_name(f"{_TASK_FILE.name}.{uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data or {"tasks": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_TASK_FILE)
        return True
    except Exception:
        return False


def _now_ts() -> float:
    return time.time()


def _safe_text(value, max_chars: int = 12000) -> str:
    text = str(value or "").strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n...[truncated]"
    return text


def _safe_role(value) -> str:
    role = str(value or "").strip().lower()
    if role in {"user", "assistant", "benben"}:
        return role
    return "assistant"


def _safe_mode(value) -> str:
    mode = str(value or "").strip()
    if mode in {"daily_chat", "studyroom", "coding_task"}:
        return mode
    return "daily_chat"


def _normalize_recent_messages(items) -> list[dict]:
    out: list[dict] = []
    if not isinstance(items, list):
        return out
    for item in items[-18:]:
        if not isinstance(item, dict):
            continue
        content = _safe_text(item.get("content"), 4000)
        if not content:
            continue
        row = {
            "role": _safe_role(item.get("role")),
            "content": content,
        }
        created_at = str(item.get("createdAt") or item.get("created_at") or "").strip()
        if created_at:
            row["createdAt"] = created_at
        out.append(row)
    return out


def _normalize_target_mentions(items) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        value = str(item or "").strip().lower()
        if value not in {"du", "benben"} or value in out:
            continue
        out.append(value)
    return out


def _safe_coding_thread_key(value, user_message: str = "") -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_.:-]", "_", raw)[:80].strip("_")
    if raw:
        return raw
    text = str(user_message or "").lower()
    if re.search(r"文游|主神|副本|玩家|道具|抽卡|结算|怪物|npc|wenyou", text):
        return "wenyou"
    if re.search(r"miniapp|小程序|前端|页面|界面|按钮|气泡|样式|ui|tsx|react", text):
        return "miniapp"
    if re.search(r"studyroom|学习|题库|错题|资料整理", text):
        return "studyroom"
    if re.search(r"小爱|音箱|migpt|xiaoai", text):
        return "xiaoai"
    if re.search(r"后端|接口|路由|网关|存储|r2|api|service|route", text):
        return "backend"
    if re.search(r"文档|方案|markdown|debug_index|索引", text):
        return "docs"
    return "general"


def _public_task(task: dict | None) -> dict | None:
    if not isinstance(task, dict):
        return None
    keep = {
        "id",
        "ok",
        "status",
        "mode",
        "window_id",
        "reply_target",
        "created_at",
        "updated_at",
        "claimed_at",
        "finished_at",
        "worker_id",
        "response",
        "error",
        "target_mentions",
        "client_request_id",
        "coding_thread_key",
        "cancel_reason",
        "cancelled_at",
    }
    return {k: task.get(k) for k in keep if k in task}


def _publish_task(task: dict | None) -> None:
    public = _public_task(task)
    if not public:
        return
    try:
        from services.realtime_publish import publish_codex_group_task

        publish_codex_group_task(public)
    except Exception:
        pass


def _sync_studyroom_task_result(task: dict | None) -> None:
    if not isinstance(task, dict) or str(task.get("mode") or "") != "studyroom":
        return
    item_id = str(task.get("study_item_id") or "").strip()
    if not item_id:
        return
    status = str(task.get("status") or "").strip()
    try:
        from storage import r2_store

        if status == "done":
            response = _safe_text(task.get("response"), 16000)
            if not response:
                updated = r2_store.update_studyroom_item(item_id, {"status": "todo"})
                logger.warning("StudyRoom 整理结果为空，已退回 todo item_id=%s task_id=%s", item_id, task.get("id"))
            else:
                updated = r2_store.update_studyroom_item(item_id, {"note": response, "status": "done"})
                logger.info("StudyRoom 整理结果已写回 item_id=%s task_id=%s chars=%s", item_id, task.get("id"), len(response))
        elif status == "error":
            updated = r2_store.update_studyroom_item(item_id, {"status": "todo"})
            logger.warning(
                "StudyRoom 整理失败，已退回 todo item_id=%s task_id=%s error=%s",
                item_id,
                task.get("id"),
                _safe_text(task.get("error"), 300),
            )
        else:
            return
        if not updated:
            logger.error("StudyRoom 整理结果写回失败 item_id=%s task_id=%s status=%s", item_id, task.get("id"), status)
    except Exception:
        logger.exception("StudyRoom 整理结果写回异常 item_id=%s task_id=%s", item_id, task.get("id"))


def _cleanup_tasks(tasks: list[dict]) -> list[dict]:
    cutoff = _now_ts() - _TASK_TTL_SECONDS
    kept = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "").strip()
        updated_ts = float(task.get("updated_ts") or task.get("created_ts") or 0)
        if status in {"done", "error", "cancelled"} and updated_ts and updated_ts < cutoff:
            continue
        kept.append(task)
    return kept[-_MAX_TASKS:]


def create_task(body: dict, device_id: str = "") -> dict | None:
    now_ts = _now_ts()
    mode = _safe_mode((body or {}).get("mode") or "daily_chat")
    user_message_limit = 20000 if mode == "studyroom" else 12000 if mode == "coding_task" else 6000
    task = {
        "id": uuid4().hex,
        "ok": True,
        "status": "queued",
        "mode": mode,
        "created_ts": now_ts,
        "updated_ts": now_ts,
        "created_at": now_beijing_iso(),
        "updated_at": now_beijing_iso(),
        "window_id": str((body or {}).get("window_id") or "").strip(),
        "reply_target": str((body or {}).get("reply_target") or device_id or "").strip(),
        "user_message": _safe_text((body or {}).get("user_message"), user_message_limit),
        "du_reply": _safe_text((body or {}).get("du_reply"), 12000),
        "recent_messages": _normalize_recent_messages((body or {}).get("recent_messages")),
        "target_mentions": _normalize_target_mentions((body or {}).get("target_mentions")),
        "client_request_id": re.sub(r"[^a-zA-Z0-9_.:-]", "", str((body or {}).get("client_request_id") or "").strip())[:120],
    }
    if mode == "coding_task":
        task["coding_thread_key"] = _safe_coding_thread_key((body or {}).get("coding_thread_key"), task["user_message"])
    if mode == "studyroom":
        task["study_item_id"] = re.sub(r"[^a-zA-Z0-9_.:-]", "", str((body or {}).get("study_item_id") or (body or {}).get("exam_item_id") or "").strip())[:120]
        task["study_title"] = _safe_text((body or {}).get("study_title") or (body or {}).get("exam_title"), 240)
        task["study_module"] = _safe_text((body or {}).get("study_module") or (body or {}).get("exam_module"), 120)
        task["study_source"] = _safe_text((body or {}).get("study_source") or (body or {}).get("exam_source"), 120)
        task["study_url"] = _safe_text((body or {}).get("study_url") or (body or {}).get("exam_url"), 1000)
        if not task["window_id"]:
            task["window_id"] = "studyroom"
        if not task["user_message"]:
            return None
    elif not task["window_id"] or not task["user_message"]:
        return None
    with _LOCK:
        state = _load_state()
        state["tasks"] = _cleanup_tasks(state.get("tasks") or [])
        client_request_id = str(task.get("client_request_id") or "").strip()
        if client_request_id:
            for existing in reversed(state["tasks"]):
                if str((existing or {}).get("client_request_id") or "").strip() == client_request_id:
                    return _public_task(existing)
        state["tasks"].append(task)
        if not _save_state(state):
            return None
    public = _public_task(task)
    _publish_task(public)
    return public


def get_task(task_id: str) -> dict | None:
    task_id = str(task_id or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    with _LOCK:
        state = _load_state()
        for task in state.get("tasks") or []:
            if str((task or {}).get("id") or "") == task_id:
                return _public_task(task)
    return None


def list_tasks(limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit or 20), 100))
    with _LOCK:
        state = _load_state()
        tasks = _cleanup_tasks(state.get("tasks") or [])
        return [t for t in (_public_task(task) for task in tasks[-limit:]) if t]


def _is_stale_running(task: dict, now_ts: float) -> bool:
    if str(task.get("status") or "") != "running":
        return False
    claimed_ts = float(task.get("claimed_ts") or task.get("updated_ts") or 0)
    return bool(claimed_ts and now_ts - claimed_ts >= _RUNNING_RECLAIM_SECONDS)


def claim_next(worker_id: str = "") -> dict | None:
    now_ts = _now_ts()
    with _LOCK:
        state = _load_state()
        tasks = _cleanup_tasks(state.get("tasks") or [])
        selected: dict | None = None
        for task in tasks:
            if str(task.get("status") or "") == "queued" or _is_stale_running(task, now_ts):
                selected = task
                break
        if selected is None:
            state["tasks"] = tasks
            _save_state(state)
            return None
        selected["status"] = "running"
        if selected.get("worker_id"):
            selected["previous_worker_id"] = selected.get("worker_id")
        selected["worker_id"] = str(worker_id or "").strip()[:80]
        selected["reclaimed_count"] = int(float(selected.get("reclaimed_count") or 0)) + (1 if selected.get("claimed_ts") else 0)
        selected["claimed_ts"] = now_ts
        selected["updated_ts"] = now_ts
        selected["claimed_at"] = now_beijing_iso()
        selected["updated_at"] = now_beijing_iso()
        state["tasks"] = tasks
        if not _save_state(state):
            return None
        public = _public_task(selected)
        _publish_task(public)
        return public


def cancel_task(task_id: str, reason: str = "") -> dict | None:
    task_id = str(task_id or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    now_ts = _now_ts()
    cancel_reason = _safe_text(reason or "user_cancelled", 1000)
    with _LOCK:
        state = _load_state()
        tasks = _cleanup_tasks(state.get("tasks") or [])
        found = None
        for task in tasks:
            if str(task.get("id") or "") != task_id:
                continue
            found = task
            task["status"] = "cancelled"
            task["cancel_reason"] = cancel_reason
            task["cancelled_ts"] = now_ts
            task["updated_ts"] = now_ts
            task["cancelled_at"] = now_beijing_iso()
            task["updated_at"] = now_beijing_iso()
            task.pop("response", None)
            task["error"] = cancel_reason
            break
        if found is None:
            return None
        state["tasks"] = tasks
        if not _save_state(state):
            return None
        public = _public_task(found)
    _publish_task(public)
    return public


def finish_task(task_id: str, response: str = "", error: str = "") -> dict | None:
    task_id = str(task_id or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    now_ts = _now_ts()
    sync_task = None
    with _LOCK:
        state = _load_state()
        tasks = _cleanup_tasks(state.get("tasks") or [])
        found = None
        for task in tasks:
            if str(task.get("id") or "") != task_id:
                continue
            found = task
            if str(task.get("status") or "") == "cancelled":
                sync_task = dict(task)
                break
            if str(error or "").strip():
                task["status"] = "error"
                task["error"] = _safe_text(error, 4000)
                task.pop("response", None)
            else:
                task["status"] = "done"
                task["response"] = _safe_text(response, 12000)
                task.pop("error", None)
            task["finished_ts"] = now_ts
            task["updated_ts"] = now_ts
            task["finished_at"] = now_beijing_iso()
            task["updated_at"] = now_beijing_iso()
            sync_task = dict(task)
            break
        if found is None:
            return None
        state["tasks"] = tasks
        if not _save_state(state):
            return None
        public = _public_task(found)
    _publish_task(public)
    _sync_studyroom_task_result(sync_task)
    return public
