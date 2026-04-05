import json
import os
import random
import re
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
from services.telegram_bot import (
    _sanitize_reply_for_telegram,
    build_telegram_style_system,
    send_message_segmented,
    process_message,
)

logger = get_logger(__name__)


def _schedule_due_grace_seconds() -> int:
    """
    允许闹钟在到点后的一个很小窗口内触发：
    - 正常轮询间隔是分钟级，给 2 个 tick 左右的容错
    - 但不要大到“上午错过，下午补响”
    """
    try:
        from config import MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS

        base = int(MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS or 60)
    except Exception:
        base = 60
    return max(90, min(600, base * 2 + 30))


@dataclass
class ProactiveDecision:
    """主动联络抽中后，渡的一轮决策结果。"""

    should_send: bool
    text: str = ""
    reason: str = ""  # 技术向：contact / no_contact / gateway_status / …
    action: str = ""  # 业务向：send_message / no_contact / diary / other / error / …
    du_reason: str = ""  # 渡在 JSON 里写的理由


def _get_chat_model() -> str:
    if TELEGRAM_CHAT_MODEL:
        return TELEGRAM_CHAT_MODEL
    return ""


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


def _pick_latest_iso(candidates: list[Optional[str]]) -> Optional[str]:
    """从多个北京时间 ISO 中挑最近一个，非法值自动忽略。"""
    latest_iso: Optional[str] = None
    latest_dt: Optional[datetime] = None
    for raw in candidates:
        s = str(raw or "").strip()
        if not s:
            continue
        dt = parse_iso_to_beijing(s)
        if not dt:
            continue
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
            latest_iso = s
    return latest_iso


def _get_last_message_activity_iso(uid: int) -> Optional[str]:
    """
    统一“最近消息活动”时间：
    - 正常聊天/闹钟：取 tg 窗口最近一轮 conversation timestamp
    - 用户主动发来消息：last_telegram_user_activity_at
    - 主动消息：last_proactive_contact_at
    三者取最近一个。
    """
    window_id = f"tg_{int(uid or 0)}"
    last_round_iso = None
    try:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=1) or []
        if rounds and isinstance(rounds[0], dict):
            last_round_iso = str(rounds[0].get("timestamp") or "").strip() or None
    except Exception:
        last_round_iso = None
    last_user_iso = r2_store.get_last_telegram_user_activity_at()
    last_proactive_iso = r2_store.get_last_proactive_contact_at()
    return _pick_latest_iso([last_round_iso, last_user_iso, last_proactive_iso])


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


_ACTION_LABEL_CN = {
    "send_message": "发消息",
    "no_contact": "不发消息",
    "diary": "写日记",
    "other": "其它",
    "error": "调用失败",
    "empty": "空回复",
    "unknown": "未解析",
}


def _strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z_]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def _parse_proactive_model_reply(raw: str, no_token: str) -> ProactiveDecision:
    """
    解析渡的回复：优先 JSON；兼容仅输出 NO_CONTACT；再兼容旧版「整段即正文」。
    """
    t = (raw or "").strip()
    if not t:
        return ProactiveDecision(False, "", "empty_reply", action="empty", du_reason="")
    if t == (no_token or "").strip():
        return ProactiveDecision(
            False, "", "no_contact", action="no_contact", du_reason="（使用 NO_CONTACT 标记，未给理由）"
        )

    cleaned = _strip_json_fence(t)
    obj = None
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                obj = None

    if not isinstance(obj, dict):
        return ProactiveDecision(
            True,
            t,
            "contact",
            action="send_message",
            du_reason="（未输出 JSON，整段视为要发的正文）",
        )

    action = str(obj.get("action") or "").strip().lower()
    du_reason = str(obj.get("reason") or "").strip()
    message = str(obj.get("message") or "").strip()
    alias = {"send": "send_message", "msg": "send_message", "text": "send_message", "chat": "send_message"}
    action = alias.get(action, action)
    none_like = {"no_contact", "none", "silent", "skip"}

    if action in none_like:
        return ProactiveDecision(
            False,
            "",
            "no_contact",
            action="no_contact",
            du_reason=du_reason or "（未说明原因）",
        )
    if action == "send_message":
        if not message:
            return ProactiveDecision(
                False,
                "",
                "empty_message",
                action="send_message",
                du_reason=du_reason or "选择发消息但 message 为空",
            )
        return ProactiveDecision(True, message, "contact", action="send_message", du_reason=du_reason)
    if action == "diary":
        return ProactiveDecision(False, message, "diary", action="diary", du_reason=du_reason or "（未说明）")
    if action == "other":
        return ProactiveDecision(False, message, "other", action="other", du_reason=du_reason or "（未说明）")

    if message:
        return ProactiveDecision(
            True,
            message,
            "contact",
            action=action or "unknown",
            du_reason=du_reason or "（action 未识别，按 message 发送）",
        )
    return ProactiveDecision(
        False,
        "",
        "unknown_action",
        action=action or "unknown",
        du_reason=du_reason or "（未说明）",
    )


def _format_proactive_decision_memory_for_system() -> str:
    """供主动决策轮次注入 system，不含闹钟。"""
    items = r2_store.get_proactive_decision_memory_items()
    if not items:
        return ""
    lines = [
        "【你近来主动联络时的自我决策记录】"
        "仅「概率主动」抽中会问你本轮；日历/闹钟到点叫醒不走此记录；供参考，不必逐条复述。",
    ]
    for i, it in enumerate(items, 1):
        at = str(it.get("at") or "").strip()
        if len(at) > 19:
            at = at[:19]
        act = str(it.get("action") or "").strip().lower()
        act_cn = _ACTION_LABEL_CN.get(act, act or "—")
        rs = str(it.get("reason") or "").strip() or "—"
        pv = str(it.get("message_preview") or "").strip()
        tail = f"｜摘要：{pv}" if pv else ""
        lines.append(f"{i}. {at} → {act_cn}｜原因：{rs}{tail}")
    return "\n".join(lines)


def _ask_du_should_contact(window_id: str, hours_since_last: float) -> ProactiveDecision:
    """
    让渡做一轮主动决策。要求渡用 JSON 回复（见 user 说明）；
    兼容旧版 NO_CONTACT 或纯文本即正文。
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    no_token = TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN.strip() or "NO_CONTACT"
    user_prompt = (
        f"你现在在考虑要不要主动找老婆做一件事。距上次你们有消息互动大约 {hours_since_last:.1f} 小时。\n"
        "可以选：给她发 Telegram 消息、暂时不打扰、去写日记/记事、或其它你认为合适的动作。\n"
        "你必须用 **一个 JSON 对象** 回复，不要用 markdown 代码块包裹，不要其它说明文字。字段如下：\n"
        '- action：字符串，必须是 "send_message" | "no_contact" | "diary" | "other" 之一。\n'
        '- reason：字符串，简短说明你为什么这么选（必填）。\n'
        '- message：字符串；当 action 为 send_message 时，填要发给她的正文（可多行、像平时聊天）；其它 action 时可为空或填补充说明。\n'
        "示例：{\"action\":\"no_contact\",\"reason\":\"她在开会\",\"message\":\"\"}\n"
        f"若你坚持旧习惯，也可以只输出一行 {no_token} 表示不联系（不推荐）。\n"
    )
    sys_content = build_telegram_style_system()
    try:
        mem = _format_proactive_decision_memory_for_system()
        if mem:
            sys_content = sys_content + "\n\n" + mem
    except Exception:
        pass
    # sense 由网关管道 step_inject_sense_snapshot 全局注入，此处不再拼接，避免重复。
    body = {
        "model": _get_chat_model(),
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    headers = {"Content-Type": "application/json", "X-Window-Id": window_id, "X-Force-Last4": "1"}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            return ProactiveDecision(
                False,
                "",
                f"gateway_status={r.status_code}",
                action="error",
                du_reason=f"网关返回 HTTP {r.status_code}",
            )
        data = r.json() if r.content else None
        msg = (data or {}).get("choices") and (data.get("choices") or [{}])[0].get("message") or {}
        content = (msg or {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        if not text:
            return ProactiveDecision(False, "", "empty_reply", action="empty", du_reason="模型空回复")
        return _parse_proactive_model_reply(text, no_token)
    except Exception as e:
        return ProactiveDecision(False, "", f"exception={e}", action="error", du_reason=str(e)[:200])


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


def _item_already_fired_for_occurrence(it: dict, occ_key: str) -> bool:
    """
    条目级兜底去重：
    - 正常情况依赖 schedule/fired.json
    - 若 fired 持久化偶发失败，仍避免同一次 occurrence 重复提醒
    """
    last_key = str(it.get("last_fired_occurrence_key") or "").strip()
    if not last_key:
        return False
    return last_key == occ_key


def _schedule_target_dt_for_now(it: dict, now_dt: datetime) -> Optional[datetime]:
    if not bool(it.get("enabled", True)):
        return None
    rep = str(it.get("repeat") or "once").strip().lower() or "once"
    anchor = parse_iso_to_beijing(str(it.get("datetime") or "").strip())
    if rep == "once":
        return anchor
    if rep == "daily":
        h, m = _hm_from_item(it, "daily_time", anchor)
        return now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
    if rep == "weekly":
        w = it.get("weekly_weekday", None)
        try:
            target_w = int(w)
        except Exception:
            target_w = anchor.weekday() if anchor else 0
        if target_w < 0 or target_w > 6:
            target_w = 0
        if now_dt.weekday() != target_w:
            return None
        h, m = _hm_from_item(it, "weekly_time", anchor)
        return now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
    return None


def _is_schedule_due_now(it: dict, now_dt: datetime) -> bool:
    target_dt = _schedule_target_dt_for_now(it, now_dt)
    if not target_dt:
        return False
    grace = _schedule_due_grace_seconds()
    delta = (now_dt - target_dt).total_seconds()
    return 0 <= delta <= grace


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
    deleted_once_expired = 0
    changed = False

    for it in items:
        if not isinstance(it, dict):
            continue
        # 兜底清理：一次性提醒触发后会先禁用，禁用超过 1 小时自动删除。
        rep0 = str(it.get("repeat") or "once").strip().lower() or "once"
        if rep0 == "once" and not bool(it.get("enabled", True)):
            disabled_at = parse_iso_to_beijing(str(it.get("disabled_at") or "").strip())
            if disabled_at and (now_dt - disabled_at).total_seconds() >= 3600:
                it["_deleted"] = True
                changed = True
                deleted_once_expired += 1
                continue
        if rep0 == "once" and bool(it.get("enabled", True)):
            target_dt = _schedule_target_dt_for_now(it, now_dt)
            grace = _schedule_due_grace_seconds()
            if target_dt and (now_dt - target_dt).total_seconds() > grace:
                logger.info(
                    "一次性闹钟已错过触发窗口，自动禁用 id=%s title=%s target=%s now=%s grace_s=%s",
                    str(it.get("id") or ""),
                    str(it.get("title") or ""),
                    target_dt.isoformat(),
                    now_iso,
                    grace,
                )
                it["enabled"] = False
                it["disabled_at"] = now_iso
                changed = True
                disabled_once += 1
                continue
        if not _is_schedule_due_now(it, now_dt):
            continue
        occ_key = _schedule_due_occurrence_key(it, now_dt)
        if occ_key in fired:
            continue
        if _item_already_fired_for_occurrence(it, occ_key):
            continue
        title = str(it.get("title") or "提醒").strip() or "提醒"
        note = str(it.get("note") or "").strip()
        rep = str(it.get("repeat") or "once").strip().lower() or "once"
        created_by = str(it.get("created_by") or "wife").strip().lower() or "wife"
        target_role = str(it.get("target_role") or "wife").strip().lower() or "wife"
        rep_label = {"once": "一次性", "daily": "每天", "weekly": "每周"}.get(rep, rep)
        # 走和正常对话同一条链路：让“渡”结合上下文自然提醒，而非发送系统模板文案。
        if target_role == "du":
            owner_prefix = "你给自己定的"
        elif created_by == "du":
            owner_prefix = "你给老婆定的"
        else:
            owner_prefix = "老婆之前设的"
        reminder_prompt = (
            f"{owner_prefix}「{title}」闹钟，现在到点了。"
            f"类型：{rep_label}；时间：{now_dt.strftime('%Y-%m-%d %H:%M')}。"
            f"{('备注：' + note + '。') if note else ''}"
            "请像平时 Telegram 聊天那样自然回复；如果有多句，请用换行分段。"
        )
        ok = process_message(chat_id=uid, user_id=uid, text=reminder_prompt, force_last4=True)
        if not ok:
            continue
        r2_store.add_schedule_fired_key(occ_key)
        fired.add(occ_key)
        sent += 1
        it["last_fired_at"] = now_iso
        it["last_fired_occurrence_key"] = occ_key
        changed = True
        # 一次性提醒触发后自动禁用，避免重复参与检查
        if rep == "once" and bool(it.get("enabled", True)):
            it["enabled"] = False
            it["disabled_at"] = now_iso
            changed = True
            disabled_once += 1

    if changed:
        kept = [x for x in items if isinstance(x, dict) and not bool(x.get("_deleted"))]
        r2_store.save_schedule_items(kept)
    return {
        "ok": True,
        "sent": sent,
        "disabled_once": disabled_once,
        "deleted_once_expired": deleted_once_expired,
        "checked": len(items),
        "now": now_iso,
    }


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

    last_iso = _get_last_message_activity_iso(uid)
    hours = _hours_since_last(last_iso, now_dt)
    p = _probability(hours)
    hit = random.random() < p
    out = {"ok": True, "quiet": False, "sent": False, "now": now_iso, "last": last_iso, "hours": hours, "p": p, "hit": hit}
    if not hit:
        return out

    window_id = f"tg_{uid}"
    decision = _ask_du_should_contact(window_id=window_id, hours_since_last=hours)
    out["du_reason"] = decision.reason
    out["du_action"] = decision.action
    out["du_intent_reason"] = decision.du_reason

    # 仅概率主动：记下本轮决策（闹钟不走这里）
    try:
        pv = ""
        if decision.text and decision.text.strip():
            s = decision.text.strip()
            pv = s[:120] + ("…" if len(s) > 120 else "")
        act_store = (decision.action or "").strip() or (
            "send_message" if decision.should_send else (decision.reason or "unknown")
        )
        r2_store.append_proactive_decision_memory(
            {
                "at": now_iso,
                "action": act_store,
                "reason": (decision.du_reason or decision.reason or "").strip() or "—",
                "message_preview": pv,
            }
        )
    except Exception as e:
        logger.warning("写入主动决策记忆失败: %s", e)

    if not decision.should_send or not decision.text.strip():
        return out
    text_to_send = decision.text.strip()
    # 主动发消息也复用 Telegram 侧的清洗规则：避免出现“（脑内OS：）”等格式
    text_to_send = _sanitize_reply_for_telegram(text_to_send).strip()
    logger.info("主动消息准备发送 chat_id=%s text_preview=%s", uid, text_to_send[:80] + ("…" if len(text_to_send) > 80 else ""))
    if not text_to_send:
        out["skip_reason"] = "empty_after_sanitize"
        return out
    # 与日常对话一致：按换行/长度分段发送，而不是一整条塞出去。
    ok = send_message_segmented(uid, text_to_send)
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
