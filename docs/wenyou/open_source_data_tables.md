# 开源数据表边界

本文档说明文游开源时哪些数据随仓库提供，哪些数据由接入方自己的后端在运行时维护。

核心原则：开源仓库提供默认内容表和规则文档；玩家存档、副本进度、钱包、背包实例和流水属于运行时数据，不随默认内容包一起发布。

默认开源实现建议使用 SQLite 作为运行时主存储，例如 `data/wenyou.sqlite3`。接入方可以替换成 Postgres、MySQL、KV 或自己的后端存储，但应保留同一组语义：当前存档、长期钱包、归档、候选池、连续性卡片和玩家流水必须能独立读写。

## 默认内容表

| 表/文件 | 类型 | 当前默认来源 | 接入方需要做什么 | 用途 |
| --- | --- | --- | --- | --- |
| `item_catalog` | 静态内容表 | `content/default/items.json`、`content/default/item_catalog.sql`、`schemas/item.schema.json` | 直接导入或按 schema 转成自己的数据库表 | 商店、抽卡、奖励、使用道具 |
| `ability_catalog` | 静态内容表 | `content/default/abilities.json`、`schemas/ability.schema.json` | 导入为核心能力原型表，或保持 JSON 查询 | 新手副本通关后的核心能力生成与使用 |
| `reward_tables` | 静态规则表 | `content/default/reward_tables.json`、`schemas/reward_table.schema.json` | 导入为奖励概率/掉落规则表 | 通关奖励、奖励 roll、隐藏奖励池 |

## 运行时存档表

| 表/文件 | 类型 | 默认来源 | 接入方需要做什么 | 用途 |
| --- | --- | --- | --- | --- |
| `players` | 运行时存档表 | 无默认数据 | 接入方创建 | 玩家角色卡、控制者、等级、阶位、基础属性 |
| `player_wallets` | 运行时存档表 | 无默认数据 | 接入方创建 | 积分、债务、抽卡保底、钱包状态 |
| `player_item_instances` | 运行时存档表 | 无默认数据 | 接入方创建 | 玩家实际拥有的道具实例、数量、次数、耐久、封印状态 |
| `instance_runs` | 运行时副本表 | 无默认数据 | 接入方创建 | 当前副本、阶段、轮次、公开/隐藏状态、威胁时钟 |
| `public_panel` | 运行时公开面板 | 无默认数据 | 接入方从副本状态生成或缓存 | 当前任务、已知线索、公开规则、地点、时间状态 |
| `task_items` | 运行时副本物品表 | 无默认数据 | 接入方创建 | 不能带出副本的任务物品、持有人、用途、是否已消耗 |
| `event_log` | 运行时日志表 | 无默认数据 | 接入方创建 | 最近事件、规则结果、前情提要来源 |
| `player_ledger` | 运行时审计表 | 无默认数据 | 接入方创建 | AI 玩家和真实玩家的消费、收入、转交、抽卡流水 |

## 默认 SQLite 存储映射

| SQLite 表 | 建议用途 | 可替换接口 |
| --- | --- | --- |
| `wenyou_kv` | 保存当前 session、wallet、candidate cache、last archive、continuity card 等 JSON 状态 | `get/save session`、`get/save wallet`、`get/save candidates`、`get/save card` |
| `wenyou_archives` | 保存已归档副本全文和列表摘要字段 | `save archive`、`list archives`、`get archive by game_id` |

第一版可以把大对象继续存成 JSON，以减少迁移成本；列表页、审计页和调试页需要排序或筛选的字段再单独拆列。

## 最小接入规则

- 静态内容表里的 `id` 是权威来源；运行时背包只存 `item_id` 和实例状态，不用物品名当权威。
- `public_panel` 必须和真实玩家 UI 看到的数据一致；AI 玩家不额外拿隐藏线索解释。
- 所有玩家工具只能读取静态内容表和运行时存档表，状态变化必须返回 `state_patch`。
- 接入方可以不用 SQL，JSON、SQLite、Postgres、KV 都可以；只要保持字段语义、事务边界和 schema 校验一致。
- 内容包可以替换 `content/default/*`，但必须保留稳定 id、稀有度、分类、门槛、价格、使用阶段和可执行效果字段。
