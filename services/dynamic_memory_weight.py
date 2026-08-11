from __future__ import annotations

from datetime import datetime
from typing import Optional

from utils.time_aware import _now_beijing, parse_iso_to_beijing


DYNAMIC_MEMORY_DECAY_GRACE_DAYS = 15
DYNAMIC_MEMORY_DECAY_PER_DAY = 0.1
DYNAMIC_MEMORY_MAX_TIME_DECAY = 2.0


def dynamic_memory_weight(memory: dict, now: Optional[datetime] = None) -> float:
    """动态记忆唯一权重公式：重要度 + 提及次数 - 时间衰减。"""
    importance = int((memory or {}).get("importance") or 0)
    mention_count = int((memory or {}).get("mention_count") or 0)
    now = now or _now_beijing()
    last_mentioned = (memory or {}).get("last_mentioned") or (memory or {}).get("created_at") or ""
    mentioned_at = parse_iso_to_beijing(last_mentioned)
    if mentioned_at is None:
        mentioned_at = now
    days_since = max(0, (now - mentioned_at).days)
    decay_days = max(0, days_since - DYNAMIC_MEMORY_DECAY_GRACE_DAYS)
    time_decay = min(decay_days * DYNAMIC_MEMORY_DECAY_PER_DAY, DYNAMIC_MEMORY_MAX_TIME_DECAY)
    return float(importance + mention_count - time_decay)
