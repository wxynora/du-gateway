# 文游奖励、经济与惩罚副本

## 通关奖励

奖励由规则引擎根据难度、玩家角色通关结果、隐藏目标和副本表现计算。

### 基础保底奖励

通关奖励分两层：

```text
基础保底 = 只要达成最低过关/撤离条件就发放
评级叠加 = 根据主线、普通支线、隐藏支线、隐藏结局、特殊成就和损耗记录增加或扣减
```

基础保底不随机，保证玩家完成副本后有稳定收入。

| 难度 | 通关保底积分 | 通关保底 EXP | 基础奖励次数 |
| --- | ---: | ---: | ---: |
| D | 100 | 30 | 1 |
| C | 220 | 60 | 1 |
| B | 450 | 120 | 2 |
| A | 900 | 220 | 2 |
| S | 1800 | 420 | 3 |

低完成度撤离时可保留部分保底；纯失败不发积分，死亡、复活、债务和道具损耗会形成实际成本。

| 结果 | 保底积分系数 | 保底 EXP 系数 | 说明 |
| --- | ---: | ---: | --- |
| 标准通关 | 1.00 | 1.00 | 达成主线最低条件 |
| 低完成逃生 | 0.50 | 0.50 | 活着离开，并带回最低任务记录或有效情报 |
| 失败撤离 | 0.00 | 0.20 | 强制撤离、放弃或只保住性命；不给积分，只给少量经历记录 |
| 死亡失败 | 0.00 | 0.00 | 死亡或彻底失败；不给积分和 EXP，并按规则结算复活/债务 |

失败成本：

| 成本 | 默认规则 |
| --- | --- |
| 复活 | 按复活公式扣积分；积分不足写入 `debts` |
| 主神债务 | 后续通关结算先偿还债务，再发放积分 |
| 道具损耗 | 随机损坏 1 件可损耗道具，或让本局使用过的道具耐久额外下降 |
| 污染/伤势 | 可保留 1 个负面状态进入下个副本，除非支付治疗费用 |
| 放弃惩罚 | 放弃副本可额外扣除本难度通关保底的 10%-30%，不足则写入债务 |

### 结算对象

默认只结算真实玩家控制的玩家角色。

规则：

- 单人游玩时，通关结果、评级、积分、EXP、奖励 roll 只看该玩家角色。
- 多名真实玩家时，可以分别结算每名玩家角色，也可以按玩家队伍共享一次副本评级；NPC 任务者不参与玩家评级。
- NPC 任务者的存活、死亡、逃脱、背叛或合作只作为副本事实记录。
- NPC 结果不会自动加分或扣分；只有当当前玩家明确完成了“救下某 NPC”“护送 NPC”“利用 NPC 身份完成工单”等公开支线、隐藏支线、隐藏结局或特殊成就时，才写入该玩家的 `settlement_flags`。
- NPC 自己不发玩家积分、EXP、抽卡资源或成长奖励。

### 评级分

后端根据结构化完成标记计算 `rating_score`，再映射成结算评级。

评级不单独给“线索分”。线索、地点探索和规则理解只作为完成主线、支线、隐藏支线或隐藏结局的证据；最终看玩家实际完成了哪些目标，而不是机械统计发现了多少条线索。

| 项目 | 分值 | 说明 |
| --- | ---: | --- |
| 主线完成度 | 0-45 | 完成核心任务、达成通关条件、没有跳过关键代价 |
| 普通支线完成度 | 0-15 | 完成公开支线、救援、资源回收或额外任务 |
| 隐藏支线完成度 | 0-15 | 完成隐藏任务、额外调查或特殊 NPC 线 |
| 隐藏结局完成度 | 0-15 | 触发特殊结局、真结局或高难结局 |
| 特殊成就 | 0-15 | 玩家角色全部存活、低污染、限时优秀、无复活等 |
| 损耗控制 | -20 到 10 | 复活、重伤、污染、债务会扣分；低损耗加分 |

结算评级：

| 评级 | 分数 | 评级积分加成 | 评级 EXP 加成 | 额外奖励 |
| --- | ---: | ---: | ---: | --- |
| S 完美 | 95+ | +70% | +70% | +2 次奖励 roll，至少 1 次 B+ |
| A 优秀 | 80-94 | +45% | +45% | +1 次奖励 roll，30% 概率 B+ |
| B 标准 | 60-79 | +20% | +20% | 正常奖励 |
| C 勉强 | 40-59 | +0% | +0% | 正常奖励，稀有度不加成 |
| D 低完成 | 20-39 | -20% | -20% | 奖励稀有度可能下调 |
| F 失败 | 0-19 | 无 | 无 | 不发积分奖励；只结算复活、债务、损耗 |

评级加成只按基础保底计算，不套娃乘特殊成就：

```text
rating_points_bonus: S=0.70, A=0.45, B=0.20, C=0, D=-0.20, F=0
rating_exp_bonus: S=0.70, A=0.45, B=0.20, C=0, D=-0.20, F=0
```

特殊成就建议：

| 成就 | 评级分 | 积分叠加 | EXP 叠加 | 额外效果 |
| --- | ---: | ---: | ---: | --- |
| 解开隐藏真相 | +10 | +12% | +10% | +1 次线索/剧情奖励 |
| 完成隐藏支线 | +8 | +8% | +8% | 支线相关物品、称号或情报 |
| 触发隐藏结局 | +12 | +20% | +15% | 至少 1 次 B+ 奖励 |
| 完成 NPC 相关支线 | +6 | +6% | +6% | 仅限该 NPC 目标被写入本局支线/隐藏支线/成就 |
| 玩家角色全部存活 | +8 | +8% | +5% | 多玩家时只计算真实玩家角色，不含 NPC 任务者 |
| 低污染通关 | +6 | +6% | +5% | 精神类奖励概率 +10% |
| 限时优秀完成 | +6 | +6% | +5% | 时间类奖励概率 +10% |
| 无复活通关 | +5 | +5% | +5% | 结算称号或额外记录奖励 |

特殊成就叠加上限：

```text
achievement_points_bonus_cap = +60%
achievement_exp_bonus_cap = +50%
```

也就是说，多项隐藏内容可以叠，但默认最多再叠基础保底的 60% 积分、50% EXP；内容包可以为真结局或唯一成就单独突破上限，但必须写在 `gm_secret.reward_overrides`。

最小结算字段：

```json
{
  "mainline": { "completed": true, "completion": 1.0 },
  "side_quests": [{ "id": "save_guard", "completed": true }],
  "hidden_side_quests": [{ "id": "find_fake_rule_source", "completed": false }],
  "hidden_endings": [{ "id": "true_escape", "completed": true }],
  "achievements": ["low_pollution_clear"],
  "player_scope": ["player1"],
  "losses": {
    "revive_count": 0,
    "death_count": 0,
    "heavy_injury_count": 1,
    "pollution": 12,
    "debt_added": 0
  }
}
```

`discovered_clues` 可以帮助后端判断上面这些字段是否完成，但不直接变成独立评分项。

### 结算标记写入

评级不应该在结算时临时读 GM 文本猜。副本运行过程中，每次任务、线索、隐藏结局、NPC 相关目标或损耗发生变化，都要通过 `state_patch` 写入 `rules_state.settlement_flags`。

推荐字段：

```json
{
  "settlement_flags": {
    "player1": {
      "mainline": { "completion": 0.75, "completed": false },
      "side_quests": {},
      "hidden_side_quests": {},
      "hidden_endings": {},
      "achievements": [],
      "losses": {
        "revive_count": 0,
        "death_count": 0,
        "heavy_injury_count": 0,
        "pollution_peak": 12,
        "debt_added": 0,
        "item_broken_count": 1
      },
      "reward_tags": []
    }
  }
}
```

写入来源：

| 事件 | 写入字段 | 说明 |
| --- | --- | --- |
| 主线任务完成或推进 | `mainline.completion/completed` | 由任务状态或蓝图通关条件触发 |
| 普通支线完成 | `side_quests[id]` | 只记录当前玩家/队伍实际完成的支线 |
| 隐藏支线完成 | `hidden_side_quests[id]` | 可以隐藏到结算才展示名称 |
| 隐藏结局触发 | `hidden_endings[id]` | 必须来自蓝图或内容包，不由 GM 临场发明 |
| 特殊成就 | `achievements[]` | 例如低污染、无复活、限时优秀 |
| NPC 相关目标 | `side_quests` / `hidden_side_quests` / `achievements` | NPC 自身结局不自动加分，必须绑定玩家目标 |
| 复活、死亡、重伤 | `losses` | 作为损耗控制和债务计算输入 |
| 污染、债务、道具损坏 | `losses` | 结算时扣分或追加成本 |
| 特殊奖励资格 | `reward_tags` | 例如 `hidden_truth`、`boss_redeemed`、`low_pollution` |

结算时只读取 `settlement_flags`、玩家当前状态和 `reward_context`。如果 GM 文本说“你完成了隐藏结局”，但没有对应 flag，后端应返回“未确认”，并让下一轮 GM 根据规则结果纠偏。

最终计算：

```text
base_points = clear_base_points[difficulty] * result_base_factor
base_exp = clear_base_exp[difficulty] * result_base_factor
rating_points = base_points * rating_points_bonus
rating_exp = base_exp * rating_exp_bonus
achievement_points_bonus = min(sum(achievement_points_bonus_items), achievement_points_bonus_cap)
achievement_exp_bonus = min(sum(achievement_exp_bonus_items), achievement_exp_bonus_cap)
achievement_points = base_points * achievement_points_bonus
achievement_exp = base_exp * achievement_exp_bonus

gross_points = round(base_points + rating_points + achievement_points)
penalty_points = revive_costs + debt_costs + abandon_penalty + treatment_costs
final_points = max(0, gross_points - penalty_points)
new_debt = max(0, penalty_points - gross_points - current_points_available_for_penalty)
final_exp = round(base_exp + rating_exp + achievement_exp)
```

最终积分不得低于 0；倒扣优先扣现有积分，不够的部分写入 `debts`，不直接让 `points` 变负。`死亡失败` 默认 `gross_points = 0`，因此只会扣复活、债务、治疗等成本。

### 奖励稀有度

每次基础奖励 roll 的稀有度：

| 副本难度 | D | C | B | A | S |
| --- | ---: | ---: | ---: | ---: | ---: |
| D | 70% | 25% | 5% | 0% | 0% |
| C | 20% | 60% | 18% | 2% | 0% |
| B | 0% | 25% | 55% | 18% | 2% |
| A | 0% | 0% | 35% | 55% | 10% |
| S | 0% | 0% | 0% | 45% | 55% |

难度上限：

| 副本难度 | 通用道具默认上限 | 副本专属可带出物默认上限 | 例外 |
| --- | --- | --- | --- |
| D | C | C | 不允许 A/S；B 只能作为隐藏唯一奖励，且必须封印或降级生效 |
| C | B | B | A 只能作为隐藏唯一奖励，且必须封印或降级生效 |
| B | A | A | S 只能作为隐藏唯一奖励，且必须封印或降级生效 |
| A | S | S | 可掉 S，但必须有代价、封印或使用限制 |
| S | S | S | 仍需遵守唯一物、代价和封印规则 |

也就是说，D 级副本的常规产出最多到 C 级。即使 D 级副本触发隐藏支线、隐藏结局或特殊成就，默认也只能给 C 级以内的通用道具；若内容包确实要给 B 级纪念物，必须写在 `gm_secret.reward_overrides` 或 `instance_unique_rewards`，并默认 `shop_allowed=false`、`gacha_allowed=false`、`seal_rank=B` 或只允许 D 阶降级效果。

结果评级修正：

- S 完美：稀有度上调 1 档，最高 S。
- A 优秀：30% 概率上调 1 档。
- C 逃生：30% 概率下调 1 档。
- D/F：稀有度下调 1 档，最低 D。

### 奖励掉落表

奖励 roll 必须先确定稀有度，再确定奖励类别，最后从内容包表中取具体物品。

通用道具和副本专属可带出物分开处理：

- 通用商店/抽卡/奖励道具从 `item_catalog` 或当前内容包覆盖的通用目录中按 `rarity/tags/era_tags/gacha_allowed` 取。
- 副本专属可带出物从当前副本或内容包的 `instance_unique_rewards` / `content_pack_rewards` 里取，不要求进入通用道具目录。
- 副本专属物可以带出副本，但默认 `shop_allowed=false`、`gacha_allowed=false`，不能出现在普通商店或通用抽卡池。
- 如果某个副本专属物后来被确认可复用，再补价格、标签、开关和封印规则，提升进通用 `item_catalog`。

类别概率：

| 稀有度 | 消耗道具 | 成长材料 | 工具道具 | 能力模板 | 进化印记 | 特殊物/称号 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D | 50% | 25% | 20% | 4% | 1% | 0% |
| C | 35% | 25% | 25% | 8% | 4% | 3% |
| B | 20% | 24% | 30% | 12% | 8% | 6% |
| A | 12% | 22% | 32% | 14% | 10% | 10% |
| S | 6% | 15% | 36% | 16% | 13% | 14% |

数量表：

| 类别 | D | C | B | A | S |
| --- | --- | --- | --- | --- | --- |
| 消耗道具 | D 道具 x1 | C 道具 x1 | B 道具 x1 | A 道具 x1 | S 道具 x1 |
| 成长材料 | 低级素材 x1 | 低级素材 x2 或异常残片 x1 | 中级素材 x2 或异常核心 x1 | 高级素材 x2 或副本核心 x1 | 传说素材 x1 或副本核心 x2 |
| 工具道具 | D 工具 x1 | C 工具 x1 | B 工具 x1 | A 工具 x1 | S 工具 x1 或 S 特殊物 x1 |
| 能力模板 | 随机 D 能力 | 随机 C 能力 | 随机 B 能力 | 随机 A 能力 | 随机 S 能力 |
| 进化印记 | 随机 D 进化 | 随机 C 进化 | 随机 B 进化 | 随机 A 进化 | 随机 S 进化 |
| 特殊物/称号 | 无 | 低级记录 | B 级称号或线索物 | A 级称号/特殊物 | S 级唯一记录/特殊物 |

掉落流程：

```text
roll_reward(state, player_id, instance_difficulty, rating, reward_table_id):
  rarity = roll_rarity(instance_difficulty)
  rarity = apply_rating_modifier(rarity, rating)
  rarity = clamp_by_instance_reward_cap(rarity, instance_difficulty, reward_source)
  category = roll_category(rarity)
  if category == "consumable_item":
    reward = pick_from_item_catalog(rarity, instance.tags, seed)
  elif category == "instance_unique":
    reward = pick_from_instance_unique_rewards(instance.id, rarity, seed)
  else:
    reward = pick_from_content_pack(reward_table_id, rarity, category, seed)
  apply_reward_to_inventory_or_profile(reward)
```

保底修正：

- S 完美额外奖励中至少 1 次 B+，如果 roll 出 D/C，强制上调到 B。
- 隐藏结局奖励至少 1 次 B+，优先从该副本主题表抽。
- 同一结算中如果连续 3 次奖励都是材料，第 4 次强制改为道具、能力模板、进化印记或特殊物。
- 若奖励到已拥有唯一物品，按同稀有度重复转化表给碎片，不返还积分。

### 副本类型奖励示例

| 类型 | D/C 奖励 | B/A 奖励 | S 奖励 |
| --- | --- | --- | --- |
| 规则怪谈 | 规则残页、白蜡烛 | 规则橡皮、禁令豁免券 | 低级规则改写笔 |
| 剧情解密 | 旧档案、证言碎片 | 因果粉笔、真相封存瓶 | 因果缝合材料 |
| 大逃杀 | 补给箱、安全区令牌 | 猎杀豁免、战利品箱 | 终局幸存者印记 |
| 对抗 | 阵营徽记、伪装面具 | 背叛契约、身份重写卡 | 主神仲裁权 |
| 生存撤离 | 物资券、氧气罐 | 撤离信标、环境抗性药剂 | 黑门撤离凭证 |
| 潜伏调查 | 身份补丁、监听纸鹤 | 嫌疑人档案、记忆针 | 完美伪装核心 |
| 限时任务 | 延迟券、计时碎片 | 时间沙漏、阶段跳转票 | 一次性时间停顿 |

通关也可以奖励工具道具和成长材料：

| 难度 | 工具/材料奖励 |
| --- | --- |
| D | 低级素材、随机 D 工具箱 |
| C | 低级素材、随机 C 工具箱、异常残片 |
| B | 中级素材、随机 B 工具箱、异常核心 |
| A | 高级素材、A 级特殊工具、低概率副本核心 |
| S | 传说素材、S 级特殊工具、副本核心、唯一道具 |

## 经济平衡

为了避免后期通胀：

- 复活成本随死亡次数上升。
- 属性药剂每次结算限购。
- A/S 物品有次数、冷却或副作用。
- 进化不再作为常驻升级消耗项；积分主要消耗在复活、治疗、抽卡、商店、刷新和特殊兑换。
- 复活、治疗、抽卡、商店刷新和高阶进化持续消耗积分或材料。
- 抽卡重复转化为碎片，不直接返还积分。
- 抽卡单抽固定 100 积分，100 抽传说大保底固定消耗 10000 积分。
- S 级道具若进入特殊商店或活动商店指定购买，价格必须高于 100 抽随机 S 大保底；默认不低于 12000 积分。
- 商店每天或每次结算刷新，刷新可收取 20 积分。
- 债务、污染、诅咒等负面状态可以作为高阶能力代价。

### 强制惩罚副本

当债务、污染或诅咒过高时，可以触发强制惩罚副本，作为失败成本和经济回收机制。

默认触发条件：

| 条件 | 触发 |
| --- | --- |
| `debts >= 1000` | 债务催收副本 |
| `debts >= 3000` | 高压债务清算副本，通关奖励优先还债 |
| `pollution >= 60` | 污染净化副本 |
| `pollution >= 90` | 强制污染清算副本，失败会追加封印或状态 |
| 连续 2 次死亡失败 | 复活代价副本 |
| 使用 S 级能力代价未偿还 | 契约追偿副本 |

惩罚副本规则：

- 不能主动跳过，除非支付高额积分或消耗指定豁免道具。
- 难度通常不低于玩家当前阶位的推荐难度。
- 通关奖励先偿还债务、移除污染或解除契约，再发放剩余收益。
- 惩罚副本不额外扩展 `hub` 剧情，只作为副本候选池的强制插队任务。

### 系统打工惩罚副本

惩罚副本可以采用“替系统打工”的形式：玩家不是以任务者身份进入，而是被临时塞进其他副本里扮演 NPC、异常工作人员、值班清洁员、门卫、病人、老师、房东、广播员等角色，完成系统派发的工单。

核心限制：

- 玩家必须维持当前 NPC 身份，不能暴露自己是任务者、复活者、系统打工人或外来者。
- 不能向其他任务者直接透露副本真相、通关答案、系统规则或自己的真实身份。
- 不能向怪物阵营、异常阵营或副本核心暴露自己受系统派遣。
- 不能直接致死其他任务者；但可以在 NPC 身份允许范围内误导、试探、拖延或交换信息。
- 不能和怪物阵营主动合谋；若工单要求接触怪物阵营，必须有明确的伪装身份和行动边界。

常见工单：

| 工单 | 目标 | 失败风险 |
| --- | --- | --- |
| 维持场景 | 按 NPC 身份完成工作，防止副本逻辑崩坏 | 暴露身份、威胁时钟 +1 |
| 投递线索 | 用符合角色的方式把线索递给目标任务者 | 直接剧透则判违规 |
| 回收异常 | 取回系统遗失道具、异常碎片或债务凭证 | 污染上升、道具损坏或债务增加 |
| 修补规则漏洞 | 阻止任务者或怪物利用副本漏洞逃课 | 失败后追加债务或封印 |
| 诱导路线 | 把任务者引到指定区域，但不能明说原因 | 被识破后进入暴露状态 |
| 代班 Boss 机制 | 扮演低阶机关/广播/门禁/巡逻 NPC | 被怪物阵营识破后被追猎 |

暴露结算：

| 暴露对象 | 后果 |
| --- | --- |
| 暴露给任务者 | 本次工单评级下调 1 档，追加 `暴露` 1-2 层；严重时强制撤离 |
| 暴露给怪物阵营 | 立刻进入追猎、污染 +5-15，威胁时钟 +1 |
| 同时暴露给双方 | 工单失败，追加债务或封印，并可能触发下一次惩罚副本 |
| 主动说出系统身份 | 视为严重违规，最低按工单失败处理 |

奖励和成本：

- 成功时优先减少债务、污染、封印或契约，不默认发普通副本完整奖励。
- 可以发少量“系统工资”，默认不超过同阶位通关保底积分的 30%。
- 隐藏完成可给称号、NPC 记录标记、低概率系统商店折扣或一次惩罚豁免券。
- 失败不发积分；按暴露对象追加债务、污染、封印或下一次强制工单。

结构化字段建议：

```json
{
  "mode": "system_work_npc",
  "cover_identity": "老小区门卫",
  "work_orders": ["投递线索", "维持场景"],
  "forbidden_reveals": ["tasker_identity", "system_worker_identity", "clear_answer"],
  "exposure_to_taskers": 0,
  "exposure_to_monsters": 0,
  "reward_policy": "repay_first"
}
```

惩罚副本队列：

```json
{
  "forced_instance_queue": [
    {
      "reason": "debt",
      "min_difficulty": "C",
      "debt_snapshot": 1450,
      "expires_after_clear": true,
      "reward_policy": "repay_first"
    }
  ]
}
```

候选副本生成时：

- 如果 `forced_instance_queue` 非空，候选列表至少 1 个位置必须来自队列。
- 高压债务清算、强制污染清算的候选权重为 100%，不能被普通刷新刷掉。
- 惩罚副本结算后，如果债务/污染仍超过阈值，可以继续保留或降级为普通强制候选。
