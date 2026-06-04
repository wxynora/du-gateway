from __future__ import annotations

import json
import re
from typing import Any


_LRC_TIME_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_CREDIT_PREFIX_RE = re.compile(r"^(作词|作曲|编曲|歌词|翻译|监制|制作|混音|母带|和声|吉他|贝斯|录音|发行)\s*[:：]", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


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


def _language_hint(text: str) -> str:
    if _KANA_RE.search(text):
        return "ja"
    if _LATIN_RE.search(text) and not _CJK_RE.search(text):
        return "latin"
    if _CJK_RE.search(text):
        return "zh"
    return "other"


def _looks_like_translation_pair(original: str, candidate: str) -> bool:
    if _language_hint(candidate) != "zh":
        return False
    return _language_hint(original) in {"ja", "latin"} and original != candidate


def _merge_translation_lines(raw_lines: list[dict]) -> list[dict]:
    items: list[dict] = []
    for item in raw_lines:
        text = _clean_lyric_text(item.get("text"))
        if not text:
            continue
        try:
            time_value = max(0.0, float(item.get("time") or 0))
        except Exception:
            time_value = 0.0
        line = {"time": round(time_value, 3), "text": text}
        translation = _clean_lyric_text(item.get("translation"))
        if translation and translation != text:
            line["translation"] = translation
        items.append(line)

    items.sort(key=lambda item: (float(item.get("time") or 0), str(item.get("text") or "")))
    merged: list[dict] = []
    i = 0
    while i < len(items):
        current = dict(items[i])
        nxt = items[i + 1] if i + 1 < len(items) else None
        if (
            nxt
            and not current.get("translation")
            and _looks_like_translation_pair(str(current.get("text") or ""), str(nxt.get("text") or ""))
        ):
            gap = float(nxt.get("time") or 0) - float(current.get("time") or 0)
            following = items[i + 2] if i + 2 < len(items) else None
            alternating = bool(following and _language_hint(str(following.get("text") or "")) in {"ja", "latin"})
            if gap <= 6.0 or alternating:
                current["translation"] = str(nxt.get("text") or "")
                if gap > 8.0:
                    current["time"] = nxt.get("time") or current.get("time") or 0
                merged.append(current)
                i += 2
                continue
        merged.append(current)
        i += 1
    return merged


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

    deduped: list[dict] = []
    seen = set()
    for item in _merge_translation_lines(lines):
        text = str(item.get("text") or "")
        time_value = float(item.get("time") or 0)
        translation = str(item.get("translation") or "")
        key = (round(time_value, 3), text)
        if key in seen:
            continue
        seen.add(key)
        line = {"time": round(time_value, 3), "text": text}
        if translation:
            line["translation"] = translation
        deduped.append(line)

    clean_plain: list[str] = []
    plain_seen = set()
    for text in plain_lines:
        clean = _clean_lyric_text(text)
        if clean and clean not in plain_seen:
            plain_seen.add(clean)
            clean_plain.append(clean)

    estimated = False
    if not deduped and clean_plain and duration_seconds > 0:
        plain_blocks = _merge_translation_lines([{"time": idx, "text": text} for idx, text in enumerate(clean_plain)])
        step = max(2.0, float(duration_seconds) / max(1, len(plain_blocks) + 1))
        deduped = [
            {
                **({"translation": str(item.get("translation"))} if item.get("translation") else {}),
                "time": round((idx + 1) * step, 3),
                "text": str(item.get("text") or ""),
            }
            for idx, item in enumerate(plain_blocks[:240])
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
    mergeable_lines = [item for item in raw_lines if isinstance(item, dict)]
    for item in _merge_translation_lines(mergeable_lines):
        text = str(item.get("text") or "")
        time_value = float(item.get("time") or 0)
        translation = str(item.get("translation") or "")
        key = (round(time_value, 3), text, translation)
        if key in seen:
            continue
        seen.add(key)
        line = {"time": round(time_value, 3), "text": text}
        if translation:
            line["translation"] = translation
        lines.append(line)

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
