from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

R2_KEY_MUSIC_BGM_CONTEXT = "global/music_bgm_context.json"
LOCAL_MUSIC_BGM_CONTEXT_FILE = DATA_DIR / "music_bgm_context.json"
MUSIC_BGM_CONTEXT_TTL_SECONDS = 15 * 60

_write_lock = threading.Lock()
logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str):
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_value(value: Any) -> float:
    try:
        n = float(value or 0)
    except Exception:
        return 0.0
    return n if n > 0 else 0.0


def _clip_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    return text[:limit].strip()


def _normalize_context(raw: Any, *, now_epoch: float | None = None, preserve_timestamp: bool = False) -> dict:
    data = raw if isinstance(raw, dict) else {}
    entry_id = _clip_text(data.get("entry_id") or data.get("id"), 120)
    title = _clip_text(data.get("title"), 120)
    artist = _clip_text(data.get("artist"), 120)
    active = _bool_value(data.get("active")) and bool(entry_id or title)
    is_playing = _bool_value(data.get("is_playing") or data.get("isPlaying")) and active
    now_ts = float(now_epoch if now_epoch is not None else time.time())
    if preserve_timestamp:
        updated_epoch = _float_value(data.get("updated_epoch") or data.get("updated_at_epoch")) or now_ts
        updated_at = _clip_text(data.get("updated_at"), 40) or now_beijing_iso()
    else:
        updated_epoch = now_ts
        updated_at = now_beijing_iso()
    segment = data.get("segment") if isinstance(data.get("segment"), dict) else None
    return {
        "active": active,
        "is_playing": is_playing,
        "entry_id": entry_id,
        "title": title,
        "artist": artist,
        "current_time": _float_value(data.get("current_time") or data.get("currentTime")),
        "duration_seconds": _float_value(data.get("duration_seconds") or data.get("durationSeconds")),
        "segment": segment or {},
        "source": "listen-with-du",
        "updated_at": updated_at,
        "updated_epoch": updated_epoch,
    }


def _read_local_context() -> dict:
    path = Path(LOCAL_MUSIC_BGM_CONTEXT_FILE)
    if not path.exists():
        return {}
    try:
        return _normalize_context(json.loads(path.read_text(encoding="utf-8")), preserve_timestamp=True)
    except Exception as e:
        logger.warning("读取本地一起听 BGM 状态失败 path=%s error=%s", path, e)
        return {}


def _write_local_context(payload: dict) -> bool:
    path = Path(LOCAL_MUSIC_BGM_CONTEXT_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return True
    except Exception as e:
        logger.error("写入本地一起听 BGM 状态失败 path=%s error=%s", path, e, exc_info=True)
        return False


def _read_context() -> tuple[dict, bool]:
    client = _s3_client()
    if client:
        data = _read_json(client, R2_KEY_MUSIC_BGM_CONTEXT)
        return _normalize_context(data, preserve_timestamp=True), True
    return _read_local_context(), False


def _write_context(payload: dict, use_r2: bool) -> bool:
    if use_r2:
        client = _s3_client()
        if not client:
            return False
        try:
            _write_json(client, R2_KEY_MUSIC_BGM_CONTEXT, payload)
            return True
        except Exception as e:
            logger.error("写入 R2 一起听 BGM 状态失败 error=%s", e, exc_info=True)
            return False
    return _write_local_context(payload)


def save_music_bgm_context(raw: Any) -> Optional[dict]:
    payload = _normalize_context(raw)
    use_r2 = bool(_s3_client())
    with _write_lock:
        if not _write_context(payload, use_r2):
            return None
    return dict(payload)


def get_music_bgm_context() -> Optional[dict]:
    payload, _ = _read_context()
    return dict(payload) if payload else None


def get_active_music_bgm_context(ttl_seconds: int = MUSIC_BGM_CONTEXT_TTL_SECONDS) -> Optional[dict]:
    payload = get_music_bgm_context()
    if not payload or not payload.get("active") or not payload.get("is_playing"):
        return None
    updated_epoch = _float_value(payload.get("updated_epoch"))
    if updated_epoch <= 0:
        return None
    elapsed = max(0.0, time.time() - updated_epoch)
    ttl = max(30, int(ttl_seconds or MUSIC_BGM_CONTEXT_TTL_SECONDS))
    if elapsed > ttl:
        return None
    current_time = _float_value(payload.get("current_time"))
    duration = _float_value(payload.get("duration_seconds"))
    if duration > 0 and current_time + elapsed >= duration - 0.25:
        return None
    payload["current_time"] = min(duration, current_time + elapsed) if duration > 0 else current_time + elapsed
    return payload
