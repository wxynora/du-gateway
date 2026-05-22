# 文游怪物系统

本文档从副本生成规则里拆出，专门维护怪物生成、怪物面板、普通怪/精英怪/Boss 的战斗与规避规则。

核心原则：

- 怪物不是全局固定图鉴，而是随副本蓝图生成的临时实体模板。
- 怪物服务于副本压力、路线选择、线索守门和资源消耗，不把文游变成刷怪升级。
- 普通怪可击退、规避或短暂消灭；精英怪可击败或削弱；Boss 默认不可正面战胜。
- GM 只描述怪物表现和后果，不临场发明数值。命中、伤害、状态、威胁时钟由后端规则引擎结算。
- 所有怪物特殊规则都必须能被系统判定，不能只写“不可理解”“极其恐怖”。

## 生成流程

副本生成顺序：

```text
1. 生成 instance_blueprint
2. 根据蓝图主题、时代、难度和威胁时钟生成 encounter_profile
3. 后端校验 encounter_profile 的数量、阶位、数值、弱点和 Boss 处理方式
4. GM 根据 encounter_profile 写入 public framework / gm_secret / opening
5. 副本运行中只实例化当前节点需要出现的怪物
```

`encounter_profile` 必须包含：

| 字段 | 说明 |
| --- | --- |
| `profile_version` | 怪物配置版本 |
| `instance_difficulty` | 副本难度 D/C/B/A/S |
| `theme_tags` | 副本主题标签 |
| `era_tags` | 时代标签：modern/republican/ancient/universal |
| `common` | 普通怪模板数组 |
| `elite` | 精英怪模板数组 |
| `boss` | Boss 或核心压力源 |
| `spawn_rules` | 出现条件、巡逻、追逐、威胁时钟触发 |
| `balance_notes` | 后端校验或内容包作者备注 |

## 数量与预算

怪物数量跟副本难度和主题有关。低难副本不需要塞满怪物；规则怪谈、潜伏调查、剧情解密可以怪少但规则压力高。

| 副本难度 | 普通怪模板 | 精英怪模板 | Boss | 遭遇预算 |
| --- | ---: | ---: | ---: | ---: |
| D | 2-4 | 0-1 | 1 | 5-8 |
| C | 3-5 | 1 | 1 | 8-12 |
| B | 3-6 | 1-2 | 1 | 12-18 |
| A | 4-7 | 2-3 | 1 | 18-25 |
| S | 5-8 | 3-4 | 1 | 24-32 |

预算消耗：

| 遭遇类型 | 预算 |
| --- | ---: |
| 弱普通怪/群体小怪 | 1 |
| 标准普通怪 | 2 |
| 强普通怪 | 3 |
| 精英怪 | 5 |
| 强精英怪 | 7 |
| Boss 压力源 | 不占预算，但必须绑定威胁时钟或阶段条件 |

生成限制：

- 普通怪模板数量可以多，但同一场景同时出现的普通怪预算不能超过当前副本预算的 40%。
- 精英怪不能在开场无预警压脸；第一次出现必须给提示、痕迹、传闻或绕路机会。
- Boss 可以提前显影、广播、污染、追逐或投影，但不能在玩家无操作空间时直接结算死亡。
- 每个怪物至少有 1 个弱点或规避方式；精英怪至少 2 个；Boss 至少 3 个非击杀处理方式。

## 面板字段

```json
{
  "id": "common_broadcast_listener",
  "name": "听广播的人",
  "tier": "common",
  "rank": "D",
  "role": "巡逻普通怪",
  "count_hint": "2-5",
  "hp": 35,
  "attack": 8,
  "defense": 2,
  "mental_attack": 6,
  "mental_resist": 2,
  "speed": 10,
  "detection": 10,
  "morale": 8,
  "tags": ["humanlike", "broadcast", "swarm"],
  "weaknesses": ["堵住耳朵", "切断广播"],
  "resistances": ["普通劝说"],
  "behaviors": ["patrol", "chase"],
  "special_rules": ["听见整点广播后 speed +2，持续 2 轮"],
  "counterplay": ["潜行绕开", "用噪音引走", "切断广播削弱"],
  "defeat_result": "击退 3 轮，或使威胁时钟 -1"
}
```

| 字段 | 说明 |
| --- | --- |
| `tier` | `common` / `elite` / `boss` |
| `rank` | D/C/B/A/S，决定基础面板和奖励口径 |
| `role` | 巡逻、追逐、守门、规则压力源等 |
| `count_hint` | 同时或总量出现建议，不是硬生成数 |
| `hp` | 可被普通攻击削减的稳定值；Boss 默认为 `null` |
| `attack` | HP 伤害基准 |
| `defense` | 物理防御 |
| `mental_attack` | SAN/污染/精神冲击基准 |
| `mental_resist` | 精神、规则和污染抗性 |
| `speed` | 追逐、先手、逃脱和命中修正 |
| `detection` | 发现潜行、伪装、异常行动的 DC 基准 |
| `morale` | 退缩、被威慑、被引走的抵抗值；无理智怪物可为 `null` |
| `tags` | 主题、弱点、奖励、道具互动标签 |
| `weaknesses` | 可降低难度或造成额外效果的弱点 |
| `resistances` | 抗性、免疫或减伤条件 |
| `behaviors` | 巡逻、追逐、守点、伏击、呼叫同类等 |
| `special_rules` | 系统可执行特殊机制 |
| `counterplay` | 非击杀处理方式 |
| `defeat_result` | 击败、击退、封印、绕过后的系统结果 |

## 分阶面板模板

普通怪模板：

| Rank | HP | Attack | Defense | Mental Attack | Mental Resist | Speed | Detection | Morale |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D | 12-26 | 5-9 | 0-2 | 3-7 | 0-2 | 7-12 | 8-12 | 6-10 |
| C | 22-45 | 8-14 | 1-3 | 6-12 | 1-5 | 8-14 | 10-14 | 8-12 |
| B | 38-70 | 12-20 | 2-5 | 10-18 | 3-8 | 10-17 | 12-17 | 10-15 |
| A | 65-115 | 16-27 | 5-9 | 16-28 | 6-14 | 12-22 | 14-20 | 12-18 |
| S | 120-220 | 24-38 | 9-16 | 24-40 | 10-22 | 15-26 | 18-24 | 16-22 |

精英怪模板：

| Rank | HP | Attack | Defense | Mental Attack | Mental Resist | Speed | Detection | Morale |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D | 28-55 | 8-13 | 1-3 | 6-11 | 2-6 | 8-13 | 10-14 | 9-13 |
| C | 45-85 | 12-20 | 2-5 | 10-18 | 4-10 | 10-16 | 12-16 | 11-15 |
| B | 75-130 | 18-29 | 4-8 | 17-27 | 7-16 | 12-20 | 14-19 | 13-18 |
| A | 120-210 | 26-40 | 8-14 | 26-40 | 12-24 | 15-24 | 17-23 | 16-22 |
| S | 220-360 | 40-58 | 14-24 | 38-56 | 20-38 | 18-30 | 20-28 | 20-28 |

Boss 压力源模板：

| Rank | HP | Stability / Seal Progress | Attack | Defense | Mental Attack | Mental Resist | Threat Clock |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D | `null` | 2-3 | 0-12 | 999 | 10-18 | 999 | 4-5 |
| C | `null` | 3-4 | 0-18 | 999 | 16-26 | 999 | 5-6 |
| B | `null` | 4-5 | 0-26 | 999 | 24-36 | 999 | 6-7 |
| A | `null` | 5-6 | 0-36 | 999 | 34-50 | 999 | 7-8 |
| S | `null` | 6-8 | 0-50 | 999 | 48-70 | 999 | 8-10 |

说明：

- Boss 的 `defense/mental_resist = 999` 表示不能用普通伤害硬打，不表示真实数值。
- 如果 Boss 可被特殊击杀，必须写 `can_be_killed=true`、击杀条件、失败后果和隐藏结局影响。
- UI 不应给 Boss 显示普通血条；应显示 `威胁时钟`、`封印进度`、`稳定度` 或 `规则破绽`。

## 战斗与规避结算

玩家攻击普通怪/精英怪：

```text
hit_score = d20 + attack_attribute_mod + tool_bonus + situational_bonus + weakness_bonus
target_dc = 10 + floor(monster.speed / 2) + monster_evasion_bonus

physical_damage = max(1, player.physical_attack + weakness_damage - monster.defense)
ranged_damage = max(1, player.ranged_attack + weakness_damage - monster.defense)
mental_damage = max(1, floor(player.spi_current / 2) + rule_item_bonus + weakness_damage - monster.mental_resist)
```

`physical_attack` 和 `ranged_attack` 已经包含基础属性、能力、进化和明确道具效果加成，不能再重复叠一次同源 bonus。

怪物攻击玩家：

```text
monster_hit_score = d20 + floor(monster.attack / 4) + situational_bonus
player_dc = 10 + floor(player.agi / 2) + cover_bonus + item_bonus

hp_damage = max(1, monster.attack - player.defense - item_mitigation)
san_damage = max(1, monster.mental_attack - player.mental_resist - item_mitigation)
```

规避/潜行/谈判：

```text
avoid_score = d20 + relevant_attribute_mod + item_bonus + clue_bonus + situational_bonus
avoid_dc = monster.detection + alert_level + threat_clock_modifier
```

| 行动 | 常用属性 | 成功 | 失败 |
| --- | --- | --- | --- |
| 潜行绕开 | `agi` | 跳过遭遇或获得先手 | 暴露 +1，怪物先手 |
| 伪装通过 | `int` / `luk` | 暂时不触发战斗 | 暴露 +1，身份系统标记 |
| 威慑逼退 | `str` / `spi_current` | 怪物退避 1-2 轮 | 怪物攻击，或呼叫同类 |
| 线索削弱 | `int` | 触发弱点或降低特殊规则 | 线索失效或威胁时钟 +1 |
| 道具解法 | 道具规则 | 按道具效果结算 | 扣次数/耐久，可能额外代价 |

战斗结果：

| 结果 | 普通怪 | 精英怪 |
| --- | --- | --- |
| 击败 | 离场或 3-5 轮不再出现 | 掉落关键线索、打开捷径、降低威胁时钟或奖励标签 |
| 击退 | 1-3 轮不追击 | 阶段性后撤，但会改变路线或提高警戒 |
| 规避 | 不消耗 HP/SAN，可能错过掉落 | 可绕过守门，但可能失去捷径/支线奖励 |
| 失败 | 造成 HP/SAN/状态损失 | 造成高额损失、封路、威胁时钟 +1 |

### 遭遇状态机与逃跑

怪物遭遇不必每次进入完整回合制战斗。后端按当前怪物状态、玩家行动和场景压力决定本轮是一次风险判定、追逐、短战斗还是 Boss 事件。

遭遇状态：

| 状态 | 说明 | 玩家常见选择 |
| --- | --- | --- |
| `unaware` | 怪物未察觉玩家 | 潜行、绕路、观察、设陷阱 |
| `suspicious` | 怪物怀疑或接近 | 伪装、谈判、躲藏、使用道具 |
| `alerted` | 怪物确认异常 | 逃跑、威慑、攻击、制造干扰 |
| `chasing` | 已进入追逐 | 逃跑、封门、牺牲道具、分散 |
| `engaged` | 已短兵相接或被规则锁定 | 攻击、防御、道具解法、强行脱离 |
| `retreated` | 怪物暂时退避 | 推进任务、撤离、封锁路线 |
| `sealed` | 被封印或满足处理条件 | 写入任务/结局/奖励标记 |

玩家输入“我逃跑成功了”时，后端只识别为 `action_type=flee`。是否成功由逃跑判定决定：

```text
flee_score = d20 + floor(player.agi / 2) + route_bonus + item_bonus + distraction_bonus
flee_dc = monster.detection + floor(monster.speed / 2) + alert_level + threat_clock_modifier
```

逃跑修正：

| 条件 | 修正 |
| --- | ---: |
| 已知安全出口、提前踩点 | `route_bonus +2` |
| 使用合适道具 | `item_bonus +1` 到 `+5` |
| 有队友掩护或制造干扰 | `distraction_bonus +2` |
| 负重过高、重伤、疲劳 | `-2` 到 `-5` |
| 正被 Boss 规则锁定 | `flee_dc +5`，且成功也可能只争取 1 轮 |
| 违反副本核心禁令后逃跑 | `threat_clock_modifier +2` |

逃跑结果：

| 结果 | 状态变化 | 代价 |
| --- | --- | --- |
| 大成功 `score >= dc + 5` | 玩家移动到安全相邻节点，怪物 `retreated` 或丢失目标 | 通常无额外代价 |
| 成功 `score >= dc` | 玩家脱离当前遭遇，怪物进入 `alerted` 或 `chasing` 延迟状态 | 可能扣少量耐久或留下痕迹 |
| 部分成功 `score >= dc - 5` | 玩家离开原地，但怪物追逐继续或路线被封 | 威胁时钟 +1、掉落物资、HP/SAN 小损耗三选一 |
| 失败 | 怪物先手、堵路或进入 `engaged` | 结算一次怪物攻击或状态损失 |

回合处理建议：

- 普通怪可以用“一轮行动 + 一次反应”处理，不强制写完整战斗轮。
- 精英怪若进入战斗，默认每轮包含玩家行动、怪物反应、状态 tick 和威胁检查。
- 多怪场景优先抽象成群体压力，不逐个怪物滚一遍，避免文游节奏被战斗拖死。
- Boss 事件默认不走普通命中/伤害轮，而走封印进度、弱点触发、威胁时钟和撤离窗口。

## Boss 规则

Boss 是副本核心压力源，不是普通战斗目标。

默认字段：

```json
{
  "tier": "boss",
  "hp": null,
  "default_invincible": true,
  "can_be_killed": false,
  "stability": 5,
  "seal_progress": 0,
  "counterplay": ["削弱", "封印", "规避", "撤离"],
  "weaken_conditions": [],
  "seal_conditions": [],
  "escape_conditions": [],
  "at_max_clock": "进入强制清算"
}
```

Boss 处理方式：

| 方式 | 系统效果 |
| --- | --- |
| 识破弱点 | 下一次 Boss 事件风险 -1 级，或封印进度 +1 |
| 完成削弱 | `mental_attack` 或规则强度下降 20%-50% |
| 完成封印 | 进入通关、隐藏结局或安全撤离分支 |
| 规避/拖延 | 获得 1-2 轮行动窗口，消耗 HP/SAN/耐久/线索 |
| 强行攻击 | 默认无效；威胁时钟 +1 或触发反击 |

Boss 必须满足：

- 至少 3 条非击杀处理方式。
- 至少 1 条处理方式来自线索链。
- 至少 1 条处理方式来自行动或道具。
- 至少 1 条失败推进规则，防止玩家卡死。
- 如果存在特殊击杀，必须是隐藏路线或高代价路线，不能成为默认最优解。

## 弱点、抗性与标签

怪物弱点不是纯叙事词，必须落到系统效果。

| 弱点类型 | 系统效果示例 |
| --- | --- |
| 物理弱点 | 伤害 +30%-50%，或 defense -2/-5/-10 |
| 精神弱点 | mental_resist -2/-5/-10，或 SAN 代价降低 |
| 环境弱点 | 特定节点中 speed -2，attack -20%，或失去特殊规则 |
| 线索弱点 | 获得线索后 `weakness_bonus +2/+4/+6` |
| 道具弱点 | 指定 tag 道具额外 +2 到 +6，或直接封印一条低级规则 |
| 社交弱点 | 伪装、称呼、身份凭证让 detection -2 到 -6 |

抗性也必须可判定：

| 抗性 | 系统写法 |
| --- | --- |
| 物理抗性 | `physical_damage_multiplier=0.5` 或 `defense +N` |
| 精神抗性 | `mental_damage_multiplier=0.5` 或 `mental_resist +N` |
| 免疫 | 仅允许低阶普通怪/特定条件；必须提供替代解法 |
| 规则护盾 | 未满足条件前伤害上限为 1 或伤害 -50% |

## 生成提示词

```text
你要为一个无限流文字副本生成怪物生态 encounter_profile。

输入：
- 副本难度：{D/C/B/A/S}
- 副本时代：{modern/republican/ancient/universal}
- 副本主题标签：{tags}
- instance_blueprint 摘要：{blueprint_summary}

输出 JSON，不要写散文解释。

必须包含：
- profile_version
- instance_difficulty
- theme_tags
- era_tags
- common: 2-8 个普通怪模板
- elite: 0-4 个精英怪模板
- boss: 1 个 Boss / 核心压力源
- spawn_rules
- balance_notes

每个普通怪/精英怪必须写：
id/name/tier/rank/role/count_hint/hp/attack/defense/mental_attack/mental_resist/speed/detection/morale/tags/weaknesses/resistances/behaviors/special_rules/counterplay/defeat_result

Boss 必须写：
id/name/tier/rank/role/hp/default_invincible/can_be_killed/stability/seal_progress/mental_attack/threat_clock/tags/counterplay/weaken_conditions/seal_conditions/escape_conditions/at_max_clock

平衡要求：
- 普通怪可以被击退、规避或短暂消灭。
- 精英怪至少有 2 种应对方式。
- Boss 默认不可正面战胜，至少有 3 种非击杀处理方式。
- 所有 special_rules 必须系统可判定，禁止只写气氛词。
- 面板数值必须符合 docs/wenyou/monster_system.md 的分阶模板。
- D 级副本不能生成 A/S 普通怪或精英怪；C 级副本不能生成 S 精英怪。
- Boss 可以高一阶，但必须通过威胁时钟、封印进度或规则弱点处理，不能要求玩家硬打。
```

## 平衡目标

默认模拟目标：

| 遭遇 | 同阶普通成长玩家目标 |
| --- | --- |
| 普通怪 1v1 | D/C 普通怪 2-5 次成功攻击可击退或击败；B/A 普通怪 3-6 次成功攻击可击退或击败；失败成本约 HP/SAN 5%-20% |
| 普通怪群体 | 不鼓励硬打；应通过道具、潜行、地形、威慑或线索拆分 |
| 精英怪 | 4-8 次成功行动解决；至少需要 1 个弱点、道具或环境配合 |
| 强精英怪 | 单人硬打高风险；队友协作或线索削弱后可解 |
| Boss | 不进入 TTK 平衡；看封印进度、威胁时钟和撤离窗口 |

调参规则：

- 普通怪过硬：优先降 defense / mental_resist，不要只降 HP。
- 普通怪太弱：优先增加 detection、群体协作或场景风险，不要堆 HP。
- 精英怪太硬：增加弱点效果、降低阶段护盾、给捷径或道具解法。
- 精英怪太弱：增加阶段规则或失败代价，不要变成 Boss 级不可解。
- Boss 太压迫：增加威胁时钟上限、增加封印进度来源或降低事件频率。
- Boss 太弱：提高失败代价或隐藏结局门槛，不要改成可硬杀血条。
