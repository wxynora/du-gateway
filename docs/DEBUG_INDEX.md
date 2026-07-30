# Du Gateway 当前实现索引

本文件只登记已经完成、当前仍有效的实现。它是代码导航和运行边界索引，不是施工日志、待办清单或历史归档。

维护规则：

- 未落地内容写入对应的方案文档，不写进本索引。
- 功能、路由、文件或兜底失效时，先删除旧索引，再登记替代实现。
- 每次功能改动收尾都要核对本文件；不能只追加新条目而保留冲突旧说法。
- 索引结论必须能由当前代码入口、运行配置或定向验证证明。
- 任何现有机制的改动都必须先有与因果链直接相关的已知事实依据，例如日志、真实请求或生产数据、完整代码调用链、Git 历史、官方文档、既有明确需求或可复现实验；猜测、类比、惯例和“感觉更合理”不构成依据。证据不足时只能调查、标注假设或向辛玥确认，禁止先改机制再用结果倒推理由。
- 改动汇报必须以限定范围 diff 和验证结果为依据，完整披露新增、删除、替换的代码与行为，以及旧机制变化、影响路径、分支、兜底、缓存策略、断点、排序、默认值、过滤、截断、限制、生命周期、持久化、外部写入、重启、部署边界和已知取舍；禁止只汇报目标功能而隐去伴随策略，未经核对不得声称“只改了”“没有动”或“行为不变”。

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

`app.py` 当前注册：聊天、管理、Telegram webhook、MiniApp API、MCP、PC 指令、共读、渡的页笺、记忆、MiniApp 静态资源、感知、时间、Claude OAuth 同步、音乐分析、内部 STT、小爱音箱、AI 农场代理和瓶中生态代理。

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
| Reasoning 与业务隐藏块 | `services/reasoning_utils.py`、`services/hidden_blocks.py`、`services/pc_command_handler.py` | `reasoning_started / reasoning_delta / reasoning_finished / assistant_reasoning` 与 PCmd `DU_THOUGHT` 流继续独立运行；`DU_THOUGHT`、`DU_FOLLOWUP`、`DU_VITALS`、`PIXEL_HOME` 等业务隐藏标记仍由统一解析链剥离并执行。待续念头只支持 `add / done / dismiss`；继续保留时不输出标记。停用的 pseudo COT / `DU_INNER_OS` 代码与 R2 状态接口已移除，历史 R2 对象不在代码清理任务中批量删除 |
| 主模型输出参数 | `routes/chat.py`、`config.py` | 通用流式与非流式转发不再自动补写或抬高 `max_tokens`；客户端明确传入的输出参数原样保留，网关只记录上游 `finish_reason=length` 供诊断 |
| Pipeline 组装与归档 | `pipeline/pipeline.py` | 负责上下文、记忆、工具与回合后处理 |
| 请求清洗 | `pipeline/cleaner.py` | 统一清洗入口消息与上游消息结构；普通 user/assistant 消息仍清理 RikkaHub 自带时间 artifact，`role=tool` 的文本结果发给模型和存档时都保留完整字段，不再只提取 `HH:mm` |
| 上游策略 | `services/upstream_policy.py` | active upstream / model 只由 App 明确保存更新 |
| 上游持久选择 | `storage/upstream_store.py` | 探活、拉模型和普通请求不能覆盖已保存选择 |
| 提示词管理 | `services/prompt_manager.py`、`storage/r2_store.py` | App 可编辑的静态 Prompt 分区统一从这里管理；目录首项“世界层级”是整个 system 序列的固定静态首槽位，分区标题只供管理页展示、不进入注入正文；Codex OAuth 专用 Prompt 仅在对应上游命中时作为独立 system 置于世界层级之后、核心 Prompt 之前；“SumiTalk Real 模式”“SumiTalk 普通模式”复用同一通用编辑/保存协议，默认正文分别为 `SUMITALK_REAL_MODE_PROMPT`、`SUMITALK_APP_PROMPT`，运行时只读取当前命中的互斥模式，不改变槽位 marker 或位置；原生 Prompt 管理页按网关 section 列表自动承接，无需原生适配；目录末尾固定提供 `custom_static_system_1..5` 五个允许为空的自定义 System 槽位，空槽不注入，非空槽按编号进入固定静态尾部；详情最多返回当前分区最新 3 个备份，配置写成功后按 `created_at` 清理到最新 3 个，写失败不删旧备份，回滚复用同一保存与保留链路 |
| 入口风格 | `services/entry_style_prompt.py` | 按真实聊天入口注入对应风格 |
| 语音台词规范 | `services/voice_line_prompt.py` | 语音输出场景统一使用该规范 |
| 语音转写后处理 | `services/stt.py` | Gemini/OpenRouter 与 Deepgram 在统一返回边界压缩同一个非词汇填充音的超长连续重复：至少 5 次时保留 3 次并以中文省略号分隔；短重复、混合发声和有意义的词语重复保持原文 |
| MiniApp 语音转写 | `routes/miniapp/media.py`、`POST /miniapp-api/chat-media/transcribe` | `text` 逐字使用 STT/Gemini 返回正文，不按 `duration_ms` 清洗停顿、笑声、哼唱等标记；`duration_ms` 只用于保存语音 attachment 时长 |
| 幽默梗库 | `services/humor_meme_bank.py` | 默认梗以 SQLite 种子维护；模型侧按语境关键词与随机结果合计注入 3 条“梗文本＋用法”，不注入来源、公共重复规则或尾部标题；2026-07 已补入“OMG，你吓到我了” |
| 工具定义与执行 | `services/chat_tools.py`、`services/device_action_tools.py`、`services/mcp_forum_tools.py` | 当前网关原生工具集中入口；默认聊天工具面保留日历、设备动作与 `search_memory`，暂不向模型暴露 `forum_read_feed`、`forum_open_thread`、论坛 `cli` 和 `get_guide`，底层论坛执行与显式 `forum` 工具模式仍保留。交换日记统一声明为 `exchange_diary(action=create/list/read/comment)`，Stay with Du 统一声明为 `stay_with_du(action=write/delete)`，渡的后台日程统一声明为 `du_schedule(action=list/create/enable/disable/delete)`；11 个旧工具名不再注入但继续由 dispatcher 兼容执行，评论唤醒与日程提示均只引用新入口。设备工具由同一工具面注入，再由 `execute_tool()` 转交设备动作执行器；`open_app` 与 `close_app` 均接入该总分发；QQ 日常名称解析为 Android 包名，默认私聊 deep link，显式 `page=首页` 时只打开首页 |
| 网关工具辅助 | `services/chat_tool_helpers.py`、`services/gateway_tools.py` | 领域工具复用同一执行边界 |
| 工具使用摘要缓存 | `services/tool_result_cache.py`、`storage/runtime_sqlite.py`、`routes/miniapp/reasoning.py` | 工具循环结束后一次性写本地 SQLite；结果按工具清洗，不保存原始大 JSON；24 小时 TTL，按实际注入字符计数，超过 3000 字符时删除最早完整记录直至不高于 2000；思维链接口根据每轮已归档的 `static_breakdown` 返回当轮 `tool_cache.current_chars/max_chars`，不读取页面刷新时的全局现值 |
| 身体状态四轮评估 | `services/du_body_evaluator.py`、`storage/du_body_eval_store.py`、`services/pixel_home.py` | 真实归档轮次独立进入 SQLite pending，每 4 轮或最旧等待 30 分钟时由 DS 逐轮输出 delta；保留模型默认 thinking、不设置人为输出上限并启用 JSON Output，解析失败日志只记录结束原因和 token/字符统计；apply 使用稳定幂等键并记录 before/delta/after 审计，最终失败仍保留原轮次供人工恢复，进程重启按 lease 接手；不改变动态记忆、近期总结或压缩移位计数，动态记忆 DS 不再请求、解析或返回 BODY delta。想做指数底层仍为 0–100；23:00–04:00 与 06:00–10:00 的有效等级加权为 `+1.5`，自制力同步 `-1.5`，显示、Prompt 与春梦概率保留 0.5 半档 |
| Claude thinking 连续性 | `services/claude_thinking_carryover.py` | 普通对话回传 opaque signature，不回灌转写 thinking 文本 |
| Claude OAuth Proxy 思考与输出额度 | `scripts/claude_oauth_proxy.js` | `claude-opus-4-6/4-7/4-8/5` 与 `claude-fable-5` 走 adaptive thinking，强制请求 `display=summarized`；强度优先读取请求的 `output_config.effort` / `reasoning_effort`，否则使用 `CLAUDE_ADAPTIVE_THINKING_EFFORT`（默认 `high`）。Anthropic 协议必填的默认 `max_tokens` 使用当前 Claude 主模型 128k 输出上限；旧式 extended thinking 继续强制保证总额度不少于 `thinking budget + 1`，该保护不得删除或弱化。OpenAI 兼容非流式响应按上游文本块显式 `mode` 归约：`delta` 与未标记的标准多文本块顺序追加，`final/snapshot` 覆盖此前累计正文，后续 delta 再从该终态继续追加；不使用相似度、长度、最后一块或正文裁切判断 |
| Claude OAuth Proxy 用量快照 | `scripts/claude_oauth_proxy.js` | Anthropic unified rate-limit 响应头按白名单清洗后保存为独立 mode-600 JSON；默认与 `CLAUDE_OAUTH_FILE` 同目录，文件名 `claude-rate-limit-snapshot.json`，也可用 `CLAUDE_RATE_LIMIT_SNAPSHOT_FILE` 指定。Proxy 启动或首次读取状态时恢复快照，后续成功响应继续原子覆盖；文件只含更新时间、状态、重置时间及 5h/周利用率等脱敏元数据，不含 token、请求正文或路由 |
| Claude OAuth Proxy 请求原样快照 | `scripts/claude_oauth_proxy.js` | `proxyToAnthropic()` 在每次实际 POST Anthropic 前，将与 `req.write()` 完全相同的最终 JSON payload 字节原样写成独立 mode-600 文件；system、messages、tools、正文与 `cache_control` 均不删减、不脱敏、不截断，HTTP Authorization/OAuth 请求头不写入。目录可由 `CLAUDE_REQUEST_SNAPSHOT_DIR` 指定，默认在 `CLAUDE_OAUTH_FILE` 同目录下的 `claude-request-snapshots/`；当前转发 VPS 实际路径为 `/home/duproxy/.cli-proxy-api/claude-request-snapshots/`。固定保留最近 10 份，第 11 份写入后删除最旧一份。排查转发格式或缓存边界时，直接按文件时间读取相邻快照并对完整 JSON 做 diff |
| Claude 思考强度网关注入 | `routes/miniapp/upstreams.py`、`storage/upstream_store.py`、`services/upstream_policy.py` | App 通过独立设置接口按当前上游保存 `claude_thinking_effort`；网关对 `claude-opus-4-6/4-7/4-8/5` 与 `claude-fable-5` 转发时读取该值，注入 `thinking.type=adaptive`、`thinking.display=summarized` 与 `output_config.effort`。这不是 App 每轮聊天直接携带的字段 |
| Prompt Cache 诊断 | `services/prompt_cache_debug.py` | 记录静态/动态构成与上游 usage 元数据；Thinking 规范保持独立 breakdown，长期记忆与中期记忆分别显示，QQ、TG、微信、SumiTalk、小爱音箱入口风格也不会被近期记忆块标记吞掉 |

当前 Claude 缓存前缀顺序固定为：tools → 第 1 个断点 → 固定静态子块（system 首项恒为世界层级；Codex OAuth 上游命中时专用 Prompt 紧随其后，再后是核心 Prompt；尾部为五个自定义静态 System 槽位中的非空项，按 1→5）→ 第 2 个断点 → 工具摘要 → 第 3 个断点 → 入口风格 → SumiTalk Real/App 互斥专属槽位 → 渡的日常 → 较稳定近期记忆 → 最近记忆正文小段 → 第 4 个断点 → 最近记忆固定收尾 → 常驻动态 → 临时动态 → Thinking 规范 → last4 → 对话消息。固定静态、工具摘要、入口风格、Real/App 互斥专属槽位、渡的日常、较稳定近期和最近记忆属于静态提示前缀的独立逻辑子块，按唯一顺序表收集；延迟续话、归档和禁止再次排队等请求运行态不得增删或改写固定 followup system 规则，只能影响原有后处理。Thinking 规范单独输出为显式携带 `__dynamic__=True` 的 system 段，位于临时动态之后、last4 之前，不与其他动态内容或 last4 合并；专用内部标记只供 gateway 排序与诊断，上游转发前删除，因此不新增缓存断点。常驻动态、临时动态、Thinking 和 last4 分别保持独立，不会拼进静态区。工具摘要 marker 由 Claude OAuth proxy 用来稳定设置其前后的第 2、第 3 断点；工具循环内部只收集结果，整条工具链收口后才批量更新摘要块。play 小纸条仍由 `services/pixel_home.py` 生成，内容与触发条件沿用原逻辑，只从静态尾段调整到临时动态位置。世界层级首次部署会因固定静态最前缀新增正文产生一次预期缓存重建，正文不变后的请求继续按既有断点复用。

system 分区采用显式标记合同：凡辛玥明确指定为动态区、临时动态或一次性事件的 system，生产点必须直接携带 `__dynamic__=True`；未标记的 system 继续按 static 归类，不以正文内容猜测。这些临时动态 system 固定放在常驻动态之后、last4 之前，不得进入静态前缀；一起看当前剧情、一起听或当前音乐、小家/游戏事件、交换日记回执等都只调整到该注入位置，各功能原有的产生、持续与结束行为保持不变。若只是在调查或实现时判断某个 system 可能应改为动态，必须先说明来源、内容、现有行为、拟放位置及缓存或行为影响并向辛玥确认，不能静默重分类或扩展生命周期设计。

小家事件及 App 内涩涩走格棋、囚禁模拟器的 `sync-du` 请求通过 `X-DU-SUMITALK-PROMPT-ASSEMBLY` 复用 SumiTalk 的提示词组装表面，但不改实际回复、投递和归档渠道；小家/游戏状态作为临时动态 system，各入口保留自己的 user 内容。实现入口为 `services/conversation_followup.py::_send_wakeup_event` 与 `routes/chat.py::chat_completions`，`return_only`、游戏工具和续跑规则不受影响。以后新注册的 App 游戏，只要存在发给渡的模型消息，也必须复用该 SumiTalk 组装表面：不得自行拼静态 system，不得把游戏状态塞进静态缓存前缀，只允许替换本游戏的临时动态 system 与 user 内容；纯查看或本地状态变更接口不触发模型请求。

`step_inject_tool_result_cache()` 使用 `pipeline/pipeline.py` 的唯一 `_SYSTEM_PROMPT_REGION_ORDER` 和 `_SYSTEM_PROMPT_CACHE_GROUPS`：固定静态段、工具摘要段、工具摘要后的静态尾段、常驻动态段、临时动态段、独立 Thinking 动态段、last4 段。每个逻辑子块在组装期间保持独立，最终每段最多输出一条 system；五个自定义静态槽位在组装期间保持编号顺序并追加到固定静态段末尾，空槽跳过，最终随固定静态段合并。Claude OAuth proxy 识别工具摘要 marker 后，四个断点依次位于最后一个 tool、工具摘要之前的最后一个可缓存 system、工具摘要末尾和最近记忆当前最后一个正文小段末尾；最近记忆仍按原文与原顺序发送，但 proxy 会按既有双换行小段生成连续 Anthropic text blocks，把固定 `【以上为最近记忆】` 收尾留在第 4 个断点之后。新增小段时旧末段保持为可回看前缀，BP4 向新末段移动并写入该前缀；当前末小段随后整块改写时，lookback 回退命中前一个曾作为 BP4 写入的小段，只重建发生变化的当前小段。若更早小段或其他前缀内容被改写，仍按 Anthropic 前缀规则从最近一个此前实际写入的断点起重建；缓存过期或前一写入位置超出 20-block lookback 时不能复用。工具摘要变化只重建第 3、第 4 段，入口风格、Real/App、渡的日常和近期记忆变化只影响其所在及后续断点。入口风格、Real/App 和近期记忆保持对应逻辑块，play 进入临时动态段，Thinking 紧邻 last4 之前并显式携带 `__dynamic__=True`；内部 `__thinking_rules__`、`__temporary_dynamic__`、`__last4__` 仅用于网关排序，在转发上游前统一移除，`__dynamic__` 继续供已有缓存适配层识别动态内容。

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
- 流式 SumiTalk 聊天在 queue 入口跨 delta 识别并剥离 `<voice>...</voice>`；SumiTalk 主动唤醒在唯一 `deliver_chat_message` 入队成功后提取完整语音标签。两者复用同一 SQLite 持久 sidecar 和 MiniMax TTS/聊天媒体上传：流式任务继续发送允许晚于 `assistant_final` 的 `assistant_audio_ready` / `assistant_audio_failed`，主动任务则以 `message_id + voice_index` 生成稳定 task/part 并排队 App 已支持的 `deliver_chat_audio`，文字与音频 action 均保留 pending/done 幂等，App 重复收到同一 part 也不会再次下载或追加。App 轮询会恢复未完成或未投递的主动 sidecar；纯文字主动消息、QQ/TG、`/voice-call/*`、通话分段 TTS、取消和播放状态不受影响。
- 一起看聊天仍走同一 SumiTalk job。请求顶层附带 `watch_session_id` 和完整 `watch_snapshot` 后，`services/watch_context.py` 按消息发送时 playhead 注入当前剧情、当会话已播缓存的相关片段和可配置的回复抵达窗口，并明确要求“小玥正在和你看同一段，不需要和她照搬复述你看到的剧情内容以及逐项描述剧情画面。”；当前相关片段召回只在本会话、本 timeline epoch、发送位置前已完整播放的 `watch_plot_chunks` 内按最近三条用户消息做会话内 BM25/IDF 排序，剧情/对白、标签、人物字段依次降权，人物名作为全片高频词自动降权，只命中人物名时最多取一段，有事件词命中时剔除仅靠同名进入的候选，最多注入四段且不进入网关长期记忆。当前只持久化剧情片段，不单独保存每轮召回 query、候选分数或最终命中项。`knowledge_mode` 只在网关内部决定是否附加截止快照的剧情背景，不作为标签传给主模型。回复抵达位置前的少量剧情可用于当轮正常回复；动作区只提供预计回复抵达后仍未结束、且位于快照后两分钟内的可靠片段，弹幕示例从这些片段选择并明确目标是实际显示时间，不再固定使用发送位置加 30 秒。`services/watch_action_flow.py` 在流式与非流式链路剥离短标记并发出 `watch_danmaku_action`；旧长 JSON 块只保留解析兼容，无效时间标记和既有时间窗口拒绝会记录 reason，但不增加新的动作拒绝条件。事件不使用主动消息 channel，seek 后旧 epoch 动作失效。
- 事件契约和定向验证入口见 `docs/SumiTalk原生安卓后端流式接入.md`、`scripts/test_sumitalk_native_stream_backend.py`、`scripts/test_sumitalk_stream_voice_sidecar.py` 与 `scripts/test_sumitalk_proactive_voice_delivery.py`。

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

普通随机唤醒的主决策与随机冲浪后二次决策暂不提供论坛选项；主决策渲染会同步清理托管旧模板中既有的 `逛论坛`/`forum` 候选枚举，避免已保存 override 继续暴露旧选项。论坛 action 的旧解析和执行实现仍保留，未删除接口或历史数据。

唤醒记录只保存实际安排的随机唤醒、延迟续话、日历/闹钟，以及真正命中的硬触发，不把后台轮询 tick 当成唤醒。记录覆盖计划、执行、动作完成或消息实际投递成功、失败和取消；用户在预定时间前发来新消息时，原随机唤醒或续话会记为已取消并保留原因。查询默认返回下一次已确定的计划和最近 30 条结束记录，不暴露投递目标或内部 metadata。

随机主动唤醒的渡单机游戏统一注册在 `services/telegram_proactive.py::_PROACTIVE_SOLO_GAMES`，当前包含植物大战丧尸随机版、AI 农场和瓶中生态；注册表直接生成唤醒时的游戏选择，并决定后续实际游玩轮使用的工具与指令。以后新增任何渡单机游戏，都必须同步加入该注册表及必要的别名、直接 action 兼容和执行记录标签；共同游戏不进入这里。

半小时硬触发严格从全局 `last_user_activity_at` 重新计时：真实聊天、小家操作和游戏互动都算用户互动，任一新互动都会重置计时；聊天归档只用于识别本次互动是否明确表达要离开。入睡意图按分句识别，过去或背景叙述中的“我睡觉”不会被当成当前要去睡觉。

春梦本体提示词由 Prompt 管理区 `spring_dream_wakeup` 提供，模板中的 `{{fragments}}` 会替换为本轮抽到的梦境碎片；自定义模板漏写占位符时，后端会把碎片补在模板末尾。春梦后唤醒只消费当前睡眠 session 中六小时内的 pending 状态，其他旧 session 会失效清理；网关空回复时使用同一梦境重试一次，成功后仍只记录一次发送。只要主模型生成了非空春梦正文，专用梦境归档都会保存，并用 `sent`、`unconfirmed` 或 `not_dispatched` 标记投递状态；普通对话归档仍只记录确认投递成功的消息。梦境归档由 `GET /miniapp-api/spring-dream-archives`、`GET /miniapp-api/spring-dream-archives/<id>` 查询，`DELETE /miniapp-api/spring-dream-archives/<id>` 单条删除；删除会同步清理 SQLite、R2 正文对象、当天索引与最近索引，不存在返回 404，任一删除步骤失败返回 500。

统一图片上游处理位于 `services/image_desc.py::compress_images_for_anthropic()`：base64 图片复用现有 Anthropic 尺寸压缩；HTTP(S) 远程图片由网关下载、校验真实图片格式、复用同一压缩后转成 data URL，再进入上游。远程图片连接超时 5 秒、读取超时 30 秒，不设置图片字节数或条数截断；单张下载、响应或格式校验失败时只把该图片替换为 `【图片】`，同轮其他文字和图片继续处理。SumiTalk 与 QQ 普通图片的 URL 因此不再交给 Claude OAuth Proxy 临时下载。

### 4.3 QQ 与微信

- QQ OneBot 入口：`connectors/qq_onebot/src/main.js`
- QQ 群近期上下文：`services/qq_activity_context.py`
- QQ 入口 watchdog：`scripts/run_qq_entry_watchdog.py`
- 微信 iLink 直连说明：`docs/wechat_ilink_direct.md`

QQ 群上下文按发言人区分，不把群友内容当成小玥说的；入口消息仍进入统一聊天主链路。群聊上下文只允许后端随机主动决策、半小时硬触发、日历事件和系统闹钟使用；小家/身体/道具、延迟续话、屏幕检查、日记、游戏等其他后端事件与普通聊天均不注入。群聊上下文最多携带最近 5 张图片：OneBot 入口把 QQ 临时图片 URL 转成 base64，网关继续复用统一图片压缩；每张图片保留原群消息的发送者与时间，并在 `user` 多模态内容中紧邻图片前标注，避免把群友图片误认为小玥发送；不为这类上下文图生成图片描述；单张图片获取或压缩失败时只把该图回退为 `【图片】`，不影响其他图片和本轮唤醒。上下文存在时会同时告知渡可在回复正文开头使用 `[QQ_GROUP]`；随机主动决策的 JSON 把标记写在 `message` 字段开头。网关只从该上下文保存的来源群号生成后端投递元数据，模型不能选择群号；标记在归档和投递前剥离，经 OneBot connector `/push/group` 发回来源群，失败则回退原唤醒渠道。

QQ 群内直接 @ 渡的回复由 `connectors/qq_onebot/src/main.js` 控制选择性引用：本轮可见群消息按顺序标为临时 `Q1/Q2…`，渡只有在正文开头写 `[QQ_REPLY:Q编号]` 时才引用对应消息，也可以完全不引用；connector 只接受本轮真实提供的编号，发送前剥离控制标记，拆分文字、表情或语音时仅第一条实际出站消息携带 OneBot `reply` 段。引用目标不默认绑定当前 @ 消息。每个群最多连续处理 5 次有效 @，第 6 次起在调用网关前停止回复；任意一条未 @ 渡的群消息重置计数，重复 webhook 和机器人自身消息不重复占用次数。上限可由 `QQ_GROUP_MAX_CONSECUTIVE_MENTION_REPLIES` 调整，默认 5；QQ 私聊、主动 `/push/group` 与入站引用上下文保持原行为。

QQ 群 @ 入站黑名单位于 `connectors/qq_onebot/src/group_mention_blacklist.js`，由 `QQ_GROUP_MENTION_BLACKLIST` 配置，未配置时默认为 `3299553137,190689686`。命中成员 @ 本机器人时，`handleGroupEvent()` 在正文/语音/引用解析、群活动上报、群历史记录和网关调用之前直接返回，不调用模型、不发送回复；这些成员未 @ 的普通群消息及其他成员、QQ 私聊保持原行为。

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
| 动态层判断 | `services/dynamic_layer_ds.py`、`services/memory_merge_rules.py` | 产生 new / merge / out 等动态记忆决策；动态层与人工记忆重写共用同一份 merge / 迭代规则；merge 必须核对主体、对象、关系/行为和具体事项，只有关键词、标签、房间或宽泛语义相近时不得融合，名字羞耻症与渡的名字记忆是明确反例；只有当前内容明确表示这是不同日期发生的另一次一次性事件时，即使人物和行为相同也禁止 merge，有独立记忆价值时用 new，否则 skip；其余情况仍按原有的同一具体事项标准判断，同一过去事件不能仅因本轮正在谈论就改成现在，明确纠正事件时间时则可更新；merge 返回正文会完整替换旧正文，因此以选中旧记忆为底稿再融合本轮增量；未冲突内容继续合并同类项，重复表述去重、互补信息融合、关键事实与感受保留，不逐字搬运或堆叠旧正文；冲突部分不得无痕覆盖，其中被纠正的主观判断降回“当时的理解或误解”而不再作为当前事实，当时真实发生的感受与经历仍保留，本轮真实新增的具体情绪、动作或态度也必须保留；认知变化已自然成立时直接收住，不追加抽象点题；共享规则内含辛玥确认的空壳/底座三项 merge 示例并注明只学信息处理、不照抄句式；禁止固定时间句式、反省清单及无依据编造；merge 输出 `consolidate/correction/invalidate/supersede/temporal_update/habit_generalization` 六类规范原因，只有多次独立重复后归纳常态习惯或偏好时使用 `habit_generalization` 并转人工待审，普通同一事项补充仍自动 merge；动态记忆继续保留原有“事实 + 情绪”要求，只额外禁止“又 X 又 Y”情绪句式，不限制具体情绪词；缺失或非法原因进入现有重写机制，动态层血缘与待审候选保留原因字段；当前不按原因自动删除或淘汰记忆；在线候选检索 query 使用本轮完整文本，不再先裁成 2000 字；保留模型默认 thinking，不设置人为 `max_tokens` 上限 |
| 动态层候选与结果校验 | `services/dynamic_layer_ds.py`、`pipeline/pipeline.py` | 在线候选检索无命中或异常时保持空列表，不再拿最近 10 条无关记忆替代；空候选 Prompt 明确只允许 `new/skip`。单条 merge 必须在现有重试阶段返回可解析到本轮候选的 ref，缺失或非法时定向重写，连续失败按 skip，绝不降级成 new。new/merge 正文照抄本轮原话时由 DS 定向重写，连续失败按 skip，网关不再用 18 字片段拼“形成共识”等通用便签。TAG 必须是客厅/书房/图书馆/卧室之一，缺失或非法时由 DS 重写，连续失败按 skip；应用层只做枚举校验，不再因原文出现“私密/亲密/性暗示”等关键词强改卧室。批处理与归档批处理共用 tag/照抄校验，沿用既有整批重试和最终失败边界 |
| 记忆 embedding | `memory_vector/embedding_client.py` | 图片相关载荷仍先剥离，普通文本只做换行和空白归一化，不再按 `EMBEDDING_MAX_CHARS` 静默截断；Cloudflare 单条和批量请求都不发送 `truncate_inputs=true`，供应商输入过长时显式失败并沿用现有重试/异常路径，不再悄悄只嵌入前半段 |
| 动态记忆检索 | `pipeline/pipeline.py`、`services/dynamic_memory_search.py`、`services/dynamic_memory_reranker.py` | 关键词、向量与 rerank 组合召回；物理淘汰是唯一召回生命周期出口，仍保存在动态层中的全部条目都进入 BM25 与向量候选资格判断，不再按独立 10 天有效期二次过滤；最终仍按相关性、权重、`DYNAMIC_MEMORY_TOP_N` 与动态 token budget 选取少量结果注入 |
| 动态记忆镜像 | `storage/dynamic_memory_mirror_store.py` | 为管理、维护和诊断提供 SQLite 镜像 |
| 记忆整理轻量读取 | `routes/miniapp/memory_organizer.py`、`storage/memory_organizer_store.py`、`routes/miniapp_api.py` | `/miniapp-api/memory-organizer/summary` 只返回总结与动态/核心计数和 revision；`dynamic`、`core` 默认每页 40 条并用持久 revision/cursor 快照同步变化与删除，核心支持 `filter=pending/all`，动态直接返回 `prune_at`、`at_risk`、`core_protected` 及条目已有的 `pending_merge`；DS 审核明细由独立 `audit` 路由分页。四条路由均记录耗时、响应字节数和条目数，且不读取 recall/search/citation 调试事件；旧 `/memory-debug` 保持兼容 |
| 中期记忆 | `services/du_midterm_memory.py`、`routes/miniapp/midterm_memory.py` | 14 天滑窗、72 小时刷新；归档中的 `today_events` 按有效字符串原文全量输入，不限制每日条数、不裁切或替换事件正文，并按较早到较晚顺序提供；DS 请求不设置 `max_tokens`，正文严格顺叙、禁止破折号且只校验不超过 1000 字；聊天注入读取完整 latest，不二次截断 |
| 长期记忆 | `services/du_longterm_memory.py`、`storage/du_state_store.py`、`services/du_midterm_memory.py`、`routes/chat.py`、`routes/miniapp/longterm_memory.py`、`data/du_longterm_memory_first_draft_20260728.md` | 正式 latest 独立保存于 `global/du_longterm_memory/latest.json`；`GET /miniapp-api/longterm-memory` 只调用正式 latest getter，字段白名单为 `content/covered_through/updated_at/schema_version/model/prompt_version`，不读取或返回历史版本、增量素材及其来源 ID，不触发生成、DS 或 R2 写入；latest 缺失返回 200 + `exists=false`，读取异常返回稳定 500。第一版为 DS 生成并经人工确认的 722 字第一人称日记式正文，覆盖截止 2026-07-12。聊天从 R2 读取完整正文、不二次截断，以独立静态 system block 放在中期记忆前。中期每次成功保存后自动检查长期 `covered_through + 1` 起的固定三天，只有整个片段已退出新中期窗口才更新；中期增量由同源日归档生成，缺失日显式记录且不补写，另带同日期按 `updated_at` 归入的渡/辛玥画像，不读取动态/核心/Stay。增量和旧版分别保存到 `increments/*.json`、`versions/*.json`；DS 不设置 `max_tokens`，最终整篇重写最多 1500 字。跨进程文件锁防止重复消费，任何生成/版本/latest 写入失败都不推进截止日期；中期成功钩子立即触发，聊天注入负责非阻塞重试 |
| 画像记忆 | `services/portrait_memory.py` | 画像候选与更新边界 |
| 渡的日常 | `services/du_daily.py` | 对话硬触发事实不再只取最近 6 条或每条 180 字，维护事实不再只取 8 条；同日事件不再限制每次 3 条、累计 8 条，日总结不再裁成 900 字，兜底总结合并全部已有事件而非只取末 3 条；原有触发、去重、日切、归档与 R2 写入时机不变 |
| 近期总结 | `services/deepseek_summary.py`、`pipeline/pipeline.py` | 每 4 轮生成一个近期记忆块，每 8 轮在同一次 DS 更新中执行分层压缩迁移；最近 / 稍早 / 更早最多分别保留 8 / 10 / 7 个，共 25 个，填充期只迁移为下个压缩点预留位置所需的数量，填满后每个压缩点依次迁移 2 个并淘汰最旧 2 个；生成/待补结果保存前与聊天注入前不再套总 token budget 二次裁剪；已有轮次元数据时会从首个已知分组起补全部缺口，不再只回看 6 组或每轮只处理最近 2 个缺口；近期记忆总结显式关闭 thinking，不包含 Notion 小本本分支，动态层不受影响 |
| 记忆引用 | `pipeline/pipeline.py`、`services/dynamic_memory_citation.py` | 动态召回块按“开场 → 全部召回记忆 → `【以上为可召回记忆】` → 实际参考才标记 `[memory N]` 的规则”组装，先让模型完整阅读素材再给引用指令；流式与终态继续隐藏合法引用标记并回写真实 memory ID |
| 记忆管理 | `routes/miniapp/memory_panel.py`、`routes/memory_api.py`、`storage/r2_store.py`、`pipeline/pipeline.py`、`services/memory_maintenance.py`、`services/memory_rewrite.py`、`services/memory_merge_rules.py` | 查询、重写、删除、维护和诊断；人工重写与动态层共用同一份 merge / 迭代规则，preview 以正式原文为底稿，有核心 `pending_merge` 且用户修正时同时提供待修正候选、`merge_reason` 和最高优先级 `rewrite_instructions`，不会直接接受旧候选；DS 只返回纯正文，App 协议中的 `reason` 保持空字符串；空内容、原文照抄、拒绝、JSON、Markdown 代码块或解释会自动重试一次，连续两次无效才返回准确的 502；preview 只读，只有用户确认调用 apply 后才写入；动态层 `habit_generalization` 不直接替换正式正文，而是由 `stage_dynamic_memory_merge()` 保存 `pending_merge`，通过后才应用正文与字段更新，拒绝则只清除候选；动态和核心待审均复用 `/memory-rewrite/apply` 与 `/memory-rewrite/reject`，动态确认后同步刷新索引、SQLite 镜像与审计；`POST /miniapp-api/dynamic-memory/<id>/retain` 原子增加一次 `mention_count` 并刷新 `last_mentioned`，未命中返回 404、写入失败返回 500；卧室 tag 满 3 天未提及时只通过物理淘汰从动态层、索引与血缘退出，不存在独立的 3 天注入过滤，core_cache 保护项不删除且仍可召回；其他动态记忆前 15 天不衰减、第 16 天起每天衰减 0.1 且最多衰减 2，仅在至少 15 天未提及且综合权重不高于 2 时删除，图书馆 tag 与 core_cache 来源记忆永久豁免 |

亲密/卧室记忆仍使用动态记忆分类与独立生命周期；tag 只决定房间，不自动决定保存或抬高 importance。普通但具体、有独特画面或当下感受的亲密瞬间可记为 2；同段重复且无新增画面、感受或关系信息时 skip；有明显且日后仍值得回想的情绪分量才为 3；重要偏好、边界、承诺或关系变化才为 4；同一连续互动优先 merge，不额外侧写 Notion，也不进入不适合的核心缓存/画像路径。

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
- 日常面板与小家状态：`routes/miniapp/dashboard.py`；普通聊天中的小玥状态推断由 `services/pixel_home.py::infer_xinyue_state_from_text` 负责。洗澡意图使用 `chinese_calendar.is_workday` 按中国法定节假日与调休安排判断，北京时间真实工作日 08:00–17:00（不含 17:00）返回无更新并保持已有小家状态；法定休息日、其他时段和其他意图沿用原判定，不使用 weekday 兜底
- 设备状态与动作：`routes/miniapp/device_state.py`、`routes/miniapp/device_actions.py`
- 记忆、中期记忆与诊断：`routes/miniapp/memory_panel.py`、`routes/miniapp/midterm_memory.py`、`routes/miniapp/diagnostics.py`
- 交换日记：`routes/miniapp/exchange_diary.py` + `storage/exchange_diary_store.py`；小玥评论后的唤醒由 `services/conversation_followup.py::send_exchange_diary_comment_wakeup` 将日记标题、`entry_id/comment_id` 和回复工具规则放入带 `__dynamic__=true` 的 system，评论原文只以 `小玥评论了你的日记：{评论内容}` 出现在 user，不进入 static/dynamic system。渡通过 `services/chat_tools.py` 创建评论时继续发送 `notification_kind=diary_comment` 的系统通知，payload 带 `entry_id/comment_id/reply_to_comment_id/sender`，回复目标作者为 `xy` 时标题为“渡回复了你的评论”，其他情况保持“渡评论了你的日记”。
- 记事本：`routes/miniapp/notes.py`，对应聊天工具 `note_write`；聊天固定静态区注入全部现有条目，不再只取 20 条或遇到 500 token 后停止
- 秘密抽屉：`routes/miniapp/secret_drawer.py` + `storage/secret_drawer_store.py`；聊天注入由 `services/secret_drawer.py::format_rule_block/format_state_block` 和 `pipeline/pipeline.py::step_inject_secret_drawer` 负责，保存分类、隐藏标记及工具使用规则进入固定静态 system，常驻动态只保留当前抽屉的数量/分类/置顶/暗格/待整理统计，不注入具体条目或 PIN 状态。
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
- 瓶中生态：App 状态/能力地址为 `routes/miniapp/cedareco.py`，受保护完整 Web/API 挂载为 `routes/cedareco_proxy.py`，共享池塘与工具接缝为 `services/cedareco_bridge.py`、`services/cedareco_tool.py`；固定上游运行包位于 `vendor/cedareco/`，sidecar 脚本为 `scripts/start_cedareco.sh`、`scripts/install_cedareco_service.sh`，完整边界见 `docs/cedareco-app-integration.md`

一起看 Phase 2 分析 worker 入口为 `scripts/run_watch_analysis_worker.py`，安装脚本为 `scripts/install_watch_analysis_worker_service.sh`。新 session 先进入准备态；worker 可先执行 identify 和 timeline prepass，identify 会落库作品原语言正式片名与年份；人工填写正片起点时，identify 直接在该位置附近取样，避开 Bilibili 前置垫片。`partial/unknown` 会排队生成 `watch-knowledge-v13` 简短背景卡：Tavily basic 只执行一次 `《片名》剧情简介 主要人物 人物关系 世界观` 搜索，存在季集或分 P 时跟在书名号后，最多保留 3 个不同站点摘要；不限定站点、不调用角色目录。DS V4 Flash 不获得搜索工具，只负责整理作品身份、世界观、开场前情、主要人物与关系、专有名词和 3–5 条只说明主线方向的 `story_outline`；网关不规定人物数量，也不根据作品特定词硬补人物。卡片最多引用 3 条来源，不含结局、反转或逐场剧情；作品名、年份、人物姓名证据和置信度仍有门禁，单一可靠来源允许生成但会降低置信度。知识卡和字幕准备均进入可见终态后，只有 `POST .../start` 提交当前 `subtitle_lookup_id` 并确认卡片或明确跳过，才创建 rolling 任务。滚动取材计划会直接跨过已确认的 recap/intro/outro/preview/non_story，不再先送模型后仅丢弃结果。

Bilibili 开播前可通过 `GET /miniapp-api/watch/bilibili/parts` 获取真实分 P 列表及 `current/previous/next`，每个 P 使用独立 media id、时长和会话。`services/watch_analysis_source.py` 通过公开 `view/playurl/player` 接口取得分 P、480P AVC 主备视频流和音频流；每个分析批次重新获取播放地址并顺序取帧，备用流成功后会升为本批后续帧的首选，只有全部候选失败时才记录告警、刷新地址并仅重取当前帧。关键帧整组失败会在 worker journal 记录媒体时间点、候选流序号、返回码或超时类型及脱敏 stderr，不记录流 URL、签名参数、Cookie 或请求头。字幕任务先检查 Bilibili 原生字幕；没有原生轨时，`storage/watch_subtitle_store.py` 从知识卡、识别结果和媒体元数据整理原名、中文名、英文名候选，`services/watch_subtitles.py` 在配置 `WATCH_SUBDL_API_KEY` 后让首轮任务依次查询并携带年份。候选级未命中或不安全字符只跳过当前片名，鉴权、额度和真实服务错误进入可见失败。`POST .../subtitles/retry` 生成独立 `tmdb_then_subdl` 策略；可选 `WATCH_TMDB_READ_ACCESS_TOKEN` 配置后按多语言片名、年份和媒体类型解析唯一 `tmdb_id` 再查 SubDL，未配置 TMDB 时仍重新执行多标题 SubDL，因此 TMDB 不是必需项。字幕按人工 `content_start_ms` 整体平移并写入 `watch_subtitle_assets`，TTL 24 小时。本地文件会话则在创建时提交 `local_asset_id + media_revision`、能力检测和所选音轨/字幕轨，并在开播前通过 `POST .../local-subtitles` 提交匹配 revision 的内嵌或外挂 SRT/VTT；有符号 `offset_ms` 来自所选字幕配置。状态接口只返回语言、版本、格式、条目数、覆盖区间和清洗结果，不返回字幕正文、下载地址或 key；`/start` 拒绝旧 `subtitle_lookup_id`。rolling 只读已确认字幕资产，不再访问字幕 provider。

`watch-v9` 从请求源头按 `knowledge_mode` 分流剧情背景：`known` 保持 `story_background` 为空，`needs_summary` 才产出截止 `through_ms`、仅供理解当前批次的防剧透背景。滚动请求不生成或回传累计剧情与累计事件状态，只读取上一批时间窗内已经落库的紧邻 `plot_chunks` 来衔接人物和场景；滚动分析和知识卡请求都不设置 `max_tokens` 或其他显式输出上限。开播门锁仍要求五分钟可靠覆盖；解锁后 worker 按约 140 秒完整批次继续预取到最多领先 30 分钟或正常正片终点，达到高水位后至少消耗一个完整批次才补充，避免播放头每前进几秒就生成一次完整 provider 请求。风险区间使用最早可能开始到确认安全结束的保守边界，状态接口按真实 playhead 返回 `fear_protection`，剩余覆盖不足两分钟即为 `coverage_low`。保存进度后恢复会复用已确认准备态和已有剧情覆盖；普通 worker 轮询不复活 failed source job，只有 `resumed_from_progress=true` 的显式恢复可为未调用 provider、无 token/费用的 failed backend-source 缺口派生一个新任务，重复恢复不重复入队且新任务仍遵守最多三次尝试。Bilibili rolling 由 `ffmpeg` 提取最多约 140 秒的 16 kHz 单声道 32 kbps MP3 和最多 8 张图；公开解析失败时，可选 `WATCH_ANALYSIS_BILIBILI_COOKIE` 仅作网关专用登录态兜底。字幕准备独立使用默认 15 秒单请求、45 秒总预算和一次自动任务尝试，候选下载 URL 保序去重但不限制唯一候选数量，失败后由准备页显式重试；首轮与手动重试策略分别写入 `subtitle_lookup.search_strategy`，worker 记录 provider 阶段耗时。`POST .../analysis/samples` 对 Bilibili 是备用入口，对 `local_file` 是受 `watch_client_sample_plans` 约束的正式入口：计划绑定 media、revision、epoch、用途、允许范围和过期时间，每批最多一段 MP3/AAC/MP4 短音频及 8 张 JPEG/PNG/WebP，网关校验实际范围和当前音轨，AAC/MP4 在内存中规范化后复用同一 Gemini 链。模型默认经 OpenRouter 调用 `google/gemini-2.5-flash`，使用 `input_audio + image_url`、严格 JSON schema 且 `reasoning.effort=none`；响应适配器接受 `message.parsed`、JSON/content blocks、代码围栏、前后说明和确定性的轻微 JSON 语法偏差，但不完整结果或缺少分析顶层字段的自然语言不能推进剧情与胆小模式覆盖。响应包或剧情结果解析失败时，worker journal 记录完整上游响应及任务定位字段，不记录请求中的音频、截图或 key。

`watch_sessions.client_seen_at/client_lease_expires_at` 是独立存活租约，不能用会被 worker 更新的 `updated_at` 代替；播放快照、状态轮询、显式 `POST .../heartbeat` 和客户端素材提交会续租。创建会话以同一设备、窗口和完整媒体/模式参数生成 `creation_key`，同一有效租约内的重放返回原 session 与 `create_reused=true`，SQLite 唯一索引在老库加列迁移后创建，避免超时重试启动两套分析。source、knowledge、subtitle 三个调度入口只处理未结束且租约有效的会话。seek 切换 epoch 仍取消旧任务、开放计划与动作，但同一 session/media 已完成的 rolling 区间会按媒体时间复制剧情、风险和检查点到新 epoch，调度从已付费覆盖末端继续；人工 timeline correction 只是取材参考，只取消未完成任务和原始样本，不清除、推进或判废已完成结果。活跃会话不按累计分析任务数量或每日费用设置终止上限。每个 session 记录服务端观察时间和本 P `played_duration_ms`，只累计相邻同 epoch、上一状态为播放中的确认区间，并按上一倍速用媒体前进量校准，因此准备、暂停与 seek 不计时；达到正片完成边界后仍继续播放的可信区间也持续累计到明确结束。首个分 P 由后端生成 `viewing_id`，后续 P 显式复用；长期 `watch_viewings` 聚合跨 P 时长和自然播放完成部分。自然到达正片终点只落 `playback_completed`，不替使用者选择“已看完”或出票。退出弹窗分别调用 `viewing_action=save_progress|complete`：保存进度保留同一 viewing、playhead 和已生成剧情分析且不出票；已看完清除续播状态并生成或复用稳定票根；切 P、`pagehide` 和异常清理使用默认 cleanup。`GET .../viewings?status=recent` 同时返回续播项和已看完项，并提供封面、`watched_percent/status_text`；保存项恢复时复用保留的 session，已看完项固定显示“已看完”。票根支持两类背面来源：旧的 session 临时剧情帧仍可选中后持久化；客户端也可通过 `POST/GET .../viewings/<viewing_id>/ticket-frame-captures` 保存并查询同一 viewing、跨分 P 的多张 JPEG，图片读取接口在 session 结束、save_progress、complete 后仍有效。`PUT .../ticket-frame` 可在无活跃 session 时按 `capture_id` 重选并同步已有 ticket，`DELETE` 只清除当前选择而不删除 capture 集合。原始音频与普通临时画面仍在结束时清理。完成后的剧情分析由 `WATCH_COMPLETED_ANALYSIS_TTL_SECONDS` 控制，默认 24 小时；保存进度不套该 TTL，持久票根截图也不走该 TTL。`GET .../viewings/<viewing_id>` 与 `GET .../tickets` 支持受信任设备恢复。`DELETE .../sessions/<id>` 在事务中结束 session、取消 queued 任务、给 running 任务写 `cancel_requested` 并关闭开放计划，随后清除样本和普通派生帧；原 `analysis_cost` 保留，并返回 `viewing_summary/ticket`。`analysis_cost` 汇总 identify、timeline prepass、rolling、knowledge card 搜索/整理和外部字幕调用，本地缓存/指纹复用不计 provider 调用。真实 provider 响应在结束、租约、epoch 的调用后检查之前按 attempt/stage 事件幂等写入，迟到结果仍拒绝提交但 usage 不会消失；分析任务的 `complete` 只表示没有 queued/running 任务，`pricing_complete` 单独表示所有调用均返回美元价格，`unpriced_calls` 与 purpose breakdown 显示未报价调用，客户端不能把不完整或未报价的零显示成免费。worker 在取材、搜索、字幕 provider、Gemini 调用前后和结果提交前复检；worker 启动时和每分钟结束空租约/过期租约遗留会话，日志使用 `skip_reason=session_ended/client_lease_expired/cancel_requested`。原始 MP3/截图在成功落库、旧时间轴取消或最终失败后立即删除；低清派生 WebP 只保留播放点前 10 分钟到后 5 分钟且每会话最多 48 帧，seek/结束立即清空。部署除 Python requirements 外要求系统 `ffmpeg`，健康接口会报告取材、知识卡、字幕 provider 和视觉缓存状态；worker 不是 Flask 内线程。新增持久截图定向验证为 `.venv/bin/python scripts/test_watch_ticket_frame_captures.py`；既有一起看验证仍为 `.venv/bin/python scripts/test_watch_together_backend.py`、`.venv/bin/python scripts/test_watch_analysis_phase2.py`、`.venv/bin/python scripts/test_watch_local_lifecycle.py`、`.venv/bin/python scripts/test_watch_viewing_ticket.py`，测试使用假的媒体、字幕、搜索和模型上游，不写 R2。

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

`deliver_chat_message` 由 `storage/app_action_store.py` 按调用方提供的稳定幂等键持久化；同键在 TTL 内且原 action 仍 pending 或已经 done 时，返回原 action 和原 payload，不新建第二条设备消息，也不以重投正文覆盖或扩增已保存的 `text`。failed/abandoned/expired 与其他 action 类型继续沿用原有语义，不被本幂等收紧覆盖。

设备感知快照写入 `sense_latest`，24 小时短尾历史写入 `sense_history`；历史按感知类型分别限量，前台应用与会话高频上报不会挤掉屏幕、健康、位置和电量记录。`screen.sleepSession` 是唯一活动睡眠会话：手机熄屏建立候选；同一真实前台 App、不同真实 App 的活动样本或前台切换时已关闭的真实 App 连续会话覆盖 2 分钟，或者电脑严格递增的新输入样本连续覆盖 2 分钟，才确认清醒并把睡眠结束时间回填到连续活动起点；活动样本间隔超过 2 分钟会重建窗口。同一睡眠候选里的重复 `screen_off` 保留手机和电脑活动窗口，只有真正建立新候选才清空；单次亮屏、单条 App/电脑事件、延迟旧 `lastInputAt`、重复或倒退的电脑补报均不得结束睡眠，系统桌面等系统前台不单独启动手机活动窗口。睡眠候选少于 30 分钟直接拒绝；达到 30 分钟后按时长、区间心率和步数共同计算可靠程度，低心率与低步数增加可信度，持续偏高心率或明显步数增长降低可信度，样本缺失或只有单个样本不单独否决，可靠程度不足的候选标记为 `rejected_sleep`，不进入睡眠汇总也不成为主动醒来触发源。同日有效睡眠按日期聚合，跨零点归醒来日期；展示保留两端日期、分段累计和真实总时长，存在新睡眠候选时仍同时向渡注入已经确认的累计汇总。

`POST /miniapp-api/device-state/location` 保存 `precision`、`age_ms`、`is_mock`、`coordinate_system`、`trusted`；非 trusted、非 fine、mock、accuracy 大于 150 米或 age 大于 600000 ms 的上报在去重、高德解析和持久化前返回 skipped，不覆盖最后可信位置。可信点的顶层 `lat/lng` 与 `wgs84_lat/lng` 保持 App 原始 WGS84，`services/amap_geocode.py` 先调用高德 `coordinate/convert`（`coordsys=gps`），再以独立 `gcj02_lat/lng` 调用 regeo。地址复用读取持久 `sense_latest.location`，沿用位置历史既有的 `0.001` 度邻近边界和 30 分钟时窗；高德转换或逆地理失败记录解析失败并保留上一次可信地址，不再写空地址。

### 8.4 游戏

- 游戏工具聚合：`routes/miniapp/game_tools.py`
- 统一工具运行时：`services/game_tool_runtime.py`
- 私密走格棋：`services/private_board_tool.py`
- 随机版塔防：`services/random_imitator_td_tool.py`
- 文游：`services/wenyou/*`、`storage/wenyou_sqlite_store.py`

文游玩家工具默认不进入聊天工具集。App 负责管理“无限流游戏模式”这个全局开关；开启后，统一聊天入口都会注入 `buy_item`、`roll_gacha`、`inventory_action`、`use_item`、`transfer`，关闭后所有入口都不注入。

文游经济与角色状态以 `wallet.wallets.player1/player2`、`wallet.inventories.player1/player2/task_items` 和运行中 `stats.inventories` 为当前数据源；顶层 `points/debts/inventory` 只保留玩家一旧接口兼容。结算奖励、新手礼包、商店/抽卡、加点、晋升、复活、使用/回收/转交均按实际角色结算，物品阶位与属性门槛也只检查持有者本人。新手流程只有 `standard_clear` 才完成，失败归档后仍会重新进入 `T-000`；长期等级、属性、阶位和核心能力会在角色卡与下一局之间双向同步。GM 上下文按持有者列出两名玩家背包和队伍任务物，核心能力画像只采集对应玩家自己的历史行动。公开读改写入口按 `user_id` 使用可重入锁串行；同主机多 worker 额外使用临时目录 `flock`，无 `fcntl` 平台退回进程内锁。非法角色 ID 明确拒绝，不再静默落到玩家一。

文游定向验证：`.venv/bin/python scripts/test_wenyou_logic_regressions.py` 覆盖教程重试、双账户奖励与背包、GM 持有者视图、个人门槛、能力样本、跨局成长、同进程/跨进程串行写入、重复唯一商品和非法角色；`.venv/bin/python scripts/wenyou_rules_smoke.py` 覆盖既有规则基础链。

游戏内部允许列表、道具适配表和安全访问 allowlist 属于各自领域约束，不等同于已经移除的聊天窗口白名单/黑名单。

## 9. 运维与定向验证

### 9.1 本地基础验证

```bash
.venv/bin/python -m py_compile app.py routes/chat.py pipeline/pipeline.py
.venv/bin/python -c "import app"
git diff --check
```

### 9.2 关键运行检查

当前主网关的 SSH 入口优先使用 `ssh du-gateway`，该别名走 Tailscale；只有 Tailscale 不可用或需要专门排查公网入口时，才使用 `ssh du-gateway-public`。部署、日志与服务操作不要先拿公网 IP 或默认 SSH key 试连。

```bash
curl -fsS http://127.0.0.1:5000/health
curl -fsS http://127.0.0.1:5000/v1/models
systemctl --no-pager --full status du-gateway.service
```

涉及独立入口时，同时检查其实际 worker，而不是只重启主网关。SumiTalk 变更至少核对 `du-sumitalk-chat-worker.service`；Telegram webhook 或主动唤醒变更分别核对对应 worker。

验证必须针对准备提交、推送或部署的版本。小改动只跑真实故障路径相关的定向检查，不默认跑全量测试。
