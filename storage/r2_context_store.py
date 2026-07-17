"""Shared summary, latest-round, and recent image context stored in R2."""

import threading
from datetime import datetime
from typing import Any, Optional

from config import R2_BUCKET_NAME, R2_KEY_LATEST_4_ROUNDS
from storage.r2_client import _read_json, _s3_client, _write_json
from storage.r2_conversation_store import (
    _conversation_guard_dates,
    _image_desc_recent_key,
    _read_conversation_backup_rounds_for_dates,
    _read_conversation_meta_status,
    _read_recent_rounds,
    normalize_window_id,
)
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso

R2_KEY_GLOBAL_SUMMARY = "global/summary.txt"
R2_KEY_GLOBAL_SUMMARY_CHUNKS = "global/summary_chunks.json"
R2_KEY_IMAGE_DESC_RECENT = "global/image_descriptions_recent.json"
IMAGE_DESC_RECENT_LIMIT = 4

_global_write_lock = threading.Lock()
logger = get_logger(__name__)


def get_summary(window_id: str = "") -> Optional[str]:
    """读取全局共享总结。window_id 保留参数兼容，未使用。"""
    client = _s3_client()
    if not client:
        return None
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_GLOBAL_SUMMARY)
        return resp["Body"].read().decode("utf-8").strip()
    except Exception:
        return None


def save_summary(window_id: str, summary: str) -> bool:
    """保存全局总结（覆盖）。多窗口写同一 key 时加锁。"""
    client = _s3_client()
    if not client:
        return False
    with _global_write_lock:
        try:
            try:
                old = client.get_object(Bucket=R2_BUCKET_NAME, Key=R2_KEY_GLOBAL_SUMMARY)
                old_body = old["Body"].read()
                if old_body:
                    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
                    backup_key = f"global/summary_backups/summary_{ts}.txt"
                    client.put_object(
                        Bucket=R2_BUCKET_NAME,
                        Key=backup_key,
                        Body=old_body,
                        ContentType="text/plain; charset=utf-8",
                    )
                    logger.info("save_summary 已备份旧总结 key=%s", backup_key)
            except Exception as e:
                logger.warning("save_summary 备份旧总结失败，继续覆盖 error=%s", e)
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=R2_KEY_GLOBAL_SUMMARY,
                Body=summary.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
            return True
        except Exception as e:
            logger.error("save_summary 失败 error=%s", e, exc_info=True)
            return False


def get_summary_chunks(window_id: str = "") -> dict:
    """读取全局实时层小段队列。window_id 保留参数兼容，未使用。"""
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, R2_KEY_GLOBAL_SUMMARY_CHUNKS)
    if not isinstance(data, dict):
        return {}
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        data["chunks"] = []
    return data


def save_summary_chunks(window_id: str, chunks_state: dict) -> bool:
    """保存全局实时层小段队列。window_id 保留参数兼容，未使用。"""
    client = _s3_client()
    if not client:
        return False
    payload = dict(chunks_state or {})
    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        payload["chunks"] = []
    payload["version"] = 2
    payload["updated_at"] = now_beijing_iso()
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_GLOBAL_SUMMARY_CHUNKS, payload)
            return True
        except Exception as e:
            logger.error("save_summary_chunks 失败 error=%s", e, exc_info=True)
            return False


def get_latest_4_rounds_global() -> list:
    """获取 R2 中全局保存的最近四轮原文（新窗口注入用）。"""
    client = _s3_client()
    if not client:
        return []
    data = _read_json(client, R2_KEY_LATEST_4_ROUNDS)
    if not data or not data.get("rounds"):
        return []
    return data.get("rounds", [])


def update_latest_4_rounds_global(rounds: list) -> bool:
    """更新全局最近四轮（每次存档后由网关调用）。多窗口写同一 key 时加锁。"""
    client = _s3_client()
    if not client:
        return False
    payload = {"rounds": rounds[-4:]}
    with _global_write_lock:
        try:
            _write_json(client, R2_KEY_LATEST_4_ROUNDS, payload)
            return True
        except Exception as e:
            logger.error("update_latest_4_rounds_global 失败 error=%s", e, exc_info=True)
            return False


def _image_desc_items(data: Any) -> list[dict]:
    if isinstance(data, dict):
        items = data.get("items") or data.get("images") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _upsert_recent_image_description_locked(client, key: str, item: dict) -> None:
    data = _read_json(client, key)
    items = [
        old
        for old in _image_desc_items(data)
        if str(old.get("image_id") or "").strip() != str(item.get("image_id") or "").strip()
    ]
    items.append(item)
    items = sorted(items, key=lambda x: str(x.get("updated_at") or ""))[-IMAGE_DESC_RECENT_LIMIT:]
    _write_json(
        client,
        key,
        {
            "schema_version": 1,
            "limit": IMAGE_DESC_RECENT_LIMIT,
            "updated_at": item.get("updated_at") or now_beijing_iso(),
            "items": items,
        },
    )


def save_recent_image_description(
    window_id: str,
    image_id: str,
    description: str,
    mime_type: str = "",
    message_id: str = "",
) -> bool:
    """保存最近图片描述表，供 last4 注入时把内部图片占位符替换成文字。"""
    client = _s3_client()
    desc = str(description or "").strip()
    ident = str(image_id or "").strip()
    if not client or not desc or not ident:
        return False
    now = now_beijing_iso()
    item = {
        "image_id": ident,
        "description": desc,
        "window_id": normalize_window_id(window_id),
        "message_id": str(message_id or "").strip(),
        "mime_type": str(mime_type or "").strip().lower(),
        "updated_at": now,
    }
    keys = [R2_KEY_IMAGE_DESC_RECENT, _image_desc_recent_key(window_id)]
    with _global_write_lock:
        try:
            for key in keys:
                _upsert_recent_image_description_locked(client, key, item)
            logger.info(
                "image_desc 最近表已更新 window_id=%s image_id=%s desc_len=%s",
                window_id,
                ident,
                len(desc),
            )
            return True
        except Exception as e:
            logger.error(
                "save_recent_image_description 失败 window_id=%s image_id=%s error=%s",
                window_id,
                ident,
                e,
                exc_info=True,
            )
            return False


def get_recent_image_description_map(window_id: str | None = None) -> dict[str, str]:
    """读取最近图片描述表。window_id=None 读取全局表；否则读取该窗口表。"""
    client = _s3_client()
    if not client:
        return {}
    key = R2_KEY_IMAGE_DESC_RECENT if window_id is None else _image_desc_recent_key(window_id)
    data = _read_json(client, key)
    out: dict[str, str] = {}
    for item in _image_desc_items(data):
        ident = str(item.get("image_id") or "").strip()
        desc = str(item.get("description") or "").strip()
        if ident and desc:
            out[ident] = desc
    return out


def has_window_history(window_id: str) -> bool:
    """该窗口是否已有过 compact 存档（有则不是新窗口）。空 window_id 等价于默认窗口。"""
    client = _s3_client()
    if not client:
        return False
    meta, read_ok, _ = _read_conversation_meta_status(client, window_id)
    if read_ok and isinstance(meta, dict):
        try:
            if int(meta.get("last_round_index") or 0) > 0 or int(meta.get("round_count") or 0) > 0:
                return True
        except Exception:
            pass
    if _read_recent_rounds(client, window_id):
        return True
    return bool(_read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates(14)))
