# 文游副本生成与怪物生态

## 副本蓝图

在生成具体开场剧情之前，必须先生成一份简短副本蓝图 `instance_blueprint`。当前 `du-gateway` 可以由 DS 生成；开源版只要求“蓝图生成模型/服务”输出同一结构，不绑定具体模型。

目的：

- 先定主线、支线、隐藏结局、线索链和阶段边界。
- 防止后续每轮即兴生成彻底放飞。
- 让后端可以根据蓝图记录探索度、支线完成度、隐藏结局触发和特殊成就。
- 让 GM 每轮推进时有可回看的短纲，而不是只看最近几轮文本。

### 生成顺序

```text
1. 玩家选择/随机副本候选
2. 生成 instance_blueprint
3. 生成 encounter_profile
4. 后端校验蓝图和怪物结构
5. 生成 public framework 与 gm_secret
6. 生成 opening
7. 正式进入 instance_running
```

### 蓝图字段

```json
{
  "blueprint_version": 1,
  "logline": "一句话说明本副本核心矛盾",
  "mainline": [
    {
      "phase": "开场",
      "goal": "让玩家确认任务与第一处异常",
      "required_clues": ["港口广播不可信"],
      "fail_forward": "错过线索时，由 NPC 触发广播事件推进"
    }
  ],
  "side_quests": [
    {
      "id": "save_tasker_lin",
      "title": "救下林砚",
      "hook": "林砚知道旧灯塔密码的一半",
      "resolution": "成功救下后解锁撤离捷径",
      "reward_tags": ["npc_relation", "shortcut"]
    }
  ],
  "hidden_endings": [
    {
      "id": "true_departure",
      "title": "真正离港",
      "requirements": ["识破假广播", "保留黑色船票", "没有杀死报信人"],
      "reward_tier_hint": "B+"
    }
  ],
  "clue_graph": [
    {
      "id": "radio_lie",
      "public_text": "广播每次报时都会漏掉第 13 分钟",
      "leads_to": ["fake_rule_notice", "true_departure"],
      "is_required_for_mainline": true
    }
  ],
  "npc_arcs": {
    "npc_001": {
      "public_role": "同批任务者",
      "hidden_goal": "优先撤离，但不会主动杀人",
      "pressure_point": "害怕广播点名",
      "possible_turns": ["合作", "误导", "抢先撤离"]
    }
  },
  "threat_clocks": [
    {
      "id": "harbor_broadcast",
      "name": "港口广播清算",
      "max": 6,
      "tick_rule": "每 2 轮或触犯广播规则 +1",
      "at_max": "进入强制撤离/清算阶段"
    }
  ],
  "hard_constraints": [
    "不能在第 3 轮前直接揭示真结局",
    "NPC 可以阴人，但默认不能直接致死玩家",
    "每条主线线索至少有 2 种获得方式"
  ]
}
```

## 副本怪物生态

每个副本生成蓝图后，后台必须结合副本设定生成 `encounter_profile`。怪物不是全局固定图鉴，而是当前副本主题下的一组临时实体模板。

详细数值模板、生成预算、战斗/规避结算和 Boss 平衡规则见 `docs/wenyou/monster_system.md`。本文只保留副本生成链路中的怪物结构示例。

生成层级：

| 层级 | 数量建议 | 定位 | 是否可战胜 |
| --- | ---: | --- | --- |
| 普通怪物 `common` | 3-8 种 | 巡逻、追逐、消耗资源、制造风险 | 可击退、规避或短暂消灭 |
| 精英怪物 `elite` | 1-3 种 | 守门、看守关键线索、压迫玩家路线 | 可击败或削弱，但成本较高 |
| Boss `boss` | 1 个 | 副本核心压力源、规则化身、倒计时终点 | 默认不可正面战胜 |

### encounter_profile

```json
{
  "profile_version": 1,
  "theme_tags": ["规则怪谈", "雾港", "广播污染"],
  "common": [
    {
      "id": "common_broadcast_listener",
      "name": "听广播的人",
      "role": "巡逻普通怪",
      "count_hint": "2-5",
      "rank": "D",
      "hp": 35,
      "attack": 8,
      "defense": 2,
      "mental_attack": 6,
      "mental_resist": 2,
      "speed": 10,
      "tags": ["humanlike", "broadcast", "swarm"],
      "weaknesses": ["堵住耳朵", "切断广播"],
      "resistances": ["普通劝说"],
      "special_rules": ["听见整点广播后速度 +2，持续 2 轮"],
      "defeat_result": "击退 3 轮或使威胁时钟 -1"
    }
  ],
  "elite": [
    {
      "id": "elite_lighthouse_keeper",
      "name": "灯塔看守",
      "role": "关键线索守门",
      "rank": "B",
      "hp": 120,
      "attack": 18,
      "defense": 8,
      "mental_attack": 16,
      "mental_resist": 10,
      "speed": 12,
      "tags": ["guardian", "key_clue"],
      "weaknesses": ["旧灯塔密码", "背光"],
      "resistances": ["远程压制"],
      "special_rules": ["未取得密码前受到伤害 -50%"],
      "defeat_result": "掉落关键线索或打开捷径"
    }
  ],
  "boss": {
    "id": "boss_harbor_broadcast",
    "name": "港口广播",
    "role": "规则压力源",
    "rank": "A",
    "hp": null,
    "attack": 0,
    "defense": 999,
    "mental_attack": 28,
    "mental_resist": 999,
    "speed": 0,
    "tags": ["boss", "rule_source", "broadcast"],
    "default_invincible": true,
    "can_be_killed": false,
    "counterplay": ["识破假广播", "找到真报时器", "关闭旧灯塔电源"],
    "weaken_conditions": ["收集 3 条广播矛盾线索"],
    "seal_conditions": ["在第 13 分钟前播放反向录音"],
    "escape_conditions": ["持有黑色船票并进入真实码头"],
    "at_max_clock": "进入强制清算"
  }
}
```

怪物面板字段：

| 字段 | 说明 |
| --- | --- |
| `rank` | D/C/B/A/S，用于套用难度和奖励口径 |
| `hp` | 可被物理/规则攻击削减的稳定值；Boss 可为 `null` |
| `attack` | HP 伤害基准 |
| `defense` | 物理防御 |
| `mental_attack` | SAN/污染伤害基准 |
| `mental_resist` | 精神/规则抗性 |
| `speed` | 追逐、先手、逃脱和命中修正 |
| `tags` | 主题、弱点匹配、奖励和道具互动标签 |
| `weaknesses` | 可降低难度或造成额外效果的弱点 |
| `resistances` | 伤害减免或无效手段 |
| `special_rules` | 特殊机制，必须系统可判定 |
| `defeat_result` | 击败/击退/封印后的系统结果 |

### Boss 规则

Boss 一般不可战胜，不作为普通战斗目标。

默认规则：

- `default_invincible = true`。
- `can_be_killed = false`，除非蓝图明确给出特殊击杀条件。
- 正面攻击 Boss 默认只会触发反击、推进威胁时钟或暴露玩家位置。
- 玩家可以通过削弱、封印、拖延、绕过、献祭资源、完成线索链或达成撤离条件来处理 Boss。
- Boss 的 `hp` 可以为 `null`；若为了 UI 展示需要血条，应改名为 `stability` 或 `seal_progress`，不能误导为可直接打死。

Boss 可交互结果：

| 行为 | 结算 |
| --- | --- |
| 正面攻击且无条件 | 无法造成有效伤害；威胁时钟 +1 或触发反击 |
| 找到弱点 | 临时降低一次 Boss 事件风险，或开启封印阶段 |
| 完成削弱条件 | Boss 的 mental_attack / 规则强度下降 20%-50% |
| 完成封印条件 | 进入通关/撤离/隐藏结局分支 |
| 强行拖延 | 获得 1-2 轮逃生窗口，但扣 HP/SAN/耐久 |

### 战斗结算

普通怪物和精英怪物可以进入战斗结算。Boss 默认进入规则事件结算。

命中判定：

```text
hit_score = d20 + attack_attribute_mod + tool_bonus + situational_bonus
target_dc = 10 + floor(target.speed / 2) + target_evasion_bonus
```

攻击属性：

| 攻击方式 | 主要属性 |
| --- | --- |
| 近战/重物破坏 | `str` |
| 远程/投掷/轻巧工具 | `agi` |
| 机关/术式/精准工具 | `int` |
| 规则/污染道具 | `spi_current` |

伤害结算：

```text
physical_hit_damage = max(1, physical_attack + situational_bonus - target.defense)
ranged_hit_damage = max(1, ranged_attack + situational_bonus - target.defense)
mental_hit_damage = max(1, floor(spi_current / 2) + rule_item_bonus - target.mental_resist)
```

`physical_attack` / `ranged_attack` 已经包含基础属性、能力、进化和明确道具效果加成，不能再重复叠同源 bonus。

精英怪物修正：

- 精英怪物至少有 1 条 `special_rules`。
- 精英怪物可以有阶段阈值，例如 HP <= 50% 时改变行为。
- 精英怪物击败后应给明确系统收益：关键线索、捷径、降威胁时钟、救 NPC、奖励 roll 标签。

怪物生成限制：

- 普通怪物不能拥有 Boss 级不可解机制。
- 精英怪物可以强，但必须存在至少 2 种应对方式：战斗、绕路、道具、线索、谈判或环境机制。
- Boss 可以不可战胜，但必须存在至少 2 种非击杀处理方式。
- 所有怪物特殊规则必须能被后端判定，不能只写“非常恐怖”“无法理解”。

### 蓝图规则

- 蓝图是 GM/后端内部资料，不默认完整展示给玩家。
- `mainline` 只写阶段目标和关键线索，不写逐字剧情。
- `side_quests` 必须短，每条只写钩子、解决方式和奖励标签。
- `hidden_endings` 写触发条件，不提前在公开信息中剧透。
- `clue_graph` 必须允许 fail-forward：玩家错过关键线索时，剧情要用其他方式推进，但代价更高。
- `npc_arcs` 只定义压力点和可能走向，不固定 NPC 每轮行为。
- `hard_constraints` 是防跑偏边界，GM 每轮推进前都应读取。
- 蓝图可以被后端版本化保存，归档时可选择是否导出 GM 版蓝图。

### 每轮使用方式

每轮状态缓存与 GM 输入输出边界见 `docs/wenyou/runtime_state.md`。副本蓝图和怪物生态只在副本生成时完整缓存；每轮 GM 推进时只读取相关切片。

每轮 GM 推进时，输入应包含：

```text
- 当前 public state
- 当前 gm_secret 摘要
- instance_blueprint 的相关阶段
- 最近剧情摘要
- 本轮玩家行动
- Rules Engine 上一轮 state_patch
```

GM 不应整段复述蓝图，也不应每轮输出完整任务、线索、背包或状态面板。若玩家走出蓝图预设路径，GM 可以提出扩展意图，但必须由后端校验后写入 runtime state：

- 主线仍有可达路径。
- 支线和隐藏结局的触发条件能被更新。
- 新增关键线索必须以 `state_proposals` 形式提交，由后端写回 `clue_graph`、`public_state` 或事件日志。
- 新增硬约束必须以 `state_proposals` 形式提交，由后端写回 `hard_constraints`，避免下一轮遗忘。
