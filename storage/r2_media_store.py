"""R2-backed generic objects, SumiTalk media, and device screenshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from uuid import uuid4

from botocore.exceptions import ClientError

from config import R2_BUCKET_NAME
from storage.r2_client import _read_json, _s3_client
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, today_beijing

logger = get_logger(__name__)

R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX = "sumitalk/chat_media"


def get_object_bytes(key: str) -> tuple[Optional[bytes], str]:
    """Read arbitrary object bytes for callers that already validate the key."""
    normalized = (key or "").strip()
    if not normalized:
        return None, ""
    client = _s3_client()
    if not client:
        return None, ""
    try:
        response = client.get_object(Bucket=R2_BUCKET_NAME, Key=normalized)
        data = response["Body"].read()
        content_type = (response.get("ContentType") or "application/octet-stream").strip()
        return data, content_type
    except ClientError as exc:
        code = (exc.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None, ""
        logger.error("get_object_bytes failed key=%s error=%s", normalized, exc, exc_info=True)
        return None, ""
    except Exception as exc:
        logger.error("get_object_bytes failed key=%s error=%s", normalized, exc, exc_info=True)
        return None, ""


def _sumitalk_chat_media_ext(filename: str, content_type: str, kind: str) -> tuple[str, str]:
    normalized_type = (content_type or "").strip().lower()
    ext = Path(filename or "").suffix.lower()
    if kind == "document":
        if ext == ".pdf" or "pdf" in normalized_type:
            return ".pdf", "application/pdf"
        if ext == ".docx" or "wordprocessingml" in normalized_type:
            return ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if ext in (".md", ".markdown") or "markdown" in normalized_type:
            return ".md", "text/markdown"
        return ".txt", "text/plain"
    if kind == "audio":
        if "mpeg" in normalized_type or "mp3" in normalized_type:
            return ".mp3", "audio/mpeg"
        if "mp4" in normalized_type or ext in (".m4a", ".mp4"):
            return ".m4a", "audio/mp4"
        if "wav" in normalized_type or ext == ".wav":
            return ".wav", "audio/wav"
        if "ogg" in normalized_type or ext == ".ogg":
            return ".ogg", "audio/ogg"
        return ".webm", "audio/webm"
    if "jpeg" in normalized_type or "jpg" in normalized_type or ext in (".jpg", ".jpeg"):
        return ".jpg", "image/jpeg"
    if "png" in normalized_type or ext == ".png":
        return ".png", "image/png"
    if "webp" in normalized_type or ext == ".webp":
        return ".webp", "image/webp"
    if "gif" in normalized_type or ext == ".gif":
        return ".gif", "image/gif"
    return ".jpg", "image/jpeg"


def upload_sumitalk_chat_media_file(kind: str, filename: str, content: bytes, content_type: str) -> Optional[dict]:
    """Upload a SumiTalk attachment and return message metadata."""
    media_kind = (kind or "").strip().lower()
    if media_kind not in {"image", "audio", "document"} or not content:
        return None
    ext, normalized_type = _sumitalk_chat_media_ext(filename, content_type, media_kind)
    key = f"{R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX}/{media_kind}/{today_beijing()}/{uuid4().hex}{ext}"
    client = _s3_client()
    if not client:
        return None
    try:
        client.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=content, ContentType=normalized_type)
        return {
            "key": key,
            "kind": media_kind,
            "name": Path(filename or key).name,
            "contentType": normalized_type,
            "size": len(content),
            "createdAt": now_beijing_iso(),
        }
    except Exception as exc:
        logger.error("upload_sumitalk_chat_media_file failed key=%s error=%s", key, exc, exc_info=True)
        return None


def upload_sumitalk_chat_media_thumbnail_file(
    original_key: str,
    content: bytes,
    content_type: str = "image/jpeg",
) -> Optional[dict]:
    original = str(original_key or "").strip()
    if not original.startswith(f"{R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX}/") or not content:
        return None
    normalized_type = (content_type or "image/jpeg").strip().lower()
    if normalized_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        normalized_type = "image/jpeg"
    ext = ".jpg" if normalized_type in {"image/jpeg", "image/jpg"} else ".png" if normalized_type == "image/png" else ".webp"
    stem = Path(original).stem or uuid4().hex
    key = f"{R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX}/thumb/{today_beijing()}/{stem}{ext}"
    client = _s3_client()
    if not client:
        return None
    try:
        client.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=content, ContentType=normalized_type)
        return {
            "key": key,
            "kind": "image",
            "name": Path(key).name,
            "contentType": normalized_type,
            "size": len(content),
            "createdAt": now_beijing_iso(),
        }
    except Exception as exc:
        logger.error("upload_sumitalk_chat_media_thumbnail_file failed key=%s error=%s", key, exc, exc_info=True)
        return None


def get_sumitalk_chat_media_file(key: str) -> tuple[Optional[bytes], str]:
    normalized = str(key or "").strip()
    if not normalized.startswith(f"{R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX}/") or ".." in normalized:
        return None, ""
    return _get_object_bytes(normalized, "get_sumitalk_chat_media_file")


def save_device_screenshot(content: bytes, content_type: str, meta: dict | None = None) -> Optional[dict]:
    """Save a user-approved device screenshot with a temporary access token."""
    if not content:
        return None
    source = meta if isinstance(meta, dict) else {}
    normalized_type = (content_type or "").strip().lower() or "image/jpeg"
    if "png" in normalized_type:
        normalized_type = "image/png"
        ext = ".png"
    else:
        normalized_type = "image/jpeg"
        ext = ".jpg"
    token = uuid4().hex
    device_id = str(source.get("deviceId") or "").strip()
    safe_device = "".join(char if char.isalnum() or char in ("_", "-") else "_" for char in device_id)[:80] or "default"
    key = f"device_screenshots/latest/{safe_device}{ext}"
    meta_key = f"{key}.json"
    meta_payload = {
        "key": key,
        "contentType": normalized_type,
        "accessToken": token,
        "createdAt": now_beijing_iso(),
        "deviceId": device_id,
        "requestId": str(source.get("requestId") or "").strip(),
        "capturedAt": str(source.get("capturedAt") or "").strip(),
        "width": int(source.get("width") or 0),
        "height": int(source.get("height") or 0),
    }
    client = _s3_client()
    if not client:
        return None
    try:
        client.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=content, ContentType=normalized_type)
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=meta_key,
            Body=json.dumps(meta_payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
        return {**meta_payload, "metaKey": meta_key}
    except Exception as exc:
        logger.error("save_device_screenshot failed error=%s", exc, exc_info=True)
        return None


def get_device_screenshot(key: str, token: str) -> tuple[Optional[bytes], str]:
    normalized = str(key or "").strip()
    access_token = str(token or "").strip()
    if not normalized.startswith("device_screenshots/") or ".." in normalized or not access_token:
        return None, ""
    client = _s3_client()
    if not client:
        return None, ""
    try:
        meta = _read_json(client, f"{normalized}.json")
        if not isinstance(meta, dict) or str(meta.get("accessToken") or "") != access_token:
            return None, ""
        response = client.get_object(Bucket=R2_BUCKET_NAME, Key=normalized)
        data = response["Body"].read()
        content_type = (response.get("ContentType") or meta.get("contentType") or "image/jpeg").strip()
        return data, content_type
    except Exception as exc:
        logger.error("get_device_screenshot failed key=%s error=%s", normalized, exc, exc_info=True)
        return None, ""


def _get_object_bytes(key: str, operation: str) -> tuple[Optional[bytes], str]:
    client = _s3_client()
    if not client:
        return None, ""
    try:
        response = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        data = response["Body"].read()
        content_type = (response.get("ContentType") or "application/octet-stream").strip()
        return data, content_type
    except Exception as exc:
        logger.error("%s failed key=%s error=%s", operation, key, exc, exc_info=True)
        return None, ""
