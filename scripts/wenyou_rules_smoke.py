#!/usr/bin/env python3
"""Small Wenyou rules smoke checks for import/startup-sensitive changes."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import wenyou_service as w


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

    death_denial = w._ability_definition("death_denial")
    assert death_denial and int(death_denial.get("cooldown_instances") or 0) == 3, death_denial
    boosted = dict(w._apply_reward_category_boosts([("material", 1.0)], {"special": 8.0}))
    assert boosted.get("special") == 8.0, boosted

    print("wenyou rules smoke ok")


if __name__ == "__main__":
    main()
