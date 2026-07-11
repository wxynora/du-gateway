"""R2-backed sticker categories, mappings, and image objects."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from config import R2_BUCKET_NAME
from storage.r2_client import _read_json, _s3_client, _write_json
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

R2_KEY_STICKERS_MAPPING = "stickers/mapping.json"
R2_KEY_STICKERS_META = "stickers/meta.json"

_sticker_write_lock = threading.Lock()


def _sticker_reserved_keys() -> frozenset:
    return frozenset({R2_KEY_STICKERS_MAPPING, R2_KEY_STICKERS_META, "stickers/mapping.json", "stickers/meta.json"})


def _merge_default_sticker_meta(raw: dict) -> dict:
    """Merge persisted category labels with the built-in category list."""
    from services.sticker_tags import DEFAULT_STICKER_TAG_ROWS, validate_sticker_tag_key

    by_key: dict[str, dict] = {row["key"]: dict(row) for row in DEFAULT_STICKER_TAG_ROWS}
    incoming = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        if not key or not validate_sticker_tag_key(key):
            continue
        label = str(item.get("label_zh") or item.get("label") or "").strip() or key
        if key in by_key:
            by_key[key]["label_zh"] = label
        else:
            by_key[key] = {"key": key, "label_zh": label}
    order = [row["key"] for row in DEFAULT_STICKER_TAG_ROWS]
    default_set = set(order)
    extras = sorted(key for key in by_key if key not in default_set)
    rows = [by_key[key] for key in order if key in by_key]
    rows.extend(by_key[key] for key in extras)
    return {"tags": rows, "updated_at": str(raw.get("updated_at") or "")}


def get_stickers_meta() -> dict:
    """Read sticker category metadata, creating defaults when absent."""
    from services.sticker_tags import DEFAULT_STICKER_TAG_ROWS

    client = _s3_client()
    if not client:
        return {"tags": list(DEFAULT_STICKER_TAG_ROWS), "updated_at": ""}
    data = _read_json(client, R2_KEY_STICKERS_META)
    if not isinstance(data, dict) or not isinstance(data.get("tags"), list):
        payload = {"tags": list(DEFAULT_STICKER_TAG_ROWS), "updated_at": now_beijing_iso()}
        with _sticker_write_lock:
            try:
                _write_json(client, R2_KEY_STICKERS_META, payload)
            except Exception:
                pass
        return payload
    return _merge_default_sticker_meta(data)


def save_stickers_meta(payload: dict) -> bool:
    """Save category metadata edited through the MiniApp."""
    client = _s3_client()
    if not client or not isinstance(payload, dict):
        return False
    saved = dict(payload)
    saved["updated_at"] = now_beijing_iso()
    with _sticker_write_lock:
        try:
            _write_json(client, R2_KEY_STICKERS_META, saved)
            try:
                from services.sticker_tags import cache_sticker_tag_keys_from_meta

                cache_sticker_tag_keys_from_meta(saved)
            except Exception:
                pass
            return True
        except Exception as exc:
            logger.error("save_stickers_meta failed error=%s", exc, exc_info=True)
            return False


def get_sticker_tag_keys() -> set[str]:
    """Return all valid lower-case category keys from metadata and mapping."""
    from services.sticker_tags import validate_sticker_tag_key

    keys: set[str] = set()
    meta = get_stickers_meta()
    for item in meta.get("tags") or []:
        if isinstance(item, dict) and item.get("key"):
            key = str(item["key"]).strip().lower()
            if validate_sticker_tag_key(key):
                keys.add(key)
    client = _s3_client()
    if client:
        mapping = _read_json(client, R2_KEY_STICKERS_MAPPING)
        if isinstance(mapping, dict):
            for key in mapping:
                if key != "updated_at" and isinstance(key, str) and key.strip():
                    normalized = key.strip().lower()
                    if validate_sticker_tag_key(normalized):
                        keys.add(normalized)
    return keys


def add_sticker_category(key: str, label_zh: str = "") -> tuple[bool, str]:
    """Add one sticker category."""
    from services.sticker_tags import validate_sticker_tag_key

    key = (key or "").strip().lower()
    if not key:
        return False, "英文代号不能为空"
    if not validate_sticker_tag_key(key):
        return False, "代号须为小写英文：字母开头，仅 a-z、0-9、下划线"
    label = (label_zh or "").strip() or key
    meta = get_stickers_meta()
    tags = [item for item in (meta.get("tags") or []) if isinstance(item, dict)]
    for item in tags:
        if str(item.get("key") or "").strip().lower() == key:
            return False, "该代号已存在"
    tags.append({"key": key, "label_zh": label})
    meta["tags"] = tags
    return (True, "") if save_stickers_meta(meta) else (False, "保存失败")


def rebuild_stickers_mapping_from_r2() -> dict[str, list[str]]:
    """Scan sticker objects and rebuild the category-to-object mapping."""
    client = _s3_client()
    output: dict[str, list[str]] = {}
    if not client:
        return output
    reserved = _sticker_reserved_keys()
    token = None
    try:
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": "stickers/", "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for obj in response.get("Contents") or []:
                key = str(obj.get("Key") or "")
                if not key or key.endswith("/"):
                    continue
                if key in reserved or key.endswith("mapping.json") or key.endswith("meta.json"):
                    continue
                parts = key.split("/")
                if len(parts) < 3:
                    continue
                tag = parts[1].strip().lower()
                if tag:
                    output.setdefault(tag, []).append(key)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
    except Exception as exc:
        logger.warning("rebuild_stickers_mapping_from_r2 listing failed error=%s", exc)
    for tag in list(output):
        output[tag] = sorted(set(output[tag]))
    return output


def save_stickers_mapping(mapping: dict[str, list[str]]) -> bool:
    """Save the category-to-object mapping."""
    client = _s3_client()
    if not client or not isinstance(mapping, dict):
        return False
    payload: dict[str, Any] = {"updated_at": now_beijing_iso()}
    for tag, items in mapping.items():
        if tag != "updated_at" and isinstance(items, list):
            payload[str(tag)] = [str(item).strip() for item in items if str(item).strip()]
    with _sticker_write_lock:
        try:
            _write_json(client, R2_KEY_STICKERS_MAPPING, payload)
            return True
        except Exception as exc:
            logger.error("save_stickers_mapping failed error=%s", exc, exc_info=True)
            return False


def get_stickers_mapping() -> dict[str, Any]:
    """Read the mapping, rebuilding it when missing or malformed."""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_STICKERS_MAPPING)
    if not isinstance(data, dict):
        mapping = rebuild_stickers_mapping_from_r2()
        save_stickers_mapping(mapping)
        data = _read_json(client, R2_KEY_STICKERS_MAPPING)
    return data if isinstance(data, dict) else {}


def upload_sticker_file(tag: str, filename: str, content: bytes, content_type: str) -> Optional[str]:
    """Upload one sticker and refresh the mapping."""
    from services.sticker_tags import validate_sticker_tag_key

    normalized_tag = (tag or "").strip().lower()
    if not normalized_tag or not validate_sticker_tag_key(normalized_tag):
        return None
    if normalized_tag not in get_sticker_tag_keys() or not content:
        return None
    ext = Path(filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    content_type = _sticker_content_type(content_type)
    key = f"stickers/{normalized_tag}/{uuid4().hex}{ext}"
    client = _s3_client()
    if not client:
        return None
    try:
        client.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=content, ContentType=content_type)
        save_stickers_mapping(rebuild_stickers_mapping_from_r2())
        logger.info("sticker uploaded key=%s", key)
        return key
    except Exception as exc:
        logger.error("upload_sticker_file failed error=%s", exc, exc_info=True)
        return None


def delete_sticker_object(key: str) -> bool:
    """Delete one sticker object and refresh the mapping."""
    normalized = (key or "").strip()
    if not normalized.startswith("stickers/") or ".." in normalized or normalized in _sticker_reserved_keys():
        return False
    client = _s3_client()
    if not client:
        return False
    try:
        client.delete_object(Bucket=R2_BUCKET_NAME, Key=normalized)
        save_stickers_mapping(rebuild_stickers_mapping_from_r2())
        logger.info("sticker deleted key=%s", normalized)
        return True
    except Exception as exc:
        logger.error("delete_sticker_object failed key=%s error=%s", normalized, exc, exc_info=True)
        return False


def _sticker_content_type(content_type: str) -> str:
    normalized = (content_type or "").strip().lower() or "image/jpeg"
    if "jpeg" in normalized or "jpg" in normalized:
        return "image/jpeg"
    if "png" in normalized:
        return "image/png"
    if "webp" in normalized:
        return "image/webp"
    if "gif" in normalized:
        return "image/gif"
    return "image/jpeg"
