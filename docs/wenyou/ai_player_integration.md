# AI 玩家接入规则

本文档定义“由另一个 AI 控制的玩家角色”如何接入文游系统。

它不是 NPC 好感系统，也不是 GM 权限扩展。AI 玩家是一个真实玩家队伍里的独立玩家角色：有自己的角色卡、钱包、背包、装备栏、抽卡保底和消费流水。GM 仍负责叙事，Rules Engine 仍负责精准数值和状态写入。

本文档使用通用命名，不绑定任何具体角色名、模型、后端或前端。

## 目标

- 让 AI 控制的玩家角色能真正参与游戏，而不是只在剧情文本里“假装行动”。
- 让 AI 玩家拥有自己的积分、债务、背包、装备、抽卡保底和消费记录。
- 真实玩家可以看见 AI 玩家的消费明细，但 AI 玩家花自己的积分不需要真实玩家确认。
- 查看角色面板、背包、商店、积分等信息不需要工具；后端应直接把必要上下文提供给 AI 玩家。
- AI 玩家每次决策前必须收到前情提要，避免脱离当前剧情、约定、危险和上一轮结果。
- 只有会修改状态的动作才走工具，并且所有结果都必须写入 `state_patch` 和 `ledger`。

## 核心边界

| 对象 | 职责 |
| --- | --- |
| 真实玩家 | 控制自己的玩家角色，决定自己的行动和消费 |
| AI 玩家 | 控制绑定的 AI 玩家角色，决定自己的行动和消费 |
| GM | 描述环境、NPC、怪物和剧情反馈，不直接改数值 |
| Rules Engine | 判定道具、商店、抽卡、背包、转交、扣积分、掉落和状态变化 |
| 前端 | 展示双方角色面板、背包、消费明细和工具结果 |

AI 玩家不能直接修改其他玩家角色的钱包、背包、装备、属性或行动结果。跨角色转交必须通过规则工具完成。

## 最小数据结构

推荐把玩家角色、钱包和背包拆开存。

```json
{
  "players": {
    "player1": {
      "display_name": "玩家一",
      "controller": "human",
      "hp": 180,
      "san": 180,
      "spi_current": 10,
      "rank": "D",
      "level": 1,
      "attributes": {
        "str": 10,
        "con": 10,
        "agi": 10,
        "int": 10,
        "spi": 10,
        "luk": 10
      }
    },
    "player2": {
      "display_name": "AI 玩家",
      "controller": "ai",
      "hp": 180,
      "san": 180,
      "spi_current": 10,
      "rank": "D",
      "level": 1,
      "attributes": {
        "str": 10,
        "con": 10,
        "agi": 10,
        "int": 10,
        "spi": 10,
        "luk": 10
      }
    }
  },
  "wallets": {
    "player1": {
      "points": 100,
      "debts": 0,
      "gacha": {},
      "ledger": []
    },
    "player2": {
      "points": 100,
      "debts": 0,
      "gacha": {},
      "ledger": []
    }
  },
  "inventories": {
    "player1": [],
    "player2": [],
    "task_items": []
  },
  "equipment": {
    "player1": {},
    "player2": {}
  }
}
```

字段说明：

| 字段 | 规则 |
| --- | --- |
| `controller` | `human` / `ai` / `system`；决定谁能发起行动 |
| `wallets[player_id]` | 每个玩家角色独立钱包，积分、债务、抽卡保底互不混用 |
| `inventories[player_id]` | 每个玩家角色独立随身背包 |
| `inventories.task_items` | 队伍或副本临时任务物品；可记录 `holder_id` |
| `equipment[player_id]` | 每个玩家角色独立装备槽 |
| `ledger` | 玩家个人消费/收入流水；真实玩家可查看 AI 玩家流水 |

## 给 AI 玩家看的上下文

AI 玩家每次决策前，后端直接提供裁剪后的只读上下文。查看这些信息不需要工具。

```json
{
  "ai_player_context": {
    "actor_id": "player2",
    "phase": "hub",
    "scene_header": {
      "phase_label": "主神空间",
      "current_task": "等待选择副本",
      "current_location": "主神空间",
      "time_state": "整备阶段 / 无倒计时",
      "status_label": "安全"
    },
    "scene": {
      "instance_name": "雾港倒计时",
      "current_location": "主神空间",
      "public_task": "等待选择副本"
    },
    "story_brief": {
      "campaign_summary": "玩家队伍刚完成新手副本，当前回到整备空间。",
      "current_scene_summary": "系统商店和命运裂隙已开放，下一场副本尚未选择。",
      "recent_events": [
        "上一局结算为 B 级标准通关。",
        "队伍获得 1 次奖励 roll。",
        "player1 在上一局受到轻伤，已回到主神空间。"
      ],
      "last_rules_result": "上一轮无战斗结算，当前阶段允许购买、抽卡、修理和整理背包。",
      "active_objectives": [
        "补充消耗品",
        "选择下一场副本"
      ],
      "known_risks": [
        "高阶道具可能因阶位不足被封印。",
        "抽卡不受幸运影响。"
      ],
      "party_notes": [
        "player1 与 AI 玩家当前同队行动。",
        "任务物品默认不能带出副本。"
      ]
    },
    "public_panel": {
      "tasks": [],
      "clues": [],
      "rules": [],
      "locations": []
    },
    "player_panel": {
      "display_name": "AI 玩家",
      "level": 1,
      "rank": "D",
      "hp": 180,
      "hp_max": 180,
      "san": 180,
      "san_max": 180,
      "spi_current": 10,
      "spi_max": 10,
      "attributes": {
        "str": 10,
        "con": 10,
        "agi": 10,
        "int": 10,
        "spi": 10,
        "luk": 10
      },
      "conditions": []
    },
    "wallet": {
      "points": 100,
      "debts": 0,
      "gacha_pity": {
        "mixed": {
          "no_cplus": 0,
          "no_bplus": 0,
          "no_s": 0
        }
      }
    },
    "inventory": [],
    "equipment": {},
    "available_services": {
      "shop": true,
      "gacha": true,
      "repair": true,
      "use_item": true,
      "transfer": true
    },
    "shop_view": {
      "regular": [],
      "special": []
    },
    "gacha_pools": [
      {
        "pool_id": "mixed",
        "single_cost": 100,
        "ten_pull_cost": 1000
      }
    ],
    "recent_ledger": []
  }
}
```

上下文裁剪规则：

- `story_brief` 是给 AI 玩家理解局势的前情提要，必须短、准、可执行，不能塞完整聊天记录。
- `scene_header` 放在上下文开头，用一眼能读懂的方式标出阶段、当前任务、地点、时间状态和公开危险状态。
- `campaign_summary` 记录长期简要进度，例如已完成哪些副本、当前处于什么阶段。
- `current_scene_summary` 记录本轮场景和即时处境。
- `recent_events` 只保留最近 3-8 条关键事件，优先包含上一轮工具结果、战斗/逃跑/道具/结算变化。
- `last_rules_result` 必须来自后端规则结果，不让 AI 玩家根据 GM 文本自行重算。
- `active_objectives` 只写当前 AI 玩家能理解的目标，不暴露隐藏结局条件。
- `known_risks` 只写已公开或规则层允许公开的风险，不暴露精确隐藏时钟。
- `party_notes` 可以写队友约定、道具归属、谁持有任务物品、谁需要治疗等队伍事实。
- `public_panel.tasks/clues/rules/locations` 直接复用真实玩家当前能看到的公开面板数据，不给 AI 玩家另做一套“线索含义”或隐藏解释。
- 如果玩家 UI 已经展示线索状态、验证结果、关联任务或地点标签，AI 玩家看到同样字段；如果 UI 没展示，就不要额外补。
- 副本隐藏规则、隐藏线索、伪线索真伪条件和隐藏结局条件不进 `public_panel`，除非它们已经被玩家侧公开。
- 给 AI 玩家看自己的完整角色卡、钱包、背包、装备和消费记录。
- 可以给 AI 玩家看真实玩家的公开状态摘要，例如 HP/SAN、是否重伤、是否在场。
- 不给 AI 玩家看真实玩家的隐藏手牌、未公开背包、隐藏结算、GM 私密状态，除非规则设定为队伍共享。
- 不发送全量道具目录；商店只发送当前货架，抽卡只发送卡池摘要和保底进度。
- 商店物品建议给短引用，例如 `offer_ref: "R01"`，后端内部映射真实 `item_id`，避免 AI 写错 id。
- AI 玩家不能凭空声明“我买到了某物”；必须使用工具并接受工具结果。

## AI 玩家行动流程

推荐流程：

```text
1. Backend summarize_story_for_ai_player(state, actor_id)
2. Backend compose_ai_player_context(actor_id)，包含 story_brief
3. AI 玩家阅读只读上下文
4. AI 玩家决定是否行动
5. 若只是叙事回应，直接返回自然语言或行动意图
6. 若要改状态，调用 ai_player_* 工具
7. Rules Engine 校验阶段、钱包、背包、门槛、封印和库存
8. Rules Engine 写入 state_patch + ledger
9. GM 或前端展示工具结果
```

重要规则：

- AI 玩家可以买东西、抽卡、修理、出售、使用道具，不需要真实玩家确认。
- AI 玩家每次消费必须写入个人 `ledger`，真实玩家可查看。
- AI 玩家不能直接改真实玩家的资源。
- AI 玩家可以浪费自己的积分；系统不需要替它做“理性消费保护”。
- 如果工具失败，AI 玩家必须接受失败结果，不能在叙事里继续当作成功。

## 四类状态修改工具

默认只保留四类状态修改入口。读取状态、查看背包、查看商店、查看角色面板都不算工具调用。

为了让 AI 玩家更容易稳定调用，可以额外暴露 `ai_player_use_item` 作为快捷工具；它只是 `ai_player_inventory_action(action="use")` 的别名，不新增规则能力。

### 1. `ai_player_buy_item`

AI 玩家从系统商店购买物品。

```json
{
  "tool": "ai_player_buy_item",
  "args": {
    "actor_id": "player2",
    "offer_ref": "R01",
    "item_id": "wy_d_002",
    "quantity": 1,
    "reason": "SAN 低于 70%，补一支精神药剂"
  }
}
```

参数：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `actor_id` | 是 | 发起购买的 AI 玩家角色 id |
| `offer_ref` | 否 | 前端/上下文给的货架短引用，优先使用 |
| `item_id` | 否 | 内容表物品 id；若有 `offer_ref` 可不传 |
| `quantity` | 否 | 默认 1；普通商店通常只允许 1 |
| `reason` | 否 | AI 玩家自述购买理由，写入流水，不能影响价格 |

规则：

- 只允许在 `hub` 或 `settlement` 阶段购买。
- 只能从当前 `shop_view` 的可购买货架里买。
- 扣 `wallets[actor_id].points`。
- 物品进入 `inventories[actor_id]`。
- 购买失败不扣积分。
- AI 玩家不能用该工具给其他玩家直接购买，买完后可另用 `ai_player_transfer` 转交。

返回：

```json
{
  "ok": true,
  "message": "AI 玩家购买【初级精神药剂】，花费 30 积分。",
  "state_patch": {
    "source": "ai_player_tools.buy_item",
    "actor_id": "player2",
    "changes": {
      "wallets": {
        "player2": {
          "points_delta": -30
        }
      },
      "inventory_add": {
        "player2": [
          {
            "item_id": "wy_d_002",
            "name": "初级精神药剂",
            "quantity": 1
          }
        ]
      }
    }
  },
  "ledger_entry": {
    "actor_id": "player2",
    "type": "shop_buy",
    "points_delta": -30,
    "item_name": "初级精神药剂"
  }
}
```

### 2. `ai_player_roll_gacha`

AI 玩家使用自己的积分抽卡。

```json
{
  "tool": "ai_player_roll_gacha",
  "args": {
    "actor_id": "player2",
    "pool_id": "mixed",
    "count": 10,
    "reason": "补充道具池，看看有没有好用的防护物"
  }
}
```

参数：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `actor_id` | 是 | 发起抽卡的 AI 玩家角色 id |
| `pool_id` | 是 | 卡池 id，例如 `mixed`、`weapon_pool`、`ability_pool`、`evolution_pool` |
| `count` | 是 | 只允许 1 或 10 |
| `reason` | 否 | AI 玩家自述抽卡理由 |

规则：

- 只允许在 `hub` 或 `settlement` 阶段抽卡。
- 单抽 100 积分，十连 1000 积分，具体价格以 ruleset 为准。
- 扣 `wallets[actor_id].points`。
- 读取并更新 `wallets[actor_id].gacha[pool_id]`。
- 抽卡不读取 `luk`，不受幸运影响。
- 抽到物品进入 `inventories[actor_id]`。
- 抽到能力/进化/高阶封印物时，按 `rank_min/seal_rank/requirements` 记录为可用、休眠或封印。
- AI 玩家和真实玩家的保底互不影响。

返回必须包含：

| 字段 | 说明 |
| --- | --- |
| `results` | 本次抽取结果 |
| `pity_after` | 抽后保底进度 |
| `points_after` | AI 玩家剩余积分 |
| `ledger_entry` | 消费流水 |
| `state_patch` | 权威状态变更 |

### 3. `ai_player_inventory_action`

AI 玩家对自己的背包和装备执行动作。

```json
{
  "tool": "ai_player_inventory_action",
  "args": {
    "actor_id": "player2",
    "action": "use",
    "item_ref": "inv-123",
    "target_id": "player2",
    "slot": "",
    "context": "副本中 SAN 下降，使用精神药剂"
  }
}
```

支持动作：

| `action` | 说明 |
| --- | --- |
| `use` | 使用消耗品、规则道具、装备主动效果 |
| `equip` | 装备武器、防具、饰品或工具 |
| `repair` | 用积分修补装备耐久 |
| `sell` | 出售可回收物品，获得回收积分 |

参数：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `actor_id` | 是 | 发起动作的 AI 玩家角色 id |
| `action` | 是 | `use` / `equip` / `repair` / `sell` |
| `item_ref` | 是 | 背包内 `uid`、短引用或精确物品名 |
| `target_id` | 否 | 道具目标；默认 `actor_id` |
| `slot` | 否 | 装备槽，例如 `main_weapon`、`armor`、`accessory` |
| `context` | 否 | 使用意图，供规则和 GM 生成反馈 |

规则：

- 工具只能操作 `inventories[actor_id]` 中的物品。
- `use` 必须检查 `use_phase`、`requirements`、`use_cost`、封印、次数、耐久和消耗。
- `equip` 必须检查槽位、属性门槛、阶位门槛、封印和损坏状态。
- `repair` 只消耗 `wallets[actor_id].points`，只恢复耐久，不升级装备。
- `sell` 只能出售非绑定、非任务、非唯一关键物、非临时物。
- 如果 `target_id` 不是 `actor_id`，只允许治疗、辅助或明确可对他人使用的道具；规则引擎最终判定。
- 未来如果保留锻造/拆解，应作为扩展动作，不进入默认最小工具集。

返回：

```json
{
  "ok": true,
  "message": "AI 玩家使用【初级精神药剂】，恢复 30 SAN。",
  "state_patch": {
    "source": "ai_player_tools.inventory_action",
    "actor_id": "player2",
    "changes": {
      "players": {
        "player2": {
          "san_delta": 30,
          "spi_delta": 2
        }
      },
      "inventory_remove": {
        "player2": ["inv-123"]
      }
    }
  },
  "ledger_entry": {
    "actor_id": "player2",
    "type": "item_use",
    "item_name": "初级精神药剂",
    "points_delta": 0
  }
}
```

### 3a. `ai_player_use_item`

AI 玩家使用自己背包里的道具。推荐把这个工具直接暴露给 AI 玩家模型，因为名字更直观，不容易把“使用道具”和“整理背包”混在一起。

```json
{
  "tool": "ai_player_use_item",
  "args": {
    "actor_id": "player2",
    "item_ref": "inv-123",
    "target_id": "player2",
    "context": "副本中 SAN 下降，使用精神药剂"
  }
}
```

等价于：

```json
{
  "tool": "ai_player_inventory_action",
  "args": {
    "actor_id": "player2",
    "action": "use",
    "item_ref": "inv-123",
    "target_id": "player2",
    "context": "副本中 SAN 下降，使用精神药剂"
  }
}
```

规则：

- 只能使用 `inventories[actor_id]` 里真实存在的物品实例。
- 必须检查 `use_phase`、目标是否合法、属性/阶位门槛、封印状态、使用代价、次数、耐久和消耗。
- 任务物品、临时物、封印高阶物、污染武器和规则类道具都按各自 `effect_json` 执行，不能只按文字描述生效。
- 对其他玩家使用时，只允许治疗、辅助、保护或物品定义明确允许的目标类型。
- 成功或失败都由 Rules Engine 返回，AI 玩家不能在叙事里提前宣称结果。

### 4. `ai_player_transfer`

AI 玩家主动转交积分或物品。

```json
{
  "tool": "ai_player_transfer",
  "args": {
    "actor_id": "player2",
    "target_id": "player1",
    "transfer_type": "item",
    "item_ref": "inv-456",
    "quantity": 1,
    "amount": 0,
    "message": "这把钥匙你拿着更方便"
  }
}
```

参数：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `actor_id` | 是 | 发起转交的 AI 玩家角色 id |
| `target_id` | 是 | 接收方玩家角色 id |
| `transfer_type` | 是 | `item` 或 `points` |
| `item_ref` | 条件 | 转交物品时必填 |
| `quantity` | 否 | 默认 1 |
| `amount` | 条件 | 转交积分时必填 |
| `message` | 否 | 给前端和 GM 展示的转交说明 |

规则：

- AI 玩家只能转出自己的积分或背包物品。
- 不能转交绑定物、封印锁定物、不可带出任务物、临时物、唯一关键物，除非物品定义允许。
- 高压战斗、追逐、濒死等阶段可以禁止转交，或要求 GM 事件判定。
- 转交积分同时写入双方 `ledger`。
- 转交物品同时更新双方 `inventory`。
- 转交不等于强迫接收者立即使用；接收后由接收方自行决定。

返回：

```json
{
  "ok": true,
  "message": "AI 玩家将【旧铜钥匙】交给 player1。",
  "state_patch": {
    "source": "ai_player_tools.transfer",
    "actor_id": "player2",
    "changes": {
      "inventory_remove": {
        "player2": ["inv-456"]
      },
      "inventory_add": {
        "player1": [
          {
            "item_id": "old_key",
            "name": "旧铜钥匙",
            "quantity": 1
          }
        ]
      }
    }
  },
  "ledger_entry": {
    "actor_id": "player2",
    "type": "item_transfer_out",
    "target_id": "player1",
    "item_name": "旧铜钥匙"
  }
}
```

## 消费明细

AI 玩家所有资源变化都要写入个人流水。真实玩家可以查看，但不需要预先确认。

推荐字段：

```json
{
  "ledger_id": "ledger_000124",
  "actor_id": "player2",
  "type": "gacha_roll",
  "points_delta": -1000,
  "debts_delta": 0,
  "item_add": [
    {
      "item_id": "wy_d_011",
      "name": "旧校服外套",
      "quantity": 1
    }
  ],
  "item_remove": [],
  "pool_id": "mixed",
  "summary": "十连抽卡，获得 10 件物品。",
  "reason": "补充防护和消耗品",
  "state_patch_id": "patch_000338",
  "created_at": "2026-05-21T14:20:00+08:00",
  "visibility": "player_visible"
}
```

常用流水类型：

| `type` | 说明 |
| --- | --- |
| `shop_buy` | 商店购买 |
| `shop_refresh` | 如果允许 AI 玩家刷新自己的商店货架 |
| `gacha_roll` | 抽卡 |
| `item_use` | 使用道具 |
| `item_equip` | 装备物品 |
| `item_repair` | 修理耐久 |
| `item_sell` | 出售回收 |
| `item_transfer_out` | 转出物品 |
| `item_transfer_in` | 收到物品 |
| `points_transfer_out` | 转出积分 |
| `points_transfer_in` | 收到积分 |
| `settlement_income` | 结算收入 |
| `debt_change` | 债务变化 |

展示建议：

```text
AI 玩家消费明细
- 抽卡 x10，花费 1000，获得：旧校服外套、初级精神药剂...
- 购买【初级精神药剂】，花费 30
- 维修【桃木短剑】，花费 12
- 出售【坏掉的手电】，获得 8
```

## GM 与 AI 玩家的职责边界

AI 玩家可以表达意图：

```text
我想买一支精神药剂，免得下一局 SAN 掉太快。
```

但 AI 玩家不能直接写：

```text
我已经买到精神药剂，背包里多了一支。
```

正确流程是：

```text
AI 玩家意图 -> 调用 ai_player_buy_item -> Rules Engine 返回结果 -> GM/前端展示结果
```

GM 可以写：

```text
AI 玩家从货架上拿起一支精神药剂，系统扣款提示随即亮起。
```

但具体扣了多少、是否买成、物品是否入包，以工具结果为准。

## 提示词注入建议

给 AI 玩家模型的系统片段可以这样写：

```text
你正在控制一个 AI 玩家角色，不是 GM，也不是规则引擎。

你可以阅读自己的角色面板、钱包、背包、装备、商店货架、抽卡保底和最近消费流水。
你会先看到场景头部，其中标出当前阶段、任务、地点、时间状态和公开危险状态。
你能看到与真实玩家公开面板一致的任务、线索、规则和地点；不要自行补充隐藏含义。
你也会收到前情提要，包括当前场景、最近事件、上一轮规则结果、当前目标、已知风险和队伍约定；行动时必须尊重这些上下文。
你可以自由使用自己的积分买东西、抽卡、修理、出售和转交物品，不需要真实玩家确认。
你不能直接花其他玩家的积分，不能直接改其他玩家的背包，不能替其他玩家决定行动。
你想修改状态时，必须调用可用的 ai_player_* 工具，并接受工具返回结果。
你不能在叙事里宣称工具尚未确认的购买、抽卡、治疗、装备或转交已经成功。
如果当前阶段不允许商店、抽卡、维修或转交，你应该等待、行动或说明原因，而不是假装完成。
```

## 与真实玩家的可见性

真实玩家默认能看到：

- AI 玩家角色面板。
- AI 玩家当前 HP/SAN/状态。
- AI 玩家背包和装备，除非某个内容包明确隐藏。
- AI 玩家积分、债务和抽卡保底。
- AI 玩家消费明细。
- AI 玩家转交给真实玩家的物品或积分。

真实玩家不需要逐笔批准：

- AI 玩家购买自己的物品。
- AI 玩家抽自己的卡。
- AI 玩家修理自己的装备。
- AI 玩家出售自己的普通物品。

需要明确记录或提醒的情况：

- AI 玩家花光积分。
- AI 玩家产生债务。
- AI 玩家出售 B 级及以上物品。
- AI 玩家抽到 A/S、唯一物、封印物或高风险污染物。
- AI 玩家转交关键物品给真实玩家。

这些提醒只负责可见，不负责阻止。

## 阶段限制

| 阶段 | AI 玩家可做 |
| --- | --- |
| `hub` | 买商店、抽卡、修理、出售、装备、转交、查看面板 |
| `candidate_selection` | 查看面板、整理非高压物品；默认不买商店，不推进副本剧情 |
| `instance_running` | 使用道具、装备允许切换、转交允许物品、查看面板；不能买系统商店或抽卡 |
| `settlement` | 买商店、抽卡、修理、出售、装备、转交、结算收入入账 |
| `archived` | 只读归档，不修改原存档 |

内容包可以扩展阶段，但默认规则不允许 AI 玩家绕过系统阶段。

## 错误处理

工具失败时必须返回结构化错误：

```json
{
  "ok": false,
  "error_code": "INSUFFICIENT_POINTS",
  "message": "AI 玩家积分不足，无法购买该物品。",
  "actor_id": "player2",
  "state_patch": null
}
```

常见错误：

| `error_code` | 说明 |
| --- | --- |
| `INVALID_ACTOR` | `actor_id` 不存在或不是 AI 玩家 |
| `PHASE_FORBIDDEN` | 当前阶段不允许该动作 |
| `INSUFFICIENT_POINTS` | 积分不足 |
| `ITEM_NOT_FOUND` | 背包或商店中找不到物品 |
| `ITEM_LOCKED` | 绑定、任务、唯一、封印或临时物不能操作 |
| `REQUIREMENT_NOT_MET` | 属性、阶位、当前精神力、等级等门槛不足 |
| `TARGET_FORBIDDEN` | 目标不是可作用对象 |
| `POOL_NOT_AVAILABLE` | 卡池不可用 |

失败不应写入成功流水，但可以写入 debug log 或失败尝试记录。

## 开源实现建议

为了方便不同后端接入，推荐抽象成下面几个纯函数：

```text
summarize_story_for_ai_player(state, actor_id) -> story_brief
compose_ai_player_context(state, actor_id) -> ai_player_context
ai_player_buy_item(state, actor_id, offer_ref | item_id, quantity) -> state_patch
ai_player_roll_gacha(state, actor_id, pool_id, count) -> state_patch
ai_player_use_item(state, actor_id, item_ref, target_id, context) -> state_patch
ai_player_inventory_action(state, actor_id, action, item_ref, target_id, slot, context) -> state_patch
ai_player_transfer(state, actor_id, target_id, transfer_type, item_ref | amount) -> state_patch
append_player_ledger(state, actor_id, ledger_entry) -> state
```

要求：

- 所有函数 deterministic，随机必须写 seed。
- 所有状态变化必须进 `state_patch`。
- 所有积分变化必须进玩家个人 `ledger`。
- `ai_player_use_item` 是推荐暴露给 AI 玩家模型的快捷入口，内部可以直接调用 `ai_player_inventory_action(..., action="use")`。
- `story_brief` 必须从 runtime state、history、event_log、ledger 和公开队伍信息生成，不让 AI 玩家自己猜前情。
- 工具名和字段名不能绑定具体角色名。
- AI 玩家上下文不能发送全量隐藏状态和全量内容表。
- AI 玩家工具不能绕过 Rules Engine。

## 与当前项目的迁移关系

当前项目文游已有 `player1/player2` 角色卡和部分双角色成长入口，但钱包、背包、商店、抽卡仍偏共享账户模型。

接入 AI 玩家后建议迁移为：

```text
旧结构：
wallet.points
wallet.gacha
stats.inventory

新结构：
wallets[player_id].points
wallets[player_id].gacha
inventories[player_id]
equipment[player_id]
```

兼容迁移策略：

1. 旧 `wallet.points` 迁到 `wallets.player1.points`。
2. 旧 `wallet.gacha` 迁到 `wallets.player1.gacha`。
3. 旧 `stats.inventory` 迁到 `inventories.player1`，除非物品已有 `holder_id/equipped_by`。
4. `player2` 初始钱包按规则包给默认积分，例如 100。
5. 前端背包面板改为按玩家切换：`player1` / `player2` / `task_items`。
6. 商店和抽卡接口增加 `actor_id`，默认 `player1`，AI 玩家工具固定传对应 AI 玩家 id。
7. 消费明细页按 `actor_id` 过滤，也可以提供“全部流水”视图。

迁移后，AI 玩家才算真正接入规则系统，而不是只在 GM 文本里行动。
