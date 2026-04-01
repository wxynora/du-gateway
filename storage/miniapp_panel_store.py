import json
import threading
from pathlib import Path

from config import MINIAPP_PANEL_TRUSTED_DEVICES_FILE
from utils.time_aware import now_beijing_iso


_LOCK = threading.Lock()


def _load(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"items": []}
    if not isinstance(data, dict):
        return {"items": []}
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    return data


def _save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def upsert_trusted_device(device_id: str, note: str = "") -> dict:
    did = str(device_id or "").strip()
    if not did:
        return {}
    now = now_beijing_iso()
    clean_note = str(note or "").strip()[:120]
    with _LOCK:
        data = _load(MINIAPP_PANEL_TRUSTED_DEVICES_FILE)
        items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
        found = None
        for item in items:
            if str(item.get("id") or "").strip() == did:
                found = item
                break
        if found is None:
            found = {"id": did, "added_at": now}
            items.append(found)
        found["last_seen"] = now
        found["revoked"] = False
        if clean_note:
            found["note"] = clean_note
        elif not str(found.get("note") or "").strip():
            found["note"] = "Browser"
        data["items"] = items
        _save(MINIAPP_PANEL_TRUSTED_DEVICES_FILE, data)
        return dict(found)


def touch_trusted_device(device_id: str) -> dict:
    return upsert_trusted_device(device_id)


def is_trusted_device(device_id: str) -> bool:
    did = str(device_id or "").strip()
    if not did:
        return False
    with _LOCK:
        data = _load(MINIAPP_PANEL_TRUSTED_DEVICES_FILE)
        for item in (data.get("items") or []):
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() == did:
                return not bool(item.get("revoked"))
    return False


def list_trusted_devices() -> list[dict]:
    with _LOCK:
        data = _load(MINIAPP_PANEL_TRUSTED_DEVICES_FILE)
        items = [dict(x) for x in (data.get("items") or []) if isinstance(x, dict)]
    items.sort(key=lambda item: str(item.get("last_seen") or item.get("added_at") or ""), reverse=True)
    return items


def revoke_trusted_device(device_id: str) -> bool:
    did = str(device_id or "").strip()
    if not did:
        return False
    changed = False
    with _LOCK:
        data = _load(MINIAPP_PANEL_TRUSTED_DEVICES_FILE)
        items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
        for item in items:
            if str(item.get("id") or "").strip() != did:
                continue
            item["revoked"] = True
            item["revoked_at"] = now_beijing_iso()
            changed = True
            break
        if changed:
            data["items"] = items
            _save(MINIAPP_PANEL_TRUSTED_DEVICES_FILE, data)
    return changed
