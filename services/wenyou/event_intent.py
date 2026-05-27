import json
import re
from typing import Any, Optional

from services.wenyou.common import (
    _compact_text,
    _first_json_object_span,
    _normalize_difficulty,
    _to_non_negative_int,
)
from services.wenyou.constants import _WENYOU_ACTION_MODIFIER, _WENYOU_EVENT_TAGS, _WENYOU_RISK_DAMAGE
from services.wenyou.runtime_state import _normalize_text_list


def _parse_event_intent(gm_text: str) -> Optional[dict]:
    """Parse GM's backend-only event intent block."""
    if not gm_text or "【事件意图】" not in gm_text:
        return None
    idx = gm_text.find("【事件意图】")
    span = _first_json_object_span(gm_text, idx)
    if not span:
        return None
    try:
        data = json.loads(gm_text[span[0] : span[1]])
    except Exception:
        return None
    return _normalize_event_intent(data)


def _normalize_event_intent(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    risk = str(raw.get("risk") or "safe").strip().lower()
    if risk not in _WENYOU_RISK_DAMAGE:
        risk = "safe"
    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list):
        targets_raw = [raw.get("target")] if raw.get("target") else []
    targets: list[str] = []
    for item in targets_raw:
        s = str(item or "").strip().lower()
        if s in ("all", "both", "玩家", "双方"):
            targets.extend(["player1", "player2"])
        elif s in ("player1", "p1", "玩家一"):
            targets.append("player1")
        elif s in ("player2", "p2", "玩家二"):
            targets.append("player2")
    if not targets:
        targets = ["player1"]
    targets = list(dict.fromkeys(targets))
    tags_raw = raw.get("tags")
    if isinstance(tags_raw, str):
        tags_raw = re.split(r"[、，,\s]+", tags_raw)
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = [str(x or "").strip().lower() for x in tags_raw]
    tags = [x for x in tags if x in _WENYOU_EVENT_TAGS]
    if not tags:
        tags = ["mixed"] if risk != "safe" else ["clue"]
    action_state = str(raw.get("action_state") or raw.get("action") or "normal").strip().lower()
    modifier = raw.get("action_modifier")
    try:
        action_modifier = float(modifier) if modifier is not None else _WENYOU_ACTION_MODIFIER.get(action_state, 1.0)
    except Exception:
        action_modifier = 1.0
    action_modifier = max(0.5, min(2.0, action_modifier))
    return {
        "event": _compact_text(raw.get("event") or "gm_event", 80),
        "risk": risk,
        "targets": targets,
        "tags": tags,
        "action_state": action_state if action_state in _WENYOU_ACTION_MODIFIER else "normal",
        "action_modifier": action_modifier,
        "fiction": _compact_text(raw.get("fiction"), 240),
        "conditions_add": _normalize_text_list(raw.get("conditions_add"), 40, 8),
        "conditions_remove": _normalize_text_list(raw.get("conditions_remove"), 40, 8),
        "clock_updates": _normalize_clock_updates(raw.get("clock_updates")),
        "rule_updates": _normalize_text_list(raw.get("rule_updates") or raw.get("rules"), 180, 8),
        "clue_updates": _normalize_text_list(raw.get("clue_updates") or raw.get("clues"), 180, 8),
        "task_update": _compact_text(raw.get("task_update") or raw.get("progress_update"), 220),
        "state_proposals": _normalize_state_proposals(raw.get("state_proposals")),
    }


def _normalize_state_proposals(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    allowed_types = {
        "discover_clue",
        "verify_clue",
        "task_update",
        "location_update",
        "npc_update",
        "monster_update",
        "rule_violation",
        "violate_rule",
        "clock_delta",
        "settlement_flag",
        "acquire_item",
        "acquire_task_item",
        "acquire_unique_item",
    }
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        ptype = str(item.get("type") or "").strip()
        if ptype not in allowed_types:
            ptype = "task_update" if "task" in ptype else "discover_clue"
        visibility = str(item.get("visibility") or "hidden").strip().lower()
        if visibility not in {"public", "hidden"}:
            visibility = "hidden"
        out.append(
            {
                "type": ptype,
                "id": _compact_text(item.get("id") or item.get("name"), 80),
                "name": _compact_text(item.get("name"), 80),
                "rarity": _normalize_difficulty(item.get("rarity") or "D"),
                "category": _compact_text(item.get("category"), 40),
                "effect": _compact_text(item.get("effect") or item.get("desc") or item.get("description"), 240),
                "carry_out": bool(item.get("carry_out")) if "carry_out" in item else None,
                "seal_rank": _normalize_difficulty(item.get("seal_rank")) if item.get("seal_rank") else None,
                "requirements": item.get("requirements") if isinstance(item.get("requirements"), dict) else {},
                "visibility": visibility,
                "reason": _compact_text(item.get("reason"), 180),
                "quantity": max(1, min(3, _to_non_negative_int(item.get("quantity") or item.get("qty"), 1))),
            }
        )
    return out


def _normalize_clock_updates(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or item.get("name") or "").strip()[:80]
        if not cid:
            continue
        try:
            delta = int(item.get("delta") or 0)
        except Exception:
            delta = 0
        try:
            max_value = int(item.get("max") or 0)
        except Exception:
            max_value = 0
        out.append(
            {
                "id": cid,
                "name": str(item.get("name") or cid).strip()[:80],
                "delta": max(-10, min(10, delta)),
                "max": max(1, max_value or 6),
            }
        )
    return out
