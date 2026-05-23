# 文游数值、成长与结算判定

## 核心数值

默认固定使用六项基础属性。攻击、防御、精神抗性、负重等不作为自由加点属性，而是由基础属性、当前状态、阶位、背包道具和核心能力派生。遭遇不设置独立行动顺序值，由剧情态势决定是否先结算威胁，默认给玩家一个行动窗口。

| 字段 | 含义 |
| --- | --- |
| `hp` | 生命值，归零进入濒死或死亡判定 |
| `san` | 精神值，归零进入失控、污染或强制判定 |
| `str` | 力量，影响近战攻击、破坏、负重、重武器门槛 |
| `con` | 体力，影响 HP 上限、抗伤、耐力、毒/病/饥寒抵抗 |
| `agi` | 敏捷，影响闪避、追逐、潜行、远程/轻武器 |
| `int` | 智力，影响观察、推理、机关、线索解析、技术工具 |
| `spi` | 精神力基础值，可加点；影响精神抗性、污染承受、规则武器、精神类能力 |
| `luk` | 幸运，影响副本内随机事件、隐藏支线发现、掉落加权、险境小概率修正；不影响付费抽卡概率和保底 |
| `spi_current` | 当前精神力，会随 SAN 损失和污染武器消耗而下降 |
| `spi_max` | 当前精神力上限，由 `spi`、阶位、道具和状态修正得到 |
| `level` | 等级，长期成长 |
| `rank` | 阶位，D/C/B/A/S |
| `exp` | 经验 |
| `points` | 主神积分 |
| `core_ability` | 核心能力，新手副本通关前为 `null`，通关后由后端按表现生成 |
| `core_ability_profile` | 核心能力生成画像，记录新手副本行为倾向分数、选中原型和生成来源 |
| `conditions` | 状态效果 |
| `inventory` | 背包 |

派生数值：

| 派生值 | 公式 | 用途 |
| --- | --- | --- |
| `physical_attack` | `floor(str / 2) + core_ability_attack + item_attack_bonus` | 近战、破坏、物理压制 |
| `ranged_attack` | `floor((agi + int) / 4) + core_ability_attack + item_attack_bonus` | 远程、投掷、精准射击 |
| `defense` | `floor(con / 3) + rank_physical_reduction + item_defense_bonus` | 抵消 HP 伤害 |
| `mental_resist` | `floor(spi_current / 3) + item_mental_resist + rank_mental_reduction` | 抵消 SAN 伤害和污染 |
| `carry_limit` | `str + floor(con / 2) + item_carry_bonus` | 负重、重物搬运、携带限制 |
| `spi_max` | `spi + rank_spi_bonus + item_spi_bonus + condition_spi_max_delta` | 当前精神力上限 |
| `spi_current` | 状态值，默认不超过 `spi_max` | 当前精神力资源 |

说明：

- `精神力 spi` 是可加点的长期基础属性。
- `当前精神力 spi_current` 是消耗性状态值；SAN 下降、污染冲击、规则道具使用会消耗它。
- `spi_current` 下降不会永久降低 `spi`，但会让精神抗性、规则道具门槛和精神类能力临时变弱。
- `SAN san` 是当前精神值，会随着惊吓、污染、能力和道具代价上下波动。
- `SAN 上限 san_max` 主要由智力、等级和阶位影响。
- `智力 int` 负责理解、观察和解谜，不等于精神力。
- `幸运 luk` 只影响副本内随机、隐藏支线发现和结算掉落小幅加权；不影响付费抽卡基础概率、十连保底、100 抽大保底、卡池权重和抽卡价格。
- 后端抽卡接口不能读取 `luk`、幸运增益或幸运状态作为概率参数；避免玩家为了抽卡被迫堆幸运。
- `str/con/agi/int/spi/luk` 是基础固定值，只会因属性点、永久道具或明确状态修正变化；普通 SAN 波动只消耗 `spi_current`，不会改基础 `spi`。

### 初始数值

默认新人：

```json
{
  "level": 1,
  "rank": "D",
  "exp": 0,
  "str": 10,
  "con": 10,
  "agi": 10,
  "int": 10,
  "spi": 10,
  "luk": 10,
  "hp": 180,
  "hp_max": 180,
  "san": 180,
  "san_max": 180,
  "spi_current": 10,
  "spi_max": 10,
  "points": 100,
  "core_ability": null,
  "core_ability_profile": null,
  "conditions": [],
  "inventory": []
}
```

### 上限公式

```text
hp_max = 80 + con * 10 + (level - 1) * 6 + rank_hp_bonus
san_max = 120 + int * 6 + (level - 1) * 6 + rank_san_bonus
spi_max = spi + rank_spi_bonus + item_spi_bonus + condition_spi_max_delta
spi_current = min(spi_current, spi_max)
```

SAN 与当前精神力联动：

```text
if san_delta < 0:
  spi_current -= max(1, ceil(abs(san_delta) / 25))

if san_delta > 0 and effect_tags contains "mental_recovery":
  spi_current += ceil(san_delta / 30)

spi_current = clamp(spi_current, 0, spi_max)
```

说明：

- 常规惊吓、污染、精神攻击导致 SAN 下降时，都会消耗当前精神力。
- 普通 SAN 回复只恢复 SAN；只有带 `mental_recovery`、休整、结算治疗或专门道具，才恢复 `spi_current`。
- `spi_current = 0` 时，精神类判定额外 -3，污染武器和高阶规则道具默认不可用。

阶位基础加成：

| 阶位 | HP 加成 | SAN 加成 | 精神力上限加成 | 物理减伤 | 精神减伤 | 属性软上限 | 属性硬上限 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D | 0 | 0 | 0 | 0 | 0 | 14 | 16 |
| C | 20 | 20 | 2 | 2 | 2 | 18 | 22 |
| B | 45 | 45 | 5 | 5 | 5 | 24 | 30 |
| A | 80 | 80 | 9 | 9 | 9 | 32 | 40 |
| S | 130 | 130 | 15 | 15 | 15 | 42 | 50 |

说明：

- 体力变化后，后端立刻重算 HP 上限。
- 智力变化后，后端立刻重算 SAN 上限。
- 精神力基础值、阶位、道具或状态变化后，后端立刻重算 `spi_max`。
- SAN 当前值下降后，后端按上方公式扣 `spi_current`。
- 当前 HP/SAN 不因上限提升自动回满，只增加上限。
- 如果上限下降，当前值不能超过新上限。

## 行动与判定

玩家可以自由输入行动，不强制选按钮。

每轮流程：

```text
1. 玩家提交行动
2. 后端归类 action_type，处理确定性 pre-rule
3. GM 输出叙事草稿和事件意图 event_intent
4. Rules Engine 根据 ruleset 计算数值
5. 后端写入 state_patch
6. GM 或模板根据 state_patch 写叙事反馈
```

GM 只能提出事件意图，不直接写精确数值：

```json
{
  "event": "trap_triggered",
  "risk": "dangerous",
  "targets": ["player1"],
  "tags": ["mental", "rule_pollution"],
  "fiction": "玩家直视了告示背后的第二行字。"
}
```

规则引擎输出：

```json
{
  "hp_delta": 0,
  "san_delta": -22,
  "conditions_add": ["轻度规则污染"],
  "clock_updates": [{ "id": "harbor_broadcast", "delta": 1 }]
}
```

### 事件风险等级

| 风险 | 基础 HP 伤害 | 基础 SAN 伤害 | 示例 |
| --- | ---: | ---: | --- |
| `safe` | 0 | 0 | 正常观察、普通交谈 |
| `minor` | 5 | 4 | 小擦伤、轻微惊吓 |
| `risky` | 12 | 10 | 危险搜索、接触异常 |
| `dangerous` | 25 | 22 | 触发陷阱、被污染凝视 |
| `desperate` | 45 | 40 | 强行突破、硬抗规则 |
| `lethal` | 80 | 70 | 致命攻击、直接违背核心禁令 |

副本难度倍率：

| 难度 | 倍率 |
| --- | ---: |
| D | 0.75 |
| C | 1.00 |
| B | 1.35 |
| A | 1.75 |
| S | 2.25 |

最终伤害：

```text
physical_damage = ceil(base_hp_damage * difficulty_multiplier * action_modifier) - defense
mental_damage = ceil(base_san_damage * difficulty_multiplier * action_modifier) - mental_resist
```

`action_modifier`：

| 行动状态 | 修正 |
| --- | ---: |
| 有准备、有工具、有队友掩护 | 0.70 |
| 普通行动 | 1.00 |
| 冒进、信息不足、赶时间 | 1.30 |
| 明知规则危险仍强行做 | 1.60 |

规则：

- 如果事件命中，最终伤害最低为 1，除非被道具、能力或规则完全抵消。
- `physical` 标签只结算 HP。
- `mental`、`rule_pollution`、`memory` 标签优先结算 SAN。
- `mixed` 标签同时结算 HP 与 SAN，但各取 60%。
- GM 不能因为叙事喜欢就随意改这些数值。

### 可选骰子规则

如果项目需要随机判定，可启用 `d20`：

```text
score = d20 + attribute_mod + item_bonus + ability_bonus
attribute_mod = floor((相关属性 - 10) / 2)
```

默认 DC：

| 难度 | 基础 DC |
| --- | ---: |
| D | 8 |
| C | 11 |
| B | 14 |
| A | 17 |
| S | 20 |

风险 DC 修正：

| 风险 | DC 修正 |
| --- | ---: |
| safe | -2 |
| minor | 0 |
| risky | +2 |
| dangerous | +4 |
| desperate | +7 |
| lethal | +10 |

结果：

| 结果 | 条件 | 效果 |
| --- | --- | --- |
| 成功 | `score >= DC + 5` | 达成目标，通常无额外代价 |
| 成功但有代价 | `score >= DC` | 达成目标，付出小代价 |
| 部分成功 | `score >= DC - 5` | 获得信息或推进，但威胁上升 |
| 失败但推进 | `score < DC - 5` | 目标失败，同时触发后果或新线索 |

失败不能等于“什么都没发生”。失败必须推进剧情、威胁、时限、NPC 关系或线索状态。

自由文本声明不改变判定结果。玩家可以写“我成功翻墙逃掉”，但后端只把它归类为 `move`、`evade` 或 `flee` 意图；成功、部分成功或失败仍由 DC、属性、道具、场景和怪物状态决定。

## 状态效果

### HP 阈值

| 条件 | 状态 | 效果 |
| --- | --- | --- |
| HP <= 50% | 轻伤 | physical 行动判定 -1 |
| HP <= 25% | 重伤 | physical 行动判定 -3，行动风险上调一级 |
| HP = 0 | 濒死 | 开启 3 tick 死亡倒计时 |

### SAN 阈值

| 条件 | 状态 | 效果 |
| --- | --- | --- |
| SAN <= 50% | 动摇 | mental / insight 判定 -1 |
| SAN <= 25% | 污染 | mental 判定 -3，规则怪谈类副本更易触发假线索 |
| SAN = 0 | 失控 | GM 可触发强制事件，但不能永久夺取玩家控制权 |

### 通用状态结构

状态效果需要能被后端直接结算，不能只写气氛描述。

| 字段 | 说明 |
| --- | --- |
| `id` | 状态唯一标识 |
| `type` | 伤势、精神、污染、疲劳、暴露、封印、增益、债务/契约 |
| `severity` | 严重度 1-3，对应轻微/中等/严重 |
| `stacks` | 层数，默认 1，普通状态建议最多 3 层 |
| `duration` | 持续轮数、副本数，或 `until_cleared` |
| `source` | 来源：怪物、道具、能力、规则、结算、惩罚副本 |
| `effects` | 系统可执行效果，如判定修正、伤害修正、行动限制 |
| `clear_condition` | 清除条件，如治疗、休息、结算、指定道具、完成目标 |

`DC` 是一次行动的目标难度值。比如撬门基础 `DC=12`，玩家投骰/判定结果达到 12 才成功；若有 `疲劳 2 层`，该行动变成 `DC=14`。它不是给玩家扣属性，而是让这一次行动更难成功。

常用状态：

| 状态 | 类型 | 层数/持续 | 效果 | 清除 |
| --- | --- | --- | --- | --- |
| 疲劳 | 疲劳 | 1-3 层 | 每层行动 DC +1；3 层时长距离追逐和连续战斗额外风险 +1 | 安全休息清 1 层，结算清空 |
| 暴露 | 暴露 | 1-3 层 | 每层潜行/伪装 -1；怪物或阵营锁定优先级上升 | 换装、伪造身份、离开区域 |
| 复活疲惫 | 伤势/精神 | 1 副本或 3 轮高压场景 | physical 和 mental 判定 -1，不能触发无复活成就 | 完成副本或安全休整 |
| 轻度污染 | 污染 | 1-3 层 | mental 判定 -1；规则类道具代价 +1 SAN | 净化道具、结算治疗、污染副本 |
| 能力封印 | 封印 | until_cleared | 指定能力不可用，或只保留低阶效果 | 晋升、契约清算、指定道具 |

### 死亡倒计时

```text
濒死后 death_clock = 3
每经过一轮未被救治，death_clock - 1
death_clock = 0 时死亡
```

立即死亡只允许出现在：

- `lethal` 风险事件且 HP 归零。
- 玩家明确选择自毁、献祭、直面必死规则。
- 副本公开规则已经明示必死后果，且玩家仍触发。

## 复活

复活消耗主神积分或指定复活道具。

默认死亡策略：

- 不永久删档，不默认报废角色。
- 死亡会转化为复活成本、债务、污染、道具损坏或强制惩罚副本。
- 如果内容包要启用永久死亡，必须作为显式高难规则写进副本公开规则，不能暗中触发。

复活价格：

```text
revive_cost = rank_base_cost + level * 50 + death_count * 200
```

| 阶位 | 基础复活价格 |
| --- | ---: |
| D | 200 |
| C | 500 |
| B | 1200 |
| A | 2600 |
| S | 6000 |

复活后：

- HP = floor(hp_max * 0.5)
- SAN = floor(san_max * 0.5)
- 添加状态 `复活疲惫`，持续 1 个副本或 3 轮高压场景。
- 同一副本每复活一次，`death_count + 1`。
- 积分不足时，默认写入 `debts`；内容包也可以提供 `契约复活` 或 `道具复活`，但必须写入状态和代价。

死亡到债务的完整流程：

```text
on_player_death(state, player_id):
  mark player.status = "dead"
  death_count += 1
  if instance_can_continue_without_player:
    keep player as dead until settlement
  else:
    trigger team failure or forced evacuation

settle_death(state, player_id):
  revive_cost = rank_base_cost + level * 50 + death_count * 200
  available = points
  paid = min(available, revive_cost)
  points -= paid
  debts += revive_cost - paid
  hp = floor(hp_max * 0.5)
  san = floor(san_max * 0.5)
  add_condition("复活疲惫")
```

债务规则：

- 债务不让 `points` 变成负数，统一写入 `debts`。
- 后续通关结算时，先从 `gross_points` 偿还债务，再把剩余积分发给玩家。
- 默认每次结算最多偿还本次 `gross_points` 的 80%；剩余 20% 仍给玩家，避免失败后完全无法恢复。
- 如果 `debts >= 1000`，候选副本池必须插入债务催收副本。
- 如果 `debts >= 3000`，下一次候选必须至少出现 1 个高压债务清算副本，且不能晋升。

债务偿还流程：

```text
repay_debt_on_settlement(gross_points, debts):
  repay_cap = floor(gross_points * 0.8)
  repay = min(repay_cap, debts)
  debts -= repay
  final_points_before_penalty = gross_points - repay
```

惩罚副本接入：

- 惩罚副本不是新剧情常驻线，只是候选池强制插队。
- 触发条件写入 `forced_instance_queue`。
- 玩家选择普通副本前，后端先检查 `forced_instance_queue`。
- 惩罚副本通关奖励优先还债、清污染或解除契约；失败会追加债务或封印。

## 成长系统

长期成长保留 4 条主线，后端分别结算，不能让 GM 文本直接改数值：

| 成长线 | 来源 | 主要产出 | 主要消耗 |
| --- | --- | --- | --- |
| 等级 | 通关 EXP、低完成逃生少量 EXP | 自由属性点、HP/SAN 上限随等级上升 | 时间和副本风险 |
| 阶位 | 等级、通关记录、积分 | 属性上限、阶位减伤、物品封印解锁 | 晋升积分、特殊试炼 |
| 属性 | 升级、新手礼包、极少量永久药剂 | `str/con/agi/int/spi/luk` 和派生数值 | 自由属性点 |
| 核心能力 | 新手副本通关表现、角色特质、后续内容包事件 | 一个可主动使用的核心能力，可随阶位或剧情变形 | 每副本次数、阶位封印、代价 |

### 经验需求

默认等级上限为 Lv30。EXP 是长期成长速度阀门，早期要让玩家 3-5 次标准通关摸到 C 阶，中后期逐渐放慢。

| 当前等级 | 升到下一级 EXP | 推荐主要副本 |
| ---: | ---: | --- |
| 1 | 40 | 新手/D |
| 2 | 70 | D |
| 3 | 110 | D/C |
| 4 | 150 | C |
| 5 | 200 | C |
| 6 | 260 | C/B |
| 7 | 340 | B |
| 8 | 440 | B |
| 9 | 560 | B |
| 10 | 720 | B/A |
| 11 | 900 | A |
| 12 | 1100 | A |
| 13 | 1320 | A |
| 14 | 1560 | A |
| 15 | 1820 | A/S |
| 16 | 2100 | S |
| 17 | 2400 | S |
| 18 | 2730 | S |
| 19 | 3090 | S |
| 20 | 3480 | S |
| 21 | 3900 | S |
| 22 | 4350 | S |
| 23 | 4830 | S |
| 24 | 5340 | S |
| 25 | 5880 | S |
| 26 | 6450 | S |
| 27 | 7050 | S |
| 28 | 7680 | S |
| 29 | 8340 | S |

升级时循环扣除经验：

```text
while exp >= next_level_exp[level] and level < 30:
  exp -= next_level_exp[level]
  level += 1
  unspent_attribute_points += 2
```

每升 1 级：

- 获得 2 点自由属性点，可加 `str/con/agi/int/spi/luk`。
- 按公式重算 HP/SAN 上限。
- 当前 HP/SAN 不自动回满。
- 升级不再发能力点或成长令牌；核心能力不从抽卡/商店购买，默认只由新手副本表现生成，后续强化由内容包明确结算。

### 新手副本礼包

玩家首次通关新手副本后，系统发放 `newbie_starter_pack`。

| 内容 | 数值 | 说明 |
| --- | ---: | --- |
| 自由属性点 | 6 | 可以把一个 D 阶属性从 10 点拉到软上限 14，并剩 2 点补短板 |
| 低级治疗道具 | 2 | 从 D 级增益类道具池抽，不进普通抽卡保底 |

礼包规则：

- `tutorial_attribute_gift_points = 6`。
- 新手礼包只发一次，按账号/角色记录。
- 新手礼包不发抽卡券，避免开局被抽卡节奏绑架。
- 若新手副本失败，只保留教学记录，不发完整礼包；重新通过后再发。

### 属性点分配流程

属性点分配是固定规则，不交给 GM 文本自由发挥。

开放阶段：

- `hub`
- `settlement`
- 副本内明确标记为安全的休整节点

默认不允许在追逐、战斗、坠落、污染爆发、死亡倒计时中加点。

基础属性上限：

| 阶位 | 普通加点软上限 | 特殊成长硬上限 |
| --- | ---: | ---: |
| D | 14 | 16 |
| C | 18 | 22 |
| B | 24 | 30 |
| A | 32 | 40 |
| S | 42 | 50 |

规则：

- 每消耗 1 点自由属性点，选择 `str/con/agi/int/spi/luk` 任一基础属性 +1。
- `con +1` 立刻让 `hp_max +10`。
- `int +1` 立刻让 `san_max +6`，并通过 SAN 上限影响当前精神力计算。
- `spi +1` 立刻让 `spi_max +1`；如果当前处于安全阶段，可同时让 `spi_current +1`，但不能超过 `spi_max`。
- `str/agi/luk +1` 不直接恢复 HP/SAN，只影响对应判定和派生值。
- 当前 HP/SAN 不随上限自动补满，除非使用治疗、结算奖励或专门道具。
- 超过当前阶位软上限时，普通加点按钮不可用；只能通过阶位晋升、特殊道具或内容包显式突破。
- 任何属性都不能超过当前阶位硬上限；硬上限只防止异常堆叠失控，不代表普通玩家应该轻易摸到。
- 永久属性药剂默认每个阶位最多生效 2 次，且只能把属性推到硬上限以内。
- 默认先不提供常驻属性重置；以后如果加重置，只返还自由属性点，不返还属性药剂或特殊物提供的永久点。

推荐 UI：

| UI 元素 | 行为 |
| --- | --- |
| 未分配点数 | 展示 `unspent_attribute_points` |
| 六基础属性行 | 展示 `str/con/agi/int/spi/luk` 当前值、软上限、`-`、`+` |
| 当前精神力行 | 展示 `spi_current/spi_max`、SAN 损耗、恢复来源 |
| 派生预览 | 展示 HP/SAN 上限、攻击、防御、精神抗性、负重、当前精神力上限变化 |
| 确认按钮 | 一次提交所有待分配点 |
| 重置待分配按钮 | 只撤销本次 UI 暂存，不影响已保存属性 |

后端流程：

```text
allocate_attribute_points(state, player_id, deltas):
  assert phase in ["hub", "settlement"] or safe_rest_node == true
  assert all(delta >= 0 for delta in deltas.values())
  assert keys(deltas) subset ["str", "con", "agi", "int", "spi", "luk"]
  assert sum(deltas.values()) <= unspent_attribute_points
  assert all(attribute + delta <= rank_soft_cap[rank])

  apply deltas to attributes
  unspent_attribute_points -= sum(deltas.values())
  hp_max = calc_hp_max(...)
  san_max = calc_san_max(...)
  spi_max = calc_spi_max(...)
  if deltas.get("spi", 0) > 0 and safe_rest_node_or_hub:
    spi_current = min(spi_max, spi_current + deltas["spi"])
  else:
    spi_current = min(spi_current, spi_max)
  derived = calc_derived_stats(...)
  hp = min(hp, hp_max)
  san = min(san, san_max)
```

### 阶位提升

| 晋升 | 等级要求 | 副本评价要求 | 积分成本 |
| --- | ---: | --- | ---: |
| D -> C | Lv3 | D 难度 A/S 评级，或 C 难度标准通关 | 200 |
| C -> B | Lv6 | C 难度 A/S 评级，或 B 难度标准通关 | 500 |
| B -> A | Lv10 | B 难度 A/S 评级，或 A 难度标准通关 | 1000 |
| A -> S | Lv15 | A 难度 S 评级 + 特殊试炼，或 S 难度标准通关 | 2000 |

阶位提升后：

- 立刻应用阶位加成。
- 解锁对应阶位的高阶物品使用权限和封印效果。
- 普通商店仍是唯一系统商店；阶位越高，越级物品出现概率越高，但不足阶位时继续封印或降级生效。
- 如果已有高阶封印物品，按新阶位解锁对应效果。
- 晋升本身不额外发属性点；阶位已经提供上限、减伤和解封能力。

晋升检查：

```text
promote_rank(state, player_id, target_rank):
  assert target_rank == next_rank(current_rank)
  assert level >= required_level[target_rank]
  assert has_required_clear_record(target_rank)
  assert points >= promotion_cost[target_rank]
  assert not has_blocking_forced_instance(player_id)

  points -= promotion_cost[target_rank]
  rank = target_rank
  hp_max = calc_hp_max(...)
  san_max = calc_san_max(...)
  unlock_sealed_effects(up_to=target_rank)
```

阻断条件：

- `debts >= 3000` 时不能晋升，必须先完成债务清算或还到 3000 以下。
- `pollution >= 90` 时不能晋升，必须先完成污染清算。
- A -> S 必须完成一次 `special_trial`，该试炼可以是强制惩罚副本，也可以是内容包指定的晋升副本。
- 角色可以挑战高一阶副本，但奖励、死亡成本和污染风险按实际副本难度结算。
- 如果角色等级已达标但积分不足，可以继续刷同阶副本；不得免费晋升。

推荐 UI：

| UI 元素 | 行为 |
| --- | --- |
| 当前阶位 | 展示当前 rank、下一阶位和解锁内容 |
| 条件列表 | 等级、通关记录、积分、债务/污染阻断逐项打勾 |
| 晋升预览 | 展示 HP/SAN 上限变化和封印解除 |
| 确认晋升 | 扣积分并写入 `state_patch` |

### 成长节奏

默认希望普通玩家按这个节奏推进；不是硬锁，但用于平衡奖励、死亡成本和副本难度。

| 阶段 | 推荐等级 | 推荐属性区间 | 推荐副本 | 目标节奏 |
| --- | --- | --- | --- | --- |
| 新手/D 初期 | Lv1-2 | 10-14 | 新手/D | 1-3 次通关熟悉规则，拿到新手礼包 |
| D -> C | Lv3-4 | 12-14 | D/C | 第 3-5 次有效通关可晋升 C |
| C 成长期 | Lv4-6 | 14-18 | C | 开始形成属性倾向和核心能力使用习惯 |
| C -> B | Lv6-8 | 16-20 | C/B | 第 8-12 次有效通关可晋升 B |
| B 成长期 | Lv8-10 | 18-24 | B | 核心能力、背包道具和副本规则开始决定打法 |
| B -> A | Lv10-13 | 22-28 | B/A | 第 16-24 次有效通关可晋升 A |
| A 成长期 | Lv13-15 | 26-34 | A | 高阶副本开始要求队伍分工和资源规划 |
| A -> S | Lv15+ | 30+ | A/S | 需要特殊试炼，不能只靠刷经验 |

### 成长平衡验收指标

后端或内容包调整奖励、死亡率、抽卡消耗后，应跑一次模拟。默认目标：

| 指标 | 目标 |
| --- | --- |
| D -> C | 平均 3-5 次有效通关，或 5-7 次普通尝试 |
| C -> B | 平均 8-12 次有效通关，或 12-16 次普通尝试 |
| B -> A | 平均 16-24 次有效通关，或 26-34 次普通尝试 |
| A -> S | Lv15 后进入特殊试炼节奏，不靠经验自动毕业 |
| 40 次普通尝试后 | 大多数活跃角色应在 B/A，少量高玩可准备 S 试炼 |
| 抽卡消耗 | 只花晋升/复活预留后的 surplus，不应让普通玩家长期卡晋升 |
| 债务率 | 40 次普通尝试后有债务角色最好低于 50%；若持续高于 60%，说明死亡或复活成本过重 |
| 死亡失败 | 应明显少于失败撤离；普通内容包不建议超过总尝试的 8%-12% |

若模拟偏离目标：

- 升阶太慢：优先降低该阶段 EXP 曲线，或增加同阶通关 EXP，不要直接送阶位。
- 积分太紧：优先降低复活/治疗频率，或提高评级/隐藏目标收益，不要降低抽卡价格。
- 债务过高：优先减少死亡失败，把更多失败改为低完成逃生、污染、疲劳或临时身份清算副本。
- 抽卡拖慢晋升：UI 可以提示“晋升预留积分”，但抽卡价格和保底不跟幸运挂钩。

### 期望战斗面板

下面是“普通成长 + 少量背包道具/核心能力加成”的期望区间，用于生成怪物面板时校准，不是玩家属性硬限制。

| 阶位 | 期望等级 | 主属性均值 | `physical_attack` | `ranged_attack` | `defense` | `mental_resist` | 说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| D | 1-3 | 11-14 | 5-9 | 5-8 | 3-6 | 3-5 | 普通怪可被赶跑或临时击退 |
| C | 3-6 | 14-18 | 8-14 | 7-12 | 6-10 | 5-8 | 精英怪需要道具或线索削弱 |
| B | 6-10 | 18-24 | 12-20 | 10-17 | 10-16 | 8-13 | 开始出现无法硬打的规则敌人 |
| A | 10-15 | 24-32 | 18-30 | 15-26 | 16-25 | 12-20 | Boss 默认不能正面杀死 |
| S | 15+ | 30-42 | 26-42 | 22-36 | 24-38 | 18-32 | 角色很强，但副本目标仍应优先规则解法 |

怪物生成约束：

- 普通怪的有效防御/抗性不应长期高过同阶玩家期望攻击的 70%。
- 精英怪可以压制单个玩家，但必须存在弱点、地形、道具、线索或队友协作解法。
- Boss 默认使用 `stability`、`seal_progress` 或威胁时钟结算，不用普通 HP 让玩家硬刮。
- 如果副本鼓励战斗，奖励和损耗风险要一起提高；如果副本鼓励逃生，战斗收益必须低于风险。

## 核心能力

核心能力是角色最主要的“无限流个人风格”落点，不做多能力槽，也不让玩家从目录里手动挑选学习。

核心能力格式：

```json
{
  "id": "core_rule",
  "name": "规则嗅觉",
  "rarity": "D",
  "desc": "每副本 1 次，验证一条低级规则是否会立刻造成危险；SAN -5。",
  "uses_per_instance": 1,
  "tags": ["rule", "investigation"],
  "origin": "tutorial_performance"
}
```

获得规则：

- 新手副本开始时 `core_ability=null`。
- 首次标准通关固定新手副本 `T-000 白箱回廊` 后，后端根据玩家行动倾向、角色特质和结算记录生成 1 个核心能力。
- 生成时同步写入 `core_ability_profile`，保留 `scores/picked/source_tags/ability_id/created_at`，方便之后解释“为什么生成这个能力”。
- 玩家不能从能力目录里自主挑选学习；抽卡、普通商店和通关奖励不直接产出可绑定的额外能力。
- 后续内容包可以让核心能力强化、变形或追加代价，但默认仍保持“一个核心能力”。
- 核心能力局内使用仍由 Rules Engine 判定次数、代价和状态补丁，GM 只拿判定结果续写。

默认核心能力原型：

| 原型 | 能力 | 固定效果 | 代价/限制 |
| --- | --- | --- | --- |
| 观察调查 | 异常余光 | 每副本 1 次，获得当前场景中一处被忽略的异常提示 | 涉及隐藏规则时 SAN -5 |
| 脱身潜行 | 退路直觉 | 每副本 1 次，逃离、规避或脱身判定 +3 | 不能跳过强制封锁 |
| 保护支援 | 代偿护手 | 每副本 1 次，为自己或同伴抵消 15 点 HP 伤害 | 自己 SAN -5 |
| 正面破局 | 破局冲击 | 每副本 1 次，破坏、压制或强行突破判定 +3 | 失败时自身 HP -5 |
| 社交伪装 | 人群伪装 | 每副本 1 次，社交、伪装或混入人群判定 +3 | 失败时暴露风险 +1 |
| 规则试探 | 规则嗅觉 | 每副本 1 次，验证一条低级规则是否立刻危险 | SAN -5 |
| 抗压存活 | 残响锚点 | 每副本 1 次，抵消一次动摇或轻度污染 | SAN 低于一半时额外稳定当前精神力 +1 |
| 默认兜底 | 求生本能 | 每副本 1 次，险境行动前获得保守提示或降低一级低级风险 | 不能替代主线解法 |

生成倾向：

| 行动倾向 | 关键词例子 | 优先原型 |
| --- | --- | --- |
| 观察、检查、分析、验证线索 | 观察、检查、打量、记录、推理、搜索、observe | 异常余光 |
| 逃跑、潜行、绕路、撤退 | 逃、跑、躲、潜行、撤退、冲过去、escape | 退路直觉 |
| 救人、保护、治疗、掩护 | 保护、挡、救、治疗、拉住、包扎、protect | 代偿护手 |
| 攻击、破坏、硬闯、压制 | 打、砸、攻击、破坏、撬、拆、combat | 破局冲击 |
| 交涉、伪装、套话、说服 | 交谈、询问、说服、安慰、呼唤、social | 人群伪装 |
| 规则、禁忌、广播、门牌 | 规则、禁忌、试探、条件、红灯、白灯、rule | 规则嗅觉 |
| 受伤、污染、濒死、坚持 | 受伤、污染、濒死、坚持、冷静、resilience | 残响锚点 |
