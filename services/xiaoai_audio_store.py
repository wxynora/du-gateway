from __future__ import annotations

import secrets
import threading
import time
import json
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from config import DATA_DIR, HTML_PREVIEW_MAX_ITEMS, HTML_PREVIEW_TTL_SECONDS
from services.html_preview_store import resolve_preview_base_url_for_http_request

_lock = threading.Lock()
# token -> {"audio": bytes, "exp": float, "created": float, "format": str, "mime": str}
_store: dict[str, dict[str, Any]] = {}
_AUDIO_DIR = DATA_DIR / "xiaoai_audio"
_AUDIO_FORMATS = ("mp3", "wav")
_LATEST_TOKEN = "latest"


def _audio_path(token: str, audio_format: str) -> Path:
    return _AUDIO_DIR / f"{token}.{audio_format}"


def _meta_path(token: str) -> Path:
    return _AUDIO_DIR / f"{token}.json"


def _used_path(token: str, version: str = "") -> Path:
    if version:
        return _AUDIO_DIR / f"{token}.{version}.used"
    return _AUDIO_DIR / f"{token}.used"


def _safe_token(token: str) -> str:
    raw = str(token or "").strip()
    if not raw or len(raw) > 200:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(ch not in allowed for ch in raw):
        return ""
    return raw


def _safe_version(version: Any) -> str:
    return _safe_token(str(version or "").strip())


def _unlink_token_sidecars(token: str) -> None:
    if not _AUDIO_DIR.exists():
        return
    prefix = f"{token}."
    for path in _AUDIO_DIR.iterdir():
        try:
            if not path.is_file():
                continue
            if path.name == f"{token}.used" or path.name == f"{token}.json" or (
                path.name.startswith(prefix) and path.name.endswith(".used")
            ):
                path.unlink(missing_ok=True)
        except Exception:
            pass


def _clear_audio_dir() -> None:
    if not _AUDIO_DIR.exists():
        return
    for path in _AUDIO_DIR.iterdir():
        try:
            if not path.is_file():
                continue
            suffix = path.suffix.lstrip(".").lower()
            if suffix in _AUDIO_FORMATS or suffix in ("used", "json") or path.name.endswith(".used"):
                path.unlink(missing_ok=True)
        except Exception:
            pass


def _read_meta(token: str) -> dict[str, Any]:
    try:
        data = json.loads(_meta_path(token).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_meta(token: str, meta: dict[str, Any]) -> None:
    _meta_path(token).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


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
                _unlink_token_sidecars(path.stem)
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
            _unlink_token_sidecars(path.stem)
        except Exception:
            pass


def _mime_for_format(audio_format: str) -> str:
    fmt = str(audio_format or "mp3").strip().lower() or "mp3"
    if fmt == "wav":
        return "audio/wav"
    return "audio/mpeg"


def resolve_xiaoai_audio_base_url_for_http_request(request_url_root: str) -> str:
    return resolve_preview_base_url_for_http_request(request_url_root)


def xiaoai_audio_url_for_token(
    token: str,
    audio_format: str = "mp3",
    base_override: Optional[str] = None,
    version: str = "",
) -> str:
    fmt = str(audio_format or "mp3").strip().lower() or "mp3"
    base = (base_override or "").strip().rstrip("/")
    url = f"{base}/api/xiaoai/tts/{token}.{fmt}"
    if version:
        url = f"{url}?v={version}"
    return url


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

    token = _LATEST_TOKEN
    version = secrets.token_urlsafe(12)
    now = time.time()
    exp = now + HTML_PREVIEW_TTL_SECONDS
    payload = bytes(audio_bytes)
    path = _audio_path(token, fmt)

    with _lock:
        _purge_expired()
        try:
            _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            _clear_audio_dir()
            tmp = path.with_name(f".{path.name}.tmp")
            tmp.write_bytes(payload)
            tmp.replace(path)
            _write_meta(
                token,
                {
                    "version": version,
                    "format": fmt,
                    "mime": _mime_for_format(fmt),
                    "created": now,
                    "exp": exp,
                },
            )
        except Exception as e:
            return False, f"音频落盘失败：{e}"
        _store.clear()
        _store[token] = {
            "audio": payload,
            "exp": exp,
            "created": now,
            "format": fmt,
            "mime": _mime_for_format(fmt),
            "used": False,
            "version": version,
        }
        _trim_to_max()

    return True, {
        "url": xiaoai_audio_url_for_token(token, audio_format=fmt, base_override=base, version=version),
        "token": token,
        "version": version,
        "expires_in": HTML_PREVIEW_TTL_SECONDS,
        "audio_format": fmt,
    }


def _consume_used_path(path: Path) -> None:
    try:
        _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        pass


def get_xiaoai_audio_row(token: str, consume: bool = False, version: str = "") -> Optional[dict[str, Any]]:
    safe = _safe_token(token)
    if not safe:
        return None
    requested_version = _safe_version(version)
    with _lock:
        _purge_expired()
        if safe == _LATEST_TOKEN:
            row = _store.get(safe)
            if row and row["exp"] > time.time():
                row_version = _safe_version(row.get("version"))
                if requested_version and row_version != requested_version:
                    return None
                used_path = _used_path(safe, row_version)
                if used_path.exists():
                    return None
                if consume:
                    row["used"] = True
                    _consume_used_path(used_path)
                return row

            meta = _read_meta(safe)
            meta_version = _safe_version(meta.get("version"))
            if requested_version and meta_version != requested_version:
                return None
            fmt = str(meta.get("format") or "mp3").strip().lower()
            if fmt not in _AUDIO_FORMATS:
                fmt = "mp3"
            path = _audio_path(safe, fmt)
            try:
                stat = path.stat()
            except Exception:
                return None
            exp = float(meta.get("exp") or (stat.st_mtime + HTML_PREVIEW_TTL_SECONDS))
            if exp <= time.time():
                try:
                    path.unlink(missing_ok=True)
                    _unlink_token_sidecars(safe)
                except Exception:
                    pass
                return None
            used_path = _used_path(safe, meta_version)
            if used_path.exists():
                return None
            try:
                audio = path.read_bytes()
            except Exception:
                return None
            if not audio:
                return None
            if consume:
                _consume_used_path(used_path)
            return {
                "audio": audio,
                "exp": exp,
                "created": float(meta.get("created") or stat.st_mtime),
                "format": fmt,
                "mime": str(meta.get("mime") or _mime_for_format(fmt)),
                "version": meta_version,
            }

        used_path = _used_path(safe)
        if used_path.exists():
            return None
        row = _store.get(safe)
        if row and row["exp"] > time.time():
            if consume:
                row["used"] = True
                _consume_used_path(used_path)
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
                _consume_used_path(used_path)
            return {
                "audio": audio,
                "exp": stat.st_mtime + HTML_PREVIEW_TTL_SECONDS,
                "created": stat.st_mtime,
                "format": fmt,
                "mime": _mime_for_format(fmt),
            }
    return None
