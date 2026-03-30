# Claude Code 与 Telegram 记忆连续方案

本文汇总「在 Claude Code（CC）与 Telegram 之间切换时，仍保持与渡的对话连续感」的产品与技术方案，并与 **du-gateway 现状**对齐。

---

## 1. 目标

- **同一套常驻记忆池**：CC 与 TG 共用 R2 上的**总结**与**动态层**，不各记各的。
- **读**：CC 启动或开新任务前能拉到与 TG 一致的上下文。
- **写**：CC 侧可把重要进展写回记忆池，TG 下一轮聊天能通过现有管道看到。
- **不要求**：与 TG 完全同频的实时更新；也不要 **Sense / 设备感知**（本方案不纳入 `sense/latest`）。

---

## 2. 网关里「常驻记忆」指什么

| 能力 | R2 / 逻辑 | 聊天管道中的注入 |
|------|-----------|------------------|
| **总结（渡的回忆）** | `global/summary.txt` 等，按 `window_id` 存 | `step_inject_summary` |
| **动态层** | `dynamic_memory/current.json` 的 `memories` | `step_inject_dynamic_memory` |
| **Sense** | `sense/latest.json` | `step_inject_sense_snapshot` |

本方案只覆盖前两项。

---

## 3. 读：CC / MCP 如何拉取（复用现网 HTTP）

无需为对齐虚构路径再造 `/api/memory/*`。

| 数据 | 方法 | 现成路径 | 说明 |
|------|------|----------|------|
| 总结 | GET | `/summary` | 与 `GET /admin/summary` 同源；当前根接口使用 **空窗口** `window_id=""` |
| 动态层 | GET | `/dynamic-memory` | 与 `GET /admin/dynamic-memory` 同源；返回 `memories` 数组 |

MCP 工具 **`get_context`** 建议合并上述两次请求，输出例如：

- `summary`：正文或 `null`
- `memories`：由 `memories[].content` 或整对象组成（实现时自行约定）

**窗口 ID**：若日后总结按窗口分桶使用，读写的 `window_id` 必须与 TG 主会话一致；当前若统一用全局总结，则与 **`""`** 对齐即可。

---

## 4. 写：动态层（必做，连续感主路径）

### 4.1 行为

- 向 **`dynamic_memory/current.json`** 的 **`memories`** 列表 **追加一条**，与 Telegram 侧动态层是**同一份数据**。

### 4.2 字段建议（与现网结构一致）

便于过期、展示与向量召回：

- `id`：UUID  
- `content`：文本  
- `importance`：整数（可与 MCP 的 high/medium/low 映射）  
- `tag`：如固定 `CC` / `开发`  
- `mention_count`、`created_at`、`last_mentioned`：与 pipeline 里 DS 写入风格一致（时间用北京时间 ISO）

### 4.3 与检索一致

若线上启用了动态层向量召回，追加后应执行与 pipeline 相同的 **embedding 索引更新**（如 `_upsert_dynamic_memory_index`），否则会出现「列表里有但搜不到」的断裂。

### 4.4 网关缺口

- 目前有 **GET** 动态层，**没有**面向外部的 **POST 追加单条** HTTP。
- 实现阶段需新增 **带鉴权** 的写接口（路径自定），内部：`get_dynamic_memory_list` → append → `save_dynamic_memory_list` → 索引 upsert。

MCP 工具 **`save_memory`** 调用该 POST；body 至少 `content`，可选 `importance` / `tag`。

---

## 5. 写：窗口总结（可选增强）

### 5.1 能不能更新

**能。** 服务端已有 `save_summary(window_id, text)`。不要求与 TG「每 N 轮 DS 融合」同频。

### 5.2 与 TG 总结如何衔接

TG 侧下次触发总结时，会把 **`get_summary(window_id)` 的当前全文** 作为 `current` 传入 `fetch_new_summary`，再与近期对话轮次融合后写回。因此 CC 写入或 **在文末追加一段「CC 备忘」** 会进入下一轮总结的上下文，**有利于**跨端连续。

### 5.3 建议策略

- **动态层**：适合离散事实（「完成了某重构」）。  
- **总结**：长文叙事；CC 侧优先 **短增量 append**，避免整篇覆盖冲掉长期风格。  
- **网关缺口**：HTTP 上目前主要是 **GET** 总结，需另增 **鉴权写接口**（内部调 `save_summary`）若要让 MCP 直接更新总结。

---

## 6. 安全

- 根路由 **`/summary`、`/dynamic-memory` 当前多为无 Token 可读**。若网关公网可访问，存在泄露风险。
- 建议：读、写统一 **Bearer Token**（环境变量配置），或仅内网 / VPN 访问；**具体路径与 `DU_MCP_API_TOKEN` 类命名实现时再定**。

---

## 7. MCP 与编辑器（实现参考）

- **本地 MCP**（Node + `@modelcontextprotocol/sdk`）：通常 **stdio** 与 CC/VS Code 对接；由 MCP 使用环境变量中的 **`DU_GATEWAY_BASE_URL`** 与 Token 调网关。
- 工具划分：
  1. **`get_context`**：GET `/summary` + `/dynamic-memory`，无 sense。  
  2. **`save_memory`**：POST 动态层追加（待网关接口）。  
  3. **`get_files`**（可选）：仅本地工作区，与网关无关。
- 可选：项目根 **`CLAUDE.md`** 约定「新任务前先 `get_context`、重要节点 `save_memory`」等行为，与渡的人设说明放一起。

---

## 8. 开发顺序建议

1. 网关：鉴权 + **POST 追加动态层**（必做）。  
2. MCP：`get_context` + `save_memory` 打通联调。  
3. 可选：网关 **POST/PATCH 总结**（append 或整段替换策略定好再做）。  
4. 加固：对 **`/summary`、`/dynamic-memory` 的 GET** 是否也要求 Token（与写接口一致）。  
5. 写 `CLAUDE.md`、配置编辑器 MCP 项，实际 TG ↔ CC 切换体验验收。

---

## 9. 小结

| 项目 | 结论 |
|------|------|
| Sense | 本方案不包含 |
| 读总结 + 读动态层 | 直接用现有 **`/summary`、`/dynamic-memory`** |
| 写动态层 | **需新接口**；连续感主依赖 |
| 写总结 | **可选**；低频或 append 即可，与 TG 总结逻辑可衔接 |
| 实时性 | 不要求与 TG 同频，保证**同池、能写回**即可 |

文档版本：与 2026-03 对话结论对齐；实现以仓库代码为准。
