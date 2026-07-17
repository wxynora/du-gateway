"""最近聊天窗口的轻量本地索引。"""

import json
import time
from pathlib import Path

from config import RECENT_WINDOWS_FILE


MAX_RECENT_WINDOWS = 200


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_recent_window(window_id: str) -> None:
    """记录一次窗口访问，供管理端和诊断页选择上下文。"""
    if not window_id:
        return
    now = time.time()
    data = _load_json(RECENT_WINDOWS_FILE, [])
    if not isinstance(data, list):
        data = []
    data = [w for w in data if isinstance(w, dict) and w.get("id") != window_id]
    data.append({"id": window_id, "last_seen": now})
    data.sort(key=lambda w: w.get("last_seen", 0), reverse=True)
    _save_json(RECENT_WINDOWS_FILE, data[:MAX_RECENT_WINDOWS])


def list_recent_windows(limit: int = 50) -> list[dict]:
    """返回最近出现过的窗口。"""
    try:
        safe_limit = max(0, min(MAX_RECENT_WINDOWS, int(limit)))
    except (TypeError, ValueError):
        safe_limit = 50
    data = _load_json(RECENT_WINDOWS_FILE, [])
    if not isinstance(data, list):
        return []
    return [w for w in data if isinstance(w, dict)][:safe_limit]
