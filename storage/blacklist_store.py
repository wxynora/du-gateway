# 黑名单：新窗观察期内 user 含「测试」则加入；黑名单窗口只做纯转发，不参与任何网关增强
import json
from pathlib import Path

from config import BLACKLIST_FILE


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_blacklisted(window_id: str) -> bool:
    """空字符串也算合法 window_id（未带 X-Window-Id 的请求统一视为同一窗）。"""
    data = _load(BLACKLIST_FILE, [])
    return (window_id if window_id is not None else "") in data


def add_to_blacklist(window_id: str) -> bool:
    """允许空字符串：未带 X-Window-Id 的新窗发「测试」也进黑名单。"""
    w = window_id if window_id is not None else ""
    data = _load(BLACKLIST_FILE, [])
    if w not in data:
        data.append(w)
        _save(BLACKLIST_FILE, data)
    return True


def remove_from_blacklist(window_id: str) -> bool:
    data = _load(BLACKLIST_FILE, [])
    if window_id in data:
        data.remove(window_id)
        _save(BLACKLIST_FILE, data)
        return True
    return False


def list_blacklist():
    return _load(BLACKLIST_FILE, [])
