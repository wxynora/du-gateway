# 文游物品与核心能力系统

当前版本不再设计装备栏。所有可获得物都留在背包中，系统只支持“使用 / 出售 / 转交”这类背包动作；工具、防护物、规则物、线索物、特殊物都按背包物品处理。

## 物品类型

结构化内容表只保留四类 `item_type`：

| 类型 | 说明 |
| --- | --- |
| `consumable` | 一次性或可堆叠消耗品，例如药剂、胶带、线索卡 |
| `tool` | 可反复使用或有耐久的工具、防护物、伪装物、规则媒介 |
| `material` | 成长、解封、兑换或内容包合成用材料 |
| `special` | 唯一物、隐藏奖励、称号/记录型物品 |

中文 `category` 仍保留玩法分类：增益类、防护类、探查类、线索类、工具类、伪装类、位移类、规则类、结算类、材料类、彩蛋类。不要把“武器、防具、饰品、装备槽”写进结构化类型。

## 内容表

默认内容表：

```text
content/default/items.json
content/default/item_catalog.sql
schemas/item.schema.json
scripts/build_wenyou_item_catalog.py
```

`items.json` 字段：

| 字段 | 说明 |
| --- | --- |
| `id/name/rarity/category/item_type` | 物品身份、稀有度、玩法分类和结构类型 |
| `effect/effect_json` | 给前端展示和规则系统执行的效果 |
| `requirements` | 等级、阶位、属性、当前精神力等使用门槛 |
| `use_cost` | SAN、污染、债务、威胁时钟、耐久等使用代价 |
| `tags/era_tags/use_phase` | 检索、时代适配和可用阶段 |
| `consume/stackable` | 是否消耗、是否堆叠 |
| `shop_allowed/gacha_allowed` | 是否进入商店或命运裂隙 |
| `seal_rank/price/weight/enabled` | 封印门槛、价格、权重和启用状态 |

内容生成器会把旧审校表里“武器/防具/饰品/可装备工具”统一归为 `tool`，并去掉槽位字段。

## 使用规则

背包物品使用由 Rules Engine 判定，GM 只接收系统判定结果并续写剧情。

执行顺序：

```text
选择背包物品
  -> 校验阶段 use_phase
  -> 校验封印和 requirements
  -> 扣 use_cost
  -> 应用 effect_json
  -> 更新数量、次数或耐久
  -> 写入 state_patch / ledger
  -> 把已结算结果交给 GM 续写
```

常见效果：

| 效果 | 后端行为 |
| --- | --- |
| `hp_restore/san_restore` | 恢复 HP/SAN，不超过上限 |
| `remove_conditions/conditions_add` | 移除或新增状态 |
| `pollution_delta/debt_delta` | 更新污染或债务 |
| `clock_updates` | 更新威胁时钟，前端只显示公开阶段 |
| `public_clue` | 写入线索缓存 |
| `safe_rest_node` | 建立临时安全节点 |
| `durability/uses` | 更新耐久或剩余次数 |

如果一个 `tool` 没有直接数值效果，也可以作为剧情互动媒介使用：系统记录“已使用”和意图，GM 根据结算结果写环境反馈，但不能自行添加额外数值收益。

## 出售与转交

- 出售只允许普通可回收物，任务物、临时物、绑定物、唯一关键物不可出售。
- 回收价低于购买价，按稀有度比例计算。
- 转交只在双方玩家之间移动积分或物品，必须写入双方 ledger。
- 默认不提供拆解、升级、锻造、穿戴或卸下流程。

## 商店与抽卡

系统商店和命运裂隙复用同一内容表：

- 普通商店每日 7-8 个物品，主要出 D/C，低概率 B。
- 普通商店每日 7-8 个物品，随玩家阶位提高低概率出现越级物品；越级物品购买后仍按封印门槛生效。
- 命运裂隙扣主神积分，保底按玩家独立记录，不读取 `luk`。
- 当前卡池建议：`mixed`、`tool_pool`、`supply_pool`、`limited_pool`。

## 核心能力

核心能力不是背包装备，也不是玩家自己从列表里买来学：

- 新手副本开始时 `core_ability=null`。
- 新手副本标准通关后，后端根据玩家在新手副本中的主要行动倾向、特质和结算记录生成一个核心能力。
- 生成结果必须同时保存 `core_ability_profile`，至少包含各倾向分数 `scores`、选中的 `picked`、前几项 `source_tags`、能力 id 和生成时间。
- 核心能力默认每副本 1 次，具体效果仍必须是后端可判定的 `state_patch`。
- 核心能力后续可以随阶位或内容包事件强化、变形或追加代价，但同一角色默认仍只有一个核心能力。
- 通关奖励、隐藏奖励、抽卡和商店不直接产出可绑定的额外能力或身体路线；最多产出能稳定/改写核心能力表现的材料或特殊物。
- 高阶物品可在背包中封印保存，达到阶位、等级或属性门槛后再解封。

## 后端接口

当前默认接口保持精简：

```text
use_item(state, player_id, item_ref, target_id, context) -> state_patch
sell_item(state, player_id, item_ref) -> state_patch
buy_item(state, player_id, offer_ref | item_id, quantity) -> state_patch
roll_gacha(state, player_id, pool_id, count) -> state_patch
transfer(state, actor_id, target_id, transfer_type, item_ref | amount) -> state_patch
use_ability(state, player_id, ability_id, detail) -> state_patch
```

不再保留默认的装备、维修、锻造或拆解接口。内容包未来如果要做某个特殊物品的“修复/改造”，应作为该物品自己的 `use_item` 效果或独立内容包规则，而不是恢复装备栏系统。
