import json
import random
import re
from typing import Any, Optional

from services.wenyou.constants import _WENYOU_DIFFICULTIES, _WENYOU_INSTANCE_GENRES, _WENYOU_RANK_ORDER


def _extract_json_object(text: str) -> Optional[dict]:
    """从模型输出中解析第一个 JSON 对象。"""
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    span = _first_json_object_span(t)
    if not span:
        return None
    raw = t[span[0] : span[1]]
    for attempt in (raw, raw.replace("\n", " ")):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _first_json_object_span(text: str, start_index: int = 0) -> Optional[tuple[int, int]]:
    """Return the first balanced JSON-object span in text, tolerant of nested objects."""
    if not text:
        return None
    start = text.find("{", max(0, start_index))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    return None


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))


def _compact_text(value: Any, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit > 0 and len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _slug_id(value: Any, fallback: str = "item") -> str:
    raw = str(value or fallback).strip().lower()
    return re.sub(r"[^a-z0-9_\u4e00-\u9fff-]+", "_", raw).strip("_")[:80] or fallback


def _rarity_rank(value: Any) -> int:
    rank = str(value or "D").strip().upper()
    return _WENYOU_RANK_ORDER.index(rank) + 1 if rank in _WENYOU_RANK_ORDER else 1


def _weighted_pick(options: list[tuple[str, float]], rng: random.Random, fallback: str = "D") -> str:
    if not options:
        return fallback
    total = sum(max(0.0, float(weight or 0.0)) for _, weight in options)
    if total <= 0:
        return options[0][0]
    roll = rng.random() * total
    acc = 0.0
    for value, weight in options:
        acc += max(0.0, float(weight or 0.0))
        if roll <= acc:
            return value
    return options[-1][0]


def _shift_rarity(rarity: str, delta: int) -> str:
    ranks = list(_WENYOU_RANK_ORDER)
    try:
        idx = ranks.index(_normalize_difficulty(rarity))
    except ValueError:
        idx = 0
    return ranks[max(0, min(len(ranks) - 1, idx + int(delta or 0)))]


def _normalize_difficulty(value: Any) -> str:
    rank = str(value or "").strip().upper()
    return rank if rank in _WENYOU_DIFFICULTIES else "C"


def _normalize_instance_genre(value: Any) -> str:
    genre = str(value or "").strip()
    return genre if genre in _WENYOU_INSTANCE_GENRES else "剧情解密"
