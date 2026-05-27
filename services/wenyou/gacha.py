import random
from typing import Any, Optional

from services.wenyou.catalog import (
    _GACHA_FRAGMENT_VALUES,
    _GACHA_ITEMS_BY_RARITY,
    _GACHA_POOL_RATES,
)
from services.wenyou.common import _rarity_rank


def _normalize_gacha_pool_id(pool_id: Any) -> str:
    pool = str(pool_id or "mixed").strip().lower()
    return pool if pool in _GACHA_POOL_RATES else "mixed"


def _normalize_gacha_pool_state(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    return {
        "total": max(0, int(data.get("total") or 0)),
        "no_cplus": max(0, int(data.get("no_cplus") or 0)),
        "no_bplus": max(0, int(data.get("no_bplus") or 0)),
        "no_s": max(0, int(data.get("no_s") or 0)),
    }


def _normalize_gacha_state(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    pools_raw = data.get("pools") if isinstance(data.get("pools"), dict) else {}
    pools = {}
    for pool_id in _GACHA_POOL_RATES:
        pools[pool_id] = _normalize_gacha_pool_state(pools_raw.get(pool_id))
    return {"pools": pools}


def _roll_rarity_by_rate(pool_id: str, rng: random.Random) -> str:
    roll = rng.random() * 100
    acc = 0.0
    for rarity, weight in _GACHA_POOL_RATES[_normalize_gacha_pool_id(pool_id)]:
        acc += weight
        if roll < acc:
            return rarity
    return "D"


def _apply_gacha_pity(pool_state: dict, rarity: str) -> tuple[str, Optional[str]]:
    guarantee: Optional[str] = None
    if int(pool_state.get("no_s") or 0) + 1 >= 100:
        guarantee = "S"
    elif int(pool_state.get("no_bplus") or 0) + 1 >= 30:
        guarantee = "B"
    elif int(pool_state.get("no_cplus") or 0) + 1 >= 10:
        guarantee = "C"
    if guarantee and _rarity_rank(rarity) < _rarity_rank(guarantee):
        return guarantee, guarantee
    return rarity, None


def _update_gacha_pity(pool_state: dict, rarity: str) -> dict:
    state = _normalize_gacha_pool_state(pool_state)
    state["total"] += 1
    if _rarity_rank(rarity) >= _rarity_rank("C"):
        state["no_cplus"] = 0
    else:
        state["no_cplus"] += 1
    if _rarity_rank(rarity) >= _rarity_rank("B"):
        state["no_bplus"] = 0
    else:
        state["no_bplus"] += 1
    if rarity == "S":
        state["no_s"] = 0
    else:
        state["no_s"] += 1
    return state


def _pick_gacha_definition(pool_id: str, rarity: str, rng: random.Random) -> dict:
    pool = _GACHA_ITEMS_BY_RARITY.get(rarity) or _GACHA_ITEMS_BY_RARITY.get("D") or []
    normalized_pool = _normalize_gacha_pool_id(pool_id)
    if normalized_pool == "tool_pool":
        filtered = [item for item in pool if str(item.get("category") or "") == "tool"]
        pool = filtered or pool
    elif normalized_pool == "supply_pool":
        filtered = [item for item in pool if str(item.get("category") or "") == "consumable"]
        pool = filtered or pool
    if not pool:
        return {
            "id": "unknown",
            "name": "未知残片",
            "rarity": rarity,
            "kind": "残片",
            "category": "fragment",
            "desc": "",
            "sigil": "UNK",
            "stackable": True,
        }
    return dict(pool[rng.randrange(len(pool))])


def _gacha_fragment_item(source_item: dict) -> dict:
    rarity = str(source_item.get("rarity") or "D")
    qty = _GACHA_FRAGMENT_VALUES.get(rarity, 5)
    return {
        "id": f"{source_item.get('id')}_fragment",
        "name": f"{source_item.get('name')}碎片",
        "kind": "碎片",
        "category": "fragment",
        "rarity": rarity,
        "desc": f"重复获得【{source_item.get('name')}】后转化。",
        "quantity": qty,
        "sigil": "FRG",
        "stackable": True,
        "converted_from": source_item.get("id"),
    }
