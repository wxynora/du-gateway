# SumiTalk 聊天系统稳定性优化方案

## 背景

目标不是把 SumiTalk 立刻改成和 QQ 一样完整的 IM 系统，而是先达到类似 RikkaHub 这类本地 LLM 聊天客户端的稳定感：消息不容易丢，断网/切后台/刷新后能恢复，失败后能明确重试，前端显示和后端状态能对上。

本方案采用路线 2：**SQLite/原生 ChatStore + React UI**。聊天界面继续使用当前 React/Capacitor 页面，但聊天消息和发送中任务不再只依赖 WebView 里的 IndexedDB/Dexie，而是下沉到 Android 原生 SQLite 存储，由前端通过 Capacitor 插件调用。

参考对象：

- RikkaHub: https://github.com/rikkahub/rikkahub
- 关键思路：本地优先、会话状态集中管理、消息持久化、生成任务可取消/可恢复、UI 不直接承担网络细节。

## 当前链路概览

当前 SumiTalk 已经具备一些基础能力：

- 前端使用 Dexie 保存本地聊天历史：`miniapp/src/ui/storage/chatHistoryDb.ts`
- 前端已有 `pending / sent / failed` 消息状态：`miniapp/src/ui/chatMessages.ts`
- 前端发送逻辑集中在 `miniapp/src/ui/MainChatScreen.tsx`
- 后端聊天任务落盘：`routes/miniapp/sumitalk_chat_jobs.py`
- 后端支持 `client_request_id` 复用，能避免一部分重复请求
- 后端历史接口会合并远端/本地消息，并通过 latest/realtime 发布最新 assistant 消息：`routes/miniapp/sumitalk_history.py`

当前主要问题：

- 发送、pending 占位、job 创建、轮询、失败处理、历史保存都揉在 `MainChatScreen.tsx` 里，状态容易分叉。
- 渡的 `job_id` 只有最终成功后才写入消息；如果中途刷新、切后台、WebView 被杀，pending 消息很难恢复继续轮询。
- 本地历史是整段 `messages` 数组覆盖式保存，没有独立的“发送中任务/outbox”表，也没有脱离 WebView 生命周期的更稳本地存储。
- 失败消息只有显示层状态，缺少可重试的原始请求上下文。
- 后端历史是整段 merge，适合轻量聊天，但不适合未来长历史、分页、分支、精确同步。

## RikkaHub 可借鉴的点

RikkaHub 不只是一个聊天页面，它的稳定性来自几层分工：

- `ChatVM` 很薄，只负责把 UI 事件交给服务层。
- `ChatService` 统一管理会话 session、生成 Job、取消、错误流、保存。
- `GenerationHandler` 把流式 chunk 转成消息状态，工具循环和输出转换在这里收口。
- `ConversationRepository` 用 Room 管会话和消息节点，支持分页、搜索、事务保存。
- 配置和会话分离：DataStore 管设置，Room 管聊天数据。

SumiTalk 不需要照搬成原生 Room + Compose 架构，但应该直接照搬“稳定本地库 + 状态集中 + 本地任务表 + 可恢复发送”的思路。也就是 UI 不重写，存储地基先升到原生 SQLite。

## 总体目标

先做小而硬的稳定性改造：

1. 页面刷新后，已有 pending 消息可以继续恢复。
2. 网络抖动后，不会重复创建多条渡回复。
3. 发送失败后，能保留重试所需上下文。
4. 本地显示、后端 job、服务器历史之间有明确 reconcile 规则。
5. 聊天消息和 operation 由原生 SQLite ChatStore 持久化，WebView 重启不影响恢复。
6. `MainChatScreen.tsx` 里的聊天发送逻辑开始拆出去，减少页面组件承担的状态复杂度。

这些是前两阶段合起来要达到的目标，不全部压在 Phase 1。Phase 1 先把本地 ChatStore 和旧历史迁移跑稳，Phase 2 再接发送 outbox 和 pending 恢复。

前两阶段不做：

- 不重写成原生 Android Room 聊天系统。
- 不重写成原生 Compose 聊天 UI。
- 不强行做完整 IM 多端同步。
- 不立刻做长历史分页。
- 不要求和 QQ 一样的消息送达/已读/撤回/多端冲突处理。
- 不把群聊、笨笨任务、自由讨论全部一次重构。

## 数据模型建议

新增原生 ChatStore。Android 侧使用 SQLite 保存两类核心数据：

- `chat_messages`: 当前设备本地消息。
- `chat_operations`: 发送中任务/outbox。
- `chat_meta`: 存储 schema 版本、迁移状态和最近一次远端同步水位。

Dexie 不再作为主存储，只保留迁移和 Web 调试 fallback。

### chat_messages

```ts
type ChatStoreMessage = {
  id: string;
  windowId: string;
  displayWindowId: string;
  role: "user" | "assistant" | "benben";
  content: string;
  createdAt: string;
  updatedAt: string;
  status: "pending" | "sent" | "failed";
  clientRequestId?: string;
  operationId?: string;
  jobId?: string;
  reasoning?: string;
  tokenCount?: {
    input?: number;
    output?: number;
    thinking?: number;
  };
  remoteKey?: string;
  localRevision?: number;
  deletedAt?: string;
};
```

### chat_operations

```ts
type ChatOperation = {
  id: string;
  clientRequestId: string;
  windowId: string;
  displayWindowId: string;
  replyTarget: string;
  model: string;
  retryPayload: any;
  retryPayloadSize?: number;
  userMessageId: string;
  assistantMessageId?: string;
  benbenMessageId?: string;
  jobId?: string;
  status: "draft" | "posting" | "running" | "done" | "failed" | "cancelled";
  error?: string;
  createdAt: string;
  updatedAt: string;
  lastAttemptAt?: string;
  retryCount: number;
  schemaVersion: number;
};
```

关键原则：

- `clientRequestId` 是端到端幂等键。
- `assistantMessageId` 是本地 pending 占位的稳定 ID。
- `jobId` 一旦拿到就立刻写入 operation 和 pending 消息。
- `retryPayload` 只保留重试所需最小内容，不保存无关 UI 状态、完整系统提示词、大段上下文或图片 base64。
- `retryPayload` 需要有大小上限；超限时只保留可重建请求的必要索引和用户原文，避免 SQLite 被大 payload 拖慢。
- operation 完成后可以保留短期记录，用于 debug 和防重复。
- 前端所有聊天读写都走 `ChatStore` 抽象，不直接知道底层是 SQLite 还是 fallback。
- 原生 SQLite 是 Android 正式存储；Dexie 只用于旧数据迁移和非 Android 环境调试。

建议索引：

- `chat_messages.id` 主键。
- `chat_messages(windowId, createdAt)` 用于加载窗口历史。
- `chat_messages(clientRequestId)` 用于回填 assistant pending。
- `chat_messages(operationId)` 用于恢复发送中轮次。
- `chat_operations.id` 主键。
- `chat_operations(clientRequestId, windowId, replyTarget)` 唯一索引，用于前端和后端幂等对齐。
- `chat_operations(windowId, status, updatedAt)` 用于扫描待恢复任务。

## 事务边界

这是稳定性的关键点。前端不要用多次独立插件调用拼出一次发送，否则中途崩溃会出现“有 pending 没 operation”或“有 operation 没消息”。

原生 ChatStore 至少提供这些事务级方法：

- `createDraftTurn({ userMessage, assistantMessage, operation })`
  - 同一个 SQLite transaction 内写入 user 消息、assistant pending 和 operation。
  - 如果 `clientRequestId` 已存在，返回已有 operation 和消息，不重复插入。

- `attachJob({ operationId, jobId })`
  - 同一个 transaction 内把 operation 改成 `running`，并把 `jobId` 写回 assistant pending。

- `completeOperation({ operationId, assistantPatch, usage })`
  - 同一个 transaction 内把 assistant pending 改成 `sent`，写入正文、reasoning、tokenCount，并把 operation 改成 `done`。

- `failOperation({ operationId, error, retryable })`
  - 同一个 transaction 内把 assistant pending 改成 `failed`，记录错误和 retry 信息。

- `applyRemoteHistory({ windowId, messages })`
  - 合并远端历史时不能覆盖本地 `posting/running` operation 绑定的 pending 消息。
  - 远端消息只补齐缺失或更新已完成消息。

这些方法是原生层必须保证的原子边界；前端 controller 只负责决定何时调用。

## 前端改造方案

新增一个聊天服务层和一个存储抽象，例如：

- `miniapp/src/ui/chat/chatStore.ts`
- `miniapp/src/ui/chat/nativeChatStore.ts`
- `miniapp/src/ui/chat/dexieChatStoreFallback.ts`
- `miniapp/src/ui/chat/sumitalkChatClient.ts`
- `miniapp/src/ui/chat/useSumiTalkChatController.ts`

职责划分：

- `chatStore.ts`
  - 定义统一接口。
  - 读写 messages。
  - 读写 operations。
  - 暴露事务级方法，而不是只暴露零散 CRUD。
  - 按窗口扫描 pending/running 操作。
  - 按 `clientRequestId / operationId / messageId` 做合并。

- `nativeChatStore.ts`
  - 调用 Android 原生插件。
  - 负责类型转换、异常兜底、批量读写。

- `dexieChatStoreFallback.ts`
  - 只在原生插件不可用时兜底。
  - 负责把旧 Dexie 历史迁移进统一接口。

- `sumitalkChatClient.ts`
  - 创建 SumiTalk job。
  - 查询 job 状态。
  - 包装 `client_request_id`、`reply_target`、`window_id`。
  - 统一处理超时、401/403/500、AbortError。

- `useSumiTalkChatController.ts`
  - 管理发送状态。
  - 创建本地 user + assistant pending。
  - 保存历史。
  - 创建/恢复 job。
  - 将 job 结果 reconcile 回消息列表。
  - 暴露 `sendMessage / retryMessage / recoverPendingOperations` 给页面。

`MainChatScreen.tsx` 第一阶段只保留 UI 和群聊分流，不继续膨胀为网络状态机。

## Android 原生 ChatStore 方案

新增一个 Capacitor 插件，例如 `SumiChatStore`。

建议文件：

- `miniapp/android/app/src/main/java/com/sumitalk/app/SumiChatStorePlugin.java`
- `miniapp/android/app/src/main/java/com/sumitalk/app/chat/SumiChatDatabase.java`
- `miniapp/android/app/src/main/java/com/sumitalk/app/chat/SumiChatStore.java`
- `miniapp/src/plugins/sumi-chat-store.ts`

原生侧职责：

- 初始化 SQLite 数据库。
- 建表和版本迁移。
- 在 `MainActivity.onCreate()` 里注册插件：`registerPlugin(SumiChatStorePlugin.class)`。
- 插件类使用 `@CapacitorPlugin(name = "SumiChatStore")`，前端 `registerPlugin("SumiChatStore")` 名字必须一致。
- `upsertMessages(messages)`
- `listMessages(windowId, limit, before?)`
- `getMessage(id)`
- `patchMessage(id, patch)`
- `upsertOperation(operation)`
- `getOperation(id)`
- `listActiveOperations(windowId)`
- `patchOperation(id, patch)`
- `deleteOldOperations(before)`

表结构只保存聊天所需数据，不把大段 UI 状态塞进数据库。

所有 SQLite 读写都走后台线程；批量写和事务方法不能阻塞主线程。插件返回给前端时只返回必要字段，避免一次把全库内容搬回 WebView。

如果后续需要更接近 RikkaHub，可以再把 Android 侧从 `SQLiteOpenHelper` 升级成 Room；第一版不需要为了 Room 引入过重改造。

## Dexie 到 SQLite 迁移规则

迁移必须幂等，不能只写“启动时迁移一次”。

建议规则：

- 用 `chat_meta` 保存迁移状态：
  - `dexie_migration_started_at`
  - `dexie_migration_finished_at`
  - `dexie_migration_source_count`
  - `dexie_migration_imported_count`
  - `dexie_migration_version`

- 迁移前先读取 Dexie 当前窗口历史，按现有 `sanitizeHistoryMessages` 规则清洗。
- 迁移时统一 canonical windowId，兼容 `sumitalk-main`、旧主会话和 `tg_` 窗口映射。
- 每条消息按稳定 key 去重：
  - 优先 `id`
  - 其次 `clientRequestId + role`
  - 最后 `role + createdAt + content digest`
- 迁移写入 SQLite 必须批量事务提交。
- 迁移完成后校验导入条数和最新一条消息时间。
- 迁移失败时不要清空 Dexie，也不要标记完成；下次启动可以继续重试。
- 迁移成功后，正式聊天读取 SQLite；Dexie 只保留 fallback/debug，不再作为主历史参与“谁更好”的比较。
- 迁移期间如果用户发送新消息，新消息直接写 SQLite，不再写入 Dexie 主历史。

## 发送流程

正常发送：

1. 生成 `clientRequestId`。
2. 调用 `createDraftTurn()`，在同一个事务里插入 user 消息、assistant pending 和 `ChatOperation(status="draft")`。
3. 本地 SQLite 立即落盘，不依赖远端成功。
4. POST `/miniapp-api/sumitalk-chat` 或 `/miniapp-api/sumitalk-chat-jobs`。
5. 拿到 `job_id` 后立刻调用 `attachJob()` 更新 operation 和 pending 消息。
6. 轮询 job。
7. done 时调用 `completeOperation()`，用 `clientRequestId`/`operationId` 替换对应 pending。
8. 从 SQLite 导出可同步消息视图，再后台同步远端历史。

中途刷新/切后台后恢复：

1. 页面启动时从 ChatStore 读取本地历史。
2. 扫描 `status in ("posting", "running")` 的 operation。
3. 如果有 `jobId`，继续 poll job。
4. 如果没有 `jobId`，用同一个 `clientRequestId` 重发创建请求。
5. 后端命中已有 job 时返回同一个 job。
6. 前端用原 `assistantMessageId` 回填结果。

失败重试：

1. failed 消息保留 `clientRequestId` 和 `operationId`。
2. 点击重试时不新建 user 消息。
3. 如果 operation 有 `jobId`，优先查 job。
4. 如果 job 已过期，再用原 `retryPayload` 和 clientRequestId 重新创建。
5. 如果后端明确返回不可重试错误，再显示最终失败。

## 后端改造方案

现有 `sumitalk_chat_jobs.py` 已有 job 落盘和 `client_request_id` 复用，第一阶段只需补强：

- job 状态返回中包含 `client_request_id / window_id / reply_target`。
- 创建接口如果复用已有 job，也返回已有 job 的当前状态。
- 可考虑增加按 `client_request_id` 查询接口：

```http
GET /miniapp-api/sumitalk-chat-jobs/by-client-request/{client_request_id}?window_id=...&reply_target=...
```

- job TTL 可以保留 30 分钟，但前端 operation 可以保留更久，过期后显示“任务已过期，可重试”。
- 错误返回统一结构，便于前端区分：
  - `upstream_error`
  - `network_error`
  - `job_expired`
  - `auth_error`
  - `gateway_error`

## 历史同步策略

第一阶段本地升级为 SQLite 消息级存储，服务端仍保留现有整段历史保存，不急着改成服务端消息表。

同步规则：

- 本地 SQLite 是即时显示源和恢复源。
- 远端历史是备份和跨端恢复源，不是本机正在发送时的权威消息表。
- pending/running 不主动覆盖远端，避免把半成品同步成最终记录。
- done/failed 后从 SQLite 导出“可同步消息视图”再后台 PUT 远端历史。
- 可同步消息视图必须过滤 pending/running，并裁剪 reasoning/tokenCount 等字段到后端当前能接受的格式。
- 拉取远端历史时，不能覆盖本地仍在运行的 operation；应先 merge，再按 operation 状态修正 pending。
- 旧 Dexie 历史首次启动时迁移进 SQLite，迁移成功后不再从 Dexie 读主历史。

后续阶段再考虑：

- 服务端消息表。
- `message_id` 级别增量同步。
- 长历史分页。
- 多设备冲突合并。

## 实时与轮询

发送恢复阶段采用“轮询为主，realtime 为辅助”：

- job poll 是最终可靠路径。
- realtime/latest 只用于更快显示新 assistant 消息。
- realtime 收到消息时，也必须按 `clientRequestId` 或 message key reconcile，不能简单 append。
- 如果 realtime 消息无法匹配本地 pending，可以作为远端新消息插入，但要避免重复。

## 需要重点防的场景

- POST 成功但前端没收到响应。
- job 创建成功但 WebView 被杀。
- poll 中途网络断开。
- 后端重启后内存 event 丢失，但 job 文件还在。
- app 重启后本地有 pending，但远端历史已有最终 assistant。
- 用户连续点发送。
- 用户点重试时旧 job 其实已经 done。
- 远端历史拉取失败，不能覆盖本地历史。
- 群聊中渡和笨笨同时 pending，不能互相误替换。

## 验收标准

手动验收：

- Phase 1：旧 Dexie 历史迁移进 SQLite 后，普通私聊历史能正常显示，重启 App 后仍从 SQLite 读取。
- Phase 1：插件未注册或原生不可用时，前端能退回 Dexie fallback，并明确记录 native unavailable。
- Phase 1：重复启动迁移不会重复插入消息。
- 发送后立刻杀 app，重新打开后能继续显示 pending，并最终变成渡回复。
- 直接杀 WebView/重启 App 后，SQLite 里的 pending operation 仍能恢复。
- 发送后断网 30 秒再恢复，不重复生成两条渡回复。
- POST 后模拟前端超时，再重试，后端复用同一个 `client_request_id`。
- job done 后刷新页面，回复仍在，不出现 pending 残留。
- 后端返回 401/403/500 时，消息变 failed，错误文案能看懂，并能决定是否重试。
- 群聊里同时 @渡/@笨笨 时，两边 pending 不串。

代码验收：

- `MainActivity` 注册 `SumiChatStorePlugin`。
- Android 原生 ChatStore 插件有最小读写 smoke。
- 原生事务方法覆盖 `createDraftTurn / attachJob / completeOperation / failOperation`。
- 新增 chat controller 的单元测试或最小 smoke。
- `chatStore` 的 merge/recover/retry 逻辑有纯函数测试。
- `sumitalk_chat_jobs.py` 至少覆盖 client_request_id 复用和 job 查询。
- 前端构建通过。
- Android 打包前确认 `miniapp_static`/Capacitor 同步路径按现有流程执行。

## 分阶段实施

当前落地状态（2026-06-07）：

- 已完成 Phase 1：Android 原生 SQLite ChatStore、Dexie fallback、旧历史迁移、原 `chatHistoryDb.ts` API 兼容层。
- 已完成 Phase 2 主体：`chat_operations` outbox、`createDraftTurn / attachJob / completeOperation / failOperation / listActiveOperations` 事务方法、SumiTalk job client、普通私聊 pending job 恢复、失败气泡重试入口。
- 已覆盖群聊里“渡”的 pending/job 恢复；自由讨论接力不会在恢复时自动重跑，避免重启后重复触发。笨笨仍走现有 Codex task/realtime 恢复。
- 仍未做：服务端消息级增量同步、长历史分页、原生 Room/Compose 重写、多端冲突合并。

### Phase 1：原生 ChatStore 与迁移

- 新增 Android SQLite ChatStore 插件。
- 新增前端 `chatStore` 抽象。
- 保留 Dexie fallback，并支持旧历史迁移。
- 先让普通私聊历史从 ChatStore 读取和写入。
- 补插件注册、后台线程、事务写入和迁移幂等。
- 不动群聊复杂分支。

验收：历史可迁移、可读取、可重启恢复；还不承诺发送中任务恢复。

风险：中。主要风险是原生插件、旧历史迁移、Android 打包验证。

### Phase 2：outbox 与普通私聊恢复

- ChatStore 增加 operation/outbox。
- 拆出 SumiTalk chat client。
- 拆出 controller。
- 普通私聊先接入可恢复发送。
- pending job 支持启动恢复。
- 发送流程改用事务方法，避免消息和 operation 半写入。

验收：发送中杀 App 可恢复；网络超时重试不重复生成；失败可重试。

风险：中。主要风险是 UI 状态同步和重复发送。

### Phase 3：群聊路径接入

- 将群聊里渡的 pending/job 也接入 operation。
- 笨笨任务已有独立 task/realtime，先只做边界整理。
- 确保自由讨论接力不会因为恢复逻辑重复触发。

风险：中。群聊分支多，适合在私聊稳定后再接。

### Phase 4：历史同步增强

- 本地 merge 规则从“整段选更好”改成“按 messageId/clientRequestId 合并”。
- 服务端 latest/realtime 返回可匹配字段。
- 远端历史 PUT 前过滤 pending/running。

风险：中。会碰到旧数据兼容。

### Phase 5：长历史与服务端消息实体化

- 本地已经消息实体化后，再评估是否把服务端历史也从 JSON 数组升级成消息级存储。
- 增量同步、分页、搜索、归档再放这一阶段。

风险：中到高。不是稳定性的第一刀。

## 推荐先改的文件

前两阶段建议只动：

- `miniapp/src/ui/storage/chatHistoryDb.ts`
- `miniapp/src/ui/MainChatScreen.tsx`
- 新增 `miniapp/src/ui/chat/chatStore.ts`
- 新增 `miniapp/src/ui/chat/nativeChatStore.ts`
- 新增 `miniapp/src/ui/chat/dexieChatStoreFallback.ts`
- 新增 `miniapp/src/ui/chat/sumitalkChatClient.ts`
- 新增 `miniapp/src/ui/chat/useSumiTalkChatController.ts`
- 新增 `miniapp/src/plugins/sumi-chat-store.ts`
- 新增 `miniapp/android/app/src/main/java/com/sumitalk/app/SumiChatStorePlugin.java`
- 新增 `miniapp/android/app/src/main/java/com/sumitalk/app/chat/SumiChatDatabase.java`
- 新增 `miniapp/android/app/src/main/java/com/sumitalk/app/chat/SumiChatStore.java`
- 视需要小改 `routes/miniapp/sumitalk_chat_jobs.py`

暂不动：

- 群聊自由讨论策略
- 笨笨 coding task 路径
- 服务器历史底层文件格式
- 原生聊天 UI / Compose / Room 重写

## 小结

最划算的路线不是重做聊天界面，而是把聊天地基升成原生 SQLite ChatStore，再把“发出去的一条消息”变成一个可恢复的本地 operation。

RikkaHub 的稳定感来自本地持久化、状态集中和生成任务生命周期管理。SumiTalk 现在已经有 React UI 和后端 job，下一步应该把本地消息与 operation 下沉到原生 SQLite，并用同一个 `clientRequestId` 串起前端显示、后端 job 和远端历史。这样先让聊天变成“断一下也能找回来”，再考虑流式、分页和更完整的 IM 能力。
