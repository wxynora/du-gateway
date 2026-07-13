from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import LAST_USER_REPLY_FILE
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import parse_iso_to_beijing


logger = get_logger(__name__)

ACTIVITY_FILE = LAST_USER_REPLY_FILE
SHARED_GAME_ACTIVITY_NAMES = {
    "private_board": "涩涩走格棋",
    "captivity_simulator": "囚禁模拟器",
}

_activity_file_lock = threading.Lock()


def _normalized_game_id(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _valid_iso(value: Any) -> str:
    raw = str(value or "").strip()
    return raw if raw and parse_iso_to_beijing(raw) is not None else ""


def _read_state_unlocked() -> dict:
    path = Path(ACTIVITY_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("用户活动上下文读取失败 path=%s error=%s", path, e)
        return {}


def _write_state_unlocked(state: dict) -> None:
    path = Path(ACTIVITY_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(state, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _trusted_game_activity(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    game_id = _normalized_game_id(raw.get("game_id"))
    game_name = SHARED_GAME_ACTIVITY_NAMES.get(game_id, "")
    activity_at = _valid_iso(raw.get("at"))
    if not game_name or not activity_at:
        return None
    return {
        "kind": "game",
        "at": activity_at,
        "game_id": game_id,
        "game_name": game_name,
        "source": str(raw.get("source") or "").strip(),
    }


def latest_interaction_from_state(state: dict) -> Optional[dict]:
    chat_at = _valid_iso((state or {}).get("last_user_reply_at"))
    latest = {"kind": "chat", "at": chat_at} if chat_at else None
    game = _trusted_game_activity((state or {}).get("last_shared_game_activity"))
    if not game:
        return latest
    if not latest:
        return game
    chat_dt = parse_iso_to_beijing(latest["at"])
    game_dt = parse_iso_to_beijing(game["at"])
    if game_dt is not None and chat_dt is not None and game_dt > chat_dt:
        return game
    return latest


def get_latest_interaction() -> Optional[dict]:
    with _activity_file_lock:
        return latest_interaction_from_state(_read_state_unlocked())


def capture_previous_interaction_and_mark_chat(occurred_at: str) -> Optional[dict]:
    activity_at = _valid_iso(occurred_at)
    if not activity_at:
        return get_latest_interaction()
    with _activity_file_lock:
        state = _read_state_unlocked()
        previous = latest_interaction_from_state(state)
        existing_at = _valid_iso(state.get("last_user_reply_at"))
        existing_dt = parse_iso_to_beijing(existing_at) if existing_at else None
        activity_dt = parse_iso_to_beijing(activity_at)
        if existing_dt is None or (activity_dt is not None and activity_dt >= existing_dt):
            state["last_user_reply_at"] = activity_at
            try:
                _write_state_unlocked(state)
            except Exception as e:
                logger.warning("最近 chat 活动时间写入失败 path=%s error=%s", ACTIVITY_FILE, e)
        return previous


def mark_shared_game_user_activity(
    *,
    game_id: str,
    occurred_at: str,
    source: str,
    detail: Optional[dict] = None,
) -> bool:
    normalized_game_id = _normalized_game_id(game_id)
    game_name = SHARED_GAME_ACTIVITY_NAMES.get(normalized_game_id, "")
    activity_at = _valid_iso(occurred_at)
    if not game_name or not activity_at:
        logger.warning(
            "共同游戏活动拒绝 game_id=%s source=%s activity_at=%s",
            normalized_game_id or "missing",
            str(source or "").strip() or "missing",
            str(occurred_at or "").strip() or "missing",
        )
        return False

    clean_detail = dict(detail or {}) if isinstance(detail, dict) else {}
    clean_detail.update(
        {
            "game_id": normalized_game_id,
            "game_name": game_name,
            "entry_source": str(source or "").strip(),
        }
    )

    with _activity_file_lock:
        state = _read_state_unlocked()
        current = _trusted_game_activity(state.get("last_shared_game_activity"))
        current_dt = parse_iso_to_beijing(current["at"]) if current else None
        activity_dt = parse_iso_to_beijing(activity_at)
        if current_dt is not None and activity_dt is not None and activity_dt < current_dt:
            return True

        local_saved = False
        state["last_shared_game_activity"] = {
            "at": activity_at,
            "game_id": normalized_game_id,
            "game_name": game_name,
            "source": str(source or "").strip(),
        }
        try:
            _write_state_unlocked(state)
            local_saved = True
        except Exception as e:
            logger.warning(
                "共同游戏活动本地写入失败 game_id=%s path=%s error=%s",
                normalized_game_id,
                ACTIVITY_FILE,
                e,
            )
        global_saved = False
        try:
            global_saved = bool(
                r2_store.save_last_user_activity_at(
                    activity_at,
                    source="shared_game_user_interaction",
                    detail=clean_detail,
                )
            )
        except Exception as e:
            logger.warning("共同游戏统一互动时间写入失败 game_id=%s error=%s", normalized_game_id, e)
        return local_saved and global_saved


def elapsed_seconds(activity: Optional[dict], now_dt: datetime) -> Optional[int]:
    activity_dt = parse_iso_to_beijing(str((activity or {}).get("at") or ""))
    if activity_dt is None:
        return None
    return max(0, int((now_dt - activity_dt).total_seconds()))


def _elapsed_text(delta_seconds: int, *, spaced: bool) -> str:
    minutes = max(0, int(delta_seconds)) // 60
    separator = " " if spaced else ""
    if minutes < 120:
        return f"{minutes}{separator}分钟"
    hours, remainder = divmod(minutes, 60)
    text = f"{hours}{separator}小时"
    if remainder:
        text += f"{separator}{remainder}{separator}分钟"
    return text


def render_incoming_gap_prompt(activity: Optional[dict], delta_seconds: int) -> str:
    if str((activity or {}).get("kind") or "") == "game":
        game_name = str((activity or {}).get("game_name") or "").strip()
        if not game_name:
            return ""
        return f"[老婆 {_elapsed_text(delta_seconds, spaced=True)}前和我在玩{game_name}。]"
    return f"[😭{_elapsed_text(delta_seconds, spaced=False)}后老婆终于回我了]"


def describe_latest_interaction(now_dt: datetime) -> str:
    activity = get_latest_interaction()
    delta_seconds = elapsed_seconds(activity, now_dt)
    if delta_seconds is None:
        return ""
    if str((activity or {}).get("kind") or "") == "game":
        game_name = str((activity or {}).get("game_name") or "").strip()
        if game_name:
            return f"老婆 {_elapsed_text(delta_seconds, spaced=True)}前和我在玩{game_name}。"
        return ""
    return f"她上次明确回你大约是 {delta_seconds / 3600.0:.1f} 小时前。"
