import json
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import requests

from config import (
    QQ_PROACTIVE_PUSH_TOKEN,
    QQ_PROACTIVE_PUSH_URL,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_GATEWAY_URL,
    WECHAT_PROACTIVE_PUSH_TOKEN,
    WECHAT_PROACTIVE_PUSH_URL,
)
from services.telegram_bot import (
    _sanitize_reply_for_telegram,
    build_telegram_style_system,
    send_message_segmented,
)
from storage import r2_store
from storage.miniapp_panel_store import list_trusted_devices
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)
sumitalk_logger = get_logger("sumitalk")

FOLLOWUP_AFTER_MINUTES = 5
FOLLOWUP_TICK_SECONDS = 60
FOLLOWUP_MAX_CONSECUTIVE = 3
FOLLOWUP_STATUS_PENDING = "pending"
FOLLOWUP_STATUS_SENT = "sent"
FOLLOWUP_STATUS_CANCELLED = "cancelled"
FOLLOWUP_STATUS_EXPIRED = "expired"
FOLLOWUP_STATUS_ERROR = "error"
FOLLOWUP_MARKER_START = "[[DU_FOLLOWUP"
FOLLOWUP_MARKER_RE = re.compile(r"\[\[DU_FOLLOWUP\s*(\{[\s\S]*?\})\s*\]\]\s*$", re.IGNORECASE)


def build_followup_system_instruction() -> str:
    return (
        "如果你这句话说完，心里还是惦记着她，觉得过几分钟还想再轻轻接一句，"
        "你可以在整条回复最后追加一个隐藏标记："
        '[[DU_FOLLOWUP {"reason":"一句简短理由"}]]。\n'
        "要求：\n"
        "1) 只在确实想稍后再追一句时使用；\n"
        "2) 标记必须放在整条回复最后；\n"
        "3) 如果同一轮还要写表情包标签、<voice>、[PCMD:...]、心事、渡的日常或相处模式候选，"
        "这些都必须放在 DU_FOLLOWUP 前面；DU_FOLLOWUP 必须是整条回复的最后一个隐藏标记；\n"
        "4) 正文里不要解释这个标记。\n"
    )


def _normalize_reply_channel(value: str, default: str = "sumitalk", allow_tg: bool = True) -> str:
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
    allowed = {"sumitalk", "wechat", "qq"}
    if allow_tg:
        allowed.add("tg")
    if s not in allowed:
        return default
    return s


def _resolve_sumitalk_target_device_id(preferred: str = "") -> str:
    pref = str(preferred or "").strip()
    try:
        items = [x for x in (list_trusted_devices() or []) if isinstance(x, dict) and not bool(x.get("revoked"))]
    except Exception as e:
        sumitalk_logger.warning("target_resolve_failed source=followup preferred=%s error=%s", pref, e)
        items = []
    if pref:
        for item in items:
            if str(item.get("id") or "").strip() == pref:
                sumitalk_logger.info("target_resolved source=followup preferred=%s device_id=%s trusted_devices=%s matched=true", pref, pref, len(items))
                return pref
    for item in items:
        did = str(item.get("id") or "").strip()
        if did.startswith("android_"):
            sumitalk_logger.info("target_resolved source=followup preferred=%s device_id=%s trusted_devices=%s matched=false preferred=android", pref, did, len(items))
            return did
    for item in items:
        did = str(item.get("id") or "").strip()
        if did:
            sumitalk_logger.info("target_resolved source=followup preferred=%s device_id=%s trusted_devices=%s matched=false preferred=first", pref, did, len(items))
            return did
    if pref:
        sumitalk_logger.warning("target_resolved source=followup preferred=%s device_id=%s trusted_devices=%s matched=false fallback=preferred", pref, pref, len(items))
    else:
        sumitalk_logger.warning("target_resolve_empty source=followup trusted_devices=%s", len(items))
    return pref


def _append_sumitalk_assistant_message_to_device(device_id: str, text: str, created_at: str | None = None) -> bool:
    from routes.miniapp.sumitalk_history import (
        _SUMITALK_HISTORY_LOCK,
        _load_sumitalk_histories,
        _merge_sumitalk_messages,
        _save_sumitalk_histories,
    )

    did = _resolve_sumitalk_target_device_id(device_id)
    if not did:
        sumitalk_logger.warning("followup_append_failed reason=no_target_device preferred=%s chars=%s", device_id, len(str(text or "").strip()))
        return False
    content = str(text or "").strip()
    if not content:
        sumitalk_logger.warning("followup_append_skip reason=empty_content device_id=%s", did)
        return False
    now_iso = str(created_at or now_beijing_iso()).strip() or now_beijing_iso()
    message = {
        "id": f"assistant-followup-{int(time.time() * 1000)}",
        "role": "assistant",
        "content": content,
        "createdAt": now_iso,
    }
    with _SUMITALK_HISTORY_LOCK:
        data = _load_sumitalk_histories()
        current = data.get(did) if isinstance(data, dict) else None
        before_count = len((current or {}).get("messages") or [])
        merged_messages = _merge_sumitalk_messages((current or {}).get("messages") or [], [message])
        payload = {
            "device_id": did,
            "updated_at": now_iso,
            "messages": merged_messages,
        }
        data[did] = payload
        sumitalk_logger.info(
            "followup_append_write preferred=%s device_id=%s chars=%s before=%s after=%s created_at=%s known_devices=%s",
            device_id,
            did,
            len(content),
            before_count,
            len(merged_messages),
            now_iso,
            len(data or {}) if isinstance(data, dict) else 0,
        )
        ok = bool(_save_sumitalk_histories(data))
    if ok:
        sumitalk_logger.info("followup_append_ok preferred=%s device_id=%s chars=%s after=%s", device_id, did, len(content), len(merged_messages))
        try:
            from services.realtime_publish import publish_assistant_message

            publish_assistant_message(did, message, window_id="sumitalk-main")
        except Exception as e:
            sumitalk_logger.debug("followup_realtime_publish_failed device_id=%s error=%s", did, e)
    else:
        sumitalk_logger.error("followup_append_failed reason=save_failed preferred=%s device_id=%s chars=%s", device_id, did, len(content))
    return ok


def _send_via_wechat(text: str, split: bool = True) -> bool:
    url = WECHAT_PROACTIVE_PUSH_URL
    if not url:
        return False
    headers = {"Content-Type": "application/json"}
    if WECHAT_PROACTIVE_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {WECHAT_PROACTIVE_PUSH_TOKEN}"
    try:
        r = requests.post(url, headers=headers, json={"text": text, "split": bool(split)}, timeout=30)
        return r.status_code == 200 and bool((r.json() or {}).get("ok"))
    except Exception:
        logger.warning("延迟续话发微信失败", exc_info=True)
        return False


def _send_via_qq(text: str, split: bool = True) -> bool:
    url = QQ_PROACTIVE_PUSH_URL
    if not url:
        return False
    headers = {"Content-Type": "application/json"}
    if QQ_PROACTIVE_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {QQ_PROACTIVE_PUSH_TOKEN}"
    try:
        r = requests.post(url, headers=headers, json={"text": text, "split": bool(split)}, timeout=30)
        return r.status_code == 200 and bool((r.json() or {}).get("ok"))
    except Exception:
        logger.warning("延迟续话发 QQ 失败", exc_info=True)
        return False


def _dispatch_followup(channel: str, target: str, text: str, created_at: str, split: bool = True) -> bool:
    ch = _normalize_reply_channel(channel, default="sumitalk", allow_tg=True)
    if ch == "sumitalk":
        sumitalk_logger.info("followup_dispatch_start channel=%s target=%s chars=%s created_at=%s", ch, target, len(str(text or "").strip()), created_at)
    if ch == "wechat":
        return _send_via_wechat(text, split=split)
    if ch == "qq":
        return _send_via_qq(text, split=split)
    if ch == "tg":
        try:
            uid = int(str(target or "").strip() or "0")
        except Exception:
            uid = 0
        if uid <= 0:
            logger.warning("延迟续话发 TG 失败：target 无效 target=%s", target)
            return False
        outbound = _sanitize_reply_for_telegram(text)
        return send_message_segmented(chat_id=uid, text=outbound, bot_token=None) if outbound else False
    return _append_sumitalk_assistant_message_to_device(target, text, created_at=created_at)


def detect_reply_channel(window_id: str, headers: dict) -> str:
    explicit = _normalize_reply_channel(str((headers or {}).get("X-Reply-Channel") or "").strip(), default="", allow_tg=True)
    if explicit:
        return explicit
    auth = str((headers or {}).get("Authorization") or "").strip().lower()
    if auth.startswith("bearer "):
        return "sumitalk"
    if str((headers or {}).get("X-TG-User-Input") or "").strip().lower() in ("1", "true", "yes"):
        return "tg"
    return "sumitalk"


def detect_reply_target(window_id: str, headers: dict, channel: str) -> str:
    explicit = str((headers or {}).get("X-Reply-Target") or "").strip()
    if explicit:
        return explicit
    if channel == "tg":
        wid = str(window_id or "").strip()
        if wid.startswith("tg_"):
            return wid[3:]
    return ""


def _build_thread_key(window_id: str, channel: str, target: str) -> str:
    return f"{str(window_id or '').strip()}::{_normalize_reply_channel(channel, default='sumitalk', allow_tg=True)}::{str(target or '').strip()}"


def extract_followup_marker(text: str) -> tuple[str, Optional[dict]]:
    raw = str(text or "")
    m = FOLLOWUP_MARKER_RE.search(raw)
    if not m:
        return raw.strip(), None
    meta_raw = str(m.group(1) or "").strip()
    clean = raw[:m.start()].rstrip()
    try:
        obj = json.loads(meta_raw)
    except Exception:
        logger.warning("延迟续话标记 JSON 无法解析 meta=%s", meta_raw[:200])
        return clean, None
    if not isinstance(obj, dict):
        return clean, None
    enabled = bool(obj.get("enabled", True))
    if not enabled:
        return clean, None
    after_minutes = int(obj.get("after_minutes") or FOLLOWUP_AFTER_MINUTES)
    if after_minutes != FOLLOWUP_AFTER_MINUTES:
        after_minutes = FOLLOWUP_AFTER_MINUTES
    reason = str(obj.get("reason") or "").strip()
    if not reason:
        reason = "她可能暂时没回，我想稍后自然续一句。"
    return clean, {"after_minutes": after_minutes, "reason": reason[:200]}


def compute_visible_streaming(acc: str) -> str:
    raw = str(acc or "")
    if not raw:
        return ""
    clean, followup = extract_followup_marker(raw)
    if followup:
        return clean

    lower = raw.lower()
    marker_start = FOLLOWUP_MARKER_START.lower()
    start = lower.rfind(marker_start)
    if start >= 0:
        tail = raw[start:]
        if "]]" not in tail:
            return raw[:start].rstrip()

    max_len = min(len(raw), len(marker_start) - 1)
    for size in range(max_len, 0, -1):
        if marker_start.startswith(lower[-size:]):
            return raw[:-size].rstrip()
    return raw


def queue_followup(window_id: str, headers: dict, assistant_text: str, created_at: str | None = None) -> tuple[str, bool]:
    clean_text, followup = extract_followup_marker(assistant_text)
    if not followup:
        return clean_text, False
    context_window_id = str(window_id or "").strip()
    if not context_window_id:
        return clean_text, False
    channel = detect_reply_channel(context_window_id, headers or {})
    target = detect_reply_target(context_window_id, headers or {}, channel)
    thread_key = _build_thread_key(context_window_id, channel, target)
    created_iso = str(created_at or now_beijing_iso()).strip() or now_beijing_iso()
    created_dt = parse_iso_to_beijing(created_iso) or parse_iso_to_beijing(now_beijing_iso())
    trigger_dt = created_dt + timedelta(minutes=FOLLOWUP_AFTER_MINUTES)
    chain_id = str((headers or {}).get("X-DU-FOLLOWUP-CHAIN-ID") or "").strip()
    chain_count_raw = str((headers or {}).get("X-DU-FOLLOWUP-COUNT") or "").strip()
    root_created_at = str((headers or {}).get("X-DU-FOLLOWUP-ROOT-AT") or "").strip() or created_iso
    continue_chain = bool(chain_id)
    if continue_chain:
        try:
            current_count = int(chain_count_raw or "0")
        except Exception:
            current_count = 0
        next_count = current_count + 1
        if next_count > FOLLOWUP_MAX_CONSECUTIVE:
            logger.info(
                "延迟续话达到上限，忽略新标记 window_id=%s channel=%s target=%s chain_id=%s current=%s",
                context_window_id,
                channel,
                target,
                chain_id,
                current_count,
            )
            return clean_text, False
        followup_index = next_count
    else:
        chain_id = f"followup_chain_{uuid4()}"
        followup_index = 1
        root_created_at = created_iso
    item = {
        "id": f"followup_{uuid4()}",
        "context_window_id": context_window_id,
        "reply_channel": channel,
        "reply_target": target,
        "thread_key": thread_key,
        "chain_id": chain_id,
        "followup_index": followup_index,
        "root_created_at": root_created_at,
        "created_at": created_iso,
        "trigger_at": trigger_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "status": FOLLOWUP_STATUS_PENDING,
        "reason": str(followup.get("reason") or "").strip(),
        "source_preview": clean_text[:120],
        "attempts": 0,
    }
    items = r2_store.get_conversation_followups() or []
    changed = False
    if not continue_chain:
        for old in items:
            if not isinstance(old, dict):
                continue
            if str(old.get("thread_key") or "") != thread_key:
                continue
            if str(old.get("status") or "").strip().lower() != FOLLOWUP_STATUS_PENDING:
                continue
            old["status"] = FOLLOWUP_STATUS_CANCELLED
            old["cancelled_at"] = created_iso
            old["cancel_reason"] = "superseded_by_new_reply"
            changed = True
    items.insert(0, item)
    if len(items) > 200:
        items = items[:200]
    ok = r2_store.save_conversation_followups(items)
    logger.info(
        "已记录延迟续话任务 ok=%s window_id=%s channel=%s target=%s trigger_at=%s chain_id=%s index=%s cancelled_old=%s",
        ok,
        context_window_id,
        channel,
        target,
        item["trigger_at"],
        chain_id,
        followup_index,
        changed,
    )
    return clean_text, bool(ok)


def _has_new_user_activity(window_id: str, since_iso: str) -> bool:
    since_dt = parse_iso_to_beijing(since_iso)
    if not since_dt:
        return False
    rounds = r2_store.get_conversation_rounds(window_id, last_n=80) or []
    for r in reversed(rounds):
        if not isinstance(r, dict):
            continue
        ts = parse_iso_to_beijing(str(r.get("timestamp") or "").strip())
        if not ts or ts <= since_dt:
            continue
        msgs = r.get("messages") or []
        for msg in msgs:
            if isinstance(msg, dict) and str(msg.get("role") or "").strip().lower() == "user":
                return True
    return False


def _call_gateway_followup(window_id: str, channel: str, reason: str, chain_id: str, followup_index: int, root_created_at: str) -> Optional[str]:
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=True) or "").strip()
    except Exception:
        model = ""
    if not model:
        return None
    body = {
        "model": model,
        "stream": False,
        "messages": [],
    }
    if channel == "tg":
        body["messages"].append({"role": "system", "content": build_telegram_style_system(include_channel_hint=False)})
    body["messages"].append(
        {
            "role": "user",
            "content": (
                f"这是同一段对话的第 {followup_index} 次延迟续话。你上一条回复发出后，对方大约 5 分钟没有再回复。"
                "请基于当前上下文，自然地再补一句，不要重复刚才那句，不要解释规则，也不要变成长篇。"
                f"这次续话的意图：{reason}"
            ),
        }
    )
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": str(window_id or "").strip(),
        "X-Reply-Channel": _normalize_reply_channel(channel, default="sumitalk", allow_tg=True),
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-FOLLOWUP-GEN": "1",
        "X-Skip-Dynamic-Memory": "1",
        "X-DU-FOLLOWUP-CHAIN-ID": str(chain_id or "").strip(),
        "X-DU-FOLLOWUP-COUNT": str(int(followup_index or 0)),
        "X-DU-FOLLOWUP-ROOT-AT": str(root_created_at or "").strip(),
    }
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            logger.warning("延迟续话调用网关失败 status=%s body=%s", r.status_code, (r.text or "")[:300])
            return None
        data = r.json() if r.content else {}
        msg = (((data or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip() or None
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if str(part.get("type") or "") == "text":
                        parts.append(str(part.get("text") or ""))
                    elif isinstance(part.get("text"), str):
                        parts.append(str(part.get("text") or ""))
            text = "\n".join(x.strip() for x in parts if str(x).strip()).strip()
            return text or None
        return None
    except Exception:
        logger.warning("延迟续话调用网关异常", exc_info=True)
        return None


def _choice_dialog_delivery_preference(default_target: str) -> tuple[str, str, dict]:
    try:
        meta = r2_store.get_last_reply_channel() or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    channel = _normalize_reply_channel(str(meta.get("channel") or ""), default="", allow_tg=True)
    target = str(meta.get("target") or "").strip()
    window_id = str(meta.get("window_id") or "").strip()
    if channel == "tg" and not target and window_id.startswith("tg_"):
        target = window_id[3:]
    if channel == "sumitalk" and not target:
        target = str(default_target or "").strip()
    return channel, target, meta


def _choice_dialog_delivery_channels(preferred_channel: str, available_channels: list[str], preferred_target: str) -> list[str]:
    ordered: list[str] = []

    def add(channel: str) -> None:
        ch = _normalize_reply_channel(channel, default="", allow_tg=True)
        if ch and ch not in ordered:
            ordered.append(ch)

    if preferred_channel in {"wechat", "qq", "sumitalk"}:
        add(preferred_channel)
    elif preferred_channel == "tg" and str(preferred_target or "").strip():
        add("tg")
    for channel in available_channels or []:
        add(channel)
    return ordered


def _dispatch_choice_dialog_reply(channel: str, target: str, text: str, created_at: str | None = None) -> bool:
    ch = _normalize_reply_channel(channel, default="", allow_tg=True)
    if ch in {"wechat", "qq"}:
        from services.telegram_proactive import _dispatch_send

        return _dispatch_send(ch, text, split=True)
    if ch in {"tg", "sumitalk"}:
        return _dispatch_followup(ch, target, text, created_at or now_beijing_iso())
    return False


def _send_wakeup_event(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    extra_instruction: str = "",
    image_url: str = "",
    archive: bool = True,
) -> dict:
    """立即让渡基于一个后端事件生成回应，并通过最近对话入口或主动入口发出。事件唤醒默认归档，避免后续对话断层。"""
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=True) or "").strip()
    except Exception:
        model = ""
    if not model:
        return {"ok": False, "error": "missing_model"}
    context_window_id = str(window_id or "").strip()
    if not context_window_id:
        return {"ok": False, "error": "missing_window_id"}
    prompt = str(event_text or "").strip()
    if not prompt:
        return {"ok": False, "error": "empty_event"}
    preferred_channel, preferred_target, preferred_meta = _choice_dialog_delivery_preference(target)
    generation_channel = preferred_channel or "sumitalk"
    content = prompt
    extra = str(extra_instruction or "").strip()
    if extra:
        content = f"{content}\n\n{extra}"
    image = str(image_url or "").strip()
    message_content = content
    if image:
        message_content = [
            {"type": "text", "text": content},
            {"type": "image_url", "image_url": {"url": image}},
        ]

    body = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": message_content,
            }
        ],
    }
    if generation_channel == "tg":
        body["messages"].insert(0, {"role": "system", "content": build_telegram_style_system(include_channel_hint=False)})
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": context_window_id,
        "X-Reply-Channel": generation_channel,
        "X-Reply-Target": str(preferred_target or target or "").strip(),
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-FOLLOWUP-GEN": "1",
        "X-Skip-Dynamic-Memory": "1",
        "X-Force-Last4": "1",
    }
    if archive:
        headers["X-DU-FOLLOWUP-ARCHIVE"] = "1"
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            logger.warning("后端事件唤醒调用网关失败 status=%s body=%s", r.status_code, (r.text or "")[:300])
            return {"ok": False, "error": f"gateway_http_{r.status_code}"}
        data = r.json() if r.content else {}
        msg = (((data or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if str(part.get("type") or "") == "text":
                        parts.append(str(part.get("text") or ""))
                    elif isinstance(part.get("text"), str):
                        parts.append(str(part.get("text") or ""))
            text = "\n".join(x.strip() for x in parts if str(x).strip()).strip()
        else:
            text = str(content or "").strip()
        text, _followup = extract_followup_marker(text)
        if not text:
            return {"ok": False, "error": "empty_gateway_reply"}
        from services.telegram_proactive import _available_channels

        channels = _choice_dialog_delivery_channels(preferred_channel, _available_channels(), preferred_target)
        if not channels:
            return {"ok": False, "error": "no_proactive_channel", "reply_preview": text[:120]}
        outbound = _sanitize_reply_for_telegram(text).strip()
        if not outbound:
            return {"ok": False, "error": "empty_after_sanitize"}
        attempted_channels = []
        for channel in channels:
            attempted_channels.append(channel)
            send_target = preferred_target if channel == preferred_channel else str(target or "").strip()
            if _dispatch_choice_dialog_reply(channel, send_target, outbound, created_at=created_at):
                return {
                    "ok": True,
                    "channel": channel,
                    "attempted_channels": attempted_channels,
                    "preferred_channel": preferred_channel,
                    "preferred_channel_at": str(preferred_meta.get("at") or ""),
                    "reply_preview": outbound[:120],
                    "error": "",
                }
        return {
            "ok": False,
            "channel": attempted_channels[-1] if attempted_channels else "",
            "attempted_channels": attempted_channels,
            "preferred_channel": preferred_channel,
            "preferred_channel_at": str(preferred_meta.get("at") or ""),
            "reply_preview": outbound[:120],
            "error": "dispatch_failed",
        }
    except Exception as e:
        logger.warning("后端事件唤醒异常", exc_info=True)
        return {"ok": False, "error": str(e)}


def send_choice_dialog_wakeup(window_id: str, target: str, event_text: str, created_at: str | None = None) -> dict:
    """立即让渡基于 SumiTalk 弹窗回执生成回应，并通过主动消息入口发出。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        extra_instruction=(
            "请你现在直接对她回应一两句。不要解释工具、回执或系统流程；"
            "不要把这当成普通任务总结，要像刚收到她这个动作一样自然接住。"
        ),
    )


def send_screen_check_wakeup(window_id: str, target: str, event_text: str, image_url: str, created_at: str | None = None) -> dict:
    """立即让渡看一张经老婆同意的手机截图，再自然回应。"""
    has_image = bool(str(image_url or "").strip())
    instruction = (
        "请你看图后自然回应一两句。不要解释工具、回执或系统流程；"
        "如果截图里有隐私内容，不要复述敏感细节，只围绕她现在在做什么给出温和回应。"
        if has_image
        else "请你根据这个查岗截图结果自然回应一两句。不要解释工具、回执或系统流程；"
    )
    instruction += "不要把系统截屏授权没完成说成她本人拒绝。"
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        image_url=image_url,
        archive=True,
        extra_instruction=instruction,
    )


def send_proactive_trigger_wakeup(window_id: str, target: str, event_text: str, created_at: str | None = None) -> dict:
    """立即让渡基于后端主动触发事实生成回应。event_text 只放事实，不追加回应指令。"""
    return _send_wakeup_event(window_id=window_id, target=target, event_text=event_text, created_at=created_at, archive=True)


def tick_conversation_followups() -> dict:
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso)
    if not now_dt:
        return {"ok": False, "error": "time_parse_failed"}
    items = r2_store.get_conversation_followups() or []
    if not items:
        return {"ok": True, "checked": 0, "sent": 0, "cancelled": 0, "pending": 0, "now": now_iso}
    changed = False
    sent = 0
    cancelled = 0
    pending = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status not in ("", FOLLOWUP_STATUS_PENDING):
            continue
        trigger_dt = parse_iso_to_beijing(str(item.get("trigger_at") or "").strip())
        if not trigger_dt:
            item["status"] = FOLLOWUP_STATUS_ERROR
            item["last_error"] = "invalid_trigger_at"
            changed = True
            continue
        if trigger_dt > now_dt:
            pending += 1
            continue
        window_id = str(item.get("context_window_id") or "").strip()
        created_at = str(item.get("created_at") or "").strip()
        if not window_id or not created_at:
            item["status"] = FOLLOWUP_STATUS_ERROR
            item["last_error"] = "missing_context"
            changed = True
            continue
        if _has_new_user_activity(window_id, created_at):
            item["status"] = FOLLOWUP_STATUS_CANCELLED
            item["cancelled_at"] = now_iso
            item["cancel_reason"] = "user_replied"
            cancelled += 1
            changed = True
            continue
        attempts = int(item.get("attempts") or 0)
        if attempts >= 3:
            item["status"] = FOLLOWUP_STATUS_EXPIRED
            item["expired_at"] = now_iso
            item["last_error"] = str(item.get("last_error") or "max_attempts_reached")
            changed = True
            continue
        text = _call_gateway_followup(
            window_id=window_id,
            channel=str(item.get("reply_channel") or "sumitalk"),
            reason=str(item.get("reason") or "").strip(),
            chain_id=str(item.get("chain_id") or "").strip(),
            followup_index=int(item.get("followup_index") or 1),
            root_created_at=str(item.get("root_created_at") or item.get("created_at") or "").strip(),
        )
        item["attempts"] = attempts + 1
        item["last_attempt_at"] = now_iso
        if not text:
            item["last_error"] = "empty_gateway_reply"
            changed = True
            pending += 1
            continue
        ok = _dispatch_followup(
            channel=str(item.get("reply_channel") or "sumitalk"),
            target=str(item.get("reply_target") or "").strip(),
            text=text,
            created_at=now_iso,
        )
        if ok:
            item["status"] = FOLLOWUP_STATUS_SENT
            item["sent_at"] = now_iso
            item["sent_preview"] = text[:120]
            sent += 1
        else:
            item["last_error"] = "dispatch_failed"
            pending += 1
        changed = True
    if changed:
        keep = []
        cutoff = now_dt - timedelta(days=3)
        for item in items:
            ts = parse_iso_to_beijing(str(item.get("created_at") or "").strip())
            if ts and ts < cutoff and str(item.get("status") or "").strip().lower() in {
                FOLLOWUP_STATUS_SENT,
                FOLLOWUP_STATUS_CANCELLED,
                FOLLOWUP_STATUS_EXPIRED,
            }:
                continue
            keep.append(item)
        r2_store.save_conversation_followups(keep)
    return {
        "ok": True,
        "checked": len(items),
        "sent": sent,
        "cancelled": cancelled,
        "pending": pending,
        "now": now_iso,
    }
