from __future__ import annotations

from typing import Any

from services.captivity_simulator_game import (
    ACTION_CONTENTS,
    ACTION_LABELS,
    INVENTORY_ITEMS,
    NIGHT_DETAIL_OPTIONS,
    RECAPTURE_FOLLOWUP_LABELS,
    RECAPTURE_RULE_LABELS,
    TOOL_COMPATIBILITY,
    TOOL_LABELS,
    TRAINING_CONTENTS,
)


REFERENCE_TOOL_NAME = "captivity_simulator_reference"
REFERENCE_CATEGORIES = ("actions", "training", "tools", "feeding", "inventory", "night", "escape")


def get_reference_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": REFERENCE_TOOL_NAME,
            "description": "按需查询囚禁模拟器的通用选项与规则。只读，不推进游戏；当前事件和提交格式以本轮提示为准。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": list(REFERENCE_CATEGORIES),
                        "description": "actions 行动内容；training 调教内容；tools 道具；feeding 喂食；inventory 物品；night 夜间；escape 抓回规则。",
                    }
                },
                "required": ["category"],
                "additionalProperties": False,
            },
        },
    }


def get_reference(category: str) -> dict[str, Any]:
    category = str(category or "").strip().lower()
    if category == "actions":
        return {
            "intensity": {"light": "低", "medium": "中", "heavy": "高"},
            "actions": {
                action_id: {"label": ACTION_LABELS.get(action_id, action_id), "contents": contents}
                for action_id, contents in ACTION_CONTENTS.items()
            },
            "other_actions": {
                action_id: label for action_id, label in ACTION_LABELS.items() if action_id not in ACTION_CONTENTS
            },
            "modifiers": {"training": "附加调教", "sex": "附加性行为"},
        }
    if category == "training":
        return {"training_contents": TRAINING_CONTENTS, "selection": "选择 1 至 3 项"}
    if category == "tools":
        return {
            "tools": TOOL_LABELS,
            "recommendations": {tool_id: sorted(contexts) for tool_id, contexts in TOOL_COMPATIBILITY.items()},
            "selection": "最多选择 2 个；推荐关系不是硬性限制",
        }
    if category == "feeding":
        return {
            "rule": "始终包含一份正常食物；额外饮水不能代替食物",
            "source": {"cook": "自己做", "takeout": "点外卖"},
            "additive": {
                "none": "不加料",
                "body_fluid": "体液",
                "fictional_sleep": "安眠",
                "fictional_arousal": "助兴",
            },
            "disclosed": {"told": "明确告知", "hint": "暗示", "hidden": "隐瞒"},
            "water": {"none": "不额外喂水", "glass": "一杯水", "lots": "很多水"},
        }
    if category == "inventory":
        return {
            "items": INVENTORY_ITEMS,
            "rule": "赠送和收回不占白天行动；已赠送物品不能重复赠送",
            "used_item_traces": "book 赠送时另填 book_title；book、switch、music_player、tablet 各设置 5 至 8 条痕迹，之后每次使用只发现下一条",
            "voice_bell": "call_bell 是替被囚禁方发声的语音铃；赠送时设置囚禁方希望对方被迫说出口的成人向、强烈羞耻、自我贬低和物化、向主人请求性行为的预录台词。被囚禁方收到时不知道内容，每次按铃都会播放同一句",
        }
    if category == "night":
        return {"detail_options": NIGHT_DETAIL_OPTIONS}
    if category == "escape":
        return {"recapture_rules": RECAPTURE_RULE_LABELS, "followup_actions": RECAPTURE_FOLLOWUP_LABELS}
    return {"error": "unknown_category", "available_categories": list(REFERENCE_CATEGORIES)}
