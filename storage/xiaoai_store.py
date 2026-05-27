from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import DATA_DIR
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_PATH = DATA_DIR / "xiaoai_state.json"
_LOCK = threading.Lock()
_MAX_LOGS = 300
_ONLINE_TTL_SECONDS = 120
_DEFAULT_ENTRY_PHRASES = ["请求连接渡"]
_DEFAULT_EXIT_PHRASES = ["退出渡"]


def _default_state() -> dict[str, Any]:
    return {
        "config": {
            "enabled": False,
            "entry_phrases": list(_DEFAULT_ENTRY_PHRASES),
            "exit_phrases": list(_DEFAULT_EXIT_PHRASES),
            "updated_at": "",
        },
        "status": {
            "connected": False,
            "last_seen_at": "",
            "last_seen_epoch": 0.0,
            "runner": "",
            "speaker": "",
            "last_event": "",
            "last_text": "",
            "last_error": "",
            "last_audio_url": "",
            "last_message_at": "",
        },
        "logs": [],
    }


def _read_state() -> dict[str, Any]:
    if not _PATH.exists():
        return _default_state()
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_state()
    except Exception as e:
        logger.warning("读取小爱状态文件失败 path=%s err=%s", _PATH, e)
        return _default_state()
    state = _default_state()
    if isinstance(data.get("config"), dict):
        state["config"].update(data.get("config") or {})
    if isinstance(data.get("status"), dict):
        state["status"].update(data.get("status") or {})
    if isinstance(data.get("logs"), list):
        state["logs"] = [x for x in data.get("logs") or [] if isinstance(x, dict)][:_MAX_LOGS]
    state["config"] = _normalize_config(state.get("config") or {})
    return state


def _write_state(state: dict[str, Any]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(_PATH) + ".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_PATH)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    if value is None:
        return default
    return bool(value)


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _normalize_phrase_list(value: Any, fallback: list[str]) -> list[str]:
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = value.replace("，", ",").replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = fallback

    items: list[str] = []
    seen = set()
    for item in raw_items:
        text = _clip(item, 32)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= 8:
            break
    return items or list(fallback)


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": _as_bool((config or {}).get("enabled"), default=False),
        "entry_phrases": _normalize_phrase_list((config or {}).get("entry_phrases"), _DEFAULT_ENTRY_PHRASES),
        "exit_phrases": _normalize_phrase_list((config or {}).get("exit_phrases"), _DEFAULT_EXIT_PHRASES),
        "updated_at": _clip((config or {}).get("updated_at"), 80),
    }


def _status_with_online(status: dict[str, Any]) -> dict[str, Any]:
    st = dict(status or {})
    try:
        last_seen_epoch = float(st.get("last_seen_epoch") or 0)
    except Exception:
        last_seen_epoch = 0
    connected = _as_bool(st.get("connected"), default=False)
    st["online"] = bool(connected and last_seen_epoch > 0 and time.time() - last_seen_epoch <= _ONLINE_TTL_SECONDS)
    st.pop("last_seen_epoch", None)
    return st


def get_xiaoai_config() -> dict[str, Any]:
    with _LOCK:
        return _normalize_config((_read_state().get("config") or {}))


def save_xiaoai_config(data: dict[str, Any]) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    with _LOCK:
        state = _read_state()
        current = dict(state.get("config") or {})
        if "enabled" in payload:
            current["enabled"] = _as_bool(payload.get("enabled"), default=False)
        if "entry_phrases" in payload:
            current["entry_phrases"] = _normalize_phrase_list(payload.get("entry_phrases"), _DEFAULT_ENTRY_PHRASES)
        if "exit_phrases" in payload:
            current["exit_phrases"] = _normalize_phrase_list(payload.get("exit_phrases"), _DEFAULT_EXIT_PHRASES)
        current["updated_at"] = now_beijing_iso()
        state["config"] = _normalize_config(current)
        _write_state(state)
        return dict(state["config"])


def get_xiaoai_status() -> dict[str, Any]:
    with _LOCK:
        state = _read_state()
        return _status_with_online(state.get("status") or {})


def update_xiaoai_status(data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    now_iso = now_beijing_iso()
    with _LOCK:
        state = _read_state()
        status = dict(state.get("status") or {})
        status["connected"] = _as_bool(payload.get("connected"), default=True)
        status["last_seen_at"] = now_iso
        status["last_seen_epoch"] = time.time()
        for key, limit in (
            ("runner", 80),
            ("speaker", 80),
            ("last_event", 120),
            ("last_text", 500),
            ("last_error", 500),
            ("last_audio_url", 500),
        ):
            if key in payload:
                status[key] = _clip(payload.get(key), limit)
        if payload.get("last_text"):
            status["last_message_at"] = now_iso
        state["status"] = status
        _write_state(state)
        return _status_with_online(status)


def add_xiaoai_log(level: str, message: str, **fields: Any) -> dict[str, Any]:
    item = {
        "id": uuid4().hex,
        "at": now_beijing_iso(),
        "level": _clip(level or "info", 20).lower() or "info",
        "message": _clip(message, 500),
    }
    for key, limit in (
        ("event", 80),
        ("runner", 80),
        ("speaker", 80),
        ("text", 500),
        ("error", 500),
        ("audio_url", 500),
    ):
        if key in fields:
            item[key] = _clip(fields.get(key), limit)
    with _LOCK:
        state = _read_state()
        logs = [item] + [x for x in (state.get("logs") or []) if isinstance(x, dict)]
        state["logs"] = logs[:_MAX_LOGS]
        _write_state(state)
    return item


def list_xiaoai_logs(limit: int = 80) -> list[dict[str, Any]]:
    try:
        n = max(1, min(300, int(limit)))
    except Exception:
        n = 80
    with _LOCK:
        return list((_read_state().get("logs") or [])[:n])
