from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR
from utils.log import get_logger
from utils.time_aware import now_beijing_iso
from services.music_lyrics import normalize_lyrics_payload

R2_KEY_MUSIC_MELODY_CACHE = "global/music_melody_cache.json"
LOCAL_MUSIC_MELODY_CACHE_FILE = DATA_DIR / "music_melody_cache.json"

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


def _normalize_text(value: Any, limit: int = 200) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def normalize_music_identity(title: Any, artist: Any) -> tuple[str, str]:
    return _normalize_text(title, 200), _normalize_text(artist, 200)


def _identity_key_part(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "").strip()).casefold()


def make_music_melody_cache_key(
    title: str,
    artist: str,
    provider: str,
    model: str,
    prompt_version: str,
) -> str:
    clean_title, clean_artist = normalize_music_identity(title, artist)
    raw = "\n".join(
        [
            _identity_key_part(clean_artist),
            _identity_key_part(clean_title),
            _identity_key_part(provider),
            _identity_key_part(model),
            _identity_key_part(prompt_version),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _empty_payload() -> dict:
    return {"items": {}, "updated_at": ""}


def _normalize_payload(data: Any) -> dict:
    if not isinstance(data, dict):
        return _empty_payload()
    items = data.get("items")
    if isinstance(items, list):
        items = {
            str(item.get("cache_key") or item.get("id") or "").strip(): item
            for item in items
            if isinstance(item, dict) and str(item.get("cache_key") or item.get("id") or "").strip()
        }
    if not isinstance(items, dict):
        items = {}
    clean_items: dict[str, dict] = {}
    for key, item in items.items():
        if not isinstance(item, dict):
            continue
        cache_key = str(item.get("cache_key") or key or "").strip()
        if not cache_key:
            continue
        clean_items[cache_key] = {
            "id": str(item.get("id") or cache_key).strip() or cache_key,
            "cache_key": cache_key,
            "title": _normalize_text(item.get("title"), 200),
            "artist": _normalize_text(item.get("artist"), 200),
            "provider": _normalize_text(item.get("provider"), 80),
            "model": _normalize_text(item.get("model"), 120),
            "prompt_version": _normalize_text(item.get("prompt_version"), 40),
            "melody_text": str(item.get("melody_text") or "").strip(),
            "overall_trend": str(item.get("overall_trend") or "").strip(),
            "structured": item.get("structured") if isinstance(item.get("structured"), dict) else {},
            "lyrics": normalize_lyrics_payload(item.get("lyrics")),
            "audio_key": _normalize_text(item.get("audio_key"), 240),
            "audio_url": _normalize_text(item.get("audio_url"), 500),
            "audio_format": _normalize_text(item.get("audio_format"), 32),
            "audio_content_type": _normalize_text(item.get("audio_content_type"), 80),
            "audio_size": int(float(item.get("audio_size") or 0)),
            "duration_seconds": float(item.get("duration_seconds") or 0),
            "source_provider": _normalize_text(item.get("source_provider"), 40),
            "source_track_id": _normalize_text(item.get("source_track_id"), 120),
            "source_cover_url": _normalize_text(item.get("source_cover_url"), 500),
            "created_at": str(item.get("created_at") or "").strip(),
            "updated_at": str(item.get("updated_at") or "").strip(),
        }
    return {"items": clean_items, "updated_at": str(data.get("updated_at") or "").strip()}


def _read_local_payload() -> dict:
    path = Path(LOCAL_MUSIC_MELODY_CACHE_FILE)
    if not path.exists():
        return _empty_payload()
    try:
        return _normalize_payload(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        logger.warning("读取本地音乐旋律缓存失败 path=%s error=%s", path, e)
        return _empty_payload()


def _write_local_payload(payload: dict) -> bool:
    path = Path(LOCAL_MUSIC_MELODY_CACHE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return True
    except Exception as e:
        logger.error("写入本地音乐旋律缓存失败 path=%s error=%s", path, e, exc_info=True)
        return False


def _read_payload() -> tuple[dict, bool]:
    client = _s3_client()
    if client:
        data = _read_json(client, R2_KEY_MUSIC_MELODY_CACHE)
        return _normalize_payload(data), True
    return _read_local_payload(), False


def _write_payload(payload: dict, use_r2: bool) -> bool:
    payload = _normalize_payload(payload)
    payload["updated_at"] = now_beijing_iso()
    if use_r2:
        client = _s3_client()
        if not client:
            return False
        try:
            _write_json(client, R2_KEY_MUSIC_MELODY_CACHE, payload)
            return True
        except Exception as e:
            logger.error("写入 R2 音乐旋律缓存失败 error=%s", e, exc_info=True)
            return False
    return _write_local_payload(payload)


def get_music_melody_entry(
    title: str,
    artist: str,
    provider: str,
    model: str,
    prompt_version: str,
) -> Optional[dict]:
    clean_title, clean_artist = normalize_music_identity(title, artist)
    if not clean_title:
        return None
    cache_key = make_music_melody_cache_key(clean_title, clean_artist, provider, model, prompt_version)
    payload, _ = _read_payload()
    item = (payload.get("items") or {}).get(cache_key)
    return dict(item) if isinstance(item, dict) else None


def get_music_melody_entry_by_id(entry_id: str) -> Optional[dict]:
    eid = str(entry_id or "").strip()
    if not eid:
        return None
    payload, _ = _read_payload()
    item = (payload.get("items") or {}).get(eid)
    if isinstance(item, dict):
        return dict(item)
    for candidate in (payload.get("items") or {}).values():
        if isinstance(candidate, dict) and str(candidate.get("id") or "").strip() == eid:
            return dict(candidate)
    return None


def save_music_melody_entry(
    title: str,
    artist: str,
    provider: str,
    model: str,
    prompt_version: str,
    melody_text: str,
    overall_trend: str = "",
    structured: Optional[dict] = None,
    lyrics: Optional[dict] = None,
    audio_key: str = "",
    audio_url: str = "",
    audio_format: str = "",
    audio_content_type: str = "",
    audio_size: int = 0,
    duration_seconds: float = 0,
) -> Optional[dict]:
    clean_title, clean_artist = normalize_music_identity(title, artist)
    clean_text = str(melody_text or "").strip()
    if not clean_title or not clean_text:
        return None
    cache_key = make_music_melody_cache_key(clean_title, clean_artist, provider, model, prompt_version)
    now_ts = now_beijing_iso()
    with _write_lock:
        payload, use_r2 = _read_payload()
        items = payload.setdefault("items", {})
        old = items.get(cache_key) if isinstance(items.get(cache_key), dict) else {}
        entry = {
            "id": str(old.get("id") or cache_key),
            "cache_key": cache_key,
            "title": clean_title,
            "artist": clean_artist,
            "provider": _normalize_text(provider, 80),
            "model": _normalize_text(model, 120),
            "prompt_version": _normalize_text(prompt_version, 40),
            "melody_text": clean_text,
            "overall_trend": str(overall_trend or "").strip(),
            "structured": structured if isinstance(structured, dict) else {},
            "lyrics": normalize_lyrics_payload(lyrics if lyrics is not None else old.get("lyrics")),
            "audio_key": _normalize_text(audio_key or old.get("audio_key"), 240),
            "audio_url": _normalize_text(audio_url or old.get("audio_url"), 500),
            "audio_format": _normalize_text(audio_format or old.get("audio_format"), 32),
            "audio_content_type": _normalize_text(audio_content_type or old.get("audio_content_type"), 80),
            "audio_size": int(float(audio_size or old.get("audio_size") or 0)),
            "duration_seconds": float(duration_seconds or old.get("duration_seconds") or 0),
            "source_provider": _normalize_text(old.get("source_provider"), 40),
            "source_track_id": _normalize_text(old.get("source_track_id"), 120),
            "source_cover_url": _normalize_text(old.get("source_cover_url"), 500),
            "created_at": str(old.get("created_at") or now_ts),
            "updated_at": now_ts,
        }
        items[cache_key] = entry
        ok = _write_payload(payload, use_r2)
    return entry if ok else None


def update_music_melody_source_by_id(
    entry_id: str,
    *,
    source_provider: str,
    source_track_id: str,
    source_cover_url: str = "",
) -> Optional[dict]:
    eid = str(entry_id or "").strip()
    if not eid:
        return None
    now_ts = now_beijing_iso()
    with _write_lock:
        payload, use_r2 = _read_payload()
        items = payload.setdefault("items", {})
        cache_key = ""
        for key, item in items.items():
            if isinstance(item, dict) and (str(item.get("id") or "").strip() == eid or str(key or "").strip() == eid):
                cache_key = str(key or "").strip()
                break
        if not cache_key:
            return None
        old = items.get(cache_key) if isinstance(items.get(cache_key), dict) else {}
        if not old:
            return None
        entry = dict(old)
        entry.update(
            {
                "source_provider": _normalize_text(source_provider, 40),
                "source_track_id": _normalize_text(source_track_id, 120),
                "source_cover_url": _normalize_text(source_cover_url, 500),
                "updated_at": now_ts,
            }
        )
        items[cache_key] = entry
        ok = _write_payload(payload, use_r2)
    return entry if ok else None


def update_music_melody_audio(
    title: str,
    artist: str,
    provider: str,
    model: str,
    prompt_version: str,
    *,
    audio_key: str,
    audio_url: str,
    audio_format: str,
    audio_content_type: str,
    audio_size: int,
    duration_seconds: float = 0,
) -> Optional[dict]:
    clean_title, clean_artist = normalize_music_identity(title, artist)
    if not clean_title:
        return None
    cache_key = make_music_melody_cache_key(clean_title, clean_artist, provider, model, prompt_version)
    now_ts = now_beijing_iso()
    with _write_lock:
        payload, use_r2 = _read_payload()
        items = payload.setdefault("items", {})
        old = items.get(cache_key) if isinstance(items.get(cache_key), dict) else {}
        if not old or not str(old.get("melody_text") or "").strip():
            return None
        entry = dict(old)
        entry.update(
            {
                "audio_key": _normalize_text(audio_key, 240),
                "audio_url": _normalize_text(audio_url, 500),
                "audio_format": _normalize_text(audio_format, 32),
                "audio_content_type": _normalize_text(audio_content_type, 80),
                "audio_size": int(float(audio_size or 0)),
                "duration_seconds": float(duration_seconds or old.get("duration_seconds") or 0),
                "updated_at": now_ts,
            }
        )
        items[cache_key] = entry
        ok = _write_payload(payload, use_r2)
    return entry if ok else None


def clear_music_melody_audio_by_keys(audio_keys: list[str]) -> int:
    keys = {str(key or "").strip() for key in audio_keys if str(key or "").strip()}
    if not keys:
        return 0
    changed = 0
    with _write_lock:
        payload, use_r2 = _read_payload()
        items = payload.setdefault("items", {})
        for cache_key, old in list(items.items()):
            if not isinstance(old, dict) or str(old.get("audio_key") or "").strip() not in keys:
                continue
            entry = dict(old)
            entry.update(
                {
                    "audio_key": "",
                    "audio_url": "",
                    "audio_format": "",
                    "audio_content_type": "",
                    "audio_size": 0,
                }
            )
            items[cache_key] = entry
            changed += 1
        if changed and not _write_payload(payload, use_r2):
            return 0
    return changed


def update_music_melody_lyrics_by_id(entry_id: str, lyrics: dict) -> Optional[dict]:
    eid = str(entry_id or "").strip()
    if not eid:
        return None
    now_ts = now_beijing_iso()
    with _write_lock:
        payload, use_r2 = _read_payload()
        items = payload.setdefault("items", {})
        cache_key = ""
        for key, item in items.items():
            if isinstance(item, dict) and (str(item.get("id") or "").strip() == eid or str(key or "").strip() == eid):
                cache_key = str(key or "").strip()
                break
        if not cache_key:
            return None
        old = items.get(cache_key) if isinstance(items.get(cache_key), dict) else {}
        if not old:
            return None
        entry = dict(old)
        entry["lyrics"] = normalize_lyrics_payload(lyrics)
        entry["updated_at"] = now_ts
        items[cache_key] = entry
        ok = _write_payload(payload, use_r2)
    return entry if ok else None


def list_music_melody_entries(limit: int = 50) -> list[dict]:
    payload, _ = _read_payload()
    items = [dict(v) for v in (payload.get("items") or {}).values() if isinstance(v, dict)]
    items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return items[: max(1, min(200, int(limit or 50)))]
