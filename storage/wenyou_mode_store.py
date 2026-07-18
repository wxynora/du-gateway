import json
import threading

from config import DATA_DIR
from utils.time_aware import now_beijing_iso


WENYOU_MODE_FILE = DATA_DIR / "wenyou_mode.json"
_LOCK = threading.Lock()


def get_state() -> dict:
    try:
        if not WENYOU_MODE_FILE.exists():
            return {"enabled": False, "updated_at": ""}
        with WENYOU_MODE_FILE.open("r", encoding="utf-8") as f:
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
    payload = {"enabled": bool(enabled), "updated_at": str(updated_at or now_beijing_iso())}
    with _LOCK:
        WENYOU_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with WENYOU_MODE_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload
