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
| 主聊天策略 | `services/entry_style_prompt.py`、`services/chat_prompt_injections.py`、`services/upstream_policy.py` | 入口风格 system、voice/followup/NSFW/禁言注入、active upstream 选择、OpenRouter/CPA/Claude OAuth 请求策略 |
| 主聊天诊断/思维链 | `services/prompt_cache_debug.py`、`services/reasoning_utils.py`、`services/chat_content.py` | prompt/cache debug、reasoning/thinking 剥离、SSE message 解析、消息字符统计 |
| 主聊天响应辅助 | `services/chat_sidecars.py`、`services/chat_response_enrichers.py`、`services/chat_tool_helpers.py`、`services/chat_request_helpers.py`、`services/chat_archive_helpers.py` | 隐藏 sidecar 写入、HTML 预览/SumiTalk 卡片补全、tool 重试/SSE 小工具、入口状态/误触保护、归档后台辅助 |
| 注入管道 | `pipeline/pipeline.py` | core prompt、summary、last4、sense、dynamic memory、tools 注入 |
| MiniApp API | `routes/miniapp_api.py` | SumiTalk、设备、思维链、设置、贴纸、日历、上游切换等接口 |
| MiniApp 前端主壳 | `miniapp/src/ui/App.tsx` | 首页、聊天页、设置页、消息渲染、SumiTalk job |
| MiniApp 分页 | `miniapp/src/ui/tabs/*` | 日志、思维链、上游、日历、贴纸、记忆调试等子页 |
| 文游规则草案 | `docs/wenyou_rules.md` | 开源版文游核心规则、副本蓝图、数值、固定装备槽位、武器锻造、回收拆解、商店、抽卡、奖励、升级、惩罚副本、后端规则引擎边界 |
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
- MiniApp 界面：`miniapp/src/ui/tabs/ListenWithDuScreen.tsx`
- MiniApp 入口：`miniapp/src/ui/ChatsHome.tsx` 的“和渡一起听”会话行，`miniapp/src/ui/AppShell.tsx` 负责全屏打开
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
- 这条通道是工具结果，不写入聊天记忆、不走普通对话归档；MiniApp “和渡一起听”界面目前只展示一起听 UI，不直接暴露给渡看的分析条目。一起听背景图在「个性化」里选择，图片压缩后只存本机 `localStorage`，不上传网关。
- 本地脚本模式用 `scripts/analyze_music_file.py --title "歌名" --artist "歌手" song.mp3`；脚本本地调 OpenRouter/Gemini，只把分析后的 JSON 发到 `/api/music/listen/result`。

当前状态（2026-05-16）：
- 已完成：新增音乐旋律分析后端 MVP，包含缓存查询、上传分析、结果写入和最近缓存列表；音频不持久化，文字结果优先写 R2，未配置 R2 时落本地 `data/music_melody_cache.json`。本地脚本 `scripts/analyze_music_file.py` 可用同一份 Gemini Flash prompt 分析本地音频，再只上传文字结果。MiniApp 已按 `ui合集/和渡一起听ui` 接入“和渡一起听”全屏界面和会话入口，并在「个性化」里支持用户本机替换一起听背景图。
- 已验证：`python3 -m py_compile` 覆盖 `storage/music_melody_store.py`、`services/music_melody_analyzer.py`、`routes/music_melody_api.py`、`scripts/analyze_music_file.py`、`app.py`；Flask `url_map` 确认 `/api/music/listen/*` 和 `/api/music-melody/*` 已注册；`scripts/analyze_music_file.py --help` 正常；`npm -C miniapp run build` 通过并生成 `ListenWithDuScreen` 前端 chunk。
- 未完成 / 不要碰：界面暂未接真实歌曲选择和真实聊天上下文注入；本轮没有触碰 QQ connector、小爱音箱文件和既有半成品。

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

## 文游 App 迁移 / TG 旧链路清理

入口：
- MiniApp API：`routes/miniapp/wenyou.py`
- 文游核心：`services/wenyou_service.py`
- 存储：`storage/r2_store.py` 的 `wenyou/active/`、`wenyou/archive/`、`wenyou/last_archive/`、`wenyou/candidates/`、`wenyou/cards/`
- 配置：`config.py::WENYOU_SESSION_ID`、`config.py::WENYOU_DS_MODEL`
- 升级方案：`docs/文游升级优化方案.md`

当前状态（2026-05-16）：
- 已完成：文游不再绑定 Telegram 群、TG 用户或 GM Bot；`/telegram/webhook_gm`、TG 文游群命令、群内玩家行动记录、TG 私聊 GM 剧情注入和文游群 Last4 混入均已移除。MiniApp 文游状态/归档/开局仍走 `WENYOU_SESSION_ID` 对应的 R2 `wenyou/` 会话。
- 已验证：`python3 -m py_compile` 和 `.venv/bin/python -m py_compile` 覆盖本组文件；`.venv/bin/python` 路由表确认 `/telegram/webhook` 保留、`/telegram/webhook_gm` 移除、`/miniapp-api/wenyou/story` 保留；`rg` 确认 `TELEGRAM_GM_BOT_TOKEN`、`WENYOU_GROUP_CHAT_ID`、`TELEGRAM_WENYOU_OWNER_USER_ID`、`step_inject_wenyou_gm`、`record_group_player*` 已无运行时代码引用；`git diff --check` 通过。
- 未完成 / 不要碰：本轮没有重做文游 App 交互、没有迁移旧 TG 群会话数据、没有改 MiniApp 前端构建产物；真正的新 App 文游形态等下一阶段再定。

当前状态（2026-05-16 续）：
- 已完成：`miniapp/src/ui/tabs/WenyouTab.tsx` 在文游开局成功后展示入副本文字动画，文案为“欢迎来到 {副本名} / 努力生存下去吧”，并显示副本编号、类型、难度；动画可点击关闭，约 4.2 秒后自动消失，尊重 `prefers-reduced-motion`。样式改为黑场、扫描网格、主神系统字幕方向，落在 `miniapp/src/styles.css`，构建产物同步到 `miniapp_static/`。
- 已验证：`npm -C miniapp run build` 通过；`rg` 确认旧版 `wenyou-entry-card/chip/line` 已无引用；构建输出为 `miniapp_static/assets/WenyouTab-D4kLZKF1.js` 与 `miniapp_static/assets/index-B3C3M5QZ.css`；`git diff --check` 通过但仍提示既有 CRLF warning。
- 未完成 / 不要碰：本轮没有做副本模式选择、任务进度、背包/道具使用、角色状态等下一阶段结构化玩法；没有清理既有 `miniapp_static/assets/*` 旧哈希产物。

当前状态（2026-05-16 续2）：
- 已完成：新增 `docs/文游升级优化方案.md`，把文游 App 化后的完整 UI 与功能目标写成方案：主神空间、副本选择/随机、入场动画、主界面、任务、背包、状态、线索、地点、人物关系、历史、结算、归档和设置。
- 已验证：文档文件已创建，`docs/DEBUG_INDEX.md` 已补方案入口。
- 未完成 / 不要碰：本轮只写产品/交互/功能方案，没有改前端实现、后端实现或构建产物。

当前状态（2026-05-16 续3）：
- 已完成：按下载的 `ui合集/文游ui.html` 参考，把文游入场动画调成更赛博的主神终端风格：青色扫描网格、CRT 纹理、LINK 状态、终端标签、进度条和标题轻微 glitch；仍保持“欢迎来到 {副本名} / 努力生存下去吧”的入场文案。
- 已验证：`npm -C miniapp run build` 通过；构建输出为 `miniapp_static/assets/WenyouTab-CCA4zc_p.js` 与 `miniapp_static/assets/index-C3vf5Atl.css`。
- 未完成 / 不要碰：本轮只调整副本入场动画，没有改一级页面骨架、任务/背包/状态/线索二级面板或后端接口。

当前状态（2026-05-16 续4）：
- 已完成：按下载的 `ui合集/文游ui.html` 一级页面参考，重做 `miniapp/src/ui/tabs/WenyouTab.tsx` 的主神空间、副本大厅、游玩主界面、历史归档和随机匹配弹窗；`miniapp/src/styles.css` 补 cyber 暗底网格、扫描线、霓虹边框、筛选条、副本卡、状态条和输入区样式。现有 `/miniapp-api/wenyou/status`、`/archives`、`/story`、`/archive/{id}` 调用路径保留，任务/背包/状态/线索二级面板先保留前端占位。
- 已验证：`npm -C miniapp run build` 通过；构建输出为 `miniapp_static/assets/WenyouTab-Ch36gUu0.js` 与 `miniapp_static/assets/index-DLEYPdeX.css`；本地 `http://127.0.0.1:5174/miniapp/` 在 Edge 打开并进入文游页，主神空间和副本大厅渲染正常；`git diff --check` 通过但仍提示既有 CRLF warning。
- 未完成 / 不要碰：本轮只抄一级 UI 和前端交互壳，没有接入任务进度、背包物品、状态详情、线索板等二级真实数据；没有改 `routes/miniapp/wenyou.py`、`services/wenyou_service.py` 或其他后端；不要清理既有 `miniapp_static/assets/*` 旧哈希产物。

当前状态（2026-05-16 续5）：
- 已完成：把副本大厅从前端写死卡片改成 DS 候选设定池：新增 `/miniapp-api/wenyou/candidates`，GET 优先读 R2 `wenyou/candidates/{WENYOU_SESSION_ID}.json`，无缓存或 POST 刷新时才调用 DS 一次生成 3-8 条轻量候选；选中候选后 `/wenyou/story` 接收 `candidate`，由 `services/wenyou_service.py::format_candidate_expansion_prompt` 转成 custom 开局提示，再扩展为完整副本框架。前端大厅显示候选生成时间、刷新候选、筛选/搜索、候选任务/生存点/风险/标签，并把“随机进入”改成生成候选池。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/wenyou.py services/wenyou_service.py storage/r2_store.py` 通过；`.venv/bin/python` smoke check 确认候选 seed 能格式化为完整副本扩展提示；`npm -C miniapp run build` 通过，当前入口指向 `miniapp_static/assets/index-DIqBcn2P.js`、`miniapp_static/assets/index-DdU-hu8p.css`，文游 chunk 为 `miniapp_static/assets/WenyouTab-C81wM0Uv.js`。
- 未完成 / 不要碰：本轮没有接任务推进、背包、状态、线索二级真实接口；没有清理旧 `miniapp_static/assets/*` 哈希产物；候选池刷新会真实调用 DS，线上需确认 `DEEPSEEK_API_KEY` 与 R2 配置可用。

当前状态（2026-05-16 续6）：
- 已完成：接上文游具体后端功能闭环：新增 `/miniapp-api/wenyou/session` 结构化读取任务、背包、状态、线索和历史；新增 `/wenyou/action` 记录玩家行动并复用 `cmd_go` 推进 GM；新增 `/wenyou/item/use` 校验背包道具并交给 GM 判定效果/消耗；新增 `/wenyou/go`、`/wenyou/end`、`/wenyou/settle` 供后续 UI 做推进/结算。`cmd_go` 会把本轮玩家行动写进 history，再保存 GM 回复与解析后的主神面板。前端行动输入、任务/背包/状态/线索面板、背包道具使用已接这些接口。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/wenyou.py services/wenyou_service.py storage/r2_store.py` 通过；`.venv/bin/python` smoke check 覆盖 `get_session_view` 的背包和线索提取；`npm -C miniapp run build` 通过，当前入口指向 `miniapp_static/assets/index-75o6menU.js`、`miniapp_static/assets/index-D4ifVuNu.css`，文游 chunk 为 `miniapp_static/assets/WenyouTab-BFpz_uzq.js`。
- 未完成 / 不要碰：行动推进和道具使用会真实调用 DS；任务进度/线索仍来自 framework 与 GM 文本备忘解析，还不是独立数据库任务系统；没有清理旧 `miniapp_static/assets/*` 哈希产物。

当前状态（2026-05-16 续7）：
- 已完成：按共读卡片思路给文游补连续性卡片 `wenyou/cards/{WENYOU_SESSION_ID}.json`，只供文游上下文使用，不进动态召回；玩家提交行动时 `/wenyou/action` 会先生成“渡本轮行动”，再把辛玥行动 + 渡行动一起交给 GM 推进，前端 feed 会显示“渡的行动”。每轮 GM 结算后会把 `[文游]` / `[文游·GM]` 前缀的虚构游戏回合写入普通 `windows/wenyou/conversation.json`，同步全局 latest4，并每 4 轮触发近期总结；摘要 prompt 已明确这些是文游游戏内容，避免 DS 当成现实经历。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/wenyou.py services/wenyou_service.py storage/r2_store.py` 通过；`npm -C miniapp run build` 通过，当前入口指向 `miniapp_static/assets/index-8r4gdEvI.js`、`miniapp_static/assets/index-D4ifVuNu.css`，文游 chunk 为 `miniapp_static/assets/WenyouTab-cQYbHaGv.js`。
- 未完成 / 不要碰：本轮没有启用动态记忆召回，也没有把文游卡片混入普通聊天；没有清理旧 `miniapp_static/assets/*` 哈希产物。渡自动行动和 GM 推进线上会真实调用 DeepSeek，需线上确认 `DEEPSEEK_API_KEY` 可用。

当前状态（2026-05-16 续8）：
- 已完成：修正文游背包交互节奏：前端背包按钮不再直接调用 `/wenyou/item/use` 推进 GM；点击道具只把 `使用道具【道具名】：` 填进行动输入框并聚焦，必须由玩家点发送后才算一轮行动。查看任务/背包/状态/线索和选择道具都只读缓存/session，不触发 DS。
- 已验证：`npm -C miniapp run build` 通过；当前入口指向 `miniapp_static/assets/index-BXWyjSNl.js`、`miniapp_static/assets/index-D4ifVuNu.css`，文游 chunk 为 `miniapp_static/assets/WenyouTab-Dav6824r.js`。
- 未完成 / 不要碰：后端 `/wenyou/item/use` 暂时保留为快捷接口，但 MiniApp 默认不使用；下一步若要严谨，可以加“道具详情/使用说明”二级弹窗。

当前状态（2026-05-17 文游规则对齐）：
- 已完成：按 `docs/wenyou_rules.md` 对齐现有文游硬规则：阶段统一到 `hub / candidate_selection / instance_running / settlement / archived`，新局默认 `instance_running`，结算进入 `settlement`；副本生成不再写死 6 人/4NPC，改为 `tasker_total 2-13` 且 `npc_taskers = tasker_total - player_count`；新人初始数值改为 HP/SAN 180/180、Lv1、D 阶、EXP 0、体力/智慧 10、血统凡人、能力/武器/状态为空；新增 `public` / `gm_secret` / `instance_blueprint` 规范化，GM 推进时会读取蓝图短纲但前端不整段展示隐藏内容；系统商店只在 `hub` 或 `settlement` 可购买，副本中只能查看货架和使用已有背包物品；默认商店货架扩成规则文档里的商品表，前端显示阶段锁定原因和 EXP/状态。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app` 与文游 shop/framework/blueprint smoke check 通过；`rg` 扫描确认源码里已无旧的固定 4NPC/6 人硬规则命中；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BmrlS9UT.js`、`miniapp_static/assets/index-MhmZJNL5.css`、`miniapp_static/assets/index-C2lubs5K.js`；`curl -I http://127.0.0.1:5174/miniapp/` 返回 200。
- 未完成 / 不要碰：这次没有把完整 Rules Engine / `state_patch`、结算奖励公式、抽卡、锻造和长期钱包一次性落完；当前仍保留兼容用【主神面板】解析，后续要逐步迁到 `GM event_intent -> Rules Engine -> state_patch -> GM narrative`。

当前状态（2026-05-17 文游规则引擎小步）：
- 已完成：在 `services/wenyou_service.py` 接上轻量 Rules Engine：GM 每轮先输出【事件意图】JSON（风险等级、目标、标签、行动状态、状态增删、威胁时钟），后端按 `docs/wenyou_rules.md` 的风险基础伤害、难度倍率、体力/智慧减免和阶位减伤计算 HP/SAN；状态阈值会自动添加轻伤/重伤/濒死、动摇/污染/失控；`state_patch` 写入 `session["event_log"]` 和 `last_state_patch`，前端剧情下方展示【规则结算】摘要。普通副本行动中若有事件意图，GM 面板里的 HP/SAN 不再覆盖后端计算。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app` 通过；规则烟测覆盖 `dangerous + mental/rule_pollution`，B 难度下玩家一 SAN 从 180 结算到 153，威胁时钟推进到 1/6；`git diff --check` 通过（仅既有 CRLF warning）；`npm -C miniapp run build` 通过。
- 未完成 / 不要碰：这一步还不是完整独立 ruleset/content-pack 文件，也没有把奖励结算、抽卡、锻造、钱包和物品效果全部迁出 prompt；GM 叙事目前仍是同一轮调用里读事件意图规则，不是严格两阶段二次调用。

当前状态（2026-05-17 文游结算/钱包骨架）：
- 已完成：跳过抽卡动画与抽卡机制，先补结算和长期钱包：`storage/r2_store.py` 新增 `wenyou/wallet/{user_id}.json` 读写；商店改为扣长期钱包积分并同步当前 session；`cmd_end` 进入 `settlement` 时按难度、通关结果和评级发放积分/EXP，优先偿还债务，写入钱包 ledger、session settlement、event_log；玩家 EXP 会按 `level * 100` 循环升级并发自由属性点/能力 token；归档会带上 wallet、settlement 和 event_log。MiniApp 文游主界面补“进入结算 / 系统商店 / 归档本局”操作。
- 已验证：`.venv/bin/python -m py_compile storage/r2_store.py services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；结算烟测覆盖 D 难度标准通关 B 评级，积分 +120、EXP +36、钱包 100 -> 220；`git diff --check` 通过（仅既有 CRLF warning）；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BZ8ljq8u.js`、`miniapp_static/assets/index-DbUb1qhR.css`、`miniapp_static/assets/index-CwRe37Ka.js`；`curl -I http://127.0.0.1:5174/miniapp/` 返回 200。
- 未完成 / 不要碰：抽卡与抽卡动画按辛玥要求先不动；奖励掉落 roll 目前只记录次数，还没接奖励池/物品掉落表；结算按钮当前默认按“标准通关 B 评级”发放，后续需要做成结算页让用户选择/确认结果或由 GM 触发。

当前状态（2026-05-17 文游结算核准页）：
- 已完成：把“进入结算”从前端硬编码 `standard_clear + B` 改成后端结算预览：新增 `/miniapp-api/wenyou/settlement/preview`，根据最近 GM 文本、玩家 HP/SAN/状态、线索数、回合数、威胁时钟等推断通关结果、评级分和评级；前端点“申请结算”先展示结算核准面板，可查看建议结果、评级分、分项、积分/EXP/奖励次数预估，也可手动调整结果/评级后再确认进入结算。`cmd_end` 不再使用前端默认 B 级，而是复用同一套 preview 结果发奖。
- 已验证：`.venv/bin/python -m py_compile storage/r2_store.py services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app` 与结算预览/确认 smoke 通过，最近 GM 写“任务完成/副本结束”时预览为 `standard_clear`、评级 B、评级分 61，确认后钱包 100 -> 220；`rg` 确认源码里无前端硬编码 `standard_clear + B`；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BwHO6XdB.js`、`miniapp_static/assets/index-CwKmZp6-.css`、`miniapp_static/assets/index-DHfIexEZ.js`；`git diff --check` 通过（仅既有 CRLF warning）；`curl -I http://127.0.0.1:5174/miniapp/` 返回 200。
- 未完成 / 不要碰：抽卡与抽卡动画继续不动；结算奖励 roll 仍只记录次数，尚未接真实掉落表；结算结果目前是规则引擎根据结构化记录 + 最近 GM 文本估算，不是独立二阶段 GM 复核调用。

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

当前状态（2026-05-16 续2）：
- 已完成：继续拆 `routes/chat.py`，把隐藏 sidecar 处理移到 `services/chat_sidecars.py`，把 HTML preview / SumiTalk 卡片补全移到 `services/chat_response_enrichers.py`，把 tool 调用结果拼接、tool trace 收集和 SSE 小工具移到 `services/chat_tool_helpers.py`；`routes/chat.py` 约 1645 行。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/chat_sidecars.py services/chat_response_enrichers.py services/chat_tool_helpers.py services/chat_content.py services/prompt_cache_debug.py services/reasoning_utils.py services/entry_style_prompt.py services/upstream_policy.py`、新服务 smoke check、`routes.chat` import check、`git diff --check` 均通过。
- 未完成 / 不要碰：`app.py`、`config.py`、`connectors/qq_onebot/src/main.js`、`routes/miniapp/wenyou.py`、`services/telegram_bot.py`、`services/wenyou_service.py`、小爱/音乐相关文件、共读文档、`miniapp_static/assets/*` 仍是本地已有改动或半成品；继续拆分可优先看 `routes/chat.py` 的 stream/non-stream 主流程，或转拆 `storage/r2_store.py`。

当前状态（2026-05-16 续3）：
- 已完成：继续拆 `routes/chat.py`，把 tool 续轮重试判断/补问注入补进 `services/chat_tool_helpers.py`，把 last user 提取、RikkaHub 幽灵 1 保护、最近入口记录移到 `services/chat_request_helpers.py`，把非流式归档后台任务和共读原文存档裁剪移到 `services/chat_archive_helpers.py`；`routes/chat.py` 约 1357 行。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/chat_tool_helpers.py services/chat_request_helpers.py services/chat_archive_helpers.py services/chat_sidecars.py services/chat_response_enrichers.py services/chat_content.py services/prompt_cache_debug.py services/reasoning_utils.py services/entry_style_prompt.py services/upstream_policy.py`、新 helper smoke check、`routes.chat` import check、`git diff --check` 均通过。
- 未完成 / 不要碰：`app.py`、`config.py`、`connectors/qq_onebot/src/main.js`、`routes/miniapp/wenyou.py`、`services/telegram_bot.py`、`services/wenyou_service.py`、小爱/音乐相关文件、共读文档、`miniapp_static/assets/*` 仍是本地已有改动或半成品；继续拆分可优先看 `routes/chat.py` 剩余 stream/non-stream 主流程，或转拆 `storage/r2_store.py`。

当前状态（2026-05-16 续4）：
- 已完成：继续拆 `routes/chat.py`，把入口 prompt 注入集中到 `services/chat_prompt_injections.py`：入口风格、语音通话台词、followup 静态规则、渠道 NSFW 和禁言模式；路由侧只保留请求 header 判断和调用顺序。`routes/chat.py` 约 1204 行。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/chat_prompt_injections.py services/chat_tool_helpers.py services/chat_request_helpers.py services/chat_archive_helpers.py services/chat_sidecars.py services/chat_response_enrichers.py services/chat_content.py services/prompt_cache_debug.py services/reasoning_utils.py services/entry_style_prompt.py services/upstream_policy.py`、prompt/helper smoke check、`routes.chat` import check、`git diff --check` 均通过。
- 未完成 / 不要碰：`app.py`、`config.py`、`connectors/qq_onebot/src/main.js`、`routes/miniapp/wenyou.py`、`services/telegram_bot.py`、`services/wenyou_service.py`、小爱/音乐相关文件、共读文档、`miniapp_static/assets/*` 仍是本地已有改动或半成品；下一步优先拆 `routes/chat.py` 的 stream/non-stream 主流程，或转拆 `storage/r2_store.py`。

当前状态（2026-05-17 文游规则草案）：
- 已完成：新增并继续补全 `docs/wenyou_rules.md`，把文游开源版规则整理成后端无关草案，包含任务者总数 2-13、玩家人数不固定、任务者 NPC 是非真人的其他任务者玩家、默认不能直接致死但可阴人、状态机、纯功能区 hub、公开/隐藏信息、副本蓝图（主线/支线/隐藏结局/线索图/NPC 弧线/威胁时钟/硬约束）、核心数值公式、伤害/精神判定、死亡走债务不默认删档、复活债务偿还和强制惩罚副本队列、属性点分配 UI/后端流程、阶位晋升条件/消耗/阻断、S 级封印体、血统/能力完整结算表、固定装备槽位、防具饰品基准、武器数值公式/模板/耐久/升级锻造/维修、出售回收/拆解流程、系统商店、道具规则表结算、100 积分/抽与 100 抽随机传说大保底、基础通关保底积分 + 剧情探索/隐藏支线/隐藏结局/特殊成就评级叠加（含具体百分比与叠加上限）、失败不发积分且通过复活/债务/装备损耗形成成本、奖励稀有度和类别掉落表、`state_patch` 边界；当前项目先按此实现测试，稳定后 copy 新仓库开源。
- 已验证：本轮为文档改动，已检查文档结构、索引和 Markdown 栅栏；未运行代码测试。
- 未完成 / 不要碰：尚未改 `routes/miniapp/wenyou.py`、`services/wenyou_service.py` 或 `miniapp/src/ui/tabs/WenyouTab.tsx`；现有文游实现仍可能固定 2 玩家 + 4 NPC，且属性点分配、晋升、血统/能力/武器数值、装备耐久/锻造/回收拆解、道具表结算、复活债务惩罚副本、奖励掉落表都还只是文档规则，后续要另起实现任务迁入后端 ruleset 和 UI。

当前状态（2026-05-17 文游命运裂隙 UI）：
- 已完成：`miniapp/src/ui/tabs/WenyouTab.tsx` 新增“命运裂隙”一级入口和前端抽卡演示流程，右上角裂隙按钮可进入，支持单抽/十连、100/1000 积分本地预览扣除、十连 C+ 兜底、裂隙展开动画、卡背结果区、逐张/批量显影和确认返回；`miniapp/src/styles.css` 参照下载 UI 合集的赛博黑白/故障/扫描线/翻牌风格重做视觉，并修正十连结果区与底部操作按钮重叠问题。
- 已验证：`npm -C miniapp run build` 通过；本地 `http://127.0.0.1:5174/miniapp/` 打开后已点击进入“命运裂隙”、执行十连、`REVEAL DATA` 显影、`CONFIRM SYNCHRONY` 返回；本地 Vite 没接 Flask 时商店/会话接口会 404，但裂隙 UI 使用前端预览积分可继续看动画。
- 未完成 / 不要碰：命运裂隙目前只是前端 UI/动画与本地结果演示，尚未接后端真实扣积分、抽卡记录、道具入背包、概率审计和 100 抽大保底持久化；后续接后端时继续限定文游相关文件，不要动 QQ connector、小爱、共读和其他半成品。

当前状态（2026-05-17 文游命运裂隙后端/对象背包）：
- 已完成：`services/wenyou_service.py` 新增对象化背包兼容层，旧字符串背包会读成 `{uid,id,name,kind,category,rarity,quantity,source}` 对象；钱包开始保存长期 `inventory` 和每池 `gacha.pools` 保底计数。新增 `roll_gacha` 后端规则：仅 `hub/settlement` 可抽，单抽 100/十连 1000，积分不足直接拒绝，按混合池概率抽取，10/30/100 抽保底分别记录，A/S 高阶物按当前阶位封印，重复武器/能力/血统转碎片。`routes/miniapp/wenyou.py` 新增 `/miniapp-api/wenyou/gacha/roll`；`miniapp/src/ui/tabs/WenyouTab.tsx` 的命运裂隙改为调用后端，不再使用前端预览积分凭空抽。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py storage/r2_store.py` 通过；`.venv/bin/python - <<'PY' import app` 通过；内存 monkeypatch 烟测覆盖 0 积分不能抽、副本中不能抽、结算阶段扣 100 并写对象背包；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BanpyNQn.js`、`miniapp_static/assets/index-Cf0MmulS.js`、`miniapp_static/assets/index-BVLf9Srz.css`，并检查当前 `index` 引用的静态 chunk 均存在。
- 未完成 / 不要碰：道具 `use_item` 仍只是把“使用道具”交给 GM，不按道具规则表扣次数/结算效果；属性点分配、阶位晋升、装备槽、武器耐久/锻造/维修/出售/拆解、复活债务和奖励掉落表仍未完整接入。继续限定文游相关文件，不要动 QQ connector、小爱、共读和其它半成品。

当前状态（2026-05-17 文游候选扩展并行化）：
- 已完成：候选副本点击进入不再同步等待一个巨大 DS 请求。`/miniapp-api/wenyou/story` 收到 candidate 后创建后台扩展任务并返回 `expanding/job_id`；新增 `/miniapp-api/wenyou/story-job/<job_id>` 供前端轮询。后台扩展先让 DS 生成自然语言核心短稿，再并行生成自然语言蓝图短稿和开场正文；后端用候选 seed + 文本块组装完整 framework，不再要求 DS 输出严格 JSON，避免单个超大 JSON 请求拖到网关/浏览器超时或因解析失败中断；失败时返回明确子任务错误，不造本地假副本。
- 已验证：`python3 -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py` 通过；`.venv/bin/python - <<'PY' import app` 通过；monkeypatch 烟测 `generate_framework_from_candidate` 可用文本 core/blueprint/opening 组装 framework；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BSKgBGT4.js`、`miniapp_static/assets/index-C6dONsQ4.js`、`miniapp_static/assets/index-BVLf9Srz.css`。
- 未完成 / 不要碰：随机开局和手写自定义关键词仍是同步完整框架生成；本次只修“大厅候选 -> 扩展完整副本”的超时路径。继续限定文游相关文件，不要动 QQ connector、小爱、共读和其它半成品。

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
   - 已拆：入口 prompt 注入（入口风格调用、voice/followup/NSFW/禁言）移到 `services/chat_prompt_injections.py`
   - 已拆：上游选择、active 模型策略、OpenRouter 请求策略移到 `services/upstream_policy.py`
   - 已拆：prompt-cache / cache debug 移到 `services/prompt_cache_debug.py`
   - 已拆：reasoning/thinking/SSE message 解析移到 `services/reasoning_utils.py`
   - 已拆：消息内容字符统计移到 `services/chat_content.py`
   - 已拆：隐藏 sidecar 写入移到 `services/chat_sidecars.py`
   - 已拆：HTML preview / SumiTalk 卡片补全移到 `services/chat_response_enrichers.py`
   - 已拆：tool 调用结果拼接、tool trace、SSE 小工具移到 `services/chat_tool_helpers.py`
   - 已拆：tool 续轮重试判断/补问注入补进 `services/chat_tool_helpers.py`
   - 已拆：last user 提取、RikkaHub 幽灵 1 保护、最近入口记录移到 `services/chat_request_helpers.py`
   - 已拆：非流式归档后台任务和共读原文存档裁剪移到 `services/chat_archive_helpers.py`
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
