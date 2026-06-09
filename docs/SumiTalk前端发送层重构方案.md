# SumiTalk 前端发送层乱线治理方案

## 结论

现在的问题不只是“不稳定”，而是聊天页发送链路已经乱成一团。

`MainChatScreen.tsx` 里同时塞了 UI、输入准备、图片上传、录音、STT、消息落库、operation、job 创建、job 轮询、取消、retry、TTS sidecar、群聊分流、笨笨 task 和自由讨论。继续往这个函数里补分支，只会越补越难判断“到底卡在哪一步”。

这次治理的目标不是重写后端、不是改成原生 Android、不是新增队列系统，而是先把当前前端发送链路拆出清楚边界：

- 保住现有 Android SQLite `chat_messages` / `chat_operations` / `chat_meta`。
- 保住 `clientRequestId` 的幂等和恢复语义。
- 保住 `createDraftTurn` / `attachJob` / `completeOperation` / `failOperation` 的原子写入语义。
- 先让私聊 Du 发送链路可读、可取消、可恢复、迟到结果不会乱改 UI。
- 群聊、笨笨、自由讨论先隔离，不能第一刀就混进来。

## 自检后修正

上一版方案有几个会误导实现的点，必须改掉：

- 不能把 retry 写成“生成新的 `requestId`”。当前 retry 必须复用原 `clientRequestId` / `operationId` / `retryPayload`，否则会破坏后端 job 复用和本地唯一索引。
- 不能把 `cancelled` 当成持久化消息状态。当前消息状态只有 `pending` / `sent` / `failed`，取消现在持久化为 `failOperation("已取消发送")`。
- 不能用一个泛泛的 `commitMessages` 绕开 native 原子写。`createDraftTurn` 原子写 user + assistant pending + operation，`attachJob` 同时写 operation 和 pending assistant，这些不能退化成单纯 `writeLocalChatHistory`。
- 图片私聊的 `modelContent` 不能只写成 string。当前图片会生成 `image_url` parts。
- 前台 active attempt 不能阻止恢复路径。刷新/切后台恢复没有前台 active request，但必须能按 `operationId/clientRequestId` 更新 pending。
- TTS sidecar 不能占用主发送状态。文字回复完成后，TTS 是每条 assistant message 的后台附加动作。
- Phase 0 不能一上来新增 controller、reducer、全局 message actions、缩日志一起做；这会碰到太多现有路径。

## 当前事实

这些是现有代码里的真实约束，方案必须贴着它们走。

### 消息状态

`ChatDraftMessage.status` 只有：

```ts
"pending" | "sent" | "failed"
```

取消发送目前是：

```text
abort 前台请求
-> 如已有 jobId 则 POST cancel
-> failOperation(operationId, "已取消发送", assistant failed message)
-> assistant 气泡显示（已取消发送）
```

如果以后要把 `cancelled` 变成真正的持久化状态，需要单独改 TS 类型、Android 插件、SQLite 读写和 UI，不放在第一阶段。

### 持久化模型

当前没有独立 outbox 表。过去口头说的 outbox，在真实代码里对应的是 `chat_operations` 的 pending/retry/recovery 能力。

第一阶段不新增 outbox 表，不新增 JS 队列。

现有关键写入不能绕开：

- `createDraftTurn`：原子写 user message + assistant pending + operation。
- `attachJob`：把 jobId 写回 operation 和 assistant pending。
- `completeOperation`：写 assistant terminal message 并把 operation 置为 done。
- `failOperation`：写失败/取消 terminal message 并把 operation 置为 failed。

### ID 语义

必须区分三个东西：

```text
clientRequestId: 一轮对话的稳定幂等键，不能因为 retry 变化。
operationId: 本地 operation 的稳定 ID，绑定 clientRequestId。
attemptId: 前台本次异步尝试 ID，只用于防止迟到结果覆盖当前 UI。
```

retry 时：

```text
clientRequestId 不变
operationId 不变
retryPayload 不变或按现有规则复用
attemptId 新建
```

恢复时：

```text
不依赖前台 active attempt
按 operationId + clientRequestId 授权更新对应 pending
```

### 私聊接口

私聊不是单纯“create job 后等待”。

`/miniapp-api/sumitalk-chat` 是 adaptive 路径，可能：

- 直接返回 done response
- 返回 job_id 后继续 poll
- 返回 error
- 因取消返回 abort/cancel

controller 或 helper 必须兼容直接 done 和 job poll 两种路径。

### TTS sidecar

渡回复里的 `<voice>...</voice>` 当前处理方式是：

```text
先剥离 <voice>，完成文字 assistant
-> 后台调用 TTS
-> 成功后给同一 assistant message 追加 audio attachment
-> 失败只记 warning，不把主消息改失败
```

这个是对的。sidecar 不能让 `sending` 继续占用，也不能让用户以为主回复还没完成。

## 第一阶段不做什么

为了不继续乱，先明确边界：

- 不改后端 job 架构。
- 不改 Android SQLite schema。
- 不新增持久化 `cancelled` 状态。
- 不新增独立 outbox。
- 不把私聊改成并发/排队发送；当前私聊 `sending` 时拒绝第二条，先保持。
- 不动群聊、笨笨 task、自由讨论主链路。
- 不把所有 `messagesRef.current = ...; setMessages(...); saveDisplayHistory(...)` 一次性全局替换。
- 不删现有关键日志，只规范新增日志字段为 metadata-only。

## 目标结构

最终应该拆成这样，但不是一口气落地：

```text
MainChatScreen.tsx
  只保留页面 UI、输入框、按钮、消息列表、入口分流

privateChatSendFlow.ts
  私聊 Du 发送主流程
  负责 request body、post、direct done / poll、assistant terminal 解析
  不直接持有 React refs；SQLite operation 原子写仍由页面调用

privateChatInput.ts
  文本/图片/语音/旅行表单输入准备
  准备失败时不创建 pending

privateChatMessageActions.ts
  纯消息变换 helper
  不直接写 SQLite，不绕开 native operation 原子语义

chatAttempt.ts
  前台 attemptId / isCurrentAttempt / abort controller 管理

chatVoiceSidecar.ts
  每条 assistant message 的后台 TTS 附件追加
```

注意：这些文件名是目标方向，Phase 0 不要求全建。

## Phase 0：先止血

Phase 0 只在现有私聊 Du 分支里加边界，不搬家。

### 改动范围

只碰 `MainChatScreen.tsx` 里私聊 `shouldRequestDu && !groupChatMode` 的路径。

群聊路径保持旧逻辑。

### 要做

1. 引入 `attemptId`

前台发送开始时生成：

```ts
const attemptId = `attempt-${clientRequestId}-${Date.now()}-${random}`;
```

`activeChatRequestRef` 增加 `attemptId`。

2. 增加 `isCurrentAttempt`

每个异步关键点回来前检查：

```ts
activeChatRequestRef.current?.attemptId === attemptId
```

需要保护的点：

- create job 返回后写 jobId 到 UI 前
- wait/poll 返回后 complete assistant 前
- catch 里写 failed assistant 前
- finally 里清 active request 前

恢复路径不能套这个 guard。`listActiveOperations -> recoverSumiTalkOperation` 没有前台 attempt，但必须能按 `operationId/clientRequestId` 更新对应 pending。Phase 0 实现时要在恢复入口旁写清楚这一点，或者加断言防止 recovery 误走 `isCurrentAttempt`。

3. 保持取消持久化语义

取消仍然走现有语义：

```text
abort
-> job cancel
-> failOperation("已取消发送")
-> assistant failed message: （已取消发送）
```

可以在 UI 层把“已取消发送”的 failed 气泡和普通 failed 区分展示，但不在 Phase 0 改存储状态。

4. TTS sidecar 增加 per-message guard

TTS append 前检查：

- assistant message 仍存在
- message id 仍是目标 assistantId
- clientRequestId 仍匹配
- message 没被后续失败/取消替换

它不依赖 active attempt，因为主回复完成后 active request 可能已经结束。

5. 不改日志体系

Phase 0 不删日志、不重命名全套事件。

只允许在现有关键日志里补：

- `attemptId`
- `clientRequestId`
- `operationId`
- `jobId`
- `source`
- `stage`
- `elapsedMs`

不记录正文、转写文本、完整附件 URL、token、key。

### Phase 0 验证

必须验证：

- 私聊文本发送成功。
- `/sumitalk-chat` 直接 done 能正常完成。
- `/sumitalk-chat` 返回 job_id 后 poll 能正常完成。
- 发送中取消后，迟到返回不能把“已取消发送”改成正常回复。
- 取消后刷新，消息仍按现有 failed/“已取消发送”语义恢复。
- `listActiveOperations` 进入的恢复路径不依赖 active attempt，不会被 `isCurrentAttempt` 拦掉。
- retry 仍复用原 `clientRequestId` / `operationId`。
- TTS 成功只追加附件，不占用 sending。
- TTS 失败只记 warning，不改主消息失败。
- 群聊发送行为没有变化。
- 私聊发送中第二条仍按现有行为拒绝，不引入队列。

### Phase 0 当前落地（2026-06-09）

已落地：

- `ActiveChatRequest` 增加 `attemptId`。
- 私聊 Du 前台发送分支增加 `isCurrentAttempt` / `chat_attempt_stale_skip`，覆盖 create job 返回、job done、catch 写失败、finally 清 active request 前的迟到保护。
- `listActiveOperations -> recoverSumiTalkOperation` 恢复入口保留按 `operationId/clientRequestId` 授权更新的语义，并加注释说明不能套前台 attempt guard。
- TTS sidecar 在开始前和 TTS 返回后都检查目标 assistant message 是否仍匹配 `assistantId/clientRequestId/operationId/status=sent`，迟到时只记 `assistant_voice_tts_skip`，不追加附件、不改主消息。
- 取消仍沿用现有 `failOperation("已取消发送")` 持久化语义，没有引入持久化 `cancelled` 状态。

未做：

- 未拆 controller / reducer。
- 未改 Android SQLite schema。
- 未改 retry 的 `clientRequestId` / `operationId` 语义。
- 未改群聊、笨笨 task、自由讨论和 travel form 主链路。
- 未新增 outbox 表或 JS 队列。

## Phase 1A：抽纯 helper

Phase 1A 只抽纯函数，不改行为。

可以抽：

- `contentWithAttachmentHint`
- `buildPrivateUserContent`
- `extractSumiTalkVoiceOutput`
- assistant terminal message 构造
- request body 构造
- token/reasoning/attachment extraction 的私聊适配

不能抽：

- `createDraftTurn`
- `attachJob`
- `completeOperation`
- `failOperation`
- 恢复流程
- 群聊分流

原因：先把可测试的纯逻辑拿出去，别一上来动持久化和异步调度。

### Phase 1A 当前落地（2026-06-09）

已落地：

- 新增 `miniapp/src/ui/chat/privateChatHelpers.ts`。
- 已抽出 `contentWithAttachmentHint`、`buildPrivateUserContent`、`extractAssistantAttachments`、`isVoiceTranscriptEcho`、`extractSumiTalkVoiceOutput`。
- `buildPrivateUserContent` 保留现有图片 `image_url` parts 行为，`PrivateModelContent` 明确支持 `string | Array<Record<string, any>>`。
- `MainChatScreen.tsx` 只改 import 和删除本地重复纯函数，发送顺序、operation、retry、recovery、群聊分流都没改。

未做：

- request body 构造在 Phase 1C 处理。
- assistant terminal message 构造在 Phase 1C 处理。
- 输入准备、STT、图片上传、travel form 在 Phase 1B 处理。
- 页面级 reducer 不属于 Phase 1 完成条件，继续延后。

## Phase 1B：输入准备拆离

这一阶段只处理“发送前准备”，让图片、语音、旅行表单不要继续污染主发送函数。

目标类型：

```ts
type PrivateChatSource = "text" | "image" | "voice" | "travel_form" | "retry";

type PrivateModelContent = string | Array<Record<string, any>>;

type PreparedPrivateChatInput = {
  source: PrivateChatSource;
  content: string;
  displayContent?: string;
  attachments: ChatAttachment[];
  modelContent: PrivateModelContent;
  sttProvider?: string;
};
```

规则：

- 文本：trim 后生成 prepared input。
- 图片：先上传，保留现有 `image_url` parts 能力；上传失败不创建 pending。
- 语音：先录音/STT，STT 失败不创建 pending；语音只是输入方式，不强制渡发语音。
- travel form：如果继续走私聊 Du，应作为 `travel_form` source 明确纳入；如果不纳入，必须保留旧路径并标注未迁移。

### Phase 1B 当前落地（2026-06-09）

已落地：

- 新增 `miniapp/src/ui/chat/privateChatInput.ts`。
- 文本、图片、语音、travel form 统一生成 `PreparedPrivateChatInput`，再交给 `sendPreparedPrivateChatInput -> sendChatContent`。
- `sendChatContent` 增加 `modelContent?: PrivateModelContent`，私聊 Du 请求优先使用准备层传入的 `modelContent`。
- 图片上传仍发生在创建 pending 前，上传成功后保留 `image_url` parts；上传失败不创建 pending。
- 语音 STT 仍发生在创建 pending 前，识别为空或 STT 失败不创建 pending；语音仍只是输入方式，不强制渡发语音。
- travel form 已按 `travel_form` source 走统一 prepared input，展示文案仍是 `已提交，渡在安排`。

未做：

- request body 构造在 Phase 1C 处理。
- assistant terminal message 构造在 Phase 1C 处理。
- 未改 retry 恢复路径。
- 未改群聊、笨笨 task、自由讨论。

## Phase 1C：私聊发送 controller

等 Phase 0 和 Phase 1A/1B 稳了，再建私聊发送流 controller。

controller 只管私聊 Du，不管群聊。

职责：

- 接收 `PreparedPrivateChatInput`
- 生成/接收 `clientRequestId`、`operationId`、`attemptId`
- 调 `/sumitalk-chat`
- 兼容 direct done 和 job poll
- 生成私聊 request body
- 生成 assistant terminal / failed message
- 暴露 jobId 和 terminal message 给页面提交 operation

controller 不能做：

- 群聊目标解析
- 笨笨 task 创建
- 自由讨论接力
- 云端历史同步
- 直接绕开 operation 写 SQLite
- 直接持有 React refs 或页面状态

### retry / cancel / recovery

这三件事不能一起糊进普通 send。

retry：

- 保留原 `clientRequestId` / `operationId`
- 新建 `attemptId`
- 复用 operation 的 `retryPayload`

cancel：

- 仍按现有存储语义落 failed + “已取消发送”
- 是否隐藏 retry 按 UI 层另行决定

recovery：

- 从 `listActiveOperations` 进入
- 按 `operationId/clientRequestId` 更新目标 pending
- 不要求 active foreground attempt

### Phase 1C 当前落地（2026-06-09）

已落地：

- 新增 `miniapp/src/ui/chat/privateChatSendFlow.ts`。
- `buildPrivateChatRequestBody` 只负责私聊 Du 的 `/miniapp-api/sumitalk-chat` request body，保留 `music_bgm_context`、`reply_target`、`client_request_id`。
- `runPrivateChatSendFlow` 负责私聊 Du 的 `createSumiTalkChatJob -> direct done / job poll -> assistant terminal`，继续打 `chat_job_create_*`、`chat_job_status`、`chat_reply_ready` 等 metadata-only 日志。
- `buildPrivateAssistantTerminal` 统一解析正文、`<voice>`、reasoning、token、assistant 图片附件；`buildPrivateAssistantFailureMessage` 统一生成取消/失败 assistant message。
- `MainChatScreen.tsx` 私聊 Du 路径改为调用 `runPrivateChatSendFlow`；`createDraftTurn`、`attachJob`、`completeOperation`、`failOperation` 仍由页面在原位置调用，保留 Android SQLite operation 的现有原子语义。
- 群聊 Du reply 仍走旧 inline 分支，没有迁进私聊 controller。

未做：

- 未迁 retry/recovery 到新 flow；retry 仍复用旧 operation 的 `retryPayload` 并走 `recoverSumiTalkOperation`。
- 未引入页面级 reducer。
- 未改群聊、笨笨 task、自由讨论。
- 未改持久化 `cancelled`、Android SQLite schema、独立 outbox/队列。

## Phase 2：群聊单独治理

私聊稳定后，再拆群聊。

群聊应该有自己的 controller，因为它不是“私聊发送的复杂参数”：

- Du reply
- Benben task
- 自由讨论
- 取消笨笨任务
- 停止/继续讨论
- realtime/fallback 更新

Phase 2 的目标是把群聊从 `sendChatContent` 里剥出来，而不是让私聊 controller 兼容所有群聊特殊情况。

### Phase 2 当前落地（2026-06-09）

已落地：

- 新增 `miniapp/src/ui/chat/groupChatRouting.ts`。
- 群聊 @ 渡 / @ 笨笨、自由聊、停止/继续、接力轮次、下一位说话者、自由讨论 prompt 构造都从 `MainChatScreen.tsx` 抽出为纯函数。
- 新增 `miniapp/src/ui/chat/groupChatSendFlow.ts`。
- 群聊 Du reply 的 request body、`/miniapp-api/sumitalk-chat-jobs` create/poll、direct done、assistant terminal/failed message 构造已从主页面拆出。
- 普通群聊 @渡 / 自由聊开场里的 Du 回复，以及自由讨论接力里的 Du 回复，都复用 `runGroupDuReplyFlow`。
- 群聊 Du reply 仍由页面调用 `createDraftTurn`、`attachJob`、`completeOperation`、`failOperation`，没有绕开 Android SQLite operation 原子语义。

未做：

- 笨笨 task 创建、取消、realtime/fallback 更新仍保留在 `MainChatScreen.tsx`，因为它们直接依赖当前页面消息列表和 task recovery refs。
- 群聊整体发送入口还在 `sendChatContent` 里分流；后续如继续拆，应先把笨笨 task side-effect 封成单独 controller，再把 `sendGroupChatContent` 独立出去。
- 未改后端 job、Android SQLite schema、retry/recovery、独立 outbox/队列。

## Phase 3：体验升级

只有前面边界清楚后，才考虑体验层升级。

可选方向：

- 更清楚的 job 阶段显示。
- SSE/流式只做前台体验，不替代 SQLite operation。
- 真正的发送队列/连续多条发送。
- 持久化 `cancelled` 状态。

这些都不是第一阶段。

## 验证清单

每阶段都要按真实路径测，不测假 happy path。

### 私聊

- 文本成功。
- 上游 error。
- 上游 401/403/500。
- direct done。
- job poll done。
- job poll timeout。
- 发送中取消。
- 取消后迟到返回。
- 失败后 retry。
- retry 后刷新恢复。
- 发送中切后台/刷新 WebView。

### 媒体

- 图片上传成功。
- 图片上传失败。
- 图片内容仍以 `image_url` parts 进入模型。
- 麦克风权限失败。
- STT 失败。
- STT 成功后普通文本回复。
- 渡主动 `<voice>` TTS 成功。
- 渡主动 `<voice>` TTS 失败。

### 持久化

- `chat_messages` 有 user + assistant。
- `chat_operations` 有正确 status。
- jobId 能写回 operation 和 assistant pending。
- 取消/失败后恢复语义一致。
- 手动云端同步不受影响。

### 不回归

- 群聊普通消息不变。
- @渡 不变。
- @笨笨 不变。
- 自由聊不变。
- 笨笨 task 取消不变。
- travel form 不丢。

## 不能踩的坑

- 不要把 `clientRequestId` 改成每次 retry 都新的 ID。
- 不要把 `attemptId` 存成业务幂等键。
- 不要在没有 schema/plugin 支撑时持久化 `cancelled`。
- 不要用 `writeLocalChatHistory` 替代 `createDraftTurn`。
- 不要用一个万能 `commitMessages` 绕开 `attachJob/completeOperation/failOperation`。
- 不要把图片模型内容强行收窄成 string。
- 不要用 active attempt 阻止 operation recovery。
- 不要让 TTS sidecar 占住主发送。
- 不要把群聊第一阶段塞进私聊 controller。
- 不要新增一个真实代码里不存在的 outbox 层。

## 当前结论

第一刀不是“把所有东西拆漂亮”。

第一刀是让现有私聊 Du 发送分支有明确的前台 attempt、防迟到保护、取消终态和 sidecar 边界，同时不破坏 `chat_operations` 这套恢复底座。

等这条主链路不再乱跳，再抽 helper，再迁 controller，再碰群聊。
