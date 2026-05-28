import json
import random
from pathlib import Path
from typing import Any

from config import BASE_DIR
from services.wenyou.catalog import _CONTENT_ITEM_CATALOG, _GACHA_CATALOG, _SHOP_CATALOG
from services.wenyou.common import _normalize_difficulty, _rarity_rank, _shift_rarity, _weighted_pick
from services.wenyou.constants import (
    _WENYOU_REWARD_CATEGORY_LABELS,
    _WENYOU_REWARD_CATEGORY_RATES,
    _WENYOU_REWARD_RARITY_RATES,
    _WENYOU_REWARD_TABLE_CONFIG,
)
from services.wenyou.inventory import _new_inventory_item
from services.wenyou.runtime_state import _framework_for_runtime, _normalize_text_list
from services.wenyou.settlement_state import _reward_context_from_raw, _settlement_flags_from_raw
from utils.log import get_logger

logger = get_logger(__name__)


def _regular_reward_rarity_cap(difficulty: str) -> str:
    difficulty = _normalize_difficulty(difficulty)
    if difficulty in {"D", "C", "B"}:
        return _shift_rarity(difficulty, 1)
    return "S"


def _cap_reward_rarity(rarity: str, cap: str) -> tuple[str, bool]:
    normalized = _normalize_difficulty(rarity)
    cap = _normalize_difficulty(cap)
    if _rarity_rank(normalized) > _rarity_rank(cap):
        return cap, True
    return normalized, False


def _load_reward_table_config() -> dict[str, Any]:
    global _WENYOU_REWARD_TABLE_CONFIG
    if _WENYOU_REWARD_TABLE_CONFIG is not None:
        return _WENYOU_REWARD_TABLE_CONFIG
    path = Path(BASE_DIR) / "content" / "default" / "reward_tables.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except Exception as exc:
        logger.warning("文游奖励表加载失败 path=%s err=%s", path, exc)
        data = {}
    _WENYOU_REWARD_TABLE_CONFIG = data if isinstance(data, dict) else {}
    return _WENYOU_REWARD_TABLE_CONFIG


def _reward_weight_options(section: str, key: str, fallback: list[tuple[str, float]]) -> list[tuple[str, float]]:
    data = _load_reward_table_config()
    section_data = data.get(section) if isinstance(data.get(section), dict) else {}
    raw = section_data.get(key) if isinstance(section_data, dict) else None
    if not isinstance(raw, list):
        return list(fallback)
    out: list[tuple[str, float]] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("id") or item.get("rarity") or item.get("category") or item.get("name") or "").strip()
            weight = item.get("weight")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name = str(item[0] or "").strip()
            weight = item[1]
        else:
            continue
        try:
            weight_f = float(weight)
        except Exception:
            weight_f = 0.0
        if name and weight_f > 0:
            out.append((name, weight_f))
    return out or list(fallback)


def _reward_category_boosts_from_context(session: dict) -> dict[str, float]:
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    context = _reward_context_from_raw(rules.get("reward_context"))
    tags = _normalize_text_list(context.get("reward_tags"), 80, 40)
    flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    tags.extend(f"hidden:{x}" for x in _normalize_text_list(flags.get("hidden_endings"), 80, 20))
    config = _load_reward_table_config()
    configured = config.get("tag_category_boosts") if isinstance(config.get("tag_category_boosts"), dict) else {}
    boosts: dict[str, float] = {}

    def add(category: str, amount: float) -> None:
        if not category or amount <= 0:
            return
        boosts[category] = boosts.get(category, 0.0) + amount

    for tag in tags:
        lower = str(tag or "").lower()
        if "monster_sealed" in lower or "boss" in lower:
            add("special", 8.0)
            add("tool_item", 3.0)
        if "monster_defeated" in lower:
            add("tool_item", 8.0)
            add("material", 5.0)
        if "monster_evaded" in lower:
            add("consumable_item", 5.0)
            add("tool_item", 3.0)
        if "hidden" in lower:
            add("special", 8.0)
        for marker, cfg in configured.items():
            if str(marker or "").lower() not in lower or not isinstance(cfg, dict):
                continue
            for category, amount in cfg.items():
                try:
                    add(str(category), float(amount))
                except Exception:
                    continue
    return boosts


def _apply_reward_category_boosts(options: list[tuple[str, float]], boosts: dict[str, float]) -> list[tuple[str, float]]:
    if not boosts:
        return options
    by_category = {name: float(weight or 0.0) for name, weight in options}
    for category, amount in boosts.items():
        by_category[category] = max(0.0, by_category.get(category, 0.0) + float(amount or 0.0))
    return [(name, weight) for name, weight in by_category.items() if weight > 0]


def _reward_catalog_candidates(category: str, rarity: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    catalog: list[dict[str, Any]] = []
    source_catalog = list(_CONTENT_ITEM_CATALOG) + list(_SHOP_CATALOG) + list(_GACHA_CATALOG)
    for raw in source_catalog:
        item = dict(raw)
        iid = str(item.get("id") or item.get("name") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        catalog.append(item)
    same_rarity = [item for item in catalog if str(item.get("rarity") or "D").upper() == rarity]
    if category == "tool_item":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "") == "tool"]
    if category == "consumable_item":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "consumable") == "consumable"]
    if category == "material":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "") == "material"]
    if category == "special":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "") == "special"]
    return []


def _reward_stack_item(category: str, rarity: str) -> dict[str, Any]:
    if category == "material":
        names = {
            "D": ("anomaly_sample_d", "灰烬样本", 1),
            "C": ("anomaly_sample_c", "异常样本", 1),
            "B": ("anomaly_crystal_b", "异常结晶", 1),
            "A": ("instance_core_shard", "副本核心碎片", 1),
            "S": ("instance_core", "副本核心", 1),
        }
        iid, name, qty = names.get(rarity, names["D"])
        return {
            "id": iid,
            "name": name,
            "kind": "材料",
            "category": "material",
            "rarity": rarity,
            "quantity": qty,
            "desc": "副本结算获得的异常材料，可用于成长、兑换或特殊内容包规则。",
            "stackable": True,
        }
    if category == "tool_item":
        for item in _GACHA_CATALOG:
            if str(item.get("category") or item.get("item_type") or "") == "tool" and _normalize_difficulty(item.get("rarity") or "D") == rarity:
                return dict(item, shop_allowed=False, gacha_allowed=True)
    if category == "consumable_item":
        for item in _GACHA_CATALOG:
            if str(item.get("category") or item.get("item_type") or "") == "consumable" and _normalize_difficulty(item.get("rarity") or "D") == rarity:
                return dict(item, shop_allowed=False, gacha_allowed=True)
    return {
        "id": f"special_record_{rarity.lower()}",
        "name": f"{rarity}级特殊记录",
        "kind": "记录",
        "category": "special",
        "rarity": rarity,
        "quantity": 1,
        "desc": "副本结算留下的特殊记录，可作为后续内容包奖励占位。",
    }


def _roll_settlement_rewards(user_id: int, session: dict, settlement: dict) -> list[dict[str, Any]]:
    rolls = max(0, int(settlement.get("reward_rolls") or 0))
    if rolls <= 0:
        return []
    difficulty = _normalize_difficulty(settlement.get("difficulty") or _framework_for_runtime(session.get("framework") or {}).get("difficulty"))
    rating = str(settlement.get("rating") or "B").upper()
    seed = f"wenyou-reward:{int(user_id)}:{session.get('gameId') or ''}:{difficulty}:{settlement.get('result') or ''}:{rating}:{session.get('startedAt') or ''}"
    rng = random.Random(seed)
    rewards: list[dict[str, Any]] = []
    has_bplus = False
    regular_cap = _regular_reward_rarity_cap(difficulty)
    category_boosts = _reward_category_boosts_from_context(session)
    bonus_bplus_remaining = 0
    if rating == "S":
        bonus_bplus_remaining += 1
    bonus_bplus_remaining += max(0, int(settlement.get("hidden_bonus_rolls") or 0))
    allow_over_cap_bonus = bonus_bplus_remaining > 0
    for index in range(rolls):
        raw_rarity = _weighted_pick(
            _reward_weight_options("rarity_rates", difficulty, _WENYOU_REWARD_RARITY_RATES.get(difficulty, [])),
            rng,
            fallback=difficulty,
        )
        rarity = raw_rarity
        if rating == "S":
            rarity = _shift_rarity(rarity, 1)
        elif rating == "A" and rng.random() < 0.3:
            rarity = _shift_rarity(rarity, 1)
        elif (rating == "C" and rng.random() < 0.3) or rating in {"D", "F"}:
            rarity = _shift_rarity(rarity, -1)
        exceptional_over_cap = False
        if bonus_bplus_remaining > 0 and _rarity_rank(rarity) < _rarity_rank("B"):
            rarity = "B"
            bonus_bplus_remaining -= 1
        capped_rarity, capped = _cap_reward_rarity(rarity, regular_cap)
        if capped:
            if allow_over_cap_bonus and _rarity_rank(rarity) <= _rarity_rank("B") and _rarity_rank(regular_cap) < _rarity_rank("B"):
                exceptional_over_cap = True
            else:
                rarity = capped_rarity
        category_options = _reward_weight_options("category_rates", rarity, _WENYOU_REWARD_CATEGORY_RATES.get(rarity, []))
        category_options = _apply_reward_category_boosts(category_options, category_boosts)
        category = _weighted_pick(category_options, rng, fallback="consumable_item")
        candidates = _reward_catalog_candidates(category, rarity)
        if candidates:
            picked = dict(candidates[rng.randrange(len(candidates))])
        else:
            picked = _reward_stack_item(category, rarity)
        extra = {
            "reward_category": category,
            "reward_roll": {
                "seed": seed,
                "raw_rarity": raw_rarity,
                "final_rarity": rarity,
                "regular_cap": regular_cap,
                "capped": bool(capped and not exceptional_over_cap),
                "exceptional_over_cap": exceptional_over_cap,
            },
        }
        if exceptional_over_cap:
            picked["shop_allowed"] = False
            picked["gacha_allowed"] = False
            picked["sealed"] = True
            picked["seal_rank"] = picked.get("seal_rank") or rarity
            picked["sealed_reason"] = f"{difficulty} 级副本的越级奖励，需达到 {rarity} 阶或按内容包降级生效。"
        item = _new_inventory_item(picked, "settlement", "reward", extra)
        rewards.append(
            {
                "roll_id": f"reward-{index + 1:02d}",
                "rarity": rarity,
                "category": category,
                "category_label": _WENYOU_REWARD_CATEGORY_LABELS.get(category, category),
                "item": item,
                "raw_rarity": raw_rarity,
                "regular_cap": regular_cap,
                "capped": bool(capped and not exceptional_over_cap),
                "exceptional_over_cap": exceptional_over_cap,
            }
        )
        has_bplus = has_bplus or _rarity_rank(rarity) >= _rarity_rank("B")
    if (rating == "S" or int(settlement.get("hidden_bonus_rolls") or 0) > 0) and rewards and not has_bplus:
        picked = _reward_stack_item("tool_item", "B")
        exceptional_over_cap = _rarity_rank("B") > _rarity_rank(regular_cap)
        if exceptional_over_cap:
            picked["sealed"] = True
            picked["seal_rank"] = "B"
            picked["sealed_reason"] = f"{difficulty} 级副本的 B+ 保底奖励，需达到 B 阶或按内容包降级生效。"
        replacement = _new_inventory_item(
            picked,
            "settlement",
            "reward",
            {"reward_category": "tool_item", "reward_roll": {"seed": seed, "forced_bplus": True, "regular_cap": regular_cap}},
        )
        rewards[0] = {
            "roll_id": rewards[0].get("roll_id") or "reward-01",
            "rarity": "B",
            "category": "tool_item",
            "category_label": _WENYOU_REWARD_CATEGORY_LABELS["tool_item"],
            "item": replacement,
            "raw_rarity": rewards[0].get("raw_rarity"),
            "regular_cap": regular_cap,
            "capped": False,
            "exceptional_over_cap": exceptional_over_cap,
            "forced_bplus": True,
        }
    return rewards
