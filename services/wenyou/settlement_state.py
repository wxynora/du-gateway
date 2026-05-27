from typing import Any

from services.wenyou.common import _compact_text, _slug_id
from services.wenyou.runtime_state import _normalize_text_list


def _settlement_flags_from_raw(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    player_flags = data.get("player1") if isinstance(data.get("player1"), dict) else {}
    mainline = player_flags.get("mainline") if isinstance(player_flags.get("mainline"), dict) else {}
    mainline_completion = data.get("mainline_completion")
    if mainline.get("completion") is not None:
        mainline_completion = mainline.get("completion")
    try:
        mainline_completion_value = max(0.0, min(1.0, float(mainline_completion or 0)))
    except (TypeError, ValueError):
        mainline_completion_value = 0.0
    mainline_completed = bool(mainline.get("completed"))
    mainline_status = _compact_text(data.get("mainline_status") or "active", 40)
    if mainline_completed or mainline_completion_value >= 1:
        mainline_status = "completed"

    def completed_names(mapping: Any) -> list[str]:
        if not isinstance(mapping, dict):
            return []
        out: list[str] = []
        for key, item in mapping.items():
            if isinstance(item, dict) and not bool(item.get("completed", True)):
                continue
            name = item.get("name") or item.get("title") or item.get("id") if isinstance(item, dict) else key
            text = _compact_text(name or key, 80)
            if text and text not in out:
                out.append(text)
        return out

    side_completed = _normalize_text_list(data.get("side_completed"), 80, 30)
    side_completed.extend(x for x in completed_names(player_flags.get("side_quests")) if x not in side_completed)
    hidden_completed = _normalize_text_list(data.get("hidden_completed"), 80, 30)
    hidden_completed.extend(x for x in completed_names(player_flags.get("hidden_side_quests")) if x not in hidden_completed)
    hidden_endings = _normalize_text_list(data.get("hidden_endings"), 80, 20)
    hidden_endings.extend(x for x in completed_names(player_flags.get("hidden_endings")) if x not in hidden_endings)
    achievements = _normalize_text_list(data.get("achievements"), 80, 30)
    achievements.extend(x for x in _normalize_text_list(player_flags.get("achievements"), 80, 30) if x not in achievements)
    loss_flags = _normalize_text_list(data.get("loss_flags"), 80, 30)
    losses = player_flags.get("losses") if isinstance(player_flags.get("losses"), dict) else data.get("losses")
    losses = dict(losses) if isinstance(losses, dict) else {}
    reward_tags = _normalize_text_list(data.get("reward_tags"), 60, 40)
    reward_tags.extend(x for x in _normalize_text_list(player_flags.get("reward_tags"), 60, 40) if x not in reward_tags)
    return {
        "mainline_status": mainline_status,
        "mainline_completion": mainline_completion_value,
        "side_completed": side_completed[:30],
        "hidden_completed": hidden_completed[:30],
        "hidden_endings": hidden_endings[:20],
        "achievements": achievements[:30],
        "loss_flags": loss_flags[:30],
        "losses": losses,
        "reward_tags": reward_tags[:40],
        "player1": {
            "mainline": {"completion": mainline_completion_value, "completed": mainline_status == "completed"},
            "side_quests": player_flags.get("side_quests") if isinstance(player_flags.get("side_quests"), dict) else {},
            "hidden_side_quests": player_flags.get("hidden_side_quests") if isinstance(player_flags.get("hidden_side_quests"), dict) else {},
            "hidden_endings": player_flags.get("hidden_endings") if isinstance(player_flags.get("hidden_endings"), dict) else {},
            "achievements": achievements[:30],
            "losses": losses,
            "reward_tags": reward_tags[:40],
        },
    }


def _record_settlement_flag(flags: dict, category: str, value: str) -> None:
    text = _compact_text(value, 80)
    if not text:
        return
    raw = str(category or "").strip().lower()
    player = flags.setdefault("player1", {})
    if not isinstance(player, dict):
        player = {}
        flags["player1"] = player
    if raw in {"main", "mainline", "主线"}:
        flags["mainline_status"] = "completed"
        flags["mainline_completion"] = 1.0
        player["mainline"] = {"completion": 1.0, "completed": True}
        return
    if raw in {"side", "side_quest", "支线"}:
        key = "side_completed"
        player_key = "side_quests"
    elif raw in {"hidden", "hidden_side", "隐藏", "隐藏支线"}:
        key = "hidden_completed"
        player_key = "hidden_side_quests"
    elif raw in {"ending", "hidden_ending", "true_ending", "隐藏结局", "真结局"}:
        key = "hidden_endings"
        player_key = "hidden_endings"
    elif raw in {"loss", "damage", "损耗", "惩罚"}:
        key = "loss_flags"
        player_key = ""
    else:
        key = "achievements"
        player_key = ""
    arr = _normalize_text_list(flags.get(key), 80, 30)
    if text not in arr:
        arr.append(text)
    flags[key] = arr[:30]
    if player_key:
        bucket = player.get(player_key) if isinstance(player.get(player_key), dict) else {}
        sid = _slug_id(text, player_key)
        bucket[sid] = {"id": sid, "name": text, "completed": True}
        player[player_key] = bucket
    elif key == "achievements":
        player["achievements"] = flags[key]


def _reward_context_from_raw(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    return {
        "reward_tags": _normalize_text_list(data.get("reward_tags"), 60, 40),
        "item_grants": [dict(x) for x in data.get("item_grants") or [] if isinstance(x, dict)][-40:],
        "unique_rewards": _normalize_text_list(data.get("unique_rewards"), 80, 20),
    }
