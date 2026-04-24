from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, Optional

import requests

from config import MAIN_GATEWAY_BEARER_TOKEN, TELEGRAM_CHAT_PATH, TELEGRAM_GATEWAY_URL
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import today_beijing, now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

MARKER_START = "<<<DU_DAILY>>>"
MARKER_END = "<<<END_DU_DAILY>>>"

_SOFT_TRIGGER_COOLDOWN_MINUTES = 45
_SOFT_TRIGGER_MIN_GAP_MINUTES = 20
_HARD_RECONNECT_GAP_MINUTES = 90
_TOPIC_DEDUPE_MINUTES = 180
_SLEEP_INACTIVITY_MINUTES = 60
_SLEEP_SIGNAL_LOOKBACK_MINUTES = 120
_SLEEP_STEP_DELTA_MAX = 20
_SLEEP_HEART_RATE_MAX = 95

_SLEEP_RE = re.compile(
    r"(晚安|先睡了|我(?:先|要|准备|打算|去|该|真的|马上)?睡(?:了|觉了|觉|觉去)?|去睡(?:了|觉)?|困得不行.*睡|撑不住.*睡)",
    re.IGNORECASE,
)
_SLEEP_NEGATION_OR_QUESTION_RE = re.compile(
    r"(不是|没有|没睡|还没睡|不睡|不想睡|别睡|不要睡|是不是|是否|吗|么|嘛|？|\?)",
    re.IGNORECASE,
)
_WAKE_RE = re.compile(r"(醒了|刚醒|起床了|睡醒了)", re.IGNORECASE)
_ALARM_RE = re.compile(r"(闹钟|到点了|醒来第一件事|提醒)", re.IGNORECASE)
_CONFLICT_RE = re.compile(r"(吵架|生气|别扭|闹掰|委屈|不开心)", re.IGNORECASE)
_RECONCILE_RE = re.compile(r"(和好|讲开了|哄好了|不生气了|没事了|不吵了)", re.IGNORECASE)
_BUG_SOLVED_RE = re.compile(r"(修好了|修好|解决了|通了|好了你试试|再试试|fix了)", re.IGNORECASE)
_BUG_PENDING_RE = re.compile(r"(待验证|待测|帮我测|你试试|再试下|测试一下)", re.IGNORECASE)
_BUG_FOUND_RE = re.compile(r"(bug|报错|有问题|坏了|崩了|不对劲|出错)", re.IGNORECASE)
_DEEP_TALK_RE = re.compile(r"(我想说|我在想|其实|认真|关系|害怕|难过|委屈|喜欢|爱你|重要)", re.IGNORECASE)
_DAILY_SOFT_RE = re.compile(r"(论坛|日记|气泡|拉肚子|生理期|温水|通宵|上班|下班|功能|测试|吃饭|睡|醒)", re.IGNORECASE)

_TOPIC_KEYWORDS = (
    ("sleep", _SLEEP_RE),
    ("wake", _WAKE_RE),
    ("alarm", _ALARM_RE),
    ("conflict", _CONFLICT_RE),
    ("reconcile", _RECONCILE_RE),
    ("bug_solved", _BUG_SOLVED_RE),
    ("bug_pending", _BUG_PENDING_RE),
    ("bug", _BUG_FOUND_RE),
    ("deep_talk", _DEEP_TALK_RE),
    ("daily", _DAILY_SOFT_RE),
)


def compute_visible_streaming(acc: str) -> str:
    if not acc:
        return ""
    if MARKER_START not in acc:
        return acc
    i = acc.find(MARKER_START)
    if MARKER_END not in acc:
        return acc[:i].rstrip()
    rest = acc[i + len(MARKER_START) :]
    j = rest.find(MARKER_END)
    if j < 0:
        return acc[:i].rstrip()
    after = rest[j + len(MARKER_END) :]
    return acc[:i] + after


def split_assistant_for_daily(full_text: str) -> tuple[str, Optional[str]]:
    if not full_text or not isinstance(full_text, str):
        return full_text or "", None
    if MARKER_START not in full_text:
        return full_text, None
    if MARKER_END not in full_text:
        i = full_text.find(MARKER_START)
        return full_text[:i].rstrip(), None
    pattern = re.escape(MARKER_START) + r"\s*(.*?)\s*" + re.escape(MARKER_END)
    match = re.search(pattern, full_text, flags=re.DOTALL)
    if not match:
        i = full_text.find(MARKER_START)
        return full_text[:i].rstrip(), None
    content = (match.group(1) or "").strip()
    visible = full_text[: match.start()] + full_text[match.end() :]
    return visible.strip(), content if content else None


def looks_like_plain_maintenance_daily(text: str, trigger: Optional[dict] = None) -> bool:
    if not bool((trigger or {}).get("hidden_only")):
        return False
    s = str(text or "").strip()
    if not s or MARKER_START in s or MARKER_END in s:
        return False
    kind = str((trigger or {}).get("kind") or "").strip()
    if _is_sleep_rollover_kind(kind):
        return bool(re.search(r"(昨天|昨日缩略|总结)\s*[：:]", s))
    return bool(re.search(r"(新增|今天)\s*[：:]", s) or re.match(r"^\d{1,2}[:：]\d{2}\s+", s))


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if str(item.get("type") or "").strip() == "text":
                    parts.append(str(item.get("text") or ""))
                else:
                    parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(x.strip() for x in parts if str(x).strip()).strip()
    return str(content).strip()


def _extract_last_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() != "user":
            continue
        return _content_to_text(msg.get("content"))
    return ""


def is_explicit_user_sleep_intent(text: str) -> bool:
    s = re.sub(r"\s+", "", str(text or "").strip())
    if not s:
        return False
    if _SLEEP_NEGATION_OR_QUESTION_RE.search(s):
        return False
    return bool(_SLEEP_RE.search(s))


def _strip_time_prefix(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"^\d{1,2}[:：]\d{2}\s*", "", s)
    s = re.sub(r"^\d{1,2}\s*[ap]\.?m\.?\s*", "", s, flags=re.IGNORECASE)
    return s.strip("：: ").strip()


def _current_hm() -> str:
    match = re.search(r"T(\d{2}:\d{2})", now_beijing_iso())
    return match.group(1) if match else ""


def _normalize_today_lines(lines: list[Any]) -> list[str]:
    out: list[str] = []
    for item in lines or []:
        s = str(item or "").strip()
        if s:
            out.append(s)
    return out


def _clean_append_line(line: str) -> str:
    s = str(line or "").strip()
    s = re.sub(r"^[-*•]\s*", "", s).strip()
    s = re.sub(r"^(新增|追加|今天新增|日常|记录)\s*[：:]\s*", "", s).strip()
    if s in {MARKER_START, MARKER_END, "新增：", "今天：", "昨天："}:
        return ""
    if re.match(r"^(当前保存版本|可用事实|触发原因|本轮|只输出|不要|格式)\s*[：:]?", s):
        return ""
    return s


def _extract_append_lines(raw_text: str) -> list[str]:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if re.search(r"今天\s*[：:]", text):
        parsed = parse_du_daily_block(text)
        return _normalize_today_lines(parsed.get("today_timeline") or [])
    lines = [_clean_append_line(x) for x in text.splitlines()]
    return _normalize_today_lines([x for x in lines if x])


def _extract_sleep_summary(raw_text: str, fallback_lines: list[str], fallback_summary: str = "") -> str:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if text:
        match = re.search(r"昨天\s*[：:]\s*(.*?)(?:\n\s*今天\s*[：:]|\Z)", text, flags=re.DOTALL)
        if match:
            summary = " ".join(x.strip() for x in match.group(1).splitlines() if x.strip()).strip()
            if summary:
                return summary
        text = re.sub(r"^(昨天|昨日缩略|总结)\s*[：:]\s*", "", text).strip()
        lines = [_clean_append_line(x) for x in text.splitlines()]
        summary = " ".join(x for x in lines if x).strip()
        if summary:
            return summary
    return _fallback_compress_today_lines(fallback_lines, fallback=fallback_summary)


def _fallback_compress_today_lines(lines: list[str], fallback: str = "") -> str:
    cleaned = [_strip_time_prefix(x) for x in (lines or []) if _strip_time_prefix(x)]
    if not cleaned:
        return str(fallback or "").strip()
    if len(cleaned) == 1:
        return cleaned[0]
    picked = cleaned[-3:]
    summary = "；".join(picked).strip("； ").strip()
    if summary and not summary.endswith(("。", "！", "？")):
        summary += "。"
    return summary


def format_du_daily_block(yesterday_summary: str, today_lines: list[str]) -> str:
    yesterday = str(yesterday_summary or "").strip()
    today = _normalize_today_lines(today_lines)
    lines = ["昨天："]
    if yesterday:
        lines.append(yesterday)
    lines.append("")
    lines.append("今天：")
    if today:
        lines.extend(today)
    return "\n".join(lines).strip()


def parse_du_daily_block(raw_text: str) -> dict:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return {"yesterday_summary": "", "today_timeline": [], "content": ""}

    yesterday_summary = ""
    today_lines: list[str] = []

    if "今天" not in text:
        today_lines = _normalize_today_lines([x for x in text.split("\n") if str(x).strip()])
        return {
            "yesterday_summary": "",
            "today_timeline": today_lines,
            "content": format_du_daily_block("", today_lines),
        }

    match = re.search(r"昨天\s*[：:]\s*(.*?)\s*今天\s*[：:]\s*(.*)$", text, flags=re.DOTALL)
    if match:
        yesterday_summary = " ".join(
            x.strip() for x in str(match.group(1) or "").splitlines() if str(x).strip()
        ).strip()
        today_lines = _normalize_today_lines(str(match.group(2) or "").splitlines())
    else:
        parts = re.split(r"今天\s*[：:]", text, maxsplit=1, flags=re.DOTALL)
        before = parts[0] if parts else ""
        after = parts[1] if len(parts) > 1 else ""
        before = re.sub(r"昨天\s*[：:]", "", before).strip()
        yesterday_summary = " ".join(x.strip() for x in before.splitlines() if x.strip()).strip()
        today_lines = _normalize_today_lines(after.splitlines())

    return {
        "yesterday_summary": yesterday_summary,
        "today_timeline": today_lines,
        "content": format_du_daily_block(yesterday_summary, today_lines),
    }


def _normalize_state(raw: Optional[dict]) -> dict:
    today = today_beijing()
    data = raw if isinstance(raw, dict) else {}
    yesterday = str(data.get("yesterday_summary") or "").strip()
    today_lines = _normalize_today_lines(data.get("today_timeline") or [])
    day = str(data.get("day") or "").strip() or today
    content = str(data.get("content") or "").strip()
    if not content:
        content = format_du_daily_block(yesterday, today_lines)
    return {
        "day": day,
        "yesterday_summary": yesterday,
        "today_timeline": today_lines,
        "content": content,
        "updated_at": str(data.get("updated_at") or "").strip(),
        "last_trigger_kind": str(data.get("last_trigger_kind") or "").strip(),
        "last_trigger_at": str(data.get("last_trigger_at") or "").strip(),
        "last_soft_trigger_at": str(data.get("last_soft_trigger_at") or "").strip(),
        "last_topic_key": str(data.get("last_topic_key") or "").strip(),
        "sleep_closed_for_date": str(data.get("sleep_closed_for_date") or "").strip(),
        "sleep_candidate_at": str(data.get("sleep_candidate_at") or "").strip(),
        "sleep_candidate_day": str(data.get("sleep_candidate_day") or "").strip(),
        "sleep_candidate_text": str(data.get("sleep_candidate_text") or "").strip(),
    }


def prepare_state_for_today(raw: Optional[dict], today: str = "") -> tuple[dict, bool]:
    target_day = str(today or today_beijing()).strip() or today_beijing()
    state = _normalize_state(raw)
    changed = False
    if state["day"] != target_day:
        if state["today_timeline"]:
            state["yesterday_summary"] = _fallback_compress_today_lines(
                state["today_timeline"], state.get("yesterday_summary") or ""
            )
            state["today_timeline"] = []
        state["day"] = target_day
        state["content"] = format_du_daily_block(state["yesterday_summary"], state["today_timeline"])
        changed = True
    return state, changed


def get_prepared_state(today: str = "") -> tuple[dict, bool]:
    raw = r2_store.get_du_daily_state()
    state, changed = prepare_state_for_today(raw, today=today)
    if changed:
        state["updated_at"] = now_beijing_iso()
        r2_store.save_du_daily_state(state)
    return state, changed


def _extract_topic_key(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    for key, pattern in _TOPIC_KEYWORDS:
        if pattern.search(raw):
            return key
    short = re.sub(r"\s+", " ", raw).strip()
    if len(short) > 24:
        short = short[:24]
    return short


def _minutes_since(iso_str: str) -> Optional[float]:
    dt = parse_iso_to_beijing(iso_str)
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not dt or not now_dt:
        return None
    delta = (now_dt - dt).total_seconds() / 60.0
    if delta < 0:
        return None
    return delta


def _last_round_gap_minutes(window_id: str) -> Optional[float]:
    rounds = r2_store.get_conversation_rounds(window_id, last_n=1) or []
    if not rounds or not isinstance(rounds[0], dict):
        return None
    return _minutes_since(str(rounds[0].get("timestamp") or "").strip())


def _in_soft_cooldown(state: dict) -> bool:
    last_iso = str(state.get("last_soft_trigger_at") or state.get("updated_at") or "").strip()
    gap = _minutes_since(last_iso)
    return gap is not None and gap < _SOFT_TRIGGER_COOLDOWN_MINUTES


def _save_sleep_candidate(state: dict, text: str) -> None:
    state["sleep_candidate_at"] = now_beijing_iso()
    state["sleep_candidate_day"] = today_beijing()
    state["sleep_candidate_text"] = str(text or "").strip()[:160]
    state["updated_at"] = now_beijing_iso()
    try:
        r2_store.save_du_daily_state(state)
    except Exception:
        logger.warning("保存睡眠候选失败", exc_info=True)


def _clear_sleep_candidate_if_needed(state: dict) -> None:
    if not any(state.get(k) for k in ("sleep_candidate_at", "sleep_candidate_day", "sleep_candidate_text")):
        return
    state["sleep_candidate_at"] = ""
    state["sleep_candidate_day"] = ""
    state["sleep_candidate_text"] = ""
    try:
        r2_store.save_du_daily_state(state)
    except Exception:
        logger.warning("清理睡眠候选失败", exc_info=True)


def _is_sleep_rollover_kind(kind: str) -> bool:
    return str(kind or "").strip() in {"sleep_inferred", "sleep_rollover"}


def build_chat_trigger(window_id: str, body: dict, headers: Optional[dict] = None) -> Optional[dict]:
    hdrs = headers or {}
    if str(hdrs.get("X-DU-DAILY-MAINTAIN") or "").strip().lower() in ("1", "true", "yes"):
        return build_maintenance_trigger(body, headers=hdrs)
    if str(hdrs.get("X-DU-FOLLOWUP-GEN") or "").strip().lower() in ("1", "true", "yes"):
        return None

    state, _ = get_prepared_state()
    text = _extract_last_user_text((body or {}).get("messages") or [])
    if not text:
        return None
    gap_minutes = _last_round_gap_minutes(window_id)
    topic_key = _extract_topic_key(text)
    facts: list[str] = []
    if gap_minutes is not None:
        facts.append(f"距离上一轮大约 {int(gap_minutes)} 分钟。")

    if is_explicit_user_sleep_intent(text):
        _save_sleep_candidate(state, text)
        return {
            "kind": "sleep_candidate",
            "hard": True,
            "reason": "用户明确说准备睡觉，先记为睡眠候选，不做一天收口",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "sleep_candidate",
            "hidden_only": False,
        }
    _clear_sleep_candidate_if_needed(state)
    if _ALARM_RE.search(text) and ("到点" in text or "闹钟" in text):
        return {
            "kind": "alarm",
            "hard": True,
            "reason": "闹钟/提醒触发",
            "facts": facts + [f"当前提醒内容：{text[:120]}"],
            "topic_key": "alarm",
            "hidden_only": False,
        }
    if _WAKE_RE.search(text):
        return {
            "kind": "wake",
            "hard": True,
            "reason": "用户明确说醒了",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "wake",
            "hidden_only": False,
        }
    if gap_minutes is not None and gap_minutes >= _HARD_RECONNECT_GAP_MINUTES:
        return {
            "kind": "reconnect",
            "hard": True,
            "reason": "隔很久后重新联系",
            "facts": facts + [f"当前这句：{text[:120]}"],
            "topic_key": topic_key or "reconnect",
            "hidden_only": False,
        }
    if _RECONCILE_RE.search(text):
        return {
            "kind": "reconcile",
            "hard": True,
            "reason": "关系状态切换到和好/讲开",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "reconcile",
            "hidden_only": False,
        }
    if _CONFLICT_RE.search(text):
        return {
            "kind": "conflict",
            "hard": True,
            "reason": "关系状态切换到争执/委屈",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "conflict",
            "hidden_only": False,
        }
    if _BUG_SOLVED_RE.search(text):
        return {
            "kind": "bug_solved",
            "hard": True,
            "reason": "问题解决或让她复测",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "bug_solved",
            "hidden_only": False,
        }
    if _BUG_PENDING_RE.search(text):
        return {
            "kind": "bug_pending",
            "hard": True,
            "reason": "问题进入待验证/待测试",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "bug_pending",
            "hidden_only": False,
        }
    if _BUG_FOUND_RE.search(text):
        return {
            "kind": "bug_found",
            "hard": True,
            "reason": "发现 bug / 报错 / 问题",
            "facts": facts + [f"用户原话：{text[:120]}"],
            "topic_key": "bug",
            "hidden_only": False,
        }
    if len(text) >= 120 and _DEEP_TALK_RE.search(text):
        return {
            "kind": "deep_talk",
            "hard": True,
            "reason": "聊了比较深的话",
            "facts": facts + [f"用户原话：{text[:180]}"],
            "topic_key": "deep_talk",
            "hidden_only": False,
        }

    if _in_soft_cooldown(state):
        return None
    if topic_key and topic_key == str(state.get("last_topic_key") or "").strip():
        last_gap = _minutes_since(str(state.get("last_trigger_at") or "").strip())
        if last_gap is not None and last_gap < _TOPIC_DEDUPE_MINUTES:
            return None

    soft_ready = False
    soft_reason = ""
    if gap_minutes is not None and gap_minutes >= _SOFT_TRIGGER_MIN_GAP_MINUTES and len(text) >= 10:
        soft_ready = True
        soft_reason = "隔了一阵又往前聊了一段"
    elif len(text) >= 45 or "\n" in text:
        soft_ready = True
        soft_reason = "这一段对话足够形成一句生活推进"
    elif len(text) >= 12 and _DAILY_SOFT_RE.search(text):
        soft_ready = True
        soft_reason = "出现了适合补进日常的一小段生活推进"

    if not soft_ready:
        return None
    return {
        "kind": "soft_progress",
        "hard": False,
        "reason": soft_reason,
        "facts": facts + [f"用户原话：{text[:120]}"],
        "topic_key": topic_key or "soft_progress",
        "hidden_only": False,
    }


def build_maintenance_trigger(body: dict, headers: Optional[dict] = None) -> dict:
    hdrs = headers or {}
    text = _extract_last_user_text((body or {}).get("messages") or [])
    facts = []
    raw_lines = [x.strip() for x in text.splitlines() if x.strip()]
    for line in raw_lines:
        if line.startswith("-"):
            facts.append(line.lstrip("- ").strip())
    if not facts:
        for line in raw_lines:
            if line.startswith("这是一次内部维护"):
                continue
            if line.startswith("你现在只需要更新"):
                continue
            if line.startswith("只输出隐藏块"):
                continue
            if line.startswith("当前北京时间"):
                continue
            if line.startswith("这次是"):
                continue
            if line.startswith("格式必须是"):
                continue
            if line.startswith("不要输出"):
                continue
            if line in {MARKER_START, MARKER_END}:
                continue
            if re.match(r"^(新增|昨天)\s*[：:]", line):
                continue
            facts.append(line)
    if not facts and text.strip():
        facts = [text.strip()]
    return {
        "kind": str(hdrs.get("X-DU-DAILY-TRIGGER-KIND") or "maintenance").strip() or "maintenance",
        "hard": True,
        "reason": "内部维护触发",
        "facts": facts[:8],
        "topic_key": str(hdrs.get("X-DU-DAILY-TOPIC") or "").strip() or _extract_topic_key(text),
        "hidden_only": True,
    }


def format_inject_block(state: dict, trigger: Optional[dict] = None, maintenance_mode: bool = False) -> str:
    current_text = str((state or {}).get("content") or "").strip()
    if not current_text:
        current_text = "昨天：\n\n今天："

    lines = [
        "【渡的日常（仅你与网关可见，勿在回复正文复述给老婆）】",
        "你有一块隐藏滚动记忆，始终只保留“昨天缩略 + 今天的时间线”。",
        "写法边界：可以写我的观察、判断、挂念、打算；不替她写内心独白、动机或未发生事实。",
        "网关会负责保存和追加；普通更新时你只写本次新增的一条，不要从头重写旧时间线。",
        "普通更新格式：",
        MARKER_START,
        "新增：07:30 ……",
        MARKER_END,
        "睡眠收口格式：",
        MARKER_START,
        "昨天：一小段昨天缩略",
        MARKER_END,
    ]
    if maintenance_mode:
        lines.append("本轮是内部维护任务：不要写任何给老婆看的正文，只输出完整 marker 隐藏块。")
    elif trigger:
        lines.append("本轮已经命中更新：请正常回复正文后，再在末尾追加完整 marker 隐藏块。")
    else:
        lines.append("本轮未命中更新：不要输出这个隐藏块。")
    if trigger:
        lines.append(f"触发原因：{str(trigger.get('reason') or '').strip() or '—'}")
        hm = _current_hm()
        if hm:
            lines.append(f"当前北京时间约 {hm}。")
        facts = trigger.get("facts") or []
        if isinstance(facts, list) and facts:
            lines.append("可用事实：")
            for item in facts[:8]:
                s = str(item or "").strip()
                if s:
                    lines.append(f"- {s}")
        kind = str(trigger.get("kind") or "").strip()
        if _is_sleep_rollover_kind(kind):
            lines.append("这次是一天收口：只在 marker 里写“昨天：一句缩略总结”，网关会清空今天。")
        elif kind.startswith("proactive_"):
            lines.append("这次是你自己的主动决策结果：只写本次新增的一条，网关会追加到今天。")
        else:
            lines.append("这次只写本次新增的一条，网关会追加到今天。")
    lines.append("当前保存版本：")
    lines.append(current_text)
    return "\n".join(lines).strip()


def _apply_trigger_metadata(state: dict, trigger: Optional[dict]) -> dict:
    now_iso = now_beijing_iso()
    state["updated_at"] = now_iso
    if not trigger:
        return state
    state["last_trigger_kind"] = str(trigger.get("kind") or "").strip()
    state["last_trigger_at"] = now_iso
    topic_key = str(trigger.get("topic_key") or "").strip()
    if topic_key:
        state["last_topic_key"] = topic_key
    if not bool(trigger.get("hard")):
        state["last_soft_trigger_at"] = now_iso
    if _is_sleep_rollover_kind(str(trigger.get("kind") or "")):
        state["sleep_closed_for_date"] = today_beijing()
    return state


def save_hidden_block(raw_block: str, trigger: Optional[dict] = None) -> bool:
    state, _ = get_prepared_state()
    kind = str((trigger or {}).get("kind") or "").strip()
    if _is_sleep_rollover_kind(kind):
        summary = _extract_sleep_summary(
            raw_block,
            _normalize_today_lines(state.get("today_timeline") or []),
            fallback_summary=str(state.get("yesterday_summary") or "").strip(),
        )
        state["yesterday_summary"] = summary
        state["today_timeline"] = []
        state["sleep_candidate_at"] = ""
        state["sleep_candidate_day"] = ""
        state["sleep_candidate_text"] = ""
    else:
        new_lines = _extract_append_lines(raw_block)
        if not new_lines:
            return False
        today_lines = _normalize_today_lines(state.get("today_timeline") or [])
        seen = set(today_lines)
        for line in new_lines[:3]:
            if line not in seen:
                today_lines.append(line)
                seen.add(line)
        state["today_timeline"] = today_lines
    state["content"] = format_du_daily_block(state["yesterday_summary"], state["today_timeline"])
    state = _apply_trigger_metadata(state, trigger)
    return bool(r2_store.save_du_daily_state(state))


def _sense_bucket_dt(bucket: dict) -> Optional[object]:
    if not isinstance(bucket, dict):
        return None
    for key in ("occurredAt", "observedAt", "capturedAt", "updatedAt"):
        dt = parse_iso_to_beijing(str(bucket.get(key) or "").strip())
        if dt:
            return dt
    return None


def _extract_recent_health_stats(now_dt) -> tuple[Optional[int], Optional[int]]:
    history = r2_store.get_sense_history_for_date(today_beijing()) or []
    floor_dt = now_dt - timedelta(minutes=_SLEEP_SIGNAL_LOOKBACK_MINUTES)
    steps: list[int] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "health":
            continue
        event_dt = parse_iso_to_beijing(str(item.get("at") or "").strip())
        if not event_dt or event_dt < floor_dt:
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        try:
            step_val = int(data.get("steps"))
        except Exception:
            step_val = None
        if step_val is not None:
            steps.append(step_val)
    if len(steps) >= 2:
        return max(steps) - min(steps), steps[-1]
    if len(steps) == 1:
        return None, steps[0]
    return None, None


def infer_sleep_rollover_trigger() -> Optional[dict]:
    state, _ = get_prepared_state()
    if not state.get("today_timeline"):
        return None
    today = today_beijing()
    if str(state.get("sleep_closed_for_date") or "").strip() == today:
        return None
    candidate_iso = str(state.get("sleep_candidate_at") or "").strip()
    candidate_text = str(state.get("sleep_candidate_text") or "").strip()
    if str(state.get("sleep_candidate_day") or "").strip() != today or not candidate_iso:
        return None
    candidate_minutes = _minutes_since(candidate_iso)
    candidate_dt = parse_iso_to_beijing(candidate_iso)
    if candidate_minutes is None or candidate_minutes < _SLEEP_INACTIVITY_MINUTES or not candidate_dt:
        return None

    last_user_iso = r2_store.get_last_telegram_user_activity_at()
    inactive_minutes = _minutes_since(last_user_iso or "")
    if inactive_minutes is None or inactive_minutes < _SLEEP_INACTIVITY_MINUTES:
        return None
    last_user_dt = parse_iso_to_beijing(last_user_iso or "")
    if last_user_dt and last_user_dt > candidate_dt + timedelta(seconds=30):
        return None

    sense = r2_store.get_sense_latest() or {}
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not now_dt:
        return None
    screen = sense.get("screen") if isinstance(sense.get("screen"), dict) else {}
    music = sense.get("music") if isinstance(sense.get("music"), dict) else {}
    health = sense.get("health") if isinstance(sense.get("health"), dict) else {}

    screen_dt = _sense_bucket_dt(screen)
    screen_ok = (
        str(screen.get("event") or "").strip().lower() == "screen_off"
        and screen_dt is not None
        and (now_dt - screen_dt).total_seconds() / 60.0 <= _SLEEP_SIGNAL_LOOKBACK_MINUTES
    )
    if not screen_ok:
        return None

    score = 2
    facts = [
        f"她明确说过准备睡觉：{candidate_text[:120]}" if candidate_text else "她明确说过准备睡觉。",
        f"之后已经大约 {int(inactive_minutes)} 分钟没回复。",
        "手机最近是熄屏状态。",
    ]

    music_dt = _sense_bucket_dt(music)
    if music_dt and (now_dt - music_dt).total_seconds() / 60.0 <= _SLEEP_SIGNAL_LOOKBACK_MINUTES:
        playing = music.get("playing")
        if playing is False or str(playing).strip().lower() in ("false", "0", "no", "off"):
            score += 1
            facts.append("音乐当前没有在播放。")
        elif playing is True or str(playing).strip().lower() in ("true", "1", "yes", "on"):
            return None

    try:
        hr = int(health.get("heart_rate"))
    except Exception:
        hr = None
    if hr is not None:
        if hr <= _SLEEP_HEART_RATE_MAX:
            score += 1
            facts.append(f"最近心率不高，大约 {hr}。")
        else:
            return None

    step_delta, latest_steps = _extract_recent_health_stats(now_dt)
    if step_delta is not None:
        if step_delta <= _SLEEP_STEP_DELTA_MAX:
            score += 1
            facts.append(f"最近一段时间步数变化很小（约 {step_delta} 步）。")
        else:
            return None
    elif latest_steps is not None:
        facts.append(f"当前步数大约 {latest_steps}。")

    if score < 4:
        return None

    return {
        "kind": "sleep_inferred",
        "hard": True,
        "reason": "多信号推定已睡，做当天收口",
        "facts": facts,
        "topic_key": "sleep",
        "hidden_only": True,
    }


def build_background_prompt(trigger: dict) -> str:
    kind = str((trigger or {}).get("kind") or "").strip()
    facts = trigger.get("facts") or []
    lines = [
        "这是一次内部维护，不发给老婆。",
        "你现在只需要更新“渡的日常”这块隐藏滚动记忆，不要写任何可见正文。",
    ]
    hm = _current_hm()
    if hm:
        lines.append(f"当前北京时间约 {hm}。")
    if _is_sleep_rollover_kind(kind):
        lines.append("这次是一天收口：只输出完整 marker 隐藏块，marker 里写“昨天：一句缩略总结”。")
        lines.append("格式必须是：")
        lines.append(MARKER_START)
        lines.append("昨天：……")
        lines.append(MARKER_END)
    else:
        lines.append("这次是一个应写进“今天”的日常推进：只输出完整 marker 隐藏块，marker 里只写本次新增的一条。")
        lines.append("格式必须是：")
        lines.append(MARKER_START)
        lines.append("新增：HH:MM ……")
        lines.append(MARKER_END)
    if isinstance(facts, list) and facts:
        lines.append("可用事实：")
        for item in facts[:8]:
            s = str(item or "").strip()
            if s:
                lines.append(f"- {s}")
    lines.append("不要输出 marker 以外的任何文字。")
    return "\n".join(lines).strip()


def request_gateway_maintenance(window_id: str, trigger: dict) -> bool:
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=True) or "").strip()
    except Exception:
        model = ""
    if not model:
        logger.warning("du_daily maintenance 跳过：当前没有可用模型")
        return False

    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": str(window_id or "").strip(),
        "X-DU-DAILY-MAINTAIN": "1",
        "X-DU-DAILY-TRIGGER-KIND": str((trigger or {}).get("kind") or "maintenance").strip() or "maintenance",
        "X-Force-Last4": "1",
    }
    topic_key = str((trigger or {}).get("topic_key") or "").strip()
    if topic_key:
        headers["X-DU-DAILY-TOPIC"] = topic_key
    if MAIN_GATEWAY_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {MAIN_GATEWAY_BEARER_TOKEN}"
    body = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": build_background_prompt(trigger)}],
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=180)
        if resp.status_code != 200:
            logger.warning("du_daily maintenance 失败 status=%s body=%s", resp.status_code, (resp.text or "")[:300])
            return False
        try:
            data = resp.json()
            msg = ((data.get("choices") or [{}])[0].get("message") or {}) if isinstance(data, dict) else {}
            leftover = _content_to_text(msg.get("content")) if isinstance(msg, dict) else ""
            if leftover.strip():
                logger.warning("du_daily maintenance 未被隐藏块消费，疑似未保存 content=%s", leftover[:200])
                return False
        except Exception:
            logger.warning("du_daily maintenance 响应解析失败，无法确认是否保存", exc_info=True)
            return False
        return True
    except Exception:
        logger.warning("du_daily maintenance 调网关异常", exc_info=True)
        return False
