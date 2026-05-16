# Du Gateway 调试索引

这个文件用于快速定位问题。先按“现象”找入口，再看关键文件和日志关键词。

## 先做三件事

```bash
git status --short
tail -n 160 gateway.log
rg -n "报错关键词|接口名|函数名" routes services storage pipeline miniapp/src
```

服务器上的线上进程可能不在当前本地目录。先确认实际进程和部署路径：

```bash
ssh ali-du 'ps -ef | grep -E "[p]ython|[g]unicorn|[f]lask|[n]ode"'
ssh ali-du 'ss -ltnp 2>/dev/null | grep -E "(:5000|:8082|:8317)"'
```

## 核心文件地图

| 模块 | 主要文件 | 说明 |
| --- | --- | --- |
| 主聊天网关 | `routes/chat.py` | `/v1/chat/completions`，stream、tool loop、reasoning、归档 |
| 主聊天策略 | `services/entry_style_prompt.py`、`services/upstream_policy.py` | 入口风格 system、active upstream 选择、OpenRouter/CPA/Claude OAuth 请求策略 |
| 主聊天诊断/思维链 | `services/prompt_cache_debug.py`、`services/reasoning_utils.py`、`services/chat_content.py` | prompt/cache debug、reasoning/thinking 剥离、SSE message 解析、消息字符统计 |
| 注入管道 | `pipeline/pipeline.py` | core prompt、summary、last4、sense、dynamic memory、tools 注入 |
| MiniApp API | `routes/miniapp_api.py` | SumiTalk、设备、思维链、设置、贴纸、日历、上游切换等接口 |
| MiniApp 前端主壳 | `miniapp/src/ui/App.tsx` | 首页、聊天页、设置页、消息渲染、SumiTalk job |
| MiniApp 分页 | `miniapp/src/ui/tabs/*` | 日志、思维链、上游、日历、贴纸、记忆调试等子页 |
| R2 存储 | `storage/r2_store.py` | 会话、summary、动态记忆、设置、贴纸、设备状态、日程等 R2 key |
| 上游配置 | `storage/upstream_store.py` | active upstream、model cache、models 探测 |
| 主动消息 | `services/telegram_proactive.py` | 概率主动、主动决策、通道投递、trigger tick |
| 唤醒/续话 | `services/conversation_followup.py` | 事件唤醒、弹窗回执、查岗回应、延迟续话 |
| 设备工具 | `services/device_action_tools.py` | 弹窗、截图、系统闹钟等工具执行和卡片 |
| 论坛 MCP 工具 | `services/mcp_forum_tools.py`、`services/forum_mcp_client.py` | 论坛高层工具、`cli/get_guide` 映射、外部 SSE MCP 调用 |
| 设备状态注入 | `services/sense_context.py` | 电量、亮屏、前台 app、位置等 sense 注入 |
| 主动触发规则 | `services/proactive_trigger_engine.py` | 睡眠、亮屏、使用时长等硬触发 |
| Telegram Bot | `routes/telegram_webhook.py`、`services/telegram_update_queue.py`、`scripts/run_telegram_webhook_worker.py`、`services/telegram_bot.py` | Webhook 入队、持久队列、独立 worker 消费、TG 风格 system/上下文/发送 |
| Claude OAuth proxy | `scripts/claude_oauth_proxy.js` | 自用 Claude 反代、thinking/cache/tool 格式转换 |

## 聊天失败 / 上游不可用

现象：
- 客户端返回 `上游不可用`
- 日志有 `[Chat] ERROR`、`Upstream resp hint`
- 502 / 401 / 429 / 503

入口：
- `routes/chat.py::chat_completions`
- `routes/chat.py::_forward_to_ai`
- `services/upstream_policy.py::get_forward_targets`
- `storage/upstream_store.py`
- `config.py` 里的 `TARGET_AI_URLS` / `TARGET_AI_API_KEYS`

常查：

```bash
rg -n "Upstream resp hint|Chat 转发失败|上游不可用|429|401|503" gateway.log routes/chat.py
rg -n "TARGET_AI_URLS|TARGET_AI_API_KEYS|OPENROUTER|SILICONFLOW" .env config.py
```

注意：
- `/v1/models` 不一定能代表 chat 可用。
- OpenRouter / SiliconFlow / Claude OAuth proxy / CPA（Codex 反代）都有各自的模型和鉴权策略，排查时不要混用。
- 所有 `127.0.0.1:*` 上游地址在服务器上都指服务器自己，不是手机或本机 Mac。

## 上游切换失败

现象：
- MiniApp 上游切换显示 `fetch failed`
- 探活失败、models 为空、active 没变

入口：
- 前端：`miniapp/src/ui/tabs/SettingsUpstream.tsx`
- 后端：`routes/miniapp_api.py` 的 `/upstreams*`
- 存储：`storage/upstream_store.py`
- CORS：`app.py`

常查：

```bash
rg -n "upstreams|probe|models|Access-Control-Allow-Methods" routes/miniapp_api.py storage/upstream_store.py app.py miniapp/src/ui/tabs/SettingsUpstream.tsx
```

历史坑：
- 切换接口用 `PUT`，WebView 跨域时会先发 `OPTIONS` 预检。
- `app.py` 必须允许 `PUT/PATCH/DELETE/OPTIONS`，否则前端只看到 `Failed to fetch`。

## 思维链 / Prompt Cache 面板

现象：
- 思维链面板为空
- 普通聊天有，网关唤醒没有
- cache read/create 没显示

入口：
- 前端：`miniapp/src/ui/tabs/ReasoningTab.tsx`
- 后端：`routes/miniapp_api.py::miniapp_reasoning_latest`
- 收集：`routes/chat.py` reasoning/cache_debug 相关逻辑
- 存储：R2 conversation rounds，`storage/r2_store.py`

常查：

```bash
rg -n "reasoning|thinking|cache_debug|prompt_cache|X-DU-FOLLOWUP-ARCHIVE" routes services miniapp/src
```

关键规则：
- 面板只读 R2 会话归档里的 `assistant.reasoning` / `cache_debug` / `tool_calls`。
- 如果请求被判定为内部生成且没带 `X-DU-FOLLOWUP-ARCHIVE: 1`，就不会出现在面板。
- 事件唤醒默认应该归档，避免后面对话断层。
- `reasoning_details` 可能只有结构化块，没有可展示正文，面板会显示“adaptive thinking 但未返回正文”。

## SumiTalk 聊天 / 本地历史

现象：
- SumiTalk 发消息没响应
- job 一直 pending
- 本地聊天历史和后端历史不一致
- Today note 刷新变默认文案

入口：
- 前端：`miniapp/src/ui/App.tsx`
- 本地历史：`miniapp/src/ui/storage/chatHistoryDb.ts`
- 后端：`routes/miniapp_api.py` 的 `/sumitalk-chat*`、`/sumitalk-history`
- 主聊天：`routes/chat.py`

常查：

```bash
rg -n "sumitalk-chat|sumitalk-history|daily-whisper|Today note|chat_request_received|chat_response_ok" routes miniapp/src services gateway.log
```

注意：
- `sumitalk-chat` 走 job 包装，不是前端直接打 `/v1/chat/completions`。
- 回包 reasoning 会从客户端可见消息里剥离，但归档副本可能保留。
- Today note 刷新失败时不应该覆盖旧内容。
- 群聊链路慢先拆三段看：渡回复前端等待、笨笨任务创建、Codex bridge 认领/回写。前端不应为了远端历史保存或笨笨最终回复阻塞发送链路。
- 笨笨任务已创建后，应靠 realtime 或 `codex-group-chat-tasks/<id>` fallback 轮询贴回最终回复；不要在发送函数里一直等到 Codex 完成。
- 本机 Codex bridge 默认参数应偏快：`CODEX_GROUP_CHAT_POLL_SECONDS=0.5`、`CODEX_GROUP_CHAT_IDLE_POLL_SECONDS=1`、`CODEX_GROUP_CHAT_CLAIM_TIMEOUT_SECONDS=3`，并用短重试降低 `SSL EOF`/超时导致的随机拖延。
- VPS 系统盘读数突然抬高时，先查是否有高频整读本地状态文件：SumiTalk 安卓壳 realtime 断开后会每 20 秒 fallback 轮询 `/sumitalk-history/latest`，realtime 服务也会每 60 秒兜底读最新消息；`data/sumitalk_display_histories.json` 必须走缓存和行数/TTL 收口。
- `<voice>`/TTS 事故先查 `services/minimax_tts.py`：超长 voice 文本会被截断到 `MINIMAX_TTS_MAX_CHARS`，MiniMax 返回音频也受 `MINIMAX_TTS_MAX_AUDIO_BYTES` 限制，避免几千字语音把 CPU/内存/网络一起拖爆。
- QQ/SumiTalk/触发唤醒里看到 `{"action":"...","message":"...","channel":"..."}` 原样正文时，先查 `services/telegram_proactive.py::_parse_proactive_model_reply`、`_sanitize_control_reply_for_delivery` 和 `services/conversation_followup.py` 的外发清洗；这类 JSON 是主动决策控制格式，不应该作为用户可见正文发出。

## 和渡一起听 / 音乐旋律分析

现象：
- App 需要按歌名/歌手查一首歌的旋律和情绪段落描述
- 已有音频但不想长期保存音频，只想缓存文字分析结果
- OpenRouter/Gemini 音频分析失败或缓存没命中

入口：
- API：`routes/music_melody_api.py`
- 分析服务：`services/music_melody_analyzer.py`
- 文字缓存：`storage/music_melody_store.py`
- 配置：`config.py` 的 `MUSIC_ANALYSIS_*` / `MUSIC_PROMPT_VERSION`

接口：

```bash
GET  /api/music/listen/cache?title=歌名&artist=歌手
POST /api/music/listen/analyze
POST /api/music/listen/result
GET  /api/music/listen/recent
```

注意：
- 音频只在请求内读取并发给模型，不落库；缓存只存 `artist + title + provider + model + prompt_version` 对应的文字和结构化结果。
- 默认模型为 `google/gemini-3-flash-preview`，备用 `google/gemini-2.5-flash`；Lite 下架时不要再作为默认。
- 未命中缓存且没有上传普通音频文件时，接口会返回错误，不会自动扫描网易云/手机沙盒缓存。
- 这条通道是工具结果，不写入聊天记忆、不走普通对话归档；后续前端可以把结果作为“和渡一起听”的上下文使用。
- 本地脚本模式用 `scripts/analyze_music_file.py --title "歌名" --artist "歌手" song.mp3`；脚本本地调 OpenRouter/Gemini，只把分析后的 JSON 发到 `/api/music/listen/result`。

当前状态（2026-05-16）：
- 已完成：新增音乐旋律分析后端 MVP，包含缓存查询、上传分析、结果写入和最近缓存列表；音频不持久化，文字结果优先写 R2，未配置 R2 时落本地 `data/music_melody_cache.json`。本地脚本 `scripts/analyze_music_file.py` 可用同一份 Gemini Flash prompt 分析本地音频，再只上传文字结果。
- 已验证：`python3 -m py_compile` 覆盖 `storage/music_melody_store.py`、`services/music_melody_analyzer.py`、`routes/music_melody_api.py`、`scripts/analyze_music_file.py`、`app.py`；Flask `url_map` 确认 `/api/music/listen/*` 和 `/api/music-melody/*` 已注册；`scripts/analyze_music_file.py --help` 正常。
- 未完成 / 不要碰：MiniApp “和渡一起听”界面还没做；本轮没有改 `miniapp/src` 或 `miniapp_static`，也没有触碰 QQ connector、小爱音箱文件和既有半成品。

当前状态（2026-05-12）：
- 已完成并推送：`d6ca54a Stop log page error toasts` 已到 `main`；日志页不再弹应用内 `日志报错` toast，系统通知继续走后端 `log_error_alert` -> `show_system_notification` -> 安卓壳 `FloatingBallService` 的现有通知栏链路。
- 已验证：前端 `npm run build` 通过；Android `:app:compileDebugJavaWithJavac` 通过；远端 `main` 已确认到 `d6ca54a128d84d292be33367563c48036ef77a78`。
- 推送踩坑：普通 `git push` 多次被 SSH/HTTPS 网络层断开；最终用 `git send-pack` 通过 `ssh.github.com:443` + 本地 socks 代理推送成功。
- 未完成 / 不要碰：QQ connector 改动、小爱音箱接入文件、`pipeline.py`、`routes/miniapp/memory_panel.py`、共读文档、旧的未跟踪 `miniapp_static/assets/*` hash 资源仍是本地半成品或杂散产物；没有明确要求前不要 stage、commit、push、delete 或 revert。

当前状态（2026-05-13）：
- 已完成：SumiTalk 云端历史文件读取加了进程内 mtime/size 缓存，保存时会按 `SUMITALK_HISTORY_MAX_ROWS` / `SUMITALK_HISTORY_TTL_DAYS` 修剪历史行；realtime fallback 读最新消息复用同一缓存；MiniMax TTS 增加输入字数和返回音频大小上限。
- 已验证：`python3 -m py_compile` 覆盖 `services/sumitalk_history_file.py`、`routes/miniapp/sumitalk_history.py`、`services/realtime_app.py`、`services/minimax_tts.py`、TG/voice-call 调用侧和 MiniApp media 路由；`.venv/bin/python` 验证超长 `喵` 文本会截断到 800 字。
- 未完成 / 不要碰：服务器 SSH 仍无法连上，线上 14:30 崩前进程级 I/O 没能抓到；QQ connector、小爱音箱文件、共读文档仍是本地半成品，不属于本次止血改动。

当前状态（2026-05-13）：
- 已完成：主动/唤醒外发增加控制 JSON 兜底清洗；`send_message` JSON 只发送 `message` 字段，`diary/no_contact/other` JSON 会被拦截，避免 QQ `/push` 或后端唤醒把 `action/message/channel` 原样发给用户。
- 已验证：`python3 -m py_compile services/telegram_proactive.py services/conversation_followup.py`、`.venv/bin/python` 覆盖正常 JSON、双写引号 JSON、`send_message` 提取和 QQ/followup 外发拦截小自测；`git diff --check` 通过。
- 未完成 / 不要碰：没有清理或重写 QQ connector 当前半成品；本轮只加网关侧外发保险。

## Telegram Webhook / TG 回复延迟

现象：
- TG 日志出现 webhook 收到消息，但后面没有网关 chat / embedding / 转发日志
- gunicorn worker 回收后，15 秒输入聚合 buffer 消失

入口：
- Webhook 入队：`routes/telegram_webhook.py`
- 持久队列：`services/telegram_update_queue.py`
- 独立消费进程：`scripts/run_telegram_webhook_worker.py`
- 输入聚合和发送：`services/telegram_bot.py`

常查：

```bash
rg -n "TGHook|TGQueue|TGWorker|TGBot|webhook 已落持久队列|queue worker 消费|输入聚合" gateway.log
```

当前状态（2026-05-12）：
- 已完成：Webhook 只写 SQLite 持久队列；TG 输入聚合和回复发送由独立 worker 持有，避免 gunicorn `max_requests` 回收直接吞掉 pending buffer。
- 未完成：线上还需要把 `scripts/run_telegram_webhook_worker.py` 配成常驻进程；只重启 `du-gateway` 不会消费新队列。
- 不要碰：现有 `du-telegram-proactive` 是主动消息/闹钟调度，不是 webhook 消费 worker，不能拿它替代。

## 事件唤醒 / Trigger / 弹窗回执

现象：
- 点弹窗选项后没有收到消息
- 早安/睡眠/亮屏 trigger 没触发
- 触发后思维链没有记录

入口：
- 设备动作完成：`routes/miniapp_api.py::_wake_du_for_device_action_results`
- 唤醒发送：`services/conversation_followup.py::_send_wakeup_event`
- 主动触发：`services/proactive_trigger_engine.py`
- 调度入口：`services/telegram_proactive.py::schedule_tick`

常查：

```bash
rg -n "choice_dialog|screen_check|proactive_trigger|send_proactive_trigger_wakeup|X-DU-FOLLOWUP-ARCHIVE|主动硬触发" routes services gateway.log
```

关键规则：
- 事件唤醒走最近对话入口或主动入口发送。
- 事件唤醒默认归档，保证后续对话能接上。
- SumiTalk 直接推送不稳定时，可能会转走 QQ/微信/TG 主动入口。
- 延迟续话 followup 不是同一种事件唤醒，默认仍可跳过归档。

## 设备状态 / 查岗 / 截图

现象：
- 设备状态没注入
- 截图工具没返回图片
- 查手机结果和回复不匹配

入口：
- Sense 上报：`routes/sense_api.py` 的 `/api/sense`
- 状态上报：MiniApp 设备状态路由的 `/device-state/*`
- 截图：`routes/miniapp_api.py` 的 `/device-screenshots*`
- 原生动作队列：`services/device_action_tools.py`
- Sense 注入：`services/sense_context.py`
- 前端/Android 桥：`miniapp/src/plugins/sumi-overlay.ts`

常查：

```bash
rg -n "device-state|device-screenshots|screen_check|sense|foreground-app|usage-stats|battery" routes services miniapp/src
```

注意：
- 截图不是偷偷读屏，必须由客户端授权/执行后回传。
- 图片会增加大量 token，图片压缩和描述归档在聊天清洗链路里查。
- 悬浮球旁边的旧气泡能力已移除；日志告警改投 SumiTalk 安卓壳的 `show_system_notification` 系统通知，会走顶部消息提醒通道。日志页实时错误提醒不要用 app 内 toast；通知栏提醒由后端 `log_error_alert` 投递现有 `show_system_notification` 动作给安卓壳处理。后续推送优先试 FCM，不行再接 ntfy。

当前状态（2026-05-12）：
- 已拆：根路由 `/api/sense` 和 location/health normalize helper 已从 `app.py` 移到 `routes/sense_api.py`，公开路径和 R2 写入行为不变。
- 未完成 / 不要碰：MiniApp device-state、截图、原生动作队列仍维持现有文件边界；不要把 QQ connector、小爱文件、共读文档或旧 `miniapp_static/assets/*` hash 资源混进这轮拆分。

## 图片 / token 暴涨

现象：
- 输入 token 突然高很多
- 图片一张就几千 token
- last4 里图片变 `[图片]` 或描述不对

入口：
- `pipeline/pipeline.py::step_clean_images_and_save_desc`
- `routes/chat.py` 请求清洗和归档
- MiniApp 消息解析：`miniapp/src/ui/App.tsx`

常查：

```bash
rg -n "image|image_url|图片|desc|last4|step_clean_images" pipeline routes miniapp/src
```

关键规则：
- 上游 usage 的 input 可能包含缓存读入部分，Anthropic/OpenAI 字段口径不同。
- MiniApp 显示的 token 来自模型返回的 usage，不一定等于网关估算。
- 图片应尽量转描述后归档，避免后续 last4 持续带图。

## 工具调用结果错位

现象：
- `GET_TIME_INFO` 显示成闹钟创建结果
- 工具 call/result 对不上

入口：
- `routes/chat.py::_collect_tool_trace_from_messages`
- `services/device_action_tools.py`
- 思维链面板：`routes/miniapp_api.py::miniapp_reasoning_latest`

常查：

```bash
rg -n "tool_calls|tool_call_id|_collect_tool_trace|create_system_alarm|GET_TIME_INFO" routes services
```

关键规则：
- 工具结果优先按 `tool_call_id` 对齐。
- 没有 id 时只能按附近顺序兜底，最容易错位。

## 论坛 MCP / tools 缓存抖动

现象：
- 一用论坛工具后 Anthropic prompt cache 大段重写
- `cache_read` 只剩 tools 附近，静态区重新 `cache_creation`
- 下一轮明明只是续聊，但 tools 区像变了

入口：
- 注入入口：`pipeline/pipeline.py::step_inject_forum_tools`
- 工具定义/执行：`services/mcp_forum_tools.py`
- 外部 SSE MCP 客户端：`services/forum_mcp_client.py`

常查：

```bash
rg -n "step_inject_forum_tools|get_forum_tools_for_inject|list_tools|cli|get_guide" pipeline services
```

关键规则：
- 工具调用结果在 `messages` 里，下一轮模型能看到，不会改变 `tools` 区。
- 不要把远端 MCP `list_tools()` 放进每轮 prompt 构造路径；远端 schema/description 抖动会让 `tools` 前缀失配。
- `cli/get_guide` 可以保留，但展示给模型的工具定义应本地固定、短、稳定；真正执行时再连外部 SSE MCP。
- 如果缓存因论坛工具重写，先查 `tools` 定义是否动态变化，不要先怀疑 tool result 被插进静态区。

## 日程 / 系统闹钟

现象：
- 闹钟创建了但 SumiTalk 没显示
- 系统闹钟卡片重复
- 日程到点没触发

入口：
- 日程 API：`routes/miniapp_api.py` 的 `/schedule/items*`
- 调度：`services/schedule_runtime.py`
- 工具：`services/device_action_tools.py::execute_create_system_alarm`
- R2：`storage/r2_store.py` 的 schedule keys

常查：

```bash
rg -n "schedule|alarm|create_system_alarm|SUMITALK_CARD|schedule_runtime" routes services storage miniapp/src
```

## 主动消息

现象：
- 很久没主动联系
- 主动发到了错误通道
- 主动消息太频繁或不触发

入口：
- 调度：`services/telegram_proactive.py::schedule_tick`
- 概率主动：`services/telegram_proactive.py::proactive_tick`
- 硬触发：`services/proactive_trigger_engine.py`
- 投递：`services.telegram_proactive._dispatch_send`
- 最近通道：`storage/r2_store.py` 的 last reply channel

常查：

```bash
rg -n "主动|proactive|last_reply_channel|last_proactive|trigger" services storage routes gateway.log
```

注意：
- SumiTalk 暂不一定作为主动投递主通道。
- 最近真实对话入口会影响弹窗/trigger 回发通道。
- 主动 trigger 和概率主动不是一回事。
- 微信/QQ `/push` 中文正文要显式按 UTF-8 bytes 发送；如果日志出现 `latin-1 codec can't encode characters`，先查 `WECHAT_PROACTIVE_PUSH_TOKEN` / `QQ_PROACTIVE_PUSH_TOKEN` 是否把 `.env` 行尾中文注释带进 header，再查 `services/telegram_proactive.py` / `services/conversation_followup.py` 的主动投递请求体编码。
- 微信 connector 日志出现 `This operation was aborted` 多半是 `getupdates` 长轮询超时；查 `WECHAT_ILINK_GETUPDATES_TIMEOUT_MS`，默认 75 秒，普通请求仍走 `WECHAT_ILINK_HTTP_TIMEOUT_MS`。

## 记忆 / 总结 / 动态层

现象：
- 回答像没记忆
- 动态记忆召回不准
- 一周/长期画像没更新

入口：
- 注入：`pipeline/pipeline.py::step_inject_summary`、`step_inject_dynamic_memory`、`step_inject_latest_4_rounds_for_new_window`
- R2：`storage/r2_store.py`
- 动态层：`services/dynamic_layer_ds.py`
- 维护：`services/memory_maintenance.py`
- MiniApp 调试页：`miniapp/src/ui/tabs/MemoryDebugTab.tsx`

常查：

```bash
rg -n "dynamic_memory|summary|latest_4|core_cache|portrait|maintenance|recall_debug" pipeline services storage routes miniapp/src
```

关键规则：
- 普通聊天归档后才会触发后续总结/动态层。
- 内部维护请求和部分 followup 请求可能跳过归档。
- `X-Force-Last4` 会强制带最近 4 轮。
- 动态层 DS 现在优先要求固定标签格式（`ACTION:` / `CONTENT:` 等），旧 JSON 只作为兼容解析；`new/merge` 的 `content` 如果太短、像半句话或标题词，会重试一次，仍不完整则 skip，不写入 R2。

当前状态（2026-05-15）：
- 已完成：`services/dynamic_layer_ds.py` 单轮/批量解析都兼容固定标签格式，`scripts/archive_ds_prompt.txt` 已从 JSON 数组改成每轮固定标签块；残缺便签会被质量门槛拦住。
- 已验证：`.venv/bin/python -m py_compile services/dynamic_layer_ds.py scripts/test_dynamic_layer_ds_parser.py`、`.venv/bin/python scripts/test_dynamic_layer_ds_parser.py`。
- 未完成 / 下次先查：历史 R2 里已经写进去的残缺动态记忆不会自动清理；如果要修旧数据，先走 MiniApp memory debug 或维护脚本，别直接手删 R2。

## 核心 Prompt / 风格规则 / 禁言模式

现象：
- 渡突然冷冰冰
- 风格规则没生效
- 禁言模式不生效或忘记关闭

入口：
- 核心 prompt：`routes/miniapp_api.py` 的 `/core-prompt`
- 核心行为注入：`pipeline/pipeline.py::step_inject_core_behavior_rules`
- SumiTalk 风格：`routes/chat.py::_inject_miniapp_style_system`
- TG 风格：`services/telegram_bot.py::build_telegram_style_system`
- 禁言模式：`storage/silence_mode_store.py`、`routes/chat.py::_inject_silence_mode_system`

常查：

```bash
rg -n "core-prompt|核心|入口风格|SumiTalk|禁言|silence" routes services pipeline storage miniapp/src
```

注意：
- 禁言模式只约束最终可见回复，不限制工具调用和内部处理。
- 风格 system 的位置会影响 prompt cache 静态区命中。
- 写系统类、规则类提示词时，先看 `AGENTS.md` 的“提示词写法规则”：优先第二人称或无人称；参考段落只用于判断写法风格，不要把示例里的具体互动内容照搬成默认规则。

当前状态（2026-05-12）：
- 已完成：`AGENTS.md` 已补“提示词写法规则”，并把现有 AGENTS 表述收成第二人称/无人称风格；刚才误把参考段落的具体互动内容写进去，已删除，只保留写法口吻规则。
- 未完成 / 不要碰：没有改运行时核心 prompt、SumiTalk/TG 风格注入或 DS 总结提示词；后续只有明确要调线上人格/风格时再改对应入口。

当前状态（2026-05-13）：
- 已完成：语音台词撰写规范已抽到 `services/voice_line_prompt.py`，并注入 QQ/TG 的 `<voice>` 规则与 `X-Voice-Call-Slim` 语音通话回复；只约束会被朗读的语音文本，不改普通文字聊天、核心 prompt 或 DS 总结提示词。
- 未完成 / 不要碰：这次不处理 voice prompt 之外的风格规则；不要把这份规范做成 Codex skill，也不要塞进全局普通聊天 prompt。

## Claude OAuth proxy / token sync

现象：
- Claude OAuth proxy 401
- Claude OAuth proxy refresh 失败
- thinking/cache/tool 格式不对
- Claude 看不了图

入口：
- Claude OAuth proxy 实现：`scripts/claude_oauth_proxy.js`
- 服务器 Claude 上游配置：`.env` 的 `TARGET_AI_URLS`
- 网关转发：`routes/chat.py`
- 上游选择：`storage/upstream_store.py`
- 本机 token 同步脚本：`/Users/doraemon/claude-token-sync.sh`
- 本机 LaunchAgent：`/Users/doraemon/Library/LaunchAgents/com.doraemon.claude-token-sync.plist`

常查：

```bash
rg -n "claude|anthropic|thinking|cache_control|tool_use|oauth|8317|8082" scripts routes storage .env
ssh -o ControlMaster=no ali-du 'ss -ltnp 2>/dev/null | grep -E "(:5000|:8082|:8317)"'
ssh -o ControlMaster=no ali-du 'systemctl --user list-units --type=service --all | grep -Ei "claude|proxy|oauth"'
```

注意：
- Claude OAuth proxy 是 Claude 反代，不是 CPA。CPA 另有一节，按 Codex 反代排查。
- 不要擅自改 `/Users/doraemon/claude-token-sync.sh` 的默认重启服务；默认应是 `claude-oauth-proxy.service`。只有用户明确说服务名变了，才改 `CLAUDE_PROXY_SERVICE` 或脚本默认值。
- Claude OAuth proxy 401 不要先猜模型，先分清是哪层 401：
  - `Invalid proxy key` / `AUTH REJECTED`：网关到代理的 key 不匹配，查 `.env` 的 `TARGET_AI_API_KEYS` 和代理服务配置。
  - `<= 401 /v1/chat/completions`、`Got 401`、`Refresh failed`：代理到 Anthropic / Claude OAuth 的 token 问题，优先查 token sync。
  - `Refresh failed: HTTP 403 ... Just a moment... Cloudflare`：服务器自己刷新 token 被 Cloudflare 挡住，不能指望远端自动刷新；要用 Mac 本地 Keychain 的 token 同步到 VPS。
  - `429`：额度/限流，不是 token sync 能修。

### Claude token sync 快查

这套脚本是为了修 Claude OAuth proxy 401：从 Mac 本机 Claude Code Keychain 取 OAuth JSON，必要时本地刷新，然后通过 HTTP POST 同步到 VPS 的 Claude OAuth proxy。不要再把“同步 token”做成 SSH 写文件 + 重启服务的主链路。

关键路径：
- 脚本：`/Users/doraemon/claude-token-sync.sh`
- LaunchAgent：`/Users/doraemon/Library/LaunchAgents/com.doraemon.claude-token-sync.plist`
- 本机日志：`/Users/doraemon/claude-token-sync.log`
- launchd stdout/stderr：`/Users/doraemon/claude-token-sync.launchd.log`、`/Users/doraemon/claude-token-sync.launchd.err`
- 状态文件：`/Users/doraemon/.claude-token-sync.state`、`/Users/doraemon/.claude-token-sync.wake`
- 本机 Keychain service：`Claude Code-credentials`
- 远端 Claude OAuth auth 文件：`/home/nora/.cli-proxy-api/claude-sumikamiss@gmail.com.json`
- Claude OAuth proxy 内部同步接口：`POST /internal/oauth-sync`
- 网关转发同步接口：`POST /internal/claude-oauth-sync`
- 网关转发状态接口：`GET /internal/claude-oauth-status`
- 本机私有配置：`/Users/doraemon/.claude-token-sync.env`

LaunchAgent 默认 `StartInterval=300`，也就是约 5 分钟跑一次。脚本先查本机 Keychain token 是否接近过期，必要时本机刷新后 POST；远端状态接口若报告新 401 或远端 token 比本机旧，也会触发 POST。远端 401 只是补救信号，不再是主链路。

本机配置示例（不要提交，不要贴密钥）：

```bash
CLAUDE_PROXY_SYNC_URL=https://duxy-home.com/internal/claude-oauth-sync
CLAUDE_PROXY_STATUS_URL=https://duxy-home.com/internal/claude-oauth-status
CLAUDE_PROXY_SYNC_KEY=...
```

服务端约束：
- `scripts/claude_oauth_proxy.js` 的同步接口用 `CLAUDE_OAUTH_SYNC_KEY` 校验；未配置时默认复用 `PROXY_KEY`。
- Claude OAuth proxy 应继续只监听服务器本机或内网；公网只暴露网关转发接口或受控内网入口。
- 同步接口只接收完整 OAuth JSON，验证 `accessToken/refreshToken/expiresAt`，原子写入 `CLAUDE_OAUTH_FILE`，并热更新内存 token，不需要 `systemctl restart`。

先查本机脚本有没有跑：

```bash
launchctl print gui/$(id -u)/com.doraemon.claude-token-sync | sed -n '1,80p'
tail -n 80 /Users/doraemon/claude-token-sync.log
tail -n 80 /Users/doraemon/claude-token-sync.launchd.err
```

需要立刻同步时：

```bash
bash -n /Users/doraemon/claude-token-sync.sh
/Users/doraemon/claude-token-sync.sh --force
launchctl kickstart -k gui/$(id -u)/com.doraemon.claude-token-sync
```

查远端 Claude OAuth proxy 服务：

```bash
ssh -o ControlMaster=no ali-du 'systemctl --user is-active claude-oauth-proxy.service'
ssh -o ControlMaster=no ali-du 'ss -ltnp 2>/dev/null | grep -E "(:8082|:8317)"'
ssh -o ControlMaster=no ali-du 'journalctl --user -u claude-oauth-proxy.service -n 120 --no-pager -o cat | grep -Ei "401|refresh|auth file|cloudflare|error|model"'
```

确认 token 是否已同步成功：
- 本机日志应出现类似：`synced oauth via_http reason=... oauth_ready refreshed=...`
- 远端 Claude OAuth proxy 日志应出现 `OAuth synced by HTTP`，或状态接口返回新的 `expiresAt`。
- `launchctl print ...` 里 `last exit code` 应为 `0`

先确认当前 active upstream 指向哪条线，别把 Claude OAuth proxy 和 CPA 混在一起：

```bash
ssh -o ControlMaster=no ali-du 'cd /root/du-gateway && .venv/bin/python - <<'"'"'PY'"'"'
from storage.upstream_store import load_upstreams, get_cached_active_model
data = load_upstreams()
items = data.get("items") or []
active = int(data.get("active") or 0)
item = items[active] if 0 <= active < len(items) else {}
print("active=", active)
print("url=", item.get("url") or "")
print("model=", get_cached_active_model(refresh_if_missing=False))
PY
'
```

如果 active URL 确认是 Claude OAuth proxy，再对该 URL 做最小 chat 探活；如果 active URL 是 CPA/Codex 反代，转去 CPA 章节排查。若 Claude OAuth proxy 仍是 `401`：
1. 先看 `/Users/doraemon/claude-token-sync.log` 最新一轮有没有 `synced oauth via_http`。
2. 看 `launchd.err` 有没有 `claude_local_refresh_failed`、`429`、`did_not_update_keychain`。
3. 用 `GET /internal/claude-oauth-status` 看远端 `expiresAt`、`lastUnauthorizedAt`。
4. 看远端 `claude-oauth-proxy.service` journal 是否继续 `Refresh failed: HTTP 403 ... Cloudflare`。
5. 确认脚本走的是 Claude OAuth sync URL，不要把 CPA/Codex 反代服务混进来。

当前状态（2026-05-16）：
- 已纠正：不要把 Claude OAuth proxy 和 CPA 混在一起；Claude 401 先查 Claude OAuth proxy 和 token sync。
- 已撤回：刚才把 token sync 默认重启服务改成 `cliproxyapi.service` 是错误改动，已改回 `claude-oauth-proxy.service`。
- 已改动：token sync 主链路改为 HTTP POST；新增 Claude proxy 内部同步/状态接口，网关新增 `/internal/claude-oauth-sync` 和 `/internal/claude-oauth-status` 转发。
- 已部署：`/home/nora/claude-proxy/proxy.js` 已更新并重启 `claude-oauth-proxy.service`；服务器本机 `GET /internal/oauth-status`、`POST /internal/oauth-sync` 已验证通过。
- 已配置：`/Users/doraemon/.claude-token-sync.env` 已创建；本地 `CLAUDE_PROXY_SYNC_KEY` 已同步到服务器 `/home/nora/claude-proxy/.env` 的 `CLAUDE_OAUTH_SYNC_KEY`，不要打印或提交该 key。
- 未完成 / 下次先查：线上网关实际目录在 `/root/du-gateway`，当前 `nora` 用户无 sudo、无 `/root/du-gateway` 写权限，网关转发路由尚未部署到线上；`https://duxy-home.com/internal/claude-oauth-status` 当前仍是 404。启用 Mac 端公网 POST 前，需要部署网关 route 或配置一个可达的内网/VPN 同步 URL。

## CPA / Codex 反代

现象：
- Codex 反代不可用
- Codex 相关 401 / 429 / 503
- Codex 模型列表、模型权限或限流异常

入口：
- CPA 是 Codex 反代，不是 Claude OAuth proxy。
- `.env` 里的上游 URL / key 可能同时配置 Claude OAuth proxy、OpenRouter、SiliconFlow、CPA 等；看 active upstream 时必须先确认当前 URL 指向哪一类服务。

常查：

```bash
rg -n "Codex|codex|CPA|cliproxy|proxy|upstream|TARGET_AI_URLS|TARGET_AI_API_KEYS" docs scripts routes storage .env
ssh -o ControlMaster=no ali-du 'ss -ltnp 2>/dev/null | grep -E "(:5000|:8082|:8317)"'
ssh -o ControlMaster=no ali-du 'systemctl --user list-units --type=service --all | grep -Ei "codex|cliproxy|proxy|cpa"'
```

注意：
- CPA 和 Claude OAuth proxy 都可能长得像 OpenAI-compatible `/v1/chat/completions`，但鉴权、token 刷新、限流来源不是一回事。
- Claude OAuth proxy 的 401 不要按 CPA 处理；CPA 的 Codex 限流/鉴权也不要用 Claude token sync 解释。

## 前端构建 / APK

现象：
- 改了前端但手机没变
- 网页能用，APK 不行
- 502 后 MiniApp 空白

入口：
- 源码：`miniapp/src/ui/*`
- 构建脚本：`miniapp/package.json`
- 静态产物：`miniapp_static/*`
- Android：`miniapp/android`

常用命令：

```bash
npm -C miniapp run build
npm -C miniapp run cap:copy
npm -C miniapp run android
```

注意：
- `npm -C miniapp run build` 会更新 `miniapp_static` 的 hash 资源。
- 前端静态产物要随源码一起提交，否则服务器页面不会变。

## 日志关键词

| 场景 | 关键词 |
| --- | --- |
| 主聊天 | `[Chat]`、`chat_request_received`、`chat_response_ok`、`Upstream resp hint` |
| SumiTalk | `[sumitalk]`、`sumitalk-chat`、`history` |
| 主动消息 | `[TGPro]`、`主动发消息`、`主动硬触发`、`proactive` |
| 设备状态 | `device-state`、`foreground-app`、`usage-stats`、`battery` |
| 唤醒 | `choice_dialog_wakeup`、`screen_check`、`followup` |
| 思维链 | `reasoning`、`thinking`、`cache_debug`、`prompt_cache_debug` |
| 上游 | `upstream`、`models`、`probe`、`429`、`401`、`503` |

## 建议拆分顺序

先建索引，再小步拆分。不要一次性大重构。

当前状态（2026-05-12）：
- 已完成：`app.py` 已拆出 SumiTalk job、Codex group task、`/api/sense`、MiniApp 静态入口/资源/app-version/favicon、`/time-info`、`/time-now`、根记忆读取和写入工具路由；公开路径保持不变，已做 py_compile、import 使用检查、Flask url_map 检查和 diff 空白检查。
- 未完成 / 不要碰：`AGENTS.md` 的提示词写法修正、QQ connector、小爱文件、共读文档、旧 `miniapp_static/assets/*` hash 资源仍是本地未推内容；继续拆分时只碰当前明确选中的代码边界。

当前状态（2026-05-13）：
- 已完成：`routes/co_read_api.py` 的共读纯逻辑已拆到 `services/co_read_flow.py`，书籍保存/小节替换/标记归一化 helper 已拆到 `services/co_read_books.py`；路由文件保留 Flask 请求、聊天管道调用、卡片更新和响应拼装。
- 已验证：`python3 -m py_compile services/co_read_flow.py services/co_read_books.py routes/co_read_api.py routes/miniapp/co_read.py`、`.venv/bin/python` 路由导入与共读解析/切段/quote 定位小自测、`git diff --check` 均通过。
- 未完成 / 不要碰：QQ connector、小爱音箱文件、共读需求文档仍是本地半成品；本轮拆分没有改前端、静态产物或线上部署。后续继续拆分可优先看 `routes/chat.py` 或把共读卡片更新进一步拆到独立 service。

当前状态（2026-05-16）：
- 已完成：`routes/chat.py` 拆出入口风格 prompt 到 `services/entry_style_prompt.py`，拆出 active upstream / OpenRouter / Claude OAuth / CPA 请求策略到 `services/upstream_policy.py`；路由文件保留请求入口、stream/non-stream 转发、tool loop、归档和响应拼装。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/entry_style_prompt.py services/upstream_policy.py`、入口风格构造小检查、`services.upstream_policy` 轻量函数调用、`git diff --check` 均通过。
- 未完成 / 不要碰：`connectors/qq_onebot/src/main.js`、小爱文件、共读文档、`miniapp_static/assets/*` 仍是本地半成品/构建产物；继续拆分可优先看 `routes/chat.py` 的 prompt-cache/reasoning/tool-loop，或 `storage/r2_store.py` 的 R2 key 分组。

当前状态（2026-05-16 续）：
- 已完成：继续拆 `routes/chat.py`，把 prompt/cache debug 移到 `services/prompt_cache_debug.py`，把 reasoning/thinking 剥离、SSE chunk 清洗、流式 message 解析移到 `services/reasoning_utils.py`，把通用消息字符统计移到 `services/chat_content.py`；`routes/chat.py` 约 1966 行，主要剩请求管线、stream/non-stream、tool loop、归档和 sidecar。
- 已修正：同文件工具重试路径使用 `copy.deepcopy` 但缺少 `import copy`，已补 import。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/chat_content.py services/prompt_cache_debug.py services/reasoning_utils.py services/entry_style_prompt.py services/upstream_policy.py`、新服务 smoke check、`routes.chat` import check、`git diff --check` 均通过。
- 未完成 / 不要碰：`app.py`、`config.py`、QQ connector、小爱/音乐相关文件、共读文档、`miniapp_static/assets/*` 仍是本地已有改动或半成品；继续拆分可优先看 `routes/chat.py` 的 tool-loop/归档 sidecar，或转拆 `storage/r2_store.py`。

1. `routes/miniapp_api.py`
   - 已拆：SumiTalk chat job 路由和任务状态机已移到 `routes/miniapp/sumitalk_chat_jobs.py`；`/sumitalk-chat` 与 `/sumitalk-chat-jobs*` 路径保持不变
   - 已拆：Codex group chat task 路由已移到 `routes/miniapp/codex_group_chat.py`；`/codex-group-chat-tasks*` 路径保持不变
   - `miniapp_auth.py`
   - `miniapp_device.py`
   - `miniapp_reasoning.py`
   - `miniapp_settings.py`
   - `miniapp_upstreams.py`

2. `app.py`
   - 已拆：`/api/sense` 已移到 `routes/sense_api.py`
   - 已拆：MiniApp 静态入口、静态资源、app-version 和 favicon 已移到 `routes/miniapp_static.py`
   - 已拆：`/time-info` 和 `/time-now` 已移到 `routes/time_api.py`
   - 已拆：`/summary`、`/dynamic-memory`、`/api/memory/append` 和 `/api/cc_log` 已移到 `routes/memory_api.py`
   - 后续可拆：root/health 或 CORS/setup 边界；再往后优先看 `routes/chat.py`

3. `miniapp/src/ui/App.tsx`
   - 聊天页面
   - 首页
   - 设置页
   - 消息渲染
   - SumiTalk job/client

4. `routes/chat.py`
   - 已拆：入口风格 system 构造移到 `services/entry_style_prompt.py`
   - 已拆：上游选择、active 模型策略、OpenRouter 请求策略移到 `services/upstream_policy.py`
   - 已拆：prompt-cache / cache debug 移到 `services/prompt_cache_debug.py`
   - 已拆：reasoning/thinking/SSE message 解析移到 `services/reasoning_utils.py`
   - 已拆：消息内容字符统计移到 `services/chat_content.py`
   - stream handling
   - tool loop
   - archive/reasoning collection

5. `routes/co_read_api.py`
   - 已拆：共读切段、prompt/card context、模型结果解析、quote 定位移到 `services/co_read_flow.py`
   - 已拆：共读书籍保存、小节替换、标记归一化移到 `services/co_read_books.py`
   - 后续可拆：`_update_co_read_card_for_section` 和聊天管道调用包装

6. `storage/r2_store.py`
   - 先建 R2 key registry
   - 再按 conversation / memory / miniapp config / schedule / stickers 分组迁移
