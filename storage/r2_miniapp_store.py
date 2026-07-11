"""MiniApp R2 assets, dashboard state, call records, and notebook."""

from __future__ import annotations

import threading
from typing import Optional
from uuid import uuid4

from botocore.exceptions import ClientError

from config import R2_BUCKET_NAME
from storage.r2_client import _read_json, _s3_client, _write_json
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

R2_KEY_MINIAPP_BG_CONFIG = "global/miniapp_bg_config.json"
R2_KEY_MINIAPP_BG_IMAGE = "global/miniapp_bg_image"
R2_KEY_MINIAPP_BG_IMAGE_PREFIX = "global/miniapp_bg_image_v"
R2_KEY_MINIAPP_VOICE_CONFIG = "global/miniapp_voice_config.json"
R2_KEY_MINIAPP_VOICE_AVATAR = "global/miniapp_voice_avatar"
R2_KEY_MINIAPP_VOICE_AVATAR_PREFIX = "global/miniapp_voice_avatar_v"
R2_KEY_MINIAPP_CALL_RECORDS = "global/miniapp_call_records.json"
R2_KEY_MINIAPP_DAILY_WHISPER = "global/miniapp_daily_whisper.json"
R2_KEY_MINIAPP_DAILY_REPORT = "global/miniapp_daily_report.json"
R2_KEY_MINIAPP_MOOD_METER = "global/miniapp_mood_meter.json"
R2_KEY_DU_NOTEBOOK = "global/du_notebook.json"

_global_write_lock = threading.Lock()

def get_miniapp_bg_config() -> Optional[dict]:
    """读取 MiniApp 背景配置（JSON）。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_BG_CONFIG)
    return data if isinstance(data, dict) else None


def save_miniapp_bg_config(data: dict) -> bool:
    """保存 MiniApp 背景配置（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    try:
        _write_json(client, R2_KEY_MINIAPP_BG_CONFIG, data)
        return True
    except Exception as e:
        logger.error("save_miniapp_bg_config 失败 error=%s", e, exc_info=True)
        return False


def _miniapp_bg_image_versioned_key(image_version: int) -> str:
    return f"{R2_KEY_MINIAPP_BG_IMAGE_PREFIX}_{int(image_version)}"


def save_miniapp_bg_image(content: bytes, content_type: str, image_version: int | None = None) -> bool:
    """保存 MiniApp 背景图片（可选写入版本化键）。"""
    client = _s3_client()
    if not client:
        return False
    if not content:
        return False
    ctype = (content_type or "application/octet-stream").strip() or "application/octet-stream"
    try:
        # 兼容旧逻辑：始终写最新别名键
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_MINIAPP_BG_IMAGE,
            Body=content,
            ContentType=ctype,
        )
        # 新逻辑：额外写版本化键，彻底规避“路径变了但对象仍是旧缓存”
        if image_version and int(image_version) > 0:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=_miniapp_bg_image_versioned_key(int(image_version)),
                Body=content,
                ContentType=ctype,
            )
        return True
    except Exception as e:
        logger.error("save_miniapp_bg_image 失败 error=%s", e, exc_info=True)
        return False


def get_miniapp_bg_image(image_version: int | None = None) -> tuple[Optional[bytes], str]:
    """读取 MiniApp 背景图片，返回 (bytes, content_type)。支持按版本读取。"""
    client = _s3_client()
    if not client:
        return None, ""
    keys: list[str] = []
    if image_version and int(image_version) > 0:
        keys.append(_miniapp_bg_image_versioned_key(int(image_version)))
    # 回退旧键，兼容历史数据
    keys.append(R2_KEY_MINIAPP_BG_IMAGE)
    try:
        for key in keys:
            try:
                resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            except ClientError as e:
                code = (e.response or {}).get("Error", {}).get("Code", "")
                if code == "NoSuchKey":
                    continue
                raise
            body = resp["Body"].read()
            ctype = ((resp.get("ContentType") or "") + "").strip() or "application/octet-stream"
            if body:
                return body, ctype
        return None, ""
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None, ""
        logger.error("get_miniapp_bg_image 失败 error=%s", e, exc_info=True)
        return None, ""
    except Exception as e:
        logger.error("get_miniapp_bg_image 失败 error=%s", e, exc_info=True)
        return None, ""


def get_miniapp_voice_config() -> Optional[dict]:
    """读取 MiniApp 语音通话配置（JSON）。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_VOICE_CONFIG)
    return data if isinstance(data, dict) else None


def save_miniapp_voice_config(data: dict) -> bool:
    """保存 MiniApp 语音通话配置（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    try:
        _write_json(client, R2_KEY_MINIAPP_VOICE_CONFIG, data)
        return True
    except Exception as e:
        logger.error("save_miniapp_voice_config 失败 error=%s", e, exc_info=True)
        return False


def _miniapp_voice_avatar_versioned_key(image_version: int) -> str:
    return f"{R2_KEY_MINIAPP_VOICE_AVATAR_PREFIX}_{int(image_version)}"


def save_miniapp_voice_avatar(content: bytes, content_type: str, image_version: int | None = None) -> bool:
    """保存 MiniApp 语音通话头像（可选写入版本化键）。"""
    client = _s3_client()
    if not client:
        return False
    if not content:
        return False
    ctype = (content_type or "application/octet-stream").strip() or "application/octet-stream"
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=R2_KEY_MINIAPP_VOICE_AVATAR,
            Body=content,
            ContentType=ctype,
        )
        if image_version and int(image_version) > 0:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=_miniapp_voice_avatar_versioned_key(int(image_version)),
                Body=content,
                ContentType=ctype,
            )
        return True
    except Exception as e:
        logger.error("save_miniapp_voice_avatar 失败 error=%s", e, exc_info=True)
        return False


def get_miniapp_voice_avatar(image_version: int | None = None) -> tuple[Optional[bytes], str]:
    """读取 MiniApp 语音通话头像，返回 (bytes, content_type)。支持按版本读取。"""
    client = _s3_client()
    if not client:
        return None, ""
    keys: list[str] = []
    if image_version and int(image_version) > 0:
        keys.append(_miniapp_voice_avatar_versioned_key(int(image_version)))
    keys.append(R2_KEY_MINIAPP_VOICE_AVATAR)
    try:
        for key in keys:
            try:
                resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            except ClientError as e:
                code = (e.response or {}).get("Error", {}).get("Code", "")
                if code == "NoSuchKey":
                    continue
                raise
            body = resp["Body"].read()
            ctype = ((resp.get("ContentType") or "") + "").strip() or "application/octet-stream"
            if body:
                return body, ctype
        return None, ""
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None, ""
        logger.error("get_miniapp_voice_avatar 失败 error=%s", e, exc_info=True)
        return None, ""
    except Exception as e:
        logger.error("get_miniapp_voice_avatar 失败 error=%s", e, exc_info=True)
        return None, ""


def get_miniapp_call_records() -> list[dict]:
    """读取 MiniApp 通话记录列表。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_MINIAPP_CALL_RECORDS)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def save_miniapp_call_records(items: list[dict]) -> bool:
    """保存 MiniApp 通话记录列表。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"items": items if isinstance(items, list) else []}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_CALL_RECORDS, payload)
            return True
        except Exception as e:
            logger.error("save_miniapp_call_records 失败 error=%s", e, exc_info=True)
            return False


def delete_miniapp_call_record(call_id: str) -> bool:
    """按 id 删除一条 MiniApp 通话记录。"""
    cid = str(call_id or "").strip()
    if not cid:
        return False
    items = get_miniapp_call_records() or []
    before = len(items)
    kept = [item for item in items if str((item or {}).get("id") or "").strip() != cid]
    if len(kept) == before:
        return False
    return save_miniapp_call_records(kept)


def get_miniapp_daily_whisper() -> Optional[dict]:
    """读取 MiniApp 每日小气泡文案。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_DAILY_WHISPER)
    return data if isinstance(data, dict) else None


def save_miniapp_daily_whisper(data: dict) -> bool:
    """保存 MiniApp 每日小气泡文案（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_DAILY_WHISPER, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_daily_whisper 失败 error=%s", e, exc_info=True)
            return False


def get_miniapp_daily_report() -> Optional[dict]:
    """读取 MiniApp 每日小报告。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_DAILY_REPORT)
    return data if isinstance(data, dict) else None


def save_miniapp_daily_report(data: dict) -> bool:
    """保存 MiniApp 每日小报告（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_DAILY_REPORT, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_daily_report 失败 error=%s", e, exc_info=True)
            return False


def get_miniapp_mood_meter() -> Optional[dict]:
    """读取 MiniApp 心情温度计。"""
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_MINIAPP_MOOD_METER)
    return data if isinstance(data, dict) else None


def save_miniapp_mood_meter(data: dict) -> bool:
    """保存 MiniApp 心情温度计（JSON）。"""
    client = _s3_client()
    if not client:
        return False
    if not isinstance(data, dict):
        return False
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_MINIAPP_MOOD_METER, data)
            return True
        except Exception as e:
            logger.error("save_miniapp_mood_meter 失败 error=%s", e, exc_info=True)
            return False


def get_du_notebook_entries() -> list[dict]:
    """读取渡的记事本条目（按 updated_at 倒序）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_DU_NOTEBOOK)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out = [x for x in items if isinstance(x, dict)]
    out.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return out


def save_du_notebook_entries(items: list[dict]) -> bool:
    """覆盖保存渡的记事本条目。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            payload = {"items": items or [], "updated_at": now_beijing_iso()}
            _write_json(client, R2_KEY_DU_NOTEBOOK, payload)
            return True
        except Exception as e:
            logger.error("save_du_notebook_entries 失败 error=%s", e, exc_info=True)
            return False


def add_du_notebook_entry(content: str) -> Optional[dict]:
    """新增一条渡的记事本条目。"""
    text = (content or "").strip()
    if not text:
        return None
    items = get_du_notebook_entries()
    now = now_beijing_iso()
    entry = {
        "id": str(uuid4()),
        "content": text,
        "created_at": now,
        "updated_at": now,
    }
    items.append(entry)
    ok = save_du_notebook_entries(items)
    return entry if ok else None


def update_du_notebook_entry(entry_id: str, content: str) -> bool:
    """更新一条渡的记事本条目内容。"""
    eid = (entry_id or "").strip()
    text = (content or "").strip()
    if not eid or not text:
        return False
    items = get_du_notebook_entries()
    changed = False
    now = now_beijing_iso()
    for it in items:
        if str(it.get("id") or "").strip() != eid:
            continue
        it["content"] = text
        it["updated_at"] = now
        changed = True
        break
    if not changed:
        return False
    return save_du_notebook_entries(items)


def delete_du_notebook_entry(entry_id: str) -> bool:
    """删除一条渡的记事本条目。"""
    eid = (entry_id or "").strip()
    if not eid:
        return False
    items = get_du_notebook_entries()
    new_items = [it for it in items if str(it.get("id") or "").strip() != eid]
    if len(new_items) == len(items):
        return False
    return save_du_notebook_entries(new_items)
