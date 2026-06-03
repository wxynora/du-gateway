from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from botocore.exceptions import ClientError

from config import DATA_DIR, R2_BUCKET_NAME
from utils.log import get_logger

logger = get_logger(__name__)

R2_KEY_MUSIC_AUDIO_PREFIX = "music_listen/audio"
LOCAL_MUSIC_AUDIO_DIR = DATA_DIR / "music_listen_audio"
SUPPORTED_MUSIC_AUDIO_FORMATS = {"mp3", "m4a", "wav", "flac", "aac", "ogg", "aiff"}


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _safe_cache_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 80:
        return ""
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", raw):
        return ""
    return raw


def _audio_format_from_name(filename: str = "", content_type: str = "") -> str:
    ctype = str(content_type or "").split(";", 1)[0].strip().lower()
    if ctype in {"audio/mpeg", "audio/mp3"}:
        return "mp3"
    if ctype in {"audio/mp4", "audio/x-m4a"}:
        return "m4a"
    if ctype in {"audio/wav", "audio/x-wav"}:
        return "wav"
    if ctype == "audio/flac":
        return "flac"
    if ctype == "audio/aac":
        return "aac"
    if ctype == "audio/ogg":
        return "ogg"
    if ctype in {"audio/aiff", "audio/x-aiff"}:
        return "aiff"
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if suffix == "mpeg":
        return "mp3"
    return suffix if suffix in SUPPORTED_MUSIC_AUDIO_FORMATS else ""


def music_audio_content_type(audio_format: str, fallback: str = "") -> str:
    fmt = str(audio_format or "").strip().lower()
    if fmt == "mp3":
        return "audio/mpeg"
    if fmt == "m4a":
        return "audio/mp4"
    if fmt == "wav":
        return "audio/wav"
    if fmt == "flac":
        return "audio/flac"
    if fmt == "aac":
        return "audio/aac"
    if fmt == "ogg":
        return "audio/ogg"
    if fmt == "aiff":
        return "audio/aiff"
    return str(fallback or "application/octet-stream").strip() or "application/octet-stream"


def music_audio_key(cache_id: str, audio_format: str) -> str:
    safe_id = _safe_cache_id(cache_id)
    fmt = str(audio_format or "").strip().lower()
    if not safe_id or fmt not in SUPPORTED_MUSIC_AUDIO_FORMATS:
        return ""
    return f"{R2_KEY_MUSIC_AUDIO_PREFIX}/{safe_id}.{fmt}"


def music_audio_url(cache_id: str, audio_format: str) -> str:
    safe_id = _safe_cache_id(cache_id)
    fmt = str(audio_format or "").strip().lower()
    if not safe_id or fmt not in SUPPORTED_MUSIC_AUDIO_FORMATS:
        return ""
    return f"/api/music/listen/audio/{safe_id}.{fmt}"


def _local_audio_path(key: str) -> Path:
    name = Path(str(key or "").strip()).name
    return LOCAL_MUSIC_AUDIO_DIR / name


def save_music_audio(
    cache_id: str,
    filename: str,
    content: bytes,
    content_type: str = "",
) -> Optional[dict]:
    if not content:
        return None
    fmt = _audio_format_from_name(filename, content_type)
    if fmt not in SUPPORTED_MUSIC_AUDIO_FORMATS:
        return None
    key = music_audio_key(cache_id, fmt)
    if not key:
        return None
    ctype = music_audio_content_type(fmt, content_type)
    client = _s3_client()
    if client:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=bytes(content),
                ContentType=ctype,
            )
            return {
                "key": key,
                "url": music_audio_url(cache_id, fmt),
                "audio_format": fmt,
                "content_type": ctype,
                "size": len(content),
                "storage": "r2",
            }
        except Exception as e:
            logger.error("音乐音频上传 R2 失败 key=%s error=%s", key, e, exc_info=True)
            return None

    try:
        LOCAL_MUSIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path = _local_audio_path(key)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(bytes(content))
        tmp.replace(path)
        return {
            "key": key,
            "url": music_audio_url(cache_id, fmt),
            "audio_format": fmt,
            "content_type": ctype,
            "size": len(content),
            "storage": "local",
        }
    except Exception as e:
        logger.error("音乐音频落本地失败 key=%s error=%s", key, e, exc_info=True)
        return None


def get_music_audio(key: str) -> tuple[Optional[bytes], str]:
    k = str(key or "").strip()
    if not k.startswith(f"{R2_KEY_MUSIC_AUDIO_PREFIX}/") or ".." in k:
        return None, ""
    client = _s3_client()
    if client:
        try:
            resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=k)
            return resp["Body"].read(), str(resp.get("ContentType") or "").strip()
        except ClientError as e:
            code = (e.response or {}).get("Error", {}).get("Code", "")
            if code == "NoSuchKey":
                return None, ""
            logger.error("读取音乐音频 R2 失败 key=%s error=%s", k, e, exc_info=True)
            return None, ""
        except Exception as e:
            logger.error("读取音乐音频 R2 失败 key=%s error=%s", k, e, exc_info=True)
            return None, ""

    path = _local_audio_path(k)
    try:
        data = path.read_bytes()
    except Exception:
        return None, ""
    fmt = path.suffix.lower().lstrip(".")
    return data, music_audio_content_type(fmt)
