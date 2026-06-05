from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from storage import r2_store
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

R2_KEY_QQ_XINYUE_GROUP_ACTIVITY = "global/qq_xinyue_group_activity.json"
_MAX_ACTIVITY_ITEMS = 24
_MAX_CONTEXT_ROWS = 8
_MAX_TEXT_CHARS = 180
_CONTEXT_TTL_HOURS = 24


def _clip_text(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = " ".join(str(value or "").replace("\r", "\n").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


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
    return {
        "at": _event_iso(raw.get("timestamp") or raw.get("ts")),
        "group_id": str(raw.get("group_id") or "").strip(),
        "user_id": str(raw.get("user_id") or "").strip(),
        "sender_name": sender or "群友",
        "is_owner": is_owner,
        "text": _clip_text(raw.get("text")),
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
    if not row.get("text"):
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


def build_group_activity_context_for_wakeup() -> str:
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

    lines = [
        "【辛玥未回复期间的QQ群活动】",
        "上次你主动找辛玥后，辛玥还没有在私聊回复你。但她期间在QQ群里有过发言。",
        "",
    ]
    if older:
        lines.append("更早记录：")
        for item in older:
            lines.append(f"- {_clock(str(item.get('latest_owner_at') or item.get('recorded_at') or ''))} 辛玥在QQ群里发言")
        lines.append("")
    lines.append("最新片段：")
    for row in (latest.get("context") or [])[-_MAX_CONTEXT_ROWS:]:
        if not isinstance(row, dict):
            continue
        name = "辛玥" if bool(row.get("is_owner")) else (str(row.get("sender_name") or "").strip() or "群友")
        text = _clip_text(row.get("text"), _MAX_TEXT_CHARS)
        if text:
            lines.append(f"{_clock(str(row.get('at') or ''))} {name}：{text}")
    lines.extend(
        [
            "",
            "这些内容不是辛玥在当前私聊里对你说的话。它们只是旁路上下文，用来帮助你理解辛玥当前可能在忙什么、注意力在哪里。不要质问她为什么没回你，不要逐条复述群聊内容，也不要把其他人的发言当成辛玥的想法。",
            "【以上为旁路上下文】",
        ]
    )
    text = "\n".join(lines).strip()
    logger.info("qq_group_activity_context_built items=%s chars=%s", len(items), len(text))
    return text
