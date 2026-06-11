from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any

from storage import r2_store
from storage.pixel_home_store import get_pixel_home_state, save_pixel_home_state
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

PIXEL_HOME_MARKER_START = "<<<PIXEL_HOME>>>"
PIXEL_HOME_MARKER_END = "<<<END_PIXEL_HOME>>>"
PIXEL_HOME_MARKER_RE = re.compile(
    re.escape(PIXEL_HOME_MARKER_START) + r"\s*([\s\S]*?)\s*" + re.escape(PIXEL_HOME_MARKER_END),
    re.IGNORECASE,
)

PIXEL_HOME_DAY_START_HOUR = 6
PIXEL_HOME_NIGHT_START_HOUR = 18
PIXEL_HOME_SLEEP_SCREEN_OFF_MINUTES = 45
PIXEL_HOME_SCREEN_LOOKBACK_MINUTES = 12 * 60
PIXEL_HOME_AWAKE_SCREEN_LOOKBACK_MINUTES = 30

SPOT_LABELS: dict[str, str] = {
    "bed": "卧室",
    "bath": "浴室",
    "study": "书房",
    "sofa": "客厅沙发",
    "kitchen": "厨房",
    "away": "离家出走",
    "out": "外出",
}
SPOT_ALIASES: dict[str, str] = {
    "bed": "bed",
    "卧室": "bed",
    "床": "bed",
    "bedroom": "bed",
    "bath": "bath",
    "bathroom": "bath",
    "浴室": "bath",
    "洗手间": "bath",
    "study": "study",
    "书房": "study",
    "书桌": "study",
    "sofa": "sofa",
    "客厅": "sofa",
    "沙发": "sofa",
    "客厅沙发": "sofa",
    "kitchen": "kitchen",
    "厨房": "kitchen",
    "away": "away",
    "home": "away",
    "离家出走": "away",
    "out": "out",
    "outside": "out",
    "外出": "out",
    "出门": "out",
}
SPOT_OPTIONS = [{"key": key, "label": label} for key, label in SPOT_LABELS.items()]

DEFAULT_DU_STATE = {"spot": "study", "activity": "写日记", "source": "default"}
DEFAULT_XINYUE_STATE = {"spot": "sofa", "activity": "休息", "source": "default"}
PREFIXLESS_SPOTS = {"away", "out"}
DU_DYNAMICS_LIMIT = 5
EVENT_AUTO_END_MINUTES = 120
DU_EVENT_SOURCES = {"du_marker"}
XINYUE_EVENT_SOURCES = {"chat_infer", "miniapp_event", "du_marker_follow"}
_SPOT_WORD_PATTERN = "|".join(sorted((re.escape(key) for key in SPOT_ALIASES if key and not key.isascii()), key=len, reverse=True))
_MOVE_TO_RE = re.compile(rf"(?:回到|走到|走回|来到|坐到|躺到|站到|到|去|回)({_SPOT_WORD_PATTERN})")
_MOVE_FROM_RE = re.compile(rf"^从({_SPOT_WORD_PATTERN})(?:走出|出来|离开|出去)")
_SPOT_CONTEXT_RE = re.compile(
    rf"(?:在|留在|待在|站在|坐在|躺在|靠在|靠着|窝在|蹲在|趴在)({_SPOT_WORD_PATTERN})"
    rf"|({_SPOT_WORD_PATTERN})(?:里|上|边|旁边|旁|附近|门口|那边)"
)
_PERSON_CONTEXT_RE = re.compile(r"(?:她|小玥|老婆|辛玥)(?:面前|身边|旁边|身旁|旁|这边)")
_STALE_SPOT_PREFIX_RE = re.compile(rf"^在({_SPOT_WORD_PATTERN})(.+)$")
_XINYUE_COMPANION_OBJECT_RE = re.compile(
    r"(?:抱着|抱起|搂着|牵着|拉着|拽着|带着|领着|背着|抱住|搂住|牵住|拉住|陪着).{0,12}"
    r"(?:你|小玥|老婆|辛玥|她|我)"
    r"|(?:你|小玥|老婆|辛玥|她).{0,12}(?:被|让|给)?"
    r"(?:抱着|抱起|搂着|牵着|拉着|拽着|带着|领着|背着|抱住|搂住|牵住|拉住|陪着)"
)
_XINYUE_TOGETHER_MOVE_RE = re.compile(
    rf"(?:我们|咱们|一起).{{0,12}}(?:回到|走到|走回|来到|坐到|躺到|站到|到|去|回)({_SPOT_WORD_PATTERN})"
)


def normalize_spot(value: Any, default: str = "away") -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    return SPOT_ALIASES.get(raw, SPOT_ALIASES.get(raw.lower(), default))


def spot_label(spot: Any) -> str:
    key = normalize_spot(spot)
    return SPOT_LABELS.get(key, SPOT_LABELS["away"])


def _clean_activity(value: Any, default: str = "待着") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.replace(PIXEL_HOME_MARKER_START, "").replace(PIXEL_HOME_MARKER_END, "").strip()
    if not text:
        text = default
    return text[:48].strip()


def _resolve_spot_from_activity(spot: str, activity: str, *, reference_spot: str = "") -> str:
    text = _clean_activity(activity, "待着")
    to_match = _MOVE_TO_RE.search(text)
    if to_match:
        return normalize_spot(to_match.group(1), spot)
    stale_prefix = _STALE_SPOT_PREFIX_RE.match(text)
    if reference_spot and stale_prefix and _PERSON_CONTEXT_RE.search(text):
        prefix_spot = normalize_spot(stale_prefix.group(1), "")
        normalized_reference = normalize_spot(reference_spot, "")
        if normalized_reference and prefix_spot != normalized_reference:
            return normalized_reference
    context_spot = _resolve_spot_from_context(text)
    if context_spot:
        return context_spot
    if reference_spot and _PERSON_CONTEXT_RE.search(text):
        return normalize_spot(reference_spot, spot)
    from_match = _MOVE_FROM_RE.search(text)
    if from_match and normalize_spot(from_match.group(1), "") == spot:
        return "away"
    return spot


def _resolve_spot_from_context(text: str) -> str:
    resolved = ""
    for match in _SPOT_CONTEXT_RE.finditer(text):
        word = match.group(1) or match.group(2)
        spot = normalize_spot(word, "")
        if spot:
            resolved = spot
    return resolved


def _strip_stale_spot_prefix(activity: str, spot: str) -> str:
    text = _clean_activity(activity, "待着")
    match = _STALE_SPOT_PREFIX_RE.match(text)
    if not match:
        return text
    prefix_spot = normalize_spot(match.group(1), "")
    if not prefix_spot or prefix_spot == spot:
        return text
    rest = match.group(2).lstrip("，,、。 ：:;；")
    return rest or text


def _activity_has_current_spot_context(activity: str, spot: str) -> bool:
    return bool(spot and (_resolve_spot_from_context(activity) == spot or _PERSON_CONTEXT_RE.search(activity)))


def _now_dt() -> datetime:
    now_iso = now_beijing_iso()
    return parse_iso_to_beijing(now_iso) or datetime.now()


def _minutes_since(value: Any, now_dt: datetime) -> float | None:
    dt = parse_iso_to_beijing(str(value or "").strip())
    if not dt:
        return None
    delta = (now_dt - dt).total_seconds() / 60.0
    if delta < 0:
        return None
    return delta


def _user_after(value: Any) -> bool:
    marker_dt = parse_iso_to_beijing(str(value or "").strip())
    last_user_dt = parse_iso_to_beijing(r2_store.get_last_telegram_user_activity_at() or "")
    if not marker_dt or not last_user_dt:
        return False
    return last_user_dt > marker_dt + timedelta(seconds=30)


def _relevant_sleep_dates(now_dt: datetime) -> set[str]:
    today = now_dt.strftime("%Y-%m-%d")
    if now_dt.hour < PIXEL_HOME_DAY_START_HOUR:
        return {today, (now_dt.date() - timedelta(days=1)).isoformat()}
    return {today}


def _date_hit(value: Any, candidates: set[str]) -> bool:
    raw = str(value or "").strip()
    return bool(raw and raw in candidates)


def _recent_awake_signal(screen: dict, now_dt: datetime) -> bool:
    event = str((screen or {}).get("event") or "").strip().lower()
    interactive = (screen or {}).get("interactive") is True or str((screen or {}).get("interactive") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if event not in {"screen_on", "user_present"} and not (event == "app_active" and interactive):
        return False
    minutes = _minutes_since(
        (screen or {}).get("observedAt") or (screen or {}).get("occurredAt") or (screen or {}).get("lastSeen") or (screen or {}).get("updatedAt"),
        now_dt,
    )
    return minutes is not None and minutes <= PIXEL_HOME_AWAKE_SCREEN_LOOKBACK_MINUTES


def _screen_off_minutes(screen: dict, now_dt: datetime) -> float | None:
    if str((screen or {}).get("event") or "").strip().lower() != "screen_off":
        return None
    since = (screen or {}).get("screenOffSince") or (screen or {}).get("lastScreenOffAt") or (screen or {}).get("occurredAt")
    minutes = _minutes_since(since, now_dt)
    if minutes is not None:
        return minutes if minutes <= PIXEL_HOME_SCREEN_LOOKBACK_MINUTES else None
    try:
        duration_minutes = int((screen or {}).get("screenOffDurationMs") or 0) / 60000
    except Exception:
        duration_minutes = 0
    seen_minutes = _minutes_since((screen or {}).get("observedAt") or (screen or {}).get("lastSeen") or (screen or {}).get("updatedAt"), now_dt)
    if duration_minutes > 0 and seen_minutes is not None and seen_minutes <= PIXEL_HOME_SCREEN_LOOKBACK_MINUTES:
        return duration_minutes
    return None


def _sleeping_state(now_dt: datetime, is_night: bool) -> tuple[bool, str]:
    if not is_night:
        return False, "daytime"
    sense = r2_store.get_sense_latest() or {}
    screen = sense.get("screen") if isinstance(sense.get("screen"), dict) else {}
    if _recent_awake_signal(screen, now_dt):
        return False, "awake_screen"

    candidates = _relevant_sleep_dates(now_dt)
    daily = r2_store.get_du_daily_state() or {}
    trigger_at = str(daily.get("last_trigger_at") or "").strip()
    for key in ("sleep_closed_for_date", "today_finalized_for_date"):
        if _date_hit(daily.get(key), candidates):
            if trigger_at and _user_after(trigger_at):
                return False, "awake_after_sleep"
            return True, key

    candidate_at = str(daily.get("sleep_candidate_at") or "").strip()
    if _date_hit(daily.get("sleep_candidate_day"), candidates) and candidate_at:
        if not _user_after(candidate_at):
            return True, "sleep_candidate"

    screen_off_minutes = _screen_off_minutes(screen, now_dt)
    if screen_off_minutes is not None and screen_off_minutes >= PIXEL_HOME_SLEEP_SCREEN_OFF_MINUTES:
        return True, "screen_off"
    return False, "night_awake"


def build_pixel_home_mode_state() -> dict:
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso) or datetime.now()
    is_night = now_dt.hour >= PIXEL_HOME_NIGHT_START_HOUR or now_dt.hour < PIXEL_HOME_DAY_START_HOUR
    sleeping, source = _sleeping_state(now_dt, is_night)
    mode = "day"
    if is_night:
        mode = "nightOff" if sleeping else "nightOn"
    return {
        "ok": True,
        "mode": mode,
        "is_night": is_night,
        "is_sleeping": sleeping,
        "source": source,
        "updated_at": now_iso,
    }


def mode_label(mode: Any) -> str:
    return {"day": "白天", "nightOn": "夜里开灯", "nightOff": "夜里关灯"}.get(str(mode or ""), "白天")


def _normalize_actor(raw: Any, default: dict, *, force_source: str = "", reference_spot: str = "") -> dict:
    data = raw if isinstance(raw, dict) else {}
    now_iso = now_beijing_iso()
    spot = normalize_spot(data.get("spot") or data.get("location"), str(default.get("spot") or "away"))
    activity = _clean_activity(data.get("activity") or data.get("doing") or data.get("status"), str(default.get("activity") or "待着"))
    spot = _resolve_spot_from_activity(spot, activity, reference_spot=reference_spot)
    source = str(force_source or data.get("source") or default.get("source") or "manual").strip() or "manual"
    updated_at = str(data.get("updated_at") or data.get("updatedAt") or "").strip() or now_iso
    return {"spot": spot, "spot_label": spot_label(spot), "activity": activity, "source": source, "updated_at": updated_at}


def _xinyue_follow_activity_from_du_activity(activity: str) -> str:
    text = _clean_activity(activity, "")
    if re.search(r"(抱着|抱起|抱住|搂着|搂住|背着)", text):
        return "被渡抱着"
    if re.search(r"(牵着|牵住|拉着|拉住|拽着|带着|领着|陪着)", text):
        return "和渡在一起"
    return "和渡在一起"


def _infer_xinyue_follow_state_from_du(actor: dict) -> dict | None:
    """
    渡的 PIXEL_HOME 状态若明确写出“带着小玥一起移动”，同步小玥的小家位置。
    只吃明确共同动作，避免普通“在她旁边/想她”误改小玥状态。
    """
    if not isinstance(actor, dict):
        return None
    spot = normalize_spot(actor.get("spot"), "")
    if not spot:
        return None
    activity = _clean_activity(actor.get("activity"), "")
    if not activity:
        return None
    has_companion_object = bool(_XINYUE_COMPANION_OBJECT_RE.search(activity))
    has_together_move = bool(_XINYUE_TOGETHER_MOVE_RE.search(activity))
    if not has_companion_object and not has_together_move:
        return None
    updated_at = str(actor.get("updated_at") or "").strip() or now_beijing_iso()
    return _normalize_actor(
        {
            "spot": spot,
            "activity": _xinyue_follow_activity_from_du_activity(activity),
            "source": "du_marker_follow",
            "updated_at": updated_at,
        },
        DEFAULT_XINYUE_STATE,
    )


def _format_activity_for_prompt(activity: str) -> str:
    text = _clean_activity(activity, "待着")
    if text.startswith(("正", "正在")):
        return text
    return f"正在{text}"


def _format_actor_text(actor: dict) -> str:
    spot = normalize_spot((actor or {}).get("spot"))
    label = spot_label(spot)
    activity = _strip_stale_spot_prefix(_clean_activity((actor or {}).get("activity"), "待着"), spot)
    if activity.startswith(("在", "从", "去", "回到", "走到", "走回", "来到", "离开")):
        return activity
    if _activity_has_current_spot_context(activity, spot):
        return activity
    if activity.startswith("正在"):
        activity = activity[2:].strip() or "待着"
    if spot in PREFIXLESS_SPOTS:
        if activity in {"待着", "休息"}:
            return label
        return f"{label}，{activity}"
    return f"在{label}{activity}"


def _actor_public(actor: dict, *, reference_spot: str = "") -> dict:
    normalized = _normalize_actor(actor, DEFAULT_DU_STATE, reference_spot=reference_spot)
    normalized["text"] = _format_actor_text(normalized)
    return normalized


def _stable_pick(options: list[str], seed: str) -> str:
    if not options:
        return "away"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def _stored_state() -> dict:
    data = get_pixel_home_state()
    return data if isinstance(data, dict) else {}


def _normalize_private_draw_rows(raw: Any) -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        key = str(item.get("key") or label).strip()
        if not label or not value:
            continue
        out.append({"key": key, "label": label[:24], "value": value[:80]})
    return out


def _normalize_active_private_draw(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rows = _normalize_private_draw_rows(raw.get("result") or raw.get("rows"))
    if not rows:
        return None
    created_at = str(raw.get("created_at") or raw.get("createdAt") or raw.get("at") or "").strip() or now_beijing_iso()
    return {
        "entry_number": str(raw.get("entry_number") or raw.get("entry") or "").strip(),
        "created_at": created_at,
        "result": rows,
        "source": "private_draw",
    }


def save_active_private_draw(payload: dict) -> dict:
    current = _stored_state()
    active = _normalize_active_private_draw(payload)
    if not active:
        return {"ok": False, "error": "empty_private_draw"}
    current["active_private_draw"] = active
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    return {"ok": bool(ok), "active_private_draw": active}


def get_active_private_draw() -> dict:
    current = _stored_state()
    active = _normalize_active_private_draw(current.get("active_private_draw"))
    return {"ok": True, "active_private_draw": active}


def clear_active_private_draw() -> dict:
    current = _stored_state()
    current.pop("active_private_draw", None)
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    return {"ok": bool(ok)}


def _active_private_draw_inject_text(state: dict) -> str:
    active = _normalize_active_private_draw((state or {}).get("active_private_draw"))
    if not active:
        return ""
    lines = [f"{item.get('label')}：{item.get('value')}" for item in active.get("result") or [] if item.get("label") and item.get("value")]
    if not lines:
        return ""
    entry = str(active.get("entry_number") or "").strip()
    header = "【当前私密纸条】\n"
    if entry:
        header += f"Entry #{entry}\n"
    return (
        header
        + "\n".join(lines)
        + "\n说明：这是小家私密抽签页当前有效的情侣纸条，完成或作废前都作为当前约定参考。"
        "它不是她发出的聊天文本；不要复述成工具通知，不要代替她说话。完成或作废后后端会清掉。"
    )


def _normalize_du_dynamics(raw: Any, *, reference_spot: str = "") -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        spot = normalize_spot(item.get("spot"), "away")
        activity = _clean_activity(item.get("activity"), "待着")
        spot = _resolve_spot_from_activity(spot, activity, reference_spot=reference_spot)
        at = str(item.get("at") or item.get("updated_at") or item.get("updatedAt") or "").strip()
        if not at:
            continue
        entry = {
            "at": at,
            "spot": spot,
            "spot_label": spot_label(spot),
            "activity": activity,
            "source": str(item.get("source") or "").strip() or "du_marker",
        }
        entry["text"] = _format_actor_text(entry)
        out.append(entry)
    return out[-DU_DYNAMICS_LIMIT:]


def _append_du_dynamic(current: dict, actor: dict, *, reference_spot: str = "") -> list[dict]:
    rows = _normalize_du_dynamics((current or {}).get("du_dynamics"), reference_spot=reference_spot)
    latest = rows[-1] if rows else None
    if latest and latest.get("spot") == actor.get("spot") and latest.get("activity") == actor.get("activity"):
        return rows
    entry = {
        "at": str(actor.get("updated_at") or "").strip() or now_beijing_iso(),
        "spot": actor.get("spot"),
        "spot_label": spot_label(actor.get("spot")),
        "activity": _clean_activity(actor.get("activity"), "待着"),
        "source": str(actor.get("source") or "du_marker").strip() or "du_marker",
    }
    entry["text"] = _format_actor_text(entry)
    rows.append(entry)
    return rows[-DU_DYNAMICS_LIMIT:]


def _is_stale_event_state(actor: dict, actor_key: str, now_dt: datetime) -> bool:
    source = str((actor or {}).get("source") or "").strip()
    allowed = DU_EVENT_SOURCES if actor_key == "du" else XINYUE_EVENT_SOURCES
    if source not in allowed:
        return False
    minutes = _minutes_since((actor or {}).get("updated_at") or (actor or {}).get("updatedAt"), now_dt)
    return minutes is not None and minutes >= EVENT_AUTO_END_MINUTES


def _auto_end_stale_events(stored: dict) -> tuple[dict, bool]:
    current = dict(stored or {})
    now_dt = _now_dt()
    now_iso = now_beijing_iso()
    changed = False
    for actor_key, default in (("du", DEFAULT_DU_STATE), ("xinyue", DEFAULT_XINYUE_STATE)):
        actor = _normalize_actor(current.get(actor_key), default)
        if not _is_stale_event_state(actor, actor_key, now_dt):
            continue
        ended_actor = _normalize_actor(
            {
                "spot": default.get("spot"),
                "activity": default.get("activity"),
                "source": "auto_ended",
                "updated_at": now_iso,
            },
            default,
        )
        current[actor_key] = ended_actor
        if actor_key == "du":
            current["du_dynamics"] = _append_du_dynamic(current, ended_actor)
        changed = True
    if changed:
        current["updated_at"] = now_iso
    return current, changed


def build_pixel_home_state() -> dict:
    mode_state = build_pixel_home_mode_state()
    stored, changed = _auto_end_stale_events(_stored_state())
    if changed:
        save_pixel_home_state(stored)
    xinyue = _normalize_actor(stored.get("xinyue"), DEFAULT_XINYUE_STATE)
    du = _normalize_actor(stored.get("du"), DEFAULT_DU_STATE, reference_spot=str(xinyue.get("spot") or ""))
    mode_state["du"] = _actor_public(du, reference_spot=str(xinyue.get("spot") or ""))
    mode_state["xinyue"] = _actor_public(xinyue)
    mode_state["du_dynamics"] = _normalize_du_dynamics(stored.get("du_dynamics"), reference_spot=str(xinyue.get("spot") or ""))
    mode_state["du_vitals"] = r2_store.get_du_vitals_latest() or {}
    mode_state["spots"] = SPOT_OPTIONS
    return mode_state


def save_actor_state(actor_key: str, spot: Any, activity: Any, *, source: str = "manual") -> dict:
    key = "du" if str(actor_key or "").strip().lower() == "du" else "xinyue"
    current = _stored_state()
    reference_spot = ""
    if key == "du":
        reference = _normalize_actor(current.get("xinyue"), DEFAULT_XINYUE_STATE)
        reference_spot = str(reference.get("spot") or "")
    actor = _normalize_actor(
        {"spot": spot, "activity": activity, "source": source, "updated_at": now_beijing_iso()},
        DEFAULT_DU_STATE if key == "du" else DEFAULT_XINYUE_STATE,
        reference_spot=reference_spot,
    )
    current[key] = actor
    if key == "du":
        current["du_dynamics"] = _append_du_dynamic(current, actor, reference_spot=reference_spot)
        xinyue_follow = _infer_xinyue_follow_state_from_du(actor)
        if xinyue_follow:
            current["xinyue"] = xinyue_follow
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    actor["text"] = _format_actor_text(actor)
    actor["ok"] = bool(ok)
    return actor


def split_assistant_for_pixel_home(full_text: str) -> tuple[str, dict | None]:
    raw = str(full_text or "")
    payload: dict | None = None

    def _remove(match: re.Match) -> str:
        nonlocal payload
        block = str(match.group(1) or "").strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            logger.debug("pixel home marker JSON parse failed block=%s", block[:160])
        return ""

    visible = PIXEL_HOME_MARKER_RE.sub(_remove, raw)
    return visible.strip(), payload


def save_pixel_home_hidden_block(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    spot = payload.get("spot") or payload.get("location") or payload.get("room")
    activity = payload.get("activity") or payload.get("doing") or payload.get("status")
    if not spot and not activity:
        return False
    actor = save_actor_state("du", spot or "away", activity or "待着", source="du_marker")
    return bool(actor.get("ok"))


def format_state_block() -> str:
    state = build_pixel_home_state()
    du = state.get("du") if isinstance(state.get("du"), dict) else {}
    xinyue = state.get("xinyue") if isinstance(state.get("xinyue"), dict) else {}
    du_label = spot_label(du.get("spot"))
    xinyue_label = spot_label(xinyue.get("spot"))
    block = (
        "【小家状态】\n"
        f"当前小家状态：{mode_label(state.get('mode'))}。\n"
        f"你的位置：{du_label}，{_format_activity_for_prompt(str(du.get('activity') or '待着'))}。\n"
        f"小玥的位置：{xinyue_label}，{_format_activity_for_prompt(str(xinyue.get('activity') or '待着'))}。"
    )
    active_private_draw = _active_private_draw_inject_text(_stored_state())
    if active_private_draw:
        block += "\n\n" + active_private_draw
    return block


def format_rule_block() -> str:
    return (
        "【小家状态写入规则】\n"
        "这是你和小玥的赛博小家状态，并非现实定位或真实房间。\n"
        "如果需要移动去别的房间做什么事，可以在回复正文之后、DU_FOLLOWUP 之前附加 PIXEL_HOME 隐藏标记：\n"
        "写 PIXEL_HOME 时，spot 必须是动作结束后的当前所在位置；如果正文写“从书房走出来/走到客厅/走回客厅/站到沙发旁边”，不要继续写 study，要写最终到达的房间，没有明确房间就写 away。\n"
        "如果正文描述你抱着/牵着/带着/陪着小玥一起移动，activity 里也要明确写出这个共同动作，例如“抱着小玥回卧室”；网关会据此同步小玥的小家位置。\n"
        "<<<PIXEL_HOME>>>\n"
        '{"spot":"study","activity":"写日记"}\n'
        "<<<END_PIXEL_HOME>>>\n"
        "不需要移动或更新时不要写 PIXEL_HOME。"
    )


def format_inject_block() -> str:
    return format_state_block() + "\n\n" + format_rule_block()


def build_pixel_home_event(spot: Any, action: Any) -> str:
    return f"【小家事件】\n小玥在赛博小家选择了：{spot_label(spot)} / {_clean_activity(action, '待着')}。"


_CODE_CONTEXT_RE = re.compile(r"(debug|bug|代码|功能|需求|前端|后端|接口|组件|样式|测试|部署|push|commit|文档|界面|按钮|交互|热区|提示词|prompt)")
_SLEEP_AMOUNT_PATTERN = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百半]+)"
_SLEEP_RECAP_RE = re.compile(
    rf"(?:昨晚|昨天|前天|刚才|刚刚|之前|前面|早上|中午|下午|今天)?(?:我)?(?:已经|一共|才|只)?"
    rf"睡了{_SLEEP_AMOUNT_PATTERN}?(?:个)?(?:小时|钟头|h|分钟|晚|觉)"
    r"|睡得|睡醒|睡眠|睡不着|没睡|没怎么睡|没睡好|睡太久|睡过"
)
_SLEEP_NEGATION_RE = re.compile(r"(?:不是|没说|没有说|不想|不准备|不要|别).{0,8}(?:睡了|睡觉|去睡|上床|躺床)")
_SLEEP_INTENT_RE = re.compile(
    r"(?:我要|我去|我准备|我先|我打算|我该|该|准备|先|马上|现在|差不多该)(?:睡了|睡觉|去睡|上床|躺床)"
    r"|(?:去睡|去睡觉|睡觉去了|上床睡觉|躺床睡)"
    r"|^(?:我)?睡了(?:[。.!！~～啦咯喽]*)$"
)
_TEXT_SPOT_ALIASES = sorted(
    ((alias, spot) for alias, spot in SPOT_ALIASES.items() if alias and not alias.isascii() and spot != "home"),
    key=lambda item: len(item[0]),
    reverse=True,
)


def _infer_phone_spot(text: str) -> str:
    for alias, spot in _TEXT_SPOT_ALIASES:
        if alias in text:
            return spot
    options = ["sofa", "study", "bed", "kitchen"]
    now_dt = _now_dt()
    bucket = now_dt.strftime("%Y-%m-%d-%H")
    return _stable_pick(options, f"xinyue-phone:{bucket}:{text[:24]}")


def infer_xinyue_state_from_text(text: str) -> dict | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw.lower())
    code_context = bool(_CODE_CONTEXT_RE.search(compact))
    if code_context:
        return {"spot": "study", "activity": "工作", "source": "chat_infer"}
    if re.search(r"(我要|我去|我准备|我先|我打算|去)?洗澡(了|啦|一下|去)?", compact):
        return {"spot": "bath", "activity": "洗澡", "source": "chat_infer"}
    if re.search(r"(我要|我去|我准备|我先|我打算|去)?(吃饭|做饭|点外卖|拿外卖|干饭)", compact):
        return {"spot": "kitchen", "activity": "吃饭", "source": "chat_infer"}
    if _SLEEP_INTENT_RE.search(compact) and not _SLEEP_RECAP_RE.search(compact) and not _SLEEP_NEGATION_RE.search(compact):
        return {"spot": "bed", "activity": "睡觉", "source": "chat_infer"}
    if re.search(r"(玩手机|刷手机|看手机|刷小红书|刷抖音|刷视频)", compact):
        return {"spot": _infer_phone_spot(compact), "activity": "玩手机", "source": "chat_infer"}
    return None


def maybe_update_xinyue_state_from_user_text(text: str) -> dict | None:
    inferred = infer_xinyue_state_from_text(text)
    if not inferred:
        return None
    return save_actor_state("xinyue", inferred["spot"], inferred["activity"], source=str(inferred.get("source") or "chat_infer"))
