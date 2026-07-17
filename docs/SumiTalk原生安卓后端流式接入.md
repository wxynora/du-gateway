# SumiTalk 原生安卓后端流式接入

## 边界

- 原生 Android 与现有 MiniApp 共用 `/miniapp-api/sumitalk-chat-jobs` 创建任务。
- `User-Agent: SumiTalk Native Android` 的任务在 `SUMITALK_CHAT_NATIVE_STREAM_ENABLED=1` 时走真实流式。
- 现有 MiniApp 任务继续走非流式，不改变原返回结构和轮询方式。
- 两种模式都通过同一个 `/v1/chat/completions` 入口，继续带：
  - `X-Reply-Channel: sumitalk`
  - `X-Reply-Target`
  - `X-Window-Id`
  - `X-Force-Last4`
  - `X-SumiTalk-Job-Id`

## 共用聊天管道

流式与非流式只在完成下列处理后才分叉：

- 请求和图片清洗
- 核心行为、思考规则、频道规则与 NSFW 规则
- 渡的身体状态、日常状态、Pixel Home
- 动态记忆、摘要、最近四轮、中期记忆
- 一起看、页笺、文游及网关工具
- 论坛、地图、网页搜索
- 音乐、QQ 群活动上下文
- 消息裁剪、动态系统消息排序和 prompt cache

不能为原生流式另造一套精简 prompt，也不能绕过原有存档和工具上下文。

## 实时事件与恢复日志

Worker 生成事件后先进入现有 realtime 进程间通道，`du-realtime` 的进程内 broker 直接转给活跃 SSE；另一个独立线程再异步追加 `SUMITALK_CHAT_QUEUE_DB` 的 `sumitalk_chat_run_events`。不引入 Redis。

- `(job_id, seq)` 为主键，`seq` 单调递增。
- `event_id` 固定为 `<job_id>:<seq>`，便于客户端幂等。
- 每个任务只允许一个终态事件。
- 实时通知队列与 SQLite 落库队列彼此独立；上一条事件写库变慢时，不会卡住下一条 reasoning、正文、工具或终态事件。
- job JSON 仍保留阶段、工具和终态摘要，兼容旧 MiniApp；token delta 只异步写 SQLite，避免每个 token 重写整份 JSON。SQLite 事件表只承担首次连接、断线重连和 sequence 缺口恢复。
- 终态已写入但 job JSON 未及时更新时，会从终态事件恢复 JSON 摘要，避免误判超时。
- 共用聊天路由在完成隐藏块、PCMD 和 reasoning 过滤后直接追加正文增量；worker 只聚合最终 OpenAI 响应，不再把同一段正文二次回放成事件。
- SumiTalk 流结束后立即收口 `assistant_final`；R2 存档、摘要和动态记忆进入单一 FIFO 后台队列，不再阻塞终态到达 App，同时保持多轮归档顺序。其他平台原有流式归档时序不变。

## 原生读取接口

### 断点轮询

`GET /miniapp-api/sumitalk-chat-jobs/<job_id>/events?after_seq=0&limit=100&wait_ms=0`

- 只返回 `seq > after_seq` 的事件。
- `wait_ms` 最大 25000，可用于长轮询。
- 返回 `event_seq`、`has_more`、`status` 和兼容的最终 `response`。

### SSE

`GET /miniapp-api/sumitalk-chat-jobs/<job_id>/events/stream?after_seq=0`

- 首次连接和携带 `after_seq` 的重连先从持久事件日志补齐已有事件，随后切到 realtime broker 直接推送。
- live 事件出现 sequence 缺口时回到持久日志补拉；realtime 通道不可用时，本地发布最多等待 150ms，失败后的 1 秒内不再让每条事件重复等待，随后使用 40ms SQLite 轮询兜底。正常活跃流不反复查询事件表。
- 15 秒发送一次 comment heartbeat。
- 发出终态事件后关闭连接。
- 响应带 `X-Accel-Buffering: no` 与 `Cache-Control: no-cache, no-transform`。

## 事件协议

- `run_started`
- `reasoning_started` / `reasoning_delta` / `reasoning_finished`
- `assistant_text_started` / `assistant_delta` / `assistant_text_finished`
- `tool_call_started` / `tool_arguments_delta` / `tool_output_delta`
- `tool_call_finished` / `tool_call_failed`
- `assistant_final`
- `run_error`
- `run_cancelled`

增量事件保留原始空格和换行。工具轮的中间对话单独作为消息 part 发送，最终正文不会再次重放这段中间对话；完整合并文本仍用于原有会话存档。

## 兼容与开关

- 环境变量：`SUMITALK_CHAT_NATIVE_STREAM_ENABLED=1`，默认开启。
- 设为 `0` 时，原生任务会退回现有非流 job 路径；终态事件和旧 job 查询仍可用。
- OpenRouter 若由现有策略强制非流，上层仍包装成 SSE 事件，不改变原生客户端协议。
- realtime 只负责活跃流低延迟投递，不是唯一恢复来源；SSE 断开后仍可用 `/events` 从 `after_seq` 继续。

## 共同游戏非流边界

- 原生普通聊天默认流式；请求顶层携带结构化 `game_id` 时，`private_board`、`wenyou`、`captivity_simulator` 强制走现有非流 job。
- `random_imitator_td` 是渡单人推进的植物大战丧尸，不在共同游戏豁免中，原生请求仍可流式。
- 其他平台仍由 `User-Agent` 边界保持非流；未知 `game_id` 不会靠文案关键词猜测或误关流式。
- `game_id` 只用于 transport 选择和日志，转发主网关前会从 body 移除；`X-SumiTalk-Game-Id` 保留可观测性。
- 现有走格棋和囚禁模拟器 `/sync-du` 唤醒、文游独立 GM 链本来就是非流，本轮不改其协议。以后原生游戏页若复用 SumiTalk job，必须显式传对应 `game_id`。

## 流式语音通话

后端已补齐通话方案中的专用接口：

- `POST /miniapp-api/voice-call/stream`：multipart 上传一轮音频，依次发 `phase`、`transcript`、`assistant_delta`、`assistant_done`、`done/error`。模型请求仍进入同一 `/v1/chat/completions`，保留 `X-Window-Id` 与 `X-Voice-Call-Slim: 1`，不另造提示词或注入链。
- 上游被现有 OpenRouter 策略强制非流时，主网关返回 `X-Du-Stream-Degraded: upstream_nonstream`，通话流转成 `degraded` 事件；真正的 reasoning、隐藏块和工具原始参数不会作为可听正文发出。
- `POST /miniapp-api/voice-call/tts-segment`：单段上限 120 字，复用 MiniMax TTS，但不写通话记录或 R2 媒体。
- `GET /miniapp-api/voice-call/tts-audio/<opaque-token>.<ext>`：本机共享临时目录保存 10 分钟，支持 Range，使用 `private, no-store`；随机 token 可跨 Web worker 读取。
- `POST /miniapp-api/voice-call/tts-cancel`：按 `turn_id` 删除尚未过期的临时音频。
- 旧 `POST /miniapp-api/voice-call`、普通 `/chat-media/transcribe` 和 `/chat-media/tts` 全部保留。

原生 App 的主通话模型文本已经通过持久 SumiTalk rich run event 流式到达，继续使用这条可补拉主链，避免再经 `/voice-call/stream` 生成第二份聊天 run 和本地消息。原生通话的分段播放已改接 `tts-segment`；`voice-call/stream` 用于录音整轮 fallback、旧 MiniApp 或后续不具备本机 STT 的客户端。

## 静默设备配对

- 新安装调用 `POST /miniapp-api/panel-auth/native-device/pair`，传入本地随机 `device_id` 和设备名，不恢复登录页。
- 请求头 `X-SumiTalk-Pairing-Secret` 使用 `SUMITALK_NATIVE_PAIRING_SECRET`；服务端未单独配置时沿用现有 `MINIAPP_PANEL_PASSWORD`，不向 APK 暴露 panel 签名密钥。
- 配对复用现有 trusted-device 存储和 panel token。已撤销的同一 `device_id` 返回 `403 device_revoked`，不会被静默解封。
- App 将换取的 panel token 存入 Android Keystore，接近过期时静默续期；普通 JSON 和 SSE 遇到 401 时最多恢复并重试一次。
- APK 构建时通过 Gradle property `sumitalk.nativePairingSecret` 或环境变量 `SUMITALK_NATIVE_PAIRING_SECRET` 注入同一密钥，密钥不写入仓库。

## 主动私聊可靠投递

- `services/conversation_followup.py` 为每条后端主动 SumiTalk 消息生成稳定 `message_id`。
- 同一 `message_id` 同时写入远端 history、持久 `deliver_chat_message` device action 和现有 realtime `assistant_message`；realtime 仍只做加速，不是唯一投递通道。
- device action 携带完整正文、`conversation_id`、`window_id`、role、sender 和 `created_at`，指定配对设备，最长保留 30 天。
- 原生 App 使用 `message_id` UPSERT 到现有 SQLite 聊天库，然后通过现有通知 inbox/presenter 展示备注名和头像；action 重试不会生成第二条气泡或第二条通知。
- 后端以后主动生成群消息时可使用同一 action 并传 `three-person-group`；现有 App 本地群聊生成路径不改。
- 日记评论已有 `entry_id + comment_id` 投递与去重，本轮没有重做。

## 验证

后端契约测试：

```bash
.venv/bin/python scripts/test_sumitalk_native_stream_backend.py
.venv/bin/python scripts/test_sumitalk_native_pairing_backend.py
.venv/bin/python scripts/test_sumitalk_native_proactive_delivery.py
.venv/bin/python scripts/test_voice_call_stream_backend.py
```

覆盖：原生/旧 MiniApp 模式选择、共同游戏非流与植物大战丧尸流式边界、通道头一致、共享注入链位置、实时发布先于异步落库、SQLite 阻塞不拖住后续事件与 `assistant_final`、首次恢复后不在活跃 SSE 轮询事件表、sequence 顺序和终态幂等、空格换行及同轮多段 reasoning 保留、worker 流/非流结果、富事件去重、工具轮顺序、SumiTalk 终态不等待 R2/记忆处理、配对成功/错误密钥/已撤销设备、主动消息三路共用稳定 ID、通话可见正文 SSE，以及临时 TTS URL 的 Range、取消和无 R2 写入。

原生仓库现有 `GatewayRunEventCodecTest`、`HttpSumiTalkChatGatewayClientTest` 与 `ChatRunEventReducerTest` 也应一起通过，用来确认事件字段、SSE/轮询降级和最终 part 对账与 App 当前实现一致。

## 当前状态

- 已部署的基础能力包括流式/非流共存、共同游戏非流边界、静默设备配对、主动消息持久投递、通话专用 SSE 与短 TTL segment TTS。
- 本轮已在本地完成 realtime broker 直推、通知/落库双队列、40ms SQLite 兜底、`assistant_final` 与后台归档解耦，以及同轮多段 reasoning 不再被首段正文提前截断。
- 本轮尚未 push、部署或重启，也未请求真实模型、写 R2、连接真实 App 或模拟器。
- 部署本轮改动时必须一起重启 `du-gateway.service`、`du-realtime.service` 和 `du-sumitalk-chat-worker.service`，再实测首事件延迟、长回复、多段 reasoning、多工具轮、断线续传、realtime 不可用兜底和终态先于后台归档。
- 当前工作区的植物大战僵尸相关源码与 `miniapp_static` 是未完成改动，不属于本次流式接入，不能混入提交。
