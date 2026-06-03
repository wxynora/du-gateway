from typing import Any, Optional

from services.co_read_card_qwen import call_card_json_update
from services.wenyou.common import _compact_text
from services.wenyou.runtime_state import _normalize_text_list
from utils.time_aware import now_beijing_iso


WENYOU_CARD_SYSTEM_PROMPT = """你是“App 文游/无限流跑团连续性卡片”的维护器，只负责整理副本连续性，不扮演 GM，不写玩家可见剧情。

你的任务：根据旧文游卡片、当前副本状态和本轮回合，输出新版文游卡片 JSON。

核心原则：
1. 只记录 App 文游/无限流跑团的虚构游戏内容；不要当作现实经历。
2. 这张卡片只供文游 GM/AI 玩家上下文使用，不参与动态召回。
3. 不保存大段剧情原文；最近 8 回合保留简要结果，长期信息沉淀到 story_milestones / open_questions。
4. 不要编造旧卡片和本轮回合没有提供的信息；不确定就写入 open_questions，或者保持旧值。
5. story_milestones 是精选长期节点，不是流水账；删除重复、低价值、已被 recent_rounds 覆盖的条目，最多 12 条。
6. open_questions 只保留会影响后续副本判断的未解规则、线索、NPC/怪物悬念，最多 8 条。
7. recent_rounds 按时间倒序，最多 8 条，每条 gm_result 120-300 字，保留行动结果、规则变化、线索/危险变化。
8. 必须使用 player1_action / player2_action 字段，不要写 xinyue_action 或 ai_player_action。
9. current_instance 必须以输入的 current_instance 为准，只允许轻微压缩，不要改写数值事实。
10. 输出必须是严格 JSON 对象，不要 Markdown，不要代码块，不要解释。

JSON schema：
{
  "version": 1,
  "scope": "wenyou_game_only",
  "note": "App 文游/无限流跑团的虚构游戏连续性卡片，只供文游上下文使用，不参与动态召回。",
  "current_instance": {
    "game_id": "string",
    "instance": "string",
    "genre": "string",
    "difficulty": "D/C/B/A/S",
    "task": "string",
    "phase": "string",
    "points": 0,
    "player1": "string",
    "player2": "string",
    "inventory": ["string"],
    "clues": ["string"]
  },
  "recent_rounds": [
    {
      "at": "string",
      "instance": "string",
      "player1_action": "string",
      "player2_action": "string",
      "gm_result": "string",
      "clues": ["string"],
      "inventory": ["string"]
    }
  ],
  "story_milestones": ["string"],
  "open_questions": ["string"],
  "updated_at": "string"
}
"""


def _list_text(items: Any, item_limit: int, count_limit: int) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items[:count_limit]:
        text = _compact_text(item, item_limit)
        if text:
            out.append(text)
    return out


def _round_entry(raw: Any) -> dict:
    item = raw if isinstance(raw, dict) else {}
    return {
        "at": _compact_text(item.get("at"), 40),
        "instance": _compact_text(item.get("instance"), 120),
        "player1_action": _compact_text(item.get("player1_action") or item.get("xinyue_action"), 260),
        "player2_action": _compact_text(item.get("player2_action") or item.get("ai_player_action"), 260),
        "gm_result": _compact_text(item.get("gm_result"), 700),
        "clues": _list_text(item.get("clues"), 160, 8),
        "inventory": _list_text(item.get("inventory"), 40, 20),
    }


def normalize_wenyou_model_card(raw: Any, *, fallback_current: Optional[dict] = None) -> dict:
    data = raw if isinstance(raw, dict) else {}
    current = data.get("current_instance") if isinstance(data.get("current_instance"), dict) else {}
    if not current and isinstance(fallback_current, dict):
        current = fallback_current
    recent = [_round_entry(x) for x in (data.get("recent_rounds") or []) if isinstance(x, dict)]
    recent = [x for x in recent if x.get("gm_result")]
    return {
        "version": 1,
        "scope": "wenyou_game_only",
        "note": "App 文游/无限流跑团的虚构游戏连续性卡片，只供文游上下文使用，不参与动态召回。",
        "current_instance": current if isinstance(current, dict) else {},
        "recent_rounds": recent[:8],
        "story_milestones": _normalize_text_list(data.get("story_milestones"), 260, 12),
        "open_questions": _normalize_text_list(data.get("open_questions"), 180, 8),
        "updated_at": _compact_text(data.get("updated_at"), 40) or now_beijing_iso(),
        "updated_by": _compact_text(data.get("updated_by") or "card_model", 40),
    }


def build_wenyou_card_update(
    *,
    old_card: dict,
    current_instance: dict,
    round_entry: dict,
) -> tuple[Optional[dict], str]:
    payload = {
        "old_card": old_card if isinstance(old_card, dict) else {},
        "current_instance": current_instance if isinstance(current_instance, dict) else {},
        "current_round": _round_entry(round_entry),
    }
    card, err = call_card_json_update(
        system_prompt=WENYOU_CARD_SYSTEM_PROMPT,
        payload=payload,
        instruction="请根据下面 JSON 更新文游连续性卡片，只返回新版文游卡片 JSON：",
        task_name="文游连续性卡片",
        temperature=0.2,
    )
    if not card:
        return None, err
    return normalize_wenyou_model_card(card, fallback_current=current_instance), ""
