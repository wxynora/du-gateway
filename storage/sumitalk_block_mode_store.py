from __future__ import annotations

import json
import threading

from config import DATA_DIR
from utils.time_aware import now_beijing_iso


SUMITALK_BLOCK_MODE_FILE = DATA_DIR / "sumitalk_block_mode.json"
BLOCK_NOTICE_TEXT = "【你已被小玥拉黑】"
MAX_AUTO_REPLIES_PER_SEGMENT = 3
AUTO_REPLY_SEGMENT_RESET_SECONDS = 30 * 60
_LOCK = threading.Lock()


def _default_state() -> dict:
    return {
        "enabled": False,
        "updated_at": "",
        "notice_sent_at": "",
        "auto_reply_count": 0,
        "segment_started_at": "",
        "last_auto_reply_at": "",
        "last_incoming_message_id": "",
    }


def _load_state_unlocked() -> dict:
    try:
        if not SUMITALK_BLOCK_MODE_FILE.exists():
            return _default_state()
        with SUMITALK_BLOCK_MODE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if not isinstance(data, dict):
            return _default_state()
        state = _default_state()
        state.update(data)
        state["enabled"] = bool(state.get("enabled"))
        try:
            state["auto_reply_count"] = max(0, int(state.get("auto_reply_count") or 0))
        except Exception:
            state["auto_reply_count"] = 0
        for key in ("updated_at", "notice_sent_at", "segment_started_at", "last_auto_reply_at", "last_incoming_message_id"):
            state[key] = str(state.get(key) or "")
        return state
    except Exception:
        return _default_state()


def _save_state_unlocked(state: dict) -> dict:
    payload = _default_state()
    payload.update(state if isinstance(state, dict) else {})
    payload["enabled"] = bool(payload.get("enabled"))
    try:
        payload["auto_reply_count"] = max(0, int(payload.get("auto_reply_count") or 0))
    except Exception:
        payload["auto_reply_count"] = 0
    SUMITALK_BLOCK_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SUMITALK_BLOCK_MODE_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def get_state() -> dict:
    with _LOCK:
        return _load_state_unlocked()


def is_enabled() -> bool:
    return bool(get_state().get("enabled"))


def set_enabled(enabled: bool, updated_at: str = "") -> dict:
    ts = str(updated_at or now_beijing_iso()).strip() or now_beijing_iso()
    with _LOCK:
        current = _load_state_unlocked()
        payload = dict(current)
        payload["enabled"] = bool(enabled)
        payload["updated_at"] = ts
        if enabled and not current.get("enabled"):
            payload["notice_sent_at"] = ""
            payload["auto_reply_count"] = 0
            payload["segment_started_at"] = ts
            payload["last_auto_reply_at"] = ""
            payload["last_incoming_message_id"] = ""
        elif not enabled:
            payload["notice_sent_at"] = ""
            payload["auto_reply_count"] = 0
            payload["segment_started_at"] = ""
            payload["last_auto_reply_at"] = ""
            payload["last_incoming_message_id"] = ""
        return _save_state_unlocked(payload)


def mark_initial_notice_sent(sent_at: str = "") -> dict:
    ts = str(sent_at or now_beijing_iso()).strip() or now_beijing_iso()
    with _LOCK:
        payload = _load_state_unlocked()
        payload["notice_sent_at"] = ts
        if not str(payload.get("segment_started_at") or "").strip():
            payload["segment_started_at"] = ts
        return _save_state_unlocked(payload)


def try_consume_auto_reply(incoming_message_id: str = "", now_ts: str = "") -> tuple[bool, dict]:
    ts = str(now_ts or now_beijing_iso()).strip() or now_beijing_iso()
    incoming_id = str(incoming_message_id or "").strip()
    with _LOCK:
        payload = _load_state_unlocked()
        if not payload.get("enabled"):
            return False, payload
        if incoming_id and incoming_id == str(payload.get("last_incoming_message_id") or ""):
            return False, payload
        count = max(0, int(payload.get("auto_reply_count") or 0))
        last_at = str(payload.get("last_auto_reply_at") or "").strip()
        should_reset = False
        if last_at:
            try:
                from utils.time_aware import parse_iso_to_beijing

                last_dt = parse_iso_to_beijing(last_at)
                now_dt = parse_iso_to_beijing(ts)
                if last_dt and now_dt and (now_dt - last_dt).total_seconds() >= AUTO_REPLY_SEGMENT_RESET_SECONDS:
                    should_reset = True
            except Exception:
                pass
        elif count <= 0:
            should_reset = True
        if should_reset:
            count = 0
            payload["segment_started_at"] = ts
        if count >= MAX_AUTO_REPLIES_PER_SEGMENT:
            return False, payload
        payload["auto_reply_count"] = count + 1
        payload["last_auto_reply_at"] = ts
        payload["last_incoming_message_id"] = incoming_id
        if not str(payload.get("segment_started_at") or "").strip():
            payload["segment_started_at"] = ts
        return True, _save_state_unlocked(payload)


def reset_segment(updated_at: str = "") -> dict:
    ts = str(updated_at or now_beijing_iso()).strip() or now_beijing_iso()
    with _LOCK:
        payload = _load_state_unlocked()
        payload["auto_reply_count"] = 0
        payload["segment_started_at"] = ts
        payload["last_auto_reply_at"] = ""
        payload["last_incoming_message_id"] = ""
        return _save_state_unlocked(payload)
