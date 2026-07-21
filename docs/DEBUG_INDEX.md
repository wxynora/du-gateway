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
| Reasoning 与业务隐藏块 | `services/reasoning_utils.py`、`services/hidden_blocks.py`、`services/pc_command_handler.py` | `reasoning_started / reasoning_delta / reasoning_finished / assistant_reasoning` 与 PCmd `DU_THOUGHT` 流继续独立运行；`DU_THOUGHT`、`DU_FOLLOWUP`、`DU_VITALS`、`PIXEL_HOME` 等业务隐藏标记仍由统一解析链剥离并执行。停用的 pseudo COT / `DU_INNER_OS` 代码与 R2 状态接口已移除，历史 R2 对象不在代码清理任务中批量删除 |
| 主模型输出参数 | `routes/chat.py`、`config.py` | 通用流式与非流式转发不再自动补写或抬高 `max_tokens`；客户端明确传入的输出参数原样保留，网关只记录上游 `finish_reason=length` 供诊断 |
| Pipeline 组装与归档 | `pipeline/pipeline.py` | 负责上下文、记忆、工具与回合后处理 |
| 请求清洗 | `pipeline/cleaner.py` | 统一清洗入口消息与上游消息结构 |
| 上游策略 | `services/upstream_policy.py` | active upstream / model 只由 App 明确保存更新 |
| 上游持久选择 | `storage/upstream_store.py` | 探活、拉模型和普通请求不能覆盖已保存选择 |
| 提示词管理 | `services/prompt_manager.py`、`storage/r2_store.py` | App 可编辑的静态 Prompt 分区统一从这里管理；详情最多返回当前分区最新 3 个备份，配置写成功后按 `created_at` 清理到最新 3 个，写失败不删旧备份，回滚复用同一保存与保留链路 |
| 入口风格 | `services/entry_style_prompt.py` | 按真实聊天入口注入对应风格 |
| 语音台词规范 | `services/voice_line_prompt.py` | 语音输出场景统一使用该规范 |
| 工具定义与执行 | `services/chat_tools.py` | 当前网关原生工具集中入口 |
| 网关工具辅助 | `services/chat_tool_helpers.py`、`services/gateway_tools.py` | 领域工具复用同一执行边界 |
| 工具使用摘要缓存 | `services/tool_result_cache.py`、`storage/runtime_sqlite.py`、`routes/miniapp/reasoning.py` | 工具循环结束后一次性写本地 SQLite；结果按工具清洗，不保存原始大 JSON；24 小时 TTL，按实际注入字符计数，超过 3000 字符时删除最早完整记录直至不高于 2000；思维链接口根据每轮已归档的 `static_breakdown` 返回当轮 `tool_cache.current_chars/max_chars`，不读取页面刷新时的全局现值 |
| 身体状态四轮评估 | `services/du_body_evaluator.py`、`storage/du_body_eval_store.py`、`services/pixel_home.py` | 真实归档轮次独立进入 SQLite pending，每 4 轮或最旧等待 30 分钟时由 DS 逐轮输出 delta；保留模型默认 thinking、不设置人为输出上限并启用 JSON Output，解析失败日志只记录结束原因和 token/字符统计；apply 使用稳定幂等键并记录 before/delta/after 审计，最终失败仍保留原轮次供人工恢复，进程重启按 lease 接手；不改变动态记忆、近期总结或压缩移位计数，动态记忆 DS 不再请求、解析或返回 BODY delta |
| Claude thinking 连续性 | `services/claude_thinking_carryover.py` | 普通对话回传 opaque signature，不回灌转写 thinking 文本 |
| Claude OAuth Proxy 输出额度 | `scripts/claude_oauth_proxy.js` | Anthropic 协议必填的默认 `max_tokens` 使用当前 Claude 主模型 128k 输出上限；旧式 extended thinking 继续强制保证总额度不少于 `thinking budget + 1`，该保护是辛玥明确设计，不得删除或弱化 |
| Prompt Cache 诊断 | `services/prompt_cache_debug.py` | 记录静态/动态构成与上游 usage 元数据；合并后的静态尾段仍按内容拆分 QQ、TG、微信、SumiTalk、小爱音箱入口风格，不会被近期记忆块标记吞掉 |

当前 Claude 缓存前缀顺序固定为：tools → 第 1 个断点 → 固定静态子块 → 第 2 个断点 → 工具摘要 → 第 3 个断点 → 入口风格 → SumiTalk Real/App 互斥提示 → play 小纸条 → 较稳定近期记忆 → 最近记忆 → 第 4 个断点 → 动态区 → 对话消息。固定静态、工具摘要、入口风格、Real/App、play、较稳定近期和最近记忆都属于静态提示前缀的子块；它们按唯一顺序表独立收集，再合并为对应缓存段，不为每个小注入额外生成 system。动态区仍单独保留，不会被拼进静态区。工具循环内部只收集结果，整条工具链收口后才批量更新摘要块。play 小纸条仍由 `services/pixel_home.py` 生成，内容与触发条件沿用原逻辑。

小家事件及 App 内涩涩走格棋、囚禁模拟器的 `sync-du` 请求通过 `X-DU-SUMITALK-PROMPT-ASSEMBLY` 复用 SumiTalk 的提示词组装表面，但不改实际回复、投递和归档渠道；小家/游戏状态作为动态 system，各入口保留自己的 user 内容。实现入口为 `services/conversation_followup.py::_send_wakeup_event` 与 `routes/chat.py::chat_completions`，`return_only`、游戏工具和续跑规则不受影响。以后新注册的 App 游戏，只要存在发给渡的模型消息，也必须复用该 SumiTalk 组装表面：不得自行拼静态 system，不得把游戏状态塞进静态缓存前缀，只允许替换本游戏的动态 system 与 user 内容；纯查看或本地状态变更接口不触发模型请求。

`step_inject_tool_result_cache()` 使用 `pipeline/pipeline.py` 的唯一 `_SYSTEM_PROMPT_REGION_ORDER` 和 `_SYSTEM_PROMPT_CACHE_GROUPS`：固定静态段、工具摘要段、工具摘要后的静态尾段、动态段。每个逻辑子块在组装期间保持独立，最终每个缓存段只输出一条 system；四个缓存断点仍由 tools、固定静态段、工具摘要段和静态尾段的末尾承载。入口风格、Real/App、play、近期记忆只改变静态尾段内容，不会携带其他子块；动态区永远单独保留。修改固定静态内容会让下一次请求重建一次缓存，后续请求按新前缀继续命中。

## 4. 对话入口与异步 worker

### 4.1 SumiTalk

- 原生聊天 job 路由：`routes/miniapp/sumitalk_chat_jobs.py`
- 持久队列：`services/sumitalk_chat_queue.py`
- 独立 worker：`scripts/run_sumitalk_chat_worker.py`
- realtime 事件：`services/realtime_app.py`、`services/realtime_publish.py`、`services/sumitalk_live_event_broker.py`
- 流式语音 sidecar：`services/sumitalk_voice_sidecar.py`
- 历史接口：`routes/miniapp/sumitalk_history.py`

当前边界：消息由前端创建 job，独立 worker 消费；后端不自行重试失败 job，是否重试由前端明确动作决定。

- 原生普通聊天使用 rich SSE；旧 MiniApp、其他平台和共同游戏豁免继续走现有非流路径，共用同一提示词、工具、记忆与通道注入。启用 reasoning 的流式请求会在流开始时预留稳定 `reasoning-*` part；正文 token 到达时立即结束当前 reasoning 阶段并继续即时发送正文，后到 reasoning 仍用同一个 part 更新，不新建正文后的 reasoning part。
- Worker 事件先经 `realtime_publish -> realtime_app -> SumiTalkRunEventBroker` 到活跃 SSE；独立 FIFO 落库队列随后写 `sumitalk_chat_run_events`。SQLite 只用于首次连接、断线重连、sequence 缺口和 realtime 不可用时的 40ms 兜底。
- SumiTalk 的 `assistant_final` 不等待 R2、摘要或动态记忆；这些工作进入单一 FIFO 后台归档队列，保证多轮顺序。其他入口的归档时序不变。
- SumiTalk 拉黑模式状态与选中文案由 `storage/sumitalk_block_mode_store.py` 管理；`PUT /miniapp-api/sumitalk-block-mode` 将 `prompt_version_id/prompt_version_name/prompt_text` 与开关状态一次落盘且不裁切文案，旧状态缺字段时迁移到原 `BLOCK_NOTICE_TEXT` 默认版本。首次开启通知、成功投递的 SumiTalk 主动唤醒、定时续话及每段最多三次自动回复都在发送时读取同一份当前选中文案；独立归档路径仍只在归档成功后追加，消息继续使用 `role=user`、`skip_memory_summary` 与 `skip_dynamic_memory`。
- 仅流式 SumiTalk 聊天会在 queue 入口跨 delta 识别并剥离 `<voice>...</voice>`；独立 sidecar 用 `job_id + source_part_id + voice_index` 在同一队列 SQLite 持久幂等，直接复用 MiniMax TTS、上传现有聊天媒体，并允许 `assistant_audio_ready` / `assistant_audio_failed` 晚于 `assistant_final`。`/voice-call/*`、通话分段 TTS、取消和播放状态不共用这套任务。
- 一起看聊天仍走同一 SumiTalk job。请求顶层附带 `watch_session_id` 和完整 `watch_snapshot` 后，`services/watch_context.py` 按消息发送时 playhead 注入当前剧情、当会话已播缓存的相关片段和可配置的回复抵达窗口，并明确要求“小玥正在和你看同一段，不需要和她照搬复述你看到的剧情内容以及逐项描述剧情画面。”；当前相关片段召回只在本会话、本 timeline epoch、发送位置前已完整播放的 `watch_plot_chunks` 内按最近三条用户消息做会话内 BM25/IDF 排序，剧情/对白、标签、人物字段依次降权，人物名作为全片高频词自动降权，只命中人物名时最多取一段，有事件词命中时剔除仅靠同名进入的候选，最多注入四段且不进入网关长期记忆。当前只持久化剧情片段，不单独保存每轮召回 query、候选分数或最终命中项。`knowledge_mode` 只在网关内部决定是否附加截止快照的剧情背景，不作为标签传给主模型。回复抵达位置前的少量剧情可用于当轮正常回复；动作区只提供预计回复抵达后仍未结束、且位于快照后两分钟内的可靠片段，弹幕示例从这些片段选择并明确目标是实际显示时间，不再固定使用发送位置加 30 秒。`services/watch_action_flow.py` 在流式与非流式链路剥离短标记并发出 `watch_danmaku_action`；旧长 JSON 块只保留解析兼容，无效时间标记和既有时间窗口拒绝会记录 reason，但不增加新的动作拒绝条件。事件不使用主动消息 channel，seek 后旧 epoch 动作失效。
- 事件契约和定向验证入口见 `docs/SumiTalk原生安卓后端流式接入.md`、`scripts/test_sumitalk_native_stream_backend.py` 与 `scripts/test_sumitalk_stream_voice_sidecar.py`。

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

半小时硬触发严格从全局 `last_user_activity_at` 重新计时：真实聊天、小家操作和游戏互动都算用户互动，任一新互动都会重置计时；聊天归档只用于识别本次互动是否明确表达要离开。入睡意图按分句识别，过去或背景叙述中的“我睡觉”不会被当成当前要去睡觉。

春梦本体提示词由 Prompt 管理区 `spring_dream_wakeup` 提供，模板中的 `{{fragments}}` 会替换为本轮抽到的梦境碎片；自定义模板漏写占位符时，后端会把碎片补在模板末尾。春梦后唤醒只消费当前睡眠 session 中六小时内的 pending 状态，其他旧 session 会失效清理；网关空回复时使用同一梦境重试一次，成功后仍只记录一次发送。只要主模型生成了非空春梦正文，专用梦境归档都会保存，并用 `sent`、`unconfirmed` 或 `not_dispatched` 标记投递状态；普通对话归档仍只记录确认投递成功的消息。梦境归档由 `GET /miniapp-api/spring-dream-archives`、`GET /miniapp-api/spring-dream-archives/<id>` 查询，`DELETE /miniapp-api/spring-dream-archives/<id>` 单条删除；删除会同步清理 SQLite、R2 正文对象、当天索引与最近索引，不存在返回 404，任一删除步骤失败返回 500。

### 4.3 QQ 与微信

- QQ OneBot 入口：`connectors/qq_onebot/src/main.js`
- QQ 群近期上下文：`services/qq_activity_context.py`
- QQ 入口 watchdog：`scripts/run_qq_entry_watchdog.py`
- 微信 iLink 直连说明：`docs/wechat_ilink_direct.md`

QQ 群上下文按发言人区分，不把群友内容当成小玥说的；入口消息仍进入统一聊天主链路。群聊上下文只允许后端随机主动决策、半小时硬触发、日历事件和系统闹钟使用；小家/身体/道具、延迟续话、屏幕检查、日记、游戏等其他后端事件与普通聊天均不注入。群聊上下文最多携带最近 5 张图片：OneBot 入口把 QQ 临时图片 URL 转成 base64，网关继续复用统一图片压缩，但不为这类上下文图生成图片描述；单张图片获取或压缩失败时只把该图回退为 `【图片】`，不影响其他图片和本轮唤醒。

### 4.4 回复通道连续性

- 最近真实聊天通道：`services/reply_channel_context.py`
- 最近窗口：`storage/recent_window_store.py`

小家、纸条、道具等内部事件不擅自把回复通道改成 SumiTalk；回复沿用最近真实聊天入口，只有原本就在 SumiTalk 对话时才回 SumiTalk。
闹钟和日历提醒在到点触发时重新读取最近真实聊天入口，并固定复用该入口的窗口、目标和投递渠道；仅当该渠道不可用时才按旧顺序兜底。
调度条目的创建、启停和删除通过 `storage/schedule_store.py` 的跨进程写锁串行；到点 tick 只按条目 ID 补丁回写本轮实际变化的状态字段，不再整表覆盖，避免慢唤醒把并发新增或编辑的系统闹钟抹掉。

## 5. 记忆与上下文

| 能力 | 代码入口 | 当前实现 |
| --- | --- | --- |
| 对话归档 | `storage/r2_conversation_store.py`、`storage/conversation_sqlite_store.py` | R2 持久化 + SQLite 运行索引 |
| 窗口上下文 | `storage/r2_context_store.py` | 最近对话、摘要等上下文数据 |
| 最近窗口 | `storage/recent_window_store.py` | 本地 `data/recent_windows.json`，最多保留 200 条 |
| 动态层判断 | `services/dynamic_layer_ds.py` | 产生 new / merge / out 等动态记忆决策；merge 同时输出 `consolidate/correction/invalidate/supersede/temporal_update` 五类规范原因，缺失或非法原因进入现有重写机制，动态层血缘与核心层待审候选保留该字段；当前不按原因自动删除或淘汰记忆；保留模型默认 thinking，不设置人为 `max_tokens` 上限 |
| 动态记忆检索 | `services/dynamic_memory_search.py`、`services/dynamic_memory_reranker.py` | 关键词、向量与 rerank 组合召回 |
| 动态记忆镜像 | `storage/dynamic_memory_mirror_store.py` | 为管理、维护和诊断提供 SQLite 镜像 |
| 中期记忆 | `services/du_midterm_memory.py`、`routes/miniapp/midterm_memory.py` | 生成、读取和管理阶段记忆 |
| 长期记忆素材审阅包 | `data/longterm_memory_material_review.json` | 本地 mode-600 素材预览，不是正式长期摘要且未写入 R2；当前 597 条候选素材已完成明确重复项合并，19 组合并保留全部来源引用；最终正式长期摘要目标约 4000 字符，不以该长度裁切原始素材 |
| 画像记忆 | `services/portrait_memory.py` | 画像候选与更新边界 |
| 每轮总结 | `services/deepseek_summary.py` | 统一摘要更新，不再包含 Notion 小本本分支；近期记忆四轮总结显式关闭 thinking，动态层不受影响 |
| 记忆引用 | `services/dynamic_memory_citation.py` | 解析并回写实际引用标记 |
| 记忆管理 | `routes/miniapp/memory_panel.py`、`routes/memory_api.py`、`storage/r2_store.py`、`pipeline/pipeline.py`、`services/memory_maintenance.py` | 查询、重写、删除、维护和诊断；`POST /miniapp-api/dynamic-memory/<id>/retain` 原子增加一次 `mention_count` 并刷新 `last_mentioned`，未命中返回 404、写入失败返回 500；动态层边缘淘汰前 15 天不衰减，第 16 天起每天衰减 0.1、最多衰减 2，仅在至少 15 天未提及且综合权重不高于 2 时删除，图书馆 tag 与 core_cache 来源记忆永久豁免 |

亲密/卧室记忆仍使用动态记忆分类与独立生命周期；不额外侧写 Notion，也不进入不适合的核心缓存/画像路径。

## 6. 当前存储边界

- R2 客户端：`storage/r2_client.py`
- R2 聚合兼容入口：`storage/r2_store.py`
- R2 领域存储：`storage/r2_store.py` 及同目录各 `r2_` 前缀领域模块
- 运行 SQLite：`storage/runtime_sqlite.py`
- 工具摘要表：`tool_result_cache`；身体状态评估表：`du_body_eval_pending`、`du_body_eval_audit`；一起看运行表：`watch_sessions`、`watch_timeline_sections`、`watch_plot_chunks`、`watch_risk_events`、`watch_risk_feedback`、`watch_analysis_samples`、`watch_analysis_jobs`、`watch_client_sample_plans`、`watch_timeline_fingerprints`、`watch_story_checkpoints`、`watch_knowledge_cards`、`watch_subtitle_assets`、`watch_visual_frames`（均在同一运行 SQLite；非 R2）
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
- 交换日记：`routes/miniapp/exchange_diary.py` + `storage/exchange_diary_store.py`；渡通过 `services/chat_tools.py` 创建评论时继续发送 `notification_kind=diary_comment` 的系统通知，payload 带 `entry_id/comment_id/reply_to_comment_id/sender`，回复目标作者为 `xy` 时标题为“渡回复了你的评论”，其他情况保持“渡评论了你的日记”。
- 记事本：`routes/miniapp/notes.py`，对应聊天工具 `note_write`
- 秘密抽屉：`routes/miniapp/secret_drawer.py` + `storage/secret_drawer_store.py`
- 渡的页笺：`routes/miniapp/du_pages.py` + `storage/du_pages_store.py`
- 共读：`routes/miniapp/co_read.py` + `storage/co_read_store.py`
- 日程：`routes/miniapp/schedule.py` + `storage/schedule_sqlite_store.py`
- 媒体、贴纸与日志：`routes/miniapp/media.py`、`routes/miniapp/stickers.py`、`routes/miniapp/logs.py`
- 音乐：`routes/miniapp/music_bgm.py`、`routes/miniapp/music_netease.py`
- 一起看：`routes/miniapp/watch.py`、`storage/watch_runtime_store.py`、`storage/watch_viewing_store.py`、`storage/watch_analysis_store.py`、`storage/watch_knowledge_store.py`、`storage/watch_subtitle_store.py`、`storage/watch_visual_store.py`、`storage/stay_with_du_store.py`、`services/watch_analysis.py`、`services/watch_analysis_source.py`、`services/watch_analysis_samples.py`、`services/watch_knowledge.py`、`services/watch_subtitles.py`、`services/watch_visual_context.py`；已实现会话准备/显式确认开播、Bilibili 分 P 列表与相邻项解析、本地媒体 revision/能力/音轨字幕契约、知识卡与字幕准备及 24 小时缓存、播放快照、独立客户端租约、模式、时间轴、网关/客户端两类取材计划、正式窗口样本上传、所有模式通用的首段剧情门禁、分析任务查询、队列诊断、剧情检查点、派生帧、高能反馈、可信播放累计、跨分 P viewing、稳定票根、票根最终标题保存、可选归档到一起看过、原子结束和状态查询，接口统一位于 `/miniapp-api/watch/*`
- 学习室：`routes/miniapp/studyroom.py`
- 游戏与文游：`routes/miniapp/game_tools.py`、`routes/miniapp/wenyou.py`
- 无限流游戏模式：`GET/PUT /miniapp-api/wenyou-mode`，状态由 `storage/wenyou_mode_store.py` 保存；默认关闭，模式开启时由统一聊天入口注入文游玩家工具
- 小爱音箱：`routes/miniapp/xiaoai.py`
- AI 农场：`routes/miniapp/aifarm.py`

一起看 Phase 2 分析 worker 入口为 `scripts/run_watch_analysis_worker.py`，安装脚本为 `scripts/install_watch_analysis_worker_service.sh`。新 session 先进入准备态；worker 可先执行 identify 和 timeline prepass，identify 会落库作品原语言正式片名与年份；人工填写正片起点时，identify 直接在该位置附近取样，避开 Bilibili 前置垫片。`partial/unknown` 会排队生成 `watch-knowledge-v13` 简短背景卡：Tavily basic 只执行一次 `《片名》剧情简介 主要人物 人物关系 世界观` 搜索，存在季集或分 P 时跟在书名号后，最多保留 3 个不同站点摘要；不限定站点、不调用角色目录。DS V4 Flash 不获得搜索工具，只负责整理作品身份、世界观、开场前情、主要人物与关系、专有名词和 3–5 条只说明主线方向的 `story_outline`；网关不规定人物数量，也不根据作品特定词硬补人物。卡片最多引用 3 条来源，不含结局、反转或逐场剧情；作品名、年份、人物姓名证据和置信度仍有门禁，单一可靠来源允许生成但会降低置信度。知识卡和字幕准备均进入可见终态后，只有 `POST .../start` 提交当前 `subtitle_lookup_id` 并确认卡片或明确跳过，才创建 rolling 任务。滚动取材计划会直接跨过已确认的 recap/intro/outro/preview/non_story，不再先送模型后仅丢弃结果。

Bilibili 开播前可通过 `GET /miniapp-api/watch/bilibili/parts` 获取真实分 P 列表及 `current/previous/next`，每个 P 使用独立 media id、时长和会话。`services/watch_analysis_source.py` 通过公开 `view/playurl/player` 接口取得分 P、低清 AVC 主备视频流和音频流。字幕任务先检查 Bilibili 原生字幕；没有原生轨时，`services/watch_subtitles.py` 在配置 `WATCH_SUBDL_API_KEY` 后只使用标准 `original_title + year` 查询一次任意语言 SRT/VTT，按人工 `content_start_ms` 整体平移并写入 `watch_subtitle_assets`，TTL 24 小时。本地文件会话则在创建时提交 `local_asset_id + media_revision`、能力检测和所选音轨/字幕轨，并在开播前通过 `POST .../local-subtitles` 提交匹配 revision 的内嵌或外挂 SRT/VTT；有符号 `offset_ms` 来自所选字幕配置。状态接口只返回语言、版本、格式、条目数、覆盖区间和清洗结果，不返回字幕正文、下载地址或 key；`/start` 拒绝旧 `subtitle_lookup_id`。rolling 只读已确认字幕资产，不再访问字幕 provider。

`watch-v9` 从请求源头按 `knowledge_mode` 分流剧情背景：`known` 保持 `story_background` 为空，`needs_summary` 才产出截止 `through_ms`、仅供理解当前批次的防剧透背景。滚动请求不生成或回传累计剧情与累计事件状态，只读取上一批时间窗内已经落库的紧邻 `plot_chunks` 来衔接人物和场景；滚动分析和知识卡请求都不设置 `max_tokens` 或其他显式输出上限。开播门锁仍要求五分钟可靠覆盖；解锁后 worker 按约 140 秒完整批次继续预取到最多领先 30 分钟或正常正片终点，达到高水位后至少消耗一个完整批次才补充，避免播放头每前进几秒就生成一次完整 provider 请求。风险区间使用最早可能开始到确认安全结束的保守边界，状态接口按真实 playhead 返回 `fear_protection`，剩余覆盖不足两分钟即为 `coverage_low`。Bilibili rolling 由 `ffmpeg` 提取最多约 140 秒的 16 kHz 单声道 32 kbps MP3 和最多 8 张图；公开解析失败时，可选 `WATCH_ANALYSIS_BILIBILI_COOKIE` 仅作网关专用登录态兜底。字幕准备独立使用默认 15 秒单请求、45 秒总预算和一次自动尝试，候选下载 URL 保序去重但不限制唯一候选数量，失败后由准备页显式重试，worker 记录 provider 阶段耗时。`POST .../analysis/samples` 对 Bilibili 是备用入口，对 `local_file` 是受 `watch_client_sample_plans` 约束的正式入口：计划绑定 media、revision、epoch、用途、允许范围和过期时间，每批最多一段 MP3/AAC/MP4 短音频及 8 张 JPEG/PNG/WebP，网关校验实际范围和当前音轨，AAC/MP4 在内存中规范化后复用同一 Gemini 链。模型默认经 OpenRouter 调用 `google/gemini-2.5-flash`，使用 `input_audio + image_url`、严格 JSON schema 且 `reasoning.effort=none`；响应适配器接受 `message.parsed`、JSON/content blocks、代码围栏、前后说明和确定性的轻微 JSON 语法偏差，但不完整结果或缺少分析顶层字段的自然语言不能推进剧情与胆小模式覆盖。响应包或剧情结果解析失败时，worker journal 记录完整上游响应及任务定位字段，不记录请求中的音频、截图或 key。

`watch_sessions.client_seen_at/client_lease_expires_at` 是独立存活租约，不能用会被 worker 更新的 `updated_at` 代替；播放快照、状态轮询、显式 `POST .../heartbeat` 和客户端素材提交会续租。创建会话以同一设备、窗口和完整媒体/模式参数生成 `creation_key`，同一有效租约内的重放返回原 session 与 `create_reused=true`，SQLite 唯一索引在老库加列迁移后创建，避免超时重试启动两套分析。source、knowledge、subtitle 三个调度入口只处理未结束且租约有效的会话。seek 切换 epoch 仍取消旧任务、开放计划与动作，但同一 session/media 已完成的 rolling 区间会按媒体时间复制剧情、风险和检查点到新 epoch，调度从已付费覆盖末端继续；人工 timeline correction 只是取材参考，只取消未完成任务和原始样本，不清除、推进或判废已完成结果。活跃会话不按累计分析任务数量或每日费用设置终止上限。每个 session 记录服务端观察时间和本 P `played_duration_ms`，只累计相邻同 epoch、上一状态为播放中的确认区间，并按上一倍速用媒体前进量校准，因此准备、暂停与 seek 不计时；达到正片完成边界后仍继续播放的可信区间也持续累计到明确结束。首个分 P 由后端生成 `viewing_id`，后续 P 显式复用；长期 `watch_viewings` 聚合跨 P 时长和完成部分。只有解锁后连续到达人工正片终点或媒体终点才落完成事件并影响 `completed`，普通 DELETE 不等于看完也不出票；使用者明确结束时调用 `DELETE ...?finalize_viewing=true`，无论作品是否完成都按当前可信累计生成稳定票根，切 P、`pagehide` 和异常清理继续使用普通 DELETE。未完成票根可保存到票夹，但不能归档为“一起看过”。`GET .../viewings/<viewing_id>` 与 `GET .../tickets` 支持受信任设备恢复。`DELETE .../sessions/<id>` 在事务中结束 session、取消 queued 任务、给 running 任务写 `cancel_requested` 并关闭开放计划，随后清除样本和派生帧；原 `analysis_cost` 保留，并新增 `viewing_summary/ticket`。`analysis_cost` 汇总 identify、timeline prepass、rolling、knowledge card 搜索/整理和外部字幕调用，本地缓存/指纹复用不计 provider 调用。真实 provider 响应在结束、租约、epoch 的调用后检查之前按 attempt/stage 事件幂等写入，迟到结果仍拒绝提交但 usage 不会消失；`complete` 只表示没有 queued/running 任务，`pricing_complete` 单独表示所有调用均返回美元价格，`unpriced_calls` 与 purpose breakdown 显示未报价调用，客户端不能把不完整或未报价的零显示成免费。worker 在取材、搜索、字幕 provider、Gemini 调用前后和结果提交前复检；worker 启动时和每分钟结束空租约/过期租约遗留会话，日志使用 `skip_reason=session_ended/client_lease_expired/cancel_requested`。原始 MP3/截图在成功落库、旧时间轴取消或最终失败后立即删除；低清派生 WebP 只保留播放点前 10 分钟到后 5 分钟且每会话最多 48 帧，seek/结束立即清空。部署除 Python requirements 外要求系统 `ffmpeg`，健康接口会报告取材、知识卡、字幕 provider 和视觉缓存状态；worker 不是 Flask 内线程。定向验证：`.venv/bin/python scripts/test_watch_together_backend.py`、`.venv/bin/python scripts/test_watch_analysis_phase2.py`、`.venv/bin/python scripts/test_watch_local_lifecycle.py`、`.venv/bin/python scripts/test_watch_viewing_ticket.py`；测试使用假的媒体、字幕、搜索和模型上游，不写 R2。

所有模式确认后播放器都保持锁定；首批 rolling 结果在同一 SQLite 提交事务中达到 `playhead + WATCH_ANALYSIS_INITIAL_READY_BUFFER_MS` 时自动写入 `playback_unlocked_at`，默认首段门禁为五分钟并在正片终点或媒体终点截断，不需要客户端再次调用 `/start`，后续 rolling 可以继续运行而不重新锁住播放器。只有胆小模式允许用户明确选择无保护继续；普通模式没有绕过。开播后的胆小模式保护状态仍按 `WATCH_ANALYSIS_FEAR_READY_BUFFER_MS` 判断，不与首段剧情门禁混用。

开源 `wxynora/Lean_In`（Lean In）参考实现同步提供了不含私有称呼的中文陪伴者动态 system 模板与 `build_companion_context_prompt()`：接入方使用 `{assistant}`、`{viewer}`、`{work}`，剧情和画面只供理解，明确禁止向 `{viewer}` 照搬复述剧情或逐项描述画面；当前剧情、会话内相关剧情和回复抵达片段用于真实回复，更远片段限制为 `[watch:danmaku ...]` 定时动作，并按预计抵达位置解释弹幕实际显示时间；可选拼图作为紧邻真实 viewer 消息前的独立 user 图片块。`SubtitleLookupPolicy` 提供默认 15 秒单请求、45 秒总预算和一次自动尝试，候选 URL 去重不附带数量上限。参考 core 已同步建会幂等、跨 epoch 媒体时间缓存复用、provider 事件先行落账和人工范围仅作取材参考；参考 Web 会读取 `DELETE` 返回的完整 `analysis_cost`，按 session ID 跨分 P 去重累计，分开显示任务是否结束与价格是否完整，正常返回/结束时展示，`pagehide` 只静默尽力结束。消息块继续区分左右来源，正文统一 12px 且内部左对齐；状态轮询直接按通用首段剧情门禁的 `start_gate.can_play` 解锁，不再等待 `ready_to_unlock` 或二次调用 `/start`，并显示相对当前播放点已经提前解析的真实剧情时长。

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

设备感知快照写入 `sense_latest`，24 小时短尾历史写入 `sense_history`；历史按感知类型分别限量，前台应用与会话高频上报不会挤掉屏幕、健康、位置和电量记录。最近睡眠摘要按滚动 24 小时展示，并合并仍在时间窗内的主睡眠与午睡段；同日摘要同时显示今天/昨天与具体月日，跨日摘要分别显示起止日期，避免只看时刻误判睡眠归属日。睡眠结算中，上午开始且持续至少 4 小时的熄屏优先归入主睡眠；系统电话界面 `com.android.incallui` 不作为明确前台活动截断睡眠，且未出现可信醒来证据时，重复熄屏事件沿用最早的 `screenOffSince`，不会把连续睡眠切短。

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
