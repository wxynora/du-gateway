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
apply_event(state, event_intent) -> state_patch
allocate_attribute_points(state, player_id, deltas) -> state_patch
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
- 物品、商店、抽卡、装备、锻造、进化相关函数见 `docs/wenyou/item_evolution_system.md`。

## 内容包建议

推荐目录：

```text
content/default/genres.json
content/default/abilities.json
content/default/reward_tables.json
rulesets/default.json
schemas/game_state.schema.json
schemas/state_patch.schema.json
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
- 将道具目录、商店、抽卡、奖励、升级、武器锻造从 prompt 迁出到 ruleset/content JSON。
- 将默认内容包从业务代码拆到 JSON。
- 保留当前无限流玩法作为 `main_god_infinite` preset；核心引擎不绑定“主神”设定。

当前代码落地缺口：

- 属性点分配 UI 和实际 `allocate_attribute_points` 流程还没接。
- 六基础属性 `str/con/agi/int/spi/luk`、当前精神力 `spi_current`、派生攻击/防御/精神抗性还没迁入当前实现，现有代码仍是体力/智慧旧字段。
- 阶位晋升条件、积分扣除、封印解除和阻断条件还没接。
- 进化、能力、武器的完整数值效果还没从文档表迁到内容包/规则引擎。
- 装备槽、武器耐久、锻造、维修、出售、回收、拆解还没完整接入前后端。
- 道具目录还没落成 `content/default/items.json` 和 `schemas/item.schema.json`；商店、抽卡、奖励还没改成复用同一份道具目录。
- 道具效果需要从普通文本效果升级为 `use_item` 规则表结算，GM 只接收后端返回的 `item_result`。
- 复活、死亡债务、债务偿还、强制惩罚副本队列还没完全接。
- 奖励 roll 不能只记录次数，需要接入稀有度、类别、数量和内容包掉落表。
