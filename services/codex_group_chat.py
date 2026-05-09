from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

from config import DATA_DIR
from utils.time_aware import now_beijing_iso


_TASK_FILE = DATA_DIR / "codex_group_chat_tasks.json"
_LOCK = threading.Lock()
_MAX_TASKS = 200
_TASK_TTL_SECONDS = 2 * 24 * 60 * 60
_RUNNING_RECLAIM_SECONDS = max(
    60,
    int(float(os.environ.get("CODEX_GROUP_CHAT_RUNNING_RECLAIM_SECONDS") or "120")),
)


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
    }
    return {k: task.get(k) for k in keep if k in task}


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
    mode = str((body or {}).get("mode") or "daily_chat").strip() or "daily_chat"
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
        "user_message": _safe_text((body or {}).get("user_message"), 6000),
        "du_reply": _safe_text((body or {}).get("du_reply"), 12000),
        "recent_messages": _normalize_recent_messages((body or {}).get("recent_messages")),
        "client_request_id": re.sub(r"[^a-zA-Z0-9_.:-]", "", str((body or {}).get("client_request_id") or "").strip())[:120],
    }
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
    elif not task["window_id"] or not task["user_message"] or not task["du_reply"]:
        return None
    with _LOCK:
        state = _load_state()
        state["tasks"] = _cleanup_tasks(state.get("tasks") or [])
        state["tasks"].append(task)
        if not _save_state(state):
            return None
    return _public_task(task)


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
        return dict(selected)


def finish_task(task_id: str, response: str = "", error: str = "") -> dict | None:
    task_id = str(task_id or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    now_ts = _now_ts()
    with _LOCK:
        state = _load_state()
        tasks = _cleanup_tasks(state.get("tasks") or [])
        found = None
        for task in tasks:
            if str(task.get("id") or "") != task_id:
                continue
            found = task
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
            break
        if found is None:
            return None
        state["tasks"] = tasks
        if not _save_state(state):
            return None
        return _public_task(found)
