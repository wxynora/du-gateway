# 文游规则索引

本文档是文游开源规则和默认内容包的入口。它只索引文游规则、内容表和接入契约，不依赖当前私有后端的调试索引。

## 推荐阅读顺序

1. 先读 [`../wenyou_rules.md`](../wenyou_rules.md)：了解整体设定、玩家人数、阶段、数值、商店、抽卡和奖励边界。
2. 再读 [`core_loop.md`](core_loop.md) 和 [`runtime_state.md`](runtime_state.md)：确认每轮行动、状态缓存、公开面板、隐藏状态和 `state_patch` 怎么分工。
3. 接着读 [`open_source_data_tables.md`](open_source_data_tables.md) 和 [`backend_contracts.md`](backend_contracts.md)：确认默认内容表、运行时存档表、后端规则函数和 GM/DS 边界。
4. 如果要接完整玩法，再读数值、道具、奖励、副本和怪物系统。
5. 如果要接入另一个 AI 玩家，再读 [`ai_player_integration.md`](ai_player_integration.md)。
6. 如果要做开源发布或独立试玩版，再读 [`open_source_distribution.md`](open_source_distribution.md)。

## 文档地图

| 文档 | 作用 |
| --- | --- |
| [`../wenyou_rules.md`](../wenyou_rules.md) | 开源规则总入口，给人快速了解文游整体规则 |
| [`core_loop.md`](core_loop.md) | 主神空间、副本中、结算、归档等核心阶段与可做动作 |
| [`runtime_state.md`](runtime_state.md) | 副本运行时状态缓存、公开/隐藏状态、GM 上下文和 `state_patch` |
| [`instance_generation.md`](instance_generation.md) | 副本生成结构、主线/支线大纲、内容包约束 |
| [`monster_system.md`](monster_system.md) | 普通怪、精英怪、Boss、遭遇预算、战斗/规避/封印规则 |
| [`numeric_growth.md`](numeric_growth.md) | 属性、HP/SAN、精神力、状态、升级、晋升、复活、成长曲线 |
| [`rewards_economy.md`](rewards_economy.md) | 通关评级、积分、EXP、奖励 roll、债务、惩罚副本 |
| [`item_ability_system.md`](item_ability_system.md) | 道具、背包物品、商店、抽卡、回收、核心能力系统 |
| [`open_source_data_tables.md`](open_source_data_tables.md) | 开源默认内容表与接入方运行时存档表的边界 |
| [`backend_contracts.md`](backend_contracts.md) | 后端规则函数、状态补丁、内容包和 GM/DS 权限边界 |
| [`ai_player_integration.md`](ai_player_integration.md) | AI 玩家角色的钱包、背包、上下文、工具和消费流水 |
| [`open_source_distribution.md`](open_source_distribution.md) | 单 HTML 懒人版、完整开源版、工具桥和 MCP 适配层分工 |
| [`implementation_checklist.md`](implementation_checklist.md) | 功能实现和测试对齐清单 |

## 默认内容包

| 文件 | 作用 |
| --- | --- |
| [`../../content/default/items.json`](../../content/default/items.json) | 默认通用道具目录，商店、抽卡和奖励复用 |
| [`../../content/default/item_catalog.sql`](../../content/default/item_catalog.sql) | 默认道具 SQL 建表和 seed |
| [`../../content/default/abilities.json`](../../content/default/abilities.json) | 默认核心能力原型 |
| [`../../content/default/reward_tables.json`](../../content/default/reward_tables.json) | 默认奖励概率和类别偏置 |

## Schema

| 文件 | 作用 |
| --- | --- |
| [`../../schemas/item.schema.json`](../../schemas/item.schema.json) | 道具目录结构校验 |
| [`../../schemas/ability.schema.json`](../../schemas/ability.schema.json) | 核心能力原型结构校验 |
| [`../../schemas/reward_table.schema.json`](../../schemas/reward_table.schema.json) | 奖励表结构校验 |

## 道具草稿源

这些 Markdown 是默认道具目录的审校源，最终结构化内容以 `content/default/items.json` 和 `content/default/item_catalog.sql` 为准。

| 文档 | 内容 |
| --- | --- |
| [`item_catalog_draft_d.md`](item_catalog_draft_d.md) | D 级道具草稿 |
| [`item_catalog_draft_c.md`](item_catalog_draft_c.md) | C 级道具草稿 |
| [`item_catalog_draft_b.md`](item_catalog_draft_b.md) | B 级道具草稿 |
| [`item_catalog_draft_a.md`](item_catalog_draft_a.md) | A 级道具草稿 |
| [`item_catalog_draft_s.md`](item_catalog_draft_s.md) | S 级道具草稿 |

## 最小接入边界

- DS/GM 负责叙事、气氛、行动反馈和非权威建议。
- Rules Engine 负责积分、掉落、背包、道具效果、战斗、成长、状态和奖励结算。
- 前端或接入后端展示 `public_panel`，AI 玩家和真实玩家看到同一份公开任务、线索、规则、地点和时间状态。
- 开源默认内容包可以直接导入，也可以替换；替换时必须保留稳定 id、稀有度、分类、价格、门槛、使用阶段和可执行效果字段。

## 默认玩家映射

- `player1`：玩家一，默认由真实玩家控制。
- `player2`：玩家二，默认由接入方的 AI 玩家控制。
- 默认显示名只使用“玩家一 / 玩家二”。首次进入时应让用户依次填写玩家一和玩家二的代号，并保存为 `player_id -> display_name` 映射。
- 开源规则层不绑定任何私有角色名、外貌或关系设定；接入方可以在自己的项目里覆盖显示名和角色外观。
