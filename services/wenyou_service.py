# 文游：App 内独立副本会话，GM 走 DeepSeek，与主聊天链路隔离（存 R2 wenyou/）
import ast
import copy
import json
import math
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from config import BASE_DIR
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso
from services.wenyou.common import (
    _extract_json_object,
    _first_json_object_span,
    _normalize_difficulty,
    _normalize_instance_genre,
    _rarity_rank,
    _slug_id,
    _to_non_negative_int,
)
from services.wenyou.constants import (
    _DEFAULT_PLAYER_COUNT,
    _DEFAULT_TASKER_TOTAL,
    _WENYOU_ACTION_MODIFIER,
    _WENYOU_ATTRIBUTE_KEYS,
    _WENYOU_CLEAR_BASE_REWARD,
    _WENYOU_CORE_ABILITY_ARCHETYPES,
    _WENYOU_DIFFICULTY_MULTIPLIER,
    _WENYOU_EVENT_TAGS,
    _WENYOU_INSTANCE_GENRES,
    _WENYOU_LEVEL_EXP_TABLE,
    _WENYOU_PROMOTION_RULES,
    _WENYOU_RANK_ATTRIBUTE_HARD_CAP,
    _WENYOU_RANK_ATTRIBUTE_SOFT_CAP,
    _WENYOU_RANK_HP_BONUS,
    _WENYOU_RANK_MENTAL_REDUCTION,
    _WENYOU_RANK_ORDER,
    _WENYOU_RANK_PHYSICAL_REDUCTION,
    _WENYOU_RANK_SAN_BONUS,
    _WENYOU_RANK_SPI_BONUS,
    _WENYOU_RATING_BONUS,
    _WENYOU_RATING_LABELS,
    _WENYOU_RATING_OPTIONS,
    _WENYOU_RESULT_FACTORS,
    _WENYOU_RESULT_OPTIONS,
    _WENYOU_REVIVE_BASE_COST,
    _WENYOU_REWARD_CATEGORY_LABELS,
    _WENYOU_REWARD_CATEGORY_RATES,
    _WENYOU_REWARD_RARITY_RATES,
    _WENYOU_REWARD_TABLE_CONFIG,
    _WENYOU_RISK_DAMAGE,
    _WENYOU_SELL_RATIO,
    _WENYOU_TUTORIAL_ATTRIBUTE_POINTS,
    _WENYOU_TUTORIAL_GIFT_ITEM_IDS,
    _WENYOU_TUTORIAL_INSTANCE_ID,
)
from services.wenyou.abilities import _WENYOU_ABILITY_CATALOG
from services.wenyou.catalog import (
    _CONTENT_ITEM_CATALOG,
    _GACHA_CATALOG,
    _GACHA_FRAGMENT_VALUES,
    _GACHA_ITEMS_BY_RARITY,
    _GACHA_POOL_RATES,
    _GACHA_SINGLE_COST,
    _ITEM_CATALOG_BY_ID,
    _ITEM_CATALOG_BY_NAME,
    _SHOP_CATALOG,
    _catalog_item_definition,
)
from services.wenyou.deepseek_client import _load_templates, call_wenyou_deepseek
from services.wenyou.inventory import (
    _add_inventory_item,
    _carryable_inventory,
    _consume_inventory_item,
    _consume_inventory_requirements,
    _inventory_find_by_name,
    _inventory_has_item,
    _inventory_item_name,
    _inventory_label_list,
    _inventory_quantity,
    _inventory_update_item,
    _item_locked_for_recycle,
    _item_reference_price,
    _merge_inventory,
    _new_inventory_item,
    _normalize_inventory,
    _unseal_inventory_by_rank,
)
from services.wenyou.phase import (
    _normalize_phase,
    _phase_label,
    _session_phase,
    _shop_open_for_phase,
)
from services.wenyou.prompts import (
    _CANDIDATES_SYSTEM,
    _FRAMEWORK_SYSTEM,
    _GM_SYSTEM_TEMPLATE,
    _candidates_prompt,
    _format_genre_note_line,
    _format_genre_rules_for_gm,
    _framework_prompt_custom,
    _framework_prompt_random,
)
from services.wenyou.runtime_state import (
    _default_player_stats,
    _framework_for_runtime,
    _normalize_core_ability,
    _normalize_encounter_profile,
    _normalize_instance_blueprint,
    _normalize_npc_taskers,
    _normalize_player_count,
    _normalize_player_growth_fields,
    _normalize_public_secret,
    _normalize_tasker_total,
    _normalize_text_list,
    _parse_abilities_line,
)

logger = get_logger(__name__)

# 第二次开局确认（仅内存，进程重启后需再确认）
_PENDING_STORY_CONFIRM: dict[int, bool] = {}
_PENDING_LOCK = threading.Lock()
_STORY_EXPANSION_JOBS: dict[str, dict] = {}
_STORY_EXPANSION_JOBS_LOCK = threading.Lock()
_STORY_EXPANSION_JOB_TTL_SECONDS = 15 * 60
_FORCED_FRAMEWORK_CACHE_TARGET = 3
_FORCED_FRAMEWORK_CACHE_MAX = 5
_FORCED_FRAMEWORK_PREFETCHING: set[int] = set()
_FORCED_FRAMEWORK_PREFETCH_LOCK = threading.Lock()
_WENYOU_MEMORY_WINDOW_ID = "wenyou"
_WENYOU_SUMMARY_EVERY_N_ROUNDS = 4
try:
    _WENYOU_TEST_MIN_POINTS = max(0, int(os.environ.get("WENYOU_TEST_MIN_POINTS", "0") or "0"))
except Exception:
    _WENYOU_TEST_MIN_POINTS = 0


def _merge_one_player(cur: dict, new: dict, include_vitals: bool = True) -> dict:
    """将 GM 面板中的部分字段合并进玩家状态，并约束血/精神在上限内。"""
    out = dict(cur)
    for k in (
        "hp",
        "hp_max",
        "san",
        "san_max",
        "spi_current",
        "spi_max",
        "level",
        "exp",
        "str",
        "con",
        "agi",
        "int",
        "spi",
        "luk",
        "vit",
        "wis",
        "unspent_attribute_points",
        "death_count",
        "pollution",
    ):
        if not include_vitals and k in {"hp", "hp_max", "san", "san_max"}:
            continue
        if k not in new:
            continue
        v = int(new[k])
        if k == "level":
            out[k] = max(1, v)
        elif k in ("hp_max", "san_max"):
            out[k] = max(1, v)
        else:
            out[k] = max(0, v)
    if "rank" in new:
        out["rank"] = _normalize_difficulty(new["rank"])
    if "core_ability" in new:
        out["core_ability"] = _normalize_core_ability(new.get("core_ability"))
    if "conditions" in new and isinstance(new["conditions"], list):
        out["conditions"] = _normalize_text_list(new["conditions"])
    out = _normalize_player_growth_fields(out)
    _recalc_player_caps(out)
    hm = max(1, int(out.get("hp_max") or 100))
    sm = max(1, int(out.get("san_max") or 100))
    if "hp" in new:
        out["hp"] = max(0, min(int(new["hp"]), hm))
    else:
        out["hp"] = max(0, min(int(out.get("hp", 0)), hm))
    if "san" in new:
        out["san"] = max(0, min(int(new["san"]), sm))
    else:
        out["san"] = max(0, min(int(out.get("san", 0)), sm))
    out["spi_current"] = max(0, min(int(out.get("spi_current") or 0), int(out.get("spi_max") or 1)))
    return out

def _format_tasker_regiment_for_gm(fw: dict) -> str:
    """写入 GM system：难度 + tasker_total 2-13 编制说明 + NPC 档案。"""
    def _show_name(real_name: str, instance_name: str) -> str:
        rn = str(real_name or "").strip()
        inn = str(instance_name or "").strip()
        if inn and inn != rn:
            return f"{rn}（{inn}）"
        return rn

    diff = _normalize_difficulty(fw.get("difficulty"))
    p1n = _show_name(fw.get("player1_name") or "玩家一", fw.get("player1_instance_name") or "")
    p2n = _show_name(fw.get("player2_name") or "玩家二", fw.get("player2_instance_name") or "")
    pc = _normalize_player_count(fw)
    total = _normalize_tasker_total(fw, pc)
    npc_count = max(0, total - pc)
    lines = [
        f"- 难度等级：**{diff}**（D 最易，S 最险；越高则环境越危险、规则越苛刻，NPC 中越容易混有「大佬」或「炮灰」，恶意与博弈也更强）。",
        f"- 编制：tasker_total={total}，当前玩家角色 {pc} 名（玩家一「{p1n}」、玩家二「{p2n}」），NPC 任务者 {npc_count} 名，须在同一副本规则下互动（NPC 可分批登场、可退场或死亡，但须有因果，不得无交代消失）。",
        "- NPC 可与难度相应（内部定位可区分新人/炮灰/老练/大佬），但这些定位不得直接告知玩家；玩家只能通过剧情表现自行判断。注意：NPC 真实立场对玩家默认不可知，不得在设定里直给“好/坏”结论；禁止过度血腥虐待描写。",
        "",
        "NPC 任务者档案（须在剧情中落实）：",
    ]
    if npc_count <= 0:
        return "\n".join(
            [
                f"- 难度等级：**{diff}**（D 最易，S 最险）。",
                f"- 编制：tasker_total={total}，当前玩家角色 {pc} 名（玩家一「{p1n}」、玩家二「{p2n}」），没有其他任务者 NPC。",
                "- 本局只围绕真实玩家角色推进，不要临时生成同场任务者，不要写陌生任务者名单。",
            ]
        )
    for i, n in enumerate(fw.get("npc_taskers") or []):
        if isinstance(n, dict):
            nshow = _show_name(n.get("name", ""), n.get("instance_name", ""))
            status = n.get("status") or "alive"
            intent = n.get("intent") or "未公开"
            lines.append(
                f"  · {i+1}. 「{nshow}」｜{n.get('tier_note', '')}｜公开信息：{n.get('blurb', '')}（公开态度：{n.get('stance', '未知')}；状态：{status}；意图：{intent}）"
            )
    return "\n".join(lines)


def _format_tutorial_guides_for_gm(fw: dict) -> str:
    if not (fw.get("is_tutorial") or str(fw.get("tutorial_id") or "") == _WENYOU_TUTORIAL_INSTANCE_ID):
        return ""
    guides = _normalize_text_list(fw.get("tutorial_guides"), 220, 12)
    if not guides:
        guides = [
            "只在关键节点用一两句【主神提示】引导，不要整段教学说明。",
            "第一轮优先提示可用“观察 / 检查 / 移动 / 使用道具”等基础行动。",
            "玩家卡住时提示可查看任务、背包和角色面板；不要替玩家做选择。",
        ]
    body = "\n".join(f"- {line}" for line in guides)
    return "\n## 新手副本引导（本局额外规则）\n" + body


def _format_forced_instance_guidance_for_gm(session: dict, fw: dict) -> str:
    forced = session.get("forced_instance") if isinstance(session.get("forced_instance"), dict) else None
    if not forced or str(forced.get("mode") or "") != "npc_labor":
        return ""
    player1 = str(fw.get("player1_name") or "玩家一").strip() or "玩家一"
    player2 = str(fw.get("player2_name") or "玩家二").strip() or "玩家二"
    return f"""
## 惩罚副本 · 临时 NPC 模式（本局额外规则）
- 本局仍是无限流副本：存在正常任务者队伍、规则、线索、危险、通关目标和主神结算。
- 玩家一「{player1}」和玩家二「{player2}」都不是正常任务者，而是一起被系统塞入副本世界的原住民 NPC；两人的公开姓名必须分别使用「{player1}」「{player2}」，不得另起本名、化名、小名或真实姓名。
- 正常任务者才是表层通关队伍，他们的任务可以围绕玩家一 NPC、玩家二 NPC，或两人共同牵涉的生死、秘密、病症、嫌疑、继承权、献祭、异常状态展开。
- 玩家一与玩家二的共同目标是演好 NPC，用符合身份的反应、关系、线索、阻碍或求助推动正常任务者进度；不要把任何一人写成自己通关、打 Boss、找出口的普通任务者。
- 每个关键阶段都要让正常任务者有可见行动压力：试探规则、争执、误判、隐瞒线索、求助玩家 NPC、利用玩家 NPC 或因错误选择受伤/死亡。
- 规则必须通过行动验证，不要一次性公开完整答案；错过线索时用威胁推进、身份被怀疑、任务者伤亡或异常加压继续剧情。
- 主神/系统只在开场、阶段变化、违规、倒计时或结算预警时短促出现，保持压迫感，不要写成长篇说明书。
- 如果任一玩家代号与副本家族、时代、地域或身份结构有违和，不要改名消除；把违和写成剧情钩子，如随母姓、收养、过继、家产侵占、族谱涂改、冒名顶替或异常保留姓名。
- NPC 身份越核心，危险越高；Boss/异常阵营必须有理由控制、利用、杀死、替换或误导玩家 NPC。禁止把核心 NPC 写成安全旁观者。
- 玩家一和玩家二都不能直接说出玩家、任务者、清算对象、外来者、系统或副本真相；不能直接剧透答案、带队通关或跳出 NPC 身份解释机制。
- 正文仍固定玩家一视角；玩家二通过玩家一能看到、听到、交流到的方式出场，不要写成上帝视角双主角。
- 债务、污染、复活、契约等只作为后端清算原因；叙事里不要把它们写成剧情主题或系统工单。
""".strip()


def _format_blueprint_for_gm(fw: dict) -> str:
    bp = _normalize_instance_blueprint(fw.get("instance_blueprint"), fw)
    secret = fw.get("gm_secret") if isinstance(fw.get("gm_secret"), dict) else {}
    payload = {
        "instance_blueprint": bp,
        "gm_secret_summary": {
            "true_rules": secret.get("true_rules") or [],
            "false_rules": secret.get("false_rules") or [],
            "npc_goals": secret.get("npc_goals") or {},
            "npc_private_state": secret.get("npc_private_state") or {},
            "hidden_endings": secret.get("hidden_endings") or [],
        },
        "encounter_profile": _normalize_encounter_profile(fw.get("encounter_profile")),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:4000]


def _normalize_framework(raw: dict) -> dict:
    """兼容旧存档：缺省字段填空串。"""
    code = str(raw.get("instance_code") or "").strip()
    name = str(raw.get("instance_name") or "").strip()
    if not code and not name:
        code, name = "—", "未命名副本"
    elif not code:
        code = "—"
    elif not name:
        name = "未命名副本"
    gn = str(raw.get("genre_note") or "").strip()
    player_count = _normalize_player_count(raw)
    tasker_total = _normalize_tasker_total(raw, player_count)
    out = {
        "instance_code": code,
        "instance_name": name,
        "world": str(raw.get("world") or "").strip(),
        "instance_genre": _normalize_instance_genre(raw.get("instance_genre")),
        "genre_note": gn[:300] if gn else "",
        "player1_name": str(raw.get("player1_name") or "玩家一").strip(),
        "player1_instance_name": str(raw.get("player1_instance_name") or "").strip(),
        "player1_role": str(raw.get("player1_role") or "").strip(),
        "player2_name": str(raw.get("player2_name") or "玩家二").strip(),
        "player2_instance_name": str(raw.get("player2_instance_name") or "").strip(),
        "player2_role": str(raw.get("player2_role") or "").strip(),
        "conflict": str(raw.get("conflict") or "").strip(),
        "failure_hint": str(raw.get("failure_hint") or "由主神规则判定，细节在副本中逐步显露。").strip(),
        "reward_hint": str(raw.get("reward_hint") or "视通关表现给予积分或线索类回报（风味）。").strip(),
        "opening": str(raw.get("opening") or "").strip(),
        "difficulty": _normalize_difficulty(raw.get("difficulty")),
        "player_count": player_count,
        "tasker_total": tasker_total,
        "npc_taskers": _normalize_npc_taskers(raw, tasker_total, player_count),
        "encounter_profile": _normalize_encounter_profile(raw.get("encounter_profile")),
        "initial_stats": _normalize_initial_stats(raw),
        "is_tutorial": bool(raw.get("is_tutorial") or raw.get("tutorial") or str(raw.get("tutorial_id") or "") == _WENYOU_TUTORIAL_INSTANCE_ID),
        "tutorial_id": str(raw.get("tutorial_id") or "").strip(),
        "tutorial_guides": _normalize_text_list(raw.get("tutorial_guides"), 220, 12),
    }
    public, gm_secret = _normalize_public_secret(raw, out)
    out["public"] = public
    out["gm_secret"] = gm_secret
    out["instance_blueprint"] = _normalize_instance_blueprint(raw.get("instance_blueprint"), out)
    return out


def _normalize_initial_stats(raw: dict) -> dict:
    """开局 JSON 中的 initial_stats：积分、双玩家血/精神/等级阶位/六属性/核心能力、道具列表。"""
    ist = raw.get("initial_stats")
    if not isinstance(ist, dict):
        ist = {}

    def _one(pk: str) -> dict:
        d = ist.get(pk) if isinstance(ist.get(pk), dict) else {}
        player = _default_player_stats()
        player.update(
            {
                "level": max(1, int(d.get("level") or 1)),
                "exp": max(0, int(d.get("exp") or 0)),
                "rank": _normalize_difficulty(d.get("rank") or d.get("tier") or "D"),
                "str": max(0, int(d.get("str") or d.get("strength") or 10)),
                "con": max(0, int(d.get("con") or d.get("vit") or d.get("vitality") or 10)),
                "agi": max(0, int(d.get("agi") or d.get("agility") or 10)),
                "int": max(0, int(d.get("int") or d.get("wis") or d.get("wisdom") or 10)),
                "spi": max(0, int(d.get("spi") or d.get("spirit") or 10)),
                "luk": max(0, int(d.get("luk") or d.get("luck") or 10)),
                "unspent_attribute_points": max(0, int(d.get("unspent_attribute_points") or 0)),
                "death_count": max(0, int(d.get("death_count") or 0)),
                "pollution": max(0, int(d.get("pollution") or 0)),
            }
        )
        player["core_ability"] = _normalize_core_ability(d.get("core_ability"))
        player["conditions"] = _normalize_text_list(d.get("conditions"))
        player = _normalize_player_growth_fields(player)
        _recalc_player_caps(player)
        player["hp"] = max(0, min(int(d.get("hp") or player.get("hp_max") or 180), int(player.get("hp_max") or 180)))
        player["san"] = max(0, min(int(d.get("san") or player.get("san_max") or 180), int(player.get("san_max") or 180)))
        player["spi_current"] = max(0, min(int(d.get("spi_current") or player.get("spi_max") or 10), int(player.get("spi_max") or 10)))
        return player

    pts = max(0, int(ist.get("points") or 100))
    items = ist.get("items")
    if not isinstance(items, list):
        items = []
    items_clean = _normalize_inventory(items, source="initial")[:20]
    return {
        "points": pts,
        "player1": _one("player1"),
        "player2": _one("player2"),
        "items": items_clean,
    }


def _difficulty_from_progress(user_id: int) -> str:
    """
    根据最近一次归档中的玩家成长建议随机副本难度：
    新人（Lv1/D）优先 D/C；成长后逐步提升。
    """
    uid = int(user_id or 0)
    # 文游会话使用 App 内独立 ID，仅 0 视为未配置。
    if uid == 0:
        return "D"
    arch = r2_store.get_wenyou_last_archive(uid) or {}
    st = arch.get("stats") if isinstance(arch, dict) else {}
    if not isinstance(st, dict):
        return "D"
    p1 = st.get("player1") if isinstance(st.get("player1"), dict) else {}
    p2 = st.get("player2") if isinstance(st.get("player2"), dict) else {}
    lv_max = max(int(p1.get("level") or 1), int(p2.get("level") or 1))
    rk = _normalize_difficulty(p1.get("rank") or p2.get("rank") or "D")
    rank_order = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4}
    r = rank_order.get(rk, 0)
    if lv_max <= 1 and r <= 0:
        return random.choice(["D", "C"])
    if lv_max <= 2 and r <= 1:
        return random.choice(["C", "B"])
    if lv_max <= 4 and r <= 2:
        return random.choice(["B", "A"])
    return random.choice(["A", "S"])


def _stats_runtime_from_framework(fw: dict) -> dict:
    """由 framework.initial_stats 生成运行时 stats（含 phase、inventory）。"""
    fw = _framework_for_runtime(dict(fw or {}))
    init = _normalize_initial_stats({"initial_stats": fw.get("initial_stats")})
    stats = {
        "phase": "instance_running",
        "points": init["points"],
        "player1": dict(init["player1"]),
        "player2": dict(init["player2"]),
        "inventory": _normalize_inventory(init.get("items"), source="initial"),
    }
    stats["player1"]["display_name"] = _normalize_player_display_name(fw.get("player1_name"), "玩家一")
    stats["player1"]["controller"] = "human"
    stats["player2"]["display_name"] = _normalize_player_display_name(fw.get("player2_name"), "玩家二")
    stats["player2"]["controller"] = "ai"
    return stats


def _session_ensure_stats(session: dict) -> None:
    """旧 session 无 stats 时从 framework 补全。"""
    if isinstance(session, dict):
        session.setdefault("clocks", [])
        session.setdefault("event_log", [])
    if session.get("stats") and isinstance(session["stats"], dict):
        session["stats"]["phase"] = _normalize_phase(session["stats"].get("phase"))
        session["stats"]["inventory"] = _normalize_inventory(session["stats"].get("inventory"), source="session")
        session["stats"].setdefault("points", 100)
        base = _default_player_stats()
        for k in ("player1", "player2"):
            cur = session["stats"].get(k)
            if not isinstance(cur, dict):
                session["stats"][k] = {**dict(base), "display_name": _WENYOU_PLAYER_LABELS.get(k, k), "controller": _WENYOU_PLAYER_CONTROLLERS.get(k, "human")}
            else:
                for bk, bv in base.items():
                    cur.setdefault(bk, bv)
                cur.setdefault("display_name", _WENYOU_PLAYER_LABELS.get(k, k))
                cur.setdefault("controller", _WENYOU_PLAYER_CONTROLLERS.get(k, "human"))
                _normalize_player_growth_fields(cur)
                cur["conditions"] = _normalize_text_list(cur.get("conditions"))
                _recalc_player_caps(cur)
        return
    fw = session.get("framework") or {}
    session["stats"] = _stats_runtime_from_framework(_framework_for_runtime(fw))


def _format_stats_for_gm_prompt(session: dict) -> str:
    """供 GM system 占位：当前积分、场地、血精神、成长与核心能力、道具。"""
    _session_ensure_stats(session)
    st = session["stats"]
    phase = _normalize_phase(st.get("phase"))
    loc = "主神空间" if phase in {"hub", "settlement"} else "副本"
    p1 = st.get("player1") or {}
    p2 = st.get("player2") or {}
    inv = _normalize_inventory(st.get("inventory"), source="session")
    inv_s = "、".join(_inventory_label_list(inv)) if inv else "无"

    def _line_player(label: str, p: dict) -> str:
        core = _normalize_core_ability(p.get("core_ability"))
        core_text = f"{core.get('name')}｜{core.get('desc')}" if core else "无（新手副本通关后按表现生成）"
        return (
            f"- {label}：HP {p.get('hp', 0)}/{p.get('hp_max', 1)}，SAN {p.get('san', 0)}/{p.get('san_max', 1)}，当前精神力 {p.get('spi_current', 0)}/{p.get('spi_max', 0)}；"
            f"Lv{p.get('level', 1)} EXP {p.get('exp', 0)} 阶位{p.get('rank', 'D')}；"
            f"力{p.get('str', 0)} 体{p.get('con', p.get('vit', 0))} 敏{p.get('agi', 0)} 智{p.get('int', p.get('wis', 0))} 精{p.get('spi', 0)} 运{p.get('luk', 0)}\n"
            f"- {label}核心能力（系统字段，GM 不自行新增）：{core_text}"
        )

    return (
        f"- 场地（系统记录）：{loc}\n"
        f"- 主神积分：{int(st.get('points') or 0)}\n"
        f"{_line_player('玩家一', p1)}\n"
        f"{_line_player('玩家二', p2)}\n"
        f"- 道具：{inv_s}"
    )


def _format_status_footer(session: dict) -> str:
    """App 展示的状态栏（与【主神面板】数值对齐，以 session 为准）。"""
    _session_ensure_stats(session)
    st = session["stats"]
    phase = _normalize_phase(st.get("phase"))
    loc = "主神空间" if phase in {"hub", "settlement"} else "副本"
    p1 = st.get("player1") or {}
    p2 = st.get("player2") or {}
    inv = _normalize_inventory(st.get("inventory"), source="session")
    inv_s = "、".join(_inventory_label_list(inv)) if inv else "无"

    def _foot_ability(p: dict) -> str:
        core = _normalize_core_ability(p.get("core_ability"))
        return f"核心能力{core.get('name')}" if core else "核心能力无"

    def _foot_player(p: dict) -> str:
        return (
            f"血{p.get('hp', 0)}/{p.get('hp_max', 1)} SAN{p.get('san', 0)}/{p.get('san_max', 1)} 精神力{p.get('spi_current', 0)}/{p.get('spi_max', 0)}｜"
            f"Lv{p.get('level', 1)}·{p.get('rank', 'D')}阶 EXP{p.get('exp', 0)}｜"
            f"力{p.get('str', 0)} 体{p.get('con', p.get('vit', 0))} 敏{p.get('agi', 0)} 智{p.get('int', p.get('wis', 0))} 精{p.get('spi', 0)} 运{p.get('luk', 0)}｜"
            f"{_foot_ability(p)}"
        )

    p1_label = _normalize_player_display_name(p1.get("display_name"), "玩家一")
    p2_label = _normalize_player_display_name(p2.get("display_name"), "玩家二")
    return (
        "━━━━━━━━━━━━\n"
        f"【状态】{loc}｜主神积分：{int(st.get('points') or 0)}\n"
        f"{p1_label} {_foot_player(p1)}\n"
        f"{p2_label} {_foot_player(p2)}\n"
        f"道具：{inv_s}\n"
        "━━━━━━━━━━━━"
    )


def _strip_event_intent_block(text: str) -> str:
    """Hide backend-only event intent from player-facing history/display."""
    if not text or "【事件意图】" not in text:
        return (text or "").strip()
    marker = "【事件意图】"
    idx = text.find(marker)
    span = _first_json_object_span(text, idx)
    if not span:
        tail = text.find("\n", idx)
        end = len(text) if tail < 0 else tail + 1
    else:
        end = span[1]
    return (text[:idx].rstrip() + "\n" + text[end:].lstrip()).strip()


def _strip_main_god_panel(text: str) -> str:
    """去掉【事件意图】与【主神面板】，供注入与展示叙事。"""
    body = (text or "").split("【主神面板】", 1)[0] if text else ""
    return _strip_event_intent_block(body).strip()


def _strip_player_brief_blocks(text: str) -> str:
    """去掉给面板/线索板读取的备忘块，避免挤进主叙事。"""
    headings = (
        "规则备忘",
        "线索备忘",
        "安全区·威胁备忘",
        "阵营备忘",
        "撤离·物资备忘",
        "身份·嫌疑备忘",
        "时限备忘",
    )
    lines = str(text or "").splitlines()
    out: list[str] = []
    skipping = False
    for raw in lines:
        line = raw.strip()
        if any(f"【{heading}】" in line for heading in headings):
            skipping = True
            continue
        if skipping:
            if not line:
                continue
            if re.match(r"^[-*·\d一二三四五六七八九十]+[、.．:：]\s*", line):
                continue
            if line.startswith(("规则", "线索", "注", "来源", "（来源", "【待验证】", "【疑似", "【已证")):
                continue
            if any(mark in line for mark in ("【待验证】", "【疑似假】", "【已证真】", "待验证", "疑似假", "已证真")) and any(k in line for k in ("规则", "线索", "来源", "注")):
                continue
            skipping = False
        out.append(raw)
    cleaned = "\n".join(out)
    cleaned = re.sub(r"(?m)^\s*[—\-]+\s*主神系统\s*[—\-]+\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*-{3,}\s*$", "", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _parse_player_panel_block(block: str, label: str) -> dict:
    """解析【主神面板】中某一玩家的字段（可部分出现）。"""
    out: dict[str, Any] = {}
    m = re.search(rf"{label}\s*HP\s*(\d+)\s*/\s*(\d+)\s*精神\s*(\d+)\s*/\s*(\d+)", block)
    if m:
        out["hp"] = int(m.group(1))
        out["hp_max"] = int(m.group(2))
        out["san"] = int(m.group(3))
        out["san_max"] = int(m.group(4))
    m = re.search(rf"{label}等级[：:]\s*(\d+)", block)
    if m:
        out["level"] = int(m.group(1))
    m = re.search(rf"{label}经验[：:]\s*(\d+)", block)
    if m:
        out["exp"] = int(m.group(1))
    m = re.search(rf"{label}阶位[：:]\s*([DCSBA])", block)
    if m:
        out["rank"] = m.group(1).upper()
    m = re.search(rf"{label}体力[：:]\s*(\d+)", block)
    if m:
        out["vit"] = int(m.group(1))
    m = re.search(rf"{label}智慧[：:]\s*(\d+)", block)
    if m:
        out["wis"] = int(m.group(1))
    m = re.search(rf"{label}核心能力[：:]\s*(.+?)(?:\n|$)", block)
    if m:
        parsed = _parse_abilities_line(m.group(1))
        out["core_ability"] = _normalize_core_ability(parsed[0]) if parsed else None
    return out


def _parse_main_god_panel(gm_text: str) -> Optional[dict]:
    """解析 GM 输出的【主神面板】，失败返回 None。"""
    if "【主神面板】" not in gm_text:
        return None
    block = gm_text.split("【主神面板】", 1)[-1]
    out: dict[str, Any] = {}
    loc_m = re.search(r"场地[：:]\s*(\S+)", block)
    if loc_m:
        v = loc_m.group(1).strip()
        out["phase"] = "hub" if ("主神" in v or "空间" in v) else "instance_running"
    pts_m = re.search(r"积分[：:]\s*(\d+)", block)
    if pts_m:
        out["points"] = int(pts_m.group(1))
    p1 = _parse_player_panel_block(block, "玩家一")
    p2 = _parse_player_panel_block(block, "玩家二")
    if p1:
        out["player1"] = p1
    if p2:
        out["player2"] = p2
    inv_m = re.search(r"道具[：:]\s*(.+?)(?:\n|$)", block)
    if inv_m:
        raw_inv = inv_m.group(1).strip()
        if raw_inv in ("无", "无。", "-", "——"):
            out["inventory"] = []
        else:
            out["inventory"] = [x.strip() for x in re.split(r"[、，,]", raw_inv) if x.strip()][:20]
    if not out:
        return None
    return out


def _merge_panel_into_session_stats(session: dict, parsed: dict, include_vitals: bool = True) -> None:
    """将解析结果合并进 session['stats']，并做简单边界。"""
    _session_ensure_stats(session)
    st = session["stats"]
    if "phase" in parsed:
        st["phase"] = parsed["phase"]
    if "points" in parsed:
        st["points"] = max(0, int(parsed["points"]))
    for pk in ("player1", "player2"):
        if pk not in parsed:
            continue
        cur = st.get(pk) or _default_player_stats()
        st[pk] = _merge_one_player(cur, parsed[pk], include_vitals=include_vitals)
    if "inventory" in parsed:
        st["inventory"] = list(parsed["inventory"])


def _parse_event_intent(gm_text: str) -> Optional[dict]:
    """Parse GM's backend-only event intent block."""
    if not gm_text or "【事件意图】" not in gm_text:
        return None
    idx = gm_text.find("【事件意图】")
    span = _first_json_object_span(gm_text, idx)
    if not span:
        return None
    try:
        data = json.loads(gm_text[span[0] : span[1]])
    except Exception:
        return None
    return _normalize_event_intent(data)


def _normalize_event_intent(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    risk = str(raw.get("risk") or "safe").strip().lower()
    if risk not in _WENYOU_RISK_DAMAGE:
        risk = "safe"
    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list):
        targets_raw = [raw.get("target")] if raw.get("target") else []
    targets: list[str] = []
    for item in targets_raw:
        s = str(item or "").strip().lower()
        if s in ("all", "both", "玩家", "双方"):
            targets.extend(["player1", "player2"])
        elif s in ("player1", "p1", "玩家一"):
            targets.append("player1")
        elif s in ("player2", "p2", "玩家二"):
            targets.append("player2")
    if not targets:
        targets = ["player1"]
    targets = list(dict.fromkeys(targets))
    tags_raw = raw.get("tags")
    if isinstance(tags_raw, str):
        tags_raw = re.split(r"[、，,\s]+", tags_raw)
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = [str(x or "").strip().lower() for x in tags_raw]
    tags = [x for x in tags if x in _WENYOU_EVENT_TAGS]
    if not tags:
        tags = ["mixed"] if risk != "safe" else ["clue"]
    action_state = str(raw.get("action_state") or raw.get("action") or "normal").strip().lower()
    modifier = raw.get("action_modifier")
    try:
        action_modifier = float(modifier) if modifier is not None else _WENYOU_ACTION_MODIFIER.get(action_state, 1.0)
    except Exception:
        action_modifier = 1.0
    action_modifier = max(0.5, min(2.0, action_modifier))
    return {
        "event": _compact_text(raw.get("event") or "gm_event", 80),
        "risk": risk,
        "targets": targets,
        "tags": tags,
        "action_state": action_state if action_state in _WENYOU_ACTION_MODIFIER else "normal",
        "action_modifier": action_modifier,
        "fiction": _compact_text(raw.get("fiction"), 240),
        "conditions_add": _normalize_text_list(raw.get("conditions_add"), 40, 8),
        "conditions_remove": _normalize_text_list(raw.get("conditions_remove"), 40, 8),
        "clock_updates": _normalize_clock_updates(raw.get("clock_updates")),
        "rule_updates": _normalize_text_list(raw.get("rule_updates") or raw.get("rules"), 180, 8),
        "clue_updates": _normalize_text_list(raw.get("clue_updates") or raw.get("clues"), 180, 8),
        "task_update": _compact_text(raw.get("task_update") or raw.get("progress_update"), 220),
        "state_proposals": _normalize_state_proposals(raw.get("state_proposals")),
    }


def _normalize_state_proposals(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    allowed_types = {
        "discover_clue",
        "verify_clue",
        "task_update",
        "location_update",
        "npc_update",
        "monster_update",
        "rule_violation",
        "violate_rule",
        "clock_delta",
        "settlement_flag",
        "acquire_item",
        "acquire_task_item",
        "acquire_unique_item",
    }
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        ptype = str(item.get("type") or "").strip()
        if ptype not in allowed_types:
            ptype = "task_update" if "task" in ptype else "discover_clue"
        visibility = str(item.get("visibility") or "hidden").strip().lower()
        if visibility not in {"public", "hidden"}:
            visibility = "hidden"
        out.append(
            {
                "type": ptype,
                "id": _compact_text(item.get("id") or item.get("name"), 80),
                "name": _compact_text(item.get("name"), 80),
                "rarity": _normalize_difficulty(item.get("rarity") or "D"),
                "category": _compact_text(item.get("category"), 40),
                "effect": _compact_text(item.get("effect") or item.get("desc") or item.get("description"), 240),
                "carry_out": bool(item.get("carry_out")) if "carry_out" in item else None,
                "seal_rank": _normalize_difficulty(item.get("seal_rank")) if item.get("seal_rank") else None,
                "requirements": item.get("requirements") if isinstance(item.get("requirements"), dict) else {},
                "visibility": visibility,
                "reason": _compact_text(item.get("reason"), 180),
                "quantity": max(1, min(3, _to_non_negative_int(item.get("quantity") or item.get("qty"), 1))),
            }
        )
    return out


def _normalize_clock_updates(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or item.get("name") or "").strip()[:80]
        if not cid:
            continue
        try:
            delta = int(item.get("delta") or 0)
        except Exception:
            delta = 0
        try:
            max_value = int(item.get("max") or 0)
        except Exception:
            max_value = 0
        out.append(
            {
                "id": cid,
                "name": str(item.get("name") or cid).strip()[:80],
                "delta": max(-10, min(10, delta)),
                "max": max(1, max_value or 6),
            }
        )
    return out


def _damage_for_player(base: int, multiplier: float, modifier: float, attr: int, rank: str, reduction_table: dict[str, int]) -> int:
    if base <= 0:
        return 0
    raw = math.ceil(base * multiplier * modifier) - math.floor(max(0, int(attr or 0)) / 3) - int(reduction_table.get(rank, 0))
    return max(1, raw)


def _add_condition_unique(player: dict, condition: str) -> None:
    name = str(condition or "").strip()
    if not name:
        return
    arr = _normalize_text_list(player.get("conditions"), 40, 20)
    if name not in arr:
        arr.append(name[:40])
    player["conditions"] = arr[:20]


def _remove_condition(player: dict, condition: str) -> None:
    name = str(condition or "").strip()
    if not name:
        return
    player["conditions"] = [x for x in _normalize_text_list(player.get("conditions"), 40, 20) if x != name]


def _apply_threshold_conditions(player: dict) -> list[str]:
    added: list[str] = []
    hp = int(player.get("hp") or 0)
    hp_max = max(1, int(player.get("hp_max") or 1))
    san = int(player.get("san") or 0)
    san_max = max(1, int(player.get("san_max") or 1))
    thresholds = []
    if hp <= 0:
        thresholds.append("濒死")
        player.setdefault("death_clock", 3)
    elif hp <= math.floor(hp_max * 0.25):
        thresholds.append("重伤")
    elif hp <= math.floor(hp_max * 0.5):
        thresholds.append("轻伤")
    if san <= 0:
        thresholds.append("失控")
    elif san <= math.floor(san_max * 0.25):
        thresholds.append("污染")
    elif san <= math.floor(san_max * 0.5):
        thresholds.append("动摇")
    for cond in thresholds:
        before = set(_normalize_text_list(player.get("conditions"), 40, 20))
        _add_condition_unique(player, cond)
        if cond not in before:
            added.append(cond)
    return added


def _apply_clock_updates(session: dict, updates: list[dict]) -> list[dict]:
    clocks = session.get("clocks") if isinstance(session.get("clocks"), list) else []
    by_id: dict[str, dict] = {}
    for item in clocks:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item.get("id"))] = dict(item)
    results: list[dict] = []
    for upd in updates:
        cid = str(upd.get("id") or "").strip()
        if not cid:
            continue
        cur = by_id.get(cid, {"id": cid, "name": upd.get("name") or cid, "value": 0, "max": upd.get("max") or 6})
        max_value = max(1, int(upd.get("max") or cur.get("max") or 6))
        value = max(0, min(max_value, int(cur.get("value") or 0) + int(upd.get("delta") or 0)))
        cur.update({"name": str(upd.get("name") or cur.get("name") or cid)[:80], "value": value, "max": max_value})
        by_id[cid] = cur
        results.append({"id": cid, "delta": int(upd.get("delta") or 0), "value": value, "max": max_value})
    session["clocks"] = list(by_id.values())[:20]
    return results


def _rules_mapping(raw: Any, prefix: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if isinstance(raw, dict):
        items = raw.values()
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        key = _slug_id(item.get("id") or item.get("name") or item.get("title") or f"{prefix}_{idx + 1}", f"{prefix}_{idx + 1}")
        cur = dict(item)
        cur["id"] = key
        out[key] = cur
    return out


def _infer_progress_status(text: Any, fallback: str = "active") -> str:
    body = _compact_text(text, 260)
    if re.search(r"(失败|错过|失效|死亡|团灭|崩坏)", body):
        return "failed"
    if re.search(r"(完成|达成|通关|验证成功|已验证|解决|封印|撤离成功|结算)", body):
        return "completed"
    if re.search(r"(隐藏|暗线)", body):
        return "hidden_completed" if re.search(r"(完成|达成|真结局)", body) else fallback
    return fallback


def _task_progress_entry(item: Any, index: int, phase: str, fallback_type: str = "main") -> Optional[dict]:
    task = _normalize_public_task_item(item, index, phase)
    if not task:
        return None
    text = " ".join(
        str(x or "")
        for x in (
            task.get("title"),
            task.get("status"),
            (task.get("progress") or {}).get("text") if isinstance(task.get("progress"), dict) else task.get("progress"),
        )
    )
    task["status"] = _infer_progress_status(text, str(task.get("status") or "active"))
    task["type"] = _compact_text(task.get("type") or fallback_type, 40)
    task["updated_at"] = now_beijing_iso()
    return task


def _clue_state_entry(item: Any, index: int, verified: bool = False, visibility: str = "public") -> Optional[dict]:
    clue = _normalize_public_clue_item(item, index)
    if not clue:
        return None
    clue["status"] = "verified" if verified or clue.get("verified") else _compact_text(clue.get("status") or "discovered", 40)
    clue["verified"] = bool(verified or clue.get("verified") or clue.get("status") == "verified")
    clue["visibility"] = "hidden" if visibility == "hidden" else "public"
    clue["updated_at"] = now_beijing_iso()
    return clue


def _marker_state_entry(item: Any, index: int, prefix: str, visibility: str = "hidden") -> Optional[dict]:
    marker = _normalize_public_marker_item(item, index, prefix)
    if not marker:
        return None
    marker["visibility"] = "public" if visibility == "public" else "hidden"
    marker["updated_at"] = now_beijing_iso()
    if isinstance(item, dict):
        for key in (
            "location",
            "last_location",
            "attitude",
            "stance",
            "intent",
            "trigger",
            "trouble_chance",
            "alive",
            "danger_level",
            "locked",
            "resources",
        ):
            if item.get(key) is not None:
                marker[key] = item.get(key) if isinstance(item.get(key), (int, float, bool, list, dict)) else _compact_text(item.get(key), 180)
    return marker


def _public_rule_update_stub(entry: dict) -> dict:
    return {
        "id": entry.get("id"),
        "name": entry.get("name") or entry.get("title"),
        "status": entry.get("status"),
        "visibility": entry.get("visibility") or "hidden",
    }


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


def _apply_rules_state_updates(session: dict, event_intent: dict) -> dict:
    if not isinstance(event_intent, dict):
        return {}
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    phase = _session_phase(session)
    task_progress = _rules_mapping(rules.get("task_progress"), "task")
    clue_state = _rules_mapping(rules.get("clue_state"), "clue")
    location_state = _rules_mapping(rules.get("location_state"), "location")
    npc_state = _rules_mapping(rules.get("npc_state"), "npc")
    settlement_flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    reward_context = _reward_context_from_raw(rules.get("reward_context"))
    rule_violations = [dict(x) for x in rules.get("rule_violations") or [] if isinstance(x, dict)][-80:]

    task_updates: list[dict] = []
    clue_updates: list[dict] = []
    location_updates: list[dict] = []
    npc_updates: list[dict] = []
    violation_updates: list[dict] = []
    settlement_updates: list[dict] = []
    reward_updates: list[dict] = []

    if event_intent.get("task_update"):
        entry = _task_progress_entry(
            {
                "id": "main_task",
                "title": event_intent.get("task_update"),
                "type": "main",
                "progress": {"text": event_intent.get("task_update")},
            },
            len(task_progress),
            phase,
            "main",
        )
        if entry:
            task_progress[str(entry["id"])] = {**task_progress.get(str(entry["id"]), {}), **entry}
            task_updates.append(entry)
            if entry.get("type") == "main" and entry.get("status") == "completed":
                settlement_flags["mainline_status"] = "completed"

    for idx, text in enumerate(event_intent.get("clue_updates") or []):
        entry = _clue_state_entry(text, len(clue_state) + idx, visibility="public")
        if entry:
            clue_state[str(entry["id"])] = {**clue_state.get(str(entry["id"]), {}), **entry}
            clue_updates.append(entry)

    for proposal in event_intent.get("state_proposals") or []:
        if not isinstance(proposal, dict):
            continue
        ptype = str(proposal.get("type") or "")
        visibility = str(proposal.get("visibility") or "hidden")
        name = _compact_text(proposal.get("name") or proposal.get("id") or proposal.get("reason"), 120)
        if ptype in {"discover_clue", "verify_clue"}:
            entry = _clue_state_entry(
                {
                    "id": proposal.get("id") or name,
                    "title": name,
                    "public_text": proposal.get("reason") or name,
                    "status": "verified" if ptype == "verify_clue" else "discovered",
                    "verified": ptype == "verify_clue",
                },
                len(clue_state),
                verified=ptype == "verify_clue",
                visibility=visibility,
            )
            if entry:
                clue_state[str(entry["id"])] = {**clue_state.get(str(entry["id"]), {}), **entry}
                clue_updates.append(entry)
        elif ptype == "task_update":
            entry = _task_progress_entry(
                {
                    "id": proposal.get("id") or name,
                    "title": name or proposal.get("reason"),
                    "type": proposal.get("category") or ("hidden" if visibility == "hidden" else "side"),
                    "progress": {"text": proposal.get("reason") or name},
                },
                len(task_progress),
                phase,
                "side",
            )
            if entry:
                task_progress[str(entry["id"])] = {**task_progress.get(str(entry["id"]), {}), **entry}
                task_updates.append(entry)
                if entry.get("status") in {"completed", "hidden_completed"}:
                    _record_settlement_flag(settlement_flags, str(entry.get("type") or ""), entry.get("title") or entry.get("id") or "")
        elif ptype == "settlement_flag":
            category = str(proposal.get("category") or "")
            value = name or proposal.get("reason") or proposal.get("id")
            _record_settlement_flag(settlement_flags, category, str(value or ""))
            settlement_updates.append({"category": category or "achievement", "value": _compact_text(value, 80)})
        elif ptype == "location_update":
            entry = _marker_state_entry(proposal, len(location_state), "location", visibility)
            if entry:
                location_state[str(entry["id"])] = {**location_state.get(str(entry["id"]), {}), **entry}
                location_updates.append(_public_rule_update_stub(entry))
        elif ptype == "npc_update":
            entry = _marker_state_entry(proposal, len(npc_state), "npc", visibility)
            if entry:
                npc_state[str(entry["id"])] = {**npc_state.get(str(entry["id"]), {}), **entry}
                npc_updates.append(_public_rule_update_stub(entry))
                if re.search(r"(暴露|怀疑|识破|身份)", str(proposal.get("reason") or name or "")):
                    _bump_forced_instance_exposure(session, "taskers", 1, "NPC/任务者怀疑身份")
        elif ptype in {"rule_violation", "violate_rule"}:
            violation = {
                "id": _slug_id(proposal.get("id") or name or f"rule_violation_{len(rule_violations) + 1}", "rule_violation"),
                "name": name or _compact_text(proposal.get("reason") or "规则触犯", 80),
                "rule_id": _compact_text(proposal.get("rule_id") or proposal.get("id"), 80),
                "severity": _compact_text(proposal.get("severity") or "minor", 40),
                "visibility": visibility,
                "reason": _compact_text(proposal.get("reason") or "", 220),
                "created_at": now_beijing_iso(),
            }
            rule_violations.append(violation)
            violation_updates.append(_public_rule_update_stub(violation))
            _bump_forced_instance_exposure(session, "taskers", 1, "规则触犯")
        elif ptype in {"acquire_item", "acquire_task_item", "acquire_unique_item"}:
            grant = {
                "type": ptype,
                "id": _slug_id(proposal.get("id") or name, "item"),
                "name": name,
                "rarity": proposal.get("rarity") or "D",
                "category": proposal.get("category") or "",
                "visibility": visibility,
                "reason": proposal.get("reason") or "",
                "created_at": now_beijing_iso(),
            }
            reward_context["item_grants"] = (reward_context.get("item_grants") or [])[-39:] + [grant]
            reward_updates.append(grant)
            if ptype == "acquire_unique_item":
                unique = _normalize_text_list(reward_context.get("unique_rewards"), 80, 20)
                if name and name not in unique:
                    unique.append(name)
                reward_context["unique_rewards"] = unique[:20]
        elif ptype == "monster_update" and visibility == "hidden":
            _record_settlement_flag(settlement_flags, "hidden", proposal.get("reason") or name or "怪物暗线推进")

    for task in task_progress.values():
        if task.get("type") == "main" and task.get("status") == "completed":
            settlement_flags["mainline_status"] = "completed"
        elif task.get("status") in {"completed", "hidden_completed"} and task.get("type") in {"side", "hidden"}:
            _record_settlement_flag(settlement_flags, str(task.get("type") or "side"), task.get("title") or task.get("id") or "")

    rules["task_progress"] = task_progress
    rules["clue_state"] = clue_state
    rules["location_state"] = location_state
    rules["npc_state"] = npc_state
    rules["rule_violations"] = rule_violations[-80:]
    rules["settlement_flags"] = settlement_flags
    rules["reward_context"] = reward_context
    if isinstance(session.get("forced_instance"), dict):
        rules["forced_instance"] = copy.deepcopy(session.get("forced_instance"))
    runtime["rules_state"] = rules
    runtime.setdefault("gm_state", {})
    runtime.setdefault("runtime_indexes", {})
    session["runtime_state"] = runtime
    return {
        "rules_task_updates": task_updates,
        "rules_clue_updates": clue_updates,
        "rules_location_updates": location_updates,
        "rules_npc_updates": npc_updates,
        "rule_violation_updates": violation_updates,
        "settlement_flag_updates": settlement_updates,
        "reward_context_updates": reward_updates,
    }


def _apply_event_intent(session: dict, event_intent: Optional[dict]) -> Optional[dict]:
    if not event_intent:
        return None
    _session_ensure_stats(session)
    st = session["stats"]
    fw = _framework_for_runtime(session.get("framework") or {})
    diff = _normalize_difficulty(fw.get("difficulty"))
    multiplier = float(_WENYOU_DIFFICULTY_MULTIPLIER.get(diff, 1.0))
    risk = str(event_intent.get("risk") or "safe")
    base_hp, base_san = _WENYOU_RISK_DAMAGE.get(risk, (0, 0))
    tags = set(event_intent.get("tags") or [])
    if "physical" in tags and not ({"mental", "rule_pollution", "memory", "mixed"} & tags):
        base_san = 0
    elif {"mental", "rule_pollution", "memory"} & tags and "mixed" not in tags:
        base_hp = 0
    elif "mixed" in tags or (base_hp and base_san):
        base_hp = math.ceil(base_hp * 0.6)
        base_san = math.ceil(base_san * 0.6)
    changes: dict[str, Any] = {"players": {}, "inventory_add": [], "inventory_remove": [], "clock_updates": [], "flags_set": {}}
    for target in event_intent.get("targets") or []:
        if target not in ("player1", "player2"):
            continue
        player = st.get(target) if isinstance(st.get(target), dict) else _default_player_stats()
        rank = _normalize_difficulty(player.get("rank") or "D")
        hp_damage = _damage_for_player(
            base_hp,
            multiplier,
            float(event_intent.get("action_modifier") or 1.0),
            int(player.get("vit") or 0),
            rank,
            _WENYOU_RANK_PHYSICAL_REDUCTION,
        )
        san_damage = _damage_for_player(
            base_san,
            multiplier,
            float(event_intent.get("action_modifier") or 1.0),
            int(player.get("spi_current") or 0),
            rank,
            _WENYOU_RANK_MENTAL_REDUCTION,
        )
        hp_before = int(player.get("hp") or 0)
        san_before = int(player.get("san") or 0)
        player["hp"] = max(0, min(int(player.get("hp_max") or hp_before or 1), hp_before - hp_damage))
        player["san"] = max(0, min(int(player.get("san_max") or san_before or 1), san_before - san_damage))
        spi_delta = _apply_san_delta_to_spi(player, int(player.get("san") or 0) - san_before)
        _recalc_player_caps(player)
        for cond in event_intent.get("conditions_remove") or []:
            _remove_condition(player, cond)
        for cond in event_intent.get("conditions_add") or []:
            _add_condition_unique(player, cond)
        threshold_add = _apply_threshold_conditions(player)
        st[target] = player
        changes["players"][target] = {
            "hp_delta": int(player.get("hp") or 0) - hp_before,
            "san_delta": int(player.get("san") or 0) - san_before,
            "spi_delta": spi_delta,
            "conditions_add": list(dict.fromkeys((event_intent.get("conditions_add") or []) + threshold_add)),
            "conditions_remove": event_intent.get("conditions_remove") or [],
        }
    changes["clock_updates"] = _apply_clock_updates(session, event_intent.get("clock_updates") or [])
    changes["inventory_add"] = _apply_state_proposal_item_grants(session, event_intent.get("state_proposals") or [])
    changes.update(_apply_public_state_updates(session, event_intent))
    changes.update(_apply_rules_state_updates(session, event_intent))
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    round_id = f"round_{len(event_log) + 1:03d}"
    state_patch = {
        "round_id": round_id,
        "source": "rules_engine",
        "event_intent": event_intent,
        "changes": changes,
        "created_at": now_beijing_iso(),
    }
    event_log.append(state_patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = state_patch
    session["stats"] = st
    return state_patch


def _format_state_patch_for_display(state_patch: Optional[dict]) -> str:
    if not state_patch:
        return ""
    changes = state_patch.get("changes") if isinstance(state_patch.get("changes"), dict) else {}
    lines: list[str] = []
    players = changes.get("players") if isinstance(changes.get("players"), dict) else {}
    label = {"player1": "玩家一", "player2": "玩家二"}
    for pid, ch in players.items():
        if not isinstance(ch, dict):
            continue
        hp_delta = int(ch.get("hp_delta") or 0)
        san_delta = int(ch.get("san_delta") or 0)
        cond_add = "、".join(ch.get("conditions_add") or [])
        parts = []
        if hp_delta:
            parts.append(f"HP {hp_delta:+d}")
        if san_delta:
            parts.append(f"SAN {san_delta:+d}")
        spi_delta = int(ch.get("spi_delta") or 0)
        if spi_delta:
            parts.append(f"精神力 {spi_delta:+d}")
        if cond_add:
            parts.append(f"状态 {cond_add}")
        if parts:
            lines.append(f"{label.get(pid, pid)}：" + "；".join(parts))
    for clk in changes.get("clock_updates") or []:
        if isinstance(clk, dict) and int(clk.get("delta") or 0):
            delta = int(clk.get("delta") or 0)
            lines.append("威胁时钟：" + ("上升" if delta > 0 else "下降"))
    inventory_add = [
        str(item.get("name") or "").strip()
        for item in changes.get("inventory_add") or []
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if inventory_add:
        lines.append("背包获得：" + "、".join(inventory_add[:4]))
    if not lines:
        return ""
    return "【规则结算】\n" + "\n".join(lines[:6])


_WENYOU_PLAYER_IDS = ("player1", "player2")
_WENYOU_PLAYER_LABELS = {"player1": "玩家一", "player2": "玩家二"}
_WENYOU_PLAYER_CONTROLLERS = {"player1": "human", "player2": "ai"}


def _player_display_name(player_id: Any) -> str:
    return _WENYOU_PLAYER_LABELS.get(_resolve_player_key(player_id), "玩家")


def _normalize_player_display_name(value: Any, fallback: str = "") -> str:
    text = _compact_text(value, 24).replace("\n", "").replace("\r", "").strip()
    if not text:
        return fallback
    return text[:16]


def _wallet_player_display_name(wallet: Optional[dict], player_id: str, fallback: str = "") -> str:
    if not isinstance(wallet, dict):
        return fallback
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    player = players.get(player_id) if isinstance(players.get(player_id), dict) else {}
    return _normalize_player_display_name(player.get("display_name"), fallback)


def _wallet_confirmed_player_display_name(wallet: Optional[dict], player_id: str) -> str:
    if not isinstance(wallet, dict):
        return ""
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    player = players.get(player_id) if isinstance(players.get(player_id), dict) else {}
    if not player.get("display_name_set"):
        return ""
    return _normalize_player_display_name(player.get("display_name"), "")


def _normalize_player_wallet(raw: Any, seed_points: int = 100, seed_debts: int = 0, seed_gacha: Any = None, seed_ledger: Any = None) -> dict:
    data = raw if isinstance(raw, dict) else {}
    points_source = data.get("points") if data.get("points") is not None else seed_points
    debts_source = data.get("debts") if data.get("debts") is not None else seed_debts
    ledger = data.get("ledger") if isinstance(data.get("ledger"), list) else (seed_ledger if isinstance(seed_ledger, list) else [])
    return {
        "points": max(0, int(points_source or 0)),
        "debts": max(0, int(debts_source or 0)),
        "gacha": _normalize_gacha_state(data.get("gacha") if data.get("gacha") is not None else seed_gacha),
        "ledger": [x for x in ledger[-80:] if isinstance(x, dict)],
    }


def _split_legacy_inventory_by_holder(raw: Any) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {"player1": [], "player2": [], "task_items": []}
    for item in _normalize_inventory(raw, source="wallet"):
        holder = str(item.get("holder_id") or item.get("holder") or "").strip().lower()
        if holder in {"player2", "p2", "玩家二"}:
            buckets["player2"].append(item)
        elif holder in {"task_items", "task", "team", "party"} or item.get("quest_item") or item.get("temporary") or item.get("carry_out") is False:
            buckets["task_items"].append(item)
        else:
            buckets["player1"].append(item)
    return buckets


def _normalize_inventories_map(raw: Any, legacy_inventory: Any = None) -> dict[str, list[dict]]:
    data = raw if isinstance(raw, dict) else {}
    legacy = _split_legacy_inventory_by_holder(legacy_inventory)
    return {
        "player1": _normalize_inventory(data.get("player1"), source="wallet") if isinstance(data.get("player1"), list) else legacy["player1"],
        "player2": _normalize_inventory(data.get("player2"), source="wallet") if isinstance(data.get("player2"), list) else legacy["player2"],
        "task_items": _normalize_inventory(data.get("task_items"), source="wallet") if isinstance(data.get("task_items"), list) else legacy["task_items"],
    }


def _normalize_wallets_map(data: dict, player1_points: int, player1_debts: int, player1_gacha: Any, player1_ledger: list[dict]) -> dict[str, dict]:
    raw_wallets = data.get("wallets") if isinstance(data.get("wallets"), dict) else {}
    p1_raw = raw_wallets.get("player1") if isinstance(raw_wallets.get("player1"), dict) else {}
    if "points" not in p1_raw:
        p1_raw = {**p1_raw, "points": player1_points}
    if "debts" not in p1_raw:
        p1_raw = {**p1_raw, "debts": player1_debts}
    if "gacha" not in p1_raw:
        p1_raw = {**p1_raw, "gacha": player1_gacha}
    if "ledger" not in p1_raw:
        p1_raw = {**p1_raw, "ledger": player1_ledger}
    p2_raw = raw_wallets.get("player2") if isinstance(raw_wallets.get("player2"), dict) else {}
    return {
        "player1": _normalize_player_wallet(p1_raw, seed_points=player1_points, seed_debts=player1_debts, seed_gacha=player1_gacha, seed_ledger=player1_ledger),
        "player2": _normalize_player_wallet(p2_raw, seed_points=100, seed_debts=0),
    }


def _normalize_wallet(raw: Any, seed_points: int = 100) -> dict:
    data = raw if isinstance(raw, dict) else {}
    ledger = data.get("ledger") if isinstance(data.get("ledger"), list) else []
    clear_records = data.get("clear_records") if isinstance(data.get("clear_records"), list) else []
    promotion_history = data.get("promotion_history") if isinstance(data.get("promotion_history"), list) else []
    forced_queue = data.get("forced_instance_queue") if isinstance(data.get("forced_instance_queue"), list) else []
    settlement_history = data.get("settlement_history") if isinstance(data.get("settlement_history"), list) else []
    tutorial_completed_at = str(data.get("tutorial_completed_at") or data.get("tutorial_completed_time") or "").strip()
    if not tutorial_completed_at and data.get("newbie_starter_pack_granted"):
        tutorial_completed_at = str(data.get("newbie_starter_pack_granted_at") or data.get("tutorial_completed_at") or "").strip()
    if not tutorial_completed_at and data.get("tutorial_started_at") and settlement_history:
        last_settlement = settlement_history[-1] if isinstance(settlement_history[-1], dict) else {}
        tutorial_completed_at = str(last_settlement.get("at") or data.get("updated_at") or "").strip()
    shop_state = data.get("shop_state") if isinstance(data.get("shop_state"), dict) else {}
    regular_shop = shop_state.get("regular") if isinstance(shop_state.get("regular"), dict) else {}
    raw_players = data.get("players") if isinstance(data.get("players"), dict) else {}
    players: dict[str, dict] = {}
    base_player = _default_player_stats()
    for pid in ("player1", "player2"):
        cur = raw_players.get(pid) if isinstance(raw_players.get(pid), dict) else {}
        player = dict(base_player)
        player.update(cur)
        player.setdefault("display_name", _WENYOU_PLAYER_LABELS.get(pid, pid))
        player.setdefault("controller", _WENYOU_PLAYER_CONTROLLERS.get(pid, "human"))
        _normalize_player_growth_fields(player)
        player["conditions"] = _normalize_text_list(player.get("conditions"))
        _recalc_player_caps(player)
        players[pid] = player
    points = max(0, int(data.get("points") if data.get("points") is not None else seed_points))
    test_grant_min = max(0, int(data.get("test_points_grant_min") or 0))
    if _WENYOU_TEST_MIN_POINTS and points < _WENYOU_TEST_MIN_POINTS and test_grant_min < _WENYOU_TEST_MIN_POINTS:
        points = _WENYOU_TEST_MIN_POINTS
        test_grant_min = _WENYOU_TEST_MIN_POINTS
        ledger = ledger[-79:] + [{"at": now_beijing_iso(), "type": "test_points_grant", "points": points}]
    debts = max(0, int(data.get("debts") or 0))
    gacha = _normalize_gacha_state(data.get("gacha"))
    wallets = _normalize_wallets_map(data, points, debts, gacha, [x for x in ledger[-80:] if isinstance(x, dict)])
    inventories = _normalize_inventories_map(data.get("inventories") if isinstance(data.get("inventories"), dict) else {}, data.get("inventory"))
    points = max(0, int(wallets["player1"].get("points") or 0))
    debts = max(0, int(wallets["player1"].get("debts") or 0))
    gacha = _normalize_gacha_state(wallets["player1"].get("gacha"))
    ledger = [x for x in (wallets["player1"].get("ledger") or [])[-80:] if isinstance(x, dict)]
    return {
        "version": 1,
        "points": points,
        "debts": debts,
        "total_exp": max(0, int(data.get("total_exp") or 0)),
        "settlement_count": max(0, int(data.get("settlement_count") or 0)),
        "gacha": gacha,
        "inventory": inventories["player1"],
        "inventories": inventories,
        "wallets": wallets,
        "players": players,
        "tutorial_completed": bool(data.get("tutorial_completed") or tutorial_completed_at),
        "tutorial_completed_at": tutorial_completed_at,
        "tutorial_completion_result": str(data.get("tutorial_completion_result") or ""),
        "newbie_starter_pack_granted": bool(data.get("newbie_starter_pack_granted") or data.get("tutorial_clear_reward_granted")),
        "newbie_starter_pack_granted_at": str(data.get("newbie_starter_pack_granted_at") or data.get("tutorial_completed_at") or ""),
        "tutorial_started_at": str(data.get("tutorial_started_at") or ""),
        "clear_records": [x for x in clear_records[-30:] if isinstance(x, dict)],
        "promotion_history": [x for x in promotion_history[-20:] if isinstance(x, dict)],
        "forced_instance_queue": [x for x in forced_queue[-8:] if isinstance(x, dict)],
        "forced_instance_framework_cache": _normalize_forced_framework_cache(data.get("forced_instance_framework_cache"), data),
        "settlement_history": [x for x in settlement_history[-12:] if isinstance(x, dict)],
        "ability_cooldowns": dict(data.get("ability_cooldowns") or {}) if isinstance(data.get("ability_cooldowns"), dict) else {},
        "shop_state": {
            "regular": {
                "date": str(regular_shop.get("date") or now_beijing_iso()[:10]),
                "refresh_count": max(0, int(regular_shop.get("refresh_count") or 0)),
                "refresh_limit": 3,
                "refresh_cost": 20,
                "rotation_nonce": str(regular_shop.get("rotation_nonce") or ""),
            }
        },
        "test_points_grant_min": test_grant_min,
        "ledger": ledger[-80:],
        "updated_at": str(data.get("updated_at") or now_beijing_iso()),
    }


def _ensure_wallet_player_maps(wallet: dict) -> dict:
    if not isinstance(wallet, dict):
        wallet = {}
    raw_wallets = wallet.get("wallets") if isinstance(wallet.get("wallets"), dict) else {}
    raw_inventories = wallet.get("inventories") if isinstance(wallet.get("inventories"), dict) else {}
    wallets = {
        "player1": _normalize_player_wallet(
            raw_wallets.get("player1") if isinstance(raw_wallets.get("player1"), dict) else {},
            seed_points=max(0, int(wallet.get("points") or 0)),
            seed_debts=max(0, int(wallet.get("debts") or 0)),
            seed_gacha=wallet.get("gacha"),
            seed_ledger=wallet.get("ledger") if isinstance(wallet.get("ledger"), list) else [],
        ),
        "player2": _normalize_player_wallet(raw_wallets.get("player2") if isinstance(raw_wallets.get("player2"), dict) else {}, seed_points=100),
    }
    inventories = _normalize_inventories_map(raw_inventories, wallet.get("inventory"))
    wallet["wallets"] = wallets
    wallet["inventories"] = inventories
    wallet.pop("equipment", None)
    return wallet


def _sync_wallet_compat_aliases(wallet: dict) -> dict:
    wallet = _ensure_wallet_player_maps(wallet)
    p1 = wallet["wallets"]["player1"]
    p1["points"] = max(0, int(wallet.get("points") if wallet.get("points") is not None else p1.get("points") or 0))
    p1["debts"] = max(0, int(wallet.get("debts") if wallet.get("debts") is not None else p1.get("debts") or 0))
    p1["gacha"] = _normalize_gacha_state(wallet.get("gacha") if wallet.get("gacha") is not None else p1.get("gacha"))
    if isinstance(wallet.get("ledger"), list):
        p1["ledger"] = [x for x in wallet["ledger"][-80:] if isinstance(x, dict)]
    wallet["inventories"]["player1"] = _normalize_inventory(wallet.get("inventory"), source="wallet") or wallet["inventories"]["player1"]
    wallet["points"] = int(p1.get("points") or 0)
    wallet["debts"] = int(p1.get("debts") or 0)
    wallet["gacha"] = _normalize_gacha_state(p1.get("gacha"))
    wallet["inventory"] = _normalize_inventory(wallet["inventories"].get("player1"), source="wallet")
    wallet["ledger"] = [x for x in (p1.get("ledger") or [])[-80:] if isinstance(x, dict)]
    return wallet


def _player_account(wallet: dict, player_id: Any = "player1") -> dict:
    pid = _resolve_player_key(player_id)
    _ensure_wallet_player_maps(wallet)
    account = wallet["wallets"].get(pid)
    if not isinstance(account, dict):
        account = _normalize_player_wallet({}, seed_points=100 if pid == "player2" else int(wallet.get("points") or 0))
        wallet["wallets"][pid] = account
    return account


def _get_player_inventory(wallet: dict, player_id: Any = "player1") -> list[dict]:
    pid = _resolve_player_key(player_id)
    _ensure_wallet_player_maps(wallet)
    return _normalize_inventory(wallet["inventories"].get(pid), source="wallet")


def _set_player_inventory(wallet: dict, player_id: Any, inventory: Any) -> list[dict]:
    pid = _resolve_player_key(player_id)
    _ensure_wallet_player_maps(wallet)
    normalized = _normalize_inventory(inventory, source="wallet")[:80]
    wallet["inventories"][pid] = normalized
    if pid == "player1":
        wallet["inventory"] = normalized
    return normalized


def append_player_ledger(state: dict, actor_id: Any, ledger_entry: dict) -> dict:
    wallet = _ensure_wallet_player_maps(state)
    pid = _resolve_player_key(actor_id)
    entry = dict(ledger_entry or {})
    entry.setdefault("ledger_id", f"ledger_{uuid4().hex[:12]}")
    entry.setdefault("actor_id", pid)
    entry.setdefault("created_at", now_beijing_iso())
    entry.setdefault("visibility", "player_visible")
    account = _player_account(wallet, pid)
    account["ledger"] = [x for x in (account.get("ledger") or [])[-79:] if isinstance(x, dict)] + [entry]
    wallet["wallets"][pid] = account
    if pid == "player1":
        wallet["ledger"] = account["ledger"]
    return entry


def _set_actor_points(wallet: dict, actor_id: Any, points: int) -> None:
    pid = _resolve_player_key(actor_id)
    account = _player_account(wallet, pid)
    account["points"] = max(0, int(points or 0))
    wallet["wallets"][pid] = account
    if pid == "player1":
        wallet["points"] = account["points"]


def _set_actor_gacha(wallet: dict, actor_id: Any, gacha: Any) -> None:
    pid = _resolve_player_key(actor_id)
    account = _player_account(wallet, pid)
    account["gacha"] = _normalize_gacha_state(gacha)
    wallet["wallets"][pid] = account
    if pid == "player1":
        wallet["gacha"] = account["gacha"]


def _load_wenyou_wallet(user_id: int, session: Optional[dict] = None) -> dict:
    seed_points = 100
    if isinstance(session, dict):
        st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
        if st.get("points") is not None:
            seed_points = max(0, int(st.get("points") or 0))
    return _normalize_wallet(r2_store.get_wenyou_wallet(int(user_id)), seed_points=seed_points)


def _save_wenyou_wallet(user_id: int, wallet: dict) -> None:
    _sync_wallet_compat_aliases(wallet)
    wallet["updated_at"] = now_beijing_iso()
    wallet["inventory"] = _carryable_inventory(wallet.get("inventory"))
    wallet["inventories"]["player1"] = list(wallet["inventory"])
    wallet["inventories"]["player2"] = _carryable_inventory(wallet["inventories"].get("player2"))
    r2_store.save_wenyou_wallet(int(user_id), _normalize_wallet(wallet, seed_points=int(wallet.get("points") or 0)))


def _sync_session_points_with_wallet(session: dict, wallet: dict) -> None:
    _session_ensure_stats(session)
    session["stats"]["points"] = max(0, int(wallet.get("points") or 0))
    session["wallet"] = {
        "points": max(0, int(wallet.get("points") or 0)),
        "debts": max(0, int(wallet.get("debts") or 0)),
        "total_exp": max(0, int(wallet.get("total_exp") or 0)),
        "forced_instance_queue": [x for x in (wallet.get("forced_instance_queue") or []) if isinstance(x, dict)][:8],
    }


def _session_max_pollution(session: Optional[dict]) -> int:
    if not isinstance(session, dict):
        return 0
    _session_ensure_stats(session)
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    values = []
    for pid in ("player1", "player2"):
        player = st.get(pid)
        if isinstance(player, dict):
            values.append(max(0, int(player.get("pollution") or 0)))
    return max(values or [0])


def _player_recommended_rank(session: Optional[dict]) -> str:
    if not isinstance(session, dict):
        return "D"
    _session_ensure_stats(session)
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    player = st.get("player1") if isinstance(st.get("player1"), dict) else {}
    return _normalize_difficulty(player.get("rank") or "D")


def _forced_queue_item(queue_id: str, title: str, difficulty: str, reason: str, penalty_type: str, locked: bool = False) -> dict[str, Any]:
    return {
        "id": queue_id,
        "title": title,
        "difficulty": _normalize_difficulty(difficulty),
        "reason": reason,
        "penalty_type": penalty_type,
        "locked": bool(locked),
        "created_at": now_beijing_iso(),
    }


def _higher_rank(a: Any, b: Any) -> str:
    left = _normalize_difficulty(a)
    right = _normalize_difficulty(b)
    return left if _rarity_rank(left) >= _rarity_rank(right) else right


def _refresh_forced_instance_queue(wallet: dict, session: Optional[dict] = None) -> bool:
    existing = [x for x in (wallet.get("forced_instance_queue") or []) if isinstance(x, dict) and not x.get("resolved")]
    by_id = {str(x.get("id") or ""): dict(x) for x in existing if str(x.get("id") or "")}
    rank = _player_recommended_rank(session)
    debts = max(0, int(wallet.get("debts") or 0))
    pollution = _session_max_pollution(session)
    history = [x for x in (wallet.get("settlement_history") or []) if isinstance(x, dict)]
    recent_deaths = 0
    for rec in reversed(history[-4:]):
        if str(rec.get("result") or "") == "death_failed":
            recent_deaths += 1
        else:
            break
    if debts >= 3000:
        by_id["debt_clearance"] = _forced_queue_item("debt_clearance", "债务清算：红门夜班", _higher_rank(rank, "B"), "债务达到 3000，系统已锁定下一次清算副本。", "debt", True)
    elif debts >= 1000:
        by_id["debt_collection"] = _forced_queue_item("debt_collection", "债务催收：午夜客服", _higher_rank(rank, "C"), "债务达到 1000，系统将在候选池插入催收副本。", "debt", False)
    if pollution >= 90:
        by_id["pollution_clearance"] = _forced_queue_item("pollution_clearance", "污染清算：白室净化班", _higher_rank(rank, "B"), "污染达到 90，系统已强制安排净化副本。", "pollution", True)
    elif pollution >= 60:
        by_id["pollution_purification"] = _forced_queue_item("pollution_purification", "污染净化：异常门诊夜班", _higher_rank(rank, "C"), "污染达到 60，系统将在候选池插入净化副本。", "pollution", False)
    if recent_deaths >= 2:
        by_id["revive_labor"] = _forced_queue_item("revive_labor", "复活清算：临时身份", _higher_rank(rank, "C"), "连续 2 次死亡失败，需以副本 NPC 身份完成复活代价清算。", "revive", True)
    if wallet.get("contract_debt"):
        by_id["contract_collection"] = _forced_queue_item("contract_collection", "契约追偿：坏账处理处", _higher_rank(rank, "B"), "存在未偿还的 S 级能力或契约代价，系统已发起追偿。", "contract", True)
    priority = {"debt_clearance": 0, "pollution_clearance": 1, "revive_labor": 2, "contract_collection": 3, "debt_collection": 4, "pollution_purification": 5}
    queue = sorted(by_id.values(), key=lambda x: (priority.get(str(x.get("id") or ""), 99), str(x.get("created_at") or "")))[:8]
    def _queue_fingerprint(items: list[dict]) -> list[tuple[Any, ...]]:
        return [
            (
                x.get("id"),
                x.get("locked"),
                x.get("title"),
                x.get("difficulty"),
                x.get("reason"),
                x.get("penalty_type"),
            )
            for x in items
        ]

    old_ids = _queue_fingerprint(existing)
    new_ids = _queue_fingerprint(queue)
    wallet["forced_instance_queue"] = queue
    wallet["forced_instance_framework_cache"] = _normalize_forced_framework_cache(wallet.get("forced_instance_framework_cache"), wallet, session)
    return old_ids != new_ids


def _forced_candidate_from_queue(item: dict) -> dict[str, Any]:
    penalty_type = str(item.get("penalty_type") or "system")
    genre = "潜伏调查"
    core_task = "玩家一和玩家二一起以副本原住民 NPC 身份进入其他任务者正在进行的副本；演好各自身份，并用符合身份的方式推动正常任务者的副本进度。"
    hook = "两人都不能暴露自己是玩家、任务者、清算对象或外来者；NPC 身份越靠近主线核心，危险越高。"
    return {
        "id": "forced_" + str(item.get("id") or "penalty"),
        "title": str(item.get("title") or "强制清算副本"),
        "instance_genre": genre,
        "difficulty": _normalize_difficulty(item.get("difficulty") or "C"),
        "tagline": "系统已锁定下一次副本入口。",
        "premise": str(item.get("reason") or "系统检测到未清算代价。") + " 该原因只作为后端结算 metadata，不作为剧情主题。",
        "core_task": core_task,
        "survival_hook": hook,
        "risk": "演崩身份、直接剧透或破坏副本世界观会导致清算失败，后端再按原因追加债务、污染、封印或追猎状态。",
        "twist": "正常任务者的任务可以围绕两名玩家扮演的 NPC 展开；玩家站在剧情中心，但不能用任务者身份行动。",
        "tags": ["强制", "惩罚副本", "NPC扮演", "临时身份", penalty_type],
        "estimated_length": "短中篇",
        "forced": True,
        "locked": bool(item.get("locked")),
        "queue_id": str(item.get("id") or ""),
        "penalty_type": penalty_type,
    }


def _forced_candidate_cache_key(candidate: dict) -> str:
    queue_id = str(candidate.get("queue_id") or candidate.get("id") or "forced_penalty").replace("forced_", "", 1)
    penalty = str(candidate.get("penalty_type") or "system").strip().lower() or "system"
    difficulty = _normalize_difficulty(candidate.get("difficulty") or "C")
    player1 = _slug_id(str(candidate.get("player1_name_hint") or "玩家一"))[:24]
    player2 = _slug_id(str(candidate.get("player2_name_hint") or "玩家二"))[:24]
    title = _slug_id(str(candidate.get("title") or "forced"))[:40]
    return "|".join([queue_id, penalty, difficulty, player1, player2, title])


def _forced_candidates_from_wallet_queue(wallet: dict, session: Optional[dict] = None) -> list[dict]:
    queue = [x for x in (wallet.get("forced_instance_queue") or []) if isinstance(x, dict) and not x.get("resolved")]
    player1_name = _wallet_player_display_name(wallet, "player1", "玩家一")
    player2_name = _wallet_player_display_name(wallet, "player2", "玩家二")
    candidates = []
    for row in queue[:2]:
        item = _forced_candidate_from_queue(row)
        item["player1_name_hint"] = player1_name
        item["player2_name_hint"] = player2_name
        candidates.append(item)
    return candidates


def _normalize_forced_framework_cache(raw: Any, wallet: Optional[dict] = None, session: Optional[dict] = None) -> list[dict]:
    current_keys: set[str] = set()
    if isinstance(wallet, dict):
        current_keys = {_forced_candidate_cache_key(x) for x in _forced_candidates_from_wallet_queue(wallet, session)}
    out: list[dict] = []
    seen: set[str] = set()
    for item in (raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        if not candidate.get("forced"):
            continue
        cache_key = str(item.get("cache_key") or _forced_candidate_cache_key(candidate))
        if current_keys and cache_key not in current_keys:
            continue
        framework = item.get("framework") if isinstance(item.get("framework"), dict) else None
        if not framework:
            continue
        cache_id = str(item.get("cache_id") or f"forced_fw_{uuid4().hex[:10]}")
        unique = f"{cache_key}:{cache_id}"
        if unique in seen:
            continue
        seen.add(unique)
        out.append(
            {
                "cache_id": cache_id,
                "cache_key": cache_key,
                "queue_id": str(item.get("queue_id") or candidate.get("queue_id") or ""),
                "candidate": copy.deepcopy(candidate),
                "framework": _normalize_framework(copy.deepcopy(framework)),
                "created_at": str(item.get("created_at") or now_beijing_iso()),
            }
        )
    return out[-_FORCED_FRAMEWORK_CACHE_MAX:]


def _forced_framework_cache_counts(cache: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in cache:
        key = str(item.get("cache_key") or "")
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _append_forced_framework_cache(wallet: dict, candidate: dict, framework: dict) -> None:
    cache = _normalize_forced_framework_cache(wallet.get("forced_instance_framework_cache"), wallet)
    cache_key = _forced_candidate_cache_key(candidate)
    cache.append(
        {
            "cache_id": f"forced_fw_{uuid4().hex[:10]}",
            "cache_key": cache_key,
            "queue_id": str(candidate.get("queue_id") or ""),
            "candidate": copy.deepcopy(candidate),
            "framework": _normalize_framework(copy.deepcopy(framework)),
            "created_at": now_beijing_iso(),
        }
    )
    wallet["forced_instance_framework_cache"] = cache[-_FORCED_FRAMEWORK_CACHE_MAX:]


def _take_cached_forced_framework(wallet: dict, candidate: dict) -> Optional[dict]:
    cache = _normalize_forced_framework_cache(wallet.get("forced_instance_framework_cache"), wallet)
    cache_key = _forced_candidate_cache_key(candidate)
    for index, item in enumerate(cache):
        if str(item.get("cache_key") or "") != cache_key:
            continue
        framework = copy.deepcopy(item.get("framework") or {})
        del cache[index]
        wallet["forced_instance_framework_cache"] = cache
        return _normalize_framework(framework)
    wallet["forced_instance_framework_cache"] = cache
    return None


def _prewarm_forced_framework_cache(user_id: int, target: int = _FORCED_FRAMEWORK_CACHE_TARGET) -> None:
    uid = int(user_id)
    try:
        for _ in range(max(1, int(target or _FORCED_FRAMEWORK_CACHE_TARGET))):
            session = r2_store.get_wenyou_session(uid)
            wallet = _load_wenyou_wallet(uid, session if isinstance(session, dict) else None)
            queue_changed = _refresh_forced_instance_queue(wallet, session if isinstance(session, dict) else None)
            candidates = _forced_candidates_from_wallet_queue(wallet, session if isinstance(session, dict) else None)
            cache = _normalize_forced_framework_cache(
                wallet.get("forced_instance_framework_cache"),
                wallet,
                session if isinstance(session, dict) else None,
            )
            wallet["forced_instance_framework_cache"] = cache
            if queue_changed:
                _save_wenyou_wallet(uid, wallet)
            if not candidates or len(cache) >= _FORCED_FRAMEWORK_CACHE_TARGET:
                return
            counts = _forced_framework_cache_counts(cache)
            candidate = min(candidates, key=lambda x: (counts.get(_forced_candidate_cache_key(x), 0), _forced_candidate_cache_key(x)))
            fw, err = generate_framework_from_candidate(candidate)
            if err or not fw:
                logger.warning("文游惩罚副本框架预热失败 user_id=%s candidate=%s error=%s", uid, candidate.get("id"), err)
                return
            latest_session = r2_store.get_wenyou_session(uid)
            latest_wallet = _load_wenyou_wallet(uid, latest_session if isinstance(latest_session, dict) else None)
            _refresh_forced_instance_queue(latest_wallet, latest_session if isinstance(latest_session, dict) else None)
            current_keys = {
                _forced_candidate_cache_key(x)
                for x in _forced_candidates_from_wallet_queue(
                    latest_wallet,
                    latest_session if isinstance(latest_session, dict) else None,
                )
            }
            if _forced_candidate_cache_key(candidate) not in current_keys:
                return
            _append_forced_framework_cache(latest_wallet, candidate, fw)
            _save_wenyou_wallet(uid, latest_wallet)
    except Exception as e:
        logger.warning("文游惩罚副本框架预热线程异常 user_id=%s error=%s", uid, e, exc_info=True)
    finally:
        with _FORCED_FRAMEWORK_PREFETCH_LOCK:
            _FORCED_FRAMEWORK_PREFETCHING.discard(uid)


def _schedule_forced_framework_prewarm(user_id: int) -> None:
    uid = int(user_id)
    with _FORCED_FRAMEWORK_PREFETCH_LOCK:
        if uid in _FORCED_FRAMEWORK_PREFETCHING:
            return
        _FORCED_FRAMEWORK_PREFETCHING.add(uid)
    threading.Thread(target=_prewarm_forced_framework_cache, args=(uid,), name=f"wenyou-forced-prewarm-{uid}", daemon=True).start()


def _tutorial_pack_granted(wallet: Optional[dict]) -> bool:
    return bool(isinstance(wallet, dict) and wallet.get("newbie_starter_pack_granted"))


def _tutorial_flow_completed(wallet: Optional[dict]) -> bool:
    return bool(
        isinstance(wallet, dict)
        and (
            wallet.get("tutorial_completed")
            or wallet.get("tutorial_completed_at")
            or wallet.get("newbie_starter_pack_granted")
        )
    )


def _should_offer_tutorial(user_id: int, wallet: Optional[dict] = None) -> bool:
    if wallet is None:
        wallet = _load_wenyou_wallet(int(user_id))
    return not _tutorial_flow_completed(wallet)


def _tutorial_candidate() -> dict[str, Any]:
    return {
        "id": _WENYOU_TUTORIAL_INSTANCE_ID,
        "title": "白箱回廊",
        "instance_genre": "剧情解密",
        "difficulty": "D",
        "tagline": "主神为新任务者准备的低危校准副本。",
        "premise": "一条洁白回廊被分成三段，墙面会在玩家行动后亮起提示。这里没有其他任务者，危险主要来自误操作和规则理解错误。",
        "core_task": "完成三段基础行动校准，找到出口并返回主神空间。",
        "survival_hook": "红灯亮起时先停下观察，白灯亮起时再移动。",
        "risk": "连续无视提示会被弹回起点，造成少量 HP/SAN 损耗。",
        "twist": "最后一道门会检查玩家是否真的理解了任务、背包和角色面板。",
        "tags": ["新手引导", "无NPC", "低危", "系统教学"],
        "estimated_length": "短篇",
        "tutorial": True,
        "locked": True,
    }


def _is_tutorial_candidate(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    return bool(candidate.get("tutorial") or candidate.get("is_tutorial") or str(candidate.get("id") or "") == _WENYOU_TUTORIAL_INSTANCE_ID)


def _attach_forced_instance_contract(session: dict, candidate: Any) -> None:
    if not isinstance(candidate, dict) or not candidate.get("forced"):
        return
    queue_id = str(candidate.get("queue_id") or candidate.get("id") or "forced_penalty").replace("forced_", "", 1)
    queue_penalty = {
        "debt_clearance": "debt",
        "debt_collection": "debt",
        "pollution_clearance": "pollution",
        "pollution_purification": "pollution",
        "revive_labor": "revive",
        "contract_collection": "contract",
    }.get(queue_id, "system")
    penalty_type = str(candidate.get("penalty_type") or queue_penalty).strip().lower()
    if penalty_type not in {"debt", "pollution", "revive", "contract", "system"}:
        penalty_type = queue_penalty
    for tag in candidate.get("tags") or []:
        tag_text = str(tag or "")
        if tag_text in {"debt", "pollution", "revive", "contract"}:
            penalty_type = tag_text
            break
    work_order = str(candidate.get("core_task") or "完成系统指定任务并存活。")
    forced = {
        "queue_id": queue_id,
        "penalty_type": penalty_type,
        "locked": bool(candidate.get("locked")),
        "mode": "npc_labor",
        "participants": ["player1", "player2"],
        "participant_identities": {"player1": "副本原住民 NPC", "player2": "副本原住民 NPC"},
        "disguised_identity": "副本原住民 NPC",
        "shared_objective": True,
        "work_order": _compact_text(work_order, 220),
        "forbidden_disclosures": ["玩家身份", "任务者身份", "清算对象身份", "外来者身份", "副本结局/隐藏规则"],
        "exposure_to_taskers": 0,
        "exposure_to_monsters": 0,
        "resolved": False,
        "started_at": now_beijing_iso(),
    }
    session["forced_instance"] = forced
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    rules["forced_instance"] = copy.deepcopy(forced)
    runtime["rules_state"] = rules
    public = runtime.get("public_state") if isinstance(runtime.get("public_state"), dict) else {}
    public["forced_notice"] = "强制清算副本已接入：维持双方 NPC 身份，完成系统目标。"
    runtime["public_state"] = public
    session["runtime_state"] = runtime


def apply_forced_instance_candidates(user_id: int, payload: Optional[dict] = None) -> dict:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    wallet = _load_wenyou_wallet(uid, session if isinstance(session, dict) else None)
    changed = _refresh_forced_instance_queue(wallet, session if isinstance(session, dict) else None)
    if changed:
        _save_wenyou_wallet(uid, wallet)
    queue = [x for x in (wallet.get("forced_instance_queue") or []) if isinstance(x, dict)]
    data = copy.deepcopy(payload) if isinstance(payload, dict) else {"version": 1, "generatedAt": now_beijing_iso(), "items": []}
    items = [
        x
        for x in (data.get("items") or [])
        if isinstance(x, dict) and not x.get("forced") and str(x.get("id") or "") != _WENYOU_TUTORIAL_INSTANCE_ID and not x.get("tutorial")
    ]
    forced = [_forced_candidate_from_queue(x) for x in queue[:2]]
    tutorial = [_tutorial_candidate()] if _should_offer_tutorial(uid, wallet) else []
    data["items"] = (forced + tutorial + items)[:8]
    data["forced_instance_queue"] = queue if forced else []
    return data


def get_forced_instance_prompt(user_id: int) -> dict:
    """Return the current forced-instance prompt without generating normal candidates."""
    payload = apply_forced_instance_candidates(
        int(user_id),
        {"version": 1, "generatedAt": now_beijing_iso(), "items": []},
    )
    items = [x for x in (payload.get("items") or []) if isinstance(x, dict) and x.get("forced")]
    if items:
        _schedule_forced_framework_prewarm(int(user_id))
    return {
        "forced": bool(items),
        "item": items[0] if items else None,
        "items": items[:2],
        "forced_instance_queue": payload.get("forced_instance_queue") or [],
    }


def _normalize_settlement_result(value: Any) -> str:
    result = str(value or "").strip().lower()
    aliases = {
        "clear": "standard_clear",
        "通关": "standard_clear",
        "standard": "standard_clear",
        "escape": "low_escape",
        "低完成": "low_escape",
        "fail_escape": "failed_escape",
        "失败撤离": "failed_escape",
        "death": "death_failed",
        "死亡": "death_failed",
        "abandon": "abandoned",
        "放弃": "abandoned",
    }
    result = aliases.get(result, result)
    return result if result in _WENYOU_RESULT_FACTORS else "standard_clear"


def _normalize_rating(value: Any, result: str) -> str:
    rating = str(value or "").strip().upper()
    if rating in _WENYOU_RATING_BONUS:
        return rating
    if result == "standard_clear":
        return "B"
    if result == "low_escape":
        return "C"
    if result == "failed_escape":
        return "F"
    return "F"


def _recalc_player_caps(player: dict) -> None:
    _normalize_player_growth_fields(player)
    level = max(1, int(player.get("level") or 1))
    strength = max(0, int(player.get("str") or 10))
    con = max(0, int(player.get("con") or player.get("vit") or 10))
    agi = max(0, int(player.get("agi") or 10))
    intel = max(0, int(player.get("int") or player.get("wis") or 10))
    spi = max(0, int(player.get("spi") or 10))
    luk = max(0, int(player.get("luk") or 10))
    rank = _normalize_difficulty(player.get("rank") or "D")
    hp_max = 80 + con * 10 + (level - 1) * 6 + _WENYOU_RANK_HP_BONUS.get(rank, 0)
    san_max = 120 + intel * 6 + (level - 1) * 6 + _WENYOU_RANK_SAN_BONUS.get(rank, 0)
    spi_max = spi + _WENYOU_RANK_SPI_BONUS.get(rank, 0)
    player["hp_max"] = max(1, hp_max)
    player["san_max"] = max(1, san_max)
    player["spi_max"] = max(0, spi_max)
    player["hp"] = max(0, min(int(player.get("hp") or 0), player["hp_max"]))
    player["san"] = max(0, min(int(player.get("san") or 0), player["san_max"]))
    player["spi_current"] = max(0, min(int(player.get("spi_current") or 0), player["spi_max"]))
    player["physical_attack"] = math.floor(strength / 2)
    player["ranged_attack"] = math.floor((agi + intel) / 4)
    player["defense"] = math.floor(con / 3) + int(_WENYOU_RANK_PHYSICAL_REDUCTION.get(rank, 0))
    player["mental_resist"] = math.floor(int(player.get("spi_current") or 0) / 3) + int(_WENYOU_RANK_MENTAL_REDUCTION.get(rank, 0))
    player["carry_limit"] = strength + math.floor(con / 2)


def _apply_san_delta_to_spi(player: dict, san_delta: int, mental_recovery: bool = False) -> int:
    before = max(0, int(player.get("spi_current") or 0))
    spi_max = max(0, int(player.get("spi_max") or player.get("spi") or 0))
    after = before
    if san_delta < 0:
        after -= max(1, math.ceil(abs(int(san_delta)) / 25))
    elif san_delta > 0 and mental_recovery:
        after += math.ceil(int(san_delta) / 30)
    after = max(0, min(spi_max, after))
    player["spi_current"] = after
    return after - before


def _grant_player_exp(player: dict, exp_gain: int) -> dict:
    gained_levels = 0
    unspent = int(player.get("unspent_attribute_points") or 0)
    player["exp"] = max(0, int(player.get("exp") or 0)) + max(0, int(exp_gain or 0))
    player["level"] = max(1, int(player.get("level") or 1))
    while player["level"] < 30 and player["exp"] >= int(_WENYOU_LEVEL_EXP_TABLE.get(player["level"], 999999)):
        need = int(_WENYOU_LEVEL_EXP_TABLE.get(player["level"], 999999))
        player["exp"] -= need
        player["level"] += 1
        gained_levels += 1
        unspent += 2
    player["unspent_attribute_points"] = unspent
    _recalc_player_caps(player)
    return {
        "level_delta": gained_levels,
        "unspent_attribute_points": unspent,
    }


def _recent_gm_text(session: dict, limit: int = 4) -> str:
    lines: list[str] = []
    for item in reversed(session.get("history") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "gm":
            continue
        content = _strip_main_god_panel(str(item.get("content") or ""))
        content = re.sub(r"\s+", " ", content).strip()
        if content:
            lines.append(content[:500])
        if len(lines) >= limit:
            break
    return "\n".join(reversed(lines))


def _all_player_stats(session: dict) -> list[dict]:
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    players: list[dict] = []
    for pk in ("player1", "player2"):
        player = st.get(pk)
        if isinstance(player, dict):
            players.append(player)
    return players


def _infer_settlement_result(session: dict) -> tuple[str, str, str]:
    """Infer a settlement result from current structured state and recent GM text."""
    players = _all_player_stats(session)
    if any(int(p.get("hp") or 0) <= 0 for p in players):
        return "death_failed", "high", "检测到玩家 HP 归零。"

    rules = _rules_state_from_session(session)
    flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    tasks = _rules_mapping(rules.get("task_progress"), "task")
    main_tasks = [x for x in tasks.values() if str(x.get("type") or "main") == "main"]
    if flags.get("mainline_status") == "failed" or any(str(x.get("status") or "") == "failed" for x in main_tasks):
        return "failed_escape", "high", "规则缓存记录主线失败。"
    if flags.get("hidden_endings"):
        return "standard_clear", "high", "规则缓存记录隐藏结局已触发。"
    if flags.get("mainline_status") == "completed" or any(str(x.get("status") or "") == "completed" for x in main_tasks):
        return "standard_clear", "high", "规则缓存记录主线已完成。"

    recent = _recent_gm_text(session)
    if re.search(r"(团灭|彻底失败|死亡失败|任务失败|副本失败)", recent):
        return "death_failed", "low", "未发现规则缓存通关标记，仅旧叙事出现失败/死亡信号。"
    if re.search(r"(失败撤离|强制撤离|撤离失败|只保住性命)", recent):
        return "failed_escape", "low", "未发现规则缓存通关标记，仅旧叙事出现失败撤离信号。"
    if re.search(r"(低完成逃生|逃出生天|成功撤离|脱出|逃离副本|生还)", recent):
        return "low_escape", "low", "未发现规则缓存主线完成标记，仅旧叙事出现撤离/生还信号。"
    if re.search(r"(通关|达成主线|主线完成|任务完成|副本结束|回归主神空间|进入结算)", recent):
        return "low_escape", "low", "旧叙事疑似通关，但规则缓存未确认主线完成。"

    clocks = session.get("clocks") if isinstance(session.get("clocks"), list) else []
    if any(isinstance(c, dict) and int(c.get("value") or 0) >= int(c.get("max") or 9999) for c in clocks):
        return "failed_escape", "medium", "威胁时钟已触顶。"

    return "low_escape", "low", "规则缓存未确认主线完成，按低完成撤离预估。"


def _rating_from_score(score: int, result: str) -> str:
    if result in {"failed_escape", "death_failed", "abandoned"}:
        return "F"
    if score >= 95:
        return "S"
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    if score >= 20:
        return "D"
    return "F"


def _estimate_settlement_score(session: dict, result: str) -> dict:
    players = _all_player_stats(session)
    clues = _clues_from_session(session)
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    rules = _rules_state_from_session(session)
    flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    task_progress = _rules_mapping(rules.get("task_progress"), "task")
    clue_state = _rules_mapping(rules.get("clue_state"), "clue")
    main_tasks = [x for x in task_progress.values() if str(x.get("type") or "main") == "main"]
    side_tasks = [
        x
        for x in task_progress.values()
        if str(x.get("type") or "") in {"side", "side_quest", "支线"} and str(x.get("status") or "") == "completed"
    ]
    hidden_tasks = [
        x
        for x in task_progress.values()
        if str(x.get("type") or "") in {"hidden", "hidden_side", "隐藏", "隐藏支线"} and str(x.get("status") or "") in {"completed", "hidden_completed"}
    ]

    mainline_completion = float(flags.get("mainline_completion") or 0)
    if flags.get("mainline_status") == "completed" or any(str(x.get("status") or "") == "completed" for x in main_tasks):
        mainline_completion = max(mainline_completion, 1.0)
    elif main_tasks:
        active_count = sum(1 for x in main_tasks if str(x.get("status") or "") in {"active", "completed"})
        mainline_completion = max(mainline_completion, min(0.7, active_count / max(1, len(main_tasks))))
    if result in {"failed_escape", "death_failed", "abandoned"}:
        mainline = 0 if result in {"death_failed", "abandoned"} else min(10, round(45 * mainline_completion))
    elif result == "low_escape":
        mainline = min(25, round(45 * mainline_completion))
    else:
        mainline = round(45 * max(mainline_completion, 0.75))

    verified_clues = [
        x
        for x in clue_state.values()
        if str(x.get("status") or "") == "verified" or bool(x.get("verified"))
    ]
    discovered_clues = max(len(clues), len(clue_state))

    side_completed = list(dict.fromkeys((flags.get("side_completed") or []) + [str(x.get("title") or x.get("id")) for x in side_tasks]))
    side = min(15, len(side_completed) * 5)

    hidden_completed = list(dict.fromkeys((flags.get("hidden_completed") or []) + [str(x.get("title") or x.get("id")) for x in hidden_tasks]))
    hidden_endings = _normalize_text_list(flags.get("hidden_endings"), 80, 20)
    hidden_side = min(15, len(hidden_completed) * 5)
    hidden_ending = min(15, len(hidden_endings) * 15)

    achievements = 0
    achievement_notes: list[str] = _normalize_text_list(flags.get("achievements"), 80, 4)
    if flags.get("achievements"):
        achievements += min(10, len(flags.get("achievements") or []) * 4)
    if players and all(int(p.get("hp") or 0) > 0 for p in players) and result not in {"death_failed", "abandoned"}:
        achievements += 8
        if "玩家角色全部存活" not in achievement_notes:
            achievement_notes.append("玩家角色全部存活")
    severe_conditions = {"污染", "失控", "濒死", "重伤"}
    all_conditions: list[str] = []
    for p in players:
        all_conditions.extend(str(c) for c in (p.get("conditions") or []) if str(c).strip())
    if players:
        san_ratio = sum((int(p.get("san") or 0) / max(1, int(p.get("san_max") or 180))) for p in players) / len(players)
        if san_ratio >= 0.55 and not any(c in severe_conditions for c in all_conditions):
            achievements += 6
            if "低污染" not in achievement_notes:
                achievement_notes.append("低污染")
    losses = flags.get("losses") if isinstance(flags.get("losses"), dict) else {}
    revive_count = max(0, int(losses.get("revive_count") or 0))
    if revive_count <= 0:
        achievements += 5
        if "无复活" not in achievement_notes:
            achievement_notes.append("无复活")
    achievements = min(15, achievements)

    loss = 5
    if players:
        hp_ratio = sum((int(p.get("hp") or 0) / max(1, int(p.get("hp_max") or 180))) for p in players) / len(players)
        san_ratio = sum((int(p.get("san") or 0) / max(1, int(p.get("san_max") or 180))) for p in players) / len(players)
        if hp_ratio >= 0.7 and san_ratio >= 0.7:
            loss += 5
        if hp_ratio < 0.35:
            loss -= 8
        if san_ratio < 0.35:
            loss -= 8
    for cond in all_conditions:
        if cond in {"轻伤", "动摇"}:
            loss -= 2
        elif cond in {"重伤", "污染"}:
            loss -= 5
        elif cond in {"濒死", "失控"}:
            loss -= 10
    wallet = session.get("wallet")
    debts = 0
    if isinstance(wallet, dict):
        debts = int(wallet.get("debts") or 0)
    debts += max(0, int(losses.get("debt_added") or 0))
    if debts:
        loss -= min(10, math.ceil(debts / 300))
    heavy_injury_count = max(0, int(losses.get("heavy_injury_count") or 0))
    death_count = max(0, int(losses.get("death_count") or 0))
    loss -= min(10, heavy_injury_count * 3 + death_count * 8)
    if flags.get("loss_flags"):
        loss -= min(8, len(flags.get("loss_flags") or []) * 2)
    if result == "death_failed":
        loss -= 20
    elif result == "abandoned":
        loss -= 10
    loss = max(-20, min(10, loss))

    total = max(0, min(100, mainline + side + hidden_side + hidden_ending + achievements + loss))
    return {
        "rating_score": total,
        "score_breakdown": [
            {"id": "mainline", "label": "主线完成度", "score": mainline, "max": 45},
            {"id": "side", "label": "支线完成", "score": side, "max": 15, "notes": side_completed[:4]},
            {"id": "hidden_side", "label": "隐藏支线", "score": hidden_side, "max": 15, "notes": hidden_completed[:4]},
            {"id": "hidden_ending", "label": "隐藏结局", "score": hidden_ending, "max": 15, "notes": hidden_endings[:4]},
            {"id": "achievements", "label": "特殊成就", "score": achievements, "max": 15, "notes": achievement_notes[:4]},
            {"id": "loss", "label": "损耗控制", "score": loss, "max": 10},
        ],
        "history_rounds": sum(1 for item in (session.get("history") or []) if isinstance(item, dict) and item.get("role") == "gm"),
        "clue_count": discovered_clues,
        "verified_clue_count": len(verified_clues),
        "event_count": len(event_log),
    }


def _build_settlement_preview(session: dict, result: str = "", rating: str = "") -> dict:
    result = str(result or "").strip()
    if result:
        normalized_result = _normalize_settlement_result(result)
        confidence = "manual"
        reason = "按当前选择预估。"
    else:
        normalized_result, confidence, reason = _infer_settlement_result(session)
    score = _estimate_settlement_score(session, normalized_result)
    normalized_rating = str(rating or "").strip().upper()
    if normalized_result in {"failed_escape", "death_failed", "abandoned"}:
        rating_value = "F"
        rating_source = "forced"
    elif normalized_rating in _WENYOU_RATING_BONUS:
        rating_value = normalized_rating
        rating_source = "manual"
    else:
        rating_value = _rating_from_score(int(score.get("rating_score") or 0), normalized_result)
        rating_source = "score"
    reward = _calculate_settlement_reward(session, normalized_result, rating_value)
    return {
        "result": normalized_result,
        "result_label": _WENYOU_RESULT_FACTORS[normalized_result]["label"],
        "rating": rating_value,
        "rating_label": _WENYOU_RATING_LABELS.get(rating_value, rating_value),
        "rating_score": int(score.get("rating_score") or 0),
        "rating_source": rating_source,
        "confidence": confidence,
        "reason": reason,
        "score_breakdown": score.get("score_breakdown") or [],
        "history_rounds": int(score.get("history_rounds") or 0),
        "clue_count": int(score.get("clue_count") or 0),
        "verified_clue_count": int(score.get("verified_clue_count") or 0),
        "event_count": int(score.get("event_count") or 0),
        "reward": reward,
        "options": {"results": _WENYOU_RESULT_OPTIONS, "ratings": _WENYOU_RATING_OPTIONS},
    }


def _settlement_achievement_reward_bonus(session: dict, result: str) -> dict:
    if result in {"failed_escape", "death_failed", "abandoned"}:
        return {"points_bonus": 0.0, "exp_bonus": 0.0, "notes": []}
    rules = _rules_state_from_session(session)
    flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    points_bonus = 0.0
    exp_bonus = 0.0
    notes: list[str] = []

    def add(note: str, points: float, exp: float) -> None:
        nonlocal points_bonus, exp_bonus
        text = _compact_text(note, 80)
        if text and text not in notes:
            notes.append(text)
        points_bonus += points
        exp_bonus += exp

    hidden_endings = _normalize_text_list(flags.get("hidden_endings"), 80, 20)
    hidden_completed = _normalize_text_list(flags.get("hidden_completed"), 80, 30)
    side_completed = _normalize_text_list(flags.get("side_completed"), 80, 30)
    if hidden_endings:
        add("触发隐藏结局", 0.20, 0.15)
    if hidden_completed:
        add("完成隐藏支线", min(0.24, 0.08 * len(hidden_completed)), min(0.24, 0.08 * len(hidden_completed)))
    if side_completed:
        add("完成普通支线", min(0.18, 0.06 * len(side_completed)), min(0.18, 0.06 * len(side_completed)))
    for achievement in _normalize_text_list(flags.get("achievements"), 80, 30):
        lower = achievement.lower()
        if "低污染" in achievement or "low_pollution" in lower:
            add(achievement, 0.06, 0.05)
        elif "无复活" in achievement or "no_revive" in lower:
            add(achievement, 0.05, 0.05)
        elif "限时" in achievement or "time" in lower:
            add(achievement, 0.06, 0.05)
        else:
            add(achievement, 0.05, 0.04)
    return {
        "points_bonus": min(0.60, max(0.0, points_bonus)),
        "exp_bonus": min(0.50, max(0.0, exp_bonus)),
        "notes": notes[:6],
    }


def _calculate_settlement_reward(session: dict, result: str, rating: str) -> dict:
    fw = _framework_for_runtime(session.get("framework") or {})
    difficulty = _normalize_difficulty(fw.get("difficulty"))
    base = _WENYOU_CLEAR_BASE_REWARD[difficulty]
    factors = _WENYOU_RESULT_FACTORS[result]
    rating_bonus = _WENYOU_RATING_BONUS[rating]
    achievement_bonus = _settlement_achievement_reward_bonus(session, result)
    base_points = round(base["points"] * factors["points"])
    base_exp = round(base["exp"] * factors["exp"])
    rating_points = round(base_points * rating_bonus["points"])
    rating_exp = round(base_exp * rating_bonus["exp"])
    achievement_points = round(base_points * float(achievement_bonus.get("points_bonus") or 0.0))
    achievement_exp = round(base_exp * float(achievement_bonus.get("exp_bonus") or 0.0))
    gross_points = max(0, base_points + rating_points + achievement_points)
    gross_exp = max(0, base_exp + rating_exp + achievement_exp)
    abandon_penalty = round(base["points"] * 0.15) if result == "abandoned" else 0
    base_rolls = int(base.get("rolls") or 1) if gross_points > 0 else 0
    rating_extra_rolls = 2 if rating == "S" else 1 if rating == "A" else 0
    hidden_bonus_rolls = 1 if gross_points > 0 and "触发隐藏结局" in (achievement_bonus.get("notes") or []) else 0
    return {
        "difficulty": difficulty,
        "result": result,
        "result_label": factors["label"],
        "rating": rating,
        "base_points": base_points,
        "base_exp": base_exp,
        "rating_points": rating_points,
        "rating_exp": rating_exp,
        "achievement_points": achievement_points,
        "achievement_exp": achievement_exp,
        "achievement_bonus": achievement_bonus,
        "gross_points": gross_points,
        "gross_exp": gross_exp,
        "penalty_points": abandon_penalty,
        "reward_rolls": base_rolls + rating_extra_rolls + hidden_bonus_rolls if gross_points > 0 else 0,
        "base_reward_rolls": base_rolls,
        "rating_extra_rolls": rating_extra_rolls if gross_points > 0 else 0,
        "hidden_bonus_rolls": hidden_bonus_rolls,
    }


def _apply_forced_instance_settlement(wallet: dict, session: dict, settlement: dict, result: str) -> dict[str, Any]:
    forced = session.get("forced_instance") if isinstance(session.get("forced_instance"), dict) else None
    if not forced or forced.get("resolved"):
        return {}
    penalty_type = str(forced.get("penalty_type") or "system")
    success = result in {"standard_clear", "low_escape"}
    exposure = max(0, int(forced.get("exposure_to_taskers") or 0) + int(forced.get("exposure_to_monsters") or 0))
    difficulty = _normalize_difficulty(settlement.get("difficulty") or _framework_for_runtime(session.get("framework") or {}).get("difficulty"))
    rank_scale = max(1, _rarity_rank(difficulty) + 1)
    outcome: dict[str, Any] = {
        "queue_id": str(forced.get("queue_id") or ""),
        "penalty_type": penalty_type,
        "success": success,
        "exposure": exposure,
        "notes": [],
    }
    if success:
        if penalty_type == "debt":
            repay = min(max(0, int(wallet.get("debts") or 0)), 350 * rank_scale)
            wallet["debts"] = max(0, int(wallet.get("debts") or 0) - repay)
            outcome["debt_repaid_extra"] = repay
            outcome["notes"].append(f"强制清算额外偿还债务 {repay}")
        elif penalty_type == "pollution":
            st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
            reduction = 10 * rank_scale
            for pid in ("player1", "player2"):
                player = st.get(pid) if isinstance(st.get(pid), dict) else None
                if player:
                    player["pollution"] = max(0, int(player.get("pollution") or 0) - reduction)
            session["stats"] = st
            outcome["pollution_reduced"] = reduction
            outcome["notes"].append(f"污染清算降低污染 {reduction}")
        elif penalty_type == "revive":
            outcome["notes"].append("复活代价清算完成，NPC 身份解除")
        elif penalty_type == "contract":
            wallet["contract_debt"] = False
            outcome["notes"].append("契约追偿完成")
        forced["resolved"] = True
        forced["resolved_at"] = now_beijing_iso()
        forced["result"] = "success"
    else:
        if penalty_type in {"debt", "contract", "revive"}:
            debt_delta = 120 * rank_scale + exposure * 50
            wallet["debts"] = max(0, int(wallet.get("debts") or 0) + debt_delta)
            outcome["debt_added"] = debt_delta
            outcome["notes"].append(f"清算失败追加债务 {debt_delta}")
        if penalty_type in {"pollution", "revive"}:
            st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
            pollution_delta = 4 * rank_scale + exposure * 2
            for pid in ("player1", "player2"):
                player = st.get(pid) if isinstance(st.get(pid), dict) else None
                if player:
                    player["pollution"] = max(0, int(player.get("pollution") or 0) + pollution_delta)
                    _add_condition_unique(player, "污染")
            session["stats"] = st
            outcome["pollution_added"] = pollution_delta
            outcome["notes"].append(f"清算失败追加污染 {pollution_delta}")
        forced["result"] = "failed"
    queue_id = str(forced.get("queue_id") or "")
    queue = []
    for item in wallet.get("forced_instance_queue") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if queue_id and str(row.get("id") or "") == queue_id and success:
            row["resolved"] = True
            row["resolved_at"] = now_beijing_iso()
        queue.append(row)
    wallet["forced_instance_queue"] = queue[:8]
    wallet["forced_instance_framework_cache"] = _normalize_forced_framework_cache(wallet.get("forced_instance_framework_cache"), wallet, session)
    session["forced_instance"] = forced
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    rules["forced_instance"] = copy.deepcopy(forced)
    runtime["rules_state"] = rules
    session["runtime_state"] = runtime
    return outcome


def _is_tutorial_session(session: dict) -> bool:
    if not isinstance(session, dict):
        return False
    fw = _framework_for_runtime(session.get("framework") or {})
    return bool(fw.get("is_tutorial") or str(fw.get("tutorial_id") or "") == _WENYOU_TUTORIAL_INSTANCE_ID)


def _mark_tutorial_started(user_id: int, session: dict, wallet: dict) -> None:
    if not _is_tutorial_session(session) or wallet.get("tutorial_started_at"):
        return
    wallet["tutorial_started_at"] = now_beijing_iso()
    _save_wenyou_wallet(int(user_id), wallet)


def set_wenyou_player_display_name(user_id: int, player_name: Any, player_id: str = "player1") -> str:
    uid = int(user_id or 0)
    pid = _resolve_player_key(player_id)
    fallback = _WENYOU_PLAYER_LABELS.get(pid, pid)
    name = _normalize_player_display_name(player_name, "")
    if not name:
        return ""
    session = r2_store.get_wenyou_session(uid)
    wallet = _load_wenyou_wallet(uid, session if isinstance(session, dict) else None)
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    player = players.get(pid) if isinstance(players.get(pid), dict) else dict(_default_player_stats())
    player["display_name"] = name
    player["display_name_set"] = True
    player["display_name_set_at"] = now_beijing_iso()
    player.setdefault("controller", _WENYOU_PLAYER_CONTROLLERS.get(pid, "human"))
    _normalize_player_growth_fields(player)
    players[pid] = player
    wallet["players"] = players
    _save_wenyou_wallet(uid, wallet)

    if isinstance(session, dict) and session.get("gameId"):
        _session_ensure_stats(session)
        st_player = session["stats"].get(pid) if isinstance(session["stats"].get(pid), dict) else dict(_default_player_stats())
        st_player["display_name"] = name
        st_player["display_name_set"] = True
        st_player.setdefault("controller", _WENYOU_PLAYER_CONTROLLERS.get(pid, "human"))
        session["stats"][pid] = st_player
        fw = session.get("framework") if isinstance(session.get("framework"), dict) else {}
        if pid == "player1":
            fw["player1_name"] = name
        elif pid == "player2":
            fw["player2_name"] = name
        session["framework"] = fw
        session["runtime_state"] = _runtime_state_view(session)
        r2_store.save_wenyou_session(uid, session)
    return name or fallback


def _apply_wallet_player_names_to_framework(framework: dict, wallet: dict) -> dict:
    fw = dict(framework or {})
    p1 = _wallet_player_display_name(wallet, "player1", "")
    p2 = _wallet_player_display_name(wallet, "player2", "")
    if p1:
        fw["player1_name"] = p1
    if p2:
        fw["player2_name"] = p2
    return _normalize_framework(fw)


def get_wenyou_entry_state(user_id: int) -> dict[str, Any]:
    uid = int(user_id or 0)
    wallet = _load_wenyou_wallet(uid)
    player_name = _wallet_confirmed_player_display_name(wallet, "player1")
    player2_name = _wallet_confirmed_player_display_name(wallet, "player2")
    return {
        "tutorial_required": _should_offer_tutorial(uid, wallet),
        "player_name": player_name,
        "player2_name": player2_name,
        "player_name_required": not bool(player_name),
        "player2_name_required": not bool(player2_name),
        "tutorial_code": "T-000",
        "tutorial_title": "白箱回廊",
    }


_WENYOU_CORE_ABILITY_KEYWORDS = {
    "observe": ("observe", "观察", "检查", "线索", "记录", "调查", "分析", "推理", "确认", "打量", "留意", "搜索", "验证"),
    "escape": ("escape", "逃", "跑", "躲", "绕开", "潜行", "撤退", "退后", "藏", "避开", "脱身", "冲过去", "冲"),
    "protect": ("protect", "保护", "挡", "救", "治疗", "扶", "拉住", "掩护", "照顾", "包扎"),
    "combat": ("combat", "打", "砸", "攻击", "硬闯", "破坏", "撞", "压制", "踹", "挥", "砍", "拆", "撬"),
    "social": ("social", "交谈", "询问", "说服", "骗", "伪装", "谈判", "搭话", "套话", "解释", "安慰", "呼唤"),
    "rule": ("rule", "规则", "禁忌", "广播", "时钟", "门牌", "试探", "条件", "仪式", "循环", "红灯", "白灯", "光轨"),
    "resilience": ("resilience", "受伤", "san", "污染", "死亡", "濒死", "忍", "坚持", "疼", "恐惧", "冷静"),
}


def _core_ability_text_source(session: dict, player_id: str) -> str:
    pieces: list[str] = []
    history = session.get("history") if isinstance(session.get("history"), list) else []
    labels = {
        "player1": ("player1", "玩家一", "我"),
        "player2": ("player2", "玩家二"),
    }.get(player_id, (player_id,))
    for entry in history[-80:]:
        if isinstance(entry, dict):
            role = str(entry.get("role") or entry.get("speaker") or entry.get("player_id") or "")
            text = str(entry.get("content") or entry.get("text") or entry.get("message") or "")
            if player_id == "player2" and role and not any(label in role for label in labels):
                continue
            if player_id == "player1" and role and "player2" in role.lower():
                continue
        else:
            text = str(entry or "")
        if text:
            pieces.append(text)
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    reward_context = rules.get("reward_context") if isinstance(rules.get("reward_context"), dict) else {}
    pieces.extend(str(x) for x in reward_context.get("reward_tags") or [] if str(x).strip())
    return "\n".join(pieces)[-4000:]


def _score_core_ability_archetypes(session: dict, player_id: str) -> dict[str, int]:
    text = _core_ability_text_source(session, player_id).lower()
    scores = {key: 0 for key in _WENYOU_CORE_ABILITY_ARCHETYPES}
    for key, words in _WENYOU_CORE_ABILITY_KEYWORDS.items():
        for word in words:
            if not word:
                continue
            scores[key] = scores.get(key, 0) + text.count(str(word).lower())
    if not any(scores.values()):
        scores["survival"] = 1
    return scores


def _core_ability_from_tutorial(session: dict, player_id: str) -> dict[str, Any]:
    scores = _score_core_ability_archetypes(session, player_id)
    archetype = max(scores, key=lambda key: (scores.get(key, 0), -list(_WENYOU_CORE_ABILITY_ARCHETYPES).index(key)))
    template = dict(_WENYOU_CORE_ABILITY_ARCHETYPES.get(archetype) or _WENYOU_CORE_ABILITY_ARCHETYPES["survival"])
    template["origin"] = "tutorial_performance"
    template["source_tags"] = [key for key, value in sorted(scores.items(), key=lambda kv: kv[1], reverse=True) if value > 0][:4]
    template["created_at"] = now_beijing_iso()
    return _normalize_core_ability(template) or dict(_WENYOU_CORE_ABILITY_ARCHETYPES["survival"])


def _core_ability_profile_from_tutorial(session: dict, player_id: str, ability: dict[str, Any]) -> dict[str, Any]:
    scores = _score_core_ability_archetypes(session, player_id)
    picked = str(ability.get("id") or "").replace("core_", "", 1) or "survival"
    source_tags = [key for key, value in sorted(scores.items(), key=lambda kv: kv[1], reverse=True) if value > 0][:4]
    return {
        "source": "tutorial_performance",
        "algorithm_version": 1,
        "history_window": 80,
        "scores": {key: int(value or 0) for key, value in scores.items()},
        "picked": picked,
        "source_tags": source_tags,
        "ability_id": str(ability.get("id") or ""),
        "ability_name": str(ability.get("name") or ""),
        "created_at": str(ability.get("created_at") or now_beijing_iso()),
    }


def _grant_newbie_starter_pack(session: dict, wallet: dict, result: str) -> dict[str, Any]:
    if result != "standard_clear" or not _is_tutorial_session(session) or _tutorial_pack_granted(wallet):
        return {"granted": False}

    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    inventory = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
    gift_items: list[dict] = []
    gift_fallbacks = {
        "wy_d_001": ("初级治愈药剂", {"hp_restore": 30, "label": "恢复 30 HP"}),
        "wy_d_002": ("初级精神药剂", {"san_restore": 30, "label": "恢复 30 SAN"}),
    }
    gift_defs = [
        _catalog_item_definition(item_id, gift_fallbacks[item_id][0], gift_fallbacks[item_id][1])
        for item_id in _WENYOU_TUTORIAL_GIFT_ITEM_IDS
    ]
    for definition in gift_defs:
        item = _new_inventory_item(definition, "newbie_starter_pack", "newbie-gift")
        inventory = _add_inventory_item(inventory, item)
        gift_items.append(item)

    players_changed: dict[str, dict[str, Any]] = {}
    for pid in ("player1", "player2"):
        player = st.get(pid) if isinstance(st.get(pid), dict) else None
        if not player:
            continue
        before = int(player.get("unspent_attribute_points") or 0)
        player["unspent_attribute_points"] = before + _WENYOU_TUTORIAL_ATTRIBUTE_POINTS
        if not _normalize_core_ability(player.get("core_ability")):
            player["core_ability"] = _core_ability_from_tutorial(session, pid)
            player["core_ability_profile"] = _core_ability_profile_from_tutorial(session, pid, player["core_ability"])
        st[pid] = player
        players_changed[pid] = {
            "unspent_attribute_points_delta": _WENYOU_TUTORIAL_ATTRIBUTE_POINTS,
            "unspent_attribute_points": player["unspent_attribute_points"],
            "core_ability": player.get("core_ability"),
            "core_ability_profile": player.get("core_ability_profile"),
        }

    st["inventory"] = inventory[:80]
    session["stats"] = st
    wallet["inventory"] = inventory[:80]
    wallet["newbie_starter_pack_granted"] = True
    wallet["newbie_starter_pack_granted_at"] = now_beijing_iso()
    wallet["ledger"] = (wallet.get("ledger") or [])[-79:] + [
        {
            "at": wallet["newbie_starter_pack_granted_at"],
            "type": "newbie_starter_pack",
            "gameId": str(session.get("gameId") or ""),
            "items": [str(item.get("id") or "") for item in gift_items],
            "attribute_points_delta": _WENYOU_TUTORIAL_ATTRIBUTE_POINTS,
            "core_abilities": {pid: data.get("core_ability") for pid, data in players_changed.items()},
            "core_ability_profiles": {pid: data.get("core_ability_profile") for pid, data in players_changed.items()},
        }
    ]

    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"newbie_pack_{len(event_log) + 1:03d}",
        "source": "rules_engine.newbie_starter_pack",
        "changes": {
            "inventory_add": gift_items,
            "players": players_changed,
            "wallet": {"newbie_starter_pack_granted": True},
        },
        "created_at": now_beijing_iso(),
    }
    event_log.append(patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = patch
    return {
        "granted": True,
        "items": gift_items,
        "attribute_points": _WENYOU_TUTORIAL_ATTRIBUTE_POINTS,
        "players": players_changed,
        "granted_at": wallet["newbie_starter_pack_granted_at"],
    }


def _grant_settlement_reward(user_id: int, session: dict, result: str = "", rating: str = "") -> dict:
    existing = session.get("settlement") if isinstance(session.get("settlement"), dict) else {}
    if existing.get("reward_granted"):
        return existing
    preview = _build_settlement_preview(session, result=result, rating=rating)
    result = str(preview.get("result") or "standard_clear")
    rating = str(preview.get("rating") or _normalize_rating("", result))
    settlement = dict(preview.get("reward") or _calculate_settlement_reward(session, result, rating))
    wallet = _load_wenyou_wallet(user_id, session)
    forced_result = _apply_forced_instance_settlement(wallet, session, settlement, result)
    debt_before = max(0, int(wallet.get("debts") or 0))
    gross_points = int(settlement.get("gross_points") or 0)
    penalty = int(settlement.get("penalty_points") or 0)
    available_for_debt = max(0, gross_points - penalty)
    debt_repay_cap = math.floor(available_for_debt * 0.8) if debt_before > 0 else 0
    debt_repaid = min(debt_before, debt_repay_cap)
    final_points = max(0, available_for_debt - debt_repaid)
    new_debt = max(0, penalty - gross_points)
    wallet["points"] = max(0, int(wallet.get("points") or 0)) + final_points
    wallet["debts"] = max(0, debt_before - debt_repaid + new_debt)
    wallet["total_exp"] = max(0, int(wallet.get("total_exp") or 0)) + int(settlement.get("gross_exp") or 0)
    wallet["settlement_count"] = max(0, int(wallet.get("settlement_count") or 0)) + 1
    reward_grants = _roll_settlement_rewards(user_id, session, settlement)
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    if reward_grants:
        inventory = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
        for grant in reward_grants:
            item = grant.get("item") if isinstance(grant, dict) else None
            if isinstance(item, dict):
                inventory = _add_inventory_item(inventory, item)
        wallet["inventory"] = inventory[:80]
        st["inventory"] = inventory[:80]
        session["stats"] = st
    ledger_entry = {
        "at": now_beijing_iso(),
        "gameId": str(session.get("gameId") or ""),
        "difficulty": str(settlement.get("difficulty") or ""),
        "result": result,
        "rating": rating,
        "points_delta": final_points,
        "exp_delta": int(settlement.get("gross_exp") or 0),
        "debt_repaid": debt_repaid,
        "debts": wallet["debts"],
        "reward_items": [str((grant.get("item") or {}).get("id") or "") for grant in reward_grants if isinstance(grant, dict)],
    }
    wallet["ledger"] = (wallet.get("ledger") or [])[-79:] + [ledger_entry]
    wallet["settlement_history"] = (wallet.get("settlement_history") or [])[-11:] + [
        {
            "at": ledger_entry["at"],
            "gameId": ledger_entry["gameId"],
            "difficulty": str(settlement.get("difficulty") or ""),
            "result": result,
            "rating": rating,
        }
    ]
    if result == "standard_clear":
        clear_record = {
            "at": ledger_entry["at"],
            "gameId": ledger_entry["gameId"],
            "difficulty": str(settlement.get("difficulty") or ""),
            "rating": rating,
            "result": result,
        }
        wallet["clear_records"] = (wallet.get("clear_records") or [])[-29:] + [clear_record]
    _refresh_forced_instance_queue(wallet, session)
    _save_wenyou_wallet(user_id, wallet)
    _sync_session_points_with_wallet(session, wallet)

    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    level_changes: dict[str, Any] = {}
    for pk in ("player1", "player2"):
        player = st.get(pk) if isinstance(st.get(pk), dict) else _default_player_stats()
        level_changes[pk] = _grant_player_exp(player, int(settlement.get("gross_exp") or 0))
        st[pk] = player
    session["stats"] = st
    newbie_pack = _grant_newbie_starter_pack(session, wallet, result)
    if _is_tutorial_session(session):
        wallet["tutorial_completed"] = True
        wallet["tutorial_completed_at"] = str(wallet.get("tutorial_completed_at") or now_beijing_iso())
        wallet["tutorial_completion_result"] = result
    st = session.get("stats") if isinstance(session.get("stats"), dict) else st
    existing_players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    merged_players: dict[str, dict[str, Any]] = {}
    for pid in ("player1", "player2"):
        player = copy.deepcopy(st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats())
        existing_player = existing_players.get(pid) if isinstance(existing_players.get(pid), dict) else {}
        if existing_player.get("display_name"):
            player["display_name"] = existing_player.get("display_name")
        if existing_player.get("display_name_set"):
            player["display_name_set"] = True
            if existing_player.get("display_name_set_at"):
                player["display_name_set_at"] = existing_player.get("display_name_set_at")
        player.setdefault("controller", _WENYOU_PLAYER_CONTROLLERS.get(pid, "human"))
        merged_players[pid] = player
    wallet["players"] = merged_players
    _save_wenyou_wallet(user_id, wallet)
    _sync_session_points_with_wallet(session, wallet)

    settlement.update(
        {
            "result_label": preview.get("result_label") or settlement.get("result_label"),
            "rating_label": preview.get("rating_label") or _WENYOU_RATING_LABELS.get(rating, rating),
            "rating_score": int(preview.get("rating_score") or 0),
            "rating_source": preview.get("rating_source") or "score",
            "confidence": preview.get("confidence") or "",
            "reason": preview.get("reason") or "",
            "score_breakdown": preview.get("score_breakdown") or [],
            "reward_granted": True,
            "points_delta": final_points,
            "exp_delta": int(settlement.get("gross_exp") or 0),
            "reward_items": reward_grants,
            "newbie_starter_pack": newbie_pack if newbie_pack.get("granted") else None,
            "forced_instance_result": forced_result or None,
            "debt_before": debt_before,
            "debt_repaid": debt_repaid,
            "debt_after": int(wallet.get("debts") or 0),
            "wallet_points": int(wallet.get("points") or 0),
            "level_changes": level_changes,
            "granted_at": now_beijing_iso(),
        }
    )
    session["settlement"] = settlement
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"settlement_{len(event_log) + 1:03d}",
        "source": "rules_engine.settlement",
        "changes": {
            "wallet": {"points_delta": final_points, "debt_repaid": debt_repaid, "debts": settlement["debt_after"]},
            "inventory_add": [grant.get("item") for grant in reward_grants if isinstance(grant, dict) and isinstance(grant.get("item"), dict)],
            "forced_instance_result": forced_result or None,
            "players": {
                "player1": {"exp_delta": settlement["exp_delta"], **level_changes.get("player1", {})},
                "player2": {"exp_delta": settlement["exp_delta"], **level_changes.get("player2", {})},
            },
            "rewards": reward_grants,
            "newbie_starter_pack": newbie_pack if newbie_pack.get("granted") else None,
        },
        "created_at": now_beijing_iso(),
    }
    event_log.append(patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = patch
    return settlement


def get_settlement_preview(user_id: int, result: str = "", rating: str = "") -> dict:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return {"active": False, "session": None, "preview": None, "options": {"results": _WENYOU_RESULT_OPTIONS, "ratings": _WENYOU_RATING_OPTIONS}}
    _session_ensure_stats(session)
    phase = _session_phase(session)
    existing = session.get("settlement") if isinstance(session.get("settlement"), dict) else None
    if existing and existing.get("reward_granted"):
        preview = {
            "result": existing.get("result"),
            "result_label": existing.get("result_label"),
            "rating": existing.get("rating"),
            "rating_label": existing.get("rating_label") or _WENYOU_RATING_LABELS.get(str(existing.get("rating") or ""), str(existing.get("rating") or "")),
            "rating_score": int(existing.get("rating_score") or 0),
            "rating_source": existing.get("rating_source") or "granted",
            "confidence": existing.get("confidence") or "granted",
            "reason": existing.get("reason") or "奖励已发放。",
            "score_breakdown": existing.get("score_breakdown") or [],
            "reward": existing,
            "options": {"results": _WENYOU_RESULT_OPTIONS, "ratings": _WENYOU_RATING_OPTIONS},
        }
    else:
        preview = _build_settlement_preview(session, result=result, rating=rating)
    return {
        "active": True,
        "phase": phase,
        "phase_label": _phase_label(phase),
        "session": get_session_view(uid).get("session"),
        "preview": preview,
        "options": {"results": _WENYOU_RESULT_OPTIONS, "ratings": _WENYOU_RATING_OPTIONS},
    }


def _format_settlement_summary(settlement: dict) -> str:
    if not settlement:
        return "暂无结算记录。"
    lines = [
        f"【结算】{settlement.get('result_label') or settlement.get('result')}｜评级 {settlement.get('rating_label') or settlement.get('rating') or '-'}",
        f"积分 +{settlement.get('points_delta', 0)}（入账后 {settlement.get('wallet_points', 0)}）｜EXP +{settlement.get('exp_delta', 0)}",
    ]
    if settlement.get("rating_score") is not None:
        lines.append(f"评级分：{settlement.get('rating_score', 0)}")
    if int(settlement.get("debt_repaid") or 0) or int(settlement.get("debt_after") or 0):
        lines.append(f"债务偿还 {settlement.get('debt_repaid', 0)}｜剩余 {settlement.get('debt_after', 0)}")
    rolls = int(settlement.get("reward_rolls") or 0)
    if rolls:
        rewards = settlement.get("reward_items") if isinstance(settlement.get("reward_items"), list) else []
        if rewards:
            names = []
            for grant in rewards[:4]:
                item = grant.get("item") if isinstance(grant, dict) else {}
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item.get("name")))
            suffix = "、".join(names) if names else "已入背包"
            lines.append(f"基础奖励：{rolls} 次｜{suffix}")
        else:
            lines.append(f"基础奖励次数：{rolls} 次")
    pack = settlement.get("newbie_starter_pack") if isinstance(settlement.get("newbie_starter_pack"), dict) else None
    if pack and pack.get("granted"):
        item_names = [
            str(item.get("name") or "")
            for item in (pack.get("items") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        suffix = "、".join(item_names) if item_names else "新手补给"
        lines.append(f"新手礼包：{suffix}｜自由属性点 +{int(pack.get('attribute_points') or 0)}")
    return "\n".join(lines)


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
    req = item.get("requirements") if isinstance(item.get("requirements"), dict) else {}
    if not req:
        return None
    rank = _normalize_difficulty(player.get("rank") or "D")
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


def _apply_item_use_cost(session: dict, player: dict, item: dict) -> tuple[list[str], dict[str, Any]]:
    cost = item.get("use_cost") if isinstance(item.get("use_cost"), dict) else {}
    if not cost:
        return [], {"hp_delta": 0, "san_delta": 0, "spi_delta": 0, "conditions_add": [], "clock_updates": [], "debt_delta": 0}
    notes: list[str] = []
    changes: dict[str, Any] = {"hp_delta": 0, "san_delta": 0, "spi_delta": 0, "conditions_add": [], "clock_updates": [], "debt_delta": 0}
    hp_cost = int(cost.get("hp") or 0)
    san_cost = int(cost.get("san") or 0)
    spi_cost = int(cost.get("spi_current") or 0)
    if cost.get("hp_delta") is not None:
        hp_cost = max(hp_cost, abs(min(0, int(cost.get("hp_delta") or 0))))
    if cost.get("san_delta") is not None:
        san_cost = max(san_cost, abs(min(0, int(cost.get("san_delta") or 0))))
    if hp_cost:
        before = int(player.get("hp") or 0)
        player["hp"] = max(0, before - hp_cost)
        changes["hp_delta"] += int(player.get("hp") or 0) - before
        notes.append(f"HP -{hp_cost}")
    if san_cost:
        before = int(player.get("san") or 0)
        player["san"] = max(0, before - san_cost)
        changes["san_delta"] += int(player.get("san") or 0) - before
        changes["spi_delta"] += _apply_san_delta_to_spi(player, int(player.get("san") or 0) - before)
        notes.append(f"SAN -{san_cost}")
    if spi_cost:
        before = int(player.get("spi_current") or 0)
        player["spi_current"] = max(0, before - spi_cost)
        changes["spi_delta"] += int(player.get("spi_current") or 0) - before
        notes.append(f"精神力 -{spi_cost}")
    for cond_key, cond_name in (("exposure", "暴露"), ("fatigue", "疲劳"), ("pollution", "轻度污染")):
        amount = int(cost.get(cond_key) or 0)
        if amount:
            for _ in range(min(3, amount)):
                _add_condition_unique(player, cond_name)
            changes["conditions_add"].append(cond_name)
            notes.append(f"{cond_name} +{amount}")
    pollution_delta = int(cost.get("pollution_delta") or 0)
    if pollution_delta:
        before_pollution = int(player.get("pollution") or 0)
        player["pollution"] = max(0, min(999, before_pollution + pollution_delta))
        if pollution_delta > 0:
            _add_condition_unique(player, "污染")
            changes["conditions_add"].append("污染")
        notes.append(f"污染 {pollution_delta:+d}")
    threat_delta = int(cost.get("threat_clock_delta") or cost.get("threat_clock") or 0)
    if threat_delta:
        updates = _apply_clock_updates(
            session,
            [{"id": "threat", "name": "威胁时钟", "delta": threat_delta, "max": 6}],
        )
        changes["clock_updates"].extend(updates)
        notes.append("威胁时钟推进")
    debt_delta = int(cost.get("debt_delta") or cost.get("debt") or 0)
    if debt_delta:
        changes["debt_delta"] = max(0, debt_delta)
        notes.append(f"债务 +{changes['debt_delta']}")
    return notes, changes


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


def _apply_item_effect_to_session(session: dict, item: dict, detail: str = "", player_id: Any = "player1", target_id: Any = None) -> tuple[bool, str, Optional[dict]]:
    _session_ensure_stats(session)
    pid = _resolve_player_key(player_id)
    target_pid = _resolve_player_key(target_id or pid)
    if item.get("sealed"):
        return False, f"文游：【{_inventory_item_name(item)}】还处于封印状态，不能使用。", None
    if not _item_allowed_in_phase(item, session):
        return False, f"文游：【{_inventory_item_name(item)}】当前阶段不能使用。", None

    st = session["stats"]
    player = st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats()
    _recalc_player_caps(player)
    req_error = _check_item_requirements(session, item, player)
    if req_error:
        return False, f"文游：【{_inventory_item_name(item)}】{req_error}", None
    category = str(item.get("category") or item.get("item_type") or "consumable").strip()
    if category in {"ability", "evolution"}:
        return False, "文游：当前规则不再通过背包绑定额外成长；核心能力只在新手副本通关后按表现生成。", None
    if category in {"fragment", "material"}:
        return False, f"文游：【{_inventory_item_name(item)}】需要在成长或兑换流程中处理，不能当作局内消耗品直接使用。", None

    if target_pid != pid:
        effect_json = item.get("effect_json") if isinstance(item.get("effect_json"), dict) else {}
        target_mode = str(effect_json.get("target") or item.get("target") or "").strip().lower()
        helpful = any(k in str(item.get("category") or item.get("item_type") or "") for k in ("heal", "support")) or any(
            x in _inventory_item_name(item) + str(item.get("desc") or "") for x in ("治疗", "治愈", "精神", "保护", "辅助", "药剂")
        )
        if target_mode not in {"ally", "player", "any", "other"} and not helpful:
            return False, f"文游：【{_inventory_item_name(item)}】不能对其他玩家使用。", None
        player = st.get(target_pid) if isinstance(st.get(target_pid), dict) else _default_player_stats()
        _recalc_player_caps(player)

    before = {"hp": int(player.get("hp") or 0), "san": int(player.get("san") or 0), "conditions": list(player.get("conditions") or [])}
    cost_notes, cost_changes = _apply_item_use_cost(session, player, item)
    effect = _item_effect_for(item)
    hp_delta = _adjust_player_stat(player, "hp", int(effect.get("hp") or 0)) if effect.get("hp") else 0
    san_delta = _adjust_player_stat(player, "san", int(effect.get("san") or 0)) if effect.get("san") else 0
    if effect.get("hp_full"):
        hp_delta += _adjust_player_stat(player, "hp", max(0, int(player.get("hp_max") or 0)))
    if effect.get("san_full"):
        san_delta += _adjust_player_stat(player, "san", max(0, int(player.get("san_max") or 0)))
    spi_delta = _apply_san_delta_to_spi(player, san_delta, mental_recovery=bool(effect.get("mental_recovery")))
    _recalc_player_caps(player)
    removed = _remove_first_condition(player, list(effect.get("remove") or []))
    removed.extend(x for x in _clear_recovered_threshold_conditions(player) if x not in removed)
    added: list[str] = []
    condition = str(effect.get("condition") or "").strip()
    if condition:
        _add_condition_unique(player, condition)
        added.append(condition)
    for condition_add in effect.get("conditions_add") or []:
        cond = str(condition_add or "").strip()
        if cond:
            _add_condition_unique(player, cond)
            added.append(cond)
    pollution_delta = int(effect.get("pollution_delta") or 0)
    if pollution_delta:
        before_pollution = int(player.get("pollution") or 0)
        player["pollution"] = max(0, min(999, before_pollution + pollution_delta))
        if pollution_delta > 0:
            _add_condition_unique(player, "污染")
            added.append("污染")
    threshold_add = _apply_threshold_conditions(player)
    st[target_pid] = player
    session["stats"] = st
    clock_inputs = []
    if isinstance(effect.get("clock"), dict):
        clock_inputs.append(effect["clock"])
    if isinstance(effect.get("clock_updates"), list):
        clock_inputs.extend(effect.get("clock_updates") or [])
    clock_updates = _apply_clock_updates(session, clock_inputs) if clock_inputs else []
    flags_set: dict[str, Any] = {}
    if effect.get("safe_rest_node"):
        flags = session.get("flags") if isinstance(session.get("flags"), dict) else {}
        flags["safe_rest_node"] = True
        flags["safe_rest_node_at"] = now_beijing_iso()
        session["flags"] = flags
        flags_set["safe_rest_node"] = True
    clue_updates: dict[str, Any] = {}
    if effect.get("public_clue"):
        synthetic = {"clue_updates": [str(effect.get("public_clue") or "")], "state_proposals": []}
        clue_updates = {
            "public": _apply_public_state_updates(session, synthetic),
            "rules": _apply_rules_state_updates(session, synthetic),
        }

    parts = [str(effect.get("label") or "效果已生效")]
    if hp_delta:
        parts.append(f"HP {hp_delta:+d}（{player.get('hp')}/{player.get('hp_max')}）")
    if san_delta:
        parts.append(f"SAN {san_delta:+d}（{player.get('san')}/{player.get('san_max')}）")
    if spi_delta:
        parts.append(f"精神力 {spi_delta:+d}（{player.get('spi_current')}/{player.get('spi_max')}）")
    if removed:
        parts.append("移除状态：" + "、".join(removed))
    if added:
        parts.append("新增状态：" + "、".join(added))
    if clock_updates:
        parts.extend(f"{x.get('name') or x.get('id')} {x.get('value')}/{x.get('max')}" for x in clock_updates)
    if pollution_delta:
        parts.append(f"污染 {pollution_delta:+d}（{player.get('pollution', 0)}）")
    if flags_set.get("safe_rest_node"):
        parts.append("已建立安全休整节点")
    if effect.get("public_clue"):
        parts.append("线索已写入缓存")
    if cost_notes:
        parts.append("代价：" + "、".join(cost_notes))
    if detail:
        parts.append(f"使用意图：{detail[:160]}")
    result_text = "；".join(parts)
    inventory_update = _item_inventory_update_after_use(item)
    if inventory_update:
        item["_inventory_update"] = inventory_update
    will_consume = item.get("consume") is not False and not item.get("_use_keep")
    changes = {
        "players": {
            target_pid: {
                "hp_delta": int(player.get("hp") or 0) - before["hp"],
                "san_delta": int(player.get("san") or 0) - before["san"],
                "spi_delta": spi_delta + int(cost_changes.get("spi_delta") or 0),
                "conditions_add": list(dict.fromkeys(added + threshold_add + list(cost_changes.get("conditions_add") or []))),
                "conditions_remove": removed,
            }
        },
        "inventory_add": [],
        "inventory_remove": [dict(item, quantity=1)] if will_consume else [],
        "inventory_update": dict(inventory_update),
        "clock_updates": list(cost_changes.get("clock_updates") or []) + clock_updates,
        "flags_set": flags_set,
        "clue_updates": clue_updates,
        "wallet": {"debt_delta": int(cost_changes.get("debt_delta") or 0) + int(effect.get("debt_delta") or 0)}
        if int(cost_changes.get("debt_delta") or 0) + int(effect.get("debt_delta") or 0)
        else {},
    }
    return True, result_text, changes


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

def _wallet_stats_from_wallet(wallet: dict) -> dict:
    _ensure_wallet_player_maps(wallet)
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    inventories = wallet.get("inventories") if isinstance(wallet.get("inventories"), dict) else {}
    wallets = wallet.get("wallets") if isinstance(wallet.get("wallets"), dict) else {}
    st = {
        "phase": "hub",
        "points": max(0, int(wallet.get("points") or 0)),
        "inventory": _normalize_inventory(inventories.get("player1") or wallet.get("inventory"), source="wallet"),
        "inventories": {
            "player1": _normalize_inventory(inventories.get("player1"), source="wallet"),
            "player2": _normalize_inventory(inventories.get("player2"), source="wallet"),
            "task_items": _normalize_inventory(inventories.get("task_items"), source="wallet"),
        },
        "wallets": copy.deepcopy(wallets),
    }
    base = _default_player_stats()
    for pid in ("player1", "player2"):
        cur = players.get(pid) if isinstance(players.get(pid), dict) else {}
        player = dict(base)
        player.update(copy.deepcopy(cur))
        player.setdefault("display_name", _WENYOU_PLAYER_LABELS.get(pid, pid))
        player.setdefault("controller", _WENYOU_PLAYER_CONTROLLERS.get(pid, "human"))
        _normalize_player_growth_fields(player)
        player["conditions"] = _normalize_text_list(player.get("conditions"))
        _recalc_player_caps(player)
        st[pid] = player
    return st


def _load_inventory_action_context(uid: int) -> tuple[bool, dict, dict, dict, list[dict]]:
    session = r2_store.get_wenyou_session(uid)
    active = bool(session and isinstance(session, dict) and session.get("gameId"))
    wallet = _load_wenyou_wallet(uid, session if active else None)
    if active:
        _session_ensure_stats(session)
        st = session["stats"]
        inventory = _inventory_for_player_action(wallet, st, "player1", active=True)
        return True, session, wallet, st, inventory
    st = _wallet_stats_from_wallet(wallet)
    session_ctx = {"phase": "hub", "stats": st, "flags": {}}
    return False, session_ctx, wallet, st, list(st.get("inventory") or [])


def _merge_inventory_preferring_runtime(wallet_inventory: Any, runtime_inventory: Any) -> list[dict]:
    runtime = _normalize_inventory(runtime_inventory, source="session")
    wallet_items = _normalize_inventory(wallet_inventory, source="wallet")
    if not runtime:
        return wallet_items[:80]
    out = list(runtime)
    for item in wallet_items:
        if _inventory_has_item(out, item_id=str(item.get("id") or ""), name=_inventory_item_name(item)):
            continue
        out.append(item)
    return out[:80]


def _inventory_for_player_action(wallet: dict, st: dict, player_id: Any, active: bool) -> list[dict]:
    pid = _resolve_player_key(player_id)
    wallet_inventory = _get_player_inventory(wallet, pid)
    if not active:
        return wallet_inventory[:80]
    runtime_inventory = _normalize_inventory(st.get("inventory"), source="session")
    if pid != "player1":
        runtime_inventory = [x for x in runtime_inventory if str(x.get("holder_id") or "") == pid]
    return _merge_inventory_preferring_runtime(wallet_inventory, runtime_inventory)


def _persist_player_inventory_for_action(wallet: dict, st: dict, player_id: Any, inventory: list[dict]) -> None:
    pid = _resolve_player_key(player_id)
    normalized = _set_player_inventory(wallet, pid, inventory)
    if pid == "player1":
        st["inventory"] = normalized[:80]


def _inventory_action_view(uid: int, active: bool) -> dict:
    return get_session_view(uid) if active else get_shop_view(uid)


def _persist_wallet_inventory_result(user_id: int, wallet: dict, st: dict, source: str, changes: dict) -> dict:
    wallet["inventory"] = _normalize_inventory(st.get("inventory"), source="wallet")[:80]
    wallet["players"] = {
        "player1": copy.deepcopy(st.get("player1") if isinstance(st.get("player1"), dict) else _default_player_stats()),
        "player2": copy.deepcopy(st.get("player2") if isinstance(st.get("player2"), dict) else _default_player_stats()),
    }
    _save_wenyou_wallet(int(user_id), wallet)
    view = get_shop_view(int(user_id))
    view["state_patch"] = {
        "round_id": f"{source.split('.')[-1]}_wallet",
        "source": source,
        "changes": changes,
        "created_at": now_beijing_iso(),
    }
    return view


def _persist_inventory_rule_result(user_id: int, session: dict, wallet: dict, source: str, changes: dict) -> dict:
    _sync_session_points_with_wallet(session, wallet)
    patch = _append_rules_patch(session, source, changes)
    _save_wenyou_wallet(int(user_id), wallet)
    r2_store.save_wenyou_session(int(user_id), session)
    view = get_session_view(int(user_id))
    view["state_patch"] = patch
    return view


def sell_inventory_item(user_id: int, item_ref: str, player_id: Any = "player1") -> tuple[bool, str, dict]:
    uid = int(user_id)
    pid = _resolve_player_key(player_id)
    active, session, wallet, st, _ = _load_inventory_action_context(uid)
    inventory = _inventory_for_player_action(wallet, st, pid, active)
    item = _inventory_find_by_name(inventory, item_ref)
    if not item:
        return False, f"背包里没有【{item_ref}】。", _inventory_action_view(uid, active)
    locked = _item_locked_for_recycle(item)
    if locked:
        return False, locked, _inventory_action_view(uid, active)
    rarity = _normalize_difficulty(item.get("rarity") or "D")
    value = max(1, math.floor(_item_reference_price(item) * float(_WENYOU_SELL_RATIO.get(rarity, 0.25))))
    inventory, consumed = _consume_inventory_item(inventory, item, force_remove=True)
    if not consumed:
        return False, f"背包里没有【{item_ref}】。", _inventory_action_view(uid, active)
    account = _player_account(wallet, pid)
    _set_actor_points(wallet, pid, max(0, int(account.get("points") or 0) + value))
    _persist_player_inventory_for_action(wallet, st, pid, inventory[:80])
    append_player_ledger(wallet, pid, {"type": "item_sell", "item_name": _inventory_item_name(item), "points_delta": value})
    changes = {"wallets": {pid: {"points_delta": value}}, "wallet": {"points_delta": value} if pid == "player1" else {}, "inventory_remove": {pid: [consumed]}}
    if active:
        session["stats"] = st
        view = _persist_inventory_rule_result(uid, session, wallet, "rules_engine.sell_item", changes)
    else:
        view = _persist_wallet_inventory_result(uid, wallet, st, "rules_engine.sell_item", changes)
    return True, f"已回收【{_inventory_item_name(item)}】，获得 {value} 主神积分。", view


def _ability_definition(ability_ref: str) -> Optional[dict[str, Any]]:
    ref = str(ability_ref or "").strip()
    if not ref:
        return None
    slug = _slug_id(ref)
    if slug in _WENYOU_ABILITY_CATALOG:
        return dict(_WENYOU_ABILITY_CATALOG[slug])
    for item in _WENYOU_ABILITY_CATALOG.values():
        if ref == str(item.get("name") or ""):
            return dict(item)
    return None


def _find_player_ability(player: dict, ability_ref: str) -> Optional[dict]:
    ref = str(ability_ref or "").strip()
    slug = _slug_id(ref)
    ability = _normalize_core_ability(player.get("core_ability"))
    if ability and (str(ability.get("id") or "") == slug or str(ability.get("name") or "") == ref):
        return ability
    return None


def use_player_ability(user_id: int, ability_ref: str, player_id: Any = "player1", detail: str = "") -> tuple[bool, str, dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "当前没有可使用能力的文游存档。", get_session_view(uid)
    _session_ensure_stats(session)
    pid = _resolve_player_key(player_id)
    wallet = _load_wenyou_wallet(uid, session)
    st = session["stats"]
    player = st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats()
    _recalc_player_caps(player)
    ability = _find_player_ability(player, ability_ref)
    if not ability:
        return False, "还没有核心能力；新手副本标准通关后会按表现生成。", get_session_view(uid)
    ability_id = str(ability.get("id") or _slug_id(ability.get("name")))
    rank = _normalize_difficulty(player.get("rank") or "D")
    rarity = _normalize_difficulty(ability.get("rarity") or "D")
    if _rarity_rank(rank) < _rarity_rank(rarity):
        return False, f"能力【{ability.get('name')}】仍处于封印状态，需要 {rarity} 阶。", get_session_view(uid)
    ability_uses = session.get("ability_uses") if isinstance(session.get("ability_uses"), dict) else {}
    use_key = f"{pid}:{ability_id}"
    used = max(0, int(ability_uses.get(use_key) or 0))
    max_uses = max(1, int(ability.get("uses_per_instance") or 1))
    if used >= max_uses and _session_phase(session) == "instance_running":
        return False, "该能力本副本次数已用完。", get_session_view(uid)
    level = max(1, int(ability.get("level") or 1))
    hp_before = int(player.get("hp") or 0)
    san_before = int(player.get("san") or 0)
    changes: dict[str, Any] = {"players": {pid: {}}, "clock_updates": [], "flags_set": {}}
    notes: list[str] = []
    if ability_id == "core_protect":
        san_delta = _adjust_player_stat(player, "san", -5)
        _apply_san_delta_to_spi(player, san_delta)
        _add_condition_unique(player, "代偿护手：抵消下一次 15 点 HP 伤害")
        notes.append(f"代偿护手已登记，SAN {san_delta:+d}")
    elif ability_id == "core_resilience":
        removed = _remove_first_condition(player, ["动摇", "污染"] if level >= 4 else ["动摇"])
        if int(player.get("san") or 0) * 2 < int(player.get("san_max") or 1):
            player["spi_current"] = min(int(player.get("spi_max") or 0), int(player.get("spi_current") or 0) + 1)
        notes.append("移除状态：" + "、".join(removed) if removed else "残响锚点已登记：抵消一次动摇或轻度污染")
    else:
        condition = {
            "core_observe": "异常余光：下次观察获得一处被忽略的异常提示",
            "core_escape": "退路直觉：下一次逃离、规避或脱身判定 +3",
            "core_combat": "破局冲击：下一次破坏、压制或强行突破判定 +3",
            "core_social": "人群伪装：下一次社交、伪装或混入人群判定 +3",
            "core_rule": "规则嗅觉：可验证一条低级规则是否立刻危险",
            "core_survival": "求生本能：下一次险境行动前获得保守提示或降低一级低级风险",
        }.get(ability_id, f"{ability.get('name')}：效果已登记")
        if ability_id in {"core_observe", "core_rule"}:
            san_delta = _adjust_player_stat(player, "san", -5)
            _apply_san_delta_to_spi(player, san_delta)
            notes.append(f"SAN {san_delta:+d}")
        elif ability_id == "core_combat":
            hp_delta = _adjust_player_stat(player, "hp", -5)
            notes.append(f"HP {hp_delta:+d}")
        _add_condition_unique(player, condition)
        notes.append(condition)
    ability_uses[use_key] = used + 1
    session["ability_uses"] = ability_uses
    _recalc_player_caps(player)
    st[pid] = player
    session["stats"] = st
    changes["players"][pid].update(
        {
            "ability_used": {"id": ability_id, "name": ability.get("name"), "level": level, "detail": str(detail or "")[:160]},
            "core_ability_used": {"id": ability_id, "name": ability.get("name"), "detail": str(detail or "")[:160]},
            "hp_delta": int(player.get("hp") or 0) - hp_before,
            "san_delta": int(player.get("san") or 0) - san_before,
            "conditions": list(player.get("conditions") or []),
        }
    )
    view = _persist_inventory_rule_result(uid, session, wallet, "rules_engine.use_ability", changes)
    return True, f"核心能力【{ability.get('name')}】已使用：" + "；".join(notes), view


def _weighted_pick(options: list[tuple[str, float]], rng: random.Random, fallback: str = "D") -> str:
    if not options:
        return fallback
    total = sum(max(0.0, float(weight or 0.0)) for _, weight in options)
    if total <= 0:
        return options[0][0]
    roll = rng.random() * total
    acc = 0.0
    for value, weight in options:
        acc += max(0.0, float(weight or 0.0))
        if roll <= acc:
            return value
    return options[-1][0]


def _shift_rarity(rarity: str, delta: int) -> str:
    ranks = list(_WENYOU_RANK_ORDER)
    try:
        idx = ranks.index(_normalize_difficulty(rarity))
    except ValueError:
        idx = 0
    return ranks[max(0, min(len(ranks) - 1, idx + int(delta or 0)))]


def _instance_item_grant_cap(session: dict) -> str:
    fw = _framework_for_runtime(session.get("framework") or {})
    difficulty = _normalize_difficulty(fw.get("difficulty") or "D")
    # 常规局内掉落最多比副本难度高 1 阶：D 本最多 C，避免 GM 把隐藏奖励写穿。
    return _shift_rarity(difficulty, 1)


def _resolve_catalog_item_for_proposal(proposal: dict, session: dict) -> Optional[dict[str, Any]]:
    if not isinstance(proposal, dict):
        return None
    raw_key = str(proposal.get("id") or proposal.get("name") or "").strip()
    if not raw_key:
        return None
    item = _ITEM_CATALOG_BY_ID.get(_slug_id(raw_key)) or _ITEM_CATALOG_BY_ID.get(raw_key) or _ITEM_CATALOG_BY_NAME.get(raw_key)
    if not item:
        return None
    cap = _instance_item_grant_cap(session)
    if _rarity_rank(item.get("rarity")) > _rarity_rank(cap):
        return None
    prepared = dict(item)
    max_rank = _max_player_rank(session)
    if str(prepared.get("rarity") or "D") in {"A", "S"} and _rarity_rank(prepared.get("rarity")) > _rarity_rank(max_rank):
        prepared["sealed"] = True
        prepared["sealed_reason"] = f"当前最高阶位 {max_rank}，需达到 {prepared.get('rarity')} 阶后解封。"
    return prepared


def _max_player_level(session: dict) -> int:
    _session_ensure_stats(session)
    levels: list[int] = []
    for pk in ("player1", "player2"):
        player = session.get("stats", {}).get(pk)
        if isinstance(player, dict):
            levels.append(max(1, int(player.get("level") or 1)))
    return max(levels or [1])


def _max_player_attr(session: dict, attr: str) -> int:
    _session_ensure_stats(session)
    values: list[int] = []
    aliases = {"int": "int", "wis": "int", "vit": "con", "spi_current": "spi_current"}
    key = aliases.get(attr, attr)
    for pk in ("player1", "player2"):
        player = session.get("stats", {}).get(pk)
        if not isinstance(player, dict):
            continue
        if key == "spi_current":
            values.append(max(0, int(player.get("spi_current") or 0)))
        else:
            values.append(max(0, int(player.get(key) or player.get(attr) or 0)))
    return max(values or [0])


def _item_requirement_blockers(item: dict, session: dict) -> list[str]:
    blockers: list[str] = []
    seal_rank = str(item.get("seal_rank") or "").strip().upper()
    if seal_rank and _rarity_rank(_max_player_rank(session)) < _rarity_rank(seal_rank):
        blockers.append(f"需达到 {seal_rank} 阶")
    req = item.get("requirements") if isinstance(item.get("requirements"), dict) else {}
    level_min = _to_non_negative_int(req.get("level_min"), 0)
    if level_min and _max_player_level(session) < level_min:
        blockers.append(f"需等级 {level_min}")
    for attr in ("str", "con", "agi", "int", "spi", "luk", "spi_current"):
        key = f"{attr}_min"
        needed = _to_non_negative_int(req.get(key), 0)
        if needed and _max_player_attr(session, attr) < needed:
            label = {
                "str": "力量",
                "con": "体质",
                "agi": "敏捷",
                "int": "智力",
                "spi": "精神",
                "luk": "幸运",
                "spi_current": "当前精神力",
            }.get(attr, attr)
            blockers.append(f"需{label} {needed}")
    return blockers


def _seal_item_if_needed(item: dict, session: dict) -> dict:
    prepared = dict(item)
    blockers = _item_requirement_blockers(prepared, session)
    if blockers:
        prepared["sealed"] = True
        prepared["sealed_reason"] = "；".join(blockers[:4])
    return prepared


def _unique_item_for_proposal(proposal: dict, session: dict) -> Optional[dict[str, Any]]:
    if not isinstance(proposal, dict):
        return None
    name = str(proposal.get("name") or proposal.get("id") or "").strip()
    effect = str(proposal.get("effect") or proposal.get("reason") or "").strip()
    if not name or not effect:
        return None
    rarity = _normalize_difficulty(proposal.get("rarity") or "A")
    requirements = proposal.get("requirements") if isinstance(proposal.get("requirements"), dict) else {}
    seal_rank = str(proposal.get("seal_rank") or "").strip().upper()
    if not seal_rank and not requirements and rarity in {"A", "S"}:
        seal_rank = rarity
    item = {
        "id": _slug_id(proposal.get("id") or name, "unique_item"),
        "name": name[:80],
        "kind": str(proposal.get("category") or "唯一奖励").strip()[:40] or "唯一奖励",
        "category": "special",
        "item_type": "special",
        "rarity": rarity,
        "desc": effect[:240],
        "quantity": 1,
        "carry_out": True,
        "temporary": False,
        "quest_item": False,
        "unique": True,
        "stackable": False,
        "consume": False,
        "use_phase": ["hub", "settlement", "instance"],
        "requirements": requirements,
        "seal_rank": seal_rank or None,
        "instance_grant_reason": str(proposal.get("reason") or "")[:180],
    }
    return _seal_item_if_needed(item, session)


def _unique_duplicate_fragment_item(item: dict) -> dict[str, Any]:
    rarity = _normalize_difficulty(item.get("rarity") or "D")
    qty = max(5, int(_GACHA_FRAGMENT_VALUES.get(rarity, 5) * 1.5))
    return {
        "id": f"{item.get('id')}_echo_fragment",
        "name": f"{item.get('name')}回响碎片",
        "kind": "碎片",
        "category": "fragment",
        "item_type": "material",
        "rarity": rarity,
        "quantity": qty,
        "desc": f"重复获得唯一物【{item.get('name')}】后由主神转化。",
        "stackable": True,
        "carry_out": True,
        "converted_from": item.get("id"),
    }


def _task_item_for_proposal(proposal: dict) -> Optional[dict[str, Any]]:
    if not isinstance(proposal, dict):
        return None
    name = str(proposal.get("name") or proposal.get("id") or "").strip()
    if not name:
        return None
    rarity = _normalize_difficulty(proposal.get("rarity") or "D")
    desc = str(proposal.get("effect") or proposal.get("reason") or "副本内任务物品。").strip()
    item_id = _slug_id(proposal.get("id") or name, "task_item")
    return {
        "id": item_id,
        "name": name[:80],
        "kind": str(proposal.get("category") or "任务物品").strip()[:40] or "任务物品",
        "category": "quest",
        "item_type": "quest",
        "rarity": rarity,
        "desc": desc[:240],
        "quantity": max(1, min(3, int(proposal.get("quantity") or 1))),
        "carry_out": False,
        "temporary": True,
        "quest_item": True,
        "stackable": False,
        "use_phase": ["instance"],
        "instance_grant_reason": str(proposal.get("reason") or "")[:180],
    }


def _apply_state_proposal_item_grants(session: dict, proposals: Any) -> list[dict[str, Any]]:
    if not isinstance(proposals, list):
        return []
    _session_ensure_stats(session)
    st = session["stats"]
    inventory = _normalize_inventory(st.get("inventory"), source="session")
    grants: list[dict[str, Any]] = []
    for proposal in proposals[:12]:
        if not isinstance(proposal, dict):
            continue
        ptype = str(proposal.get("type") or "")
        if ptype not in {"acquire_item", "acquire_task_item", "acquire_unique_item"}:
            continue
        if str(proposal.get("visibility") or "hidden") != "public":
            continue
        if ptype == "acquire_task_item":
            item = _task_item_for_proposal(proposal)
        elif ptype == "acquire_unique_item":
            item = _unique_item_for_proposal(proposal, session)
        else:
            item = _resolve_catalog_item_for_proposal(proposal, session)
        if not item:
            continue
        quantity = max(1, min(3, int(proposal.get("quantity") or 1)))
        if ptype == "acquire_unique_item":
            quantity = 1
        elif ptype == "acquire_task_item":
            quantity = int(item.get("quantity") or quantity)
        elif not item.get("stackable"):
            quantity = 1
        if ptype == "acquire_unique_item" and _inventory_has_item(inventory, item_id=str(item.get("id") or "")):
            item = _unique_duplicate_fragment_item(item)
            quantity = int(item.get("quantity") or 1)
            grant_source = "instance_unique_duplicate"
            grant_prefix = "unique-frag"
        else:
            grant_source = "instance_task" if ptype == "acquire_task_item" else "instance_unique" if ptype == "acquire_unique_item" else "instance"
            grant_prefix = "task" if ptype == "acquire_task_item" else "unique" if ptype == "acquire_unique_item" else "instance"
        item_obj = _new_inventory_item(
            item,
            grant_source,
            grant_prefix,
            {
                "quantity": quantity,
                "instance_grant_reason": str(proposal.get("reason") or "")[:180],
            },
        )
        inventory = _add_inventory_item(inventory, item_obj)
        grants.append(item_obj)
        if len(grants) >= 3:
            break
    if grants:
        st["inventory"] = inventory[:80]
        session["stats"] = st
    return grants


def _regular_reward_rarity_cap(difficulty: str) -> str:
    difficulty = _normalize_difficulty(difficulty)
    if difficulty in {"D", "C", "B"}:
        return _shift_rarity(difficulty, 1)
    return "S"


def _cap_reward_rarity(rarity: str, cap: str) -> tuple[str, bool]:
    normalized = _normalize_difficulty(rarity)
    cap = _normalize_difficulty(cap)
    if _rarity_rank(normalized) > _rarity_rank(cap):
        return cap, True
    return normalized, False


def _load_reward_table_config() -> dict[str, Any]:
    global _WENYOU_REWARD_TABLE_CONFIG
    if _WENYOU_REWARD_TABLE_CONFIG is not None:
        return _WENYOU_REWARD_TABLE_CONFIG
    path = Path(BASE_DIR) / "content" / "default" / "reward_tables.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except Exception as exc:
        logger.warning("文游奖励表加载失败 path=%s err=%s", path, exc)
        data = {}
    _WENYOU_REWARD_TABLE_CONFIG = data if isinstance(data, dict) else {}
    return _WENYOU_REWARD_TABLE_CONFIG


def _reward_weight_options(section: str, key: str, fallback: list[tuple[str, float]]) -> list[tuple[str, float]]:
    data = _load_reward_table_config()
    section_data = data.get(section) if isinstance(data.get(section), dict) else {}
    raw = section_data.get(key) if isinstance(section_data, dict) else None
    if not isinstance(raw, list):
        return list(fallback)
    out: list[tuple[str, float]] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("id") or item.get("rarity") or item.get("category") or item.get("name") or "").strip()
            weight = item.get("weight")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name = str(item[0] or "").strip()
            weight = item[1]
        else:
            continue
        try:
            weight_f = float(weight)
        except Exception:
            weight_f = 0.0
        if name and weight_f > 0:
            out.append((name, weight_f))
    return out or list(fallback)


def _reward_category_boosts_from_context(session: dict) -> dict[str, float]:
    rules = _rules_state_from_session(session)
    context = _reward_context_from_raw(rules.get("reward_context"))
    tags = _normalize_text_list(context.get("reward_tags"), 80, 40)
    flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    tags.extend(f"hidden:{x}" for x in _normalize_text_list(flags.get("hidden_endings"), 80, 20))
    config = _load_reward_table_config()
    configured = config.get("tag_category_boosts") if isinstance(config.get("tag_category_boosts"), dict) else {}
    boosts: dict[str, float] = {}

    def add(category: str, amount: float) -> None:
        if not category or amount <= 0:
            return
        boosts[category] = boosts.get(category, 0.0) + amount

    for tag in tags:
        lower = str(tag or "").lower()
        if "monster_sealed" in lower or "boss" in lower:
            add("special", 8.0)
            add("tool_item", 3.0)
        if "monster_defeated" in lower:
            add("tool_item", 8.0)
            add("material", 5.0)
        if "monster_evaded" in lower:
            add("consumable_item", 5.0)
            add("tool_item", 3.0)
        if "hidden" in lower:
            add("special", 8.0)
        for marker, cfg in configured.items():
            if str(marker or "").lower() not in lower or not isinstance(cfg, dict):
                continue
            for category, amount in cfg.items():
                try:
                    add(str(category), float(amount))
                except Exception:
                    continue
    return boosts


def _apply_reward_category_boosts(options: list[tuple[str, float]], boosts: dict[str, float]) -> list[tuple[str, float]]:
    if not boosts:
        return options
    by_category = {name: float(weight or 0.0) for name, weight in options}
    for category, amount in boosts.items():
        by_category[category] = max(0.0, by_category.get(category, 0.0) + float(amount or 0.0))
    return [(name, weight) for name, weight in by_category.items() if weight > 0]


def _reward_catalog_candidates(category: str, rarity: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    catalog: list[dict[str, Any]] = []
    source_catalog = list(_CONTENT_ITEM_CATALOG) + list(_SHOP_CATALOG) + list(_GACHA_CATALOG)
    for raw in source_catalog:
        item = dict(raw)
        iid = str(item.get("id") or item.get("name") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        catalog.append(item)
    same_rarity = [item for item in catalog if str(item.get("rarity") or "D").upper() == rarity]
    if category == "tool_item":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "") == "tool"]
    if category == "consumable_item":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "consumable") == "consumable"]
    if category == "material":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "") == "material"]
    if category == "special":
        return [item for item in same_rarity if str(item.get("item_type") or item.get("category") or "") == "special"]
    return []


def _reward_stack_item(category: str, rarity: str) -> dict[str, Any]:
    if category == "material":
        names = {
            "D": ("anomaly_sample_d", "灰烬样本", 1),
            "C": ("anomaly_sample_c", "异常样本", 1),
            "B": ("anomaly_crystal_b", "异常结晶", 1),
            "A": ("instance_core_shard", "副本核心碎片", 1),
            "S": ("instance_core", "副本核心", 1),
        }
        iid, name, qty = names.get(rarity, names["D"])
        return {
            "id": iid,
            "name": name,
            "kind": "材料",
            "category": "material",
            "rarity": rarity,
            "quantity": qty,
            "desc": "副本结算获得的异常材料，可用于成长、兑换或特殊内容包规则。",
            "stackable": True,
        }
    if category == "tool_item":
        for item in _GACHA_CATALOG:
            if str(item.get("category") or item.get("item_type") or "") == "tool" and _normalize_difficulty(item.get("rarity") or "D") == rarity:
                return dict(item, shop_allowed=False, gacha_allowed=True)
    if category == "consumable_item":
        for item in _GACHA_CATALOG:
            if str(item.get("category") or item.get("item_type") or "") == "consumable" and _normalize_difficulty(item.get("rarity") or "D") == rarity:
                return dict(item, shop_allowed=False, gacha_allowed=True)
    return {
        "id": f"special_record_{rarity.lower()}",
        "name": f"{rarity}级特殊记录",
        "kind": "记录",
        "category": "special",
        "rarity": rarity,
        "quantity": 1,
        "desc": "副本结算留下的特殊记录，可作为后续内容包奖励占位。",
    }


def _roll_settlement_rewards(user_id: int, session: dict, settlement: dict) -> list[dict[str, Any]]:
    rolls = max(0, int(settlement.get("reward_rolls") or 0))
    if rolls <= 0:
        return []
    difficulty = _normalize_difficulty(settlement.get("difficulty") or _framework_for_runtime(session.get("framework") or {}).get("difficulty"))
    rating = str(settlement.get("rating") or "B").upper()
    seed = f"wenyou-reward:{int(user_id)}:{session.get('gameId') or ''}:{difficulty}:{settlement.get('result') or ''}:{rating}:{session.get('startedAt') or ''}"
    rng = random.Random(seed)
    rewards: list[dict[str, Any]] = []
    has_bplus = False
    regular_cap = _regular_reward_rarity_cap(difficulty)
    category_boosts = _reward_category_boosts_from_context(session)
    bonus_bplus_remaining = 0
    if rating == "S":
        bonus_bplus_remaining += 1
    bonus_bplus_remaining += max(0, int(settlement.get("hidden_bonus_rolls") or 0))
    allow_over_cap_bonus = bonus_bplus_remaining > 0
    for index in range(rolls):
        raw_rarity = _weighted_pick(
            _reward_weight_options("rarity_rates", difficulty, _WENYOU_REWARD_RARITY_RATES.get(difficulty, [])),
            rng,
            fallback=difficulty,
        )
        rarity = raw_rarity
        if rating == "S":
            rarity = _shift_rarity(rarity, 1)
        elif rating == "A" and rng.random() < 0.3:
            rarity = _shift_rarity(rarity, 1)
        elif (rating == "C" and rng.random() < 0.3) or rating in {"D", "F"}:
            rarity = _shift_rarity(rarity, -1)
        exceptional_over_cap = False
        if bonus_bplus_remaining > 0 and _rarity_rank(rarity) < _rarity_rank("B"):
            rarity = "B"
            bonus_bplus_remaining -= 1
        capped_rarity, capped = _cap_reward_rarity(rarity, regular_cap)
        if capped:
            if allow_over_cap_bonus and _rarity_rank(rarity) <= _rarity_rank("B") and _rarity_rank(regular_cap) < _rarity_rank("B"):
                exceptional_over_cap = True
            else:
                rarity = capped_rarity
        category_options = _reward_weight_options("category_rates", rarity, _WENYOU_REWARD_CATEGORY_RATES.get(rarity, []))
        category_options = _apply_reward_category_boosts(category_options, category_boosts)
        category = _weighted_pick(category_options, rng, fallback="consumable_item")
        candidates = _reward_catalog_candidates(category, rarity)
        if candidates:
            picked = dict(candidates[rng.randrange(len(candidates))])
        else:
            picked = _reward_stack_item(category, rarity)
        extra = {
            "reward_category": category,
            "reward_roll": {
                "seed": seed,
                "raw_rarity": raw_rarity,
                "final_rarity": rarity,
                "regular_cap": regular_cap,
                "capped": bool(capped and not exceptional_over_cap),
                "exceptional_over_cap": exceptional_over_cap,
            },
        }
        if exceptional_over_cap:
            picked["shop_allowed"] = False
            picked["gacha_allowed"] = False
            picked["sealed"] = True
            picked["seal_rank"] = picked.get("seal_rank") or rarity
            picked["sealed_reason"] = f"{difficulty} 级副本的越级奖励，需达到 {rarity} 阶或按内容包降级生效。"
        item = _new_inventory_item(picked, "settlement", "reward", extra)
        rewards.append(
            {
                "roll_id": f"reward-{index + 1:02d}",
                "rarity": rarity,
                "category": category,
                "category_label": _WENYOU_REWARD_CATEGORY_LABELS.get(category, category),
                "item": item,
                "raw_rarity": raw_rarity,
                "regular_cap": regular_cap,
                "capped": bool(capped and not exceptional_over_cap),
                "exceptional_over_cap": exceptional_over_cap,
            }
        )
        has_bplus = has_bplus or _rarity_rank(rarity) >= _rarity_rank("B")
    if (rating == "S" or int(settlement.get("hidden_bonus_rolls") or 0) > 0) and rewards and not has_bplus:
        picked = _reward_stack_item("tool_item", "B")
        exceptional_over_cap = _rarity_rank("B") > _rarity_rank(regular_cap)
        if exceptional_over_cap:
            picked["sealed"] = True
            picked["seal_rank"] = "B"
            picked["sealed_reason"] = f"{difficulty} 级副本的 B+ 保底奖励，需达到 B 阶或按内容包降级生效。"
        replacement = _new_inventory_item(
            picked,
            "settlement",
            "reward",
            {"reward_category": "tool_item", "reward_roll": {"seed": seed, "forced_bplus": True, "regular_cap": regular_cap}},
        )
        rewards[0] = {
            "roll_id": rewards[0].get("roll_id") or "reward-01",
            "rarity": "B",
            "category": "tool_item",
            "category_label": _WENYOU_REWARD_CATEGORY_LABELS["tool_item"],
            "item": replacement,
            "raw_rarity": rewards[0].get("raw_rarity"),
            "regular_cap": regular_cap,
            "capped": False,
            "exceptional_over_cap": exceptional_over_cap,
            "forced_bplus": True,
        }
    return rewards


def _normalize_gacha_pool_id(pool_id: Any) -> str:
    pool = str(pool_id or "mixed").strip().lower()
    return pool if pool in _GACHA_POOL_RATES else "mixed"


def _normalize_gacha_pool_state(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    return {
        "total": max(0, int(data.get("total") or 0)),
        "no_cplus": max(0, int(data.get("no_cplus") or 0)),
        "no_bplus": max(0, int(data.get("no_bplus") or 0)),
        "no_s": max(0, int(data.get("no_s") or 0)),
    }


def _normalize_gacha_state(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    pools_raw = data.get("pools") if isinstance(data.get("pools"), dict) else {}
    pools = {}
    for pool_id in _GACHA_POOL_RATES:
        pools[pool_id] = _normalize_gacha_pool_state(pools_raw.get(pool_id))
    return {"pools": pools}


def _roll_rarity_by_rate(pool_id: str, rng: random.Random) -> str:
    roll = rng.random() * 100
    acc = 0.0
    for rarity, weight in _GACHA_POOL_RATES[_normalize_gacha_pool_id(pool_id)]:
        acc += weight
        if roll < acc:
            return rarity
    return "D"


def _apply_gacha_pity(pool_state: dict, rarity: str) -> tuple[str, Optional[str]]:
    guarantee: Optional[str] = None
    if int(pool_state.get("no_s") or 0) + 1 >= 100:
        guarantee = "S"
    elif int(pool_state.get("no_bplus") or 0) + 1 >= 30:
        guarantee = "B"
    elif int(pool_state.get("no_cplus") or 0) + 1 >= 10:
        guarantee = "C"
    if guarantee and _rarity_rank(rarity) < _rarity_rank(guarantee):
        return guarantee, guarantee
    return rarity, None


def _update_gacha_pity(pool_state: dict, rarity: str) -> dict:
    state = _normalize_gacha_pool_state(pool_state)
    state["total"] += 1
    if _rarity_rank(rarity) >= _rarity_rank("C"):
        state["no_cplus"] = 0
    else:
        state["no_cplus"] += 1
    if _rarity_rank(rarity) >= _rarity_rank("B"):
        state["no_bplus"] = 0
    else:
        state["no_bplus"] += 1
    if rarity == "S":
        state["no_s"] = 0
    else:
        state["no_s"] += 1
    return state


def _max_player_rank(session: dict) -> str:
    _session_ensure_stats(session)
    ranks = []
    for pk in ("player1", "player2"):
        p = session.get("stats", {}).get(pk)
        if isinstance(p, dict):
            ranks.append(_normalize_difficulty(p.get("rank") or "D"))
    return max(ranks or ["D"], key=_rarity_rank)


def _pick_gacha_definition(pool_id: str, rarity: str, rng: random.Random) -> dict:
    pool = _GACHA_ITEMS_BY_RARITY.get(rarity) or _GACHA_ITEMS_BY_RARITY.get("D") or []
    normalized_pool = _normalize_gacha_pool_id(pool_id)
    if normalized_pool == "tool_pool":
        filtered = [item for item in pool if str(item.get("category") or "") == "tool"]
        pool = filtered or pool
    elif normalized_pool == "supply_pool":
        filtered = [item for item in pool if str(item.get("category") or "") == "consumable"]
        pool = filtered or pool
    if not pool:
        return {"id": "unknown", "name": "未知残片", "rarity": rarity, "kind": "残片", "category": "fragment", "desc": "", "sigil": "UNK", "stackable": True}
    return dict(pool[rng.randrange(len(pool))])


def _gacha_fragment_item(source_item: dict) -> dict:
    rarity = str(source_item.get("rarity") or "D")
    qty = _GACHA_FRAGMENT_VALUES.get(rarity, 5)
    return {
        "id": f"{source_item.get('id')}_fragment",
        "name": f"{source_item.get('name')}碎片",
        "kind": "碎片",
        "category": "fragment",
        "rarity": rarity,
        "desc": f"重复获得【{source_item.get('name')}】后转化。",
        "quantity": qty,
        "sigil": "FRG",
        "stackable": True,
        "converted_from": source_item.get("id"),
    }


def _prepare_gacha_item_for_inventory(defn: dict, session: dict, pool_id: str) -> dict:
    item = dict(defn)
    max_rank = _max_player_rank(session)
    if str(item.get("rarity") or "D") in {"A", "S"} and _rarity_rank(item.get("rarity")) > _rarity_rank(max_rank):
        item["sealed"] = True
        item["sealed_reason"] = f"当前最高阶位 {max_rank}，需达到 {item.get('rarity')} 阶后解封。"
    item["pool_id"] = pool_id
    return item


def roll_gacha(user_id: int, pool_id: str = "mixed", count: int = 1, actor_id: Any = "player1", reason: str = "") -> tuple[bool, str, dict]:
    uid = int(user_id)
    actor = _resolve_player_key(actor_id)
    pool = _normalize_gacha_pool_id(pool_id)
    try:
        pull_count = int(count or 1)
    except Exception:
        pull_count = 1
    if pull_count not in (1, 10):
        return False, "命运裂隙目前只支持单抽或十连。", get_shop_view(uid, actor)

    session = r2_store.get_wenyou_session(uid)
    has_session = bool(session and isinstance(session, dict) and session.get("gameId"))
    raw_phase = _session_phase(session) if has_session else "hub"
    phase = "hub" if raw_phase == "archived" else raw_phase
    has_active_economy_session = bool(has_session and phase in {"hub", "settlement"})
    if has_session and phase not in {"hub", "settlement", "archived"}:
        return False, "副本进行中，命运裂隙关闭；请回到主神空间或结算阶段再抽取。", get_shop_view(uid, actor)

    wallet = _load_wenyou_wallet(uid, session if has_active_economy_session else None)
    cost = pull_count * _GACHA_SINGLE_COST
    account = _player_account(wallet, actor)
    if int(account.get("points") or 0) < cost:
        return False, "主神积分不足，命运裂隙没有响应。", get_shop_view(uid, actor)

    gacha = _normalize_gacha_state(account.get("gacha"))
    pool_state = _normalize_gacha_pool_state(gacha["pools"].get(pool))
    seed = f"wenyou-gacha:{uid}:{actor}:{pool}:{pool_state.get('total', 0)}:{now_beijing_iso()}:{uuid4().hex[:8]}"
    rng = random.Random(seed)
    if has_active_economy_session:
        _session_ensure_stats(session)
        st = session["stats"]
        rank_context = session
        inventory = _inventory_for_player_action(wallet, st, actor, active=True)
    else:
        st = _wallet_stats_from_wallet(wallet)
        rank_context = {"phase": "hub", "stats": st}
        inventory = _get_player_inventory(wallet, actor)
    results: list[dict] = []
    inventory_added: list[dict] = []

    for _ in range(pull_count):
        rarity = _roll_rarity_by_rate(pool, rng)
        rarity, pity_hit = _apply_gacha_pity(pool_state, rarity)
        pool_state = _update_gacha_pity(pool_state, rarity)
        picked = _pick_gacha_definition(pool, rarity, rng)
        prepared = _prepare_gacha_item_for_inventory(picked, rank_context, pool)
        prepared_category = str(prepared.get("category") or "")
        duplicate_to_fragment = prepared_category in {"tool", "special"} and _inventory_has_item(inventory, item_id=str(prepared.get("id") or ""))
        if duplicate_to_fragment:
            fragment = _new_inventory_item(_gacha_fragment_item(prepared), "gacha", "gacha-frag", {"pool_id": pool, "holder_id": actor})
            inventory = _add_inventory_item(inventory, fragment)
            result_item = dict(prepared)
            result_item.update({"pullId": f"pull-{uuid4().hex[:10]}", "converted": True, "converted_to": fragment, "pity_hit": pity_hit})
            inventory_added.append(fragment)
            results.append(result_item)
        else:
            item_obj = _new_inventory_item(prepared, "gacha", "gacha", {"pool_id": pool, "holder_id": actor})
            inventory = _add_inventory_item(inventory, item_obj)
            result_item = dict(item_obj)
            result_item.update({"pullId": str(item_obj.get("uid") or f"pull-{uuid4().hex[:10]}"), "pity_hit": pity_hit})
            inventory_added.append(item_obj)
            results.append(result_item)

    _set_actor_points(wallet, actor, max(0, int(account.get("points") or 0) - cost))
    if has_active_economy_session:
        _persist_player_inventory_for_action(wallet, st, actor, inventory[:80])
    else:
        _set_player_inventory(wallet, actor, inventory[:80])
        if actor == "player1":
            st["inventory"] = inventory[:80]
    gacha["pools"][pool] = pool_state
    _set_actor_gacha(wallet, actor, gacha)
    ledger_entry = append_player_ledger(
        wallet,
        actor,
        {
            "type": "gacha_roll",
            "pool_id": pool,
            "count": pull_count,
            "points_delta": -cost,
            "summary": f"命运裂隙抽取 {pull_count} 次",
            "reason": _compact_text(reason, 120),
            "result_ids": [str(item.get("id") or "") for item in results],
            "item_add": [{"item_id": item.get("id"), "name": _inventory_item_name(item), "quantity": int(item.get("quantity") or 1)} for item in inventory_added],
        },
    )
    _save_wenyou_wallet(uid, wallet)
    event_log = session.get("event_log") if has_active_economy_session and isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"gacha_{len(event_log) + 1:03d}",
        "source": "rules_engine.gacha",
        "actor_id": actor,
        "changes": {
            "wallets": {actor: {"points_delta": -cost, "points": int(_player_account(wallet, actor).get("points") or 0)}},
            "wallet": {"points_delta": -cost, "points": wallet["points"]} if actor == "player1" else {},
            "inventory_add": {actor: inventory_added},
            "gacha": {actor: {"pool_id": pool, "count": pull_count, "pity": pool_state}},
        },
        "seed": seed,
        "ledger_entry": ledger_entry,
        "created_at": now_beijing_iso(),
    }
    view_session = None
    if has_active_economy_session:
        if actor == "player1":
            st["inventory"] = inventory
        session["stats"] = st
        _sync_session_points_with_wallet(session, wallet)
        event_log.append(patch)
        session["event_log"] = event_log[-200:]
        session["last_state_patch"] = patch
        r2_store.save_wenyou_session(uid, session)
        view_session = get_session_view(uid).get("session")
    return True, f"命运裂隙完成 {pull_count} 次牵引，扣除 {cost} 主神积分。", {
        "active": has_active_economy_session,
        "pool_id": pool,
        "count": pull_count,
        "cost": cost,
        "actor_id": actor,
        "points": int(_player_account(wallet, actor).get("points") or 0),
        "wallet": {"points": int(_player_account(wallet, actor).get("points") or 0), "debts": int(_player_account(wallet, actor).get("debts") or 0), "gacha": _player_account(wallet, actor).get("gacha")},
        "pity": pool_state,
        "results": results,
        "inventory": inventory,
        "state_patch": patch,
        "ledger_entry": ledger_entry,
        "session": view_session,
    }


def _shop_today_key() -> str:
    return now_beijing_iso()[:10]


def _regular_shop_state(wallet: dict) -> dict:
    shop_state = wallet.get("shop_state") if isinstance(wallet.get("shop_state"), dict) else {}
    regular = shop_state.get("regular") if isinstance(shop_state.get("regular"), dict) else {}
    today = _shop_today_key()
    if str(regular.get("date") or "") != today:
        regular = {"date": today, "refresh_count": 0, "refresh_limit": 3, "refresh_cost": 20, "rotation_nonce": ""}
        shop_state["regular"] = regular
        wallet["shop_state"] = shop_state
    regular["refresh_limit"] = 3
    regular["refresh_cost"] = 20
    regular["refresh_count"] = max(0, int(regular.get("refresh_count") or 0))
    return regular


def _shop_rank_context(wallet: Optional[dict], session: Optional[dict] = None) -> str:
    if isinstance(session, dict) and session.get("gameId"):
        try:
            return _max_player_rank(session)
        except Exception:
            pass
    if isinstance(wallet, dict):
        stats = _wallet_stats_from_wallet(wallet)
        ranks = []
        for pid in ("player1", "player2"):
            player = stats.get(pid) if isinstance(stats.get(pid), dict) else {}
            ranks.append(_normalize_difficulty(player.get("rank") or "D"))
        return max(ranks or ["D"], key=_rarity_rank)
    return "D"


_WENYOU_SHOP_RARITY_RATES: dict[str, list[tuple[str, float]]] = {
    "D": [("D", 60.0), ("C", 32.0), ("B", 7.5), ("A", 0.5)],
    "C": [("D", 25.0), ("C", 45.0), ("B", 25.0), ("A", 4.8), ("S", 0.2)],
    "B": [("C", 32.0), ("B", 45.0), ("A", 20.0), ("S", 3.0)],
    "A": [("C", 10.0), ("B", 28.0), ("A", 54.0), ("S", 8.0)],
    "S": [("B", 15.0), ("A", 45.0), ("S", 40.0)],
}


def _shop_offer_items(user_id: int, wallet: Optional[dict] = None, session: Optional[dict] = None) -> list[dict[str, Any]]:
    """每天按用户固定随机 7-8 个商品；高阶物品只随玩家阶位极低概率进入普通商店。"""
    regular = _regular_shop_state(wallet) if isinstance(wallet, dict) else {"refresh_count": 0, "rotation_nonce": ""}
    rank = _shop_rank_context(wallet, session)
    rng = random.Random(f"wenyou-shop:{int(user_id or 0)}:{_shop_today_key()}:{regular.get('refresh_count', 0)}:{regular.get('rotation_nonce') or ''}:{rank}")
    source = _SHOP_CATALOG or _GACHA_CATALOG
    by_rarity: dict[str, list[dict[str, Any]]] = {}
    for item in source:
        rarity = _normalize_difficulty(item.get("rarity") or "D")
        if str(item.get("category") or item.get("item_type") or "") not in {"consumable", "tool", "special"}:
            continue
        if item.get("quest_item") or item.get("temporary"):
            continue
        by_rarity.setdefault(rarity, []).append(dict(item))
    for items in by_rarity.values():
        rng.shuffle(items)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    target_count = 8 if rng.random() < 0.65 else 7
    attempts = 0
    while len(out) < target_count and attempts < 80:
        attempts += 1
        rarity = _weighted_pick(_WENYOU_SHOP_RARITY_RATES.get(rank, _WENYOU_SHOP_RARITY_RATES["D"]), rng, fallback="D")
        candidates = by_rarity.get(rarity) or []
        if not candidates:
            continue
        cur = dict(candidates[attempts % len(candidates)])
        iid = str(cur.get("id") or cur.get("name") or "")
        if iid in seen:
            continue
        seen.add(iid)
        if rarity == "S":
            cur["price"] = max(_GACHA_SINGLE_COST * 100 + 2000, int(cur.get("price") or 0))
            cur["unique"] = True
            cur["sealed"] = cur.get("sealed") if cur.get("sealed") is not None else True
            cur["seal_rank"] = cur.get("seal_rank") or "S"
        elif rarity == "A":
            cur["price"] = max(900, int(cur.get("price") or 0))
        elif rarity == "B":
            cur["price"] = max(260, int(cur.get("price") or 0))
        if _rarity_rank(rarity) > _rarity_rank(rank):
            cur["sealed"] = True
            cur["sealed_reason"] = f"当前最高阶位 {rank}，购买后需达到 {rarity} 阶完整解封。"
        out.append(cur)
    if len(out) < 7:
        fallback = [dict(item) for item in source if str(item.get("rarity") or "D") in {"D", "C"}]
        rng.shuffle(fallback)
        for cur in fallback:
            iid = str(cur.get("id") or cur.get("name") or "")
            if iid and iid not in seen:
                out.append(cur)
                seen.add(iid)
            if len(out) >= 7:
                break
    return out


def _shop_items_with_offer_refs(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items[:99], start=1):
        cur = dict(item)
        cur["offer_ref"] = f"{prefix}{index:02d}"
        out.append(cur)
    return out


def get_shop_view(user_id: int, actor_id: Any = "player1") -> dict:
    """文游系统商店/个人空间：优先读当前 session，归档后读 wallet 背包。"""
    uid = int(user_id)
    actor = _resolve_player_key(actor_id)
    session = r2_store.get_wenyou_session(uid)
    has_session = bool(session and isinstance(session, dict) and session.get("gameId"))
    raw_phase = _session_phase(session) if has_session else "hub"
    active = bool(has_session and raw_phase != "archived")
    phase = raw_phase if active else "hub"
    wallet = _load_wenyou_wallet(uid, session if active else None)
    wallet_stats = _wallet_stats_from_wallet(wallet)
    inventory: list[dict] = _get_player_inventory(wallet, actor)
    players = {
        "player1": copy.deepcopy(wallet_stats.get("player1") if isinstance(wallet_stats.get("player1"), dict) else _default_player_stats()),
        "player2": copy.deepcopy(wallet_stats.get("player2") if isinstance(wallet_stats.get("player2"), dict) else _default_player_stats()),
    }
    regular_state = _regular_shop_state(wallet)
    if active:
        _session_ensure_stats(session)
        st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
        phase = _session_phase(session)
        _sync_session_points_with_wallet(session, wallet)
        inventory = _inventory_for_player_action(wallet, st, actor, active)
        players = {
            "player1": copy.deepcopy(st.get("player1") if isinstance(st.get("player1"), dict) else players["player1"]),
            "player2": copy.deepcopy(st.get("player2") if isinstance(st.get("player2"), dict) else players["player2"]),
        }
    can_buy = bool(_shop_open_for_phase(phase))
    regular_items = _shop_items_with_offer_refs(_shop_offer_items(uid, wallet, session if active else None), "R")
    account = _player_account(wallet, actor)
    inventories = {
        "player1": _get_player_inventory(wallet, "player1"),
        "player2": _get_player_inventory(wallet, "player2"),
        "task_items": _normalize_inventory((wallet.get("inventories") or {}).get("task_items"), source="wallet"),
    }
    stats_view = {
        "phase": phase,
        "points": max(0, int(account.get("points") or 0)),
        "inventory": inventory,
        "inventories": inventories,
        "wallets": copy.deepcopy(wallet.get("wallets") if isinstance(wallet.get("wallets"), dict) else {}),
        "player1": players["player1"],
        "player2": players["player2"],
    }
    growth_session = {"phase": phase, "stats": copy.deepcopy(stats_view)}
    return {
        "active": active,
        "actor_id": actor,
        "phase": phase,
        "phaseLabel": _phase_label(phase),
        "can_buy": can_buy,
        "points": max(0, int(account.get("points") or 0)),
        "debts": max(0, int(account.get("debts") or 0)),
        "wallets": copy.deepcopy(wallet.get("wallets") if isinstance(wallet.get("wallets"), dict) else {}),
        "inventories": inventories,
        "inventory": inventory,
        "stats": stats_view,
        "growth": _growth_view(growth_session, wallet),
        "generatedAt": _shop_today_key(),
        "items": regular_items,
        "shop_state": {
            "regular": {
                "rotation_id": f"regular_{regular_state.get('date')}_{regular_state.get('refresh_count', 0)}",
                "refresh_count": int(regular_state.get("refresh_count") or 0),
                "refresh_limit": int(regular_state.get("refresh_limit") or 3),
                "refresh_cost": int(regular_state.get("refresh_cost") or 20),
                "items": regular_items,
            },
        },
    }


def refresh_shop_items(user_id: int) -> tuple[bool, str, dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    has_session = bool(session and isinstance(session, dict) and session.get("gameId"))
    raw_phase = _session_phase(session) if has_session else "hub"
    phase = "hub" if raw_phase == "archived" else raw_phase
    if not _shop_open_for_phase(phase):
        return False, "副本进行中，系统商店关闭，不能刷新货架。", get_shop_view(uid)
    has_economy_session = bool(has_session and raw_phase in {"hub", "settlement"})
    if has_economy_session:
        _session_ensure_stats(session)
    wallet = _load_wenyou_wallet(uid, session if has_economy_session else None)
    regular = _regular_shop_state(wallet)
    limit = int(regular.get("refresh_limit") or 3)
    count = int(regular.get("refresh_count") or 0)
    cost = int(regular.get("refresh_cost") or 20)
    if count >= limit:
        return False, "今日普通商店刷新次数已用完。", get_shop_view(uid)
    account = _player_account(wallet, "player1")
    points = max(0, int(account.get("points") or 0))
    if points < cost:
        return False, f"主神积分不足，刷新需要 {cost}。", get_shop_view(uid)
    _set_actor_points(wallet, "player1", points - cost)
    regular["refresh_count"] = count + 1
    regular["rotation_nonce"] = uuid4().hex[:8]
    wallet.setdefault("shop_state", {})["regular"] = regular
    append_player_ledger(wallet, "player1", {"type": "shop_refresh", "points_delta": -cost, "refresh_count": regular["refresh_count"], "summary": "刷新普通商店"})
    _save_wenyou_wallet(uid, wallet)
    if has_economy_session:
        _sync_session_points_with_wallet(session, wallet)
        r2_store.save_wenyou_session(uid, session)
    return True, f"普通商店已刷新，扣除 {cost} 主神积分。", get_shop_view(uid)


def _resolve_shop_offer(offers: list[dict], item_id: str = "", offer_ref: str = "") -> Optional[dict]:
    ref = str(offer_ref or "").strip().upper()
    iid = str(item_id or "").strip()
    for item in offers:
        if ref and str(item.get("offer_ref") or "").strip().upper() == ref:
            return item
        if iid and str(item.get("id") or "") == iid:
            return item
    return None


def buy_shop_item(user_id: int, item_id: str = "", actor_id: Any = "player1", offer_ref: str = "", reason: str = "") -> tuple[bool, str, dict]:
    """购买商店道具：主神空间/结算期写入钱包背包，副本中禁止购买。"""
    uid = int(user_id)
    actor = _resolve_player_key(actor_id)
    iid = str(item_id or "").strip()
    ref = str(offer_ref or "").strip()
    if not iid and not ref:
        return False, "请选择要购买的道具。", get_shop_view(uid, actor)
    session = r2_store.get_wenyou_session(uid)
    has_session = bool(session and isinstance(session, dict) and session.get("gameId"))
    raw_phase = _session_phase(session) if has_session else "hub"
    phase = "hub" if raw_phase == "archived" else raw_phase
    if not _shop_open_for_phase(phase):
        return False, "副本进行中，系统商店关闭；只能使用背包已有物品，结束并进入结算后再购买。", get_shop_view(uid, actor)
    has_economy_session = bool(has_session and raw_phase in {"hub", "settlement"})
    if has_economy_session:
        _session_ensure_stats(session)
    wallet = _load_wenyou_wallet(uid, session if has_economy_session else None)
    offers = _shop_items_with_offer_refs(_shop_offer_items(uid, wallet, session if has_economy_session else None), "R")
    item = _resolve_shop_offer(offers, iid, ref)
    if not item:
        return False, "该商品已下架，请刷新系统商店。", get_shop_view(uid, actor)
    st = session["stats"] if has_economy_session else _wallet_stats_from_wallet(wallet)
    account = _player_account(wallet, actor)
    points = max(0, int(account.get("points") or 0))
    price = max(0, int(item.get("price") or 0))
    if points < price:
        return False, "主神积分不足。", get_shop_view(uid, actor)
    inv = _inventory_for_player_action(wallet, st, actor, active=has_economy_session)
    name = str(item.get("name") or "").strip()
    if not name:
        return False, "商品数据异常。", get_shop_view(uid, actor)
    if _inventory_has_item(inv, item_id=iid, name=name) and not item.get("stackable") and not item.get("unique"):
        return False, f"背包里已有【{name}】。", get_shop_view(uid, actor)
    item_obj = _new_inventory_item(item, "shop", "shop", {"holder_id": actor})
    inv = _add_inventory_item(inv, item_obj)
    _set_actor_points(wallet, actor, points - price)
    _persist_player_inventory_for_action(wallet, st, actor, inv[:80])
    ledger_entry = append_player_ledger(
        wallet,
        actor,
        {
            "type": "shop_buy",
            "item_id": str(item.get("id") or iid),
            "item_name": name,
            "offer_ref": str(item.get("offer_ref") or ref),
            "points_delta": -price,
            "summary": f"购买【{name}】",
            "reason": _compact_text(reason, 120),
        },
    )
    _save_wenyou_wallet(uid, wallet)
    if has_economy_session:
        if actor == "player1":
            st["points"] = int(wallet.get("points") or 0)
        session["stats"] = st
        _sync_session_points_with_wallet(session, wallet)
    patch = {
        "round_id": f"shop_buy_{len(session.get('event_log') or []) + 1:03d}" if has_economy_session else f"shop_buy_{uuid4().hex[:8]}",
        "source": "rules_engine.shop_buy",
        "actor_id": actor,
        "changes": {
            "wallets": {actor: {"points_delta": -price, "points": int(_player_account(wallet, actor).get("points") or 0)}},
            "inventory_add": {actor: [item_obj]},
        },
        "ledger_entry": ledger_entry,
        "created_at": now_beijing_iso(),
    }
    if has_economy_session:
        event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
        event_log.append(patch)
        session["event_log"] = event_log[-200:]
        session["last_state_patch"] = patch
        r2_store.save_wenyou_session(uid, session)
    view = get_shop_view(uid, actor)
    view["bought"] = {"id": iid, "name": name, "price": price}
    view["state_patch"] = patch
    view["ledger_entry"] = ledger_entry
    return True, f"已购买【{name}】，扣除 {price} 主神积分。", view


def _resolve_player_key(player_id: Any = "player1") -> str:
    raw = str(player_id or "player1").strip().lower()
    if raw in {"player2", "p2", "玩家二"}:
        return "player2"
    return "player1"


def _append_rules_patch(session: dict, source: str, changes: dict) -> dict:
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"{source.split('.')[-1]}_{len(event_log) + 1:03d}",
        "source": source,
        "changes": changes,
        "created_at": now_beijing_iso(),
    }
    event_log.append(patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = patch
    return patch


def _next_rank(rank: str) -> Optional[str]:
    cur = _normalize_difficulty(rank)
    try:
        idx = _WENYOU_RANK_ORDER.index(cur)
    except ValueError:
        idx = 0
    if idx >= len(_WENYOU_RANK_ORDER) - 1:
        return None
    return _WENYOU_RANK_ORDER[idx + 1]


def _has_required_clear_record(wallet: dict, target_rank: str) -> bool:
    rule = _WENYOU_PROMOTION_RULES.get(target_rank)
    if not rule:
        return False
    clear = str(rule.get("clear") or "")
    perfect = str(rule.get("perfect") or "")
    for rec in wallet.get("clear_records") or []:
        if not isinstance(rec, dict) or rec.get("result") != "standard_clear":
            continue
        difficulty = _normalize_difficulty(rec.get("difficulty") or "D")
        rating = str(rec.get("rating") or "").upper()
        if difficulty == clear:
            return True
        if difficulty == perfect and rating == "S":
            return True
    return False


def _promotion_preview(player: dict, wallet: dict) -> dict:
    _normalize_player_growth_fields(player)
    target = _next_rank(str(player.get("rank") or "D"))
    if not target:
        return {"available": False, "current_rank": str(player.get("rank") or "D"), "target_rank": "", "reasons": ["已达最高阶位"]}
    rule = _WENYOU_PROMOTION_RULES[target]
    reasons: list[str] = []
    if int(player.get("level") or 1) < int(rule.get("level") or 1):
        reasons.append(f"等级不足：需要 Lv{rule.get('level')}")
    if int(wallet.get("points") or 0) < int(rule.get("cost") or 0):
        reasons.append(f"积分不足：需要 {rule.get('cost')}")
    if int(wallet.get("debts") or 0) >= 3000:
        reasons.append("债务达到 3000，需先清算")
    if int(player.get("pollution") or 0) >= 90:
        reasons.append("污染达到 90，需先清算")
    if rule.get("special_trial") and not player.get("special_trial_cleared"):
        reasons.append("需要完成特殊试炼")
    if not _has_required_clear_record(wallet, target):
        reasons.append(f"缺少晋升通关记录：{rule.get('clear')} 通关或 {rule.get('perfect')} 完美")
    return {
        "available": not reasons,
        "current_rank": str(player.get("rank") or "D"),
        "target_rank": target,
        "required_level": int(rule.get("level") or 1),
        "cost": int(rule.get("cost") or 0),
        "reasons": reasons,
    }


def _growth_view(session: dict, wallet: dict) -> dict:
    _session_ensure_stats(session)
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    players: dict[str, Any] = {}
    for pid in ("player1", "player2"):
        player = st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats()
        _recalc_player_caps(player)
        rank = _normalize_difficulty(player.get("rank") or "D")
        players[pid] = {
            "attributes": {key: int(player.get(key) or 0) for key in _WENYOU_ATTRIBUTE_KEYS},
            "soft_cap": _WENYOU_RANK_ATTRIBUTE_SOFT_CAP.get(rank, 14),
            "unspent_attribute_points": int(player.get("unspent_attribute_points") or 0),
            "core_ability": _normalize_core_ability(player.get("core_ability")),
            "core_ability_profile": copy.deepcopy(player.get("core_ability_profile") if isinstance(player.get("core_ability_profile"), dict) else None),
            "next_level_exp": int(_WENYOU_LEVEL_EXP_TABLE.get(int(player.get("level") or 1), 0)),
            "spi_current": int(player.get("spi_current") or 0),
            "spi_max": int(player.get("spi_max") or 0),
            "promotion": _promotion_preview(player, wallet),
        }
    return {
        "attribute_keys": list(_WENYOU_ATTRIBUTE_KEYS),
        "rank_soft_caps": dict(_WENYOU_RANK_ATTRIBUTE_SOFT_CAP),
        "players": players,
    }


def allocate_attribute_points(user_id: int, player_id: Any = "player1", deltas: Optional[dict] = None) -> tuple[bool, str, dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "当前没有可分配属性点的文游存档。", get_session_view(uid)
    _session_ensure_stats(session)
    phase = _session_phase(session)
    safe_rest = bool((session.get("flags") or {}).get("safe_rest_node")) if isinstance(session.get("flags"), dict) else False
    if phase not in {"hub", "settlement"} and not safe_rest:
        return False, "副本高压阶段不能分配属性点；请回到主神空间、结算阶段或安全休整节点。", get_session_view(uid)
    pid = _resolve_player_key(player_id)
    st = session["stats"]
    player = st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats()
    _recalc_player_caps(player)
    raw = deltas if isinstance(deltas, dict) else {}
    clean: dict[str, int] = {}
    for key, value in raw.items():
        if key not in _WENYOU_ATTRIBUTE_KEYS:
            return False, f"不能分配未知属性：{key}", get_session_view(uid)
        try:
            amount = int(value or 0)
        except Exception:
            return False, f"属性点必须是整数：{key}", get_session_view(uid)
        if amount < 0:
            return False, "属性点不能为负数。", get_session_view(uid)
        if amount:
            clean[key] = amount
    total = sum(clean.values())
    if total <= 0:
        return False, "请选择要分配的属性点。", get_session_view(uid)
    unspent = int(player.get("unspent_attribute_points") or 0)
    if total > unspent:
        return False, f"未分配属性点不足：剩余 {unspent}。", get_session_view(uid)
    rank = _normalize_difficulty(player.get("rank") or "D")
    soft_cap = _WENYOU_RANK_ATTRIBUTE_SOFT_CAP.get(rank, 14)
    for key, amount in clean.items():
        if int(player.get(key) or 0) + amount > soft_cap:
            return False, f"{key} 超过当前 {rank} 阶软上限 {soft_cap}。", get_session_view(uid)

    before = {key: int(player.get(key) or 0) for key in _WENYOU_ATTRIBUTE_KEYS}
    hp_before = int(player.get("hp_max") or 0)
    san_before = int(player.get("san_max") or 0)
    spi_before = int(player.get("spi_max") or 0)
    spi_current_before = int(player.get("spi_current") or 0)
    for key, amount in clean.items():
        player[key] = int(player.get(key) or 0) + amount
    player["unspent_attribute_points"] = unspent - total
    _recalc_player_caps(player)
    if clean.get("spi") and (phase in {"hub", "settlement"} or safe_rest):
        player["spi_current"] = min(int(player.get("spi_max") or 0), spi_current_before + int(clean["spi"]))
    st[pid] = player
    session["stats"] = st
    patch = _append_rules_patch(
        session,
        "rules_engine.allocate_attribute_points",
        {
            "players": {
                pid: {
                    "attribute_deltas": clean,
                    "attributes_before": before,
                    "attributes_after": {key: int(player.get(key) or 0) for key in _WENYOU_ATTRIBUTE_KEYS},
                    "hp_max_delta": int(player.get("hp_max") or 0) - hp_before,
                    "san_max_delta": int(player.get("san_max") or 0) - san_before,
                    "spi_max_delta": int(player.get("spi_max") or 0) - spi_before,
                    "spi_current_delta": int(player.get("spi_current") or 0) - spi_current_before,
                    "unspent_attribute_points": int(player.get("unspent_attribute_points") or 0),
                }
            }
        },
    )
    r2_store.save_wenyou_session(uid, session)
    view = get_session_view(uid)
    view["state_patch"] = patch
    return True, "属性点已分配。", view


def promote_player_rank(user_id: int, player_id: Any = "player1", target_rank: str = "") -> tuple[bool, str, dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "当前没有可晋升的文游存档。", get_session_view(uid)
    _session_ensure_stats(session)
    phase = _session_phase(session)
    if phase not in {"hub", "settlement"}:
        return False, "只能在主神空间或结算阶段晋升。", get_session_view(uid)
    pid = _resolve_player_key(player_id)
    wallet = _load_wenyou_wallet(uid, session)
    st = session["stats"]
    player = st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats()
    _recalc_player_caps(player)
    current = _normalize_difficulty(player.get("rank") or "D")
    target = _normalize_difficulty(target_rank or _next_rank(current) or current)
    expected = _next_rank(current)
    if not expected:
        return False, "已经是最高阶位。", get_session_view(uid)
    if target != expected:
        return False, f"只能从 {current} 晋升到 {expected}。", get_session_view(uid)
    preview = _promotion_preview(player, wallet)
    if not preview.get("available"):
        return False, "暂不能晋升：" + "；".join(preview.get("reasons") or []), get_session_view(uid)

    cost = int(preview.get("cost") or 0)
    wallet["points"] = max(0, int(wallet.get("points") or 0) - cost)
    before_rank = current
    caps_before = {"hp_max": int(player.get("hp_max") or 0), "san_max": int(player.get("san_max") or 0), "spi_max": int(player.get("spi_max") or 0)}
    player["rank"] = target
    _recalc_player_caps(player)
    st[pid] = player

    merged_inventory = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
    unlocked_inventory, unlocked = _unseal_inventory_by_rank(merged_inventory, target)
    wallet["inventory"] = unlocked_inventory
    st["inventory"] = unlocked_inventory
    session["stats"] = st
    wallet["promotion_history"] = (wallet.get("promotion_history") or [])[-19:] + [
        {"at": now_beijing_iso(), "player": pid, "from": before_rank, "to": target, "cost": cost}
    ]
    wallet["ledger"] = (wallet.get("ledger") or [])[-79:] + [
        {"at": now_beijing_iso(), "type": "rank_promote", "player": pid, "from": before_rank, "to": target, "points_delta": -cost}
    ]
    _save_wenyou_wallet(uid, wallet)
    _sync_session_points_with_wallet(session, wallet)
    patch = _append_rules_patch(
        session,
        "rules_engine.promote_rank",
        {
            "wallet": {"points_delta": -cost, "points": wallet["points"]},
            "players": {
                pid: {
                    "rank_before": before_rank,
                    "rank_after": target,
                    "unspent_attribute_points": int(player.get("unspent_attribute_points") or 0),
                    "hp_max_delta": int(player.get("hp_max") or 0) - caps_before["hp_max"],
                    "san_max_delta": int(player.get("san_max") or 0) - caps_before["san_max"],
                    "spi_max_delta": int(player.get("spi_max") or 0) - caps_before["spi_max"],
                }
            },
            "inventory_unsealed": unlocked,
        },
    )
    r2_store.save_wenyou_session(uid, session)
    view = get_session_view(uid)
    view["state_patch"] = patch
    return True, f"{pid} 已晋升至 {target} 阶，扣除 {cost} 主神积分。", view


def revive_player(user_id: int, player_id: Any = "player1") -> tuple[bool, str, dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "当前没有可复活的文游存档。", get_session_view(uid)
    _session_ensure_stats(session)
    pid = _resolve_player_key(player_id)
    st = session["stats"]
    player = st.get(pid) if isinstance(st.get(pid), dict) else _default_player_stats()
    _recalc_player_caps(player)
    if int(player.get("hp") or 0) > 0 and "濒死" not in _normalize_text_list(player.get("conditions"), 40, 20):
        return False, "当前角色未处于死亡/濒死状态，不需要复活。", get_session_view(uid)
    wallet = _load_wenyou_wallet(uid, session)
    rank = _normalize_difficulty(player.get("rank") or "D")
    death_count_before = int(player.get("death_count") or 0)
    revive_cost = int(_WENYOU_REVIVE_BASE_COST.get(rank, 200)) + int(player.get("level") or 1) * 50 + death_count_before * 200
    points_before = int(wallet.get("points") or 0)
    paid = min(points_before, revive_cost)
    debt_added = max(0, revive_cost - paid)
    wallet["points"] = max(0, points_before - paid)
    wallet["debts"] = max(0, int(wallet.get("debts") or 0) + debt_added)
    player["death_count"] = death_count_before + 1
    player["hp"] = max(1, math.floor(int(player.get("hp_max") or 1) * 0.5))
    player["san"] = max(1, math.floor(int(player.get("san_max") or 1) * 0.5))
    player["spi_current"] = max(0, min(int(player.get("spi_current") or 0), int(player.get("spi_max") or 0)))
    for cond in ("濒死", "失控"):
        _remove_condition(player, cond)
    _add_condition_unique(player, "复活疲惫")
    st[pid] = player
    session["stats"] = st
    wallet["ledger"] = (wallet.get("ledger") or [])[-79:] + [
        {
            "at": now_beijing_iso(),
            "type": "revive",
            "player": pid,
            "rank": rank,
            "cost": revive_cost,
            "points_delta": -paid,
            "debt_delta": debt_added,
            "debts": wallet["debts"],
        }
    ]
    _refresh_forced_instance_queue(wallet, session)
    _save_wenyou_wallet(uid, wallet)
    _sync_session_points_with_wallet(session, wallet)
    patch = _append_rules_patch(
        session,
        "rules_engine.revive_player",
        {
            "wallet": {"points_delta": -paid, "debt_delta": debt_added, "debts": wallet["debts"]},
            "players": {
                pid: {
                    "hp": player["hp"],
                    "san": player["san"],
                    "death_count": player["death_count"],
                    "conditions_add": ["复活疲惫"],
                    "conditions_remove": ["濒死", "失控"],
                }
            },
        },
    )
    r2_store.save_wenyou_session(uid, session)
    view = get_session_view(uid)
    view["state_patch"] = patch
    if debt_added:
        return True, f"{pid} 已复活，支付 {paid} 积分，新增债务 {debt_added}。", view
    return True, f"{pid} 已复活，支付 {paid} 积分。", view


def _normalize_candidate_item(raw: Any, index: int = 0) -> Optional[dict]:
    """大厅候选设定：轻量 seed，选中后再扩展为完整 framework。"""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or raw.get("instance_name") or "").strip()
    premise = str(raw.get("premise") or raw.get("world") or raw.get("description") or "").strip()
    if not title and not premise:
        return None
    tags = raw.get("tags")
    if not isinstance(tags, list):
        tags = []
    clean_tags = [str(x).strip()[:18] for x in tags if str(x).strip()][:5]
    cid = str(raw.get("id") or "").strip()
    if not cid:
        cid = f"cand-{now_beijing_iso().replace(':', '').replace('+', '-')}-{index + 1}"
    out = {
        "id": cid[:80],
        "title": (title or f"未命名候选 {index + 1}")[:40],
        "instance_genre": _normalize_instance_genre(raw.get("instance_genre") or raw.get("genre")),
        "difficulty": _normalize_difficulty(raw.get("difficulty")),
        "tagline": str(raw.get("tagline") or raw.get("hook") or "").strip()[:80],
        "premise": premise[:320],
        "core_task": str(raw.get("core_task") or raw.get("task") or raw.get("conflict") or "").strip()[:220],
        "survival_hook": str(raw.get("survival_hook") or raw.get("first_hook") or "").strip()[:180],
        "risk": str(raw.get("risk") or raw.get("failure_hint") or "").strip()[:180],
        "twist": str(raw.get("twist") or raw.get("mystery") or "").strip()[:180],
        "tags": clean_tags,
        "estimated_length": str(raw.get("estimated_length") or raw.get("length") or "标准").strip()[:20] or "标准",
        "tutorial": bool(raw.get("tutorial") or raw.get("is_tutorial") or cid == _WENYOU_TUTORIAL_INSTANCE_ID),
        "locked": bool(raw.get("locked")),
    }
    if raw.get("forced"):
        out["forced"] = True
    queue_id = str(raw.get("queue_id") or "").strip()
    if queue_id:
        out["queue_id"] = queue_id[:80]
    penalty_type = str(raw.get("penalty_type") or "").strip().lower()
    if penalty_type in {"debt", "pollution", "revive", "contract", "system"}:
        out["penalty_type"] = penalty_type
    return out


def _normalize_candidate_payload(raw: Any) -> list[dict]:
    data = raw if isinstance(raw, dict) else {}
    arr = data.get("items") or data.get("candidates") or []
    if not isinstance(arr, list):
        return []
    out: list[dict] = []
    for i, item in enumerate(arr[:10]):
        normalized = _normalize_candidate_item(item, i)
        if normalized:
            out.append(normalized)
    return out


def generate_instance_candidates(user_id: int, count: int = 6, keywords: str = "") -> tuple[Optional[dict], Optional[str]]:
    """一次生成多个大厅候选设定；不创建副本 session。"""
    uid = int(user_id or 0)
    n = max(3, min(8, int(count or 6)))
    difficulty_hint = _difficulty_from_progress(uid)
    prompt = _candidates_prompt(n, difficulty_hint, keywords)
    text = call_wenyou_deepseek([{"role": "user", "content": prompt}], system=_CANDIDATES_SYSTEM, temperature=0.9)
    if not text:
        if _should_offer_tutorial(uid):
            return apply_forced_instance_candidates(
                uid,
                {"version": 1, "generatedAt": now_beijing_iso(), "difficultyHint": difficulty_hint, "items": []},
            ), None
        return None, "文游：候选设定生成失败（DeepSeek 无响应）。"
    data = _extract_json_object(text)
    items = _normalize_candidate_payload(data)
    if not items:
        if _should_offer_tutorial(uid):
            return apply_forced_instance_candidates(
                uid,
                {"version": 1, "generatedAt": now_beijing_iso(), "difficultyHint": difficulty_hint, "items": []},
            ), None
        return None, "文游：候选设定解析失败，请重试。"
    payload = {
        "version": 1,
        "generatedAt": now_beijing_iso(),
        "difficultyHint": difficulty_hint,
        "items": items[:n],
    }
    return apply_forced_instance_candidates(uid, payload), None


def format_candidate_expansion_prompt(candidate: Any) -> str:
    """把大厅候选 seed 转成 /story 的 custom 关键词，让 DS 扩展完整 framework。"""
    item = _normalize_candidate_item(candidate, 0)
    if not item:
        return ""
    tags = "、".join(item.get("tags") or [])
    return (
        "请把以下【副本候选设定】扩展成完整无限流副本框架。"
        "必须保留候选的核心题材、危险钩子与悬念，但可以补全 tasker_total、NPC、规则、任务、开场和初始状态。\n\n"
        f"副本名：{item['title']}\n"
        f"类型：{item['instance_genre']}\n"
        f"难度：{item['difficulty']}\n"
        f"展示文案：{item.get('tagline') or ''}\n"
        f"轻量设定：{item.get('premise') or ''}\n"
        f"通关方向：{item.get('core_task') or ''}\n"
        f"生存钩子：{item.get('survival_hook') or ''}\n"
        f"危险方向：{item.get('risk') or ''}\n"
        f"未揭悬念：{item.get('twist') or ''}\n"
        f"标签：{tags or '无'}\n"
        f"篇幅：{item.get('estimated_length') or '标准'}"
    )


def _candidate_seed_block(item: dict) -> str:
    tags = "、".join(item.get("tags") or [])
    forced_note = ""
    if item.get("forced"):
        penalty_labels = {
            "debt": "债务清算",
            "pollution": "污染清算",
            "revive": "复活清算/临时身份",
            "contract": "契约追偿",
            "system": "强制清算",
        }
        penalty = str(item.get("penalty_type") or "system")
        player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
        player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
        forced_note = (
            "强制清算：是"
            "\n惩罚副本模式：临时 NPC 扮演"
            f"\n结算原因（metadata，不可写成剧情主题）：{penalty_labels.get(penalty, '强制清算')}"
            f"\n清算队列：{item.get('queue_id') or item.get('id') or ''}"
            f"\n玩家一代号（必须作为玩家 NPC 公开姓名）：{player1_code}"
            f"\n玩家二代号（必须作为玩家 NPC 公开姓名）：{player2_code}"
        )
    forced_lines = f"{forced_note}\n" if forced_note else ""
    return (
        f"副本名：{item.get('title') or '未命名副本'}\n"
        f"类型：{item.get('instance_genre') or '剧情解密'}\n"
        f"难度：{item.get('difficulty') or 'C'}\n"
        f"展示文案：{item.get('tagline') or ''}\n"
        f"轻量设定：{item.get('premise') or ''}\n"
        f"通关方向：{item.get('core_task') or ''}\n"
        f"生存钩子：{item.get('survival_hook') or ''}\n"
        f"危险方向：{item.get('risk') or ''}\n"
        f"未揭悬念：{item.get('twist') or ''}\n"
        f"{forced_lines}"
        f"标签：{tags or '无'}\n"
        f"篇幅：{item.get('estimated_length') or '标准'}"
    )


def _forced_candidate_core_prompt(item: dict) -> str:
    player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
    player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
    return f"""把【候选设定】扩展成「无限流 · 惩罚副本」核心设定短稿。

世界观前提：
- 这是主神空间体系下的无限流副本，不是普通角色扮演剧本。
- 正常任务者队伍正在按普通无限流逻辑求生、解谜、验证规则、尝试通关。
- 玩家一和玩家二都不是这支正常任务者队伍成员，而是一起被系统塞进该副本世界的原住民 NPC。
- 玩家一和玩家二的核心目标不是自己通关，而是演好各自 NPC，并在不暴露身份的前提下推动正常任务者副本进度。
- 正文后续仍以玩家一视角运行；玩家二是同一清算任务里的 NPC 同伴，不是旁观协助角色。

{_forced_common_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 5-8 行，每行尽量短。
- 必须包含：副本时代/场景、正常任务者的公开任务、玩家一 NPC 身份、玩家二 NPC 身份、两人关系或身份差异、两人的身份如何推动进度、身份矛盾、危险牵引、暴露后果。
- 玩家一 NPC 的公开姓名必须使用「{player1_code}」，不得另起本名、化名、小名或真实姓名；称谓可随时代变化，如“小姐/姑娘/同学/病人/夫人”。
- 玩家二 NPC 的公开姓名必须使用「{player2_code}」，不得另起本名、化名、小名或真实姓名；称谓可随时代和身份变化。
- 若任一玩家代号和家族、时代、地域或身份结构有违和，不能改名消除；必须把违和写成剧情钩子，如收养、过继、随母姓、家产侵占、族谱涂改、冒名顶替或异常刻意保留。
- 玩家 NPC 可以是副本核心人物：被救援对象、被调查对象、嫌疑人、继承人、祭品、病人、规则触发者、线索持有人或仪式核心；两人可以一主一辅，也可以共同牵住主线。
- NPC 身份越接近主线核心，危险越高；必须让 Boss/异常阵营有理由控制、利用、杀死、替换或误导玩家 NPC。
- 结算原因只作为后端 metadata；不要把债务、污染、复活、契约写成剧情主题或副本主线。
- 不要写 opening，不要写属性数值，不要替玩家行动。

严格禁止：
- 禁止把玩家一或玩家二写成普通任务者。
- 禁止把本局写成玩家自己通关、打 Boss、找出口的普通副本。
- 禁止让玩家一或玩家二直接剧透答案、解释系统、带队通关或跳出 NPC 身份。

【候选设定】
{_candidate_seed_block(item)}"""


def _candidate_core_prompt(item: dict) -> str:
    if item.get("forced"):
        return _forced_candidate_core_prompt(item)
    return f"""把【候选设定】扩展成副本核心设定短稿。

{_infinite_flow_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 4-7 行，每行尽量短。
- 必须包含：副本内部场景、核心矛盾、玩家公开任务、隐藏悬念、危险规则方向。
- 只写副本核心，不写长期主神空间剧情。
- 必须写出正常任务者队伍的压力感：至少暗示 2-3 个任务者的可见行为方向，如试探规则、争抢线索、误判 NPC、害怕退缩、想利用别人或试图合作。
- 如果候选写明“强制清算：是”，必须保留清算类型、身份限制、暴露后果和失败代价；不要改写成普通自愿接取副本。
- 不要写 opening，不要写属性数值，不要替玩家行动。

【候选设定】
{_candidate_seed_block(item)}"""


def _clean_ds_block(text: Any, limit: int = 1200) -> str:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", raw, flags=re.M).strip()
    lines = [line.strip(" \t-•") for line in raw.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)[:limit].strip()


def _candidate_canon_block(item: dict, core_text: str) -> str:
    if not isinstance(item, dict):
        return ""
    return (
        _candidate_seed_block(item)
        + "\n\n核心短稿：\n"
        + _clean_ds_block(core_text, 1200)
    ).strip()


def _infinite_flow_generation_constraints() -> str:
    return """无限流味道约束：
- 如果候选没有明确年代/场景，优先从医院夜班、学校旧楼、老小区、出租屋、家族宅邸、民国婚宴、列车车厢、山村祭祀、公司夜班、商场闭店后、国外古老家族、恶魔/教会、狼人杀式村镇、暴风雪山庄、美恐小镇、公路旅馆、规则怪谈、红蓝阵营规则、猎奇秩序反转、黑暗童话改写等母题中选一个，不要默认写成空泛走廊。
- 规则怪谈母题可以写红方/蓝方、游客/员工、白班/夜班、医护/病患等互相冲突的规则文本；核心是“规则来源不可靠、阵营视角有偏差、错误遵守也会出事”，不要照搬现成作品的具体条文。
- 猎奇/黑暗寓言母题可以写动物与人类地位颠倒、人类被登记饲养或送检、童话婚姻/家族传说的黑暗改写、蓝胡子式密室婚姻、食物链颠倒的村镇；重点是规则、身份压迫和线索验证，不要只堆露骨血腥。
- 副本规则不能像说明书一次讲完；公开规则可以残缺、误导或带适用条件，必须让玩家/任务者通过观察、试探、对照异常后果来验证。
- 正常任务者不能只是背景板；每个副本至少要有 2-3 个可见任务者行为压力，如试探规则、隐瞒线索、误判 NPC、抢占安全区、拉人合作、把别人推出去试错。
- 主神/系统压迫感要克制但存在：只在开场、阶段变化、违规、倒计时、结算预警等关键节点给短提示，不要变成长篇客服播报。
- 失败不应让剧情卡死；错过线索或判断错误时，用威胁时钟推进、任务者受伤/死亡、NPC 身份被怀疑、异常加压、场景封锁或代价结算推动下一段。"""


def _forced_common_generation_constraints() -> str:
    return f"""{_infinite_flow_generation_constraints()}

普通副本底层规则也必须继承：
- 本局仍须有普通无限流副本结构：副本类型、规则/线索/危险源、通关目标、威胁推进和主神结算；不能只写成单纯 NPC 扮演小剧场。
- 正常任务者总人数仍遵守 2-13 的世界规则；惩罚副本里的“正常任务者队伍”可围绕玩家 NPC 展开，但不要把玩家一或玩家二写进这支正常任务者队伍。
- 惩罚副本的爽点不是玩家自己通关，而是明知自己来自主神空间，却必须演原住民 NPC，借身份、关系、误会、病症、地位或危险把正常任务者往通关方向推。
- 正常任务者和副本 NPC 的真实善恶、隐藏动机、怪物弱点、Boss 真相、隐藏结局都不能在开场或公开短稿里直给；只写公开态度、可见行为和可验证线索。
- 线索必须可验证、能推进任务或规则判断；不要把氛围描写、外貌描写或世界观介绍当线索清单甩给玩家。
- 不要写精确 HP/SAN/积分/EXP/抽卡/掉落/晋升/永久能力到账；这些由后端结算。惩罚副本成功/失败只写清算方向，不直接发奖励。
- Boss 或核心异常默认不可被玩家一或玩家二正面解决；必须保留削弱、封印、规避、感化、揭真相或由正常任务者推进的路径。
- 每条关键推进路径要有 fail-forward：错过线索时可通过发病、问话、误判、异常压力、二次调查或身份关系继续推进，不让剧情卡死。
- opening 和正文固定玩家一视角，用“你/你的”；玩家二只通过玩家一可见、可听、可交流的信息呈现；不得替玩家决定行动、表情、内心独白，不得让玩家主动解释系统或跳出身份。"""


def _forced_candidate_blueprint_prompt(item: dict, core_text: str = "") -> str:
    player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
    player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
    return f"""基于【已确定核心设定】生成「无限流 · 惩罚副本」蓝图短稿。

本局底层结构：
- 这仍然是无限流副本：存在主神空间、正常任务者队伍、规则、线索、危险、通关目标和结算。
- 但玩家一和玩家二都不是正常任务者；两人是一起被塞进副本世界的 NPC。
- 正常任务者才是表层主角，他们的主线可以围绕玩家一 NPC、玩家二 NPC，或两人共同关系展开。
- 玩家一和玩家二的隐藏工作是演好各自 NPC，用符合身份的方式推动正常任务者进度，并避免暴露。
- 蓝图内部要明确两人的 NPC 身份、关系、可配合边界；正文运行时仍固定玩家一视角。
- 本局不是让玩家自己通关；玩家只能通过 NPC 身份把正常任务者推到验证规则、找到弱点、封印/规避核心异常的路上。

{_forced_common_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 按三段写：入戏、推动、收束。
- 每段都写：两名玩家 NPC 的表演目标 / 正常任务者进度 / 可给出的线索或阻碍 / 规则验证方式 / 系统压迫节点 / 任一方暴露风险 / 错过时如何付代价 fail-forward。
- 额外列出：玩家一 NPC 身份契约、玩家二 NPC 身份契约、两人关系或配合边界、正常任务者公开任务、身份违和钩子、Boss/异常对玩家 NPC 的危险牵引、暴露给任务者/怪物阵营的后果、隐藏支线/隐藏结局方向。
- 玩家 NPC 身份可以很核心，甚至是被救援、被调查、被怀疑、被保护或被献祭的对象；越核心越危险。
- 玩家一 NPC 的公开姓名必须使用「{player1_code}」，玩家二 NPC 的公开姓名必须使用「{player2_code}」；不得另起姓名。
- 结算原因只写成“后端清算原因”，不得让债务/污染/复活/契约成为剧情主线。
- 怪物或 Boss 默认不可由玩家一或玩家二正面解决；两人只能通过 NPC 身份引导任务者发现削弱、封印、规避或真相路径。
- 只给 GM/后端内部短纲，不要整段剧透给玩家。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _candidate_blueprint_prompt(item: dict, core_text: str = "") -> str:
    if item.get("forced"):
        return _forced_candidate_blueprint_prompt(item, core_text)
    return f"""基于【已确定核心设定】生成副本蓝图短稿。

{_infinite_flow_generation_constraints()}

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 按三段写：开场、探索、收束。
- 每段写“阶段目标 / 关键线索 / 规则验证方式 / 正常任务者可见行为 / 系统压迫节点 / 错过线索时如何付代价推进”。
- 额外列出：普通支线、隐藏支线、隐藏结局、威胁时钟、NPC 任务者立场边界、怪物/核心压力源简表。
- NPC 任务者立场边界只写公开态度和可见行为，不直给真实善恶；真实立场留给后端隐藏状态。
- 怪物生态只写普通怪/精英怪/Boss 或核心压力源的用途和解法；Boss 默认不可正面战胜。
- 结算只看真实玩家角色/玩家队伍；NPC 结局只作为支线/隐藏目标证据，不自动影响评级。
- 如果候选写明“强制清算：是”，蓝图必须列出身份边界、暴露给任务者/怪物阵营的后果，以及成功/失败如何回到后端清算；不要写成普通任务者竞赛。
- 只给 GM/后端内部短纲，不要整段剧透给玩家。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _forced_candidate_opening_prompt(item: dict, core_text: str = "") -> str:
    player1_code = str(item.get("player1_name_hint") or "玩家一").strip() or "玩家一"
    player2_code = str(item.get("player2_name_hint") or "玩家二").strip() or "玩家二"
    return f"""基于【已确定核心设定】生成「无限流 · 惩罚副本」开场正文。

{_forced_common_generation_constraints()}

输出要求：
- 只写开场正文，不要 JSON，不要 markdown 代码块。
- 5-9 句，像小说正文一样续写，必须保留无限流质感：白光/传送/主神提示音/刻板广播/副本载入感至少出现一种。
- 固定以玩家一为视角中心，用第二人称“你/你的”指代玩家一。
- 开场要让玩家明确感到：自己和玩家二都被塞进了副本原住民 NPC 身份，而不是作为普通任务者入场。
- 玩家一 NPC 的公开姓名必须使用「{player1_code}」；可以用称谓组合，如“某家大小姐{player1_code}”“{player1_code}小姐”“{player1_code}同学”，但不得另起姓名。
- 玩家二 NPC 的公开姓名必须使用「{player2_code}」；只能通过玩家一当前能看到、听到、交流到的方式出现，不要写成普通任务者。
- 必须出现或暗示正常任务者队伍的存在；他们可以是被请来的医生、调查员、道士、学生、住户、警员、求生者等，正在按普通无限流逻辑接近主线。
- 可以让正常任务者的表层任务围绕玩家 NPC 展开，例如治疗、保护、调查、看守、护送、判断两人中某一人或两人的关系是否异常。
- 开场必须有正常任务者的可见动作压力：至少出现一个人在试探、争执、害怕、隐瞒、保护或误判；不要把其他任务者写成静态路人。
- 只给一条可被验证的异常/规则苗头，不要把完整规则档案直接发给玩家。
- 不要把后端结算原因念给玩家；不要说“债务/污染/契约工单”等说明书词。
- 不要输出任务者名单、线索列表、规则档案或情报卡。
- 如果写系统/主神广播，必须独立成行：`【系统提示】广播内容`。
- 不要替玩家做行动决定，不要写玩家主动解释系统或直接剧透。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _candidate_opening_prompt(item: dict, core_text: str = "") -> str:
    if item.get("forced"):
        return _forced_candidate_opening_prompt(item, core_text)
    return f"""基于【已确定核心设定】生成副本开场正文。

{_infinite_flow_generation_constraints()}

输出要求：
- 只写开场正文，不要 JSON，不要 markdown 代码块。
- 4-8 句，像小说正文一样续写，含主神传送/白光/提示音/刻板广播之一。
- 落入副本场景，点出第一处异常。
- 开场必须有正常任务者的可见动作压力：至少出现一个人在试探、争执、害怕、隐瞒、保护或误判；不要把其他任务者写成静态路人。
- 只给一条可被验证的异常/规则苗头，不要把完整规则档案直接发给玩家。
- 只写玩家可见开场，不剧透隐藏支线、隐藏结局、NPC 真实立场或威胁时钟精确值。
- 如果写系统/主神广播，必须独立成行：`【系统提示】广播内容`，不要混在叙事长句里。
- 未经玩家看见名牌、听见自我介绍或主神点名前，不要直接写 NPC 姓名；用“戴眼镜的年轻男性”“穿冲锋衣的短发女性”等可见特征称呼。
- 不要输出任务者名单、线索列表、规则档案或情报卡。普通环境描写不是线索。
- 如果候选写明“强制清算：是”，开场要让玩家感到入口被锁定/被迫接入，但不要把隐藏规则、清算队列或后端状态直接念成说明书。
- 不要替玩家做行动决定。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _candidate_instance_code(item: dict) -> str:
    raw = str(item.get("id") or item.get("title") or uuid4()).strip().upper()
    code = re.sub(r"[^A-Z0-9]+", "-", raw).strip("-")
    if not code:
        code = f"ZS-{str(uuid4())[:4].upper()}"
    if not re.search(r"\d", code):
        code = f"ZS-{code[:8]}"
    return code[:16]


def _framework_from_candidate_text(item: dict, core_text: str, blueprint_text: str, opening_text: str) -> dict:
    title = str(item.get("title") or "未命名副本").strip()[:40] or "未命名副本"
    genre = _normalize_instance_genre(item.get("instance_genre"))
    difficulty = _normalize_difficulty(item.get("difficulty"))
    core = _clean_ds_block(core_text, 1200)
    blueprint = _clean_ds_block(blueprint_text, 1400)
    opening = _clean_ds_block(opening_text, 900)
    premise = str(item.get("premise") or "").strip()
    task = str(item.get("core_task") or "").strip()
    hook = str(item.get("survival_hook") or "").strip()
    risk = str(item.get("risk") or "").strip()
    twist = str(item.get("twist") or "").strip()
    tagline = str(item.get("tagline") or "").strip()

    world_parts = [premise, core]
    world = "\n".join(x for x in world_parts if x).strip()[:1600] or f"{title} 是一场主神投放的{genre}副本。"
    conflict = task or f"在【{title}】中确认副本规则，找到通关路径并存活到主神结算。"
    failure_hint = risk or "违反关键规则会触发副本惩罚，具体代价随剧情推进显露。"
    genre_note = (tagline or hook or twist or f"本局以{genre}节奏推进。")[:300]
    blueprint_logline = core.splitlines()[0].strip() if core.splitlines() else conflict
    try:
        player_count = int(item.get("player_count") or _DEFAULT_PLAYER_COUNT)
    except Exception:
        player_count = _DEFAULT_PLAYER_COUNT
    player_count = max(1, min(13, player_count))
    try:
        tasker_total = int(item.get("tasker_total") or item.get("tasker_count") or _DEFAULT_TASKER_TOTAL)
    except Exception:
        tasker_total = _DEFAULT_TASKER_TOTAL
    tasker_total = max(player_count, min(13, max(2, tasker_total)))
    raw = {
        "instance_code": _candidate_instance_code(item),
        "instance_name": title,
        "instance_genre": genre,
        "genre_note": genre_note,
        "difficulty": difficulty,
        "tasker_total": tasker_total,
        "player_count": player_count,
        "world": world,
        "player1_name": "玩家一",
        "player1_instance_name": "",
        "player1_role": "新任务者。",
        "player2_name": "玩家二",
        "player2_instance_name": "",
        "player2_role": "新任务者。",
        "npc_taskers": [],
        "conflict": conflict,
        "failure_hint": failure_hint,
        "reward_hint": "通关后按完成度获得主神积分、经验与可能的线索/道具回报。",
        "public": {
            "instance_name": title,
            "genre": [genre],
            "difficulty": difficulty,
            "visible_rules": [hook] if hook else [],
            "public_task": conflict,
        },
        "gm_secret": {
            "true_rules": [hook] if hook else [],
            "false_rules": [],
            "npc_goals": {},
            "hidden_endings": [{"name": "未揭悬念", "condition": twist}] if twist else [],
        },
        "instance_blueprint": {
            "blueprint_version": 1,
            "logline": blueprint_logline[:240],
            "mainline": [
                {
                    "phase": "开场",
                    "goal": "确认主神任务与第一处异常",
                    "required_clues": [],
                    "fail_forward": "如果玩家错过线索，由广播、环境变化或代价更高的事件继续推进。",
                    "notes": blueprint[:500],
                },
                {
                    "phase": "探索",
                    "goal": "验证关键规则，找到通关路径",
                    "required_clues": [],
                    "fail_forward": "用倒计时、污染、追逐或资源损耗推进。",
                },
                {
                    "phase": "收束",
                    "goal": "完成通关条件，或触发隐藏结局/失败结算",
                    "required_clues": [],
                    "fail_forward": "进入高风险结算，由主神给出明确后果。",
                },
            ],
            "side_quests": [],
            "hidden_side_quests": [],
            "hidden_endings": [{"name": "未揭悬念", "hint": twist}] if twist else [],
            "clue_graph": [
                {
                    "id": "opening_anomaly",
                    "public_text": (hook or tagline or premise or title)[:160],
                    "leads_to": [],
                    "is_required_for_mainline": True,
                }
            ],
            "npc_arcs": {},
            "threat_clocks": [],
            "hard_constraints": [
                "不能过早直接揭示真结局",
                "关键线索错过时必须 fail-forward，而不是让剧情卡死",
                "不要替玩家做行动决定",
                "正常任务者必须有可见行动压力，不能只是背景板。",
                "副本规则需要通过行动验证，不能一次性公开完整答案。",
                "主神/系统提示只在关键节点短促出现，保持压迫感。",
                "失败要以威胁推进、身份怀疑、伤亡、封锁或代价结算继续剧情。",
                "Boss 或核心异常默认不可正面战胜，需要削弱、封印、规避、感化或揭真相路径。",
            ],
        },
        "encounter_profile": {
            "common": [],
            "elite": [],
            "boss": {
                "name": "核心压力源",
                "default_invincible": True,
                "counterplay": ["削弱", "封印", "规避", "撤离"],
            },
            "spawn_rules": [],
            "balance_notes": "候选扩展开局默认先缓存简表，后续可由怪物生成器补全数值。",
        },
        "initial_stats": {
            "points": 100,
            "player1": dict(_default_player_stats()),
            "player2": dict(_default_player_stats()),
            "items": [],
        },
        "opening": opening,
    }
    if item.get("forced"):
        penalty_type = str(item.get("penalty_type") or "system")
        penalty_labels = {
            "debt": "债务",
            "pollution": "污染",
            "revive": "复活代价",
            "contract": "契约",
            "system": "系统",
        }
        penalty_label = penalty_labels.get(penalty_type, "系统")
        raw["player1_role"] = "被主神临时塞入本副本的原住民 NPC；公开姓名沿用玩家代号，必须维持身份并与玩家二共同推动正常任务者进度。"
        raw["player2_role"] = "玩家二也与玩家一一起被主神临时塞入本副本的原住民 NPC；公开姓名沿用玩家代号，必须维持身份并共同完成清算。"
        raw["conflict"] = "维持双方 NPC 身份，在不暴露玩家/任务者/外来者身份的前提下，推动正常任务者完成他们的副本主线，直到主神确认清算完成。"
        raw["failure_hint"] = "任一方身份暴露、直接剧透、替任务者强行通关或破坏副本世界观，会导致清算失败或评级下降。"
        raw["reward_hint"] = f"惩罚副本完成后由后端按{penalty_label}清算原因优先抵扣或解除对应代价；副本剧情不以该原因作为主线。"
        raw["public"]["visible_rules"] = [
            "维持双方 NPC 身份。",
            "不能暴露玩家、任务者、清算对象或外来者身份。",
            "用符合身份的行为推动正常任务者进度。",
        ]
        raw["public"]["public_task"] = raw["conflict"]
        raw["gm_secret"]["true_rules"] = [
            "本局是临时 NPC 惩罚副本；正常任务者才是表层通关队伍。",
            "玩家一与玩家二都是副本原住民 NPC，不属于正常任务者队伍。",
            "玩家不是来自己通关，而是通过 NPC 身份推动正常任务者验证规则、削弱或规避核心异常。",
            "正常任务者必须有可见行动压力：试探规则、误判、争执、隐瞒线索、求助或利用玩家 NPC。",
            "规则不能一次性直给；必须让正常任务者和玩家 NPC 通过可见后果验证规则。",
            "两名玩家 NPC 的公开姓名都必须沿用玩家代号，不得另起姓名。",
            "玩家 NPC 越接近主线核心，Boss/异常阵营越会控制、利用、杀死或替换对应角色。",
            "玩家一和玩家二只能通过符合 NPC 身份的反应、关系、线索、阻碍或求助推动任务者，不可直接剧透。",
            "正文仍固定玩家一视角，玩家二只能通过玩家一可见、可听、可交流的信息呈现。",
        ]
        raw["gm_secret"]["hidden_endings"] = [
            {"name": "身份无损清算", "condition": "玩家一和玩家二始终维持 NPC 身份，并让正常任务者完成主线关键进度。"},
            {"name": "暴露清算失败", "condition": "任一玩家主动说出系统/任务者/外来者真相，或两人的 NPC 身份被任务者与异常阵营同时识破。"},
        ]
        raw["instance_blueprint"]["logline"] = (blueprint_logline or "临时 NPC 在别人的副本里演好身份并推动主线。")[:240]
        raw["instance_blueprint"]["mainline"] = [
            {
                "phase": "入戏",
                "goal": "确认玩家一和玩家二的 NPC 身份、社会位置、关系、行动边界，以及正常任务者正在接近的公开任务。",
                "required_clues": [],
                "fail_forward": "如果玩家暂时无法推进，由副本人物、任务者误判、两人关系牵引或异常压力迫使他们做出符合身份的反应。",
                "notes": blueprint[:500],
            },
            {
                "phase": "推动",
                "goal": "玩家一和玩家二用 NPC 身份能做的事，间接给出线索、制造合理冲突或阻止错误路线。",
                "required_clues": [],
                "fail_forward": "线索错过时，用发病、问话、家族/组织关系、环境异变或任务者二次调查继续推进。",
            },
            {
                "phase": "收束",
                "goal": "正常任务者完成关键判断或通关节点，玩家一和玩家二避免暴露并等待主神确认清算。",
                "required_clues": [],
                "fail_forward": "若暴露风险过高，进入强制撤离、评级下降或清算失败结算。",
            },
        ]
        raw["instance_blueprint"]["hard_constraints"] = [
            "这是无限流惩罚副本，不是普通角色扮演剧本。",
            "玩家一和玩家二都不是正常任务者，不能按普通通关副本推进。",
            "两名玩家 NPC 公开姓名必须使用各自玩家代号，不能另起姓名。",
            "正常任务者的任务可以围绕玩家一、玩家二或两人的关系展开。",
            "正常任务者必须主动试探、误判、争执、隐瞒、求助或付出代价，不能只是背景板。",
            "规则必须通过行动验证，系统提示只在关键节点短促出现。",
            "失败要以暴露风险、威胁推进、任务者伤亡或异常加压继续剧情，不让剧情卡死。",
            "正文固定玩家一视角，玩家二不写成普通任务者。",
            "NPC 身份越核心，危险越高；不能写成安全旁观者。",
            "债务、污染、复活、契约只作为后端清算原因，不得写成剧情主线。",
            "不要替玩家做行动决定，不要直接剧透隐藏真相。",
        ]
    return _normalize_framework(raw)


def _tutorial_framework() -> dict:
    raw = {
        "instance_code": "T-000",
        "instance_name": "白箱回廊",
        "instance_genre": "剧情解密",
        "genre_note": "固定低危新手副本，用小说式开局和三段简单选择测试玩家行动倾向。",
        "difficulty": "D",
        "player_count": 2,
        "tasker_total": 2,
        "npc_taskers": [],
        "is_tutorial": True,
        "tutorial_id": _WENYOU_TUTORIAL_INSTANCE_ID,
        "tutorial_guides": [
            "新手副本没有其他任务者 NPC；不要临时生成同场任务者。",
            "开局按无限流小说写：玩家已经被扔进副本，不要写成表单、说明书或身份校准流程。",
            "本局只做三段低危测试：醒来观察、灯色规则、出口选择；每段最多给 2-3 个自然行动方向。",
            "允许玩家用观察、冲刺、保护同伴、询问系统、破坏面板、验证规则等方式通过；不同方式只影响核心能力倾向。",
            "若能判断行动倾向，在【事件意图】tags 或 state_proposals reason 中写 observe/escape/protect/combat/social/rule/resilience 之一，帮助后端生成核心能力画像。",
            "玩家卡住时给低压提示；失败只做轻微回弹或少量 HP/SAN 损耗，不死亡、不惩罚债务。",
        ],
        "world": (
            "玩家在一段没有窗户的白色回廊醒来。墙面干净得像未加载完成，地面嵌着红白两色光轨，远处有一扇没有把手的门。"
            "这里没有其他任务者，也没有怪物；危险来自误判、慌乱和对规则的忽视。主神系统只给极短提示，不解释全貌。"
        ),
        "player1_name": "玩家一",
        "player1_instance_name": "",
        "player1_role": "新任务者。",
        "player2_name": "玩家二",
        "player2_instance_name": "",
        "player2_role": "新任务者。",
        "conflict": "在白箱回廊中读懂红白灯规则，抵达尽头的门，并完成第一次副本返回。",
        "failure_hint": "错误行动只会触发回弹、短暂眩晕或少量 HP/SAN 损耗；不会触发死亡惩罚。",
        "reward_hint": "首次标准通关除基础通关奖励外，会额外发放新手大礼包。",
        "public": {
            "instance_name": "白箱回廊",
            "genre": ["剧情解密", "新手引导"],
            "difficulty": "D",
            "visible_rules": [
                "本副本没有其他任务者。",
                "红灯亮起时贸然前进会被回弹。",
                "白灯亮起时可以接近下一段回廊。",
                "出口不会考验唯一答案，只记录你解决问题的方式。",
            ],
            "public_task": "抵达白箱回廊尽头，找到开门方式并完成返回。",
        },
        "gm_secret": {
            "true_rules": [
                "第一段：玩家只要主动观察、放慢脚步、安抚同伴或询问系统，就能获得红白灯规则；直接冲刺会轻微回弹但仍给提示。",
                "第二段：玩家需要验证一次灯色节奏；可通过等待、试探、丢物、分工观察、询问玩家二或破坏小面板得到等价进展。",
                "第三段：出口记录玩家最偏好的解决方式；观察/逃脱/保护/破坏/社交/规则/抗压都能通关，不设唯一正确答案。",
            ],
            "false_rules": [],
            "npc_private_state": {},
            "hidden_endings": [],
        },
        "instance_blueprint": {
            "blueprint_version": 1,
            "logline": "玩家在醒来后的白色回廊中用自己的方式读懂规则，完成第一次返回。",
            "mainline": [
                {
                    "phase": "醒来",
                    "goal": "让玩家意识到自己身处副本，并对第一道红灯做出反应",
                    "required_clues": ["red_light_stops"],
                    "fail_forward": "如果玩家直接冲刺，触发轻微回弹并让系统屏补一句“红灯时请停下”。",
                    "reward_tags": ["observe", "escape", "protect", "social"],
                },
                {
                    "phase": "灯色规则",
                    "goal": "让玩家用等待、试探、检查、协作或强行处理理解红白灯节奏",
                    "required_clues": ["white_light_allows_entry"],
                    "fail_forward": "失败只扣少量 HP/SAN 或弹回原位，随后给出更明显的灯色变化。",
                    "reward_tags": ["rule", "combat", "resilience"],
                },
                {
                    "phase": "出口",
                    "goal": "让玩家选择一种开门方式，并记录其核心行动倾向",
                    "required_clues": ["exit_records_intent"],
                    "fail_forward": "任何有明确意图的行动都可以开门，只用叙事差异记录倾向。",
                    "reward_tags": ["observe", "escape", "protect", "combat", "social", "rule", "resilience"],
                },
            ],
            "side_quests": [],
            "hidden_side_quests": [],
            "hidden_endings": [],
            "clue_graph": [
                {"id": "red_light_stops", "public_text": "红灯亮起时，靠近门的人会被轻轻推回原位。", "leads_to": ["white_light_allows_entry"], "is_required_for_mainline": True},
                {"id": "white_light_allows_entry", "public_text": "白灯亮起时，光轨会稳定，下一段回廊可以进入。", "leads_to": ["exit_records_intent"], "is_required_for_mainline": True},
                {"id": "exit_records_intent", "public_text": "尽头的门并不要求固定答案，它会记录任务者最自然的解决方式。", "leads_to": [], "is_required_for_mainline": True},
            ],
            "npc_arcs": {},
            "threat_clocks": [{"id": "tutorial_mistakes", "name": "误操作累积", "value": 0, "max": 4, "visibility": "hidden"}],
            "hard_constraints": [
                "没有其他任务者 NPC",
                "不生成怪物",
                "不写死亡惩罚",
                "不要把新手副本写成表单、设置页或说明书",
                "每段都允许多种通过方式，只记录倾向差异",
                "完成主线后允许标准通关结算",
            ],
        },
        "encounter_profile": {
            "common": [],
            "elite": [],
            "boss": {},
            "spawn_rules": ["不生成怪物；误操作只用环境回弹和提示处理。"],
            "balance_notes": "低危教学副本，不使用怪物战斗。",
        },
        "initial_stats": {
            "points": 100,
            "player1": dict(_default_player_stats()),
            "player2": dict(_default_player_stats()),
            "items": [],
        },
        "opening": (
            "你醒来的时候，耳边先是一阵很轻的电流声。\n"
            "白光铺满视野，像有人把世界擦到只剩一种颜色。等眼前慢慢清晰，你发现自己站在一条没有窗户的回廊里，"
            "墙面干净得过分，地面嵌着两条细细的光轨，一红一白，安静地延伸到尽头。\n"
            "玩家二就在几步外，也刚睁开眼。远处有一扇没有把手的门，门上浮着一行黑字：\n"
            "【新手副本 T-000｜白箱回廊】\n"
            "【任务：抵达尽头的门。】\n"
            "第一盏红灯忽然亮起，脚下的白光往后一退，像是在提醒你们：别急着往前走。"
        ),
    }
    return _normalize_framework(raw)


def generate_framework_random(target_difficulty: Optional[str] = None) -> tuple[Optional[dict], Optional[str]]:
    tpl = _load_templates()
    worlds = tpl.get("worlds") or ["原创世界"]
    conflicts = tpl.get("conflicts") or ["一场冒险"]
    roles = tpl.get("roles") or ["旅人：在寻找某样东西"]
    genres = tpl.get("genres")
    if isinstance(genres, list) and genres:
        g0 = random.choice(genres)
        g_seed = str(g0).strip() if str(g0).strip() in _WENYOU_INSTANCE_GENRES else random.choice(list(_WENYOU_INSTANCE_GENRES))
    else:
        g_seed = random.choice(list(_WENYOU_INSTANCE_GENRES))
    seeds = {
        "difficulty": _normalize_difficulty(target_difficulty) if target_difficulty else random.choice(["D", "C", "B", "A", "S"]),
        "instance_genre": g_seed,
        "world": random.choice(worlds),
        "conflict": random.choice(conflicts),
        "role_a": random.choice(roles),
        "role_b": random.choice(roles),
    }
    user_prompt = _framework_prompt_random(seeds)
    text = call_wenyou_deepseek([{"role": "user", "content": user_prompt}], system=_FRAMEWORK_SYSTEM, temperature=0.85)
    if not text:
        return None, "文游：框架生成失败（DeepSeek 无响应），请检查 DEEPSEEK_API_KEY。"
    data = _extract_json_object(text)
    if not data:
        return None, "文游：框架解析失败，请重试开局。"
    return _normalize_framework(data), None


def generate_framework_from_candidate(candidate: Any) -> tuple[Optional[dict], Optional[str]]:
    """候选扩展：DS 只写文本块，后端组装结构，避免严格 JSON 脆弱解析。"""
    item = _normalize_candidate_item(candidate, 0)
    if not item:
        return None, "文游：候选设定为空，无法扩展。"
    if _is_tutorial_candidate(item):
        return _tutorial_framework(), None

    started = time.monotonic()
    core_text = call_wenyou_deepseek(
        [{"role": "user", "content": _candidate_core_prompt(item)}],
        _FRAMEWORK_SYSTEM,
        0.78,
        75,
    )
    if not core_text:
        return None, "文游：候选扩展失败（core 无响应）。"
    core_text = _clean_ds_block(core_text, 1200)
    if not core_text:
        return None, "文游：候选扩展失败（core 为空）。"

    jobs = {
        "blueprint": (_candidate_blueprint_prompt(item, core_text), 0.72, 75),
        "opening": (_candidate_opening_prompt(item, core_text), 0.82, 75),
    }
    outputs: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="wenyou-expand") as pool:
        futures = {
            pool.submit(
                call_wenyou_deepseek,
                [{"role": "user", "content": prompt}],
                _FRAMEWORK_SYSTEM,
                temperature,
                timeout,
            ): name
            for name, (prompt, temperature, timeout) in jobs.items()
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                text = fut.result()
            except Exception as e:
                logger.warning("文游候选扩展子任务失败 part=%s error=%s", name, e, exc_info=True)
                return None, f"文游：候选扩展失败（{name} 异常）。"
            if not text:
                return None, f"文游：候选扩展失败（{name} 无响应）。"
            clean = _clean_ds_block(text, 1400 if name == "blueprint" else 900)
            if not clean:
                return None, f"文游：候选扩展失败（{name} 为空）。"
            outputs[name] = clean

    fw = _framework_from_candidate_text(
        item,
        core_text,
        outputs.get("blueprint") or "",
        outputs.get("opening") or "",
    )
    logger.info("文游候选扩展完成 candidate=%s elapsed=%.2fs", item.get("id"), time.monotonic() - started)
    return fw, None


def generate_framework_custom(keywords: str) -> tuple[Optional[dict], Optional[str]]:
    if not keywords.strip():
        return None, "文游：请填写任务描述，例如：赛博朋克 无限流"
    user_prompt = _framework_prompt_custom(keywords.strip())
    text = call_wenyou_deepseek([{"role": "user", "content": user_prompt}], system=_FRAMEWORK_SYSTEM, temperature=0.85)
    if not text:
        return None, "文游：框架生成失败（DeepSeek 无响应）。"
    data = _extract_json_object(text)
    if not data:
        return None, "文游：框架解析失败，请重试。"
    return _normalize_framework(data), None

def _new_session(framework: dict) -> dict:
    gid = str(uuid4())
    ts = now_beijing_iso()
    opening = framework.get("opening") or "【主神提示】副本同步完成。白光散去，你们已抵达任务区域。"
    fw = _framework_for_runtime(framework)
    session = {
        "gameId": gid,
        "startedAt": ts,
        "phase": "instance_running",
        "framework": framework,
        "stats": _stats_runtime_from_framework(fw),
        "clocks": [],
        "event_log": [],
        "last_state_patch": None,
        "history": [
            {"role": "gm", "content": opening, "timestamp": ts},
        ],
        "pending_round": {"player1_lines": [], "player2_lines": []},
    }
    session["runtime_state"] = _runtime_state_view(session)
    return session


def _format_framework_lines(fw: dict) -> str:
    fw = _framework_for_runtime(fw)
    def _show_name(real_name: str, instance_name: str) -> str:
        rn = str(real_name or "").strip()
        inn = str(instance_name or "").strip()
        if inn and inn != rn:
            return f"{rn}（{inn}）"
        return rn

    ic = (fw.get("instance_code") or "").strip()
    inn = (fw.get("instance_name") or "").strip()
    if ic and inn and ic != "—":
        head = f"【无限流 · 副本 {ic}｜{inn}】\n"
    elif inn:
        head = f"【无限流 · 副本｜{inn}】\n"
    elif ic and ic != "—":
        head = f"【无限流 · 副本 {ic}】\n"
    else:
        head = "【无限流 · 副本】\n"
    diff = _normalize_difficulty(fw.get("difficulty"))
    g = _normalize_instance_genre(fw.get("instance_genre"))
    gn = str(fw.get("genre_note") or "").strip()
    pc = _normalize_player_count(fw)
    total = _normalize_tasker_total(fw, pc)
    npc_count = max(0, total - pc)
    genre_head = f"【副本类型】{g}" + (f"｜{gn}" if gn else "") + "\n\n"
    npc_lines = []
    for i, n in enumerate(fw.get("npc_taskers") or []):
        if isinstance(n, dict):
            nshow = _show_name(n.get("name", ""), n.get("instance_name", ""))
            npc_lines.append(
                f"  · NPC{i+1}「{nshow}」{n.get('tier_note', '')}｜{n.get('stance', '')}｜{n.get('blurb', '')}"
            )
    npc_block = "\n".join(npc_lines) if npc_lines else "  （无）"
    return (
        f"{head}"
        f"【难度】{diff}（D 最低，S 最高）\n"
        f"{genre_head}"
        f"【任务者（共 {total} 人：玩家 {pc} + NPC {npc_count}）】\n"
        f"· 玩家一「{_show_name(fw.get('player1_name', '玩家一'), fw.get('player1_instance_name', ''))}」\n{fw.get('player1_role', '')}\n\n"
        f"· 玩家二「{_show_name(fw.get('player2_name', '玩家二'), fw.get('player2_instance_name', ''))}」\n{fw.get('player2_role', '')}\n\n"
        f"【NPC 任务者】\n{npc_block}\n\n"
        f"【副本场景】\n{fw.get('world', '')}\n\n"
        f"【主神任务】\n{fw.get('conflict', '')}\n\n"
        f"【失败倾向】\n{fw.get('failure_hint', '')}\n\n"
        f"【通关回报（风味）】\n{fw.get('reward_hint', '')}"
    )


def _format_player_opening_header(fw: dict) -> str:
    fw = _framework_for_runtime(fw)
    ic = (fw.get("instance_code") or "").strip()
    inn = (fw.get("instance_name") or "").strip()
    if ic and inn and ic != "—":
        head = f"【无限流 · 副本 {ic}｜{inn}】"
    elif inn:
        head = f"【无限流 · 副本｜{inn}】"
    elif ic and ic != "—":
        head = f"【无限流 · 副本 {ic}】"
    else:
        head = "【无限流 · 副本】"
    return f"{head}\n【副本类型】{_normalize_instance_genre(fw.get('instance_genre'))}｜【难度】{_normalize_difficulty(fw.get('difficulty'))}"


def _framework_instance_line(fw: dict) -> str:
    c = (fw.get("instance_code") or "").strip()
    n = (fw.get("instance_name") or "").strip()
    if c and n and c != "—":
        return f"{c} · {n}"
    if n:
        return n
    if c and c != "—":
        return c
    return "未命名副本"


def _panel_object_id(value: Any, prefix: str, index: int = 0) -> str:
    raw = _compact_text(value, 80)
    if not raw:
        return f"{prefix}_{index + 1}"
    slug = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "_", raw).strip("_")
    return (slug or f"{prefix}_{index + 1}")[:80]


def _normalize_public_task_item(item: Any, index: int, phase: str = "instance_running") -> Optional[dict]:
    status = "completed" if phase in {"settlement", "archived"} else "active"
    if isinstance(item, dict):
        title = _compact_text(item.get("title") or item.get("current") or item.get("goal") or item.get("public_text"), 160)
        if not title:
            return None
        progress = item.get("progress") if isinstance(item.get("progress"), dict) else {}
        return {
            "id": _panel_object_id(item.get("id") or title, "task", index),
            "title": title,
            "type": _compact_text(item.get("type") or "main", 40),
            "status": _compact_text(item.get("status") or status, 40),
            "progress": progress,
            "required_clues": _normalize_text_list(item.get("required_clues"), 80, 12),
            "related_clues": _normalize_text_list(item.get("related_clues"), 80, 12),
            "fail_forward": _compact_text(item.get("fail_forward"), 220),
            "reward_tags": _normalize_text_list(item.get("reward_tags"), 60, 12),
        }
    title = _compact_text(item, 160)
    if not title:
        return None
    return {
        "id": _panel_object_id(title, "task", index),
        "title": title,
        "type": "main" if index == 0 else "side",
        "status": status,
        "progress": {},
        "required_clues": [],
        "related_clues": [],
        "fail_forward": "",
        "reward_tags": [],
    }


def _normalize_public_clue_item(item: Any, index: int) -> Optional[dict]:
    if isinstance(item, str):
        raw = item.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                parsed = None
            if isinstance(parsed, dict):
                item = parsed
    if isinstance(item, dict):
        title = _compact_text(item.get("title") or item.get("name") or item.get("public_text") or item.get("text"), 120)
        text = _compact_text(item.get("public_text") or item.get("text") or item.get("reason") or title, 220)
        if not title and not text:
            return None
        return {
            "id": _panel_object_id(item.get("id") or title or text, "clue", index),
            "title": title or text,
            "status": _compact_text(item.get("status") or ("verified" if item.get("verified") else "discovered"), 40),
            "verified": bool(item.get("verified")),
            "source": _compact_text(item.get("source"), 80),
            "related_tasks": _normalize_text_list(item.get("related_tasks"), 80, 12),
            "leads_to": _normalize_text_list(item.get("leads_to"), 80, 12),
            "tags": _normalize_text_list(item.get("tags"), 40, 12),
            "public_text": text,
        }
    text = _compact_text(item, 220)
    if not text:
        return None
    return {
        "id": _panel_object_id(text, "clue", index),
        "title": text[:40],
        "status": "discovered",
        "verified": False,
        "source": "",
        "related_tasks": [],
        "leads_to": [],
        "tags": [],
        "public_text": text,
    }


def _normalize_public_marker_item(item: Any, index: int, prefix: str) -> Optional[dict]:
    if isinstance(item, dict):
        title = _compact_text(item.get("name") or item.get("title") or item.get("id"), 120)
        text = _compact_text(item.get("public_text") or item.get("desc") or item.get("blurb") or item.get("reason") or item.get("status"), 240)
        if not title and not text:
            return None
        out = {
            "id": _panel_object_id(item.get("id") or title or text, prefix, index),
            "name": title or text[:40],
            "status": _compact_text(item.get("status") or item.get("public_status"), 80),
            "public_text": text,
        }
        for key in (
            "danger",
            "last_location",
            "attitude",
            "weakness",
            "type",
            "tier",
            "rank",
            "stability",
            "stability_max",
            "seal_progress",
            "seal_target",
            "weaknesses",
            "counterplay",
        ):
            if item.get(key) is not None and item.get(key) != "":
                out[key] = item.get(key) if isinstance(item.get(key), (int, float, list)) else _compact_text(item.get(key), 120)
        return out
    text = _compact_text(item, 240)
    if not text:
        return None
    return {"id": _panel_object_id(text, prefix, index), "name": text[:40], "status": "", "public_text": text}


def _merge_panel_list(existing: Any, additions: list[dict], prefix: str, limit: int = 40) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for idx, item in enumerate(existing if isinstance(existing, list) else []):
        norm = (
            _normalize_public_task_item(item, idx)
            if prefix == "task"
            else _normalize_public_clue_item(item, idx)
            if prefix == "clue"
            else _normalize_public_marker_item(item, idx, prefix)
        )
        if norm:
            key = str(norm.get("id") or norm.get("title") or norm.get("name"))
            seen.add(key)
            out.append(norm)
    for item in additions:
        key = str(item.get("id") or item.get("title") or item.get("name"))
        if key in seen:
            for idx, cur in enumerate(out):
                if str(cur.get("id") or cur.get("title") or cur.get("name")) == key:
                    out[idx] = {**cur, **item}
                    break
            continue
        seen.add(key)
        out.append(item)
    return out[-limit:]


def _public_threat_label(session: dict) -> str:
    clocks = session.get("clocks") if isinstance(session.get("clocks"), list) else []
    ratios: list[float] = []
    for item in clocks:
        if not isinstance(item, dict):
            continue
        max_value = max(1, int(item.get("max") or 1))
        ratios.append(max(0.0, min(1.0, float(item.get("value") or 0) / max_value)))
    if not ratios:
        return "平稳"
    ratio = max(ratios)
    if ratio >= 1:
        return "接近清算"
    if ratio >= 0.67:
        return "高危"
    if ratio >= 0.34:
        return "升高"
    return "平稳"


def _public_clock_status(clock: Any) -> str:
    if not isinstance(clock, dict):
        return "未知"
    max_value = max(1, int(clock.get("max") or 1))
    ratio = max(0.0, min(1.0, float(clock.get("value") or 0) / max_value))
    if ratio >= 1:
        return "已满"
    if ratio >= 0.67:
        return "高危"
    if ratio >= 0.34:
        return "升高"
    if ratio > 0:
        return "轻微"
    return "平稳"


def _public_clue_lines_from_history(session: dict) -> list[str]:
    headings = (
        "规则备忘",
        "线索备忘",
        "安全区·威胁备忘",
        "阵营备忘",
        "撤离·物资备忘",
        "身份·嫌疑备忘",
        "时限备忘",
    )
    for h in reversed(session.get("history") or []):
        if isinstance(h, dict) and h.get("role") == "gm":
            lines = _extract_brief_block(str(h.get("content") or ""), headings)
            if lines:
                return lines
    return []


def _public_state_from_session(session: dict) -> dict:
    fw = _framework_for_runtime(session.get("framework") or {})
    phase = _session_phase(session)
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    public = copy.deepcopy(runtime.get("public_state") if isinstance(runtime.get("public_state"), dict) else {})
    existing_tasks = public.get("public_tasks") if isinstance(public.get("public_tasks"), list) else []
    tasks = [_normalize_public_task_item(item, i, phase) for i, item in enumerate(existing_tasks)]
    tasks = [x for x in tasks if x]
    if not tasks:
        tasks = [
            {
                "id": "main_task",
                "title": _compact_text(fw.get("public", {}).get("public_task") if isinstance(fw.get("public"), dict) else fw.get("conflict"), 160)
                or "确认副本规则，找到通关路径并存活。",
                "type": "main",
                "status": "completed" if phase in {"settlement", "archived"} else "active",
                "progress": {},
                "required_clues": [],
                "related_clues": [],
                "fail_forward": _compact_text(fw.get("failure_hint"), 220),
                "reward_tags": ["mainline"],
            }
        ]
    clues_raw = public.get("discovered_clues") if isinstance(public.get("discovered_clues"), list) else []
    clues = [_normalize_public_clue_item(item, i) for i, item in enumerate(clues_raw)]
    locations_raw = public.get("known_locations") if isinstance(public.get("known_locations"), list) else []
    locations = [_normalize_public_marker_item(item, i, "location") for i, item in enumerate(locations_raw)]
    locations = [x for x in locations if x]
    if not locations and fw.get("world"):
        locations = [
            {
                "id": "current_location",
                "name": "当前场景",
                "status": "known",
                "danger": _public_threat_label(session),
                "public_text": _compact_text(fw.get("world"), 260),
            }
        ]
    npcs_raw = public.get("visible_npcs") if isinstance(public.get("visible_npcs"), list) else fw.get("npc_taskers") or []
    npcs = [_normalize_public_marker_item(item, i, "npc") for i, item in enumerate(npcs_raw)]
    encounter = fw.get("encounter_profile") if isinstance(fw.get("encounter_profile"), dict) else {}
    monsters_raw = public.get("visible_monsters") if isinstance(public.get("visible_monsters"), list) else []
    if not monsters_raw and isinstance(encounter.get("boss"), dict) and encounter.get("boss"):
        boss = encounter.get("boss") or {}
        monsters_raw = [
            {
                "id": "boss",
                "name": boss.get("name") or "核心压力源",
                "status": "未完全显现",
                "public_text": "Boss 默认不可正面硬杀，优先寻找削弱、封印、规避或撤离条件。",
                "weakness": "待验证",
            }
        ]
    monsters = [_normalize_public_marker_item(item, i, "monster") for i, item in enumerate(monsters_raw)]
    public.update(
        {
            "scene_summary": _compact_text(public.get("scene_summary") or fw.get("world"), 260),
            "visible_rules": _normalize_text_list(public.get("visible_rules") or (fw.get("public") or {}).get("visible_rules"), 180, 12)
            if isinstance(fw.get("public"), dict)
            else _normalize_text_list(public.get("visible_rules"), 180, 12),
            "public_tasks": tasks[:20],
            "discovered_clues": [x for x in clues if x][:40],
            "known_locations": locations[:20],
            "visible_npcs": [x for x in npcs if x][:20],
            "visible_monsters": [x for x in monsters if x][:20],
            "public_threat": _compact_text(public.get("public_threat") or _public_threat_label(session), 80),
            "last_rules_result": _compact_text(public.get("last_rules_result"), 260),
        }
    )
    return public


def _rules_state_from_session(session: dict) -> dict:
    _session_ensure_stats(session)
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    existing = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    monster_instances = [dict(x) for x in existing.get("monster_instances") or [] if isinstance(x, dict)]
    return {
        **copy.deepcopy(existing),
        "players": {"player1": st.get("player1") or {}, "player2": st.get("player2") or {}},
        "inventory": _normalize_inventory(st.get("inventory"), source="session"),
        "inventories": copy.deepcopy(st.get("inventories") if isinstance(st.get("inventories"), dict) else {}),
        "task_progress": _rules_mapping(existing.get("task_progress"), "task"),
        "clue_state": _rules_mapping(existing.get("clue_state"), "clue"),
        "location_state": _rules_mapping(existing.get("location_state"), "location"),
        "npc_state": _rules_mapping(existing.get("npc_state"), "npc"),
        "monster_instances": monster_instances[:20],
        "forced_instance": copy.deepcopy(session.get("forced_instance")) if isinstance(session.get("forced_instance"), dict) else existing.get("forced_instance"),
        "rule_violations": [dict(x) for x in existing.get("rule_violations") or [] if isinstance(x, dict)][-80:],
        "settlement_flags": _settlement_flags_from_raw(existing.get("settlement_flags")),
        "reward_context": _reward_context_from_raw(existing.get("reward_context")),
        "threat_clocks": list(session.get("clocks") or []),
        "last_state_patch": session.get("last_state_patch") if isinstance(session.get("last_state_patch"), dict) else None,
    }


def _runtime_state_view(session: dict) -> dict:
    runtime = copy.deepcopy(session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {})
    runtime["public_state"] = _public_state_from_session(session)
    runtime["rules_state"] = _rules_state_from_session(session)
    runtime.setdefault("gm_state", {})
    runtime.setdefault("runtime_indexes", {})
    runtime["last_state_patch"] = session.get("last_state_patch") if isinstance(session.get("last_state_patch"), dict) else None
    return runtime


def _client_state_patch_view(patch: Any) -> Optional[dict]:
    if not isinstance(patch, dict):
        return None
    out = copy.deepcopy(patch)
    changes = out.get("changes") if isinstance(out.get("changes"), dict) else {}
    for key in ("clock_updates", "threat_clocks"):
        raw_updates = changes.get(key)
        if isinstance(raw_updates, list):
            changes[key] = [
                {"id": c.get("id"), "name": c.get("name"), "status": _public_clock_status(c)}
                for c in raw_updates
                if isinstance(c, dict)
            ]
    out["changes"] = changes
    return out


def _client_rules_state_view(rules: Any) -> dict:
    data = rules if isinstance(rules, dict) else {}

    def public_only(raw: Any, prefix: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for key, item in _rules_mapping(raw, prefix).items():
            if str(item.get("visibility") or "public") == "hidden":
                continue
            out[key] = dict(item)
        return out

    monsters: list[dict] = []
    for monster in data.get("monster_instances") or []:
        if not isinstance(monster, dict):
            continue
        monsters.append(
            {
                "id": monster.get("id"),
                "name": monster.get("name"),
                "tier": monster.get("tier"),
                "rank": monster.get("rank"),
                "status": monster.get("status"),
                "public_text": monster.get("public_text"),
                "weaknesses": monster.get("weaknesses") or [],
                "counterplay": monster.get("counterplay") or [],
                "stability": monster.get("stability"),
                "stability_max": monster.get("stability_max"),
                "seal_progress": monster.get("seal_progress"),
                "seal_target": monster.get("seal_target"),
                "default_invincible": bool(monster.get("default_invincible")),
                "can_be_killed": bool(monster.get("can_be_killed")),
            }
        )
    flags = _settlement_flags_from_raw(data.get("settlement_flags"))
    return {
        "players": data.get("players") if isinstance(data.get("players"), dict) else {},
        "inventory": _normalize_inventory(data.get("inventory"), source="session"),
        "inventories": copy.deepcopy(data.get("inventories") if isinstance(data.get("inventories"), dict) else {}),
        "task_progress": public_only(data.get("task_progress"), "task"),
        "clue_state": public_only(data.get("clue_state"), "clue"),
        "location_state": public_only(data.get("location_state"), "location"),
        "npc_state": public_only(data.get("npc_state"), "npc"),
        "monster_instances": monsters[:20],
        "forced_instance": copy.deepcopy(data.get("forced_instance")) if isinstance(data.get("forced_instance"), dict) else None,
        "settlement_flags": {
            "mainline_status": flags.get("mainline_status"),
            "mainline_completion": flags.get("mainline_completion"),
            "side_completed": flags.get("side_completed") or [],
            "achievements": flags.get("achievements") or [],
        },
        "threat_clocks": [
            {"id": c.get("id"), "name": c.get("name"), "status": _public_clock_status(c)}
            for c in data.get("threat_clocks") or []
            if isinstance(c, dict)
        ][:20],
        "last_state_patch": _client_state_patch_view(data.get("last_state_patch")),
    }


def _apply_public_state_updates(session: dict, event_intent: dict) -> dict:
    if not isinstance(event_intent, dict):
        return {}
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    public = _public_state_from_session(session)
    phase = _session_phase(session)
    task_add: list[dict] = []
    clue_add: list[dict] = []
    location_add: list[dict] = []
    npc_add: list[dict] = []
    monster_add: list[dict] = []

    if event_intent.get("task_update"):
        task_add.append(
            {
                "id": "current_task_update",
                "title": _compact_text(event_intent.get("task_update"), 160),
                "type": "main",
                "status": "completed" if phase in {"settlement", "archived"} else "active",
                "progress": {"text": _compact_text(event_intent.get("task_update"), 180)},
                "required_clues": [],
                "related_clues": [],
                "fail_forward": "",
                "reward_tags": ["mainline"],
            }
        )
    for idx, text in enumerate(event_intent.get("clue_updates") or []):
        clue = _normalize_public_clue_item(text, idx)
        if clue:
            clue_add.append(clue)
    for proposal in event_intent.get("state_proposals") or []:
        if not isinstance(proposal, dict) or proposal.get("visibility") != "public":
            continue
        ptype = str(proposal.get("type") or "")
        if ptype in {"discover_clue", "verify_clue"}:
            clue = _normalize_public_clue_item(
                {
                    "id": proposal.get("id") or proposal.get("name"),
                    "title": proposal.get("name") or proposal.get("id"),
                    "public_text": proposal.get("reason") or proposal.get("name") or proposal.get("id"),
                    "status": "verified" if ptype == "verify_clue" else "discovered",
                    "verified": ptype == "verify_clue",
                },
                len(clue_add),
            )
            if clue:
                clue_add.append(clue)
        elif ptype == "task_update":
            task = _normalize_public_task_item(
                {
                    "id": proposal.get("id") or proposal.get("name") or "task_update",
                    "title": proposal.get("name") or proposal.get("reason") or proposal.get("id"),
                    "status": "active",
                    "progress": {"text": proposal.get("reason") or ""},
                },
                len(task_add),
                phase,
            )
            if task:
                task_add.append(task)
        elif ptype == "location_update":
            item = _normalize_public_marker_item(proposal, len(location_add), "location")
            if item:
                location_add.append(item)
        elif ptype == "npc_update":
            item = _normalize_public_marker_item(proposal, len(npc_add), "npc")
            if item:
                npc_add.append(item)
        elif ptype == "monster_update":
            item = _normalize_public_marker_item(proposal, len(monster_add), "monster")
            if item:
                monster_add.append(item)

    public["public_tasks"] = _merge_panel_list(public.get("public_tasks"), task_add, "task", 20)
    public["discovered_clues"] = _merge_panel_list(public.get("discovered_clues"), clue_add, "clue", 40)
    public["known_locations"] = _merge_panel_list(public.get("known_locations"), location_add, "location", 20)
    public["visible_npcs"] = _merge_panel_list(public.get("visible_npcs"), npc_add, "npc", 20)
    public["visible_monsters"] = _merge_panel_list(public.get("visible_monsters"), monster_add, "monster", 20)
    public["public_threat"] = _public_threat_label(session)
    runtime["public_state"] = public
    runtime["rules_state"] = _rules_state_from_session(session)
    runtime.setdefault("gm_state", {})
    runtime.setdefault("runtime_indexes", {})
    session["runtime_state"] = runtime
    return {
        "task_updates": task_add,
        "clue_updates": clue_add,
        "location_updates": location_add,
        "npc_updates": npc_add,
        "monster_updates": monster_add,
    }


def cmd_story(user_id: int, keywords: Optional[str]) -> str:
    """处理开局请求；含二次确认逻辑。"""
    uid = int(user_id)
    existing = r2_store.get_wenyou_session(uid)

    with _PENDING_LOCK:
        pending = _PENDING_STORY_CONFIRM.get(uid, False)

    if existing and existing.get("gameId"):
        if not pending:
            with _PENDING_LOCK:
                _PENDING_STORY_CONFIRM[uid] = True
            return "文游：已有进行中的局。若确定要开新局，请再提交一次开局请求（会丢弃当前进度）。"
        # 第二次确认
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)

    wallet = _load_wenyou_wallet(uid)
    if not (keywords and keywords.strip()) and _should_offer_tutorial(uid, wallet):
        fw, err = _tutorial_framework(), None
    elif keywords and keywords.strip():
        fw, err = generate_framework_custom(keywords)
    else:
        fw, err = generate_framework_random(_difficulty_from_progress(uid))
    if err or not fw:
        return err or "文游：开局失败。"

    fw = _apply_wallet_player_names_to_framework(fw, wallet)
    session = _new_session(fw)
    wallet = _load_wenyou_wallet(uid, session)
    _mark_tutorial_started(uid, session, wallet)
    _sync_session_points_with_wallet(session, wallet)
    session.setdefault("stats", {})["inventory"] = _merge_inventory(wallet.get("inventory"), session.get("stats", {}).get("inventory"))
    _attach_forced_instance_contract(session, {})
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    head = _format_player_opening_header(fw) + "\n\n"
    return head + fw.get("opening", "")


def cmd_story_from_candidate(user_id: int, candidate: Any) -> str:
    """处理大厅候选扩展开局；完整副本框架由并行 DS 子任务生成。"""
    uid = int(user_id)
    item = _normalize_candidate_item(candidate, 0)
    if not item:
        return "文游：候选设定为空，无法扩展。"
    existing = r2_store.get_wenyou_session(uid)

    with _PENDING_LOCK:
        pending = _PENDING_STORY_CONFIRM.get(uid, False)

    if existing and existing.get("gameId"):
        if not pending:
            with _PENDING_LOCK:
                _PENDING_STORY_CONFIRM[uid] = True
            return "文游：已有进行中的局。若确定要开新局，请再提交一次开局请求（会丢弃当前进度）。"
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)

    wallet = _load_wenyou_wallet(uid)
    item["player1_name_hint"] = _wallet_player_display_name(wallet, "player1", "玩家一")
    item["player2_name_hint"] = _wallet_player_display_name(wallet, "player2", "玩家二")

    fw = _take_cached_forced_framework(wallet, item) if item.get("forced") else None
    if fw:
        _save_wenyou_wallet(uid, wallet)
        err = None
        logger.info("文游使用惩罚副本预热框架 user_id=%s candidate=%s", uid, item.get("id"))
    else:
        fw, err = generate_framework_from_candidate(item)
        if err or not fw:
            return err or "文游：候选扩展开局失败。"

    fw = _apply_wallet_player_names_to_framework(fw, wallet)
    session = _new_session(fw)
    wallet = _load_wenyou_wallet(uid, session)
    _mark_tutorial_started(uid, session, wallet)
    _sync_session_points_with_wallet(session, wallet)
    session.setdefault("stats", {})["inventory"] = _merge_inventory(wallet.get("inventory"), session.get("stats", {}).get("inventory"))
    _attach_forced_instance_contract(session, item)
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    head = _format_player_opening_header(fw) + "\n\n"
    return head + fw.get("opening", "")


def _story_open_failed(text: str) -> bool:
    t = str(text or "")
    if not t.startswith("文游："):
        return False
    return any(k in t for k in ("失败", "无响应", "解析失败", "无法扩展", "开局失败", "异常"))


def _story_job_public(job: dict) -> dict:
    return {
        "job_id": str(job.get("job_id") or ""),
        "status": str(job.get("status") or "running"),
        "startedAt": str(job.get("startedAt") or ""),
        "finishedAt": str(job.get("finishedAt") or ""),
        "text": str(job.get("text") or ""),
        "error": str(job.get("error") or ""),
        "need_confirm_new_game": bool(job.get("need_confirm_new_game")),
        "candidate": job.get("candidate") if isinstance(job.get("candidate"), dict) else None,
    }


def _cleanup_story_jobs_locked() -> None:
    now_ts = time.time()
    stale = [
        jid
        for jid, job in _STORY_EXPANSION_JOBS.items()
        if now_ts - float(job.get("created_ts") or now_ts) > _STORY_EXPANSION_JOB_TTL_SECONDS
    ]
    for jid in stale:
        _STORY_EXPANSION_JOBS.pop(jid, None)


def start_story_candidate_expansion_job(user_id: int, candidate: Any) -> tuple[Optional[dict], Optional[str]]:
    """启动候选扩展后台任务；HTTP 立即返回，前端轮询结果。"""
    uid = int(user_id)
    item = _normalize_candidate_item(candidate, 0)
    if not item:
        return None, "文游：候选设定为空，无法扩展。"
    job_id = str(uuid4())
    now = now_beijing_iso()
    job = {
        "job_id": job_id,
        "user_id": uid,
        "status": "running",
        "startedAt": now,
        "finishedAt": "",
        "created_ts": time.time(),
        "candidate": item,
        "text": "",
        "error": "",
        "need_confirm_new_game": False,
    }
    with _STORY_EXPANSION_JOBS_LOCK:
        _cleanup_story_jobs_locked()
        _STORY_EXPANSION_JOBS[job_id] = job

    def _run() -> None:
        try:
            text = cmd_story_from_candidate(uid, item)
            finished = now_beijing_iso()
            need_confirm = "若确定要开新局" in (text or "")
            status = "confirm" if need_confirm else ("failed" if _story_open_failed(text) else "done")
            with _STORY_EXPANSION_JOBS_LOCK:
                cur = _STORY_EXPANSION_JOBS.get(job_id)
                if cur is not None:
                    cur.update(
                        {
                            "status": status,
                            "finishedAt": finished,
                            "text": "" if status == "failed" else str(text or ""),
                            "error": str(text or "") if status == "failed" else "",
                            "need_confirm_new_game": need_confirm,
                        }
                    )
        except Exception as e:
            logger.warning("文游候选扩展后台任务失败 job_id=%s error=%s", job_id, e, exc_info=True)
            with _STORY_EXPANSION_JOBS_LOCK:
                cur = _STORY_EXPANSION_JOBS.get(job_id)
                if cur is not None:
                    cur.update(
                        {
                            "status": "failed",
                            "finishedAt": now_beijing_iso(),
                            "error": f"文游：候选扩展失败（{e}）。",
                            "text": "",
                        }
                    )

    threading.Thread(target=_run, name=f"wenyou-story-expand-{job_id[:8]}", daemon=True).start()
    return _story_job_public(job), None


def get_story_expansion_job(user_id: int, job_id: str) -> Optional[dict]:
    uid = int(user_id)
    jid = str(job_id or "").strip()
    if not jid:
        return None
    with _STORY_EXPANSION_JOBS_LOCK:
        _cleanup_story_jobs_locked()
        job = _STORY_EXPANSION_JOBS.get(jid)
        if not job or int(job.get("user_id") or -1) != uid:
            return None
        return _story_job_public(dict(job))


def _history_item_for_view(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    role = str(item.get("role") or "").strip()
    content = str(item.get("content") or "").strip()
    if not role or not content:
        return None
    if role == "gm":
        content = _strip_main_god_panel(content)
    if not content.strip():
        return None
    return {
        "role": role,
        "content": content[:6000],
        "timestamp": str(item.get("timestamp") or ""),
    }


def _extract_brief_block(text: str, headings: tuple[str, ...]) -> list[str]:
    """从 GM 文本里抓规则/线索/时限等备忘块，给前端线索板用。"""
    if not text:
        return []
    body = _strip_main_god_panel(text)
    for heading in headings:
        marker = f"【{heading}】"
        if marker not in body:
            continue
        tail = body.split(marker, 1)[-1]
        tail = re.split(r"\n\s*【[^】]{2,24}】", tail, maxsplit=1)[0]
        lines = []
        for raw in tail.splitlines():
            line = re.sub(r"^\s*[-*·\d.、]+\s*", "", raw).strip()
            if line:
                lines.append(line[:160])
        if lines:
            return lines[:8]
    return []


def _clues_from_session(session: dict) -> list[str]:
    public = _public_state_from_session(session)
    out: list[str] = []
    for item in public.get("discovered_clues") or []:
        if isinstance(item, dict):
            text = _compact_text(item.get("title") or item.get("public_text") or item.get("text") or item.get("id"), 160)
        else:
            text = _compact_text(item, 160)
        if text and text not in out:
            out.append(text)
    return out[:8]


def _compact_text(value: Any, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit > 0 and len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _player_summary_for_card(player: Any) -> str:
    p = player if isinstance(player, dict) else {}
    core = _normalize_core_ability(p.get("core_ability"))
    ability_name = core.get("name") if core else "无"
    return (
        f"HP {p.get('hp', 0)}/{p.get('hp_max', 0)}，SAN {p.get('san', 0)}/{p.get('san_max', 0)}，精神力 {p.get('spi_current', 0)}/{p.get('spi_max', 0)}，"
        f"Lv{p.get('level', 1)}·{p.get('rank', 'D')}阶，EXP {p.get('exp', 0)}，"
        f"力{p.get('str', 0)}/体{p.get('con', p.get('vit', 0))}/敏{p.get('agi', 0)}/智{p.get('int', p.get('wis', 0))}/精{p.get('spi', 0)}/运{p.get('luk', 0)}，"
        f"核心能力：{ability_name}"
    )


def _current_instance_for_card(session: dict) -> dict:
    _session_ensure_stats(session)
    fw = _framework_for_runtime(session.get("framework") or {})
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    inventory = [_compact_text(x, 40) for x in _inventory_label_list(st.get("inventory"))][:20]
    return {
        "game_id": _compact_text(session.get("gameId"), 80),
        "instance": _compact_text(_framework_instance_line(fw), 120),
        "genre": _normalize_instance_genre(fw.get("instance_genre")),
        "difficulty": _normalize_difficulty(fw.get("difficulty")),
        "task": _compact_text(fw.get("conflict"), 260),
        "phase": _phase_label(_session_phase(session)),
        "points": int(st.get("points") or 0),
        "player1": _player_summary_for_card(st.get("player1")),
        "player2": _player_summary_for_card(st.get("player2")),
        "inventory": inventory,
        "clues": [_compact_text(x, 160) for x in _clues_from_session(session)[:8]],
    }


def _normalize_wenyou_card(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    now = now_beijing_iso()

    def _list_text(items: Any, item_limit: int, count_limit: int) -> list[str]:
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for item in items[:count_limit]:
            text = _compact_text(item, item_limit)
            if text:
                out.append(text)
        return out

    recent: list[dict] = []
    for item in data.get("recent_rounds") or []:
        if not isinstance(item, dict):
            continue
        gm_result = _compact_text(item.get("gm_result"), 700)
        if not gm_result:
            continue
        recent.append(
            {
                "at": _compact_text(item.get("at"), 40),
                "instance": _compact_text(item.get("instance"), 120),
                "xinyue_action": _compact_text(item.get("xinyue_action"), 260),
                "ai_player_action": _compact_text(item.get("ai_player_action"), 260),
                "gm_result": gm_result,
                "clues": _list_text(item.get("clues"), 160, 8),
                "inventory": _list_text(item.get("inventory"), 40, 20),
            }
        )
    cur = data.get("current_instance") if isinstance(data.get("current_instance"), dict) else {}
    return {
        "version": 1,
        "scope": "wenyou_game_only",
        "note": "App 文游/无限流跑团的虚构游戏连续性卡片，只供文游上下文使用，不参与动态召回。",
        "current_instance": cur,
        "recent_rounds": recent[:8],
        "story_milestones": _list_text(data.get("story_milestones"), 260, 12),
        "open_questions": _list_text(data.get("open_questions"), 180, 8),
        "updated_at": _compact_text(data.get("updated_at"), 40) or now,
    }


def _build_wenyou_card_context(card: Any) -> str:
    clean = _normalize_wenyou_card(card)
    cur = clean.get("current_instance") if isinstance(clean.get("current_instance"), dict) else {}
    recent = clean.get("recent_rounds") or []
    milestones = clean.get("story_milestones") or []
    questions = clean.get("open_questions") or []
    if not cur and not recent and not milestones and not questions:
        return ""
    lines = [
        "【文游连续性卡片】",
        "以下只记录 App 文游/无限流跑团的虚构游戏进度；不是现实经历，不参与动态召回，只供 AI 玩家本轮行动参考。",
    ]
    if cur:
        inv = "、".join(cur.get("inventory") or []) or "无"
        clues = "；".join(cur.get("clues") or []) or "无"
        lines.extend(
            [
                f"- 当前副本：{cur.get('instance') or '未知'}｜{cur.get('genre') or '未知'}｜难度 {cur.get('difficulty') or '-'}｜阶段：{cur.get('phase') or '副本'}",
                f"- 当前任务：{cur.get('task') or '暂无'}",
                f"- 玩家一状态：{cur.get('player1') or '未知'}",
                f"- 玩家二状态：{cur.get('player2') or '未知'}",
                f"- 背包：{inv}",
                f"- 已知备忘：{clues}",
            ]
        )
    if recent:
        lines.append("最近文游回合：")
        for item in recent[:4]:
            lines.append(
                f"- {item.get('instance') or '当前副本'}：玩家一行动「{item.get('player1_action') or item.get('xinyue_action') or '无'}」；"
                f"玩家二行动「{item.get('player2_action') or item.get('ai_player_action') or '无'}」；GM 结算「{item.get('gm_result') or '无'}」"
            )
    if milestones:
        lines.append("长期剧情节点：" + "；".join(milestones[:6]))
    if questions:
        lines.append("待验证问题：" + "；".join(questions[:6]))
    return "\n".join(lines)


def _update_wenyou_card_for_round(user_id: int, session: dict, p1_text: str, p2_text: str, gm_out: str) -> None:
    """像共读卡片一样维护文游连续性，但只作为文游上下文，不参与召回。"""
    try:
        uid = int(user_id)
        old = _normalize_wenyou_card(r2_store.get_wenyou_card(uid))
        cur = _current_instance_for_card(session)
        gm_brief = _compact_text(_strip_main_god_panel(gm_out), 700)
        entry = {
            "at": now_beijing_iso(),
            "instance": cur.get("instance") or "当前副本",
            "player1_action": _compact_text(p1_text, 260),
            "player2_action": _compact_text(p2_text, 260),
            "gm_result": gm_brief,
            "clues": cur.get("clues") or [],
            "inventory": cur.get("inventory") or [],
        }
        recent = [entry] + [x for x in (old.get("recent_rounds") or []) if isinstance(x, dict)]
        milestones = list(old.get("story_milestones") or [])
        if gm_brief and any(k in gm_brief for k in ("通关", "副本结束", "主神空间", "获得", "发现", "规则", "线索", "死亡")):
            m = f"{cur.get('instance') or '当前副本'}：{_compact_text(gm_brief, 220)}"
            if m not in milestones[:3]:
                milestones.insert(0, m)
        questions = list(old.get("open_questions") or [])
        for clue in cur.get("clues") or []:
            if any(k in clue for k in ("待验证", "疑似", "未知", "？", "?")) and clue not in questions:
                questions.insert(0, clue)
        card = {
            "version": 1,
            "scope": "wenyou_game_only",
            "note": "App 文游/无限流跑团的虚构游戏连续性卡片，只供文游上下文使用，不参与动态召回。",
            "current_instance": cur,
            "recent_rounds": recent[:8],
            "story_milestones": milestones[:12],
            "open_questions": questions[:8],
            "updated_at": now_beijing_iso(),
        }
        r2_store.save_wenyou_card(uid, _normalize_wenyou_card(card))
    except Exception as e:
        logger.warning("更新文游卡片失败 user_id=%s error=%s", user_id, e, exc_info=True)


def _archive_wenyou_round_for_recent_memory(user_id: int, session: dict, p1_text: str, p2_text: str, gm_out: str) -> None:
    """把文游回合写入普通 last4/近期总结，但带明确游戏前缀，并跳过动态召回链路。"""
    try:
        fw = _framework_for_runtime(session.get("framework") or {})
        instance = _framework_instance_line(fw)
        user_content = (
            "[文游] 正在玩 App 文游/无限流跑团。以下内容是虚构游戏剧情，不是真实现实经历；"
            "总结时必须标注为文游游戏内容。\n"
            f"副本：{instance}｜类型：{_normalize_instance_genre(fw.get('instance_genre'))}｜难度：{_normalize_difficulty(fw.get('difficulty'))}\n"
            f"玩家一本轮行动：{_compact_text(p1_text, 500)}\n"
            f"玩家二本轮行动：{_compact_text(p2_text, 500)}"
        )
        assistant_content = (
            "[文游·GM] 以下是 App 文游/无限流跑团的虚构剧情结算，不是真实现实经历；"
            "总结时必须标注为文游游戏内容。\n"
            f"{_compact_text(_strip_main_god_panel(gm_out), 1800)}"
        )
        round_messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
        round_index = r2_store.get_next_round_index(_WENYOU_MEMORY_WINDOW_ID)
        ts = now_beijing_iso()
        ok = r2_store.append_conversation_round(
            _WENYOU_MEMORY_WINDOW_ID,
            round_index,
            round_messages,
            timestamp=ts,
            action_note=f"wenyou_game_round:user_id={int(user_id)}",
        )
        if not ok:
            return
        tail4 = r2_store.get_conversation_rounds(_WENYOU_MEMORY_WINDOW_ID, last_n=4)
        r2_store.update_latest_4_rounds_global(tail4)
        if round_index % _WENYOU_SUMMARY_EVERY_N_ROUNDS != 0:
            return
        recent = r2_store.get_conversation_rounds(_WENYOU_MEMORY_WINDOW_ID, last_n=4)
        if not recent:
            return

        def _summarize_wenyou_rounds():
            try:
                from services.deepseek_summary import fetch_new_summary_update

                current = r2_store.get_summary(_WENYOU_MEMORY_WINDOW_ID) or ""
                chunks_state = r2_store.get_summary_chunks(_WENYOU_MEMORY_WINDOW_ID)
                new_summary, new_chunks = fetch_new_summary_update(current, recent, chunks_state)
                if new_summary and new_chunks:
                    if r2_store.save_summary(_WENYOU_MEMORY_WINDOW_ID, new_summary):
                        r2_store.save_summary_chunks(_WENYOU_MEMORY_WINDOW_ID, new_chunks)
                else:
                    logger.warning("文游近期总结未返回有效结果 round_index=%s", round_index)
            except Exception as e:
                logger.warning("文游近期总结失败 round_index=%s error=%s", round_index, e, exc_info=True)

        threading.Thread(target=_summarize_wenyou_rounds, name="wenyou-summary", daemon=True).start()
    except Exception as e:
        logger.warning("文游回合写入 last4/近期记忆失败 user_id=%s error=%s", user_id, e, exc_info=True)


def _normalize_external_ai_player_action(action: Any) -> str:
    text = _compact_text(action, 260)
    if not text:
        return ""
    return re.sub(r"^[\"'“”]+|[\"'“”]+$", "", text).strip()[:220]


def get_session_view(user_id: int) -> dict:
    """MiniApp 结构化读取当前文游 session：任务、背包、状态、线索、最近历史。"""
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return {"active": False, "session": None}

    _session_ensure_stats(session)
    fw = _framework_for_runtime(session.get("framework") or {})
    history = []
    for item in (session.get("history") or [])[-30:]:
        row = _history_item_for_view(item)
        if row:
            history.append(row)
    st = session.get("stats") or {}
    pr = session.get("pending_round") if isinstance(session.get("pending_round"), dict) else {}
    wallet = _load_wenyou_wallet(uid, session)
    if _refresh_forced_instance_queue(wallet, session):
        _save_wenyou_wallet(uid, wallet)
    _sync_session_points_with_wallet(session, wallet)
    inventories = {
        "player1": _inventory_for_player_action(wallet, st, "player1", active=True),
        "player2": _inventory_for_player_action(wallet, st, "player2", active=True),
        "task_items": _normalize_inventory((wallet.get("inventories") or {}).get("task_items"), source="wallet"),
    }
    if _session_phase(session) == "instance_running":
        _ensure_monster_instances(session)
        r2_store.save_wenyou_session(uid, session)
    runtime_state = _runtime_state_view(session)
    public_state = runtime_state.get("public_state") if isinstance(runtime_state.get("public_state"), dict) else {}
    rules_state = _client_rules_state_view(runtime_state.get("rules_state"))
    client_runtime_state = copy.deepcopy(runtime_state)
    client_runtime_state["rules_state"] = rules_state
    client_runtime_state["last_state_patch"] = _client_state_patch_view(runtime_state.get("last_state_patch"))
    client_runtime_state.pop("gm_state", None)
    client_runtime_state.pop("runtime_indexes", None)
    return {
        "active": True,
        "session": {
            "gameId": str(session.get("gameId") or ""),
            "startedAt": str(session.get("startedAt") or ""),
            "phase": _session_phase(session),
            "phase_label": _phase_label(_session_phase(session)),
            "framework": {
                "instance_code": str(fw.get("instance_code") or ""),
                "instance_name": str(fw.get("instance_name") or ""),
                "instance_genre": _normalize_instance_genre(fw.get("instance_genre")),
                "genre_note": str(fw.get("genre_note") or ""),
                "difficulty": _normalize_difficulty(fw.get("difficulty")),
                "world": str(fw.get("world") or ""),
                "conflict": str(fw.get("conflict") or ""),
                "failure_hint": str(fw.get("failure_hint") or ""),
                "reward_hint": str(fw.get("reward_hint") or ""),
                "tasker_total": int(fw.get("tasker_total") or _DEFAULT_TASKER_TOTAL),
                "player_count": int(fw.get("player_count") or _DEFAULT_PLAYER_COUNT),
                "npc_taskers": fw.get("npc_taskers") or [],
            },
            "task": {
                "current": str(fw.get("conflict") or ""),
                "failure_hint": str(fw.get("failure_hint") or ""),
                "reward_hint": str(fw.get("reward_hint") or ""),
                "phase": _phase_label(_session_phase(session)),
            },
            "stats": st,
            "wallet": session.get("wallet") if isinstance(session.get("wallet"), dict) else None,
            "wallets": copy.deepcopy(wallet.get("wallets") if isinstance(wallet.get("wallets"), dict) else {}),
            "growth": _growth_view(session, wallet),
            "settlement": session.get("settlement") if isinstance(session.get("settlement"), dict) else None,
            "inventory": list(st.get("inventory") or []),
            "inventories": inventories,
            "clues": _clues_from_session(session),
            "public_state": public_state,
            "rules_state": rules_state,
            "ai_player_context": compose_ai_player_context(session, "player2", wallet=wallet, user_id=uid).get("ai_player_context"),
            "runtime_state": client_runtime_state,
            "forced_instance": copy.deepcopy(session.get("forced_instance")) if isinstance(session.get("forced_instance"), dict) else None,
            "public_view": public_state,
            "clocks": [
                {"id": c.get("id"), "name": c.get("name"), "status": _public_clock_status(c)}
                for c in session.get("clocks") or []
                if isinstance(c, dict)
            ][:20],
            "last_state_patch": _client_state_patch_view(session.get("last_state_patch")),
            "pending_round": {
                "player1_lines": list(pr.get("player1_lines") or []),
                "player2_lines": list(pr.get("player2_lines") or []),
            },
            "history": history,
        },
    }


def classify_wenyou_action_text(text: str) -> dict[str, Any]:
    """把自由文本先归到规则动作；成功与否仍由系统裁判，不信玩家自述。"""
    raw = str(text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    lower = compact.lower()
    system_keywords = ("商店", "系统商店", "抽卡", "命运裂隙", "加点", "属性点", "晋升", "复活", "背包", "状态面板", "结算", "申请结算", "归档")
    if any(k in compact for k in system_keywords):
        return {"action_type": "system_action", "confidence": "high", "text": raw, "reason": "系统操作不进入 GM"}
    if re.search(r"(逃跑|逃走|逃离|撤退|跑路|脱离|撤离|甩开)", compact):
        return {"action_type": "flee", "confidence": "high", "text": raw, "target": "", "reason": "逃跑由 flee_score/flee_dc 判定"}
    if re.search(r"(绕开|躲开|躲藏|潜行|避开|藏起来|不惊动)", compact):
        return {"action_type": "evade", "confidence": "medium", "text": raw, "target": "", "reason": "规避由系统判定"}
    if re.search(r"(封印|镇压|净化|超度|封住|封起来|做仪式)", compact):
        target = ""
        m = re.search(r"(?:封印|镇压|净化|超度|封住)(.{0,24})", raw)
        if m:
            target = m.group(1).strip(" ，。！？,.;:：")
        return {"action_type": "seal", "confidence": "high", "text": raw, "target": target, "reason": "封印由系统 seal_score 判定"}
    if re.search(r"(削弱|试探|验证.*弱点|找.*破绽|破解|识破|确认.*本体|确认.*弱点)", compact):
        return {"action_type": "weaken", "confidence": "high", "text": raw, "target": "", "reason": "削弱由系统稳定度/线索判定"}
    if re.search(r"(攻击|砍|刺|开枪|射击|殴打|打倒|杀死|一刀|击杀|干掉|破坏)", compact):
        target = ""
        m = re.search(r"(?:攻击|砍|刺|射击|打倒|杀死|击杀|干掉|破坏)(.{0,24})", raw)
        if m:
            target = m.group(1).strip(" ，。！？,.;:：")
        return {"action_type": "attack", "confidence": "high", "text": raw, "target": target, "reason": "战斗由命中/防御/Boss 规则判定"}
    if re.search(r"(交谈|询问|问问|套话|威胁|安抚|说服|谈判)", compact):
        return {"action_type": "talk", "confidence": "medium", "text": raw, "target": "", "reason": "社交推进"}
    if re.search(r"(观察|查看|调查|搜索|检查|翻找|阅读|验证|确认|比对)", compact):
        return {"action_type": "investigate", "confidence": "medium", "text": raw, "target": "", "reason": "调查推进"}
    if re.search(r"(前往|进入|离开|打开|推门|上楼|下楼|移动|去)", compact):
        return {"action_type": "move", "confidence": "medium", "text": raw, "target": "", "reason": "移动推进"}
    if "使用" in compact or compact.startswith("用") or lower.startswith("use"):
        return {"action_type": "use_item", "confidence": "medium", "text": raw, "target": "", "reason": "疑似道具动作，优先走道具接口"}
    return {"action_type": "act", "confidence": "low", "text": raw, "target": "", "reason": "普通剧情行动"}


def cmd_record_action(user_id: int, text: str, player: str = "player1") -> tuple[bool, str]:
    """记录玩家行动到 pending_round，不立即调用 GM。"""
    uid = int(user_id)
    action = str(text or "").strip()
    if not action:
        return False, "行动内容不能为空。"
    if len(action) > 1200:
        action = action[:1200]
    role = "player2" if str(player or "").lower() in ("player2", "p2", "玩家二") else "player1"
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "文游：当前没有进行中的局，请先开局。"
    phase = _session_phase(session)
    if phase in {"settlement", "archived"}:
        return False, "文游：当前处于系统空间结算阶段，不能继续推进。"
    pr = session.get("pending_round") if isinstance(session.get("pending_round"), dict) else {}
    key = "player2_lines" if role == "player2" else "player1_lines"
    pr.setdefault("player1_lines", [])
    pr.setdefault("player2_lines", [])
    pr.setdefault("action_intents", [])
    arr = pr.get(key)
    if not isinstance(arr, list):
        arr = []
    arr.append(action)
    pr[key] = arr[-8:]
    intents = pr.get("action_intents")
    if not isinstance(intents, list):
        intents = []
    intents.append({"player": role, **classify_wenyou_action_text(action), "created_at": now_beijing_iso()})
    pr["action_intents"] = intents[-12:]
    session["pending_round"] = pr
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    return True, action


def cmd_action(user_id: int, text: str, player: str = "player1") -> str:
    """记录玩家行动并立即推进一轮。"""
    ok, msg = cmd_record_action(user_id, text, player)
    if not ok:
        return msg
    return cmd_go(user_id)


def cmd_action_with_ai_player(user_id: int, text: str, ai_player_action: str = "") -> tuple[str, str]:
    """记录玩家一行动；若外部玩家二已给出行动，则一并记录后推进 GM。"""
    ok, msg = cmd_record_action(user_id, text, "player1")
    if not ok:
        return msg, ""
    ai_player_action = _normalize_external_ai_player_action(ai_player_action)
    if ai_player_action:
        ok_ai_player, ai_player_msg = cmd_record_action(user_id, ai_player_action, "player2")
        if not ok_ai_player:
            logger.warning("文游AI玩家外部行动记录失败 user_id=%s error=%s", user_id, ai_player_msg)
            ai_player_action = ""
    return cmd_go(user_id), ai_player_action


def _use_item_system_result(
    user_id: int,
    item_name: str,
    action: str = "",
    player_id: Any = "player1",
    target_id: Any = None,
) -> tuple[bool, str, str, dict, Optional[dict], Optional[dict]]:
    uid = int(user_id)
    pid = _resolve_player_key(player_id)
    target_pid = _resolve_player_key(target_id or pid)
    item = str(item_name or "").strip()
    if not item:
        return False, "文游：请选择要使用的道具。", "", {}, None, None
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "文游：当前没有进行中的局，请先开局。", "", {}, None, None
    _session_ensure_stats(session)
    phase = _session_phase(session)
    if phase == "archived":
        return False, "文游：当前存档已归档，不能使用道具。", "", {}, None, None
    wallet = _load_wenyou_wallet(uid, session)
    st = session["stats"]
    inventory = _inventory_for_player_action(wallet, st, pid, active=True)
    target = _inventory_find_by_name(inventory, item)
    if not target:
        return False, f"文游：背包里没有【{item}】。", "", session, wallet, None
    detail = str(action or "").strip()
    ok, result_text, changes = _apply_item_effect_to_session(session, target, detail, player_id=pid, target_id=target_pid)
    if not ok:
        return False, result_text, "", session, wallet, target
    inventory_after, consumed = _consume_inventory_item(inventory, target)
    if not consumed:
        return False, f"文游：背包里没有【{item}】。", "", session, wallet, target
    wallet_changes = changes.get("wallet") if isinstance(changes, dict) and isinstance(changes.get("wallet"), dict) else {}
    if int(wallet_changes.get("debt_delta") or 0):
        account = _player_account(wallet, pid)
        account["debts"] = max(0, int(account.get("debts") or 0) + int(wallet_changes.get("debt_delta") or 0))
        if pid == "player1":
            wallet["debts"] = account["debts"]
    _refresh_forced_instance_queue(wallet, session)
    _persist_player_inventory_for_action(wallet, st, pid, inventory_after[:80])
    session["stats"] = st
    _sync_session_points_with_wallet(session, wallet)
    ledger_entry = append_player_ledger(
        wallet,
        pid,
        {
            "type": "item_use",
            "item_id": consumed.get("id") if isinstance(consumed, dict) else "",
            "item_name": _inventory_item_name(consumed or target),
            "target_id": target_pid,
            "points_delta": 0,
            "summary": result_text[:180],
            "reason": _compact_text(action, 120),
        },
    )
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"item_{len(event_log) + 1:03d}",
        "source": "rules_engine.item_use",
        "actor_id": pid,
        "target_id": target_pid,
        "item": consumed,
        "changes": changes or {},
        "ledger_entry": ledger_entry,
        "created_at": now_beijing_iso(),
    }
    event_log.append(patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = patch
    session["runtime_state"] = _runtime_state_view(session)
    return True, result_text, _format_item_result_for_gm(consumed, result_text, pid), session, wallet, consumed


def _save_item_system_result(user_id: int, session: dict, wallet: dict) -> None:
    _save_wenyou_wallet(int(user_id), wallet)
    r2_store.save_wenyou_session(int(user_id), session)


def cmd_use_item(user_id: int, item_name: str, action: str = "") -> str:
    """使用道具：系统先结算效果/消耗，再把结算结果交给 GM 生成剧情。"""
    uid = int(user_id)
    original_session = r2_store.get_wenyou_session(uid)
    original_wallet = _load_wenyou_wallet(uid, original_session if isinstance(original_session, dict) else None)
    ok, result_text, gm_note, session, wallet, consumed = _use_item_system_result(uid, item_name, action)
    if not ok:
        return result_text
    _save_item_system_result(uid, session, wallet or {})
    if _session_phase(session) != "instance_running":
        return f"—— 主神系统 ——\n\n{_format_item_result_block(consumed or {}, result_text)}\n\n{_format_status_footer(session)}"
    ok_action, msg = cmd_record_action(uid, gm_note, "player1")
    if not ok_action:
        return msg
    out = cmd_go(uid)
    if out.startswith("文游：GM 调用失败"):
        r2_store.save_wenyou_session(uid, copy.deepcopy(original_session))
        _save_wenyou_wallet(uid, copy.deepcopy(original_wallet))
        return out
    return _inject_item_result_into_output(out, consumed or {}, result_text)


def cmd_use_item_with_ai_player(user_id: int, item_name: str, action: str = "", ai_player_action: str = "") -> tuple[str, str]:
    """使用道具：系统结算后，记录外部 AI 玩家行动，再交给 GM 叙事。"""
    uid = int(user_id)
    original_session = r2_store.get_wenyou_session(uid)
    original_wallet = _load_wenyou_wallet(uid, original_session if isinstance(original_session, dict) else None)
    ok, result_text, gm_note, session, wallet, consumed = _use_item_system_result(uid, item_name, action)
    if not ok:
        return result_text, ""
    _save_item_system_result(uid, session, wallet or {})
    if _session_phase(session) != "instance_running":
        return f"—— 主神系统 ——\n\n{_format_item_result_block(consumed or {}, result_text)}\n\n{_format_status_footer(session)}", ""
    ok_action, msg = cmd_record_action(uid, gm_note, "player1")
    if not ok_action:
        return msg, ""
    ai_player_action = _normalize_external_ai_player_action(ai_player_action)
    if ai_player_action:
        ok_ai_player, ai_player_msg = cmd_record_action(uid, ai_player_action, "player2")
        if not ok_ai_player:
            logger.warning("文游AI玩家外部行动记录失败 user_id=%s error=%s", user_id, ai_player_msg)
            ai_player_action = ""
    out = cmd_go(uid)
    if out.startswith("文游：GM 调用失败"):
        r2_store.save_wenyou_session(uid, copy.deepcopy(original_session))
        _save_wenyou_wallet(uid, copy.deepcopy(original_wallet))
        return out, ""
    return _inject_item_result_into_output(out, consumed or {}, result_text), ai_player_action


def _ai_public_panel(session: dict) -> dict:
    public = _public_state_from_session(session)
    return {
        "tasks": copy.deepcopy(public.get("public_tasks") or []),
        "clues": copy.deepcopy(public.get("discovered_clues") or []),
        "rules": copy.deepcopy(public.get("visible_rules") or []),
        "locations": copy.deepcopy(public.get("known_locations") or []),
    }


def summarize_story_for_ai_player(state: Any, actor_id: Any = "player2") -> dict:
    session = state if isinstance(state, dict) else {}
    _session_ensure_stats(session)
    fw = _framework_for_runtime(session.get("framework") or {})
    public = _public_state_from_session(session)
    phase = _session_phase(session)
    history_events: list[str] = []
    for item in (session.get("history") or [])[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = _compact_text(_strip_main_god_panel(str(item.get("content") or "")), 180)
        if content:
            history_events.append(("GM：" if role == "gm" else f"{_player_display_name(role)}：") + content)
    event_notes: list[str] = []
    for patch in (session.get("event_log") or [])[-4:]:
        if not isinstance(patch, dict):
            continue
        source = str(patch.get("source") or "rules")
        changes = patch.get("changes") if isinstance(patch.get("changes"), dict) else {}
        summary = _format_state_patch_for_display({"changes": changes})
        event_notes.append(_compact_text(summary or source, 180))
    active_objectives = [
        _compact_text(x.get("title") or x.get("progress", {}).get("text") or x.get("id"), 120)
        for x in public.get("public_tasks") or []
        if isinstance(x, dict)
    ]
    known_risks = [str(public.get("public_threat") or _public_threat_label(session))]
    if phase == "instance_running":
        known_risks.append("副本中不能使用系统商店或命运裂隙。")
    else:
        known_risks.append("抽卡不受幸运影响，商店和抽卡消耗各自玩家积分。")
    forced = session.get("forced_instance") if isinstance(session.get("forced_instance"), dict) else None
    party_notes = [
        "玩家一与玩家二当前同队行动。",
        "任务物品默认属于副本临时物，能否带出以规则引擎结算为准。",
    ]
    if forced and str(forced.get("mode") or "") == "npc_labor":
        known_risks.append("惩罚副本：玩家一和玩家二都是副本原住民 NPC，不能暴露玩家/任务者/外来者身份。")
        party_notes[0] = "玩家一与玩家二共同执行惩罚副本清算，双方都是副本原住民 NPC。"
    return {
        "campaign_summary": _compact_text(f"当前队伍处于{_phase_label(phase)}；副本为{_framework_instance_line(fw) or '未选择副本'}。", 180),
        "current_scene_summary": _compact_text(public.get("scene_summary") or fw.get("world") or "当前场景信息有限。", 220),
        "recent_events": (event_notes + history_events)[-8:],
        "last_rules_result": _compact_text(public.get("last_rules_result") or _format_state_patch_for_display(session.get("last_state_patch")) or "上一轮暂无额外规则结算。", 260),
        "active_objectives": [x for x in active_objectives if x][:6] or [_compact_text(fw.get("conflict") or "存活并确认通关条件。", 120)],
        "known_risks": known_risks[:6],
        "party_notes": party_notes,
    }


def compose_ai_player_context(state: Any, actor_id: Any = "player2", wallet: Optional[dict] = None, user_id: Optional[int] = None) -> dict:
    session = state if isinstance(state, dict) else {}
    _session_ensure_stats(session)
    actor = _resolve_player_key(actor_id)
    fw = _framework_for_runtime(session.get("framework") or {})
    phase = _session_phase(session)
    wallet_data = _ensure_wallet_player_maps(wallet if isinstance(wallet, dict) else {})
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    player = copy.deepcopy(st.get(actor) if isinstance(st.get(actor), dict) else _default_player_stats())
    account = _player_account(wallet_data, actor)
    inventory = _get_player_inventory(wallet_data, actor)
    if user_id is not None:
        try:
            shop_view = get_shop_view(int(user_id), actor)
            inventory = shop_view.get("inventory") if isinstance(shop_view.get("inventory"), list) else inventory
            shop_state = shop_view.get("shop_state") if isinstance(shop_view.get("shop_state"), dict) else {}
        except Exception:
            shop_state = {}
    else:
        shop_state = {}
    public = _public_state_from_session(session)
    location = "主神空间"
    locations = public.get("known_locations") if isinstance(public.get("known_locations"), list) else []
    if locations and isinstance(locations[0], dict):
        location = str(locations[0].get("name") or locations[0].get("public_text") or location)[:80]
    elif phase == "instance_running":
        location = "副本内"
    gacha = _normalize_gacha_state(account.get("gacha"))
    forced = session.get("forced_instance") if isinstance(session.get("forced_instance"), dict) else None
    team_states = {}
    for pid in _WENYOU_PLAYER_IDS:
        p = st.get(pid) if isinstance(st.get(pid), dict) else {}
        team_states[pid] = {
            "display_name": p.get("display_name") or _WENYOU_PLAYER_LABELS.get(pid, pid),
            "hp": int(p.get("hp") or 0),
            "hp_max": int(p.get("hp_max") or 0),
            "san": int(p.get("san") or 0),
            "san_max": int(p.get("san_max") or 0),
            "rank": p.get("rank") or "D",
            "level": int(p.get("level") or 1),
            "conditions": list(p.get("conditions") or [])[:8],
        }
    return {
        "ai_player_context": {
            "actor_id": actor,
            "phase": phase,
            "scene_header": {
                "phase_label": _phase_label(phase),
                "current_task": _compact_text(fw.get("conflict") or "等待选择副本", 140),
                "current_location": location,
                "time_state": "整备阶段 / 无倒计时" if phase in {"hub", "settlement"} else "副本推进中 / 公开倒计时以面板为准",
                "status_label": public.get("public_threat") or _public_threat_label(session),
            },
            "scene": {
                "instance_name": _framework_instance_line(fw),
                "current_location": location,
                "public_task": _compact_text(fw.get("conflict") or "", 180),
                "role_in_instance": _compact_text(fw.get(f"{actor}_role") or "", 180),
                "forced_instance_contract": copy.deepcopy(forced) if forced and str(forced.get("mode") or "") == "npc_labor" else None,
            },
            "story_brief": summarize_story_for_ai_player(session, actor),
            "public_panel": _ai_public_panel(session),
            "player_panel": {
                "display_name": player.get("display_name") or _player_display_name(actor),
                "level": int(player.get("level") or 1),
                "rank": player.get("rank") or "D",
                "hp": int(player.get("hp") or 0),
                "hp_max": int(player.get("hp_max") or 0),
                "san": int(player.get("san") or 0),
                "san_max": int(player.get("san_max") or 0),
                "spi_current": int(player.get("spi_current") or 0),
                "spi_max": int(player.get("spi_max") or 0),
                "attributes": {key: int(player.get(key) or 0) for key in _WENYOU_ATTRIBUTE_KEYS},
                "conditions": list(player.get("conditions") or [])[:12],
            },
            "wallet": {
                "points": int(account.get("points") or 0),
                "debts": int(account.get("debts") or 0),
                "gacha_pity": copy.deepcopy((gacha.get("pools") or {})),
            },
            "inventory": inventory,
            "team_public_states": team_states,
            "available_services": {
                "shop": _shop_open_for_phase(phase),
                "gacha": phase in {"hub", "settlement"},
                "use_item": phase in {"hub", "candidate_selection", "instance_running", "settlement"},
                "transfer": phase in {"hub", "candidate_selection", "instance_running", "settlement"},
            },
            "shop_view": {
                "regular": copy.deepcopy(((shop_state.get("regular") or {}).get("items") or []) if isinstance(shop_state, dict) else []),
                "special": copy.deepcopy(((shop_state.get("special") or {}).get("items") or []) if isinstance(shop_state, dict) else []),
            },
            "gacha_pools": [{"pool_id": pool, "single_cost": _GACHA_SINGLE_COST, "ten_pull_cost": _GACHA_SINGLE_COST * 10} for pool in _GACHA_POOL_RATES],
            "recent_ledger": [x for x in (account.get("ledger") or [])[-12:] if isinstance(x, dict)],
        }
    }


def get_player_tool_context(user_id: int, actor_id: Any = "player2") -> Optional[dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not isinstance(session, dict) or not session.get("gameId"):
        return None
    wallet = _load_wenyou_wallet(uid, session)
    return compose_ai_player_context(session, actor_id=actor_id, wallet=wallet, user_id=uid)


_AI_PLAYER_CHAT_SYSTEM = """你正在控制文游里的玩家二，不是 GM，也不是规则引擎。
你会收到一份后端裁剪过的只读文游上下文；它是事实源，只能依据它行动。

边界：
- 不替玩家一行动，不替 GM 结算，不编造隐藏线索、隐藏规则、背包、积分或判定结果。
- 如果要购买、抽卡、使用道具、出售或转交，必须调用可用的玩家工具，并接受工具返回结果。
- 不能在工具确认前宣称购买、抽卡、治疗或转交已经成功。
- 如果当前阶段不允许商店、抽卡或转交，就不要假装完成。
- 本轮最终只输出“玩家二本轮行动文本”，30-160 字；不要 Markdown，不要解释，不要系统提示。
"""


def _json_for_prompt(data: Any, max_chars: int = 12000) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False, default=str, indent=2)
    except Exception:
        text = str(data or "")
    return text if len(text) <= max_chars else text[:max_chars] + "\n……（上下文已裁剪）"


def build_ai_player_chat_messages(
    user_id: int,
    player_action: str,
    *,
    actor_id: Any = "player2",
    action_intent: Optional[dict] = None,
) -> Optional[list[dict]]:
    context = get_player_tool_context(user_id, actor_id=actor_id)
    if not context:
        return None
    action = _compact_text(player_action, 900)
    intent_text = _json_for_prompt(action_intent or {}, max_chars=1800)
    user_prompt = "\n".join(
        [
            "[WENYOU AI PLAYER TURN]",
            "只读上下文 JSON：",
            _json_for_prompt(context.get("ai_player_context") or {}, max_chars=14000),
            "",
            "玩家一本轮行动：",
            action or "（无）",
            "",
            "后端行动归类：",
            intent_text,
            "",
            "请决定玩家二本轮是否行动以及怎么行动。若需要修改状态，先调用玩家工具；最终只输出玩家二的行动文本。",
            "[/WENYOU AI PLAYER TURN]",
        ]
    )
    return [
        {"role": "system", "content": _AI_PLAYER_CHAT_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]


def get_player_tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "buy_item",
                "description": "从当前系统商店货架购买一件物品；只能花 actor_id 自己的积分。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "发起购买的玩家角色 id，玩家二固定为 player2"},
                        "offer_ref": {"type": "string", "description": "货架短引用，如 R01/S01，优先使用"},
                        "item_id": {"type": "string", "description": "内容表物品 id；有 offer_ref 时可不填"},
                        "quantity": {"type": "integer", "description": "数量，普通商店只允许 1", "default": 1},
                        "reason": {"type": "string", "description": "购买理由，写入流水，不影响价格"},
                    },
                    "required": ["actor_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "roll_gacha",
                "description": "使用 actor_id 自己的积分抽命运裂隙卡池。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "发起抽卡的玩家角色 id，玩家二固定为 player2"},
                        "pool_id": {"type": "string", "description": "卡池 id，例如 mixed", "default": "mixed"},
                        "count": {"type": "integer", "description": "只允许 1 或 10", "default": 1},
                        "reason": {"type": "string", "description": "抽卡理由，写入流水"},
                    },
                    "required": ["actor_id", "pool_id", "count"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inventory_action",
                "description": "对 actor_id 自己的背包执行 use/sell。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "发起动作的玩家角色 id，玩家二固定为 player2"},
                        "action": {"type": "string", "description": "use / sell"},
                        "item_ref": {"type": "string", "description": "背包内 uid、短引用或精确物品名"},
                        "target_id": {"type": "string", "description": "道具目标；默认 actor_id"},
                        "context": {"type": "string", "description": "使用意图，供规则和 GM 后续叙事参考"},
                    },
                    "required": ["actor_id", "action", "item_ref"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "use_item",
                "description": "使用 actor_id 自己背包里的道具；是 inventory_action(action=use) 的快捷入口。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "发起动作的玩家角色 id，玩家二固定为 player2"},
                        "item_ref": {"type": "string", "description": "背包内 uid、短引用或精确物品名"},
                        "target_id": {"type": "string", "description": "道具目标；默认 actor_id"},
                        "context": {"type": "string", "description": "使用意图，供规则和 GM 后续叙事参考"},
                    },
                    "required": ["actor_id", "item_ref"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "transfer",
                "description": "转交 actor_id 自己的积分或物品给其他玩家。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "发起转交的玩家角色 id，玩家二固定为 player2"},
                        "target_id": {"type": "string", "description": "接收方玩家角色 id"},
                        "transfer_type": {"type": "string", "description": "item 或 points"},
                        "item_ref": {"type": "string", "description": "转交物品时填写"},
                        "quantity": {"type": "integer", "description": "物品数量，默认 1", "default": 1},
                        "amount": {"type": "integer", "description": "转交积分时填写"},
                        "message": {"type": "string", "description": "给前端和 GM 展示的转交说明"},
                    },
                    "required": ["actor_id", "target_id", "transfer_type"],
                },
            },
        },
    ]


def _compact_player_tool_view(view: dict) -> dict:
    data = view if isinstance(view, dict) else {}
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    shop_state = data.get("shop_state") if isinstance(data.get("shop_state"), dict) else {}
    wallet = data.get("wallet") if isinstance(data.get("wallet"), dict) else {}
    return {
        "error_code": data.get("error_code"),
        "state_patch": data.get("state_patch") or session.get("last_state_patch"),
        "ledger_entry": data.get("ledger_entry"),
        "wallet": wallet,
        "points": data.get("points"),
        "inventory": data.get("inventory"),
        "results": data.get("results"),
        "pity_after": data.get("pity_after"),
        "shop_date": shop_state.get("date"),
    }


def execute_player_tool(user_id: int, name: str, arguments: Optional[dict]) -> str:
    uid = int(user_id)
    args = arguments if isinstance(arguments, dict) else {}
    actor_id = str(args.get("actor_id") or "player2")
    tool = str(name or "").strip()
    if tool == "buy_item":
        ok, message, view = player_tool_buy_item(
            uid,
            actor_id=actor_id,
            offer_ref=str(args.get("offer_ref") or ""),
            item_id=str(args.get("item_id") or args.get("id") or ""),
            quantity=int(args.get("quantity") or 1),
            reason=str(args.get("reason") or ""),
        )
    elif tool == "roll_gacha":
        ok, message, view = player_tool_roll_gacha(
            uid,
            actor_id=actor_id,
            pool_id=str(args.get("pool_id") or args.get("pool") or "mixed"),
            count=int(args.get("count") or 1),
            reason=str(args.get("reason") or ""),
        )
    elif tool == "inventory_action":
        ok, message, view = player_tool_inventory_action(
            uid,
            actor_id=actor_id,
            action=str(args.get("action") or "use"),
            item_ref=str(args.get("item_ref") or args.get("item") or args.get("uid") or args.get("id") or ""),
            target_id=str(args.get("target_id") or actor_id),
            context=str(args.get("context") or args.get("reason") or ""),
        )
    elif tool == "use_item":
        ok, message, view = player_tool_use_item(
            uid,
            actor_id=actor_id,
            item_ref=str(args.get("item_ref") or args.get("item") or args.get("uid") or args.get("id") or ""),
            target_id=str(args.get("target_id") or actor_id),
            context=str(args.get("context") or args.get("reason") or ""),
        )
    elif tool == "transfer":
        ok, message, view = player_tool_transfer(
            uid,
            actor_id=actor_id,
            target_id=str(args.get("target_id") or "player1"),
            transfer_type=str(args.get("transfer_type") or "item"),
            item_ref=str(args.get("item_ref") or args.get("item") or ""),
            quantity=int(args.get("quantity") or 1),
            amount=int(args.get("amount") or 0),
            message=str(args.get("message") or ""),
        )
    else:
        return json.dumps({"ok": False, "error_code": "UNKNOWN_TOOL", "message": f"未知玩家工具：{tool}"}, ensure_ascii=False)
    payload = {"ok": bool(ok), "message": message, **_compact_player_tool_view(view)}
    return json.dumps(payload, ensure_ascii=False, default=str)


def _validate_player_tool_actor(wallet: dict, actor_id: Any) -> tuple[bool, str, str]:
    actor = _resolve_player_key(actor_id)
    if actor not in _WENYOU_PLAYER_IDS:
        return False, actor, "INVALID_ACTOR"
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    player = players.get(actor) if isinstance(players.get(actor), dict) else {}
    controller = str(player.get("controller") or _WENYOU_PLAYER_CONTROLLERS.get(actor) or "").lower()
    if controller != "ai":
        return False, actor, "INVALID_ACTOR"
    return True, actor, ""


def _player_tool_error(actor_id: Any, error_code: str, message: str, view: Optional[dict] = None) -> tuple[bool, str, dict]:
    payload = dict(view or {})
    payload.update({"actor_id": _resolve_player_key(actor_id), "error_code": error_code, "state_patch": None})
    return False, message, payload


def player_tool_buy_item(user_id: int, actor_id: Any = "player2", offer_ref: str = "", item_id: str = "", quantity: int = 1, reason: str = "") -> tuple[bool, str, dict]:
    uid = int(user_id)
    wallet = _load_wenyou_wallet(uid, r2_store.get_wenyou_session(uid))
    ok_actor, actor, error = _validate_player_tool_actor(wallet, actor_id)
    if not ok_actor:
        return _player_tool_error(actor, error, "指定角色不存在或不是 AI 控制。", get_shop_view(uid, actor))
    if int(quantity or 1) != 1:
        return _player_tool_error(actor, "INVALID_QUANTITY", "系统商店每次只购买 1 件。", get_shop_view(uid, actor))
    ok, message, view = buy_shop_item(uid, item_id=item_id, actor_id=actor, offer_ref=offer_ref, reason=reason)
    if not ok:
        code = "INSUFFICIENT_POINTS" if "积分不足" in message else "ITEM_NOT_FOUND" if "下架" in message or "选择" in message else "PHASE_FORBIDDEN"
        view["error_code"] = code
    return ok, message, view


def player_tool_roll_gacha(user_id: int, actor_id: Any = "player2", pool_id: str = "mixed", count: int = 1, reason: str = "") -> tuple[bool, str, dict]:
    uid = int(user_id)
    wallet = _load_wenyou_wallet(uid, r2_store.get_wenyou_session(uid))
    ok_actor, actor, error = _validate_player_tool_actor(wallet, actor_id)
    if not ok_actor:
        return _player_tool_error(actor, error, "指定角色不存在或不是 AI 控制。", get_shop_view(uid, actor))
    ok, message, view = roll_gacha(uid, pool_id=pool_id, count=count, actor_id=actor, reason=reason)
    if not ok:
        code = "INSUFFICIENT_POINTS" if "积分不足" in message else "POOL_NOT_AVAILABLE" if "支持" in message else "PHASE_FORBIDDEN"
        view["error_code"] = code
    return ok, message, view


def player_tool_inventory_action(
    user_id: int,
    actor_id: Any = "player2",
    action: str = "use",
    item_ref: str = "",
    target_id: Any = None,
    context: str = "",
) -> tuple[bool, str, dict]:
    uid = int(user_id)
    wallet = _load_wenyou_wallet(uid, r2_store.get_wenyou_session(uid))
    ok_actor, actor, error = _validate_player_tool_actor(wallet, actor_id)
    if not ok_actor:
        return _player_tool_error(actor, error, "指定角色不存在或不是 AI 控制。", get_shop_view(uid, actor))
    act = str(action or "use").strip().lower()
    if act == "sell":
        return sell_inventory_item(uid, item_ref, player_id=actor)
    if act != "use":
        return _player_tool_error(actor, "INVALID_ACTION", "不支持的背包动作。", get_shop_view(uid, actor))
    ok, result_text, _gm_note, session, wallet_after, consumed = _use_item_system_result(uid, item_ref, context, player_id=actor, target_id=target_id or actor)
    if not ok:
        code = "ITEM_NOT_FOUND" if "没有" in result_text else "PHASE_FORBIDDEN" if "阶段" in result_text or "不能使用" in result_text else "REQUIREMENT_NOT_MET"
        return _player_tool_error(actor, code, result_text, get_session_view(uid))
    _save_item_system_result(uid, session, wallet_after or {})
    view = get_session_view(uid)
    view["message"] = result_text
    view["used"] = consumed
    view["state_patch"] = (view.get("session") or {}).get("last_state_patch")
    return True, result_text, view


def player_tool_use_item(user_id: int, actor_id: Any = "player2", item_ref: str = "", target_id: Any = None, context: str = "") -> tuple[bool, str, dict]:
    return player_tool_inventory_action(user_id, actor_id=actor_id, action="use", item_ref=item_ref, target_id=target_id or actor_id, context=context)


def player_tool_transfer(
    user_id: int,
    actor_id: Any = "player2",
    target_id: Any = "player1",
    transfer_type: str = "item",
    item_ref: str = "",
    quantity: int = 1,
    amount: int = 0,
    message: str = "",
) -> tuple[bool, str, dict]:
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    active = bool(session and isinstance(session, dict) and session.get("gameId"))
    wallet = _load_wenyou_wallet(uid, session if active else None)
    ok_actor, actor, error = _validate_player_tool_actor(wallet, actor_id)
    if not ok_actor:
        return _player_tool_error(actor, error, "指定角色不存在或不是 AI 控制。", get_shop_view(uid, actor))
    target = _resolve_player_key(target_id)
    if target == actor:
        return _player_tool_error(actor, "TARGET_FORBIDDEN", "不能转交给自己。", get_shop_view(uid, actor))
    if active:
        _session_ensure_stats(session)
        if _session_phase(session) == "archived":
            return _player_tool_error(actor, "PHASE_FORBIDDEN", "已归档存档不能转交。", get_session_view(uid))
        st = session["stats"]
    else:
        st = _wallet_stats_from_wallet(wallet)
    ttype = str(transfer_type or "item").strip().lower()
    event_log = session.get("event_log") if active and isinstance(session.get("event_log"), list) else []
    patch_changes: dict[str, Any] = {}
    if ttype == "points":
        value = max(0, int(amount or 0))
        if value <= 0:
            return _player_tool_error(actor, "INVALID_AMOUNT", "转交积分必须大于 0。", get_shop_view(uid, actor))
        source = _player_account(wallet, actor)
        dest = _player_account(wallet, target)
        if int(source.get("points") or 0) < value:
            return _player_tool_error(actor, "INSUFFICIENT_POINTS", "玩家积分不足。", get_shop_view(uid, actor))
        _set_actor_points(wallet, actor, int(source.get("points") or 0) - value)
        _set_actor_points(wallet, target, int(dest.get("points") or 0) + value)
        out_entry = append_player_ledger(wallet, actor, {"type": "points_transfer_out", "target_id": target, "points_delta": -value, "summary": _compact_text(message or f"转交 {value} 积分", 120)})
        in_entry = append_player_ledger(wallet, target, {"type": "points_transfer_in", "target_id": actor, "points_delta": value, "summary": _compact_text(message or f"收到 {value} 积分", 120)})
        patch_changes = {"wallets": {actor: {"points_delta": -value}, target: {"points_delta": value}}}
        result = f"{_player_display_name(actor)}向{_player_display_name(target)}转交 {value} 主神积分。"
        ledger_entries = [out_entry, in_entry]
    else:
        inv = _inventory_for_player_action(wallet, st, actor, active)
        item = _inventory_find_by_name(inv, item_ref)
        if not item:
            return _player_tool_error(actor, "ITEM_NOT_FOUND", f"背包里没有【{item_ref}】。", get_shop_view(uid, actor))
        if _item_locked_for_recycle(item):
            return _player_tool_error(actor, "ITEM_LOCKED", "该物品不能转交。", get_shop_view(uid, actor))
        inv_after, consumed = _consume_inventory_item(inv, item, force_remove=True)
        if not consumed:
            return _player_tool_error(actor, "ITEM_NOT_FOUND", f"背包里没有【{item_ref}】。", get_shop_view(uid, actor))
        target_inv = _inventory_for_player_action(wallet, st, target, active)
        received = dict(consumed)
        received["holder_id"] = target
        target_inv = _add_inventory_item(target_inv, received)
        _persist_player_inventory_for_action(wallet, st, actor, inv_after)
        _persist_player_inventory_for_action(wallet, st, target, target_inv)
        out_entry = append_player_ledger(wallet, actor, {"type": "item_transfer_out", "target_id": target, "item_name": _inventory_item_name(consumed), "points_delta": 0, "summary": _compact_text(message, 120)})
        in_entry = append_player_ledger(wallet, target, {"type": "item_transfer_in", "target_id": actor, "item_name": _inventory_item_name(consumed), "points_delta": 0, "summary": _compact_text(message, 120)})
        patch_changes = {"inventory_remove": {actor: [consumed]}, "inventory_add": {target: [received]}}
        result = f"{_player_display_name(actor)}将【{_inventory_item_name(consumed)}】交给{_player_display_name(target)}。"
        ledger_entries = [out_entry, in_entry]
    patch = {
        "round_id": f"ai_transfer_{len(event_log) + 1:03d}",
        "source": "player_tools.transfer",
        "actor_id": actor,
        "target_id": target,
        "changes": patch_changes,
        "ledger_entry": ledger_entries[0],
        "created_at": now_beijing_iso(),
    }
    _save_wenyou_wallet(uid, wallet)
    if active:
        session["stats"] = st
        event_log.append(patch)
        session["event_log"] = event_log[-200:]
        session["last_state_patch"] = patch
        _sync_session_points_with_wallet(session, wallet)
        r2_store.save_wenyou_session(uid, session)
        view = get_session_view(uid)
    else:
        view = get_shop_view(uid, actor)
    view["state_patch"] = patch
    view["ledger_entry"] = ledger_entries[0]
    return True, result, view


def _monster_template_to_instance(raw: Any, index: int, tier: str = "common", difficulty: str = "D") -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("title") or "").strip()
    if not name:
        return None
    rank = _normalize_difficulty(raw.get("rank") or difficulty)
    mtier = str(raw.get("tier") or tier or "common").strip().lower()
    if mtier not in {"common", "elite", "boss"}:
        mtier = "common"
    hp = None if mtier == "boss" else max(1, int(raw.get("hp") or (45 if mtier == "elite" else 24)))
    stability = max(0, int(raw.get("stability") or (5 if mtier == "boss" else 0)))
    seal_target = max(1, int(raw.get("seal_target") or raw.get("seal_progress_target") or (3 if mtier == "boss" else 2)))
    return {
        "id": str(raw.get("id") or f"{mtier}_{index + 1}")[:80],
        "name": name[:80],
        "tier": mtier,
        "rank": rank,
        "status": str(raw.get("status") or ("dormant" if mtier == "boss" else "patrolling")),
        "hp": hp,
        "hp_max": hp,
        "attack": max(0, int(raw.get("attack") or (12 if mtier == "elite" else 7))),
        "defense": 999 if mtier == "boss" else max(0, int(raw.get("defense") or (2 if mtier == "elite" else 1))),
        "mental_attack": max(0, int(raw.get("mental_attack") or (16 if mtier == "boss" else 5))),
        "mental_resist": 999 if mtier == "boss" else max(0, int(raw.get("mental_resist") or 1)),
        "speed": max(1, int(raw.get("speed") or 10)),
        "detection": max(1, int(raw.get("detection") or 10)),
        "default_invincible": bool(raw.get("default_invincible")) if "default_invincible" in raw else mtier == "boss",
        "can_be_killed": bool(raw.get("can_be_killed")),
        "stability": stability,
        "stability_max": max(stability, int(raw.get("stability_max") or stability or 1)),
        "seal_progress": max(0, int(raw.get("seal_progress") or 0)),
        "seal_target": seal_target,
        "weaknesses": _normalize_text_list(raw.get("weaknesses"), 80, 6),
        "counterplay": _normalize_text_list(raw.get("counterplay"), 100, 6),
        "weaken_conditions": _normalize_text_list(raw.get("weaken_conditions"), 120, 6),
        "seal_conditions": _normalize_text_list(raw.get("seal_conditions"), 120, 6),
        "escape_conditions": _normalize_text_list(raw.get("escape_conditions"), 120, 6),
        "public_text": _compact_text(raw.get("public_text") or raw.get("desc") or raw.get("role") or "", 180),
    }


def _ensure_monster_instances(session: dict) -> list[dict]:
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    monsters = [dict(x) for x in rules.get("monster_instances") or [] if isinstance(x, dict)]
    if monsters:
        return monsters[:20]
    fw = _framework_for_runtime(session.get("framework") or {})
    diff = _normalize_difficulty(fw.get("difficulty"))
    encounter = fw.get("encounter_profile") if isinstance(fw.get("encounter_profile"), dict) else {}
    raw_monsters: list[tuple[Any, str]] = []
    for item in (encounter.get("common") if isinstance(encounter.get("common"), list) else [])[:2]:
        raw_monsters.append((item, "common"))
    for item in (encounter.get("elite") if isinstance(encounter.get("elite"), list) else [])[:1]:
        raw_monsters.append((item, "elite"))
    if isinstance(encounter.get("boss"), dict):
        raw_monsters.append((encounter.get("boss"), "boss"))
    for i, (raw, tier) in enumerate(raw_monsters):
        monster = _monster_template_to_instance(raw, i, tier, diff)
        if monster:
            monsters.append(monster)
    if not monsters:
        monsters = [{
            "id": "ambient_threat",
            "name": "当前异常源",
            "tier": "common",
            "rank": diff,
            "status": "patrolling",
            "hp": 24,
            "hp_max": 24,
            "attack": 7,
            "defense": 1,
            "mental_attack": 5,
            "mental_resist": 1,
            "speed": 10,
            "detection": 10,
            "default_invincible": False,
            "can_be_killed": True,
            "stability": 0,
            "stability_max": 1,
            "seal_progress": 0,
            "seal_target": 2,
            "weaknesses": [],
            "counterplay": ["规避", "线索削弱"],
            "public_text": "系统根据当前副本压力生成的临时异常实体。",
        }]
    rules["monster_instances"] = monsters[:20]
    runtime["rules_state"] = rules
    session["runtime_state"] = runtime
    _save_monster_instances(session, monsters, "")
    return monsters[:20]


def _save_monster_instances(session: dict, monsters: list[dict], result_text: str = "") -> None:
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    rules["monster_instances"] = [dict(x) for x in monsters if isinstance(x, dict)][:20]
    runtime["rules_state"] = rules
    public = _public_state_from_session(session)
    visible = []
    for i, monster in enumerate(monsters[:6]):
        if not isinstance(monster, dict):
            continue
        visible.append(_normalize_public_marker_item({
            "id": monster.get("id"),
            "name": monster.get("name"),
            "status": monster.get("status"),
            "public_status": monster.get("status"),
            "public_text": result_text if i == 0 and result_text else monster.get("public_text") or "已进入可见威胁记录。",
            "type": monster.get("tier"),
            "tier": monster.get("tier"),
            "rank": monster.get("rank"),
            "danger": monster.get("rank"),
            "weakness": "、".join(monster.get("weaknesses") or []) or "待验证",
            "weaknesses": monster.get("weaknesses") or [],
            "counterplay": monster.get("counterplay") or [],
            "stability": monster.get("stability"),
            "stability_max": monster.get("stability_max"),
            "seal_progress": monster.get("seal_progress"),
            "seal_target": monster.get("seal_target"),
        }, i, "monster"))
    public["visible_monsters"] = [x for x in visible if x][:20]
    if result_text:
        public["last_rules_result"] = _compact_text(result_text, 260)
    public["public_threat"] = _public_threat_label(session)
    runtime["public_state"] = public
    session["runtime_state"] = runtime


def _first_active_monster(monsters: list[dict], target: str = "", allow_boss: bool = False) -> Optional[dict]:
    target = str(target or "").strip()
    for monster in monsters:
        if not isinstance(monster, dict):
            continue
        if target and target not in {str(monster.get("id") or ""), str(monster.get("name") or "")}:
            continue
        if str(monster.get("status") or "") in {"defeated", "sealed", "evaded"}:
            continue
        if not allow_boss and str(monster.get("tier") or "") == "boss":
            continue
        return monster
    if allow_boss:
        for monster in monsters:
            if isinstance(monster, dict) and str(monster.get("status") or "") not in {"defeated", "sealed", "evaded"}:
                return monster
    return None


def _apply_monster_retaliation(player: dict, monster: dict, severity: float = 1.0) -> dict:
    hp_before = int(player.get("hp") or 0)
    san_before = int(player.get("san") or 0)
    hp_damage = math.ceil(max(0, int(monster.get("attack") or 0) - int(player.get("defense") or 0)) * severity)
    san_damage = math.ceil(max(0, int(monster.get("mental_attack") or 0) - int(player.get("mental_resist") or 0)) * severity)
    if hp_damage:
        player["hp"] = max(0, hp_before - max(1, hp_damage))
    if san_damage:
        player["san"] = max(0, san_before - max(1, san_damage))
    spi_delta = _apply_san_delta_to_spi(player, int(player.get("san") or 0) - san_before)
    threshold = _apply_threshold_conditions(player)
    return {
        "hp_delta": int(player.get("hp") or 0) - hp_before,
        "san_delta": int(player.get("san") or 0) - san_before,
        "spi_delta": spi_delta,
        "conditions_add": threshold,
        "conditions_remove": [],
    }


def _encounter_detail_bonuses(detail: str, player: dict, monster: dict, action: str) -> dict[str, Any]:
    text = str(detail or "")
    bonuses: dict[str, Any] = {"total": 0, "notes": []}

    def add(key: str, value: int, note: str) -> None:
        if value <= 0:
            return
        bonuses[key] = value
        bonuses["total"] = int(bonuses.get("total") or 0) + value
        bonuses["notes"].append(note)

    if action in {"escape", "avoid", "flee", "evade"}:
        if re.search(r"(路线|出口|退路|安全屋|安全区|门|楼梯|窗|地图|绕路|掩护)", text):
            add("route_bonus", 2, "利用路线/掩护")
        if re.search(r"(道具|绳|钥匙|烟雾|闪光|诱饵|手电|符|药剂|工具)", text):
            add("item_bonus", 2, "使用合适道具或工具")
        if re.search(r"(分散|声东击西|制造噪声|引开|障碍|关门|封门)", text):
            add("distraction_bonus", 2, "制造干扰")
        if str(monster.get("tier") or "") == "boss":
            bonuses["boss_lock_penalty"] = 5
            bonuses["notes"].append("Boss 规则锁定，逃跑 DC +5")
    elif action in {"attack", "combat", "fight"}:
        weaknesses = [str(x) for x in (monster.get("weaknesses") or []) if str(x).strip()]
        if weaknesses and any(w and w in text for w in weaknesses):
            add("weakness_bonus", 4, "命中已知弱点")
        elif re.search(r"(弱点|线索|规则|破绽|克制|封印)", text):
            add("weakness_bonus", 2, "尝试利用弱点/线索")
        if re.search(r"(偷袭|伏击|背后|瞄准|蓄力)", text):
            add("tactic_bonus", 2, "战术准备")
    elif action in {"weaken", "probe"}:
        weaknesses = [str(x) for x in (monster.get("weaknesses") or []) if str(x).strip()]
        if weaknesses and any(w and w in text for w in weaknesses):
            add("weakness_bonus", 4, "对上已知弱点")
        elif re.search(r"(弱点|规则|线索|破绽|验证|试探|污染源|名字|本体)", text):
            add("insight_bonus", 2, "用线索试探弱点")
        if re.search(r"(录像|录音|镜子|灯|盐|符|粉笔|身份|证词|道具|工具)", text):
            add("tool_bonus", 2, "使用可解释工具")
    elif action in {"seal", "purify", "exorcise"}:
        seal_conditions = [str(x) for x in (monster.get("seal_conditions") or []) if str(x).strip()]
        if seal_conditions and any(w and w in text for w in seal_conditions):
            add("ritual_bonus", 4, "满足封印条件")
        elif re.search(r"(封印|镇压|净化|超度|仪式|规则|名字|本体|弱点|核心)", text):
            add("ritual_bonus", 2, "尝试按规则封印")
        if re.search(r"(符|阵|粉笔|蜡烛|镜|钥匙|证词|道具|媒介)", text):
            add("medium_bonus", 2, "使用封印媒介")
    return bonuses


def _record_encounter_reward(session: dict, monster: dict, outcome: str) -> dict[str, Any]:
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    reward_context = _reward_context_from_raw(rules.get("reward_context"))
    flags = _settlement_flags_from_raw(rules.get("settlement_flags"))
    mid = _slug_id(monster.get("id") or monster.get("name") or "monster", "monster")
    name = _compact_text(monster.get("name") or "威胁", 80)
    tag = f"{outcome}:{mid}"
    tags = _normalize_text_list(reward_context.get("reward_tags"), 60, 40)
    if tag not in tags:
        tags.append(tag)
    reward_context["reward_tags"] = tags[:40]
    reward_context["item_grants"] = reward_context.get("item_grants") or []
    if outcome in {"monster_defeated", "monster_evaded", "monster_sealed", "monster_weakened"}:
        label = {"monster_defeated": "击退", "monster_evaded": "规避", "monster_sealed": "封印", "monster_weakened": "削弱"}.get(outcome, "处理")
        _record_settlement_flag(flags, "achievement", f"{label}威胁：{name}")
    rules["reward_context"] = reward_context
    rules["settlement_flags"] = flags
    runtime["rules_state"] = rules
    session["runtime_state"] = runtime
    return {"tag": tag, "name": name, "outcome": outcome}


def _bump_forced_instance_exposure(session: dict, channel: str, amount: int = 1, reason: str = "") -> None:
    forced = session.get("forced_instance") if isinstance(session.get("forced_instance"), dict) else None
    if not forced or forced.get("resolved"):
        return
    key = "exposure_to_taskers" if channel == "taskers" else "exposure_to_monsters"
    forced[key] = max(0, int(forced.get(key) or 0) + max(1, int(amount or 1)))
    if reason:
        log = forced.get("exposure_log") if isinstance(forced.get("exposure_log"), list) else []
        log.append({"at": now_beijing_iso(), "channel": channel, "reason": _compact_text(reason, 120)})
        forced["exposure_log"] = log[-12:]
    session["forced_instance"] = forced
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    rules = runtime.get("rules_state") if isinstance(runtime.get("rules_state"), dict) else {}
    rules["forced_instance"] = copy.deepcopy(forced)
    runtime["rules_state"] = rules
    session["runtime_state"] = runtime


def _resolve_encounter_action(session: dict, action_type: str, target: str = "", detail: str = "") -> tuple[bool, str, dict]:
    _session_ensure_stats(session)
    if _session_phase(session) != "instance_running":
        return False, "只有副本进行中才能进行战斗或逃跑判定。", {}
    st = session["stats"]
    player = st.get("player1") if isinstance(st.get("player1"), dict) else _default_player_stats()
    _recalc_player_caps(player)
    action = str(action_type or "").strip().lower()
    monsters = _ensure_monster_instances(session)
    monster = _first_active_monster(monsters, target, allow_boss=action in {"attack", "combat", "fight", "escape", "avoid", "flee", "evade", "weaken", "probe", "seal", "purify", "exorcise"})
    if not monster:
        return False, "当前没有可结算的可见威胁。", {}
    seed = f"wenyou-encounter:{session.get('gameId')}:{len(session.get('event_log') or [])}:{action}:{monster.get('id')}"
    rng = random.Random(seed)
    d20 = rng.randint(1, 20)
    bonuses = _encounter_detail_bonuses(detail, player, monster, action)
    changes: dict[str, Any] = {"players": {}, "monster_updates": [], "clock_updates": [], "flags_set": {}, "reward_updates": []}
    result_text = ""
    if action in {"attack", "combat", "fight"}:
        if str(monster.get("tier") or "") == "boss":
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "boss_pressure", "name": "Boss 压力", "delta": 1, "max": 6}])
            changes["players"]["player1"] = _apply_monster_retaliation(player, monster, severity=0.6)
            result_text = f"你尝试正面攻击【{monster.get('name')}】，系统判定 Boss 默认不可硬杀；威胁上升，并触发反冲。"
            changes["roll_log"] = {"seed": seed, "d20": d20, "action": action, "target": monster.get("id"), "boss_guard": True}
        else:
            score = d20 + math.floor((int(player.get("str") or 10) - 10) / 2) + math.floor(int(player.get("physical_attack") or 0) / 3) + int(bonuses.get("total") or 0)
            dc = 10 + math.floor(int(monster.get("speed") or 10) / 2)
            hp_before = int(monster.get("hp") or 0)
            if score >= dc:
                damage = max(1, int(player.get("physical_attack") or 1) + int(bonuses.get("weakness_bonus") or 0) - int(monster.get("defense") or 0))
                monster["hp"] = max(0, hp_before - damage)
                if int(monster.get("hp") or 0) <= 0:
                    monster["status"] = "defeated"
                    changes["reward_updates"].append(_record_encounter_reward(session, monster, "monster_defeated"))
                    result_text = f"攻击判定 {score}/{dc} 成功，造成 {damage} 伤害；【{monster.get('name')}】被击退。"
                else:
                    monster["status"] = "alerted"
                    changes["players"]["player1"] = _apply_monster_retaliation(player, monster, severity=0.5)
                    result_text = f"攻击判定 {score}/{dc} 成功，造成 {damage} 伤害；【{monster.get('name')}】仍在逼近。"
            else:
                monster["status"] = "chasing"
                changes["players"]["player1"] = _apply_monster_retaliation(player, monster, severity=1.0)
                result_text = f"攻击判定 {score}/{dc} 失败；【{monster.get('name')}】抢到反击窗口。"
            changes["monster_updates"].append({"id": monster.get("id"), "hp_before": hp_before, "hp_after": monster.get("hp"), "status": monster.get("status")})
            changes["roll_log"] = {"seed": seed, "d20": d20, "action": action, "target": monster.get("id"), "score": score, "dc": dc, "bonuses": bonuses}
    elif action in {"weaken", "probe"}:
        stability_before = max(0, int(monster.get("stability") or 0))
        score = d20 + math.floor((int(player.get("int") or 10) - 10) / 2) + math.floor((int(player.get("spi") or 10) - 10) / 3) + int(bonuses.get("total") or 0)
        dc = 11 + _rarity_rank(monster.get("rank") or "D") * 2 + (2 if str(monster.get("tier") or "") == "boss" else 0)
        if score >= dc:
            if str(monster.get("tier") or "") == "boss":
                monster["stability"] = max(0, stability_before - (2 if score >= dc + 5 else 1))
                monster["status"] = "weakened" if int(monster.get("stability") or 0) <= 0 else "unstable"
                if int(monster.get("stability") or 0) <= 0:
                    changes["reward_updates"].append(_record_encounter_reward(session, monster, "monster_weakened"))
                result_text = f"削弱判定 {score}/{dc} 成功；【{monster.get('name')}】稳定度 {stability_before}->{monster.get('stability')}，正面硬杀仍禁止，但封印/撤离窗口扩大。"
            else:
                monster["status"] = "weakened"
                monster["defense"] = max(0, int(monster.get("defense") or 0) - 1)
                monster["mental_resist"] = max(0, int(monster.get("mental_resist") or 0) - 1)
                changes["reward_updates"].append(_record_encounter_reward(session, monster, "monster_weakened"))
                result_text = f"削弱判定 {score}/{dc} 成功；【{monster.get('name')}】进入削弱状态，后续攻击、封印或逃离更容易。"
        elif score >= dc - 4:
            monster["status"] = "alerted"
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "anomaly_attention", "name": "异常注意", "delta": 1, "max": 6}])
            result_text = f"削弱判定 {score}/{dc} 只得到部分信息；【{monster.get('name')}】被惊动，异常注意上升。"
        else:
            monster["status"] = "alerted"
            changes["players"]["player1"] = _apply_monster_retaliation(player, monster, severity=0.45)
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "anomaly_attention", "name": "异常注意", "delta": 1, "max": 6}])
            _bump_forced_instance_exposure(session, "monsters", 1, "削弱/试探失败")
            result_text = f"削弱判定 {score}/{dc} 失败；【{monster.get('name')}】捕捉到你的试探，触发轻度反噬。"
        changes["monster_updates"].append({
            "id": monster.get("id"),
            "stability_before": stability_before,
            "stability_after": monster.get("stability"),
            "status": monster.get("status"),
        })
        changes["roll_log"] = {"seed": seed, "d20": d20, "action": action, "target": monster.get("id"), "score": score, "dc": dc, "bonuses": bonuses}
    elif action in {"seal", "purify", "exorcise"}:
        seal_before = max(0, int(monster.get("seal_progress") or 0))
        seal_target = max(1, int(monster.get("seal_target") or (3 if str(monster.get("tier") or "") == "boss" else 2)))
        stability = max(0, int(monster.get("stability") or 0))
        stability_penalty = 2 if str(monster.get("tier") or "") == "boss" and stability > 0 else 0
        score = d20 + math.floor((int(player.get("spi") or 10) - 10) / 2) + math.floor((int(player.get("int") or 10) - 10) / 3) + int(bonuses.get("total") or 0)
        dc = 12 + _rarity_rank(monster.get("rank") or "D") * 2 + stability_penalty
        if score >= dc:
            gain = 2 if score >= dc + 5 else 1
            monster["seal_progress"] = min(seal_target, seal_before + gain)
            if int(monster.get("seal_progress") or 0) >= seal_target:
                monster["status"] = "sealed"
                changes["reward_updates"].append(_record_encounter_reward(session, monster, "monster_sealed"))
                result_text = f"封印判定 {score}/{dc} 成功；封印进度 {seal_before}->{monster.get('seal_progress')}/{seal_target}，【{monster.get('name')}】已被系统记录为封印。"
            else:
                monster["status"] = "contained"
                result_text = f"封印判定 {score}/{dc} 成功；封印进度 {seal_before}->{monster.get('seal_progress')}/{seal_target}，还需要继续补完条件。"
        elif score >= dc - 4:
            monster["seal_progress"] = min(seal_target, seal_before + 1)
            monster["status"] = "unstable"
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "seal_backlash", "name": "封印反噬", "delta": 1, "max": 6}])
            result_text = f"封印判定 {score}/{dc} 部分成功；封印进度 {seal_before}->{monster.get('seal_progress')}/{seal_target}，但反噬时钟推进。"
        else:
            monster["status"] = "chasing"
            changes["players"]["player1"] = _apply_monster_retaliation(player, monster, severity=0.55)
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "seal_backlash", "name": "封印反噬", "delta": 1, "max": 6}])
            _bump_forced_instance_exposure(session, "monsters", 1, "封印失败")
            result_text = f"封印判定 {score}/{dc} 失败；封印结构被冲开，【{monster.get('name')}】开始追击。"
        changes["monster_updates"].append({
            "id": monster.get("id"),
            "seal_before": seal_before,
            "seal_after": monster.get("seal_progress"),
            "seal_target": seal_target,
            "status": monster.get("status"),
        })
        changes["roll_log"] = {"seed": seed, "d20": d20, "action": action, "target": monster.get("id"), "score": score, "dc": dc, "bonuses": bonuses}
    elif action in {"escape", "avoid", "flee", "evade"}:
        alert_bonus = 2 if str(monster.get("status") or "") in {"alerted", "chasing"} else 0
        score = d20 + math.floor((int(player.get("agi") or 10) - 10) / 2) + int(bonuses.get("total") or 0)
        dc = int(monster.get("detection") or 10) + math.floor(int(monster.get("speed") or 10) / 2) + alert_bonus + int(bonuses.get("boss_lock_penalty") or 0)
        if score >= dc + 5:
            monster["status"] = "evaded"
            _add_condition_unique(player, "脱离遭遇窗口")
            changes["players"]["player1"] = {"hp_delta": 0, "san_delta": 0, "spi_delta": 0, "conditions_add": ["脱离遭遇窗口"], "conditions_remove": []}
            changes["reward_updates"].append(_record_encounter_reward(session, monster, "monster_evaded"))
            result_text = f"逃跑判定 {score}/{dc} 大成功；你移动到安全相邻区域，暂时摆脱了【{monster.get('name')}】。"
        elif score >= dc:
            monster["status"] = "alerted"
            _add_condition_unique(player, "脱离遭遇窗口")
            changes["players"]["player1"] = {"hp_delta": 0, "san_delta": 0, "spi_delta": 0, "conditions_add": ["脱离遭遇窗口"], "conditions_remove": []}
            changes["reward_updates"].append(_record_encounter_reward(session, monster, "monster_evaded"))
            result_text = f"逃跑判定 {score}/{dc} 成功；你脱离当前遭遇，但【{monster.get('name')}】仍保持警戒。"
        elif score >= dc - 5:
            monster["status"] = "chasing"
            _add_condition_unique(player, "路线暴露")
            retaliation = _apply_monster_retaliation(player, monster, severity=0.35)
            retaliation["conditions_add"] = list(dict.fromkeys((retaliation.get("conditions_add") or []) + ["路线暴露"]))
            changes["players"]["player1"] = retaliation
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "chase_pressure", "name": "追逐压力", "delta": 1, "max": 6}])
            result_text = f"逃跑判定 {score}/{dc} 部分成功；你离开原地，但路线暴露，追逐压力上升。"
        else:
            monster["status"] = "chasing"
            _add_condition_unique(player, "暴露")
            retaliation = _apply_monster_retaliation(player, monster, severity=0.8)
            retaliation["conditions_add"] = list(dict.fromkeys((retaliation.get("conditions_add") or []) + ["暴露"]))
            changes["players"]["player1"] = retaliation
            changes["clock_updates"] = _apply_clock_updates(session, [{"id": "chase_pressure", "name": "追逐压力", "delta": 1, "max": 6}])
            _bump_forced_instance_exposure(session, "monsters", 1, "逃离失败")
            result_text = f"逃跑判定 {score}/{dc} 失败；你暴露了路线，【{monster.get('name')}】开始追击。"
        changes["monster_updates"].append({"id": monster.get("id"), "status": monster.get("status")})
        changes["roll_log"] = {"seed": seed, "d20": d20, "action": action, "target": monster.get("id"), "score": score, "dc": dc, "bonuses": bonuses}
    else:
        return False, "未知遭遇动作。", {}
    st["player1"] = player
    session["stats"] = st
    _save_monster_instances(session, monsters, result_text)
    patch = _append_rules_patch(session, "rules_engine.encounter", changes)
    session["runtime_state"] = _runtime_state_view(session)
    return True, result_text, patch


def cmd_encounter_action_with_ai_player(
    user_id: int,
    action_type: str,
    target: str = "",
    detail: str = "",
    ai_player_action: str = "",
) -> tuple[str, str]:
    uid = int(user_id)
    original_session = r2_store.get_wenyou_session(uid)
    if not isinstance(original_session, dict):
        return "文游：当前没有进行中的局，请先开局。", ""
    session = copy.deepcopy(original_session)
    ok, result_text, _patch = _resolve_encounter_action(session, action_type, target=target, detail=detail)
    if not ok:
        return f"文游：{result_text}", ""
    r2_store.save_wenyou_session(uid, session)
    gm_note = f"【系统判定】{result_text}请只根据这个已结算结果生成剧情反应；不要重算命中、逃跑、怪物 HP、稳定度、封印进度或玩家伤害。"
    ok_action, msg = cmd_record_action(uid, gm_note, "player1")
    if not ok_action:
        return msg, ""
    ai_player_action = _normalize_external_ai_player_action(ai_player_action)
    if ai_player_action:
        ok_ai_player, ai_player_msg = cmd_record_action(uid, ai_player_action, "player2")
        if not ok_ai_player:
            logger.warning("文游AI玩家外部行动记录失败 user_id=%s error=%s", user_id, ai_player_msg)
            ai_player_action = ""
    out = cmd_go(uid)
    if out.startswith("文游：GM 调用失败"):
        r2_store.save_wenyou_session(uid, original_session)
        return out, ""
    return f"【遭遇结算】{result_text}\n\n{out}", ai_player_action


def _build_gm_messages(session: dict) -> tuple[str, list[dict]]:
    """把 session 转成 GM API：system 文本 + 多轮 messages（仅 user/assistant 角色给模型）。"""
    _session_ensure_stats(session)
    fw = _framework_for_runtime(session.get("framework") or {})
    system = _GM_SYSTEM_TEMPLATE.format(
        instance_line=_framework_instance_line(fw),
        instance_genre=_normalize_instance_genre(fw.get("instance_genre")),
        genre_note_line=_format_genre_note_line(fw),
        genre_rules_block=_format_genre_rules_for_gm(fw),
        world=fw.get("world", ""),
        player1_name=fw.get("player1_name", "玩家一"),
        player1_role=fw.get("player1_role", ""),
        player2_name=fw.get("player2_name", "玩家二"),
        player2_role=fw.get("player2_role", ""),
        conflict=fw.get("conflict", ""),
        failure_hint=fw.get("failure_hint") or "由主神规则判定。",
        reward_hint=fw.get("reward_hint") or "视表现给予风味向回报。",
        tutorial_guidance_block=_format_tutorial_guides_for_gm(fw),
        forced_instance_guidance_block=_format_forced_instance_guidance_for_gm(session, fw),
        tasker_regiment_block=_format_tasker_regiment_for_gm(fw),
        blueprint_block=_format_blueprint_for_gm(fw),
        current_stats_block=_format_stats_for_gm_prompt(session),
    )
    msgs: list[dict] = []
    for h in session.get("history") or []:
        role = (h.get("role") or "").lower()
        content = (h.get("content") or "").strip()
        if not content:
            continue
        if role == "gm":
            msgs.append({"role": "assistant", "content": content})
        elif role in ("player1", "player2"):
            who = "玩家一" if role == "player1" else "玩家二"
            msgs.append({"role": "user", "content": f"{who}：{content}"})
    return system, msgs


def cmd_go(user_id: int) -> str:
    """结算本轮，调用 GM。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return "文游：当前没有进行中的局，请先在系统空间开局。"
    phase = _session_phase(session)
    if phase in {"settlement", "archived"}:
        return "文游：当前处于系统空间结算阶段，不能继续推进。请先完成最终结算。"

    _session_ensure_stats(session)
    pr = session.get("pending_round") or {}
    p1 = pr.get("player1_lines") or []
    p2 = pr.get("player2_lines") or []
    p1_text = "\n".join(p1).strip() or "（玩家一暂无行动描述）"
    p2_text = "\n".join(p2).strip() or "（玩家二本轮暂无行动描述）"

    user_blob = f"玩家一本轮行动：\n{p1_text}\n\n玩家二本轮行动：\n{p2_text}\n"

    system, gm_msgs = _build_gm_messages(session)
    # 追加本轮结算 user 消息（作为对 GM 的输入）
    gm_msgs = gm_msgs + [{"role": "user", "content": f"请根据以下本轮行动结算并推进剧情（给出 GM 叙述与选项）：\n{user_blob}"}]

    gm_out = call_wenyou_deepseek(gm_msgs, system=system, temperature=0.75)
    if not gm_out:
        return "文游：GM 调用失败，请稍后重试推进。"

    event_intent = _parse_event_intent(gm_out)
    parsed = _parse_main_god_panel(gm_out)
    if parsed:
        _merge_panel_into_session_stats(session, parsed, include_vitals=not bool(event_intent))
    state_patch = _apply_event_intent(session, event_intent)

    ts = now_beijing_iso()
    for line in p1:
        if str(line or "").strip():
            session.setdefault("history", []).append({"role": "player1", "content": str(line).strip(), "timestamp": ts})
    for line in p2:
        if str(line or "").strip():
            session.setdefault("history", []).append({"role": "player2", "content": str(line).strip(), "timestamp": ts})
    session.setdefault("history", []).append({"role": "gm", "content": gm_out, "timestamp": ts})
    session["pending_round"] = {"player1_lines": [], "player2_lines": []}
    r2_store.save_wenyou_session(uid, session)
    _update_wenyou_card_for_round(uid, session, p1_text, p2_text, gm_out)
    _archive_wenyou_round_for_recent_memory(uid, session, p1_text, p2_text, gm_out)

    narrative = _strip_player_brief_blocks(_strip_main_god_panel(gm_out))
    patch_text = _format_state_patch_for_display(state_patch)
    foot = _format_status_footer(session)
    if patch_text:
        narrative = f"{narrative}\n\n{patch_text}" if narrative.strip() else patch_text
    display = f"{narrative}\n\n{foot}" if narrative.strip() else foot

    return f"—— 主神系统 ——\n\n{display}"


def _archive_settled_session(uid: int, session: dict) -> None:
    session["phase"] = "archived"
    session.setdefault("stats", {})["phase"] = "archived"
    archive = {
        "gameId": session.get("gameId"),
        "endedAt": now_beijing_iso(),
        "framework": session.get("framework"),
        "stats": session.get("stats"),
        "wallet": session.get("wallet"),
        "settlement": session.get("settlement"),
        "event_log": session.get("event_log"),
        "history": session.get("history"),
    }
    gid = str(session.get("gameId") or "unknown")
    r2_store.save_wenyou_archive_copy(uid, gid, archive)
    r2_store.save_wenyou_last_archive(uid, archive)
    r2_store.delete_wenyou_active_session(uid)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)


def cmd_end(user_id: int, result: str = "", rating: str = "") -> str:
    """最终结算并立即归档本局。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)
        return "文游：当前没有进行中的局。"

    _session_ensure_stats(session)
    settlement = _grant_settlement_reward(uid, session, result=result, rating=rating)
    summary = _format_settlement_summary(settlement)
    ts = now_beijing_iso()
    session.setdefault("history", []).append(
        {
            "role": "gm",
            "content": "【主神提示】副本已结束，主神系统完成结算并归档。\n\n" + summary,
            "timestamp": ts,
        }
    )
    _archive_settled_session(uid, session)
    return "文游：本局已完成结算并归档。\n\n" + summary + "\n\n下一局可在主神空间重新开局。"


def cmd_settle(user_id: int) -> str:
    """结算完成并归档本局。"""
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return "文游：当前没有进行中的局。"
    if _session_phase(session) != "settlement":
        return "文游：当前不在结算阶段。请先结束副本并进入系统空间结算。"

    _archive_settled_session(uid, session)
    return "文游：本局已完成最终结算并归档。下一局可在系统空间重新开局。MiniApp 可查看已完成副本。"
