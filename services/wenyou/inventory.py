from typing import Any, Optional
from uuid import uuid4

from services.wenyou.common import _normalize_difficulty, _rarity_rank, _slug_id
from utils.time_aware import now_beijing_iso


def _normalize_inventory_item(raw: Any, index: int = 0, source: str = "session") -> Optional[dict]:
    if isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("label") or raw.get("title") or "").strip()
        if not name:
            return None
        iid = _slug_id(raw.get("id") or raw.get("item_id") or name)
        qty = max(1, int(raw.get("quantity") or raw.get("qty") or 1))
        rarity = str(raw.get("rarity") or "D").strip().upper()
        if rarity not in {"D", "C", "B", "A", "S"}:
            rarity = "D"
        item = {
            "uid": str(raw.get("uid") or raw.get("item_uid") or f"{source}-{iid}-{index}")[:96],
            "id": iid,
            "name": name[:80],
            "kind": str(raw.get("kind") or raw.get("type") or "道具").strip()[:40],
            "category": str(raw.get("category") or raw.get("item_type") or "consumable").strip()[:40],
            "rarity": rarity,
            "desc": str(raw.get("desc") or raw.get("description") or "").strip()[:240],
            "quantity": qty,
            "source": str(raw.get("source") or source).strip()[:40],
            "acquired_at": str(raw.get("acquired_at") or raw.get("created_at") or now_beijing_iso()),
        }
        for key in (
            "sigil",
            "price",
            "bound",
            "broken",
            "depleted",
            "traits",
            "fragments_value",
            "pool_id",
            "sealed",
            "sealed_reason",
            "converted_from",
            "item_type",
            "use_category",
            "effect_json",
            "requirements",
            "use_cost",
            "tags",
            "era_tags",
            "use_phase",
            "consume",
            "durability",
            "durability_max",
            "uses_left",
            "seal_rank",
            "instance_grant_reason",
            "carry_out",
            "temporary",
            "quest_item",
            "unique",
        ):
            if key in raw:
                item[key] = raw[key]
        if "stackable" in raw:
            item["stackable"] = bool(raw.get("stackable"))
        return item
    name = str(raw or "").strip()
    if not name:
        return None
    iid = _slug_id(name)
    return {
        "uid": f"legacy-{iid}-{index}",
        "id": iid,
        "name": name[:80],
        "kind": "道具",
        "category": "legacy",
        "rarity": "D",
        "desc": "",
        "quantity": 1,
        "source": "legacy",
        "acquired_at": now_beijing_iso(),
    }


def _normalize_inventory(raw: Any, source: str = "session") -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for i, item in enumerate(raw[:80]):
        normalized = _normalize_inventory_item(item, i, source)
        if normalized:
            out.append(normalized)
    return out[:80]


def _inventory_item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or "").strip()
    return str(item or "").strip()


def _inventory_item_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item or "").strip()
    name = _inventory_item_name(item)
    qty = int(item.get("quantity") or 1)
    suffix = f" x{qty}" if qty > 1 else ""
    sealed = "（封印）" if item.get("sealed") else ""
    temporary = "（任务）" if item.get("carry_out") is False or item.get("temporary") else ""
    return f"{name}{suffix}{sealed}{temporary}".strip()


def _inventory_label_list(items: Any) -> list[str]:
    return [x for x in (_inventory_item_label(item) for item in _normalize_inventory(items, source="session")) if x]


def _inventory_has_item(inventory: list[dict], item_id: str = "", name: str = "") -> bool:
    iid = _slug_id(item_id) if item_id else ""
    name = str(name or "").strip()
    for item in _normalize_inventory(inventory, source="session"):
        if iid and str(item.get("id") or "") == iid:
            return True
        if name and _inventory_item_name(item) == name:
            return True
    return False


def _inventory_find_by_name(inventory: list[dict], name: str) -> Optional[dict]:
    needle = str(name or "").strip()
    if not needle:
        return None
    for item in _normalize_inventory(inventory, source="session"):
        if _inventory_item_name(item) == needle or str(item.get("uid") or "") == needle or str(item.get("id") or "") == needle:
            return item
    return None


def _inventory_item_matches(item: dict, target: dict) -> bool:
    if not isinstance(item, dict) or not isinstance(target, dict):
        return False
    uid = str(target.get("uid") or "").strip()
    if uid and str(item.get("uid") or "").strip() == uid:
        return True
    iid = str(target.get("id") or "").strip()
    if iid and str(item.get("id") or "").strip() == iid:
        return True
    name = _inventory_item_name(target)
    return bool(name and _inventory_item_name(item) == name)


def _consume_inventory_item(inventory: list[dict], target: dict, force_remove: bool = False) -> tuple[list[dict], Optional[dict]]:
    inv = _normalize_inventory(inventory, source="session")
    consumed: Optional[dict] = None
    out: list[dict] = []
    used = False
    for item in inv:
        cur = dict(item)
        if not used and _inventory_item_matches(cur, target):
            used = True
            consumed = dict(cur)
            inventory_update = target.get("_inventory_update") if isinstance(target.get("_inventory_update"), dict) else {}
            keep_item = not force_remove and (bool(target.get("_use_keep")) or cur.get("consume") is False)
            if keep_item:
                for key, value in inventory_update.items():
                    cur[key] = value
                    consumed[key] = value
                uses_left = max(0, int(cur.get("uses_left") or 0))
                if uses_left:
                    cur["uses_left"] = max(0, uses_left - 1)
                    consumed["uses_left_after"] = cur["uses_left"]
                    if cur["uses_left"] == 0:
                        cur["depleted"] = True
                        consumed["depleted"] = True
                consumed["use_consumed"] = False
                out.append(cur)
                continue
            uses_left = max(0, int(cur.get("uses_left") or 0))
            if uses_left > 1:
                cur["uses_left"] = uses_left - 1
                consumed["quantity"] = 1
                consumed["use_consumed"] = False
                consumed["uses_left_after"] = cur["uses_left"]
                out.append(cur)
                continue
            qty = max(1, int(cur.get("quantity") or 1))
            consumed["quantity"] = 1
            consumed["use_consumed"] = True
            if qty > 1:
                cur["quantity"] = qty - 1
                out.append(cur)
            continue
        out.append(cur)
    return out[:80], consumed


def _unseal_inventory_by_rank(inventory: list[dict], rank: str) -> tuple[list[dict], list[dict]]:
    max_rank = _normalize_difficulty(rank)
    out: list[dict] = []
    unlocked: list[dict] = []
    for item in _normalize_inventory(inventory, source="session"):
        cur = dict(item)
        req = cur.get("requirements") if isinstance(cur.get("requirements"), dict) else {}
        has_attr_or_level_req = bool(req.get("level_min") or any(req.get(f"{attr}_min") for attr in ("str", "con", "agi", "int", "spi", "luk", "spi_current")))
        seal_rank = str(cur.get("seal_rank") or cur.get("rarity") or "D").strip().upper()
        if cur.get("sealed") and not has_attr_or_level_req and _rarity_rank(seal_rank) <= _rarity_rank(max_rank):
            cur.pop("sealed", None)
            cur.pop("sealed_reason", None)
            unlocked.append(cur)
        out.append(cur)
    return out[:80], unlocked


def _new_inventory_item(defn: dict[str, Any], source: str, uid_prefix: str = "item", extra: Optional[dict] = None) -> dict:
    data = dict(defn or {})
    data.update(extra or {})
    data["uid"] = f"{uid_prefix}-{uuid4().hex[:12]}"
    data["source"] = source
    data["acquired_at"] = now_beijing_iso()
    return _normalize_inventory_item(data, 0, source) or {
        "uid": f"{uid_prefix}-{uuid4().hex[:12]}",
        "id": "unknown",
        "name": "未知物品",
        "kind": "道具",
        "category": "consumable",
        "rarity": "D",
        "desc": "",
        "quantity": 1,
        "source": source,
        "acquired_at": now_beijing_iso(),
    }


def _add_inventory_item(inventory: list[dict], item: dict) -> list[dict]:
    inv = _normalize_inventory(inventory, source="session")
    new_item = _normalize_inventory_item(item, len(inv), str(item.get("source") or "system"))
    if not new_item:
        return inv
    if new_item.get("stackable") or str(new_item.get("category") or "") in {"fragment", "material"}:
        for cur in inv:
            if str(cur.get("id") or "") == str(new_item.get("id") or "") and str(cur.get("category") or "") == str(new_item.get("category") or ""):
                cur["quantity"] = max(1, int(cur.get("quantity") or 1)) + max(1, int(new_item.get("quantity") or 1))
                cur["acquired_at"] = new_item.get("acquired_at") or now_beijing_iso()
                return inv[:80]
    inv.append(new_item)
    return inv[:80]


def _merge_inventory(base: Any, extra: Any) -> list[dict]:
    inv = _normalize_inventory(base, source="wallet")
    for item in _normalize_inventory(extra, source="session"):
        if str(item.get("category") or "") in {"fragment", "material"} or item.get("stackable"):
            inv = _add_inventory_item(inv, item)
        elif not _inventory_has_item(inv, item_id=str(item.get("id") or ""), name=_inventory_item_name(item)):
            inv.append(item)
    return inv[:80]


def _inventory_item_can_carry_out(item: Any) -> bool:
    if not isinstance(item, dict):
        return True
    if item.get("carry_out") is False or item.get("temporary") or item.get("quest_item"):
        return False
    if str(item.get("category") or "") in {"quest", "task_item"}:
        return False
    return True


def _carryable_inventory(raw: Any) -> list[dict]:
    return [item for item in _normalize_inventory(raw, source="wallet") if _inventory_item_can_carry_out(item)][:80]


def _inventory_update_item(inventory: list[dict], target: dict, updates: dict) -> tuple[list[dict], Optional[dict]]:
    inv = _normalize_inventory(inventory, source="session")
    out: list[dict] = []
    updated: Optional[dict] = None
    used = False
    for item in inv:
        cur = dict(item)
        if not used and _inventory_item_matches(cur, target):
            used = True
            cur.update(updates or {})
            updated = dict(cur)
        out.append(cur)
    return out[:80], updated


def _inventory_quantity(inventory: list[dict], item_id: str = "", name: str = "", category: str = "") -> int:
    total = 0
    iid = str(item_id or "").strip()
    target_name = str(name or "").strip()
    target_category = str(category or "").strip()
    for item in _normalize_inventory(inventory, source="session"):
        if iid and str(item.get("id") or "") != iid:
            continue
        if target_name and _inventory_item_name(item) != target_name:
            continue
        if target_category and str(item.get("category") or "") != target_category:
            continue
        total += max(1, int(item.get("quantity") or 1))
    return total


def _consume_inventory_requirements(inventory: list[dict], requirements: list[dict[str, Any]]) -> tuple[list[dict], list[str]]:
    inv = _normalize_inventory(inventory, source="session")
    missing: list[str] = []
    for req in requirements:
        need = max(1, int(req.get("quantity") or 1))
        have = _inventory_quantity(inv, str(req.get("id") or ""), str(req.get("name") or ""), str(req.get("category") or ""))
        if have < need:
            missing.append(f"{req.get('name') or req.get('id')} x{need - have}")
    if missing:
        return inv, missing
    for req in requirements:
        remain = max(1, int(req.get("quantity") or 1))
        out: list[dict] = []
        for item in inv:
            cur = dict(item)
            matched = True
            if req.get("id") and str(cur.get("id") or "") != str(req.get("id") or ""):
                matched = False
            if req.get("name") and _inventory_item_name(cur) != str(req.get("name") or ""):
                matched = False
            if req.get("category") and str(cur.get("category") or "") != str(req.get("category") or ""):
                matched = False
            if matched and remain > 0:
                qty = max(1, int(cur.get("quantity") or 1))
                take = min(qty, remain)
                remain -= take
                if qty > take:
                    cur["quantity"] = qty - take
                    out.append(cur)
                continue
            out.append(cur)
        inv = out[:80]
    return inv[:80], []


def _item_reference_price(item: dict) -> int:
    if int(item.get("price") or 0) > 0:
        return int(item.get("price") or 0)
    return {"D": 60, "C": 150, "B": 420, "A": 1200, "S": 12000}.get(_normalize_difficulty(item.get("rarity") or "D"), 60)


def _item_locked_for_recycle(item: dict) -> Optional[str]:
    if item.get("quest_item") or item.get("temporary") or item.get("carry_out") is False:
        return "副本任务物/临时物不能出售或回收。"
    if item.get("unique") or item.get("bound"):
        return "唯一物或绑定物不能出售或回收。"
    return None
