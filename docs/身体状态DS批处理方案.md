# 身体状态 DS 批处理方案

> 状态：已按当前架构实现。pending 与审计落运行 SQLite，不新增 R2 状态文件。
> 目标：把「体力/敏感度/占有欲/坏心值/隐性压强」从动态记忆 DS 中拆出，改成独立、低频、逐轮 delta 的身体状态评估链路。

当前代码入口：

- `services/du_body_evaluator.py`：批次调度、DS 调用、逐轮 apply、启动恢复。
- `storage/du_body_eval_store.py`：SQLite pending、lease、失败重试与审计。
- `pipeline/pipeline.py::step_run_post_archive_tasks()`：真实归档轮次登记入口。
- `services/pixel_home.py::apply_du_body_delta()`：统一数值应用与稳定幂等键。
- `storage/pixel_home_store.py::mutate_pixel_home_state()`：线程和同机进程锁内读改写。

## 背景

当前身体状态更新和动态记忆写入绑在一起：

- `services/dynamic_layer_ds.py`：同一个 DS prompt 同时判断动态记忆 `ACTION/new/merge/skip` 和 `BODY_*_DELTA`。
- `pipeline/pipeline.py::_step_dynamic_layer_evolve()`：拿 DS 决策后，先按 `ACTION` 写动态记忆，再调用 `_apply_dynamic_body_delta()` 写身体 delta。
- `services/pixel_home.py::apply_du_body_delta()`：把 `stamina/sensitivity/possessiveness/mischief/restraint_pressure` delta 应用到 `global/pixel_home_state.json`。

这导致一个问题：动态记忆 DS 空回、格式坏、重试失败、或者输出里漏了 `BODY_STAMINA_DELTA` 时，体力就不会变化。另一方面，体力还有自然恢复：

- `services/pixel_home.py::DU_BODY_STAMINA_RECOVERY_LOW_RATE_PER_HOUR = 24.0`
- `services/pixel_home.py::DU_BODY_STAMINA_RECOVERY_MID_RATE_PER_HOUR = 18.0`
- `services/pixel_home.py::DU_BODY_STAMINA_RECOVERY_HIGH_RATE_PER_HOUR = 12.0`

当 DS 漏扣体力，或者扣得太小，后续自然恢复会很快把体力顶回满值。

## 目标

新增一个独立的「身体状态 DS evaluator」：

1. 不再每轮调用。
2. 每个窗口攒到约 4 轮后批量调用一次。
3. DS 必须逐轮输出 delta，不允许只输出整批总和。
4. 后端按 round 顺序逐条 apply。
5. 单独记录审计，能看到每轮 before/delta/after/recovery/原因。
6. 不干扰动态记忆写入、实时总结、压缩移位、R2 会话存档。
7. 支持失败重试和进程崩溃恢复，不重复扣/加同一轮身体数值。

## 非目标

本方案不做这些事：

- 不重写动态记忆系统。
- 不改变实时层总结频率。
- 不改变动态记忆 new/merge/skip/淘汰计数。
- 不让渡在小家隐藏标记里直接写 `stamina_value`。
- 不把身体状态变成前端手动状态的替代品。
- 不把身体状态 DS 的失败当成聊天失败。
- 不对历史所有轮次重跑，除非另写一次性修复脚本。

## 现有边界

### 不碰总结计数

身体状态 DS 只能读取已经归档的真实轮次，不能写这些东西：

```text
summary_chunks
summary update_count
dynamic_memory/current.json
dynamic_memory/ds_audit.json
```

也不能调用实时总结生成、压缩移位、淘汰逻辑。

这条是硬边界：身体状态是小家状态流水，不是记忆总结的一部分。它失败、重试、补跑，都不应该改变下一次是“光总结”还是“总结+压缩移位”。

### 不能重新绑回动态记忆

现有代码已经把两个 skip 拆开：

- `skip_dynamic_memory_write`
- `skip_body_delta`

当前含义应该继续保留：

- `skip_dynamic_memory_write=True, skip_body_delta=False`：不写动态记忆，但身体状态仍可更新。
- `skip_dynamic_memory_write=True, skip_body_delta=True`：动态记忆和身体状态都跳过。

新方案不能把 BODY 更新重新绑回动态记忆早退逻辑。

### 文游/游戏工具回合仍应跳过

现有 `pipeline/pipeline.py::_wenyou_round_skip_dynamic()` 会跳过文游虚构回合。

游戏工具回合现在会设置 `skip_body_delta`，例如 `routes/chat.py` 中 `game_tool_used` 后：

```python
archive_skip_body_delta = skip_post_archive_body_delta or game_tool_used
```

新链路应沿用这个跳过边界，避免把文游/游戏剧情当作真实小家身体状态。

## 推荐架构

新增模块：

```text
services/du_body_evaluator.py
storage/du_body_eval_store.py
```

可选测试：

```text
scripts/test_du_body_evaluator.py
```

保留现有状态应用入口：

```text
services/pixel_home.py::apply_du_body_delta()
```

不要直接在新 evaluator 里手写状态加减规则，最终状态写入仍统一走 `apply_du_body_delta()`，避免两套 clamp/default/recovery 逻辑。

不过落地时建议给 PixelHome store 补一个锁内 `read-modify-write` helper：

```text
mutate_pixel_home_state(mutator)
```

原因是小家手动道具、隐藏标记、身体 DS 都会改 `du_body_state`。如果还是各自读一份旧状态再保存，容易出现“DS 刚扣了体力，手动道具保存又用旧快照覆盖回去”的并发问题。

这个 helper 只负责原子保存，不改变业务含义。

## 调度位置

在 `pipeline/pipeline.py::step_run_post_archive_tasks()` 里新增一个轻量登记步骤：

```python
if not skip_body_delta:
    du_body_evaluator.enqueue_round(window_id, round_index, round_messages)
```

建议放在动态层调用前后都可以，但不要阻塞主存档。更推荐顺序：

1. 实时层总结调度保持原样。
2. enqueue 身体状态 pending。
3. 若 pending 满 4 轮，起后台线程跑身体 evaluator。
4. 动态层记忆逻辑保持原样。

关键：身体 evaluator 的失败不影响 `_step_dynamic_layer_evolve()`。

## 批处理规则

默认配置：

```text
DU_BODY_EVAL_BATCH_SIZE=4
DU_BODY_EVAL_MAX_PENDING=12
DU_BODY_EVAL_MAX_ATTEMPTS=3
DU_BODY_EVAL_AUDIT_KEEP=300
```

触发条件：

- 当前窗口 pending 轮数 >= 4。
- 或 pending 最旧轮次超过一个宽限时间，例如 30 分钟。

宽限时间不是为了每条都跑，而是避免一晚上只聊 1-3 轮时永远不评估。

## 运行状态结构

当前不新增 R2 key。运行 SQLite 使用两张表：

```text
du_body_eval_pending
du_body_eval_audit
```

`pending` 暂存尚未处理的已清洗真实轮次，成功或判定无变化后立即删除；失败保留并按 lease/attempts 重试。`audit` 只保存 round/hash、before/delta/after、原因和状态，不保存完整对话，并按最近 300 条限量。最终身体状态仍沿用 `global/pixel_home_state.json`，幂等键与状态同次写入。

## 幂等策略

每个 round 最多 apply 一次。

每轮生成稳定幂等键：

```text
body_delta:{window_id}:{round_index}:{round_hash}:{prompt_version}
```

说明：

- `window_id`：窗口。
- `round_index`：轮次。
- `round_hash`：从归档 round 的关键内容算 hash，避免同一轮内容被修复后还误认为同一次。
- `prompt_version`：身体 DS prompt 版本，后续换规则时能区分。

状态机：

```text
pending -> processing -> applied / already_applied / no_delta / shadow / skipped / failed
```

审计事件和 state 都要记录：

```text
window_id
round_index
round_hash
prompt_version
idempotency_key
batch_id
status
applied_at
```

执行前检查：

1. 如果该 `idempotency_key` 已在 SQLite 审计或 PixelHome 的近期已应用键中出现，跳过。
2. 如果 pending 里同一轮重复出现，只保留一条。
3. 如果 DS 重试后成功，按成功结果 apply。
4. 如果 DS 失败，pending 保留，`attempts += 1`。
5. 如果 attempts 超过上限，标记 `failed`，不再自动重跑，除非管理端手动 reset。

更稳的做法：在 `pixel_home_state.json -> du_body_state` 里维护一个 bounded 列表：

```json
{
  "du_body_delta_applied_ids": [
    "body_delta:tg_8260066512:11801:sha256...:v1"
  ]
}
```

保留最近 100-300 条即可。

原因：R2 审计和 PixelHome 状态不是事务。如果进程崩在“apply 后、写 audit 前”，只靠 audit 会导致重试时重复 apply。把最近幂等键跟当前状态一起写，能挡住这类重复扣数。

## DS 输出格式

建议用 JSON，避免固定标签批量解析又被尾巴截断。

输入给 DS：

```json
{
  "current_body_state": {
    "stamina_value": 88,
    "sensitivity_value": 79,
    "possessiveness_value": 83,
    "mischief_value": 100,
    "restraint_pressure_value": 42
  },
  "rounds": [
    {
      "round_index": 11801,
      "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
      ]
    }
  ]
}
```

输出：

```json
{
  "items": [
    {
      "round_index": 11801,
      "stamina_delta": -3,
      "sensitivity_delta": 4,
      "possessiveness_delta": 2,
      "mischief_delta": 0,
      "restraint_pressure_delta": -8,
      "reason": "持续亲密推进，有明显体力消耗，随后释放使隐性压强下降"
    }
  ]
}
```

要求：

- `items.length` 不必等于输入 rounds 数量；无变化的轮次可以不返回。
- 但如果返回了某个 `round_index`，必须是输入中的 round。
- 所有 delta 都是整数。
- 未变化字段可省略或写 0，后端归一化时去掉 0。
- 不允许输出总和字段，例如 `total_stamina_delta`。

## delta 限制

沿用现有范围：

```text
stamina: -6 到 6
sensitivity: -10 到 12
possessiveness: -12 到 12
mischief: -18 到 18
restraint_pressure: -35 到 30
```

归一化函数可以从现有逻辑迁出或复用：

- `services/dynamic_layer_ds.py::_BODY_DELTA_LIMITS`
- `services/pixel_home.py::DU_BODY_DELTA_LIMITS`
- `services/pixel_home.py::_normalize_du_body_delta_payload()`

落地时推荐把 delta 限制常量统一到一个小 helper，避免动态层和身体 evaluator 两边不一致。

## 应用顺序

后端必须按 `round_index` 升序 apply：

```text
11801 -> 11802 -> 11803 -> 11804
```

第一版建议批内只触发一次自然恢复，然后按顺序 apply 四轮 delta。

原因：`apply_du_body_delta()` 现在每次都会先调用 `_auto_recover_du_body_stamina()`。如果四轮在同一个 batch 内连续 apply，每轮都恢复一次，容易把体力扣减抵消掉。

注意：如果批处理在 01:20 才处理 00:10 的轮次，`apply_du_body_delta()` 会按当前时间自然恢复一次。这会使审计里的 before 受到延迟影响。方案落地有两个选择：

1. 简单版：接受当前时间恢复，先把稳定性做出来。
2. 精确版：给 `apply_du_body_delta()` 增加可选 `now_iso`，按每轮 timestamp 顺序模拟恢复。

第一阶段推荐简单版，避免扩大改动。

如果 pending 拖得太久，例如超过 6 小时，建议标记 `stale_pending`：

- 非 stamina 字段仍可按规则 apply。
- stamina delta 先不自动 apply，或降权 apply。
- 审计里写清 `skip_reason=stale_pending`。

这样可以避免半天前的体力扣减，在已经自然恢复很久后突然补扣造成错觉。

## 自动恢复调整

这次问题里体力满值的另一个原因是恢复过快。

建议第二阶段再调整恢复速度，不和 evaluator 第一版混在一起：

```text
75-100：每小时 +4 到 +6
50-75：每小时 +8 到 +10
0-50：每小时 +12 到 +16
```

也可以新增配置：

```text
DU_BODY_STAMINA_RECOVERY_HIGH_RATE_PER_HOUR
DU_BODY_STAMINA_RECOVERY_MID_RATE_PER_HOUR
DU_BODY_STAMINA_RECOVERY_LOW_RATE_PER_HOUR
```

当前代码里这三个是常量，落地时可先保持常量，后续再 env 化。

## 审计日志

SQLite `du_body_eval_audit` 的 `event_json` 记录：

```json
{
  "events": [
    {
      "audit_schema_version": 1,
      "timestamp": "2026-07-05T01:20:00+08:00",
      "subsystem": "body_state_delta",
      "prompt_version": "v1",
      "model": "deepseek-...",
      "window_id": "tg_8260066512",
      "round_index": 11801,
      "round_timestamp": "2026-07-05T00:10:31+08:00",
      "round_hash": "sha256:...",
      "batch_id": "body_tg_8260066512_11801_11804_20260705012000",
      "idempotency_key": "body_delta:tg_8260066512:11801:sha256...:v1",
      "source": "body_ds_batch",
      "status": "applied",
      "input_state_updated_at": "2026-07-05T01:19:59+08:00",
      "input_toy_snapshot": {
        "toy_types": ["vibration_ring"],
        "intensity": 3
      },
      "before": {
        "stamina_value": 91,
        "sensitivity_value": 70,
        "possessiveness_value": 80,
        "mischief_value": 88,
        "restraint_pressure_value": 50
      },
      "parsed_delta": {
        "stamina": -3,
        "sensitivity": 4,
        "possessiveness": 2,
        "restraint_pressure": -8
      },
      "clamped_delta": {
        "stamina": -3,
        "sensitivity": 4,
        "possessiveness": 2,
        "restraint_pressure": -8
      },
      "delta": {
        "stamina": -3,
        "sensitivity": 4,
        "possessiveness": 2,
        "restraint_pressure": -8
      },
      "recovery_applied": {
        "stamina_before_recovery": 90,
        "stamina_after_recovery": 91,
        "hours": 0.08
      },
      "after": {
        "stamina_value": 88,
        "sensitivity_value": 74,
        "possessiveness_value": 82,
        "mischief_value": 88,
        "restraint_pressure_value": 42
      },
      "reason": "持续亲密推进，有明显体力消耗，随后释放使隐性压强下降",
      "attempt": 1,
      "latency_ms": 1820,
      "applied_at": "2026-07-05T01:20:01+08:00"
    }
  ],
  "updated_at": "2026-07-05T01:20:00+08:00"
}
```

还要记录失败事件：

```json
{
  "status": "failed_parse",
  "raw_preview": "...",
  "attempt": 2,
  "error_class": "parse_error",
  "error_message": "items is not a list",
  "round_indices": [11801, 11802, 11803, 11804]
}
```

不要把完整私密对话写进 audit。audit 里最多放短 preview、hash、round_index。需要看全文时再按 `window_id + round_index` 去 R2 round 里查。

日志行建议：

```text
身体状态 DS batch 已调度 window_id=tg_8260066512 rounds=11801-11804
身体状态 DS batch 解析成功 window_id=tg_8260066512 batch_id=... items=3
身体状态 delta 已写入 window_id=tg_8260066512 round_index=11801 before_stamina=91 delta=-3 after_stamina=88
身体状态 DS batch 失败 window_id=tg_8260066512 batch_id=... issue=parse_error attempt=2
```

## 失败处理

失败时不要写默认 delta。

原因：

- 默认扣体力容易误伤普通聊天。
- 默认加减会成为新的污染源。

处理策略：

1. DS API 错误：pending 保留，attempts +1。
2. 结构解析失败：pending 保留，attempts +1。
3. 只返回部分 rounds：成功的先 apply，没返回的当作无变化并标记 `no_change`。
4. round 内容读不到：标记 `missing_round`，从 pending 移除，写 audit。
5. 超过最大 attempts：标记 `failed`，不阻塞后续新 batch。

## 与动态记忆 DS 的关系

第一阶段先不要删除动态层 prompt 里的 `BODY_*_DELTA`，但要让它不再 apply。

推荐落地步骤：

1. 新增 body evaluator 和 audit。
2. 在 `pipeline._step_dynamic_layer_evolve()` 中保留 DS 解析出的 `body_delta` 审计，但默认不调用 `_apply_dynamic_body_delta()`。
3. 或者新增开关：

```text
DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED=0
DU_BODY_EVALUATOR_ENABLED=1
```

这样可以灰度：

- 新 evaluator 稳定后，彻底从动态层 prompt 删除 BODY 段。
- 如果新 evaluator 出问题，能临时回退到旧 BODY delta。

注意：不能让旧动态层 BODY apply 和新 evaluator 同时生效。否则同一轮会被双算。

推荐灰度顺序：

1. `DU_BODY_EVALUATOR_SHADOW=1`：只跑新 DS，写 audit，不 apply。
2. shadow 稳定后，`DU_BODY_EVALUATOR_APPLY=1`。
3. 同时设置 `DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED=0`。
4. 观察一晚审计后，再删动态层 prompt 里的 BODY 段。

## 与小家手动道具状态的关系

小家手动道具仍走：

```text
routes/miniapp/dashboard.py::miniapp_pixel_home_du_body_state()
services/pixel_home.py::save_du_body_state()
```

新 evaluator 只处理数值 delta，不负责道具列表、位置、档位文案。

边界：

- `toy_types/intensity/position/state` 仍由手动设置和小家隐藏标记维护。
- body evaluator 不生成小家事件文案。
- 如果一轮里出现道具变化，body evaluator 可以根据那一轮内容改变 `sensitivity/stamina`，但不写道具字段。
- 如果手动校准和 DS delta 同时发生，两者都在同一把跨进程锁内读取最新状态后写入；手动道具字段与 DS 数值 delta 分开合并，不互相覆盖。

## 与前端的关系

第一阶段不要求新增前端。

最小可用只看日志和 SQLite audit。

第二阶段可以在 MiniApp 小家/记忆调试里加一个“身体数值审计”折叠区：

- 最近 20 条 delta。
- 每条显示 round_index、体力 before/delta/after、来源、reason。
- 支持按窗口过滤。

## 阶段拆分

### 阶段 1：Shadow，只新增 evaluator 和审计，不 apply（已具备开关）

改动范围：

```text
services/du_body_evaluator.py
storage/du_body_eval_store.py
pipeline/pipeline.py
services/pixel_home.py（最多只加 before/after helper，不改核心逻辑）
storage/r2_store.py（如选择把 audit helper 放这里）
```

验收：

- pending 满 4 轮后触发 body DS。
- DS 输出逐轮 delta。
- audit 能看到 parsed/clamped delta、round_hash、idempotency_key。
- 动态记忆 new/merge/skip 仍按原来跑。
- `skip_body_delta=True` 的回合不进入 pending。
- 小家身体状态不实际变化。

### 阶段 2：幂等 apply，关闭动态层 BODY apply（已实现）

改动范围：

```text
pipeline/pipeline.py
services/dynamic_layer_ds.py（可先不删 prompt，只不应用）
services/pixel_home.py（补 `du_body_delta_applied_ids` 幂等保护）
```

验收：

- 动态层 DS 即使输出 `BODY_*_DELTA`，也不会再改小家身体状态。
- body evaluator 是唯一自动数值来源。
- 同一轮重试、重复 batch、进程重启，都不会二次 apply。
- 手动道具字段不会被 DS delta 覆盖。

### 阶段 2.5：Pending worker 和 stale 处理（已实现）

改动范围：

```text
services/du_body_evaluator.py
storage/du_body_eval_store.py
```

验收：

- DS 失败后 pending 保留。
- 部分成功时，已 applied 的轮次不重跑，未处理轮次继续 pending。
- 超过最大 attempts 后标记 failed。
- 过久 pending 标记 stale，不偷偷按旧语义补扣 stamina。

### 阶段 3：调体力自然恢复

改动范围：

```text
services/pixel_home.py
```

验收：

- 高体力区恢复明显变慢。
- 连续亲密场景后不会几轮内自动回满。
- 休息/收尾仍能恢复，但不会瞬间满。

### 阶段 4：前端审计展示

改动范围：

```text
routes/miniapp/dashboard.py 或 memory_panel.py
miniapp/src/ui/tabs/PixelHomeTab.tsx 或 MemoryDebugTab.tsx
```

验收：

- 能看到最近 body delta。
- 默认折叠，不污染小家主界面。

## 测试清单

### 单元/smoke

1. DS 输出四轮，其中两轮有 delta，两轮无变化。
2. DS 输出重复 round_index，后端去重。
3. DS 输出不在输入里的 round_index，后端丢弃并审计。
4. DS 输出越界 delta，后端 clamp。
5. `skip_body_delta=True` 时不入 pending。
6. 文游/游戏工具回合不入 pending。
7. pending 满 4 轮触发 batch。
8. 不满 4 轮不触发，超过宽限时间可触发。
9. batch 失败后 pending 保留 attempts+1。
10. 同一 round 重跑不会二次 apply。
11. body batch 后 `summary_chunks.update_count` 不变。
12. body batch 后不写 `dynamic_memory/current.json`。
13. 手动改道具后 DS apply 不清 `toy_types/intensity/position/state`。
14. 进程崩在 apply 前/后，恢复后不重复扣数。
15. pending 超时后 stamina 不按旧上下文突然补扣。

### 线上验证

1. 查日志出现 `身体状态 DS batch 已调度`。
2. 查 SQLite `du_body_eval_audit` 有事件。
3. 小家体力不再长期假满。
4. 动态记忆 DS 审计仍正常。
5. 实时总结 4 轮计数不变。
6. 同一轮的 `idempotency_key` 只出现一次 `status=applied`。

## 当前建议

先做阶段 1 和阶段 2。

原因：

- 当前最大问题不是恢复速度，而是 body delta 被动态层 DS 拖丢。
- 先把来源拆干净，再调恢复速度，风险更小。
- 审计先上线，后面调数值才有依据。

恢复速度可以等审计跑一晚再改。否则现在凭感觉调，容易从“永动机”变成“动两下就趴”的另一个极端。
