from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from du_imitator_pvz.engine import _engine_from_session
from du_imitator_pvz.game.models import to_jsonable
from du_imitator_pvz.game.player_view import (
    PLANT_NAMES,
    PLANT_SYMBOLS,
    ZOMBIE_NAMES,
    ZOMBIE_SYMBOLS,
)


EVENT_LABELS = {
    "imitator_planted": "种下模仿者",
    "imitator_revealed": "模仿者开奖",
    "reveal_spawned_plant": "开出植物",
    "reveal_spawned_zombie": "开出僵尸",
    "reveal_spawned_boss_event": "开出僵王事件",
    "plant_attack_fired": "植物攻击",
    "plant_produced_sun": "产出阳光",
    "plant_eaten": "植物被吃掉",
    "plant_shoveled": "植物被铲除",
    "imitator_destroyed_before_reveal": "模仿者被摧毁",
    "zombie_spawned": "僵尸入场",
    "zombie_spawned_by_special": "特殊僵尸入场",
    "zombie_died": "僵尸被消灭",
    "lawnmower_triggered": "推车启动",
    "lawnmower_cleared_lane": "推车清路",
    "airdrop_spawned": "空投落地",
    "airdrop_opened": "空投开启",
    "game_won": "关卡通过",
    "game_lost": "防线失守",
    "game_ended_by_player": "主动结束本局",
}


def build_random_imitator_td_spectator_view(save_path: Path) -> dict[str, Any]:
    save_path = Path(save_path)
    records = _read_json(save_path.with_name(f"{save_path.stem}_records.json"))
    base = {
        "ok": True,
        "game_id": "random_imitator_td",
        "save_id": "default",
        "has_save": save_path.exists(),
        "updated_at": _updated_at(save_path),
        "records": _records_view(records),
    }
    if not save_path.exists():
        return {
            **base,
            "setup_required": True,
            "status": "not_started",
            "stage": _empty_stage(),
            "plants": [],
            "pending_imitators": [],
            "zombies": [],
            "boss_events": [],
            "airdrops": [],
            "cards": [],
            "events": [],
            "recent_rounds": [],
        }

    session = _read_json(save_path)
    engine = _engine_from_session(session) if session else None
    if engine is None:
        level = int(session.get("level", 1) or 1)
        loadout = [str(card_id) for card_id in session.get("card_loadout", [])]
        return {
            **base,
            "setup_required": True,
            "status": "setup",
            "stage": {**_empty_stage(), "level": level},
            "plants": [],
            "pending_imitators": [],
            "zombies": [],
            "boss_events": [],
            "airdrops": [],
            "cards": [_card_view(card_id, index + 1, ready=True, remaining=0) for index, card_id in enumerate(loadout)],
            "events": [],
            "recent_rounds": [],
        }

    state = engine.state
    config = engine.config
    wave_progress = engine._wave_progress_observation()
    cards = [
        _card_view(
            str(slot.get("card_id") or ""),
            index + 1,
            ready=bool(slot.get("ready")),
            remaining=int(slot.get("cooldown_remaining_ticks", 0) or 0),
            slot_id=str(slot.get("slot_id") or ""),
        )
        for index, slot in enumerate(engine._card_slot_observations())
    ]
    status = "finished" if state.game_over else "playing"
    cleared_through = max(0, state.level - 1)
    if state.game_over and state.result == "won" and not config.is_endless:
        cleared_through = state.level

    return {
        **base,
        "setup_required": False,
        "status": status,
        "stage": {
            "level": state.level,
            "mode": engine.mode,
            "variant": "airdrop" if config.enable_airdrops else "plain",
            "tick": state.tick,
            "sun": state.sun,
            "rows": config.lanes,
            "cols": config.cols,
            "spawn_x": config.spawn_x,
            "is_day": config.is_day,
            "is_roof": config.is_roof,
            "is_endless": config.is_endless,
            "water_lanes": list(config.water_lanes),
            "fog_start_col": config.fog_start_col,
            "game_over": state.game_over,
            "result": state.result or "",
            "turns": len(engine.player_round_history),
            "cleared_through": cleared_through,
            "wave_progress": wave_progress,
            "lawnmowers": {str(lane): available for lane, available in state.lawnmowers.items()},
        },
        "plants": [
            {
                "entity_id": plant.entity_id,
                "plant_id": plant.plant_id,
                "name": PLANT_NAMES.get(plant.plant_id, plant.plant_id),
                "symbol": PLANT_SYMBOLS.get(plant.plant_id, plant.plant_id[:1]),
                "lane": plant.lane,
                "col": plant.col,
                "hp": plant.hp,
                "max_hp": engine.plant_defs.get(plant.plant_id).hp if engine.plant_defs.get(plant.plant_id) else plant.hp,
                "status": plant.status,
            }
            for plant in sorted(state.plants.values(), key=lambda item: (item.lane, item.col, item.entity_id))
        ],
        "pending_imitators": [
            {
                "entity_id": imitator.entity_id,
                "name": "模仿者",
                "symbol": "模",
                "lane": imitator.lane,
                "col": imitator.col,
                "hp": imitator.hp,
                "reveal_in_ticks": max(0, imitator.reveal_tick - state.tick),
                "status": imitator.status,
            }
            for imitator in sorted(state.pending_imitators.values(), key=lambda item: (item.lane, item.col, item.entity_id))
        ],
        "zombies": [
            {
                "entity_id": zombie.entity_id,
                "zombie_id": zombie.zombie_id,
                "name": ZOMBIE_NAMES.get(zombie.zombie_id, zombie.zombie_id),
                "symbol": ZOMBIE_SYMBOLS.get(zombie.zombie_id, zombie.zombie_id[:1]),
                "lane": zombie.lane,
                "x": zombie.x,
                "hp": zombie.hp,
                "max_hp": engine.zombie_defs.get(zombie.zombie_id).hp if engine.zombie_defs.get(zombie.zombie_id) else zombie.hp,
                "status": zombie.status,
            }
            for zombie in sorted(state.zombies.values(), key=lambda item: (item.lane, item.x, item.entity_id))
        ],
        "boss_events": [
            {
                **to_jsonable(boss),
                "remaining_ticks": max(0, boss.end_tick - state.tick),
            }
            for boss in sorted(state.boss_events.values(), key=lambda item: item.entity_id)
        ],
        "airdrops": [
            {
                **to_jsonable(airdrop),
                "expires_in_ticks": max(0, airdrop.expires_tick - state.tick),
            }
            for airdrop in sorted(state.airdrops.values(), key=lambda item: (item.lane, item.col, item.entity_id))
        ],
        "cards": cards,
        "events": [_event_view(event) for event in engine.event_log if event.visible_to_ai][-12:],
        "recent_rounds": [_round_view(item) for item in engine.player_round_history[-8:]],
    }


def _empty_stage() -> dict[str, Any]:
    return {
        "level": 1,
        "mode": "random_imitator",
        "variant": "plain",
        "tick": 0,
        "sun": 0,
        "rows": 5,
        "cols": 9,
        "spawn_x": 10,
        "is_day": True,
        "is_roof": False,
        "is_endless": False,
        "water_lanes": [],
        "fog_start_col": None,
        "game_over": False,
        "result": "",
        "turns": 0,
        "cleared_through": 0,
        "wave_progress": {"spawned": 0, "total": 0, "completed": False, "remaining": 0},
        "lawnmowers": {str(lane): True for lane in range(1, 6)},
    }


def _card_view(card_id: str, index: int, *, ready: bool, remaining: int, slot_id: str = "") -> dict[str, Any]:
    return {
        "slot_id": slot_id or f"slot_{index}",
        "card_id": card_id,
        "name": PLANT_NAMES.get(card_id, card_id),
        "symbol": "模" if card_id == "imitator" else PLANT_SYMBOLS.get(card_id, card_id[:1]),
        "ready": ready,
        "cooldown_remaining_ticks": remaining,
    }


def _event_view(event: Any) -> dict[str, Any]:
    payload = dict(event.payload or {})
    plant_id = str(payload.get("plant_id") or payload.get("plant_type") or "")
    zombie_id = str(payload.get("zombie_id") or payload.get("zombie_type") or "")
    result_id = str(payload.get("result") or "")
    if not plant_id and result_id in PLANT_NAMES:
        plant_id = result_id
    if not zombie_id and result_id in ZOMBIE_NAMES:
        zombie_id = result_id
    return {
        "event_id": event.event_id,
        "tick": event.tick,
        "type": event.type,
        "label": EVENT_LABELS.get(event.type, event.type.replace("_", " ")),
        "severity": event.severity,
        "lane": payload.get("lane"),
        "col": payload.get("col"),
        "plant_id": plant_id,
        "plant_name": PLANT_NAMES.get(plant_id, plant_id),
        "zombie_id": zombie_id,
        "zombie_name": ZOMBIE_NAMES.get(zombie_id, zombie_id),
        "flavor_text": str(payload.get("flavor_text") or ""),
        "result": result_id,
    }


def _round_view(round_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "round_id": str(round_record.get("round_id") or ""),
        "from_tick": int(round_record.get("from_tick", 0) or 0),
        "to_tick": int(round_record.get("to_tick", 0) or 0),
        "actions": list(round_record.get("executed_actions") or round_record.get("actions") or []),
        "failed_actions": list(round_record.get("failed_actions") or []),
        "result_events": list(round_record.get("result_events") or []),
    }


def _records_view(records: dict[str, Any]) -> dict[str, Any]:
    endless = []
    for record_id, value in records.items():
        if record_id == "version" or not isinstance(value, dict):
            continue
        endless.append({"record_id": record_id, **value})
    return {"endless": endless}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _updated_at(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return ""
