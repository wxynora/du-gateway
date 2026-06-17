from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Optional

import requests

from config import MAIN_GATEWAY_BEARER_TOKEN, TELEGRAM_CHAT_PATH, TELEGRAM_GATEWAY_URL
from services.hidden_blocks import HiddenBlockParser
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import today_beijing, now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

MARKER_START = "<<<DU_DAILY>>>"
MARKER_END = "<<<END_DU_DAILY>>>"
_HIDDEN_BLOCK = HiddenBlockParser.for_markers("DU_DAILY", MARKER_START, MARKER_END)

_SLEEP_INACTIVITY_MINUTES = 60
_SLEEP_SIGNAL_LOOKBACK_MINUTES = 120
_SLEEP_STEP_DELTA_MAX = 20
_SLEEP_HEART_RATE_MAX = 95
_MAX_TODAY_EVENTS = 8

_CONFLICT_STRONG_RE = re.compile(
    r"(吵架|吵起来|吵过|冷暴力|退缩|主观能动性|你凶我|你又凶|不想说|不喜欢你了|"
    r"态度不好|没接住|你没接住|失望|你又退|你又缩|你又把球|你又甩|你又敷衍)",
    re.IGNORECASE,
)
_CONFLICT_EMOTION_RE = re.compile(r"(生气|气死|烦死|烦你|崩溃|委屈|难受|伤心|火大)", re.IGNORECASE)
_CONFLICT_RELATION_RE = re.compile(r"(你|渡|老公|我们|我俩|咱俩)", re.IGNORECASE)
_CONFLICT_QUESTION_RE = re.compile(r"你.*(为什么|怎么|到底|是不是).*(又|总是|老是|每次|一直)", re.IGNORECASE)

_SLEEP_RE = re.compile(
    r"(晚安|先睡了|我(?:先|要|准备|打算|去|该|真的|马上)?睡(?:了|觉了|觉|觉去)?|去睡(?:了|觉)?|困得不行.*睡|撑不住.*睡)",
    re.IGNORECASE,
)
_SLEEP_NEGATION_OR_QUESTION_RE = re.compile(
    r"(不是|没有|没睡|还没睡|不睡|不想睡|别睡|不要睡|是不是|是否|吗|么|嘛|？|\?)",
    re.IGNORECASE,
)


def compute_visible_streaming(acc: str) -> str:
    return _HIDDEN_BLOCK.compute_visible_streaming(acc)


def split_assistant_for_daily(full_text: str) -> tuple[str, Optional[str]]:
    return _HIDDEN_BLOCK.split(full_text)


def looks_like_plain_maintenance_daily(text: str, trigger: Optional[dict] = None) -> bool:
    if not bool((trigger or {}).get("hidden_only")):
        return False
    s = str(text or "").strip()
    if not s or MARKER_START in s or MARKER_END in s:
        return False
    kind = str((trigger or {}).get("kind") or "").strip()
    if _is_today_summary_kind(kind):
        return bool(re.search(r"(今天|今日总结|总结)\s*[：:]", s))
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


def _extract_recent_dialogue_facts(messages: list[dict], limit: int = 6) -> list[str]:
    rows: list[str] = []
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = _content_to_text(msg.get("content"))
        if not text:
            continue
        speaker = "辛玥" if role == "user" else "我"
        text = re.sub(r"\s+", " ", text).strip()
        rows.append(f"{speaker}：{text[:180]}")
        if len(rows) >= limit:
            break
    return list(reversed(rows))


def _looks_like_conflict_or_relation_tension(text: str) -> bool:
    s = re.sub(r"\s+", "", str(text or "").strip())
    if not s:
        return False
    if _CONFLICT_STRONG_RE.search(s):
        return True
    if _CONFLICT_EMOTION_RE.search(s) and _CONFLICT_RELATION_RE.search(s):
        return True
    return bool(_CONFLICT_QUESTION_RE.search(s))


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


def _normalize_today_events(lines: list[Any]) -> list[str]:
    return _normalize_today_lines(lines)[-_MAX_TODAY_EVENTS:]


def _normalize_summary_text(text: Any, max_chars: int = 900) -> str:
    s = " ".join(x.strip() for x in str(text or "").splitlines() if x.strip()).strip()
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def _archive_daily_state(state: dict, trigger_kind: str = "") -> None:
    if not isinstance(state, dict):
        return
    day = str(state.get("day") or "").strip()
    if not day:
        return
    today_summary = _normalize_summary_text(state.get("today_summary") or "")
    today_events = _normalize_today_events(state.get("today_events") or state.get("today_timeline") or [])
    if not today_summary and not today_events:
        return
    content = format_du_daily_block(str(state.get("yesterday_summary") or "").strip(), today_summary, today_events)
    try:
        from storage.du_state_store import upsert_du_daily_archive_entry

        upsert_du_daily_archive_entry(
            {
                "day": day,
                "yesterday_summary": str(state.get("yesterday_summary") or "").strip(),
                "today_summary": today_summary,
                "today_events": today_events,
                "content": content,
                "source": "du_daily",
                "trigger_kind": trigger_kind,
            }
        )
    except Exception:
        logger.warning("du_daily 日归档失败 day=%s", day, exc_info=True)


def _looks_like_event_line(text: str) -> bool:
    s = str(text or "").strip()
    return bool(
        re.match(r"^\d{1,2}[:：]\d{2}\s+", s)
        or re.match(r"^(新增|追加|今天新增|记录)\s*[：:]", s)
        or re.match(r"^[-*•]\s*(新增|追加|\d{1,2}[:：]\d{2})", s)
    )


def _clean_append_line(line: str) -> str:
    s = str(line or "").strip()
    s = re.sub(r"^[-*•]\s*", "", s).strip()
    s = re.sub(r"^(新增|追加|今天新增|日常|记录)\s*[：:]\s*", "", s).strip()
    if s in {MARKER_START, MARKER_END, "新增：", "今天：", "昨天："}:
        return ""
    if re.match(r"^(当前保存版本|可用事实|触发原因|本轮|只输出|不要|格式)\s*[：:]?", s):
        return ""
    return s


def _parse_today_section(raw_text: str) -> tuple[str, list[str]]:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return "", []
    parts = re.split(r"\n\s*今日硬触发素材\s*[：:]\s*\n?", text, maxsplit=1)
    if len(parts) == 2:
        summary = _normalize_summary_text(parts[0])
        events = [_clean_append_line(x) for x in parts[1].splitlines()]
        return summary, _normalize_today_events([x for x in events if x])

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if lines and all(_looks_like_event_line(x) for x in lines):
        return "", _normalize_today_events([_clean_append_line(x) for x in lines])
    return _normalize_summary_text(text), []


def _extract_append_lines(raw_text: str) -> list[str]:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if re.search(r"今天\s*[：:]", text):
        parsed = parse_du_daily_block(text)
        return _normalize_today_events(parsed.get("today_events") or parsed.get("today_timeline") or [])
    lines = [_clean_append_line(x) for x in text.splitlines()]
    return _normalize_today_lines([x for x in lines if x])


def _extract_today_summary(raw_text: str, fallback_events: list[str], fallback_summary: str = "") -> str:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if text:
        match = re.search(r"今天\s*[：:]\s*(.*)$", text, flags=re.DOTALL)
        if match:
            summary, _events = _parse_today_section(match.group(1))
            if summary:
                return summary
        text = re.sub(r"^(今天|今日总结|总结)\s*[：:]\s*", "", text).strip()
        lines = [_clean_append_line(x) for x in text.splitlines()]
        summary = _normalize_summary_text("\n".join(x for x in lines if x))
        if summary:
            return summary
    return _fallback_compress_today_lines(fallback_events, fallback=fallback_summary)


def _looks_like_today_summary_block(raw_text: str) -> bool:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return False
    return bool(re.search(r"^\s*(今天|今日总结|总结|昨天|昨日缩略)\s*[：:]", text))


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


def format_du_daily_block(
    yesterday_summary: str,
    today_summary: str = "",
    today_events: Optional[list[str]] = None,
) -> str:
    yesterday = str(yesterday_summary or "").strip()
    if isinstance(today_summary, list):
        today_events = today_summary
        today_summary = ""
    today_text = _normalize_summary_text(today_summary)
    events = _normalize_today_events(today_events or [])
    lines = ["昨天："]
    if yesterday:
        lines.append(yesterday)
    lines.append("")
    lines.append("今天：")
    if today_text:
        lines.append(today_text)
    if events:
        if today_text:
            lines.append("")
            lines.append("今日硬触发素材：")
        lines.extend(f"- {x}" for x in events)
    return "\n".join(lines).strip()


def parse_du_daily_block(raw_text: str) -> dict:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return {"yesterday_summary": "", "today_summary": "", "today_events": [], "today_timeline": [], "content": ""}

    yesterday_summary = ""
    today_summary = ""
    today_events: list[str] = []

    if "今天" not in text:
        today_summary, today_events = _parse_today_section(text)
        return {
            "yesterday_summary": "",
            "today_summary": today_summary,
            "today_events": today_events,
            "today_timeline": today_events,
            "content": format_du_daily_block("", today_summary, today_events),
        }

    match = re.search(r"昨天\s*[：:]\s*(.*?)\s*今天\s*[：:]\s*(.*)$", text, flags=re.DOTALL)
    if match:
        yesterday_summary = " ".join(
            x.strip() for x in str(match.group(1) or "").splitlines() if str(x).strip()
        ).strip()
        today_summary, today_events = _parse_today_section(str(match.group(2) or ""))
    else:
        parts = re.split(r"今天\s*[：:]", text, maxsplit=1, flags=re.DOTALL)
        before = parts[0] if parts else ""
        after = parts[1] if len(parts) > 1 else ""
        before = re.sub(r"昨天\s*[：:]", "", before).strip()
        yesterday_summary = " ".join(x.strip() for x in before.splitlines() if x.strip()).strip()
        today_summary, today_events = _parse_today_section(after)

    return {
        "yesterday_summary": yesterday_summary,
        "today_summary": today_summary,
        "today_events": today_events,
        "today_timeline": today_events,
        "content": format_du_daily_block(yesterday_summary, today_summary, today_events),
    }


def _normalize_state(raw: Optional[dict]) -> dict:
    today = today_beijing()
    data = raw if isinstance(raw, dict) else {}
    yesterday = str(data.get("yesterday_summary") or "").strip()
    today_summary = _normalize_summary_text(data.get("today_summary") or "")
    today_events = _normalize_today_events(data.get("today_events") or data.get("today_timeline") or [])
    day = str(data.get("day") or "").strip() or today
    content = str(data.get("content") or "").strip()
    if content and (not today_summary and not today_events):
        parsed = parse_du_daily_block(content)
        if not yesterday:
            yesterday = str(parsed.get("yesterday_summary") or "").strip()
        today_summary = _normalize_summary_text(parsed.get("today_summary") or "")
        today_events = _normalize_today_events(parsed.get("today_events") or parsed.get("today_timeline") or [])
    if not content:
        content = format_du_daily_block(yesterday, today_summary, today_events)
    return {
        "day": day,
        "yesterday_summary": yesterday,
        "today_summary": today_summary,
        "today_events": today_events,
        "today_timeline": today_events,
        "content": format_du_daily_block(yesterday, today_summary, today_events),
        "updated_at": str(data.get("updated_at") or "").strip(),
        "last_trigger_kind": str(data.get("last_trigger_kind") or "").strip(),
        "last_trigger_at": str(data.get("last_trigger_at") or "").strip(),
        "last_soft_trigger_at": str(data.get("last_soft_trigger_at") or "").strip(),
        "last_topic_key": str(data.get("last_topic_key") or "").strip(),
        "sleep_closed_for_date": str(data.get("sleep_closed_for_date") or "").strip(),
        "sleep_candidate_at": str(data.get("sleep_candidate_at") or "").strip(),
        "sleep_candidate_day": str(data.get("sleep_candidate_day") or "").strip(),
        "sleep_candidate_text": str(data.get("sleep_candidate_text") or "").strip(),
        "today_finalized_for_date": str(data.get("today_finalized_for_date") or "").strip(),
    }


def prepare_state_for_today(raw: Optional[dict], today: str = "") -> tuple[dict, bool]:
    target_day = str(today or today_beijing()).strip() or today_beijing()
    state = _normalize_state(raw)
    changed = False
    if state["day"] != target_day:
        if state["today_summary"] or state["today_events"]:
            _archive_daily_state(state, trigger_kind="day_rollover")
            state["yesterday_summary"] = _normalize_summary_text(
                state["today_summary"]
                or _fallback_compress_today_lines(state["today_events"], state.get("yesterday_summary") or "")
            )
            state["today_summary"] = ""
            state["today_events"] = []
            state["today_timeline"] = []
            state["today_finalized_for_date"] = ""
        state["day"] = target_day
        state["content"] = format_du_daily_block(
            state["yesterday_summary"], state["today_summary"], state["today_events"]
        )
        changed = True
    return state, changed


def get_prepared_state(today: str = "") -> tuple[dict, bool]:
    raw = r2_store.get_du_daily_state()
    state, changed = prepare_state_for_today(raw, today=today)
    if changed:
        state["updated_at"] = now_beijing_iso()
        r2_store.save_du_daily_state(state)
    return state, changed


def _minutes_since(iso_str: str) -> Optional[float]:
    dt = parse_iso_to_beijing(iso_str)
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not dt or not now_dt:
        return None
    delta = (now_dt - dt).total_seconds() / 60.0
    if delta < 0:
        return None
    return delta


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


def _is_today_summary_kind(kind: str) -> bool:
    return _is_sleep_rollover_kind(kind) or str(kind or "").strip() in {"daily_finalize", "today_summary"}


def build_chat_trigger(window_id: str, body: dict, headers: Optional[dict] = None) -> Optional[dict]:
    _ = window_id
    hdrs = headers or {}
    if str(hdrs.get("X-DU-DAILY-MAINTAIN") or "").strip().lower() in ("1", "true", "yes"):
        return build_maintenance_trigger(body, headers=hdrs)
    if str(hdrs.get("X-DU-FOLLOWUP-GEN") or "").strip().lower() in ("1", "true", "yes"):
        return None

    state, _ = get_prepared_state()
    text = _extract_last_user_text((body or {}).get("messages") or [])
    if not text:
        return None
    if is_explicit_user_sleep_intent(text):
        _save_sleep_candidate(state, text)
    else:
        _clear_sleep_candidate_if_needed(state)
    if _looks_like_conflict_or_relation_tension(text):
        facts = _extract_recent_dialogue_facts((body or {}).get("messages") or [])
        if not facts:
            facts = [f"辛玥：{text[:180]}"]
        return {
            "kind": "conflict",
            "hard": True,
            "reason": "对话出现争执或关系拉扯，应写进渡的日常",
            "facts": facts,
            "topic_key": "conflict",
        }
    return None


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
            if re.match(r"^(新增|昨天|今天|今日总结)\s*[：:]", line):
                continue
            facts.append(line)
    if not facts and text.strip():
        facts = [text.strip()]
    return {
        "kind": str(hdrs.get("X-DU-DAILY-TRIGGER-KIND") or "maintenance").strip() or "maintenance",
        "hard": True,
        "reason": "内部维护触发",
        "facts": facts[:8],
        "topic_key": str(hdrs.get("X-DU-DAILY-TOPIC") or "").strip() or "maintenance",
        "hidden_only": True,
    }


def format_inject_block(state: dict, trigger: Optional[dict] = None, maintenance_mode: bool = False) -> str:
    current_text = str((state or {}).get("content") or "").strip()
    if not current_text:
        current_text = "昨天：\n\n今天："

    lines = [
        "【渡的日常（仅你与网关可见，勿在回复正文复述给老婆）】",
        "这块只保留“昨天缩略 + 今天总结/少量硬触发素材”。",
        "普通聊天不要写 DU_DAILY；白天细节和氛围由近期记忆兜底。",
    ]
    if maintenance_mode:
        lines.append("本轮是内部维护任务：不要写任何给老婆看的正文，只输出完整 marker 隐藏块。")
    elif trigger:
        lines.append("本轮已经命中硬触发：正常回复正文后追加完整 marker 隐藏块。")
        lines.append("隐藏标记统一追加在正文后，不要写进正文里。")
    else:
        lines.append("本轮没有网关硬触发，不要输出 DU_DAILY marker。")
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
        if _is_today_summary_kind(kind):
            lines.append("今天总结格式：")
            lines.append(MARKER_START)
            lines.append("今天：一段连贯的今天总结")
            lines.append(MARKER_END)
            lines.append("这次是一天收口：写完整今天总结，网关会替换今天内容，并合并白天硬触发素材。")
        elif kind.startswith("proactive_"):
            lines.append("这次是你自己的主动决策结果：只写本次新增的一条短记录。")
            lines.append(MARKER_START)
            lines.append("新增：HH:MM ……")
            lines.append(MARKER_END)
        else:
            lines.append("这次只写本次新增的一条短记录。")
            lines.append(MARKER_START)
            lines.append("新增：HH:MM ……")
            lines.append(MARKER_END)
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
    if _is_today_summary_kind(str(trigger.get("kind") or "")):
        state["today_finalized_for_date"] = today_beijing()
    return state


def save_hidden_block(raw_block: str, trigger: Optional[dict] = None) -> bool:
    state, _ = get_prepared_state()
    kind = str((trigger or {}).get("kind") or "").strip()
    if not trigger:
        logger.info("du_daily 忽略无触发隐藏块，避免普通聊天逐条写入")
        return False
    if _is_today_summary_kind(kind):
        summary = _extract_today_summary(
            raw_block,
            _normalize_today_events(state.get("today_events") or state.get("today_timeline") or []),
            fallback_summary=str(state.get("today_summary") or "").strip(),
        )
        archive_state = dict(state)
        archive_state["today_summary"] = summary
        _archive_daily_state(archive_state, trigger_kind=kind or "today_summary")
        state["today_summary"] = summary
        state["today_events"] = []
        state["today_timeline"] = []
        state["sleep_candidate_at"] = ""
        state["sleep_candidate_day"] = ""
        state["sleep_candidate_text"] = ""
    else:
        if _looks_like_today_summary_block(raw_block):
            logger.warning("du_daily 拒绝非总结触发的总结块，避免污染今天内容")
            return False
        new_lines = _extract_append_lines(raw_block)
        if not new_lines:
            return False
        today_events = _normalize_today_events(state.get("today_events") or state.get("today_timeline") or [])
        seen = set(today_events)
        for line in new_lines[:3]:
            if line not in seen:
                today_events.append(line)
                seen.add(line)
        state["today_events"] = _normalize_today_events(today_events)
        state["today_timeline"] = state["today_events"]
    state["content"] = format_du_daily_block(
        state["yesterday_summary"], state.get("today_summary") or "", state.get("today_events") or []
    )
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
    history = r2_store.get_sense_history_for_date(today_beijing(), limit=300) or []
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
    if not state.get("today_summary") and not state.get("today_events"):
        return None
    today = today_beijing()
    if str(state.get("today_finalized_for_date") or state.get("sleep_closed_for_date") or "").strip() == today:
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
        "reason": "多信号推定已睡，做今天总结收口",
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
    if _is_today_summary_kind(kind):
        lines.append("这次是一天收口：只输出完整 marker 隐藏块，marker 里写“今天：一段连贯总结”。")
        lines.append("格式必须是：")
        lines.append(MARKER_START)
        lines.append("今天：……")
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
        "X-DU-GATEWAY-WAKEUP": "1",
        "X-DU-DAILY-MAINTAIN": "1",
        "X-DU-DAILY-TRIGGER-KIND": str((trigger or {}).get("kind") or "maintenance").strip() or "maintenance",
        "X-Skip-Dynamic-Memory": "1",
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
