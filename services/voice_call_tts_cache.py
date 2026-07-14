import json
import os
import re
import secrets
import time
from pathlib import Path

from config import DATA_DIR


VOICE_CALL_TTS_TTL_SECONDS = 600
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{24,80}$")
_CACHE_DIR = Path(DATA_DIR) / "voice_call_tts_cache"


def _safe_token(value: str) -> str:
    token = str(value or "").strip()
    return token if _TOKEN_RE.fullmatch(token) else ""


def _safe_format(value: str) -> str:
    audio_format = str(value or "mp3").strip().lower()
    return audio_format if audio_format in {"mp3", "wav"} else ""


def _paths(token: str, audio_format: str) -> tuple[Path, Path]:
    return _CACHE_DIR / f"{token}.{audio_format}", _CACHE_DIR / f"{token}.json"


def _delete_token(token: str, audio_format: str) -> None:
    audio_path, meta_path = _paths(token, audio_format)
    audio_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)


def cleanup_expired_voice_call_tts(now: float | None = None) -> int:
    if not _CACHE_DIR.exists():
        return 0
    current = float(now if now is not None else time.time())
    removed = 0
    for meta_path in _CACHE_DIR.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            token = _safe_token(meta_path.stem)
            audio_format = _safe_format(meta.get("audio_format"))
            expired = float(meta.get("expires_at") or 0) <= current
        except Exception:
            token = _safe_token(meta_path.stem)
            audio_format = ""
            expired = True
        if not expired:
            continue
        if token and audio_format:
            _delete_token(token, audio_format)
        else:
            meta_path.unlink(missing_ok=True)
        removed += 1
    return removed


def save_voice_call_tts_audio(
    audio_bytes: bytes,
    *,
    audio_format: str,
    turn_id: str,
    ttl_seconds: int = VOICE_CALL_TTS_TTL_SECONDS,
) -> dict:
    content = bytes(audio_bytes or b"")
    fmt = _safe_format(audio_format)
    if not content or not fmt:
        raise ValueError("invalid voice call TTS audio")
    cleanup_expired_voice_call_tts()
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    audio_path, meta_path = _paths(token, fmt)
    expires_in = max(30, min(int(ttl_seconds or VOICE_CALL_TTS_TTL_SECONDS), 3600))
    expires_at = time.time() + expires_in
    audio_tmp = audio_path.with_suffix(audio_path.suffix + ".tmp")
    meta_tmp = meta_path.with_suffix(".json.tmp")
    audio_tmp.write_bytes(content)
    meta_tmp.write_text(
        json.dumps(
            {
                "audio_format": fmt,
                "turn_id": str(turn_id or "").strip()[:160],
                "expires_at": expires_at,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.replace(audio_tmp, audio_path)
    os.replace(meta_tmp, meta_path)
    return {
        "token": token,
        "audio_format": fmt,
        "expires_in": expires_in,
        "bytes": len(content),
    }


def load_voice_call_tts_audio(token: str, audio_format: str) -> tuple[bytes, str] | None:
    safe_token = _safe_token(token)
    fmt = _safe_format(audio_format)
    if not safe_token or not fmt:
        return None
    audio_path, meta_path = _paths(safe_token, fmt)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if _safe_format(meta.get("audio_format")) != fmt:
            return None
        if float(meta.get("expires_at") or 0) <= time.time():
            _delete_token(safe_token, fmt)
            return None
        content = audio_path.read_bytes()
    except Exception:
        return None
    if not content:
        _delete_token(safe_token, fmt)
        return None
    mime = "audio/wav" if fmt == "wav" else "audio/mpeg"
    return content, mime


def cancel_voice_call_tts_turn(turn_id: str) -> int:
    wanted = str(turn_id or "").strip()
    if not wanted or not _CACHE_DIR.exists():
        return 0
    removed = 0
    for meta_path in _CACHE_DIR.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(meta.get("turn_id") or "").strip() != wanted:
            continue
        token = _safe_token(meta_path.stem)
        audio_format = _safe_format(meta.get("audio_format"))
        if token and audio_format:
            _delete_token(token, audio_format)
            removed += 1
    return removed
