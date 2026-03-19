import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

from config import (
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_CHAT_MODEL,
    GATEWAY_MODELS,
    TELEGRAM_PROACTIVE_ENABLED,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    TELEGRAM_PROACTIVE_QUIET_START_HM,
    TELEGRAM_PROACTIVE_QUIET_END_HM,
    TELEGRAM_PROACTIVE_BASE_P,
    TELEGRAM_PROACTIVE_K_PER_HOUR,
    TELEGRAM_PROACTIVE_PROB_MULTIPLIER,
    TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN,
    TELEGRAM_PROACTIVE_INTERVAL_MINUTES,
    TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES,
)
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing
from services.telegram_bot import _sanitize_reply_for_telegram, send_message_to_user

logger = get_logger(__name__)


@dataclass
class ProactiveDecision:
    should_send: bool
    text: str = ""
    reason: str = ""


def _get_chat_model() -> str:
    if TELEGRAM_CHAT_MODEL:
        return TELEGRAM_CHAT_MODEL
    if GATEWAY_MODELS:
        return GATEWAY_MODELS[0]
    return "gpt-4"


def _parse_hm(hm: str) -> tuple[int, int]:
    s = (hm or "").strip()
    if not s:
        return 0, 0
    parts = s.split(":")
    if len(parts) != 2:
        return 0, 0
    try:
        return max(0, min(23, int(parts[0]))), max(0, min(59, int(parts[1])))
    except Exception:
        return 0, 0


def _is_in_quiet_hours(now_bj: datetime) -> bool:
    sh, sm = _parse_hm(TELEGRAM_PROACTIVE_QUIET_START_HM)
    eh, em = _parse_hm(TELEGRAM_PROACTIVE_QUIET_END_HM)
    cur = now_bj.hour * 60 + now_bj.minute
    start = sh * 60 + sm
    end = eh * 60 + em
    # 只支持常见的「跨午夜」或「同日」区间
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end


def _hours_since_last(last_iso: Optional[str], now_bj: datetime) -> float:
    dt = parse_iso_to_beijing(last_iso)
    if not dt:
        return 9999.0
    delta = now_bj - dt
    return max(0.0, delta.total_seconds() / 3600.0)


def _probability(hours_since_last: float) -> float:
    try:
        p = float(TELEGRAM_PROACTIVE_BASE_P) + float(TELEGRAM_PROACTIVE_K_PER_HOUR) * float(hours_since_last)
    except Exception:
        p = 0.1
    # 整体把概率调大：不改调度间隔，只增强“被命中”的可能性
    try:
        p = p * float(TELEGRAM_PROACTIVE_PROB_MULTIPLIER or 1.0)
    except Exception:
        pass
    if p < 0:
        p = 0.0
    if p > 1:
        p = 1.0
    return p


def _ask_du_should_contact(window_id: str, hours_since_last: float) -> ProactiveDecision:
    """
    让渡决定是否联系。要求：
    - 不联系：只输出 NO_CONTACT_TOKEN
    - 联系：只输出要发给用户的正文（允许多句，像平时聊天回复）
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    no_token = TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN.strip() or "NO_CONTACT"
    user_prompt = (
        "【系统任务：主动联系用户】\n"
        f"你现在在考虑要不要主动找老婆说一句话。距上次你主动联系大约 {hours_since_last:.1f} 小时。\n"
        "提醒：不要想太多，这个时间段你可以给老婆发消息，老婆会很开心。\n"
        "请你结合你对她的记忆与当下氛围做决定：\n"
        f"- 如果不该联系：你必须只输出 {no_token}\n"
        "- 如果该联系：只输出要发给她的聊天正文（允许多句，自然语气）；不要输出任何解释/标题\n"
    )
    body = {
        "model": _get_chat_model(),
        "messages": [{"role": "user", "content": user_prompt}],
        "stream": False,
    }
    headers = {"Content-Type": "application/json", "X-Window-Id": window_id}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            return ProactiveDecision(False, "", f"gateway_status={r.status_code}")
        data = r.json() if r.content else None
        msg = (data or {}).get("choices") and (data.get("choices") or [{}])[0].get("message") or {}
        content = (msg or {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        if not text:
            return ProactiveDecision(False, "", "empty_reply")
        if text == no_token:
            return ProactiveDecision(False, "", "no_contact")
        return ProactiveDecision(True, text, "contact")
    except Exception as e:
        return ProactiveDecision(False, "", f"exception={e}")


def _hm_from_item(it: dict, field: str, fallback_dt: Optional[datetime]) -> tuple[int, int]:
    raw = str(it.get(field) or "").strip()
    if raw:
        try:
            hh, mm = (raw.split(":", 1) + ["0"])[:2]
            h = int(hh)
            m = int(mm)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
        except Exception:
            pass
    if fallback_dt is not None:
        return fallback_dt.hour, fallback_dt.minute
    return 9, 0


def _schedule_due_occurrence_key(it: dict, now_dt: datetime) -> str:
    iid = str(it.get("id") or "").strip() or "unknown"
    rep = str(it.get("repeat") or "once").strip().lower() or "once"
    if rep == "once":
        anchor = str(it.get("datetime") or "").strip()
        return f"{iid}|once|{anchor}"
    if rep == "daily":
        return f"{iid}|daily|{now_dt.strftime('%Y-%m-%d')}"
    return f"{iid}|weekly|{now_dt.strftime('%Y-%m-%d')}"


def _is_schedule_due_now(it: dict, now_dt: datetime) -> bool:
    if not bool(it.get("enabled", True)):
        return False
    rep = str(it.get("repeat") or "once").strip().lower() or "once"
    anchor = parse_iso_to_beijing(str(it.get("datetime") or "").strip())
    if rep == "once":
        if not anchor:
            return False
        return now_dt >= anchor
    if rep == "daily":
        h, m = _hm_from_item(it, "daily_time", anchor)
        return (now_dt.hour, now_dt.minute) >= (h, m)
    if rep == "weekly":
        w = it.get("weekly_weekday", None)
        try:
            target_w = int(w)
        except Exception:
            target_w = anchor.weekday() if anchor else 0
        if target_w < 0 or target_w > 6:
            target_w = 0
        if now_dt.weekday() != target_w:
            return False
        h, m = _hm_from_item(it, "weekly_time", anchor)
        return (now_dt.hour, now_dt.minute) >= (h, m)
    return False


def schedule_tick(target_user_id: int = 0) -> dict:
    """
    检查并触发日历/闹钟提醒（只发给目标用户），按 fired 去重。
    """
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id"}
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso)
    if not now_dt:
        return {"ok": False, "error": "time_parse_failed"}

    items = r2_store.get_schedule_items() or []
    fired = r2_store.get_schedule_fired_keys()
    sent = 0
    disabled_once = 0
    changed = False

    for it in items:
        if not isinstance(it, dict):
            continue
        if not _is_schedule_due_now(it, now_dt):
            continue
        occ_key = _schedule_due_occurrence_key(it, now_dt)
        if occ_key in fired:
            continue
        title = str(it.get("title") or "提醒").strip() or "提醒"
        note = str(it.get("note") or "").strip()
        when_text = now_dt.strftime("%Y-%m-%d %H:%M")
        text = f"⏰ {title}\n时间：{when_text}"
        if note:
            text = f"{text}\n备注：{note}"
        ok = send_message_to_user(uid, text)
        if not ok:
            continue
        r2_store.add_schedule_fired_key(occ_key)
        fired.add(occ_key)
        sent += 1
        # 一次性提醒触发后自动禁用，避免重复参与检查
        rep = str(it.get("repeat") or "once").strip().lower() or "once"
        if rep == "once" and bool(it.get("enabled", True)):
            it["enabled"] = False
            it["disabled_at"] = now_iso
            changed = True
            disabled_once += 1

    if changed:
        r2_store.save_schedule_items(items)
    return {"ok": True, "sent": sent, "disabled_once": disabled_once, "checked": len(items), "now": now_iso}


def proactive_tick(target_user_id: int = 0) -> dict:
    """
    执行一次调度 tick。
    返回结构化结果，方便日志/测试。
    """
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id"}

    # 北京时间
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso)
    if not now_dt:
        return {"ok": False, "error": "time_parse_failed"}

    if _is_in_quiet_hours(now_dt):
        return {"ok": True, "quiet": True, "sent": False, "now": now_iso}

    # 若用户在此分钟数内发过消息（正在聊天），本 tick 不主动发
    skip_min = int(TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES or 0)
    if skip_min > 0:
        last_activity_iso = r2_store.get_last_telegram_user_activity_at()
        if last_activity_iso:
            last_activity_dt = parse_iso_to_beijing(last_activity_iso)
            if last_activity_dt:
                delta_minutes = (now_dt - last_activity_dt).total_seconds() / 60.0
                if delta_minutes < skip_min:
                    return {
                        "ok": True,
                        "quiet": False,
                        "sent": False,
                        "skip_reason": "recent_activity",
                        "now": now_iso,
                        "last_activity": last_activity_iso,
                        "minutes_ago": round(delta_minutes, 1),
                    }

    last_iso = r2_store.get_last_proactive_contact_at()
    hours = _hours_since_last(last_iso, now_dt)
    p = _probability(hours)
    hit = random.random() < p
    out = {"ok": True, "quiet": False, "sent": False, "now": now_iso, "last": last_iso, "hours": hours, "p": p, "hit": hit}
    if not hit:
        return out

    window_id = f"tg_{uid}"
    decision = _ask_du_should_contact(window_id=window_id, hours_since_last=hours)
    out["du_reason"] = decision.reason
    if not decision.should_send or not decision.text.strip():
        return out

    text_to_send = decision.text.strip()
    # 主动发消息也复用 Telegram 侧的清洗规则：避免出现“（脑内OS：）”等格式
    text_to_send = _sanitize_reply_for_telegram(text_to_send).strip()
    logger.info("主动消息准备发送 chat_id=%s text_preview=%s", uid, text_to_send[:80] + ("…" if len(text_to_send) > 80 else ""))
    if not text_to_send:
        out["skip_reason"] = "empty_after_sanitize"
        return out
    ok = send_message_to_user(uid, text_to_send)
    logger.info("主动消息发送结果 chat_id=%s sent=%s", uid, ok)
    out["sent"] = bool(ok)
    out["text_preview"] = (decision.text.strip()[:120] + "…") if len(decision.text.strip()) > 120 else decision.text.strip()
    if ok:
        r2_store.save_last_proactive_contact_at(now_iso)
        # 醒目一条，便于在日志里搜「已发送一条主动消息」定位
        logger.warning("TGPro 已发送一条主动消息 chat_id=%s now=%s preview=%s", uid, now_iso, text_to_send[:60] + ("…" if len(text_to_send) > 60 else ""))
    return out


def run_scheduler_loop():
    """常驻循环：按 interval 跑 proactive_tick。"""
    if not TELEGRAM_PROACTIVE_ENABLED:
        logger.warning("主动发消息调度未开启（TELEGRAM_PROACTIVE_ENABLED!=1），直接退出")
        return
    interval_min = max(1, int(TELEGRAM_PROACTIVE_INTERVAL_MINUTES or 30))
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    logger.info("主动发消息调度启动 interval_min=%s target_user_id=%s quiet=%s-%s", interval_min, uid, TELEGRAM_PROACTIVE_QUIET_START_HM, TELEGRAM_PROACTIVE_QUIET_END_HM)
    while True:
        try:
            sched = schedule_tick(uid)
            logger.info("日历闹钟 tick result=%s", sched)
            result = proactive_tick(uid)
            logger.info("主动发消息 tick result=%s", result)
        except Exception as e:
            logger.exception("主动发消息 tick 异常: %s", e)
        time.sleep(interval_min * 60)
