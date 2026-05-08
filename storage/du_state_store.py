"""R2 storage helpers for Du state and portrait candidate records."""
import threading
from typing import Any, Optional
from uuid import uuid4

from utils.log import get_logger
from utils.time_aware import now_beijing_iso

R2_KEY_DU_THOUGHT_LATEST = "global/du_thought_latest.json"
R2_KEY_DU_DAILY_STATE = "global/du_daily_state.json"
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
