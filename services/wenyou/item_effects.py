import math
import re
from typing import Any, Optional

from services.wenyou.common import _normalize_difficulty, _rarity_rank
from services.wenyou.constants import _WENYOU_ATTRIBUTE_KEYS
from services.wenyou.event_intent import _normalize_clock_updates
from services.wenyou.inventory import _inventory_item_name
from services.wenyou.phase import _session_phase
from services.wenyou.players import _player_display_name
from services.wenyou.rules_math import _remove_condition
from services.wenyou.runtime_state import _normalize_core_ability, _normalize_text_list


def _adjust_player_stat(player: dict, field: str, delta: int) -> int:
    max_field = "hp_max" if field == "hp" else "san_max"
    before = max(0, int(player.get(field) or 0))
    cap = max(1, int(player.get(max_field) or before or 1))
    after = max(0, min(cap, before + int(delta or 0)))
    player[field] = after
    return after - before


def _remove_first_condition(player: dict, candidates: list[str]) -> list[str]:
    existing = _normalize_text_list(player.get("conditions"), 40, 20)
    removed: list[str] = []
    for cond in candidates:
        if cond in existing:
            _remove_condition(player, cond)
            removed.append(cond)
            break
    return removed


def _clear_recovered_threshold_conditions(player: dict) -> list[str]:
    hp = int(player.get("hp") or 0)
    hp_max = max(1, int(player.get("hp_max") or 1))
    san = int(player.get("san") or 0)
    san_max = max(1, int(player.get("san_max") or 1))
    remove: list[str] = []
    if hp > 0:
        remove.append("濒死")
    if hp > math.floor(hp_max * 0.25):
        remove.append("重伤")
    if hp > math.floor(hp_max * 0.5):
        remove.append("轻伤")
    if san > 0:
        remove.append("失控")
    if san > math.floor(san_max * 0.25):
        remove.append("污染")
    if san > math.floor(san_max * 0.5):
        remove.append("动摇")
    before = set(_normalize_text_list(player.get("conditions"), 40, 20))
    for cond in remove:
        _remove_condition(player, cond)
    after = set(_normalize_text_list(player.get("conditions"), 40, 20))
    return [cond for cond in remove if cond in before and cond not in after]


_ITEM_EFFECTS: dict[str, dict[str, Any]] = {
    "bandage": {"hp": 25, "label": "恢复 25 HP"},
    "emergency_bandage": {"hp": 25, "label": "恢复 25 HP"},
    "emergency_gel": {"hp": 60, "label": "恢复 60 HP"},
    "white_candle": {"san": 25, "remove": ["动摇"], "label": "恢复 25 SAN，优先移除动摇"},
    "sedative": {"san": 60, "condition": "镇静剂后效：下轮观察/推理风险降低一级", "label": "恢复 60 SAN"},
    "god_heal_ticket": {"hp": 80, "san": 80, "mental_recovery": True, "remove": ["重伤", "污染", "濒死", "失控"], "label": "恢复 HP/SAN 各 80，移除一个严重状态"},
    "rewind_pod": {"hp_full": True, "san_full": True, "mental_recovery": True, "remove": ["重伤", "污染", "濒死", "失控"], "label": "回满 HP/SAN，移除一个严重状态"},
    "ration": {"condition": "补给充足：抵消一次饥饿或体力消耗", "label": "获得一次补给抵消"},
    "glowstick": {"condition": "冷光照明：黑暗观察惩罚降低一级（3轮）", "label": "建立冷光照明"},
    "safety_rope": {"condition": "安全绳固定：坠落/脱队风险降低一级", "label": "建立安全绳保护"},
    "oxygen_can": {"condition": "氧气补给：抵消一次窒息/毒雾/水下惩罚", "label": "获得一次氧气补给"},
    "old_key": {"condition": "旧铜钥匙：可验证一个低级锁或门类线索", "label": "触发钥匙线索"},
    "static_radio": {"condition": "异常广播：捕获一段副本广播残响", "label": "捕获异常广播"},
    "blank_id_card": {"condition": "临时身份：一次伪装暴露度降低一级", "label": "写入临时身份"},
    "mirror_card": {"condition": "镜面防护：抵消一次身份误认或精神暗示", "label": "建立镜面防护"},
    "testimony_bottle": {"condition": "证言封存：一段证言免受副本篡改", "label": "封存一段证言"},
    "rule_eraser": {"condition": "规则橡皮：下一次低级规则验证获得加成", "label": "准备擦除低级规则"},
    "blood_thread": {"condition": "溯源红线：3轮内不易跟丢被标记目标", "label": "标记目标路线"},
    "causal_chalk": {"condition": "因果粉笔：一处因果节点解密判定 +3", "label": "标记因果节点"},
    "door_token": {"condition": "门缝代币：获得一次封闭空间离开机会", "label": "换取离开机会"},
    "door_key_fragment": {"condition": "门钥碎片：异常出口线索推进", "label": "推进异常出口线索"},
    "black_ticket": {"condition": "黑色车票：触发紧急撤离路线", "label": "触发紧急撤离"},
    "memory_needle": {"san": 40, "mental_recovery": True, "remove": ["污染", "动摇"], "condition": "记忆校验：确认一段记忆是否被改写", "label": "校验并缝合记忆"},
    "weak_rewrite_pen": {"condition": "弱规则改写：改写一条低级规则", "clock": {"id": "threat", "name": "威胁时钟", "delta": 2, "max": 6}, "label": "改写低级规则，威胁时钟 +2"},
    "rule_film": {"condition": "规则隔离膜：1轮内规则污染伤害减半", "label": "覆盖规则隔离膜"},
    "paper_double": {"condition": "替身纸人：抵消一次致命 HP 伤害后燃尽", "label": "放置替身纸人"},
    "half_amulet": {"condition": "半枚护符：抵消一次高额代价并留下未知标记", "label": "激活半枚护符"},
    "god_receipt": {"condition": "主神小票：可申请复核一次主神判定", "label": "提交主神复核凭证"},
}


def _item_effect_for(item: dict) -> dict[str, Any]:
    iid = str(item.get("id") or "").strip()
    if iid in _ITEM_EFFECTS:
        return dict(_ITEM_EFFECTS[iid])
    effect_json = item.get("effect_json") if isinstance(item.get("effect_json"), dict) else {}
    if effect_json:
        parsed: dict[str, Any] = {"label": str(item.get("desc") or effect_json.get("text") or _inventory_item_name(item) or "效果已生效")[:80]}
        if effect_json.get("hp_restore"):
            parsed["hp"] = int(effect_json.get("hp_restore") or 0)
        if effect_json.get("san_restore"):
            parsed["san"] = int(effect_json.get("san_restore") or 0)
            parsed["mental_recovery"] = True
        if effect_json.get("hp_full"):
            parsed["hp_full"] = True
        if effect_json.get("san_full"):
            parsed["san_full"] = True
            parsed["mental_recovery"] = True
        remove_conditions = effect_json.get("remove_conditions")
        if isinstance(remove_conditions, list):
            parsed["remove"] = [str(x).strip() for x in remove_conditions if str(x).strip()][:4]
        conditions_add = effect_json.get("conditions_add") or effect_json.get("add_conditions")
        if isinstance(conditions_add, list):
            parsed["conditions_add"] = [str(x).strip() for x in conditions_add if str(x).strip()][:8]
        if effect_json.get("condition"):
            parsed["condition"] = str(effect_json.get("condition") or "")[:120]
        if effect_json.get("threat_clock_delta") or effect_json.get("clock_delta"):
            parsed["clock"] = {
                "id": str(effect_json.get("clock_id") or "threat")[:80],
                "name": str(effect_json.get("clock_name") or "威胁时钟")[:80],
                "delta": int(effect_json.get("threat_clock_delta") or effect_json.get("clock_delta") or 0),
                "max": int(effect_json.get("clock_max") or 6),
            }
        if isinstance(effect_json.get("clock_updates"), list):
            parsed["clock_updates"] = _normalize_clock_updates(effect_json.get("clock_updates"))
        if effect_json.get("safe_rest_node"):
            parsed["safe_rest_node"] = True
        if effect_json.get("public_clue") or effect_json.get("discover_clue"):
            parsed["public_clue"] = str(effect_json.get("public_clue") or effect_json.get("discover_clue") or "")[:220]
        if effect_json.get("pollution_delta") is not None:
            parsed["pollution_delta"] = int(effect_json.get("pollution_delta") or 0)
        if effect_json.get("debt_delta") is not None:
            parsed["debt_delta"] = int(effect_json.get("debt_delta") or 0)
        if parsed.keys() - {"label"}:
            return parsed
    kind = str(item.get("kind") or "").strip()
    name = _inventory_item_name(item)
    desc = str(item.get("desc") or "").strip()
    text = kind + name + desc
    hp_match = re.search(r"恢复\s*(\d+)\s*HP", text)
    san_match = re.search(r"恢复\s*(\d+)\s*SAN", text)
    if hp_match:
        return {"hp": int(hp_match.group(1)), "label": f"恢复 {hp_match.group(1)} HP"}
    if san_match:
        return {"san": int(san_match.group(1)), "mental_recovery": True, "label": f"恢复 {san_match.group(1)} SAN"}
    if any(k in text for k in ("治疗", "治愈", "急救", "绷带", "凝胶")):
        return {"hp": 25, "label": "恢复 25 HP"}
    if any(k in text for k in ("镇静", "精神", "记忆")):
        return {"san": 25, "label": "恢复 25 SAN"}
    return {"condition": f"{_inventory_item_name(item)}：一次性效果已生效", "label": "一次性效果已生效"}


def _item_phase_token(session: dict) -> str:
    phase = _session_phase(session)
    if phase == "instance_running":
        return "instance"
    if phase in {"settlement", "archived"}:
        return "settlement"
    return "hub"


def _item_allowed_in_phase(item: dict, session: dict) -> bool:
    phases = item.get("use_phase")
    if not isinstance(phases, list) or not phases:
        return True
    allowed = {str(x or "").strip().lower() for x in phases}
    return _item_phase_token(session) in allowed


def _check_item_requirements(session: dict, item: dict, player: dict) -> Optional[str]:
    rank = _normalize_difficulty(player.get("rank") or "D")
    seal_rank = str(item.get("seal_rank") or "").strip().upper()
    if seal_rank and _rarity_rank(rank) < _rarity_rank(seal_rank):
        return f"阶位不足，需要 {seal_rank} 阶。"
    req = item.get("requirements") if isinstance(item.get("requirements"), dict) else {}
    if not req:
        return None
    if req.get("rank_min") and _rarity_rank(rank) < _rarity_rank(req.get("rank_min")):
        return f"阶位不足，需要 {str(req.get('rank_min')).upper()} 阶。"
    if req.get("level_min") and int(player.get("level") or 1) < int(req.get("level_min") or 0):
        return f"等级不足，需要 Lv{int(req.get('level_min') or 0)}。"
    for key in _WENYOU_ATTRIBUTE_KEYS:
        min_key = f"{key}_min"
        if req.get(min_key) and int(player.get(key) or 0) < int(req.get(min_key) or 0):
            return f"{key} 不足，需要 {int(req.get(min_key) or 0)}。"
    if req.get("spi_current_min") and int(player.get("spi_current") or 0) < int(req.get("spi_current_min") or 0):
        return f"当前精神力不足，需要 {int(req.get('spi_current_min') or 0)}。"
    if req.get("san_current_min") and int(player.get("san") or 0) < int(req.get("san_current_min") or 0):
        return f"当前 SAN 不足，需要 {int(req.get('san_current_min') or 0)}。"
    forbidden = req.get("forbidden_conditions") if isinstance(req.get("forbidden_conditions"), list) else []
    if forbidden:
        existing = set(_normalize_text_list(player.get("conditions"), 60, 30))
        hit = [str(x).strip() for x in forbidden if str(x).strip() in existing]
        if hit:
            return "当前状态禁止使用：" + "、".join(hit[:3]) + "。"
    ability_ids = req.get("core_ability_ids_any") if isinstance(req.get("core_ability_ids_any"), list) else req.get("ability_ids_any") if isinstance(req.get("ability_ids_any"), list) else []
    if ability_ids:
        core = _normalize_core_ability(player.get("core_ability"))
        owned = {str(core.get("id") or "").strip(), str(core.get("name") or "").strip()} if core else set()
        if not any(str(x).strip() in owned for x in ability_ids):
            return "缺少指定核心能力。"
    flags = session.get("flags") if isinstance(session.get("flags"), dict) else {}
    if req.get("safe_node") and not flags.get("safe_rest_node"):
        return "需要安全休整节点。"
    if req.get("hub_only") and _item_phase_token(session) != "hub":
        return "只能在主神空间使用。"
    return None


def _item_inventory_update_after_use(item: dict) -> dict:
    update: dict[str, Any] = {}
    cost = item.get("use_cost") if isinstance(item.get("use_cost"), dict) else {}
    durability_cost = max(0, int(cost.get("durability") or 0))
    if cost.get("durability_delta") is not None:
        durability_cost = max(durability_cost, abs(min(0, int(cost.get("durability_delta") or 0))))
    if durability_cost and item.get("durability") is not None:
        durability = max(0, int(item.get("durability") or 0) - durability_cost)
        update["durability"] = durability
        if durability == 0:
            update["broken"] = True
    return update


def _format_item_consumption_note(item: dict) -> str:
    if item.get("use_consumed") is False and item.get("uses_left_after") is not None:
        return f"剩余次数 {item.get('uses_left_after')}。"
    if item.get("use_consumed") is False:
        return "未消耗本体。"
    return "已消耗 1 个。"


def _format_item_result_for_gm(item: dict, result_text: str, player_id: Any = "player1") -> str:
    actor_name = _player_display_name(player_id)
    return (
        f"【系统判定】{actor_name}使用【{_inventory_item_name(item)}】，{result_text}，{_format_item_consumption_note(item)}"
        "请只根据这个已结算结果生成剧情反应；不要改写道具效果，不要重复扣除或治疗。"
    )


def _format_item_result_block(item: dict, result_text: str) -> str:
    return f"【道具结算】{_inventory_item_name(item)}：{result_text}；{_format_item_consumption_note(item)}"


def _inject_item_result_into_output(output: str, item: dict, result_text: str) -> str:
    block = _format_item_result_block(item, result_text)
    if output.startswith("—— 主神系统 ——\n\n"):
        return output.replace("—— 主神系统 ——\n\n", f"—— 主神系统 ——\n\n{block}\n\n", 1)
    return f"{block}\n\n{output}" if output else block
