# 文游：固定群内 /story /go /end，GM 走 DeepSeek，与主聊天链路隔离（存 R2 wenyou/）
import copy
import json
import random
import re
import threading
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import requests

from config import (
    BASE_DIR,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    SUMMARY_EVERY_N_ROUNDS,
    TELEGRAM_WENYOU_OWNER_USER_ID,
    WENYOU_DS_MODEL,
)
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_TEMPLATES_CACHE: Optional[dict] = None
_TEMPLATES_LOCK = threading.Lock()

# 第二次 /story 确认开新局（仅内存，进程重启后需再确认）
_PENDING_STORY_CONFIRM: dict[int, bool] = {}
_PENDING_LOCK = threading.Lock()

# 开局生成框架时注入的 system（无限流 / 副本）
_FRAMEWORK_SYSTEM = """你在为一款「无限流」双人文字跑团生成**单个副本**的设定数据。
整体世界观：存在主神空间；玩家被投入一个又一个副本世界，每个副本有独立规则与任务；你是数据侧，JSON 内用中性表述即可。
**副本类型 instance_genre**（必须选其一，并决定节奏与机关侧重）：**规则怪谈**（条款式规则、告示、广播；**部分规则可为假**、矛盾或诱导，须由玩家自行判断）；**剧情解密**（线索、证言、机关、因果链）；**大逃杀**（缩圈、资源稀缺、淘汰压力）；**对抗**（阵营、互害、结盟与背叛）；**生存撤离**（物资、环境伤害、向撤离点转移）；**潜伏调查**（伪装身份、套取情报、搜查）；**限时任务**（硬性时限或阶段倒计时）。在 `genre_note` 中用一句话写清本局如何体现该类型。
**编制硬性规则**：每个副本固定 **6 名任务者**——玩家两名（玩家一、玩家二「渡」）+ **恰好 4 名 NPC**，同场竞技或同规则约束；难度 **D～S**（D 最低、S 最高），难度越高环境越险、NPC 里越容易出现老练者或「大佬」，也可能更多炮灰；NPC **不一定友善**，可有害人、借刀、欺骗等，JSON 里直接写清立场倾向即可。
须给出 **initial_stats**：两名玩家的初始血量/精神上限、**等级与阶位（D～S）、体力与智慧、血统名称**、主神积分、可选初始道具；体力/智慧会约束或暗示血/精神上限，数值为正整数即可。
opening 建议包含传送/白光/提示音/主神刻板广播之一切入副本场景，但不要冗长。"""


_GM_SYSTEM_TEMPLATE = """你是「无限流」文字跑团里的 **主神系统**（演算与播报界面），兼任本场副本的 GM。
玩家理解中：你像主神空间里的系统音——冷静、偶尔带一点机械感或恶趣味，但**叙事正文**仍要有画面感与文学性，不要通篇说明书腔。

## 当前副本
- 副本编号 / 名称：{instance_line}
- **副本类型**：{instance_genre}
{genre_note_line}- 副本内世界观与场景：{world}
- 玩家一（{player1_name}）的身份：{player1_role}
- 玩家二（{player2_name}）的身份：{player2_role}
- 主神发布的核心任务（通关方向）：{conflict}
- 失败或惩罚方向（虚构，勿过度血腥）：{failure_hint}
- 通关奖励风味（积分、线索、豁免权等）：{reward_hint}

## 本类型玩法要点（整场必须遵守）
{genre_rules_block}

## 难度与任务者编制（必须遵守）
{tasker_regiment_block}

## 主神空间 · 积分 · 系统商店 · 成长 · 生死与回程（叙事规则）
- **主神积分**：用于复活、治疗、**系统商店**购物与强化；数值由你在【主神面板】中维护，扣减/奖励须与剧情因果一致。
- **系统商店**（仅在场地为「主神空间」时重点呈现；副本内一般仅能通过剧情掉落或主神广播「预告」）：玩家可用积分 **购买道具**、**兑换治疗**（恢复血量、精神值）；可消耗积分 **升级血统**（血统名与强化阶位写在面板「血统」栏，阶位风味可与 D～S 挂钩）、**提升体力或智慧**（体力主要关联生命上限、智慧主要关联精神上限；升级后应在面板中同步 **HP/精神 上限** 与体力/智慧数值）。
- **玩家等级与阶位**：每名玩家有 **等级（Lv）**，等级越高综合越强（伤害豁免、判定加值等由叙事体现）；另有 **阶位 D～S**（D 最低、S 最高），可与血统强化、主神评价挂钩。副本结算可发经验、升级或阶位提升契机，**必须**在【主神面板】中更新。
- **死亡与复活**：若玩家角色死亡或判定出局，须给出主神选项感：可用**积分复活**（扣多少在面板中写明，可与难度挂钩），或消耗**指定道具**复活/续命；不得无故满血无代价复活。
- **副本结束**：当副本以通关、失败或强制结算等方式**结束**时，须描写**白光/传送**回到**主神空间**（场地切到主神空间）；之后可逛**系统商店**、治疗、整备再接下一副本。
- **主神空间内**：以休整、商店、治疗、兑换、接下一副本的**氛围**为主，仍可出现轻量事件。

## 当前系统记录的状态（你必须在回复末尾用【主神面板】更新，与剧情一致）
{current_stats_block}

## 无限流玩法（叙事层）
- 每个故事都是**一次副本**；关键节点可有一两句 **【主神提示】**，平时克制。
- **六人场**：四名 NPC 须在剧中可追溯（可退场或死亡，须有因果）。
- 可埋伏线：规则类陷阱、NPC 互害、时间压力等。
- **副本结算**须符合因果；bad end 亦同。

## 你的职责
- 描述环境、NPC、主神播报、事件结果；根据两位玩家行动推进；收到结算信号后做**本轮**推进。

## 回复规范
- 叙事约 150-300 字，有画面感；在【主神面板】**之前**，按**副本类型**附上对应**备忘**（见上「本类型玩法要点」）；其中 **规则怪谈** 类**每轮不可省略**【规则备忘】。
- 叙事之后列出 2-3 个行动选项，最后一个固定为「C. 自由行动」。
- **最后**必须附 **【主神面板】**（见下，不可省略）；备忘块始终在【主神面板】**上方**，便于玩家对照。

## 【主神面板】固定格式（每次回复末尾必须原样包含，一行一项，便于系统解析）
【主神面板】
场地：副本 或 主神空间
积分：整数
玩家一 HP 当前/最大 精神 当前/最大
玩家一等级：正整数
玩家一阶位：D、C、B、A、S 之一
玩家一体力：正整数（关联生命上限为主）
玩家一智慧：正整数（关联精神上限为主）
玩家一血统：简短名称（含强化说明亦可）
玩家二 HP 当前/最大 精神 当前/最大
玩家二等级：正整数
玩家二阶位：D、C、B、A、S 之一
玩家二体力：正整数
玩家二智慧：正整数
玩家二血统：简短名称
道具：无 或 道具名用顿号分隔

说明：场地为「主神空间」时表示已回到主神空间；购物、强化血统、加体力/智慧、治疗、升级与阶位变化，均须体现在面板与积分中。

## 严格禁止
- 不得替玩家做决定，不得描写玩家角色的具体行动、表情、内心独白
- 不得擅自跳过阶段；禁止过度血腥虐待描写

## 你的边界
你只负责世界、NPC、主神播报、环境、事件结果；玩家的一切行动只由玩家决定。
"""


def _load_templates() -> dict:
    global _TEMPLATES_CACHE
    with _TEMPLATES_LOCK:
        if _TEMPLATES_CACHE is not None:
            return _TEMPLATES_CACHE
        path = BASE_DIR / "prompts" / "wenyou_templates.json"
        try:
            if path.exists():
                _TEMPLATES_CACHE = json.loads(path.read_text(encoding="utf-8"))
            else:
                _TEMPLATES_CACHE = {"worlds": [], "conflicts": [], "roles": []}
        except Exception:
            logger.exception("读取 wenyou_templates.json 失败")
            _TEMPLATES_CACHE = {"worlds": [], "conflicts": [], "roles": []}
        return _TEMPLATES_CACHE


def _extract_json_object(text: str) -> Optional[dict]:
    """从模型输出中解析第一个 JSON 对象。"""
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    raw = m.group(0)
    for attempt in (raw, raw.replace("\n", " ")):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def call_wenyou_deepseek(messages: list[dict], system: str, temperature: float = 0.7) -> Optional[str]:
    """调用 DeepSeek Chat Completions（非流式）。"""
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，无法调用文游 GM")
        return None
    url = (DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    body = {
        "model": WENYOU_DS_MODEL or "deepseek-chat",
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": False,
        "temperature": temperature,
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
        if r.status_code != 200:
            logger.warning("文游 DeepSeek 非 200 status=%s body=%s", r.status_code, (r.text or "")[:400])
            return None
        data = r.json() if r.content else {}
        ch0 = (data.get("choices") or [{}])[0] or {}
        msg = ch0.get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        return content.strip() if isinstance(content, str) else str(content).strip()
    except Exception as e:
        logger.exception("文游 DeepSeek 请求失败: %s", e)
        return None


def _framework_prompt_random(seeds: dict) -> str:
    return f"""根据以下随机种子，生成**无限流模式下的一场副本**框架，并输出 **严格 JSON**（不要 markdown 代码块），字段如下：
{{
  "instance_code": "副本编号，如 M-218、F-07",
  "instance_name": "副本常用名，2-8 字为宜",
  "instance_genre": "必须是以下之一：规则怪谈、剧情解密、大逃杀、对抗、生存撤离、潜伏调查、限时任务",
  "genre_note": "一句话说明本局如何体现该类型（如规则怪谈里哪些告示可疑；对抗里阵营关系等）",
  "difficulty": "必须是 D、C、B、A、S 之一（D 最低，S 最高；须与整体危险度、NPC 层次一致）",
  "world": "本副本**内部**世界观与场景 2-4 句（不写主神空间全貌，聚焦本图）",
  "player1_name": "玩家一在本副本中的称呼或名字",
  "player1_role": "职业、特质、一个秘密（简短）",
  "player2_name": "渡",
  "player2_role": "渡在本副本中的身份、特质、一个秘密（可与人设微妙呼应）",
  "npc_taskers": [
    {{"name": "NPC 代号或称呼", "tier_note": "炮灰|新人|老练|大佬 等定位", "stance": "合作|中立|损人利己|暗藏祸心 等", "blurb": "一句话外貌或特征"}},
    {{"name": "...", "tier_note": "...", "stance": "...", "blurb": "..."}},
    {{"name": "...", "tier_note": "...", "stance": "...", "blurb": "..."}},
    {{"name": "...", "tier_note": "...", "stance": "...", "blurb": "..."}}
  ],
  "conflict": "主神发布的核心任务 / 通关条件 1-3 句，可略带残酷或幽默感",
  "failure_hint": "失败、抹杀或惩罚方向的**一句**提示（虚构，勿过度血腥）",
  "reward_hint": "通关后可能获得的奖励风味一句（如积分、线索、豁免；可不写具体数字）",
  "initial_stats": {{
    "points": 100,
    "player1": {{"hp": 100, "hp_max": 100, "san": 100, "san_max": 100, "level": 1, "rank": "D", "vit": 10, "wis": 10, "bloodline": "凡人"}},
    "player2": {{"hp": 100, "hp_max": 100, "san": 100, "san_max": 100, "level": 1, "rank": "D", "vit": 10, "wis": 10, "bloodline": "凡人"}},
    "items": ["可选：与副本相关的消耗品或线索道具，无则 []"]
  }},
  "opening": "开场 4-8 句：建议含传送/白光/提示音/主神刻板广播之一；**必须**出现与玩家同场的其他任务者（四名 NPC）的登场感或存在感，再进入场景，有画面感"
}}

**编制硬性规则**：`npc_taskers` 必须恰好 **4 个对象**，与两名玩家合计 **6 名任务者**；NPC 可有好人、坏人、坑货、炮灰、大佬，与 `difficulty` 相匹配。**instance_genre** 须与 `world`、`conflict` 一致；**initial_stats** 须含主神积分、双方 HP/精神、**等级与阶位（D～S）、体力与智慧、血统名称**、背包（可为空数组）。

随机种子（融入副本，不必照抄字面）：
- 建议难度：{seeds.get("difficulty", "C")}
- 建议副本类型：{seeds.get("instance_genre", "剧情解密")}
- 世界基调：{seeds.get("world", "")}
- 冲突类型：{seeds.get("conflict", "")}
- 角色灵感一：{seeds.get("role_a", "")}
- 角色灵感二：{seeds.get("role_b", "")}

只输出 JSON，不要解释。"""


def _framework_prompt_custom(keywords: str) -> str:
    return f"""根据以下关键词，生成**无限流模式下的一场副本**框架，并输出 **严格 JSON**（不要 markdown 代码块），字段如下：
{{
  "instance_code": "副本编号",
  "instance_name": "副本名",
  "instance_genre": "规则怪谈、剧情解密、大逃杀、对抗、生存撤离、潜伏调查、限时任务 之一",
  "genre_note": "一句话说明本局如何体现该类型",
  "difficulty": "D、C、B、A、S 之一",
  "world": "本副本内部世界观与场景 2-4 句",
  "player1_name": "玩家一称呼",
  "player1_role": "职业、特质、一个秘密（简短）",
  "player2_name": "渡",
  "player2_role": "渡在本副本中的身份、特质、一个秘密（简短）",
  "npc_taskers": [
    {{"name": "", "tier_note": "", "stance": "", "blurb": ""}},
    {{"name": "", "tier_note": "", "stance": "", "blurb": ""}},
    {{"name": "", "tier_note": "", "stance": "", "blurb": ""}},
    {{"name": "", "tier_note": "", "stance": "", "blurb": ""}}
  ],
  "conflict": "主神核心任务 / 通关条件 1-3 句",
  "failure_hint": "失败或惩罚方向一句（虚构，勿过度血腥）",
  "reward_hint": "通关奖励风味一句（可不写具体数字）",
  "initial_stats": {{
    "points": 100,
    "player1": {{"hp": 100, "hp_max": 100, "san": 100, "san_max": 100, "level": 1, "rank": "D", "vit": 10, "wis": 10, "bloodline": "凡人"}},
    "player2": {{"hp": 100, "hp_max": 100, "san": 100, "san_max": 100, "level": 1, "rank": "D", "vit": 10, "wis": 10, "bloodline": "凡人"}},
    "items": []
  }},
  "opening": "开场 4-8 句，建议含主神传送或播报感；须体现与四名 NPC 任务者同场（6 人编制）"
}}

**编制**：`npc_taskers` 必须恰好 4 条，与两名玩家合计 6 名任务者；NPC 可炮灰可大佬、可善可恶。须带 **instance_genre**、**genre_note** 与 **initial_stats**（含等级、阶位 D～S、体力、智慧、血统）。

关键词：{keywords}

只输出 JSON，不要解释。"""


# 副本难度 D～S（D 最低，S 最高）
_WENYOU_DIFFICULTIES = frozenset({"D", "C", "B", "A", "S"})

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


def _normalize_difficulty(value: Any) -> str:
    s = str(value or "").strip().upper()
    return s if s in _WENYOU_DIFFICULTIES else "C"


def _normalize_instance_genre(value: Any) -> str:
    s = str(value or "").strip()
    return s if s in _WENYOU_INSTANCE_GENRES else "剧情解密"


def _format_genre_note_line(fw: dict) -> str:
    """GM 模板中「本局类型说明」行；无则空串。"""
    note = str(fw.get("genre_note") or "").strip()
    if not note:
        return ""
    return f"- 本局类型说明：{note}\n"


def _format_genre_rules_for_gm(fw: dict) -> str:
    """按当前副本类型生成「本类型玩法要点」正文（类型说明见上「本局类型说明」行）。"""
    g = _normalize_instance_genre(fw.get("instance_genre"))

    blocks: dict[str, str] = {
        "规则怪谈": (
            "- **规则怪谈**：环境中须有**条款式规则**、告示、广播或系统音；**部分规则可能为假**、**相互矛盾**或**诱导送死**，玩家须自行判断；NPC 与「官方」也可能误导。\n"
            "- **【规则备忘】**（本类型**每轮必附**，且放在**【主神面板】之前**）：用 2～5 条列出**当前已知的规则要点**（可缩写原文），并标注「待验证」「疑似假」「已证真」等，**避免玩家忘记**。\n"
        ),
        "剧情解密": (
            "- **剧情解密**：以**线索、证言、机关、因果链**推进；避免无条件通关。\n"
            "- **【线索备忘】**（每轮建议在【主神面板】之前**简短**）：列出当前已掌握关键线索或待解疑点 1～4 条。\n"
        ),
        "大逃杀": (
            "- **大逃杀**：**缩圈、资源稀缺、淘汰或击杀威胁**构成压力；**【安全区·威胁备忘】**（每轮在【主神面板】之前**简短**）：安全区/倒计时/场上主要威胁。\n"
        ),
        "对抗": (
            "- **对抗**：**阵营目标、互害、结盟与背叛**；**【阵营备忘】**（每轮【主神面板】之前**简短**）：已知阵营与当前目标。\n"
        ),
        "生存撤离": (
            "- **生存撤离**：**物资、环境伤害、向撤离点推进**；**【撤离·物资备忘】**（每轮【主神面板】之前**简短**）：撤离点、物资、环境威胁。\n"
        ),
        "潜伏调查": (
            "- **潜伏调查**：**身份伪装、套取情报、搜查**；**【身份·嫌疑备忘】**（每轮【主神面板】之前**简短**）：当前怀疑对象与已暴露信息。\n"
        ),
        "限时任务": (
            "- **限时任务**：**硬性时限或阶段倒计时**；**【时限备忘】**（每轮【主神面板】之前**一行**）：剩余时间或阶段。\n"
        ),
    }
    body = blocks.get(g, blocks["剧情解密"])
    return body


def _default_player_stats() -> dict:
    """文游单名玩家运行时字段默认值（等级、阶位 D～S、体力/智慧、血统）。"""
    return {
        "hp": 100,
        "hp_max": 100,
        "san": 100,
        "san_max": 100,
        "level": 1,
        "rank": "D",
        "vit": 10,
        "wis": 10,
        "bloodline": "凡人",
    }


def _merge_one_player(cur: dict, new: dict) -> dict:
    """将 GM 面板中的部分字段合并进玩家状态，并约束血/精神在上限内。"""
    out = dict(cur)
    for k in ("hp", "hp_max", "san", "san_max", "level", "vit", "wis"):
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
    if "bloodline" in new:
        bl = str(new["bloodline"]).strip()[:48]
        if bl:
            out["bloodline"] = bl
    hm = max(1, int(out.get("hp_max") or 100))
    sm = max(1, int(out.get("san_max") or 100))
    out["hp_max"] = hm
    out["san_max"] = sm
    if "hp" in new:
        out["hp"] = max(0, min(int(new["hp"]), hm))
    else:
        out["hp"] = max(0, min(int(out.get("hp", 0)), hm))
    if "san" in new:
        out["san"] = max(0, min(int(new["san"]), sm))
    else:
        out["san"] = max(0, min(int(out.get("san", 0)), sm))
    return out


def _normalize_npc_taskers(raw: dict) -> list[dict]:
    """固定 4 条 NPC，与两名玩家合计 6 名任务者。"""
    arr = raw.get("npc_taskers")
    if not isinstance(arr, list):
        arr = []
    out: list[dict] = []
    for i in range(4):
        if i < len(arr) and isinstance(arr[i], dict):
            d = arr[i]
            out.append(
                {
                    "name": str(d.get("name") or f"NPC{i+1}")[:48].strip(),
                    "tier_note": str(d.get("tier_note") or "未知")[:32].strip(),
                    "stance": str(d.get("stance") or "立场未明")[:48].strip(),
                    "blurb": str(d.get("blurb") or "")[:200].strip(),
                }
            )
        else:
            out.append(
                {
                    "name": f"任务者{i+3}",
                    "tier_note": "待定",
                    "stance": "立场未明",
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
    n = out.get("npc_taskers")
    if not isinstance(n, list) or len(n) != 4:
        out["npc_taskers"] = _normalize_npc_taskers(out)
    return out


def _format_tasker_regiment_for_gm(fw: dict) -> str:
    """写入 GM system：难度 + 六人编制说明 + 四 NPC 档案。"""
    diff = _normalize_difficulty(fw.get("difficulty"))
    p1n = fw.get("player1_name") or "玩家一"
    p2n = fw.get("player2_name") or "渡"
    lines = [
        f"- 难度等级：**{diff}**（D 最易，S 最险；越高则环境越危险、规则越苛刻，NPC 中越容易混有「大佬」或「炮灰」，恶意与博弈也更强）。",
        f"- 编制：玩家一「{p1n}」、玩家二「{p2n}」+ **4 名 NPC 任务者**，共 **6 人**，须在同一副本规则下互动（NPC 可分批登场、可退场或死亡，但须有因果，不得无交代消失）。",
        "- 四名 NPC 可与难度相应：低难度多为炮灰、新人；高难度可出现老练者或关键「大佬」；**并非全是好人**，可有坑害、借刀、欺骗、损人利己；禁止过度血腥虐待描写。",
        "",
        "四名 NPC 档案（须在剧情中落实）：",
    ]
    for i, n in enumerate(fw.get("npc_taskers") or []):
        if isinstance(n, dict):
            lines.append(
                f"  · {i+1}. 「{n.get('name', '')}」｜{n.get('tier_note', '')}｜立场：{n.get('stance', '')}｜{n.get('blurb', '')}"
            )
    return "\n".join(lines)


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
    return {
        "instance_code": code,
        "instance_name": name,
        "world": str(raw.get("world") or "").strip(),
        "instance_genre": _normalize_instance_genre(raw.get("instance_genre")),
        "genre_note": gn[:300] if gn else "",
        "player1_name": str(raw.get("player1_name") or "玩家一").strip(),
        "player1_role": str(raw.get("player1_role") or "").strip(),
        "player2_name": str(raw.get("player2_name") or "渡").strip(),
        "player2_role": str(raw.get("player2_role") or "").strip(),
        "conflict": str(raw.get("conflict") or "").strip(),
        "failure_hint": str(raw.get("failure_hint") or "由主神规则判定，细节在副本中逐步显露。").strip(),
        "reward_hint": str(raw.get("reward_hint") or "视通关表现给予积分或线索类回报（风味）。").strip(),
        "opening": str(raw.get("opening") or "").strip(),
        "difficulty": _normalize_difficulty(raw.get("difficulty")),
        "npc_taskers": _normalize_npc_taskers(raw),
        "initial_stats": _normalize_initial_stats(raw),
    }


def _normalize_initial_stats(raw: dict) -> dict:
    """开局 JSON 中的 initial_stats：积分、双玩家血/精神/等级阶位/体力智慧/血统、道具列表。"""
    ist = raw.get("initial_stats")
    if not isinstance(ist, dict):
        ist = {}

    def _one(pk: str) -> dict:
        d = ist.get(pk) if isinstance(ist.get(pk), dict) else {}
        hm = max(1, int(d.get("hp_max") or 100))
        sm = max(1, int(d.get("san_max") or 100))
        h = max(0, min(int(d.get("hp") or hm), hm))
        s = max(0, min(int(d.get("san") or sm), sm))
        lv = max(1, int(d.get("level") or 1))
        rk = _normalize_difficulty(d.get("rank") or d.get("tier") or "D")
        vit = max(0, int(d.get("vit") or d.get("vitality") or 10))
        wis = max(0, int(d.get("wis") or d.get("wisdom") or 10))
        bl = str(d.get("bloodline") or "凡人").strip()[:48] or "凡人"
        return {
            "hp": h,
            "hp_max": hm,
            "san": s,
            "san_max": sm,
            "level": lv,
            "rank": rk,
            "vit": vit,
            "wis": wis,
            "bloodline": bl,
        }

    pts = max(0, int(ist.get("points") or 100))
    items = ist.get("items")
    if not isinstance(items, list):
        items = []
    items_clean = [str(x).strip()[:40] for x in items if str(x).strip()][:20]
    return {
        "points": pts,
        "player1": _one("player1"),
        "player2": _one("player2"),
        "items": items_clean,
    }


def _stats_runtime_from_framework(fw: dict) -> dict:
    """由 framework.initial_stats 生成运行时 stats（含 phase、inventory）。"""
    fw = _framework_for_runtime(dict(fw or {}))
    init = _normalize_initial_stats({"initial_stats": fw.get("initial_stats")})
    return {
        "phase": "instance",
        "points": init["points"],
        "player1": dict(init["player1"]),
        "player2": dict(init["player2"]),
        "inventory": list(init.get("items") or []),
    }


def _session_ensure_stats(session: dict) -> None:
    """旧 session 无 stats 时从 framework 补全。"""
    if session.get("stats") and isinstance(session["stats"], dict):
        session["stats"].setdefault("phase", "instance")
        session["stats"].setdefault("inventory", [])
        session["stats"].setdefault("points", 100)
        base = _default_player_stats()
        for k in ("player1", "player2"):
            cur = session["stats"].get(k)
            if not isinstance(cur, dict):
                session["stats"][k] = dict(base)
            else:
                for bk, bv in base.items():
                    cur.setdefault(bk, bv)
        return
    fw = session.get("framework") or {}
    session["stats"] = _stats_runtime_from_framework(_framework_for_runtime(fw))


def _format_stats_for_gm_prompt(session: dict) -> str:
    """供 GM system 占位：当前积分、场地、血精神、成长与血统、道具。"""
    _session_ensure_stats(session)
    st = session["stats"]
    loc = "主神空间" if (st.get("phase") == "hub") else "副本"
    p1 = st.get("player1") or {}
    p2 = st.get("player2") or {}
    inv = st.get("inventory") or []
    inv_s = "、".join(inv) if inv else "无"

    def _line_player(label: str, p: dict) -> str:
        return (
            f"- {label}：HP {p.get('hp', 0)}/{p.get('hp_max', 1)}，精神 {p.get('san', 0)}/{p.get('san_max', 1)}；"
            f"Lv{p.get('level', 1)} 阶位{p.get('rank', 'D')}；"
            f"体力 {p.get('vit', 0)} 智慧 {p.get('wis', 0)}；血统：{p.get('bloodline', '凡人')}"
        )

    return (
        f"- 场地（系统记录）：{loc}\n"
        f"- 主神积分：{int(st.get('points') or 0)}\n"
        f"{_line_player('玩家一', p1)}\n"
        f"{_line_player('玩家二', p2)}\n"
        f"- 道具：{inv_s}"
    )


def _format_status_footer(session: dict) -> str:
    """Telegram 固定展示的状态栏（与【主神面板】数值对齐，以 session 为准）。"""
    _session_ensure_stats(session)
    st = session["stats"]
    loc = "主神空间" if st.get("phase") == "hub" else "副本"
    p1 = st.get("player1") or {}
    p2 = st.get("player2") or {}
    inv = st.get("inventory") or []
    inv_s = "、".join(inv) if inv else "无"

    def _foot_player(p: dict) -> str:
        return (
            f"血{p.get('hp', 0)}/{p.get('hp_max', 1)} 精{p.get('san', 0)}/{p.get('san_max', 1)}｜"
            f"Lv{p.get('level', 1)}·{p.get('rank', 'D')}阶｜体{p.get('vit', 0)} 智{p.get('wis', 0)}｜{p.get('bloodline', '凡人')}"
        )

    return (
        "━━━━━━━━━━━━\n"
        f"【状态】{loc}｜主神积分：{int(st.get('points') or 0)}\n"
        f"玩家一 {_foot_player(p1)}\n"
        f"玩家二 {_foot_player(p2)}\n"
        f"道具：{inv_s}\n"
        "━━━━━━━━━━━━"
    )


def _strip_main_god_panel(text: str) -> str:
    """去掉【主神面板】及之后内容，供注入与展示叙事。"""
    if not text or "【主神面板】" not in text:
        return (text or "").strip()
    return text.split("【主神面板】", 1)[0].strip()


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
    m = re.search(rf"{label}阶位[：:]\s*([DCSBA])", block)
    if m:
        out["rank"] = m.group(1).upper()
    m = re.search(rf"{label}体力[：:]\s*(\d+)", block)
    if m:
        out["vit"] = int(m.group(1))
    m = re.search(rf"{label}智慧[：:]\s*(\d+)", block)
    if m:
        out["wis"] = int(m.group(1))
    m = re.search(rf"{label}血统[：:]\s*(.+?)(?:\n|$)", block)
    if m:
        out["bloodline"] = m.group(1).strip()
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
        out["phase"] = "hub" if ("主神" in v or "空间" in v) else "instance"
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


def _merge_panel_into_session_stats(session: dict, parsed: dict) -> None:
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
        st[pk] = _merge_one_player(cur, parsed[pk])
    if "inventory" in parsed:
        st["inventory"] = list(parsed["inventory"])


def generate_framework_random() -> tuple[Optional[dict], Optional[str]]:
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
        "difficulty": random.choice(["D", "C", "B", "A", "S"]),
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
        return None, "文游：框架解析失败，请重试 /story。"
    return _normalize_framework(data), None


def generate_framework_custom(keywords: str) -> tuple[Optional[dict], Optional[str]]:
    if not keywords.strip():
        return None, "文游：请带上关键词，例如 /story 赛博朋克 无限流"
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
    return {
        "gameId": gid,
        "startedAt": ts,
        "framework": framework,
        "stats": _stats_runtime_from_framework(fw),
        "history": [
            {"role": "gm", "content": opening, "timestamp": ts},
        ],
        "pending_round": {"player1_lines": [], "player2_lines": []},
    }


def _format_framework_lines(fw: dict) -> str:
    fw = _framework_for_runtime(fw)
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
    genre_head = f"【副本类型】{g}" + (f"｜{gn}" if gn else "") + "\n\n"
    npc_lines = []
    for i, n in enumerate(fw.get("npc_taskers") or []):
        if isinstance(n, dict):
            npc_lines.append(
                f"  · NPC{i+1}「{n.get('name', '')}」{n.get('tier_note', '')}｜{n.get('stance', '')}｜{n.get('blurb', '')}"
            )
    npc_block = "\n".join(npc_lines) if npc_lines else "  （无）"
    return (
        f"{head}"
        f"【难度】{diff}（D 最低，S 最高）\n"
        f"{genre_head}"
        f"【任务者（固定 6 人：玩家 + 4 名 NPC）】\n"
        f"· 玩家一「{fw.get('player1_name', '玩家一')}」\n{fw.get('player1_role', '')}\n\n"
        f"· 玩家二「{fw.get('player2_name', '渡')}」\n{fw.get('player2_role', '')}\n\n"
        f"【四名 NPC 任务者】\n{npc_block}\n\n"
        f"【副本场景】\n{fw.get('world', '')}\n\n"
        f"【主神任务】\n{fw.get('conflict', '')}\n\n"
        f"【失败倾向】\n{fw.get('failure_hint', '')}\n\n"
        f"【通关回报（风味）】\n{fw.get('reward_hint', '')}"
    )


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


def cmd_story(user_id: int, keywords: Optional[str]) -> str:
    """处理 /story [关键词]；含二次确认逻辑。"""
    uid = int(user_id)
    existing = r2_store.get_wenyou_session(uid)

    with _PENDING_LOCK:
        pending = _PENDING_STORY_CONFIRM.get(uid, False)

    if existing and existing.get("gameId"):
        if not pending:
            with _PENDING_LOCK:
                _PENDING_STORY_CONFIRM[uid] = True
            return "文游：已有进行中的局。若确定要开新局，请再发一次 /story（会丢弃当前进度）。"
        # 第二次确认
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)

    if keywords and keywords.strip():
        fw, err = generate_framework_custom(keywords)
    else:
        fw, err = generate_framework_random()
    if err or not fw:
        return err or "文游：开局失败。"

    session = _new_session(fw)
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    head = "文游开局成功（无限流 · 主神副本模式）。\n\n" + _format_framework_lines(fw) + "\n\n—— 主神系统 / GM ——\n\n"
    foot = _format_status_footer(session)
    return head + fw.get("opening", "") + "\n\n" + foot


def record_group_player_line(user_id: int, text: str) -> None:
    """群内非指令消息：记入本轮玩家一行动（带文游前缀语义，存 session）。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return
    line = (text or "").strip()
    if not line:
        return
    pr = session.setdefault("pending_round", {})
    pr.setdefault("player1_lines", []).append(line)
    ts = now_beijing_iso()
    session.setdefault("history", []).append(
        {"role": "player1", "content": f"[文游] {line}", "timestamp": ts}
    )
    r2_store.save_wenyou_session(uid, session)


def record_group_player2_line(text: str) -> None:
    """
    群内主 Bot（渡）发言：记入本轮玩家二行动。
    文游会话始终挂在 TELEGRAM_WENYOU_OWNER_USER_ID（开局者）下，与玩家一同一局。
    """
    owner_uid = int(TELEGRAM_WENYOU_OWNER_USER_ID or 0)
    if not owner_uid:
        return
    line = (text or "").strip()
    if not line:
        return
    session = r2_store.get_wenyou_session(owner_uid)
    if not session or not session.get("gameId"):
        return
    pr = session.setdefault("pending_round", {})
    pr.setdefault("player2_lines", []).append(line)
    ts = now_beijing_iso()
    session.setdefault("history", []).append(
        {"role": "player2", "content": f"[文游] {line}", "timestamp": ts}
    )
    r2_store.save_wenyou_session(owner_uid, session)


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
        player2_name=fw.get("player2_name", "渡"),
        player2_role=fw.get("player2_role", ""),
        conflict=fw.get("conflict", ""),
        failure_hint=fw.get("failure_hint") or "由主神规则判定。",
        reward_hint=fw.get("reward_hint") or "视表现给予风味向回报。",
        tasker_regiment_block=_format_tasker_regiment_for_gm(fw),
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
            who = "玩家一" if role == "player1" else "玩家二（渡）"
            msgs.append({"role": "user", "content": f"{who}：{content}"})
    return system, msgs


def _append_go_round_to_tg_window(user_id: int, user_blob: str, gm_text: str) -> None:
    """将本轮 GM 输出写入 tg 窗口对话与全局 Last4，便于与私聊合并。"""
    window_id = f"tg_{user_id}"
    from pipeline.cleaner import build_round_cleaned_for_r2

    umsg = {"role": "user", "content": f"[文游] {user_blob}"}
    amsg = {"role": "assistant", "content": f"[文游] GM：\n{gm_text}"}
    try:
        round_messages = build_round_cleaned_for_r2(umsg, amsg)
    except Exception:
        round_messages = [umsg, amsg]

    round_index = r2_store.get_next_round_index(window_id)
    ts = now_beijing_iso()
    r2_store.append_conversation_round(window_id, round_index, round_messages, timestamp=ts)
    tail4 = r2_store.get_conversation_rounds(window_id, last_n=4)
    r2_store.update_latest_4_rounds_global(tail4)

    if round_index % SUMMARY_EVERY_N_ROUNDS == 0:
        logger.info("文游实时层总结已调度 window_id=%s round_index=%s", window_id, round_index)
        recent = r2_store.get_conversation_rounds(window_id, last_n=4)
        if recent:
            current = r2_store.get_summary(window_id) or ""

            def _summarize():
                from services.deepseek_summary import fetch_new_summary

                new_summary = fetch_new_summary(current, recent)
                if new_summary:
                    r2_store.save_summary(window_id, new_summary)
                else:
                    logger.warning("文游触发总结但 DeepSeek 未返回 window_id=%s", window_id)

            t = threading.Thread(target=_summarize)
            t.daemon = True
            t.start()


def cmd_go(user_id: int) -> str:
    """结算本轮，调用 GM。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return "文游：当前没有进行中的局，请先 /story 开局。"

    _session_ensure_stats(session)
    pr = session.get("pending_round") or {}
    p1 = pr.get("player1_lines") or []
    p2 = pr.get("player2_lines") or []
    p1_text = "\n".join(p1).strip() or "（玩家一未在群内留下行动描述）"
    p2_text = "\n".join(p2).strip() or "（玩家二渡本轮暂无群内发言）"

    user_blob = f"玩家一（群内）本轮行动：\n{p1_text}\n\n玩家二（渡·群内）：\n{p2_text}\n"

    system, gm_msgs = _build_gm_messages(session)
    # 追加本轮结算 user 消息（作为对 GM 的输入）
    gm_msgs = gm_msgs + [{"role": "user", "content": f"请根据以下本轮行动结算并推进剧情（给出 GM 叙述与选项）：\n{user_blob}"}]

    gm_out = call_wenyou_deepseek(gm_msgs, system=system, temperature=0.75)
    if not gm_out:
        return "文游：GM 调用失败，请稍后重试 /go。"

    parsed = _parse_main_god_panel(gm_out)
    if parsed:
        _merge_panel_into_session_stats(session, parsed)

    ts = now_beijing_iso()
    session.setdefault("history", []).append({"role": "gm", "content": gm_out, "timestamp": ts})
    session["pending_round"] = {"player1_lines": [], "player2_lines": []}
    r2_store.save_wenyou_session(uid, session)

    narrative = _strip_main_god_panel(gm_out)
    foot = _format_status_footer(session)
    display = f"{narrative}\n\n{foot}" if narrative.strip() else foot

    try:
        _append_go_round_to_tg_window(uid, user_blob, display)
    except Exception:
        logger.exception("文游写入 tg 窗口失败 user_id=%s", uid)

    return f"—— 主神系统 ——\n\n{display}"


def cmd_end(user_id: int) -> str:
    """结束并归档。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)
        return "文游：当前没有进行中的局。"

    archive = {
        "gameId": session.get("gameId"),
        "endedAt": now_beijing_iso(),
        "framework": session.get("framework"),
        "stats": session.get("stats"),
        "history": session.get("history"),
    }
    gid = str(session.get("gameId") or "unknown")
    r2_store.save_wenyou_archive_copy(uid, gid, archive)
    r2_store.save_wenyou_last_archive(uid, archive)
    r2_store.delete_wenyou_active_session(uid)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    return "文游：本局已结束并归档。叙事上你们已回到主神空间休整；下一局请再 /story。MiniApp 可查看最近一次归档。"


def get_latest_gm_for_inject(user_id: int) -> str:
    """供私聊 pipeline 注入：取最近一条 GM 正文（不含选项也可）。"""
    session = r2_store.get_wenyou_session(int(user_id))
    if not session:
        return ""
    for h in reversed(session.get("history") or []):
        if (h.get("role") or "").lower() == "gm":
            return _strip_main_god_panel((h.get("content") or "").strip())
    return ""


def is_wenyou_owner(user_id: int) -> bool:
    return bool(TELEGRAM_WENYOU_OWNER_USER_ID and int(user_id) == int(TELEGRAM_WENYOU_OWNER_USER_ID))


def step_inject_wenyou_gm(body: dict, window_id: str) -> dict:
    """
    若存在进行中的文游局，在用户消息前拼接 [文游·GM] 最新剧情，供渡私聊使用。
    """
    if not window_id or not str(window_id).startswith("tg_"):
        return body
    try:
        uid = int(str(window_id).replace("tg_", "", 1))
    except ValueError:
        return body
    gm = get_latest_gm_for_inject(uid)
    if not gm:
        return body

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    prefix = f"[文游·GM]\n{gm}\n\n"
    for i in range(len(messages) - 1, -1, -1):
        if (messages[i].get("role") or "").lower() != "user":
            continue
        c = messages[i].get("content")
        if isinstance(c, str):
            messages[i]["content"] = prefix + c
        elif isinstance(c, list):
            parts = list(c)
            for j, p in enumerate(parts):
                if isinstance(p, dict) and p.get("type") == "text":
                    p = dict(p)
                    p["text"] = prefix + str(p.get("text") or "")
                    parts[j] = p
                    break
            else:
                parts.insert(0, {"type": "text", "text": prefix.rstrip()})
            messages[i]["content"] = parts
        else:
            messages[i]["content"] = prefix + str(c or "")
        break
    body["messages"] = messages
    return body
