# Du Gateway 当前实现索引

本文件只登记已经完成、当前仍有效的实现。它是代码导航和运行边界索引，不是施工日志、待办清单或历史归档。

维护规则：

- 未落地内容写入对应的方案文档，不写进本索引。
- 功能、路由、文件或兜底失效时，先删除旧索引，再登记替代实现。
- 每次功能改动收尾都要核对本文件；不能只追加新条目而保留冲突旧说法。
- 索引结论必须能由当前代码入口、运行配置或定向验证证明。

## 1. 仓库与产品边界

| 范围 | 当前实现 |
| --- | --- |
| 网关后端 | 本仓库 `/Users/doraemon/Downloads/du-gateway` |
| 原生 Android App | `/Users/doraemon/Downloads/sumitalk-android-native`，是当前主要产品界面 |
| MiniApp | 本仓库 `routes/miniapp/*` 与 `miniapp_static/`，主要承接管理、调试、历史兼容和 Web 专属功能 |
| 聊天入口 | QQ、Telegram、微信、SumiTalk、主动唤醒共用同一聊天、提示词、工具、记忆和归档主链路 |
| 窗口标识 | `X-Window-Id` 只标识上下文；当前没有聊天白名单/黑名单分流 |
| Notion | 运行链已移除；当前数据不依赖 Notion API |

## 2. 应用入口与路由

### 2.1 Flask 入口

- 应用装配：`app.py`
- 生产启动：`scripts/start_gateway_prod.sh`
- 聊天代理：`routes/chat.py`
- 管理接口：`routes/admin.py`
- 原生 App / MiniApp 聚合：`routes/miniapp_api.py`
- 静态 MiniApp：`routes/miniapp_static.py`

`app.py` 当前注册：聊天、管理、Telegram webhook、MiniApp API、MCP、PC 指令、共读、渡的页笺、记忆、MiniApp 静态资源、感知、时间、Claude OAuth 同步、音乐分析、内部 STT、小爱音箱和 AI 农场代理。

### 2.2 核心公开接口

| 用途 | 路径 |
| --- | --- |
| 健康检查 | `GET /health` |
| 模型列表 | `GET /v1/models`、`GET /models` |
| 聊天代理 | `POST /v1/chat/completions`、`POST /chat/completions` |
| 最近窗口 | `GET /admin/windows` |
| 状态概览 | `GET /admin/status` |
| 窗口轮次 | `GET /admin/windows/<window_id>/rounds` |
| MiniApp / 原生 App 后端 | `/miniapp-api/*` |
| Telegram webhook | `/telegram/webhook/*` |
| 共读 | `/api/co-read/*` 与 `/miniapp-api/co-read/*` |
| 小爱音箱 | `/api/xiaoai/*` 与 `/miniapp-api/xiaoai/*` |
| MCP | `/mcp/health`、`/mcp/tools`、`/mcp/invoke` |
| 渡的页笺公开预览 | `/du-pages/v/<page_id>` |

## 3. 聊天、上游与提示词

| 能力 | 代码入口 | 当前边界 |
| --- | --- | --- |
| 请求接收、流式响应、工具循环、隐藏标记 | `routes/chat.py` | 所有支持入口走统一主链路 |
| Pipeline 组装与归档 | `pipeline/pipeline.py` | 负责上下文、记忆、工具与回合后处理 |
| 请求清洗 | `pipeline/cleaner.py` | 统一清洗入口消息与上游消息结构 |
| 上游策略 | `services/upstream_policy.py` | active upstream / model 只由 App 明确保存更新 |
| 上游持久选择 | `storage/upstream_store.py` | 探活、拉模型和普通请求不能覆盖已保存选择 |
| 提示词管理 | `services/prompt_manager.py` | App 可编辑的静态 Prompt 分区统一从这里管理 |
| 入口风格 | `services/entry_style_prompt.py` | 按真实聊天入口注入对应风格 |
| 语音台词规范 | `services/voice_line_prompt.py` | 语音输出场景统一使用该规范 |
| 工具定义与执行 | `services/chat_tools.py` | 当前网关原生工具集中入口 |
| 网关工具辅助 | `services/chat_tool_helpers.py`、`services/gateway_tools.py` | 领域工具复用同一执行边界 |
| 工具使用摘要缓存 | `services/tool_result_cache.py`、`storage/runtime_sqlite.py` | 工具循环结束后一次性写本地 SQLite；结果按工具清洗，不保存原始大 JSON；24 小时 TTL，超过约 5k tokens 时按完整旧记录收缩到约 3.5k |
| Claude thinking 连续性 | `services/claude_thinking_carryover.py` | 普通对话回传 opaque signature，不回灌转写 thinking 文本 |
| Prompt Cache 诊断 | `services/prompt_cache_debug.py` | 记录静态/动态构成与上游 usage 元数据 |

当前 Claude 缓存前缀顺序固定为：工具定义 → 静态 system → 最近工具使用摘要 → SumiTalk Real/App 互斥提示 → play 小纸条 → 较稳定近期记忆 → 最近记忆。四个断点依次落在工具定义、静态 system、工具摘要和最近记忆末尾；工具循环内部只收集结果，整条工具链收口后才批量更新摘要块。play 小纸条仍由 `services/pixel_home.py` 生成，内容与触发条件沿用原逻辑。

`step_inject_tool_result_cache()` 固定的是缓存分区的相对顺序，不锁死静态 Prompt 的具体内容。修改或新增普通静态 system 无需调整该函数；新增 Real、Play、记忆、动态事件等非静态 system 时必须设置对应 marker，否则会被归入静态区并移动到工具摘要之前。修改静态内容会让下一次请求重建一次缓存，后续请求按新前缀继续命中。

## 4. 对话入口与异步 worker

### 4.1 SumiTalk

- 原生聊天 job 路由：`routes/miniapp/sumitalk_chat_jobs.py`
- 持久队列：`services/sumitalk_chat_queue.py`
- 独立 worker：`scripts/run_sumitalk_chat_worker.py`
- realtime 事件：`services/realtime_app.py`、`services/realtime_publish.py`、`services/sumitalk_live_event_broker.py`
- 历史接口：`routes/miniapp/sumitalk_history.py`

当前边界：消息由前端创建 job，独立 worker 消费；后端不自行重试失败 job，是否重试由前端明确动作决定。

- 原生普通聊天使用 rich SSE；旧 MiniApp、其他平台和共同游戏豁免继续走现有非流路径，共用同一提示词、工具、记忆与通道注入。
- Worker 事件先经 `realtime_publish -> realtime_app -> SumiTalkRunEventBroker` 到活跃 SSE；独立 FIFO 落库队列随后写 `sumitalk_chat_run_events`。SQLite 只用于首次连接、断线重连、sequence 缺口和 realtime 不可用时的 40ms 兜底。
- SumiTalk 的 `assistant_final` 不等待 R2、摘要或动态记忆；这些工作进入单一 FIFO 后台归档队列，保证多轮顺序。其他入口的归档时序不变。
- 事件契约和定向验证入口见 `docs/SumiTalk原生安卓后端流式接入.md` 与 `scripts/test_sumitalk_native_stream_backend.py`。

### 4.2 Telegram

- Webhook：`routes/telegram_webhook.py`
- 更新持久队列：`services/telegram_update_queue.py`
- Webhook worker：`scripts/run_telegram_webhook_worker.py`
- 主动唤醒：`services/telegram_proactive.py`
- 主动唤醒进程：`scripts/run_telegram_proactive.py`
- 唤醒记录生命周期：`services/wakeup_event_log.py`
- 唤醒记录查询：`GET /miniapp-api/wakeup-events?limit=30`（`routes/miniapp/wakeup_events.py`）
- 春梦状态与归档：`services/spring_dream.py`
- Telegram 发送与展示：`services/telegram_bot.py`

当前边界：webhook 快速入队，聚合、聊天调用和回复由独立 worker 完成；主动唤醒不依赖 Gunicorn worker 常驻。

唤醒记录只保存实际安排的随机唤醒、延迟续话、日历/闹钟，以及真正命中的硬触发，不把后台轮询 tick 当成唤醒。记录覆盖计划、执行、动作完成或消息实际投递成功、失败和取消；用户在预定时间前发来新消息时，原随机唤醒或续话会记为已取消并保留原因。查询默认返回下一次已确定的计划和最近 30 条结束记录，不暴露投递目标或内部 metadata。

春梦后唤醒只消费当前睡眠 session 中六小时内的 pending 状态，其他旧 session 会失效清理；网关空回复时使用同一梦境重试一次，成功后仍只记录一次发送。

### 4.3 QQ 与微信

- QQ OneBot 入口：`connectors/qq_onebot/src/main.js`
- QQ 群近期上下文：`services/qq_activity_context.py`
- QQ 入口 watchdog：`scripts/run_qq_entry_watchdog.py`
- 微信 iLink 直连说明：`docs/wechat_ilink_direct.md`

QQ 群上下文按发言人区分，不把群友内容当成小玥说的；入口消息仍进入统一聊天主链路。群聊上下文最多携带最近 5 张图片：OneBot 入口把 QQ 临时图片 URL 转成 base64，网关继续复用统一图片压缩，但不为这类上下文图生成图片描述；单张图片获取或压缩失败时只把该图回退为 `【图片】`，不影响其他图片和本轮唤醒。

### 4.4 回复通道连续性

- 最近真实聊天通道：`services/reply_channel_context.py`
- 最近窗口：`storage/recent_window_store.py`

小家、纸条、道具等内部事件不擅自把回复通道改成 SumiTalk；回复沿用最近真实聊天入口，只有原本就在 SumiTalk 对话时才回 SumiTalk。
闹钟和日历提醒在到点触发时重新读取最近真实聊天入口，并固定复用该入口的窗口、目标和投递渠道；仅当该渠道不可用时才按旧顺序兜底。

## 5. 记忆与上下文

| 能力 | 代码入口 | 当前实现 |
| --- | --- | --- |
| 对话归档 | `storage/r2_conversation_store.py`、`storage/conversation_sqlite_store.py` | R2 持久化 + SQLite 运行索引 |
| 窗口上下文 | `storage/r2_context_store.py` | 最近对话、摘要等上下文数据 |
| 最近窗口 | `storage/recent_window_store.py` | 本地 `data/recent_windows.json`，最多保留 200 条 |
| 动态层判断 | `services/dynamic_layer_ds.py` | 产生 new / merge / out 等动态记忆决策 |
| 动态记忆检索 | `services/dynamic_memory_search.py`、`services/dynamic_memory_reranker.py` | 关键词、向量与 rerank 组合召回 |
| 动态记忆镜像 | `storage/dynamic_memory_mirror_store.py` | 为管理、维护和诊断提供 SQLite 镜像 |
| 中期记忆 | `services/du_midterm_memory.py`、`routes/miniapp/midterm_memory.py` | 生成、读取和管理阶段记忆 |
| 画像记忆 | `services/portrait_memory.py` | 画像候选与更新边界 |
| 每轮总结 | `services/deepseek_summary.py` | 统一摘要更新，不再包含 Notion 小本本分支 |
| 记忆引用 | `services/dynamic_memory_citation.py` | 解析并回写实际引用标记 |
| 记忆管理 | `routes/miniapp/memory_panel.py`、`routes/memory_api.py` | 查询、重写、删除、维护和诊断 |

亲密/卧室记忆仍使用动态记忆分类与独立生命周期；不额外侧写 Notion，也不进入不适合的核心缓存/画像路径。

## 6. 当前存储边界

- R2 客户端：`storage/r2_client.py`
- R2 聚合兼容入口：`storage/r2_store.py`
- R2 领域存储：`storage/r2_store.py` 及同目录各 `r2_` 前缀领域模块
- 运行 SQLite：`storage/runtime_sqlite.py`
- 工具摘要表：`tool_result_cache`（同一运行 SQLite；非 R2）
- 对话 SQLite：`storage/conversation_sqlite_store.py`
- 文游 SQLite：`storage/wenyou_sqlite_store.py`
- 日程 SQLite：`storage/schedule_sqlite_store.py`

共享 R2 不是测试环境。未经当轮明确允许，不运行会写入、修改或删除生产 R2 的测试、迁移或预览。

## 7. 原生 App / MiniApp 已接入模块

`routes/miniapp_api.py` 当前聚合以下已实现模块：

- 上游与模型：`routes/miniapp/upstreams.py`
- 提示词、模式与设置：`routes/miniapp/settings.py`
- 对话 job、历史与 reasoning：`routes/miniapp/sumitalk_chat_jobs.py`、`routes/miniapp/sumitalk_history.py`、`routes/miniapp/reasoning.py`
- 日常面板与小家状态：`routes/miniapp/dashboard.py`
- 设备状态与动作：`routes/miniapp/device_state.py`、`routes/miniapp/device_actions.py`
- 记忆、中期记忆与诊断：`routes/miniapp/memory_panel.py`、`routes/miniapp/midterm_memory.py`、`routes/miniapp/diagnostics.py`
- 交换日记：`routes/miniapp/exchange_diary.py` + `storage/exchange_diary_store.py`
- 记事本：`routes/miniapp/notes.py`，对应聊天工具 `note_write`
- 秘密抽屉：`routes/miniapp/secret_drawer.py` + `storage/secret_drawer_store.py`
- 渡的页笺：`routes/miniapp/du_pages.py` + `storage/du_pages_store.py`
- 共读：`routes/miniapp/co_read.py` + `storage/co_read_store.py`
- 日程：`routes/miniapp/schedule.py` + `storage/schedule_sqlite_store.py`
- 媒体、贴纸与日志：`routes/miniapp/media.py`、`routes/miniapp/stickers.py`、`routes/miniapp/logs.py`
- 音乐：`routes/miniapp/music_bgm.py`、`routes/miniapp/music_netease.py`
- 学习室：`routes/miniapp/studyroom.py`
- 游戏与文游：`routes/miniapp/game_tools.py`、`routes/miniapp/wenyou.py`
- 无限流游戏模式：`GET/PUT /miniapp-api/wenyou-mode`，状态由 `storage/wenyou_mode_store.py` 保存；默认关闭，模式开启时由统一聊天入口注入文游玩家工具
- 小爱音箱：`routes/miniapp/xiaoai.py`
- AI 农场：`routes/miniapp/aifarm.py`

## 8. 独立领域能力

### 8.1 共读

- 路由：`routes/co_read_api.py`、`routes/miniapp/co_read.py`
- 书籍与章节：`services/co_read_books.py`
- 共读流程：`services/co_read_flow.py`
- 共读卡片压缩：`services/co_read_card_qwen.py`
- 存储：`storage/co_read_store.py`

### 8.2 渡的页笺

- 工具与业务：`services/du_pages.py`
- App 管理：`routes/miniapp/du_pages.py`
- 公开预览：`routes/du_pages.py`
- 存储：`storage/du_pages_store.py`

HTML 使用当前页笺工具直接持久化；旧临时预览工具不再作为入口。

### 8.3 小爱音箱与设备能力

- 小爱 API：`routes/xiaoai_api.py`
- 状态与动作队列：`storage/xiaoai_store.py`
- 音频文件：`services/xiaoai_audio_store.py`
- App 设备上报：`routes/miniapp/device_state.py`
- App 设备动作：`routes/miniapp/device_actions.py`

设备感知快照写入 `sense_latest`，24 小时短尾历史写入 `sense_history`；历史按感知类型分别限量，前台应用与会话高频上报不会挤掉屏幕、健康、位置和电量记录。最近睡眠摘要按滚动 24 小时展示，并合并仍在时间窗内的主睡眠与午睡段。

### 8.4 游戏

- 游戏工具聚合：`routes/miniapp/game_tools.py`
- 统一工具运行时：`services/game_tool_runtime.py`
- 私密走格棋：`services/private_board_tool.py`
- 随机版塔防：`services/random_imitator_td_tool.py`
- 文游：`services/wenyou/*`、`storage/wenyou_sqlite_store.py`

文游玩家工具默认不进入聊天工具集。App 负责管理“无限流游戏模式”这个全局开关；开启后，统一聊天入口都会注入 `buy_item`、`roll_gacha`、`inventory_action`、`use_item`、`transfer`，关闭后所有入口都不注入。

游戏内部允许列表、道具适配表和安全访问 allowlist 属于各自领域约束，不等同于已经移除的聊天窗口白名单/黑名单。

## 9. 运维与定向验证

### 9.1 本地基础验证

```bash
.venv/bin/python -m py_compile app.py routes/chat.py pipeline/pipeline.py
.venv/bin/python -c "import app"
git diff --check
```

### 9.2 关键运行检查

```bash
curl -fsS http://127.0.0.1:5000/health
curl -fsS http://127.0.0.1:5000/v1/models
systemctl --no-pager --full status du-gateway.service
```

涉及独立入口时，同时检查其实际 worker，而不是只重启主网关。SumiTalk 变更至少核对 `du-sumitalk-chat-worker.service`；Telegram webhook 或主动唤醒变更分别核对对应 worker。

验证必须针对准备提交、推送或部署的版本。小改动只跑真实故障路径相关的定向检查，不默认跑全量测试。
