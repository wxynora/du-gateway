import math
from typing import Any

from services.wenyou.runtime_state import _normalize_text_list


def _damage_for_player(base: int, multiplier: float, modifier: float, attr: int, rank: str, reduction_table: dict[str, int]) -> int:
    if base <= 0:
        return 0
    raw = math.ceil(base * multiplier * modifier) - math.floor(max(0, int(attr or 0)) / 3) - int(reduction_table.get(rank, 0))
    return max(1, raw)


def _add_condition_unique(player: dict, condition: str) -> None:
    name = str(condition or "").strip()
    if not name:
        return
    arr = _normalize_text_list(player.get("conditions"), 40, 20)
    if name not in arr:
        arr.append(name[:40])
    player["conditions"] = arr[:20]


def _remove_condition(player: dict, condition: str) -> None:
    name = str(condition or "").strip()
    if not name:
        return
    player["conditions"] = [x for x in _normalize_text_list(player.get("conditions"), 40, 20) if x != name]


def _apply_threshold_conditions(player: dict) -> list[str]:
    added: list[str] = []
    hp = int(player.get("hp") or 0)
    hp_max = max(1, int(player.get("hp_max") or 1))
    san = int(player.get("san") or 0)
    san_max = max(1, int(player.get("san_max") or 1))
    thresholds = []
    if hp <= 0:
        thresholds.append("濒死")
        player.setdefault("death_clock", 3)
    elif hp <= math.floor(hp_max * 0.25):
        thresholds.append("重伤")
    elif hp <= math.floor(hp_max * 0.5):
        thresholds.append("轻伤")
    if san <= 0:
        thresholds.append("失控")
    elif san <= math.floor(san_max * 0.25):
        thresholds.append("污染")
    elif san <= math.floor(san_max * 0.5):
        thresholds.append("动摇")
    for cond in thresholds:
        before = set(_normalize_text_list(player.get("conditions"), 40, 20))
        _add_condition_unique(player, cond)
        if cond not in before:
            added.append(cond)
    return added


def _apply_clock_updates(session: dict, updates: list[dict]) -> list[dict]:
    clocks = session.get("clocks") if isinstance(session.get("clocks"), list) else []
    by_id: dict[str, dict] = {}
    for item in clocks:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item.get("id"))] = dict(item)
    results: list[dict] = []
    for upd in updates:
        cid = str(upd.get("id") or "").strip()
        if not cid:
            continue
        cur = by_id.get(cid, {"id": cid, "name": upd.get("name") or cid, "value": 0, "max": upd.get("max") or 6})
        max_value = max(1, int(upd.get("max") or cur.get("max") or 6))
        value = max(0, min(max_value, int(cur.get("value") or 0) + int(upd.get("delta") or 0)))
        cur.update({"name": str(upd.get("name") or cur.get("name") or cid)[:80], "value": value, "max": max_value})
        by_id[cid] = cur
        results.append({"id": cid, "delta": int(upd.get("delta") or 0), "value": value, "max": max_value})
    session["clocks"] = list(by_id.values())[:20]
    return results
