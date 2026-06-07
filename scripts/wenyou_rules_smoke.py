#!/usr/bin/env python3
"""Small Wenyou rules smoke checks for import/startup-sensitive changes."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import wenyou_service as w
from services.wenyou.settlement_rewards import _apply_reward_category_boosts
from services.wenyou.text_sanitize import _strip_gm_context_blocks, _strip_main_god_panel


def _framework() -> dict:
    return {
        "instance_code": "SMOKE-001",
        "instance_name": "烟测回廊",
        "instance_genre": "规则怪谈",
        "difficulty": "D",
        "world": "一条用于规则烟测的走廊。",
        "conflict": "验证怪物与结算规则。",
        "failure_hint": "失败会触发惩罚副本。",
        "reward_hint": "按规则发放。",
        "encounter_profile": {
            "boss": {
                "id": "smoke_boss",
                "name": "烟测 Boss",
                "tier": "boss",
                "rank": "D",
                "stability": 2,
                "seal_target": 2,
                "weaknesses": ["镜面"],
                "seal_conditions": ["镜面"],
                "counterplay": ["削弱", "封印"],
            }
        },
    }


def main() -> None:
    session = w._new_session(_framework())
    monsters = w._ensure_monster_instances(session)
    assert monsters and monsters[0]["tier"] == "boss"

    ok, text, _patch = w._resolve_encounter_action(session, "attack", detail="我一刀砍死 Boss")
    assert ok, text
    boss = w._ensure_monster_instances(session)[0]
    assert boss["status"] != "defeated", boss
    assert boss.get("hp") is None, boss

    ok, text, _patch = w._resolve_encounter_action(session, "weaken", detail="利用镜面验证弱点并削弱它")
    assert ok, text
    boss = w._ensure_monster_instances(session)[0]
    assert int(boss.get("stability") or 0) <= 2, boss

    session["stats"]["player1"]["spi"] = 24
    session["stats"]["player1"]["int"] = 24
    ok, text, _patch = w._resolve_encounter_action(session, "seal", detail="用镜面作为媒介封印它")
    assert ok, text
    boss = w._ensure_monster_instances(session)[0]
    assert int(boss.get("seal_progress") or 0) >= 1, boss

    session2 = w._new_session(_framework())
    candidate = {
        "forced": True,
        "locked": True,
        "queue_id": "revive_labor",
        "core_task": "扮演 NPC 完成系统工单。",
        "tags": ["强制", "惩罚副本", "系统打工"],
    }
    w._attach_forced_instance_contract(session2, candidate)
    wallet = {"points": 0, "debts": 500, "forced_instance_queue": [{"id": "revive_labor", "locked": True}]}
    settlement = {"difficulty": "D"}
    forced = w._apply_forced_instance_settlement(wallet, session2, settlement, "standard_clear")
    assert forced.get("success") is True, forced
    assert session2["forced_instance"]["resolved"] is True

    debt_wallet = {"points": 0, "debts": 3200, "forced_instance_queue": []}
    session_forced = w._new_session(_framework())
    changed = w._refresh_forced_instance_queue(debt_wallet, session_forced)
    assert changed is True, debt_wallet
    queue = debt_wallet.get("forced_instance_queue") or []
    assert queue and queue[0].get("id") == "debt_clearance" and queue[0].get("locked") is True, queue
    forced_candidate = w._forced_candidate_from_queue(queue[0])
    assert forced_candidate.get("forced") is True and "NPC" in forced_candidate.get("core_task", ""), forced_candidate
    w._attach_forced_instance_contract(session_forced, forced_candidate)
    assert session_forced["forced_instance"]["mode"] == "npc_labor", session_forced.get("forced_instance")
    assert "forced_notice" in session_forced["runtime_state"]["public_state"], session_forced["runtime_state"]["public_state"]
    w._bump_forced_instance_exposure(session_forced, "taskers", 1, "烟测暴露")
    assert int(session_forced["forced_instance"].get("exposure_to_taskers") or 0) == 1, session_forced["forced_instance"]

    session_fallback = w._new_session({**_framework(), "encounter_profile": {}})
    fallback_monsters = w._ensure_monster_instances(session_fallback)
    assert fallback_monsters and fallback_monsters[0]["id"] == "ambient_threat", fallback_monsters
    ok, text, patch = w._resolve_encounter_action(session_fallback, "flee", detail="观察路线后从楼梯撤离")
    assert ok, text
    assert patch.get("source") == "rules_engine.encounter", patch
    assert "roll_log" in (patch.get("changes") or {}), patch
    assert session_fallback["runtime_state"]["public_state"].get("visible_monsters"), session_fallback["runtime_state"]["public_state"]

    session3 = w._new_session(_framework())
    unique = w._unique_item_for_proposal(
        {"type": "acquire_unique_item", "visibility": "public", "id": "mirror_blessing", "name": "镜中祝福", "rarity": "B", "effect": "隐藏结局纪念物", "seal_rank": "B"},
        session3,
    )
    session3["stats"]["inventory"] = [w._new_inventory_item(unique, "test", "unique")] if unique else []
    grants = w._apply_state_proposal_item_grants(
        session3,
        [{"type": "acquire_unique_item", "visibility": "public", "id": "mirror_blessing", "name": "镜中祝福", "rarity": "B", "effect": "隐藏结局纪念物", "seal_rank": "B"}],
    )
    assert grants and grants[0].get("category") == "fragment", grants

    core_survival = w._ability_definition("core_survival")
    assert core_survival and int(core_survival.get("uses_per_instance") or 0) == 1, core_survival
    boosted = dict(_apply_reward_category_boosts([("material", 1.0)], {"special": 8.0}))
    assert boosted.get("special") == 8.0, boosted

    context_session = w._new_session(_framework())
    context_session["phase"] = "instance_running"
    context_wallet = w._normalize_wallet(
        {
            "points": 300,
            "wallets": {"player1": {"points": 300}, "player2": {"points": 300, "ledger": [{"type": "test"}]}},
            "inventories": {"player1": [], "player2": [], "task_items": []},
        },
        seed_points=300,
    )
    tool_context = w.compose_ai_player_context(context_session, wallet=context_wallet, context_mode="tool")["ai_player_context"]
    assert "shop_view" in tool_context and "gacha_pools" in tool_context and "recent_ledger" in tool_context, tool_context
    turn_context = w.compose_ai_player_context(context_session, wallet=context_wallet, context_mode="turn")["ai_player_context"]
    for hidden_key in ("shop_view", "gacha_pools", "recent_ledger", "wallet"):
        assert hidden_key not in turn_context, turn_context
    assert set(turn_context.get("available_services") or {}) == {"use_item", "transfer"}, turn_context
    channel_context = w.compose_ai_player_context(context_session, wallet=context_wallet, context_mode="channel")["ai_player_context"]
    for hidden_key in ("shop_view", "gacha_pools", "recent_ledger", "wallet", "inventory", "available_services"):
        assert hidden_key not in channel_context, channel_context

    leaked = """剧情正常开头。
[WENYOU_GM_CONTEXT]
用途：这是后端每轮生成的压缩上下文。GM 只用它维持连续性。
## 当前副本状态
- game_id：secret
## 后端规则态摘要（内部，不要直接剧透）
- 怪物实例：hidden
[/WENYOU_GM_CONTEXT]
剧情正常结尾。"""
    cleaned = _strip_gm_context_blocks(leaked)
    assert "WENYOU_GM_CONTEXT" not in cleaned, cleaned
    assert "后端规则态摘要" not in cleaned, cleaned
    assert "secret" not in cleaned, cleaned
    assert "剧情正常开头" in cleaned and "剧情正常结尾" in cleaned, cleaned
    assert "后端规则态摘要" not in _strip_main_god_panel(leaked), leaked

    print("wenyou rules smoke ok")


if __name__ == "__main__":
    main()
