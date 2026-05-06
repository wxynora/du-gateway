import json
import threading

from config import DATA_DIR


SILENCE_MODE_FILE = DATA_DIR / "silence_mode.json"
_LOCK = threading.Lock()


def get_state() -> dict:
    try:
        if not SILENCE_MODE_FILE.exists():
            return {"enabled": False, "updated_at": ""}
        with SILENCE_MODE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return {
            "enabled": bool(data.get("enabled")),
            "updated_at": str(data.get("updated_at") or ""),
        }
    except Exception:
        return {"enabled": False, "updated_at": ""}


def is_enabled() -> bool:
    return bool(get_state().get("enabled"))


def set_enabled(enabled: bool, updated_at: str = "") -> dict:
    payload = {"enabled": bool(enabled), "updated_at": str(updated_at or "")}
    with _LOCK:
        SILENCE_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SILENCE_MODE_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload
