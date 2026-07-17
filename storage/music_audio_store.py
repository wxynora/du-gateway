from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from botocore.exceptions import ClientError

from config import DATA_DIR, MUSIC_AUDIO_TTL_SECONDS, R2_BUCKET_NAME
from utils.log import get_logger

logger = get_logger(__name__)

R2_KEY_MUSIC_AUDIO_PREFIX = "music_listen/audio"
LOCAL_MUSIC_AUDIO_DIR = DATA_DIR / "music_listen_audio"
SUPPORTED_MUSIC_AUDIO_FORMATS = {"mp3", "m4a", "wav", "flac", "aac", "ogg", "aiff"}
MUSIC_AUDIO_PRUNE_INTERVAL_SECONDS = 5 * 60

_prune_lock = threading.Lock()
_last_prune_monotonic = 0.0


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


def _ttl_seconds() -> int:
    return max(5 * 60, int(MUSIC_AUDIO_TTL_SECONDS or 7200))


def _expires_at_epoch() -> int:
    return int(time.time()) + _ttl_seconds()


def _datetime_epoch(value: object) -> float:
    if not isinstance(value, datetime):
        return 0.0
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _response_is_expired(response: dict) -> bool:
    metadata = response.get("Metadata") if isinstance(response.get("Metadata"), dict) else {}
    try:
        expires_at = float(metadata.get("expires-at") or 0)
    except Exception:
        expires_at = 0.0
    if expires_at > 0:
        return expires_at <= time.time()
    modified_at = _datetime_epoch(response.get("LastModified"))
    return modified_at > 0 and modified_at + _ttl_seconds() <= time.time()


def delete_music_audio(key: str) -> bool:
    k = str(key or "").strip()
    if not k.startswith(f"{R2_KEY_MUSIC_AUDIO_PREFIX}/") or ".." in k:
        return False
    client = _s3_client()
    if client:
        try:
            client.delete_object(Bucket=R2_BUCKET_NAME, Key=k)
            return True
        except Exception as e:
            logger.warning("删除过期音乐音频 R2 失败 key=%s error=%s", k, e)
            return False

    path = _local_audio_path(k)
    try:
        path.unlink(missing_ok=True)
        return True
    except Exception as e:
        logger.warning("删除过期音乐音频本地文件失败 key=%s error=%s", k, e)
        return False


def prune_expired_music_audio(*, force: bool = False) -> list[str]:
    global _last_prune_monotonic

    now_mono = time.monotonic()
    with _prune_lock:
        if not force and now_mono - _last_prune_monotonic < MUSIC_AUDIO_PRUNE_INTERVAL_SECONDS:
            return []
        _last_prune_monotonic = now_mono

        expired_keys: list[str] = []
        client = _s3_client()
        if client:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=_ttl_seconds())
            token = None
            r2_candidates: list[str] = []
            try:
                while True:
                    kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": f"{R2_KEY_MUSIC_AUDIO_PREFIX}/"}
                    if token:
                        kwargs["ContinuationToken"] = token
                    response = client.list_objects_v2(**kwargs)
                    for item in response.get("Contents") or []:
                        key = str(item.get("Key") or "").strip()
                        modified_at = item.get("LastModified")
                        if key and isinstance(modified_at, datetime):
                            aware = modified_at if modified_at.tzinfo else modified_at.replace(tzinfo=timezone.utc)
                            if aware <= cutoff:
                                r2_candidates.append(key)
                    if not response.get("IsTruncated"):
                        break
                    token = response.get("NextContinuationToken")
                for offset in range(0, len(r2_candidates), 1000):
                    chunk = r2_candidates[offset : offset + 1000]
                    deleted = client.delete_objects(
                        Bucket=R2_BUCKET_NAME,
                        Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
                    )
                    failed = {
                        str(item.get("Key") or "").strip()
                        for item in deleted.get("Errors") or []
                        if str(item.get("Key") or "").strip()
                    }
                    expired_keys.extend(key for key in chunk if key not in failed)
                    if failed:
                        logger.warning("部分过期音乐音频 R2 删除失败 keys=%s", sorted(failed))
            except Exception as e:
                logger.warning("清理过期音乐音频 R2 失败 error=%s", e)

        if LOCAL_MUSIC_AUDIO_DIR.exists():
            cutoff_epoch = time.time() - _ttl_seconds()
            for path in LOCAL_MUSIC_AUDIO_DIR.iterdir():
                if not path.is_file():
                    continue
                try:
                    if path.stat().st_mtime > cutoff_epoch:
                        continue
                    path.unlink(missing_ok=True)
                    expired_keys.append(f"{R2_KEY_MUSIC_AUDIO_PREFIX}/{path.name}")
                except Exception as e:
                    logger.warning("清理过期音乐音频本地文件失败 path=%s error=%s", path, e)

        return list(dict.fromkeys(expired_keys))


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
    expires_at = _expires_at_epoch()
    client = _s3_client()
    if client:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=bytes(content),
                ContentType=ctype,
                Metadata={"expires-at": str(expires_at)},
            )
            return {
                "key": key,
                "url": music_audio_url(cache_id, fmt),
                "audio_format": fmt,
                "content_type": ctype,
                "size": len(content),
                "storage": "r2",
                "expires_at": expires_at,
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
            "expires_at": expires_at,
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
            if _response_is_expired(resp):
                body = resp.get("Body")
                if body and hasattr(body, "close"):
                    body.close()
                delete_music_audio(k)
                return None, ""
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
        if path.stat().st_mtime + _ttl_seconds() <= time.time():
            path.unlink(missing_ok=True)
            return None, ""
        data = path.read_bytes()
    except Exception:
        return None, ""
    fmt = path.suffix.lower().lstrip(".")
    return data, music_audio_content_type(fmt)
