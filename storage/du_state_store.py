"""R2 storage helpers for Du state and portrait candidate records."""
import threading
from typing import Any, Optional
from uuid import uuid4

from utils.log import get_logger
from utils.time_aware import now_beijing_iso

R2_KEY_DU_THOUGHT_LATEST = "global/du_thought_latest.json"
R2_KEY_DU_VITALS_LATEST = "global/du_vitals_latest.json"
R2_KEY_DU_VITALS_HISTORY = "global/du_vitals_history.json"
R2_KEY_DU_DAILY_STATE = "global/du_daily_state.json"
R2_KEY_DU_DAILY_ARCHIVE = "global/du_daily_archive.json"
R2_KEY_DU_MIDTERM_MEMORY = "global/du_midterm_memory.json"
R2_KEY_XINYUE_PORTRAIT_CANDIDATES = "portrait_memory/xinyue_candidates.json"
R2_KEY_DU_PORTRAIT_CANDIDATES = "portrait_memory/du_candidates.json"
R2_KEY_INTERACTION_CANDIDATES = "portrait_memory/interaction_candidates.json"

_du_state_write_lock = threading.Lock()

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def save_du_thought_latest(at_iso: str, content: str) -> bool:
    """写入 global/du_thought_latest.json（渡上一则心事）。"""
    client = _s3_client()
    if not client:
        return False
    if not content or not str(content).strip():
        return False
    payload = {"at": (at_iso or "").strip(), "content": str(content).strip()}
    with _du_state_write_lock:
        try:
            _write_json(client, R2_KEY_DU_THOUGHT_LATEST, payload)
            return True
        except Exception as e:
            logger.error("save_du_thought_latest 失败 error=%s", e, exc_info=True)
            return False


def get_du_thought_latest() -> Optional[dict]:
    """读取 global/du_thought_latest.json。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_DU_THOUGHT_LATEST)
    if not isinstance(data, dict):
        return None
    return data


def save_du_vitals_latest(payload: dict) -> bool:
    """写入 global/du_vitals_latest.json（渡的拟态心跳/呼吸状态）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(payload, dict) or not payload:
        return False
    with _du_state_write_lock:
        try:
            _write_json(client, R2_KEY_DU_VITALS_LATEST, payload)
            return True
        except Exception as e:
            logger.error("save_du_vitals_latest 失败 error=%s", e, exc_info=True)
            return False


def get_du_vitals_latest() -> Optional[dict]:
    """读取 global/du_vitals_latest.json。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_DU_VITALS_LATEST)
    if not isinstance(data, dict):
        return None
    return data


def get_du_vitals_history(limit: int = 10) -> list[dict]:
    """读取渡的拟态心跳/呼吸最近历史，默认最近 10 条。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DU_VITALS_HISTORY)
    rows = data.get("items") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out = [dict(item) for item in rows if isinstance(item, dict)]
    try:
        n = int(limit or 10)
    except Exception:
        n = 10
    return out[-max(1, min(50, n)) :]


def append_du_vitals_history(payload: dict, limit: int = 10) -> bool:
    """追加一条渡的拟态心跳/呼吸历史，并只保留最近 limit 条。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(payload, dict) or not payload:
        return False
    try:
        n = int(limit or 10)
    except Exception:
        n = 10
    n = max(1, min(50, n))
    with _du_state_write_lock:
        try:
            data = _read_json(client, R2_KEY_DU_VITALS_HISTORY)
            rows = data.get("items") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                rows = []
            rows = [dict(item) for item in rows if isinstance(item, dict)]
            rows.append(dict(payload))
            _write_json(client, R2_KEY_DU_VITALS_HISTORY, {"items": rows[-n:], "updated_at": now_beijing_iso()})
            return True
        except Exception as e:
            logger.error("append_du_vitals_history 失败 error=%s", e, exc_info=True)
            return False


def save_du_daily_state(data: dict) -> bool:
    """写入 global/du_daily_state.json。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _du_state_write_lock:
        try:
            _write_json(client, R2_KEY_DU_DAILY_STATE, data)
            return True
        except Exception as e:
            logger.error("save_du_daily_state 失败 error=%s", e, exc_info=True)
            return False


def get_du_daily_state() -> Optional[dict]:
    """读取 global/du_daily_state.json。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_DU_DAILY_STATE)
    if not isinstance(data, dict):
        return None
    return data


def get_du_daily_archive() -> list[dict]:
    return _get_items_json(R2_KEY_DU_DAILY_ARCHIVE)


def save_du_daily_archive(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_DU_DAILY_ARCHIVE, items)


def upsert_du_daily_archive_entry(entry: dict, limit: int = 45) -> bool:
    if not isinstance(entry, dict):
        return False
    day = str(entry.get("day") or "").strip()
    if not day:
        return False
    items = get_du_daily_archive()
    now = now_beijing_iso()
    payload = {
        "id": day,
        "day": day,
        "yesterday_summary": str(entry.get("yesterday_summary") or "").strip(),
        "today_summary": str(entry.get("today_summary") or "").strip(),
        "today_events": entry.get("today_events") if isinstance(entry.get("today_events"), list) else [],
        "content": str(entry.get("content") or "").strip(),
        "source": str(entry.get("source") or "du_daily").strip() or "du_daily",
        "trigger_kind": str(entry.get("trigger_kind") or "").strip(),
        "created_at": str(entry.get("created_at") or now).strip(),
        "updated_at": now,
    }
    replaced = False
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("day") or "").strip() == day:
            old_created = str(item.get("created_at") or "").strip()
            if old_created:
                payload["created_at"] = old_created
            out.append(payload)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(payload)
    out = sorted(out, key=lambda x: str((x or {}).get("day") or ""))[-max(1, int(limit or 45)) :]
    return save_du_daily_archive(out)


def get_du_midterm_memory() -> Optional[dict]:
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_DU_MIDTERM_MEMORY)
    if not isinstance(data, dict):
        return None
    return data


def save_du_midterm_memory(data: dict) -> bool:
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _du_state_write_lock:
        try:
            _write_json(client, R2_KEY_DU_MIDTERM_MEMORY, data)
            return True
        except Exception as e:
            logger.error("save_du_midterm_memory 失败 error=%s", e, exc_info=True)
            return False


def _get_items_json(key: str) -> list[dict]:
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, key)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def _save_items_json(key: str, items: list[dict]) -> bool:
    client = _s3_client()
    if not client:
        return False
    payload = {"items": items if isinstance(items, list) else []}
    with _du_state_write_lock:
        try:
            _write_json(client, key, payload)
            return True
        except Exception as e:
            logger.error("save items json 失败 key=%s error=%s", key, e, exc_info=True)
            return False


def get_xinyue_portrait_candidates() -> list[dict]:
    return _get_items_json(R2_KEY_XINYUE_PORTRAIT_CANDIDATES)


def save_xinyue_portrait_candidates(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_XINYUE_PORTRAIT_CANDIDATES, items)


def get_du_portrait_candidates() -> list[dict]:
    return _get_items_json(R2_KEY_DU_PORTRAIT_CANDIDATES)


def save_du_portrait_candidates(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_DU_PORTRAIT_CANDIDATES, items)


def get_interaction_candidates() -> list[dict]:
    return _get_items_json(R2_KEY_INTERACTION_CANDIDATES)


def save_interaction_candidates(items: list[dict]) -> bool:
    return _save_items_json(R2_KEY_INTERACTION_CANDIDATES, items)


def append_interaction_candidate(summary: str, source_message_id: str = "") -> Optional[dict]:
    content = str(summary or "").strip()
    if not content:
        return None
    items = get_interaction_candidates()
    now = now_beijing_iso()
    entry = {
        "id": str(uuid4()),
        "summary": content,
        "source_message_id": str(source_message_id or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    items.append(entry)
    ok = save_interaction_candidates(items)
    return entry if ok else None


def delete_xinyue_portrait_candidate(entry_id: str) -> bool:
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    items = get_xinyue_portrait_candidates()
    new_items = [it for it in items if str((it or {}).get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_xinyue_portrait_candidates(new_items)


def delete_du_portrait_candidate(entry_id: str) -> bool:
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    items = get_du_portrait_candidates()
    new_items = [it for it in items if str((it or {}).get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_du_portrait_candidates(new_items)


def delete_interaction_candidate(entry_id: str) -> bool:
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    items = get_interaction_candidates()
    new_items = [it for it in items if str((it or {}).get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_interaction_candidates(new_items)
