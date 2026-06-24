from __future__ import annotations

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from storage import r2_store, whitelist_store


def normalize_reply_channel(value: str, default: str = "", allow_tg: bool = True) -> str:
    s = str(value or "").strip().lower()
    alias = {
        "wx": "wechat",
        "weixin": "wechat",
        "sumi": "sumitalk",
        "sumi-talk": "sumitalk",
        "sumi_talk": "sumitalk",
        "telegram": "tg",
    }
    s = alias.get(s, s)
    allowed = {"sumitalk", "wechat", "qq", "xiaoai"}
    if allow_tg:
        allowed.add("tg")
    return s if s in allowed else default


def resolve_primary_chat_window_id() -> str:
    try:
        uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    except Exception:
        uid = 0
    if uid > 0:
        return f"tg_{uid}"
    try:
        recent = whitelist_store.list_recent_windows(limit=200) or []
    except Exception:
        recent = []
    for item in recent:
        wid = str((item or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


def resolve_recent_reply_context(default_target: str = "") -> dict:
    try:
        meta = r2_store.get_last_reply_channel() or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    channel = normalize_reply_channel(str(meta.get("channel") or ""), default="", allow_tg=True)
    window_id = str(meta.get("window_id") or "").strip()
    target = str(meta.get("target") or "").strip()

    if not window_id:
        window_id = resolve_primary_chat_window_id()
    if not channel and window_id.startswith("tg_"):
        channel = "tg"
    if channel == "tg" and not target and window_id.startswith("tg_"):
        target = window_id[3:]
    if channel == "sumitalk" and not target:
        target = str(default_target or "").strip()
    if not target and not channel:
        target = str(default_target or "").strip()
    return {
        "channel": channel,
        "window_id": window_id,
        "target": target,
        "meta": meta,
    }
