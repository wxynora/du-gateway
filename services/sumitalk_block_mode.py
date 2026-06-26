from __future__ import annotations

import logging

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from storage import r2_store, sumitalk_block_mode_store, whitelist_store
from utils.time_aware import now_beijing_iso


logger = logging.getLogger("sumitalk")


def _resolve_global_archive_window_id() -> str:
    try:
        meta = r2_store.get_last_reply_channel() or {}
        wid = str(meta.get("window_id") or "").strip()
        if wid:
            return wid
    except Exception:
        pass
    try:
        recent = whitelist_store.list_recent_windows(limit=200) or []
        for row in recent:
            wid = str((row or {}).get("id") or "").strip()
            if wid.startswith("tg_"):
                return wid
        for row in recent:
            wid = str((row or {}).get("id") or "").strip()
            if wid:
                return wid
    except Exception:
        pass
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    return "sumitalk-main"


def _append_block_notice_to_global_context(created_at: str, reason: str = "") -> bool:
    window_id = _resolve_global_archive_window_id()
    message = {
        "role": "user",
        "archive_label": "小玥",
        "content": sumitalk_block_mode_store.BLOCK_NOTICE_TEXT,
        "skip_memory_summary": True,
        "skip_dynamic_memory": True,
        "source": "sumitalk_block_mode",
    }
    try:
        round_index = r2_store.get_next_round_index(window_id)
        ok = bool(
            r2_store.append_conversation_round(
                window_id,
                round_index,
                [message],
                timestamp=created_at,
                action_note=reason or "sumitalk_block_mode_notice",
            )
        )
        if ok:
            latest = r2_store.get_conversation_rounds(window_id, last_n=4)
            r2_store.update_latest_4_rounds_global(latest)
            logger.info("block_mode_notice_archive_ok window_id=%s round_index=%s reason=%s", window_id, round_index, reason)
        else:
            logger.warning("block_mode_notice_archive_failed window_id=%s round_index=%s reason=%s", window_id, round_index, reason)
        return ok
    except Exception as e:
        logger.warning("block_mode_notice_archive_error window_id=%s reason=%s error=%s", window_id, reason, e, exc_info=True)
        return False


def send_block_notice(*, created_at: str | None = None, reason: str = "") -> dict:
    ts = str(created_at or now_beijing_iso()).strip() or now_beijing_iso()
    context_ok = _append_block_notice_to_global_context(ts, reason=reason)
    return {"context_ok": bool(context_ok), "created_at": ts}


def maybe_auto_reply_after_sumitalk_assistant(*, incoming_message_id: str = "", created_at: str | None = None) -> dict:
    ts = str(created_at or now_beijing_iso()).strip() or now_beijing_iso()
    allowed, state = sumitalk_block_mode_store.try_consume_auto_reply(incoming_message_id, now_ts=ts)
    if not allowed:
        return {"sent": False, "state": state}
    result = send_block_notice(created_at=ts, reason="sumitalk_block_mode_auto_reply")
    return {"sent": True, "state": sumitalk_block_mode_store.get_state(), **result}
