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
    CHAT_RESPONSE_TIMEOUT_SECONDS,
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
    send_rich_message,
)
from services import wakeup_state
from services.conversation_followup import (
    FOLLOWUP_TICK_SECONDS,
    send_post_spring_dream_wakeup,
    send_spring_dream_wakeup,
    tick_conversation_followups,
)
from services.du_daily import infer_sleep_rollover_trigger, request_gateway_maintenance
from services.user_activity_context import describe_latest_interaction
from services.spring_dream import (
    maybe_prepare_post_spring_dream_wakeup,
    maybe_prepare_spring_dream_wakeup,
    record_post_spring_dream_wakeup_sent,
    record_spring_dream_sent,
    release_spring_dream_slot,
)
from services.proactive_prompt_templates import (
    RANDOM_PROACTIVE_DECISION_SECTION_ID,
    RANDOM_PROACTIVE_DECISION_TEMPLATE,
)

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
    action: str = ""      # 业务向：send_message / no_contact / diary / forum / surf / drawer / other / error / …
    du_reason: str = ""   # 渡在 JSON 里写的理由
    channel: str = ""           # 发送入口：wechat / qq；SumiTalk 暂不参与主动消息


def _get_chat_model() -> str:
    try:
        from storage.upstream_store import get_cached_active_model

        return str(get_cached_active_model(refresh_if_missing=False) or "").strip()
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
    统一“最近真实互动节流”时间。

    注意不要取 conversation_rounds 的最新 timestamp：
    后端闹钟、随机唤醒执行轮、弹窗回执等都会归档成轮次，
    但这些不代表小玥真的回来了，不能拿来计算“她多久没说话”。

    这里只看小玥最近一次真实互动：last_user_activity_at。
    渡主动外发成功的 last_proactive_contact_at 只作为历史记录，不参与这里的时间感计算；
    如果他连续醒来都想找她，就让模型自己判断要不要连发，而不是后端先压住。
    """
    last_user_iso = r2_store.get_last_user_activity_at()
    return _pick_latest_iso([last_user_iso])


def _describe_recent_exchange(now_dt: datetime) -> str:
    """给主动决策提示词描述最近一次 chat 或共同游戏互动。"""
    interaction_text = describe_latest_interaction(now_dt)
    if interaction_text:
        return interaction_text

    # 兼容尚未生成本地活动上下文的旧部署数据。
    last_user_iso = r2_store.get_last_user_activity_at()
    last_user_dt = parse_iso_to_beijing(last_user_iso)

    if last_user_dt:
        hours_since_user = _hours_since_last(last_user_iso, now_dt)
        return f"她上次明确回你大约是 {hours_since_user:.1f} 小时前。"

    return "最近没有可参考的明确用户回复记录。"


def _render_random_proactive_decision_prompt(
    *,
    recent_exchange: str,
    hours_since_last: float,
    channel_field_desc: str,
    default_channel: str,
    no_contact_token: str,
) -> str:
    try:
        from services.prompt_manager import get_managed_prompt_text

        template = get_managed_prompt_text(
            RANDOM_PROACTIVE_DECISION_SECTION_ID,
            fallback=RANDOM_PROACTIVE_DECISION_TEMPLATE,
        )
    except Exception:
        template = RANDOM_PROACTIVE_DECISION_TEMPLATE
    text = str(template or RANDOM_PROACTIVE_DECISION_TEMPLATE)
    hours_text = f"{hours_since_last:.1f}"
    replacements = {
        "{{recent_exchange}}": str(recent_exchange or "").strip(),
        "{{hours_since_last}}": hours_text,
        "{{channel_field_desc}}": str(channel_field_desc or "").strip(),
        "{{default_channel}}": str(default_channel or "").strip(),
        "{{no_contact_token}}": str(no_contact_token or "NO_CONTACT").strip(),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text.replace("X.X", hours_text).strip()


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
    "forum": "逛论坛",
    "surf": "随机冲浪",
    "drawer": "整理秘密抽屉",
    "other": "其它",
    "error": "调用失败",
    "empty": "空回复",
    "unknown": "未解析",
}


_SELF_ACTION_TOOL_LABELS = {
    "exchange_diary_create": "写了交换日记",
    "daily_whisper_write": "写了气泡",
    "forum_read_feed": "逛了论坛信息流",
    "forum_open_thread": "看了论坛帖子",
    "du_surf": "随机冲浪看了素材",
    "secret_drawer": "整理了秘密抽屉",
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


def _decode_loose_control_string(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, str):
            return decoded.strip()
    except Exception:
        pass
    if raw.endswith(","):
        raw = raw[:-1].strip()
    while len(raw) >= 2 and raw[0] in {"\"", "'"} and raw[-1] == raw[0]:
        raw = raw[1:-1].strip()
    return (
        raw.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .strip()
    )


def _load_loose_proactive_control_object(text: str) -> Optional[dict]:
    """Best-effort parse for control JSON whose message contains unescaped quotes."""
    raw = _extract_json_object_text(text) or _strip_json_fence(text)
    raw = str(raw or "").strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        return None
    normalized = raw.replace('""', '"').replace('\\"', '"')
    if '"action"' not in normalized or '"message"' not in normalized:
        return None

    pattern = re.compile(r'(?P<prefix>[,{]\s*)["\'](?P<key>action|reason|message|channel)["\']\s*:', re.IGNORECASE)
    matches = list(pattern.finditer(raw))
    if not matches:
        return None
    found: dict[str, str] = {}
    for idx, match in enumerate(matches):
        key = match.group("key").lower()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else raw.rfind("}")
        if end <= start:
            continue
        chunk = raw[start:end].strip()
        if chunk.endswith(","):
            chunk = chunk[:-1].strip()
        found[key] = _decode_loose_control_string(chunk)

    action = str(found.get("action") or "").strip().lower()
    message = str(found.get("message") or "").strip()
    if not action and not message:
        return None
    return found


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
    send_message 只取 message；diary/forum/no_contact/surf/drawer/other 说明本轮不该发。
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    obj = _load_proactive_control_object(raw) or _load_loose_proactive_control_object(raw)
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

    obj = _load_proactive_control_object(t) or _load_loose_proactive_control_object(t)

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
    alias = {
        "send": "send_message",
        "msg": "send_message",
        "text": "send_message",
        "chat": "send_message",
        "browse": "surf",
        "web_surf": "surf",
        "du_surf": "surf",
        "read_forum": "forum",
        "browse_forum": "forum",
        "forum_read_feed": "forum",
        "forum_open_thread": "forum",
        "逛论坛": "forum",
        "看论坛": "forum",
        "secret_drawer": "drawer",
        "drawer": "drawer",
        "random_drawer": "drawer",
        "整理抽屉": "drawer",
        "秘密抽屉": "drawer",
        "翻抽屉": "drawer",
    }
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
    if action == "forum":
        return ProactiveDecision(False, message, "forum", action="forum", du_reason=du_reason or "（未说明）", channel=channel)
    if action == "surf":
        return ProactiveDecision(False, message, "surf", action="surf", du_reason=du_reason or "（未说明）", channel=channel)
    if action == "drawer":
        return ProactiveDecision(False, message, "drawer", action="drawer", du_reason=du_reason or "（未说明）", channel=channel)
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
        r = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
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
    user_prompt = _render_random_proactive_decision_prompt(
        recent_exchange=_describe_recent_exchange(now_ref),
        hours_since_last=hours_since_last,
        channel_field_desc=channel_field_desc,
        default_channel=default_channel,
        no_contact_token=no_token,
    )
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
    # 入口风格由网关主流程统一注入，避免主动唤醒预置 system 导致静态前缀顺序漂移。
    messages = []
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
        r = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
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


def _run_proactive_surf_action() -> dict:
    """随机唤醒选择 surf 时，后端实际执行一次 du_surf，避免只留下口头动作。"""
    try:
        from services.gateway_tools import execute_du_surf_tool

        raw = execute_du_surf_tool("du_surf", {"limit": 3})
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            data = {"ok": False, "error": "invalid_du_surf_result"}
        cards = data.get("cards") if isinstance(data.get("cards"), list) else []
        titles = [
            str((card or {}).get("title") or "").strip()
            for card in cards
            if isinstance(card, dict) and str((card or {}).get("title") or "").strip()
        ][:3]
        cards_for_du = []
        for card in cards[:3]:
            if not isinstance(card, dict):
                continue
            cards_for_du.append(
                {
                    "title": str(card.get("title") or "").strip()[:120],
                    "url": str(card.get("url") or "").strip()[:240],
                    "snippet": str(card.get("snippet") or "").strip()[:260],
                    "content": str(card.get("content") or "").strip()[:520],
                    "why_fun": str(card.get("why_fun") or "").strip()[:160],
                }
            )
        summary = {
            "ok": bool(data.get("ok")),
            "topic": str(data.get("topic") or "").strip(),
            "count": len(cards),
            "titles": titles,
            "cards_for_du": cards_for_du,
        }
        if data.get("error"):
            summary["error"] = str(data.get("error") or "")[:120]
        logger.info(
            "主动随机冲浪执行结果 ok=%s topic=%s count=%s titles=%s error=%s",
            summary.get("ok"),
            summary.get("topic") or "",
            summary.get("count"),
            " | ".join(titles),
            summary.get("error") or "",
        )
        return summary
    except Exception as e:
        logger.warning("主动随机冲浪执行失败: %s", e)
        return {"ok": False, "error": str(e)[:160], "topic": "", "count": 0, "titles": []}


def _format_proactive_surf_result_for_du(surf_result: dict) -> str:
    if not isinstance(surf_result, dict):
        return "随机冲浪没有返回可用结果。"
    if not surf_result.get("ok"):
        err = str(surf_result.get("error") or "unknown").strip()
        return f"随机冲浪失败：{err or 'unknown'}。"
    topic = str(surf_result.get("topic") or "").strip() or "随机话题"
    lines = [f"随机冲浪结果：话题「{topic}」，拿到 {int(surf_result.get('count') or 0)} 张素材卡。"]
    cards = surf_result.get("cards_for_du") if isinstance(surf_result.get("cards_for_du"), list) else []
    for idx, card in enumerate(cards[:3], 1):
        if not isinstance(card, dict):
            continue
        title = str(card.get("title") or "").strip()
        snippet = str(card.get("snippet") or "").strip()
        content = str(card.get("content") or "").strip()
        why_fun = str(card.get("why_fun") or "").strip()
        url = str(card.get("url") or "").strip()
        lines.append(
            "\n".join(
                part
                for part in [
                    f"{idx}. {title}" if title else f"{idx}. （无标题）",
                    f"摘要：{snippet}" if snippet else "",
                    f"正文片段：{content}" if content and content != snippet else "",
                    f"可聊点：{why_fun}" if why_fun else "",
                    f"来源：{url}" if url else "",
                ]
                if part
            )
        )
    return "\n\n".join(lines).strip()


def _run_proactive_diary_action(
    *,
    window_id: str,
    hours_since_last: float,
    initial_reason: str,
    now_dt: Optional[datetime] = None,
) -> dict:
    """随机唤醒选择 diary 时，再走一轮主网关，提醒渡直接去写日记。"""
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    channels = _available_channels()
    default_channel = _preferred_proactive_channel(channels)
    now_ref = now_dt or parse_iso_to_beijing(now_beijing_iso()) or datetime.now()
    user_prompt = (
        "你刚才在随机唤醒里选择了写日记/记事。\n"
        "现在不是重新做选择，也不要输出 JSON；请直接去写。\n"
        "请调用 exchange_diary_create 写一条交换日记。\n"
        "写完后用一句很短的话说明已经写好；如果工具失败，也用一句话说明失败原因。\n"
        f"{_describe_recent_exchange(now_ref)} 从系统节流角度看，距最近一次真实互动大约 {hours_since_last:.1f} 小时。\n"
        f"你刚才选择写日记的理由：{str(initial_reason or '').strip() or '（未说明）'}"
    )
    body = {
        "model": _get_chat_model(),
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
        "X-Reply-Channel": default_channel,
        "X-Reply-Target": str(TELEGRAM_PROACTIVE_TARGET_USER_ID or "").strip(),
        "X-Force-Last4": "1",
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-WAKEUP-KIND": "proactive_diary",
        "X-Skip-Dynamic-Memory": "1",
        "X-Skip-Post-Archive-Dynamic-Memory": "1",
    }
    try:
        logger.info(
            "主动写日记执行轮请求 window_id=%s model=%s reason_chars=%s",
            window_id,
            body.get("model") or "",
            len(str(initial_reason or "")),
        )
        r = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
        if r.status_code != 200:
            logger.warning(
                "主动写日记执行轮失败 status=%s body_preview=%s",
                r.status_code,
                (r.text or "")[:300],
            )
            return {
                "ok": False,
                "error": f"http_{r.status_code}",
                "reply_preview": (r.text or "")[:160],
            }
        data = r.json() if r.content else None
        msg = (data or {}).get("choices") and (data.get("choices") or [{}])[0].get("message") or {}
        content = (msg or {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        logger.info("主动写日记执行轮完成 window_id=%s reply_preview=%s", window_id, text[:120])
        return {"ok": bool(text), "reply_preview": text[:240], "error": "" if text else "empty_reply"}
    except Exception as e:
        logger.warning("主动写日记执行轮异常: %s", e)
        return {"ok": False, "error": str(e)[:160], "reply_preview": ""}


def _run_proactive_forum_action(
    *,
    window_id: str,
    hours_since_last: float,
    initial_reason: str,
    now_dt: Optional[datetime] = None,
) -> dict:
    """随机唤醒选择 forum 时，再走一轮主网关，提醒渡直接去逛论坛。"""
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    channels = _available_channels()
    default_channel = _preferred_proactive_channel(channels)
    now_ref = now_dt or parse_iso_to_beijing(now_beijing_iso()) or datetime.now()
    user_prompt = (
        "你刚才在随机唤醒里选择了逛论坛。\n"
        "现在不是重新做选择，也不要输出 JSON；请直接去论坛看看。\n"
        "优先调用 forum_read_feed 浏览信息流；如果看到你想继续看的帖子，再调用 forum_open_thread 打开一篇。\n"
        "看完后用一句很短的话说明你看了什么；如果工具失败，也用一句话说明失败原因。\n"
        f"{_describe_recent_exchange(now_ref)} 从系统节流角度看，距最近一次真实互动大约 {hours_since_last:.1f} 小时。\n"
        f"你刚才选择逛论坛的理由：{str(initial_reason or '').strip() or '（未说明）'}"
    )
    body = {
        "model": _get_chat_model(),
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
        "X-Reply-Channel": default_channel,
        "X-Reply-Target": str(TELEGRAM_PROACTIVE_TARGET_USER_ID or "").strip(),
        "X-Force-Last4": "1",
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-WAKEUP-KIND": "proactive_forum",
        "X-Skip-Dynamic-Memory": "1",
        "X-Skip-Post-Archive-Dynamic-Memory": "1",
    }
    try:
        logger.info(
            "主动逛论坛执行轮请求 window_id=%s model=%s reason_chars=%s",
            window_id,
            body.get("model") or "",
            len(str(initial_reason or "")),
        )
        r = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
        if r.status_code != 200:
            logger.warning(
                "主动逛论坛执行轮失败 status=%s body_preview=%s",
                r.status_code,
                (r.text or "")[:300],
            )
            return {
                "ok": False,
                "error": f"http_{r.status_code}",
                "reply_preview": (r.text or "")[:160],
            }
        data = r.json() if r.content else None
        msg = (data or {}).get("choices") and (data.get("choices") or [{}])[0].get("message") or {}
        content = (msg or {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        logger.info("主动逛论坛执行轮完成 window_id=%s reply_preview=%s", window_id, text[:120])
        return {"ok": bool(text), "reply_preview": text[:240], "error": "" if text else "empty_reply"}
    except Exception as e:
        logger.warning("主动逛论坛执行轮异常: %s", e)
        return {"ok": False, "error": str(e)[:160], "reply_preview": ""}


def _run_proactive_drawer_action(
    *,
    window_id: str,
    hours_since_last: float,
    initial_reason: str,
    now_dt: Optional[datetime] = None,
) -> dict:
    """随机唤醒选择 drawer 时，再走一轮主网关，提醒渡直接整理/翻秘密抽屉。"""
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    channels = _available_channels()
    default_channel = _preferred_proactive_channel(channels)
    now_ref = now_dt or parse_iso_to_beijing(now_beijing_iso()) or datetime.now()
    user_prompt = (
        "你刚才在随机唤醒里选择了整理秘密抽屉/随机翻旧条目。\n"
        "现在不是重新做选择，也不要输出 JSON；请直接去秘密抽屉做一件小事。\n"
        "可以调用 secret_drawer：优先看 stats；如果有待整理条目，就 list 后 update 补标题、标签或 why；"
        "如果没有待整理，就 random 翻一条旧记录，必要时 update 置顶、封存或补一句为什么存。\n"
        "做完后用一句很短的话说明你做了什么；如果工具失败，也用一句话说明失败原因。\n"
        f"{_describe_recent_exchange(now_ref)} 从系统节流角度看，距最近一次真实互动大约 {hours_since_last:.1f} 小时。\n"
        f"你刚才选择秘密抽屉的理由：{str(initial_reason or '').strip() or '（未说明）'}"
    )
    body = {
        "model": _get_chat_model(),
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
        "X-Reply-Channel": default_channel,
        "X-Reply-Target": str(TELEGRAM_PROACTIVE_TARGET_USER_ID or "").strip(),
        "X-Force-Last4": "1",
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-WAKEUP-KIND": "proactive_drawer",
        "X-Skip-Dynamic-Memory": "1",
        "X-Skip-Post-Archive-Dynamic-Memory": "1",
    }
    try:
        logger.info(
            "主动秘密抽屉执行轮请求 window_id=%s model=%s reason_chars=%s",
            window_id,
            body.get("model") or "",
            len(str(initial_reason or "")),
        )
        r = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
        if r.status_code != 200:
            logger.warning(
                "主动秘密抽屉执行轮失败 status=%s body_preview=%s",
                r.status_code,
                (r.text or "")[:300],
            )
            return {
                "ok": False,
                "error": f"http_{r.status_code}",
                "reply_preview": (r.text or "")[:160],
            }
        data = r.json() if r.content else None
        msg = (data or {}).get("choices") and (data.get("choices") or [{}])[0].get("message") or {}
        content = (msg or {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        logger.info("主动秘密抽屉执行轮完成 window_id=%s reply_preview=%s", window_id, text[:120])
        return {"ok": bool(text), "reply_preview": text[:240], "error": "" if text else "empty_reply"}
    except Exception as e:
        logger.warning("主动秘密抽屉执行轮异常: %s", e)
        return {"ok": False, "error": str(e)[:160], "reply_preview": ""}


def _ask_du_after_surf_result(
    *,
    window_id: str,
    hours_since_last: float,
    surf_result: dict,
    initial_reason: str,
    now_dt: Optional[datetime] = None,
) -> ProactiveDecision:
    """把后端实际冲浪结果交给渡，让渡基于素材做最终主动决策。"""
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    channels = _available_channels()
    default_channel = _preferred_proactive_channel(channels)
    channel_lines = "\n".join(f'  - "{ch}"' for ch in channels)
    if channels and default_channel:
        channel_field_desc = (
            f'- channel：固定填 "{default_channel}"。本轮主动唤醒固定使用这个入口生成和发送，'
            "不要在其它入口之间切换。\n"
            f"{channel_lines}\n"
        )
    else:
        channel_field_desc = '- channel：当前没有可用发送入口；不要选择 "send_message"。\n'
    now_ref = now_dt or parse_iso_to_beijing(now_beijing_iso()) or datetime.now()
    user_prompt = (
        "你刚才选择了随机冲浪，后端已经实际调用 du_surf，并把结果交给你。\n"
        "现在请基于这些素材做最终决定。不要再调用 du_surf，也不要只说“我去冲浪”。\n"
        f"{_describe_recent_exchange(now_ref)} 从系统节流角度看，距最近一次真实互动大约 {hours_since_last:.1f} 小时。\n"
        f"你刚才选择冲浪的理由：{str(initial_reason or '').strip() or '（未说明）'}\n\n"
        f"{_format_proactive_surf_result_for_du(surf_result)}\n\n"
        "你必须用 **一个 JSON 对象** 回复，不要用 markdown 代码块包裹，不要其它说明文字。字段如下：\n"
        '- action：字符串，必须是 "send_message" | "no_contact" | "diary" | "forum" | "drawer" | "other" 之一。不要再填 "surf"。\n'
        '- reason：字符串，简短说明你为什么这么选（必填）。\n'
        '- message：字符串；当 action 为 send_message 时，填要发给她的正文；其它 action 时可为空或填补充说明。\n'
        + channel_field_desc
        + (
            f'示例：{{"action":"no_contact","reason":"素材只是自己看过就好，暂时不打扰她","message":"","channel":"{default_channel}"}}\n'
            if default_channel
            else f'示例：{{"action":"no_contact","reason":"当前没有可用发送入口","message":"","channel":""}}\n'
        )
    )
    body = {
        "model": _get_chat_model(),
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
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
            "主动随机冲浪结果回喂请求 window_id=%s model=%s cards=%s",
            window_id,
            body.get("model") or "",
            len(surf_result.get("cards_for_du") or []) if isinstance(surf_result, dict) else 0,
        )
        r = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
        if r.status_code != 200:
            logger.warning(
                "主动随机冲浪结果回喂失败 status=%s body_preview=%s",
                r.status_code,
                (r.text or "")[:300],
            )
            return ProactiveDecision(
                False,
                "",
                f"surf_followup_status={r.status_code}",
                action="no_contact",
                du_reason=f"随机冲浪结果已拿到，但回喂决策失败 HTTP {r.status_code}，本轮先不打扰。",
                channel=default_channel,
            )
        data = r.json() if r.content else None
        msg = (data or {}).get("choices") and (data.get("choices") or [{}])[0].get("message") or {}
        content = (msg or {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        if not text:
            return ProactiveDecision(
                False,
                "",
                "surf_followup_empty",
                action="no_contact",
                du_reason="随机冲浪结果已拿到，但回喂后模型空回复，本轮先不打扰。",
                channel=default_channel,
            )
        decision = _parse_proactive_model_reply(text, TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN.strip() or "NO_CONTACT", default_channel=default_channel, channels=channels)
        if (decision.action or "").strip().lower() == "surf":
            return ProactiveDecision(
                False,
                "",
                "surf_followup_repeat_surf",
                action="no_contact",
                du_reason="已经把随机冲浪结果看过了，模型仍要求继续 surf；本轮先不重复冲浪。",
                channel=default_channel,
            )
        if decision.should_send and default_channel:
            decision.channel = default_channel
        return decision
    except Exception as e:
        return ProactiveDecision(
            False,
            "",
            f"surf_followup_exception={e}",
            action="no_contact",
            du_reason=f"随机冲浪结果已拿到，但回喂决策异常：{str(e)[:160]}",
            channel=default_channel,
        )


def _try_spring_dream_wakeup(window_id: str, uid: int, now_dt: datetime, now_iso: str) -> dict | None:
    try:
        prepared = maybe_prepare_spring_dream_wakeup(now_dt=now_dt)
    except Exception as e:
        logger.warning("春梦唤醒准备失败，继续普通随机主动决策 window_id=%s error=%s", window_id, e)
        return None
    if not prepared:
        return None
    prompt = str(prepared.get("prompt") or "").strip()
    if not prompt:
        try:
            release_spring_dream_slot(prepared)
        except Exception as e:
            logger.warning("春梦唤醒 prompt 为空后释放预占名额失败 session=%s error=%s", str(prepared.get("sleep_session_key") or ""), e)
        return None
    result = send_spring_dream_wakeup(
        window_id=window_id,
        target=str(uid or "").strip(),
        event_text=prompt,
        created_at=now_iso,
        archive_meta={
            "sleep_session_key": str(prepared.get("sleep_session_key") or ""),
            "theme_id": str(prepared.get("theme_id") or ""),
            "fragments": prepared.get("fragments") or [],
            "sleep_source": str(prepared.get("sleep_source") or ""),
            "roll": prepared.get("roll"),
            "threshold": prepared.get("threshold"),
            "miss_count_before": int(prepared.get("miss_count_before") or 0),
            "count_before": int(prepared.get("count_before") or 0),
            "count_after": int(prepared.get("count_after") or 0),
            "max_per_sleep": int(prepared.get("max_per_sleep") or 0),
        },
    )
    ok = bool((result or {}).get("ok"))
    stored = False
    if not ok:
        try:
            release_spring_dream_slot(prepared)
        except Exception as e:
            logger.warning("春梦唤醒失败后释放预占名额失败 session=%s error=%s", str(prepared.get("sleep_session_key") or ""), e)
        logger.warning(
            "春梦唤醒发送失败，继续普通随机主动决策 window_id=%s error=%s",
            window_id,
            str((result or {}).get("error") or ""),
        )
        return None
    try:
        stored = record_spring_dream_sent(prepared, sent_at=now_iso)
    except Exception as e:
        stored = False
        logger.warning("春梦唤醒已发送但记录发送时间失败 window_id=%s error=%s", window_id, e)
    archive_ok = bool((result or {}).get("archive_ok", True))
    if not archive_ok:
        logger.warning("春梦唤醒已投递但归档失败 window_id=%s channel=%s", window_id, str((result or {}).get("channel") or ""))
    return {
        "ok": ok,
        "sent": ok,
        "wake_mode": "spring_dream",
        "spring_dream": {
            "triggered": True,
            "stored": stored,
            "archive_ok": archive_ok,
            "body_archive_ok": bool((result or {}).get("spring_dream_archive_ok", True)),
            "body_archive_id": str((result or {}).get("spring_dream_archive_id") or ""),
            "body_archive_r2_key": str((result or {}).get("spring_dream_archive_r2_key") or ""),
            "theme_id": str(prepared.get("theme_id") or ""),
            "sleep_source": str(prepared.get("sleep_source") or ""),
            "roll": prepared.get("roll"),
            "threshold": prepared.get("threshold"),
            "miss_count_before": int(prepared.get("miss_count_before") or 0),
            "count": int(prepared.get("count_after") or 0) if ok else int(prepared.get("count_before") or 0),
            "max_per_sleep": int(prepared.get("max_per_sleep") or 0),
        },
        "channel": str((result or {}).get("channel") or ""),
        "reply_preview": str((result or {}).get("reply_preview") or ""),
        "error": str((result or {}).get("error") or ""),
    }


def _try_post_spring_dream_wakeup(window_id: str, uid: int, now_dt: datetime, now_iso: str) -> dict | None:
    try:
        prepared = maybe_prepare_post_spring_dream_wakeup(now_dt=now_dt)
    except Exception as e:
        logger.warning("春梦后唤醒准备失败，继续普通随机主动决策 window_id=%s error=%s", window_id, e)
        return None
    if not prepared:
        return None
    prompt = str(prepared.get("prompt") or "").strip()
    if not prompt:
        return None
    result = send_post_spring_dream_wakeup(
        window_id=window_id,
        target=str(uid or "").strip(),
        event_text=prompt,
        created_at=now_iso,
    )
    ok = bool((result or {}).get("ok"))
    stored = False
    if ok:
        try:
            stored = record_post_spring_dream_wakeup_sent(prepared, sent_at=now_iso)
        except Exception as e:
            stored = False
            logger.warning("春梦后唤醒已发送但清除待触发状态失败 window_id=%s error=%s", window_id, e)
    archive_ok = bool((result or {}).get("archive_ok", True))
    if ok and not archive_ok:
        logger.warning("春梦后唤醒已投递但归档失败 window_id=%s channel=%s", window_id, str((result or {}).get("channel") or ""))
    if not ok:
        logger.warning(
            "春梦后唤醒发送失败，本轮不继续普通随机主动决策 window_id=%s error=%s",
            window_id,
            str((result or {}).get("error") or ""),
        )
    return {
        "ok": ok,
        "sent": ok,
        "wake_mode": "post_spring_dream",
        "post_spring_dream": {
            "triggered": True,
            "stored": stored,
            "archive_ok": archive_ok,
            "sleep_source": str(prepared.get("sleep_source") or ""),
            "last_spring_dream_sent_at": str(prepared.get("last_spring_dream_sent_at") or ""),
        },
        "channel": str((result or {}).get("channel") or ""),
        "reply_preview": str((result or {}).get("reply_preview") or ""),
        "error": str((result or {}).get("error") or ""),
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
    post_spring_dream_result = _try_post_spring_dream_wakeup(window_id, uid, now_dt, now_iso)
    if post_spring_dream_result:
        out.update(post_spring_dream_result)
        if bool(post_spring_dream_result.get("sent")):
            r2_store.save_last_proactive_contact_at(now_iso)
        return out

    spring_dream_result = _try_spring_dream_wakeup(window_id, uid, now_dt, now_iso)
    if spring_dream_result:
        out.update(spring_dream_result)
        if bool(spring_dream_result.get("sent")):
            r2_store.save_last_proactive_contact_at(now_iso)
        return out

    decision = _ask_du_should_contact(window_id=window_id, hours_since_last=hours, now_dt=now_dt)
    out["du_reason"] = decision.reason
    out["du_action"] = decision.action
    out["du_intent_reason"] = decision.du_reason
    surf_summary = None
    initial_surf_reason = ""
    forum_summary = None
    initial_forum_reason = ""
    diary_summary = None
    initial_diary_reason = ""
    drawer_summary = None
    initial_drawer_reason = ""
    if (decision.action or "").strip().lower() == "surf":
        initial_surf_reason = (decision.du_reason or decision.reason or "").strip()
        surf_summary = _run_proactive_surf_action()
        out["surf"] = surf_summary
        followup_decision = _ask_du_after_surf_result(
            window_id=window_id,
            hours_since_last=hours,
            surf_result=surf_summary,
            initial_reason=initial_surf_reason,
            now_dt=now_dt,
        )
        out["du_initial_action"] = "surf"
        out["du_initial_reason"] = initial_surf_reason
        out["du_action_after_surf"] = followup_decision.action
        out["du_reason_after_surf"] = followup_decision.reason
        out["du_intent_reason_after_surf"] = followup_decision.du_reason
        decision = followup_decision
        out["du_reason"] = decision.reason
        out["du_action"] = decision.action
        out["du_intent_reason"] = decision.du_reason
    if (decision.action or "").strip().lower() == "forum" and not forum_summary:
        initial_forum_reason = (decision.du_reason or decision.reason or "").strip()
        forum_summary = _run_proactive_forum_action(
            window_id=window_id,
            hours_since_last=hours,
            initial_reason=initial_forum_reason,
            now_dt=now_dt,
        )
        out["forum"] = forum_summary
        if not surf_summary:
            out["du_initial_action"] = "forum"
            out["du_initial_reason"] = initial_forum_reason
        out["forum_execution_ok"] = bool((forum_summary or {}).get("ok"))
    if (decision.action or "").strip().lower() == "diary" and not diary_summary:
        initial_diary_reason = (decision.du_reason or decision.reason or "").strip()
        diary_summary = _run_proactive_diary_action(
            window_id=window_id,
            hours_since_last=hours,
            initial_reason=initial_diary_reason,
            now_dt=now_dt,
        )
        out["diary"] = diary_summary
        if not surf_summary:
            out["du_initial_action"] = "diary"
            out["du_initial_reason"] = initial_diary_reason
        out["diary_execution_ok"] = bool((diary_summary or {}).get("ok"))
    if (decision.action or "").strip().lower() == "drawer" and not drawer_summary:
        initial_drawer_reason = (decision.du_reason or decision.reason or "").strip()
        drawer_summary = _run_proactive_drawer_action(
            window_id=window_id,
            hours_since_last=hours,
            initial_reason=initial_drawer_reason,
            now_dt=now_dt,
        )
        out["drawer"] = drawer_summary
        if not surf_summary:
            out["du_initial_action"] = "drawer"
            out["du_initial_reason"] = initial_drawer_reason
        out["drawer_execution_ok"] = bool((drawer_summary or {}).get("ok"))

    # 随机唤醒主动决策：记下本轮决策（闹钟不走这里）
    try:
        pv = ""
        if decision.text and decision.text.strip():
            s = decision.text.strip()
            pv = s[:120] + ("…" if len(s) > 120 else "")
        act_store = (decision.action or "").strip() or (
            "send_message" if decision.should_send else (decision.reason or "unknown")
        )
        if surf_summary:
            act_store = f"surf->{act_store}"
        if forum_summary:
            forum_act = "forum->executed" if forum_summary.get("ok") else "forum->failed"
            act_store = f"surf->{forum_act}" if surf_summary else forum_act
        if diary_summary:
            diary_act = "diary->executed" if diary_summary.get("ok") else "diary->failed"
            act_store = f"surf->{diary_act}" if surf_summary else diary_act
        if drawer_summary:
            drawer_act = "drawer->executed" if drawer_summary.get("ok") else "drawer->failed"
            act_store = f"surf->{drawer_act}" if surf_summary else drawer_act
        reason_store = (decision.du_reason or decision.reason or "").strip() or "—"
        if surf_summary:
            topic = str(surf_summary.get("topic") or "").strip()
            count = int(surf_summary.get("count") or 0)
            titles = [str(x or "").strip() for x in (surf_summary.get("titles") or []) if str(x or "").strip()]
            if surf_summary.get("ok"):
                surf_note = f"已实际冲浪并回喂给渡：{topic or '随机话题'}，拿到 {count} 张卡片"
                if initial_surf_reason:
                    surf_note = f"最初想冲浪：{initial_surf_reason}；{surf_note}"
                reason_store = f"{surf_note}；看完后的决定：{reason_store}"
                if titles and not pv:
                    pv = "；".join(titles)[:120]
            else:
                reason_store = f"实际冲浪失败：{str(surf_summary.get('error') or 'unknown')[:80]}；最终决定：{reason_store}"
        if forum_summary:
            reply_preview = str(forum_summary.get("reply_preview") or "").strip()
            if forum_summary.get("ok"):
                reason_store = (
                    f"最初想逛论坛：{initial_forum_reason or '（未说明）'}；"
                    f"已追加执行轮提醒渡去逛论坛。"
                )
                if surf_summary:
                    reason_store = f"先冲浪后决定逛论坛；{reason_store}"
                if reply_preview:
                    pv = reply_preview[:120]
            else:
                reason_store = (
                    f"最初想逛论坛：{initial_forum_reason or '（未说明）'}；"
                    f"追加执行轮失败：{str(forum_summary.get('error') or 'unknown')[:80]}"
                )
                if surf_summary:
                    reason_store = f"先冲浪后决定逛论坛；{reason_store}"
                if reply_preview and not pv:
                    pv = reply_preview[:120]
        if diary_summary:
            reply_preview = str(diary_summary.get("reply_preview") or "").strip()
            if diary_summary.get("ok"):
                reason_store = (
                    f"最初想写日记：{initial_diary_reason or '（未说明）'}；"
                    f"已追加执行轮提醒渡去写。"
                )
                if surf_summary:
                    reason_store = f"先冲浪后决定写日记；{reason_store}"
                if reply_preview:
                    pv = reply_preview[:120]
            else:
                reason_store = (
                    f"最初想写日记：{initial_diary_reason or '（未说明）'}；"
                    f"追加执行轮失败：{str(diary_summary.get('error') or 'unknown')[:80]}"
                )
                if surf_summary:
                    reason_store = f"先冲浪后决定写日记；{reason_store}"
                if reply_preview and not pv:
                    pv = reply_preview[:120]
        if drawer_summary:
            reply_preview = str(drawer_summary.get("reply_preview") or "").strip()
            if drawer_summary.get("ok"):
                reason_store = (
                    f"最初想整理秘密抽屉：{initial_drawer_reason or '（未说明）'}；"
                    f"已追加执行轮提醒渡去整理/翻旧条目。"
                )
                if surf_summary:
                    reason_store = f"先冲浪后决定整理秘密抽屉；{reason_store}"
                if reply_preview:
                    pv = reply_preview[:120]
            else:
                reason_store = (
                    f"最初想整理秘密抽屉：{initial_drawer_reason or '（未说明）'}；"
                    f"追加执行轮失败：{str(drawer_summary.get('error') or 'unknown')[:80]}"
                )
                if surf_summary:
                    reason_store = f"先冲浪后决定整理秘密抽屉；{reason_store}"
                if reply_preview and not pv:
                    pv = reply_preview[:120]
        r2_store.append_proactive_decision_memory(
            {
                "at": now_iso,
                "action": act_store,
                "reason": reason_store,
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


async def run_scheduler_loop_async():
    """Async wrapper kept for callers; execution still uses the direct state-index scheduler."""
    await asyncio.to_thread(run_scheduler_loop)


def _scheduler_source_id(uid: int) -> str:
    return str(int(uid or 0) or 0)


def _ensure_scheduler_state(kind: str, source_id: str, due_at: str, payload: dict | None = None) -> None:
    row = wakeup_state.get_state(kind, source_id)
    if row and str(row.get("next_due_at") or "").strip():
        return
    wakeup_state.upsert_state(
        kind=kind,
        source_id=source_id,
        next_due_at=due_at,
        status=wakeup_state.STATUS_SCHEDULED,
        payload=payload,
    )


def _state_status(result: dict, fired: bool) -> str:
    if not bool((result or {}).get("ok", False)) or str((result or {}).get("error") or "").strip():
        return wakeup_state.STATUS_ERROR
    if fired:
        return wakeup_state.STATUS_FIRED
    return wakeup_state.STATUS_CHECKED


def _result_fired(kind: str, result: dict) -> bool:
    if kind == wakeup_state.KIND_SCHEDULE:
        return int((result or {}).get("sent") or 0) > 0
    if kind == wakeup_state.KIND_DU_DAILY_SLEEP:
        return bool((result or {}).get("triggered"))
    return bool((result or {}).get("sent"))


def _ensure_scheduler_states(
    *,
    uid: int,
    source_id: str,
    schedule_enabled: bool,
    proactive_enabled: bool,
    schedule_interval_s: int,
) -> None:
    now_iso = now_beijing_iso()
    if schedule_enabled:
        _ensure_scheduler_state(
            wakeup_state.KIND_SCHEDULE,
            source_id,
            now_iso,
            {"interval_seconds": schedule_interval_s},
        )
    if proactive_enabled:
        _ensure_scheduler_state(
            wakeup_state.KIND_FOLLOWUP,
            source_id,
            now_iso,
            {"interval_seconds": max(15, int(FOLLOWUP_TICK_SECONDS or 60))},
        )
        _ensure_scheduler_state(
            wakeup_state.KIND_HARD_TRIGGER,
            source_id,
            now_iso,
            {"interval_seconds": 60},
        )
        _ensure_scheduler_state(
            wakeup_state.KIND_DU_DAILY_SLEEP,
            source_id,
            now_iso,
            {"interval_seconds": 300},
        )
        delay = _next_proactive_delay_seconds()
        _ensure_scheduler_state(
            wakeup_state.KIND_RANDOM_PROACTIVE,
            source_id,
            _iso_after_seconds(delay),
            {"delay_seconds": delay, "reason": "startup"},
        )
        logger.info("下一次随机主动唤醒 scheduled_in=%.1fmin", delay / 60.0)


def _run_due_state(kind: str, uid: int, source_id: str, schedule_interval_s: int) -> None:
    label = {
        wakeup_state.KIND_SCHEDULE: "日历闹钟",
        wakeup_state.KIND_FOLLOWUP: "延迟续话",
        wakeup_state.KIND_HARD_TRIGGER: "主动硬触发",
        wakeup_state.KIND_DU_DAILY_SLEEP: "渡的日常入睡收口",
        wakeup_state.KIND_RANDOM_PROACTIVE: "主动发消息",
    }.get(kind, kind)
    next_seconds = 60
    result: dict = {"ok": False, "error": f"unknown_wakeup_state_kind:{kind}"}
    try:
        if kind == wakeup_state.KIND_SCHEDULE:
            next_seconds = schedule_interval_s
            result = schedule_tick(uid)
        elif kind == wakeup_state.KIND_FOLLOWUP:
            next_seconds = max(15, int(FOLLOWUP_TICK_SECONDS or 60))
            result = tick_conversation_followups()
        elif kind == wakeup_state.KIND_HARD_TRIGGER:
            from services.proactive_trigger_engine import tick_proactive_triggers

            next_seconds = 60
            result = tick_proactive_triggers(uid)
            if bool((result or {}).get("sent")):
                post_delay = _next_post_hard_trigger_delay_seconds()
                wakeup_state.upsert_state(
                    kind=wakeup_state.KIND_RANDOM_PROACTIVE,
                    source_id=source_id,
                    next_due_at=_iso_after_seconds(post_delay),
                    status=wakeup_state.STATUS_SCHEDULED,
                    payload={"delay_seconds": post_delay, "reason": "after_hard_trigger"},
                )
                logger.info("硬触发已发出，下一次随机主动唤醒重排 scheduled_in=%.1fmin", post_delay / 60.0)
        elif kind == wakeup_state.KIND_DU_DAILY_SLEEP:
            next_seconds = 300
            result = du_daily_sleep_tick(uid)
        elif kind == wakeup_state.KIND_RANDOM_PROACTIVE:
            result = proactive_tick(uid)
            next_seconds = _next_proactive_delay_seconds()
            logger.info("下一次随机主动唤醒 scheduled_in=%.1fmin", next_seconds / 60.0)
    except Exception as e:
        logger.exception("%s tick 异常: %s", label, e)
        result = {"ok": False, "error": str(e)}
    fired = _result_fired(kind, result)
    next_due_at = _iso_after_seconds(next_seconds)
    status = _state_status(result, fired)
    wakeup_state.record_result(
        kind=kind,
        source_id=source_id,
        result=result if isinstance(result, dict) else {"ok": False, "error": "invalid_result"},
        next_due_at=next_due_at,
        status=status,
        fired=fired,
    )
    logger.info("%s tick result=%s next_due_at=%s state_status=%s", label, result, next_due_at, status)


def _sleep_for_state_index(active_kinds: list[str], source_id: str) -> None:
    wait = wakeup_state.seconds_until_next(kinds=active_kinds, source_id=source_id)
    if wait is None:
        time.sleep(15)
        return
    time.sleep(max(1.0, min(15.0, wait)))


def _state_due_now(kind: str, source_id: str) -> bool:
    row = wakeup_state.get_state(kind, source_id)
    if not row:
        return False
    due_dt = parse_iso_to_beijing(str(row.get("next_due_at") or "").strip())
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    return bool(due_dt and now_dt and due_dt <= now_dt)


def run_scheduler_loop():
    """常驻循环：只用 wakeup_state 判断时间；业务触发仍走原有直接函数。"""
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
        "主动调度进程启动 proactive_enabled=%s legacy_interval_min=%s random_window=%s-%smin schedule_enabled=%s schedule_interval_s=%s target_user_id=%s state_index=enabled queue_execution=removed",
        proactive_enabled,
        interval_min,
        random_min,
        random_max,
        schedule_enabled,
        schedule_interval_s,
        uid,
    )
    source_id = _scheduler_source_id(uid)
    active_kinds: list[str] = []
    if schedule_enabled:
        active_kinds.append(wakeup_state.KIND_SCHEDULE)
    if proactive_enabled:
        active_kinds.extend(
            [
                wakeup_state.KIND_FOLLOWUP,
                wakeup_state.KIND_HARD_TRIGGER,
                wakeup_state.KIND_DU_DAILY_SLEEP,
                wakeup_state.KIND_RANDOM_PROACTIVE,
            ]
        )
    _ensure_scheduler_states(
        uid=uid,
        source_id=source_id,
        schedule_enabled=schedule_enabled,
        proactive_enabled=proactive_enabled,
        schedule_interval_s=schedule_interval_s,
    )
    while True:
        due = wakeup_state.list_due_states(kinds=active_kinds, source_id=source_id, limit=10)
        if not due:
            _sleep_for_state_index(active_kinds, source_id)
            continue
        for row in due:
            kind = str(row.get("kind") or "").strip()
            if kind not in active_kinds:
                continue
            if not _state_due_now(kind, source_id):
                continue
            _run_due_state(kind, uid, source_id, schedule_interval_s)
