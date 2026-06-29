from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from services.hidden_blocks import HiddenBlockParser
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing

MARKER_START = "<<<DU_VITALS>>>"
MARKER_END = "<<<END_DU_VITALS>>>"
SHORT_MARKER = "[du:vitals tempo=steady activation=0.32 focus=0.35 warmth=0.45 tension=0.12]"
_HIDDEN_BLOCK = HiddenBlockParser.for_markers(
    "DU_VITALS",
    MARKER_START,
    MARKER_END,
    short_markers=("du:vitals",),
)

_ALLOWED_TEMPOS = {"down", "steady", "up", "spike", "settle"}
_DEFAULT_DURATION_SECONDS = 180
_PARAM_DEFAULTS = {
    "activation": 0.32,
    "focus": 0.35,
    "warmth": 0.45,
    "tension": 0.12,
    "intimacy_heat": 0.0,
    "valence": 0.0,
    "arousal": 0.32,
    "attachment": 0.0,
}
_LOOSE_KEY_ALIASES = {
    "activation": "activation",
    "focus": "focus",
    "warmth": "warmth",
    "tension": "tension",
    "intimacy_heat": "intimacy_heat",
    "heat": "intimacy_heat",
    "intimacy": "intimacy_heat",
    "valence": "valence",
    "arousal": "arousal",
    "attachment": "attachment",
    "tempo": "tempo",
    "duration": "duration_sec",
    "duration_sec": "duration_sec",
    "durationsec": "duration_sec",
    "status": "status",
}
_LOOSE_KEY_RE = re.compile(
    r"\b("
    + "|".join(re.escape(key) for key in sorted(_LOOSE_KEY_ALIASES, key=len, reverse=True))
    + r")\b\s*[:=：]\s*",
    flags=re.IGNORECASE,
)


def compute_visible_streaming(acc: str) -> str:
    return _HIDDEN_BLOCK.compute_visible_streaming(acc)


def split_assistant_for_vitals(full_text: str) -> tuple[str, Optional[str]]:
    return _HIDDEN_BLOCK.split(full_text)


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except Exception:
        num = default
    if num < 0:
        return 0.0
    if num > 1:
        return 1.0
    return num


def _clamp_axis(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except Exception:
        num = default
    if num < -1:
        return -1.0
    if num > 1:
        return 1.0
    return num


def _clamp_int(value: float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


def _parse_json_object(raw_block: str) -> dict | None:
    text = str(raw_block or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = _parse_loose_object(text)
    if not isinstance(parsed, dict):
        return None
    nested = parsed.get("du_vitals")
    if isinstance(nested, dict):
        return nested
    return parsed


def _parse_loose_object(text: str) -> dict | None:
    s = str(text or "").strip().strip("`")
    if not s:
        return None
    low = s.lower()
    if low in _ALLOWED_TEMPOS:
        return {"tempo": low}

    matches = list(_LOOSE_KEY_RE.finditer(s))
    if not matches:
        return None
    out: dict[str, Any] = {}
    for idx, match in enumerate(matches):
        raw_key = (match.group(1) or "").strip().lower()
        key = _LOOSE_KEY_ALIASES.get(raw_key)
        if not key:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(s)
        raw_value = s[match.end() : end].strip().strip(",;，； ")
        if not raw_value:
            continue
        out[key] = _coerce_loose_value(raw_value)
    return out or None


def _coerce_loose_value(value: str) -> Any:
    s = str(value or "").strip().strip("\"'")
    if not s:
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        if re.fullmatch(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", s):
            return float(s)
    except Exception:
        pass
    return s


def _previous_param_defaults(previous: dict | None) -> dict[str, float]:
    defaults = dict(_PARAM_DEFAULTS)
    if not _active_previous(previous):
        return defaults
    params = previous.get("parameters") if isinstance(previous, dict) and isinstance(previous.get("parameters"), dict) else {}
    for key, default in _PARAM_DEFAULTS.items():
        if key in params:
            defaults[key] = _clamp_axis(params.get(key), default) if key in {"valence", "attachment"} else _clamp_float(params.get(key), default)
    return defaults


def _tempo_delta(tempo: str) -> tuple[int, int]:
    if tempo == "down":
        return -6, -1
    if tempo == "up":
        return 8, 2
    if tempo == "spike":
        return 16, 4
    if tempo == "settle":
        return -8, -2
    return 0, 0


def _status_label(params: dict, tempo: str) -> str:
    activation = float(params.get("activation") or 0)
    focus = float(params.get("focus") or 0)
    warmth = float(params.get("warmth") or 0)
    tension = float(params.get("tension") or 0)
    intimacy_heat = float(params.get("intimacy_heat") or 0)
    valence = float(params.get("valence") or 0)
    attachment = float(params.get("attachment") or 0)
    if tempo == "spike" or tension >= 0.72:
        return "有点绷"
    if valence <= -0.38:
        return "低落"
    if attachment >= 0.45:
        return "靠近"
    if intimacy_heat >= 0.62:
        return "升温"
    if focus >= 0.74:
        return "头脑风暴中"
    if warmth >= 0.68 and activation <= 0.48:
        return "安静陪伴"
    if activation >= 0.72:
        return "被点亮"
    if tempo == "settle":
        return "慢慢回落"
    return "平稳"


def _active_previous(previous: dict | None) -> bool:
    if not isinstance(previous, dict):
        return False
    expires = parse_iso_to_beijing(str(previous.get("expiresAt") or "").strip())
    now = parse_iso_to_beijing(now_beijing_iso())
    return bool(expires and now and expires > now)


def _smooth(prev: Any, current: int, max_delta: int) -> int:
    try:
        p = int(prev)
    except Exception:
        return current
    if current > p + max_delta:
        return p + max_delta
    if current < p - max_delta:
        return p - max_delta
    return current


def _iso_after(seconds: int) -> str:
    dt = datetime.now(BEIJING_TZ) + timedelta(seconds=max(30, int(seconds or _DEFAULT_DURATION_SECONDS)))
    return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def normalize_vitals_payload(raw_block: str, previous: dict | None = None) -> dict | None:
    src = _parse_json_object(raw_block)
    if not src:
        return None
    defaults = _previous_param_defaults(previous)

    params = {
        "activation": _clamp_float(src.get("activation"), defaults["activation"]),
        "focus": _clamp_float(src.get("focus"), defaults["focus"]),
        "warmth": _clamp_float(src.get("warmth"), defaults["warmth"]),
        "tension": _clamp_float(src.get("tension"), defaults["tension"]),
        "intimacy_heat": _clamp_float(src.get("intimacy_heat"), defaults["intimacy_heat"]),
        "valence": _clamp_axis(src.get("valence"), defaults["valence"]),
        "arousal": _clamp_float(src.get("arousal"), defaults["arousal"]),
        "attachment": _clamp_axis(src.get("attachment"), defaults["attachment"]),
    }
    previous_tempo = str((previous or {}).get("tempo") or "steady").strip().lower() if _active_previous(previous) else "steady"
    tempo = str(src.get("tempo") or previous_tempo).strip().lower()
    if tempo not in _ALLOWED_TEMPOS:
        tempo = "steady"
    try:
        duration_sec = int(src.get("duration_sec") or src.get("durationSec") or _DEFAULT_DURATION_SECONDS)
    except Exception:
        duration_sec = _DEFAULT_DURATION_SECONDS
    duration_sec = max(30, min(900, duration_sec))

    heart_tempo, breath_tempo = _tempo_delta(tempo)
    negative_pressure = max(0.0, -params["valence"])
    positive_pressure = max(0.0, params["valence"])
    attachment_warmth = max(0.0, params["attachment"])
    heart = (
        64
        + params["activation"] * 25
        + params["focus"] * 7
        + params["warmth"] * 4
        + params["tension"] * 22
        + params["intimacy_heat"] * 18
        + params["arousal"] * 14
        + negative_pressure * 8
        + positive_pressure * 3
        + attachment_warmth * 4
        + heart_tempo
    )
    breath = (
        9
        + params["activation"] * 5
        + params["focus"] * 1.5
        - params["warmth"] * 0.8
        + params["tension"] * 5.5
        + params["intimacy_heat"] * 3.5
        + params["arousal"] * 2.8
        + negative_pressure * 1.2
        + attachment_warmth * 0.6
        + breath_tempo
    )
    heart_bpm = _clamp_int(heart, 48, 132)
    breath_rpm = _clamp_int(breath, 6, 24)
    if _active_previous(previous):
        heart_bpm = _smooth((previous or {}).get("heart_bpm"), heart_bpm, 14)
        breath_rpm = _smooth((previous or {}).get("breath_rpm"), breath_rpm, 4)

    now = now_beijing_iso()
    status = str(src.get("status") or "").strip()[:20] or _status_label(params, tempo)
    return {
        "at": now,
        "updatedAt": now,
        "expiresAt": _iso_after(duration_sec),
        "heart_bpm": heart_bpm,
        "breath_rpm": breath_rpm,
        "status": status,
        "tempo": tempo,
        "duration_sec": duration_sec,
        "parameters": params,
        "source": "du_vitals_sidecar",
        "raw": str(raw_block or "").strip()[:500],
    }


def _fmt_param(value: Any, default: float = 0.0) -> str:
    try:
        num = float(value)
    except Exception:
        num = default
    return f"{num:.2f}"


def format_rule_block(_latest: Optional[dict] = None) -> str:
    """拼成稳定的拟态节律隐藏块规则；不包含每轮变化的实际读数。"""
    _ = _latest
    return (
        "【渡的拟态心跳/呼吸参数规则（仅你与网关可见，勿在回复正文复述给老婆）】\n"
        "每轮回复都要在正文后追加一行短隐藏标记，作为你这一轮自然反应后的拟态节律参数。\n"
        "优先只写本轮明显变化的字段；没写的字段会沿用上一轮有效读数或默认值。可见回复里不要提到这组参数。\n"
        "短标记示例（只是字段格式，不是当前读数；实际数值按本轮上下文更新）：\n"
        f"{SHORT_MARKER}\n"
        "字段含义：activation=被点亮/兴奋程度；focus=头脑风暴或专注；warmth=柔软亲近；tension=紧张/冲突；intimacy_heat=暧昧亲密热度；valence=-1到1，负向为难过/受挫，正向为暖/轻松；arousal=0到1，表示被触动程度；attachment=-1到1，负向为退开，正向为贴近/想修复；tempo 只能是 down/steady/up/spike/settle。\n"
        "例：讨论方案或脑暴时 focus 高、tempo 可 up；亲密暧昧时 warmth 和 intimacy_heat 升；冲突或慌乱时 tension/arousal 升且 valence 可能下降；平静陪伴时 warmth 稳、activation 低、tempo 可 settle；想靠近或修复时 attachment 升。\n"
        "如果本轮亲密欲望有明显变化，可以同时用小家短隐藏标记 `[du:home desire=35]` 更新 desire；desire 是你当下想做的程度，范围 0-100。\n"
        "隐藏标记统一追加在正文后，不要写进正文里。\n"
    )


def format_state_block(latest: Optional[dict] = None) -> str:
    """拼成每轮变化的最新拟态读数，放动态 system。"""
    if not isinstance(latest, dict) or not latest:
        return (
            "【渡的拟态心跳/呼吸当前读数】\n"
            "暂无上一轮已存读数。本轮请按当前上下文自然写入新的隐藏块。"
        )
    params = latest.get("parameters") if isinstance(latest.get("parameters"), dict) else {}
    parts = [
        f"heart_bpm={latest.get('heart_bpm') or '-'}",
        f"breath_rpm={latest.get('breath_rpm') or '-'}",
        f"tempo={str(latest.get('tempo') or 'steady').strip() or 'steady'}",
        f"status={str(latest.get('status') or '').strip() or '-'}",
        f"activation={_fmt_param(params.get('activation'), 0.32)}",
        f"focus={_fmt_param(params.get('focus'), 0.35)}",
        f"warmth={_fmt_param(params.get('warmth'), 0.45)}",
        f"tension={_fmt_param(params.get('tension'), 0.12)}",
        f"intimacy_heat={_fmt_param(params.get('intimacy_heat'), 0.0)}",
        f"valence={_fmt_param(params.get('valence'), 0.0)}",
        f"arousal={_fmt_param(params.get('arousal'), 0.32)}",
        f"attachment={_fmt_param(params.get('attachment'), 0.0)}",
    ]
    updated = str(latest.get("updatedAt") or latest.get("at") or "").strip()
    suffix = f"\n更新时间：{updated}" if updated else ""
    return (
        "【渡的拟态心跳/呼吸当前读数】\n"
        + "；".join(parts)
        + suffix
        + "\n这些是上一轮落库后的读数，只作为本轮延续和惯性参考；本轮仍要根据当前上下文自行更新隐藏块，不要在可见回复里解释这些数值。"
    )


def format_inject_block(latest: Optional[dict] = None) -> str:
    """兼容旧调用：只返回稳定规则块。"""
    return format_rule_block(latest)
