# 固定副本内容包规范

> 状态：公共服固定副本设计规范，尚未实现对应加载器、Schema 或规则执行器。

固定副本内容包用于 `scripted_solo` 和 `scripted_multiplayer`。它必须在没有 DS、没有 LLM GM 的情况下完整运行，同时也可以在单机 AI GM 模式中作为长期故事大纲。

## 1. 内容包的职责

一个固定副本内容包必须回答四类问题：

1. 这个副本在玩家进入前发生过什么，真正的异常和因果是什么。
2. 当前有哪些人物、地点、规则、线索、怪物和危险状态。
3. 玩家做出某类行动后，规则引擎如何更新权威状态。
4. 哪些状态组合会触发新事件、伏笔回收、失败推进或结局。

内容包不负责：

- 预写玩家会说的每一句话。
- 穷举玩家所有行动顺序。
- 替玩家决定行动。
- 绕过数值、道具和状态规则。
- 在运行时调用维护者的模型。

## 2. 作者底稿与运行蓝图

同一个固定副本分成两层。

### 作者底稿 `authoring_package`

完整保存：

- 世界历史和真相。
- 主线、暗线、人物弧线。
- 全量地图、线索和伏笔。
- 全量故事节点和文本。
- 所有结局及其判定证据。

它用于审校、发布、版本升级和单机 AI GM 的大纲来源，不应每轮全量发送给任何 AI。

### 运行实例 `instance_runtime`

房间开始时根据内容版本、房间 seed、成员数量和身份槽分配生成，只保存本局需要的数据：

- 房间成员与本局身份槽的绑定。
- 本局地点状态、任务状态和线索状态。
- 当前可触发节点索引。
- 当前威胁时钟和怪物实例。
- 已埋下但尚未回收的伏笔。
- 已触发事件和结局资格。

每个进行中的房间必须锁定 `instance_id + content_version + seed`。内容包更新不能改变旧房间正在使用的规则。

## 3. 推荐目录

```text
content/default/instances/
  shen_manor_strange_illness/
    manifest.json
    canon.json
    map.json
    cast.json
    clues.json
    storylets.json
    encounters.json
    endings.json
    texts.zh-CN.json
```

开发早期可以先用一个 JSON 文件保存全部字段。拆文件只为便于多人审校，不改变加载后的统一对象结构。

## 4. 顶层结构

```json
{
  "schema_version": 1,
  "instance_id": "shen_manor_strange_illness",
  "content_version": 1,
  "meta": {},
  "canon": {},
  "pair_capacity": {},
  "role_slots": [],
  "map": {},
  "tasks": {},
  "clues": [],
  "foreshadowing": [],
  "cast": {},
  "encounters": {},
  "clocks": [],
  "storylets": [],
  "endings": [],
  "settlement": {},
  "text_catalog": {}
}
```

所有内部引用必须使用稳定 id，不能依赖数组位置、中文标题或模型临时生成名称。

## 5. 基础档案 `meta`

```json
{
  "title": "沈宅怪病",
  "difficulty": "C",
  "genres": ["剧情解密", "规则怪谈", "潜伏调查"],
  "era_tags": ["民国", "江南宅院"],
  "tone_tags": ["家族秘密", "身份侵占", "镜像怪谈"],
  "expected_scene_count": [18, 30],
  "public_summary": "受邀进入沈宅调查继承人的怪病，在照影礼完成前找出病因。",
  "content_warnings": ["身份抹除", "家族谋害", "轻度猎奇"]
}
```

`public_summary` 不能泄露真相、隐藏结局或 Boss 解法。

## 6. 伴侣容量和任务者编制

```json
{
  "pair_capacity": {
    "min": 1,
    "max": 3
  }
}
```

规则：

- `tasker_total = player_count = pair_count * 2`。
- `scripted_solo` 使用 1 支伴侣小队；`scripted_multiplayer` 至少使用 2 支。
- 联机任务者全部是房间中的真人玩家与各自绑定的 AI 玩家，禁止用 NPC 或 DS 补位。
- 副本原住民不计入任务者人数。
- 房间小队数不在 `pair_capacity` 范围内时禁止开始，而不是临时删改身份槽或剧情人物。

## 7. 身份槽 `role_slots`

固定副本可以给持久玩家分配临时副本身份，但不能覆盖其玩家代号。

```json
{
  "slot_id": "returned_heir",
  "assignment": "seeded_human_member",
  "pair_binding": {
    "partner_slot": "trusted_attendant",
    "same_pair_required": true
  },
  "public_role": "久病后被接回沈宅的继承人",
  "private_hook": "你的名字始终没有被写进沈氏族谱",
  "name_policy": "use_player_display_name",
  "required": true
}
```

身份槽只定义副本中的社会位置和已知信息。真人与 AI 恋人的长期角色数据、关系和记忆仍属于各自账户。

## 8. 世界真相 `canon`

```json
{
  "logline": "一句话概括核心矛盾",
  "background_timeline": [
    {
      "order": 1,
      "time_label": "十八年前",
      "event": "只写已经发生的真实历史",
      "evidence_clue_ids": ["clue_old_birth_register"]
    }
  ],
  "core_truth": "完整说明异常来源、反派目的和玩家为什么被卷入",
  "factions": [],
  "true_rules": [],
  "false_rules": [],
  "hard_constraints": []
}
```

作者底稿必须写完整真相，不能把关键因果留给运行时模型补全。

### 真规则

每条真规则至少包含：

```json
{
  "rule_id": "rule_call_true_name",
  "statement": "规则摘要",
  "condition": {},
  "effect": [],
  "verification_clue_ids": [],
  "counterplay": []
}
```

### 假规则

假规则必须说明：

- 谁留下了它。
- 为什么要误导玩家。
- 如何验证它是假的。
- 玩家照做会产生什么确定后果。

## 9. 地图 `map`

地点节点：

```json
{
  "location_id": "east_bedroom",
  "title": "东厢病房",
  "aliases": ["东厢", "病房", "小姐房间"],
  "initial_state": "accessible",
  "public_description_text_id": "loc.east_bedroom.initial",
  "interactable_ids": ["mirror_east_room", "medicine_bowl", "window_lattice"],
  "signal_state": "weak",
  "danger_tags": ["mirror", "identity_erasure"],
  "state_variants": {}
}
```

连接边：

```json
{
  "from": "east_bedroom",
  "to": "mirror_corridor",
  "direction": "west",
  "requirements": [],
  "blocked_when": [],
  "travel_effects": []
}
```

对讲机信号是地点或事件状态，不由叙事文字临时决定。

## 10. 任务结构 `tasks`

任务分为：

- `mainline`
- `side_quests`
- `hidden_side_quests`

任务只写目标、条件和因果，不预写完成过程。

```json
{
  "task_id": "main_preserve_identity",
  "type": "main",
  "title": "阻止照影礼抹除继承人的身份",
  "visibility": "public",
  "activate_when": [],
  "complete_when": [],
  "fail_when": [],
  "required_clue_ids": [],
  "fail_forward_storylet_id": "storylet_forced_ritual_begins",
  "settlement_tags": ["mainline"]
}
```

## 11. 线索 `clues`

```json
{
  "clue_id": "clue_old_birth_register",
  "title": "被改写的出生簿",
  "meaning": "沈老爷不是继承人的生父",
  "public_text_id": "clue.old_birth_register.public",
  "visibility": "member_or_scene",
  "obtain_routes": [
    {
      "route_id": "account_room_search",
      "conditions": [],
      "effects": []
    },
    {
      "route_id": "nanny_confession",
      "conditions": [],
      "effects": []
    }
  ],
  "verify_routes": [],
  "leads_to": [],
  "related_task_ids": [],
  "miss_recovery": "错过原件后可从照片题字和乳母证词交叉验证"
}
```

规则：

- 每条主线关键线索至少有两种获得方式。
- `meaning` 只给规则引擎、复盘和可选单机 GM，不直接展示。
- 线索正文和系统意义分开，避免玩家一拾取就直接读到真相。
- 线索被毁、NPC 死亡或地点封锁时必须存在更昂贵的替代路线。

## 12. 伏笔 `foreshadowing`

只有会影响后文的场景细节才进入伏笔表。

```json
{
  "foreshadow_id": "foreshadow_extra_person_photo",
  "setup_storylet_ids": ["storylet_photo_studio_first_visit"],
  "setup_fact": "合照中比现场多出一个被刮去脸的人",
  "payoff_storylet_ids": ["storylet_reveal_mirror_guest"],
  "reveal_when": [],
  "related_clue_ids": [],
  "runtime_status": "unseeded"
}
```

运行状态：

```text
unseeded -> seeded -> noticed -> paid_off
                  -> invalidated
```

普通对话、气氛和一次性动作不写入伏笔表。运行时如果某个临时细节需要影响后文，规则引擎只能把它升级为内容包预先允许的开放伏笔槽，不能无限增加未知世界规则。

## 13. 剧情原住民 `cast`

```json
{
  "character_id": "shen_master",
  "type": "native_npc",
  "public_profile": "沈宅主人",
  "private_goal": "完成身份侵占仪式",
  "behavior_rules": [],
  "state_variants": [],
  "storylet_links": []
}
```

每名剧情原住民需要稳定 id、公开身份、私密目标、状态变体、行为优先级和故事节点关联。原住民可以合作、欺骗、背叛、逃离或死亡，但始终是副本世界中的人物，不是任务者，也不能持有玩家账户资产。

## 14. 怪物生态 `encounters`

固定副本继续使用普通怪、精英怪和 Boss 层级，但行为必须结构化。

```json
{
  "entity_id": "mirror_servant",
  "tier": "common",
  "territory_ids": ["mirror_corridor"],
  "signs": [],
  "activate_when": [],
  "behavior_rules": [],
  "counterplay": [],
  "defeat_or_escape_effects": [],
  "ecology_links": []
}
```

Boss 至少具有两条非正面击杀处理路线。每条路线必须引用真实线索、状态条件、执行步骤和失败代价。

## 15. 威胁时钟 `clocks`

```json
{
  "clock_id": "identity_erasure",
  "title": "身份抹除",
  "max": 6,
  "visibility": "hidden",
  "tick_conditions": [],
  "threshold_effects": {
    "2": [],
    "4": [],
    "6": []
  },
  "reduction_routes": []
}
```

每次推进和降低都必须来自规则事件。场景文本不能单独改变时钟。

## 16. 故事节点 `storylets`

固定副本不使用一棵从 A 分到 B/C、再无限分裂的巨大剧情树，而使用满足条件即可触发的故事节点。

```json
{
  "storylet_id": "storylet_photo_studio_first_visit",
  "phase": "investigation",
  "priority": 60,
  "once": true,
  "location_ids": ["photo_studio"],
  "visibility": "scene_group",
  "prerequisites": [],
  "triggers": [
    {
      "action_types": ["investigate"],
      "target_ids": ["old_family_photo"]
    }
  ],
  "text_variants": [
    {
      "when": [],
      "text_id": "storylet.photo.first.default"
    }
  ],
  "effects": [],
  "unlock_storylet_ids": [],
  "seed_foreshadow_ids": ["foreshadow_extra_person_photo"],
  "fail_forward": null
}
```

### 节点选择顺序

1. 过滤当前地点和场景组不可见节点。
2. 过滤未满足前置条件的节点。
3. 匹配本轮结构化行动和状态触发。
4. 按 `priority` 排序。
5. 先执行必须响应的直接结果，再执行环境和时钟连锁。
6. 同一批效果在一个事务中写入。
7. 产生带 sequence 的房间事件。

### 节点必须有确定结果

每个可执行节点至少产生一种效果：

- 状态变化。
- 线索发现或验证。
- 任务推进。
- 地点开放或封锁。
- NPC/怪物状态变化。
- 威胁时钟变化。
- 仅叙事反馈但明确标记为不推进。

## 17. 自由文本与动作别名

内容包为可交互对象定义动作别名：

```json
{
  "target_id": "mirror_east_room",
  "noun_aliases": ["镜子", "梳妆镜", "铜镜", "镜面"],
  "action_aliases": {
    "investigate": ["看", "检查", "照", "摸边框", "看背面"],
    "interact": ["掀红布", "盖住", "转过去"],
    "attack": ["砸", "劈", "打碎"]
  },
  "method_aliases": {
    "flashlight": ["手电", "照明"],
    "reflection_test": ["照自己", "看倒影"]
  }
}
```

通用解析器负责行动类型，内容包负责识别当前故事里的对象和特殊手段。推荐选项直接使用同一套 target/action/method id。

无法唯一识别时返回澄清，不触发故事节点。没有任何节点匹配的合法行动仍可执行通用规则，例如移动、普通观察、交谈、休整、战斗或使用道具。

## 18. 预写文本 `text_catalog`

文本与规则 id 分离：

```json
{
  "storylet.photo.first.default": "你把相框从墙上取下……",
  "storylet.photo.first.after_warning": "在沈老爷的脚步声逼近时……"
}
```

文本允许稳定变量：

```text
{{member.display_name}}
{{partner.display_name}}
{{location.title}}
{{clock.public_stage}}
```

禁止把隐藏状态或 API 配置作为可插值变量。

文本应覆盖：

- 首次触发。
- 已发现线索后的不同理解。
- 关键 NPC 存活/死亡差异。
- 高威胁阶段变化。
- 失败推进。
- 结局正文。

不要求为无关状态组合重复写全文，可以使用短前缀、主体和后果片段组合。

## 19. 结局 `endings`

```json
{
  "ending_id": "true_name_restored",
  "tier": "hidden_good",
  "title": "姓名归还",
  "requirements": [],
  "forbidden_states": [],
  "priority": 100,
  "text_id": "ending.true_name_restored",
  "settlement_tags": ["hidden_ending", "boss_released", "low_loss"],
  "reward_table_id": "reward_shen_manor_true"
}
```

如果同时满足多个结局，按 priority 选择主结局，其余可以作为已完成隐藏目标计入评级，但不能同时播放互相矛盾的结局。

## 20. 结算 `settlement`

固定副本只提供结算证据和奖励表引用，不自行修改钱包。

```json
{
  "rating_evidence": {
    "mainline": [],
    "side_quests": [],
    "hidden_side_quests": [],
    "hidden_endings": [],
    "special_achievements": [],
    "loss_control": []
  },
  "reward_tables": {}
}
```

每名持久玩家分别结算。剧情原住民的生死只在内容包明确关联支线或隐藏结局时提供结算证据，不拥有玩家钱包。

## 21. AI GM 单机适配

单机 AI GM 可以读取：

- 当前阶段大纲。
- 当前场景相关地点和人物。
- 已发现线索和本阶段可触发线索。
- 当前怪物/时钟相关规则。
- 已埋下未回收的伏笔。
- 最近剧情摘要和规则层上轮结果。

它不应每轮读取作者底稿全文，也不应看到与当前阶段无关的全部结局文本。

AI GM 可以生成具体过程、环境和对话，但不能改写 `canon.core_truth`、线索引用、结局条件和权威状态。新增临时细节默认只留在近期剧情；只有匹配开放伏笔槽时才能进入长期状态。

## 22. 内容校验

发布固定副本前至少检查：

- 所有 id 唯一，所有引用存在。
- 主线从开场到至少一个通关结局可达。
- 每条主线关键线索至少有两种获取方式。
- 关键 NPC 死亡或线索被毁后仍有 fail-forward。
- 每条伏笔有可达回收节点，或明确允许失效。
- 每个威胁时钟到达上限都有确定后果。
- 每个 Boss 至少有两条可执行的非正面处理路线。
- 每个故事阶段至少有一个推进节点和一个失败推进节点。
- 所有支持的小队数量都能分配必需身份，且不存在依赖缺席玩家才能触发的推进节点。
- 自由行动的目标和特殊物件具有动作别名。
- 所有结局条件可以由规则状态计算，不依赖人工理解长文本。
- 相同版本、seed 和行动序列产生相同权威状态。

## 23. 内容版本升级

- 已开始的房间继续使用创建时锁定的 `content_version`。
- 只改错别字且不影响规则时可以更新文本资源版本，但必须保留旧文本可回放。
- 修改节点条件、线索引用、地图或结局属于规则版本升级。
- 删除 id 前必须确认没有活动房间或归档仍引用它。
- 归档至少保存实例 id、内容版本、seed、行动序列和最终状态摘要。
