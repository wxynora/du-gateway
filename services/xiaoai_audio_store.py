from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Optional, Tuple, Union

from config import HTML_PREVIEW_MAX_ITEMS, HTML_PREVIEW_TTL_SECONDS
from services.html_preview_store import resolve_preview_base_url_for_http_request

_lock = threading.Lock()
# token -> {"audio": bytes, "exp": float, "created": float, "format": str, "mime": str}
_store: dict[str, dict[str, Any]] = {}


def _purge_expired() -> None:
    now = time.time()
    dead = [t for t, v in _store.items() if v["exp"] <= now]
    for t in dead:
        del _store[t]


def _trim_to_max() -> None:
    if len(_store) <= HTML_PREVIEW_MAX_ITEMS:
        return
    order = sorted(_store.keys(), key=lambda t: _store[t]["created"])
    while len(_store) > HTML_PREVIEW_MAX_ITEMS and order:
        del _store[order.pop(0)]


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

    token = secrets.token_urlsafe(24)
    now = time.time()
    exp = now + HTML_PREVIEW_TTL_SECONDS

    with _lock:
        _purge_expired()
        _store[token] = {
            "audio": bytes(audio_bytes),
            "exp": exp,
            "created": now,
            "format": fmt,
            "mime": _mime_for_format(fmt),
        }
        _trim_to_max()

    base = (url_base or "").strip().rstrip("/")
    if not base:
        return False, "未配置公网域名或当前请求 Host 不可外网访问"

    return True, {
        "url": xiaoai_audio_url_for_token(token, audio_format=fmt, base_override=base),
        "token": token,
        "expires_in": HTML_PREVIEW_TTL_SECONDS,
        "audio_format": fmt,
    }


def get_xiaoai_audio_row(token: str) -> Optional[dict[str, Any]]:
    if not token or len(token) > 200:
        return None
    with _lock:
        _purge_expired()
        row = _store.get(token)
    if not row or row["exp"] <= time.time():
        return None
    return row
