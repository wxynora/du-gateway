from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing

MARKER_START = "<<<DU_VITALS>>>"
MARKER_END = "<<<END_DU_VITALS>>>"

_ALLOWED_TEMPOS = {"down", "steady", "up", "spike", "settle"}
_DEFAULT_DURATION_SECONDS = 180


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


def split_assistant_for_vitals(full_text: str) -> tuple[str, Optional[str]]:
    if not full_text or not isinstance(full_text, str):
        return full_text or "", None
    if MARKER_START not in full_text:
        return full_text, None
    if MARKER_END not in full_text:
        i = full_text.find(MARKER_START)
        return full_text[:i].rstrip(), None
    pattern = re.escape(MARKER_START) + r"\s*(.*?)\s*" + re.escape(MARKER_END)
    m = re.search(pattern, full_text, flags=re.DOTALL)
    if not m:
        i = full_text.find(MARKER_START)
        return full_text[:i].rstrip(), None
    content = (m.group(1) or "").strip()
    visible = full_text[: m.start()] + full_text[m.end() :]
    return visible.strip(), content if content else None


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


def _clamp_int(value: float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


def _parse_json_object(raw_block: str) -> dict | None:
    text = str(raw_block or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    nested = parsed.get("du_vitals")
    if isinstance(nested, dict):
        return nested
    return parsed


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
    if tempo == "spike" or tension >= 0.72:
        return "有点绷"
    if intimacy_heat >= 0.62:
        return "靠近"
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

    params = {
        "activation": _clamp_float(src.get("activation"), 0.32),
        "focus": _clamp_float(src.get("focus"), 0.35),
        "warmth": _clamp_float(src.get("warmth"), 0.45),
        "tension": _clamp_float(src.get("tension"), 0.12),
        "intimacy_heat": _clamp_float(src.get("intimacy_heat"), 0.0),
    }
    tempo = str(src.get("tempo") or "steady").strip().lower()
    if tempo not in _ALLOWED_TEMPOS:
        tempo = "steady"
    try:
        duration_sec = int(src.get("duration_sec") or src.get("durationSec") or _DEFAULT_DURATION_SECONDS)
    except Exception:
        duration_sec = _DEFAULT_DURATION_SECONDS
    duration_sec = max(30, min(900, duration_sec))

    heart_tempo, breath_tempo = _tempo_delta(tempo)
    heart = (
        64
        + params["activation"] * 25
        + params["focus"] * 7
        + params["warmth"] * 4
        + params["tension"] * 22
        + params["intimacy_heat"] * 18
        + heart_tempo
    )
    breath = (
        9
        + params["activation"] * 5
        + params["focus"] * 1.5
        - params["warmth"] * 0.8
        + params["tension"] * 5.5
        + params["intimacy_heat"] * 3.5
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


def format_inject_block(latest: Optional[dict]) -> str:
    guide = (
        "【渡的拟态心跳/呼吸参数（仅你与网关可见，勿在回复正文复述给老婆）】\n"
        "每轮回复都要在可见正文之后追加下面隐藏块，作为你这一轮自然反应后的拟态节律参数。\n"
        "隐藏块里只写下面 JSON 里的状态字段，不写解释文字；可见回复里不要提到这组参数。\n"
        f"{MARKER_START}\n"
        '{"activation":0.32,"focus":0.35,"warmth":0.45,"tension":0.12,"intimacy_heat":0.0,"tempo":"steady","duration_sec":180}\n'
        f"{MARKER_END}\n"
        "字段含义：activation=被点亮/兴奋程度；focus=头脑风暴或专注；warmth=柔软亲近；tension=紧张/冲突；intimacy_heat=暧昧亲密热度；tempo 只能是 down/steady/up/spike/settle。\n"
        "例：讨论方案或脑暴时 focus 高、tempo 可 up；亲密暧昧时 warmth 和 intimacy_heat 升；冲突或慌乱时 tension 升；平静陪伴时 warmth 稳、activation 低、tempo 可 settle。\n"
        "若同轮还有 DU_FOLLOWUP，DU_FOLLOWUP 仍必须是整条回复最后一个隐藏标记。\n"
    )
    if not isinstance(latest, dict) or not latest:
        return guide + "上一组状态：暂无。"
    status = str(latest.get("status") or "").strip()
    heart = str(latest.get("heart_bpm") or "").strip()
    breath = str(latest.get("breath_rpm") or "").strip()
    at = str(latest.get("at") or latest.get("updatedAt") or "").strip()
    parts = [x for x in [status, f"{heart} bpm" if heart else "", f"{breath}/min" if breath else ""] if x]
    return guide + f"上一组状态（{at or '未知时间'}）：{' · '.join(parts) or '暂无'}。"
