# 历史记录归档流程说明

## 核心缓存层处理方案（实时 + 人工筛选）

实时对话里**不写记忆库 Notion**（只写卧室 Notion 房间、小本本工具）。流程如下：

```
动态层（R2 current.json）
       ↓ new/merge 时
核心缓存层（R2 core_cache/pending.json）
       ↓ 管理端 sync_to_notion（可选）
核心缓存待审（Notion 表 NOTION_CORE_CACHE_DATABASE_ID）
       ↓ 人工在 Notion 里筛选
长期层 / 记忆库（Notion 记忆库 或 四房间）
```

- **实时**：每轮 DS 决策后只更新动态层 R2 + promote 到核心缓存 R2；不写记忆库。卧室仍写 Notion 卧室页面，小本本仍可用工具写。
- **人工**：在 Notion「核心缓存待审」表里筛选，选中的再手动或后续脚本进长期层/记忆库。
- **批处理归档**：跑 `feed_conversation_for_memory.py` 时，动态层 + 核心缓存照常更新 R2，**同时**把卧室/new/merge 写入记忆库 Notion（由脚本在应用决策后调 `write_archive_entry`）。

---

## 整体流程

```
RikkaHub 导出 JSON
       ↓
rikkahub_export_to_feed.py  →  feed_input.json（rounds，含可选时间戳）
       ↓
feed_conversation_for_memory.py  逐轮跑
       ↓
每轮：清洗 → _step_dynamic_layer_evolve（动态层）
       ↓
DS 分类 + 决策（new/merge/skip，tag：书房/客厅/图书馆/卧室）
       ↓
┌──────────────────────────────────────────────────────────────┐
│ 卧室：不写动态层，把本轮原文（非 DS 的 content）写入 Notion 卧室；DS 仍写 content 供别处用。 │
│ 书房/客厅/图书馆：按 action 更新 R2 dynamic_memory/current.json │
│   - new：追加一条记忆（content/tag/importance/timestamp/mention_count/last_mentioned） │
│   - merge：找到 fused_with_id 对应的旧记忆，用 DS 返回的 content 覆盖，更新 last_mentioned 和 mention_count（+1） │
│   - skip：不写                                                 │
└──────────────────────────────────────────────────────────────┘
       ↓
核心缓存：new/merge 时会 promote_to_core_cache（与窗口原文关联，供后续长期层筛选）
```

---

## 1. 数据从哪来

- **RikkaHub 导出**：从 RikkaHub 导出的 JSON（例如桌面上的 `居家版渡.json`），结构是数组，每项有 `messages`（字符串化的消息数组）、`node_index` 等；每条消息里可有 `createdAt`（原始记录时间）。
- **转换脚本** `scripts/rikkahub_export_to_feed.py`：
  - 按 `node_index` 排序，相邻的 user + assistant 配成一轮。
  - 输出 `scripts/feed_input.json`，格式：`{ "window_id": "", "rounds": [ {"user": "...", "assistant": "..."}, ... ] }`。
  - 若导出里有 `createdAt`，可在这里解析并写入每轮，供归档时「按原始时间」存 R2/Notion。

---

## 2. 预喂脚本（归档执行入口）

- **脚本**：`scripts/feed_conversation_for_memory.py`
- **用法**：`python scripts/feed_conversation_for_memory.py [--window-id ""] [--batch-size 8] <input.json>`，一般用 `feed_input.json`。`--batch-size 8` 表示每 8 轮打成一个 DS 请求（用归档 prompt）。
- **做的事**：
  - 读取 `window_id` 和 `rounds`；本地预筛空轮（极短/纯嗯啊哦）不调 DS。
  - **batch_size > 1**：非空轮按批打包，每批调 `call_archive_batch_ds`（读 `scripts/archive_ds_prompt.txt`），拿到决策数组后逐条 `_apply_one_decision`。
  - **batch_size == 1**：逐轮调 `_step_dynamic_layer_evolve`（网关单轮 DS），只跑动态层和卧室 Notion。
  - 不写窗口存档、不做每 4 轮总结。

---

## 3. 动态层一步（pipeline）

- **函数**：`pipeline.pipeline._step_dynamic_layer_evolve(window_id, round_index, round_messages)`
- **步骤**：
  1. 从 R2 读 `dynamic_memory/current.json`，得到当前记忆列表，并补全每条 `id`。
  2. 调用 DS：把「当前记忆列表」+「本轮对话」发给 DS，拿到一条决策（tag、action、content、fused_with_id 等；归档模式下还有 timestamp、mention_count、last_mentioned）。
  3. **卧室**：若 `tag === "卧室"`，不写动态层，把**本轮原文**（`_round_messages_to_raw_text`）通过 `append_bedroom_raw` 写入 Notion 卧室（不存 DS 的 content；DS 仍写 content 供别处用），然后 return。
  4. **书房/客厅/图书馆**：
     - **new**：生成新 id，追加一条记忆（content、importance、tag、mention_count、created_at、last_mentioned），写回 R2，并 `promote_to_core_cache`。
     - **merge**：找到 `fused_with_id` 对应的旧记忆，用 DS 返回的 content 覆盖，更新 `last_mentioned` 和 `mention_count`（+1），写回 R2，并 `promote_to_core_cache`。
     - **skip**：不写。

当前实现里，时间用的是「当前时间」`now_beijing_iso()`；归档模式要改成用「本条记录的原始时间」（由 DS 返回的 timestamp，或从输入 round 里传入）。

---

## 4. DS 与 prompt

- **正常对话**：用 `services/dynamic_layer_ds.py` 里的 `_DYNAMIC_LAYER_PROMPT`，`call_dynamic_layer_ds(round_messages, current_memories)` 返回 tag、action、importance、content、fused_with_id。
- **归档脚本**：用 `scripts/archive_ds_prompt.txt` 的 prompt（批处理多轮版）；DS 返回 `timestamp`、`mention_count`、`last_mentioned` 等。脚本批处理时调用 `call_archive_batch_ds` 读该文件发请求；卧室存**本轮原文**到 Notion，不存 DS 的 content。

---

## 5. R2 里和归档相关的 key

- **dynamic_memory/current.json**：动态层记忆列表，每条有 id、content、tag、importance、mention_count、created_at、last_mentioned 等；归档时这些字段应用「原始时间」和归档约定初始值。
- **core_cache/pending.json**：核心缓存，new/merge 时会把本轮原文与 touched 记忆关联，供后续长期层筛选。
- 卧室原文不写进动态层，只进 Notion（通过 `append_bedroom_raw`）。

---

## 6. 分批怎么跑

- 代码里没有限制「单次最多多少条」；实际受 DS 上下文（当前记忆列表会随轮数变长）和接口限流影响。
- 建议每批几百～一两千条；多批时：第一批跑完后**不要清空 R2**，下一批用新的 `feed_input.json`（或新 rounds）再跑同一脚本，会接着现有动态层继续跑。
- 若需「先清空再跑」：执行 `python scripts/wipe_r2_only.py`（只清 R2，不动本地）。

---

## 7. 尚未接好的部分（归档专用）

- 转换或 feed 输入里带**每轮原始时间**（如从导出 `createdAt` 解析），并传给 `_step_dynamic_layer_evolve` 或 DS 入参。
- 归档跑时改用 **archive_ds_prompt**，并解析 DS 返回的 timestamp、mention_count、last_mentioned；写 R2 时用这些值，且动态层按时间排序。
- 卧室：原文按「该条记录原始时间」存到 Notion（若 Notion API 支持带时间则带上，否则至少逻辑上按轮顺序对应原始时间）。

以上即当前「历史记录归档」从导出到 R2/Notion 的完整流程。
