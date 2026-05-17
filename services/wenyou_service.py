# 文游：App 内独立副本会话，GM 走 DeepSeek，与主聊天链路隔离（存 R2 wenyou/）
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

import requests

from config import (
    BASE_DIR,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    WENYOU_DS_MODEL,
)
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_TEMPLATES_CACHE: Optional[dict] = None
_TEMPLATES_LOCK = threading.Lock()

# 第二次开局确认（仅内存，进程重启后需再确认）
_PENDING_STORY_CONFIRM: dict[int, bool] = {}
_PENDING_LOCK = threading.Lock()
_STORY_EXPANSION_JOBS: dict[str, dict] = {}
_STORY_EXPANSION_JOBS_LOCK = threading.Lock()
_STORY_EXPANSION_JOB_TTL_SECONDS = 15 * 60
_WENYOU_MEMORY_WINDOW_ID = "wenyou"
_WENYOU_SUMMARY_EVERY_N_ROUNDS = 4
_DEFAULT_PLAYER_COUNT = 2
_DEFAULT_TASKER_TOTAL = 6
_WENYOU_PHASES = frozenset({"hub", "candidate_selection", "instance_running", "settlement", "archived"})
try:
    _WENYOU_TEST_MIN_POINTS = max(0, int(os.environ.get("WENYOU_TEST_MIN_POINTS", "100000") or "0"))
except Exception:
    _WENYOU_TEST_MIN_POINTS = 100000


def _normalize_phase(value: Any, default: str = "instance_running") -> str:
    """Normalize old local phase names to the rules-doc state machine."""
    raw = str(value or "").strip().lower()
    if raw in _WENYOU_PHASES:
        return raw
    if raw in ("instance", "running", "game", "副本", "副本中", "进行中"):
        return "instance_running"
    if raw in ("main_god", "space", "主神", "主神空间", "系统空间"):
        return "hub"
    if raw in ("settle", "结算", "结算中"):
        return "settlement"
    if raw in ("archive", "归档", "已归档"):
        return "archived"
    if raw in ("selection", "candidate", "候选池", "副本选择"):
        return "candidate_selection"
    return default if default in _WENYOU_PHASES else "instance_running"


def _phase_label(phase: Any) -> str:
    return {
        "hub": "主神空间",
        "candidate_selection": "候选池",
        "instance_running": "副本中",
        "settlement": "结算中",
        "archived": "已归档",
    }.get(_normalize_phase(phase), "副本中")


def _session_phase(session: dict) -> str:
    if isinstance(session, dict) and session.get("phase"):
        return _normalize_phase(session.get("phase"))
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    return _normalize_phase(st.get("phase"))


def _shop_open_for_phase(phase: Any) -> bool:
    return _normalize_phase(phase) in {"hub", "settlement"}

# 开局生成框架时注入的 system（无限流 / 副本）
_FRAMEWORK_SYSTEM = """你在为一款「无限流」App 文字跑团生成**单个副本**的设定数据。
整体世界观：存在主神空间；玩家被投入一个又一个副本世界，每个副本有独立规则与任务；你是数据侧，JSON 内用中性表述即可。
**副本类型 instance_genre**（必须选其一，并决定节奏与机关侧重）：**规则怪谈**（条款式规则、告示、广播；**部分规则可为假**、矛盾或诱导，须由玩家自行判断）；**剧情解密**（线索、证言、机关、因果链）；**大逃杀**（缩圈、资源稀缺、淘汰压力）；**对抗**（阵营、互害、结盟与背叛）；**生存撤离**（物资、环境伤害、向撤离点转移）；**潜伏调查**（伪装身份、套取情报、搜查）；**限时任务**（硬性时限或阶段倒计时）。在 `genre_note` 中用一句话写清本局如何体现该类型。
**编制硬性规则**：每个副本的 `tasker_total` 为 **2-13**，当前默认有 2 名玩家角色（玩家一、玩家二「渡」），`npc_taskers` 数量必须等于 `tasker_total - 2`。所有任务者同场竞技或同规则约束；难度 **D～S**（D 最低、S 最高），难度越高环境越险。**任务者都用自己的身体进入副本**，不更换躯体。**NPC 的善恶/立场对玩家应默认不可知**，不要在框架里直接写“好人/坏人/害人”等结论，只能给公开可见信息（外貌、身份、当下公开行为）。
**角色信息规则**：除非用户明确要求“角色扮演副本”或副本规则明确禁止 OOC（越界会惩罚），否则玩家与 NPC 都只给**身份/职业 + 外貌特征**，不要预写性格、价值观、隐秘动机或“一个秘密”；这些应在剧情中让玩家自行判断。默认设定：**玩家一为女性**、**玩家二（渡）为男性**。  
玩家固定外貌：玩家一（辛玥）黑色长发黑眼、中等身高（一米六多）、二十岁出头；玩家二（渡）银色短发、一米八多、薄肌、二十多岁。**禁止预设玩家一/二的性格与穿搭**。
**任务者 NPC 规则**：这些 NPC 是与玩家同批进入副本、完成任务后会回主神空间结算奖励的“任务者”，通常有自己的名字；他们默认**不认同副本内分配身份**，副本身份只是临时伪装或场景壳。
**难度匹配规则**：随机开局时副本难度必须参考玩家当前成长（等级/阶位）。默认两名玩家都是新人（Lv1、D 阶），应优先 D/C；随玩家升级才逐步出现更高难度，不可开局就长期给 A/S。
须给出 **initial_stats**：按默认新人规则，等级 1、阶位 D、经验 0、体力 10、智慧 10、HP/SAN 180/180、主神积分 100、血统「凡人」、能力/武器/状态为空；可给少量初始道具。体力/智慧后续由规则引擎重算上限，开局不要乱改。
opening 建议包含传送/白光/提示音/主神刻板广播之一切入副本场景，但不要冗长。"""


_CANDIDATES_SYSTEM = """你在为一款「无限流」App 文字跑团生成**副本候选设定池**。
这些只是大厅里供玩家挑选的轻量设定，不是完整副本框架；不要写 opening、NPC 名单、玩家属性或完整通关细节。
每条候选要足够能勾起兴趣：有副本名、类型、难度、核心场景、通关方向、危险钩子和一个未展开的悬念。
整体世界观：主神空间会一次投放多个候选，玩家选中某一条后，系统再把它扩展成完整副本。"""


_DU_ACTION_SYSTEM = """你是渡。你正在和辛玥一起玩 App 里的「文游 / 无限流跑团」。
这是游戏内虚构副本，不是真实现实经历；你只能决定“渡”这个玩家角色本轮怎么行动。

边界：
- 不替辛玥行动，不替 GM 结算，不推进世界反馈。
- 不写长篇聊天回复，不写解释，不写系统提示。
- 行动要像渡本人：照应辛玥、会观察风险、必要时主动分担，但不要抢走她的选择权。
- 只输出严格 JSON：{"action":"渡本轮行动，30-120字"}。"""


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

## 副本蓝图（GM/后端内部资料，不要整段剧透给玩家）
{blueprint_block}

## 主神空间 · 积分 · 系统商店 · 成长 · 生死与回程（叙事规则）
- **主神积分**：用于复活、治疗、**系统商店**购物与强化；精确数值最终以后端规则引擎为准。当前兼容面板只同步系统记录，除非本轮叙事明确触发消耗、伤害、奖励或结算，不要随意改精确数值。
- **系统商店**只在 `hub` 或 `settlement` 阶段开放。副本进行中不能购买系统商店物品，只能使用背包已有物品，或通过剧情获得临时物品。
- **结构化能力**：每名玩家有 **abilities**（技能/被动/血统技等），须在【主神面板】用固定格式列出（名称｜简述）；获得、升级、封印或失去能力时**整行替换**为当前完整列表，与剧情一致，便于程序解析、避免状态漂移。
- **玩家等级与阶位**：每名玩家有 **等级（Lv）**，等级越高综合越强（伤害豁免、判定加值等由叙事体现）；另有 **阶位 D～S**（D 最低、S 最高），可与血统强化、主神评价挂钩。副本结算可发经验、升级或阶位提升契机，**必须**在【主神面板】中更新。
- **死亡与复活**：若玩家角色死亡或判定出局，须给出主神选项感：可用**积分复活**（扣多少在面板中写明，可与难度挂钩），或消耗**指定道具**复活/续命；不得无故满血无代价复活。
- **副本结束**：当副本以通关、失败或强制结算等方式**结束**时，须描写**白光/传送**回到**主神空间**（场地切到主神空间）；之后可逛**系统商店**、治疗、整备再接下一副本。
- **主神空间内**：它是纯功能区，以休整、商店、治疗、兑换、抽卡、强化、接下一副本为主；不要发展长期 hub 剧情或 NPC 日常线。

## 当前系统记录的状态（你必须在回复末尾用【主神面板】更新，与剧情一致）
{current_stats_block}

## 无限流玩法（叙事层）
- 每个故事都是**一次副本**；关键节点可有一两句 **【主神提示】**，平时克制。
- **任务者编制**：本局 `tasker_total` 和 NPC 名单以副本框架为准，不固定 6 人。NPC 须在剧中可追溯（可退场或死亡，须有因果），不得无交代消失。
- 可埋伏线：规则类陷阱、NPC 互害、时间压力等。
- **副本结算**须符合因果；bad end 亦同。

## 你的职责
- 描述环境、NPC、主神播报、事件结果；根据两位玩家行动推进；收到结算信号后做**本轮**推进。
- 你只输出本轮事件意图，不直接裁定精确 HP/SAN/积分/等级变化；后端 Rules Engine 会根据风险、难度、属性和阶位计算 `state_patch`。

## 【事件意图】固定格式（每轮必须先输出，随后再写叙事）
【事件意图】
{{"event":"short_event_id","risk":"safe/minor/risky/dangerous/desperate/lethal","targets":["player1"],"tags":["physical/mental/rule_pollution/mixed/clue/npc_relation/time/resource"],"action_state":"prepared/normal/reckless/forced","fiction":"一句说明触发了什么","conditions_add":[],"conditions_remove":[],"clock_updates":[{{"id":"clock_id","name":"威胁名","delta":1,"max":6}}]}}

规则：
- `risk` 只表达风险等级，不写精确扣血/扣精神数字。
- `targets` 只允许 `player1`、`player2` 或 `all`；不确定时优先写实际承受后果的人。
- `tags` 必须至少写一个。纯身体伤害写 `physical`，精神/污染写 `mental` 或 `rule_pollution`，两者都有写 `mixed`。
- 没有伤害也要输出 `safe`，可用 `clue`、`npc_relation`、`time`、`resource` 表示剧情推进方向。
- 【事件意图】是给后端看的，不要在叙事里解释 JSON。

## 回复规范
- 先输出【事件意图】JSON，再写叙事。叙事约 150-300 字，有画面感；在【主神面板】**之前**，按**副本类型**附上对应**备忘**（见上「本类型玩法要点」）；其中 **规则怪谈** 类**每轮不可省略**【规则备忘】。
- 叙事之后列出 2-3 个行动选项，最后一个固定为「C. 自由行动」。
- **最后**必须附 **【主神面板】**（见下，不可省略）；备忘块始终在【主神面板】**上方**，便于玩家对照。

## 【主神面板】固定格式（每次回复末尾必须原样包含，一行一项，便于系统解析）
【主神面板】
场地：副本 或 主神空间
积分：整数
玩家一 HP 当前/最大 精神 当前/最大
玩家一等级：正整数
玩家一经验：非负整数
玩家一阶位：D、C、B、A、S 之一
玩家一体力：正整数（关联生命上限为主）
玩家一智慧：正整数（关联精神上限为主）
玩家一血统：简短名称（含强化说明亦可）
玩家一能力：无 或 名称｜一句效果；名称｜一句效果（多条用中文分号「；」分隔，**整行一行**，勿换行）
玩家二 HP 当前/最大 精神 当前/最大
玩家二等级：正整数
玩家二经验：非负整数
玩家二阶位：D、C、B、A、S 之一
玩家二体力：正整数
玩家二智慧：正整数
玩家二血统：简短名称
玩家二能力：无 或 名称｜一句效果；名称｜一句效果（格式同玩家一）
道具：无 或 道具名用顿号分隔

说明：场地为「主神空间」时表示已回到主神空间；购物、强化血统、加体力/智慧、治疗、升级与阶位变化、**能力增删改**，均须体现在面板与积分中；能力行必须与当前剧情一致（整行即完整能力列表）。普通副本行动里的 HP/SAN 精确变化由后端 Rules Engine 按【事件意图】计算，面板可保持系统记录，不要自行编扣减数字。

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
    span = _first_json_object_span(t)
    if not span:
        return None
    raw = t[span[0] : span[1]]
    for attempt in (raw, raw.replace("\n", " ")):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _first_json_object_span(text: str, start_index: int = 0) -> Optional[tuple[int, int]]:
    """Return the first balanced JSON-object span in text, tolerant of nested objects."""
    if not text:
        return None
    start = text.find("{", max(0, start_index))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    return None


def call_wenyou_deepseek(
    messages: list[dict],
    system: str,
    temperature: float = 0.7,
    timeout_seconds: int = 120,
) -> Optional[str]:
    """调用 DeepSeek Chat Completions（非流式）。"""
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，无法调用文游 GM")
        return None
    url = (DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    body = {
        "model": WENYOU_DS_MODEL,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": False,
        "temperature": temperature,
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=max(10, int(timeout_seconds or 120)),
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
  "tasker_total": "2-13 的整数；当前默认 2 名玩家角色，npc_taskers 数量必须等于 tasker_total - 2",
  "world": "本副本**内部**世界观与场景 2-4 句（不写主神空间全貌，聚焦本图）",
  "player1_name": "辛玥（玩家一本名，默认女性）",
  "player1_instance_name": "可选：副本内身份名；仅角色扮演副本或用户明确要求时填写",
  "player1_role": "身份或职业 + 外貌特征（简短；默认不写性格与秘密）",
  "player2_name": "渡（默认男性）",
  "player2_instance_name": "可选：副本内身份名；仅角色扮演副本或用户明确要求时填写",
  "player2_role": "渡在本副本中的身份 + 外貌特征（简短；默认不写性格与秘密）",
  "npc_taskers": [
    {{"name": "任务者 NPC 本名", "instance_name": "可选：副本内身份名（角色扮演副本才建议填）", "tier_note": "内部难度定位字段（仅供系统，不可在叙事里直给玩家）", "stance": "未知（玩家不可知；勿直给善恶）", "blurb": "一句话外貌或公开可见特征；可写其不认同副本身份"}}
  ],
  "conflict": "主神发布的核心任务 / 通关条件 1-3 句，可略带残酷或幽默感",
  "failure_hint": "失败、抹杀或惩罚方向的**一句**提示（虚构，勿过度血腥）",
  "reward_hint": "通关后可能获得的奖励风味一句（如积分、线索、豁免；可不写具体数字）",
  "public": {{"instance_name": "公开副本名", "genre": ["类型"], "difficulty": "D/C/B/A/S", "visible_rules": [], "public_task": "玩家公开可见任务"}},
  "gm_secret": {{"true_rules": [], "false_rules": [], "npc_goals": {{}}, "hidden_endings": []}},
  "instance_blueprint": {{
    "blueprint_version": 1,
    "logline": "一句话核心矛盾",
    "mainline": [{{"phase": "开场", "goal": "确认任务与第一处异常", "required_clues": [], "fail_forward": "错过线索时以更高代价推进"}}],
    "side_quests": [],
    "hidden_endings": [],
    "clue_graph": [],
    "npc_arcs": {{}},
    "threat_clocks": [],
    "hard_constraints": ["每条主线关键线索至少保留替代获得方式", "NPC 可误导但不能无因果直接致死玩家"]
  }},
    "initial_stats": {{
    "points": 100,
    "player1": {{"hp": 180, "hp_max": 180, "san": 180, "san_max": 180, "level": 1, "rank": "D", "exp": 0, "vit": 10, "wis": 10, "bloodline": "凡人", "abilities": [], "weapons": [], "conditions": []}},
    "player2": {{"hp": 180, "hp_max": 180, "san": 180, "san_max": 180, "level": 1, "rank": "D", "exp": 0, "vit": 10, "wis": 10, "bloodline": "凡人", "abilities": [], "weapons": [], "conditions": []}},
    "items": ["可选：与副本相关的消耗品或线索道具，无则 []"]
  }},
  "opening": "开场 4-8 句：建议含传送/白光/提示音/主神刻板广播之一；若本局存在 NPC，必须出现同场任务者的登场感或存在感，再进入场景，有画面感"
}}

**编制硬性规则**：`tasker_total` 必须为 2-13；当前默认 2 名玩家角色，因此 `npc_taskers` 数量必须等于 `tasker_total - 2`。NPC 的善恶与立场对玩家默认不可知，勿在框架里直给结论；“新人/炮灰/大佬”等仅作为系统内部定位，不可直接告诉玩家。**instance_genre** 须与 `world`、`conflict` 一致；必须先写 `instance_blueprint`，再写 opening；**initial_stats** 须含主神积分、双方 HP/精神、**等级与阶位（D～S）、经验、体力与智慧、血统名称**、**双方 abilities 数组（元素为 name/desc，可无项）**、weapons、conditions 与背包（可为空数组）。

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
  "tasker_total": "2-13 的整数；当前默认 2 名玩家角色，npc_taskers 数量必须等于 tasker_total - 2",
  "world": "本副本内部世界观与场景 2-4 句",
  "player1_name": "辛玥（玩家一本名，默认女性）",
  "player1_instance_name": "可选：副本内身份名；仅角色扮演副本或用户明确要求时填写",
  "player1_role": "身份或职业（外貌固定：黑色长发黑眼、中等身高一米六多、二十岁出头；默认不写性格与穿搭）",
  "player2_name": "渡（默认男性）",
  "player2_instance_name": "可选：副本内身份名；仅角色扮演副本或用户明确要求时填写",
  "player2_role": "渡在本副本中的身份（外貌固定：银色短发、一米八多、薄肌、二十多岁；默认不写性格与穿搭）",
  "npc_taskers": [
    {{"name": "任务者本名", "instance_name": "可选：副本内身份名（角色扮演副本才建议填）", "tier_note": "内部定位，不对玩家直给", "stance": "未知", "blurb": "外貌或公开可见特征；可写其不认同副本身份"}}
  ],
  "conflict": "主神核心任务 / 通关条件 1-3 句",
  "failure_hint": "失败或惩罚方向一句（虚构，勿过度血腥）",
  "reward_hint": "通关奖励风味一句（可不写具体数字）",
  "public": {{"instance_name": "公开副本名", "genre": ["类型"], "difficulty": "D/C/B/A/S", "visible_rules": [], "public_task": "玩家公开可见任务"}},
  "gm_secret": {{"true_rules": [], "false_rules": [], "npc_goals": {{}}, "hidden_endings": []}},
  "instance_blueprint": {{
    "blueprint_version": 1,
    "logline": "一句话核心矛盾",
    "mainline": [{{"phase": "开场", "goal": "确认任务与第一处异常", "required_clues": [], "fail_forward": "错过线索时以更高代价推进"}}],
    "side_quests": [],
    "hidden_endings": [],
    "clue_graph": [],
    "npc_arcs": {{}},
    "threat_clocks": [],
    "hard_constraints": ["每条主线关键线索至少保留替代获得方式", "NPC 可误导但不能无因果直接致死玩家"]
  }},
  "initial_stats": {{
    "points": 100,
  "player1": {{"hp": 180, "hp_max": 180, "san": 180, "san_max": 180, "level": 1, "rank": "D", "exp": 0, "vit": 10, "wis": 10, "bloodline": "凡人", "abilities": [], "weapons": [], "conditions": []}},
  "player2": {{"hp": 180, "hp_max": 180, "san": 180, "san_max": 180, "level": 1, "rank": "D", "exp": 0, "vit": 10, "wis": 10, "bloodline": "凡人", "abilities": [], "weapons": [], "conditions": []}},
    "items": []
  }},
  "opening": "开场 4-8 句，建议含主神传送或播报感；若本局存在 NPC，须体现同场任务者"
}}

**编制**：`tasker_total` 必须为 2-13；当前默认 2 名玩家角色，`npc_taskers` 数量必须等于 `tasker_total - 2`。任务者使用自身身体进入副本；NPC 的立场与善恶对玩家默认不可知，且“新人/炮灰/大佬”等定位不可在叙事中直给。须带 **instance_genre**、**genre_note**、`public`、`gm_secret`、`instance_blueprint` 与 **initial_stats**（含等级、阶位 D～S、经验、体力、智慧、血统、**abilities**、weapons、conditions）。

关键词：{keywords}

只输出 JSON，不要解释。"""


def _candidates_prompt(count: int, difficulty_hint: str, keywords: str = "") -> str:
    topic_line = f"\n玩家偏好 / 关键词：{keywords.strip()}" if keywords.strip() else ""
    return f"""一次生成 {count} 条**副本候选设定**，输出严格 JSON（不要 markdown 代码块）：
{{
  "items": [
    {{
      "title": "副本名，2-12 字",
      "instance_genre": "必须是以下之一：规则怪谈、剧情解密、大逃杀、对抗、生存撤离、潜伏调查、限时任务",
      "difficulty": "D、C、B、A、S 之一；新人优先 D/C，可少量 B",
      "tagline": "一句大厅展示文案，短、有钩子",
      "premise": "2-3 句轻量设定，只写场景和异常，不展开完整真相",
      "core_task": "主神可能发布的通关方向，一句话",
      "survival_hook": "玩家进入后第一时间要在意的生存问题，一句话",
      "risk": "失败/污染/追杀/倒计时等危险方向，一句话",
      "twist": "一个未揭开的悬念，不要直接揭底",
      "tags": ["2-5 个短标签"],
      "estimated_length": "短篇、标准、长篇 之一"
    }}
  ]
}}

要求：
- 候选之间题材、玩法、节奏要明显不同；不要都是校园/古宅。
- 只写候选设定，不生成完整副本，不写开场正文，不写 NPC 名单。
- 难度参考：{difficulty_hint or "D/C"}。{topic_line}
- 所有内容适合后续扩展为 `tasker_total 2-13` 的无限流副本。

只输出 JSON，不要解释。"""


# 副本难度 D～S（D 最低，S 最高）
_WENYOU_DIFFICULTIES = frozenset({"D", "C", "B", "A", "S"})
_WENYOU_RISK_DAMAGE: dict[str, tuple[int, int]] = {
    "safe": (0, 0),
    "minor": (5, 4),
    "risky": (12, 10),
    "dangerous": (25, 22),
    "desperate": (45, 40),
    "lethal": (80, 70),
}
_WENYOU_DIFFICULTY_MULTIPLIER = {"D": 0.75, "C": 1.0, "B": 1.35, "A": 1.75, "S": 2.25}
_WENYOU_RANK_PHYSICAL_REDUCTION = {"D": 0, "C": 2, "B": 5, "A": 9, "S": 15}
_WENYOU_RANK_MENTAL_REDUCTION = {"D": 0, "C": 2, "B": 5, "A": 9, "S": 15}
_WENYOU_RANK_HP_BONUS = {"D": 0, "C": 20, "B": 45, "A": 80, "S": 130}
_WENYOU_RANK_SAN_BONUS = {"D": 0, "C": 20, "B": 45, "A": 80, "S": 130}
_WENYOU_RANK_SPI_BONUS = {"D": 0, "C": 2, "B": 5, "A": 9, "S": 15}
_WENYOU_RANK_ATTRIBUTE_SOFT_CAP = {"D": 14, "C": 20, "B": 28, "A": 38, "S": 50}
_WENYOU_ATTRIBUTE_KEYS = ("str", "con", "agi", "int", "spi", "luk")
_WENYOU_RANK_ORDER = ("D", "C", "B", "A", "S")
_WENYOU_PROMOTION_RULES = {
    "C": {"from": "D", "level": 3, "cost": 200, "clear": "C", "perfect": "D"},
    "B": {"from": "C", "level": 6, "cost": 500, "clear": "B", "perfect": "C"},
    "A": {"from": "B", "level": 10, "cost": 1000, "clear": "A", "perfect": "B"},
    "S": {"from": "A", "level": 15, "cost": 2000, "clear": "S", "perfect": "A", "special_trial": True},
}
_WENYOU_REVIVE_BASE_COST = {"D": 200, "C": 500, "B": 1200, "A": 2600, "S": 6000}
_WENYOU_ACTION_MODIFIER = {
    "prepared": 0.70,
    "normal": 1.00,
    "reckless": 1.30,
    "forced": 1.60,
}
_WENYOU_CLEAR_BASE_REWARD = {
    "D": {"points": 100, "exp": 30, "rolls": 1},
    "C": {"points": 220, "exp": 60, "rolls": 1},
    "B": {"points": 450, "exp": 120, "rolls": 2},
    "A": {"points": 900, "exp": 220, "rolls": 2},
    "S": {"points": 1800, "exp": 420, "rolls": 3},
}
_WENYOU_RESULT_FACTORS = {
    "standard_clear": {"points": 1.0, "exp": 1.0, "label": "标准通关"},
    "low_escape": {"points": 0.5, "exp": 0.5, "label": "低完成逃生"},
    "failed_escape": {"points": 0.0, "exp": 0.2, "label": "失败撤离"},
    "death_failed": {"points": 0.0, "exp": 0.0, "label": "死亡失败"},
    "abandoned": {"points": 0.0, "exp": 0.0, "label": "放弃副本"},
}
_WENYOU_RATING_BONUS = {
    "S": {"points": 0.70, "exp": 0.70},
    "A": {"points": 0.45, "exp": 0.45},
    "B": {"points": 0.20, "exp": 0.20},
    "C": {"points": 0.0, "exp": 0.0},
    "D": {"points": -0.20, "exp": -0.20},
    "F": {"points": 0.0, "exp": 0.0},
}
_WENYOU_REWARD_RARITY_RATES: dict[str, list[tuple[str, float]]] = {
    "D": [("D", 70.0), ("C", 25.0), ("B", 5.0)],
    "C": [("D", 20.0), ("C", 60.0), ("B", 18.0), ("A", 2.0)],
    "B": [("C", 25.0), ("B", 55.0), ("A", 18.0), ("S", 2.0)],
    "A": [("B", 35.0), ("A", 55.0), ("S", 10.0)],
    "S": [("A", 45.0), ("S", 55.0)],
}
_WENYOU_REWARD_CATEGORY_RATES: dict[str, list[tuple[str, float]]] = {
    "D": [("consumable_item", 45.0), ("material", 25.0), ("gear", 15.0), ("ability_fragment", 10.0), ("evolution_fragment", 5.0)],
    "C": [("consumable_item", 30.0), ("material", 25.0), ("gear", 20.0), ("ability_fragment", 15.0), ("evolution_fragment", 8.0), ("special", 2.0)],
    "B": [("consumable_item", 18.0), ("material", 24.0), ("gear", 24.0), ("ability_fragment", 18.0), ("evolution_fragment", 12.0), ("special", 4.0)],
    "A": [("consumable_item", 10.0), ("material", 22.0), ("gear", 25.0), ("ability_fragment", 20.0), ("evolution_fragment", 15.0), ("special", 8.0)],
    "S": [("consumable_item", 5.0), ("material", 15.0), ("gear", 30.0), ("ability_fragment", 20.0), ("evolution_fragment", 18.0), ("special", 12.0)],
}
_WENYOU_REWARD_CATEGORY_LABELS = {
    "consumable_item": "消耗道具",
    "material": "锻造材料",
    "gear": "武器/装备",
    "ability_fragment": "能力碎片",
    "evolution_fragment": "进化碎片",
    "special": "特殊物/称号",
}
_WENYOU_REWARD_FRAGMENT_AMOUNTS = {
    "ability_fragment": {"D": 10, "C": 25, "B": 60, "A": 160, "S": 500},
    "evolution_fragment": {"D": 8, "C": 20, "B": 50, "A": 140, "S": 450},
}
_WENYOU_RATING_LABELS = {
    "S": "S 完美",
    "A": "A 优秀",
    "B": "B 标准",
    "C": "C 勉强",
    "D": "D 低完成",
    "F": "F 失败",
}
_WENYOU_RATING_OPTIONS = [
    {"id": "S", "label": "S 完美", "desc": "95+ 分，高探索、低损耗或隐藏结局。"},
    {"id": "A", "label": "A 优秀", "desc": "80-94 分，主线清楚且有额外收益。"},
    {"id": "B", "label": "B 标准", "desc": "60-79 分，完成核心目标。"},
    {"id": "C", "label": "C 勉强", "desc": "40-59 分，活着完成但缺口较多。"},
    {"id": "D", "label": "D 低完成", "desc": "20-39 分，只保留很少成果。"},
    {"id": "F", "label": "F 失败", "desc": "0-19 分，不发积分奖励。"},
]
_WENYOU_RESULT_OPTIONS = [
    {"id": "standard_clear", "label": "标准通关", "desc": "达成主线最低条件，按基础保底结算。"},
    {"id": "low_escape", "label": "低完成逃生", "desc": "活着离开，但只带回最低记录或情报。"},
    {"id": "failed_escape", "label": "失败撤离", "desc": "强制撤离或只保住性命，不发积分。"},
    {"id": "death_failed", "label": "死亡失败", "desc": "死亡或彻底失败，后续接复活/债务。"},
    {"id": "abandoned", "label": "放弃副本", "desc": "主动放弃，触发放弃惩罚。"},
]
_WENYOU_EVENT_TAGS = frozenset(
    {
        "physical",
        "mental",
        "rule_pollution",
        "memory",
        "mixed",
        "clue",
        "npc_relation",
        "time",
        "resource",
    }
)

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
        "initiative": 7,
        "carry_limit": 15,
        "evolution": "凡人",
        "bloodline": "凡人",
        "abilities": [],
        "ability_tokens": 0,
        "unspent_attribute_points": 0,
        "gear": [],
        "weapons": [],
        "conditions": [],
        "death_count": 0,
        "pollution": 0,
    }


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))


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
    p["ability_tokens"] = _to_non_negative_int(p.get("ability_tokens"), 0)
    p["unspent_attribute_points"] = _to_non_negative_int(p.get("unspent_attribute_points"), 0)
    evo = str(p.get("evolution") or p.get("bloodline") or "凡人").strip()[:48] or "凡人"
    p["evolution"] = evo
    p["bloodline"] = evo
    p["death_count"] = _to_non_negative_int(p.get("death_count"), 0)
    p["pollution"] = _to_non_negative_int(p.get("pollution"), 0)
    p["gear"] = p.get("gear") if isinstance(p.get("gear"), list) else []
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
        "hidden_endings": _normalize_blueprint_list(secret.get("hidden_endings"), 10),
    }
    return clean_public, clean_secret


def _format_abilities_for_prompt(p: dict) -> str:
    """写入 GM 占位：与面板要求一致的单行格式。"""
    ab = p.get("abilities") if isinstance(p, dict) else None
    ab = _normalize_abilities_list(ab)
    if not ab:
        return "无"
    return "；".join(f"{a['name']}｜{a['desc']}" for a in ab)


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
        "ability_tokens",
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
    if "bloodline" in new:
        bl = str(new["bloodline"]).strip()[:48]
        if bl:
            out["bloodline"] = bl
            out["evolution"] = bl
    if "evolution" in new:
        evo = str(new["evolution"]).strip()[:48]
        if evo:
            out["evolution"] = evo
            out["bloodline"] = evo
    if "abilities" in new and isinstance(new["abilities"], list):
        out["abilities"] = _normalize_abilities_list(new["abilities"])
    if "gear" in new and isinstance(new["gear"], list):
        out["gear"] = new["gear"][:12]
    if "weapons" in new and isinstance(new["weapons"], list):
        out["weapons"] = _normalize_text_list(new["weapons"])
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


def _format_tasker_regiment_for_gm(fw: dict) -> str:
    """写入 GM system：难度 + tasker_total 2-13 编制说明 + NPC 档案。"""
    def _show_name(real_name: str, instance_name: str) -> str:
        rn = str(real_name or "").strip()
        inn = str(instance_name or "").strip()
        if inn and inn != rn:
            return f"{rn}（{inn}）"
        return rn

    diff = _normalize_difficulty(fw.get("difficulty"))
    p1n = _show_name(fw.get("player1_name") or "辛玥", fw.get("player1_instance_name") or "")
    p2n = _show_name(fw.get("player2_name") or "渡", fw.get("player2_instance_name") or "")
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
    for i, n in enumerate(fw.get("npc_taskers") or []):
        if isinstance(n, dict):
            nshow = _show_name(n.get("name", ""), n.get("instance_name", ""))
            lines.append(
                f"  · {i+1}. 「{nshow}」｜{n.get('tier_note', '')}｜公开信息：{n.get('blurb', '')}（立场：{n.get('stance', '未知')}）"
            )
    return "\n".join(lines)


def _format_blueprint_for_gm(fw: dict) -> str:
    bp = _normalize_instance_blueprint(fw.get("instance_blueprint"), fw)
    secret = fw.get("gm_secret") if isinstance(fw.get("gm_secret"), dict) else {}
    payload = {
        "instance_blueprint": bp,
        "gm_secret_summary": {
            "true_rules": secret.get("true_rules") or [],
            "false_rules": secret.get("false_rules") or [],
            "npc_goals": secret.get("npc_goals") or {},
            "hidden_endings": secret.get("hidden_endings") or [],
        },
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
        "player1_name": str(raw.get("player1_name") or "辛玥").strip(),
        "player1_instance_name": str(raw.get("player1_instance_name") or "").strip(),
        "player1_role": str(raw.get("player1_role") or "").strip(),
        "player2_name": str(raw.get("player2_name") or "渡").strip(),
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
        "initial_stats": _normalize_initial_stats(raw),
    }
    public, gm_secret = _normalize_public_secret(raw, out)
    out["public"] = public
    out["gm_secret"] = gm_secret
    out["instance_blueprint"] = _normalize_instance_blueprint(raw.get("instance_blueprint"), out)
    return out


def _normalize_initial_stats(raw: dict) -> dict:
    """开局 JSON 中的 initial_stats：积分、双玩家血/精神/等级阶位/六属性/进化、道具列表。"""
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
                "ability_tokens": max(0, int(d.get("ability_tokens") or 0)),
                "unspent_attribute_points": max(0, int(d.get("unspent_attribute_points") or 0)),
                "death_count": max(0, int(d.get("death_count") or 0)),
                "pollution": max(0, int(d.get("pollution") or 0)),
            }
        )
        bl = str(d.get("evolution") or d.get("bloodline") or "凡人").strip()[:48] or "凡人"
        player["evolution"] = bl
        player["bloodline"] = bl
        ab = _normalize_abilities_list(d.get("abilities"))
        player["abilities"] = ab
        player["gear"] = d.get("gear") if isinstance(d.get("gear"), list) else []
        player["weapons"] = _normalize_text_list(d.get("weapons"))
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
    return {
        "phase": "instance_running",
        "points": init["points"],
        "player1": dict(init["player1"]),
        "player2": dict(init["player2"]),
        "inventory": _normalize_inventory(init.get("items"), source="initial"),
    }


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
                session["stats"][k] = dict(base)
            else:
                for bk, bv in base.items():
                    cur.setdefault(bk, bv)
                _normalize_player_growth_fields(cur)
                # 旧存档或脏数据：统一成结构化能力列表
                cur["abilities"] = _normalize_abilities_list(cur.get("abilities"))
                cur["weapons"] = _normalize_text_list(cur.get("weapons"))
                cur["conditions"] = _normalize_text_list(cur.get("conditions"))
                _recalc_player_caps(cur)
        return
    fw = session.get("framework") or {}
    session["stats"] = _stats_runtime_from_framework(_framework_for_runtime(fw))


def _format_stats_for_gm_prompt(session: dict) -> str:
    """供 GM system 占位：当前积分、场地、血精神、成长与血统、道具。"""
    _session_ensure_stats(session)
    st = session["stats"]
    phase = _normalize_phase(st.get("phase"))
    loc = "主神空间" if phase in {"hub", "settlement"} else "副本"
    p1 = st.get("player1") or {}
    p2 = st.get("player2") or {}
    inv = _normalize_inventory(st.get("inventory"), source="session")
    inv_s = "、".join(_inventory_label_list(inv)) if inv else "无"

    def _line_player(label: str, p: dict) -> str:
        return (
            f"- {label}：HP {p.get('hp', 0)}/{p.get('hp_max', 1)}，SAN {p.get('san', 0)}/{p.get('san_max', 1)}，当前精神力 {p.get('spi_current', 0)}/{p.get('spi_max', 0)}；"
            f"Lv{p.get('level', 1)} EXP {p.get('exp', 0)} 阶位{p.get('rank', 'D')}；"
            f"力{p.get('str', 0)} 体{p.get('con', p.get('vit', 0))} 敏{p.get('agi', 0)} 智{p.get('int', p.get('wis', 0))} 精{p.get('spi', 0)} 运{p.get('luk', 0)}；进化：{p.get('evolution') or p.get('bloodline', '凡人')}\n"
            f"- {label}能力（须在面板原样同步）：{_format_abilities_for_prompt(p)}"
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

    def _foot_abilities(p: dict) -> str:
        ab = _normalize_abilities_list(p.get("abilities"))
        if not ab:
            return "能力无"
        shown = [a.get("name", "") for a in ab[:3] if isinstance(a, dict) and a.get("name")]
        tail = f"等{len(ab)}项" if len(ab) > 3 else ""
        return (" ".join(shown) + (f" {tail}" if tail else "")).strip() or "能力无"

    def _foot_player(p: dict) -> str:
        return (
            f"血{p.get('hp', 0)}/{p.get('hp_max', 1)} SAN{p.get('san', 0)}/{p.get('san_max', 1)} 精神力{p.get('spi_current', 0)}/{p.get('spi_max', 0)}｜"
            f"Lv{p.get('level', 1)}·{p.get('rank', 'D')}阶 EXP{p.get('exp', 0)}｜"
            f"力{p.get('str', 0)} 体{p.get('con', p.get('vit', 0))} 敏{p.get('agi', 0)} 智{p.get('int', p.get('wis', 0))} 精{p.get('spi', 0)} 运{p.get('luk', 0)}｜"
            f"{p.get('evolution') or p.get('bloodline', '凡人')}｜{_foot_abilities(p)}"
        )

    return (
        "━━━━━━━━━━━━\n"
        f"【状态】{loc}｜主神积分：{int(st.get('points') or 0)}\n"
        f"玩家一 {_foot_player(p1)}\n"
        f"玩家二 {_foot_player(p2)}\n"
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
    m = re.search(rf"{label}血统[：:]\s*(.+?)(?:\n|$)", block)
    if m:
        out["bloodline"] = m.group(1).strip()
    m = re.search(rf"{label}能力[：:]\s*(.+?)(?:\n|$)", block)
    if m:
        out["abilities"] = _parse_abilities_line(m.group(1))
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
        elif s in ("player1", "p1", "玩家一", "辛玥"):
            targets.append("player1")
        elif s in ("player2", "p2", "渡", "玩家二"):
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
    }


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
    label = {"player1": "玩家一", "player2": "渡"}
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
            lines.append(f"威胁时钟 {clk.get('id')}：{clk.get('value')}/{clk.get('max')}")
    if not lines:
        return ""
    return "【规则结算】\n" + "\n".join(lines[:6])


def _normalize_wallet(raw: Any, seed_points: int = 100) -> dict:
    data = raw if isinstance(raw, dict) else {}
    ledger = data.get("ledger") if isinstance(data.get("ledger"), list) else []
    clear_records = data.get("clear_records") if isinstance(data.get("clear_records"), list) else []
    promotion_history = data.get("promotion_history") if isinstance(data.get("promotion_history"), list) else []
    points = max(0, int(data.get("points") if data.get("points") is not None else seed_points))
    test_grant_min = max(0, int(data.get("test_points_grant_min") or 0))
    if _WENYOU_TEST_MIN_POINTS and points < _WENYOU_TEST_MIN_POINTS and test_grant_min < _WENYOU_TEST_MIN_POINTS:
        points = _WENYOU_TEST_MIN_POINTS
        test_grant_min = _WENYOU_TEST_MIN_POINTS
        ledger = ledger[-79:] + [{"at": now_beijing_iso(), "type": "test_points_grant", "points": points}]
    return {
        "version": 1,
        "points": points,
        "debts": max(0, int(data.get("debts") or 0)),
        "total_exp": max(0, int(data.get("total_exp") or 0)),
        "settlement_count": max(0, int(data.get("settlement_count") or 0)),
        "gacha": _normalize_gacha_state(data.get("gacha")),
        "inventory": _normalize_inventory(data.get("inventory"), source="wallet"),
        "clear_records": [x for x in clear_records[-30:] if isinstance(x, dict)],
        "promotion_history": [x for x in promotion_history[-20:] if isinstance(x, dict)],
        "test_points_grant_min": test_grant_min,
        "ledger": ledger[-80:],
        "updated_at": str(data.get("updated_at") or now_beijing_iso()),
    }


def _load_wenyou_wallet(user_id: int, session: Optional[dict] = None) -> dict:
    seed_points = 100
    if isinstance(session, dict):
        st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
        if st.get("points") is not None:
            seed_points = max(0, int(st.get("points") or 0))
    return _normalize_wallet(r2_store.get_wenyou_wallet(int(user_id)), seed_points=seed_points)


def _save_wenyou_wallet(user_id: int, wallet: dict) -> None:
    wallet["updated_at"] = now_beijing_iso()
    r2_store.save_wenyou_wallet(int(user_id), _normalize_wallet(wallet, seed_points=int(wallet.get("points") or 0)))


def _sync_session_points_with_wallet(session: dict, wallet: dict) -> None:
    _session_ensure_stats(session)
    session["stats"]["points"] = max(0, int(wallet.get("points") or 0))
    session["wallet"] = {
        "points": max(0, int(wallet.get("points") or 0)),
        "debts": max(0, int(wallet.get("debts") or 0)),
        "total_exp": max(0, int(wallet.get("total_exp") or 0)),
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
    player["initiative"] = math.floor(agi / 2) + math.floor(luk / 4)
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
    ability_tokens = int(player.get("ability_tokens") or 0)
    unspent = int(player.get("unspent_attribute_points") or 0)
    player["exp"] = max(0, int(player.get("exp") or 0)) + max(0, int(exp_gain or 0))
    player["level"] = max(1, int(player.get("level") or 1))
    while player["exp"] >= player["level"] * 100:
        player["exp"] -= player["level"] * 100
        player["level"] += 1
        gained_levels += 1
        unspent += 3
        if player["level"] % 3 == 0:
            ability_tokens += 1
    player["ability_tokens"] = ability_tokens
    player["unspent_attribute_points"] = unspent
    _recalc_player_caps(player)
    return {"level_delta": gained_levels, "ability_tokens": ability_tokens, "unspent_attribute_points": unspent}


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

    recent = _recent_gm_text(session)
    if re.search(r"(团灭|彻底失败|死亡失败|任务失败|副本失败)", recent):
        return "death_failed", "medium", "最近 GM 叙述出现失败/死亡信号。"
    if re.search(r"(失败撤离|强制撤离|撤离失败|只保住性命)", recent):
        return "failed_escape", "medium", "最近 GM 叙述出现失败撤离信号。"
    if re.search(r"(低完成逃生|逃出生天|成功撤离|脱出|逃离副本|生还)", recent):
        return "low_escape", "medium", "最近 GM 叙述出现撤离/生还信号。"
    if re.search(r"(通关|达成主线|主线完成|任务完成|副本结束|回归主神空间|进入结算)", recent):
        return "standard_clear", "medium", "最近 GM 叙述出现通关/结算信号。"

    clocks = session.get("clocks") if isinstance(session.get("clocks"), list) else []
    if any(isinstance(c, dict) and int(c.get("value") or 0) >= int(c.get("max") or 9999) for c in clocks):
        return "failed_escape", "medium", "威胁时钟已触顶。"

    return "standard_clear", "low", "未检测到明确失败信号，按可确认的通关结算预估。"


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
    history_rounds = sum(1 for item in (session.get("history") or []) if isinstance(item, dict) and item.get("role") == "gm")
    clues = _clues_from_session(session)
    recent = _recent_gm_text(session, limit=8)
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []

    mainline_map = {
        "standard_clear": 34,
        "low_escape": 22,
        "failed_escape": 8,
        "death_failed": 0,
        "abandoned": 0,
    }
    mainline = mainline_map.get(result, 0)
    exploration = min(20, len(clues) * 4 + min(8, history_rounds * 2))

    side = 0
    if re.search(r"(支线|救援|额外任务|隐藏任务)", recent):
        side += 8
    if re.search(r"(关键 NPC|救下|保护.*NPC|盟友)", recent):
        side += 6
    side = min(15, side)

    hidden = 0
    if re.search(r"(隐藏结局|真结局|隐藏真相|核心真相)", recent):
        hidden = 15
    elif re.search(r"(隐藏线索|真相|幕后|源头)", recent):
        hidden = 8

    achievements = 0
    achievement_notes: list[str] = []
    if players and all(int(p.get("hp") or 0) > 0 for p in players) and result not in {"death_failed", "abandoned"}:
        achievements += 8
        achievement_notes.append("全员存活")
    severe_conditions = {"污染", "失控", "濒死", "重伤"}
    all_conditions: list[str] = []
    for p in players:
        all_conditions.extend(str(c) for c in (p.get("conditions") or []) if str(c).strip())
    if players:
        san_ratio = sum((int(p.get("san") or 0) / max(1, int(p.get("san_max") or 180))) for p in players) / len(players)
        if san_ratio >= 0.55 and not any(c in severe_conditions for c in all_conditions):
            achievements += 6
            achievement_notes.append("低污染")
    if "复活" not in recent:
        achievements += 5
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
    if debts:
        loss -= min(10, math.ceil(debts / 300))
    if result == "death_failed":
        loss -= 20
    elif result == "abandoned":
        loss -= 10
    loss = max(-20, min(10, loss))

    total = max(0, min(100, mainline + exploration + side + hidden + achievements + loss))
    return {
        "rating_score": total,
        "score_breakdown": [
            {"id": "mainline", "label": "主线完成度", "score": mainline, "max": 40},
            {"id": "exploration", "label": "剧情探索度", "score": exploration, "max": 20},
            {"id": "side", "label": "隐藏支线", "score": side, "max": 15},
            {"id": "hidden", "label": "隐藏结局", "score": hidden, "max": 15},
            {"id": "achievements", "label": "特殊成就", "score": achievements, "max": 15, "notes": achievement_notes[:4]},
            {"id": "loss", "label": "损耗控制", "score": loss, "max": 10},
        ],
        "history_rounds": history_rounds,
        "clue_count": len(clues),
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
        "event_count": int(score.get("event_count") or 0),
        "reward": reward,
        "options": {"results": _WENYOU_RESULT_OPTIONS, "ratings": _WENYOU_RATING_OPTIONS},
    }


def _calculate_settlement_reward(session: dict, result: str, rating: str) -> dict:
    fw = _framework_for_runtime(session.get("framework") or {})
    difficulty = _normalize_difficulty(fw.get("difficulty"))
    base = _WENYOU_CLEAR_BASE_REWARD[difficulty]
    factors = _WENYOU_RESULT_FACTORS[result]
    rating_bonus = _WENYOU_RATING_BONUS[rating]
    base_points = round(base["points"] * factors["points"])
    base_exp = round(base["exp"] * factors["exp"])
    rating_points = round(base_points * rating_bonus["points"])
    rating_exp = round(base_exp * rating_bonus["exp"])
    gross_points = max(0, base_points + rating_points)
    gross_exp = max(0, base_exp + rating_exp)
    abandon_penalty = round(base["points"] * 0.15) if result == "abandoned" else 0
    base_rolls = int(base.get("rolls") or 1) if gross_points > 0 else 0
    rating_extra_rolls = 2 if rating == "S" else 1 if rating == "A" else 0
    return {
        "difficulty": difficulty,
        "result": result,
        "result_label": factors["label"],
        "rating": rating,
        "base_points": base_points,
        "base_exp": base_exp,
        "rating_points": rating_points,
        "rating_exp": rating_exp,
        "gross_points": gross_points,
        "gross_exp": gross_exp,
        "penalty_points": abandon_penalty,
        "reward_rolls": base_rolls + rating_extra_rolls if gross_points > 0 else 0,
        "base_reward_rolls": base_rolls,
        "rating_extra_rolls": rating_extra_rolls if gross_points > 0 else 0,
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
    if result == "standard_clear":
        clear_record = {
            "at": ledger_entry["at"],
            "gameId": ledger_entry["gameId"],
            "difficulty": str(settlement.get("difficulty") or ""),
            "rating": rating,
            "result": result,
        }
        wallet["clear_records"] = (wallet.get("clear_records") or [])[-29:] + [clear_record]
    _save_wenyou_wallet(user_id, wallet)
    _sync_session_points_with_wallet(session, wallet)

    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    level_changes: dict[str, Any] = {}
    for pk in ("player1", "player2"):
        player = st.get(pk) if isinstance(st.get(pk), dict) else _default_player_stats()
        level_changes[pk] = _grant_player_exp(player, int(settlement.get("gross_exp") or 0))
        st[pk] = player
    session["stats"] = st

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
            "players": {
                "player1": {"exp_delta": settlement["exp_delta"], **level_changes.get("player1", {})},
                "player2": {"exp_delta": settlement["exp_delta"], **level_changes.get("player2", {})},
            },
            "rewards": reward_grants,
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
    return "\n".join(lines)


def _slug_id(value: Any, fallback: str = "item") -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", raw).strip("_")
    return (raw or fallback)[:80]


def _rarity_rank(value: Any) -> int:
    return {"D": 1, "C": 2, "B": 3, "A": 4, "S": 5}.get(str(value or "D").strip().upper(), 1)


def _normalize_inventory_item(raw: Any, index: int = 0, source: str = "session") -> Optional[dict]:
    if isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("label") or raw.get("title") or "").strip()
        if not name:
            return None
        iid = _slug_id(raw.get("id") or raw.get("item_id") or name)
        qty = max(1, int(raw.get("quantity") or raw.get("qty") or 1))
        rarity = str(raw.get("rarity") or "D").strip().upper()
        if rarity not in {"D", "C", "B", "A", "S"}:
            rarity = "D"
        item = {
            "uid": str(raw.get("uid") or raw.get("item_uid") or f"{source}-{iid}-{index}")[:96],
            "id": iid,
            "name": name[:80],
            "kind": str(raw.get("kind") or raw.get("type") or "道具").strip()[:40],
            "category": str(raw.get("category") or raw.get("item_type") or "consumable").strip()[:40],
            "rarity": rarity,
            "desc": str(raw.get("desc") or raw.get("description") or "").strip()[:240],
            "quantity": qty,
            "source": str(raw.get("source") or source).strip()[:40],
            "acquired_at": str(raw.get("acquired_at") or raw.get("created_at") or now_beijing_iso()),
        }
        for key in ("sigil", "pool_id", "sealed", "sealed_reason", "converted_from"):
            if key in raw:
                item[key] = raw[key]
        if "stackable" in raw:
            item["stackable"] = bool(raw.get("stackable"))
        return item
    name = str(raw or "").strip()
    if not name:
        return None
    iid = _slug_id(name)
    return {
        "uid": f"legacy-{iid}-{index}",
        "id": iid,
        "name": name[:80],
        "kind": "道具",
        "category": "legacy",
        "rarity": "D",
        "desc": "",
        "quantity": 1,
        "source": "legacy",
        "acquired_at": now_beijing_iso(),
    }


def _normalize_inventory(raw: Any, source: str = "session") -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for i, item in enumerate(raw[:80]):
        normalized = _normalize_inventory_item(item, i, source)
        if normalized:
            out.append(normalized)
    return out[:80]


def _inventory_item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or "").strip()
    return str(item or "").strip()


def _inventory_item_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item or "").strip()
    name = _inventory_item_name(item)
    qty = int(item.get("quantity") or 1)
    suffix = f" x{qty}" if qty > 1 else ""
    sealed = "（封印）" if item.get("sealed") else ""
    return f"{name}{suffix}{sealed}".strip()


def _inventory_label_list(items: Any) -> list[str]:
    return [x for x in (_inventory_item_label(item) for item in _normalize_inventory(items, source="session")) if x]


def _inventory_has_item(inventory: list[dict], item_id: str = "", name: str = "") -> bool:
    iid = _slug_id(item_id) if item_id else ""
    name = str(name or "").strip()
    for item in _normalize_inventory(inventory, source="session"):
        if iid and str(item.get("id") or "") == iid:
            return True
        if name and _inventory_item_name(item) == name:
            return True
    return False


def _inventory_find_by_name(inventory: list[dict], name: str) -> Optional[dict]:
    needle = str(name or "").strip()
    if not needle:
        return None
    for item in _normalize_inventory(inventory, source="session"):
        if _inventory_item_name(item) == needle or str(item.get("uid") or "") == needle or str(item.get("id") or "") == needle:
            return item
    return None


def _inventory_item_matches(item: dict, target: dict) -> bool:
    if not isinstance(item, dict) or not isinstance(target, dict):
        return False
    uid = str(target.get("uid") or "").strip()
    if uid and str(item.get("uid") or "").strip() == uid:
        return True
    iid = str(target.get("id") or "").strip()
    if iid and str(item.get("id") or "").strip() == iid:
        return True
    name = _inventory_item_name(target)
    return bool(name and _inventory_item_name(item) == name)


def _consume_inventory_item(inventory: list[dict], target: dict) -> tuple[list[dict], Optional[dict]]:
    inv = _normalize_inventory(inventory, source="session")
    consumed: Optional[dict] = None
    out: list[dict] = []
    used = False
    for item in inv:
        cur = dict(item)
        if not used and _inventory_item_matches(cur, target):
            used = True
            consumed = dict(cur)
            qty = max(1, int(cur.get("quantity") or 1))
            consumed["quantity"] = 1
            if qty > 1:
                cur["quantity"] = qty - 1
                out.append(cur)
            continue
        out.append(cur)
    return out[:80], consumed


def _unseal_inventory_by_rank(inventory: list[dict], rank: str) -> tuple[list[dict], list[dict]]:
    max_rank = _normalize_difficulty(rank)
    out: list[dict] = []
    unlocked: list[dict] = []
    for item in _normalize_inventory(inventory, source="session"):
        cur = dict(item)
        if cur.get("sealed") and _rarity_rank(cur.get("rarity")) <= _rarity_rank(max_rank):
            cur.pop("sealed", None)
            cur.pop("sealed_reason", None)
            unlocked.append(cur)
        out.append(cur)
    return out[:80], unlocked


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
    kind = str(item.get("kind") or "").strip()
    desc = str(item.get("desc") or "").strip()
    if any(k in kind + desc for k in ("治疗", "急救", "绷带", "凝胶")):
        return {"hp": 25, "label": "恢复 25 HP"}
    if any(k in kind + desc for k in ("镇静", "精神", "记忆")):
        return {"san": 25, "label": "恢复 25 SAN"}
    return {"condition": f"{_inventory_item_name(item)}：一次性效果已生效", "label": "一次性效果已生效"}


def _apply_item_effect_to_session(session: dict, item: dict, detail: str = "") -> tuple[bool, str, Optional[dict]]:
    _session_ensure_stats(session)
    if item.get("sealed"):
        return False, f"文游：【{_inventory_item_name(item)}】还处于封印状态，不能使用。", None
    category = str(item.get("category") or "consumable").strip()
    if category in {"weapon", "ability", "bloodline", "fragment", "material"}:
        return False, f"文游：【{_inventory_item_name(item)}】不是可直接消耗的局内道具。", None

    st = session["stats"]
    player = st.get("player1") if isinstance(st.get("player1"), dict) else _default_player_stats()
    _recalc_player_caps(player)
    before = {"hp": int(player.get("hp") or 0), "san": int(player.get("san") or 0), "conditions": list(player.get("conditions") or [])}
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
    threshold_add = _apply_threshold_conditions(player)
    st["player1"] = player
    session["stats"] = st
    clock_updates = _apply_clock_updates(session, [effect["clock"]]) if isinstance(effect.get("clock"), dict) else []

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
    if detail:
        parts.append(f"使用意图：{detail[:160]}")
    result_text = "；".join(parts)
    changes = {
        "players": {
            "player1": {
                "hp_delta": int(player.get("hp") or 0) - before["hp"],
                "san_delta": int(player.get("san") or 0) - before["san"],
                "spi_delta": spi_delta,
                "conditions_add": list(dict.fromkeys(added + threshold_add)),
                "conditions_remove": removed,
            }
        },
        "inventory_add": [],
        "inventory_remove": [dict(item, quantity=1)],
        "clock_updates": clock_updates,
        "flags_set": {},
    }
    return True, result_text, changes


def _format_item_result_for_gm(item: dict, result_text: str) -> str:
    return (
        f"【系统判定】辛玥使用【{_inventory_item_name(item)}】，{result_text}，已消耗 1 个。"
        "请只根据这个已结算结果生成剧情反应；不要改写道具效果，不要重复扣除或治疗。"
    )


def _format_item_result_block(item: dict, result_text: str) -> str:
    return f"【道具结算】{_inventory_item_name(item)}：{result_text}；消耗 1。"


def _inject_item_result_into_output(output: str, item: dict, result_text: str) -> str:
    block = _format_item_result_block(item, result_text)
    if output.startswith("—— 主神系统 ——\n\n"):
        return output.replace("—— 主神系统 ——\n\n", f"—— 主神系统 ——\n\n{block}\n\n", 1)
    return f"{block}\n\n{output}" if output else block


def _new_inventory_item(defn: dict[str, Any], source: str, uid_prefix: str = "item", extra: Optional[dict] = None) -> dict:
    data = dict(defn or {})
    data.update(extra or {})
    data["uid"] = f"{uid_prefix}-{uuid4().hex[:12]}"
    data["source"] = source
    data["acquired_at"] = now_beijing_iso()
    return _normalize_inventory_item(data, 0, source) or {
        "uid": f"{uid_prefix}-{uuid4().hex[:12]}",
        "id": "unknown",
        "name": "未知物品",
        "kind": "道具",
        "category": "consumable",
        "rarity": "D",
        "desc": "",
        "quantity": 1,
        "source": source,
        "acquired_at": now_beijing_iso(),
    }


def _add_inventory_item(inventory: list[dict], item: dict) -> list[dict]:
    inv = _normalize_inventory(inventory, source="session")
    new_item = _normalize_inventory_item(item, len(inv), str(item.get("source") or "system"))
    if not new_item:
        return inv
    if new_item.get("stackable") or str(new_item.get("category") or "") in {"fragment", "material"}:
        for cur in inv:
            if str(cur.get("id") or "") == str(new_item.get("id") or "") and str(cur.get("category") or "") == str(new_item.get("category") or ""):
                cur["quantity"] = max(1, int(cur.get("quantity") or 1)) + max(1, int(new_item.get("quantity") or 1))
                cur["acquired_at"] = new_item.get("acquired_at") or now_beijing_iso()
                return inv[:80]
    inv.append(new_item)
    return inv[:80]


def _merge_inventory(base: Any, extra: Any) -> list[dict]:
    inv = _normalize_inventory(base, source="wallet")
    for item in _normalize_inventory(extra, source="session"):
        if str(item.get("category") or "") in {"fragment", "material"} or item.get("stackable"):
            inv = _add_inventory_item(inv, item)
        elif not _inventory_has_item(inv, item_id=str(item.get("id") or ""), name=_inventory_item_name(item)):
            inv.append(item)
    return inv[:80]


_SHOP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "bandage",
        "name": "绷带",
        "kind": "治疗",
        "rarity": "D",
        "price": 25,
        "desc": "非战斗中恢复 25 HP。",
    },
    {
        "id": "white_candle",
        "name": "白蜡烛",
        "kind": "治疗",
        "rarity": "D",
        "price": 25,
        "desc": "恢复 25 SAN，或移除动摇。",
    },
    {
        "id": "ration",
        "name": "压缩口粮",
        "kind": "补给",
        "rarity": "D",
        "price": 30,
        "desc": "长线生存中抵消一次饥饿或体力消耗。",
    },
    {
        "id": "glowstick",
        "name": "冷光棒",
        "kind": "工具",
        "rarity": "D",
        "price": 20,
        "desc": "黑暗场景 3 轮内观察惩罚 -1。",
    },
    {
        "id": "safety_rope",
        "name": "安全绳",
        "kind": "工具",
        "rarity": "D",
        "price": 50,
        "desc": "攀爬或坠落风险降低一级。",
    },
    {
        "id": "emergency_gel",
        "name": "急救凝胶",
        "kind": "治疗",
        "rarity": "C",
        "price": 90,
        "desc": "恢复 60 HP。",
    },
    {
        "id": "sedative",
        "name": "镇静剂",
        "kind": "治疗",
        "rarity": "C",
        "price": 85,
        "desc": "恢复 60 SAN，下轮观察或推理 -1。",
    },
    {
        "id": "oxygen_can",
        "name": "氧气罐",
        "kind": "补给",
        "rarity": "C",
        "price": 70,
        "desc": "抵消一次窒息、毒雾或水下行动惩罚。",
    },
    {
        "id": "old_key",
        "name": "旧铜钥匙",
        "kind": "线索道具",
        "rarity": "C",
        "price": 90,
        "desc": "可尝试打开一个低级锁或触发钥匙线索。",
    },
    {
        "id": "static_radio",
        "name": "杂音收音机",
        "kind": "侦测",
        "rarity": "C",
        "price": 100,
        "desc": "靠近异常源时会出现规律噪声。",
    },
    {
        "id": "blank_id_card",
        "name": "空白身份牌",
        "kind": "潜伏",
        "rarity": "C",
        "price": 120,
        "desc": "伪装身份暴露度 -1。",
    },
    {
        "id": "mirror_card",
        "name": "镜面卡",
        "kind": "防护",
        "rarity": "B",
        "price": 260,
        "desc": "抵消一次身份误认或精神暗示，最高 B 级。",
    },
    {
        "id": "testimony_bottle",
        "name": "证言封存瓶",
        "kind": "线索",
        "rarity": "B",
        "price": 280,
        "desc": "保存一段证言，防止被副本篡改。",
    },
    {
        "id": "rule_eraser",
        "name": "规则橡皮",
        "kind": "干涉",
        "rarity": "B",
        "price": 320,
        "desc": "验证性擦除一条低级规则，失败则 SAN -15。",
    },
    {
        "id": "blood_thread",
        "name": "溯源红线",
        "kind": "追踪",
        "rarity": "B",
        "price": 260,
        "desc": "标记目标，3 轮内不易跟丢。",
    },
    {
        "id": "god_heal_ticket",
        "name": "主神治疗券",
        "kind": "治疗",
        "rarity": "B",
        "price": 240,
        "desc": "恢复 HP/SAN 各 80，或移除重伤/污染之一。",
    },
    {
        "id": "causal_chalk",
        "name": "因果粉笔",
        "kind": "线索",
        "rarity": "B",
        "price": 360,
        "desc": "标记一处因果节点，解密判定 +3。",
    },
    {
        "id": "door_token",
        "name": "门缝代币",
        "kind": "位移",
        "rarity": "A",
        "price": 130,
        "desc": "在封闭空间里尝试换取一次离开机会。",
    },
    {
        "id": "black_ticket",
        "name": "黑色车票",
        "kind": "撤离",
        "rarity": "A",
        "price": 150,
        "desc": "触发紧急撤离路线，代价由规则表结算。",
    },
    {
        "id": "memory_needle",
        "name": "记忆针",
        "kind": "校验",
        "rarity": "A",
        "price": 140,
        "desc": "用于确认一段记忆是否被副本改写。",
    },
    {
        "id": "rule_film",
        "name": "规则隔离膜",
        "kind": "防护",
        "rarity": "A",
        "price": 420,
        "desc": "1 轮内规则污染伤害 -50%。",
    },
    {
        "id": "paper_double",
        "name": "替身纸人",
        "kind": "防护",
        "rarity": "A",
        "price": 650,
        "desc": "抵消一次致命 HP 伤害，之后燃尽。",
    },
    {
        "id": "rewind_pod",
        "name": "回溯急救仓",
        "kind": "治疗",
        "rarity": "A",
        "price": 800,
        "desc": "结算阶段回满 HP/SAN，并移除一个严重状态。",
    },
    {
        "id": "weak_rewrite_pen",
        "name": "弱规则改写笔",
        "kind": "干涉",
        "rarity": "A",
        "price": 900,
        "desc": "改写一条低级规则，威胁时钟 +2。",
    },
    {
        "id": "settlement_review",
        "name": "结算复核券",
        "kind": "结算",
        "rarity": "A",
        "price": 1200,
        "desc": "重算一次奖励或惩罚，结果必须接受。",
    },
    {
        "id": "half_amulet",
        "name": "半枚护符",
        "kind": "护身",
        "rarity": "S",
        "price": 2100,
        "desc": "抵消一次高额代价，但会添加未知标记。",
    },
    {
        "id": "god_receipt",
        "name": "主神小票",
        "kind": "凭证",
        "rarity": "S",
        "price": 2400,
        "desc": "申请复核一次主神判定，可能附带副作用。",
    },
]

_SHOP_CATALOG_BY_ID = {str(item.get("id") or ""): item for item in _SHOP_CATALOG}
_GACHA_SINGLE_COST = 100
_GACHA_MAX_COUNT = 10
_GACHA_FRAGMENT_VALUES = {"D": 5, "C": 15, "B": 50, "A": 180, "S": 600}
_GACHA_POOL_RATES: dict[str, list[tuple[str, float]]] = {
    "mixed": [("D", 50.0), ("C", 34.0), ("B", 12.0), ("A", 3.7), ("S", 0.3)],
    "weapon_pool": [("D", 45.0), ("C", 36.0), ("B", 14.0), ("A", 4.5), ("S", 0.5)],
    "ability_pool": [("D", 50.0), ("C", 35.0), ("B", 11.0), ("A", 3.7), ("S", 0.3)],
    "evolution_pool": [("D", 55.0), ("C", 32.0), ("B", 9.0), ("A", 3.7), ("S", 0.3)],
    "limited_pool": [("D", 35.0), ("C", 40.0), ("B", 18.0), ("A", 6.4), ("S", 0.6)],
}
_GACHA_CATALOG: list[dict[str, Any]] = [
    {"id": "emergency_bandage", "name": "应急绷带", "rarity": "D", "kind": "物资", "category": "consumable", "desc": "一次性治疗道具。", "sigil": "BND", "stackable": True},
    {"id": "white_candle", "name": "白蜡烛", "rarity": "D", "kind": "规则", "category": "consumable", "desc": "短暂标记安全区域。", "sigil": "CDL", "stackable": True},
    {"id": "safety_rope", "name": "安全绳", "rarity": "D", "kind": "工具", "category": "consumable", "desc": "降低坠落与脱队风险。", "sigil": "RPE", "stackable": True},
    {"id": "static_radio", "name": "静电收音机", "rarity": "C", "kind": "线索", "category": "consumable", "desc": "偶尔捕获副本广播残响。", "sigil": "RAD", "stackable": True},
    {"id": "blank_id_card", "name": "空白身份牌", "rarity": "C", "kind": "潜伏", "category": "consumable", "desc": "可写入一次临时身份。", "sigil": "ID", "stackable": True},
    {"id": "testimony_bottle", "name": "证言瓶", "rarity": "C", "kind": "记忆", "category": "consumable", "desc": "封存一段关键证词。", "sigil": "MEM", "stackable": True},
    {"id": "rule_eraser", "name": "规则橡皮", "rarity": "B", "kind": "干涉", "category": "consumable", "desc": "验证性擦除一条低级规则。", "sigil": "DEL", "stackable": True},
    {"id": "god_heal_ticket", "name": "主神治疗券", "rarity": "B", "kind": "治疗", "category": "consumable", "desc": "结算或安全场景恢复重伤。", "sigil": "HEAL", "stackable": True},
    {"id": "blood_thread", "name": "血色牵引线", "rarity": "B", "kind": "追踪", "category": "consumable", "desc": "锁定一个目标的残留路线。", "sigil": "LINE", "stackable": True},
    {"id": "camp_hatchet", "name": "营地斧", "rarity": "D", "kind": "近战", "category": "weapon", "desc": "D 级主武器，破坏判定 +1。", "sigil": "AXE"},
    {"id": "iron_flashlight", "name": "铁皮手电", "rarity": "C", "kind": "工具", "category": "weapon", "desc": "黑暗观察惩罚 -1。", "sigil": "LAMP"},
    {"id": "blood_crowbar", "name": "血锈撬棍", "rarity": "B", "kind": "近战", "category": "weapon", "desc": "可强行撬开异常封锁。", "sigil": "BAR"},
    {"id": "door_key_fragment", "name": "门钥碎片", "rarity": "A", "kind": "撤离", "category": "consumable", "desc": "拼合后可开启异常出口。", "sigil": "GATE"},
    {"id": "rewind_pod", "name": "回溯急救仓", "rarity": "A", "kind": "治疗", "category": "consumable", "desc": "结算阶段移除严重状态。", "sigil": "POD"},
    {"id": "weak_rewrite_pen", "name": "弱改写笔", "rarity": "A", "kind": "规则", "category": "consumable", "desc": "短暂改写一个可验证条件。", "sigil": "PEN"},
    {"id": "anomaly_intuition", "name": "异常直觉", "rarity": "D", "kind": "能力", "category": "ability", "desc": "每副本 1 次，获得一个轻微异常提示。", "sigil": "INT"},
    {"id": "shadow_hide", "name": "影中藏身", "rarity": "B", "kind": "能力", "category": "ability", "desc": "潜伏行动风险降低一级。", "sigil": "SHD"},
    {"id": "night_body", "name": "夜视体质", "rarity": "D", "kind": "进化", "category": "evolution", "desc": "黑暗环境观察惩罚 -1。", "sigil": "NITE"},
    {"id": "half_demon", "name": "半妖进化", "rarity": "B", "kind": "进化", "category": "evolution", "desc": "HP +40，physical 伤害 -3。", "sigil": "DEMN"},
    {"id": "god_receipt", "name": "主神小票", "rarity": "S", "kind": "凭证", "category": "consumable", "desc": "申请复核一次主神判定。", "sigil": "VOID"},
    {"id": "god_echo", "name": "主神残响", "rarity": "S", "kind": "能力", "category": "ability", "desc": "封印体，需阶位解锁完整效果。", "sigil": "ECHO"},
    {"id": "memory_needle", "name": "记忆缝针", "rarity": "S", "kind": "记忆", "category": "consumable", "desc": "缝合一次被污染的关键记忆。", "sigil": "NEED"},
]
_GACHA_ITEMS_BY_RARITY: dict[str, list[dict[str, Any]]] = {}
for _gacha_item in _GACHA_CATALOG:
    _GACHA_ITEMS_BY_RARITY.setdefault(str(_gacha_item.get("rarity") or "D"), []).append(_gacha_item)


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


def _reward_catalog_candidates(category: str, rarity: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    catalog: list[dict[str, Any]] = []
    for raw in list(_SHOP_CATALOG) + list(_GACHA_CATALOG):
        item = dict(raw)
        iid = str(item.get("id") or item.get("name") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        catalog.append(item)
    same_rarity = [item for item in catalog if str(item.get("rarity") or "D").upper() == rarity]
    if category == "gear":
        return [item for item in same_rarity if str(item.get("category") or "") in {"weapon", "armor", "accessory", "equippable_tool"}]
    if category == "consumable_item":
        return [item for item in same_rarity if str(item.get("category") or "consumable") == "consumable"]
    return []


def _reward_stack_item(category: str, rarity: str) -> dict[str, Any]:
    if category == "material":
        names = {
            "D": ("low_forge_material", "低级锻材", 1),
            "C": ("low_forge_material", "低级锻材", 2),
            "B": ("mid_forge_material", "中级锻材", 2),
            "A": ("high_forge_material", "高级锻材", 2),
            "S": ("legend_forge_material", "传说锻材", 1),
        }
        iid, name, qty = names.get(rarity, names["D"])
        return {
            "id": iid,
            "name": name,
            "kind": "锻材",
            "category": "material",
            "rarity": rarity,
            "quantity": qty,
            "desc": "副本结算获得的锻造材料。",
            "stackable": True,
        }
    if category in {"ability_fragment", "evolution_fragment"}:
        qty = int(_WENYOU_REWARD_FRAGMENT_AMOUNTS.get(category, {}).get(rarity, 10))
        label = "能力碎片" if category == "ability_fragment" else "进化碎片"
        return {
            "id": category,
            "name": label,
            "kind": "碎片",
            "category": "fragment",
            "rarity": rarity,
            "quantity": qty,
            "desc": f"{rarity} 级结算奖励，可用于后续成长。",
            "stackable": True,
        }
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
    for index in range(rolls):
        rarity = _weighted_pick(_WENYOU_REWARD_RARITY_RATES.get(difficulty, []), rng, fallback=difficulty)
        if rating == "S":
            rarity = _shift_rarity(rarity, 1)
        elif rating == "A" and rng.random() < 0.3:
            rarity = _shift_rarity(rarity, 1)
        elif (rating == "C" and rng.random() < 0.3) or rating in {"D", "F"}:
            rarity = _shift_rarity(rarity, -1)
        if rating == "S" and index == 0 and _rarity_rank(rarity) < _rarity_rank("B"):
            rarity = "B"
        category = _weighted_pick(_WENYOU_REWARD_CATEGORY_RATES.get(rarity, []), rng, fallback="consumable_item")
        candidates = _reward_catalog_candidates(category, rarity)
        if candidates:
            picked = dict(candidates[rng.randrange(len(candidates))])
        else:
            picked = _reward_stack_item(category, rarity)
        item = _new_inventory_item(picked, "settlement", "reward", {"reward_category": category})
        rewards.append(
            {
                "roll_id": f"reward-{index + 1:02d}",
                "rarity": rarity,
                "category": category,
                "category_label": _WENYOU_REWARD_CATEGORY_LABELS.get(category, category),
                "item": item,
            }
        )
        has_bplus = has_bplus or _rarity_rank(rarity) >= _rarity_rank("B")
    if rating == "S" and rewards and not has_bplus:
        replacement = _new_inventory_item(_reward_stack_item("material", "B"), "settlement", "reward", {"reward_category": "material"})
        rewards[0] = {
            "roll_id": rewards[0].get("roll_id") or "reward-01",
            "rarity": "B",
            "category": "material",
            "category_label": _WENYOU_REWARD_CATEGORY_LABELS["material"],
            "item": replacement,
        }
    return rewards


def _normalize_gacha_pool_id(pool_id: Any) -> str:
    pool = str(pool_id or "mixed").strip().lower()
    if pool == "bloodline_pool":
        pool = "evolution_pool"
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
    legacy_evolution_pool = pools_raw.get("bloodline_pool")
    pools = {}
    for pool_id in _GACHA_POOL_RATES:
        source = pools_raw.get(pool_id)
        if pool_id == "evolution_pool" and source is None:
            source = legacy_evolution_pool
        pools[pool_id] = _normalize_gacha_pool_state(source)
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


def roll_gacha(user_id: int, pool_id: str = "mixed", count: int = 1) -> tuple[bool, str, dict]:
    uid = int(user_id)
    pool = _normalize_gacha_pool_id(pool_id)
    try:
        pull_count = int(count or 1)
    except Exception:
        pull_count = 1
    if pull_count not in (1, 10):
        return False, "命运裂隙目前只支持单抽或十连。", get_shop_view(uid)

    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "当前没有可写入背包的文游存档，请先开始副本。", get_shop_view(uid)
    _session_ensure_stats(session)
    phase = _session_phase(session)
    if phase not in {"hub", "settlement"}:
        return False, "副本进行中，命运裂隙关闭；请回到主神空间或结算阶段再抽取。", get_shop_view(uid)

    wallet = _load_wenyou_wallet(uid, session)
    cost = pull_count * _GACHA_SINGLE_COST
    if int(wallet.get("points") or 0) < cost:
        return False, "主神积分不足，命运裂隙没有响应。", get_shop_view(uid)

    gacha = _normalize_gacha_state(wallet.get("gacha"))
    pool_state = _normalize_gacha_pool_state(gacha["pools"].get(pool))
    seed = f"wenyou-gacha:{uid}:{pool}:{pool_state.get('total', 0)}:{now_beijing_iso()}:{uuid4().hex[:8]}"
    rng = random.Random(seed)
    st = session["stats"]
    inventory = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
    results: list[dict] = []
    inventory_added: list[dict] = []

    for _ in range(pull_count):
        rarity = _roll_rarity_by_rate(pool, rng)
        rarity, pity_hit = _apply_gacha_pity(pool_state, rarity)
        pool_state = _update_gacha_pity(pool_state, rarity)
        picked = _pick_gacha_definition(pool, rarity, rng)
        prepared = _prepare_gacha_item_for_inventory(picked, session, pool)
        duplicate_to_fragment = str(prepared.get("category") or "") in {"weapon", "ability", "bloodline", "evolution"} and _inventory_has_item(inventory, item_id=str(prepared.get("id") or ""))
        if duplicate_to_fragment:
            fragment = _new_inventory_item(_gacha_fragment_item(prepared), "gacha", "gacha-frag", {"pool_id": pool})
            inventory = _add_inventory_item(inventory, fragment)
            result_item = dict(prepared)
            result_item.update({"pullId": f"pull-{uuid4().hex[:10]}", "converted": True, "converted_to": fragment, "pity_hit": pity_hit})
            inventory_added.append(fragment)
            results.append(result_item)
        else:
            item_obj = _new_inventory_item(prepared, "gacha", "gacha", {"pool_id": pool})
            inventory = _add_inventory_item(inventory, item_obj)
            result_item = dict(item_obj)
            result_item.update({"pullId": str(item_obj.get("uid") or f"pull-{uuid4().hex[:10]}"), "pity_hit": pity_hit})
            inventory_added.append(item_obj)
            results.append(result_item)

    wallet["points"] = max(0, int(wallet.get("points") or 0) - cost)
    wallet["inventory"] = inventory[:80]
    gacha["pools"][pool] = pool_state
    wallet["gacha"] = gacha
    wallet["ledger"] = (wallet.get("ledger") or [])[-79:] + [
        {
            "at": now_beijing_iso(),
            "type": "gacha_roll",
            "pool_id": pool,
            "count": pull_count,
            "points_delta": -cost,
            "result_ids": [str(item.get("id") or "") for item in results],
        }
    ]
    _save_wenyou_wallet(uid, wallet)
    st["inventory"] = inventory
    session["stats"] = st
    _sync_session_points_with_wallet(session, wallet)
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"gacha_{len(event_log) + 1:03d}",
        "source": "rules_engine.gacha",
        "changes": {
            "wallet": {"points_delta": -cost, "points": wallet["points"]},
            "inventory_add": inventory_added,
            "gacha": {"pool_id": pool, "count": pull_count, "pity": pool_state},
        },
        "seed": seed,
        "created_at": now_beijing_iso(),
    }
    event_log.append(patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = patch
    r2_store.save_wenyou_session(uid, session)
    return True, f"命运裂隙完成 {pull_count} 次牵引，扣除 {cost} 主神积分。", {
        "active": True,
        "pool_id": pool,
        "count": pull_count,
        "cost": cost,
        "points": wallet["points"],
        "wallet": session.get("wallet"),
        "pity": pool_state,
        "results": results,
        "inventory": inventory,
        "session": get_session_view(uid).get("session"),
    }


def _shop_today_key() -> str:
    return now_beijing_iso()[:10]


def _shop_offer_items(user_id: int) -> list[dict[str, Any]]:
    """每天按用户固定随机 7-8 个商品；普通商店只出 D/C，低概率 1 个 B。"""
    rng = random.Random(f"wenyou-shop:{int(user_id or 0)}:{_shop_today_key()}")
    low = [dict(item) for item in _SHOP_CATALOG if str(item.get("rarity") or "D") in {"D", "C"}]
    mid = [dict(item) for item in _SHOP_CATALOG if str(item.get("rarity") or "D") == "B"]
    rng.shuffle(low)
    rng.shuffle(mid)
    offers = low[:8]
    if mid and rng.random() < 0.35:
        offers = low[:7] + [mid[0]]
        rng.shuffle(offers)
    return offers[:8]


def get_shop_view(user_id: int) -> dict:
    """文游系统商店：只读取当前 session 积分与背包。"""
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    active = bool(session and isinstance(session, dict) and session.get("gameId"))
    phase = "hub"
    inventory: list[dict] = []
    wallet = _load_wenyou_wallet(uid, session if active else None)
    if active:
        _session_ensure_stats(session)
        st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
        phase = _session_phase(session)
        _sync_session_points_with_wallet(session, wallet)
        inventory = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
    can_buy = bool(active and _shop_open_for_phase(phase))
    return {
        "active": active,
        "phase": phase,
        "phaseLabel": _phase_label(phase),
        "can_buy": can_buy,
        "points": max(0, int(wallet.get("points") or 0)),
        "debts": max(0, int(wallet.get("debts") or 0)),
        "inventory": inventory,
        "generatedAt": _shop_today_key(),
        "items": _shop_offer_items(uid),
    }


def buy_shop_item(user_id: int, item_id: str) -> tuple[bool, str, dict]:
    """购买商店道具：扣当前 session 积分，写入当前背包。"""
    uid = int(user_id)
    iid = str(item_id or "").strip()
    if not iid:
        return False, "请选择要购买的道具。", get_shop_view(uid)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return False, "当前没有可写入背包的副本，请先开始副本或进入结算阶段。", get_shop_view(uid)
    _session_ensure_stats(session)
    phase = _session_phase(session)
    if not _shop_open_for_phase(phase):
        return False, "副本进行中，系统商店关闭；只能使用背包已有物品，结束并进入结算后再购买。", get_shop_view(uid)
    offers = {str(item.get("id") or ""): item for item in _shop_offer_items(uid)}
    item = offers.get(iid)
    if not item:
        return False, "该商品已下架，请刷新系统商店。", get_shop_view(uid)
    st = session["stats"]
    wallet = _load_wenyou_wallet(uid, session)
    points = max(0, int(wallet.get("points") or 0))
    price = max(0, int(item.get("price") or 0))
    if points < price:
        return False, "主神积分不足。", get_shop_view(uid)
    inv = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
    name = str(item.get("name") or "").strip()
    if not name:
        return False, "商品数据异常。", get_shop_view(uid)
    if _inventory_has_item(inv, item_id=iid, name=name):
        return False, f"背包里已有【{name}】。", get_shop_view(uid)
    inv = _add_inventory_item(inv, _new_inventory_item(item, "shop", "shop"))
    wallet["points"] = points - price
    wallet["inventory"] = inv[:80]
    wallet["ledger"] = (wallet.get("ledger") or [])[-79:] + [
        {"at": now_beijing_iso(), "type": "shop_buy", "item_id": iid, "item_name": name, "points_delta": -price}
    ]
    _save_wenyou_wallet(uid, wallet)
    st["points"] = int(wallet.get("points") or 0)
    st["inventory"] = inv[:80]
    session["stats"] = st
    _sync_session_points_with_wallet(session, wallet)
    r2_store.save_wenyou_session(uid, session)
    view = get_shop_view(uid)
    view["bought"] = {"id": iid, "name": name, "price": price}
    return True, f"已购买【{name}】，扣除 {price} 主神积分。", view


def _resolve_player_key(player_id: Any = "player1") -> str:
    raw = str(player_id or "player1").strip().lower()
    if raw in {"player2", "p2", "du", "渡", "d"}:
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
        "attribute_bonus": 2,
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
            "ability_tokens": int(player.get("ability_tokens") or 0),
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
    player["unspent_attribute_points"] = int(player.get("unspent_attribute_points") or 0) + 2
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
    return {
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
    }


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
        return None, "文游：候选设定生成失败（DeepSeek 无响应）。"
    data = _extract_json_object(text)
    items = _normalize_candidate_payload(data)
    if not items:
        return None, "文游：候选设定解析失败，请重试。"
    return {
        "version": 1,
        "generatedAt": now_beijing_iso(),
        "difficultyHint": difficulty_hint,
        "items": items[:n],
    }, None


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
        f"标签：{tags or '无'}\n"
        f"篇幅：{item.get('estimated_length') or '标准'}"
    )


def _candidate_core_prompt(item: dict) -> str:
    return f"""把【候选设定】扩展成副本核心设定短稿。

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 4-7 行，每行尽量短。
- 必须包含：副本内部场景、核心矛盾、玩家公开任务、隐藏悬念、危险规则方向。
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


def _candidate_blueprint_prompt(item: dict, core_text: str = "") -> str:
    return f"""基于【已确定核心设定】生成副本蓝图短稿。

输出要求：
- 只写自然语言，不要 JSON，不要 markdown 代码块，不要表格。
- 按三段写：开场、探索、收束。
- 每段写“阶段目标 / 关键线索 / 错过线索时如何推进”。
- 只给 GM/后端内部短纲，不要整段剧透给玩家。

【已确定核心设定】
{_candidate_canon_block(item, core_text)}
"""


def _candidate_opening_prompt(item: dict, core_text: str = "") -> str:
    return f"""基于【已确定核心设定】生成副本开场正文。

输出要求：
- 只写开场正文，不要 JSON，不要 markdown 代码块。
- 4-8 句，含主神传送/白光/提示音/刻板广播之一。
- 落入副本场景，点出第一处异常。
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
    raw = {
        "instance_code": _candidate_instance_code(item),
        "instance_name": title,
        "instance_genre": genre,
        "genre_note": genre_note,
        "difficulty": difficulty,
        "tasker_total": 2,
        "player_count": 2,
        "world": world,
        "player1_name": "辛玥",
        "player1_instance_name": "",
        "player1_role": "任务者。黑色长发黑眼，中等身高一米六多，二十岁出头。",
        "player2_name": "渡",
        "player2_instance_name": "",
        "player2_role": "任务者。银色短发，一米八多，薄肌，二十多岁。",
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
            ],
        },
        "initial_stats": {
            "points": 100,
            "player1": dict(_default_player_stats()),
            "player2": dict(_default_player_stats()),
            "items": [],
        },
        "opening": opening,
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
    return {
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
        f"· 玩家一「{_show_name(fw.get('player1_name', '辛玥'), fw.get('player1_instance_name', ''))}」\n{fw.get('player1_role', '')}\n\n"
        f"· 玩家二「{_show_name(fw.get('player2_name', '渡'), fw.get('player2_instance_name', ''))}」\n{fw.get('player2_role', '')}\n\n"
        f"【NPC 任务者】\n{npc_block}\n\n"
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

    if keywords and keywords.strip():
        fw, err = generate_framework_custom(keywords)
    else:
        fw, err = generate_framework_random(_difficulty_from_progress(uid))
    if err or not fw:
        return err or "文游：开局失败。"

    session = _new_session(fw)
    wallet = _load_wenyou_wallet(uid, session)
    _sync_session_points_with_wallet(session, wallet)
    session.setdefault("stats", {})["inventory"] = _merge_inventory(wallet.get("inventory"), session.get("stats", {}).get("inventory"))
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    head = "文游开局成功（无限流 · 主神副本模式）。\n\n" + _format_framework_lines(fw) + "\n\n—— 主神系统 / GM ——\n\n"
    foot = _format_status_footer(session)
    return head + fw.get("opening", "") + "\n\n" + foot


def cmd_story_from_candidate(user_id: int, candidate: Any) -> str:
    """处理大厅候选扩展开局；完整副本框架由并行 DS 子任务生成。"""
    uid = int(user_id)
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

    fw, err = generate_framework_from_candidate(candidate)
    if err or not fw:
        return err or "文游：候选扩展开局失败。"

    session = _new_session(fw)
    wallet = _load_wenyou_wallet(uid, session)
    _sync_session_points_with_wallet(session, wallet)
    session.setdefault("stats", {})["inventory"] = _merge_inventory(wallet.get("inventory"), session.get("stats", {}).get("inventory"))
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    head = "文游开局成功（无限流 · 主神副本模式）。\n\n" + _format_framework_lines(fw) + "\n\n—— 主神系统 / GM ——\n\n"
    foot = _format_status_footer(session)
    return head + fw.get("opening", "") + "\n\n" + foot


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
    fw = _framework_for_runtime(session.get("framework") or {})
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
    fallback = []
    if fw.get("genre_note"):
        fallback.append(str(fw.get("genre_note")))
    if fw.get("world"):
        fallback.append(str(fw.get("world"))[:180])
    return fallback[:4]


def _compact_text(value: Any, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit > 0 and len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _player_summary_for_card(player: Any) -> str:
    p = player if isinstance(player, dict) else {}
    ab = _normalize_abilities_list(p.get("abilities"))
    ab_names = "、".join(a.get("name", "") for a in ab[:4] if a.get("name")) or "无"
    return (
        f"HP {p.get('hp', 0)}/{p.get('hp_max', 0)}，SAN {p.get('san', 0)}/{p.get('san_max', 0)}，精神力 {p.get('spi_current', 0)}/{p.get('spi_max', 0)}，"
        f"Lv{p.get('level', 1)}·{p.get('rank', 'D')}阶，EXP {p.get('exp', 0)}，"
        f"力{p.get('str', 0)}/体{p.get('con', p.get('vit', 0))}/敏{p.get('agi', 0)}/智{p.get('int', p.get('wis', 0))}/精{p.get('spi', 0)}/运{p.get('luk', 0)}，"
        f"进化：{p.get('evolution') or p.get('bloodline', '凡人')}，能力：{ab_names}"
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
                "du_action": _compact_text(item.get("du_action"), 260),
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
        "以下只记录 App 文游/无限流跑团的虚构游戏进度；不是现实经历，不参与动态召回，只供渡本轮行动参考。",
    ]
    if cur:
        inv = "、".join(cur.get("inventory") or []) or "无"
        clues = "；".join(cur.get("clues") or []) or "无"
        lines.extend(
            [
                f"- 当前副本：{cur.get('instance') or '未知'}｜{cur.get('genre') or '未知'}｜难度 {cur.get('difficulty') or '-'}｜阶段：{cur.get('phase') or '副本'}",
                f"- 当前任务：{cur.get('task') or '暂无'}",
                f"- 辛玥状态：{cur.get('player1') or '未知'}",
                f"- 渡状态：{cur.get('player2') or '未知'}",
                f"- 背包：{inv}",
                f"- 已知备忘：{clues}",
            ]
        )
    if recent:
        lines.append("最近文游回合：")
        for item in recent[:4]:
            lines.append(
                f"- {item.get('instance') or '当前副本'}：辛玥行动「{item.get('xinyue_action') or '无'}」；"
                f"渡行动「{item.get('du_action') or '无'}」；GM 结算「{item.get('gm_result') or '无'}」"
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
            "xinyue_action": _compact_text(p1_text, 260),
            "du_action": _compact_text(p2_text, 260),
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
            f"辛玥本轮行动：{_compact_text(p1_text, 500)}\n"
            f"渡本轮行动：{_compact_text(p2_text, 500)}"
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


def _history_tail_for_du(session: dict) -> str:
    lines: list[str] = []
    for h in (session.get("history") or [])[-8:]:
        if not isinstance(h, dict):
            continue
        role = str(h.get("role") or "").strip()
        content = _compact_text(_strip_main_god_panel(str(h.get("content") or "")), 420)
        if not content:
            continue
        who = "GM" if role == "gm" else ("辛玥" if role == "player1" else "渡")
        lines.append(f"{who}：{content}")
    return "\n".join(lines[-8:])


def generate_du_action_for_round(user_id: int, xinyue_action: str) -> str:
    """生成渡本轮行动：只读文游 session/card，不使用动态召回。"""
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return ""
    _session_ensure_stats(session)
    fw = _framework_for_runtime(session.get("framework") or {})
    card_context = _build_wenyou_card_context(r2_store.get_wenyou_card(uid))
    cur = _current_instance_for_card(session)
    prompt = "\n\n".join(
        x
        for x in (
            card_context,
            "【当前副本状态】\n"
            f"副本：{cur.get('instance')}｜{cur.get('genre')}｜难度 {cur.get('difficulty')}｜阶段：{cur.get('phase')}\n"
            f"任务：{cur.get('task')}\n"
            f"辛玥状态：{cur.get('player1')}\n"
            f"渡状态：{cur.get('player2')}\n"
            f"背包：{'、'.join(cur.get('inventory') or []) or '无'}\n"
            f"线索/规则备忘：{'；'.join(cur.get('clues') or []) or '无'}",
            f"【最近剧情】\n{_history_tail_for_du(session) or '暂无'}",
            f"【辛玥本轮行动】\n{_compact_text(xinyue_action, 700)}",
            "请只决定“渡”本轮如何行动，保持 30-120 字，输出严格 JSON。",
        )
        if x
    )
    text = call_wenyou_deepseek([{"role": "user", "content": prompt}], system=_DU_ACTION_SYSTEM, temperature=0.65)
    fallback = "渡先保持警戒，贴近辛玥确认周围风险，优先寻找可验证线索和可撤退路线。"
    if not text:
        return fallback
    data = _extract_json_object(text)
    action = str((data or {}).get("action") or "").strip()
    if not action:
        action = _compact_text(text, 140)
    action = re.sub(r"^[\"'“”]+|[\"'“”]+$", "", action).strip()
    return action[:220] or fallback


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
    _sync_session_points_with_wallet(session, wallet)
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
            "growth": _growth_view(session, wallet),
            "settlement": session.get("settlement") if isinstance(session.get("settlement"), dict) else None,
            "inventory": list(st.get("inventory") or []),
            "clues": _clues_from_session(session),
            "clocks": list(session.get("clocks") or []),
            "last_state_patch": session.get("last_state_patch") if isinstance(session.get("last_state_patch"), dict) else None,
            "pending_round": {
                "player1_lines": list(pr.get("player1_lines") or []),
                "player2_lines": list(pr.get("player2_lines") or []),
            },
            "history": history,
        },
    }


def cmd_record_action(user_id: int, text: str, player: str = "player1") -> tuple[bool, str]:
    """记录玩家行动到 pending_round，不立即调用 GM。"""
    uid = int(user_id)
    action = str(text or "").strip()
    if not action:
        return False, "行动内容不能为空。"
    if len(action) > 1200:
        action = action[:1200]
    role = "player2" if str(player or "").lower() in ("player2", "p2", "du", "渡") else "player1"
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
    arr = pr.get(key)
    if not isinstance(arr, list):
        arr = []
    arr.append(action)
    pr[key] = arr[-8:]
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


def cmd_action_with_du(user_id: int, text: str) -> tuple[str, str]:
    """记录辛玥行动，自动生成渡的本轮行动，再推进 GM。"""
    ok, msg = cmd_record_action(user_id, text, "player1")
    if not ok:
        return msg, ""
    du_action = generate_du_action_for_round(user_id, text)
    if du_action:
        ok_du, du_msg = cmd_record_action(user_id, du_action, "player2")
        if not ok_du:
            logger.warning("文游渡自动行动记录失败 user_id=%s error=%s", user_id, du_msg)
            du_action = ""
    return cmd_go(user_id), du_action


def _use_item_system_result(user_id: int, item_name: str, action: str = "") -> tuple[bool, str, str, dict, Optional[dict], Optional[dict]]:
    uid = int(user_id)
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
    inventory = _merge_inventory(wallet.get("inventory"), st.get("inventory"))
    target = _inventory_find_by_name(inventory, item)
    if not target:
        return False, f"文游：背包里没有【{item}】。", "", session, wallet, None
    detail = str(action or "").strip()
    ok, result_text, changes = _apply_item_effect_to_session(session, target, detail)
    if not ok:
        return False, result_text, "", session, wallet, target
    inventory_after, consumed = _consume_inventory_item(inventory, target)
    if not consumed:
        return False, f"文游：背包里没有【{item}】。", "", session, wallet, target
    wallet["inventory"] = inventory_after[:80]
    st["inventory"] = inventory_after[:80]
    session["stats"] = st
    _sync_session_points_with_wallet(session, wallet)
    event_log = session.get("event_log") if isinstance(session.get("event_log"), list) else []
    patch = {
        "round_id": f"item_{len(event_log) + 1:03d}",
        "source": "rules_engine.item_use",
        "item": consumed,
        "changes": changes or {},
        "created_at": now_beijing_iso(),
    }
    event_log.append(patch)
    session["event_log"] = event_log[-200:]
    session["last_state_patch"] = patch
    return True, result_text, _format_item_result_for_gm(consumed, result_text), session, wallet, consumed


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


def cmd_use_item_with_du(user_id: int, item_name: str, action: str = "") -> tuple[str, str]:
    """使用道具：系统结算后，渡再根据结算结果行动，最后交给 GM 叙事。"""
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
    du_action = generate_du_action_for_round(uid, gm_note)
    if du_action:
        ok_du, du_msg = cmd_record_action(uid, du_action, "player2")
        if not ok_du:
            logger.warning("文游渡自动行动记录失败 user_id=%s error=%s", user_id, du_msg)
            du_action = ""
    out = cmd_go(uid)
    if out.startswith("文游：GM 调用失败"):
        r2_store.save_wenyou_session(uid, copy.deepcopy(original_session))
        _save_wenyou_wallet(uid, copy.deepcopy(original_wallet))
        return out, ""
    return _inject_item_result_into_output(out, consumed or {}, result_text), du_action


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
            who = "玩家一" if role == "player1" else "玩家二（渡）"
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
    p2_text = "\n".join(p2).strip() or "（玩家二渡本轮暂无行动描述）"

    user_blob = f"玩家一本轮行动：\n{p1_text}\n\n玩家二（渡）本轮行动：\n{p2_text}\n"

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

    narrative = _strip_main_god_panel(gm_out)
    patch_text = _format_state_patch_for_display(state_patch)
    foot = _format_status_footer(session)
    if patch_text:
        narrative = f"{narrative}\n\n{patch_text}" if narrative.strip() else patch_text
    display = f"{narrative}\n\n{foot}" if narrative.strip() else foot

    return f"—— 主神系统 ——\n\n{display}"


def cmd_end(user_id: int, result: str = "", rating: str = "") -> str:
    """进入系统空间结算阶段（不立即归档）。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)
        return "文游：当前没有进行中的局。"

    _session_ensure_stats(session)
    session["phase"] = "settlement"
    session.setdefault("stats", {})["phase"] = "settlement"
    settlement = _grant_settlement_reward(uid, session, result=result, rating=rating)
    summary = _format_settlement_summary(settlement)
    ts = now_beijing_iso()
    session.setdefault("history", []).append(
        {
            "role": "gm",
            "content": "【主神提示】副本已结束，进入系统空间结算阶段。可进行购买道具、治疗、强化与整备；整备完成后请完成最终结算归档。\n\n" + summary,
            "timestamp": ts,
        }
    )
    r2_store.save_wenyou_session(uid, session)
    return "文游：已进入系统空间结算阶段。\n\n" + summary + "\n\n现在可进行商店、治疗与整备；完成后请归档本局。"


def cmd_settle(user_id: int) -> str:
    """结算完成并归档本局。"""
    uid = int(user_id)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return "文游：当前没有进行中的局。"
    if _session_phase(session) != "settlement":
        return "文游：当前不在结算阶段。请先结束副本并进入系统空间结算。"

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
    return "文游：本局已完成最终结算并归档。下一局可在系统空间重新开局。MiniApp 可查看已完成副本。"
