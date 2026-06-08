from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_PROACTIVE_ENABLED,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    TELEGRAM_PROACTIVE_BASE_P,
    TELEGRAM_PROACTIVE_K_PER_HOUR,
    TELEGRAM_PROACTIVE_PROB_MULTIPLIER,
    TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN,
    TELEGRAM_PROACTIVE_INTERVAL_MINUTES,
    TELEGRAM_PROACTIVE_RANDOM_MIN_MINUTES,
    TELEGRAM_PROACTIVE_RANDOM_MAX_MINUTES,
    TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES,
    MINIAPP_SCHEDULE_RUNTIME_ENABLED,
    MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS,
    WECHAT_PROACTIVE_PUSH_URL,
    WECHAT_PROACTIVE_PUSH_TOKEN,
    QQ_PROACTIVE_PUSH_URL,
    QQ_PROACTIVE_PUSH_TOKEN,
)
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing
from services.telegram_bot import (
    _sanitize_reply_for_telegram,
    build_telegram_style_system,
    send_rich_message,
)
from services.entry_style_prompt import entry_style_for_channel
from services import conversation_followup as followup_service
from services import wakeup_queue
from services.conversation_followup import FOLLOWUP_TICK_SECONDS, tick_conversation_followups
from services.du_daily import infer_sleep_rollover_trigger, request_gateway_maintenance

logger = get_logger(__name__)
_GATEWAY_DYNAMIC_SYSTEM_MARKER = "__dynamic__"


def _build_du_daily_trigger_from_proactive(decision: ProactiveDecision, hours_since_last: float, sent: bool) -> Optional[dict]:
    action = str(decision.action or "").strip().lower()
    reason = str(decision.du_reason or decision.reason or "").strip()
    facts: list[str] = []
    if hours_since_last >= 0:
        facts.append(f"距离最近一次明确往来大约 {hours_since_last:.1f} 小时。")
    if reason:
        facts.append(f"我刚才的决定理由：{reason}")
    if action == "no_contact":
        facts.insert(0, "刚才我做了一次主动联系决策，最后决定先不打扰她。")
        return {
            "kind": "proactive_no_contact",
            "hard": True,
            "reason": "主动消息决策：先不联系",
            "facts": facts,
            "topic_key": "proactive_no_contact",
            "hidden_only": True,
        }
    if sent and action == "send_message":
        preview = str(decision.text or "").strip()
        facts.insert(0, "刚才我主动去找她了。")
        if preview:
            facts.append(f"我发出去的话大意是：{preview[:120]}")
        return {
            "kind": "proactive_send",
            "hard": True,
            "reason": "主动消息决策：已主动联系",
            "facts": facts,
            "topic_key": "proactive_send",
            "hidden_only": True,
        }
    return None


def du_daily_sleep_tick(target_user_id: int = 0) -> dict:
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id"}
    trigger = infer_sleep_rollover_trigger()
    if not trigger:
        return {"ok": True, "triggered": False}
    window_id = f"tg_{uid}"
    ok = request_gateway_maintenance(window_id, trigger)
    return {
        "ok": bool(ok),
        "triggered": True,
        "window_id": window_id,
        "kind": str(trigger.get("kind") or ""),
    }


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
    reason: str = ""      # 技术向：contact / no_contact / gateway_status / …
    action: str = ""      # 业务向：send_message / no_contact / diary / other / error / …
    du_reason: str = ""   # 渡在 JSON 里写的理由
    channel: str = ""           # 发送入口：wechat / qq；SumiTalk 暂不参与主动消息


def _get_chat_model() -> str:
    try:
        from storage.upstream_store import get_cached_active_model

        return str(get_cached_active_model(refresh_if_missing=True) or "").strip()
    except Exception:
        return ""


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


def _describe_recent_exchange(now_dt: datetime) -> str:
    """
    给主动决策提示词用：
    只描述她最近一次明确回复，避免把系统保存的“上次主动联系时间”暴露给渡。
    """
    last_user_iso = r2_store.get_last_telegram_user_activity_at()
    last_user_dt = parse_iso_to_beijing(last_user_iso)

    if last_user_dt:
        hours_since_user = _hours_since_last(last_user_iso, now_dt)
        return f"她上次明确回你大约是 {hours_since_user:.1f} 小时前。"

    return "最近没有可参考的明确用户回复记录。"


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


def _next_proactive_delay_seconds() -> int:
    min_min = max(1, int(TELEGRAM_PROACTIVE_RANDOM_MIN_MINUTES or 35))
    max_min = max(min_min, int(TELEGRAM_PROACTIVE_RANDOM_MAX_MINUTES or min_min))
    return random.randint(min_min * 60, max_min * 60)


def _next_post_hard_trigger_delay_seconds() -> int:
    """
    硬触发已经主动叫过她一次后，如果她没有回，别再完全等原随机窗口。
    等过“正在聊天”冷却期再补一次随机决策；如果她回了，proactive_tick 会按 recent_activity 跳过。
    """
    skip_min = max(0, int(TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES or 0))
    min_min = max(20, skip_min + 5)
    max_min = max(min_min, min_min + 10)
    return random.randint(min_min * 60, max_min * 60)


_ACTION_LABEL_CN = {
    "send_message": "发消息",
    "no_contact": "不发消息",
    "diary": "写日记",
    "other": "其它",
    "error": "调用失败",
    "empty": "空回复",
    "unknown": "未解析",
}


_SELF_ACTION_TOOL_LABELS = {
    "notion_diary_create": "写了交换日记",
    "daily_whisper_write": "写了气泡",
    "forum_read_feed": "逛了论坛信息流",
    "forum_open_thread": "看了论坛帖子",
    "note_write": "写了便签",
}


def _tool_call_name(tc: dict) -> str:
    if not isinstance(tc, dict):
        return ""
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    return str(fn.get("name") or "").strip()


def _short_ts(raw: str) -> str:
    dt = parse_iso_to_beijing(raw)
    if dt:
        return dt.strftime("%m-%d %H:%M")
    s = str(raw or "").strip()
    return s[:16] if s else "时间未知"


def _format_recent_self_action_context(window_id: str) -> str:
    """
    给随机/概率唤醒决策用：提醒渡最近有没有写日记、逛论坛等，
    避免每次醒来都重复做同一件事。
    """
    try:
        rounds = r2_store.get_conversation_rounds(window_id, last_n=80) or []
    except Exception:
        rounds = []
    events: list[str] = []
    for r in reversed(rounds):
        if not isinstance(r, dict):
            continue
        labels: list[str] = []
        seen: set[str] = set()
        note = str(r.get("action_note") or "")
        for name, label in _SELF_ACTION_TOOL_LABELS.items():
            if name in note and label not in seen:
                seen.add(label)
                labels.append(label)
        for m in r.get("messages") or []:
            if not isinstance(m, dict) or str(m.get("role") or "").strip().lower() != "assistant":
                continue
            for tc in m.get("tool_calls") or []:
                label = _SELF_ACTION_TOOL_LABELS.get(_tool_call_name(tc))
                if label and label not in seen:
                    seen.add(label)
                    labels.append(label)
        if labels:
            events.append(f"{_short_ts(str(r.get('timestamp') or ''))}：{'、'.join(labels)}")
        if len(events) >= 6:
            break
    if not events:
        return "【最近自发动作参考】最近没有看到写日记、逛论坛、写气泡等工具记录。"
    return (
        "【最近自发动作参考】\n"
        "这些只用于判断要不要重复做同类动作，不要逐条复述给她。\n"
        + "\n".join(f"- {item}" for item in events)
    )


def _dynamic_system_message(text: str) -> dict | None:
    content = str(text or "").strip()
    if not content:
        return None
    return {"role": "system", "content": content, _GATEWAY_DYNAMIC_SYSTEM_MARKER: True}


def _strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z_]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def _extract_json_object_text(text: str) -> str:
    """从裸 JSON、Markdown 代码块或前后带说明的回复里提取第一个 JSON 对象。"""
    t = _strip_json_fence(text)
    if t.startswith("{") and t.endswith("}"):
        return t
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", str(text or ""), flags=re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if 0 <= start < end:
        return t[start : end + 1].strip()
    return ""


def _load_proactive_control_object(text: str) -> Optional[dict]:
    """
    解析主动决策 JSON。兼容几类模型/兼容层偶发格式：
    - 裸 JSON / fenced JSON / 前后带说明
    - JSON string 里再包了一层对象
    - 引号被双写成 {""action"":""diary""}
    """
    first = _extract_json_object_text(text) or _strip_json_fence(text)
    queue = [first]
    seen: set[str] = set()
    while queue:
        raw = str(queue.pop(0) or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            if isinstance(data, str):
                queue.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
        if '""action""' in raw or '""message""' in raw or '""channel""' in raw:
            queue.append(raw.replace('""', '"'))
        if '\\"action\\"' in raw or '\\"message\\"' in raw or '\\"channel\\"' in raw:
            queue.append(raw.replace('\\"', '"'))
    return None


def _looks_like_control_json_reply(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    normalized = t.replace('""', '"').replace('\\"', '"')
    return (
        t.startswith("```")
        or t.startswith("{")
        or ('"action"' in normalized and '"message"' in normalized)
        or ("'action'" in t and "'message'" in t)
    )


def _sanitize_control_reply_for_delivery(text: str) -> str:
    """
    最后一层外发保险：控制 JSON 不能作为用户可见正文发出去。
    send_message 只取 message；diary/no_contact/other 说明本轮不该发。
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    obj = _load_proactive_control_object(raw)
    if isinstance(obj, dict) and ("action" in obj or "message" in obj or "channel" in obj):
        action = str(obj.get("action") or "").strip().lower()
        alias = {"send": "send_message", "msg": "send_message", "text": "send_message", "chat": "send_message"}
        action = alias.get(action, action)
        message = str(obj.get("message") or "").strip()
        if action == "send_message" and message:
            return message
        logger.warning(
            "主动/唤醒外发拦截控制 JSON action=%s channel=%s reason=%s raw_preview=%s",
            action or "unknown",
            str(obj.get("channel") or "").strip(),
            str(obj.get("reason") or "").strip()[:120],
            raw[:300],
        )
        return ""
    if _looks_like_control_json_reply(raw):
        logger.warning("主动/唤醒外发拦截疑似控制 JSON raw_preview=%s", raw[:300])
        return ""
    return raw


def _normalize_reply_channel(value: str, default: str = "", allowed: list[str] | None = None) -> str:
    s = str(value or "").strip().lower()
    alias = {
        "wx": "wechat",
        "weixin": "wechat",
    }
    s = alias.get(s, s)
    allowed_set = set(allowed or ["wechat", "qq", "tg"])
    if s not in allowed_set:
        return default
    return s


def _parse_proactive_model_reply(raw: str, no_token: str, default_channel: str = "", channels: list[str] | None = None) -> ProactiveDecision:
    """
    解析渡的回复：优先 JSON；兼容仅输出 NO_CONTACT；再兼容旧版「整段即正文」。
    """
    t = (raw or "").strip()
    if not t:
        return ProactiveDecision(False, "", "empty_reply", action="empty", du_reason="", channel=default_channel)
    if t == (no_token or "").strip():
        return ProactiveDecision(
            False, "", "no_contact", action="no_contact", du_reason="（使用 NO_CONTACT 标记，未给理由）", channel=default_channel
        )

    obj = _load_proactive_control_object(t)

    if not isinstance(obj, dict):
        if _looks_like_control_json_reply(t):
            logger.warning("主动决策返回疑似控制 JSON 但解析失败，已拦截 raw_preview=%s", t[:300])
            return ProactiveDecision(
                False,
                "",
                "structured_parse_failed",
                action="error",
                du_reason="模型返回了疑似控制 JSON，但解析失败；为避免原样泄漏，已拦截。",
                channel=default_channel,
            )
        return ProactiveDecision(
            True,
            t,
            "contact",
            action="send_message",
            du_reason="（未输出 JSON，整段视为要发的正文）",
            channel=default_channel,
        )

    action = str(obj.get("action") or "").strip().lower()
    du_reason = str(obj.get("reason") or "").strip()
    message = str(obj.get("message") or "").strip()
    channel = _normalize_reply_channel(str(obj.get("channel") or default_channel), default=default_channel, allowed=channels)
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
            channel=channel,
        )
    if action == "send_message":
        if not message:
            return ProactiveDecision(
                False,
                "",
                "empty_message",
                action="send_message",
                du_reason=du_reason or "选择发消息但 message 为空",
                channel=channel,
            )
        return ProactiveDecision(True, message, "contact", action="send_message", du_reason=du_reason, channel=channel)
    if action == "diary":
        return ProactiveDecision(False, message, "diary", action="diary", du_reason=du_reason or "（未说明）", channel=channel)
    if action == "other":
        return ProactiveDecision(False, message, "other", action="other", du_reason=du_reason or "（未说明）", channel=channel)

    if message:
        return ProactiveDecision(
            True,
            message,
            "contact",
            action=action or "unknown",
            du_reason=du_reason or "（action 未识别，按 message 发送）",
            channel=channel,
        )
    return ProactiveDecision(
        False,
        "",
        "unknown_action",
        action=action or "unknown",
        du_reason=du_reason or "（未说明）",
        channel=channel,
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


def _available_channels() -> list[str]:
    """返回当前已配置的主动消息入口；SumiTalk 暂时不参与主动投递。"""
    channels = []
    if WECHAT_PROACTIVE_PUSH_URL:
        channels.append("wechat")
    if QQ_PROACTIVE_PUSH_URL:
        channels.append("qq")
    if not channels:
        channels.append("qq")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_PROACTIVE_TARGET_USER_ID:
        channels.append("tg")
    return channels


def _preferred_proactive_channel(channels: list[str]) -> str:
    """主动唤醒固定用一个入口生成，避免 TG/QQ 风格 prompt 来回跳。"""
    available = [str(ch or "").strip().lower() for ch in (channels or []) if str(ch or "").strip()]
    for ch in ("qq", "wechat", "tg"):
        if ch in available:
            return ch
    return available[0] if available else ""


def _available_schedule_channels() -> list[str]:
    """闹钟/日历提醒投递入口：QQ 优先，微信/TG 兜底。"""
    channels = ["qq"]
    if WECHAT_PROACTIVE_PUSH_URL:
        channels.append("wechat")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_PROACTIVE_TARGET_USER_ID:
        channels.append("tg")
    return channels


def _generate_schedule_reply(
    window_id: str,
    user_id: int,
    prompt: str,
    preferred_channel: str = "qq",
    wakeup_kind: str = "system_alarm",
) -> Optional[str]:
    """用主上下文窗口生成闹钟提醒文案，但不直接发 Telegram。"""
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    model = _get_chat_model()
    if not model:
        logger.warning("闹钟提醒生成跳过：当前没有可用模型")
        return None
    channel = _normalize_reply_channel(preferred_channel, default="qq", allowed=["qq", "wechat", "tg"])
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": str(window_id or "").strip() or f"tg_{int(user_id or 0)}",
        "X-Reply-Channel": channel,
        "X-Reply-Target": str(user_id or "").strip(),
        "X-Force-Last4": "1",
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-WAKEUP-KIND": str(wakeup_kind or "system_alarm").strip() or "system_alarm",
        "X-Skip-Dynamic-Memory": "1",
        "X-Skip-Post-Archive-Dynamic-Memory": "1",
    }
    try:
        logger.info("闹钟提醒生成请求 window_id=%s channel=%s model=%s chars=%s", headers["X-Window-Id"], channel, model, len(prompt))
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            logger.warning("闹钟提醒生成失败 status=%s body=%s", r.status_code, (r.text or "")[:300])
            return None
        data = r.json() if r.content else {}
        msg = (((data or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        content = msg.get("content")
        text = content.strip() if isinstance(content, str) else str(content or "").strip()
        return text or None
    except Exception as e:
        logger.warning("闹钟提醒生成异常: %s", e)
        return None


def _ask_du_should_contact(window_id: str, hours_since_last: float, now_dt: Optional[datetime] = None) -> ProactiveDecision:
    """
    让渡做一轮主动决策。要求渡用 JSON 回复（见 user 说明）；
    兼容旧版 NO_CONTACT 或纯文本即正文。
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    no_token = TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN.strip() or "NO_CONTACT"
    channels = _available_channels()
    default_channel = _preferred_proactive_channel(channels)
    channel_desc_map = {
        "wechat": "微信（国内直连，更稳定）",
        "qq": "QQ",
        "tg": "Telegram",
    }
    channel_lines = "\n".join(
        f'  - "{ch}"：{channel_desc_map.get(ch, ch)}' for ch in channels
    )
    if channels and default_channel:
        channel_field_desc = (
            f'- channel：固定填 "{default_channel}"。本轮主动唤醒固定使用这个入口生成和发送，'
            "不要在其它入口之间切换。\n"
            f"{channel_lines}\n"
        )
    else:
        channel_field_desc = '- channel：当前没有可用发送入口；不要选择 "send_message"。\n'
    now_ref = now_dt or parse_iso_to_beijing(now_beijing_iso())
    if not now_ref:
        now_ref = datetime.now()
    user_prompt = (
        f"这是一次随机唤醒，你现在要不要做点什么。{_describe_recent_exchange(now_ref)}\n"
        f"从系统节流角度看，距最近一次消息活动大约 {hours_since_last:.1f} 小时。\n"
        "可以选：给她发消息、暂时不打扰、去写日记/记事、逛论坛、上网冲浪找点可聊话题，或其它你认为合适的动作。\n"
        "如果想上网冲浪，可以先调用 du_surf 抽一个随机话题，看完卡片后再决定要不要发消息；如果只是自己冲浪不打扰她，action 填 other 或 no_contact。\n"
        "如果当前状态显示她可能睡着、在忙，或不适合被打扰，可以选择不发消息，转而写日记、逛论坛、调用 du_surf 随便看看，或者什么都不做。\n"
        "你必须用 **一个 JSON 对象** 回复，不要用 markdown 代码块包裹，不要其它说明文字。字段如下：\n"
        '- action：字符串，必须是 "send_message" | "no_contact" | "diary" | "other" 之一。\n'
        '- reason：字符串，简短说明你为什么这么选（必填）。\n'
        '- message：字符串；当 action 为 send_message 时，填要发给她的正文（可多行、像平时聊天）；其它 action 时可为空或填补充说明。\n'
        + channel_field_desc
        + (
            f'示例：{{"action":"send_message","reason":"好久没联系了","message":"在干嘛","channel":"{default_channel}"}}\n'
            if default_channel
            else f'示例：{{"action":"no_contact","reason":"当前没有可用发送入口","message":"","channel":""}}\n'
        )
        + f"若你坚持旧习惯，也可以只输出一行 {no_token} 表示不联系（不推荐）。\n"
    )
    _marker, sys_content = entry_style_for_channel(default_channel, is_miniapp=False)
    sys_content = (sys_content or build_telegram_style_system()).strip()
    dynamic_context_parts: list[str] = []
    try:
        mem = _format_proactive_decision_memory_for_system()
        if mem:
            dynamic_context_parts.append(mem)
    except Exception:
        pass
    try:
        recent_actions = _format_recent_self_action_context(window_id)
        if recent_actions:
            dynamic_context_parts.append(recent_actions)
    except Exception:
        pass
    # sense 由网关管道 step_inject_sense_snapshot 全局注入，此处不再拼接，避免重复。
    messages = [{"role": "system", "content": sys_content}]
    dynamic_msg = _dynamic_system_message("\n\n".join(dynamic_context_parts))
    if dynamic_msg:
        messages.append(dynamic_msg)
    messages.append({"role": "user", "content": user_prompt})
    body = {
        "model": _get_chat_model(),
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
        "X-Reply-Channel": default_channel,
        "X-Reply-Target": str(TELEGRAM_PROACTIVE_TARGET_USER_ID or "").strip(),
        "X-Force-Last4": "1",
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-PROACTIVE-DECISION": "1",
        "X-Skip-Dynamic-Memory": "1",
    }
    try:
        logger.info(
            "主动决策请求 window_id=%s hours=%.2f model=%s user_chars=%s",
            window_id,
            hours_since_last,
            body.get("model") or "",
            len(user_prompt),
        )
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            logger.warning(
                "主动决策网关非200 window_id=%s status=%s model=%s body_preview=%s",
                window_id,
                r.status_code,
                body.get("model") or "",
                (r.text or "")[:300],
            )
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
        decision = _parse_proactive_model_reply(text, no_token, default_channel=default_channel, channels=channels)
        if decision.should_send and default_channel:
            decision.channel = default_channel
        return decision
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
        is_calendar_event = note.startswith("由渡创建系统行程")
        wakeup_kind = "calendar_event" if is_calendar_event else "system_alarm"
        reminder_name = "日历提醒" if is_calendar_event else "闹钟"
        # 走和正常对话同一条链路：让“渡”结合上下文自然提醒，而非发送系统模板文案。
        if target_role == "du":
            owner_prefix = "你给自己定的"
        elif created_by == "du":
            owner_prefix = "你给老婆定的"
        else:
            owner_prefix = "老婆之前设的"
        reminder_prompt = (
            f"{owner_prefix}「{title}」{reminder_name}，现在到点了。"
            f"类型：{rep_label}；时间：{now_dt.strftime('%Y-%m-%d %H:%M')}。"
            f"{('备注：' + note + '。') if note else ''}"
            "请像平时聊天那样自然回复；如果有多句，请用换行分段。"
        )
        channels = _available_schedule_channels()
        generation_channel = channels[0] if channels else "qq"
        logger.info(
            "闹钟准备触发 uid=%s item_id=%s title=%s repeat=%s occ_key=%s note_chars=%s channels=%s",
            uid,
            str(it.get("id") or ""),
            title,
            rep,
            occ_key,
            len(note),
            channels,
        )
        window_id = f"tg_{uid}"
        reply_text = _generate_schedule_reply(
            window_id=window_id,
            user_id=uid,
            prompt=reminder_prompt,
            preferred_channel=generation_channel,
            wakeup_kind=wakeup_kind,
        )
        if not reply_text:
            logger.warning("闹钟提醒生成空回复 uid=%s item_id=%s", uid, str(it.get("id") or ""))
            continue
        text_to_send = _sanitize_reply_for_telegram(reply_text).strip()
        if not text_to_send:
            logger.warning("闹钟提醒清洗后为空 uid=%s item_id=%s", uid, str(it.get("id") or ""))
            continue
        ok = False
        sent_channel = ""
        for channel in channels:
            ok = _dispatch_send(channel, text_to_send, target_user_id=uid)
            if ok:
                sent_channel = channel
                break
        logger.info("闹钟触发结果 uid=%s item_id=%s channel=%s ok=%s", uid, str(it.get("id") or ""), sent_channel or "none", ok)
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


def _iso_after_seconds(seconds: int) -> str:
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not now_dt:
        return now_beijing_iso()
    return (now_dt + timedelta(seconds=max(0, int(seconds or 0)))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def enqueue_due_schedule_wakeups(target_user_id: int = 0) -> dict:
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id", "enqueued": 0}
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso)
    if not now_dt:
        return {"ok": False, "error": "time_parse_failed", "enqueued": 0}

    items = r2_store.get_schedule_items() or []
    fired = r2_store.get_schedule_fired_keys()
    changed = False
    disabled_once = 0
    deleted_once_expired = 0
    enqueued = 0

    for it in items:
        if not isinstance(it, dict):
            continue
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
        if occ_key in fired or _item_already_fired_for_occurrence(it, occ_key):
            continue

        title = str(it.get("title") or "提醒").strip() or "提醒"
        note = str(it.get("note") or "").strip()
        rep = str(it.get("repeat") or "once").strip().lower() or "once"
        created_by = str(it.get("created_by") or "wife").strip().lower() or "wife"
        target_role = str(it.get("target_role") or "wife").strip().lower() or "wife"
        rep_label = {"once": "一次性", "daily": "每天", "weekly": "每周"}.get(rep, rep)
        is_calendar_event = note.startswith("由渡创建系统行程")
        wakeup_kind = "calendar_event" if is_calendar_event else "system_alarm"
        reminder_name = "日历提醒" if is_calendar_event else "闹钟"
        if target_role == "du":
            owner_prefix = "你给自己定的"
        elif created_by == "du":
            owner_prefix = "你给老婆定的"
        else:
            owner_prefix = "老婆之前设的"
        reminder_prompt = (
            f"{owner_prefix}「{title}」{reminder_name}，现在到点了。"
            f"类型：{rep_label}；时间：{now_dt.strftime('%Y-%m-%d %H:%M')}。"
            f"{('备注：' + note + '。') if note else ''}"
            "请像平时聊天那样自然回复；如果有多句，请用换行分段。"
        )
        channels = _available_schedule_channels()
        generation_channel = channels[0] if channels else "qq"
        payload = {
            "item_id": str(it.get("id") or "").strip(),
            "occurrence_key": occ_key,
            "repeat": rep,
            "title": title,
            "prompt": reminder_prompt,
            "channels": channels,
            "generation_channel": generation_channel,
            "wakeup_kind": wakeup_kind,
            "target_user_id": uid,
        }
        item = wakeup_queue.make_item(
            kind=wakeup_queue.TYPE_SCHEDULE,
            due_at=now_iso,
            dedupe_key=f"schedule:{occ_key}",
            payload=payload,
            priority=20,
            window_id=f"tg_{uid}",
            channel=generation_channel,
            target=str(uid),
        )
        inserted, _item_id = wakeup_queue.upsert_pending(item)
        if inserted:
            enqueued += 1
            logger.info("闹钟已入唤醒队列 uid=%s item_id=%s occ_key=%s", uid, payload["item_id"], occ_key)

    if changed:
        kept = [x for x in items if isinstance(x, dict) and not bool(x.get("_deleted"))]
        r2_store.save_schedule_items(kept)
    return {
        "ok": True,
        "checked": len(items),
        "enqueued": enqueued,
        "disabled_once": disabled_once,
        "deleted_once_expired": deleted_once_expired,
        "now": now_iso,
    }


def enqueue_due_followup_wakeups() -> dict:
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso)
    if not now_dt:
        return {"ok": False, "error": "time_parse_failed", "enqueued": 0}
    items = r2_store.get_conversation_followups() or []
    if not items:
        return {"ok": True, "checked": 0, "enqueued": 0, "pending": 0, "cancelled": 0, "now": now_iso}
    changed = False
    enqueued = 0
    cancelled = 0
    pending = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status not in ("", followup_service.FOLLOWUP_STATUS_PENDING):
            continue
        trigger_dt = parse_iso_to_beijing(str(item.get("trigger_at") or "").strip())
        if not trigger_dt:
            item["status"] = followup_service.FOLLOWUP_STATUS_ERROR
            item["last_error"] = "invalid_trigger_at"
            changed = True
            continue
        if trigger_dt > now_dt:
            pending += 1
            continue
        window_id = str(item.get("context_window_id") or "").strip()
        created_at = str(item.get("created_at") or "").strip()
        if not window_id or not created_at:
            item["status"] = followup_service.FOLLOWUP_STATUS_ERROR
            item["last_error"] = "missing_context"
            changed = True
            continue
        if followup_service._has_new_user_activity(window_id, created_at):
            item["status"] = followup_service.FOLLOWUP_STATUS_CANCELLED
            item["cancelled_at"] = now_iso
            item["cancel_reason"] = "user_replied"
            cancelled += 1
            changed = True
            continue
        if int(item.get("attempts") or 0) >= 3:
            item["status"] = followup_service.FOLLOWUP_STATUS_EXPIRED
            item["expired_at"] = now_iso
            item["last_error"] = str(item.get("last_error") or "max_attempts_reached")
            changed = True
            continue
        followup_id = str(item.get("id") or "").strip()
        if not followup_id:
            item["status"] = followup_service.FOLLOWUP_STATUS_ERROR
            item["last_error"] = "missing_id"
            changed = True
            continue
        queue_item = wakeup_queue.make_item(
            kind=wakeup_queue.TYPE_FOLLOWUP,
            due_at=str(item.get("trigger_at") or now_iso),
            dedupe_key=f"followup:{followup_id}",
            payload={"followup_id": followup_id},
            priority=10,
            window_id=window_id,
            channel=str(item.get("reply_channel") or "sumitalk"),
            target=str(item.get("reply_target") or "").strip(),
        )
        inserted, _item_id = wakeup_queue.upsert_pending(queue_item)
        if inserted:
            enqueued += 1
            logger.info("延迟续话已入唤醒队列 followup_id=%s window_id=%s", followup_id, window_id)
    if changed:
        keep = []
        cutoff = now_dt - timedelta(days=3)
        for item in items:
            ts = parse_iso_to_beijing(str(item.get("created_at") or "").strip())
            if ts and ts < cutoff and str(item.get("status") or "").strip().lower() in {
                followup_service.FOLLOWUP_STATUS_SENT,
                followup_service.FOLLOWUP_STATUS_CANCELLED,
                followup_service.FOLLOWUP_STATUS_EXPIRED,
            }:
                continue
            keep.append(item)
        r2_store.save_conversation_followups(keep)
    return {"ok": True, "checked": len(items), "enqueued": enqueued, "pending": pending, "cancelled": cancelled, "now": now_iso}


def enqueue_due_hard_trigger_wakeups(target_user_id: int = 0) -> dict:
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id", "enqueued": 0}
    try:
        from services.proactive_trigger_engine import collect_due_proactive_trigger_events

        result = collect_due_proactive_trigger_events(uid)
    except Exception as e:
        logger.warning("主动硬触发收集异常 error=%s", e, exc_info=True)
        return {"ok": False, "error": str(e), "enqueued": 0}
    events = [x for x in (result.get("events") or []) if isinstance(x, dict)] if isinstance(result, dict) else []
    enqueued = 0
    for event in events[:1]:
        due_at = str(event.get("event_at") or now_beijing_iso()).strip() or now_beijing_iso()
        queue_item = wakeup_queue.make_item(
            kind=wakeup_queue.TYPE_HARD_TRIGGER,
            due_at=due_at,
            dedupe_key=f"hard_trigger:{str(event.get('dedupe_key') or '').strip()}",
            payload=event,
            priority=15,
            window_id=str(event.get("window_id") or f"tg_{uid}"),
            channel="qq",
            target=str(event.get("device_id") or "").strip(),
        )
        inserted, _item_id = wakeup_queue.upsert_pending(queue_item)
        if inserted:
            enqueued += 1
            logger.info("主动硬触发已入唤醒队列 type=%s dedupe=%s", event.get("trigger_type"), event.get("dedupe_key"))
    return {"ok": bool(result.get("ok", True)) if isinstance(result, dict) else True, "enqueued": enqueued, "events": len(events), "skip_reason": (result or {}).get("skip_reason") if isinstance(result, dict) else ""}


def enqueue_next_random_proactive_wakeup(target_user_id: int = 0, delay_seconds: int | None = None, reason: str = "") -> dict:
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        return {"ok": False, "error": "missing_target_user_id", "enqueued": 0}
    if wakeup_queue.has_active_kind(wakeup_queue.TYPE_RANDOM_PROACTIVE):
        return {"ok": True, "enqueued": 0, "skip_reason": "already_active"}
    delay = int(delay_seconds if delay_seconds is not None else _next_proactive_delay_seconds())
    due_at = _iso_after_seconds(delay)
    queue_item = wakeup_queue.make_item(
        kind=wakeup_queue.TYPE_RANDOM_PROACTIVE,
        due_at=due_at,
        dedupe_key=f"random_proactive:{uid}:{due_at}",
        payload={"target_user_id": uid, "reason": str(reason or "").strip()},
        priority=50,
        window_id=f"tg_{uid}",
        channel=_preferred_proactive_channel(_available_channels()),
        target=str(uid),
    )
    inserted, _item_id = wakeup_queue.upsert_pending(queue_item)
    if inserted:
        logger.info("下一次随机主动唤醒已入队 scheduled_in=%.1fmin due_at=%s", delay / 60.0, due_at)
    return {"ok": True, "enqueued": 1 if inserted else 0, "due_at": due_at, "delay_seconds": delay}


def _update_schedule_after_sent(item_id: str, occurrence_key: str, repeat: str, now_iso: str) -> dict:
    items = r2_store.get_schedule_items() or []
    changed = False
    disabled_once = False
    for it in items:
        if str(it.get("id") or "").strip() != str(item_id or "").strip():
            continue
        it["last_fired_at"] = now_iso
        it["last_fired_occurrence_key"] = occurrence_key
        changed = True
        if str(repeat or "").strip().lower() == "once" and bool(it.get("enabled", True)):
            it["enabled"] = False
            it["disabled_at"] = now_iso
            disabled_once = True
        break
    if changed:
        r2_store.save_schedule_items(items)
    return {"changed": changed, "disabled_once": disabled_once}


def _dispatch_schedule_wakeup(item: dict, target_user_id: int) -> dict:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    occ_key = str(payload.get("occurrence_key") or "").strip()
    if not occ_key:
        return {"ok": False, "error": "missing_occurrence_key"}
    if occ_key in r2_store.get_schedule_fired_keys():
        return {"ok": True, "cancelled": True, "reason": "already_fired"}
    uid = int(payload.get("target_user_id") or target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    prompt = str(payload.get("prompt") or "").strip()
    channels = [str(x or "").strip() for x in (payload.get("channels") or []) if str(x or "").strip()] or _available_schedule_channels()
    generation_channel = str(payload.get("generation_channel") or (channels[0] if channels else "qq")).strip() or "qq"
    wakeup_kind = str(payload.get("wakeup_kind") or "system_alarm").strip() or "system_alarm"
    reply_text = _generate_schedule_reply(
        window_id=str(item.get("window_id") or f"tg_{uid}"),
        user_id=uid,
        prompt=prompt,
        preferred_channel=generation_channel,
        wakeup_kind=wakeup_kind,
    )
    if not reply_text:
        return {"ok": False, "error": "empty_gateway_reply"}
    text_to_send = _sanitize_reply_for_telegram(reply_text).strip()
    if not text_to_send:
        return {"ok": False, "error": "empty_after_sanitize"}
    sent_channel = ""
    for channel in channels:
        if _dispatch_send(channel, text_to_send, target_user_id=uid):
            sent_channel = channel
            break
    if not sent_channel:
        return {"ok": False, "error": "dispatch_failed", "preview": text_to_send[:120]}
    r2_store.add_schedule_fired_key(occ_key)
    update = _update_schedule_after_sent(
        item_id=str(payload.get("item_id") or ""),
        occurrence_key=occ_key,
        repeat=str(payload.get("repeat") or ""),
        now_iso=now_beijing_iso(),
    )
    return {"ok": True, "sent": True, "channel": sent_channel, "preview": text_to_send[:120], **update}


def _dispatch_followup_wakeup(item: dict) -> dict:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    followup_id = str(payload.get("followup_id") or "").strip()
    if not followup_id:
        return {"ok": False, "error": "missing_followup_id"}
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso)
    items = r2_store.get_conversation_followups() or []
    target = None
    for row in items:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == followup_id:
            target = row
            break
    if not isinstance(target, dict):
        return {"ok": True, "cancelled": True, "reason": "followup_missing"}
    status = str(target.get("status") or "").strip().lower()
    if status not in ("", followup_service.FOLLOWUP_STATUS_PENDING):
        return {"ok": True, "cancelled": True, "reason": f"followup_status_{status or 'unknown'}"}
    window_id = str(target.get("context_window_id") or "").strip()
    created_at = str(target.get("created_at") or "").strip()
    if not window_id or not created_at:
        target["status"] = followup_service.FOLLOWUP_STATUS_ERROR
        target["last_error"] = "missing_context"
        r2_store.save_conversation_followups(items)
        return {"ok": False, "error": "missing_context"}
    if followup_service._has_new_user_activity(window_id, created_at):
        target["status"] = followup_service.FOLLOWUP_STATUS_CANCELLED
        target["cancelled_at"] = now_iso
        target["cancel_reason"] = "user_replied"
        r2_store.save_conversation_followups(items)
        return {"ok": True, "cancelled": True, "reason": "user_replied"}
    attempts = int(target.get("attempts") or 0)
    if attempts >= 3:
        target["status"] = followup_service.FOLLOWUP_STATUS_EXPIRED
        target["expired_at"] = now_iso
        target["last_error"] = str(target.get("last_error") or "max_attempts_reached")
        r2_store.save_conversation_followups(items)
        return {"ok": False, "error": "max_attempts_reached", "cancelled": True}
    text = followup_service._call_gateway_followup(
        window_id=window_id,
        channel=str(target.get("reply_channel") or "sumitalk"),
        reason=str(target.get("reason") or "").strip(),
        chain_id=str(target.get("chain_id") or "").strip(),
        followup_index=int(target.get("followup_index") or 1),
        root_created_at=str(target.get("root_created_at") or target.get("created_at") or "").strip(),
    )
    target["attempts"] = attempts + 1
    target["last_attempt_at"] = now_iso
    if not text:
        target["last_error"] = "empty_gateway_reply"
        r2_store.save_conversation_followups(items)
        return {"ok": False, "error": "empty_gateway_reply"}
    ok = followup_service._dispatch_followup(
        channel=str(target.get("reply_channel") or "sumitalk"),
        target=str(target.get("reply_target") or "").strip(),
        text=text,
        created_at=now_iso,
    )
    if ok:
        target["status"] = followup_service.FOLLOWUP_STATUS_SENT
        target["sent_at"] = now_iso
        target["sent_preview"] = text[:120]
    else:
        target["last_error"] = "dispatch_failed"
    if now_dt:
        cutoff = now_dt - timedelta(days=3)
        keep = []
        for row in items:
            ts = parse_iso_to_beijing(str((row or {}).get("created_at") or "").strip()) if isinstance(row, dict) else None
            if ts and ts < cutoff and str((row or {}).get("status") or "").strip().lower() in {
                followup_service.FOLLOWUP_STATUS_SENT,
                followup_service.FOLLOWUP_STATUS_CANCELLED,
                followup_service.FOLLOWUP_STATUS_EXPIRED,
            }:
                continue
            keep.append(row)
        items = keep
    r2_store.save_conversation_followups(items)
    return {"ok": bool(ok), "sent": bool(ok), "error": "" if ok else "dispatch_failed", "preview": (text or "")[:120]}


def _dispatch_hard_trigger_wakeup(item: dict, target_user_id: int) -> dict:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    try:
        from services.conversation_followup import send_proactive_trigger_wakeup
        from services.proactive_trigger_engine import mark_proactive_trigger_event_fired
    except Exception as e:
        logger.warning("队列主动硬触发导入异常 error=%s", e, exc_info=True)
        return {"ok": False, "error": str(e)}
    try:
        result = send_proactive_trigger_wakeup(
            window_id=str(payload.get("window_id") or item.get("window_id") or f"tg_{int(target_user_id or 0)}"),
            target=str(payload.get("device_id") or item.get("target") or "").strip(),
            event_text=str(payload.get("event_text") or "").strip(),
            created_at=str(payload.get("event_at") or now_beijing_iso()).strip(),
        )
    except Exception as e:
        logger.warning("队列主动硬触发执行异常 error=%s", e, exc_info=True)
        result = {"ok": False, "error": str(e)}
    if not isinstance(result, dict):
        result = {"ok": False, "error": "invalid_result"}
    fired_marked = mark_proactive_trigger_event_fired(payload, result)
    return {"ok": bool(result.get("ok")), "sent": bool(result.get("ok")), "fired_marked": fired_marked, "no_retry": fired_marked, **result}


def _dispatch_random_proactive_wakeup(item: dict, target_user_id: int) -> dict:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    uid = int(payload.get("target_user_id") or target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    return proactive_tick(uid)


def _dispatch_wakeup_queue_item(item: dict, target_user_id: int = 0) -> dict:
    kind = str((item or {}).get("kind") or "").strip()
    if kind == wakeup_queue.TYPE_SCHEDULE:
        return _dispatch_schedule_wakeup(item, target_user_id)
    if kind == wakeup_queue.TYPE_FOLLOWUP:
        return _dispatch_followup_wakeup(item)
    if kind == wakeup_queue.TYPE_HARD_TRIGGER:
        return _dispatch_hard_trigger_wakeup(item, target_user_id)
    if kind == wakeup_queue.TYPE_RANDOM_PROACTIVE:
        return _dispatch_random_proactive_wakeup(item, target_user_id)
    return {"ok": False, "error": f"unknown_wakeup_kind:{kind}"}


def _finish_wakeup_queue_item(item: dict, result: dict, target_user_id: int = 0) -> None:
    item_id = str((item or {}).get("id") or "").strip()
    kind = str((item or {}).get("kind") or "").strip()
    if not item_id:
        return
    if result.get("cancelled"):
        wakeup_queue.mark_cancelled(item_id, str(result.get("reason") or result.get("error") or "cancelled"), result=result)
    elif result.get("ok"):
        wakeup_queue.mark_sent(item_id, result=result)
    elif result.get("no_retry"):
        wakeup_queue.mark_failed_or_retry(item_id, str(result.get("error") or "dispatch_failed"), retry_after_seconds=60, max_attempts=0, result=result)
    else:
        wakeup_queue.mark_failed_or_retry(item_id, str(result.get("error") or "dispatch_failed"), retry_after_seconds=60, max_attempts=3, result=result)
    if kind == wakeup_queue.TYPE_RANDOM_PROACTIVE:
        enqueue_next_random_proactive_wakeup(target_user_id, reason="after_random_tick")
    elif kind == wakeup_queue.TYPE_HARD_TRIGGER and result.get("sent"):
        wakeup_queue.cancel_active_kind(wakeup_queue.TYPE_RANDOM_PROACTIVE, reason="hard_trigger_sent")
        enqueue_next_random_proactive_wakeup(
            target_user_id,
            delay_seconds=_next_post_hard_trigger_delay_seconds(),
            reason="after_hard_trigger",
        )


def _send_via_wechat(text: str, split: bool = True) -> bool:
    """通过微信 connector 的 /push 端点主动发消息。"""
    url = WECHAT_PROACTIVE_PUSH_URL
    if not url:
        logger.warning("WECHAT_PROACTIVE_PUSH_URL 未配置，跳过微信发送")
        return False
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if WECHAT_PROACTIVE_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {WECHAT_PROACTIVE_PUSH_TOKEN}"
    try:
        body = json.dumps({"text": str(text or ""), "split": bool(split)}, ensure_ascii=False).encode("utf-8")
        r = requests.post(url, headers=headers, data=body, timeout=30)
        if r.status_code == 200 and r.json().get("ok"):
            return True
        logger.warning("微信 /push 失败 status=%s body=%s", r.status_code, (r.text or "")[:200])
        return False
    except Exception as e:
        logger.warning("微信 /push 异常: %s", e)
        return False


def _send_via_qq(text: str, split: bool = True) -> bool:
    """通过 QQ connector 的 /push 端点主动发消息。"""
    url = QQ_PROACTIVE_PUSH_URL or "http://127.0.0.1:8092/push"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if QQ_PROACTIVE_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {QQ_PROACTIVE_PUSH_TOKEN}"
    try:
        body = json.dumps({"text": str(text or ""), "split": bool(split)}, ensure_ascii=False).encode("utf-8")
        r = requests.post(url, headers=headers, data=body, timeout=30)
        if r.status_code == 200 and r.json().get("ok"):
            return True
        logger.warning("QQ /push 失败 status=%s body=%s", r.status_code, (r.text or "")[:200])
        return False
    except Exception as e:
        logger.warning("QQ /push 异常: %s", e)
        return False


def _send_via_tg(text: str, target_user_id: int = 0) -> bool:
    """通过 Telegram Bot 主动发富媒体消息。"""
    uid = int(target_user_id or TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid <= 0:
        logger.warning("TG 主动发送失败：target_user_id 为空")
        return False
    return send_rich_message(chat_id=uid, text=text, bot_token=None)


def _dispatch_send(channel: str, text: str, split: bool = True, target_user_id: int = 0) -> bool:
    """根据 channel 选择发送入口，返回是否发送成功。"""
    text = _sanitize_control_reply_for_delivery(text).strip()
    if not text:
        logger.warning("主动消息发送跳过：清洗后为空 channel=%s", channel)
        return False
    if channel == "wechat":
        return _send_via_wechat(text, split=split)
    if channel == "qq":
        return _send_via_qq(text, split=split)
    if channel == "tg":
        return _send_via_tg(text, target_user_id=target_user_id)
    logger.warning("主动消息发送入口不可用 channel=%s", channel)
    return False


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

    # 若最近任一入口有消息活动（正在聊天），本 tick 不主动发。
    # 这里必须与主动概率计算使用同一个口径，避免 SumiTalk/QQ/微信等入口正在聊时误触发主动消息。
    skip_min = int(TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES or 0)
    last_iso = _get_last_message_activity_iso(uid)
    if skip_min > 0:
        if last_iso:
            last_activity_dt = parse_iso_to_beijing(last_iso)
            if last_activity_dt:
                delta_minutes = (now_dt - last_activity_dt).total_seconds() / 60.0
                if delta_minutes < skip_min:
                    return {
                        "ok": True,
                        "quiet": False,
                        "sent": False,
                        "skip_reason": "recent_activity",
                        "now": now_iso,
                        "last_activity": last_iso,
                        "minutes_ago": round(delta_minutes, 1),
                    }

    hours = _hours_since_last(last_iso, now_dt)
    p = _probability(hours)
    out = {
        "ok": True,
        "quiet": False,
        "sent": False,
        "now": now_iso,
        "last": last_iso,
        "hours": hours,
        "legacy_p": p,
        "wake_mode": "random_decision",
    }
    channels = _available_channels()
    out["channels"] = channels
    if not channels:
        out["skip_reason"] = "no_delivery_channel"
        logger.warning("主动消息命中但没有可用发送入口，已跳过")
        return out

    window_id = f"tg_{uid}"
    decision = _ask_du_should_contact(window_id=window_id, hours_since_last=hours, now_dt=now_dt)
    out["du_reason"] = decision.reason
    out["du_action"] = decision.action
    out["du_intent_reason"] = decision.du_reason

    # 随机唤醒主动决策：记下本轮决策（闹钟不走这里）
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

    window_id = f"tg_{uid}"
    if not decision.should_send or not decision.text.strip():
        trigger = _build_du_daily_trigger_from_proactive(decision, hours, sent=False)
        if trigger:
            try:
                out["du_daily_updated"] = bool(request_gateway_maintenance(window_id, trigger))
            except Exception as e:
                logger.warning("主动决策写入渡的日常失败: %s", e)
        return out
    text_to_send = decision.text.strip()
    # 主动发消息也复用 Telegram 侧的清洗规则：避免出现“（脑内OS：）”等格式
    text_to_send = _sanitize_reply_for_telegram(text_to_send).strip()
    text_to_send = _sanitize_control_reply_for_delivery(text_to_send).strip()
    default_channel = channels[0] if channels else ""
    channel = _normalize_reply_channel(decision.channel or default_channel, default=default_channel, allowed=channels)
    out["channel"] = channel
    logger.info(
        "主动消息准备发送 channel=%s chat_id=%s text_preview=%s",
        channel, uid, text_to_send[:80] + ("…" if len(text_to_send) > 80 else ""),
    )
    if not text_to_send:
        out["skip_reason"] = "empty_after_sanitize"
        return out
    if not channel:
        out["skip_reason"] = "no_delivery_channel"
        return out
    ok = _dispatch_send(channel, text_to_send, target_user_id=uid)
    logger.info("主动消息发送结果 channel=%s chat_id=%s sent=%s", channel, uid, ok)
    out["sent"] = bool(ok)
    out["text_preview"] = (decision.text.strip()[:120] + "…") if len(decision.text.strip()) > 120 else decision.text.strip()
    if ok:
        r2_store.save_last_proactive_contact_at(now_iso)
        trigger = _build_du_daily_trigger_from_proactive(decision, hours, sent=True)
        if trigger:
            try:
                out["du_daily_updated"] = bool(request_gateway_maintenance(window_id, trigger))
            except Exception as e:
                logger.warning("主动消息结果写入渡的日常失败: %s", e)
        logger.warning(
            "Pro 已发送一条主动消息 channel=%s chat_id=%s now=%s preview=%s",
            channel, uid, now_iso, text_to_send[:60] + ("…" if len(text_to_send) > 60 else ""),
        )
    return out


async def _periodic_to_thread(name: str, interval_seconds: int, func, *args):
    interval = max(5, int(interval_seconds or 60))
    while True:
        try:
            result = await asyncio.to_thread(func, *args)
            logger.info("%s result=%s", name, result)
        except Exception as e:
            logger.exception("%s 异常: %s", name, e)
        await asyncio.sleep(interval)


async def _du_daily_sleep_loop(uid: int):
    while True:
        try:
            result = await asyncio.to_thread(du_daily_sleep_tick, uid)
            logger.info("渡的日常入睡收口 tick result=%s", result)
        except Exception as e:
            logger.exception("渡的日常入睡收口 tick 异常: %s", e)
        await asyncio.sleep(300)


async def _wakeup_queue_dispatch_loop(uid: int):
    while True:
        try:
            claimed = await asyncio.to_thread(wakeup_queue.claim_due, 1, "telegram_proactive_async")
            if not claimed:
                await asyncio.sleep(5)
                continue
            for item in claimed:
                result = await asyncio.to_thread(_dispatch_wakeup_queue_item, item, uid)
                logger.info("唤醒队列执行 kind=%s id=%s result=%s", item.get("kind"), item.get("id"), result)
                await asyncio.to_thread(_finish_wakeup_queue_item, item, result if isinstance(result, dict) else {"ok": False, "error": "invalid_result"}, uid)
        except Exception as e:
            logger.exception("唤醒队列 dispatcher 异常: %s", e)
            await asyncio.sleep(5)


async def run_scheduler_loop_async():
    """Async coordinator: producers fill wakeup_queue; dispatcher only consumes due queue items."""
    schedule_enabled = bool(MINIAPP_SCHEDULE_RUNTIME_ENABLED)
    proactive_enabled = bool(TELEGRAM_PROACTIVE_ENABLED)
    if not proactive_enabled and not schedule_enabled:
        logger.warning("主动发消息和日历闹钟调度均未开启，直接退出")
        return
    interval_min = max(1, int(TELEGRAM_PROACTIVE_INTERVAL_MINUTES or 30))
    random_min = max(1, int(TELEGRAM_PROACTIVE_RANDOM_MIN_MINUTES or 35))
    random_max = max(random_min, int(TELEGRAM_PROACTIVE_RANDOM_MAX_MINUTES or random_min))
    schedule_interval_s = max(30, int(MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS or 60))
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    logger.info(
        "主动调度进程启动 proactive_enabled=%s legacy_interval_min=%s random_window=%s-%smin schedule_enabled=%s schedule_interval_s=%s target_user_id=%s",
        proactive_enabled,
        interval_min,
        random_min,
        random_max,
        schedule_enabled,
        schedule_interval_s,
        uid,
    )
    if proactive_enabled:
        await asyncio.to_thread(enqueue_next_random_proactive_wakeup, uid, None, "startup")

    tasks = [asyncio.create_task(_wakeup_queue_dispatch_loop(uid))]
    if schedule_enabled:
        tasks.append(asyncio.create_task(_periodic_to_thread("日历闹钟入队 tick", schedule_interval_s, enqueue_due_schedule_wakeups, uid)))
    if proactive_enabled:
        tasks.extend(
            [
                asyncio.create_task(_periodic_to_thread("延迟续话入队 tick", max(15, int(FOLLOWUP_TICK_SECONDS or 60)), enqueue_due_followup_wakeups)),
                asyncio.create_task(_periodic_to_thread("主动硬触发入队 tick", 60, enqueue_due_hard_trigger_wakeups, uid)),
                asyncio.create_task(_periodic_to_thread("随机主动唤醒排程 tick", 60, enqueue_next_random_proactive_wakeup, uid)),
                asyncio.create_task(_du_daily_sleep_loop(uid)),
            ]
        )
    await asyncio.gather(*tasks)


def run_scheduler_loop():
    """常驻循环：按各自旧逻辑直接执行；wakeup_queue 只保留为观测/管理表。"""
    schedule_enabled = bool(MINIAPP_SCHEDULE_RUNTIME_ENABLED)
    proactive_enabled = bool(TELEGRAM_PROACTIVE_ENABLED)
    if not proactive_enabled and not schedule_enabled:
        logger.warning("主动发消息和日历闹钟调度均未开启，直接退出")
        return
    interval_min = max(1, int(TELEGRAM_PROACTIVE_INTERVAL_MINUTES or 30))
    random_min = max(1, int(TELEGRAM_PROACTIVE_RANDOM_MIN_MINUTES or 35))
    random_max = max(random_min, int(TELEGRAM_PROACTIVE_RANDOM_MAX_MINUTES or random_min))
    schedule_interval_s = max(30, int(MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS or 60))
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    logger.info(
        "主动调度进程启动 proactive_enabled=%s legacy_interval_min=%s random_window=%s-%smin schedule_enabled=%s schedule_interval_s=%s target_user_id=%s queue_execution=disabled",
        proactive_enabled,
        interval_min,
        random_min,
        random_max,
        schedule_enabled,
        schedule_interval_s,
        uid,
    )
    first_delay = _next_proactive_delay_seconds()
    next_main_at = time.time() + first_delay
    logger.info("下一次随机主动唤醒 scheduled_in=%.1fmin", first_delay / 60.0)
    next_schedule_at = 0.0
    next_followup_at = 0.0
    next_du_daily_at = 0.0
    next_hard_trigger_at = 0.0
    while True:
        now_ts = time.time()
        try:
            if schedule_enabled and now_ts >= next_schedule_at:
                sched = schedule_tick(uid)
                logger.info("日历闹钟 tick result=%s", sched)
                next_schedule_at = now_ts + schedule_interval_s
            if proactive_enabled and now_ts >= next_followup_at:
                followup = tick_conversation_followups()
                logger.info("延迟续话 tick result=%s", followup)
                next_followup_at = now_ts + max(15, int(FOLLOWUP_TICK_SECONDS or 60))
            if proactive_enabled and now_ts >= next_hard_trigger_at:
                from services.proactive_trigger_engine import tick_proactive_triggers

                hard_trigger = tick_proactive_triggers(uid)
                logger.info("主动硬触发 tick result=%s", hard_trigger)
                if hard_trigger.get("sent"):
                    post_delay = _next_post_hard_trigger_delay_seconds()
                    next_main_at = now_ts + post_delay
                    logger.info(
                        "硬触发已发出，下一次随机主动唤醒重排 scheduled_in=%.1fmin",
                        post_delay / 60.0,
                    )
                next_hard_trigger_at = now_ts + 60
            if proactive_enabled and now_ts >= next_du_daily_at:
                daily = du_daily_sleep_tick(uid)
                logger.info("渡的日常入睡收口 tick result=%s", daily)
                next_du_daily_at = now_ts + 300
            if proactive_enabled and now_ts >= next_main_at:
                result = proactive_tick(uid)
                logger.info("主动发消息 tick result=%s", result)
                next_delay = _next_proactive_delay_seconds()
                next_main_at = now_ts + next_delay
                logger.info("下一次随机主动唤醒 scheduled_in=%.1fmin", next_delay / 60.0)
        except Exception as e:
            logger.exception("主动发消息 tick 异常: %s", e)
        time.sleep(15)
