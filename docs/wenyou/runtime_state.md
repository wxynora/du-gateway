# 文游运行时状态与缓存规则

本文档定义副本生成后系统要缓存什么、每轮行动如何更新状态、哪些内容发送给 GM/DS、哪些内容只由后端规则引擎维护。

核心原则：

- 后端状态是唯一事实源。任务进度、线索、威胁时钟、背包、装备、状态、位置、怪物实例和奖励进度都不能让 GM 每轮自由重写。
- GM/DS 负责叙事、NPC 表演、环境反馈和提出事件意图；它可以提出“可能发现线索/可能推进任务”的意图，但最终是否更新由后端规则判断。
- 前端任务面板、线索面板、状态面板、地图、背包都从后端缓存状态读，不从 GM 本轮文本里临时解析。
- GM 每轮只接收必要切片，不接收全量隐藏状态，不要求它每轮输出完整任务/线索/背包。
- 所有状态变化都通过 `state_patch` 写入，方便回放、调试和开源后替换后端。

## 最小可运行闭环

如果先不做完整后端，只要保证下面 5 件事，流程就能稳定运行：

1. 选择副本后，系统生成并缓存 `instance_runtime_state`，至少包含副本蓝图、初始任务、隐藏支线/隐藏结局标记、NPC 任务者、怪物生态、威胁时钟和玩家状态。
2. 每轮行动前，后端先处理确定性规则：阶段、道具、冷却、耐久、状态 tick、威胁时钟固定推进。
3. 后端只把本轮需要的 `gm_context` 发给 GM/DS；GM/DS 只输出剧情、事件意图和状态建议。
4. 后端根据事件意图生成 `state_patch`，更新任务、线索、地点、NPC、怪物、威胁时钟、背包和玩家状态。
5. 结算时从缓存状态读取当前玩家角色/玩家队伍的主线、支线、隐藏支线、隐藏结局、特殊成就和损耗记录计算评级，不让 GM 临场总结决定奖励；NPC 任务者只作为副本事实记录，不参与玩家评级。

这套闭环里，GM/DS 不直接改面板、不发奖励、不判定精确数值。

## 状态分层

| 层 | 名称 | 谁能读 | 用途 |
| --- | --- | --- | --- |
| 公开层 | `public_state` | 玩家、前端、GM | 玩家已知任务、已发现线索、当前位置、公开 NPC、可见异常、公开规则 |
| 隐藏层 | `gm_state` | 后端、GM 的相关切片 | 真规则、假规则、隐藏结局、NPC 隐藏目标、未发现线索、Boss 条件 |
| 规则层 | `rules_state` | 后端规则引擎 | 精确 HP/SAN、当前精神力、精确威胁时钟、随机 seed、掉落记录、冷却、计数器 |
| 归档层 | `archive_state` | 后端、复盘页面 | 回合历史、state_patch、结算记录、可公开的隐藏内容 |

注意：

- `public_state` 是给 UI 和玩家看的，不包含精确隐藏时钟、未发现线索和隐藏结局条件。
- `gm_state` 可以发送给 GM，但必须按当前场景裁剪，只给“本轮可能用到的隐藏摘要”。
- `rules_state` 不应该原样发给 GM；GM 不需要知道所有 seed、精确掉落权重、完整库存池和所有隐藏触发器。

## 副本生成后必须缓存

副本一旦从候选变成正式副本，后端要生成并缓存 `instance_runtime_state`。

必需字段：

```json
{
  "instance_id": "inst_001",
  "seed": "run-20260517-001",
  "phase": "instance_running",
  "round": 0,
  "instance_meta": {},
  "public_state": {},
  "gm_state": {},
  "rules_state": {},
  "runtime_indexes": {},
  "history": [],
  "event_log": [],
  "last_state_patch": null
}
```

### instance_meta

固定副本身份，不随每轮叙事重写。

| 字段 | 说明 |
| --- | --- |
| `instance_id` | 副本 id |
| `name` | 副本名 |
| `difficulty` | D/C/B/A/S |
| `genre` | 副本类型 |
| `era_tags` | 时代标签 |
| `tasker_total` | 总任务者数量 |
| `player_ids` | 玩家角色 id |
| `npc_tasker_ids` | 任务者 NPC id |
| `blueprint_id` | 蓝图 id |
| `encounter_profile_id` | 怪物生态 id |
| `content_pack_id` | 内容包 id |
| `ruleset_id` | 规则包 id |

### public_state

玩家可见状态，前端面板只读这里和玩家 profile。

| 模块 | 说明 |
| --- | --- |
| `visible_rules` | 玩家已知规则、公告、禁令 |
| `public_tasks` | 主线任务、已公开支线、当前目标、显示进度 |
| `discovered_clues` | 已发现线索、验证状态、关联任务 |
| `known_locations` | 已知地点、当前位置、可到达路径、公开危险等级 |
| `visible_npcs` | 已见 NPC 任务者、公开身份、公开态度、最后位置、存活状态 |
| `visible_monsters` | 已见怪物、公开弱点、最近动向 |
| `public_threat` | 模糊危险阶段，例如 `低/升高/接近清算`，不显示精确数值 |
| `scene_summary` | 当前场景短摘要 |
| `last_rules_result` | 上轮后端规则结算摘要 |

### gm_state

隐藏叙事状态，GM 可读取相关切片，但不能把它直接展示给玩家。

| 模块 | 说明 |
| --- | --- |
| `instance_blueprint` | 主线、支线、隐藏结局、线索图、硬约束 |
| `gm_secret` | 真规则、假规则、NPC 立场和行为倾向、隐藏触发 |
| `hidden_tasks` | 未公开任务、隐藏支线、隐藏结局进度 |
| `clue_graph` | 全量线索图，包含未发现线索和 fail-forward 路径 |
| `npc_private_state` | NPC 任务者立场、当前意图、是否会使坏、公开状态 |
| `boss_logic` | Boss 处理条件、封印条件、撤离条件 |
| `scene_directives` | 本阶段 GM 必须遵守的短规则 |

### rules_state

后端权威状态，不让 GM 直接改。

| 模块 | 说明 |
| --- | --- |
| `players` | HP/SAN、当前精神力、属性、状态、位置、行动锁定 |
| `inventory` | 背包实例、数量、耐久、剩余次数、封印 |
| `equipment` | 装备槽、武器/防具/饰品/工具加成 |
| `task_progress` | 所有任务的精确状态：locked/active/completed/failed |
| `clue_state` | 所有线索的 discovered/verified/contradicted/consumed |
| `location_state` | 节点开放、封锁、危险等级、一次性资源 |
| `npc_state` | NPC 位置、存活状态、公开态度、立场、使坏触发记录 |
| `monster_instances` | 当前生成的怪物实例、HP、状态、警戒值 |
| `threat_clocks` | 精确威胁时钟、触发规则、阶段后果 |
| `rule_violations` | 玩家触犯规则记录 |
| `cooldowns` | 道具、能力、Boss 事件、场景事件冷却 |
| `settlement_flags` | 当前玩家角色/玩家队伍的主线、支线、隐藏支线、隐藏结局、特殊成就和损耗记录 |
| `reward_context` | 已获得 reward tags、待结算奖励、隐藏奖励资格 |
| `rng_state` | 可回放随机 seed 和 roll 记录 |

### runtime_indexes

为运行效率准备的索引，不要求 GM 看到。

| 索引 | 说明 |
| --- | --- |
| `task_by_id` | 任务 id -> 任务对象 |
| `clue_by_id` | 线索 id -> 线索对象 |
| `location_by_id` | 地点 id -> 地点对象 |
| `npc_by_id` | NPC id -> NPC 对象 |
| `monster_by_id` | 怪物实例 id -> 怪物对象 |
| `active_triggers` | 当前可触发规则、线索、怪物、时钟 |

## 任务和线索状态

任务结构：

```json
{
  "id": "main_escape_harbor",
  "title": "找到真正离港凭证",
  "type": "main",
  "visibility": "public",
  "status": "active",
  "progress": {
    "current": 1,
    "target": 3,
    "mode": "steps"
  },
  "required_clues": ["radio_lie", "black_ticket"],
  "fail_forward": "错过黑色船票时，可通过救下报信人获得替代路线",
  "reward_tags": ["mainline", "escape"]
}
```

线索结构：

```json
{
  "id": "radio_lie",
  "title": "广播漏掉第 13 分钟",
  "visibility": "public",
  "status": "discovered",
  "verified": false,
  "source": "scene_observation",
  "leads_to": ["fake_rule_notice", "true_departure"],
  "related_tasks": ["main_escape_harbor"],
  "tags": ["broadcast", "time"],
  "public_text": "广播每次报时都会漏掉第 13 分钟",
  "gm_note": "验证后可削弱 Boss 广播一次"
}
```

状态枚举：

| 对象 | 状态 |
| --- | --- |
| 任务 | `locked` / `active` / `completed` / `failed` / `hidden_completed` |
| 线索 | `unknown` / `hinted` / `discovered` / `verified` / `contradicted` / `consumed` |
| 地点 | `unknown` / `known` / `accessible` / `locked` / `sealed` / `collapsed` |
| NPC | `unknown` / `met` / `ally` / `neutral` / `hostile` / `missing` / `dead` |
| 怪物实例 | `dormant` / `patrolling` / `alerted` / `chasing` / `defeated` / `sealed` |

GM 可以描述“你觉得这张票很重要”，但不能直接把线索状态改成 `verified`。必须由后端根据行动、道具、判定或蓝图规则更新。

## 每轮行动流程

推荐严格两阶段流程：

```text
1. Player Action
2. Backend validate phase / action / item / cooldown
3. Pre-rule update: 处理确定性变化
4. Compose GM Context: 从缓存状态裁剪本轮上下文
5. GM 输出 narrative_draft + event_intent + state_proposals
6. Rules Engine 校验 event_intent/state_proposals
7. Apply State Patch
8. GM 或模板根据 state_patch 生成最终叙事反馈
9. Save runtime_state / event_log / history
10. Frontend panels 从 public_state 读取，不从 GM 文本解析
```

如果为了省调用使用单次 GM：

```text
Player Action -> Backend Pre-rule -> GM Narrative + Intent -> Backend Apply Patch -> UI 显示后端状态摘要
```

单次 GM 模式下，若 GM 文本和后端结算冲突，后端状态优先；下一轮要把 `last_rules_result` 发给 GM 纠偏。

### Pre-rule update

玩家行动进入 GM 前，后端先处理确定规则：

- 阶段是否合法。
- 玩家是否濒死、失控、行动锁定。
- 使用道具是否存在、次数/耐久是否足够、是否满足门槛。
- 切换装备、移动、查看面板、购买、抽卡、加点等纯系统操作。
- 已经确定的冷却、持续状态 tick、威胁时钟固定推进。
- 上轮延迟效果，例如中毒、流血、追逐倒计时。

这些结果写成 `pre_state_patch`，并以摘要形式发给 GM。

### 玩家行动归类

玩家可以自由输入文本，但文本里的“我成功逃跑了”“我一刀杀死它”不是权威结果。后端先把自由文本归类成结构化 `action_intent`，再按阶段、状态、道具、怪物和蓝图规则结算。

最小行动结构：

```json
{
  "raw_text": "我披上塑料雨衣，从后门绕出去，尽量避开那个护士",
  "actor_id": "player1",
  "action_type": "evade",
  "declared_goal": "离开护士站",
  "targets": ["monster_nurse_001"],
  "used_item_ids": ["wy_d_plastic_raincoat"],
  "declared_method_tags": ["disguise", "stealth", "backdoor"],
  "risk_acceptance": "normal"
}
```

行动类型：

| `action_type` | 说明 | 默认处理 |
| --- | --- | --- |
| `investigate` | 搜索、观察、验证线索、阅读规则 | 走线索/规则判定，可能发现或验证线索 |
| `move` | 移动到地点、开门、进入/离开区域 | 校验地点连通、锁定、危险和触发器 |
| `talk` | 交涉、套话、威慑、安抚、欺骗 | 走 NPC/怪物社交或精神判定 |
| `use_item` | 明确使用背包物品 | 先走 `use_item` 规则，成功结果再给 GM 叙事 |
| `equip` | 切换武器、防具、饰品或工具 | 只在允许阶段或安全节点直接结算 |
| `attack` | 攻击、破坏、压制怪物或障碍 | 走战斗/破坏判定 |
| `evade` | 潜行、伪装、绕路、躲避遭遇 | 走规避判定，成功可避开战斗 |
| `flee` | 已被追逐或战斗中尝试逃跑 | 走逃跑判定，成功改变位置和怪物状态 |
| `defend` | 防守、掩护、格挡、保护队友 | 降低本轮风险或改变目标 |
| `rest` | 治疗、整理、恢复、临时休整 | 只在安全节点或低压场景允许 |
| `system_action` | 商店、抽卡、加点、晋升、结算确认 | 不进 GM，后端直接返回系统 patch |

归类规则：

- 如果文本同时包含多个目标，后端按“主要目标”结算，次要目标只能作为情境加成或后续提示；不能一轮完成过多高价值操作。
- 如果玩家声明结果，例如“我已经逃出去了”，后端只保留“尝试逃跑”的意图，结果由 `state_patch` 决定。
- 如果玩家给出具体工具、路线、线索或伪装，后端可以给 `situational_bonus`、`item_bonus` 或降低风险。
- 如果行动目标不清楚，GM 可以先叙事追问；但高危场景中模糊行动默认按普通风险处理，不免费停表。
- 纯系统操作不应消耗剧情轮，除非处于副本内高压状态且规则明确会推进时钟。

行动归类可以由规则代码、轻量分类模型或 GM 输出提议完成，但最终 `action_type` 必须落到固定枚举，方便测试和回放。

### GM Context

每轮发给 GM 的不是全量存档，而是裁剪后的上下文：

```json
{
  "round": 12,
  "phase": "instance_running",
  "player_action": "我用录音笔复听广播第 13 分钟",
  "visible_state": {
    "scene_summary": "...",
    "current_location": "...",
    "public_tasks": [],
    "discovered_clues": [],
    "visible_npcs": [],
    "visible_monsters": [],
    "public_threat": "正在升高"
  },
  "relevant_gm_secret": {
    "current_blueprint_phase": "...",
    "relevant_hidden_rules": [],
    "possible_clue_unlocks": [],
    "npc_private_notes": {}
  },
  "rules_feedback": {
    "pre_state_patch_summary": "...",
    "last_state_patch_summary": "..."
  },
  "recent_history": []
}
```

必须发给 GM：

- 当前场景短摘要。
- 玩家本轮行动。
- 玩家可见任务和已发现线索摘要。
- 当前地点、可见 NPC、可见怪物。
- 本轮相关的隐藏蓝图切片。
- 上轮后端结算摘要。
- 最近 3-6 轮剧情摘要。

不应每轮发给 GM：

- 全量道具目录。
- 全量奖励表。
- 全量未发现线索和隐藏结局。
- 精确抽卡概率、掉落 seed、所有商店库存。
- 所有 NPC 的完整隐藏立场和后续行为计划。
- 全量历史正文。

## DS 提示词最小约束

每轮 GM/DS 提示词必须固定包含下面的约束，避免模型又把面板和规则拿回去自己写：

```text
你是副本 GM，只负责叙事、环境反馈、NPC 表演和事件意图。
后端 runtime_state 是唯一事实源。
不要每轮重写完整任务、线索、背包、状态或奖励面板。
不要直接判定 HP/SAN/积分/EXP/抽卡/掉落/晋升。
不要凭空新增可带出副本的高价值物品、能力、进化或隐藏结局。
本轮只输出：
1. narrative：玩家可见剧情；
2. event_intent：风险、目标、标签、NPC/怪物/环境意图；
3. state_proposals：可能的任务推进、线索发现、地点变化、时钟变化建议。
最终是否更新状态，由后端按 ruleset 和 state_patch 判定。
```

副本生成提示词也必须提醒：

```text
先生成 instance_blueprint 和 encounter_profile，再由后端缓存。
蓝图只列主线、支线、隐藏支线、隐藏结局、关键线索、NPC 任务者、怪物生态和威胁时钟。
不要把完整后续剧情写死；每轮推进时只读取当前阶段切片。
```

## GM 输出格式

GM 输出分三层：

| 层 | 是否权威 | 用途 |
| --- | --- | --- |
| `narrative` | 否 | 玩家看到的剧情文本 |
| `event_intent` | 否 | 本轮风险、怪物行动、NPC 行动、环境变化意图 |
| `state_proposals` | 否 | 可能发现线索、推进任务、改变地点、触发时钟、获得局内任务物品或可带走物品的建议 |

示例：

```json
{
  "narrative": "录音笔里，第 13 分钟的位置只有一段很轻的水声……",
  "event_intent": {
    "risk": "moderate",
    "targets": ["player1"],
    "tags": ["mental", "broadcast", "clue_check"],
    "monster_action": null,
    "npc_action": {
      "npc_001": "tries_to_hide_fear"
    }
  },
  "state_proposals": [
    {
      "type": "discover_clue",
      "id": "radio_lie",
      "confidence": "high",
      "reason": "玩家使用录音笔复核广播"
    },
    {
      "type": "clock_delta",
      "id": "harbor_broadcast",
      "delta": 1,
      "reason": "复听广播触发监听"
    },
    {
      "type": "acquire_task_item",
      "id": "boss_release_bell",
      "name": "渡魂铃",
      "rarity": "S",
      "effect": "只在本副本内使用；对当前 Boss 的执念超度判定 +8，使用后碎裂",
      "visibility": "public",
      "reason": "玩家完成隐藏支线后获得的副本内任务物品"
    },
    {
      "type": "acquire_item",
      "id": "wy_d_002",
      "visibility": "public",
      "reason": "玩家在护士站药箱中找到了可带出通用物品"
    },
    {
      "type": "acquire_unique_item",
      "id": "boss_blessing",
      "name": "无面新娘的祝福",
      "rarity": "S",
      "effect": "可带出；完全解封后对婚契/身份误认/执念类规则判定 +6",
      "seal_rank": "A",
      "requirements": {"spi_min": 18},
      "visibility": "public",
      "reason": "隐藏好结局中 Boss 被感化并主动赠予"
    }
  ]
}
```

GM 禁止：

- 直接输出“HP -20 / SAN -10 / 获得 300 积分”作为权威结算。
- 每轮重写完整任务列表、线索列表、背包和状态。
- 凭空新增高价值道具、奖励、隐藏结局。
- 凭叙事直接把长期道具塞进背包；任务物品只能提议 `acquire_task_item`，由后端写入局内临时背包且默认 `carry_out=false`。
- 把副本内任务物品当成可带出通用奖励；可带出物只能提议 `acquire_item`，由后端按内容表、难度上限、封印和数量规则决定。
- 把隐藏好结局唯一奖励当成普通掉落刷；这类只能提议 `acquire_unique_item`，必须有强因果、`seal_rank` 或 `requirements`，入包后默认按门槛封印。
- 把隐藏时钟精确数值写给玩家。
- 因为叙事顺手就完成任务、验证线索或关闭 Boss。

## State Patch

后端把 GM 意图和玩家行动结算成 `state_patch`。

```json
{
  "round_id": "round_012",
  "source": "rules_engine",
  "pre_patch": false,
  "changes": {
    "players": {
      "player1": {
        "hp_delta": 0,
        "san_delta": -8,
        "spi_current_delta": -2,
        "conditions_add": [],
        "conditions_remove": []
      }
    },
    "tasks": [
      {
        "id": "main_escape_harbor",
        "status": "active",
        "progress_delta": 1
      }
    ],
    "clues": [
      {
        "id": "radio_lie",
        "status": "discovered",
        "verified": true
      }
    ],
    "locations": [],
    "npcs": [],
    "monsters": [],
    "clock_updates": [
      {
        "id": "harbor_broadcast",
        "delta": 1,
        "visibility": "hidden"
      }
    ],
    "inventory": [],
    "flags_set": {
      "heard_13th_minute_water": true
    }
  },
  "public_summary": "你确认广播第 13 分钟存在异常，但复听动作也让广播更接近你。",
  "gm_summary": "radio_lie 已验证；harbor_broadcast +1。"
}
```

`changes` 字段规范：

| 字段 | 说明 |
| --- | --- |
| `players` | HP/SAN/当前精神力、EXP、积分、属性点、状态、位置、行动锁定变化 |
| `inventory` | 道具获得、消耗、次数/耐久变化、封印/解封、临时任务物品变化 |
| `equipment` | 装备槽变化、装备等级/锻造/耐久/报废/维修 |
| `tasks` | 主线、支线、隐藏支线的状态和进度变化 |
| `clues` | 线索提示、发现、验证、矛盾、消耗 |
| `locations` | 地点开放、封锁、坍塌、危险等级和当前所在位置 |
| `npcs` | NPC 任务者公开状态、位置、存活、使坏记录和隐藏立场变化 |
| `monsters` | 怪物实例生成、HP、警戒、追逐、击退、封印、离场 |
| `clock_updates` | 威胁时钟精确变化和公开可见性 |
| `cooldowns` | 道具、能力、Boss 事件、场景事件冷却 |
| `settlement_flags` | 主线/支线/隐藏结局/成就/损耗记录 |
| `reward_context` | 待结算奖励标签、奖励 roll 次数、保底状态、唯一奖励资格 |
| `flags_set` | 轻量布尔或枚举标记，不能替代上面的结构化字段 |

GM `state_proposals` 到 patch 的映射：

| proposal 类型 | 后端校验 | 写入位置 |
| --- | --- | --- |
| `discover_clue` | 是否存在该线索、行动是否满足发现条件 | `public_state.discovered_clues` + `rules_state.clue_state` |
| `verify_clue` | 是否已发现、是否有证据/道具/判定成功 | `rules_state.clue_state` |
| `task_progress` | 是否满足蓝图目标或替代条件 | `rules_state.task_progress` + `public_state.public_tasks` |
| `clock_delta` | 时钟 id 是否存在、是否允许公开 | `rules_state.threat_clocks`，必要时更新 `public_threat` |
| `npc_update` | NPC 是否在场、是否符合立场/压力规则 | `rules_state.npc_state`，公开部分投影到 `visible_npcs` |
| `monster_update` | 怪物实例是否存在、是否符合战斗/追逐规则 | `rules_state.monster_instances`，公开部分投影到 `visible_monsters` |
| `acquire_task_item` | 是否来自当前副本蓝图/隐藏任务，默认不可带出 | `rules_state.inventory`，`carry_out=false` |
| `acquire_item` | 是否在通用目录、难度上限、数量和封印规则内 | `rules_state.inventory` |
| `acquire_unique_item` | 是否有隐藏结局/强因果，是否写门槛和封印 | `rules_state.inventory` + `reward_context` |
| `settlement_flag` | 是否由任务、线索、结局或成就触发 | `rules_state.settlement_flags` |

Patch 规则：

- `event_log` 追加保存完整 patch。
- `public_state` 只写玩家可见部分。
- `gm_state` 写隐藏任务、隐藏线索、NPC 暗线变化。
- `rules_state` 写精确数值、时钟、seed、冷却和掉落。
- patch 必须可回放；不能只保存自然语言。

## 面板读取规则

前端面板读取：

| 面板 | 数据来源 |
| --- | --- |
| 任务 | `public_state.public_tasks` |
| 线索 | `public_state.discovered_clues` |
| 状态 | `rules_state.players[player_id]` 的可公开投影 |
| 背包 | `rules_state.inventory` 的可公开投影 |
| 地图/地点 | `public_state.known_locations` |
| NPC | `public_state.visible_npcs` |
| 怪物 | `public_state.visible_monsters` |
| 危险程度 | `public_state.public_threat`，不是精确 `threat_clock` |
| 历史 | `history` + `event_log.public_summary` |

GM 文本只进入剧情历史，不作为面板事实源。若玩家问“任务现在是什么”，前端应读任务缓存，而不是让 DS 重新总结。

## 威胁时钟可见性

威胁时钟默认属于隐藏层和规则层。

| 内容 | 玩家可见性 |
| --- | --- |
| 时钟 id/name | 可模糊公开，例如“广播清算正在逼近” |
| 精确数值 4/6 | 默认隐藏 |
| tick 规则 | 默认隐藏，可通过线索/道具部分揭示 |
| 阶段提示 | 可用氛围表现 |
| 到达 max 的后果 | 可通过规则、传闻或失败经历逐步揭示 |

前端默认只显示：

```text
危险程度：平稳 / 升高 / 高危 / 接近清算
```

探查类道具或能力可以返回：

```text
威胁正在升高；距离清算不远。
```

不能直接返回：

```text
harbor_broadcast = 4/6
```

除非内容包明确设计成公开倒计时副本。

## 缓存生命周期

| 时机 | 操作 |
| --- | --- |
| 候选生成 | 只缓存轻量候选，不生成完整运行态 |
| 选择副本 | 生成并缓存 `instance_blueprint`、`encounter_profile`、初始 runtime state |
| 开场 | 写入 `public_state.scene_summary`、初始任务和已知规则 |
| 每轮行动前 | 读 runtime state，做 pre-rule update |
| 每轮行动后 | 应用 state_patch，更新 public/gm/rules 三层 |
| 每 3-6 轮 | 压缩 history 摘要，但不丢 event_log |
| 结算 | 锁定 runtime state，生成 settlement_result |
| 归档 | 公开归档 + 可选 GM 归档；隐藏内容按设置脱敏 |

缓存失效：

- ruleset/content_pack 版本变化时，旧副本继续用旧版本，不能中途换规则。
- 如果必须迁移，写 `migration_patch`，并进入 event_log。
- GM 文本解析失败不能丢状态；保留上轮状态并生成错误事件。

## 后端接口建议

```text
create_instance_runtime(candidate, player_profile, ruleset, content_pack) -> runtime_state
get_public_view(runtime_state, player_id) -> public_view
classify_player_action(runtime_state, raw_action) -> action_intent
compose_gm_context(runtime_state, player_action) -> gm_context
apply_pre_rules(runtime_state, player_action) -> pre_state_patch
parse_gm_intent(gm_output) -> event_intent + state_proposals
resolve_action(runtime_state, action_intent, gm_intent) -> state_patch
apply_event_intent(runtime_state, event_intent, state_proposals) -> state_patch
apply_state_patch(runtime_state, state_patch) -> runtime_state
append_history(runtime_state, narrative, state_patch) -> runtime_state
archive_instance(runtime_state, settlement_result) -> archive
```

这些接口可以用任意后端实现；核心要求是：

- 读写同一份 runtime state。
- 面板数据来自 `get_public_view`。
- GM context 来自 `compose_gm_context`。
- 所有变更通过 patch。
