"""R2 storage helpers for the shared cyber home state."""
from __future__ import annotations

import threading
from typing import Any, Optional

from utils.log import get_logger
from utils.time_aware import now_beijing_iso

R2_KEY_PIXEL_HOME_STATE = "global/pixel_home_state.json"

_pixel_home_write_lock = threading.Lock()
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


def get_pixel_home_state() -> Optional[dict]:
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_PIXEL_HOME_STATE)
    return data if isinstance(data, dict) else None


def save_pixel_home_state(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    payload = dict(data)
    payload["updated_at"] = str(payload.get("updated_at") or "").strip() or now_beijing_iso()
    with _pixel_home_write_lock:
        try:
            _write_json(client, R2_KEY_PIXEL_HOME_STATE, payload)
            return True
        except Exception as e:
            logger.error("save_pixel_home_state failed error=%s", e, exc_info=True)
            return False


def update_pixel_home_state(patch: dict) -> Optional[dict]:
    if not isinstance(patch, dict):
        return None
    client = _s3_client()
    if not client:
        return None
    with _pixel_home_write_lock:
        try:
            current = _read_json(client, R2_KEY_PIXEL_HOME_STATE)
            if not isinstance(current, dict):
                current = {}
            current.update(patch)
            current["updated_at"] = now_beijing_iso()
            _write_json(client, R2_KEY_PIXEL_HOME_STATE, current)
            return current
        except Exception as e:
            logger.error("update_pixel_home_state failed error=%s", e, exc_info=True)
            return None
