from __future__ import annotations

import base64
import copy
import json
import mimetypes
import random
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

import requests
from botocore.exceptions import ClientError

from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso


logger = get_logger(__name__)

R2_KEY_SECRET_DRAWER = "global/du_secret_drawer.json"
R2_KEY_SECRET_DRAWER_CONFIG = "global/du_secret_drawer_config.json"

SECRET_DRAWER_SCHEMA_VERSION = 1
SECRET_DRAWER_IMAGE_MAX_BYTES = 12 * 1024 * 1024
SECRET_DRAWER_DOWNLOAD_TIMEOUT_SECONDS = 12

VALID_TYPES = {"message", "photo", "dream", "note", "surf", "misc"}
VALID_ACTION_TYPES = {
    "save_message": "message",
    "save_photo": "photo",
    "save_dream": "dream",
    "save_note": "note",
    "save_surf": "surf",
}

_write_lock = threading.Lock()
_CONFIG_READ_ERROR = object()
_PAYLOAD_READ_ERROR = object()


def _write_json(key: str, data: Any) -> bool:
    client = r2_store._s3_client()
    if not client:
        return False
    return r2_store._write_json(client, key, data)


def _read_payload_json() -> dict | None | object:
    client = r2_store._s3_client()
    if not client:
        logger.warning("secret_drawer payload read failed: R2 client unavailable")
        return _PAYLOAD_READ_ERROR
    try:
        resp = client.get_object(Bucket=r2_store.R2_BUCKET_NAME, Key=R2_KEY_SECRET_DRAWER)
        body = resp["Body"].read().decode("utf-8")
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("secret_drawer payload read failed key=%s error=%s", R2_KEY_SECRET_DRAWER, e, exc_info=True)
        return _PAYLOAD_READ_ERROR
    except Exception as e:
        logger.error("secret_drawer payload read failed key=%s error=%s", R2_KEY_SECRET_DRAWER, e, exc_info=True)
        return _PAYLOAD_READ_ERROR


def _read_config_json() -> dict | None | object:
    client = r2_store._s3_client()
    if not client:
        logger.warning("secret_drawer config read failed: R2 client unavailable")
        return _CONFIG_READ_ERROR
    try:
        resp = client.get_object(Bucket=r2_store.R2_BUCKET_NAME, Key=R2_KEY_SECRET_DRAWER_CONFIG)
        body = resp["Body"].read().decode("utf-8")
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("secret_drawer config read failed key=%s error=%s", R2_KEY_SECRET_DRAWER_CONFIG, e, exc_info=True)
        return _CONFIG_READ_ERROR
    except Exception as e:
        logger.error("secret_drawer config read failed key=%s error=%s", R2_KEY_SECRET_DRAWER_CONFIG, e, exc_info=True)
        return _CONFIG_READ_ERROR


def _empty_payload() -> dict:
    now = now_beijing_iso()
    return {
        "schema_version": SECRET_DRAWER_SCHEMA_VERSION,
        "items": [],
        "created_at": now,
        "updated_at": now,
    }


def _payload_from_raw(data: Any) -> dict:
    if not isinstance(data, dict):
        return _empty_payload()
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    return {
        "schema_version": int(data.get("schema_version") or SECRET_DRAWER_SCHEMA_VERSION),
        "items": [_normalize_item(it) for it in items if isinstance(it, dict)],
        "created_at": str(data.get("created_at") or now_beijing_iso()),
        "updated_at": str(data.get("updated_at") or now_beijing_iso()),
    }


def _read_payload() -> dict:
    data = _read_payload_json()
    if data is _PAYLOAD_READ_ERROR:
        payload = _empty_payload()
        payload["read_error"] = True
        return payload
    return _payload_from_raw(data)


def _read_payload_for_write() -> dict | None:
    data = _read_payload_json()
    if data is _PAYLOAD_READ_ERROR:
        return None
    return _payload_from_raw(data)


def _write_payload(payload: dict) -> bool:
    data = payload if isinstance(payload, dict) else _empty_payload()
    data["schema_version"] = SECRET_DRAWER_SCHEMA_VERSION
    data["items"] = [_normalize_item(it) for it in (data.get("items") or []) if isinstance(it, dict)]
    data["updated_at"] = now_beijing_iso()
    if not data.get("created_at"):
        data["created_at"] = data["updated_at"]
    return _write_json(R2_KEY_SECRET_DRAWER, data)


def _normalize_type(value: Any) -> str:
    t = str(value or "").strip().lower()
    return t if t in VALID_TYPES else "misc"


def _normalize_tags(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value] if value else []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text[:40])
    return out[:20]


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r", "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _normalize_source(value: Any) -> dict:
    src = value if isinstance(value, dict) else {}
    message_ids = src.get("message_ids") or src.get("messageIds") or []
    if not isinstance(message_ids, list):
        message_ids = [message_ids] if message_ids else []
    return {
        "channel": _clip_text(src.get("channel"), 40),
        "message_ids": [_clip_text(x, 80) for x in message_ids if str(x or "").strip()][:20],
        "turn_id": _clip_text(src.get("turn_id") or src.get("turnId"), 120),
        "url": _clip_text(src.get("url") or src.get("source_url") or src.get("sourceUrl"), 500),
        "window_id": _clip_text(src.get("window_id") or src.get("windowId"), 120),
    }


def _normalize_media_ref(value: Any) -> dict:
    src = value if isinstance(value, dict) else {}
    key = str(src.get("key") or src.get("remoteKey") or "").strip()
    url = str(src.get("url") or src.get("remoteUrl") or src.get("src") or "").strip()
    kind = str(src.get("kind") or "image").strip().lower() or "image"
    content_type = str(src.get("contentType") or src.get("mime") or src.get("content_type") or "").strip().lower()
    name = str(src.get("name") or src.get("filename") or src.get("fileName") or "").strip()
    out = {
        "kind": kind,
        "key": key,
        "url": url,
        "name": name,
        "contentType": content_type,
        "size": _safe_int(src.get("size")),
        "createdAt": str(src.get("createdAt") or src.get("created_at") or now_beijing_iso()),
    }
    return {k: v for k, v in out.items() if v not in ("", 0, None)}


def _normalize_media_refs(value: Any) -> list[dict]:
    raw = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        ref = _normalize_media_ref(item)
        ident = str(ref.get("key") or ref.get("url") or "")
        if not ref or not ident or ident in seen:
            continue
        seen.add(ident)
        out.append(ref)
    return out[:30]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except Exception:
        return default


def _normalize_item(raw: dict) -> dict:
    now = now_beijing_iso()
    item_id = str(raw.get("id") or "").strip() or f"sd_{uuid4().hex}"
    created = str(raw.get("created_at") or raw.get("createdAt") or now)
    updated = str(raw.get("updated_at") or raw.get("updatedAt") or created or now)
    item = {
        "id": item_id,
        "type": _normalize_type(raw.get("type")),
        "title": _clip_text(raw.get("title"), 120),
        "content": _clip_text(raw.get("content"), 12000),
        "media_refs": _normalize_media_refs(raw.get("media_refs") or raw.get("mediaRefs")),
        "why": _clip_text(raw.get("why"), 500),
        "tags": _normalize_tags(raw.get("tags")),
        "pinned": bool(raw.get("pinned")),
        "sealed": bool(raw.get("sealed")),
        "deleted": bool(raw.get("deleted")),
        "source": _normalize_source(raw.get("source")),
        "created_at": created,
        "updated_at": updated,
    }
    return item


def _normalize_item_input_media(raw: dict) -> dict:
    src = copy.deepcopy(raw if isinstance(raw, dict) else {})
    if "media_refs" not in src and "mediaRefs" not in src:
        return src
    refs = _normalize_media_refs(src.get("media_refs") or src.get("mediaRefs"))
    src["media_refs"] = ensure_media_refs(refs)
    src.pop("mediaRefs", None)
    return src


def needs_organize(item: dict) -> bool:
    if not isinstance(item, dict) or item.get("deleted"):
        return False
    return not str(item.get("title") or "").strip() or not (item.get("tags") or []) or not str(item.get("why") or "").strip()


def get_config() -> dict:
    data = _read_config_json()
    if data is _CONFIG_READ_ERROR:
        return {
            "box_pin": "",
            "sealed_pin": "",
            "updated_at": "",
            "read_error": True,
        }
    if not isinstance(data, dict):
        data = {}
    return {
        "box_pin": str(data.get("box_pin") or data.get("boxPin") or ""),
        "sealed_pin": str(data.get("sealed_pin") or data.get("sealedPin") or ""),
        "updated_at": str(data.get("updated_at") or data.get("updatedAt") or ""),
        "read_error": False,
    }


def save_config(config: dict) -> bool:
    src = config if isinstance(config, dict) else {}
    payload = {
        "box_pin": _normalize_pin(src.get("box_pin") or src.get("boxPin")),
        "sealed_pin": _normalize_pin(src.get("sealed_pin") or src.get("sealedPin")),
        "updated_at": now_beijing_iso(),
    }
    return _write_json(R2_KEY_SECRET_DRAWER_CONFIG, payload)


def _normalize_pin(value: Any) -> str:
    text = re.sub(r"\D+", "", str(value or ""))
    return text[:4]


def set_pin(layer: str, pin: Any) -> tuple[bool, dict]:
    normalized = _normalize_pin(pin)
    if len(normalized) != 4:
        return False, {"error": "PIN 必须是 4 位数字"}
    config = get_config()
    if config.get("read_error"):
        return False, {"error": "PIN 配置读取失败，未写入"}
    if str(layer or "").strip().lower() in {"sealed", "lock", "inner"}:
        config["sealed_pin"] = normalized
    else:
        config["box_pin"] = normalized
    ok = save_config(config)
    return ok, get_config()


def verify_pin(layer: str, pin: Any) -> bool:
    config = get_config()
    if config.get("read_error"):
        return False
    target = config.get("sealed_pin") if str(layer or "").strip().lower() in {"sealed", "lock", "inner"} else config.get("box_pin")
    if not target:
        target = "0000"
    return _normalize_pin(pin) == str(target)


def save_item(data: dict) -> dict | None:
    raw = _normalize_item_input_media(data if isinstance(data, dict) else {})
    item = _normalize_item(
        {
            **raw,
            "id": raw.get("id") or f"sd_{uuid4().hex}",
            "created_at": raw.get("created_at") or now_beijing_iso(),
            "updated_at": now_beijing_iso(),
        }
    )
    with _write_lock:
        payload = _read_payload_for_write()
        if payload is None:
            return None
        items = payload.get("items") or []
        items.insert(0, item)
        payload["items"] = items
        if not _write_payload(payload):
            return None
    return item


def list_items(
    *,
    include_deleted: bool = False,
    include_sealed: bool = False,
    sealed_only: bool = False,
    type_filter: str = "",
    tag: str = "",
    query: str = "",
    needs_organize_only: bool = False,
    pinned_only: bool | None = None,
    limit: int = 100,
) -> list[dict]:
    payload = _read_payload()
    t_filter = _normalize_type(type_filter) if type_filter else ""
    tag_filter = str(tag or "").strip()
    q = str(query or "").strip().lower()
    out: list[dict] = []
    for item in payload.get("items") or []:
        if not include_deleted and item.get("deleted"):
            continue
        if sealed_only and not item.get("sealed"):
            continue
        if not sealed_only and not include_sealed and item.get("sealed"):
            continue
        if t_filter and item.get("type") != t_filter:
            continue
        if tag_filter and tag_filter not in (item.get("tags") or []):
            continue
        if needs_organize_only and not needs_organize(item):
            continue
        if pinned_only is not None and bool(item.get("pinned")) is not bool(pinned_only):
            continue
        if q:
            hay = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("content") or ""),
                    str(item.get("why") or ""),
                    " ".join(str(x) for x in (item.get("tags") or [])),
                ]
            ).lower()
            if q not in hay:
                continue
        out.append(item)
    out.sort(key=lambda it: (bool(it.get("pinned")), str(it.get("created_at") or "")), reverse=True)
    n = max(1, min(500, _safe_int(limit, 100)))
    return out[:n]


def get_item(item_id: str, *, include_deleted: bool = False) -> dict | None:
    target = str(item_id or "").strip()
    if not target:
        return None
    for item in (_read_payload().get("items") or []):
        if item.get("id") != target:
            continue
        if item.get("deleted") and not include_deleted:
            return None
        return item
    return None


def update_item(item_id: str, patch: dict) -> dict | None:
    target = str(item_id or "").strip()
    if not target:
        return None
    src = _normalize_item_input_media(patch if isinstance(patch, dict) else {})
    allowed = {"title", "content", "why", "tags", "pinned", "sealed", "deleted", "type", "media_refs", "source"}
    with _write_lock:
        payload = _read_payload_for_write()
        if payload is None:
            return None
        items = payload.get("items") or []
        updated = None
        next_items = []
        for item in items:
            if item.get("id") != target:
                next_items.append(item)
                continue
            merged = {**item}
            for key in allowed:
                if key in src:
                    merged[key] = src.get(key)
            merged["updated_at"] = now_beijing_iso()
            updated = _normalize_item(merged)
            next_items.append(updated)
        if not updated:
            return None
        payload["items"] = next_items
        if not _write_payload(payload):
            return None
    return updated


def soft_delete_item(item_id: str) -> dict | None:
    return update_item(item_id, {"deleted": True})


def restore_item(item_id: str) -> dict | None:
    return update_item(item_id, {"deleted": False})


def random_item(
    *,
    include_sealed: bool = False,
    sealed_only: bool = False,
    tag: str = "",
    type_filter: str = "",
    needs_organize_only: bool = False,
) -> dict | None:
    items = list_items(
        include_sealed=include_sealed,
        sealed_only=sealed_only,
        tag=tag,
        type_filter=type_filter,
        needs_organize_only=needs_organize_only,
        limit=500,
    )
    if not items:
        return None
    return random.choice(items)


def stats(*, include_sealed_details: bool = False) -> dict:
    payload = _read_payload()
    all_items = payload.get("items") or []
    items = [item for item in all_items if not item.get("deleted")]
    visible_items = items if include_sealed_details else [item for item in items if not item.get("sealed")]
    by_type = {t: 0 for t in ["message", "photo", "dream", "note", "surf", "misc"]}
    needs_by_type = {t: 0 for t in ["message", "photo", "dream", "note", "surf", "misc"]}
    by_tag: dict[str, int] = {}
    for item in visible_items:
        item_type = _normalize_type(item.get("type"))
        by_type[item_type] = by_type.get(item_type, 0) + 1
        if needs_organize(item):
            needs_by_type[item_type] = needs_by_type.get(item_type, 0) + 1
        for tag in item.get("tags") or []:
            text = str(tag or "").strip()
            if text:
                by_tag[text] = by_tag.get(text, 0) + 1
    latest_at = ""
    for item in visible_items:
        created = str(item.get("created_at") or "")
        if created > latest_at:
            latest_at = created
    return {
        "total": len(visible_items),
        "all_total": len(items),
        "ordinary": sum(1 for item in items if not item.get("sealed")),
        "deleted": sum(1 for item in all_items if item.get("deleted")),
        "by_type": by_type,
        "by_tag": dict(sorted(by_tag.items(), key=lambda kv: (-kv[1], kv[0]))[:80]),
        "needs_by_type": needs_by_type,
        "pinned": sum(1 for item in visible_items if item.get("pinned")),
        "sealed": sum(1 for item in items if item.get("sealed")),
        "needs整理": sum(1 for item in visible_items if needs_organize(item)),
        "latest_at": latest_at,
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _public_chat_media_url(key: str) -> str:
    k = str(key or "").strip()
    if not k:
        return ""
    return f"/miniapp-api/chat-media/raw-public?key={quote(k, safe='/')}"


def _key_from_chat_media_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    query = parse_qs(parsed.query or "")
    key = (query.get("key") or [""])[0]
    key = unquote(str(key or "")).strip()
    if key.startswith("sumitalk/chat_media/"):
        return key
    path = unquote(parsed.path or "").strip("/")
    idx = path.find("sumitalk/chat_media/")
    return path[idx:] if idx >= 0 else ""


def _content_type_ext(content_type: str, fallback: str = ".jpg") -> str:
    ctype = str(content_type or "").split(";", 1)[0].strip().lower()
    if ctype == "image/jpeg" or ctype == "image/jpg":
        return ".jpg"
    if ctype == "image/png":
        return ".png"
    if ctype == "image/webp":
        return ".webp"
    if ctype == "image/gif":
        return ".gif"
    return mimetypes.guess_extension(ctype) or fallback


def _copy_data_url_image(url: str, name: str = "") -> dict | None:
    raw = str(url or "").strip()
    m = re.match(r"^data:([^;,]+)?(;base64)?,(.*)$", raw, flags=re.I | re.S)
    if not m:
        return None
    ctype = (m.group(1) or "image/jpeg").strip().lower()
    if not ctype.startswith("image/"):
        return None
    try:
        if m.group(2):
            data = base64.b64decode(m.group(3), validate=False)
        else:
            data = unquote(m.group(3)).encode("utf-8")
    except Exception:
        return None
    if not data or len(data) > SECRET_DRAWER_IMAGE_MAX_BYTES:
        return None
    ext = _content_type_ext(ctype)
    row = r2_store.upload_sumitalk_chat_media_file("image", name or f"secret-drawer{ext}", data, ctype)
    return _normalize_uploaded_media_row(row) if row else None


def _copy_http_image(url: str, name: str = "") -> dict | None:
    raw = str(url or "").strip()
    if not raw.lower().startswith(("http://", "https://")):
        return None
    key = _key_from_chat_media_url(raw)
    if key:
        return {
            "kind": "image",
            "key": key,
            "url": _public_chat_media_url(key),
            "name": Path(key).name,
        }
    try:
        resp = requests.get(raw, timeout=SECRET_DRAWER_DOWNLOAD_TIMEOUT_SECONDS, stream=True)
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(";", 1)[0].strip().lower()
        if not ctype.startswith("image/"):
            return None
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > SECRET_DRAWER_IMAGE_MAX_BYTES:
                return None
            chunks.append(chunk)
        data = b"".join(chunks)
    except Exception as e:
        logger.warning("secret_drawer image copy failed url=%s err=%s", raw[:160], e)
        return None
    if not data:
        return None
    ext = _content_type_ext(ctype)
    row = r2_store.upload_sumitalk_chat_media_file("image", name or f"secret-drawer{ext}", data, ctype)
    return _normalize_uploaded_media_row(row) if row else None


def _normalize_uploaded_media_row(row: dict) -> dict:
    src = row if isinstance(row, dict) else {}
    key = str(src.get("key") or "").strip()
    return {
        "kind": str(src.get("kind") or "image").strip() or "image",
        "key": key,
        "url": _public_chat_media_url(key),
        "name": str(src.get("name") or Path(key).name),
        "contentType": str(src.get("contentType") or ""),
        "size": _safe_int(src.get("size")),
        "createdAt": str(src.get("createdAt") or now_beijing_iso()),
    }


def ensure_media_ref(ref: dict) -> dict | None:
    src = ref if isinstance(ref, dict) else {}
    key = str(src.get("key") or src.get("remoteKey") or "").strip()
    if key.startswith("sumitalk/chat_media/"):
        return _normalize_media_ref({**src, "key": key, "url": _public_chat_media_url(key), "kind": src.get("kind") or "image"})
    url = str(src.get("url") or src.get("remoteUrl") or src.get("src") or "").strip()
    if not url:
        return None
    if url.lower().startswith("data:"):
        return _copy_data_url_image(url, str(src.get("name") or ""))
    if url.lower().startswith(("http://", "https://")):
        copied = _copy_http_image(url, str(src.get("name") or ""))
        if copied:
            return copied
        return None
    return _normalize_media_ref(src)


def ensure_media_refs(refs: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for ref in refs or []:
        item = ensure_media_ref(ref)
        ident = str((item or {}).get("key") or (item or {}).get("url") or "")
        if not item or not ident or ident in seen:
            continue
        seen.add(ident)
        out.append(item)
    return out
