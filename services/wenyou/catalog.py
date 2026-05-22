import json
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from services.wenyou.common import _normalize_difficulty, _slug_id
from utils.log import get_logger


logger = get_logger(__name__)


_CATALOG_ITEM_TYPES = frozenset({"consumable", "tool", "material", "special"})


def _normalize_catalog_definition(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    rarity = _normalize_difficulty(raw.get("rarity") or "D")
    item_type = str(raw.get("item_type") or "").strip()
    if item_type not in _CATALOG_ITEM_TYPES:
        item_type = str(raw.get("category") or "consumable").strip()
    if item_type not in _CATALOG_ITEM_TYPES:
        item_type = "consumable"
    use_category = str(raw.get("category") or raw.get("kind") or "道具").strip()[:40] or "道具"
    effect_json = raw.get("effect_json") if isinstance(raw.get("effect_json"), dict) else {}
    effect_text = str(raw.get("effect") or effect_json.get("text") or raw.get("desc") or "").strip()
    item: dict[str, Any] = {
        "id": _slug_id(raw.get("id") or name),
        "name": name[:80],
        "kind": use_category,
        "use_category": use_category,
        "category": item_type,
        "item_type": item_type,
        "rarity": rarity,
        "price": max(0, int(raw.get("price") or 0)),
        "desc": effect_text[:240],
        "effect_json": effect_json,
        "requirements": raw.get("requirements") if isinstance(raw.get("requirements"), dict) else {},
        "use_cost": raw.get("use_cost") if isinstance(raw.get("use_cost"), dict) else {},
        "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
        "era_tags": raw.get("era_tags") if isinstance(raw.get("era_tags"), list) else ["universal"],
        "use_phase": raw.get("use_phase") if isinstance(raw.get("use_phase"), list) else [],
        "consume": bool(raw.get("consume")),
        "stackable": bool(raw.get("stackable")),
        "shop_allowed": bool(raw.get("shop_allowed")),
        "gacha_allowed": bool(raw.get("gacha_allowed")),
        "seal_rank": str(raw.get("seal_rank") or "").strip() or None,
        "weight": max(0, int(raw.get("weight") or 100)),
    }
    if effect_json.get("durability"):
        try:
            item["durability"] = max(0, int(effect_json.get("durability") or 0))
            item["durability_max"] = item["durability"]
        except Exception:
            pass
    if effect_json.get("uses"):
        try:
            item["uses_left"] = max(0, int(effect_json.get("uses") or 0))
        except Exception:
            pass
    return item


def _load_content_item_catalog() -> list[dict[str, Any]]:
    path = Path(BASE_DIR) / "content" / "default" / "items.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.warning("文游道具目录加载失败 path=%s err=%s", path, exc)
        return []
    raw_items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        item = _normalize_catalog_definition(raw)
        if not item:
            continue
        iid = str(item.get("id") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        out.append(item)
    return out


_SHOP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "bandage",
        "name": "绷带",
        "kind": "治疗",
        "rarity": "D",
        "price": 25,
        "desc": "非战斗中恢复 25 HP。",
    },
    {
        "id": "white_candle",
        "name": "白蜡烛",
        "kind": "治疗",
        "rarity": "D",
        "price": 25,
        "desc": "恢复 25 SAN，或移除动摇。",
    },
    {
        "id": "ration",
        "name": "压缩口粮",
        "kind": "补给",
        "rarity": "D",
        "price": 30,
        "desc": "长线生存中抵消一次饥饿或体力消耗。",
    },
    {
        "id": "glowstick",
        "name": "冷光棒",
        "kind": "工具",
        "rarity": "D",
        "price": 20,
        "desc": "黑暗场景 3 轮内观察惩罚 -1。",
    },
    {
        "id": "safety_rope",
        "name": "安全绳",
        "kind": "工具",
        "rarity": "D",
        "price": 50,
        "desc": "攀爬或坠落风险降低一级。",
    },
    {
        "id": "emergency_gel",
        "name": "急救凝胶",
        "kind": "治疗",
        "rarity": "C",
        "price": 90,
        "desc": "恢复 60 HP。",
    },
    {
        "id": "sedative",
        "name": "镇静剂",
        "kind": "治疗",
        "rarity": "C",
        "price": 85,
        "desc": "恢复 60 SAN，下轮观察或推理 -1。",
    },
    {
        "id": "oxygen_can",
        "name": "氧气罐",
        "kind": "补给",
        "rarity": "C",
        "price": 70,
        "desc": "抵消一次窒息、毒雾或水下行动惩罚。",
    },
    {
        "id": "old_key",
        "name": "旧铜钥匙",
        "kind": "线索道具",
        "rarity": "C",
        "price": 90,
        "desc": "可尝试打开一个低级锁或触发钥匙线索。",
    },
    {
        "id": "static_radio",
        "name": "杂音收音机",
        "kind": "侦测",
        "rarity": "C",
        "price": 100,
        "desc": "靠近异常源时会出现规律噪声。",
    },
    {
        "id": "blank_id_card",
        "name": "空白身份牌",
        "kind": "潜伏",
        "rarity": "C",
        "price": 120,
        "desc": "伪装身份暴露度 -1。",
    },
    {
        "id": "mirror_card",
        "name": "镜面卡",
        "kind": "防护",
        "rarity": "B",
        "price": 260,
        "desc": "抵消一次身份误认或精神暗示，最高 B 级。",
    },
    {
        "id": "testimony_bottle",
        "name": "证言封存瓶",
        "kind": "线索",
        "rarity": "B",
        "price": 280,
        "desc": "保存一段证言，防止被副本篡改。",
    },
    {
        "id": "rule_eraser",
        "name": "规则橡皮",
        "kind": "干涉",
        "rarity": "B",
        "price": 320,
        "desc": "验证性擦除一条低级规则，失败则 SAN -15。",
    },
    {
        "id": "blood_thread",
        "name": "溯源红线",
        "kind": "追踪",
        "rarity": "B",
        "price": 260,
        "desc": "标记目标，3 轮内不易跟丢。",
    },
    {
        "id": "god_heal_ticket",
        "name": "主神治疗券",
        "kind": "治疗",
        "rarity": "B",
        "price": 240,
        "desc": "恢复 HP/SAN 各 80，或移除重伤/污染之一。",
    },
    {
        "id": "causal_chalk",
        "name": "因果粉笔",
        "kind": "线索",
        "rarity": "B",
        "price": 360,
        "desc": "标记一处因果节点，解密判定 +3。",
    },
    {
        "id": "door_token",
        "name": "门缝代币",
        "kind": "位移",
        "rarity": "A",
        "price": 130,
        "desc": "在封闭空间里尝试换取一次离开机会。",
    },
    {
        "id": "black_ticket",
        "name": "黑色车票",
        "kind": "撤离",
        "rarity": "A",
        "price": 150,
        "desc": "触发紧急撤离路线，代价由规则表结算。",
    },
    {
        "id": "memory_needle",
        "name": "记忆针",
        "kind": "校验",
        "rarity": "A",
        "price": 140,
        "desc": "用于确认一段记忆是否被副本改写。",
    },
    {
        "id": "rule_film",
        "name": "规则隔离膜",
        "kind": "防护",
        "rarity": "A",
        "price": 420,
        "desc": "1 轮内规则污染伤害 -50%。",
    },
    {
        "id": "paper_double",
        "name": "替身纸人",
        "kind": "防护",
        "rarity": "A",
        "price": 650,
        "desc": "抵消一次致命 HP 伤害，之后燃尽。",
    },
    {
        "id": "rewind_pod",
        "name": "回溯急救仓",
        "kind": "治疗",
        "rarity": "A",
        "price": 800,
        "desc": "结算阶段回满 HP/SAN，并移除一个严重状态。",
    },
    {
        "id": "weak_rewrite_pen",
        "name": "弱规则改写笔",
        "kind": "干涉",
        "rarity": "A",
        "price": 900,
        "desc": "改写一条低级规则，威胁时钟 +2。",
    },
    {
        "id": "settlement_review",
        "name": "结算复核券",
        "kind": "结算",
        "rarity": "A",
        "price": 1200,
        "desc": "重算一次奖励或惩罚，结果必须接受。",
    },
    {
        "id": "half_amulet",
        "name": "半枚护符",
        "kind": "护身",
        "rarity": "S",
        "price": 2100,
        "desc": "抵消一次高额代价，但会添加未知标记。",
    },
    {
        "id": "god_receipt",
        "name": "主神小票",
        "kind": "凭证",
        "rarity": "S",
        "price": 2400,
        "desc": "申请复核一次主神判定，可能附带副作用。",
    },
]

_SHOP_CATALOG_BY_ID = {str(item.get("id") or ""): item for item in _SHOP_CATALOG}
_GACHA_SINGLE_COST = 100
_GACHA_MAX_COUNT = 10
_GACHA_FRAGMENT_VALUES = {"D": 5, "C": 15, "B": 50, "A": 180, "S": 600}
_GACHA_POOL_RATES: dict[str, list[tuple[str, float]]] = {
    "mixed": [("D", 50.0), ("C", 34.0), ("B", 12.0), ("A", 3.7), ("S", 0.3)],
    "tool_pool": [("D", 45.0), ("C", 36.0), ("B", 14.0), ("A", 4.5), ("S", 0.5)],
    "supply_pool": [("D", 60.0), ("C", 30.0), ("B", 8.5), ("A", 1.4), ("S", 0.1)],
    "limited_pool": [("D", 35.0), ("C", 40.0), ("B", 18.0), ("A", 6.4), ("S", 0.6)],
}
_GACHA_CATALOG: list[dict[str, Any]] = [
    {"id": "emergency_bandage", "name": "应急绷带", "rarity": "D", "kind": "物资", "category": "consumable", "desc": "一次性治疗道具。", "sigil": "BND", "stackable": True},
    {"id": "white_candle", "name": "白蜡烛", "rarity": "D", "kind": "规则", "category": "consumable", "desc": "短暂标记安全区域。", "sigil": "CDL", "stackable": True},
    {"id": "safety_rope", "name": "安全绳", "rarity": "D", "kind": "工具", "category": "consumable", "desc": "降低坠落与脱队风险。", "sigil": "RPE", "stackable": True},
    {"id": "static_radio", "name": "静电收音机", "rarity": "C", "kind": "线索", "category": "consumable", "desc": "偶尔捕获副本广播残响。", "sigil": "RAD", "stackable": True},
    {"id": "blank_id_card", "name": "空白身份牌", "rarity": "C", "kind": "潜伏", "category": "consumable", "desc": "可写入一次临时身份。", "sigil": "ID", "stackable": True},
    {"id": "testimony_bottle", "name": "证言瓶", "rarity": "C", "kind": "记忆", "category": "consumable", "desc": "封存一段关键证词。", "sigil": "MEM", "stackable": True},
    {"id": "rule_eraser", "name": "规则橡皮", "rarity": "B", "kind": "干涉", "category": "consumable", "desc": "验证性擦除一条低级规则。", "sigil": "DEL", "stackable": True},
    {"id": "god_heal_ticket", "name": "主神治疗券", "rarity": "B", "kind": "治疗", "category": "consumable", "desc": "结算或安全场景恢复重伤。", "sigil": "HEAL", "stackable": True},
    {"id": "blood_thread", "name": "血色牵引线", "rarity": "B", "kind": "追踪", "category": "consumable", "desc": "锁定一个目标的残留路线。", "sigil": "LINE", "stackable": True},
    {"id": "camp_hatchet", "name": "营地斧", "rarity": "D", "kind": "近战工具", "category": "tool", "desc": "破坏判定 +1。", "sigil": "AXE"},
    {"id": "iron_flashlight", "name": "铁皮手电", "rarity": "C", "kind": "工具", "category": "tool", "desc": "黑暗观察惩罚 -1。", "sigil": "LAMP"},
    {"id": "blood_crowbar", "name": "血锈撬棍", "rarity": "B", "kind": "近战工具", "category": "tool", "desc": "可强行撬开异常封锁。", "sigil": "BAR"},
    {"id": "door_key_fragment", "name": "门钥碎片", "rarity": "A", "kind": "撤离", "category": "consumable", "desc": "拼合后可开启异常出口。", "sigil": "GATE"},
    {"id": "rewind_pod", "name": "回溯急救仓", "rarity": "A", "kind": "治疗", "category": "consumable", "desc": "结算阶段移除严重状态。", "sigil": "POD"},
    {"id": "weak_rewrite_pen", "name": "弱改写笔", "rarity": "A", "kind": "规则", "category": "consumable", "desc": "短暂改写一个可验证条件。", "sigil": "PEN"},
    {"id": "god_receipt", "name": "主神小票", "rarity": "S", "kind": "凭证", "category": "consumable", "desc": "申请复核一次主神判定。", "sigil": "VOID"},
    {"id": "memory_needle", "name": "记忆缝针", "rarity": "S", "kind": "记忆", "category": "consumable", "desc": "缝合一次被污染的关键记忆。", "sigil": "NEED"},
]

_FALLBACK_SHOP_CATALOG = list(_SHOP_CATALOG)
_FALLBACK_GACHA_CATALOG = list(_GACHA_CATALOG)
_CONTENT_ITEM_CATALOG = _load_content_item_catalog()
if _CONTENT_ITEM_CATALOG:
    _SHOP_CATALOG = [
        dict(item)
        for item in _CONTENT_ITEM_CATALOG
        if item.get("category") in _CATALOG_ITEM_TYPES
        and item.get("category") != "material"
        and not item.get("temporary")
        and not item.get("quest_item")
    ]
    _GACHA_CATALOG = [
        dict(item)
        for item in _CONTENT_ITEM_CATALOG
        if item.get("gacha_allowed") and item.get("category") != "material"
    ]
_SHOP_CATALOG_BY_ID = {str(item.get("id") or ""): item for item in _SHOP_CATALOG}
_ITEM_CATALOG_BY_ID = {str(item.get("id") or ""): item for item in _CONTENT_ITEM_CATALOG}
_ITEM_CATALOG_BY_NAME = {str(item.get("name") or ""): item for item in _CONTENT_ITEM_CATALOG}


def _catalog_item_definition(item_id: str, fallback_name: str, fallback_effect: dict[str, Any]) -> dict[str, Any]:
    item = _ITEM_CATALOG_BY_ID.get(str(item_id or "")) or _SHOP_CATALOG_BY_ID.get(str(item_id or ""))
    if isinstance(item, dict) and item:
        return dict(item)
    return {
        "id": str(item_id or fallback_name),
        "name": fallback_name,
        "kind": "新手补给",
        "category": "consumable",
        "item_type": "consumable",
        "rarity": "D",
        "desc": str(fallback_effect.get("label") or "新手补给。"),
        "effect_json": dict(fallback_effect),
        "consume": True,
        "stackable": True,
        "price": 30,
    }


_GACHA_ITEMS_BY_RARITY: dict[str, list[dict[str, Any]]] = {}
for _gacha_item in _GACHA_CATALOG:
    _GACHA_ITEMS_BY_RARITY.setdefault(str(_gacha_item.get("rarity") or "D"), []).append(_gacha_item)
