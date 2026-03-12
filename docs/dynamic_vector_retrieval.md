## 动态层向量检索改造（落地说明）

### 目标

- **不改**现有权重公式（`importance + mention_count - time_decay`）。
- 只把“候选集召回方式”从关键词升级为：**向量召回 topK → 用现有 weight 重排 topN**。
- 未配置 Cloudflare 向量配置或向量接口失败时，**自动降级**为关键词匹配（不影响线上稳定性）。

### 存储约定（R2）

- 动态层 embeddings 索引：`dynamic_memory/embeddings/{tag}.embeddings.json`
- 每条记录包含：
  - `memory_id`
  - `text`
  - `embedding`（float[]）
  - `content_hash`（sha256）
  - `metadata`（用于调试/兜底）

### 新增代码目录

- `memory_vector/embedding_client.py`：把文本变成向量（HTTP 调用 OpenAI embeddings，失败重试一次）
- `memory_vector/embedding_client.py`：把文本变成向量（优先 Cloudflare Workers AI embeddings；失败重试一次）
- `memory_vector/cosine.py`：余弦相似度
- `memory_vector/vector_index_store.py`：R2 上 embeddings JSON 的 load/save/upsert
- `memory_vector/dynamic_vector_retriever.py`：两阶段检索入口 `dynamic_vector_retrieve(query, tag=None)`
- `memory_vector/rebuild_index.py`：全量重建索引脚本（建议首次上线跑一次）

### 接入点

动态层注入在 `pipeline/pipeline.py` 的 `step_inject_dynamic_memory`：

- 优先尝试 `dynamic_vector_retrieve(last_user_text)`
- 若失败/无结果：回退到原有关键词召回逻辑

### 配置（环境变量）

- `CF_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`：不配置会自动降级
- `CF_EMBEDDING_MODEL`：默认 `@cf/baai/bge-m3`（多语言，中文效果好，成本低）
- `CF_EMBEDDING_POOLING`：默认 `cls`（更准；上线后不要随便切 pooling）
- `VECTOR_MIN_SIM`：默认 0.2
- `VECTOR_TOPK`：默认 50
- `VECTOR_TOPN`：默认 10

### 首次上线建议

1. 配好 `CF_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`
2. 全量重建索引：

```bash
python -m memory_vector.rebuild_index
```

