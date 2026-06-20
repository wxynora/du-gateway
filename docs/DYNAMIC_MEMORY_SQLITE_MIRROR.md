# Dynamic Memory SQLite Mirror

这份文档记录动态记忆 SQLite mirror 的边界。第一阶段只做“可搜索复印件”和关键词索引，不改变聊天召回主链路。

## 结论

- R2 `dynamic_memory/current.json` 仍是唯一权威原件。
- SQLite `data/dynamic_memory_mirror.sqlite3` 是可重建副本。
- 同步方向只能是 `R2 -> SQLite`，禁止 `SQLite -> R2`。
- SQLite 第一阶段只服务查询、展示、关键词覆盖率和排查。
- 聊天注入、DS `new/merge/skip`、`mention_count` 回写、core cache 提拔都不读 SQLite。

## 文件

- `config.py`
  - `DYNAMIC_MEMORY_MIRROR_DB`
  - `DYNAMIC_MEMORY_MIRROR_ENABLED`
  - `DYNAMIC_MEMORY_MIRROR_READ_FOR_CHAT`
  - `DYNAMIC_MEMORY_KEYWORD_BACKFILL_DRY_RUN`
  - `DYNAMIC_MEMORY_KEYWORD_MAX_TERMS`
- `storage/dynamic_memory_mirror_store.py`
  - SQLite schema、R2 快照 hash、items、terms、FTS、sync_runs。
- `services/dynamic_memory_keywords.py`
  - 规则关键词抽取，不调用 DS，不改写记忆正文。
- `scripts/backfill_dynamic_memory_keywords.py`
  - 一次性从 R2 current 读取动态记忆并写入 SQLite mirror。

## 表

- `dynamic_memory_items`
  - 每条动态记忆的可查询副本：`memory_id/content/retrieval_text/tag/importance/mention_count/last_mentioned/content_hash/raw_json`。
- `dynamic_memory_terms`
  - 每条记忆的关键词：`term/normalized_term/source/weight/confidence`。
- `dynamic_memory_fts`
  - FTS5 全文索引，辅助英文、模型名、长文本搜索；中文核心仍靠关键词表。
- `mirror_meta`
  - `source_snapshot_hash/ids_hash/memory_count/last_synced_at`。
- `sync_runs`
  - 每次 backfill/sync 的结果和错误。
- `memory_keyword_overrides`
  - 预留手动关键词覆盖，第一阶段不接 UI。

## Backfill

默认 dry-run，不写 SQLite：

```bash
.venv/bin/python scripts/backfill_dynamic_memory_keywords.py
```

写入 SQLite mirror：

```bash
.venv/bin/python scripts/backfill_dynamic_memory_keywords.py --write
```

查看状态：

```bash
.venv/bin/python scripts/backfill_dynamic_memory_keywords.py --status
```

列出镜像：

```bash
.venv/bin/python scripts/backfill_dynamic_memory_keywords.py --list --limit 20
```

## MiniApp 排查接口

第二阶段只接调试面板，不接聊天召回：

- `GET /miniapp-api/dynamic-memory-mirror?limit=20`
  - 返回 mirror 状态、active/inactive/term 数量、最近同步信息、最近若干条记忆及关键词。
  - 前端会瘦身掉 `raw_json`，避免调试页 payload 变大。
- `POST /miniapp-api/dynamic-memory-mirror/backfill`
  - body: `{"write": true, "max_terms": 32}`
  - 从 R2 current 读取动态记忆，抽关键词后写 SQLite mirror。
  - 返回 `r2_write=false`；这个接口不写 R2。

MiniApp 入口在 `miniapp/src/ui/tabs/MemoryDebugTab.tsx` 的“动态记忆”tab，显示 mirror/R2 条数、关键词数、最后同步时间、快照 hash 和最近几条关键词。

## Shadow Compare

第三阶段只写调试信息，不影响回复：

- `pipeline/pipeline.py::step_inject_dynamic_memory` 仍按原来的 R2 + 向量 + BM25 流程决定真实注入。
- SQLite mirror 只在 debug 侧运行 `shadow_candidates()`，返回候选 `memory_id`。
- `dynamic_memory/recall_debug.json` 的事件会多一个 `sqlite_shadow` 字段：
  - `candidate_ids`：SQLite 关键词索引命中的候选。
  - `actual_ids`：本轮真实注入的记忆 id。
  - `overlap_ids`：两边都命中的 id。
  - `missed_actual_ids`：真实注入了但 SQLite 没命中的 id。
  - `stale_candidate_ids`：SQLite 命中了但当前有效 R2 动态记忆里没有的 id。
  - `candidates`：候选预览、分数、命中词。
- 如果 mirror DB 不存在，shadow 不会自动创建空库，只记录 `mirror_db_missing`。
- `DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED=0` 可关闭 shadow compare。
- Shadow 过滤会把 `tag/emotion_label/scene_type/target_type` 这类低信号标签降权；`拒绝/不行/老婆说` 等泛词不作为候选依据；最终候选至少需要高信号词命中，或足够高的综合分。

MiniApp 的自动召回卡片会显示 SQLite shadow 的 hit/miss/stale 和候选关键词。

## 安全边界

第一阶段绝不能改：

- `dynamic_memory/current.json` 顶层结构。
- 每条记忆的 `id/content/retrieval_text/tag/importance/mention_count/created_at/last_mentioned`。
- 动态层 DS 输出协议。
- `pipeline/pipeline.py::step_inject_dynamic_memory` 注入顺序。
- core cache 提拔逻辑。
- 向量索引写入逻辑。
- `[memory n]` citation map。

## 退回 R2 的条件

以后如果把 SQLite 作为候选源，遇到这些情况必须退回 R2：

- SQLite 不可读、锁住、损坏。
- `source_snapshot_hash` 与当前 R2 快照不一致。
- `ids_hash` 或 `memory_count` 不一致。
- mirror 超过 staleness 阈值。
- SQLite 返回的候选 id 在 R2 current 中找不到。
- `raw_json` 解析失败或缺少 `id/content/tag/last_mentioned`。

第一阶段聊天链路不读 SQLite，所以回滚只需要关开关或删除 `data/dynamic_memory_mirror.sqlite3`。

## 验证

```bash
PYTHONPYCACHEPREFIX=/tmp/du-gateway-pycache .venv/bin/python -m py_compile \
  config.py \
  services/dynamic_memory_keywords.py \
  storage/dynamic_memory_mirror_store.py \
  scripts/backfill_dynamic_memory_keywords.py \
  scripts/test_dynamic_memory_mirror.py

PYTHONPYCACHEPREFIX=/tmp/du-gateway-pycache .venv/bin/python scripts/test_dynamic_memory_mirror.py
```
