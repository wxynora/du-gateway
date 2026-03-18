# Telegram Mini App 运维面板：升级路线与意图说明

## 0. 为什么要做这个 Mini App
把“需要开电脑才能运维/排查”的能力搬到 **Telegram 内置浏览器（Mini App）**里：躺着就能看日志、看关键内容，并能做最小化的安全管理操作。

本文档用于让后续接手的 agent 能立刻理解：**你要升级什么、为什么这么做、第一版边界在哪里、后续怎么扩**。

## 1. 已实现的第一版（当前范围）
第一版只覆盖“三件事”，刻意避免扩散 Bug 风险：

1. 思维链展示（reasoning 折叠/收起）
2. 手机端看日志（末尾拉取 + SSE 实时，支持过滤与一键复制）
3. 上游中转站切换（全局立即生效，且只允许“切换 active”，不让手机端新增/删除 URL）

## 2. 关键设计约束（防 Bug + 防泄露）
### 2.1 鉴权
- 所有 `Mini App API` 均走双保险：
  - Telegram WebApp `initData` 校验
  - IP 白名单 allowlist（可选开启信任代理头）

### 2.2 上游切换（switch_only）
- 手机端不编辑 secrets，不新增/删除 URL 列表。
- `data/upstreams.json` 仅保存 `active`（items 由环境变量构建）。
- `routes/chat.py` 在转发前把 active 上游放到候选列表第一个，从而“全局生效”。

### 2.3 日志读取（file -> stdout fallback）
- 优先读 `gateway.log`（或 `MINIAPP_LOG_FILE` 指定文件）。
- 若文件不存在，则从进程内 ring buffer 读取（保证“无需开电脑也能看”）。
- SSE 流式输出会保持心跳，避免移动端代理断连。

### 2.4 reasoning 展示策略
- 网关在存档时尽量把上游字段 `reasoning | reasoning_content | thinking` 透传到 `assistant message` 上的 `reasoning` 字段。
- 前端在轮次详情里对 assistant message 的 `reasoning` 使用 `<details>` 默认折叠（不强制展开）。

## 3. 后续阶段升级（按难易度 + Bug 风险排序）
下面按实现难易度与 Bug 风险从低到高给出路线。建议严格按顺序推进，避免“还没稳定触发器就上复杂写入”。

### Phase 1（低风险）：日历组件 + 闹钟查看 + 取消（禁用）
目标：在手机端做到“看得清、能简单管理”。

需要提供：
- `日历/月视图/日程列表（只读）`
- `闹钟/提醒列表（只读 + 取消按钮）`
- 取消语义：**disable_future**（禁用该条目未来触发），避免“只取消某一次 occurrence”的复杂逻辑。

数据结构建议（R2 / r2_only）：
- `schedule/items.json`：条目列表（包含 enabled、repeat 等）
- `schedule/fired.json`：已触发去重记录（按 occurrence_key）

### Phase 2（中等风险）：AI 设定闹钟（写入 R2）
目标：聊天里让 AI “理解意图并写入 schedule”，而不是前端直接写。

建议做法：
- 给 chat 管道注入一组 `r2_schedule_*` 工具，让 AI 以结构化参数创建条目。
- 写入时做幂等（unique_key/source_round 等），避免模型重试导致重复条目。

### Phase 3（中高风险）：到点触发提醒（Telegram 发提醒）
目标：调度器到点向 Telegram 固定接收人发提醒。

触发要求：
- 固定接收人：使用项目现有 `TELEGRAM_PROACTIVE_TARGET_USER_ID`（不新增用户分发逻辑，降低并发 Bug）
- 时间口径：统一北京时间，保存与计算同一口径
- 去重：使用 `schedule/fired.json` 记录 occurrence_key，避免重复提醒
- enabled=false：取消后不会触发未来提醒

### Phase 4（中等风险）：可编辑“全局便签/系统提示”持续注入（防 AI 失忆）
目标：提供一个你可编辑的文本块（便签/近期重要事件记录），每次请求时注入到 prompt，降低 AI 忘记关键约束。

建议做法：
- R2 保存：`global/miniapp_notes.txt`（或等价命名）
- API：
  - `GET /miniapp-api/notes`
  - `PUT /miniapp-api/notes`
- Pipeline 注入：
  - 注入位置靠近系统 prompt / 发送前，并设置最大长度截断，避免 prompt 过长导致上游报错或“被截断反而更容易失忆”

注入作用范围（与你当前选择一致）：
- 默认注入所有窗口（global）

### Phase 5（更高风险但可控）：记忆管理搬到手机上（分层开放）
建议策略：
- 先只读：动态记忆列表、核心缓存 pending 列表、小本本列表、窗口轮次/内容
- 再做最小安全操作：例如删除/禁用类操作
- 延后高风险结构操作：融合/合并/升级等会改变检索与一致性的方法

## 4. 接口/路由清单（供 agent 定位）
Mini App API（当前/后续会扩）：
- `GET /miniapp-api/logs?lines=200`：取末尾日志
- `GET /miniapp-api/logs/stream`：SSE 实时 tail
- `GET /miniapp-api/windows`：窗口列表
- `GET /miniapp-api/windows/<window_id>/rounds`：轮次预览
- `GET /miniapp-api/windows/<window_id>/rounds/<round_index>`：轮次详情（含 reasoning）
- `DELETE /miniapp-api/windows/<window_id>/rounds/<round_index>`：删除轮次（如需）
- `GET /miniapp-api/upstreams`：查看当前 active 上游
- `PUT /miniapp-api/upstreams/active`：切换 active（switch_only）

## 5. 关键文件（后续升级优先看这里）
- 入口与 Mini App 托管：
  - `app.py`：`/miniapp` 与静态资源托管
- Mini App API 与鉴权：
  - `routes/miniapp_api.py`
  - `utils/telegram_webapp.py`：initData 校验
  - `utils/ip_allowlist.py`：IP 白名单
  - `utils/log_reader.py`、`utils/log_buffer.py`：日志读取/回退
- 上游切换生效点：
  - `storage/upstream_store.py`：只保存 active
  - `routes/chat.py`：`_get_forward_targets()` 把 active 上游放前面
- reasoning 存档与展示链路：
  - `routes/chat.py`：尽量提取 reasoning 字段写入 message
  - `pipeline/cleaner.py`：存 R2 时保留 `msg["reasoning"]`
  - 前端：`miniapp/src/ui/tabs/ReasoningTab.tsx`

## 6. 你接下来（让 agent 继续推进）应当怎么读
优先按下面顺序推进 Phase 1~5：
1) 先实现 schedule/alarms 的**只读展示与取消 disable**（Phase 1）
2) 再实现 AI tool 写入（Phase 2）
3) 最后实现到点触发（Phase 3）
4) 便签注入（Phase 4）
5) 记忆管理（Phase 5）

