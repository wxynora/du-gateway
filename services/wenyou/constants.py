from typing import Any, Optional


_DEFAULT_PLAYER_COUNT = 2
_DEFAULT_TASKER_TOTAL = 6

# 副本难度 D～S（D 最低，S 最高）
_WENYOU_DIFFICULTIES = frozenset({"D", "C", "B", "A", "S"})
_WENYOU_RISK_DAMAGE: dict[str, tuple[int, int]] = {
    "safe": (0, 0),
    "minor": (5, 4),
    "risky": (12, 10),
    "dangerous": (25, 22),
    "desperate": (45, 40),
    "lethal": (80, 70),
}
_WENYOU_DIFFICULTY_MULTIPLIER = {"D": 0.75, "C": 1.0, "B": 1.35, "A": 1.75, "S": 2.25}
_WENYOU_RANK_PHYSICAL_REDUCTION = {"D": 0, "C": 2, "B": 5, "A": 9, "S": 15}
_WENYOU_RANK_MENTAL_REDUCTION = {"D": 0, "C": 2, "B": 5, "A": 9, "S": 15}
_WENYOU_RANK_HP_BONUS = {"D": 0, "C": 20, "B": 45, "A": 80, "S": 130}
_WENYOU_RANK_SAN_BONUS = {"D": 0, "C": 20, "B": 45, "A": 80, "S": 130}
_WENYOU_RANK_SPI_BONUS = {"D": 0, "C": 2, "B": 5, "A": 9, "S": 15}
_WENYOU_RANK_ATTRIBUTE_SOFT_CAP = {"D": 14, "C": 18, "B": 24, "A": 32, "S": 42}
_WENYOU_RANK_ATTRIBUTE_HARD_CAP = {"D": 16, "C": 22, "B": 30, "A": 40, "S": 50}
_WENYOU_LEVEL_EXP_TABLE = {
    1: 40,
    2: 70,
    3: 110,
    4: 150,
    5: 200,
    6: 260,
    7: 340,
    8: 440,
    9: 560,
    10: 720,
    11: 900,
    12: 1100,
    13: 1320,
    14: 1560,
    15: 1820,
    16: 2100,
    17: 2400,
    18: 2730,
    19: 3090,
    20: 3480,
    21: 3900,
    22: 4350,
    23: 4830,
    24: 5340,
    25: 5880,
    26: 6450,
    27: 7050,
    28: 7680,
    29: 8340,
}
_WENYOU_ATTRIBUTE_KEYS = ("str", "con", "agi", "int", "spi", "luk")
_WENYOU_RANK_ORDER = ("D", "C", "B", "A", "S")
_WENYOU_PROMOTION_RULES = {
    "C": {"from": "D", "level": 3, "cost": 200, "clear": "C", "perfect": "D"},
    "B": {"from": "C", "level": 6, "cost": 500, "clear": "B", "perfect": "C"},
    "A": {"from": "B", "level": 10, "cost": 1000, "clear": "A", "perfect": "B"},
    "S": {"from": "A", "level": 15, "cost": 2000, "clear": "S", "perfect": "A", "special_trial": True},
}
_WENYOU_REVIVE_BASE_COST = {"D": 200, "C": 500, "B": 1200, "A": 2600, "S": 6000}
_WENYOU_SELL_RATIO = {"D": 0.25, "C": 0.30, "B": 0.35, "A": 0.40, "S": 0.45}
_WENYOU_CORE_ABILITY_ARCHETYPES = {
    "observe": {
        "id": "core_observe",
        "name": "异常余光",
        "rarity": "D",
        "tags": ["observe", "investigation"],
        "desc": "每副本 1 次，获得当前场景中一处被忽略的异常提示；若涉及隐藏规则，SAN -5。",
    },
    "escape": {
        "id": "core_escape",
        "name": "退路直觉",
        "rarity": "D",
        "tags": ["escape", "stealth"],
        "desc": "每副本 1 次，逃离、规避或脱身判定 +3。",
    },
    "protect": {
        "id": "core_protect",
        "name": "代偿护手",
        "rarity": "D",
        "tags": ["protect", "support"],
        "desc": "每副本 1 次，为自己或同伴抵消 15 点 HP 伤害；自己 SAN -5。",
    },
    "combat": {
        "id": "core_combat",
        "name": "破局冲击",
        "rarity": "D",
        "tags": ["combat", "force"],
        "desc": "每副本 1 次，破坏、压制或强行突破判定 +3；失败时自身 HP -5。",
    },
    "social": {
        "id": "core_social",
        "name": "人群伪装",
        "rarity": "D",
        "tags": ["social", "deception"],
        "desc": "每副本 1 次，社交、伪装或混入人群判定 +3；失败时暴露风险 +1。",
    },
    "rule": {
        "id": "core_rule",
        "name": "规则嗅觉",
        "rarity": "D",
        "tags": ["rule", "investigation"],
        "desc": "每副本 1 次，验证一条低级规则是否会立刻造成危险；SAN -5。",
    },
    "resilience": {
        "id": "core_resilience",
        "name": "残响锚点",
        "rarity": "D",
        "tags": ["resilience", "mental"],
        "desc": "每副本 1 次，抵消一次动摇或轻度污染；SAN 低于一半时额外稳定当前精神力 +1。",
    },
    "survival": {
        "id": "core_survival",
        "name": "求生本能",
        "rarity": "D",
        "tags": ["survival"],
        "desc": "每副本 1 次，在险境行动前获得一次保守提示，或将一次低级风险降低一级。",
    },
}
_WENYOU_ACTION_MODIFIER = {
    "prepared": 0.70,
    "normal": 1.00,
    "reckless": 1.30,
    "forced": 1.60,
}
_WENYOU_CLEAR_BASE_REWARD = {
    "D": {"points": 100, "exp": 30, "rolls": 1},
    "C": {"points": 220, "exp": 60, "rolls": 1},
    "B": {"points": 450, "exp": 120, "rolls": 2},
    "A": {"points": 900, "exp": 220, "rolls": 2},
    "S": {"points": 1800, "exp": 420, "rolls": 3},
}
_WENYOU_RESULT_FACTORS = {
    "standard_clear": {"points": 1.0, "exp": 1.0, "label": "标准通关"},
    "low_escape": {"points": 0.5, "exp": 0.5, "label": "低完成逃生"},
    "failed_escape": {"points": 0.0, "exp": 0.2, "label": "失败撤离"},
    "death_failed": {"points": 0.0, "exp": 0.0, "label": "死亡失败"},
    "abandoned": {"points": 0.0, "exp": 0.0, "label": "放弃副本"},
}
_WENYOU_TUTORIAL_INSTANCE_ID = "tutorial_white_box_corridor"
_WENYOU_TUTORIAL_ATTRIBUTE_POINTS = 6
_WENYOU_TUTORIAL_GIFT_ITEM_IDS = ("wy_d_001", "wy_d_002")
_WENYOU_RATING_BONUS = {
    "S": {"points": 0.70, "exp": 0.70},
    "A": {"points": 0.45, "exp": 0.45},
    "B": {"points": 0.20, "exp": 0.20},
    "C": {"points": 0.0, "exp": 0.0},
    "D": {"points": -0.20, "exp": -0.20},
    "F": {"points": 0.0, "exp": 0.0},
}
_WENYOU_REWARD_RARITY_RATES: dict[str, list[tuple[str, float]]] = {
    "D": [("D", 70.0), ("C", 25.0), ("B", 5.0)],
    "C": [("D", 20.0), ("C", 60.0), ("B", 18.0), ("A", 2.0)],
    "B": [("C", 25.0), ("B", 55.0), ("A", 18.0), ("S", 2.0)],
    "A": [("B", 35.0), ("A", 55.0), ("S", 10.0)],
    "S": [("A", 45.0), ("S", 55.0)],
}
_WENYOU_REWARD_CATEGORY_RATES: dict[str, list[tuple[str, float]]] = {
    "D": [("consumable_item", 56.0), ("material", 24.0), ("tool_item", 18.0), ("special", 2.0)],
    "C": [("consumable_item", 40.0), ("material", 25.0), ("tool_item", 30.0), ("special", 5.0)],
    "B": [("consumable_item", 24.0), ("material", 26.0), ("tool_item", 38.0), ("special", 12.0)],
    "A": [("consumable_item", 14.0), ("material", 24.0), ("tool_item", 42.0), ("special", 20.0)],
    "S": [("consumable_item", 8.0), ("material", 18.0), ("tool_item", 44.0), ("special", 30.0)],
}
_WENYOU_REWARD_TABLE_CONFIG: Optional[dict[str, Any]] = None
_WENYOU_REWARD_CATEGORY_LABELS = {
    "consumable_item": "消耗道具",
    "material": "材料",
    "tool_item": "工具道具",
    "special": "特殊物/称号",
}
_WENYOU_DEFAULT_ABILITIES = {item["id"]: item for item in _WENYOU_CORE_ABILITY_ARCHETYPES.values()}
_WENYOU_RATING_LABELS = {
    "S": "S 完美",
    "A": "A 优秀",
    "B": "B 标准",
    "C": "C 勉强",
    "D": "D 低完成",
    "F": "F 失败",
}
_WENYOU_RATING_OPTIONS = [
    {"id": "S", "label": "S 完美", "desc": "95+ 分，高探索、低损耗或隐藏结局。"},
    {"id": "A", "label": "A 优秀", "desc": "80-94 分，主线清楚且有额外收益。"},
    {"id": "B", "label": "B 标准", "desc": "60-79 分，完成核心目标。"},
    {"id": "C", "label": "C 勉强", "desc": "40-59 分，活着完成但缺口较多。"},
    {"id": "D", "label": "D 低完成", "desc": "20-39 分，只保留很少成果。"},
    {"id": "F", "label": "F 失败", "desc": "0-19 分，不发积分奖励。"},
]
_WENYOU_RESULT_OPTIONS = [
    {"id": "standard_clear", "label": "标准通关", "desc": "达成主线最低条件，按基础保底结算。"},
    {"id": "low_escape", "label": "低完成逃生", "desc": "活着离开，但只带回最低记录或情报。"},
    {"id": "failed_escape", "label": "失败撤离", "desc": "强制撤离或只保住性命，不发积分。"},
    {"id": "death_failed", "label": "死亡失败", "desc": "死亡或彻底失败，后续接复活/债务。"},
    {"id": "abandoned", "label": "放弃副本", "desc": "主动放弃，触发放弃惩罚。"},
]
_WENYOU_EVENT_TAGS = frozenset(
    {
        "physical",
        "mental",
        "rule_pollution",
        "memory",
        "mixed",
        "clue",
        "npc_relation",
        "time",
        "resource",
    }
)

# 副本玩法类型（须与框架 JSON 字段 instance_genre 一致）
_WENYOU_INSTANCE_GENRES = frozenset(
    {
        "规则怪谈",
        "剧情解密",
        "大逃杀",
        "对抗",
        "生存撤离",
        "潜伏调查",
        "限时任务",
    }
)

