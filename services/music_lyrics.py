from __future__ import annotations

import json
import re
from typing import Any


_LRC_TIME_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_CREDIT_PREFIX_RE = re.compile(r"^(作词|作曲|编曲|歌词|翻译|监制|制作|混音|母带|和声|吉他|贝斯|录音|发行)\s*[:：]", re.IGNORECASE)


def _clean_lyric_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").replace("\u00a0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    if _CREDIT_PREFIX_RE.match(text):
        return ""
    return text[:limit]


def _lrc_time_to_seconds(match: re.Match) -> float:
    minutes = int(match.group(1) or 0)
    seconds = int(match.group(2) or 0)
    frac_raw = match.group(3) or ""
    frac = 0.0
    if frac_raw:
        if len(frac_raw) == 1:
            frac = int(frac_raw) / 10
        elif len(frac_raw) == 2:
            frac = int(frac_raw) / 100
        else:
            frac = int(frac_raw[:3]) / 1000
    return minutes * 60 + seconds + frac


def _netease_json_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    return _clean_lyric_text("".join(str((part or {}).get("tx") or "") for part in parts if isinstance(part, dict)))


def parse_lyrics_text(raw: str, *, duration_seconds: float = 0) -> dict:
    lines: list[dict] = []
    plain_lines: list[str] = []
    for raw_line in str(raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                text = _netease_json_text(obj.get("c"))
                if not text:
                    continue
                try:
                    t_ms = float(obj.get("t") or 0)
                except Exception:
                    t_ms = 0
                if t_ms > 0:
                    lines.append({"time": round(t_ms / 1000, 3), "text": text})
                else:
                    plain_lines.append(text)
                continue

        matches = list(_LRC_TIME_RE.finditer(line))
        text = _clean_lyric_text(_LRC_TIME_RE.sub("", line))
        if not text:
            continue
        if matches:
            for match in matches:
                lines.append({"time": round(_lrc_time_to_seconds(match), 3), "text": text})
        else:
            plain_lines.append(text)

    lines.sort(key=lambda item: (float(item.get("time") or 0), str(item.get("text") or "")))
    deduped: list[dict] = []
    seen = set()
    for item in lines:
        text = _clean_lyric_text(item.get("text"))
        if not text:
            continue
        try:
            time_value = max(0.0, float(item.get("time") or 0))
        except Exception:
            time_value = 0.0
        key = (round(time_value, 3), text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"time": round(time_value, 3), "text": text})

    clean_plain: list[str] = []
    plain_seen = set()
    for text in plain_lines:
        clean = _clean_lyric_text(text)
        if clean and clean not in plain_seen:
            plain_seen.add(clean)
            clean_plain.append(clean)

    estimated = False
    if not deduped and clean_plain and duration_seconds > 0:
        step = max(2.0, float(duration_seconds) / max(1, len(clean_plain) + 1))
        deduped = [
            {"time": round((idx + 1) * step, 3), "text": text}
            for idx, text in enumerate(clean_plain[:240])
        ]
        estimated = True

    return {
        "lines": deduped[:300],
        "plain_lines": clean_plain[:300],
        "synced": bool(deduped),
        "estimated": estimated,
    }


def normalize_lyrics_payload(value: Any) -> dict:
    if isinstance(value, str):
        return parse_lyrics_text(value)
    if isinstance(value, list):
        value = {"lines": value}
    if not isinstance(value, dict):
        return {"lines": [], "plain_lines": [], "synced": False, "estimated": False}
    raw_lines = value.get("lines") if isinstance(value.get("lines"), list) else []
    lines: list[dict] = []
    seen = set()
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        text = _clean_lyric_text(item.get("text"))
        if not text:
            continue
        try:
            time_value = max(0.0, float(item.get("time") or 0))
        except Exception:
            time_value = 0.0
        key = (round(time_value, 3), text)
        if key in seen:
            continue
        seen.add(key)
        lines.append({"time": round(time_value, 3), "text": text})
    lines.sort(key=lambda item: (float(item.get("time") or 0), str(item.get("text") or "")))

    raw_plain = value.get("plain_lines") if isinstance(value.get("plain_lines"), list) else []
    plain_lines = []
    plain_seen = set()
    for item in raw_plain:
        text = _clean_lyric_text(item)
        if text and text not in plain_seen:
            plain_seen.add(text)
            plain_lines.append(text)
    return {
        "lines": lines[:300],
        "plain_lines": plain_lines[:300],
        "synced": bool(lines),
        "estimated": bool(value.get("estimated")),
    }
