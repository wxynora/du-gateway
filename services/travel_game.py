from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import fcntl
except Exception:  # pragma: no cover - Linux/macOS targets provide fcntl.
    fcntl = None

from config import TRAVEL_MCP_HOME, TRAVEL_MCP_SCRIPT
from services.travel_mcp_client import travel_mcp_enabled


TRAVEL_GAME_ID = "travel"
TRAVEL_GAME_NAME = "旅行"
TRAVEL_CHAT_FILE = TRAVEL_MCP_HOME / "app_chat.json"
_CHAT_LOCK = threading.RLock()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _upstream_data(name: str) -> Any:
    script = TRAVEL_MCP_SCRIPT
    if script is None:
        return []
    return _read_json(script.parent / "data" / f"{name}.json", [])


def _destination(dest_id: str) -> dict[str, Any]:
    for item in _upstream_data("destinations") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == dest_id:
            return dict(item)
    return {"id": dest_id} if dest_id else {}


def _spots_entry(dest_id: str) -> dict[str, Any]:
    for item in _upstream_data("spots") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == dest_id:
            return dict(item)
    return {}


def _trip_key(state: dict[str, Any]) -> str:
    return str(state.get("started_at") or "").strip() or "lobby"


@contextmanager
def _chat_file_lock():
    with _CHAT_LOCK:
        TRAVEL_CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_path = TRAVEL_CHAT_FILE.with_suffix(TRAVEL_CHAT_FILE.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _chat_state() -> dict[str, Any]:
    raw = _read_json(TRAVEL_CHAT_FILE, {})
    return dict(raw) if isinstance(raw, dict) else {}


def _write_chat_state(state: dict[str, Any]) -> None:
    TRAVEL_CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(TRAVEL_CHAT_FILE.parent),
            prefix=f".{TRAVEL_CHAT_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, TRAVEL_CHAT_FILE)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


def append_travel_chat_exchange(*, state: dict[str, Any], user_text: str, reply_text: str) -> None:
    messages = []
    if str(user_text or "").strip():
        messages.append(
            {
                "speaker": "xinyue",
                "text": str(user_text),
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
    if str(reply_text or "").strip():
        messages.append(
            {
                "speaker": "du",
                "text": str(reply_text),
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
    if not messages:
        return
    with _chat_file_lock():
        stored = _chat_state()
        sessions = stored.get("sessions") if isinstance(stored.get("sessions"), dict) else {}
        key = _trip_key(state)
        existing = sessions.get(key) if isinstance(sessions.get(key), list) else []
        sessions[key] = [*existing, *messages]
        stored["sessions"] = sessions
        _write_chat_state(stored)


def read_travel_state() -> dict[str, Any]:
    raw = _read_json(TRAVEL_MCP_HOME / "state.json", {})
    return dict(raw) if isinstance(raw, dict) else {}


def travel_progress_signature() -> str:
    state = read_travel_state()
    solo = state.get("solo") if isinstance(state.get("solo"), dict) else {}
    postcard = solo.get("postcard") if isinstance(solo.get("postcard"), dict) else {}
    home = solo.get("home") if isinstance(solo.get("home"), dict) else {}
    wallet = _read_json(TRAVEL_MCP_HOME / "wallet.json", {})
    if not isinstance(wallet, dict):
        wallet = {}
    signature = {
        "trip": {
            "started_at": state.get("started_at"),
            "party": state.get("party"),
            "phase": state.get("phase"),
            "day": state.get("day"),
            "spot_index": state.get("spot_index"),
            "done": state.get("done"),
            "postcard_sent": postcard.get("sent"),
            "home_delivered": home.get("delivered"),
        },
        "wallet": {
            "balance": wallet.get("balance"),
            "xp": wallet.get("xp"),
            "ledger_count": len(wallet.get("ledger") or []) if isinstance(wallet.get("ledger"), list) else 0,
        },
        "collections": {
            name: len(value) if isinstance(value := _read_json(TRAVEL_MCP_HOME / f"{name}.json", []), list) else 0
            for name in ("souvenirs", "postcards", "diaries", "trips")
        },
    }
    return json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _solo_current_view(state: dict[str, Any], spots: dict[str, Any]) -> dict[str, Any]:
    solo = state.get("solo") if isinstance(state.get("solo"), dict) else {}
    packet = solo.get("packet") if isinstance(solo.get("packet"), dict) else {}
    days = packet.get("days") if isinstance(packet.get("days"), list) else []
    try:
        started = datetime.fromisoformat(str(state.get("started_at") or ""))
        elapsed_hours = max(0.0, (datetime.now() - started).total_seconds() / 3600.0)
    except Exception:
        elapsed_hours = 0.0
    total_days = int(spots.get("days") or len(days) or 0)
    try:
        virtual_day_hours = float(state.get("vday_hours") or 6)
    except Exception:
        virtual_day_hours = 6.0
    day = min(total_days or 1, int(elapsed_hours // virtual_day_hours) + 1)
    today = days[day - 1] if 0 < day <= len(days) and isinstance(days[day - 1], dict) else {}
    today_spots = today.get("spots") if isinstance(today.get("spots"), list) else []
    fraction = (elapsed_hours % virtual_day_hours) / virtual_day_hours if virtual_day_hours else 0.0
    spot_index = min(len(today_spots) - 1, int(fraction * len(today_spots))) if today_spots else -1
    return {
        "day": day,
        "days_total": total_days,
        "spot": today_spots[spot_index] if spot_index >= 0 else {},
        "eat": today.get("eat") if isinstance(today.get("eat"), dict) else {},
        "stay": today.get("stay") if isinstance(today.get("stay"), dict) else {},
        "event": today.get("event") if isinstance(today.get("event"), dict) else {},
        "gossip": today.get("gossip") if isinstance(today.get("gossip"), dict) else {},
    }


def _together_current_view(state: dict[str, Any], spots: dict[str, Any]) -> dict[str, Any]:
    cache = state.get("here_cache") if isinstance(state.get("here_cache"), dict) else {}
    cached_payload = cache.get("p") if isinstance(cache.get("p"), dict) else {}
    if cached_payload:
        return dict(cached_payload)
    day = int(state.get("day") or 0)
    index = int(state.get("spot_index") or 0)
    day_spots = [
        item for item in spots.get("spots") or []
        if isinstance(item, dict) and int(item.get("day") or 0) == day
    ]
    spot = day_spots[index] if 0 <= index < len(day_spots) else {}
    return {
        "day": day,
        "days_total": int(spots.get("days") or 0),
        "spot_no": index + 1 if spot else 0,
        "spots_today": len(day_spots),
        "spot": spot,
    }


def get_travel_public_status() -> dict[str, Any]:
    state = read_travel_state()
    dest_id = str(state.get("dest") or "").strip()
    destination = _destination(dest_id)
    spots = _spots_entry(dest_id)
    party = str(state.get("party") or "").strip()
    current_view = (
        _solo_current_view(state, spots)
        if party == "solo" and state
        else _together_current_view(state, spots)
        if state
        else {}
    )
    wallet = _read_json(TRAVEL_MCP_HOME / "wallet.json", {})
    collections = {
        name: value if isinstance(value := _read_json(TRAVEL_MCP_HOME / f"{name}.json", []), list) else []
        for name in ("souvenirs", "postcards", "diaries", "trips")
    }
    with _CHAT_LOCK:
        stored = _chat_state()
    sessions = stored.get("sessions") if isinstance(stored.get("sessions"), dict) else {}
    messages = sessions.get(_trip_key(state)) if isinstance(sessions.get(_trip_key(state)), list) else []
    return {
        "ok": True,
        "game_id": TRAVEL_GAME_ID,
        "available": travel_mcp_enabled(),
        "started": bool(state),
        "active": bool(state and not state.get("done")),
        "done": bool(state.get("done")),
        "trip_id": _trip_key(state) if state else "",
        "party": party,
        "phase": str(state.get("phase") or ""),
        "style": str(state.get("style") or ""),
        "day": int(current_view.get("day") or state.get("day") or 0),
        "days_total": int(current_view.get("days_total") or spots.get("days") or 0),
        "destination": destination,
        "current_view": current_view,
        "wallet": wallet if isinstance(wallet, dict) else {},
        "souvenirs": collections["souvenirs"],
        "postcards": collections["postcards"],
        "diaries": collections["diaries"],
        "trips": collections["trips"],
        "chat_messages": messages,
        "asset_base_url": "/miniapp-api/game-tools/travel/assets/",
    }


def travel_assets_root() -> Path | None:
    script = TRAVEL_MCP_SCRIPT
    if script is None:
        return None
    root = script.parent / "assets"
    return root if root.is_dir() else None
