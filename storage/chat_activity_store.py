"""Small R2 cache for recent chat activity rhythm."""
from __future__ import annotations

from typing import Any

from utils.log import get_logger

R2_KEY_CHAT_ACTIVITY_CONTEXT = "global/chat_activity_context.json"

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Any:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def get_chat_activity_context() -> dict:
    """Read cached three-day chat activity context."""
    client = _s3_client()
    if not client:
        return {}
    try:
        data = _read_json(client, R2_KEY_CHAT_ACTIVITY_CONTEXT)
    except Exception as e:
        logger.warning("chat_activity_context read failed error=%s", e)
        return {}
    return data if isinstance(data, dict) else {}


def save_chat_activity_context(payload: dict) -> bool:
    """Save cached chat activity context; keep caller payload compact."""
    if not isinstance(payload, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        _write_json(client, R2_KEY_CHAT_ACTIVITY_CONTEXT, payload)
        return True
    except Exception as e:
        logger.warning("chat_activity_context save failed error=%s", e)
        return False
