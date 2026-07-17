from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

from services.image_desc import compress_base64_image_for_anthropic
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

R2_KEY_QQ_XINYUE_GROUP_ACTIVITY = "global/qq_xinyue_group_activity.json"
_MAX_ACTIVITY_ITEMS = 24
_MAX_CONTEXT_ROWS = 20
_MAX_TEXT_CHARS = 180
_CONTEXT_TTL_HOURS = 24
_IMAGE_CONTEXT_TTL_HOURS = 1
_MAX_CONTEXT_IMAGES = 5


def _clip_text(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = " ".join(str(value or "").replace("\r", "\n").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _image_urls(value: Any) -> list[str]:
    out: list[str] = []
    for raw in value if isinstance(value, list) else []:
        url = str(raw or "").strip()
        if not url.lower().startswith("data:image/") or ";base64," not in url[:100].lower():
            continue
        if url not in out:
            out.append(url)
    return out


def _compress_image_data_urls(value: Any) -> tuple[list[str], int]:
    out: list[str] = []
    failed = 0
    for data_url in _image_urls(value):
        try:
            head, payload = data_url.split(",", 1)
            raw = base64.b64decode(payload, validate=True)
            if not raw:
                raise ValueError("empty image")
        except Exception:
            failed += 1
            continue
        mime_type = head.split(";", 1)[0].replace("data:", "").strip().lower() or "image/png"
        compressed, output_mime, meta = compress_base64_image_for_anthropic(payload, mime_type)
        if str(meta.get("reason") or "") in {"invalid_size", "pillow_missing", "resize_failed"}:
            failed += 1
            continue
        normalized = f"data:{output_mime};base64,{compressed}"
        if normalized not in out:
            out.append(normalized)
    return out, failed


def _append_image_fallbacks(text: str, count: int, limit: int = _MAX_TEXT_CHARS) -> str:
    if count <= 0:
        return _clip_text(text, limit)
    suffix = " ".join("【图片】" for _ in range(count))
    available = max(0, int(limit) - len(suffix) - 1)
    prefix = _clip_text(text, available).strip() if available else ""
    return " ".join(part for part in (prefix, suffix) if part)


def _event_iso(raw_ts: Any = None) -> str:
    try:
        n = float(raw_ts or 0)
    except Exception:
        n = 0
    if n > 0:
        # OneBot event time is seconds since epoch.
        if n > 10_000_000_000:
            n = n / 1000.0
        return datetime.fromtimestamp(n, tz=BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    return now_beijing_iso()


def _clock(iso_str: str) -> str:
    dt = parse_iso_to_beijing(str(iso_str or "").strip())
    if not dt:
        return str(iso_str or "")[:16] or "--:--"
    return dt.strftime("%H:%M")


def _row_from_payload(raw: dict) -> dict:
    is_owner = bool(raw.get("is_owner"))
    sender = str(raw.get("sender_name") or raw.get("name") or "").strip()
    if is_owner:
        sender = "辛玥"
    images, failed_images = _compress_image_data_urls(raw.get("images"))
    return {
        "at": _event_iso(raw.get("timestamp") or raw.get("ts")),
        "group_id": str(raw.get("group_id") or "").strip(),
        "user_id": str(raw.get("user_id") or "").strip(),
        "sender_name": sender or "群友",
        "is_owner": is_owner,
        "text": _append_image_fallbacks(str(raw.get("text") or ""), failed_images),
        "images": images,
        "message_id": str(raw.get("message_id") or "").strip(),
    }


def _normalize_context_rows(rows: Any, current_row: dict) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for raw in (rows if isinstance(rows, list) else []):
        if not isinstance(raw, dict):
            continue
        row = _row_from_payload(raw)
        key = row.get("message_id") or f"{row.get('at')}|{row.get('user_id')}|{row.get('text')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    cur_key = current_row.get("message_id") or f"{current_row.get('at')}|{current_row.get('user_id')}|{current_row.get('text')}"
    if cur_key not in seen:
        out.append(current_row)
    return out[-_MAX_CONTEXT_ROWS:]


def _load_state() -> dict:
    client = r2_store._s3_client()
    if not client:
        return {}
    data = r2_store._read_json(client, R2_KEY_QQ_XINYUE_GROUP_ACTIVITY)
    return data if isinstance(data, dict) else {}


def _save_state(state: dict) -> bool:
    client = r2_store._s3_client()
    if not client:
        return False
    with r2_store._global_write_lock:
        r2_store._write_json(client, R2_KEY_QQ_XINYUE_GROUP_ACTIVITY, state)
    return True


def record_group_activity(payload: dict) -> bool:
    """Record one owner-anchored QQ group activity snapshot for later wakeup context."""
    if not isinstance(payload, dict) or not bool(payload.get("is_owner")):
        return False
    row = _row_from_payload(payload)
    if not row.get("text") and not row.get("images"):
        return False
    msg_id = row.get("message_id") or f"{row.get('group_id')}|{row.get('user_id')}|{row.get('at')}|{row.get('text')[:40]}"
    item = {
        "id": msg_id,
        "recorded_at": now_beijing_iso(),
        "latest_owner_at": row.get("at"),
        "group_id": row.get("group_id"),
        "message_id": row.get("message_id"),
        "owner_text": row.get("text"),
        "context": _normalize_context_rows(payload.get("context") or [], row),
    }
    try:
        state = _load_state()
        items = [x for x in (state.get("items") or []) if isinstance(x, dict)]
        for old_item in items:
            for old_row in old_item.get("context") or []:
                if isinstance(old_row, dict):
                    old_row["images"] = []
        replaced = False
        for idx, old in enumerate(items):
            if str(old.get("id") or "") == msg_id:
                items[idx] = item
                replaced = True
                break
        if not replaced:
            items.insert(0, item)
        items = sorted(items, key=lambda x: str(x.get("latest_owner_at") or x.get("recorded_at") or ""), reverse=True)
        state["items"] = items[:_MAX_ACTIVITY_ITEMS]
        state["updated_at"] = now_beijing_iso()
        ok = _save_state(state)
        logger.info(
            "qq_group_activity_record ok=%s group_id=%s message_id=%s text_chars=%s context_rows=%s",
            ok,
            row.get("group_id"),
            row.get("message_id"),
            len(row.get("text") or ""),
            len(item["context"]),
        )
        return bool(ok)
    except Exception as e:
        logger.warning("qq_group_activity_record_failed error=%s", e, exc_info=True)
        return False


def clear_group_activity_context(reason: str = "user_private_reply") -> bool:
    try:
        state = _load_state()
        state["items"] = []
        state["cleared_at"] = now_beijing_iso()
        state["clear_reason"] = str(reason or "").strip() or "user_private_reply"
        state["updated_at"] = now_beijing_iso()
        return _save_state(state)
    except Exception as e:
        logger.debug("qq_group_activity_clear_failed reason=%s error=%s", reason, e)
        return False


def _items_after_last_proactive(items: list[dict]) -> list[dict]:
    last_contact = r2_store.get_last_proactive_contact_at()
    last_dt = parse_iso_to_beijing(str(last_contact or "").strip())
    if not last_dt:
        return []
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    cutoff = None
    if now_dt:
        cutoff = now_dt - timedelta(hours=_CONTEXT_TTL_HOURS)
    out = []
    for item in items:
        item_dt = parse_iso_to_beijing(str(item.get("latest_owner_at") or item.get("recorded_at") or "").strip())
        if not item_dt or item_dt <= last_dt:
            continue
        if cutoff and item_dt < cutoff:
            continue
        out.append(item)
    return sorted(out, key=lambda x: str(x.get("latest_owner_at") or x.get("recorded_at") or ""))


def _recent_context_images(rows: list[dict]) -> list[str]:
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    cutoff = None
    if now_dt:
        cutoff = now_dt - timedelta(hours=_IMAGE_CONTEXT_TTL_HOURS)
    out: list[str] = []
    for row in reversed(rows[-_MAX_CONTEXT_ROWS:]):
        if not isinstance(row, dict):
            continue
        row_dt = parse_iso_to_beijing(str(row.get("at") or "").strip())
        if cutoff and (not row_dt or row_dt < cutoff):
            continue
        for url in reversed(_image_urls(row.get("images"))):
            if url not in out:
                out.append(url)
            if len(out) >= _MAX_CONTEXT_IMAGES:
                return out
    return out


def build_group_activity_context_for_wakeup() -> list[dict] | str:
    try:
        state = _load_state()
        items = _items_after_last_proactive([x for x in (state.get("items") or []) if isinstance(x, dict)])
    except Exception as e:
        logger.debug("qq_group_activity_build_skip error=%s", e)
        return ""
    if not items:
        return ""
    latest = items[-1]
    older = items[:-1][-6:]
    latest_rows = [x for x in (latest.get("context") or [])[-_MAX_CONTEXT_ROWS:] if isinstance(x, dict)]
    image_urls = list(reversed(_recent_context_images(latest_rows)))

    lines = [
        "【辛玥近期的QQ群活动】",
        "上次你发信息后，小玥还没有在私聊回复你，但她期间在QQ群里有过发言。这些是近期群聊上下文，区分不同发言人，不要把群友的话当成小玥说的。",
        "",
    ]
    if older:
        lines.append("更早记录：")
        for item in older:
            lines.append(f"- {_clock(str(item.get('latest_owner_at') or item.get('recorded_at') or ''))} 辛玥在QQ群里发言")
        lines.append("")
    lines.append("最新片段：")
    for row in latest_rows:
        name = "辛玥" if bool(row.get("is_owner")) else (str(row.get("sender_name") or "").strip() or "群友")
        text = _clip_text(row.get("text"), _MAX_TEXT_CHARS)
        if text:
            lines.append(f"{_clock(str(row.get('at') or ''))} {name}：{text}")
    if image_urls:
        lines.append(f"（已随上下文附上最近 1 小时内最新的 {len(image_urls)} 张群聊图片，按时间从旧到新排列。）")
    lines.extend(
        [
            "",
            "【以上为近期群聊上下文】",
        ]
    )
    text = "\n".join(lines).strip()
    logger.info(
        "qq_group_activity_context_built items=%s chars=%s images=%s",
        len(items),
        len(text),
        len(image_urls),
    )
    if not image_urls:
        return text
    content = [{"type": "text", "text": text}]
    content.extend(
        {
            "type": "image_url",
            "image_url": {"url": url},
            "__skip_image_description": True,
        }
        for url in image_urls
    )
    return content
