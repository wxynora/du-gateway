import time
from datetime import datetime, timezone

from config import (
    RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED,
    RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS,
)
from services.chat_content import message_content_chars
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)


def last_user_message(messages):
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() == "user":
            return m
    return None


def extract_last_user_text(messages) -> str:
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return (content or "").strip().lower()
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and (c.get("type") or "").lower() == "text":
                    parts.append(str(c.get("text") or ""))
            return " ".join(parts).strip().lower()
        return str(content or "").strip().lower()
    return ""


def parse_iso_ts(ts: str):
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_suspected_rikkahub_phantom_one(body: dict, window_id: str, headers: dict) -> bool:
    """拦截 RikkaHub 偶发误发的单独 '1'（短时间内紧跟上一轮）。"""
    if not RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED:
        return False
    ua = (headers.get("User-Agent") or "").lower()
    if "rikkahub" not in ua:
        return False
    cur_user = (extract_last_user_text(body.get("messages") or []) or "").strip()
    if cur_user not in ("1", "１"):
        return False
    try:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=1) or []
        if not rounds:
            return False
        last_round = rounds[-1] if isinstance(rounds[-1], dict) else {}
        last_ts = parse_iso_ts(str(last_round.get("timestamp") or ""))
        if not last_ts:
            return False
        gap_s = (datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)).total_seconds()
        if gap_s < 0 or gap_s > max(1, int(RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS or 90)):
            return False
        prev_user = (extract_last_user_text(last_round.get("messages") or []) or "").strip()
        if prev_user in ("1", "１"):
            return False
        return True
    except Exception:
        return False


def build_noop_chat_response(body: dict) -> dict:
    model = (body.get("model") or "noop")
    return {
        "id": f"chatcmpl_noop_{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "（检测到客户端误触发，已忽略本次空输入）"},
                "finish_reason": "stop",
            }
        ],
    }


def is_cross_platform_tg_window_user_input(
    window_id: str,
    body: dict,
    *,
    reply_channel: str,
    is_followup_generation: bool,
) -> bool:
    wid = str(window_id or "").strip()
    if not wid.startswith("tg_"):
        return False
    if is_followup_generation:
        return False
    if reply_channel not in {"sumitalk", "wechat", "qq"}:
        return False
    last_user = last_user_message((body or {}).get("messages") or [])
    if not isinstance(last_user, dict):
        return False
    content = last_user.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(
            isinstance(part, dict) and str(part.get("type") or "").strip().lower() in {"text", "image_url", "input_audio"}
            for part in content
        )
    return bool(str(content or "").strip())


def maybe_mark_tg_window_user_activity(
    window_id: str,
    body: dict,
    *,
    reply_channel: str,
    is_followup_generation: bool,
) -> None:
    if not is_cross_platform_tg_window_user_input(
        window_id,
        body,
        reply_channel=reply_channel,
        is_followup_generation=is_followup_generation,
    ):
        return
    try:
        r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
        logger.info("按 tg 窗口更新最近用户回复时间 window_id=%s reply_channel=%s", window_id, reply_channel)
    except Exception as e:
        logger.warning("按 tg 窗口更新最近用户回复时间失败 window_id=%s error=%s", window_id, e)


def maybe_record_last_reply_channel(
    window_id: str,
    body: dict,
    *,
    reply_channel: str,
    reply_target: str = "",
    is_followup_generation: bool,
    is_du_daily_maintenance: bool,
) -> None:
    if is_followup_generation or is_du_daily_maintenance:
        return
    if reply_channel not in {"tg", "sumitalk", "wechat", "qq"}:
        return
    last_user = last_user_message((body or {}).get("messages") or [])
    if not isinstance(last_user, dict) or message_content_chars(last_user.get("content")) <= 0:
        return
    target = str(reply_target or "").strip()
    if not target and reply_channel == "tg":
        wid = str(window_id or "").strip()
        if wid.startswith("tg_"):
            target = wid[3:]
    try:
        r2_store.save_last_reply_channel(
            channel=reply_channel,
            window_id=window_id,
            target=target,
            at_iso=now_beijing_iso(),
        )
        logger.info("已更新最近对话入口 window_id=%s channel=%s target=%s", window_id, reply_channel, target)
    except Exception as e:
        logger.warning("更新最近对话入口失败 window_id=%s channel=%s error=%s", window_id, reply_channel, e)
