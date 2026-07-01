import json
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import requests

from config import (
    QQ_PROACTIVE_PUSH_TOKEN,
    QQ_PROACTIVE_PUSH_URL,
    STREAM_TIMEOUT_SECONDS,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    WECHAT_PROACTIVE_PUSH_TOKEN,
    WECHAT_PROACTIVE_PUSH_URL,
)
from services.telegram_bot import (
    _sanitize_reply_for_telegram,
    build_telegram_style_system,
    send_rich_message,
    send_message_segmented,
)
from services.hidden_blocks import HiddenBlockParser
from services.reply_channel_context import normalize_reply_channel as _shared_normalize_reply_channel
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
FOLLOWUP_MARKER_START = "<<<DU_FOLLOWUP>>>"
FOLLOWUP_MARKER_END = "<<<END_DU_FOLLOWUP>>>"
FOLLOWUP_SHORT_MARKER = "[du:followup 一句简短理由]"
_FOLLOWUP_BLOCK = HiddenBlockParser.for_markers(
    "DU_FOLLOWUP",
    FOLLOWUP_MARKER_START,
    FOLLOWUP_MARKER_END,
    short_markers=("du:followup",),
)


def build_followup_system_instruction() -> str:
    return (
        "如果你这句话说完，心里还是惦记着她，觉得过几分钟还想再轻轻接一句，"
        "你可以在正文后追加一行短隐藏标记：\n"
        f"{FOLLOWUP_SHORT_MARKER}\n"
        "要求：\n"
        "1) 只在确实想稍后再追一句时使用；\n"
        "2) 只写一句简短理由，不要写 JSON；\n"
        "3) 隐藏标记统一追加在正文后，不要写进正文里；\n"
        "4) 正文里不要解释这个标记。\n"
    )


def _normalize_reply_channel(value: str, default: str = "sumitalk", allow_tg: bool = True) -> str:
    return _shared_normalize_reply_channel(value, default=default, allow_tg=allow_tg)


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


def _post_spring_dream_prompt_override_for_trigger(wakeup_kind: str, created_at: str | None = None) -> dict:
    if str(wakeup_kind or "").strip() != "proactive_trigger":
        return {}
    now_dt = parse_iso_to_beijing(str(created_at or "").strip()) or parse_iso_to_beijing(now_beijing_iso())
    if not now_dt:
        return {}
    try:
        from services.spring_dream import maybe_prepare_post_spring_dream_wakeup

        prepared = maybe_prepare_post_spring_dream_wakeup(
            now_dt=now_dt,
            require_sleeping=False,
            clear_on_empty_prompt=False,
        )
    except Exception:
        logger.warning("post_spring_dream prompt override lookup failed", exc_info=True)
        return {}
    if not isinstance(prepared, dict) or not str(prepared.get("prompt") or "").strip():
        return {}
    return prepared


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
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if WECHAT_PROACTIVE_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {WECHAT_PROACTIVE_PUSH_TOKEN}"
    try:
        body = json.dumps({"text": str(text or ""), "split": bool(split)}, ensure_ascii=False).encode("utf-8")
        r = requests.post(url, headers=headers, data=body, timeout=30)
        return r.status_code == 200 and bool((r.json() or {}).get("ok"))
    except Exception:
        logger.warning("延迟续话发微信失败", exc_info=True)
        return False


def _send_via_qq(text: str, split: bool = True) -> bool:
    url = QQ_PROACTIVE_PUSH_URL
    if not url:
        return False
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if QQ_PROACTIVE_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {QQ_PROACTIVE_PUSH_TOKEN}"
    try:
        body = json.dumps({"text": str(text or ""), "split": bool(split)}, ensure_ascii=False).encode("utf-8")
        r = requests.post(url, headers=headers, data=body, timeout=30)
        return r.status_code == 200 and bool((r.json() or {}).get("ok"))
    except Exception:
        logger.warning("延迟续话发 QQ 失败", exc_info=True)
        return False


def _dispatch_followup(channel: str, target: str, text: str, created_at: str, split: bool = True) -> bool:
    ch = _normalize_reply_channel(channel, default="sumitalk", allow_tg=True)
    try:
        from services.telegram_proactive import _sanitize_control_reply_for_delivery

        text = _sanitize_control_reply_for_delivery(text).strip()
    except Exception:
        text = str(text or "").strip()
    if not text:
        logger.warning("延迟续话外发跳过：清洗后为空 channel=%s target=%s", ch, target)
        return False
    if ch == "sumitalk":
        sumitalk_logger.info("followup_dispatch_start channel=%s target=%s chars=%s created_at=%s", ch, target, len(str(text or "").strip()), created_at)
    if ch == "wechat":
        return _send_via_wechat(text, split=split)
    if ch == "qq":
        return _send_via_qq(text, split=split)
    if ch == "xiaoai":
        logger.info("延迟续话暂不支持投递到小爱音箱，跳过")
        return False
    if ch == "tg":
        try:
            uid = int(str(target or "").strip() or "0")
        except Exception:
            uid = 0
        if uid <= 0:
            logger.warning("延迟续话发 TG 失败：target 无效 target=%s", target)
            return False
        return send_rich_message(chat_id=uid, text=text, bot_token=None)
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
    clean, meta_raw = _FOLLOWUP_BLOCK.split(raw)
    if not meta_raw:
        return clean.strip(), None
    meta_raw = str(meta_raw or "").strip()
    try:
        obj = json.loads(meta_raw)
    except Exception:
        if meta_raw.lstrip().startswith(("{", "[")):
            logger.warning("延迟续话标记 JSON 无法解析 meta=%s", meta_raw[:200])
            return clean, None
        reason = meta_raw.strip()
        if not reason:
            return clean, None
        return clean, {"after_minutes": FOLLOWUP_AFTER_MINUTES, "reason": reason[:200]}
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
    return _FOLLOWUP_BLOCK.compute_visible_streaming(raw)


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
            if not isinstance(msg, dict):
                continue
            if str(msg.get("source") or "") == "sumitalk_block_mode":
                continue
            if str(msg.get("role") or "").strip().lower() == "user":
                return True
    return False


def _call_gateway_followup(window_id: str, channel: str, reason: str, chain_id: str, followup_index: int, root_created_at: str) -> Optional[str]:
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
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
        r = requests.post(url, headers=headers, json=body, timeout=STREAM_TIMEOUT_SECONDS)
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


def _stable_proactive_wakeup_channel(default: str = "") -> str:
    """主动硬触发固定用一个入口生成，避免入口风格 system 在 TG/QQ 间抖动。"""
    if QQ_PROACTIVE_PUSH_URL:
        return "qq"
    if WECHAT_PROACTIVE_PUSH_URL:
        return "wechat"
    if TELEGRAM_BOT_TOKEN and TELEGRAM_PROACTIVE_TARGET_USER_ID:
        return "tg"
    return _normalize_reply_channel(default, default="sumitalk", allow_tg=True)


def _dispatch_choice_dialog_reply(channel: str, target: str, text: str, created_at: str | None = None) -> bool:
    ch = _normalize_reply_channel(channel, default="", allow_tg=True)
    if ch in {"wechat", "qq"}:
        from services.telegram_proactive import _dispatch_send

        return _dispatch_send(ch, text, split=True)
    if ch in {"tg", "sumitalk"}:
        return _dispatch_followup(ch, target, text, created_at or now_beijing_iso())
    return False


def _archive_wakeup_after_delivery(
    *,
    window_id: str,
    request_messages: list,
    assistant_text: str,
    wakeup_kind: str,
    reply_channel: str,
) -> bool:
    kind = str(wakeup_kind or "").strip().lower()
    if kind in {"spring_dream", "random_spring_dream"}:
        archive_user = {"role": "event", "archive_label": "随机唤醒", "content": "睡眠期随机唤醒触发了一次春梦。"}
    elif kind == "post_spring_dream":
        archive_user = {"role": "event", "archive_label": "随机唤醒", "content": "睡眠期随机唤醒延续上一轮春梦。"}
    else:
        archive_user = {"role": "event", "archive_label": "网关提醒", "content": "这是一次网关唤醒提醒。"}
    archive_assistant = {"role": "assistant", "content": str(assistant_text or "").strip()}
    if not archive_assistant["content"]:
        return False
    try:
        from pipeline.pipeline import step_archive_round
        from services.chat_archive_helpers import run_nonstream_post_archive_in_background

        archived = step_archive_round(
            str(window_id or "").strip(),
            request_messages if isinstance(request_messages, list) else [],
            archive_assistant,
            round_cleaned_for_r2=[archive_user, archive_assistant],
        )
        if archived:
            run_nonstream_post_archive_in_background(
                window_id=str(window_id or "").strip(),
                round_index=int(archived.get("round_index") or 0),
                round_messages=archived.get("round_messages") or [archive_user, archive_assistant],
                reply_channel=str(reply_channel or "").strip(),
                skip_dynamic_layer=True,
            )
            if str(reply_channel or "").strip().lower() == "sumitalk":
                try:
                    from services.sumitalk_block_mode import maybe_auto_reply_after_sumitalk_assistant

                    maybe_auto_reply_after_sumitalk_assistant(
                        incoming_message_id=f"wakeup-{str(wakeup_kind or '').strip()}-{int(archived.get('round_index') or 0)}",
                        created_at=now_beijing_iso(),
                    )
                except Exception as e:
                    sumitalk_logger.warning("block_mode_wakeup_auto_reply_failed window_id=%s error=%s", window_id, e)
            return True
    except Exception:
        logger.warning("后端事件投递后归档失败 window_id=%s kind=%s", window_id, kind, exc_info=True)
    return False


def _send_wakeup_event(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    extra_instruction: str = "",
    image_url: str = "",
    archive: bool = True,
    stable_proactive_channel: bool = False,
    wakeup_kind: str = "",
    system_event: bool = False,
    preferred_channel_override: str = "",
    preferred_target_override: str = "",
    preferred_meta_override: dict | None = None,
    lock_preferred_channel: bool = False,
    allow_followup: bool = True,
    archive_after_delivery: bool = False,
    allow_tool_only_reply: bool = False,
    skip_qq_group_activity: bool = False,
    system_event_user_summary: str = "",
    spring_dream_archive_meta: dict | None = None,
) -> dict:
    """立即让渡基于一个后端事件生成回应，并通过最近对话入口或主动入口发出。事件唤醒默认归档，避免后续对话断层。"""
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
    except Exception:
        model = ""
    if not model:
        return {"ok": False, "error": "missing_model"}
    context_window_id = str(window_id or "").strip()
    if not context_window_id:
        return {"ok": False, "error": "missing_window_id"}
    kind = str(wakeup_kind or "").strip()
    prompt = str(event_text or "").strip()
    if not prompt:
        return {"ok": False, "error": "empty_event"}
    post_spring_prompt_override = _post_spring_dream_prompt_override_for_trigger(kind, created_at)
    if post_spring_prompt_override:
        prompt = str(post_spring_prompt_override.get("prompt") or "").strip() or prompt
    preferred_channel, preferred_target, preferred_meta = _choice_dialog_delivery_preference(target)
    override_channel = _normalize_reply_channel(preferred_channel_override, default="", allow_tg=True)
    if override_channel:
        preferred_channel = override_channel
        preferred_target = str(preferred_target_override or preferred_target or target or "").strip()
        if isinstance(preferred_meta_override, dict):
            preferred_meta = preferred_meta_override
    if stable_proactive_channel:
        preferred_channel = _stable_proactive_wakeup_channel(preferred_channel)
        if preferred_channel == "tg" and not preferred_target and context_window_id.startswith("tg_"):
            preferred_target = context_window_id[3:]
        elif preferred_channel == "sumitalk" and not preferred_target:
            preferred_target = str(target or "").strip()
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
        "messages": [],
    }
    if generation_channel == "tg":
        body["messages"].insert(0, {"role": "system", "content": build_telegram_style_system(include_channel_hint=False)})
    if system_event and not image:
        body["messages"].append({"role": "system", "content": message_content})
        body["messages"].append(
            {
                "role": "user",
                "content": (
                    str(system_event_user_summary or "").strip()
                    or "请根据上面的系统提示生成要发送给她的回复。这是一条后端技术触发，不是她说的话。"
                ),
            }
        )
    else:
        body["messages"].append({"role": "user", "content": message_content})
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": context_window_id,
        "X-Reply-Channel": generation_channel,
        "X-Reply-Target": str(preferred_target or target or "").strip(),
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-FOLLOWUP-GEN": "1",
        "X-Skip-Dynamic-Memory": "1",
        "X-Skip-Post-Archive-Dynamic-Memory": "1",
        "X-Force-Last4": "1",
    }
    if kind:
        headers["X-DU-WAKEUP-KIND"] = kind
    if archive and not archive_after_delivery:
        headers["X-DU-FOLLOWUP-ARCHIVE"] = "1"
    if not allow_followup:
        headers["X-DU-DISABLE-FOLLOWUP"] = "1"
    if allow_tool_only_reply:
        headers["X-Allow-Tool-Only-Reply"] = "1"
    if skip_qq_group_activity:
        headers["X-Skip-QQ-Group-Activity"] = "1"
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    try:
        r = requests.post(url, headers=headers, json=body, timeout=STREAM_TIMEOUT_SECONDS)
        if r.status_code != 200:
            logger.warning("后端事件唤醒调用网关失败 status=%s body=%s", r.status_code, (r.text or "")[:300])
            return {"ok": False, "error": f"gateway_http_{r.status_code}"}
        data = r.json() if r.content else {}
        msg = (((data or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        if isinstance(msg, dict) and bool(msg.get("tool_only_reply_done")):
            return {
                "ok": True,
                "channel": "",
                "attempted_channels": [],
                "preferred_channel": preferred_channel,
                "preferred_channel_at": str(preferred_meta.get("at") or ""),
                "locked_channel": bool(lock_preferred_channel),
                "tool_only": True,
                "archive_ok": True,
                "reply_preview": str(msg.get("content") or "")[:120],
                "error": "",
            }
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
        available_channels: list[str] = []
        if not lock_preferred_channel:
            from services.telegram_proactive import _available_channels

            available_channels = _available_channels()
        channels = _choice_dialog_delivery_channels(preferred_channel, available_channels, preferred_target)
        if not channels:
            return {"ok": False, "error": "no_proactive_channel", "reply_preview": text[:120]}
        outbound = _sanitize_reply_for_telegram(text).strip()
        try:
            from services.telegram_proactive import _sanitize_control_reply_for_delivery

            outbound = _sanitize_control_reply_for_delivery(outbound).strip()
        except Exception:
            outbound = str(outbound or "").strip()
        if not outbound:
            return {"ok": False, "error": "empty_after_sanitize"}
        attempted_channels = []
        for channel in channels:
            attempted_channels.append(channel)
            send_target = preferred_target if channel == preferred_channel else str(target or "").strip()
            if _dispatch_choice_dialog_reply(channel, send_target, outbound, created_at=created_at):
                archive_ok = True
                if archive and archive_after_delivery:
                    archive_ok = _archive_wakeup_after_delivery(
                        window_id=context_window_id,
                        request_messages=body.get("messages") or [],
                        assistant_text=outbound,
                        wakeup_kind=kind,
                        reply_channel=channel,
                    )
                spring_archive: dict = {}
                if kind in {"spring_dream", "random_spring_dream"}:
                    try:
                        from services.spring_dream import archive_spring_dream_body

                        spring_archive = archive_spring_dream_body(
                            window_id=context_window_id,
                            target=send_target,
                            channel=channel,
                            content=outbound,
                            prompt=prompt,
                            created_at=created_at or "",
                            sent_at=now_beijing_iso(),
                            meta=spring_dream_archive_meta if isinstance(spring_dream_archive_meta, dict) else {},
                        )
                        if not bool(spring_archive.get("ok")):
                            logger.warning(
                                "春梦专用存档失败 window_id=%s channel=%s archive=%s",
                                context_window_id,
                                channel,
                                spring_archive,
                            )
                    except Exception:
                        spring_archive = {"ok": False, "error": "exception"}
                        logger.warning("春梦专用存档异常 window_id=%s channel=%s", context_window_id, channel, exc_info=True)
                if post_spring_prompt_override:
                    try:
                        from services.spring_dream import record_post_spring_dream_wakeup_sent

                        record_post_spring_dream_wakeup_sent(post_spring_prompt_override, sent_at=now_beijing_iso())
                    except Exception:
                        logger.warning("post_spring_dream prompt override clear failed window_id=%s", context_window_id, exc_info=True)
                return {
                    "ok": True,
                    "channel": channel,
                    "attempted_channels": attempted_channels,
                    "preferred_channel": preferred_channel,
                    "preferred_channel_at": str(preferred_meta.get("at") or ""),
                    "locked_channel": bool(lock_preferred_channel),
                    "archive_ok": bool(archive_ok),
                    "spring_dream_archive_ok": bool(spring_archive.get("ok")) if spring_archive else True,
                    "spring_dream_archive_id": str(spring_archive.get("id") or "") if spring_archive else "",
                    "spring_dream_archive_r2_key": str(spring_archive.get("r2_key") or "") if spring_archive else "",
                    "reply_preview": outbound[:120],
                    "error": "",
                }
        return {
            "ok": False,
            "channel": attempted_channels[-1] if attempted_channels else "",
            "attempted_channels": attempted_channels,
            "preferred_channel": preferred_channel,
            "preferred_channel_at": str(preferred_meta.get("at") or ""),
            "locked_channel": bool(lock_preferred_channel),
            "reply_preview": outbound[:120],
            "error": "dispatch_failed",
        }
    except Exception as e:
        logger.warning("后端事件唤醒异常", exc_info=True)
        return {"ok": False, "error": str(e)}


def send_choice_dialog_wakeup(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    preferred_channel: str = "",
    preferred_meta: dict | None = None,
) -> dict:
    """立即让渡基于 SumiTalk 弹窗回执生成回应，并通过主动消息入口发出。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        extra_instruction=(
            "请你现在直接对她回应一两句。不要解释工具、回执或系统流程。"
        ),
        wakeup_kind="choice_dialog",
        preferred_channel_override=preferred_channel,
        preferred_target_override=target,
        preferred_meta_override=preferred_meta,
        lock_preferred_channel=bool(preferred_channel),
    )


def send_private_draw_wakeup(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    preferred_channel: str = "",
    preferred_meta: dict | None = None,
) -> dict:
    """立即让渡基于小玥发来的 sex play 抽签结果生成回应，并投递到最近聊天入口。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        archive=True,
        extra_instruction=(
            "这是小玥发来的 sex play 抽签结果。请按最近聊天入口的语气自然接一两句；"
            "不要代替小玥说话，不要写开场白，不要写旁白，不要扩成角色扮演剧情，也不要解释工具或系统流程。"
        ),
        wakeup_kind="private_draw",
        system_event=True,
        preferred_channel_override=preferred_channel,
        preferred_target_override=target,
        preferred_meta_override=preferred_meta,
        lock_preferred_channel=bool(preferred_channel),
    )


def send_exchange_diary_comment_wakeup(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    preferred_channel: str = "",
    preferred_meta: dict | None = None,
) -> dict:
    """立即让渡看到小玥的新日记评论，并自己决定回评论或直接发消息。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        archive=True,
        extra_instruction=(
            "这是小玥刚刚写在交换日记下面的评论，不是聊天框正文。"
            "请你自己决定：如果想回在日记下面，就调用 exchange_diary_comment_create 回复这条评论，"
            "调用工具后不要再额外输出聊天正文；如果想直接找她说话，就不要调用工具，"
            "直接写要发给她的一两句话。不要解释工具或系统流程。"
        ),
        wakeup_kind="exchange_diary_comment",
        system_event=True,
        system_event_user_summary=event_text,
        preferred_channel_override=preferred_channel,
        preferred_target_override=target,
        preferred_meta_override=preferred_meta,
        lock_preferred_channel=bool(preferred_channel),
        allow_followup=False,
        allow_tool_only_reply=True,
        skip_qq_group_activity=True,
    )


def send_pixel_home_wakeup(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    preferred_channel: str = "",
    preferred_meta: dict | None = None,
) -> dict:
    """立即让渡基于小家事件生成回应，并沿用最近真实聊天入口。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        archive=True,
        extra_instruction=(
            "这是小家里的状态或道具事件，不是她在聊天框里说的话。"
            "请沿用最近真实聊天入口的语气自然回应一两句，不要解释工具或系统流程。"
        ),
        wakeup_kind="pixel_home",
        system_event=True,
        preferred_channel_override=preferred_channel,
        preferred_target_override=target,
        preferred_meta_override=preferred_meta,
        lock_preferred_channel=bool(preferred_channel),
    )


def send_screen_check_wakeup(
    window_id: str,
    target: str,
    event_text: str,
    image_url: str,
    created_at: str | None = None,
    preferred_channel: str = "",
    preferred_meta: dict | None = None,
) -> dict:
    """立即让渡看一张经老婆同意的手机截图，再自然回应。"""
    has_image = bool(str(image_url or "").strip())
    instruction = (
        "请你看图后自然回应一两句。不要解释工具、回执或系统流程；"
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
        wakeup_kind="screen_check",
        preferred_channel_override=preferred_channel,
        preferred_target_override=target,
        preferred_meta_override=preferred_meta,
        lock_preferred_channel=bool(preferred_channel),
    )


def send_proactive_trigger_wakeup(window_id: str, target: str, event_text: str, created_at: str | None = None) -> dict:
    """立即让渡基于后端主动触发事实生成回应。event_text 只放事实，不追加回应指令。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        archive=True,
        stable_proactive_channel=True,
        wakeup_kind="proactive_trigger",
    )


def send_spring_dream_wakeup(
    window_id: str,
    target: str,
    event_text: str,
    created_at: str | None = None,
    archive_meta: dict | None = None,
) -> dict:
    """睡眠期随机唤醒命中春梦时，让渡基于梦境触发自然生成一条外发。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        archive=True,
        stable_proactive_channel=True,
        wakeup_kind="spring_dream",
        system_event=True,
        allow_followup=False,
        archive_after_delivery=True,
        spring_dream_archive_meta=archive_meta,
        extra_instruction=(
            "这是睡眠期随机唤醒触发的一段春梦，不是小玥在聊天框里发来的消息。"
            "请直接以你梦醒后对小玥说话的口吻自然发出；不要解释系统流程，不要输出 JSON 或工具说明。"
        ),
    )


def send_post_spring_dream_wakeup(window_id: str, target: str, event_text: str, created_at: str | None = None) -> dict:
    """睡眠期随机唤醒在春梦后一轮使用本地自定义 prompt replacement。"""
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=event_text,
        created_at=created_at,
        archive=True,
        stable_proactive_channel=True,
        wakeup_kind="post_spring_dream",
        system_event=True,
        allow_followup=False,
        archive_after_delivery=True,
        extra_instruction=(
            "这是睡眠期随机唤醒在上一轮春梦后的延续触发，不是小玥在聊天框里发来的消息。"
            "请直接以你此刻对小玥说话的口吻自然发出；不要解释系统流程，不要输出 JSON 或工具说明。"
        ),
    )


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
            if _normalize_reply_channel(str(item.get("reply_channel") or "sumitalk"), default="sumitalk", allow_tg=True) == "sumitalk":
                try:
                    from services.sumitalk_block_mode import maybe_auto_reply_after_sumitalk_assistant

                    maybe_auto_reply_after_sumitalk_assistant(
                        incoming_message_id=f"followup-{str(item.get('chain_id') or '').strip()}-{int(item.get('followup_index') or 1)}",
                        created_at=now_beijing_iso(),
                    )
                except Exception as e:
                    sumitalk_logger.warning("block_mode_followup_auto_reply_failed chain_id=%s error=%s", item.get("chain_id"), e)
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
