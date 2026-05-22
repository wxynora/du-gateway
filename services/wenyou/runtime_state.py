import re
from typing import Any, Optional

from services.wenyou.common import (
    _normalize_difficulty,
    _normalize_instance_genre,
    _slug_id,
    _to_non_negative_int,
)
from services.wenyou.constants import _DEFAULT_PLAYER_COUNT, _DEFAULT_TASKER_TOTAL


def _default_player_stats() -> dict:
    """文游单名玩家运行时字段默认值（兼容旧 vit/wis，主字段为六属性）。"""
    return {
        "hp": 180,
        "hp_max": 180,
        "san": 180,
        "san_max": 180,
        "spi_current": 10,
        "spi_max": 10,
        "level": 1,
        "rank": "D",
        "exp": 0,
        "str": 10,
        "con": 10,
        "agi": 10,
        "int": 10,
        "spi": 10,
        "luk": 10,
        "vit": 10,
        "wis": 10,
        "physical_attack": 5,
        "ranged_attack": 5,
        "defense": 3,
        "mental_resist": 3,
        "carry_limit": 15,
        "core_ability": None,
        "core_ability_profile": None,
        "unspent_attribute_points": 0,
        "conditions": [],
        "death_count": 0,
        "pollution": 0,
    }


_WENYOU_PLAYER_STATE_KEYS = frozenset(
    {
        "id",
        "player_id",
        "display_name",
        "controller",
        "hp",
        "hp_max",
        "san",
        "san_max",
        "spi_current",
        "spi_max",
        "level",
        "rank",
        "exp",
        "str",
        "con",
        "agi",
        "int",
        "spi",
        "luk",
        "vit",
        "wis",
        "physical_attack",
        "ranged_attack",
        "defense",
        "mental_resist",
        "carry_limit",
        "core_ability",
        "core_ability_profile",
        "unspent_attribute_points",
        "conditions",
        "death_count",
        "pollution",
        "mainline",
        "mainline_status",
        "mainline_completion",
        "achievements",
        "special_trial_cleared",
    }
)


def _normalize_core_ability(raw: Any) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    raw_id = str(raw.get("id") or raw.get("ability_id") or raw.get("name") or "core_ability").strip()
    ability_id = _slug_id(raw_id, "core_ability")
    name = str(raw.get("name") or "").strip()[:80]
    if not name:
        return None
    try:
        uses_per_instance = max(1, int(raw.get("uses_per_instance") or 1))
    except Exception:
        uses_per_instance = 1
    tags = raw.get("tags") or raw.get("source_tags")
    if not isinstance(tags, list):
        tags = []
    ability = {
        "id": ability_id,
        "name": name,
        "rarity": _normalize_difficulty(raw.get("rarity") or "D"),
        "origin": str(raw.get("origin") or "tutorial_performance")[:60],
        "desc": str(raw.get("desc") or raw.get("description") or raw.get("effect") or "").strip()[:260],
        "tags": [str(x).strip()[:40] for x in tags if str(x).strip()][:8],
        "uses_per_instance": uses_per_instance,
    }
    source_tags = raw.get("source_tags")
    if isinstance(source_tags, list):
        ability["source_tags"] = [str(x).strip()[:40] for x in source_tags if str(x).strip()][:8]
    if raw.get("created_at"):
        ability["created_at"] = str(raw.get("created_at"))[:40]
    return ability


def _normalize_player_growth_fields(player: dict) -> dict:
    p = player if isinstance(player, dict) else {}
    for key, fallback in (
        ("str", 10),
        ("con", p.get("vit", 10)),
        ("agi", 10),
        ("int", p.get("wis", 10)),
        ("spi", 10),
        ("luk", 10),
    ):
        p[key] = _to_non_negative_int(p.get(key), int(fallback or 10))
    p["vit"] = p["con"]
    p["wis"] = p["int"]
    p["rank"] = _normalize_difficulty(p.get("rank") or "D")
    p["level"] = max(1, _to_non_negative_int(p.get("level"), 1))
    p["exp"] = _to_non_negative_int(p.get("exp"), 0)
    p["unspent_attribute_points"] = _to_non_negative_int(p.get("unspent_attribute_points"), 0)
    p.pop("ability_tokens", None)
    p.pop("growth_milestone_tokens", None)
    if not isinstance(p.get("core_ability"), dict):
        legacy = _normalize_abilities_list(p.get("abilities"))
        p["core_ability"] = _normalize_core_ability(legacy[0]) if legacy else None
    else:
        p["core_ability"] = _normalize_core_ability(p.get("core_ability"))
    if not isinstance(p.get("core_ability_profile"), dict):
        p["core_ability_profile"] = None
    p["death_count"] = _to_non_negative_int(p.get("death_count"), 0)
    p["pollution"] = _to_non_negative_int(p.get("pollution"), 0)
    p.pop("gear", None)
    p.pop("equipment", None)
    p.pop("weapons", None)
    for key in list(p.keys()):
        if key not in _WENYOU_PLAYER_STATE_KEYS:
            p.pop(key, None)
    return p


def _normalize_abilities_list(raw: Any) -> list[dict]:
    """结构化能力列表：每项 {{name, desc}}，开局 JSON 与面板解析共用。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for x in raw[:12]:
        if isinstance(x, dict):
            name = str(x.get("name") or "").strip()[:48]
            desc = str(x.get("desc") or x.get("description") or "").strip()[:200]
            if name:
                out.append({"name": name, "desc": desc})
        elif isinstance(x, str):
            s = x.strip()
            if not s or s in ("无", "无。", "-", "——"):
                continue
            if "｜" in s:
                a, b = s.split("｜", 1)
            elif "|" in s:
                a, b = s.split("|", 1)
            else:
                a, b = s, ""
            name = a.strip()[:48]
            desc = b.strip()[:200]
            if name:
                out.append({"name": name, "desc": desc})
    return out


def _parse_abilities_line(line: str) -> list[dict]:
    """解析面板「名称｜描述；名称｜描述」单行文本为结构化列表。"""
    line = (line or "").strip()
    if not line or line in ("无", "无。", "-", "——"):
        return []
    parts = re.split(r"[；;]", line)
    chunks = [p.strip() for p in parts if p.strip()]
    return _normalize_abilities_list(chunks)


def _normalize_text_list(raw: Any, item_limit: int = 60, count_limit: int = 20) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip()[:item_limit] for x in raw[:count_limit] if str(x).strip()]


def _normalize_blueprint_list(raw: Any, count_limit: int = 12) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:count_limit]:
        if isinstance(item, dict):
            clean = {str(k): v for k, v in item.items() if str(k).strip()}
            if clean:
                out.append(clean)
    return out


def _normalize_instance_blueprint(raw: Any, fw: Optional[dict] = None) -> dict:
    """Internal instance blueprint required by docs; UI should not reveal it wholesale."""
    data = raw if isinstance(raw, dict) else {}
    base = fw if isinstance(fw, dict) else {}
    conflict = str(base.get("conflict") or "确认主线任务并寻找第一条可验证线索").strip()
    genre_note = str(base.get("genre_note") or "").strip()
    world = str(base.get("world") or "").strip()
    name = str(base.get("instance_name") or "未命名副本").strip()
    blueprint = {
        "blueprint_version": int(data.get("blueprint_version") or data.get("version") or 1),
        "logline": str(data.get("logline") or conflict or name).strip()[:240],
        "mainline": _normalize_blueprint_list(data.get("mainline"), 8),
        "side_quests": _normalize_blueprint_list(data.get("side_quests"), 8),
        "hidden_side_quests": _normalize_blueprint_list(data.get("hidden_side_quests"), 8),
        "hidden_endings": _normalize_blueprint_list(data.get("hidden_endings"), 8),
        "clue_graph": _normalize_blueprint_list(data.get("clue_graph"), 16),
        "npc_arcs": data.get("npc_arcs") if isinstance(data.get("npc_arcs"), dict) else {},
        "threat_clocks": _normalize_blueprint_list(data.get("threat_clocks"), 8),
        "hard_constraints": _normalize_text_list(data.get("hard_constraints"), 140, 12),
    }
    if not blueprint["mainline"]:
        blueprint["mainline"] = [
            {
                "phase": "开场",
                "goal": conflict or "确认任务与第一处异常",
                "required_clues": [],
                "fail_forward": "错过关键线索时，由 NPC、环境变化或主神提示以更高代价推进。",
            }
        ]
    if not blueprint["clue_graph"] and (genre_note or world):
        blueprint["clue_graph"] = [
            {
                "id": "opening_anomaly",
                "public_text": (genre_note or world)[:160],
                "leads_to": [],
                "is_required_for_mainline": True,
            }
        ]
    if not blueprint["hard_constraints"]:
        blueprint["hard_constraints"] = [
            "不能过早直接揭示真结局",
            "NPC 可以误导或抢资源，但默认不能无因果直接致死玩家",
            "关键线索错过时必须 fail-forward，而不是让剧情卡死",
        ]
    return blueprint


def _normalize_public_secret(raw: dict, fw: dict) -> tuple[dict, dict]:
    public = raw.get("public") if isinstance(raw.get("public"), dict) else {}
    secret = raw.get("gm_secret") if isinstance(raw.get("gm_secret"), dict) else {}
    clean_public = {
        "instance_name": str(public.get("instance_name") or fw.get("instance_name") or "").strip(),
        "genre": public.get("genre") if isinstance(public.get("genre"), list) else [fw.get("instance_genre")],
        "difficulty": _normalize_difficulty(public.get("difficulty") or fw.get("difficulty")),
        "visible_rules": _normalize_text_list(public.get("visible_rules"), 180, 12),
        "public_task": str(public.get("public_task") or fw.get("conflict") or "").strip(),
    }
    clean_secret = {
        "true_rules": _normalize_text_list(secret.get("true_rules"), 180, 20),
        "false_rules": _normalize_text_list(secret.get("false_rules"), 180, 20),
        "npc_goals": secret.get("npc_goals") if isinstance(secret.get("npc_goals"), dict) else {},
        "npc_private_state": secret.get("npc_private_state") if isinstance(secret.get("npc_private_state"), dict) else {},
        "hidden_endings": _normalize_blueprint_list(secret.get("hidden_endings"), 10),
    }
    return clean_public, clean_secret


def _normalize_encounter_profile(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    boss = data.get("boss") if isinstance(data.get("boss"), dict) else {}
    return {
        "common": _normalize_blueprint_list(data.get("common"), 8),
        "elite": _normalize_blueprint_list(data.get("elite"), 4),
        "boss": boss,
        "spawn_rules": _normalize_blueprint_list(data.get("spawn_rules"), 12),
        "balance_notes": str(data.get("balance_notes") or "").strip()[:500],
    }


def _normalize_player_count(raw: dict) -> int:
    try:
        value = int(raw.get("player_count") or _DEFAULT_PLAYER_COUNT)
    except Exception:
        value = _DEFAULT_PLAYER_COUNT
    return max(1, min(13, value))


def _normalize_tasker_total(raw: dict, player_count: int) -> int:
    arr = raw.get("npc_taskers")
    fallback = player_count + len(arr) if isinstance(arr, list) and arr else _DEFAULT_TASKER_TOTAL
    try:
        total = int(raw.get("tasker_total") or fallback)
    except Exception:
        total = fallback
    total = max(2, min(13, total))
    return max(player_count, total)


def _normalize_npc_taskers(raw: dict, tasker_total: Optional[int] = None, player_count: Optional[int] = None) -> list[dict]:
    """任务者 NPC 数量跟随 rules doc: npc_tasker_count = tasker_total - player_count."""
    arr = raw.get("npc_taskers")
    if not isinstance(arr, list):
        arr = []
    pc = int(player_count or _normalize_player_count(raw))
    total = int(tasker_total or _normalize_tasker_total(raw, pc))
    npc_count = max(0, min(12, total - pc))
    out: list[dict] = []
    for i in range(npc_count):
        if i < len(arr) and isinstance(arr[i], dict):
            d = arr[i]
            out.append(
                {
                    "name": str(d.get("name") or f"NPC{i+1}")[:48].strip(),
                    "instance_name": str(d.get("instance_name") or d.get("alias_name") or "")[:48].strip(),
                    "tier_note": str(d.get("tier_note") or "未知")[:32].strip(),
                    "stance": str(d.get("stance") or "立场未明")[:48].strip(),
                    "intent": str(d.get("intent") or "")[:80].strip(),
                    "trouble_chance": max(0, min(100, _to_non_negative_int(d.get("trouble_chance"), 0))),
                    "status": str(d.get("status") or "alive")[:24].strip() or "alive",
                    "blurb": str(d.get("blurb") or "")[:200].strip(),
                }
            )
        else:
            out.append(
                {
                    "name": f"任务者{i+3}",
                    "instance_name": "",
                    "tier_note": "待定",
                    "stance": "立场未明",
                    "intent": "",
                    "trouble_chance": 0,
                    "status": "alive",
                    "blurb": "主神档案尚未同步",
                }
            )
    return out


def _framework_for_runtime(fw: Optional[dict]) -> dict:
    """旧存档补全 difficulty / npc_taskers / instance_genre，避免缺字段。"""
    out = dict(fw or {})
    out["difficulty"] = _normalize_difficulty(out.get("difficulty"))
    out["instance_genre"] = _normalize_instance_genre(out.get("instance_genre"))
    gn = str(out.get("genre_note") or "").strip()
    out["genre_note"] = gn[:300] if gn else ""
    out["player_count"] = _normalize_player_count(out)
    out["tasker_total"] = _normalize_tasker_total(out, out["player_count"])
    n = out.get("npc_taskers")
    expected_npc = max(0, int(out["tasker_total"]) - int(out["player_count"]))
    if not isinstance(n, list) or len(n) != expected_npc:
        out["npc_taskers"] = _normalize_npc_taskers(out, out["tasker_total"], out["player_count"])
    public, gm_secret = _normalize_public_secret(out, out)
    out["public"] = public
    out["gm_secret"] = gm_secret
    out["instance_blueprint"] = _normalize_instance_blueprint(out.get("instance_blueprint"), out)
    return out
