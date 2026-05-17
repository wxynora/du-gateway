# 文游后端契约、内容包与迁移备注

## 默认 Schema 草案

### Game State

```json
{
  "version": "1.0.0",
  "ruleset_id": "default",
  "content_pack_id": "main_god_infinite",
  "seed": "run-20260516-001",
  "phase": "instance_running",
  "instance": {
    "id": "inst_001",
    "name": "雾港倒计时",
    "difficulty": "B",
    "genre": ["规则怪谈", "限时任务"],
    "tasker_total": 7,
    "blueprint_id": "bp_inst_001",
    "public": {},
    "gm_secret": {}
  },
  "players": [],
  "npc_taskers": [],
  "encounter_profile": {},
  "runtime_state": {
    "public_state": {},
    "gm_state": {},
    "rules_state": {},
    "runtime_indexes": {},
    "last_state_patch": null
  },
  "gear": [],
  "clocks": [],
  "flags": {},
  "history": [],
  "event_log": []
}
```

### State Patch

```json
{
  "round_id": "round_012",
  "source": "rules_engine",
  "changes": {
    "players": {
      "player1": {
        "hp_delta": -12,
        "san_delta": 0,
        "exp_delta": 0,
        "points_delta": 0,
        "conditions_add": ["轻伤"],
        "conditions_remove": []
      }
    },
    "inventory_add": [],
    "inventory_remove": [],
    "task_updates": [],
    "clue_updates": [],
    "location_updates": [],
    "npc_updates": [],
    "monster_updates": [],
    "clock_updates": [
      { "id": "harbor_broadcast", "delta": 1 }
    ],
    "flags_set": {
      "saw_hidden_notice": true
    }
  }
}
```

## 后端接口建议

后端至少实现这些纯规则函数：

```text
classify_player_action(runtime_state, raw_action) -> action_intent
apply_event(state, event_intent) -> state_patch
create_instance_runtime(candidate, player_profile, ruleset, content_pack) -> runtime_state
get_public_view(runtime_state, player_id) -> public_view
compose_gm_context(runtime_state, player_action) -> gm_context
apply_pre_rules(runtime_state, player_action) -> pre_state_patch
parse_gm_intent(gm_output) -> event_intent + state_proposals
resolve_action(runtime_state, action_intent, gm_intent) -> state_patch
resolve_combat_or_escape(runtime_state, action_intent, monster_id) -> state_patch
apply_state_patch(runtime_state, state_patch) -> runtime_state
allocate_attribute_points(state, player_id, deltas) -> state_patch
use_item(state, player_id, item_uid, context) -> state_patch
equip_item(state, player_id, item_uid, slot) -> state_patch
upgrade_or_forge_gear(state, player_id, item_uid, recipe_id) -> state_patch
use_ability(state, player_id, ability_id, context) -> state_patch
roll_reward(state, player_id, reward_context) -> state_patch
grant_reward(state, settlement_result) -> state_patch
level_up_if_needed(state, player_id) -> state_patch
promote_rank(state, player_id) -> state_patch
revive_player(state, player_id, method) -> state_patch
enqueue_forced_instance_if_needed(state, player_id) -> state_patch
settle_instance(state, result) -> archive
```

接口要求：

- 规则函数必须 deterministic：同一 `state + seed + input` 得到同一结果。
- 所有随机必须来自可记录 seed。
- 所有数值变化都写入 `event_log`，方便回放和 debug。
- GM 输出不能直接覆盖 `hp/san/points/level/rank`。
- 任务、线索、位置、NPC、怪物、威胁时钟和背包都从 runtime state 派生；GM 不能每轮重写这些面板。
- GM 每轮输入由 `compose_gm_context` 从 runtime state 裁剪生成，不发送全量隐藏状态和全量内容表。
- 最小实现必须支持 `public_state/gm_state/rules_state/state_patch`；更复杂的数据库表、索引和缓存策略可以后续替换。
- 结算评级只读取当前玩家角色/玩家队伍的主线、普通支线、隐藏支线、隐藏结局、特殊成就和损耗记录，不按“线索数量”或 NPC 自身结局单独评分。
- NPC 任务者不参与玩家评级；只有 NPC 相关目标被写入当前玩家的支线、隐藏支线、隐藏结局或特殊成就时，才影响该玩家结算。
- NPC 任务者最小实现只需要 `stance/intent/trouble_chance/status`，不强制实现关系值或好感系统。
- 玩家自由文本必须先归类为固定 `action_type`，文本声明“成功/击杀/逃脱”不构成规则结果。
- 物品、商店、抽卡、装备、锻造、进化相关函数见 `docs/wenyou/item_evolution_system.md`。
- 运行时状态缓存、状态分层和 GM 输入输出边界见 `docs/wenyou/runtime_state.md`。

## 内容包建议

推荐目录：

```text
content/default/genres.json
content/default/items.json
content/default/abilities.json
content/default/evolution_paths.json
content/default/reward_tables.json
rulesets/default.json
schemas/game_state.schema.json
schemas/state_patch.schema.json
schemas/item.schema.json
schemas/ability.schema.json
schemas/evolution.schema.json
```

物品、装备和进化内容包目录见 `docs/wenyou/item_evolution_system.md`。

内容包可以换成：

- 无限流主神空间
- 修仙秘境
- 赛博都市
- 克苏鲁调查
- 校园怪谈
- 末日撤离

只要遵守同一套 state 和 state_patch，前端与后端就可以替换。

## 当前项目落地策略

当前 `du-gateway` 先按这套规则草案改造并测试。测试稳定后，再 copy 一份建立独立新仓库作为开源版。

开源仓库边界：

- 核心仓库命名为通用文字副本跑团引擎，不绑定“主神”叙事。
- `main_god_infinite` 作为默认内容包或示例 preset。
- 当前项目里的辛玥/渡、R2、DeepSeek、MiniApp 绑定逻辑不进入核心规则层。
- 新仓库应优先沉淀 `rulesets/`、`schemas/`、`content/` 和 `core/rules_engine`。
- 适配层另放 `adapters/`，例如 Flask、Node、SQLite、Supabase、本地 JSON 存档等。

## 当前实现迁移备注

当前 `du-gateway` 文游实现里已有：

- 主神空间/副本/归档流程。
- 候选池和自定义开局。
- HP、SAN、等级、阶位、体力/智慧旧字段、进化、能力、积分、背包；后续要迁移到 `str/con/agi/int/spi/luk` 六基础属性和 `spi_current` 当前精神力。
- 商店和道具购买。
- 文游连续性卡片。

后续迁移方向：

- 将固定“2 玩家 + 4 NPC”改成 `tasker_total 2-13`。
- 将文本版【主神面板】升级为 `state_patch`。
- 将任务、线索、位置、NPC、怪物实例和威胁时钟迁入 `runtime_state`，前端面板改为读取 `public_view`，不再从 GM 文本解析。
- 道具目录已先迁到 `content/default/items.json`，并生成 `content/default/item_catalog.sql` 与 `schemas/item.schema.json`；后续继续把升级、武器锻造、进化从 prompt 迁出到 ruleset/content JSON。
- 将默认内容包从业务代码拆到 JSON。
- 保留当前无限流玩法作为 `main_god_infinite` preset；核心引擎不绑定“主神”设定。

### 功能实现对齐表

这张表用于 `du-gateway` 测试期对齐文档和代码。功能做完后，应把“当前状态”更新为已实现版本号，或移到实现清单/变更记录；不要让旧缺口长期留在开源说明里。

| 规则模块 | 文档真源 | 当前状态口径 | 实现入口 |
| --- | --- | --- | --- |
| 副本蓝图与任务者 2-13 | `core_loop.md`、`instance_generation.md` | 候选和自定义生成要统一输出 `tasker_total/player_count/npc_taskers` | `create_instance_runtime` |
| runtime state 三层缓存 | `runtime_state.md` | 必须落成 `public_state/gm_state/rules_state`，面板不读 GM 文本 | `create_instance_runtime`、`get_public_view`、`apply_state_patch` |
| 自由文本行动归类 | `runtime_state.md` | 新增固定 `action_type`，声明成功不等于成功 | `classify_player_action`、`resolve_action` |
| 战斗/逃跑/怪物 | `monster_system.md` | 普通风险扣血之外，还要有怪物实例、逃跑和遭遇状态机 | `resolve_combat_or_escape` |
| 属性加点和派生面板 | `numeric_growth.md` | 后端和 UI 都要支持六属性、软/硬上限、当前精神力 | `allocate_attribute_points`、`level_up_if_needed` |
| 阶位晋升 | `numeric_growth.md` | 条件、扣积分、阻断、封印解除和特殊商店解锁要同一 patch | `promote_rank` |
| 道具效果执行 | `item_evolution_system.md` | 文本 `effect` 不能作为裁判；正式执行读 `effect_json` | `use_item` |
| 装备/耐久/锻造/回收 | `item_evolution_system.md` | 装备槽、耐久、维修、出售、拆解和锻造统一走规则函数 | `equip_item`、`upgrade_or_forge_gear` |
| 能力/进化 | `numeric_growth.md`、`item_evolution_system.md` | 从内容包读取，支持封印、解封、升级、触发和副作用 | `apply_evolution_effect`、`use_ability` |
| 商店/抽卡 | `item_evolution_system.md` | 商店和抽卡复用内容表；抽卡接口不得读取幸运 | `generate_shop_rotation`、`buy_item`、`roll_gacha` |
| 结算评级 | `rewards_economy.md` | 只读 `settlement_flags`，不按线索数量或 GM 总结评分 | `settle_instance` |
| 奖励 roll | `rewards_economy.md` | 先稀有度、再类别、再内容包；必须做难度上限和保底 | `roll_reward`、`grant_reward` |
| 惩罚副本 | `rewards_economy.md` | 债务/污染/契约进入强制队列，可生成系统打工 NPC 模式 | `enqueue_forced_instance_if_needed` |

开发验收用例见 `docs/wenyou/implementation_checklist.md`。
