from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from config import DATA_DIR, HTML_PREVIEW_MAX_ITEMS, HTML_PREVIEW_TTL_SECONDS
from services.html_preview_store import resolve_preview_base_url_for_http_request

_lock = threading.Lock()
# token -> {"audio": bytes, "exp": float, "created": float, "format": str, "mime": str}
_store: dict[str, dict[str, Any]] = {}
_AUDIO_DIR = DATA_DIR / "xiaoai_audio"
_AUDIO_FORMATS = ("mp3", "wav")


def _audio_path(token: str, audio_format: str) -> Path:
    return _AUDIO_DIR / f"{token}.{audio_format}"


def _used_path(token: str) -> Path:
    return _AUDIO_DIR / f"{token}.used"


def _safe_token(token: str) -> str:
    raw = str(token or "").strip()
    if not raw or len(raw) > 200:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(ch not in allowed for ch in raw):
        return ""
    return raw


def _iter_audio_files() -> list[Path]:
    if not _AUDIO_DIR.exists():
        return []
    try:
        return [
            p
            for p in _AUDIO_DIR.iterdir()
            if p.is_file() and p.suffix.lstrip(".").lower() in _AUDIO_FORMATS
        ]
    except Exception:
        return []


def _purge_expired() -> None:
    now = time.time()
    dead = [t for t, v in _store.items() if v["exp"] <= now]
    for t in dead:
        del _store[t]
    for path in _iter_audio_files():
        try:
            if path.stat().st_mtime + HTML_PREVIEW_TTL_SECONDS <= now:
                path.unlink(missing_ok=True)
                _used_path(path.stem).unlink(missing_ok=True)
        except Exception:
            pass


def _trim_to_max() -> None:
    order = sorted(_store.keys(), key=lambda t: _store[t]["created"])
    while len(_store) > HTML_PREVIEW_MAX_ITEMS and order:
        del _store[order.pop(0)]
    files = sorted(_iter_audio_files(), key=lambda p: p.stat().st_mtime)
    while len(files) > HTML_PREVIEW_MAX_ITEMS:
        path = files.pop(0)
        try:
            path.unlink(missing_ok=True)
            _used_path(path.stem).unlink(missing_ok=True)
        except Exception:
            pass


def _mime_for_format(audio_format: str) -> str:
    fmt = str(audio_format or "mp3").strip().lower() or "mp3"
    if fmt == "wav":
        return "audio/wav"
    return "audio/mpeg"


def resolve_xiaoai_audio_base_url_for_http_request(request_url_root: str) -> str:
    return resolve_preview_base_url_for_http_request(request_url_root)


def xiaoai_audio_url_for_token(token: str, audio_format: str = "mp3", base_override: Optional[str] = None) -> str:
    fmt = str(audio_format or "mp3").strip().lower() or "mp3"
    base = (base_override or "").strip().rstrip("/")
    return f"{base}/api/xiaoai/tts/{token}.{fmt}"


def create_xiaoai_audio(
    audio_bytes: bytes,
    audio_format: str = "mp3",
    url_base: Optional[str] = None,
) -> Tuple[bool, Union[dict, str]]:
    if not audio_bytes:
        return False, "音频为空"
    fmt = str(audio_format or "mp3").strip().lower() or "mp3"
    if fmt not in ("mp3", "wav"):
        return False, f"暂不支持的音频格式：{fmt}"

    base = (url_base or "").strip().rstrip("/")
    if not base:
        return False, "未配置公网域名或当前请求 Host 不可外网访问"

    token = secrets.token_urlsafe(24)
    now = time.time()
    exp = now + HTML_PREVIEW_TTL_SECONDS
    payload = bytes(audio_bytes)
    path = _audio_path(token, fmt)

    with _lock:
        _purge_expired()
        try:
            _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.tmp")
            tmp.write_bytes(payload)
            tmp.replace(path)
        except Exception as e:
            return False, f"音频落盘失败：{e}"
        _store[token] = {
            "audio": payload,
            "exp": exp,
            "created": now,
            "format": fmt,
            "mime": _mime_for_format(fmt),
            "used": False,
        }
        _trim_to_max()

    return True, {
        "url": xiaoai_audio_url_for_token(token, audio_format=fmt, base_override=base),
        "token": token,
        "expires_in": HTML_PREVIEW_TTL_SECONDS,
        "audio_format": fmt,
    }


def get_xiaoai_audio_row(token: str, consume: bool = False) -> Optional[dict[str, Any]]:
    safe = _safe_token(token)
    if not safe:
        return None
    with _lock:
        _purge_expired()
        used_path = _used_path(safe)
        if used_path.exists():
            return None
        row = _store.get(safe)
        if row and row["exp"] > time.time():
            if consume:
                row["used"] = True
                try:
                    _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
                    used_path.write_text(str(int(time.time())), encoding="utf-8")
                except Exception:
                    pass
            return row
        for fmt in _AUDIO_FORMATS:
            path = _audio_path(safe, fmt)
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            except Exception:
                continue
            if stat.st_mtime + HTML_PREVIEW_TTL_SECONDS <= time.time():
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
                continue
            try:
                audio = path.read_bytes()
            except Exception:
                continue
            if not audio:
                continue
            if consume:
                try:
                    used_path.write_text(str(int(time.time())), encoding="utf-8")
                except Exception:
                    pass
            return {
                "audio": audio,
                "exp": stat.st_mtime + HTML_PREVIEW_TTL_SECONDS,
                "created": stat.st_mtime,
                "format": fmt,
                "mime": _mime_for_format(fmt),
            }
    return None
