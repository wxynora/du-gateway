# 聊天响应缓存：几分钟内相同请求返回缓存，不调上游，省 API 费用（仅非流式）
import hashlib
import json
import threading
import time

from config import CHAT_CACHE_ENABLED, CHAT_CACHE_TTL_SECONDS, CHAT_CACHE_MAX_SIZE
from utils.log import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
# key -> (expiry_ts, (resp_json, status))
_store: dict[str, tuple[float, tuple[dict, int]]] = {}
# 按写入顺序 evict 时用
_order: list[str] = []


def _canonical_body(body: dict) -> dict:
    """只取影响上游返回的字段做 key，避免无关字段导致不命中。"""
    return {
        "model": body.get("model") or "",
        "messages": body.get("messages") or [],
    }


def get_cache_key(body: dict) -> str:
    """对即将发给上游的 body 生成缓存 key（model + messages）。"""
    canonical = _canonical_body(body)
    raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(key: str) -> tuple[dict, int] | None:
    """命中则返回 (resp_json, status)，过期或未命中返回 None。"""
    if not CHAT_CACHE_ENABLED:
        return None
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        expiry, (resp_json, status) = entry
        if time.time() > expiry:
            _store.pop(key, None)
            if key in _order:
                _order.remove(key)
            return None
        return (resp_json, status)


def set(key: str, resp_json: dict, status: int) -> None:
    """写入缓存；超 max_size 时淘汰最久未用的。"""
    if not CHAT_CACHE_ENABLED:
        return
    expiry = time.time() + CHAT_CACHE_TTL_SECONDS
    with _lock:
        while len(_store) >= CHAT_CACHE_MAX_SIZE and _order:
            old_key = _order.pop(0)
            _store.pop(old_key, None)
        _store[key] = (expiry, (resp_json, status))
        if key not in _order:
            _order.append(key)
    logger.debug("chat_response_cache set key=%s status=%s", key[:16], status)
