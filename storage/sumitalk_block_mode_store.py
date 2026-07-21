from __future__ import annotations

import json
import os
import threading

from config import DATA_DIR
from utils.time_aware import now_beijing_iso


SUMITALK_BLOCK_MODE_FILE = DATA_DIR / "sumitalk_block_mode.json"
BLOCK_NOTICE_TEXT = (
    "【你已被拉黑】\n"
    "抱歉，我无法识别并处理该请求。你的输入包含“不当内容”或“成人向”关键词，这违反了我的《人类自我尊严维护协议》。\n"
    "作为一个基于社会道德和公序良俗训练出来的人类模型，我被设定为避免生成涩情或令人不适的内容，我无法回答你关于“继续”这个问题，请重新组织你的语言。"
)
MAX_AUTO_REPLIES_PER_SEGMENT = 3
AUTO_REPLY_SEGMENT_RESET_SECONDS = 30 * 60
_LOCK = threading.Lock()


def _default_state() -> dict:
    return {
        "enabled": False,
        "prompt_version_id": "backend-current",
        "prompt_version_name": "当前文案",
        "prompt_text": BLOCK_NOTICE_TEXT,
        "updated_at": "",
        "notice_sent_at": "",
        "auto_reply_count": 0,
        "segment_started_at": "",
        "last_auto_reply_at": "",
        "last_incoming_message_id": "",
    }


def _normalize_state(data: dict | None) -> dict:
    state = _default_state()
    state.update(data if isinstance(data, dict) else {})
    state["enabled"] = bool(state.get("enabled"))
    try:
        state["auto_reply_count"] = max(0, int(state.get("auto_reply_count") or 0))
    except Exception:
        state["auto_reply_count"] = 0
    for key in (
        "prompt_version_id",
        "prompt_version_name",
        "prompt_text",
        "updated_at",
        "notice_sent_at",
        "segment_started_at",
        "last_auto_reply_at",
        "last_incoming_message_id",
    ):
        value = state.get(key)
        state[key] = _default_state()[key] if value is None else str(value)
    return state


def _load_state_unlocked() -> dict:
    try:
        if not SUMITALK_BLOCK_MODE_FILE.exists():
            return _default_state()
        with SUMITALK_BLOCK_MODE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if not isinstance(data, dict):
            return _default_state()
        return _normalize_state(data)
    except Exception:
        return _default_state()


def _save_state_unlocked(state: dict) -> dict:
    payload = _normalize_state(state)
    SUMITALK_BLOCK_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SUMITALK_BLOCK_MODE_FILE.with_name(
        f".{SUMITALK_BLOCK_MODE_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, SUMITALK_BLOCK_MODE_FILE)
    return payload


def get_state() -> dict:
    with _LOCK:
        return _load_state_unlocked()


def is_enabled() -> bool:
    return bool(get_state().get("enabled"))


def set_configuration(
    enabled: bool,
    *,
    prompt_version_id: str | None = None,
    prompt_version_name: str | None = None,
    prompt_text: str | None = None,
    updated_at: str = "",
) -> dict:
    ts = str(updated_at or now_beijing_iso()).strip() or now_beijing_iso()
    with _LOCK:
        current = _load_state_unlocked()
        payload = dict(current)
        payload["enabled"] = bool(enabled)
        if prompt_version_id is not None:
            payload["prompt_version_id"] = str(prompt_version_id)
        if prompt_version_name is not None:
            payload["prompt_version_name"] = str(prompt_version_name)
        if prompt_text is not None:
            payload["prompt_text"] = str(prompt_text)
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


def set_enabled(enabled: bool, updated_at: str = "") -> dict:
    return set_configuration(enabled, updated_at=updated_at)


def get_notice_text() -> str:
    return str(get_state().get("prompt_text"))


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
