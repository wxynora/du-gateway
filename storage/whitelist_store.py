# 白名单与最近窗口：文件存储，方便添加；白名单有上限与过期（LRU + 14 天）
import json
import time
from pathlib import Path

from config import (
    WHITELIST_FILE,
    RECENT_WINDOWS_FILE,
    MAX_WHITELIST_SIZE,
    WHITELIST_EXPIRE_DAYS,
)

# 最近窗口最多保留条数
MAX_RECENT_WINDOWS = 200


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _prune_whitelist() -> list:
    """
    按 last_seen 保留最近 MAX_WHITELIST_SIZE 个，且剔除超过 WHITELIST_EXPIRE_DAYS 未出现的。
    直接改写 WHITELIST_FILE，返回当前白名单 id 列表。
    """
    data = _load_json(WHITELIST_FILE, [])
    if not data:
        return []
    recent = _load_json(RECENT_WINDOWS_FILE, [])
    now = time.time()
    expire_ts = now - (WHITELIST_EXPIRE_DAYS * 24 * 3600)
    id_to_seen = {w.get("id"): w.get("last_seen", 0) for w in recent if w.get("id")}
    # 只保留在 recent 里且未过期的，按 last_seen 降序，取前 MAX
    valid = [
        (wid, id_to_seen.get(wid, 0))
        for wid in data
        if id_to_seen.get(wid, 0) >= expire_ts
    ]
    valid.sort(key=lambda x: -x[1])
    kept = [wid for wid, _ in valid[:MAX_WHITELIST_SIZE]]
    if set(kept) != set(data):
        _save_json(WHITELIST_FILE, kept)
    return kept


def is_whitelisted(window_id: str) -> bool:
    """判断窗口是否在白名单中（先修剪过期/超量再判断）。"""
    if not window_id:
        return False
    kept = _prune_whitelist()
    return window_id in kept


def add_to_whitelist(window_id: str) -> bool:
    """将窗口 ID 加入白名单；加入后执行修剪。"""
    if not window_id:
        return False
    data = _load_json(WHITELIST_FILE, [])
    if not isinstance(data, list):
        data = []
    if window_id not in data:
        data.append(window_id)
        _save_json(WHITELIST_FILE, data)
    _prune_whitelist()
    return True


def remove_from_whitelist(window_id: str) -> bool:
    """从白名单移除窗口 ID。"""
    data = _load_json(WHITELIST_FILE, [])
    if window_id in data:
        data.remove(window_id)
        _save_json(WHITELIST_FILE, data)
        return True
    return False


def list_whitelist():
    """返回当前白名单列表（已修剪）。"""
    return _prune_whitelist()


def record_recent_window(window_id: str):
    """记录一次窗口访问，用于管理端列表。"""
    if not window_id:
        return
    now = time.time()
    data = _load_json(RECENT_WINDOWS_FILE, [])
    # 结构: [ {"id": "xxx", "last_seen": 123}, ... ]
    data = [w for w in data if w.get("id") != window_id]
    data.append({"id": window_id, "last_seen": now})
    data.sort(key=lambda w: w["last_seen"], reverse=True)
    data = data[:MAX_RECENT_WINDOWS]
    _save_json(RECENT_WINDOWS_FILE, data)


def list_recent_windows(limit: int = 50):
    """返回最近出现过的窗口列表（供管理端使用）。"""
    data = _load_json(RECENT_WINDOWS_FILE, [])
    return data[:limit]
