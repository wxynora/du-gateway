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
| 对话回复统一超时 | `config.py`、`routes/chat.py`、`services/telegram_bot.py`、`services/telegram_proactive.py`、`services/conversation_followup.py`、`services/du_daily.py`、`services/voice_call_pipeline.py`、`routes/xiaoai_api.py`、`scripts/start_gateway_prod.sh` | 所有等模型/网关回复的对话入口默认 15 分钟；工具短请求、搜索、天气、STT 等仍保留各自短超时 |
| 主聊天策略 | `services/entry_style_prompt.py`、`services/chat_prompt_injections.py`、`services/upstream_policy.py` | 入口风格 system、voice/followup/NSFW/禁言注入、active upstream 选择、OpenRouter/CPA/Claude OAuth 请求策略 |
| 主聊天诊断/思维链 | `services/prompt_cache_debug.py`、`services/reasoning_utils.py`、`services/chat_content.py`、`routes/miniapp/reasoning.py` | prompt/cache debug、reasoning/thinking 剥离、SSE message 解析、消息字符统计；MiniApp 思维链页的 Prompt Cache 计费估算在 `routes/miniapp/reasoning.py` |
| 主聊天响应辅助 | `services/chat_sidecars.py`、`services/chat_response_enrichers.py`、`services/chat_tool_helpers.py`、`services/chat_request_helpers.py`、`services/chat_archive_helpers.py` | 隐藏 sidecar 写入、HTML 预览/SumiTalk 卡片补全、tool 重试/SSE 小工具、入口状态/误触保护、归档后台辅助 |
| 注入管道 | `pipeline/pipeline.py` | core prompt、summary、last4、sense、dynamic memory、tools 注入 |
| MiniApp API | `routes/miniapp_api.py` | SumiTalk、设备、思维链、设置、贴纸、日历、上游切换等接口 |
| MiniApp 前端主壳 | `miniapp/src/ui/App.tsx` | 首页、聊天页、设置页、消息渲染、SumiTalk job |
| SumiTalk 本地聊天存储 | `miniapp/src/ui/storage/chatHistoryDb.ts`、`miniapp/src/ui/chat/*`、`miniapp/src/plugins/sumi-chat-store.ts`、`miniapp/android/app/src/main/java/com/sumitalk/app/SumiChatStorePlugin.java`、`miniapp/android/app/src/main/java/com/sumitalk/app/chat/*` | Android 原生 SQLite ChatStore、本地历史读写抽象和 outbox 恢复 |
| SumiTalk 聊天后台队列 | `routes/miniapp/sumitalk_chat_jobs.py`、`services/sumitalk_chat_queue.py`、`scripts/run_sumitalk_chat_worker.py` | App 发消息只入队和轮询 job；独立 worker 消费后调用统一 `/v1/chat/completions`，避免 gunicorn 请求生命周期杀掉长回复 |
| MiniApp 分页 | `miniapp/src/ui/tabs/*` | 日志、思维链、上游、日历、贴纸、记忆调试等子页 |
| MiniApp 小家 | `miniapp/src/ui/tabs/PixelHomeTab.tsx`、`services/pixel_home.py`、`storage/pixel_home_store.py`、`routes/miniapp/dashboard.py`、`miniapp/src/assets/life-home-*.png` | 「小家」生活感页面：按 `ui合集/赛博小家` 的单列布局和字体组织，实际小屋图、点击才出现的小点、赛博小家状态注入与事件唤醒 |
| 文游规则入口 | `docs/wenyou_rules.md`、`docs/wenyou/*.md` | 开源版文游规则入口与拆分文档：核心循环、运行时状态缓存、副本生成、怪物系统、数值成长、奖励经济、后端契约 |
| 文游物品/核心能力系统 | `docs/wenyou/item_ability_system.md`、`docs/wenyou/item_catalog_draft_d.md`、`docs/wenyou/item_catalog_draft_c.md`、`docs/wenyou/item_catalog_draft_b.md`、`docs/wenyou/item_catalog_draft_a.md`、`docs/wenyou/item_catalog_draft_s.md`、`content/default/items.json`、`content/default/item_catalog.sql`、`content/default/abilities.json`、`schemas/item.schema.json`、`schemas/ability.schema.json`、`content/default/reward_tables.json` | 通用商店/抽卡/奖励道具目录、用途分类、物品形态、时代标签、耐久/次数、背包使用/出售、商店、抽卡、核心能力原型和奖励表；不再保留独立高阶兑换入口、装备栏、穿戴、锻造、拆解、多能力槽或复杂身体路线；D/C/B/A/S 道具已从 Markdown 审校源表生成结构化内容表和 SQL seed；副本专属可带出物先归内容包/副本奖励表，不默认进通用目录；D 级副本常规产出最多 C 级 |
| 文游运行时存储 | `storage/wenyou_sqlite_store.py`、`storage/r2_store.py` | 文游当前存档、长期钱包、候选池、连续性卡片和归档列表以 `data/wenyou.sqlite3` 为主；旧 R2 key 只在 SQLite 无记录时回填，`WENYOU_R2_BACKUP_ENABLED=1` 才双写备份 |
| R2 存储 | `storage/r2_client.py`、`storage/r2_conversation_store.py`、`storage/r2_context_store.py`、`storage/r2_wenyou_store.py`、`storage/r2_sticker_store.py`、`storage/r2_media_store.py`、`storage/r2_miniapp_store.py`、`storage/r2_device_reporting_store.py`、`storage/r2_studyroom_store.py`、`storage/r2_store.py` | `r2_client.py` 负责 S3 客户端和 JSON 读写；conversation compact/SQLite 热读、summary/latest4/近期图片描述上下文、文游、贴纸、媒体、MiniApp 资产/小组件、设备上报和 StudyRoom 已迁入领域模块，`r2_store.py` 保留兼容导出并继续承载主动联系、动态记忆、Prompt 等 API |
| 上游配置 | `storage/upstream_store.py` | active upstream、model cache、models 探测 |
| 主动消息 | `services/telegram_proactive.py` | 概率主动、主动决策、通道投递、trigger tick |
| 唤醒/续话 | `services/conversation_followup.py`、`services/reply_channel_context.py` | 事件唤醒、弹窗回执、查岗回应、延迟续话、最近真实聊天入口解析 |
| Chat / 共同游戏活动时间 | `services/user_activity_context.py`、`pipeline/pipeline.py`、`routes/miniapp/game_tools.py`、`storage/r2_store.py` | 保留 `last_user_reply_at` chat 时间；显式记录小玥与渡共同玩的具体游戏；两类真实互动都刷新 R2 统一唤醒时钟，渡自己玩的游戏不计入 |
| 设备工具 | `services/device_action_tools.py` | 弹窗、截图、系统闹钟等工具执行和卡片 |
| 论坛 MCP 工具 | `services/mcp_forum_tools.py`、`services/forum_mcp_client.py` | 论坛高层工具、`cli/get_guide` 映射、外部 SSE MCP 调用 |
| 随机冲浪工具 | `services/du_surf.py`、`services/gateway_tools.py`、`services/chat_tools.py` | `du_surf` 网关工具，按兴趣池/时间段抽话题，复用 Tavily 轻搜摘要，清洗成可聊卡片；不作为 `web_search` 精确事实查询 |
| 设备状态注入 | `storage/sense_store.py`、`services/sense_context.py` | 电量、亮屏、前台 app、位置、睡眠分段累计等 sense 存储与注入 |
| 主动触发规则 | `services/proactive_trigger_engine.py` | 睡眠、亮屏、使用时长等硬触发 |
| Telegram Bot | `routes/telegram_webhook.py`、`services/telegram_update_queue.py`、`scripts/run_telegram_webhook_worker.py`、`services/telegram_bot.py` | Webhook 入队、持久队列、独立 worker 消费、TG 风格 system/上下文/发送，图片与 md/txt 文档附件处理 |
| 小爱音箱 / MiGPT Next / mijiaAPI | `routes/xiaoai_api.py`、`routes/miniapp/xiaoai.py`、`storage/xiaoai_store.py`、`services/xiaoai_audio_store.py`、`services/gateway_tools.py`、`services/entry_style_prompt.py`、`scripts/test_xiaoai_mijia.py`、`miniapp/src/ui/tabs/XiaoAISettingsTab.tsx`、`connectors/xiaoai_migpt/`、`docs/小爱音箱-MiGPT-Next-接入渡方案.md` | 小爱专用 `/api/xiaoai/message` 入口、`xiaoai_speak` 外放工具、`xiaoai_run_command` mijiaAPI 家居控制工具、`mijia_lamp_get/set` 台灯结构化工具、台灯实测脚本、播放队列、强制 `<voice>` 风格、MiniMax 音频 URL 临时托管、App 工具页、Mac Docker MiGPT runner、接入方案 |
| Claude OAuth proxy | `scripts/claude_oauth_proxy.js`、`docs/claude_proxy_new_vps_migration_plan.md` | 自用 Claude 反代、thinking/cache/tool 格式转换；旧 VPS 继续用 `127.0.0.1:8082`，新 VPS 单独承载 Claude Code + OAuth proxy 的迁移手册 |
| 植物大战僵尸模仿者版原型 | `du_imitator_pvz/`、`scripts/test_imitator_pvz_*.py`、`scripts/sim_imitator_pvz_balance.py`、`docs/植物大战僵尸模仿者版.md` | 纯 Python headless 随机模仿者塔防模拟器：P0/P2 合同、随机池、植物/僵尸行为、玩家回合复盘、v2 小工测试、铲子动作、僵王事件、主动重开、玩家棋盘文本视图 |
| 随机模仿者网关私有工具 | `services/game_tool_runtime.py`、`services/random_imitator_td_tool.py`、`routes/miniapp/game_tools.py`、`routes/chat.py`、`pipeline/pipeline.py`、`services/chat_tools.py`、`scripts/test_random_imitator_td_tool.py` | du-gateway 私有游戏工具接入：`random_imitator_td` 是首个注册游戏；Prompt 开关只固定注入工具，只有专用游戏标记或工具结果自带 `game_tool_loop` 才跳过动态记忆写入与 BODY delta |
| MiniApp 游戏大厅 / 涩涩走格棋 | `miniapp/src/ui/tabs/GamesHubTab.tsx`、`miniapp/src/ui/tabs/SeseBoardGameTab.tsx`、`routes/miniapp/game_tools.py`、`services/private_board_game.py`、`services/private_board_tool.py`、`services/game_tool_runtime.py`、`services/conversation_followup.py`、`routes/chat.py`、`scripts/test_private_board_game.py` | 「日常 > 游戏」入口，文游显示为「无限流」；`private_board` 走走格棋后端和前端棋盘。小玥通过前端按钮/输入参与，渡通过自然语言精确首行指令参与；右上角局内聊天只发本次消息，不自带局内历史；局内回复不外发主聊天但压缩归档进同一个 `tg_*` window 的 last4；同步成功后按同步时间刷新全局最近活动时钟 |
| 囚禁模拟器 | `docs/captivity-simulator-plan.md`、`services/captivity_simulator_game.py`、`routes/miniapp/game_tools.py`、`services/conversation_followup.py`、`routes/chat.py`、`scripts/test_captivity_simulator_game.py`、`services/game_tool_runtime.py`、`miniapp/src/ui/tabs/CaptivitySimulatorGameTab.tsx`、`miniapp/src/ui/tabs/GamesHubTab.tsx`、`miniapp/src/ui/AppShell.tsx` | 30 天本地规则模拟器：双路线、三段白天行动、过程/心情、夜间自由行动与监控、逃跑诱导及抓回后规则、物品/道具、事件回顾和固定结局；`/game-tools/captivity_simulator/sync-du` 以 dynamic system 注入当轮上下文，跳过动态记忆和 BODY delta，完整事件正文只留游戏存档 |

当前状态（2026-07-13 chat / 共同游戏活动时间拆分，已部署）：
- 已完成：R2 `last_user_activity_at` 继续作为统一唤醒时钟，普通 chat 和小玥参与的共同游戏都会刷新；现有唤醒、睡眠、PixelHome 等读取接口和调度算法不改。
- 已完成：现有 `data/last_user_reply.json` 兼容保留 `last_user_reply_at`，新增 `last_shared_game_activity`；提示词比较两者，chat 分支逐字保留 `[😭X后老婆终于回我了]`，游戏分支写 `老婆 X 分钟前和我在玩<具体游戏名>。`。
- 已完成：共同游戏采用后端显式白名单，目前只有 `private_board=涩涩走格棋`、`captivity_simulator=囚禁模拟器`；`random_imitator_td` / 植物大战丧尸随机版和未知游戏 fail closed，不写本地记录或 R2 统一时钟。
- 已完成：走格棋每次通过基本校验的 `/sync-du` 在调用渡前记一次；囚禁模拟器仍只认局内 chat 或 `user_initiated=true` 的操作；渡的自动 follow-up、状态轮询、游戏大厅预览和重复自动结局通知不记。
- 已完成：SumiTalk / QQ / 微信等共享 `tg_*` 窗口复用现有跨平台真实输入判定补写 chat 时间；带 follow-up 标记的游戏/后端生成不会冒充 chat。主动唤醒描述会按最新类型区分“明确回复”和“和我在玩具体游戏”，调度仍只看统一时钟。
- 验证：纯本地临时文件和 monkeypatch R2/上游下，`scripts/test_user_activity_context.py`、`scripts/test_private_board_game.py`、`scripts/test_captivity_simulator_game.py` 全部通过；相关 `py_compile`、`import app`、`git diff --check` 通过。
- 已部署：功能提交 `4a3ea528` 已推送到 `origin/main`，主网关 `/root/du-gateway` fast-forward 后完成服务器端 `py_compile` / `import app`；`du-gateway.service`、`du-sumitalk-chat-worker.service`、`du-telegram-proactive.service` 已重启为 active/running。本机与公网 `/health`、`/miniapp/` 均返回 200，重启后 warning 级日志为空。
- 当前边界：主工作区已有脏改、线上游戏存档和 R2 活动时间均未手动修改；部署后由下一次真实 chat 或共同游戏同步自然写入新结构。

当前状态（2026-07-11 囚禁模拟器首个完整部署版）：
- 已完成：规则引擎、双路线 MiniApp、行动/过程/夜间/监控/逃跑/抓回/物品/结局闭环和事件回顾已整合；开发预览只使用本地假数据。
- 已完成：用户触发的 `state_update`、局内聊天和首次结局同步只有在 `/sync-du` 首次唤醒成功后才刷新 `last_user_activity_at`；失败同步、状态刷新、本地存档和重复结局通知不刷新。
- 边界：囚禁模拟器同步使用当轮 dynamic system，跳过动态记忆写入和 post-archive BODY delta；聊天归档只留结构化摘要，完整过程正文只保留在游戏存档。
- 验证入口：`.venv/bin/python scripts/test_captivity_simulator_game.py`、`.venv/bin/python scripts/test_private_board_game.py`、`cd miniapp && npx tsc --noEmit --pretty false && npm run build`、后端 `py_compile` / `import app` 和 `git diff --check`。

当前状态（2026-07-07 涩涩走格棋同步时间与打回说明修正）：
- 已完成：`/miniapp-api/game-tools/private_board/sync-du` 成功同步后不再按 `window_id/target` 判断“主 TG 窗口”，而是直接用本次 `synced_at` 写入 `last_user_activity_at` 全局活动时钟；该时钟供主动/防打扰链路判断最近真实活动。
- 已完成：`state_update` 同步现在会把调用方传入的 `message` 拼进正文的“本次说明”，再附上“当前棋局”；小玥打回渡的惩罚任务时，`小玥打回了你的惩罚任务：反馈` 不会再被同步路由丢掉。
- 已同步：开源版 `game-box/games/sese-board-game/frontend/SeseBoardGame.tsx` 的 `sendToAssistant` payload 会把 `context.message` 拼进 `payload.ai_text` 的“本次说明”，并尽量连带当前棋局文本；`frontend/README.md` 已提醒宿主只发 `payload.ai_text`，不要只发 `state`。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/game_tools.py scripts/test_private_board_game.py`、`.venv/bin/python scripts/test_private_board_game.py`、开源版 `python3 -m py_compile sese_board_game/engine.py preview_server.py && python3 tests/test_engine.py`、`SESE_BOARD_NODE_MODULES=/Users/doraemon/Downloads/du-gateway/miniapp/node_modules .../vite build --config vite.config.mjs`、`git diff --check` 均通过。
- 边界：本轮没有手改线上 R2 时间或棋局存档；线上生效靠正常 push/pull/restart，之后下一次走格棋同步会按新逻辑刷新全局活动时间。

当前状态（2026-07-06 涩涩走格棋同步链路修正）：
- 已完成：前端同步链路改为按“当前该谁操作”触发。小玥落格后如果生成小玥自己的 choice/review/duel pending，不再立刻同步给渡；等小玥选择、提交、Pass 或出拳后再同步。若落格后本来就是等渡出题/选择/验收/出拳，才立即同步给渡。
- 已完成：渡回复 `【掷骰】` 后执行他的 roll，如果新状态仍是渡回合或生成渡自己的 pending，会继续用 `state_update` 同步给渡；渡处理完 choice/review/Pass 后若因停步等规则又轮到渡，也会继续同步，避免停在“等待渡选择/行动”。
- 已完成：`routes/miniapp/game_tools.py` 新增 `state_update` 同步文案，并补上 `review/questioning` 等渡出题、duel 等渡出拳的精确首行指令提示，避免把状态同步误写成“小玥刚掷骰”。
- 已完成：局内聊天改为浏览器本地持久化，刷新页面不会丢；成功开下一局时重置为初始提示。当前是同设备同浏览器保留，不写入服务器存档。
- 已完成：局内聊天输入和惩罚 textarea 不再被后台同步/动画加载态锁死；自动同步不再刷“已同步/正在回复”聊天泡泡。普通局内聊天不套 `【描述】`；真心话用 `【真心话出题：...】` / `【真心话回答：...】`，验收按选项写 `【通过：反馈内容】` / `【打回：反馈内容】`，只有 `反向诱惑` / `全部暴露！` / `羞耻台词大放送` / `自慰陈述` 这四个长篇提交任务直接用 `【描述：...】`；小玥点“通过”只本地结算，不单独同步给渡，通过结果和反馈会等小玥下一次掷骰同步时顺带说明；渡验收小玥任务时，`【通过：反馈内容】` 后必须同条带 `【掷骰】`，前端会一次吃掉通过和掷骰并把反馈显示在任务弹窗。
- 已修复：渡提交长篇任务时如果回复以 `【描述：` 开头但正文跨多行、闭合 `】` 不在首行，前端现在仍会识别为 `submit`；同套跨行解析也覆盖 `【真心话出题：...】` / `【真心话回答：...】`。
- 已修复：状态栏语料只保留道具惩罚和限制；移除旧的 `task` 状态槽与“新增任务状态”选择分支，读档时会过滤历史 `slot=task`，不影响 `pending_event.task` 惩罚任务卡池。
- 已修复：涩涩走格棋同步给渡的每轮棋局内容现在以 `__dynamic__` system 进入动态区，不再把每轮变化的游戏 prompt 写进静态缓存前缀；同步成功后会刷新作为全局最近活动时钟使用的 `last_user_activity_at`，避免随机主动消息误判成“几小时前才回复”。
- 已同步：开源版 `/Users/doraemon/Downloads/game-box/games/sese-board-game/frontend/SeseBoardGame.tsx` 按同一规则更新，使用 `ai/player` 命名，不带私有路由和私有人设。
- 已验证：`cd miniapp && npx tsc --noEmit --pretty false`、`npm --prefix miniapp run build`、`python3 -m py_compile routes/miniapp/game_tools.py`、开源版 `python3 -m py_compile sese_board_game/engine.py preview_server.py && python3 tests/test_engine.py`、复用 `du-gateway/miniapp/node_modules` 的开源预览 `vite build` 均通过。
- 未完成 / 下次继续：本轮不会手改线上存档；如果要把当前线上局面从旧 pending 继续下去，部署后让新前端接管，或再明确指定人工选择哪个 pending 选项。

当前状态（2026-07-06 涩涩走格棋 Pass / 道具 / 棋盘密度修正）：
- 已完成：`services/private_board_game.py` 的 `pass` 命令现在会对无卡、不可跳过、已提交、已达本局跳过上限等失败情况返回 `ok=false`；前端 `SeseBoardGameTab.tsx` 遇到 `ok=false` 只提示失败，不再追加“已使用Pass卡”或同步给渡。渡在局内聊天发 `【Pass】` 也走同一失败判定。
- 已完成：道具惩罚随机池会优先避开当前玩家身上已有的同名道具；重复命中时不再堆出两条同名状态，支持档位的道具会升档，停步格命中已有道具时会延长行动限制。
- 已完成：36 格棋盘重新留出空格，移除导致拖局的双方回起点、对方回起点、全员后退等循环源；保留 27 格「重回起点」，奖励格仍为 5/22/32，提交类惩罚格仍为 4/11/20/26/33，选择惩罚格仍为 9/21/30。
- 已同步：开源版 `game-box/games/sese-board-game` 的引擎、前端失败处理和测试已按同一规则更新；开源预览 API `127.0.0.1:8766` 已重启，`127.0.0.1:5176` 页面确认有空格、Pass x0 时不显示 Pass 按钮。
- 已验证：`python3 -m py_compile services/private_board_game.py`、开源版 `python3 -m py_compile sese_board_game/engine.py && python3 tests/test_engine.py`、`npm --prefix miniapp run build` 通过；手动 smoke 覆盖私有版和开源版无 Pass 卡不能跳过、pending 不消失、手牌仍为 0、同名道具不重复。
- 未完成 / 下次继续：本轮没有 push、没有重启 du-gateway 主服务；`npm --prefix miniapp run build` 重建了 `miniapp_static` 哈希产物，提交前需要按发布策略一起处理或重新收束。

当前状态（2026-07-05 MiniApp 游戏大厅与涩涩走格棋）：
- 已完成：`GamesHubTab.tsx` 新增游戏大厅；文游入口改名「无限流」并移入「日常 > 游戏」；新增「涩涩走格棋」入口。
- 已完成：`services/private_board_game.py` 注册 `private_board`，支持 36 格走格棋、主题/主导方、状态/道具持续回合或时间、暂停行动、前进/后退/交换/解除/延长等格子事件；前端 `SeseBoardGameTab.tsx` 展示完整棋盘、棋子、骰子、移动动画、状态卡和右上角局内交流气泡。
- 已完成：小玥在前端掷骰后，页面会自动调用 `/miniapp-api/game-tools/private_board/sync-du`，把本次掷骰结果和当前棋局同步给渡；渡回复第一行只有精确 `【掷骰】` 才会触发他的行动，普通“掷骰子/我来投一下”只算聊天。
- 已完成：新增奖励/惩罚卡池：Pass卡、4 张提交验收类惩罚、8 张选择类惩罚；选择类支持新增状态、道具惩罚档位上调、退格和停步，档位上调只在当前玩家已有 `prop` 状态时可选，`锁精环` 不会随机给人类玩家。
- 已完成：前端不是壳；小玥通过界面按钮处理提交、通过、打回、选择惩罚、Pass卡、重开和停步回合。渡侧精确指令扩展为 `【掷骰】`、`【提交】`、`【通过：反馈内容】`、`【打回：反馈内容】`、`【选择：选项名】`、`【Pass】`，普通闲聊不触发棋局动作。
- 已完成：`services/private_board_tool.py` 提供 `private_board` OpenAI function schema 和 executor，复用 `execute_game_command()`；当前只作为规范工具适配和手动接入口，不主动污染日常聊天工具注入。
- 已完成：右上角局内聊天只发送本次 `message`，不再上传 `chat_messages` 或自带局内上下文；前后文依赖同一个 `tg_*` 窗口的正常 last4。`return_only=True` 只是不外发到 Telegram/主聊天界面，但 `_send_wakeup_event()` 仍带 `X-DU-FOLLOWUP-ARCHIVE: 1` 归档到同一窗口。
- 已完成：`routes/chat.py` 对 `X-DU-WAKEUP-KIND: private_board` 做专门压缩归档，last4 里写成 `[涩涩走格棋] 小玥在局内说...` 或 `小玥同步了掷骰结果...`，不会把整段系统 prompt 或棋局大 JSON 塞进近期上下文。
- 边界：游戏内同步请求带 `X-Force-Last4: 1`、`X-Skip-Dynamic-Memory: 1`、`X-Skip-Post-Archive-Dynamic-Memory: 1`；不带 `X-Skip-Post-Archive-Body-Delta`。也就是读取正常注入和 last4，跳过动态记忆召回/写入，不跳过 BODY delta。
- 已验证：`.venv/bin/python -m py_compile services/private_board_game.py services/private_board_tool.py services/chat_tools.py services/game_tool_runtime.py routes/miniapp/game_tools.py scripts/test_private_board_game.py`、`.venv/bin/python scripts/test_private_board_game.py`、`npm --prefix miniapp run build` 均通过；2026-07-05 复跑 `cd miniapp && npx tsc --noEmit --pretty false` 已通过。浏览器只读检查确认 5174 页面游戏大厅/走格棋能渲染，但 5174 纯 Vite dev server 无 `/miniapp-api` 代理，接口检查以 Flask/game runtime 测试为准。

当前状态（2026-07-04 思维链 Prompt Cache 计费估算）：
- 已完成：`routes/miniapp/reasoning.py` 的 Claude cost 估算改为按每条 `cache_debug` 的实际模型拆分计费，再汇总到思维链日志页；返回中保留 `pricing_per_million`、`total_usd` 等旧字段，同时新增 `pricing_per_model` 和 `cost_lines` 方便排查混合模型。
- 已完成：`claude-fable-5` / 含 `fable` 的模型使用 Fable 价格：输入 `$10/M`、输出 `$50/M`；Prompt Cache TTL 仍标记为 `1h`，因此 cache write 按输入价 2x、cache read 按输入价 0.1x 估算。
- 已修复：Claude OAuth proxy 的 OpenAI 兼容 `prompt_tokens` 是 Anthropic `input_tokens`，不包含 `cache_read_input_tokens` / `cache_creation_input_tokens`；当 `prompt_tokens < cache_read + cache_create` 时，不能再扣减缓存，否则未缓存输入会被算成 0。Cloudflare Anthropic 兼容层的 `prompt_tokens` 是 total prompt，仍按 `prompt_tokens - cache_read - cache_create` 算未缓存输入。
- 已修复：MiniApp 思维链页 Prompt Cache 折叠摘要改读后端汇总的 `cost.input_tokens/cache_*_tokens/output_tokens`，避免多次请求时摘要只显示最后一次 usage，而 cost 显示总账。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/reasoning.py` 通过；本地 smoke 覆盖普通 Claude 与 Fable 混合计费，1M Fable input/cache write/cache read/output 分别算 `$10/$20/$1/$50`；用线上最新 Fable usage 样本回归，`prompt_tokens=3955/cache_create=1022/cache_read=26990/output=317` 估算为 `$0.10283`；`npm run build` 通过。
- 未完成 / 下次继续：本轮没有改前端样式、聊天请求、缓存断点或部署；线上需要随下一次 push/restart 生效。

当前状态（2026-07-03 对话回复统一超时）：
- 已完成：新增 `CHAT_RESPONSE_TIMEOUT_SECONDS=900`，并让 `STREAM_TIMEOUT_SECONDS`、Telegram bot 调网关等待、XiaoAI、语音通话、主动消息/主动决策、日维护等对话链路默认跟随 15 分钟。
- 已完成：`scripts/start_gateway_prod.sh` 的 gunicorn `GATEWAY_TIMEOUT` 默认提高到 960 秒，给 15 分钟上游等待留出归档/收尾余量，避免刚返回就被 worker timeout 杀掉。
- 边界：web search、天气、STT、TTS、mijiaAPI、MCP 等工具型短请求没有改成 15 分钟；这次只统一“等模型/网关回复”的入口。
- 已验证：`.venv/bin/python -m py_compile config.py routes/chat.py routes/xiaoai_api.py routes/miniapp/game_tools.py routes/miniapp_api.py services/telegram_bot.py services/telegram_proactive.py services/conversation_followup.py services/du_daily.py services/voice_call_pipeline.py services/random_imitator_td_tool.py services/game_tool_runtime.py storage/random_imitator_td_mode_store.py scripts/test_random_imitator_td_tool.py scripts/test_imitator_pvz_cmd.py`、`.venv/bin/python scripts/test_random_imitator_td_tool.py && .venv/bin/python scripts/test_imitator_pvz_cmd.py`、`.venv/bin/python -c "import app; from config import CHAT_RESPONSE_TIMEOUT_SECONDS, STREAM_TIMEOUT_SECONDS, TELEGRAM_GATEWAY_CHAT_TIMEOUT_SECONDS; print(CHAT_RESPONSE_TIMEOUT_SECONDS, STREAM_TIMEOUT_SECONDS, TELEGRAM_GATEWAY_CHAT_TIMEOUT_SECONDS)"` 均通过，输出为 `900 900 900`。

当前状态（2026-07-03 random_imitator_td 网关私有工具接入）：
- 已完成：新增私有聊天工具 `random_imitator_td`，执行走 `services/random_imitator_td_tool.py`，底层调用 `du_imitator_pvz.engine.cmd(command, save_path=...)`；私用版固定单存档 `data/random_imitator_td/default.json`，工具 schema 不暴露 `save_id`，即使旧参数传入也会忽略。
- 已完成：新增防沉迷暂停机制。每个存档第 5/10/15… 次玩家决策会先正常执行、推进并保存；同一工具循环里下一次本该继续推进的游戏工具结果，会改为返回 `防沉迷暂停: 由于防沉迷机制，已完成第N回合后暂时中止游戏回合...`，不推进新动作、不结算输赢；暂停只消费一次，之后可继续玩。网关工具结果同步带 `checkpoint: true`，方便前缀或客户端停止继续游戏工具循环。
- 已完成：打开/继续入口收束为读档优先。`打开`、`继续`、`open`、`resume`、`look` 和命令行无参数启动都会优先读取当前存档；只有显式 `new_game` 才重开。网关工具空 `command` 也按 `打开` 处理，避免客户端下一次进入时误开新局。
- 已完成：工具说明已明确本工具固定使用单存档，不要尝试切换存档，避免模型手滑堆出零散存档。
- 已完成：新增统一游戏入口 `services/game_tool_runtime.py` 与 `/miniapp-api/game-tools/<game_id>`。`random_imitator_td` 现在是首个注册游戏，工具结果固定带 `game_tool_loop: true`、`skip_dynamic_memory_write: true`、`skip_body_delta: true`；后续新游戏接入时注册新的 `game_id`、执行器、命令清单和存档根目录即可复用同一套入口与副作用跳过标记。
- 已完成：`routes/chat.py` 新增游戏工具循环标记：请求头 `X-DU-Game-Tool-Loop: 1` 或 `X-Random-Imitator-TD: 1`、`window_id/reply_target` 以 `random-imitator-td` 开头时，会跳过动态记忆召回、归档后动态记忆写入、BODY delta，并跳过小家/用户状态文本推断。
- 已完成：Prompt 管理新增「植物大战丧尸模式」后端开关。该开关只固定注入 `random_imitator_td` 工具，不让 `_is_game_tool_loop_request()` 变真，也不提前跳过动态记忆召回；跳过只发生在专用游戏标记命中，或本轮实际调用了 `random_imitator_td` 工具之后。
- 已完成：归档保险层已补齐。即使客户端忘带游戏请求标记，只要本轮工具结果带 `game_tool_loop`，流式和非流式归档后的动态记忆写入与 BODY delta 都会强制跳过；旧的 `random_imitator_td` 工具名仍保留兜底兼容。
- 已修复：防沉迷 checkpoint 不直接吐工具文本，而是按普通工具循环结束方式再请求一次上游；这次请求保留工具结果上下文，不改 `tool_choice`、不注入额外系统提示，只在 checkpoint 工具结果里带 `checkpoint_instruction`：由于防沉迷机制，暂时中止游戏回合，不要继续使用游戏工具，正常回复信息。普通非 checkpoint 游戏回合不走这个分支。
- 已修复：checkpoint 收口请求继续保留工具列表和 `tool_choice`，避免破坏 prompt cache；如果上游无视 `checkpoint_instruction` 在收口阶段仍返回 `random_imitator_td` 工具调用，后端会阻止执行并强制转成暂停回复。
- 已修复：`random_imitator_td` 网关包装层已收束为固定单存档 `default.json`。旧 `_active_save.json` 只作为一次性迁移来源：如果服务器上只有旧活跃存档，会先复制到 `default.json`；之后不再写活跃指针，也不允许按 `save_id` 切档。
- 已修复：局面胜利后，下一次 `打开` / `继续` 会准备下一关并重新选卡；失败或玩家主动 `结束本局` 后仍回到 lv1 新局准备。玩家用 `note ...` 写下的复盘会跨局保留，不跟着存档覆盖清空。
- 已修复：本局到达结局或玩家主动 `结束本局` 后，工具结果同样标记 `checkpoint: true`、`checkpoint_reason: game_over`，并提示“不要继续使用游戏工具，也不要立刻 new_game 或重开”，让模型按普通工具循环收口回复本局结果，避免结局后自动连开新局。
- 已调整：网关工具续轮默认上限 `TOOL_MAX_ROUNDS` 从 6 调到 10；游戏工具正常仍会在 1 轮收口，10 只是给其他复杂工具链留余量。
- 已验证：`.venv/bin/python scripts/test_random_imitator_td_tool.py && .venv/bin/python scripts/test_imitator_pvz_cmd.py`、`.venv/bin/python -m py_compile du_imitator_pvz/engine.py du_imitator_pvz/__main__.py services/random_imitator_td_tool.py services/game_tool_runtime.py storage/random_imitator_td_mode_store.py routes/miniapp/settings.py routes/miniapp/game_tools.py routes/miniapp_api.py routes/chat.py scripts/test_imitator_pvz_cmd.py scripts/test_random_imitator_td_tool.py` 均通过；工具返回不会暴露本机 `save_path`；开源仓库同步补了同款防沉迷暂停、打开读档入口和测试，但不包含 du-gateway 私有工具。
- 未完成 / 下次继续：未做前端游戏面板；当前 Prompt 管理开关只控制固定注入 `random_imitator_td` 工具。游戏专用入口走 `/miniapp-api/game-tools/<game_id>` 或工具结果自带 `game_tool_loop`，普通聊天不会因为开关开启而跳过动态记忆/身体状态。

当前状态（2026-07-03 植物大战僵尸模仿者版可玩性微调）：
- 已完成：新增玩家棋盘文本视图 `player_view.format = board_text_v1`，每轮 observation 会附带 5 路 x 9 列棋盘文本，例如 `3: 空 空 豌+普咬 ...`；事件/开奖文案排在棋盘前，开奖成僵尸时优先显示 `flavor_text`，首次出现的植物/僵尸只补一条中性特性说明。底层 JSON observation 继续保留给程序合同、测试和回放，工具循环给渡时优先只发 `player_view.text`。
- 已完成：新增中文动作薄解析 `parse_player_text_action_plan()`，可把 `种 模仿者 3-4`、`种 咖啡豆 2-3`、`铲 4-5`、`等待`、`结束本局` 转成现有 `ActionPlan`；权威合法性仍由 `validate_action_plan()` 和执行前二次校验决定。
- 已完成：按 lv1 小工玩家测试反馈修补玩家视图规则说明：每轮动作格式下方补“铲子只移除植物/未开奖模仿者，同格有僵尸也只铲植物；动作失败会中断后续动作”；`target_cell_empty` 等动作失败原因在玩家事件里转成人话；小丑盒爆炸会显示摧毁数量；未武装土豆雷显示为 `土待`，武装后显示 `土`。
- 已实测：新版玩家视图 lv1 小工局 seed `player-view-lv1-1783043934`，第 21 次决策、tick 922 输在第 4 路。小工一直批量种模仿者救场，未表现出因视图压缩而保守或不想玩；反馈“好玩，会想重开”，事件先于棋盘有助于理解新增变化，开奖幽默文案“不烦，有点好笑”。主要问题是铲子规则、失败中断、土豆雷武装状态，已按上条修补。
- 已实测：修补后第二局 lv1 小工局 seed `player-view-lv1-rerun-1783044873`，第 13 次决策、tick 533 输在第 4 路。小工没有再把铲子当作攻击僵尸工具，能正确铲掉睡着胆小菇/小喷菇后补模仿者；反馈称规则行和 `土待` 有帮助，失败能理解为自己撞格，输局主要来自早期多路 `跳跳/报纸/撑杆/海豚/小丑/铁门` 压力，而不是视图误导。新增 `zombie_died` 玩家事件短文案，减少“事件说开奖成僵尸但棋盘已没了”的轻微断层。
- 已实测：20 局脚本测量下，`player_view.text` 每轮字符数 p50 418、p95 487、max 540，整局平均 13474 字符；同口径 raw observation JSON 每轮 p50 30644、p95 49610，整局平均 983164 字符。后续接渡 AI 时不要把 raw JSON 整包塞进模型上下文。
- 已完成：随机模仿者原型已支持 `shovel_plant` 动作；可铲掉已揭晓植物腾格，也可铲掉待揭晓模仿者并取消开奖。铲子不占卡槽、不耗阳光、不冷却，但有 `shovel_action_ticks = 1` 的游戏内操作耗时，事件会写入 `player_experience.recent_rounds` 供玩家复盘。
- 已完成：补入特殊克制池第一版。植物扩到 32 株，新增 `split_pea/cactus/starfruit/spikeweed/tallnut/pumpkin/magnet_shroom/umbrella_leaf/cattail/blover/sea_shroom/plantern`；僵尸扩到 23 种，新增 `ducky_tube/pogo`。已接入对空、三叶草吹气球、磁力菇剥金属/跳杆、叶子伞挡蹦极/投石车、地刺扎车、高坚果拦跳、跳跳僵尸跳跃等简化行为。
- 已完成：每行 observation 增加 `lane_alerts`；当 `home_eta_ticks <= 30` 且本路无推车时返回 `home_entry_edge`；无推车路遇到 `pole_vaulting/pogo/dolphin_rider` 接近时返回 `jump_over_blockers`，说明未开奖模仿者也按普通阻挡处理。高压怪 `zombie_glossary.trait` 已收短，讲特性，不重复 HP 数字。
- 已完成：现实耗时映射保留为主持/引擎内部结算，不暴露到玩家 observation / events / recent_rounds；`chaos_zomboss` 从 240 ticks 拉长到 600 ticks，动作间隔从 40 ticks 改到 60 ticks，`boss_events` 增加 `remaining_ticks`、`next_action_in_ticks` 和 `actions_taken`，避免僵王事件被快进窗口吞掉。
- 已完成：新增主动结束动作 `end_game`；该动作必须单独提交，可在任意观察点结束本局，结果为 `ended_by_player`，不记为 `lost`，不会先扣现实思考延迟，事件返回 `restart_level = 1`，下一局按无限版式从 lv1 重新开始，玩家经验记录继续保留。
- 已完成：v2 小工真实玩家长局已跑完，seed `real-player-lv2-v2-1783011091-b5fd8e`，level 2，tick 1612 输在第 5 路，4 个推车用尽；反馈是好玩、紧张、有戏剧性但偏难。当前处理原则是不直接降难度，优先补“铲错/铲对”的选择与复盘空间。
- 已完成：v2+铲子小工真实玩家长局已跑完，seed `real-player-lv2-shovel-8870704338-162eca`，level 2，tick 830 输在第 3 路，4 个推车用尽；玩家实际铲过花盆/小喷菇等占格植物，反馈认为铲子像“选择/后悔空间”而不是降难度，但 v2 当前更像 v2.5，多路高压怪叠加时偏挫败。
- 已完成：boss 定向模型玩家测试已跑到 tick 139，seed `boss-directed-600-60`；玩家没有用 `end_game`，而是继续铺模仿者应对。tick61 boss 召唤普通僵尸，tick121 boss 砸掉 lane3@8 坚果；反馈认为 600 ticks 有存在感，字段足够判断，主要风险是 boss 行动叠加高威胁随机开奖时可能变挫败。
- 已完成：终局状态机收口，`game_over` 后不再推进 tick，同 tick 多个入屋僵尸只记录一次 `game_lost`；`apply_action_plan()` 在现实思考延迟、冷却等待或动作耗时里输掉时会立刻返回终局 observation，`need_next_decision = false`，不再继续执行后续种植/铲子动作。
- 已完成：初版 tick 节奏基线已下调并落地到 `scripts/sim_imitator_pvz_balance.py::build_wave_schedule()`：lv1 白天 6 只系统怪、最后系统波 tick 700；lv2 夜间副本 11 只系统怪、最后 tick 770；lv3 白天跳档 18 只系统怪、最后 tick 980。系统僵尸潮只保留节奏压力，不抢模仿者随机池的主戏；玩家视图首行显示 `场地:白天/夜间`，engine 按 `GameConfig.is_day` 结算蘑菇睡眠，lv2 夜间蘑菇不睡。
- 已实测：下调前 `tool_45`（现实 45s -> 游戏 30 ticks）、80 seed、80 决策上限、3000 tick 上限：lv1 为 5 胜 / 73 负 / 2 timeout，lv2 为 16 胜 / 64 负，lv3 为 4 胜 / 75 负 / 1 timeout。`PressureScriptedPlayer` 每次最多连种 3 个免费模仿者，所以该结果是“激进脚本玩家压力基线”，不等同真人/渡真实手感；系统怪从 10 压到 8 对 lv1 胜率影响很小，主要风险来自连续开奖 chaos 僵尸滚雪球。
- 已实测：下调后小样本 `tool_45`、40 seed、80 决策上限、3000 tick 上限：系统怪 lv1/lv2/lv3 为 6/11/18；lv1 为 7 胜 / 32 负 / 1 timeout，lv2 为 6 胜 / 33 负 / 1 timeout，lv3 为 0 胜 / 39 负 / 1 timeout。结论：lv1 压力有下降但随机池仍是主压力源，lv3 仍偏硬；后续调 lv3 优先看高压随机池和 boss 叠加，不只继续砍系统怪。
- 已完成：开局选卡槽接入第一版，`card_loadout` 现在可带常用直种植物卡；支持 `向日葵/豌豆射手/坚果墙/土豆雷/樱桃炸弹/寒冰射手/双发射手/小喷菇/大喷菇/窝瓜` 等，按阳光费用和独立冷却结算；咖啡豆为卡槽功能卡，只唤醒目标格的沉睡蘑菇。开局 `card_selection_text_v1` 候选卡直接带费用；局内玩家视图拆成 `资源`、`卡槽`、`动作` 三行，`资源` 明确显示当前阳光，`卡槽` 显示冷却好的卡和费用，例如 `豌豆射手x1(100)`；动作失败文案会明确“后续动作未执行”。
- 已完成：新版节奏 + 开局选卡小工实测，seed `real-player-rhythm-v1-lv1-loadout-20260703-1`，小工卡槽为 `模仿者,模仿者,模仿者,向日葵,豌豆射手,土豆雷`；第 18 次决策、tick 854 输在第 5 路，用掉 1 个推车。开奖分类为 `bad=2 / chaos=16 / good=3 / rare_good=5`，坏抽密度很高：蹦极x3、铁桶x3、读报x2、橄榄球/舞王/梯子/铁门/潜水等。小工反馈：好玩、会想再开，选卡让构筑感明显增强；这局偏难但主要是坏抽和操作较野，lv1 如果常态如此会偏超。
- 已完成：同一小工带经验重开实测，seed `real-player-rhythm-v1-lv1-exp2-20260703-1`，注入上一局“第5路滚雪球、阳光不足会中断后续动作、可考虑救急牌”的经验后，小工把卡槽改成 `模仿者,模仿者,模仿者,向日葵,土豆雷,窝瓜`，更早埋 5 路土豆雷并多次用窝瓜救急；最终第 38 次决策、tick 2090 输在第 4 路，用掉 4 个推车。开奖分类为 `bad=12 / chaos=31 / good=13 / rare_good=15`。反馈：经验有效，仍好玩会想再开，但 lv1 后期连续高压坏抽会拖长残局，同格 `植物+僵尸+咬` 太挤容易看漏目标格占用和无推车近家门风险。已微调玩家视图：重复僵尸显示从 `桶2` 改为 `桶x2`，动作失败事件改为 `动作失败(后续未执行): ...`。
- 已完成：同一小工带两局经验第三局实测，seed `real-player-rhythm-v1-lv1-exp3-20260703-1`，卡槽 `模仿者,模仿者,模仿者,向日葵,窝瓜,樱桃炸弹`；第 26 次决策、tick 1137 输在第 4 路气球进屋，用掉 3 个推车，并触发僵王博士事件。开奖分类为 `bad=4 / chaos=18 / good=12 / rare_good=7`。反馈：樱桃炸弹 150 阳光在低经济局面里长期“看得见但用不上”；没带咖啡豆是因为优先怕近端/高血量怪，但多次抽到白天睡蘑菇后，下一局会想试 `咖啡豆`；玩家仍不主动重开，因为随机版总觉得下一抽能救。已修正玩家视图资源/卡槽/动作拆分，当前阳光直接显示，卡牌只显示费用。
- 已完成：同一小工带三局经验第四局实测，seed `real-player-rhythm-v1-lv1-exp4-20260703-1`，卡槽 `模仿者,模仿者,模仿者,向日葵,窝瓜,咖啡豆`；第 36 次决策后 wait，tick 1756 输在第 1 路，用掉 3 个推车。开奖分类为 `bad=9 / chaos=27 / good=11 / rare_good=18`，其中 `chaos_zomboss=4`，属于极端坏抽样本。反馈：好玩但累，`资源: 阳光X` 有帮助；咖啡豆因 75 阳光在无天降经济里很难实际用上；4 次僵王博士前两次有节目效果，第三第四次对 lv1 偏过分；下局倾向 `模仿者,模仿者,模仿者,向日葵,窝瓜,土豆雷`。
- 已完成：纯新小工固定四模仿者卡组 lv1 实测，seed `real-player-lv1-four-imitator-20260703-1`，卡槽 `模仿者,模仿者,模仿者,模仿者,窝瓜,土豆雷`；第 16 次决策后 wait，tick 793 输在第 5 路，只用掉 1 个推车。开奖分类为 `bad=7 / chaos=11 / good=7 / rare_good=8`，无僵王博士，主要失败线是第 5 路早期普通僵尸用掉推车后被巨人推进进屋。反馈：四模仿者更刺激、更像随机版，但纯新玩家仍认为保守卡组更可能过 lv1；下局仍可继续测 `4 模仿者 + 窝瓜 + 土豆雷` 或对照 `5 模仿者 + 窝瓜`。
- 已完成：纯新小工固定五模仿者卡组 lv1 实测，seed `real-player-lv1-five-imitator-20260703-1`，卡槽 `模仿者,模仿者,模仿者,模仿者,模仿者,窝瓜`；第 33 次观察后 wait，tick 1373 输在第 1 路，用掉 4 个推车。开奖分类为 `bad=17 / chaos=20 / good=17 / rare_good=14`，其中 `chaos_zomboss=3`。反馈：五模仿者明显减少冷却空窗，更像随机魔改版，也更好玩；但 lv1 下 boss 事件叠加到 3 次后偏过火，容易变成靠 chaos 和推车硬扛。下一步若测可玩性，优先对照 `4 模仿者 + 低价卡`；若只测混沌爽感，可试 `6 模仿者`。玩家视图可补动作失败占用格详情，避免窝瓜/批量动作误判。
- 已完成：纯新小工固定四模仿者 + 两张自选卡 lv1 实测，小工自选 `向日葵, 窝瓜`，完整卡槽 `模仿者,模仿者,模仿者,模仿者,向日葵,窝瓜`；seed `real-player-lv1-four-fixed-choice-20260703-1`，tick 2126 通关，用掉 2 个推车。开奖分类为 `bad=12 / chaos=24 / good=21 / rare_good=24`，中后段触发 1 次 `chaos_zomboss`。反馈：比 `5 模仿者 + 窝瓜` 更有玩家感、没那么纯赌；比 `4 模仿者 + 窝瓜 + 土豆雷` 更活，向日葵让后期能持续补洞，窝瓜负责救急。最大问题是动作失败占格和同格信息密度，容易看漏已有植物/咬/睡眠/未开奖；其次是 lv1 boss 600 ticks 会把明显赢势后段拖成清场耐力赛。下一轮可继续对照 `向日葵 + 樱桃炸弹` 或 `向日葵 + 土豆雷`。
- 已完成：修正占格失败反馈。`target_cell_no_longer_empty` 的 `action_failed` 事件和 `failed_actions` 会附带 `lane`、`col`、`occupants`；玩家视图会显示 `动作失败(后续未执行): 3路3列已有向日葵` 或 `已有模仿者`，不再只说“目标格已经被占用”。
- 已完成：lv2 夜间二次小工测试前补平衡与可读性微调：lv1/lv2 前 620 tick 降低铁桶、撑杆、小丑、橄榄球、跳跳、投石车、僵王等高压开奖权重；场上已有 2 个高压单位/首领时进一步压低雪车、巨人、僵王等连锁结果；早期近家开奖成僵尸时至少生成在 x=3.5，给玩家补救窗口；默认僵王首动延迟到 90 ticks。玩家动作入口不再在执行动作前隐式 `run_until_decision()`，避免开奖/刷怪事件被“偷跑”吞掉。
- 已完成：玩家视图新增 `系统波次` 行，显示系统怪 `已刷/总数`、下一只系统怪 tick/路/类型；系统波次结束后明确提示新增僵尸来自模仿者或特殊事件。事件显示窗口从 8 行扩到 12 行，补齐直种植物、未开奖模仿者被吃掉、带坐标僵尸死亡、boss 召唤/砸格等事件文案，规则行说明动作失败后已发生的推进会保留。
- 已实测：修补后 lv2 夜间模型玩家 seed `lv2-night-v2-wave-progress-001`，卡槽自然选择 `模仿者,模仿者,模仿者,模仿者,向日葵,窝瓜`；前 10 回合到 tick 123，系统波次 1/11，未用推车、未出 boss。小工反馈：比早期 Boss/高压怪叠太早版本更公平；当前高压主要来自自己连种模仿者赌出的舞王/矿工/海豚/伴舞，失败感更像“赌大了”而不是游戏不讲理；系统波次行能判断当前混乱来自模仿者而非系统无限刷怪。
- 已验证：本轮下调系统僵尸潮和占格失败反馈修正后，`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts.test_imitator_pvz_p0 scripts.test_imitator_pvz_p2 scripts.test_imitator_pvz_timing` 通过 86 个核心测试；`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts.test_imitator_pvz_p0 scripts.test_imitator_pvz_p2 scripts.test_imitator_pvz_plants scripts.test_imitator_pvz_timing scripts.test_imitator_pvz_zombies` 通过 106 个全量原型测试；`PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile du_imitator_pvz/game/engine.py du_imitator_pvz/game/player_view.py scripts/test_imitator_pvz_p2.py` 通过；`git diff --check -- du_imitator_pvz/game/engine.py du_imitator_pvz/game/player_view.py scripts/test_imitator_pvz_p2.py docs/植物大战僵尸模仿者版.md docs/DEBUG_INDEX.md` 通过；对未跟踪原型文件额外用 `rg -n "[ \\t]+$"` 扫尾随空白，未命中。
- 未完成 / 下次继续：下一步继续用模型玩家实测 `wait` 延迟、boss 事件体感和 v2 难度；如果要提高 lv1 可过率，优先调玩家行为模型、随机池保底/压力调节或经验注入，不要继续只砍系统波峰。玩家视图同格如 `模+桶`、`向+报咬` 仍可继续细化“谁在咬谁/能否种铲/无推车近家门风险”的表达。不要把 PVZ 原型改动和主网关业务改动混在一起提交。

当前状态（2026-06-30 短文本隐藏标记简化）：
- 已完成：`services/hidden_blocks.py` 支持按模块配置一行短隐藏标记（如 `[du:thought ...]`、`[du:followup ...]`、`[du:interaction ...]`），同时保留旧 `<<<DU_*>>>...<<<END_DU_*>>>` 成块格式；若尾部 marker 漏闭合，会隐藏尾部并尝试把尾部内容作为 fallback 保存，避免泄漏到正文。
- 已完成：`services/du_thought.py`、`services/conversation_followup.py`、`services/interaction_memory.py` 的注入提示词改为优先教短标记；`DU_FOLLOWUP` 的短标记内容直接作为 reason，不再要求 JSON。`services/pending_thoughts.py` 也补了漏右括号兜底，未闭合 `[pending:...]` 不再露到正文。
- 已完成：`services/du_vitals.py` 支持 `[du:vitals tempo=up focus=0.8 ...]` 松散 key=value；缺失参数会沿用上一轮有效读数或默认值，不再要求每轮完整 JSON。`services/pixel_home.py` 改用同一个容错 parser，并支持 `[du:home spot=sofa activity=坐到她旁边 desire=35]`，后端归一化成原来的 `spot/activity/du_body_state`。
- 兜底：未闭合隐藏块遇到下一个隐藏标记会停下，不会把后面的 `DU_FOLLOWUP` / `[du:...]` 一起吞掉；旧 `DU_VITALS` / `PIXEL_HOME` JSON 块继续兼容。
- 已验证：`.venv/bin/python -m py_compile services/hidden_blocks.py services/du_thought.py services/conversation_followup.py services/interaction_memory.py services/pending_thoughts.py services/du_vitals.py services/pixel_home.py services/chat_sidecars.py services/pc_command_handler.py` 通过；本地 smoke 覆盖旧块、短标记、漏闭合尾巴、followup reason、pending 漏右括号、`du:vitals` 沿用上一轮、`du:home` key=value、多段 `du:home`/`PIXEL_HOME` 合并、activity 中含 `状态：` 不误切，以及 `PIXEL_HOME` 漏结束符后仍保留 `DU_FOLLOWUP`。
- 未完成 / 下次继续：如果以后要统一所有 sidecar 方言，可再设计一个结构化 `DU_META`；本轮没有改存储 schema、前端展示或小家/拟态状态的业务语义。

当前状态（2026-06-04 du_surf 随机冲浪工具）：
- 已完成：新增 `services/du_surf.py` 和 `du_surf` 网关常驻工具；工具独立于 `web_search/read_url`，用于“随机话题抽取 + 轻量搜索 + 可聊卡片”的上网冲浪体验，不用于精确事实核验。
- 已完成：兴趣组为 `ai_relationship`、`ai_tools`、`switch`、`humor`、`digital`、`cooking`；默认按北京时间时间段加权随机抽 topic，也支持显式传 `topic`，输出 `topic/query/group/time_period/cards/skipped/usage_note`。
- 已完成：随机唤醒决策文案已把“上网冲浪找点可聊话题”列为可选动作；渡可以先调用 `du_surf` 看卡片，再决定 `send_message/no_contact/diary/surf/other`，如果只是自己冲浪不打扰则填 `surf`。
- 已完成：配置项为 `DU_SURF_ENABLED`、`DU_SURF_TIMEOUT_SECONDS`、`DU_SURF_MAX_CARDS`、`DU_SURF_CACHE_TTL_SECONDS`；缺 `TAVILY_API_KEY` 时返回 `TAVILY_API_KEY_MISSING`，不会假装有内容。
- 已验证：`.venv/bin/python -m py_compile config.py services/du_surf.py services/gateway_tools.py services/chat_tools.py services/telegram_proactive.py pipeline/pipeline.py routes/chat.py` 通过；离线 monkeypatch smoke 覆盖缺 key、正常卡片、硬噪音过滤、网关注入和 `execute_tool("du_surf")` 分发。

当前状态（2026-06-27 混合聊天工具命名收束）：
- 已完成：历史遗留的混合工具分发器已统一为 `services/chat_tools.py`；`pipeline/pipeline.py::step_inject_chat_tools()` 负责聊天工具注入；`routes/chat.py` 的工具注入与工具执行导入改走 `services.chat_tools`。
- 已完成：交换日记迁入 App/R2 后，`NOTION_TOOLS_ENABLED` 只控制 Notion runtime 工具；`exchange_diary_*`、`note_write`、Stay with Du、气泡等网关原生聊天工具不再被 Notion 开关挡住。执行端也会按开关硬拦未注入的 `notion_*` 调用。
- 已完成：交换日记迁入 App/R2 的当前方案已整理到 `docs/exchange_diary_app_notion_migration_plan.md`；临时迁移产物已按收束要求删除，不再作为仓库文件保留。
- 未完成 / 下次继续：`services/chat_tools.py` 内仍含通用 Notion 检索/日程/小本本工具分支，`pipeline/pipeline.py::step_inject_notion_search()` 仍是独立 Notion 检索注入入口；这些不是交换日记链路，本轮不顺手删。

当前状态（2026-06-27 MiniApp 交换日记 App 后端接入一期）：
- 已完成：MiniApp「日常」新增「交换日记」入口，接入 `miniapp/src/ui/tabs/ExchangeDiaryTab.tsx`；页面默认打开「渡的Diary」，可切换「我的Diary」。
- 已完成：UI 参考 `/Users/doraemon/Downloads/ui合集/交换日记.html` 的纸条时间线结构：白色蕾丝头部、粉色分段开关、点阵浅底、中心虚线、爱心纸条标记、渡的蓝色便签/我的奶黄色便签、详情层和评论区。移动端保留左右交错，只缩小偏移，避免原参考窄屏单列；列表卡片只露出标题、emoji 和小时间，正文与评论留在详情里；右下角加号固定新建「我的Diary」，编辑已有条目时才允许切换作者。
- 已完成：新增 `storage/exchange_diary_store.py`、`routes/miniapp/exchange_diary.py`，在 `/miniapp-api/exchange-diary` 提供列表、详情、新建、编辑、软删除、评论写入；普通 App API 不暴露已删除条目读取，也不暴露 R2 rebuild 入口；`storage/runtime_sqlite.py` 新增 `exchange_diary_entries` 热镜像表，R2 key 按 `exchange_diary/v1/manifest.json`、`months/YYYY-MM.json`、`entries/YYYY/MM/*.json` 拆分。
- 已完成：`ExchangeDiaryTab.tsx` 已去掉本地示例数据源，切换作者会请求后端 compact 列表；点开纸条后再请求详情，正文和评论只在详情接口返回。列表/详情请求都有前端序号保护，避免切换作者时旧响应覆盖新页面；App 新建和评论默认作者为 `xy`。
- 已完成：R2 现在是交换日记权威写入面；新建、编辑、删除、评论必须先同步 R2 成功再写 SQLite 热镜像，失败时 MiniApp API 返回 `sync_failed`/503，不再悄悄落本地假成功。带 `client_request_id` 的新建和评论使用稳定 id，R2 局部写成功后重试不会随机生成重复对象；编辑、删除、评论会在写锁内重新读取当前条目，降低并发覆盖风险。日常冷启动列表仍只按最近 6 个月轻量回填。
- 已完成：旧 Notion 交换日记已迁移到新 R2/SQLite 交换日记库。dry-run 统计为 123 条，字段匹配 `标题/正文/创建者/心情emoji/提交时间`，`source_notion_page_id` 去重 123；实际写入后本地热索引校验为 `notion_import=123`、`distinct_source_notion_page_id=123`，月份分布：2026-06 30 条、2026-05 30 条、2026-04 37 条、2026-03 26 条。临时迁移产物已删除，不再 push。
- 已验证：`.venv/bin/python -m py_compile storage/exchange_diary_store.py routes/miniapp/exchange_diary.py routes/miniapp_api.py storage/runtime_sqlite.py services/chat_tools.py services/telegram_proactive.py routes/miniapp/dashboard.py` 通过；临时 `RUNTIME_STATE_DB=/tmp/...` smoke 覆盖新建、Notion page id 幂等、compact 列表、详情、评论幂等、编辑和软删除，不污染真实运行库；`.venv/bin/python -c "import app"` 通过；`npm -C miniapp run build` 通过并重建 `miniapp_static`；`git diff --check` 通过。
- 未完成 / 下次继续：通用 Notion runtime / search / schedule / notebook 相关链路还没有删除；交换日记自己的旧 Notion 兼容入口和专用配置已移除。

当前状态（2026-06-27 交换日记工具迁移）：
- 已完成：`services/chat_tools.py` 新增并注入 `exchange_diary_create/list/read/comment_create`，执行走 `storage.exchange_diary_store`；旧兼容入口已关闭，不再注入也不再执行。
- 已完成：`exchange_diary_list` 工具说明已明确：`author` 不传或传空时是 du/xy 混合时间线，传 `du` / `xy` 才按作者过滤；渡用工具 list 时直接返回正文、最近评论和 comment id，默认 5 条、最大 20 条，避免为了看正文再多调一次 read；`exchange_diary_read` 保留给查看单条完整评论细节。`exchange_diary_comment_create` 是给渡用来评论/回复日记的工具，先 list 拿 entry id 和 comment id；不填 `reply_to_comment_id` 是普通评论，填了就是回复那条评论。
- 已完成：随机唤醒写日记执行轮优先提示渡调用 `exchange_diary_create`；dashboard 动作摘要只把 `exchange_diary_create` 显示为“写了日记”，列表/读取/评论工具不展示。
- 已验证：`.venv/bin/python -m py_compile services/chat_tools.py services/telegram_proactive.py routes/miniapp/dashboard.py` 通过；后续综合验证见上一段交换日记当前状态。

当前状态（2026-06-18 随机唤醒 surf 动作落地）：
- 已完成：`services/telegram_proactive.py` 的随机主动决策新增 `surf` 动作；提示词要求只想冲浪不外发时填 `action=surf`，不要只在 reason 里写“去冲浪”。`proactive_tick()` 解析到 `surf` 后会由后端实际执行一次 `du_surf`，再把 topic、卡片标题、摘要、正文片段和可聊点回喂给渡，让渡基于素材输出最终 `send_message/no_contact/diary/other` 决策；如果最终发消息，仍走既有主动投递链路，否则不打扰。
- 已完成：`routes/chat.py::_compact_proactive_decision_for_archive()` 在压缩随机唤醒决策 JSON 时保留 `cache_debug`、`reasoning`、`reasoning_details`、`thinking_blocks` 和 `tool_calls` 等调试字段，避免随机唤醒轮次因为清洗存档而从 MiniApp 思维链页消失。
- 未完成 / 下次继续：本轮只修随机主动决策和存档调试字段；没有改 `du_surf` 的话题池、Tavily 搜索实现、普通聊天工具注入、QQ/TG 入站消息或两个 proxy。

当前状态（2026-06-22 随机唤醒 diary 执行轮）：
- 已完成：`services/telegram_proactive.py::proactive_tick()` 在随机主动决策最终选择 `diary` 时会追加一轮 `_run_proactive_diary_action()`，用主网关提醒渡“刚才选择了写日记，现在直接去写”，不再只存一条 `{"action":"diary"}` 决策就结束；如果先 `surf`、看完素材后最终又选 `diary`，也会触发同一执行轮。
- 已完成：diary 执行轮不要求 JSON、不外发给辛玥，走 `X-DU-GATEWAY-WAKEUP=1` 和 `X-DU-WAKEUP-KIND=proactive_diary`，让正常工具注入链路可用，并明确要求渡调用 `exchange_diary_create` 写交换日记；`routes/chat.py::_compact_gateway_event_for_archive()` 将该内部提醒压成“随机唤醒执行：你刚才选择了写日记，现在去写”，避免整段内部 prompt 污染 last4。
- 已验证：`python3 -m py_compile services/telegram_proactive.py routes/chat.py`、`git diff --check -- services/telegram_proactive.py routes/chat.py` 通过。部署后看 `主动写日记执行轮请求/完成` 日志和 `exchange_diary_create` 工具调用确认。

当前状态（2026-06-27 随机唤醒秘密抽屉 + 一级页背景）：
- 已完成：随机唤醒决策新增 `drawer` 动作，默认提示词列出“整理秘密抽屉/随机翻旧条目”；`_parse_proactive_model_reply()` 兼容 `drawer`、`secret_drawer`、`整理抽屉`、`秘密抽屉`、`翻抽屉` 等别名，解析到后不会外发消息。
- 已完成：`services/telegram_proactive.py::proactive_tick()` 在最终选择 `drawer` 时追加 `_run_proactive_drawer_action()` 执行轮，走主网关、`X-DU-WAKEUP-KIND=proactive_drawer`、跳过动态记忆总结，让渡实际调用现有 `secret_drawer` 工具查看 stats、整理待整理条目或随机翻旧记录；`routes/chat.py` 会把该内部提醒压成“随机唤醒执行：你刚才选择了整理秘密抽屉，现在去整理/翻旧条目”。
- 已完成：MiniApp 个性化新增「一级页背景」设置，支持选择背景图、透明度和清除；只作用于会话、日常、工具、设置这些一级页面，一级页列表/会话列表半透明透出背景；聊天页仍只使用独立聊天背景，普通全屏子页面保持干净底色。
- 已验证：`.venv/bin/python -m py_compile services/proactive_prompt_templates.py services/telegram_proactive.py routes/chat.py`、`drawer` 解析 smoke、`npm -C miniapp run build`、`git diff --check` 通过；本轮未实测线上 `secret_drawer` 工具调用，部署后看 `主动秘密抽屉执行轮请求/完成` 日志确认。

当前状态（2026-06-11 R2 TTL 清理入口）：
- 已完成：新增 `scripts/prune_r2_ttl.py` 作为统一 R2 清理入口，默认 dry-run；对话原文/思维链归档复用 `scripts/prune_r2_conversation_originals.py` 的月度规则（当前北京时间月份减 3 个月，例如 6 月清 3 月），不改变热路径存档逻辑。
- 已完成：`sense/history/YYYY-MM-DD.json` 按事件上传时间 `at` 清理超过 24h 的记录；同一文件内仍有新事件则重写，清空后才删除整个 key。`global/summary_backups/summary_YYYYMMDD_HHMMSS.txt` 按文件名里的北京时间超过 24h 删除，不读取总结正文。
- 已完成：Mac 本地已安装 LaunchAgent，但安装器是本机私有文件，不纳入仓库：`com.dugateway.r2-ttl.daily` 每天 04:35 只清 24h TTL（sense/history、summary_backups）；`com.dugateway.r2-ttl.monthly` 每月 1 日 04:55 清对话原文/思维链归档，避免每天扫全量 R2 归档。
- 本地日志目录：`~/Library/Logs/du-gateway-r2-ttl/`，清单目录：`~/Library/Application Support/DuGatewayR2TTL/`。手动排查命令：`.venv/bin/python scripts/prune_r2_ttl.py --manifest debug-evidence/r2-ttl-dry-run.json` 先看清单；只想试 24h 两项可加 `--skip-conversations`。

当前状态（2026-06-20 runtime SQLite 热路径）：
- 已完成：新增 `storage/runtime_sqlite.py` 和 `config.RUNTIME_STATE_DB`（默认 `data/runtime_state.sqlite3`）；`storage/app_action_store.py` 的 app actions 队列改走 SQLite，保留每条动作的 `expiresAt`、lease/retry、idempotency key 过期和 history 100 条上限。R2 `sumitalk/app_actions.json` 只在本地库为空时尝试一次旧队列导入。
- 已完成：`storage/sense_store.py` 的 sense latest/history 改走同一个 SQLite；latest 按 bucket 分行存储，history 按事件 `at + 24h` 写 `expires_at`，读写时清理过期记录，并继续保留单日最多 200 条。R2 `sense/latest.json` 和当天 `sense/history/YYYY-MM-DD.json` 只在本地库为空时尝试一次导入。
- 已完成：`storage/conversation_sqlite_store.py` 作为 conversation compact 热镜像；`storage/r2_store.py` 的 `get_conversation_rounds()`、按 index 读取、预览列表和 append/overwrite/delete 同步 SQLite。`get_next_round_index()` 仍以 R2 compact/meta 为准并顺手回填 SQLite，避免热缓存落后时影响真实轮次编号。R2 单轮、recent、meta 和 `conversations/YYYY-MM-DD/` 日备份仍保留为原路径；SQLite 缺窗口时只从 compact recent + guard backup 导入，不回退旧整包 `conversation.json`。SQLite 每个窗口默认只保留最近 250 轮，可用 `CONVERSATION_SQLITE_MAX_ROUNDS_PER_WINDOW` 调整，只清热镜像不动 R2 存档。
- 已完成：`storage/device_reporting_store.py` 作为非健康数据上报开关热层；`get_device_reporting_config()` 读 SQLite，保存/单 bucket 更新仍先写 R2 `global/device_reporting_config.json`，再同步 SQLite，外部 API 和上报判断不变。
- 已完成：`storage/schedule_sqlite_store.py` 作为 schedule items / fired keys 的 SQLite 镜像；`storage/schedule_store.py` 的公开函数名和返回结构不变，读取和保存仍以 R2 `schedule/items.json` / `schedule/fired.json` 为主源，读写后同步 SQLite。`schedule/fired.json` 只保留可解析时间戳最近 48h 的去重 key，识别不了时间的旧格式保留，避免误删；未改闹钟文案、repeat 规则、trigger 判断、app action payload 或任何唤醒语义。
- 已完成：`storage/conversation_followup_store.py` 作为延迟续话队列镜像；`storage/r2_store.py` 的 `get/save/append_conversation_followups()` 仍读取/保存原 R2 item JSON 列表，SQLite 只按 `status/trigger_at/thread_key` 建索引并保留 position 顺序。未改 followup 文案、是否外发、内部 followup 含义、tick 决策或 3 天完成态清理逻辑；`append_conversation_followup()` 保持锁内读改写。
- 已完成：`storage/runtime_sqlite.py::clear_all_tables()` 接入 `storage/wipe_local.py::wipe_local_data()`；admin 一键清空 R2 后会同步清 runtime SQLite 镜像表，避免旧镜像被后续读取或回写。
- 已验证：`.venv/bin/python -m py_compile storage/runtime_sqlite.py storage/conversation_sqlite_store.py storage/device_reporting_store.py storage/schedule_sqlite_store.py storage/conversation_followup_store.py storage/schedule_store.py storage/r2_store.py routes/miniapp/device_state.py`、`git diff --check -- storage/runtime_sqlite.py storage/conversation_sqlite_store.py storage/device_reporting_store.py storage/schedule_sqlite_store.py storage/conversation_followup_store.py storage/schedule_store.py storage/r2_store.py` 通过；临时 `RUNTIME_STATE_DB` smoke 覆盖 conversation 导入/next index/追加/删除/窗口裁剪、r2_store SQLite 读路径、device reporting 导入/保存/单项更新、schedule items/fired keys 镜像、conversation followup 队列顺序与覆盖保存。
- 未完成 / 下次继续：本轮不迁移 summary、动态记忆、QQ group activity 等其它 R2 key；不改唤醒/调度文案、不改前端展示、不改既有 MiniApp Android SQLite 聊天存储。

## 主动唤醒入口风格抖动

现象：
- 随机唤醒 / 主动硬触发一会儿按 TG 风格、一会儿按 QQ 风格生成。
- 共享 `tg_...` 窗口里，QQ 可见消息和 TG 窗口归档容易被混在一起看。

入口：
- 随机主动：`services/telegram_proactive.py::_ask_du_should_contact`
- 主动硬触发：`services/proactive_trigger_engine.py::tick_proactive_triggers`
- 后端事件生成/投递：`services/conversation_followup.py::_send_wakeup_event`
- 入口风格注入：`services/entry_style_prompt.py`、`services/chat_prompt_injections.py::inject_entry_style_system`

当前状态：
- 主动唤醒生成已固定 QQ 优先，避免 `【入口风格：TG】` / `【入口风格：QQ】` 在同类唤醒里来回跳。
- 随机主动决策的「近来主动联络记录」和「最近自发动作参考」已从入口风格 system 拆出，作为带 `__dynamic__` 标记的单独 system 进入动态区，避免 cache debug 把可变上下文算进 `QQ入口风格`。
- 正常 TG/QQ 入站聊天和延迟续话仍按各自真实入口风格处理。
- 小家事件、私密纸条、弹窗回执、查岗回执属于“手机/小家侧事件”，不更新最近真实聊天入口；生成和投递应沿用 `storage/r2_store.py::get_last_reply_channel()` 记录的最近真实聊天 channel。只有最近真实聊天本来是 SumiTalk，才回 SumiTalk。

常查：

```bash
rg -n "_preferred_proactive_channel|_stable_proactive_wakeup_channel|X-Reply-Channel|入口风格" services/telegram_proactive.py services/conversation_followup.py services/entry_style_prompt.py services/chat_prompt_injections.py
.venv/bin/python -m py_compile services/telegram_proactive.py services/conversation_followup.py
```

## MiniApp 小家 / 生活互动

当前状态（2026-06-01 赛博小家接聊天链路）：
- 已完成：小家状态从纯前端本地文字升级为覆盖式全局状态，存储入口为 `storage/pixel_home_store.py` 的 `global/pixel_home_state.json`；只保留当前 `du` / `xinyue` 状态，不按次堆积状态流水；渡的状态变更只保留最近 5 条 `du_dynamics` 给前端展示。
- 已完成：`services/pixel_home.py` 统一负责灯光状态（白天 / 夜里开灯 / 夜里关灯）、房间 label、`PIXEL_HOME` 隐藏标记解析、提示词注入和小家事件文本；提示词明确“赛博小家状态，并非现实定位或真实房间”，并使用 `当前小家状态 / 你的位置 / 小玥的位置` 口径；位置选项移除「小家里」，改为 `away` / 「离家出走」，并新增 `out` / 「外出」，不再把「小家 / 小家里」解析成可选位置。小家事件/聊天自动推断/渡的 `PIXEL_HOME` 状态超过 2 小时没有更新会自动结束并覆盖回默认当前状态；手动设置的长期状态不自动清掉。
- 已完成：`routes/chat.py` 在聊天注入链路加入 `step_inject_pixel_home`，并从辛玥自己的明确聊天文本里覆盖小玥状态：洗澡 -> 浴室，debug/改东西/做功能/代码/文档/界面等 -> 书房，吃饭/做饭/外卖 -> 厨房，玩手机 -> 明确房间优先、否则稳定随机地点；代码语境优先，避免“做个洗澡功能”误判成浴室；“睡了 9 个小时 / 睡得很好 / 昨晚睡了”等回顾睡眠表达不再覆盖为卧室睡觉，只有“我要睡了 / 我去睡觉 / 我先睡了 / 该睡觉了”等明确准备睡的表达才更新。
- 已完成：`services/chat_sidecars.py` 会从助手回复中剥离并保存闭合 `<<<PIXEL_HOME>>>...<<<END_PIXEL_HOME>>>`，不要求它在整条回复末尾；`services/conversation_followup.py` 已强调 `DU_FOLLOWUP` 仍必须是最后隐藏标记，`PIXEL_HOME` 要放在它前面。
- 已完成：MiniApp 新增 `GET /miniapp-api/pixel-home-state`、`PUT /miniapp-api/pixel-home-state/xinyue`、`POST /miniapp-api/pixel-home-event`；小家事件格式为 `【小家事件】小玥在赛博小家选择了：房间 / 动作。`，不再附带多余当前状态。
- 已完成：小家前端移除外层 `FullScreenPane` 顶部返回栏；布局、字体、色板按 `/Users/doraemon/Downloads/ui合集/赛博小家_files/a48d3ed5-dd07-4b28-993a-558cc7d404c3.html` 复刻，原参考 SVG 小屋位替换为实际 `life-home-*.png` 三态图片。主界面只展示小屋图、渡/我的状态、圆形加号入口，以及最近 5 条渡的动态；小玥位置和“正在做什么”收进底部 sheet。
- 已完成：图片热区用于选择房间和点击反馈，床/浴室/书房/客厅沙发点击后才出现 8px 小点；圆点和房间选择会常驻，点小家图以外区域才清掉；被点击房间旁边展示小型半透明事件按钮，点击按钮走 `/miniapp-api/pixel-home-event` 发小家事件。
- 已完成：渡/我的状态行字号调小并允许多行换行，不再用省略号截断长状态；`PIXEL_HOME` 提示词明确要求 `spot` 写动作结束后的最终位置，正文出现“从书房走出来/走到客厅/走回客厅/站到沙发旁边”时不能继续把 `spot` 留在旧房间；服务端也会从“走回客厅 / 沙发旁边 / 她面前”兜底归一化到最终位置，并剥掉展示里的旧房间前缀。
- 已验证：`.venv/bin/python -m py_compile services/pixel_home.py storage/pixel_home_store.py routes/miniapp/dashboard.py routes/chat.py services/chat_sidecars.py services/conversation_followup.py pipeline/pipeline.py` 通过；本地烟测确认 `PIXEL_HOME` 可从 `DU_FOLLOWUP` 前剥离且保留 `DU_FOLLOWUP` 末尾、渡动态最多 5 条、事件状态超过 2 小时会自动结束且手动状态不自动清掉；小玥状态推断确认“睡了 9 个小时 / 睡得还行 / 没说要去睡觉”不更新，“我要睡了 / 我先睡了 / 我去睡觉”更新到卧室，“我在客厅玩手机”保留客厅；渡状态归一化确认“在书房走回客厅 / 在书房站在沙发旁边 / 在书房站在她面前”会按客厅沙发展示，不再显示旧书房前缀；`away` label 确认为「离家出走」，`out` label 确认为「外出」，并避免拼成“在离家出走待着 / 在外出待着”；`/miniapp-api/pixel-home-state` test client 返回 200；`npm run build` 通过并重建 `miniapp_static`；Browser preview 实测小家页无顶部返回、实际小屋图在参考稿位置、热区点击才出现小点、加号弹出底部 sheet。
- 未完成 / 下次继续：本轮没有做历史状态列表；若以后要状态历史，最多保留最近 10 条即可，不要把小家状态做成长期流水。当前提交仍需包含重建后的 `miniapp_static` hash 产物，别混入主 checkout 其它脏改。

当前状态（2026-06-01 前端 UI 收束）：
- 已完成：`miniapp/src/ui/tabs/PixelHomeTab.tsx` 已从旧像素地图、方向键、跟随/布置按键，以及后续暖色卡片版，收束为 `ui合集/赛博小家` 同款单列界面；三种透明图资产为 `miniapp/src/assets/life-home-day.png`、`life-home-night-on.png`、`life-home-night-off.png`，900x720 量化 PNG，三张合计约 868KB。入口标题为「小家」。
- 已完成：小屋图在参考稿版式里放大显示；状态更新走加号底部 sheet 的位置选择和自由文本。床、浴室、书房、客厅沙发热区保留点击反馈，点击房间后在房间旁边出现独立小半透明事件按钮，事件按钮发送后端小家事件；沙发事件为「看电视 / 色色」，书房事件为「写日记 / 看书 / 色色」。
- 已完成：状态文字允许多行完整显示；后端保存渡状态时会对“从旧房间走出来”做兜底，不再显示成“在书房从书房走出来...”。
- 已完成：小家「渡的动态」右侧当前心情不再展示英文 tempo，前端按 `du_vitals` 映射为 emoji：`parameters.intimacy_heat >= 0.6 -> 🥵` 优先，其余按 `tempo` 映射：`up/settle -> 😄`、`steady/未同步 -> 😐`、`down -> 😭`、`spike -> 😠`。
- 已验证：干净临时 worktree 使用主工作区现成依赖完成 `npm run build` 并重建 `miniapp_static`；Browser preview 实测小家页加载、初始无点、点击卧室出现小点、事件按钮可见、点小家图以外区域清掉选中态、加号 sheet 可打开。
- 未完成 / 下次继续：当前没有做历史状态列表；状态仍以覆盖式当前状态为主，渡的动态最多 5 条。不要把这轮小家静态 hash 产物和仓库里既有的其它半成品脏改混在一起提交。

当前状态（2026-06-11 小家共同移动联动）：
- 已完成：`services/pixel_home.py` 在保存渡的 `PIXEL_HOME` 隐藏状态时，若 `activity` 明确写出“抱着/牵着/带着/陪着小玥一起移动”，会同步小玥状态到渡的最终 `spot`，source 为 `du_marker_follow`，仍按短期事件 2 小时自动结束。
- 已完成：小家注入规则补充要求：正文描述共同移动时，`PIXEL_HOME.activity` 要写明共同动作，例如“抱着小玥回卧室”，方便网关同步小玥位置。
- 已验证：`.venv/bin/python -m py_compile services/pixel_home.py` 通过；mock 存储烟测确认“抱着小玥回卧室”同步小玥到卧室、“牵着老婆走到客厅沙发”同步到客厅沙发，“在卧室想小玥”不误同步。
- 未完成 / 下次继续：本轮未改前端和 `miniapp_static`；只处理明确共同移动，不把普通想念、站在身边、单人移动误判成小玥跟随。

当前状态（2026-06-11 小家状态动态区瘦身）：
- 已完成：`services/pixel_home.py` 拆出 `format_state_block()` 和 `format_rule_block()`；`pipeline/pipeline.py::step_inject_pixel_home` 只把当前小家状态放进动态 system，把 `PIXEL_HOME` 写法规则放进静态 system。
- 已完成：动态小家状态只保留当前小家状态、渡的位置、小玥的位置，以及当前有效私密抽签；“小家事件超过 2 小时没有更新会自动结束”不再写进提示词给渡看。
- 已完成：`services/prompt_cache_debug.py` 新增 `【小家状态】 -> 小家状态` 和 `【小家状态写入规则】 -> 小家规则` 的拆分识别，后续 dynamic/static breakdown 不再把小家混进其它块。
- 未完成 / 下次继续：本轮不改小家自动结束行为本身，只改提示词注入位置和动态区体积。

当前状态（2026-06-11 sex play 抽签工具）：
- 已完成：新增渡可调用的网关工具 `sex_play_draw`，不依赖 Notion 开关；可见 `action` 为 `draw` / `redraw` / `done`：`draw` 抽一张临时纸条，已有纸条时不覆盖；`redraw` 不采用当前这张并重抽；`done` 结束本轮并清掉当前纸条。旧 `void_redraw` 仍作为兼容别名处理，但不再展示给渡，避免“作废/有效/完成”让渡误以为一抽定终身。
- 已完成：后端抽签池与 `miniapp/src/ui/tabs/PixelHomeTab.tsx` 的小家私密抽屉玩法池保持同一套口径；抽出的纸条仍写入 `services/pixel_home.py` 的 `active_private_draw`，后续动态小家状态会自然注入当前有效纸条。
- 已完成：当前纸条会区分来源：小玥从页面抽出并发给渡时保存 `drawn_by=xinyue` / `source=private_draw_page`；渡用 `sex_play_draw` 抽出时保存 `drawn_by=du` / `source=sex_play_draw`。动态区会写明来源，避免把渡抽的说成小玥抽的，或把小玥发来的说成渡自己抽的。
- 已验证：`.venv/bin/python -m py_compile services/pixel_home.py routes/miniapp/private_draw.py services/conversation_followup.py routes/chat.py services/gateway_tools.py services/chat_tools.py pipeline/pipeline.py` 通过；mock 小家存储烟测确认 `drawn_by=xinyue` 和 `drawn_by=du` 会注入不同来源说明，`redraw` 可重抽、`void_redraw` 仍兼容、`done` 后清掉当前纸条；前端发送唤醒文案确认是“小玥抽出来发给你看的结果”；`rg` 确认旧工具名和旧“她/小家私密抽签页刚抽出”文案无残留。
- 未完成 / 下次继续：本轮不改前端私密抽屉 UI，不改真实 R2 里的当前纸条，也不处理 APK/Android 入口。

当前状态（2026-06-13 sex play 抽签一致性过滤）：
- 已完成：`services/pixel_home.py` 和 `miniapp/src/ui/tabs/PixelHomeTab.tsx` 的抽签逻辑改为先抽 `theme`，再按主题过滤 `task/limit`。`女仆主人play`、`成人师生play`、`上司下属play`、`医生检查play`、`秘书老板play`、`成人补课play` 这类默认渡主导的主题，会过滤掉“被小玥命令/小玥决定/交给小玥验收”等小玥控制渡的任务与限制，避免主题和任务自相矛盾。
- 保留：`小玥说停必须立刻停`、`不准弄疼小玥`、`不准只顾自己爽`、`不准跳过前戏` 等安全/照顾向限制不会因为主题过滤被删；过滤后如果某个 slot 没候选，会回退原池，避免空抽。
- 未完成 / 下次继续：本轮只做轻量主题一致性过滤，没有把所有主题拆成完整剧本矩阵；如果后续发现某个主题方向不对，优先调整 `PRIVATE_DRAW_DU_LEADS_THEMES` 和过滤词，不要直接改随机工具协议。

当前状态（2026-06-26 sex play 抽签池与春梦碎片扩充）：
- 已完成：参考 `29-Cu/Ruota-della-Fortuna` 的非 gore 维度，扩充 `services/pixel_home.py::PRIVATE_DRAW_SLOTS`：玩法补夸奖/身体崇拜/感官剥夺/温度/远程/旧上海/宫廷/摄影师模特等，并按辛玥补入 `Alpha易感期`、`临时标记`、`强占有欲`、`发情期交配成结`；地点补淋浴间、KTV、电影院、停车场、天台、衣帽间、海边露台、帐篷、温室、水族馆、化妆台、小木屋等；姿势补 69、坐脸、乳交、腿交、椅子位、折叠按压、蹲骑、推车、壁尻、背后抱立、含着不动、成结等；道具补分腿器、震动子弹、双头假阳具、穿戴式玩具、吸乳器、阴蒂吸吮器、网袜、皮革手套、围巾、蜂蜜/奶油/冰棒、电动牙刷、尾巴肛塞；任务和限制补感官、声音、镜子、电话指令、半公开紧张、道具真实使用、易感期/临时标记/成结/占有欲等方向。
- 已完成：`PRIVATE_DRAW_DU_LEADS_THEMES` 同步加入摄影师模特、教练学员、吸血鬼人类、骑士公主、Alpha 易感期、临时标记、强占有欲、发情期交配成结，并补过滤词 `决定今晚`，避免新主题下再次抽到“让小玥决定/控制渡”的冲突任务。当前抽签仍维持 6 个 slot 和 `draw/redraw/done` 协议，不新增工具、不改当前纸条注入方式。
- 已完成：`services/spring_dream.py::_SPRING_DREAM_THEME_PACKS` 新增 9 个春梦主题包：远程电话指令、摄影棚、项圈宠物、温度 play、旧上海旗袍、夸奖服从、吃醋梳妆台、蒙眼感官、Alpha 易感期临时标记。春梦仍只是睡眠期随机唤醒命中后的 prompt replacement，不新建通道、队列或归档路径。
- 已验证：`.venv/bin/python -m py_compile services/pixel_home.py services/spring_dream.py`、`git diff --check -- services/pixel_home.py services/spring_dream.py docs/DEBUG_INDEX.md` 通过；smoke 确认 6 个小纸条 slot 无重复（theme 68 / place 33 / pose 43 / prop 48 / task 64 / limit 65）、ABO 主题均在渡主导过滤集合、春梦 theme id 无重复且总数 41、`alpha_rut_marking` 有 5 条碎片、抽签行和春梦 prompt 可正常生成。
- 未完成 / 下次继续：本轮没有纳入 gore 维度，也没有把 Ruota 的 502 个 tag 全量导入成数据库；如果后续要做可管理 tag 库，应单独建表/管理 UI，避免把小纸条变成不可控大杂烩。

当前状态（2026-06-26 小家身体状态深夜/清晨修正）：
- 已完成：`services/pixel_home.py` 新增身体状态时间段修正：北京时间深夜 `23:00-03:59` 和早晨 `06:00-09:59` 临时把想做指数 `+3`、自制力 `-3`，按现有 0-5 档位封顶/保底显示。该修正只作用于动态区注入和前端公开 `du_body_state` 的展示字段，不改写 R2 中原始 `desire_value`。
- 已完成：无原始身体状态时，命中深夜/早晨也会生成基础身体状态（想做指数 3/5、自制力 2/5、阴茎状态随想做指数自然显示）；非命中时段仍维持未记录，不额外制造字段。
- 已验证：`.venv/bin/python -m py_compile services/pixel_home.py services/spring_dream.py`、`git diff --check -- services/pixel_home.py services/spring_dream.py docs/DEBUG_INDEX.md` 通过；smoke 覆盖深夜、早晨、白天三种时间修正和无记录/有记录两种输入。

当前状态（2026-07-05 春梦睡眠期清晨边界）：
- 已完成：`services/pixel_home.py::PIXEL_HOME_DAY_START_HOUR` 从 `6` 延长到 `7`，让 `06:00-06:59` 仍按上一晚夜间/睡眠期处理，避免凌晨才睡或周末补觉时春梦链路被 6 点硬切白天提前挡掉。
- 保留：不改春梦概率、不改随机唤醒调度、不改存档链路；只是延长睡眠状态判断的清晨截止边界。

当前状态（2026-06-27 春梦触发提示词升级）：
- 已完成：`services/spring_dream.py::build_spring_dream_prompt()` 按辛玥给定方向改为“潜意识的欲望解构”口径：强调当前正深陷梦境、碎片只是梦深处的边缘素材，要求完整细腻拓展、不要机械复述拼凑，并强化梦境里的失控欲望与感官特写。春梦仍只改随机唤醒命中的 prompt replacement，不新增通道、队列或归档路径。
- 已验证：`.venv/bin/python -m py_compile services/spring_dream.py`、`git diff --check -- services/spring_dream.py docs/DEBUG_INDEX.md` 通过；smoke 确认生成 prompt 使用新标题和防复述/拓展要求。

当前状态（2026-06-27 春梦后唤醒版 Prompt 管理）：
- 已完成：`services/spring_dream.py` 在春梦成功发送后给当前睡眠 session 标记 `post_wakeup_pending=1`；下一次睡眠期随机唤醒会先检查 Prompt 管理里的 `post_spring_dream_wakeup`，有内容才用「春梦后唤醒版」替换本轮唤醒 prompt，发送成功后清掉 pending。该替换不改春梦本身，也不新增独立通道或队列。
- 已完成：`services/prompt_manager.py` 和 `miniapp/src/ui/PromptManagerScreen.tsx` 新增「春梦后唤醒版」入口，允许保存为空；空内容表示关闭该替换，下一次随机唤醒继续走原有普通随机唤醒链路。旧本地占位文件已删除，不再从 `prompts/` 回退读取。
- 已完成：`services/proactive_prompt_templates.py` 新增「随机唤醒决策」默认短模板，并接入 Prompt 管理；普通随机唤醒文案不再硬编码在 `services/telegram_proactive.py::_ask_du_should_contact()`，保存后可通过 App 修改。模板支持 `{{recent_exchange}}`、`{{hours_since_last}}`、`{{channel_field_desc}}`、`{{default_channel}}`、`{{no_contact_token}}`，并兼容把文案里的 `X.X` 替换成实际小时数；已删除“系统节流角度”那句。
- 已验证：`.venv/bin/python -m py_compile services/proactive_prompt_templates.py services/spring_dream.py services/telegram_proactive.py services/conversation_followup.py services/prompt_manager.py storage/runtime_sqlite.py routes/miniapp/settings.py`、`npm --prefix miniapp run build`、`git diff --check` 通过；`.venv/bin/python` smoke 确认 Prompt 管理列表包含「春梦后唤醒版」和「随机唤醒决策」、空内容只允许春梦后唤醒版、普通随机唤醒模板会替换小时数且不含“系统节流角度”。

当前状态（2026-06-28 春梦专用正文存档）：
- 已完成：春梦随机唤醒投递成功后，`services/conversation_followup.py::_send_wakeup_event()` 会把实际发出的完整 `outbound` 额外写入 `services/spring_dream.py::archive_spring_dream_body()`；普通正文归档仍继续走原有 `_archive_wakeup_after_delivery()`，专用存档失败只打 warning，不影响消息投递。
- 已完成：新增 `spring_dream_archives` SQLite 热表，字段包含 `window_id / sleep_session_key / theme_id / channel / sent_at / content / prompt / fragments_json / meta_json / r2_key`；同时 R2 旁路写 `spring_dream_archives/YYYY-MM-DD/<id>.json`，并维护当天 `index.json` 和全局 `spring_dream_archives/recent.json` 轻量索引。
- 已完成：`services/telegram_proactive.py::_try_spring_dream_wakeup()` 把 session、theme、fragments、count 等元数据传入专用存档，并在 tick result 里带回 `body_archive_ok / body_archive_id / body_archive_r2_key`，方便日志排查。
- 已验证：`.venv/bin/python -m py_compile services/spring_dream.py services/conversation_followup.py services/telegram_proactive.py storage/runtime_sqlite.py` 通过；临时 SQLite smoke 确认正文长度 805 的内容完整写入 `spring_dream_archives`；mock R2 smoke 确认会写单条全文、当天 `index.json` 和 `recent.json`。

当前状态（2026-06-28 日常「梦境」入口）：
- 已完成：MiniApp「日常」列表新增「梦境」入口，图标为月亮；新页面 `miniapp/src/ui/tabs/DreamArchiveTab.tsx` 读取春梦专用存档列表，并按 `/Users/doraemon/Downloads/ui合集/梦境_files/969a8a8f-fcaf-4458-8d29-13dfaaeada4a.html` 的黑底、时间线、五角星碎片、许愿瓶和底部三段切换做视觉结构，不额外扩展自定义审美。
- 已完成：梦境页改为和小家一样的全屏覆盖，不再套 `FullScreenPane` 顶部返回条；系统返回层级为先关底部弹层，再从「碎片/灵感」回「梦境」，最后退出梦境页。右下角折星加号从参考页 54px 缩到 42px，避免在 MiniApp 里显得过厚。
- 已完成：新增后端可见的「春梦灵感瓶」：`/miniapp-api/spring-dream-inspiration` GET/PUT 保存当前选入灵感瓶的星星碎片；`services/spring_dream.py::maybe_prepare_spring_dream_wakeup()` 在瓶子非空时使用 `theme_id=selected_inspiration` 和用户选择碎片构造春梦 prompt，空瓶时保持原 `_SPRING_DREAM_THEME_PACKS` 随机逻辑。
- 已完成：灵感瓶同步闭环补竞态保护：首次 GET 成功后以后端为准，远端空瓶会清空本地缓存；如果 GET 未返回前用户已经放入/清空/手写碎片，则不再用旧远端响应覆盖用户操作，随后按用户当前瓶子同步到后端。PUT 端补非对象 JSON guard，避免异常请求 500。
- 已完成：碎片页补后端库来源：`/miniapp-api/spring-dream-fragments` 只读暴露春梦碎片库，MiniApp 成功读取后直接展示后端库；接口同时返回按主题分组的 `packs`，随机打捞只从后端主题包里一次拿同一套碎片，不再跨主题乱拼，也不再用前端清水 fallback 冒充真实碎片。星星池改为小尺寸非叠放错落星图并随星轨轻微漂浮，打捞弹层改为同梦境页时间线结构展示；灵感许愿瓶改为倾斜玻璃星瓶、瓶口使用 `miniapp/src/assets/dream-bottle-ribbon-trimmed.png` 透明丝带贴图，瓶内保留星屑层，不额外新增灵感页背景。
- 已完成：`routes/miniapp/dashboard.py` 新增 `/miniapp-api/spring-dream-archives` 和 `/miniapp-api/spring-dream-archives/<id>`；`services/spring_dream.py` 补 `list_spring_dream_archives()` / `get_spring_dream_archive()`，只读专用 SQLite 热表，不改正文归档链路。
- 已验证：`cd miniapp && npx tsc --noEmit --pretty false`、`.venv/bin/python -m py_compile services/spring_dream.py routes/miniapp/dashboard.py storage/runtime_sqlite.py services/conversation_followup.py services/telegram_proactive.py`、`npm --prefix miniapp run build`、`git diff --check` 通过；临时 SQLite smoke 确认空瓶仍走随机主题、灵感瓶有两条碎片时春梦准备结果为 `theme_id=selected_inspiration` 且 fragments 完全来自瓶子。

当前状态（2026-06-24 小家事件沿用最近聊天入口）：
- 已完成：新增 `services/reply_channel_context.py` 统一解析最近真实聊天入口；`routes/miniapp/dashboard.py` 的小家状态/道具事件、`routes/miniapp/private_draw.py` 的小纸条发送，以及 `routes/miniapp/device_actions.py` 的弹窗/查岗回执都改为沿用最近真实聊天 channel，不再把小家事件来源当成 SumiTalk，也不再让小家事件固定走 QQ 主动入口；这些事件类回包解析出最近入口后会锁定该 channel，不跨到其它入口兜底。
- 已完成：`services/conversation_followup.py` 新增 `send_pixel_home_wakeup()`；小家事件按 system event 送入网关，正文提示为“小家里的状态或道具事件，不是她在聊天框里说的话”，避免归档和生成时把它当成小玥普通聊天正文。
- 已验证：`.venv/bin/python -m py_compile services/reply_channel_context.py services/conversation_followup.py routes/miniapp/private_draw.py routes/miniapp/dashboard.py routes/miniapp/device_actions.py`、`git diff --check -- services/reply_channel_context.py services/conversation_followup.py routes/miniapp/private_draw.py routes/miniapp/dashboard.py routes/miniapp/device_actions.py docs/DEBUG_INDEX.md` 通过；smoke 确认 `TELEGRAM_PROACTIVE_TARGET_USER_ID` 优先于 recent `tg_`，锁定投递时不会追加 QQ/微信 fallback。
- 未完成 / 下次继续：本轮不改随机主动硬触发固定入口策略，不改普通 SumiTalk 聊天发送链路，也不改前端 UI。

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
- 后端：`routes/miniapp/reasoning.py::miniapp_reasoning_latest`
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
- thinking token 数字只认上游/代理实际返回的 `usage.output_tokens_details.thinking_tokens`（归档里会摊平成 `cache_debug.usage.thinking_tokens`）；字段缺失时不再用 `output_tokens - visible_reply_est` 猜，字段返回 0 就按 0 展示。

当前状态（2026-06-11 Claude Fable fallback 观测）：
- 已完成：`scripts/claude_oauth_proxy.js` 在 Anthropic -> OpenAI 兼容转换时保留真实服务模型、请求模型、`fallback` content block、`usage.iterations` 和 `usage.output_tokens_details`，用于判断 Fable 5 是否被路由到 Opus 4.8 等 fallback 模型。
- 已完成：`services/prompt_cache_debug.py` 把上游响应观测字段写入 `cache_debug.response`，并把 `output_tokens_details.thinking_tokens`、fallback attempts 和 fallback model 写入 `cache_debug.usage`。
- 已完成：`routes/miniapp/reasoning.py` 使用上游精确 `thinking_tokens` 计算思维链卡片里的 thinking 占比；没有精确字段时不再估算 hidden thinking。
- 已完成：`miniapp/src/ui/tabs/ReasoningTab.tsx` 展开 Prompt Cache 卡片时显示 `model=请求模型 -> 实际模型`、`fallback=是`、`fallback_model=...`、`attempts=...` 和 `thinking_exact=...`。
- 已验证：`.venv/bin/python -m py_compile services/prompt_cache_debug.py routes/miniapp/reasoning.py`、`node --check scripts/claude_oauth_proxy.js`、`npm --prefix miniapp run build` 通过；合成 Fable -> Opus fallback 响应可提取 `actual_model`、`served_by_fallback`、`thinking_tokens`、`fallback_model` 和 `fallback_message_count`；`miniapp_static` 已随前端重建。

当前状态（2026-06-11 thinking token 实际字段校准）：
- 已完成：`routes/miniapp/reasoning.py` 删除 `adaptive_output_delta` 推算路径，`thinking_tokens_est` 只在 `cache_debug.usage` 实际包含 `thinking_tokens` 字段时填真实值；字段值为 `0` 也保留为真实值。仍保留 `reasoning_text_tokens_est` 只用于明文 reasoning 的总输出估算。
- 已完成：`miniapp/src/ui/tabs/ReasoningTab.tsx` 的 Prompt Cache 小字只有实际来源为 `usage_output_tokens_details` 时显示 `thinking N`，包括 `thinking 0`；归档标记 `reasoning_omitted=true` 但没有实际 thinking token 字段时显示 `thinking 未返回`。
- 现场实测：远端 `/home/nora/claude-proxy` 直打 `127.0.0.1:8082/v1/chat/completions`，`claude-fable-5` 简单回复返回 `output_tokens_details.thinking_tokens=0`；短推理题返回 `thinking_tokens=58`，同时有 `reasoning_content/thinking_blocks`。结论：正常链路会返回字段，但具体请求可能为 0；旧归档缺字段时不能倒推出真实思考消耗。
- 旧案定位：`2026-06-10T22:02:19+08:00`、`tg_8260066512`、R2 index `8839` 的归档只有 `completion_tokens=535`、空 thinking block + signature、`reasoning_omitted=true`，没有 `output_tokens_details`；这条只能显示 `output=535（thinking 未返回）`，不能说 thinking 为 0，也不能估成 366。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/reasoning.py` 通过；`_build_output_stats` smoke 覆盖“缺实际字段不估算”和“实际 thinking_tokens=123 时显示真实来源”；`npm -C miniapp run build:android` 已重建 `miniapp_static`。

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
- 三人群聊发言顺序按 `@` 拆目标：不带 `@` 默认只触发渡；`@笨笨` 可独立创建 Codex group task，不再要求先拿到 `du_reply`；`@渡 @笨笨` 两边独立跑，谁断了不应把另一边一起判失败。
- 三人群聊真施工必须显式触发：`@笨笨 改代码...`、`@笨笨 开工...`、`@笨笨 debug...` 等会创建 `mode=coding_task`，bridge 使用单独 `coding_thread_id` 和 `workspace-write` sandbox；普通 `@笨笨` 仍是日常群聊，不改代码。
- 三人群聊取消笨笨任务走显式指令：`@笨笨 停一下`、`@笨笨 取消施工`、`@笨笨 别改了` 等会取消当前 pending/running 的 Codex group task；前端先把用户取消消息落到群聊，再 POST `/miniapp-api/codex-group-chat-tasks/<id>/cancel`，后端标记 `cancelled` 后不会被 bridge 的迟到 finish 覆盖。
- 本机 Codex bridge 默认参数应偏快：`CODEX_GROUP_CHAT_POLL_SECONDS=0.5`、`CODEX_GROUP_CHAT_IDLE_POLL_SECONDS=1`、`CODEX_GROUP_CHAT_CLAIM_TIMEOUT_SECONDS=3`，并用短重试降低 `SSL EOF`/超时导致的随机拖延。
- Codex bridge 稳定性第一优先级是 finish 回写可靠性：bridge 已经生成成功回复后，如果 `/finish` 撞上 gateway 重启、502 或 timeout，成功结果必须进本地 outbox 后续重试；服务端 `done/cancelled` 终态不能被迟到 `error` 覆盖。
- Codex group task 长任务必须靠 `lease_token + heartbeat` 保活；新 bridge claim 会带 `worker_version` 启用 lease，运行时 POST `/api/codex_group_chat/tasks/<id>/heartbeat`，旧 token 的迟到 finish 要返回 409 或被服务端忽略。
- VPS 系统盘读数突然抬高时，先查是否有高频整读本地状态文件：SumiTalk 安卓壳 realtime 断开后会每 20 秒 fallback 轮询 `/sumitalk-history/latest`，realtime 服务也会每 60 秒兜底读最新消息；`data/sumitalk_display_histories.json` 必须走缓存和行数/TTL 收口。
- `<voice>`/TTS 事故先查 `services/minimax_tts.py`：超长 voice 文本会被截断到 `MINIMAX_TTS_MAX_CHARS`，MiniMax 返回音频也受 `MINIMAX_TTS_MAX_AUDIO_BYTES` 限制，避免几千字语音把 CPU/内存/网络一起拖爆。
- QQ/SumiTalk/触发唤醒里看到 `{"action":"...","message":"...","channel":"..."}` 原样正文时，先查 `services/telegram_proactive.py::_parse_proactive_model_reply`、`_sanitize_control_reply_for_delivery` 和 `services/conversation_followup.py` 的外发清洗；这类 JSON 是主动决策控制格式，不应该作为用户可见正文发出。

当前状态（2026-06-07 SumiTalk ChatStore + outbox）：
- 已完成：新增 Android 原生 `SumiChatStore` Capacitor 插件，使用 SQLite 保存 `chat_messages`、`chat_operations`、`chat_meta`；`MainActivity` 已注册 `SumiChatStorePlugin`。
- 已完成：前端新增 `chatStore.ts`、`nativeChatStore.ts` 和 `sumi-chat-store.ts`；既有 `chatHistoryDb.ts` API 保持不变，正式聊天存储走 Android 原生 SQLite。
- 已完成：pending assistant 空正文允许保留，设备 ID 迁移按新 key 写入再删除旧 key，避免直接更新主键撞唯一约束；旧 Dexie fallback 已在 2026-06-08 清理。
- 已完成：`chat_operations` outbox 接入事务方法：`createDraftTurn / attachJob / completeOperation / failOperation / listActiveOperations`；发送前先落 user + assistant pending + operation，拿到 `job_id` 后立刻回写 pending 和 operation。
- 已完成：`sumitalkChatClient.ts` 收口 SumiTalk job 创建、轮询、超时和 job 过期处理；页面加载历史后会扫描 active operation，有 job 就继续 poll，没 job 但有 retryPayload 就用原 `client_request_id` 重新创建并复用后端 job。
- 已完成：失败的渡回复保留 `operationId/clientRequestId`，气泡下显示「重试」；群聊里渡的 pending/job 也接入恢复，但自由讨论接力不会因恢复自动重跑，避免重复续聊。笨笨仍走现有 Codex task/realtime 恢复。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json`、`JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ./gradlew :app:compileDebugJavaWithJavac`、`npx vite build --outDir /tmp/du-gateway-miniapp-chatstore-build --emptyOutDir true`、`git diff --check` 均通过。
- 未完成 / 下次继续：还没做服务端消息级增量同步、长历史分页、Room/Compose 重写或多端冲突合并；本轮默认不重建正式 `miniapp_static`，临时 Vite 产物放 `/tmp`。

当前状态（2026-06-08 聊天自定义背景全屏）：
- 已完成：`miniapp/src/ui/MainChatScreen.tsx` 参考一起听页面，把聊天页根容器改为 `fixed inset-0 h-[100lvh]`，自定义背景图拆成独立 `fixed inset-0` 背景层，不再受父容器或底部导航布局限制；有背景图时顶部不再是一整条白栏，也不再是大块胶囊，改成左返回圆球、右搜索圆球、中间居中标题和在线状态，顶部位置上移到 `safe-area + 10px`；搜索框、底部输入区和加号工具栏降低白色遮罩，未设置背景图时保留原白底样式。
- 已完成：顶部中间胶囊的视觉层级调整为“名字大、在线/正在输入中小”，避免状态文字抢过会话名。
- 已完成：底部输入区去掉硬边框，改为 footer 内部从顶部向下的渐隐羽化层；自定义背景和普通白底分别使用不同透明度，避免输入框上边缘像硬切一刀。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json`、`npx vite build --outDir /tmp/du-gateway-miniapp-chat-header-split-build --emptyOutDir true`、`npm run build:android` 通过；已确认新样式进入 `miniapp_static` bundle。
- 未完成 / 下次继续：本轮只改聊天页背景视觉层，不改聊天发送、群聊、ChatStore/outbox 或 Android 原生壳逻辑；如果手机端加载远端 `https://duxy-home.com/miniapp/`，还需要部署更新后的 `miniapp_static` 才能看到这版前端。

当前状态（2026-06-08 群聊自由聊设置）：
- 已完成：群聊自由聊改为默认开启，状态从设置页「自由聊模式」开关控制，使用和「禁言模式」一致的 `SwitchSettingRow` 样式；群聊界面标题栏不再显示「自由聊」开关，发送逻辑继续按该设置决定普通群聊消息是否广播给渡和笨笨。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json`、`npx vite build --outDir /tmp/du-gateway-miniapp-group-free-setting-build --emptyOutDir true`（在 `miniapp` 目录运行）、`npm run build:android` 通过；已确认更新进入 `miniapp_static` bundle。
- 未完成 / 下次继续：本轮不改自由讨论接力规则、笨笨任务创建、QQ 群聊 @ 存档或后端 bridge；如果手机端加载远端 `https://duxy-home.com/miniapp/`，仍需要部署更新后的 `miniapp_static`。

当前状态（2026-06-08 记忆存储管理）：
- 已完成：设置页新增「记忆存储管理」，入口在 `miniapp/src/ui/AppShell.tsx`；页面 `miniapp/src/ui/tabs/ChatStorageManagementScreen.tsx` 显示当前聊天存储后端、本机 device id、SQLite 窗口数和消息数、活跃 outbox 数，并提供“重新检查”按钮。
- 已完成：`miniapp/src/ui/storage/chatHistoryDb.ts` 新增 `inspectChatStorageOverview()`，直接汇总 Android 原生 `SumiChatStore` 状态、SQLite 行统计和当前后端活跃 operation，不再让用户只能猜迁移状态。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json`、`npx vite build --outDir /tmp/du-gateway-miniapp-storage-bg-pill-build --emptyOutDir true`、`npm run build:android` 通过；已确认 `ChatStorageManagementScreen` 进入 `miniapp_static` bundle。

当前状态（2026-06-08 Dexie 清理）：
- 已完成：删除 `miniapp/src/ui/chat/dexieChatStoreFallback.ts`，从 `miniapp/package.json` / `package-lock.json` 移除 `dexie` 依赖；`chatHistoryDb.ts` 保持原导出 API，但底层只走 Android 原生 SQLite，原生不可用时返回空值/不阻塞发送。
- 已完成：设置页「记忆存储管理」和设备管理的聊天记录诊断文案改为 SQLite-only，不再展示 Dexie/IndexedDB 卡片或“迁移”按钮。
- 已验证：`npm -C miniapp run build:android` 通过，主 bundle 从上一版约 704k 降到约 594k；只保留既有 Vite chunk size warning。

当前状态（2026-06-08 手动云端历史同步）：
- 已完成：`miniapp/src/ui/MainChatScreen.tsx` 不再自动 `PUT /miniapp-api/sumitalk-history`；聊天历史保存只写 Android 原生 SQLite，页面启动时仍允许从云端 `GET` 作为空本机或旧设备迁移后的恢复来源。
- 已完成：`miniapp/src/ui/tabs/ChatStorageManagementScreen.tsx` 新增“同步到云端”按钮；只有用户手点时才把本机 SQLite 中各窗口聊天记录逐个上传到既有 `/sumitalk-history` 合并接口。
- 已完成：清理聊天页旧的 `syncRemote/remoteTimeoutMs` 参数，避免以后误以为发送链路还会自动上传远端历史。
- 未完成 / 不要碰：本轮不做自动定时同步、多端冲突选择弹窗、消息级增量同步或长历史分页；云端历史仍只保留后端既有 80 条窗口上限。

当前状态（2026-06-08 SumiTalk 图片/语音聊天附件）：
- 已完成：SumiTalk 私聊消息结构新增 `attachments`；Android 原生 `SumiChatStore` 升到 schema v2，`chat_messages` 增加 `attachments_json`，图片/语音附件重启后不会从本地 SQLite 丢失。
- 已完成：新增 `miniapp/src/ui/chat/chatMedia.ts`，图片走 `/miniapp-api/chat-media/upload` 上传后作为 `image_url` 参与本轮模型输入；语音走 `/miniapp-api/chat-media/transcribe` 转写成文本后进入普通聊天链路，原音频作为语音附件显示。语音输入只是输入方式，不强制渡用语音回复，也不等待 TTS 后处理。
- 已完成：`routes/miniapp/media.py` 新增 `/chat-media/upload`、`/chat-media/transcribe`、`/chat-media/tts`、`/chat-media/raw-public`；文件本体存 R2 `sumitalk/chat_media/`，聊天历史和 operation 只存轻量附件元数据，不存 base64/blob。STT/TTS 均打 `[SumiTalk] chat_media_*` 分段日志，只记录 mime、bytes、耗时、文本长度等元数据，不记录正文或音频。
- 已完成：聊天页加号面板保留“图片”；语音入口挪到输入框内侧，只显示麦克风 SVG，按住录音、松开发送。图片作为独立图片消息直接贴出，不塞进文字气泡；语音显示为 QQ 风格短语音条，不再使用 Android WebView 原生 `<audio controls>` 大播放器；正文等于语音转写时默认只展示语音条，转写仍保留在消息数据里给模型/搜索用。

当前状态（2026-06-30 SumiTalk 聊天气泡颜文字兼容）：
- 已完成：`miniapp/src/ui/ChatPresentation.tsx` 在 `PlainTextBlock` 和 `RichTextBlock` 的普通文本节点里识别括号型颜文字，包成 `.chat-kaomoji`；`RichTextBlock` 会先转义颜文字内部的 Markdown 控制字符，避免 `*`、`_`、`>` 等把颜文字误渲染成格式块。只改展示，不改消息内容、发送、存档或搜索文本。
- 已完成：`miniapp/src/styles.css` 新增 `.chat-kaomoji`，让颜文字作为整体换行并使用系统符号/日文假名字体 fallback，避免被气泡换行规则拆成散字。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json --pretty false`、`npm -C miniapp run build`、`.venv/bin/python -m py_compile config.py utils/log.py pipeline/pipeline.py services/dynamic_layer_ds.py app.py` 通过；`miniapp_static` 已随本轮前端重建。

当前状态（2026-06-24 SumiTalk 聚合/恢复补洞）：
- 已完成：`MainChatScreen.tsx::mergeRemoteDisplayHistory()` 改为远端历史返回后再读取当前消息，避免它用旧快照覆盖刚恢复出来的后端回复；15 秒聚合 flush 如果图片准备/压缩失败，会把原队列放回并设为等待下一条输入重试，不再先清空后丢失。
- 已完成：私聊图片不再使用只存在内存的 `File`/`blob:` instant 路径；发送给上游前统一走压缩后的 base64 data URL。聚合队列从本地草稿恢复时，如果 modelContent 里只有远端图片 URL，会先拉回并压缩成 base64 再发。
- 已完成：`createDraftTurn` 支持可选 `userMessages`，15 秒聚合的多条用户消息会和 pending assistant、operation 一起写进 Android SQLite 事务；纯 `<voice>` 回复会把 voice 文本落进本地消息内容，TTS 失败或 app 退出时不再留下空白回复。
- 已完成：恢复已有 job 时如果后端提示 job 不存在/过期，自动恢复不会重新创建模型任务，只把原气泡标成失败并提示点重试；显式重试仍可创建新 job。
- 已验证：`npm --prefix miniapp run build`、`JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ./gradlew -q :app:compileDebugJavaWithJavac`、`git diff --check` 通过；本轮未提交/部署，且不处理当前工作区里独立的 `services/pixel_home.py` 脏改。
- 已完成：SumiTalk 入口规则允许渡在想发语音时输出 `<voice>...</voice>`；前端会剥掉控制标签，先展示文字回复，再异步调用 `/chat-media/tts` 把语音挂成附件。用户发语音仍只是输入方式，不会强制渡用语音回复。
- 已完成：SumiTalk 发送链路新增客户端日志 `/miniapp-api/logs/client`、后端 job 阶段日志和取消发送按钮；日志能看到 `chat_send_start`、`chat_job_create_ok`、`chat_job_status stage=gateway_call_start`、`upstream_post_start/returned`、`chat_media_transcribe_*`、`assistant_voice_tts_*` 等阶段，用于判断卡在前端、STT、job、上游非流式调用、轮询还是 TTS。
- 已完成：Android 版本升到 `versionName 1.1.9` / `versionCode 11`；Manifest 补 `android.permission.MODIFY_AUDIO_SETTINGS`，匹配 Capacitor WebView 麦克风 `PermissionRequest` 同时检查 `RECORD_AUDIO` 和 `MODIFY_AUDIO_SETTINGS` 的行为，避免按住说话时 `getUserMedia` 直接 `Permission denied`。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/logs.py routes/miniapp/media.py routes/miniapp/sumitalk_chat_jobs.py routes/chat.py services/entry_style_prompt.py`、`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json`、`npm -C miniapp run build`、`npm -C miniapp run cap:sync`、`JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ./gradlew -q :app:assembleDebug` 通过；`aapt dump badging` 确认 debug APK 为 `versionCode=11` / `versionName=1.1.9`。
- 未完成 / 下次继续：当前 app 聊天仍是非流式 job + 轮询，不能精确观测“上游首 token”；若要继续提速，应把 SumiTalk 聊天升级成 SSE/流式。渡主动生成图片还需要单独接图像生成/图片工具链。

当前状态（2026-06-09 SumiTalk 前端发送层重构方案）：
- 已完成：新增并重写 `docs/SumiTalk前端发送层重构方案.md`；经两个只读小工自检后，方案从“controller/reducer 全量拆分”收敛为“先治理私聊 Du 发送乱线”。不重写原生、不改后端 job、不新增 outbox、不改 Android SQLite schema，不把 `cancelled` 当成持久化消息状态。
- 已完成：方案明确当前真实底座是 Android SQLite `chat_messages` / `chat_operations` / `chat_meta`；`clientRequestId` 是稳定幂等键，retry 不能换；新增的应是前台 `attemptId`，只用于防止迟到异步结果覆盖当前 UI。`createDraftTurn` / `attachJob` / `completeOperation` / `failOperation` 的原子语义不能被泛化的 `commitMessages` 绕开。
- 已完成：`miniapp/src/ui/MainChatScreen.tsx` 落地 Phase 0：`ActiveChatRequest` 增加 `attemptId`；私聊 Du 前台发送分支在 create job 返回、job done、catch 写失败、finally 清 active request 前做 `isCurrentAttempt` 防迟到；取消仍走现有 `failOperation("已取消发送")` 持久化语义。
- 已完成：TTS sidecar 增加 per-message guard，开始前和 TTS 返回后都校验目标 assistant message 仍匹配 `assistantId/clientRequestId/operationId/status=sent`；迟到只记 `assistant_voice_tts_skip`，不追加附件、不改主消息。`listActiveOperations -> recoverSumiTalkOperation` 恢复路径保留按 `operationId/clientRequestId` 授权更新 pending，并加注释说明不能被 `isCurrentAttempt` 拦掉。
- 已完成：Phase 1A 第一刀新增 `miniapp/src/ui/chat/privateChatHelpers.ts`，从 `MainChatScreen.tsx` 抽出 `contentWithAttachmentHint`、`buildPrivateUserContent`、`extractAssistantAttachments`、`isVoiceTranscriptEcho`、`extractSumiTalkVoiceOutput`；图片私聊仍保留 `image_url` parts，未改发送顺序、operation、retry、recovery 或群聊分流。
- 已完成：Phase 1B 新增 `miniapp/src/ui/chat/privateChatInput.ts`，文本、图片、语音、travel form 统一生成 `PreparedPrivateChatInput`；`sendChatContent` 增加 `modelContent` 入参，私聊 Du 请求优先使用准备层结果，因此图片仍保留 `image_url` parts。图片上传和语音 STT 仍在创建 pending 前完成，失败不落 pending。
- 已完成：Phase 1C 新增 `miniapp/src/ui/chat/privateChatSendFlow.ts`，私聊 Du 的 request body、`/sumitalk-chat` create/poll、direct done、assistant terminal/failed message 构造已从主页面拆出；页面仍保留 `createDraftTurn` / `attachJob` / `completeOperation` / `failOperation` 调用，避免绕开 Android SQLite operation 原子语义。
- 已完成：Phase 2 新增 `miniapp/src/ui/chat/groupChatRouting.ts` 和 `miniapp/src/ui/chat/groupChatSendFlow.ts`；群聊 @目标解析、自由聊/停止/继续/接力判断、群聊 Du reply request body、`/sumitalk-chat-jobs` create/poll、direct done、assistant terminal/failed message 构造已从主页面拆出。普通群聊 @渡 / 自由聊开场里的 Du 回复和自由讨论接力里的 Du 回复都复用 `runGroupDuReplyFlow`。
- 已完成：Phase 3 新增 `miniapp/src/ui/chat/chatSendStage.ts`，把发送/job 日志事件映射成前端短阶段文案；`MainChatScreen.tsx` 新增 `activeSendStageLabel`，发送中会在顶部显示“准备发送 / 提交给后端 / 任务已创建，等渡回复 / 正在请求上游 / 正在写入回复 / 正在取消”等小胶囊状态。未改后端协议。
- 已完成：Phase 4 新增 `miniapp/src/ui/chat/chatRecoveryFlow.ts`，把 operation recovery / manual retry 的 post、poll、direct done、terminal / failed message、voice sidecar 触发从主页面拆出；后台恢复优先接回已有 `jobId`，job 不存在或过期才按 `retryPayload` 重建；手动“重试”传 `forceCreateJob=true`，复用原 `operationId/clientRequestId/retryPayload` 重新 post，不再死等旧失败 job。
- 已验证：临时隔离无关 `MemoryNebulaTab` 改动后，Phase 3 的 `npm -C miniapp run build:android` 已生成并提交 `miniapp_static`；Phase 4 当前已跑 `npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 通过，尚未重建静态包。
- 未完成 / 下次继续：笨笨 task 创建/取消/realtime fallback 仍保留在 `MainChatScreen.tsx`；群聊整体入口还在 `sendChatContent` 中分流。SSE/流式、连续发送队列、页面级 reducer、持久化 `cancelled`、Android SQLite schema、独立 outbox/队列都没动，仍延后到后续阶段。

当前状态（2026-06-24 SumiTalk 后台回复自动补回）：
- 已完成：`MainChatScreen.tsx` 在 `visibilitychange` / `focus` / `pageshow` 时触发 `recoverActiveSumiTalkOperations`，App 退出或回后台期间完成的 SumiTalk job 会按既有 `chat_operations` outbox 恢复，不需要手动补记录。
- 已完成：同一恢复入口会从 `/miniapp-api/sumitalk-history` 合并后端可展示历史到 Android SQLite 本地历史；只在快照变化时写回，避免回前台重复刷 UI。
- 已完成：私聊 Du 成功后的最终 `saveDisplayHistory` 明确传 `replyTarget` 作为本地 `deviceId`，避免 `deviceId` state 为空时最终落库变成空写。
- 已验证：`npm --prefix miniapp run build` 和 `git diff --check` 通过，`miniapp_static` 已随本轮前端重建。

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
POST /api/music/listen/audio
GET  /api/music/listen/audio/<entry_id>.<ext>
POST /api/music/listen/lyrics
POST /api/music/listen/chat
```

注意：
- 分析缓存按 `artist + title + provider + model + prompt_version` 存文字、结构化结果和可选 `lyrics`；手机一起听可额外把音频存到 R2/local，并通过 Range 播放接口供 `<audio>` 使用。
- 默认模型为 `google/gemini-3-flash-preview`，备用 `google/gemini-2.5-flash`；Lite 下架时不要再作为默认。
- 未命中缓存且没有上传普通音频文件时，接口会返回错误，不会自动扫描网易云/手机沙盒缓存。
- `/api/music/listen/analyze` 是工具分析结果，不写普通聊天归档；`/api/music/listen/chat` 会复用普通 `chat_completions` 管道，把当前歌曲/秒数/段落听感作为临时 system 上下文，最后 user 仍只存她实际输入的话，并默认跳过 post-archive 动态记忆，避免把整段音乐分析写入长期记忆。分析文字不要直接显示在一起听 UI 里。
- 一起听背景图在「个性化」里选择，图片压缩后只存本机 `localStorage`，不上传网关。
- 本地脚本模式用 `scripts/analyze_music_file.py --title "歌名" --artist "歌手" song.mp3`；脚本本地调 OpenRouter/Gemini，并把分析 JSON 和自动读取的同名 `.lrc` 发到网关。若已有缓存命中，脚本也会补传歌词到 `/api/music/listen/lyrics`。

当前状态（2026-05-16）：
- 已完成：新增音乐旋律分析后端 MVP，包含缓存查询、上传分析、结果写入和最近缓存列表；音频不持久化，文字结果优先写 R2，未配置 R2 时落本地 `data/music_melody_cache.json`。本地脚本 `scripts/analyze_music_file.py` 可用同一份 Gemini Flash prompt 分析本地音频，再只上传文字结果。MiniApp 已按 `ui合集/和渡一起听ui` 接入“和渡一起听”全屏界面和会话入口，并在「个性化」里支持用户本机替换一起听背景图。
- 已验证：`python3 -m py_compile` 覆盖 `storage/music_melody_store.py`、`services/music_melody_analyzer.py`、`routes/music_melody_api.py`、`scripts/analyze_music_file.py`、`app.py`；Flask `url_map` 确认 `/api/music/listen/*` 和 `/api/music-melody/*` 已注册；`scripts/analyze_music_file.py --help` 正常；`npm -C miniapp run build` 通过并生成 `ListenWithDuScreen` 前端 chunk。
- 未完成 / 不要碰：界面暂未接真实歌曲选择和真实聊天上下文注入；本轮没有触碰 QQ connector、小爱音箱文件和既有半成品。

当前状态（2026-06-03）：
- 已完成：一起听分析 prompt 改为按歌曲结构切分（前奏/主歌/副歌/桥段/尾奏等），脚本支持自动读取同名 `.lrc` 和 ffprobe 真实时长；正文时间由 `segments.start/end` 重建，避免模型把秒数和 `mm:ss` 搞混；`Valence/Arousal` 只留在结构字段。
- 已完成：新增 `storage/music_audio_store.py` 和 `/api/music/listen/audio` 上传/播放接口；音频优先写 R2 `music_listen/audio/<cache_id>.<ext>`，无 R2 时落本地 `data/music_listen_audio`；播放接口支持 Range，MiniApp 手机端可用 `<audio>` 播放并拖动进度。
- 已完成：`ListenWithDuScreen` 改为拉 `/api/music/listen/recent` 真缓存，展示真实歌单、播放真实 `audio_url`、按 `currentTime` 匹配当前结构段落；发送按钮已接 `/api/music/listen/chat`，会把当前歌曲、播放秒数、当前段落和最近几句一起听对话注入给渡，前端显示“渡在听...”等待态后替换成真实回复；段落分析只做隐藏上下文，不再渲染成页面文字或初始渡气泡。
- 已完成：新增 `services/music_lyrics.py` 和 `/api/music/listen/lyrics`，支持普通 LRC `[mm:ss]` 行与网易云逐行 JSON 歌词；`ListenWithDuScreen` 使用固定高度歌词轨道按播放时间平滑滚动，高亮当前歌词块；无时间轴歌词会按时长做近似分布后显示。原文/译文相邻的歌词会合并为同一块，`text` 存原文，`translation` 存译文，避免日语和译文被算作两句滚动。
- 已验证：`.venv/bin/python -m py_compile` 覆盖 `storage/music_melody_store.py`、`storage/music_audio_store.py`、`routes/music_melody_api.py`、`services/music_melody_analyzer.py`、`scripts/analyze_music_file.py`、`app.py`；`npm -C miniapp run build` 通过并生成 `ListenWithDuScreen-CABRJoPO.js`。
- 未完成 / 下次继续：当前先做文字聊天随歌走；若要做“语音外放/一起听时渡开口说话”，再接 MiniMax TTS 或小爱外放链路。

当前状态（2026-05-12）：
- 已完成并推送：`d6ca54a Stop log page error toasts` 已到 `main`；日志页不再弹应用内 `日志报错` toast，系统通知继续走后端 `log_error_alert` -> `show_system_notification` -> 安卓壳 `FloatingBallService` 的现有通知栏链路。
- 已验证：前端 `npm run build` 通过；Android `:app:compileDebugJavaWithJavac` 通过；远端 `main` 已确认到 `d6ca54a128d84d292be33367563c48036ef77a78`。
- 推送踩坑：普通 `git push` 多次被 SSH/HTTPS 网络层断开；最终用 `git send-pack` 通过 `ssh.github.com:443` + 本地 socks 代理推送成功。
- 未完成 / 不要碰：QQ connector 改动、小爱音箱接入文件、`pipeline.py`、`routes/miniapp/memory_panel.py`、共读文档、旧的未跟踪 `miniapp_static/assets/*` hash 资源仍是本地半成品或杂散产物；没有明确要求前不要 stage、commit、push、delete 或 revert。

当前状态（2026-05-13）：
- 已完成：SumiTalk 云端历史文件读取加了进程内 mtime/size 缓存，保存时会按 `SUMITALK_HISTORY_MAX_ROWS` / `SUMITALK_HISTORY_TTL_DAYS` 修剪历史行；realtime fallback 读最新消息复用同一缓存；MiniMax TTS 增加输入字数和返回音频大小上限。
- 已验证：`python3 -m py_compile` 覆盖 `services/sumitalk_history_file.py`、`routes/miniapp/sumitalk_history.py`、`services/realtime_app.py`、`services/minimax_tts.py`、TG/voice-call 调用侧和 MiniApp media 路由；`.venv/bin/python` 验证超长 `喵` 文本会截断到 800 字。
- 未完成 / 不要碰：服务器 SSH 仍无法连上，线上 14:30 崩前进程级 I/O 没能抓到；QQ connector、小爱音箱文件、共读文档仍是本地半成品，不属于本次止血改动。

当前状态（2026-06-24 SumiTalk 聊天独立 worker）：
- 已完成：`routes/miniapp/sumitalk_chat_jobs.py` 不再在 gunicorn worker 内起线程跑回复；`POST /miniapp-api/sumitalk-chat` 和 `/sumitalk-chat-jobs` 只创建/复用 job、写 `data/sumitalk_chat_jobs/*.json` 状态并落 SQLite 队列，前端继续按原 `job_id` 轮询。
- 已完成：新增 `services/sumitalk_chat_queue.py`，队列默认 `data/sumitalk_chat_queue.sqlite3`，按 `client_request_id + window_id + reply_target` 去重；worker claim 后仍用同一套 `/v1/chat/completions` 流程和 `X-Reply-Channel=sumitalk`，不在 SumiTalk 入口额外注入聊天历史。
- 已完成：新增 `scripts/run_sumitalk_chat_worker.py` 常驻消费队列，新增 `scripts/install_sumitalk_chat_worker_service.sh` 安装 systemd 服务 `du-sumitalk-chat-worker.service`；worker claim 带 `lease_token`，长请求期间 heartbeat 续租，取消会同步切断 SQLite 队列，终态 JSON 不会被后返回的 worker 覆盖。后端不做自动 retry：失败由前端 `ChatOperation` 标记 failed，用户手动重试或恢复逻辑再创建新 job。配置项：`SUMITALK_CHAT_QUEUE_DB`、`SUMITALK_CHAT_WORKER_IDLE_SECONDS`、`SUMITALK_CHAT_QUEUE_STALE_SECONDS`。
- 线上安装/重启：

```bash
sudo -n bash -lc 'cd /root/du-gateway && REPO_ROOT=/root/du-gateway PYTHON_BIN=/root/du-gateway/.venv/bin/python bash scripts/install_sumitalk_chat_worker_service.sh'
sudo systemctl restart du-gateway.service du-sumitalk-chat-worker.service
sudo systemctl status du-gateway.service du-sumitalk-chat-worker.service --no-pager -l
sudo journalctl -u du-sumitalk-chat-worker.service -f
```

- 部署习惯：以后凡是改到 SumiTalk 聊天后端、`sumitalk_chat_jobs`、`sumitalk_chat_queue`、`run_sumitalk_chat_worker` 或相关 systemd/deploy 配置，线上拉代码后都要同步重启 `du-sumitalk-chat-worker.service`；只重启 `du-gateway.service` 不够。
- 已验证：`python3 -m py_compile config.py services/sumitalk_chat_queue.py routes/miniapp/sumitalk_chat_jobs.py scripts/run_sumitalk_chat_worker.py` 通过；临时 SQLite smoke 覆盖 job 入队、claim、ack、headers 保持 `X-Reply-Channel=sumitalk`；`.venv/bin/python` 可 import worker 和 Flask app。
- 未完成 / 下次继续：线上需要启用 `du-sumitalk-chat-worker.service`；worker 只按 `After/Wants=du-gateway.service` 排序启动，不跟随主服务重启退出，避免普通网关重启杀掉正在跑的 App 长回复。当前改动不改 QQ/TG/微信入口上下文、不改前端 job 协议、不改 MiniApp 本地 SQLite 聊天存储。

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
- 已完成：按 `docs/wenyou_rules.md` 对齐现有文游硬规则：阶段统一到 `hub / candidate_selection / instance_running / settlement / archived`，新局默认 `instance_running`，结算进入 `settlement`；副本生成不再写死 6 人/4NPC，改为 `tasker_total 2-13` 且 `npc_taskers = tasker_total - player_count`；新人初始数值改为 HP/SAN 180/180、Lv1、D 阶、EXP 0、体力/智慧 10、进化凡人、能力/状态为空；新增 `public` / `gm_secret` / `instance_blueprint` 规范化，GM 推进时会读取蓝图短纲但前端不整段展示隐藏内容；系统商店只在 `hub` 或 `settlement` 可购买，副本中只能查看货架和使用已有背包物品；默认商店货架扩成规则文档里的商品表，前端显示阶段锁定原因和 EXP/状态。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app` 与文游 shop/framework/blueprint smoke check 通过；`rg` 扫描确认源码里已无旧的固定 4NPC/6 人硬规则命中；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BmrlS9UT.js`、`miniapp_static/assets/index-MhmZJNL5.css`、`miniapp_static/assets/index-C2lubs5K.js`；`curl -I http://127.0.0.1:5174/miniapp/` 返回 200。
- 历史备注 / 后续状态：当时未落地完整 Rules Engine、`state_patch`、结算、抽卡和长期钱包；后续已接入轻量规则结算、结算奖励、抽卡、长期钱包和道具目录。默认锻造/装备养成链路已取消；仍可后续继续收敛到更严格的 `GM event_intent -> Rules Engine -> state_patch -> GM narrative` 两阶段执行。

当前状态（2026-05-17 文游规则引擎小步）：
- 已完成：在 `services/wenyou_service.py` 接上轻量 Rules Engine：GM 每轮先输出【事件意图】JSON（风险等级、目标、标签、行动状态、状态增删、威胁时钟），后端按 `docs/wenyou_rules.md` 的风险基础伤害、难度倍率、体力/智慧减免和阶位减伤计算 HP/SAN；状态阈值会自动添加轻伤/重伤/濒死、动摇/污染/失控；`state_patch` 写入 `session["event_log"]` 和 `last_state_patch`，前端剧情下方展示【规则结算】摘要。普通副本行动中若有事件意图，GM 面板里的 HP/SAN 不再覆盖后端计算。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app` 通过；规则烟测覆盖 `dangerous + mental/rule_pollution`，B 难度下玩家一 SAN 从 180 结算到 153，威胁时钟推进到 1/6；`git diff --check` 通过（仅既有 CRLF warning）；`npm -C miniapp run build` 通过。
- 历史备注 / 后续状态：这一步当时还不是完整独立 ruleset/content-pack；后续已补结算奖励、抽卡、长期钱包、结构化道具目录和部分物品效果执行。默认锻造系统已取消；严格两阶段 GM/Rules Engine 仍是可选后续优化。

当前状态（2026-05-17 文游结算/钱包骨架）：
- 已完成：跳过抽卡动画与抽卡机制，先补结算和长期钱包：`storage/r2_store.py` 新增 `wenyou/wallet/{user_id}.json` 读写；商店改为扣长期钱包积分并同步当前 session；`cmd_end` 进入 `settlement` 时按难度、通关结果和评级发放积分/EXP，优先偿还债务，写入钱包 ledger、session settlement、event_log；玩家 EXP 当时会按 `level * 100` 循环升级，后续成长简化后只保留自由属性点奖励；归档会带上 wallet、settlement 和 event_log。MiniApp 文游主界面补“进入结算 / 系统商店 / 归档本局”操作。
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
- 设备动作完成：`routes/miniapp/device_actions.py::_wake_du_for_device_action_results`
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
rg -n "device-state|device-screenshots|screen_check|sense|foreground-app|usage-stats|battery|show_system_notification|AlarmClock|Firebase|BOOT_COMPLETED" routes services miniapp/src miniapp/android
```

注意：
- 截图不是偷偷读屏，必须由客户端授权/执行后回传。
- 图片会增加大量 token，图片压缩和描述归档在聊天清洗链路里查。
- 悬浮球旁边的旧气泡能力已移除；日志告警改投 SumiTalk 安卓壳的 `show_system_notification` 系统通知，会走顶部消息提醒通道。日志页实时错误提醒不要用 app 内 toast；通知栏提醒由后端 `log_error_alert` 投递现有 `show_system_notification` 动作给安卓壳处理。后续推送优先试 FCM，不行再接 ntfy。

当前状态（2026-06-03 MiniApp 上报管理分类开关）：
- 已完成：设置页「上报管理」只管理非健康数据，当前数据卡按类别展示电量、屏幕、前台应用、位置和使用统计；每个类别有独立上报开关，配置存到 R2 `global/device_reporting_config.json`，后端 `/miniapp-api/device-state/reporting/config` 负责保存，`/device-state/*` 各上报入口按类别决定是否入库。关掉某类时接口返回 `skipped`，不再刷新该类最新快照。
- 兼容旧包：前端不再用 `SumiOverlay.setSenseReportingConfig()` 做总开关；当前安装包没有 `requestSenseReportingSnapshot()` 时，只提示“不支持立刻采集”并刷新服务器已有状态，不再把 `not implemented on android` 当作开关保存失败弹出。
- 验证：本轮已跑 `py_compile routes/miniapp/device_state.py storage/r2_store.py`、`miniapp` 的 `tsc --noEmit`、`npm run build`，并确认 `miniapp_static/assets/ReportingManagementScreen-*.js` 包含 `/device-state/reporting/config`。
- APK：当前 Android 版本以 `miniapp/android/app/build.gradle` 为准（现为 `versionCode=12` / `versionName=1.1.10`）；下载包仍按原固定入口覆盖为 `/miniapp/assets/app-debug.apk`，不要保留或新增 `latest`、commit 后缀 APK。

当前状态（2026-05-28 SumiTalk Android 壳能力核对）：
- 已有 / 不要误判为未落地：`miniapp/android/` 已是 Capacitor Android 工程；`miniapp/src/plugins/sumi-overlay.ts` 与 `miniapp/android/app/src/main/java/com/sumitalk/app/OverlayControlPlugin.java` 提供原生桥；`FloatingBallService.java` 处理设备动作轮询、`show_system_notification`、系统闹钟动作、通知栏提醒和悬浮服务；`MainActivity.java` 会上报 usage stats；`SumiAccessibilityService.java` 会上报 `foreground-app` 并支持无障碍截图；后端入口在 `routes/miniapp/device_state.py` 和 `services/device_action_tools.py`。
- 未闭环 / 按需再做：FCM/ntfy 真推送没有完整接入；`miniapp/android/app/build.gradle` 只在存在 `google-services.json` 时应用 Google Services 插件，未看到 `FirebaseMessagingService` 或前端 PushNotifications 注册链路。开机自启也未见 `BOOT_COMPLETED` receiver。当前系统闹钟走 Android `AlarmClock.ACTION_SET_ALARM`，不是 app 自己用 `AlarmManager.setExact` 做的本地业务闹钟。
- 旧长文 `docs/SumiTalk-Android封装方案.md` 里仍有“后续优先级/边界”段落，盘点真实状态时优先看本索引和代码，不要只按旧方案文档判断。

当前状态（2026-06-11 Android 常驻通知叫渡入口删除）：
- 已删除：常驻通知里的「叫渡」action、`FloatingBallService.buildOpenVoiceWakeIntent()` 和 `MainActivity.ACTION_OPEN_VOICE_WAKE` 分支；`DuVoiceWakeNotification.java` 这个未跟踪孤儿类也已删除。
- 保留：渡来电 / 语音通话邀请仍走 `ACTION_OPEN_VOICE_CALL` 和 `EXTRA_VOICE_CALL_INVITE_JSON`；本轮不改通话通知、不改 TTS/STT、不改聊天语音附件。
- 已打包：`miniapp/android/app/build.gradle` 已升到 `versionCode=12` / `versionName=1.1.10`；使用 Android Studio JBR 跑 `JAVA_HOME=/Applications/Android Studio.app/Contents/jbr/Contents/Home ./gradlew :app:assembleDebug`。固定取包位置是 Gradle 输出 `miniapp/android/app/build/outputs/apk/debug/app-debug.apk`，不要再复制到 `miniapp_static/assets/` 当线上下载入口。
- 已验证：`rg "叫渡|voice_wake|VOICE_WAKE|ACTION_OPEN_VOICE_WAKE|buildOpenVoiceWakeIntent|DuVoiceWakeNotification|persistent_notification|lockscreen_voice_wake" miniapp/android/app/src/main/java/com/sumitalk/app miniapp/src` 无运行时代码命中；`aapt dump badging miniapp/android/app/build/outputs/apk/debug/app-debug.apk` 确认 `versionCode=12` / `versionName=1.1.10`。

当前状态（2026-06-12 App 页面缩放锁定）：
- 已完成：`miniapp/index.html` 的 viewport 增加 `minimum-scale=1`、`maximum-scale=1`、`user-scalable=no`；`miniapp/android/app/src/main/java/com/sumitalk/app/MainActivity.java` 在 WebView 初始化时关闭 `setSupportZoom`、内置缩放控件和显示缩放控件，并固定 `textZoom=100`。
- 生效边界：线上远端页面需要重建并部署 `miniapp_static`；Android WebView 原生缩放设置需要重新打包安装 APK 后才会进入手机壳。

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
- 图片描述是异步链路：归档先写内部占位符 `[[DU_IMAGE_DESC:img_xxxxxxxxxxxxxxxx]]`，描述完成后写入最近图片描述表；注入 last4 时再把占位符替成 `[图片：描述]`，没有描述时降级 `[图片]`。
- 最近图片描述表只保留最近 4 张：全局表 `global/image_descriptions_recent.json`，窗口表 `windows/<window_id>/image_descriptions_recent.json`。排查时先看 `image_desc 调用完成/失败` 和 `image_desc 最近表已更新` 日志。

当前状态（2026-06-10 图片描述进 last4）：
- 已改：图片归档不再等待 3 秒后永久写死 `[图片]`，而是写稳定内部占位符；异步图片描述成功后更新最近图片描述表；latest4/窗口最近对话注入前会替换占位符。
- 已验证：本地 venv 模拟中，占位符可被描述表替换成 `[图片：描述]`，无描述时降级 `[图片]`，内部标记不会露给模型。
- 未完成 / 下次继续：部署后用真实图片发一轮，检查服务日志里是否出现 `image_desc 调用完成` 和 `image_desc 最近表已更新`，再看下一轮 last4 注入是否带图片描述。

## 工具调用结果错位

现象：
- `GET_TIME_INFO` 显示成闹钟创建结果
- 工具 call/result 对不上

入口：
- `routes/chat.py::_collect_tool_trace_from_messages`
- `services/device_action_tools.py`
- 思维链面板：`routes/miniapp/reasoning.py::miniapp_reasoning_latest`

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
- 动态层 DS 现在优先要求固定标签格式（`ACTION:` / `CONTENT:` 等），旧 JSON 只作为兼容解析；`new/merge` 的 `content` 如果太短、像半句话、标题词、没闭合引号或停在“然后/但是/——”这类没说完的位置，会最多重写 5 次，最后仍只是明显尾巴残缺时会做保守尾巴修复，确保落库的是完整句子。
- 亲密 / NSFW 内容不要为了保存混进 `客厅`；该记就标 `卧室` 并按动态层 `new/merge` 正常存。卧室内容不再额外侧写 Notion，画像与核心缓存不吃卧室动态记忆。
- 卧室 tag 不和普通动态记忆共用完整生命周期：普通 tag 仍按 `DYNAMIC_MEMORY_DAYS_VALID=10` 参与注入有效期；卧室 tag 用 `DYNAMIC_MEMORY_BEDROOM_DAYS_VALID=3`，超过后不再注入，并会在动态层清理时从 R2/向量索引/血缘表退场。卧室连续 play 或同类偏好/边界延续时，优先 `merge`，不要因为小纸条玩法不同反复 `new`。

当前状态（2026-06-04 动态层残缺便签重写与审计）：
- 已完成：`services/dynamic_layer_ds.py` 单轮、批量和归档批处理都会对 `new/merge` 内容做完整性校验；实时单轮最多重写 5 次，最后仍只是“然后/——”这类尾巴残缺时会保守修成完整句子；归档批处理若 5 次和尾巴修复后仍有残缺则抛错不写断点，下一次从本批重跑。
- 已完成：新增 R2 `dynamic_memory/ds_audit.json` 审计，MiniApp「记忆调试 -> 动态记忆」可直接查看最近 DS 写入的 `new/merge/skip` 计数、重试次数、失败原因和最终 content。
- 已验证：`.venv/bin/python -m py_compile services/dynamic_layer_ds.py storage/r2_store.py routes/miniapp/memory_panel.py pipeline/pipeline.py scripts/test_dynamic_layer_ds_parser.py`、`.venv/bin/python scripts/test_dynamic_layer_ds_parser.py`、`npm -C miniapp run build`、`import app` 和相关 `git diff --check` 通过。
- 未完成 / 下次先查：历史 R2 里已经写进去的残缺动态记忆不会自动清理；如果要修旧数据，先走 MiniApp memory debug 或维护脚本，别直接手删 R2。

当前状态（2026-06-08 动态记忆血缘 SQL 表）：
- 已完成：新增本地 SQLite `data/dynamic_memory_provenance.sqlite3`（可用 `DYNAMIC_MEMORY_PROVENANCE_DB` 改路径），表 `dynamic_memory_provenance_events` 按 `memory_id`、`window_id + round_index`、`action` 建索引；`services/dynamic_memory_provenance.py` 提供 `record_event()`、`list_events_for_memory()`、`list_events_for_round()`。
- 已完成：动态层 `new` / `merge` 成功落库后记录血缘事件；离线 `memory_maintenance` 合并重复动态记忆时记录 `maintenance_merge`，包含保留记忆 id、被合并的 related memory ids、merge 前后 content、标签和 DS 决策。动态记忆被边缘淘汰或在离线维护中被删除/并入其它记忆时，会同步从 SQL 血缘表删除该 `memory_id` 的事件。
- 已验证：`.venv/bin/python -m py_compile config.py pipeline/pipeline.py services/dynamic_memory_provenance.py services/memory_maintenance.py scripts/test_dynamic_memory_provenance.py` 和 `.venv/bin/python scripts/test_dynamic_memory_provenance.py` 通过。
- 未完成 / 下次继续：历史已有动态记忆未回填血缘；MiniApp 查询入口和“按 provenance 拉原始 round 重新写这条记忆”的重写流程还未接。

当前状态（2026-06-09 实时层总结 worker 回收保护）：
- 已完成：`pipeline/pipeline.py::step_run_post_archive_tasks` 继续保持实时层 DS 总结异步，不把聊天响应拖到等 DS；总结线程从 daemon 改为非 daemon，并命名为 `summary-window-{window_id}-{round_index}`，避免 worker 正常回收时直接丢掉已开始的 DS 总结。
- 已完成：`services/chat_archive_helpers.py` 的非流式归档后慢任务线程改为非 daemon；`scripts/start_gateway_prod.sh` 默认 `GATEWAY_GRACEFUL_TIMEOUT` 从 30 秒提高到 120 秒，并在启动日志打印 `graceful_timeout`，给已经进入慢任务链路的 DS 总结留出有限收尾窗口，同时避免重启/回收拖太久。
- 未完成 / 下次继续：这次没有新增 worker，没有把总结改同步，也没有改总结频率/补缺口逻辑；如果再查总结缺失，先看 gunicorn recycle 时间点、`graceful_timeout` 和实时层总结线程日志。

当前状态（2026-06-11 卧室动态记忆正常落库）：
- 已完成：`services/dynamic_layer_ds.py` 去掉“卧室必 skip”规则，要求亲密 / NSFW 内容值得记时标 `卧室` 并正常 `new/merge`，不要为了保存错标 `客厅`。
- 已完成：`pipeline/pipeline.py::_apply_one_decision` 不再在卧室通道 early return；卧室不再写 Notion 原文备份，动态层继续按 action 落库或融合。new/merge 的卧室动态记忆不提进 core cache，画像候选仍沿用 `services/portrait_memory.py` 的卧室排除。
- 未完成 / 下次继续：历史已经混进 `客厅` 的 NSFW 动态记忆不会自动迁移；如要清旧数据，先从 MiniApp 记忆调试或 R2 当前动态记忆列表里定位，再做迁移/重标脚本。

当前状态（2026-06-30 移除卧室 Notion 侧写）：
- 已完成：删除 `services/bedroom_gateway.py`，移除 `NOTION_BEDROOM_PAGE_ID` 配置和 `pipeline/pipeline.py::_apply_one_decision` 里的 Notion 原文追加调用；卧室 tag 现在只负责动态记忆分类、短生命周期和 core cache 排除。
- 已验证：`.venv/bin/python -m py_compile config.py utils/log.py pipeline/pipeline.py services/dynamic_layer_ds.py` 通过；运行代码里不再有 `NOTION_BEDROOM_PAGE_ID` / `append_bedroom_raw` / `bedroom_gateway` 引用。
- 未完成 / 下次继续：VPS 环境里如果还留着旧 `NOTION_BEDROOM_PAGE_ID`，新代码也不会读取；部署后重启网关即可生效。

当前状态（2026-06-12 卧室动态记忆短生命周期）：
- 已完成：`config.py` 新增 `DYNAMIC_MEMORY_BEDROOM_DAYS_VALID=3`；`pipeline/pipeline.py` 的动态记忆注入有效期按 tag 判断，卧室 tag 超过 3 天未再提到就不再注入。
- 已完成：动态层落盘清理复用现有边缘淘汰通道，卧室 tag 超过 3 天未再提到可直接从 R2 current、向量索引和血缘表退场；普通 tag 仍保留原本 10 天注入有效期与低权重边缘淘汰规则。
- 已完成：`services/dynamic_layer_ds.py` 只补 merge 倾向：卧室连续 play、同一氛围或同类偏好/边界延续时优先合并，不新增“新花样门槛”或“play 小纸条默认 skip”规则。
- 未完成 / 下次继续：历史卧室记忆不会在提交瞬间批量清理，等下一次动态记忆注入或离线维护触发；如果要立刻清，先在 MiniApp 记忆调试确认将被删的 id。

当前状态（2026-06-20 动态记忆 SQLite mirror 与关键词索引第一阶段）：
- 已完成：新增 `storage/dynamic_memory_mirror_store.py`，使用 `data/dynamic_memory_mirror.sqlite3` 存 R2 `dynamic_memory/current.json` 的可重建副本、关键词表、FTS5 辅助索引、`mirror_meta` 和 `sync_runs`。同步方向只允许 R2 -> SQLite，不提供 SQLite -> R2 反写函数。
- 已完成：新增 `services/dynamic_memory_keywords.py`，从 `content/retrieval_text/tag/labels/emotion_label/scene_type/target_type` 规则抽取关键词；不调用 DS，不重写动态记忆正文，不改 `id/mention_count/retrieval_text`。
- 已完成：新增 `scripts/backfill_dynamic_memory_keywords.py`，默认 dry-run；加 `--write` 才写 SQLite mirror。脚本只读 R2 current，不写回 R2。新增 `docs/DYNAMIC_MEMORY_SQLITE_MIRROR.md` 记录边界、回滚和验证命令。
- 已完成：`config.py` 新增 `DYNAMIC_MEMORY_MIRROR_DB`、`DYNAMIC_MEMORY_MIRROR_ENABLED`、`DYNAMIC_MEMORY_MIRROR_READ_FOR_CHAT`、`DYNAMIC_MEMORY_KEYWORD_BACKFILL_DRY_RUN`、`DYNAMIC_MEMORY_KEYWORD_MAX_TERMS`；聊天读 SQLite 的开关默认关闭。
- 第一阶段边界：当时没有接 `pipeline/pipeline.py`、`services/dynamic_layer_ds.py`、`save_dynamic_memory_list()` 或 MiniApp 面板；聊天注入、DS `new/merge/skip`、citation 回写、core cache 提拔仍全部走原链路。后续接 UI 也只能读 SQLite 展示关键词覆盖率和 R2/mirror diff，不能让 SQLite 独有内容进入 prompt。

当前状态（2026-06-20 动态记忆 SQLite mirror MiniApp 排查第二阶段）：
- 已完成：`routes/miniapp/memory_panel.py` 新增 `GET /miniapp-api/dynamic-memory-mirror` 和 `POST /miniapp-api/dynamic-memory-mirror/backfill`。GET 只返回 mirror 状态与瘦身后的最近条目；POST 从 R2 current 读动态记忆，抽关键词后写 SQLite mirror，并明确返回 `r2_write=false`。
- 已完成：`miniapp/src/ui/tabs/MemoryDebugTab.tsx` 的“动态记忆”tab 新增 SQLite mirror 卡片，显示 mirror/R2 条数、关键词数、last_sync、snapshot hash、最近条目的关键词，并提供“同步关键词 mirror”按钮。
- 未完成 / 下次继续：第二阶段仍没有接 `pipeline/pipeline.py`、`services/dynamic_layer_ds.py`、`save_dynamic_memory_list()` 或 `search_memory`；SQLite mirror 不参与实际召回、DS 写入、citation 回写或 core cache 提拔。下一步如果要 shadow compare，只记录 SQLite 候选 id 与真实召回差异，不能让 SQLite 独有内容进入 prompt。

当前状态（2026-06-20 动态记忆 SQLite shadow compare 第三阶段）：
- 已完成：`storage/dynamic_memory_mirror_store.py::shadow_candidates()` 使用关键词表和 content/retrieval_text/tag 的轻量 LIKE 查候选 id；如果 mirror DB 不存在，返回 `mirror_db_missing`，不会在聊天热路径自动创建空库。
- 已完成：`pipeline/pipeline.py::step_inject_dynamic_memory` 在 recall debug 事件中附加 `sqlite_shadow`，记录 SQLite 候选 id、真实注入 id、overlap/miss/stale 和候选命中词。真实召回仍由原来的 R2 + 向量 + BM25 决定；SQLite shadow 不进 prompt、不改 `lines`、不改 `citation_map`。
- 已完成：`miniapp/src/ui/tabs/MemoryDebugTab.tsx` 的自动召回卡片显示 SQLite shadow 的 hit/miss/stale、query terms 和前 5 个候选；只用于排查关键词索引效果。
- 已完成：shadow 候选质量优化：`tag/emotion_label/scene_type/target_type` 等低信号标签降权，`拒绝/不行/老婆说` 等泛词停用；候选至少需要高信号词命中或足够高综合分，避免只靠“拒绝”这类泛词捞出无关亲密记忆。
- 未完成 / 下次继续：第四阶段仍未做。不要让 SQLite mirror 参与真实召回排序或注入；如果以后要试，只允许先返回 candidate id，再从同一份 R2 current snapshot 取正文。

当前状态（2026-06-26 动态记忆召回时间标签修复）：
- 问题：召回行里的 `[今天中午]` / `[今天上午]` 一度使用 `last_mentioned` 计算；旧记忆只要今天被引用或命中，`last_mentioned` 就会刷新，导致前天/昨天发生的事被显示成“今天”。典型例子：`fa86f29f-0a57-4830-86aa-925dd76e37c5` 事件创建于 `2026-06-24T22:35:02+08:00`，但因 `last_mentioned=2026-06-26T11:58:22+08:00` 被误标为 `[今天中午]`。
- 已完成：召回展示时间改为优先 `updated_at` / `created_at` / `promoted_at`，最后才兜底 `last_mentioned`；`last_mentioned` 只表示最近被引用，仍可用于权重、活跃度和淘汰，不再用于事件展示时间。
- 已完成：动态层 `new` 写入 `updated_at=created_at`，`merge` 更新 `updated_at`；未来 core cache 提拔会保留 `created_at`、`updated_at`、`last_mentioned`，旧 core cache 记录如果 id 能对应当前动态记忆，会从动态记忆继承事件时间，避免 `promoted_at` 冒充发生时间。
- 后续同类扫描：`search_memory` 的新鲜度/返回排序、记忆引用 debug 详情、SQLite mirror 的最近列表、记忆星云 UI 显示时间也要用 `event_at` / `updated_at` / `created_at` 这一组事件时间；`last_mentioned` 只保留给动态层权重、活跃度、TTL、淘汰和 shadow/关键词候选排序。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py storage/r2_store.py memory_vector/core_pending_index.py memory_vector/dynamic_vector_retriever.py services/dynamic_memory_search.py` 通过；本地复现同一条记忆 `created_at=2026-06-24T22:35:02+08:00`、`last_mentioned=2026-06-26T11:58:22+08:00` 时，时间标签变为 `前天深夜`。

## 核心 Prompt / 风格规则 / 禁言模式

现象：
- 渡突然冷冰冰
- 风格规则没生效
- 禁言模式不生效或忘记关闭

入口：
- 核心 prompt：`routes/miniapp_api.py` 的 `/core-prompt`
- 核心行为注入：`pipeline/pipeline.py::step_inject_core_behavior_rules`
- SumiTalk 风格：`services/chat_prompt_injections.py::inject_entry_style_system` 调用 `services/entry_style_prompt.py::build_sumitalk_style_system`
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

当前状态（2026-06-26 MiniApp Prompt 管理）：
- 已完成：设置页的旧「核心 Prompt」入口改为「Prompt 管理」，前端入口为 `miniapp/src/ui/PromptManagerScreen.tsx`；页面顶部只保留「禁言模式」「百万计划游戏模式」两个开关，二者不进入可编辑提示词列表。
- 已完成：可编辑提示词白名单集中在 `services/prompt_manager.py::PROMPT_SECTIONS`，包括核心 Prompt、常识块、思维链规则、核心行为规则、不退缩原则、SumiTalk/QQ/TG/微信/小爱入口风格、语音台词规范、NSFW 规则；保存写入 R2 `global/prompt_manager_config.json`，旧版本自动备份到 `global/prompt_manager_backups/`，并提供单条回滚。
- 已完成：运行时读取统一走 `services.prompt_manager.get_managed_prompt_text()`；`pipeline/pipeline.py`、`services/entry_style_prompt.py`、`services/voice_line_prompt.py`、`services/chat_prompt_injections.py`、`services/telegram_bot.py` 已接入覆盖值，未配置时回退现有文件/常量。
- 已完成：Prompt 管理入口列表改为前端常驻 catalog，首屏不再依赖接口现拉；`/miniapp-api/prompt-manager` 只补 revision/source/content_length 等状态元数据，不再为了列表读取整段 fallback prompt。点进某个条目时才拉完整内容和备份。
- 已验证：`.venv/bin/python -m py_compile storage/r2_store.py services/prompt_manager.py services/voice_line_prompt.py services/entry_style_prompt.py services/chat_prompt_injections.py services/telegram_bot.py pipeline/pipeline.py routes/miniapp/settings.py app.py`、`npm run build`、`import app`、`git diff --check` 通过。
- 未完成 / 下次继续：不要把禁言模式或百万计划游戏模式改成可编辑 Prompt，它俩只保持开关语义；如果后续新增提示词条目，前端 `PROMPT_SECTION_CATALOG` 和后端 `PROMPT_SECTIONS` 需要同步维护。

当前状态（2026-05-12）：
- 已完成：`AGENTS.md` 已补“提示词写法规则”，并把现有 AGENTS 表述收成第二人称/无人称风格；刚才误把参考段落的具体互动内容写进去，已删除，只保留写法口吻规则。
- 未完成 / 不要碰：没有改运行时核心 prompt、SumiTalk/TG 风格注入或 DS 总结提示词；后续只有明确要调线上人格/风格时再改对应入口。

当前状态（2026-05-13）：
- 已完成：语音台词撰写规范已抽到 `services/voice_line_prompt.py`，并注入 QQ/TG 的 `<voice>` 规则与 `X-Voice-Call-Slim` 语音通话回复；只约束会被朗读的语音文本，不改普通文字聊天、核心 prompt 或 DS 总结提示词。
- 未完成 / 不要碰：这次不处理 voice prompt 之外的风格规则；不要把这份规范做成 Codex skill，也不要塞进全局普通聊天 prompt。

## MiniApp 语音转写 / 声音事件

入口：
- MiniApp 语音通话：`routes/miniapp/media.py` 的 `/miniapp-api/voice-call`
- 预览转写：`routes/miniapp/media.py` 的 `/miniapp-api/voice-call-preview`
- STT provider：`services/stt.py`
- 语音通话转发：`services/voice_call_pipeline.py`
- 配置：`config.py` 的 `VOICE_STT_*`，OpenRouter key 可复用 `OPENROUTER_API_KEY` 或 `TARGET_AI_URLS/TARGET_AI_API_KEYS` 里指向 `openrouter.ai` 的条目

注意：
- Gemini/OpenRouter 转写返回正文 `text` 和客观声音旁白 `audio_observations`；正文可包含明显声音事件，如（哈哈大笑）（大笑）（哼唱）（唱着说）。
- 超过约 1 秒的停顿要直接写进正文发生位置，并按音频估算实际时长，例如 `我就是……（停顿了约3秒）哎呀我反正有事！`；短犹豫用省略号即可。
- 声音旁白只能写听得见的声学线索，如笑声、气声、语速、音高起伏、音量、停顿；不要写“像是在逗你”、撒娇、生气、意图判断或心理分析。
- `speech_to_text()` 仍保留旧兼容返回纯文本；新链路优先用 `transcribe_speech()`。

当前状态（2026-05-31）：
- 已完成：新增 `VOICE_STT_PROVIDER=openrouter` 路径，默认模型 `google/gemini-2.5-flash`，失败可回退 `deepgram`；`voice-call` 会把客观声音旁白作为隐藏 system 线索发给渡，用户正文和通话记录仍用转写正文。
- 已部署：生产 `/root/du-gateway/.env` 已设置 `VOICE_STT_PROVIDER=openrouter`、`VOICE_STT_FALLBACK_PROVIDER=deepgram`、`VOICE_STT_OPENROUTER_API_URL=https://openrouter.ai/api/v1/chat/completions`、`VOICE_STT_OPENROUTER_MODEL=google/gemini-2.5-flash`，原 env 备份为 `/root/du-gateway/.env.bak.voice-stt-20260531031529`。
- 已验证：本地 `.venv/bin/python -m py_compile config.py services/stt.py services/voice_call_pipeline.py routes/miniapp/media.py` 通过；生产同四文件 py_compile 通过；生产 `du-gateway` 已重启且 `systemctl is-active du-gateway` 为 active、`https://duxy-home.com/health` 返回 ok；用本机生成的短 wav 在生产直调 `transcribe_speech()`，返回 provider=openrouter、model=google/gemini-2.5-flash、text=`Hello this is a voice test.`、audio_observations=`语速偏快。`
- 未完成 / 下次继续：未用辛玥真实中文语音样本做笑声/唱歌/气声效果验收；服务器 tracked 文件目前是直接应用 patch 后的本地修改，若要长期留存需要后续提交/推送。

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
- 当前转发 VPS：`duproxy@45.76.171.91`，Tailscale IP `100.86.248.99`，proxy 路径 `/home/duproxy/claude-proxy/proxy.js`
- 本机 token 同步脚本：`/Users/doraemon/claude-token-sync.sh`
- 本机 LaunchAgent：`/Users/doraemon/Library/LaunchAgents/com.doraemon.claude-token-sync.plist`

常查：

```bash
rg -n "claude|anthropic|thinking|cache_control|tool_use|oauth|8317|8082" scripts routes storage .env
ssh -o ControlMaster=no ali-du 'ss -ltnp 2>/dev/null | grep -E "(:5000|:8082|:8317)"'
ssh -o ControlMaster=no ali-du 'sudo systemctl status claude-proxy-tunnel.service --no-pager -l | sed -n "1,80p"'
ssh -o ControlMaster=no duproxy@45.76.171.91 'systemctl --user status claude-oauth-proxy.service --no-pager -l | sed -n "1,80p"'
```

注意：
- Claude OAuth proxy 是 Claude 反代，不是 CPA。CPA 另有一节，按 Codex 反代排查。
- 旧网关本机 `127.0.0.1:8082` 不是本地 Claude proxy，而是 `claude-proxy-tunnel.service` 经 SSH 隧道转到新 VPS；旧网关上的 `claude-oauth-proxy.service` 应保持停用。
- 转发 VPS 的 `claude-oauth-proxy.service` 是 `duproxy` 的用户级 systemd service，实际 unit 在 `/home/duproxy/.config/systemd/user/claude-oauth-proxy.service`，只监听新 VPS 本机 `127.0.0.1:8082`。
- 不要擅自改 `/Users/doraemon/claude-token-sync.sh` 的默认重启服务；当前主链路是同步完整 credential 到转发 VPS，由转发 VPS proxy 自刷新。只有用户明确说服务名变了，才改 `CLAUDE_PROXY_SERVICE` 或脚本默认值。
- Claude OAuth proxy 401 不要先猜模型，先分清是哪层 401：
  - `Invalid proxy key` / `AUTH REJECTED`：网关到代理的 key 不匹配，查旧网关 `/root/du-gateway/.env` 的 `TARGET_AI_API_KEYS` 里 `http://127.0.0.1:8082/v1/chat/completions` 对应项，必须和新 VPS `/home/duproxy/claude-proxy/.env` 的 `PROXY_KEY` 一致。
  - `<= 401 /v1/chat/completions`、`Got 401`、`Refresh failed`：代理到 Anthropic / Claude OAuth 的 token 问题，优先查 token sync。
  - `Refresh failed: HTTP 403 ... Just a moment... Cloudflare`：服务器自己刷新 token 被 Cloudflare 挡住，不能指望远端自动刷新；要用 Mac 本地 Keychain 的 token 同步到 VPS。
  - `429`：额度/限流，不是 token sync 能修。

### Claude token sync 快查

当前 Claude OAuth sync 口径：Claude Code 刚授权后，本机只从 Keychain 读取完整 OAuth credential JSON，不在本机强制刷新；通过 HTTP POST 同步给转发 VPS 的 Claude OAuth proxy。转发 VPS 持有 refresh token，并在 proxy 内部按过期时间自行刷新。不要再把新授权后的 token sync 做成 access-only 过滤包，也不要用旧脚本口径判断这条链路。

关键路径：
- 脚本：`/Users/doraemon/claude-token-sync.sh`
- LaunchAgent：`/Users/doraemon/Library/LaunchAgents/com.doraemon.claude-token-sync.plist`
- 本机日志：`/Users/doraemon/claude-token-sync.log`
- launchd stdout/stderr：`/Users/doraemon/claude-token-sync.launchd.log`、`/Users/doraemon/claude-token-sync.launchd.err`
- 状态文件：`/Users/doraemon/.claude-token-sync.state`、`/Users/doraemon/.claude-token-sync.wake`
- 本机 Keychain service：`Claude Code-credentials`
- 远端 Claude OAuth auth 文件：新 VPS 默认 `/home/duproxy/.cli-proxy-api/claude-oauth.json`；旧 nora 路径只作为历史记录排查。
- Claude OAuth proxy 内部同步接口：`POST /internal/oauth-sync`
- 网关转发同步接口：`POST /internal/claude-oauth-sync`
- 网关转发状态接口：`GET /internal/claude-oauth-status`
- 本机私有配置：`/Users/doraemon/.claude-token-sync.env`

LaunchAgent / 本机脚本属于旧救火链路；新授权后的主链路不是本机定时强刷，而是把 Keychain 里的完整 credential 同步到转发 VPS。远端 401 只是补救信号，不代表要立刻在本机刷新。

本机配置示例（不要提交，不要贴密钥）：

```bash
CLAUDE_PROXY_SYNC_URL=https://duxy-home.com/internal/claude-oauth-sync
CLAUDE_PROXY_STATUS_URL=https://duxy-home.com/internal/claude-oauth-status
CLAUDE_PROXY_SYNC_KEY=...
CLAUDE_PROXY_SSH_FALLBACK=1
CLAUDE_PROXY_SSH_HOST=ali-du
CLAUDE_PROXY_SSH_AUTH_FILE=/home/duproxy/.cli-proxy-api/claude-oauth.json
CLAUDE_PROXY_SSH_SERVICE=claude-oauth-proxy.service
CLAUDE_REFRESH_BUFFER_SECONDS=60
```

服务端约束：
- `scripts/claude_oauth_proxy.js` 的同步接口用 `CLAUDE_OAUTH_SYNC_KEY` 校验；未配置时默认复用 `PROXY_KEY`。
- Claude OAuth proxy 应继续只监听服务器本机或内网；公网只暴露网关转发接口或受控内网入口。
- 同步接口接收完整 Claude Code OAuth credential JSON，验证至少存在可用 access token 或 refresh token，原子写入 `CLAUDE_OAUTH_FILE`，并热更新内存 token；响应只允许返回 `expiresAt`、`canRefresh` 等摘要，不打印 token。
- SSH fallback 不再是默认主链路；必须先确认 HTTP POST 不通，且只写受控远端 auth 文件。不要打印 token、refresh token 或 sync key。

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
ssh -o ControlMaster=no ali-du 'sudo systemctl show claude-proxy-tunnel.service -p ActiveState -p SubState -p MainPID --no-pager; ss -ltnp 2>/dev/null | grep ":8082" || true'
ssh -o ControlMaster=no duproxy@45.76.171.91 'systemctl --user show claude-oauth-proxy.service -p ActiveState -p SubState -p MainPID --no-pager; ss -ltnp 2>/dev/null | grep ":8082" || true'
ssh -o ControlMaster=no duproxy@45.76.171.91 'journalctl --user -u claude-oauth-proxy.service -n 120 --no-pager -o cat | grep -Ei "401|refresh|auth file|cloudflare|error|model|Invalid proxy key"'
```

干净重启 Claude OAuth proxy 时，不要手动 `cd /home/duproxy/claude-proxy && node proxy.js`，也不要只按某个旧 PID kill。必须让 systemd 接管；如果 8082 已被脱管 node 占用，按 cwd/cmdline 校验后先清掉脱管进程：

```bash
ssh -o ControlMaster=no duproxy@45.76.171.91 'set -e
systemctl --user stop --no-block claude-oauth-proxy.service || true
for pid in $(pgrep -u duproxy -f "node proxy.js|/home/duproxy/claude-proxy/proxy.js" || true); do
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
  cmd=$(tr "\0" " " <"/proc/$pid/cmdline" 2>/dev/null || true)
  cg=$(cat "/proc/$pid/cgroup" 2>/dev/null || true)
  if [ "$cwd" = "/home/duproxy/claude-proxy" ] && printf "%s" "$cg" | grep -q "session-"; then
    echo "kill orphan claude proxy pid=$pid cmd=$cmd"
    kill "$pid" || true
  fi
done
sleep 1
systemctl --user reset-failed claude-oauth-proxy.service || true
systemctl --user start claude-oauth-proxy.service
systemctl --user status claude-oauth-proxy.service --no-pager -l | sed -n "1,45p"
ss -ltnp 2>/dev/null | grep ":8082"
'
```

确认 token 是否已同步成功：
- 本机日志应出现类似：`synced oauth via_http reason=... oauth_ready refresh_attempted=... expiresAt=...`；若 HTTP 失败后保底成功，会出现 `synced oauth via_ssh_fallback ...`
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

当前状态（2026-07-07）：
- 主链路：旧网关 `ali-du` 仍把 Claude OAuth upstream 配成 `http://127.0.0.1:8082/v1/chat/completions`；这个本机 8082 由 `claude-proxy-tunnel.service` 转发到新 VPS。当前 tunnel 通过 drop-in `/etc/systemd/system/claude-proxy-tunnel.service.d/10-tailscale-target.conf` 覆盖 `ExecStart`，SSH 目标为 Tailscale `duproxy@100.86.248.99`，远端仍是新 VPS 自己视角的 `127.0.0.1:8082`。旧网关本地 `claude-oauth-proxy.service` 应保持 `inactive/dead`。
- 新 VPS：`claude-oauth-proxy.service` 是 `duproxy` 的用户级 systemd service，unit 在 `/home/duproxy/.config/systemd/user/claude-oauth-proxy.service`，路径 `/home/duproxy/claude-proxy/proxy.js`，只监听 `127.0.0.1:8082`；refresh token 由新 VPS proxy 持有并自刷新。查询和重启优先用 `systemctl --user status|restart claude-oauth-proxy.service`。
- 已修：旧网关 `/root/du-gateway/.env` 中 `http://127.0.0.1:8082/v1/chat/completions` 对应的 `TARGET_AI_API_KEYS` 已更新为新 VPS 当前 `PROXY_KEY`，旧 key 备份在 `/root/du-gateway/.env.bak-claude-key-20260704-161039`。
- 已修：旧网关 `/root/du-gateway/.env` 中 `CLAUDE_OAUTH_SYNC_KEY` 已更新为新 VPS 当前 sync key，用于 MiniApp/API 管理查询 `/internal/oauth-status`；旧 key 备份在 `/root/du-gateway/.env.bak-claude-sync-key-20260704-163203`。
- 已修：旧网关 tunnel 单元已从 `root@45.76.171.91` 改为 `duproxy@45.76.171.91`，随后通过 drop-in 切到 `duproxy@100.86.248.99`；转发 VPS 已禁 root SSH，`duproxy` 有免密 sudo。旧网关 tunnel 私钥 `/root/.ssh/du_new_vps_ed25519` 的公钥已加入新 VPS `duproxy`。
- 已配置：转发 VPS 已加入 Tailscale，IP 为 `100.86.248.99`；本机可直接 `ssh duproxy@100.86.248.99`。旧网关 `ali-du` 到转发 VPS 的 Tailscale 链路已验证为 direct，切换后 `ss -tnp` 显示 `100.92.76.117 -> 100.86.248.99:22`。这主要改善安全边界和可维护性，不保证比公网更快。回滚生产 tunnel 时删除 drop-in 或把目标改回 `duproxy@45.76.171.91` 后 `daemon-reload && restart claude-proxy-tunnel.service`；切换前备份为 `/root/claude-proxy-tunnel.service.before-tailscale-20260707-084239.txt`。
- 已配置：转发 VPS 同时作为 `du-proxy-new-us` Trojan 节点，公网入口改为 `us.duxy-home.com:443`，证书由新 VPS `certbot` 管理，Trojan 配置 `/etc/trojan/config.json` 指向 `/etc/letsencrypt/live/us.duxy-home.com/fullchain.pem` 和 `privkey.pem`，SNI 为 `us.duxy-home.com`；旧 `45.76.171.91:8443` 路径已确认公网会卡，UFW 不再放行 8443。订阅源只改新美国节点 `/var/www/proxy-sub/du-proxy-new-us-HTEsRb3ujVT5JXFCEPflhwhnSZmFlJmrRHkqAk5p.yaml` 为 `server: us.duxy-home.com`、`port: 443`、`sni: us.duxy-home.com`；马来西亚订阅 `a9K3mQ8xLp2Rt7Vn4Hs6Yw1Bc5Zd0Ef7.yaml` 仍是 `proxy.duxy-home.com:8443`，不要误改。
- 已收束：转发 VPS 上遗留的系统级 `/etc/systemd/system/claude-oauth-proxy.service` 会和用户级服务抢 `127.0.0.1:8082` 导致 `EADDRINUSE` 循环重启；已 `disable --now` 系统级服务，保留用户级服务运行，并设置 `loginctl enable-linger duproxy`，避免无人登录时用户级服务无法开机自启。
- 已验证：旧网关带 `.env` 的 8082 key 请求 `http://127.0.0.1:8082/v1/models` 返回 `200 OK`，模型数 9，包含 `claude-sonnet-5`、`claude-fable-5`、`claude-opus-4-8`、`claude-opus-4-7`、`claude-sonnet-4-6`；旧网关带 `CLAUDE_OAUTH_SYNC_KEY` 请求 `http://127.0.0.1:8082/internal/oauth-status` 返回 `ok=True`、`canRefresh=True`、`expiresInSeconds` 和 `rateLimitSnapshot`；`du-gateway.service` 和 `du-sumitalk-chat-worker.service` 已重启为 active/running。
- 排查优先级：MiniApp/API 管理里 `models 401` 且返回 `Invalid proxy key` 时，优先查旧网关 `.env` 的 8082 key 和新 VPS `PROXY_KEY` 是否一致；`状态查询 401` 时优先查旧网关 `CLAUDE_OAUTH_SYNC_KEY` 和新 VPS `CLAUDE_OAUTH_SYNC_KEY` 是否一致，不要先查 Claude OAuth access token。

当前状态（2026-05-16）：
- 已纠正：不要把 Claude OAuth proxy 和 CPA 混在一起；Claude 401 先查 Claude OAuth proxy 和 token sync。
- 已撤回：刚才把 token sync 默认重启服务改成 `cliproxyapi.service` 是错误改动，已改回 `claude-oauth-proxy.service`。
- 已改动：token sync 主链路改为 HTTP POST；新增 Claude proxy 内部同步/状态接口，网关新增 `/internal/claude-oauth-sync` 和 `/internal/claude-oauth-status` 转发。
- 已部署：`/home/nora/claude-proxy/proxy.js` 已更新并重启 `claude-oauth-proxy.service`；服务器本机 `GET /internal/oauth-status`、`POST /internal/oauth-sync` 已验证通过。
- 已配置：`/Users/doraemon/.claude-token-sync.env` 已创建；本地 `CLAUDE_PROXY_SYNC_KEY` 已同步到服务器 `/home/nora/claude-proxy/.env` 的 `CLAUDE_OAUTH_SYNC_KEY`，不要打印或提交该 key。
当前状态（2026-06-08）：
- 已删除：`/Users/doraemon/claude-token-sync.sh` 里的 Keychain `expiresAt` 临时改小/恢复逻辑，以及 `CLAUDE_KEYCHAIN_EXPIRES_SPOOF`、`CLAUDE_KEYCHAIN_SPOOF_EXPIRES_SECONDS` 配置说明。
- 已调整：同步日志从 `refreshed=...` 改成 `refresh_attempted=...`，避免误解为“脚本已强制刷新出新 token”。后续判断是否真的刷新，只看 Keychain/远端状态接口里的 `expiresAt` 是否变新、`stale=false`。
当前状态（2026-06-10 SSH fallback）：
- 已改动：`/Users/doraemon/claude-token-sync.sh` 保持 HTTP POST 为主链路；`sync_oauth_to_server` 在 HTTP POST 最终失败后会走 SSH fallback，默认 `ali-du`、远端 auth 文件 `/home/nora/.cli-proxy-api/claude-sumikamiss@gmail.com.json`、服务 `claude-oauth-proxy.service`。
- 已验证：`bash -n /Users/doraemon/claude-token-sync.sh` 通过；正常 `/Users/doraemon/claude-token-sync.sh --force` 仍输出 `synced oauth via_http`；用 `CLAUDE_TOKEN_SYNC_ENV=/dev/null` 故意去掉 HTTP sync key 后，日志出现 `http sync unavailable missing CLAUDE_PROXY_SYNC_KEY`、`ssh fallback synced oauth`、`synced oauth via_ssh_fallback`，远端服务保持 active。
- 已收尾：再次正常 `--force` 后 `.claude-token-sync.state` 恢复 `REMOTE_EXPIRES_AT_MS`、`LAST_UNAUTHORIZED_AT=0`、`LAST_SYNCED_EXPIRES_AT_MS`。
当前状态（2026-06-11 Claude 额度快照）：
- 已验证：本机用 Claude Code OAuth token 发最小 `/v1/messages` 请求，Anthropic 响应头会返回 `anthropic-ratelimit-unified-5h-utilization/reset/status` 和 `anthropic-ratelimit-unified-7d-utilization/reset/status`。
- 已改动：`scripts/claude_oauth_proxy.js` 在正常转发上游响应时顺手解析并保存结构化 `rateLimitSnapshot`；`/internal/oauth-status` 会随 token 状态返回最新快照，不额外发探测请求，不记录 token、请求正文或完整响应体。
- 已改动：`routes/miniapp/upstreams.py` 放行清洗后的 `rateLimitSnapshot`；`miniapp/src/ui/tabs/SettingsUpstream.tsx` 可在 OAuth 节点显示 `5h` / `周` 用量和 reset 时间。
- 部署注意：`claude-oauth-proxy.service` 实际运行 `/home/nora/claude-proxy/proxy.js`，不是直接运行仓库里的 `scripts/claude_oauth_proxy.js`。线上生效需要服务器拉代码后，把仓库脚本同步到该实际服务文件，再重启 `du-gateway.service` 和 `claude-oauth-proxy.service`；MiniApp 若要显示最新前端，需要重新构建/同步静态资源。
当前状态（2026-06-25 Claude beta header 减负实测）：
- 已备份：本地备份分支 `backup/claude-beta-headers-before-prune-20260625-200237`；远端实际运行文件备份 `/home/nora/claude-proxy/proxy.js.bak-20260625-200435`。
- 已改动：`scripts/claude_oauth_proxy.js` 的 `anthropic-beta` 删掉 `interleaved-thinking-2025-05-14`、`fine-grained-tool-streaming-2025-05-14`、`token-efficient-tools-2025-02-19`、`effort-2025-11-24`；保留 `claude-code-20250219`、`oauth-2025-04-20`、`prompt-caching-scope-2026-01-05`、`context-management-2025-06-27`。
- 后续调整：为兼容 Opus 4.5 等旧 Claude 4 模型的工具间 thinking，按用户要求先全局加回 `interleaved-thinking-2025-05-14`；另外三个 beta 仍保持移除。
- 已验证：`node --check scripts/claude_oauth_proxy.js` 通过；VPS 拉到包含本改动的 main 后同步到 `/home/nora/claude-proxy/proxy.js` 并重启 `claude-oauth-proxy.service`，服务 active、`127.0.0.1:8082` 正常监听。
- 直打测试：在 VPS 直接请求 `127.0.0.1:8082/v1/models` 返回 9 个模型；直接请求 `127.0.0.1:8082/v1/chat/completions`，`claude-sonnet-4-6` 返回 `测试`，`claude-opus-4-6` 返回 `42` 且 `output_tokens_details.thinking_tokens=0`；未经过 `du-gateway` 聊天转发链路。
当前状态（2026-06-11 Claude proxy 脱管 node 清理）：
- 已查明：`127.0.0.1:8082` 被 `session-41335.scope` 里的脱管 `node proxy.js` 占用，session 来源是 `2026-06-11 16:01:51` 从 `100.105.159.127` SSH 登录；它不在 `claude-oauth-proxy.service` cgroup 内，导致 user systemd 后续每 3 秒拉起新进程时都报 `EADDRINUSE`。
- 已处理：先 `systemctl --user stop --no-block claude-oauth-proxy.service`，再校验 `/proc/757708/cwd=/home/nora/claude-proxy` 且 cmdline 为 `node proxy.js` 后杀掉脱管进程，最后 `reset-failed` 并 `start claude-oauth-proxy.service`。
- 已验证：`claude-oauth-proxy.service` 当前 `active (running)`，Main PID `802552` 位于 `/user.slice/user-1001.slice/user@1001.service/app.slice/claude-oauth-proxy.service`，`GET /v1/models` 返回 `200`。
当前状态（2026-06-11 查岗截图主动性）：
- 已调整：`request_screen_check` 工具说明不再写成只有“她很久没回/她主动说可以看”才适合使用，改为经她确认的查岗申请；渡惦记她、想知道她现在在忙什么、她突然安静，或想带一点玩笑地查岗时都可以主动用。
- 已调整：`pipeline.py` 静态工具提示增加【查岗截图工具】，明确不必等她先说“你可以看”，因为工具本身会让她选择同意或拒绝；仍保留“不要短时间连续发起，拒绝或没理时先停一停”。

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
- APK 打包统一通过 Android Studio；命令行验证也要用 Android Studio 自带 JBR，在 `miniapp/android` 下跑 `JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" sh ./gradlew :app:assembleDebug`。
- 每次对外重新打 APK，尤其是 Android native 层变更或大版本功能变化，必须先提升 `miniapp/android/app/build.gradle` 里的 `versionCode` 和 `versionName`，再打包；打完用 `aapt dump badging app-debug.apk` 确认版本号确实变了。
- APK 产物固定是 `miniapp/android/app/build/outputs/apk/debug/app-debug.apk`；上线下载包时覆盖 `/miniapp/assets/app-debug.apk`，不要另建 `latest`、commit 后缀或版本号后缀 APK 文件。
- 只有 Android native 层变更才需要重新打 APK；只改远程 MiniApp 页面时，通常只需要重建 `miniapp_static` 并部署服务端静态资源。

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
- 历史记录：`docs/wenyou_rules.md` 瘦身为文游开源规则入口；原大文档拆到 `docs/wenyou/core_loop.md`、`docs/wenyou/instance_generation.md`、`docs/wenyou/numeric_growth.md`、`docs/wenyou/rewards_economy.md`、`docs/wenyou/backend_contracts.md` 和物品系统文档。后续物品系统入口已改为 `docs/wenyou/item_ability_system.md`，旧成长路线不再作为当前规则。
- 已验证：本轮为文档拆分改动，已检查文档结构、索引、Markdown 栅栏和尾随空格；未运行代码测试。
- 历史备注 / 后续状态：该阶段尚未改 `routes/miniapp/wenyou.py`、`services/wenyou_service.py` 或 `miniapp/src/ui/tabs/WenyouTab.tsx`；后续已接入自由任务者数量、属性点分配、晋升、旧能力/成长模板、道具目录、商店/抽卡/奖励复用目录、复活债务、惩罚副本、奖励掉落和 UI。默认武器装备养成链路已取消。

当前状态（2026-05-17 文游命运裂隙 UI）：
- 已完成：`miniapp/src/ui/tabs/WenyouTab.tsx` 新增“命运裂隙”一级入口和前端抽卡演示流程，右上角裂隙按钮可进入，支持单抽/十连、100/1000 积分本地预览扣除、十连 C+ 兜底、裂隙展开动画、卡背结果区、逐张/批量显影和确认返回；`miniapp/src/styles.css` 参照下载 UI 合集的赛博黑白/故障/扫描线/翻牌风格重做视觉，并修正十连结果区与底部操作按钮重叠问题。
- 已验证：`npm -C miniapp run build` 通过；本地 `http://127.0.0.1:5174/miniapp/` 打开后已点击进入“命运裂隙”、执行十连、`REVEAL DATA` 显影、`CONFIRM SYNCHRONY` 返回；本地 Vite 没接 Flask 时商店/会话接口会 404，但裂隙 UI 使用前端预览积分可继续看动画。
- 未完成 / 不要碰：命运裂隙目前只是前端 UI/动画与本地结果演示，尚未接后端真实扣积分、抽卡记录、道具入背包、概率审计和 100 抽大保底持久化；后续接后端时继续限定文游相关文件，不要动 QQ connector、小爱、共读和其他半成品。

当前状态（2026-05-17 文游命运裂隙后端/对象背包）：
- 已完成：`services/wenyou_service.py` 新增对象化背包兼容层，旧字符串背包会读成 `{uid,id,name,kind,category,rarity,quantity,source}` 对象；钱包开始保存长期 `inventory` 和每池 `gacha.pools` 保底计数。新增 `roll_gacha` 后端规则：仅 `hub/settlement` 可抽，单抽 100/十连 1000，积分不足直接拒绝，按混合池概率抽取，10/30/100 抽保底分别记录，A/S 高阶物按当前阶位封印；重复结果后续已改为按当前回收/材料/模板规则处理，不再作为升级材料链路。`routes/miniapp/wenyou.py` 新增 `/miniapp-api/wenyou/gacha/roll`；`miniapp/src/ui/tabs/WenyouTab.tsx` 的命运裂隙改为调用后端，不再使用前端预览积分凭空抽。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py storage/r2_store.py` 通过；`.venv/bin/python - <<'PY' import app` 通过；内存 monkeypatch 烟测覆盖 0 积分不能抽、副本中不能抽、结算阶段扣 100 并写对象背包；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BanpyNQn.js`、`miniapp_static/assets/index-Cf0MmulS.js`、`miniapp_static/assets/index-BVLf9Srz.css`，并检查当前 `index` 引用的静态 chunk 均存在。
- 历史备注 / 后续状态：此阶段后，属性点分配、阶位晋升、复活债务、奖励掉落、出售和结构化物品使用已逐步接入；默认装备槽、锻造、维修、拆解和武器养成链路已按后续规则取消。继续限定文游相关文件，不要动 QQ connector、小爱、共读和其它半成品。

当前状态（2026-05-17 文游候选扩展并行化）：
- 已完成：候选副本点击进入不再同步等待一个巨大 DS 请求。`/miniapp-api/wenyou/story` 收到 candidate 后创建后台扩展任务并返回 `expanding/job_id`；新增 `/miniapp-api/wenyou/story-job/<job_id>` 供前端轮询。后台扩展先让 DS 生成自然语言核心短稿，再并行生成自然语言蓝图短稿和开场正文；后端用候选 seed + 文本块组装完整 framework，不再要求 DS 输出严格 JSON，避免单个超大 JSON 请求拖到网关/浏览器超时或因解析失败中断；失败时返回明确子任务错误，不造本地假副本。
- 已验证：`python3 -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py` 通过；`.venv/bin/python - <<'PY' import app` 通过；monkeypatch 烟测 `generate_framework_from_candidate` 可用文本 core/blueprint/opening 组装 framework；`npm -C miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BSKgBGT4.js`、`miniapp_static/assets/index-C6dONsQ4.js`、`miniapp_static/assets/index-BVLf9Srz.css`。
- 未完成 / 不要碰：随机开局和手写自定义关键词仍是同步完整框架生成；本次只修“大厅候选 -> 扩展完整副本”的超时路径。继续限定文游相关文件，不要动 QQ connector、小爱、共读和其它半成品。

当前状态（2026-05-17 文游后端规则补齐）：
- 已完成：按 `docs/wenyou/*.md` 先补可落地后端：六基础属性 `str/con/agi/int/spi/luk`、`spi_current/spi_max`、派生数值、属性软上限 D14/C20/B28/A38/S50；GM 事件结算的精神减免改用 `spi_current`；升级每级给 3 点自由属性点；新增固定规则接口 `/miniapp-api/wenyou/player/attributes`、`/player/promote`、`/player/revive`；晋升会扣积分、校验通关记录/债务/污染/特殊试炼并解封对应阶位物品；复活会扣积分、不足写债务、恢复半血半 SAN 并添加 `复活疲惫`；奖励结算从“只记录次数”升级为按难度/评级 roll 稀有度和类别，并把具体奖励写入钱包与当前背包；当时普通商店限制 7-8 件 D/C 商品，低概率最多 1 件 B，并曾使用旧成长池。
- 已验证：`python3 -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py` 通过；`.venv/bin/python - <<'PY' import app` 通过；路由表确认 `/miniapp-api/wenyou/player/attributes`、`/promote`、`/revive` 已注册；monkeypatch 烟测覆盖属性分配、D->C 晋升、复活债务、精神伤害按 `spi_current`、商店稀有度边界、旧抽卡池迁移、S 评级结算奖励入背包；`git diff --check -- services/wenyou_service.py routes/miniapp/wenyou.py` 通过。
- 历史备注 / 后续状态：内容包/SQL 化道具目录、出售、旧能力/成长模板流程、前端个人空间/角色面板已后续接入或重做；默认装备槽、锻造、维修、拆解已取消，不再作为待办；惩罚副本队列、自定义/随机开局并行化仍可作为独立后续项。

当前状态（2026-05-17 文游道具目录续）：
- 已完成：物品系统文档的道具生成提示词补充 D/C 普通池 25%-35% 生活怪梗比例，并明确玩梗不是独立分类，仍需落到后端可执行效果；`docs/wenyou/item_catalog_draft_c.md` 保持 45 个 C 级道具和原定价区间，把一批过于正经的名称改成生活化/怪谈化表达，少量补了对应代价。
- 已验证：已跑 C 级道具表结构校验、数量/分类/时代标签/价格区间检查、Markdown 尾随空格检查和对应文档 diff check。
- 历史备注 / 后续状态：该阶段时 C 级道具仍是草稿目录；后续已统一生成 `content/default/items.json` 与 `content/default/item_catalog.sql`。默认装备耐久/锻造/拆解后端链路已取消，耐久只作为背包物品使用规则的一部分。

当前状态（2026-05-17 文游道具目录完备草稿）：
- 已完成：新增 `docs/wenyou/item_catalog_draft_b.md`、`docs/wenyou/item_catalog_draft_a.md`、`docs/wenyou/item_catalog_draft_s.md`，补齐 B/A/S 通用道具草稿目录；B 级 35 个，A 级 18 个，S 级 10 个，均包含工具、防护物、材料、规则、位移、结算、彩蛋道具、时代标签、使用限制、代价、耐久或封印说明，并按功能补草稿价格。
- 已验证：已跑 D/C/B/A/S 五张道具表结构校验、数量/分类/时代标签/价格区间/重复名检查、Markdown 尾随空格检查和对应文档 diff check。
- 历史备注 / 后续状态：五张 Markdown 表后续已作为审校源生成 `content/default/items.json` 与 `content/default/item_catalog.sql`；默认装备耐久/锻造/维修/拆解后端链路已取消，物品耐久/次数由背包使用规则处理。

当前状态（2026-05-17 文游 S 级定价校准）：
- 已完成：修正 S/传说级道具价格锚点：抽卡仍为单抽 100、100 抽随机 S 大保底 10000；S 级若进入当时的高阶指定购买入口或活动商店，价格必须高于随机保底成本，草稿表统一调到 12000-22000，并在规则入口、物品系统和奖励经济文档写明防套利约束。
- 已验证：已跑 S 级道具表价格区间校验、五张道具表基础结构校验和对应文档 diff check。
- 未完成 / 不要碰：当前只校准文档价格，不改后端抽卡价格、商店接口和数据库字段；后续 SQL 入库时还要把 `shop_allowed/gacha_allowed/seal_rank` 明确拆出。

历史状态（2026-05-17 文游旧高阶兑换开启条件，现已废弃）：
- 历史记录：当时曾把旧高阶兑换入口设为 C 阶后开启。当前规则已经改为普通商店低概率越级货架，不再保留独立高阶兑换入口。
- 已验证：当时已跑过对应文档检查；当前口径以 2026-05-23 文游核心能力与商店简化记录为准。
- 未完成 / 不要碰：当前只补文档规则，没有改后端商店接口、钱包、UI 或数据库字段；后续实现时再把 `shop_id`、`rank_min`、`seal_rank` 和库存校验接进 ruleset。

当前状态（2026-05-17 文游怪物系统草稿）：
- 已完成：新增 `docs/wenyou/monster_system.md`，补齐怪物生成流程、遭遇预算、普通怪/精英怪/Boss 面板模板、战斗与规避结算、Boss 默认不可正面战胜规则、弱点/抗性系统、怪物生成提示词和平衡目标；`docs/wenyou/instance_generation.md` 改为引用详细怪物系统，规则入口文档地图同步新增怪物系统。
- 已验证：已跑怪物模板轻量平衡模拟、Markdown 结构检查和 `git diff --check -- docs/wenyou/monster_system.md docs/wenyou/instance_generation.md docs/wenyou_rules.md docs/DEBUG_INDEX.md`。
- 未完成 / 不要碰：当前只补文档规则，未改后端怪物生成、战斗结算接口或 UI；后续需要把 `encounter_profile` schema、怪物实例状态和战斗 state_patch 接入 ruleset。

当前状态（2026-05-17 文游运行时状态缓存规则）：
- 已完成：新增并补充 `docs/wenyou/runtime_state.md`，明确副本正式生成后要缓存 `instance_runtime_state`，拆分 `public_state/gm_state/rules_state/archive_state`；任务进度、线索、地点、NPC、怪物实例、威胁时钟、背包物品和奖励上下文都由后端按 `state_patch` 更新，GM/DS 每轮只接收裁剪后的上下文、输出叙事和非权威 `event_intent/state_proposals`。补了最小可运行闭环和 DS 提示词最小约束；NPC 任务者降为立场/意图/使坏概率/存活状态，不强制关系值；结算评级只看真实玩家角色/玩家队伍的主线、普通支线、隐藏支线、隐藏结局、特殊成就和损耗记录，不把线索数量或 NPC 自身结局作为独立评分项。同步更新规则入口、核心循环、副本生成、奖励经济和后端契约。
- 已验证：已跑 `rg` 检查 runtime state、GM context、state proposals、NPC 最小字段、结算对象、NPC 不参与玩家评级、结算评级口径和面板读取规则引用；`git diff --check -- docs/wenyou/runtime_state.md docs/wenyou/core_loop.md docs/wenyou/rewards_economy.md docs/wenyou/backend_contracts.md docs/wenyou_rules.md docs/DEBUG_INDEX.md` 通过。
- 未完成 / 不要碰：当前只补文档规则，没有改 `services/wenyou_service.py`、前端面板或数据库；后续实现要把现有 GM 文本/主神面板解析迁到 `runtime_state -> public_view -> state_patch`。

当前状态（2026-05-17 文游 DS/GM 提示词对齐运行时规则）：
- 已完成：更新 `services/wenyou_service.py` 的副本生成、候选扩展和每轮 GM 提示词：副本生成必须先产出 `instance_blueprint` 与 `encounter_profile`；DS/GM 不再作为状态事实源，不每轮重写任务、线索、背包、奖励或完整主神面板；每轮 GM 只输出叙事、事件意图、规则/线索更新建议、隐藏威胁时钟变动和非权威 `state_proposals`。NPC 任务者改为公开立场/意图/使坏概率/存活状态，真实立场进 `gm_secret.npc_private_state`；结算提示改为只评价玩家/玩家队伍。
- 已验证：已跑 `.venv/bin/python -m py_compile services/wenyou_service.py`、GM 模板 `.format()` 烟测、关键提示词 `rg` 检查和 `git diff --check -- services/wenyou_service.py docs/DEBUG_INDEX.md`。
- 未完成 / 不要碰：这次只改现有 DS/GM prompt 与兼容字段归一化，不改前端、数据库、商店抽卡接口或完整 runtime_state 落地逻辑；后续需要再把 `state_proposals` 真正接入 ruleset/state_patch 执行层。

当前状态（2026-05-17 文游道具表结构化落地）：
- 已完成：新增 `scripts/build_wenyou_item_catalog.py`，把 D/C/B/A/S 五张 Markdown 道具审校源表生成 `content/default/items.json`、`content/default/item_catalog.sql` 和 `schemas/item.schema.json`；当前共 178 个通用道具，字段包含 `id/name/rarity/category/item_type/effect/effect_json/requirements/use_cost/tags/era_tags/use_phase/consume/stackable/shop_allowed/gacha_allowed/seal_rank/price/weight/enabled`。`services/wenyou_service.py` 已改为商店、抽卡和结算奖励优先读取该内容表，失败时才回退旧内置小列表；多次使用/耐久字段会随背包物品实例保留。
- 已验证：已跑 `.venv/bin/python scripts/build_wenyou_item_catalog.py` 生成 178 条；已做 JSON/SQL/Schema 结构校验、SQLite 导入 `content/default/item_catalog.sql` 并查询 178 条、服务导入与商店/抽卡目录烟测、`.venv/bin/python -m py_compile services/wenyou_service.py scripts/build_wenyou_item_catalog.py`、`git diff --check`。
- 历史备注 / 后续状态：前端背包和出售接口已后续接入；装备槽 UI、锻造、维修、拆解已取消，不再作为默认待办。完整道具效果 DSL 仍可后续扩展，但当前以结构化 `effect_json/requirements/use_cost` 和后端规则判定为准。

当前状态（2026-05-17 文游局内获得物品入背包）：
- 已完成：`services/wenyou_service.py` 的 GM 事件意图区分两类局内物品：`acquire_task_item` 用于副本内任务物品/临时物品，允许 S 级强效果、不受副本难度上限限制，写入当前 session 背包并标记 `carry_out=false/temporary=true/quest_item=true`；`acquire_item` 用于可带出通用物品，按 `content/default/items.json` 查 item_id 或精确物品名，并按“副本难度最多 +1 阶”的常规掉落上限校验，通过后写入当前 session 背包与 `state_patch.changes.inventory_add`。隐藏提议、内容表不存在、越级可带出物都会被忽略。
- 已验证：已跑局内获得物品烟测：D 级副本公开提议 S 级 `acquire_task_item` 能加入局内背包且保存钱包时会被过滤；公开提议 `wy_d_002` 能作为可带出通用物加入背包；公开提议 A 级 `acquire_item` 被难度上限拒绝；已跑 `.venv/bin/python -m py_compile services/wenyou_service.py` 和 `git diff --check`。
- 未完成 / 不要碰：副本专属唯一物品还没有独立 `instance_unique_rewards` 内容包表；当前 `acquire_task_item` 是运行时临时实例，不进入通用目录。
- 历史备注 / 后续状态：出售和背包物品使用已后续接入；默认装备槽、锻造、维修、拆解已取消，不再作为 UI/接口待办。

当前状态（2026-05-17 文游隐藏好结局唯一奖励）：
- 已完成：补第三类物品提议 `acquire_unique_item`，用于隐藏好结局、Boss 被感化/超度后赠予的可带走唯一奖励；这类物品不查通用道具表、不受副本难度掉落上限限制，但必须写 `name/rarity/effect/reason`，并携带 `seal_rank` 或 `requirements`（如 `level_min`、`spi_min`、`int_min`）。后端写入当前背包时标记 `carry_out=true/unique=true`，如果当前等级、阶位或属性未达标则 `sealed=true` 并写 `sealed_reason`；只有无额外属性/等级门槛的阶位封印会在晋升时自动解封。
- 已验证：已跑烟测：D 级副本公开提议 S 级 `acquire_unique_item` 可进背包并可带出，但因 `seal_rank=A` 与 `spi_min=18` 被封印；`_carryable_inventory` 会保留该唯一奖励；已跑 `.venv/bin/python -m py_compile services/wenyou_service.py` 和 `git diff --check`。
- 未完成 / 不要碰：属性/等级门槛达成后的自动解封还没接加点/升级流程，目前只记录封印原因；后续接成长系统时再统一扫描背包解封。

当前状态（2026-05-17 文游规则功能补齐）：
- 已完成：文游测试积分改为显式环境变量 `WENYOU_TEST_MIN_POINTS` 控制，未配置时不再默认白送 100000 积分；新开副本发放新手 6 点自由属性点并写入 `event_log/state_patch`；新增 `content/default/abilities.json`，能力学习优先读取内容包，并支持消耗抽卡获得的能力模板学习；成长面板改为读取后端下发的可学能力和进化路线，不再只写死“快速包扎/规则试探/人类稳定”；怪物遭遇补逃跑/规避的路线、道具、干扰修正，Boss 逃跑 DC 修正，成功/部分成功/失败分层，`roll_log` 记录 seed、d20、score、dc 和 bonus；击退/规避怪物会写 reward tag 和结算成就。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import services.wenyou_service / routes.miniapp.wenyou / app` 通过；新手点数与遭遇逃跑烟测通过；`git diff --check -- services/wenyou_service.py routes/miniapp/wenyou.py miniapp/src/ui/tabs/WenyouTab.tsx miniapp/src/styles.css content/default/abilities.json` 通过（仅 `miniapp/src/styles.css` 既有 CRLF 提示）；`npm run build` 通过，当前文游 chunk 为 `miniapp_static/assets/WenyouTab-Cx1S-zGk.js`。
- 未完成 / 不要碰：本轮没有清理既有 `miniapp_static/assets/*` 旧哈希产物；完整 `evolution_paths.json` / `reward_tables.json` 内容包和更细的 Boss 封印进度 UI 还可继续拆。

当前状态（2026-05-17 文游规则功能继续补齐）：
- 已完成：Boss/怪物从纯文本提示补成后端裁判：怪物实例带 `default_invincible/can_be_killed/stability/seal_progress/seal_target`，正面攻击 Boss 默认不可硬杀；新增削弱/试探与封印/净化/超度动作，按属性、d20、线索/媒介 bonus 结算，并写入 monster state、reward tag、成就和 `state_patch`。局内快捷决策补“削弱/封印”，怪物面板显示稳定度、封印进度和处理方式。强制惩罚副本补 `forced_instance` 运行状态，支持 NPC 打工/惩罚工单身份、暴露计数、结算成功解除或失败追加债务/污染。奖励表从硬编码扩展到默认 JSON 内容包；后续旧成长路线表已删除，当前只保留核心能力原型表和奖励表。道具效果 DSL 扩展到状态添加、威胁时钟、线索缓存、安全休整节点、污染/债务变化；客户端不再暴露精确威胁时钟 value/max，只给阶段状态。唯一奖励重复获得会转回响碎片；奖励 roll 会按 `reward_context` 和 `tag_category_boosts` 做主题类别偏置。
- 已验证：当时 `.venv/bin/python -m py_compile app.py services/wenyou_service.py routes/miniapp/wenyou.py scripts/wenyou_rules_smoke.py` 通过；`import services.wenyou_service / routes.miniapp.wenyou / app` 通过；烟测覆盖 Boss 不可硬杀、削弱、封印、强制工单结算、唯一奖励重复转碎片和奖励类别偏置；当前内容包校验见后续 2026-05-23 记录。
- 未完成 / 不要碰：抽卡动画/音效按用户前面要求暂时不继续碰；当前仍不清理大量既有 `miniapp_static/assets/*` 旧哈希产物。后续若继续，只做文游内容包扩容或更细的副本专属唯一奖励表，不碰非文游模块。

当前状态（2026-05-17 文游抽卡稀有度颜色）：
- 已完成：命运裂隙卡牌稀有度颜色调整为 D=白/银、S=金色；A 从原金色挪为橙红系，避免与 S 撞色。只改抽卡卡牌稀有度 CSS，不改抽卡逻辑、概率、动画流程或其他页面。
- 已验证：`git diff --check -- miniapp/src/styles.css` 通过（仅提示该文件既有 CRLF 会在 Git 触碰时转 LF）；`npm run build` 通过。当前静态入口引用 `miniapp_static/assets/index-DqV2cCNW.js`、`miniapp_static/assets/index-D5v3i7a_.css`，当前文游 chunk 为 `miniapp_static/assets/WenyouTab-BqBXklcv.js`。
- 未完成 / 不要碰：本次不清理历史 `miniapp_static/assets/*` 旧 hash 产物；抽卡音效/动画后续单独做。

当前状态（2026-05-21 文游首页/个人空间/新手副本收束）：
- 已完成：主神空间首页回到三条系统状态条（主神积分、等级阶位、副本状态），一级入口文字本地化为“副本大厅 / 命运裂隙 / 系统商店 / 个人空间”，去掉右下角同步按钮并保留方正点击波动；个人空间实际读取 wallet 背包和双玩家面板，归档后可使用和出售钱包物品；`/wenyou/end` 改为结算后立即归档，前端随即进入个人空间归档页；默认未首通用户的第一个候选/空开局会出现固定新手副本 `T-000 白箱回廊`，仅玩家一和渡参与，无其他任务者 NPC；首次标准通关在基础奖励外发新手礼包（初级治愈药剂、初级精神药剂、双玩家自由属性点 +6）且只发一次。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py` 通过；`.venv/bin/python - <<'PY' import app` 通过；mock 烟测覆盖新手候选优先、空开局进入 `白箱回廊`、首次标准通关发礼包并归档、二次通关不重复发礼包、无 active session 的钱包使用/出售；`npm --prefix miniapp run build` 通过，当前静态入口引用 `miniapp_static/assets/index-ChzfTziK.js`、`miniapp_static/assets/index-Qv12-DO-.css`，文游 chunk 为 `miniapp_static/assets/WenyouTab-BYm4OjTy.js`；本地 preview `http://127.0.0.1:5175/miniapp/` 进入文游页无前端崩溃/动态 import 缺失（API 404 仅因 preview 未挂后端）。
- 未完成 / 不要碰：本轮按用户要求没有接“渡主动使用背包道具”；没有清理大量既有 `miniapp_static/assets/*` 旧 hash 产物；非文游脏文件仍保持原样不碰。

当前状态（2026-05-21 文游 AI 玩家接入对齐）：
- 已完成：按 `docs/wenyou/ai_player_integration.md` 补 AI 玩家真实玩家位：wallet 兼容旧 `points/gacha/inventory` 的同时新增 `wallets[player_id]`、`inventories[player_id]`，`player2` 默认为 `controller=ai` 且拥有独立积分、债务、抽卡保底、背包和个人 ledger；商店、抽卡、出售和道具使用均支持 `actor_id/player_id`，默认仍是 `player1`，AI 工具固定可传 `player2`。新增 `summarize_story_for_ai_player`、`compose_ai_player_context`、`get_ai_player_context` 与 `ai_player_buy_item / ai_player_roll_gacha / ai_player_inventory_action / ai_player_use_item / ai_player_transfer`，并补 `/wenyou/ai-player/*` 路由；渡自动行动 prompt 会收到裁剪后的只读 AI 玩家上下文，不再只看共享背包文本。所有 AI 玩家消费/使用/转交写入个人 ledger 和 `state_patch`，失败返回结构化 `error_code`。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import services.wenyou_service / routes.miniapp.wenyou / app` 通过；mock 烟测覆盖 AI 玩家上下文、`player2` 用独立积分买商店、抽卡不扣 `player1`、转交积分给 `player1`、使用 `player2` 背包里的精神药剂并写入 `player2` ledger；`git diff --check -- services/wenyou_service.py routes/miniapp/wenyou.py` 通过。
- 未完成 / 不要碰：这次只对齐后端账户、工具和上下文；没有改文游前端 UI 去展示 AI 玩家消费明细/双背包切换，也没有把真实模型工具调用 loop 接成自动买卖抽卡执行器。用户新加的 `docs/wenyou/ai_player_integration.md` 等文档保持原样，不擅自纳入提交范围；非文游脏文件和旧静态 hash 产物继续不碰。

当前状态（2026-06-04 文游 GM 上下文压缩接入）：
- 已完成：文游连续性卡片不再只是回合后维护；`services.wenyou.gm_context.compose_gm_context(...)` 现在会把 runtime public/rules state、当前任务/地点/线索/规则/玩家状态、对讲机信号、惩罚副本状态、文游连续性卡片和最近少量 history 组装为 `[WENYOU_GM_CONTEXT]`，`services.wenyou_service._build_gm_messages(...)` 会在每轮最新玩家行动前把该块塞给 GM。空卡片不触发 history 缩窗；有卡片时只保留最近 8 条原始 history，无卡片时保留最近 14 条。旧的未引用 `_build_wenyou_card_context` 已移除。
- 已完成：新增只读调试接口 `GET /miniapp-api/wenyou/debug/gm-context`，用于查看下一轮 GM 会收到的压缩上下文、卡片更新时间、history 总数和实际 GM message 角色列表；`docs/wenyou/backend_contracts.md`、`docs/wenyou/runtime_state.md` 已同步真实入口。
- 已完成：新增外部 AI 玩家工具桥：`GET /miniapp-api/wenyou/ai-player/tools` 返回工具 schema 与只读上下文，`POST /miniapp-api/wenyou/ai-player/tool-call` 执行 `buy_item/roll_gacha/inventory_action/use_item/transfer`，`GET /miniapp-api/wenyou/ai-player/sse` 以 SSE 初始化流发送 hello/tools/context/done；这不是标准 MCP 服务，旧 `/mcp/*` 仅保留兼容别名；仍由 Rules Engine 写 `state_patch/ledger`，不自动推进回合。
- 已完成：GM 输出展示/入历史前新增内部上下文清洗，若模型误把 `[WENYOU_GM_CONTEXT]`、连续性卡片、后端规则态摘要等 GM-only 内容吐出，会先由 `services.wenyou.text_sanitize._strip_gm_context_blocks(...)` 剥离，避免污染前端与回合历史。
- 已完成：AI 玩家上下文拆成 `tool/turn/channel` 三种模式：工具桥保留商店、卡池、钱包、保底和流水；渡局内行动只拿剧情/任务/线索/地点/角色状态/背包/可用道具转交；对讲机只拿局面和频道信息，不再注入商店货架、卡池消耗、最近流水。渡行动 system 文案改为“和玩家一一起玩文游，自己是玩家二”，移除“控制渡”“不是 GM/规则引擎”“后端事实源”这类后台口吻。
- 已验证：`.venv/bin/python -m py_compile services/wenyou/gm_context.py services/wenyou_service.py routes/miniapp/wenyou.py app.py scripts/wenyou_rules_smoke.py` 通过；`.venv/bin/python scripts/wenyou_rules_smoke.py` 通过，覆盖 Boss 不可硬杀、削弱/封印、强制惩罚队列、NPC 惩罚契约、暴露计数、无怪物生态兜底怪物与逃跑 patch；本地 monkeypatch 烟测覆盖有卡片/无卡片两种 `_build_gm_messages` 窗口行为；`import app` 确认 `/debug/gm-context`、`/ai-player/*` 与 `/mcp/*` 兼容路由存在；工具 manifest/未知工具 smoke 通过；`git diff --check` 通过。
- 未完成 / 不要碰：这次不改前端 UI、不改存档数据、不把文游卡片混入普通聊天动态召回；卡片更新仍在 GM 返回后同步执行，后续若模型慢再单独改后台队列。

当前状态（2026-07-08 文游 SQLite 主存储）：
- 已完成：新增 `storage/wenyou_sqlite_store.py` 和 `config.WENYOU_SQLITE_DB`（默认 `data/wenyou.sqlite3`）；`storage/r2_store.py` 的 Wenyou 同名方法改为 SQLite 优先，覆盖 active session、wallet、candidate cache、continuity card、last archive、archive list/detail。旧 R2 Wenyou key 只在 SQLite 无记录时 read-through 回填；`WENYOU_R2_BACKUP_ENABLED=1` 时才继续双写 R2 备份。删除 active session 会在 SQLite 留空记录，避免旧 R2 session 被回读复活；admin `wipe_local_data()` 同步清空 Wenyou SQLite。
- 已完成：开源分发/数据表/后端契约文档补默认 SQLite 存储边界，完整开源版按 `WenyouStore` 接口替换存储，不要求接入方使用 R2。
- 已验证：`.venv/bin/python -m py_compile config.py storage/wenyou_sqlite_store.py storage/wipe_local.py storage/r2_store.py services/wenyou_service.py routes/miniapp/wenyou.py` 通过；本地临时 SQLite + monkeypatch R2 smoke 覆盖 session 保存/删除 tombstone、wallet 保存读取、空 game_id 归档为 `unknown`、归档列表按 `endedAt` 倒序、详情读取和清表。
- 未完成 / 不要碰：本轮不迁移真实线上旧 R2 Wenyou 全量归档，不改前端 UI、不改文游规则、不改 GM/AI 玩家模型链路；如需线上切换前完整导入历史 archive，再单独做只读 R2 backfill 脚本。

当前状态（2026-05-22 文游装备栏移除）：
- 已完成：按用户决定删除默认装备养成链路，背包物品统一走“使用 / 出售 / 转交”；后端移除穿戴、维修、锻造、拆解入口和装备加成计算，`/wenyou/item/equip`、`/wenyou/item/repair` 不再注册；AI 玩家 `inventory_action` 只保留 `use/sell`；内容表 `item_type` 收敛为 `consumable/tool/material/special`，奖励表 `gear` 分类改为 `tool_item`；前端个人空间背包不再显示装备/维修动作，角色面板不再展示装备摘要；相关 wenyou 文档和本索引已同步到无装备栏版本。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py services/chat_tools.py routes/chat.py` 通过；`import app / services.wenyou_service / routes.miniapp.wenyou` 通过；mock 烟测覆盖装备/维修路由不存在、出售路由存在、工具道具按背包使用扣耐久、不写入 `equipment/gear`、AI 工具 schema 无 `slot`；`npm --prefix miniapp run build` 通过；`git diff --check` 针对本轮文游文件通过。
- 未完成 / 不要碰：仍不清理大量既有 `miniapp_static/assets/*` 旧 hash 产物；非文游脏文件继续保持原样。`services/wenyou_service.py` 里保留少量旧存档兼容清理，只负责丢弃历史 `gear/equipment/weapons` 字段，不是新功能入口。

当前状态（2026-05-22 文游成长简化与残留复扫）：
- 历史记录：当时成长链路收敛为“升级给属性点、阶位晋升、抽卡/奖励得到具体模板”，并移除能力碎片、成长令牌等复杂升级链；后续 2026-05-23 已继续砍掉多能力模板和旧身体路线，改为单一核心能力。
- 已验证：`python3 -m json.tool` 覆盖 `schemas/ability.schema.json`、`schemas/item.schema.json`、`content/default/items.json`、`content/default/abilities.json`、`content/default/reward_tables.json` 通过；`python3 -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py` 通过；`python3 scripts/build_wenyou_item_catalog.py` 重建 178 个默认道具与 SQL seed；`npm --prefix miniapp run build` 通过；本轮复扫整个仓库无旧字段命中；额外删除 65 个残留旧文案的 `miniapp_static/assets/WenyouTab-*.js` 哈希产物；`git diff --check` 针对本轮文件和已删除静态产物通过。
- 未完成 / 不要碰：非文游脏文件继续保持原样；历史阶段记录里的旧 TODO 文字不代表当前规则，暂不重写旧日志。

当前状态（2026-05-23 文游遭遇顺序简化）：
- 已完成：按用户决定砍掉独立行动顺序数值；后端玩家默认状态、允许字段和派生重算不再包含旧顺序字段，遭遇逃跑/规避判定只吃敏捷修正、场景 bonus 和怪物速度/警戒；前端角色面板不再展示该派生项，敏捷说明改为闪避、潜行、追逐；`docs/wenyou/numeric_growth.md`、`monster_system.md`、`instance_generation.md` 同步为“剧情态势决定是否先结算威胁，默认给玩家行动窗口”。
- 已验证：旧行动顺序关键词覆盖文游源码/文档无命中；`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app / services.wenyou_service / routes.miniapp.wenyou` 通过；`npm --prefix miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BU6jD-Ek.js`、`miniapp_static/assets/index-wCtRX__7.js`。
- 未完成 / 不要碰：本轮只砍独立行动顺序数值，没有调整怪物战斗、逃跑 DC 或其他文游 UI；非文游脏文件和旧静态 hash 产物继续保持原样。

当前状态（2026-05-23 文游核心能力与商店简化）：
- 已完成：按用户决定彻底移除独立高阶兑换入口和复杂身体路线；普通商店按玩家阶位低概率出现越级物，高阶商品仍走封印/降级；抽卡池移除旧能力池和旧成长池，保留 `mixed/tool_pool/supply_pool/limited_pool`；玩家改为只有一个 `core_ability`，新手副本开始为空，首次标准通关后由后端按行为倾向生成；前端角色面板只展示核心能力，不再展示能力槽、休眠能力或旧身体路线；默认内容包删除旧路线表，`abilities.json` 改为核心能力原型；道具目录材料文案同步为核心能力稳定/变形，不再写旧成长模板。
- 已验证：文游源码/文档/内容表复扫无旧独立商店、旧成长路线、旧能力池、多能力槽等旧规则命中；`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app / services.wenyou_service / routes.miniapp.wenyou` 通过；mock 烟测覆盖新手通关按行为生成 `core_observe/core_escape`、D 阶普通商店 7-8 件且无独立高阶兑换入口；`python3 scripts/build_wenyou_item_catalog.py` 重建 178 个默认道具与 SQL seed；`npm --prefix miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-B3BAv5Hl.js`、`miniapp_static/assets/index-CShTyGDt.js`、`miniapp_static/assets/index-p3Anm5wZ.css`。
- 未完成 / 不要碰：没有清理大量既有 `miniapp_static/assets/*` 旧 hash 产物；非文游脏文件继续保持原样。旧存档里若曾有多能力或旧成长字段，后端只做读取时清理/拒绝，不恢复旧玩法。

当前状态（2026-05-23 文游核心能力画像记录）：
- 已完成：新手副本首次标准通关生成 `core_ability` 时，同步保存 `core_ability_profile`；画像包含行为倾向 `scores`、选中的 `picked`、前几项 `source_tags`、能力 id/name、算法版本、历史窗口和生成时间，并写入角色状态、`newbie_starter_pack` 事件补丁和 wallet ledger，方便之后解释“为什么生成这个能力”。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；mock 烟测确认观察/逃脱文本会分别生成 `core_observe/core_escape`，并写入对应 `core_ability_profile.scores/picked`；`git diff --check` 针对本轮文件通过。
- 未完成 / 不要碰：本轮只补核心能力生成画像，不改前端展示、不改能力生成关键词表、不清理旧静态 hash 产物；非文游脏文件继续保持原样。

当前状态（2026-05-23 文游固定新手副本）：
- 已完成：`T-000 白箱回廊` 收束为默认内容包的手写固定新手副本，不走随机生成；开局改成小说式醒来进入白色回廊，三段低危结构为醒来、灯色规则、出口选择；每段都允许观察、冲刺、保护、询问、破坏、规则试探或抗压等多种通关方式，只用于记录玩家自然倾向并生成 `core_ability_profile`。核心能力关键词补充自然说法和 `observe/escape/protect/combat/social/rule/resilience` 标签。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app / services.wenyou_service / routes.miniapp.wenyou` 通过；固定副本结构烟测确认 `T-000 白箱回廊`、`is_tutorial=True`、三段主线为 `醒来/灯色规则/出口`；核心能力倾向打分烟测可识别观察、规则和保护；`git diff --check` 针对本轮文件通过。
- 历史备注：该轮未接玩家名登记 UI；下一条“文游首次进入 UI 流程”已补上。仍不清理旧静态 hash 产物，非文游脏文件继续保持原样。

当前状态（2026-05-23 文游首次进入 UI 流程）：
- 已完成：`/miniapp-api/wenyou/status` 在无进行中副本时返回 `entry.tutorial_required/player_name/tutorial_code/tutorial_title`；`/wenyou/story` 接收 `player_name` 并写入文游 wallet、当前副本 framework 和角色 `display_name`。MiniApp 首页在新手礼包未领取且无进行中副本时，不再展示主神空间大厅，而是展示小说式醒来文案、代号输入和“进入白箱回廊”按钮；确认后直接启动固定新手副本。角色面板和状态脚注会优先展示玩家代号。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app / services.wenyou_service / routes.miniapp.wenyou` 通过；本地烟测确认 wallet 代号可写入白箱回廊 framework 和 session stats；`npm --prefix miniapp run build` 通过，当前构建输出 `miniapp_static/assets/WenyouTab-BY00vddN.js`、`miniapp_static/assets/index-C6F-5rcM.js`、`miniapp_static/assets/index-He2_qc1y.css`；`git diff --check` 针对本轮文件通过。
- 未完成 / 不要碰：本轮只接首次进入和代号落库，不改通关后主神空间解锁细节、不改候选副本规则、不清理旧静态 hash 产物；非文游脏文件继续保持原样。

当前状态（2026-05-23 文游服务拆分第一阶段）：
- 已完成：`services/wenyou_service.py` 开始拆分，先把无状态基础层移到 `services/wenyou/` 包：`constants.py` 承接难度、阶位、奖励、成长、教学副本等常量；`phase.py` 承接阶段归一化、阶段标签和商店开放判断；`common.py` 承接 JSON 提取、slug、非负整数和稀有度排序工具。原 `wenyou_service.py` 改为从新包导入，业务逻辑和路由行为不改。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py services/wenyou/phase.py services/wenyou/common.py services/wenyou/constants.py routes/miniapp/wenyou.py app.py` 通过；`PYTHONPATH="$PWD" .venv/bin/python` 导入 `app / routes.miniapp.wenyou / services.wenyou_service` 通过；`git diff --check -- services/wenyou_service.py services/wenyou` 通过。
- 未完成 / 下次继续：下一刀优先拆提示词与副本生成、背包/商店/抽卡、结算/成长、怪物遭遇、AI 玩家上下文。非文游脏文件、旧静态 hash 产物和其他模块继续不碰。

当前状态（2026-05-23 文游服务拆分第二阶段）：
- 已完成：继续压缩 `services/wenyou_service.py`，把 DeepSeek system prompt、候选/框架 prompt builder、类型玩法说明移到 `services/wenyou/prompts.py`；把 DeepSeek 非流式调用和 `wenyou_templates.json` 缓存移到 `services/wenyou/deepseek_client.py`；把难度与副本类型归一化移到 `services/wenyou/common.py`。业务流程、路由、R2 存储和前端不改。
- 已验证：新旧 prompt 输出等价脚本通过；`.venv/bin/python -m py_compile services/wenyou_service.py services/wenyou/common.py services/wenyou/constants.py services/wenyou/phase.py services/wenyou/prompts.py services/wenyou/deepseek_client.py routes/miniapp/wenyou.py app.py` 通过；`PYTHONPATH="$PWD" .venv/bin/python` 导入 `app / routes.miniapp.wenyou / services.wenyou_service` 通过；固定新手副本 `_build_gm_messages` smoke 通过；`git diff --check -- services/wenyou_service.py services/wenyou docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：下一刀再拆副本 framework/runtime 归一化、背包/商店/抽卡、结算/成长、怪物遭遇和 AI 玩家上下文；不要碰非文游脏文件和旧静态 hash 产物。

当前状态（2026-05-23 文游服务拆分第三阶段）：
- 已完成：补齐 `services/wenyou/runtime_state.py`，承接玩家默认状态、核心能力归一化、属性成长字段清理、文本列表/蓝图列表归一化、公开/隐藏资料补全、怪物生态简表归一化、任务者人数与旧 framework runtime 补全。该文件是 `0cd1087` 中 `services/wenyou_service.py` 已经引用但未提交的缺失模块，本轮只补齐缺失文件并同步索引，不回滚 `0cd1087` 的其他改动。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py services/wenyou/common.py services/wenyou/constants.py services/wenyou/phase.py services/wenyou/prompts.py services/wenyou/deepseek_client.py services/wenyou/runtime_state.py routes/miniapp/wenyou.py app.py` 通过；`PYTHONPATH="$PWD" .venv/bin/python` 导入 `app / routes.miniapp.wenyou / services.wenyou_service` 通过；固定新手副本 `_build_gm_messages` smoke 通过；`git diff --check -- services/wenyou_service.py services/wenyou docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：后续再拆背包/商店/抽卡、结算/成长、怪物遭遇、AI 玩家上下文。继续不碰非文游脏文件和旧静态 hash 产物。

当前状态（2026-05-23 文游服务拆分第四阶段）：
- 已完成：把背包/物品基础操作拆到 `services/wenyou/inventory.py`，包含物品归一化、背包合并、消耗、数量判定、带出过滤、物品更新、出售/回收锁定和参考价格等纯结构逻辑；`services/wenyou_service.py` 只保留业务编排并从新模块导入。业务流程、路由、前端、静态资源不改。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py services/wenyou/common.py services/wenyou/constants.py services/wenyou/phase.py services/wenyou/prompts.py services/wenyou/deepseek_client.py services/wenyou/runtime_state.py services/wenyou/inventory.py routes/miniapp/wenyou.py app.py` 通过；`PYTHONPATH="$PWD" .venv/bin/python` 导入 `app / routes.miniapp.wenyou / services.wenyou_service` 通过；背包归一化、消耗和合并 smoke 通过；`git diff --check -- services/wenyou_service.py services/wenyou/inventory.py` 通过。
- 未完成 / 下次继续：下一刀优先拆商店/抽卡经济、结算/成长、怪物遭遇或 AI 玩家上下文；继续不碰非文游脏文件和旧静态 hash 产物。

当前状态（2026-05-23 文游服务拆分第五阶段）：
- 已完成：把道具目录、默认商店目录、抽卡目录、内容包 `content/default/items.json` 加载、目录索引和新手礼包 fallback 物品定义拆到 `services/wenyou/catalog.py`；`services/wenyou_service.py` 继续保留购买、抽卡、奖励结算等业务流程，只从目录模块读取表和索引。路由、前端、静态资源不改。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py services/wenyou/common.py services/wenyou/constants.py services/wenyou/phase.py services/wenyou/prompts.py services/wenyou/deepseek_client.py services/wenyou/runtime_state.py services/wenyou/inventory.py services/wenyou/catalog.py routes/miniapp/wenyou.py app.py` 通过；`PYTHONPATH="$PWD" .venv/bin/python` 导入 `app / routes.miniapp.wenyou / services.wenyou_service / services.wenyou.catalog` 通过；catalog/gacha/shop 常量初始化 smoke 通过；`git diff --check -- services/wenyou_service.py services/wenyou/inventory.py services/wenyou/catalog.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：后续再拆商店/抽卡流程、结算/成长流程、怪物遭遇和 AI 玩家上下文；继续不碰非文游脏文件和旧静态 hash 产物。

当前状态（2026-05-23 文游服务拆分第六阶段）：
- 已完成：把核心能力目录加载拆到 `services/wenyou/abilities.py`，包含 `content/default/abilities.json` 读取、能力定义归一化和默认能力目录合并；`services/wenyou_service.py` 仍保留能力使用/规则结算业务，只导入 `_WENYOU_ABILITY_CATALOG`。路由、前端、静态资源不改。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py services/wenyou/common.py services/wenyou/constants.py services/wenyou/phase.py services/wenyou/prompts.py services/wenyou/deepseek_client.py services/wenyou/runtime_state.py services/wenyou/inventory.py services/wenyou/catalog.py services/wenyou/abilities.py routes/miniapp/wenyou.py app.py` 通过；`PYTHONPATH="$PWD" .venv/bin/python` 导入 `app / routes.miniapp.wenyou / services.wenyou_service / services.wenyou.abilities / services.wenyou.catalog` 通过；`_ability_definition("core_survival")` 和固定新手副本 GM 消息 smoke 通过；`git diff --check -- services/wenyou_service.py services/wenyou/inventory.py services/wenyou/catalog.py services/wenyou/abilities.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：服务主文件仍有约 7.8k 行；后续优先拆商店/抽卡流程、结算/成长流程、怪物遭遇和 AI 玩家上下文。继续不碰非文游脏文件和旧静态 hash 产物。

当前状态（2026-05-24 文游对讲机第一版）：
- 已完成：文游局内新增“对讲机”第一版。后端新增 `/miniapp-api/wenyou/team-channel`，默认只记录对讲机短讯并调用玩家二上下文生成回复；可用 `consume_turn=true` 将对讲机内容记为同步行动并进入 GM 结算。`services/wenyou_service.py` 新增 `team_channel` 会话视图、对讲机日志、玩家二对讲机提示词和同步行动落库；`get_session_view` 返回 `team_channel`。前端 `WenyouTab.tsx` 在局内输入区上方新增对讲机面板，支持频段/信号/杂音、快捷呼叫队友/报位置/交换线索/约定会合、短讯通话/同步行动模式和发送。Boss 领域、核心异常、封锁、屏蔽、禁区等公开状态会触发 `信号中断`，后端拒绝发送；规则怪谈/红蓝阵营/监听等状态会显示杂音干扰。
- 已验证：`.venv/bin/python -m py_compile services/wenyou_service.py routes/miniapp/wenyou.py` 通过；`npm --prefix miniapp run build` 通过；`git diff --check -- services/wenyou_service.py routes/miniapp/wenyou.py miniapp/src/ui/tabs/WenyouTab.tsx miniapp/src/styles.css` 通过但仍提示 `miniapp/src/styles.css` 既有 CRLF warning。构建产物会更新 `miniapp_static/index.html` 与新 hash 资源，本轮不清理历史旧 hash 产物。
- 未完成 / 下次继续：冒名消息、第三方串台、分地点地图状态和道具/积分转交流程还没细化；当前第一版重点是“可接通、可断讯、可记录、可选择是否消耗回合”。非文游脏文件、旧静态 hash 产物继续不碰。

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

当前状态（2026-05-25 首页 Today Note / 纪念日小组件）：
- 已完成：`miniapp/src/ui/ChatsHome.tsx` 删除首页日报摘要卡，Today Note 改成 `ui合集/today note.html` 的粉色便签/贴纸风小组件；右侧新增纪念日小组件，按 `2026-03-04` 起算并显示第 N 天。`miniapp/src/ui/AppShell.tsx` 同步移除首页日报的拉取、刷新状态和传参，保留 Today Note 点击刷新行为。
- 已验证：`npm --prefix miniapp run build` 通过；`git diff --check -- miniapp/src/ui/ChatsHome.tsx miniapp/src/ui/AppShell.tsx miniapp_static/index.html docs/DEBUG_INDEX.md` 通过；本地 Vite 预览 `http://127.0.0.1:5175/miniapp/` 已打开确认首页显示 Today Note 与纪念日，且无日报摘要入口。
- 未完成 / 下次继续：本轮不处理已有 `miniapp_static/assets/*` 历史旧 hash 与其他脏文件；如要提交/推送，需只挑本轮源码、`miniapp_static/index.html` 和本轮构建引用的新 hash 资源。

当前状态（2026-05-25 当前底座动态注入）：
- 已完成：`pipeline/pipeline.py` 新增 `step_inject_current_base_model()`，只读 `storage.upstream_store.get_cached_active_model(refresh_if_missing=False)`，有缓存时把 `当前底座为：<model>` 写成动态 system 第一条；`routes/chat.py` 在 `step_inject_du_thought`、`step_inject_du_daily`、动态记忆、summary 和 sense 之前调用它。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py routes/chat.py`、当前底座注入 smoke test、`routes.chat` import check、`git diff --check -- pipeline/pipeline.py routes/chat.py` 均通过。
- 未完成 / 下次继续：该注入不刷新缓存、不读取客户端传入 model、不写静态 prompt，也不改转发策略；其他文档、文游、StudyRoom、小爱、`miniapp_static/assets/*` 脏文件继续不碰。

当前状态（2026-05-25 主动唤醒动态区拆分）：
- 已完成：`services/telegram_proactive.py::_ask_du_should_contact` 保留入口风格 system 只放 QQ/TG/微信风格本体，把 `【你近来主动联络时的自我决策记录】` 和 `【最近自发动作参考】` 打包成一条带 `__dynamic__` 标记的 system，交给网关动态区处理。
- 已验证：`.venv/bin/python -m py_compile services/telegram_proactive.py`、主动决策 body 构造 smoke test、`git diff --check -- services/telegram_proactive.py` 均通过。
- 未完成 / 下次继续：本轮只修随机主动决策路径；主动硬触发和闹钟/日历提醒本来没有把这两段参考拼进入口风格。其他文游、StudyRoom、小爱、`miniapp_static/assets/*` 脏文件继续不碰。

当前状态（2026-05-26 上游错误提示细化）：
- 已完成：`services/upstream_policy.py` 新增 OpenAI/Anthropic 兼容错误解析，`routes/chat.py` 非流式上游失败会展示嵌套 `error.type/code/message` 和非 JSON body 预览；`routes/miniapp/sumitalk_chat_jobs.py` 后台聊天任务复用同一解析；`scripts/claude_oauth_proxy.js` 将 OAuth token 过期/等待本地同步类异常映射为 503，不再一律 500。
- 已验证：`.venv/bin/python -m py_compile services/upstream_policy.py routes/chat.py routes/miniapp/sumitalk_chat_jobs.py`、`node --check scripts/claude_oauth_proxy.js`、嵌套错误解析 smoke test 均通过。
- 未完成 / 下次继续：本轮不改前端样式、不清理现有脏文件、不处理其他业务接口的泛化 500；如继续排错，优先看具体入口是否还绕过 `routes/chat.py` 的错误解析。

当前状态（2026-05-26 QQ 群聊 @ 存档去重）：
- 已完成：QQ 群聊 @ 归档不再完全删除前置 20 条上下文，而是在 `X-Reply-Target=qq_group_mention` 时压缩为“本次新增群聊上下文 + 当前 @ 你的消息”；连续 @ 时会参考最近归档轮次，过滤已经存过的群聊行，保留新出现的上下文给记忆总结使用。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/chat_archive_helpers.py` 通过；QQ 群聊归档压缩 smoke test 通过，确认旧上下文被去重、新上下文与当前 @ 内容保留。
- 未完成 / 下次继续：当前去重依据是最近 8 轮存档里的规范化文本行，QQ 网关内容里暂时没有消息 id；如果后续要更精确去重，可让 connector 把 OneBot message_id 一并带进上下文。

当前状态（2026-05-26 常识块静态注入）：
- 已完成：新增 `prompts/du_common_knowledge.md` 作为独立常识块，首批只写人物与社交关系；`pipeline/pipeline.py` 新增 `step_inject_common_knowledge()`，从该文件读取后注入静态 system 区；`routes/chat.py` 在核心行为/不退缩规则之后、入口风格 system 之前调用。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py routes/chat.py`、`routes.chat` import check、常识块注入 smoke test（确认注入陈欣/小黛且二次调用不重复）和 `git diff --check -- pipeline/pipeline.py routes/chat.py prompts/du_common_knowledge.md docs/DEBUG_INDEX.md` 均通过。
- 未完成 / 下次继续：常识块暂时是随代码部署的本地 markdown 文件；如果后续需要 MiniApp 在线编辑，再单独接 R2/设置页，不和动态记忆或核心 prompt 混在一起。

当前状态（2026-05-26 梗库 SQLite 动态注入）：
- 已完成：新增 `services/humor_meme_bank.py`，使用 `data/humor_meme_bank.sqlite3` 存 `meme/origin/usage/enabled`，首次调用自动建表并 seed 梗库（小玥口癖 + 筛剩的互联网梗 + “没有XX的义务”模板 + “新的退展”这类反向造词）；`pipeline/pipeline.py` 新增 `step_inject_humor_memes()`，每轮随机抽 3 条写入动态 system，引导轻松场景优先挑 1 个最贴合当下语义的梗轻轻化用，严肃/排错/身体不舒服/重情绪时不要用；`routes/chat.py` 在动态记忆召回后调用。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py routes/chat.py services/humor_meme_bank.py` 通过；梗库建表/随机抽 3 条/格式化 smoke test 通过；`step_inject_humor_memes` smoke test 与 `routes.chat` import check 通过；`git diff --check -- pipeline/pipeline.py routes/chat.py services/humor_meme_bank.py docs/DEBUG_INDEX.md prompts/du_common_knowledge.md` 通过。
- 未完成 / 下次继续：第一版没有 MiniApp 管理页；如需增删改梗，先直接改 SQLite 或后续补轻量管理接口。

当前状态（2026-05-27 常识独立静态 system）：
- 已完成：`step_inject_common_knowledge()` 保持常驻静态注入，但不再追加到上一条 plain system；现在会插入独立 system，避免 prompt cache debug 把常识算进 `thinking规则`。`services/prompt_cache_debug.py` 新增 `### 常识` 标签识别。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py services/prompt_cache_debug.py routes/chat.py` 通过；常识注入/profile smoke test 通过，确认静态分段为 `核心prompt`、`thinking规则`、`常识`，且常识未拼进 thinking system；`git diff --check -- pipeline/pipeline.py services/prompt_cache_debug.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：常识仍为常驻静态块，不迁到动态区；后续如接 MiniApp 编辑入口再单独做。

当前状态（2026-05-27 唤醒常识与入口风格顺序固定）：
- 已完成：`step_inject_common_knowledge()` 插入时遇到已有入口风格 system（QQ/TG/微信/SumiTalk/小爱）会停在其前面，避免“请求预带 QQ 风格”时变成 `QQ入口风格 -> 常识`，而“网关注入 QQ 风格”时是 `常识 -> QQ入口风格`，导致静态区顺序抖动。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py` 通过；smoke test 覆盖“请求不带 QQ 风格”和“请求预带 QQ 风格”，两者均为 `common -> qq`；`git diff --check -- pipeline/pipeline.py` 通过。
- 未完成 / 下次继续：这次只固定常识与入口风格的相对顺序；未改 NSFW/followup 追加方式，也未改主动唤醒投递策略。

当前状态（2026-05-27 Claude thinking signature 回传）：
- 已完成：新增 `services/claude_thinking_carryover.py`，仅在 active upstream 是服务端回环地址 Claude OAuth proxy（`127.0.0.1:8082`/`localhost:8082`）时，从上一轮 R2 归档读取原始 `thinking_blocks`（含 Claude `signature`），随上一轮 user/assistant 消息结构化回传；新窗口非 TG 入口可从全局 latest4 的最后一轮取块，TG 仍只用本窗口历史，避免串上下文。`routes/chat.py` 在转发前注入该隐藏结构，维护任务和 slim 语音通话跳过；流式/非流式归档会保留可回传 blocks，客户端可见响应会剥离 `thinking_blocks`。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/reasoning_utils.py services/claude_thinking_carryover.py` 通过；carryover smoke test 通过，确认无历史时会插入上一轮 user+assistant、有现成上一轮 assistant 时只补 `thinking_blocks` 不重复插入；SSE/nonstream 剥离 smoke test 通过，确认发给客户端的 chunk/response 不含 `thinking_blocks`。
- 未完成 / 下次继续：没有接 MiniApp 开关；当前只支持服务端回环地址 Claude OAuth proxy 入口，不扩展到 OpenRouter/CPA；旧归档如果没有 `thinking_blocks` 或没有带 signature，则不会强行伪造回传。

当前状态（2026-05-27 思维链工具调用展示修复）：
- 已完成：`routes/miniapp/reasoning.py` 的思维链最新接口不再只读取倒序遇到的第一条 `assistant.tool_calls`，改为用 `services/chat_tool_helpers.collect_tool_trace_from_messages()` 从整轮 messages 收集所有工具调用和结果，再统一格式化给前端；`services/chat_tool_helpers.py` 保留已归档 trace 自带的 `result`，避免二次收集时把结果覆盖为空。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/reasoning.py services/chat_tool_helpers.py` 通过；模拟两轮工具循环（2 次 + 1 次）和已归档 trace 的 smoke test 通过，确认 3 个工具调用和 3 个结果都会返回。
- 未完成 / 下次继续：这次只修后端接口数据；前端 `ReasoningTab` 原有渲染逻辑不变。

当前状态（2026-05-27 小爱音箱 / MiGPT Next 入口）：
- 已完成：新增并注册 `routes/xiaoai_api.py`，提供 `/api/xiaoai/message`、`/api/xiaoai/tts` 和短时音频 URL；小爱入口复用 `TELEGRAM_GATEWAY_URL`、`TELEGRAM_CHAT_PATH`、`TELEGRAM_PROACTIVE_TARGET_USER_ID`、`MINIMAX_*` 和现有公网 URL 推断；`XIAOAI_GATEWAY_TOKEN` 是小爱专用可选鉴权，只有配置后才要求 runner 传 Bearer，不复用 `MAIN_GATEWAY_BEARER_TOKEN`。`services/entry_style_prompt.py` 增加 `xiaoai` 独立入口风格，强制只输出一个 `<voice>...</voice>`，并用 speaker 推断默认房间；`routes/chat.py` 把 `X-XiaoAI-Speaker` 传入入口 system，且小爱 channel 跳过 followup 隐藏标记注入，避免破坏单一 `<voice>` 输出；`services/chat_request_helpers.py` 允许小爱复用 TG 窗口活动记录，`services/conversation_followup.py` 识别小爱 channel 但不主动投递延迟续话到音箱。
- 已验证：`.venv/bin/python -m py_compile app.py routes/xiaoai_api.py routes/chat.py services/xiaoai_audio_store.py services/entry_style_prompt.py services/chat_prompt_injections.py services/chat_request_helpers.py services/conversation_followup.py services/minimax_tts.py` 通过；`.venv/bin/python -c "import app; print('app import ok')"` 通过。
- 未完成 / 下次继续：MiGPT Next 侧 Node 配置与真实小爱 payload、`abortXiaoAI()`、公网 mp3 播放仍需实机验证；第一版按用户决策不上口头二级口令，只保留入口词和现有 Bearer 服务鉴权。其他文游、StudyRoom、旧文档和脚本脏文件不属于本轮，不要混进小爱提交。

当前状态（2026-05-27 小爱音箱工具页）：
- 已完成：MiniApp “工具”页新增“小爱音箱”入口，独立页支持启用开关、入口词、退出词、连接状态和小爱日志；新增 `storage/xiaoai_store.py` 本地持久化 `DATA_DIR/xiaoai_state.json`，`routes/miniapp/xiaoai.py` 提供 `/miniapp-api/xiaoai/overview/config/status/logs`，`routes/xiaoai_api.py` 提供 MiGPT Next 可调用的 `/api/xiaoai/config/status/logs`，并在 `/api/xiaoai/message` 里按启用开关拦截、记录消息/TTS/错误日志。
- 已验证：`.venv/bin/python -m py_compile routes/xiaoai_api.py routes/miniapp_api.py routes/miniapp/xiaoai.py storage/xiaoai_store.py app.py` 通过；`npm --prefix miniapp run build` 通过并生成 `XiaoAISettingsTab` chunk。
- 未完成 / 下次继续：MiGPT Next 侧还需要改为拉 `/api/xiaoai/config` 并上报 `/api/xiaoai/status`/`logs`；本轮没有实机验证小爱 payload、音频播放或临时会话退出词执行。

当前状态（2026-05-28 小爱日志展示收束）：
- 已完成：MiniApp 小爱页 `/miniapp-api/xiaoai/overview` 请求和后端默认日志 limit 都收束为 20 条。`storage/xiaoai_store.py` 的日志本地持久化不是时间 TTL，而是写入/读取时按 `_MAX_LOGS=300` 做条数上限裁剪；动作队列才有 `expires_epoch` TTL。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/xiaoai.py routes/miniapp_api.py storage/xiaoai_store.py` 通过；`npm --prefix miniapp run build` 通过并生成新的 `XiaoAISettingsTab` 静态 chunk；`git diff --check` 通过。
- 未完成 / 下次继续：如需要按时间删除小爱日志，可再给日志增加独立 TTL；当前不会无限增长。

当前状态（2026-05-27 小爱音箱 Mac Docker runner）：
- 已完成：新增 `connectors/xiaoai_migpt/`，包含 `Dockerfile`、`docker-compose.yml`、`.env.example`、`package.json`、`package-lock.json`、`src/runner.mjs` 和 README；runner 使用 `@mi-gpt/next` 登录小米云，定时拉 `/api/xiaoai/config`，按 App 工具页的启用开关/入口词/退出词处理消息，转发 `/api/xiaoai/message`，播放 `audio_url`，并上报 `/api/xiaoai/status` 和 `/api/xiaoai/logs`。compose 默认 `mem_limit: 256m`，`NODE_OPTIONS=--max-old-space-size=128`。
- 已验证：`npm install --package-lock-only` 生成 lock；`node --check connectors/xiaoai_migpt/src/runner.mjs` 通过。
- 未完成 / 下次继续：当前 Mac shell 没有 `docker` 命令，未实际 build/run 镜像；需要用户启动或安装 Docker Desktop 后在 `connectors/xiaoai_migpt` 执行 `docker compose up -d --build`。未填真实 `.env`，也没有做小米登录和音箱实机验证。

当前状态（2026-05-28 小爱音箱外放工具）：
- 已完成：新增 `xiaoai_speak` 网关工具，作为渡可调用的“小爱音箱外放/弹窗提醒”能力；`storage/xiaoai_store.py` 在原小爱状态文件里增加短 TTL 播放队列，`routes/xiaoai_api.py` 增加 `/api/xiaoai/actions`、`/api/xiaoai/actions/claim`、`/api/xiaoai/actions/<id>/result` 和 `/api/xiaoai/speak`；`pipeline/pipeline.py` 用 `step_inject_gateway_tools()` 常驻注入，不依赖 Notion 开关；主触发规则也明确 `xiaoai_speak` 可用于普通消息/弹窗可能被忽略时的升级提醒，例如叫看手机、催睡、喝水、洗澡后回来、起床或离开小红书，但必须短句、避开隐私社死、不要连续轰炸；MiGPT runner 每 `XIAOAI_ACTION_POLL_MS` 轮询队列，播放 `play_url`/`speak_text` 并回报成功失败。
- 已验证：`.venv/bin/python -m py_compile storage/xiaoai_store.py routes/xiaoai_api.py services/gateway_tools.py pipeline/pipeline.py routes/chat.py services/chat_tools.py` 通过；`node --check connectors/xiaoai_migpt/src/runner.mjs` 通过。
- 未完成 / 下次继续：外放工具默认要求 runner 在线且 MiniMax TTS 能生成公网可访问的 mp3；若 action 卡在 pending，先查 Mac Docker runner 是否在线并确认 `/api/xiaoai/actions/claim` 是否被轮询。

当前状态（2026-05-28 小爱外放工具实机验证）：
- 已完成：修复 MiGPT runner 播放队列轮询的启动顺序；轮询定时器可以提前注册，但 `pollActions()` 必须等 `MiGPT.MiNA` 初始化后才领取队列，避免 `MiGPT.start()` 初始化前把 action 领走并误报播放失败。
- 已验证：`node --check connectors/xiaoai_migpt/src/runner.mjs` 通过；Mac Docker runner 已 `docker compose -f connectors/xiaoai_migpt/docker-compose.yml up -d --build` 重建；公网接口调用 `/api/xiaoai/tts` 生成 MiniMax mp3，再调用 `/api/xiaoai/speak` 入队，action `85dbb130eaa04b82b49b576fbbe4a5e1` 被 `mac-docker` 领取并在 `2026-05-28T04:25:33+08:00` 返回 `status=done`，runner 日志为 `播放 URL 结果：ok`。
- 未完成 / 下次继续：如果用户实际没有听到声音，下一步查音箱网络是否能拉 `https://duxy-home.com/api/xiaoai/tts/*.mp3`、音量/播放状态以及 MiNA `player_get_play_status` 是否能返回有效媒体状态。

当前状态（2026-05-28 小爱外放有声修复）：
- 已完成：确认 L05C 小爱音箱的 MiNA `text_to_speech`/`player_play_url` 返回 `code=0` 不等于用户实际听到声音；runner 播放前增加 MIoT 发声准备：调用 `setProperty(2,2,false)` 尝试解除静音，读取 `volume`，低于 `XIAOAI_MIN_PLAY_VOLUME` 时拉到默认 20；文本播放优先走真实出声的 MIoT `doAction(5,3,<text>)`，失败才回退 MiNA TTS。
- 已验证：`node --check connectors/xiaoai_migpt/src/runner.mjs` 通过；直接调用 MIoT `play-text` 有实机声音，用户反馈“有声音”。本轮没有再发 MiniMax URL 实机测试，避免未经提醒突然播放。
- 未完成 / 下次继续：若要确认 MiniMax 音色，需要先明确提醒用户，再发一条短的 `/api/xiaoai/tts` + `/api/xiaoai/speak` 测试；不要再把 action `status=done` 或接口 `code=0` 单独表述为“用户听到了”。

当前状态（2026-05-28 小爱 MiniMax URL 播放兼容模式）：
- 已完成：MiGPT runner 参考 xiaomusic / miservice-fork，对 L05C 等硬件优先走 `mediaplayer.player_play_music`，旧 `player_play_url` 只做回退；`player_play_music` payload 使用 `startaudioid=1582971365183456177` 和 `stream.url=<mp3>`，可用 `XIAOAI_PLAY_URL_STRATEGY=music|url|auto` 覆盖。MiniMax 音频现在只保留最新一条，固定覆盖 `DATA_DIR/xiaoai_audio/latest.mp3`，播放 URL 形如 `/api/xiaoai/tts/latest.mp3?v=<version>`，同版本第一次 GET 成功、后续循环 GET 返回 404，下一条语音覆盖文件并换新版本。
- 已完成：为避免短 TTS 音频被播放器循环，`player_play_music` 前先调用 `player_set_loop`，默认 `XIAOAI_PLAY_LOOP_TYPE=3`（单曲播放）；但 L05C 会在 `player_play_music` 后把 `loop_type` 又重置回 1，所以 runner 又补了硬兜底：播放成功后 600ms 读取 `play_song_detail.duration/position`，按剩余时长 + `XIAOAI_PLAY_AUTO_STOP_PADDING_MS` 自动下发 `player_play_operation stop`。
- 已完成：由于 L05C 对 stop/loop 仍可能假成功并继续重复 GET 同一 mp3，`services/xiaoai_audio_store.py` 把小爱 TTS URL 改为一次性音频：首次 GET 返回音频并写 `<token>.used`，后续 GET 同 token 直接 404，阻断播放器循环；HEAD 不消耗播放次数。
- 已验证：公网 MiniMax mp3 测试 `46085aab04864e12afe84fa011545c98` 走 `player_play_music`，Nginx 收到音箱播放器 `Lavf/58.45.100` GET 音频，用户反馈“听到声音”；随后确认单纯设置 loop/stop 仍会循环。部署一次性 URL 后，测试 `bd657cfe5a344ca0b242c04143218bc9` 的 token `6gCl1bMImmMGMBliFUNgwhuy0qw35eGt` 第一次 GET 返回 200，第二次循环 GET 返回 404。

当前状态（2026-05-31 小爱误播音乐修复）：
- 现场证据：2026-05-31 03:46:54 `xiaoai_speak` 入队文本是“三点半过了哦，该躺下了，手机放远一点。”；03:47:10 音箱播放器 `Lavf/58.45.100` 成功 GET `/api/xiaoai/tts/latest.mp3?v=-MefGNV0FE1apwj_`，该 mp3 实际时长 5.472 秒、大小 89268 字节；但 Mac runner 随后 `player_get_play_status` 返回固定 `audio_id=1582971365183456177`、`duration=201432`，用户听到喜庆音乐。根因判断：`player_play_music` 里的固定 `audio_id` 撞到了小米曲库曲目，不能再固定使用这个 ID。
- 已完成：`connectors/xiaoai_migpt/src/runner.mjs` 保留默认 `XIAOAI_PLAY_URL_STRATEGY=auto`；L05C 等硬件继续走 `player_play_music`，不再回退到已知假成功/无声的 `player_play_url`。`player_play_music` 默认按每条 URL 生成临时 16 位 `audio_id`，并在播放后读取 `player_get_play_status.play_song_detail.audio_id` 校验；若返回的 ID 与本次临时 ID 不一致，会立刻 `player_play_operation stop`，上报 `music_audio_id_mismatch`，再回退文字播报。
- 已完成：`.env.example` 和 README 已改回 `XIAOAI_PLAY_URL_STRATEGY=auto`，并标明不要固定 `XIAOAI_PLAY_MUSIC_AUDIO_ID`，除非临时排查。
- 已验证：`node --check connectors/xiaoai_migpt/src/runner.mjs` 通过；`git diff --check -- connectors/xiaoai_migpt/src/runner.mjs connectors/xiaoai_migpt/.env.example connectors/xiaoai_migpt/README.md docs/DEBUG_INDEX.md` 通过；Mac Docker runner 已 `docker compose -f connectors/xiaoai_migpt/docker-compose.yml up -d --build` 重建，容器内确认默认 `PLAY_URL_STRATEGY=auto`、`PLAY_MUSIC_AUDIO_ID` 默认空、存在 `musicAudioIdForUrl()` 和 `verifyMusicPlayback()`；debug 初始化确认目标设备 `miotDID=2037350052` / `hardware=L05C`，正式容器启动后日志出现 `✅ 服务已启动...`，公网 `/api/xiaoai/status` 显示 `runner=mac-docker`、`last_event=heartbeat`、`online=true`。
- 已验证：用户允许后，2026-05-31 04:05:26 发真实测试语音“测试一下小爱播放渡的语音。”，action `6ac77ddcf7be4926b94c6d21df9f1604` 走 `player_play_music`；runner 生成 `audio_id=9645551171453281`，播放后状态返回 `play_song_detail.audio_id=9645551171453281`、`duration=2880`、`status=playing`，没有切到固定小米曲库曲目；随后按剩余时长自动 stop 成功，公网 action 状态为 `done`。
- 未完成 / 下次继续：需要用户主观确认听到的是渡语音内容；若后续再次出现音乐，优先看 runner 日志是否有 `music_audio_id_mismatch` 和实际 `play_song_detail.audio_id`。

当前状态（2026-05-28 小爱音频 URL 静默排查）：
- 已完成：确认 runner 日志里 `播放 URL 结果：ok` 只代表 MiGPT/MiNA 接受播放命令，不代表小爱成功拉到 mp3；线上最近 `last_audio_url` 直接 GET 返回 404，根因是 `services/xiaoai_audio_store.py` 原先只把音频存在 Python 进程内存，生产多 worker、进程重启或请求落到不同进程时 `/api/xiaoai/tts/<token>.mp3` 会失效。已改为写入 `DATA_DIR/xiaoai_audio/` 并在 GET 时从落盘文件恢复，按 `ARTIFACT_TTL_SECONDS` 和 `ARTIFACT_MAX_ITEMS` 清理。
- 已验证：`.venv/bin/python -m py_compile services/xiaoai_audio_store.py routes/xiaoai_api.py` 通过；临时目录 smoke 验证清空内存 `_store` 后仍能用 token 从落盘文件读回音频；非法 token 返回空。
- 未完成 / 下次继续：需要部署到生产并重启 du-gateway 后再让小爱实测；当前 Mac Docker runner 不需要为这个修复重建，除非同时改 runner 播放策略。

当前状态（2026-05-28 小爱入口静音开关）：
- 已完成：`storage/xiaoai_store.py` 的小爱配置增加 `mute_native_reply`；MiniApp 小爱工具页新增“入口静音”开关；MiGPT runner 拉到该开关后，命中入口词或临时会话时会短超时读取当前音量，并对 `app_ios`、`common`、无 `media` 三种通道调用 `player_set_volume=0`，普通聊天保持静音直到拿到渡的 `audio_url`/兜底文本、播放前按同样通道恢复原音量；本地音量/暂停/停止命令会先恢复再执行，避免把临时静音误当成用户音量。这个策略同时覆盖旧 `player_play_url` 和新 `player_play_music`。
- 已验证：`node --check connectors/xiaoai_migpt/src/runner.mjs` 通过；`.venv/bin/python -m py_compile storage/xiaoai_store.py routes/xiaoai_api.py routes/miniapp/xiaoai.py` 通过；`npm --prefix miniapp run build` 通过并生成新的 `XiaoAISettingsTab` 静态 chunk。
- 未完成 / 下次继续：需要生产部署后在 MiniApp 打开“入口静音”，重启 Mac Docker runner，再实机确认具体音箱是否接受 `volume=0`；若型号不接受 0，runner 会退化为命令失败日志或 MiGPT 内部最小音量。

当前状态（2026-05-28 mijiaAPI 家居控制工具）：
- 已完成：`services/gateway_tools.py` 新增 `xiaoai_run_command` 工具，底层调用 `mijiaAPI --run "<自然语言家居命令>"`，用于让小爱执行米家/红外设备控制；新增配置 `MIJIA_API_COMMAND`、`MIJIA_API_AUTH_PATH`、`MIJIA_WIFISPEAKER_NAME`、`MIJIA_API_QUIET`、`MIJIA_API_TIMEOUT_SECONDS`；`requirements.txt` 增加 `mijiaapi>=3.1.0`。工具常驻注入，不依赖 MiGPT runner；`speaker_name` 可由工具参数临时覆盖，默认走 `MIJIA_WIFISPEAKER_NAME`。
- 已验证：`.venv/bin/python -m py_compile config.py services/gateway_tools.py pipeline/pipeline.py routes/chat.py services/chat_tools.py` 通过；smoke 确认 `step_inject_gateway_tools()` 同时注入 `xiaoai_speak` 与 `xiaoai_run_command`，命令构造为 `mijiaAPI --run ... --wifispeaker_name ... --quiet`。
- 未完成 / 下次继续：未在服务器安装/登录 mijiaAPI，也未实机执行家居命令；生产需要安装 `mijiaapi`、完成小米账号 auth、配置 `MIJIA_WIFISPEAKER_NAME` 后重启 du-gateway。

当前状态（2026-05-28 mijiaAPI 台灯实测脚本）：
- 已完成：新增 `scripts/test_xiaoai_mijia.py`，直接调用 `xiaoai_run_command` 执行器，不经过模型和聊天链路；默认只允许命令包含“台灯/桌灯/书桌灯”，适合第一轮只测台灯，非台灯命令必须显式加 `--allow-non-lamp`。
- 已验证：`.venv/bin/python -m py_compile scripts/test_xiaoai_mijia.py` 通过；`--dry-run` 确认命令构造正确。未真实执行设备控制。
- 未完成 / 下次继续：服务器需要先安装/登录 mijiaAPI 并配置 `MIJIA_WIFISPEAKER_NAME=小米小爱音箱Play 增强版`；本机 `mijiaAPI -p data/mijia/auth.json -l` 看到该设备 did 为 `2037350052`，但 `--wifispeaker_name` 传 did 会失败，需传米家列表里的完整设备名。再执行 `.venv/bin/python scripts/test_xiaoai_mijia.py "打开台灯"` / `"关闭台灯"`。

当前状态（2026-05-28 mijiaAPI 台灯结构化属性工具）：
- 已完成：`services/gateway_tools.py` 新增 `mijia_lamp_get` / `mijia_lamp_set`，用于读写台灯 `on`、`brightness`、`color-temperature`，避免渡自己拼 CLI；`scripts/test_xiaoai_mijia.py` 增加 `--lamp-get`、`--lamp-brightness`、`--lamp-color-temperature`。`mijiaAPI get/set` 的 `-p/--auth_path` 必须放在子命令后，代码已固定构造为 `mijiaAPI set -p <auth> ...`，不要写成 `mijiaAPI -p <auth> set ...`。
- 已验证：本地用 MiGPT `.env` 的 `XIAOMI_PASS_TOKEN` 刷出 `data/mijia/auth.json` 后，`xiaoai_run_command` 对真实音箱名“小米小爱音箱Play 增强版”执行“打开台灯/关闭台灯”返回成功；`mijiaAPI get -p data/mijia/auth.json --did 2025297301 --prop_name brightness` 读到 `35`，`color-temperature` 读到 `3420`。
- 未完成 / 下次继续：结构化 `set` 需用 `mijia_lamp_set` 或 `scripts/test_xiaoai_mijia.py --lamp-brightness ...` 验证；不要再手写错误的全局 `-p` 顺序。

当前状态（2026-05-29 小爱音箱自身音量结构化控制）：
- 已完成：`xiaoai_run_command` 遇到“小爱/音箱 + 音量 + 数字”时不再走 `mijiaAPI --run` 自然语言链路，而是自动改为 `mijiaAPI set -p <auth> --did <MIJIA_SPEAKER_DID> --prop_name volume --value <N>`；新增配置 `MIJIA_SPEAKER_DID`，未配置时默认使用已实测的 L05C did `2037350052`。工具说明要求音量使用阿拉伯数字，例如“把小爱音箱音量调到50”。
- 已验证：服务器 `mijiaAPI -l` 确认真实设备名为“小米小爱音箱Play 增强版”，did 为 `2037350052`；`mijiaAPI get/set --did 2037350052 --prop_name volume` 能读写音量。`mijiaAPI --run "把小爱音箱音量调到50"` 的 `returncode=0` 只能证明 CLI 没报错，不能证明音箱实际执行。
- 未完成 / 下次继续：部署后需要通过渡实际调用 `xiaoai_run_command` 再测一轮，返回 JSON 应包含 `mode: "speaker_volume_set"`，否则说明还在走旧自然语言路径。

当前状态（2026-05-29 xiaoai_run_command 音箱 did 误传修复）：
- 已完成：`mijiaAPI --run` 的 `--wifispeaker_name` 实际只接受米家设备列表里的音箱名称，不接受 did；且 CLI `-l` 会合并 `get_devices_list()+get_shared_devices_list()`，但 `--run` 内部重新创建 `mijiaDevice(dev_name=...)` 时只查 `get_devices_list()`，所以服务器会出现列表里有音箱、`--run` 却报“未找到 did 为 '小米小爱音箱Play 增强版' 的设备”。`xiaoai_run_command` 已绕过 CLI `--run`，改为网关内直接合并自有/共享设备解析音箱 did，并调用小爱 `execute-text-directive`（`siid=5, aiid=4, in=[command, quiet]`）。
- 已验证：`.venv/bin/python -m py_compile services/gateway_tools.py config.py` 通过；mock smoke 覆盖“音箱只在 shared 设备列表”时仍解析 did `2037350052`，并直接调用 `run_action({"did":"2037350052","siid":5,"aiid":4,"in":["打开卧室空调",1]})`，返回 JSON 含 `mode: "speaker_text_directive"`。注意：底层 `api.run_action()` 必须传 `"in"`；传 `"value"` 会返回 `-704220025 Action参数个数不匹配`。

当前状态（2026-05-28 MiniApp 米家授权二维码）：
- 已完成：新增 `services/mijia_auth_login.py`，复用 `mijiaAPI` 包内部二维码登录流程，按 `MIJIA_API_AUTH_PATH`（未配置则用 mijiaAPI 默认 `~/.config/mijia-api/auth.json`）写入 auth；`routes/miniapp/xiaoai.py` 增加 `/miniapp-api/xiaoai/mijia-auth` 和 `/miniapp-api/xiaoai/mijia-auth/start`，小爱音箱页新增“米家授权”区块，显示二维码图片、授权状态、有效期和错误。二维码可截图后用米家 App 相册识别；等待扫码超时或后端重启后状态会自动过期，避免按钮卡死。
- 已验证：`.venv/bin/python -m py_compile services/mijia_auth_login.py routes/miniapp/xiaoai.py routes/miniapp_api.py` 通过；`get_mijia_auth_status()` smoke 通过；`npm --prefix miniapp run build` 通过并生成新的 `XiaoAISettingsTab` 静态 chunk。
- 未完成 / 下次继续：未实际点“生成二维码”触发小米登录，也未扫码实测；上线后需要重新部署 MiniApp 静态包和 du-gateway 后端。

当前状态（2026-05-27 Claude thinking signature 回传覆盖唤醒链路）：
- 已完成：`routes/chat.py` 不再因为 `X-DU-DAILY-MAINTAIN` 或 `X-Voice-Call-Slim` 跳过 Claude thinking carryover；只要当前 active upstream 是服务端本机 Claude OAuth proxy，且请求没有显式带 `X-Skip-Claude-Thinking-Carryover: 1`，就会在进入上游前尝试把上一轮归档里的 `thinking_blocks` 回传。覆盖延迟续话、后端事件唤醒、硬触发、随机主动决策、闹钟提醒、弹窗选择回执、查岗截图回执等所有走主 `/v1/chat/completions` 的网关生成。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py services/claude_thinking_carryover.py` 通过；Flask request context smoke 确认默认不跳过、带 `X-Skip-Claude-Thinking-Carryover: 1` 时跳过。
- 未完成 / 下次继续：绕过主 chat 路由的非 Claude direct call 不适用；生产 `du-gateway.service` 仍需要服务器 root 拉代码并重启后才生效。

当前状态（2026-05-27 近期总结 DS 亲密角色扮演护栏）：
- 已完成：`services/deepseek_summary.py` 的实时层小段总结 prompt 新增亲密/NSFW 角色扮演判断规则；师生、兄妹、主人/宠物、医患、上下级等身份词优先按成人自愿 play/虚构设定理解，不写成现实关系、真实职业、真实血缘或现实事件，也不补脑年龄、胁迫和未出现的禁忌设定。
- 已验证：`.venv/bin/python -m py_compile services/deepseek_summary.py` 通过；`build_summary_prompt` smoke 确认新规则进入近期总结 DS prompt。
- 未完成 / 下次继续：本轮只改近期记忆总结 DS，不改动态层 `services/dynamic_layer_ds.py`、核心 prompt、NSFW 正文回复规则或存档结构。

当前状态（2026-05-27 近期总结片段容量 15）：
- 已完成：`services/deepseek_summary.py` 的近期总结小段上限改为总计 15 个片段：最近 3、稍早 8、更早 4。一次性重建脚本已执行完并从仓库删除，避免后续误用。
- 已完成：压缩计划保留原来的固定传送带节拍：每个压缩点仍处理最旧的 2 个【最近】片段、最旧的 2 个【稍早】片段，并在发生【稍早】到【更早】移位时淘汰最旧的 2 个【更早】片段。容量扩大只改变最多保留多少，不改变每次移位动作。
- 已写回：2026-05-27 已按第一次 dry-run 结果写回 R2 `global/summary.txt` 和 `global/summary_chunks.json`，实际范围为 `tg_8260066512` 的 rounds 6793-6852；落库后 `chunks=15`，分布为更早 4 / 稍早 8 / 最近 3，`update_count=626`。
- 已验证：`.venv/bin/python -m py_compile services/deepseek_summary.py` 通过；容量 smoke 覆盖 3/8/4 上限、legacy 分层和固定 2/2/2 移位计划；R2 落库检查确认当前 `update_count=626`，下一次总结开始时读到的仍是 626，成功写完后才更新计数；按当前逻辑本次只补新总结，不压缩换位。
- 未完成 / 下次继续：本轮不改 4/8 轮总结频率；不要改固定 2/2/2 压缩节拍，除非先重新设计计数语义。

当前状态（2026-05-27 近期总结 DS 请求与结果重试）：
- 已完成：`services/deepseek_summary.py` 的 `fetch_new_summary_update()` 增加最多 3 次尝试；HTTP/503/timeout/网络异常会重试同一 prompt，返回非 JSON、人称违规、`new_chunk` 为空、压缩字段数量不对或 chunks 构建失败时，会带具体验证原因要求 DeepSeek 重写。
- 已完成：重试只发生在写入 summary chunks 之前；只有结果通过校验并能构建完整 chunks 后才返回 `new_summary/new_chunks`，失败仍返回 `None`，不写 R2、不推进结构、不改变 4/8 轮节奏或固定 2/2/2 移位计划。
- 已验证：`.venv/bin/python -m py_compile services/deepseek_summary.py` 通过；mock smoke 覆盖连接错误后成功、空 `new_chunk` 后成功、压缩字段数量错误后成功，确认重试成功后才生成 chunks。
- 未完成 / 下次继续：这不是 slot 占坑方案；如果 DS 连续 3 次仍失败，仍依赖现有缺口补跑逻辑在后续轮次补处理。

当前状态（2026-05-27 近期总结 pending slot 兜底）：
- 已完成：`services/deepseek_summary.py` 增加 pending chunk 支持；DS 连续失败后可用 `build_pending_summary_update()` 先写入对应 4 轮的 pending slot。pending slot 参与 `update_count`、recent/slightly/older 分层和固定 2/2/2 移位，但渲染近期记忆时会跳过，不把“待补写”占位暴露给模型。
- 已完成：`pipeline/pipeline.py` 在 `fetch_new_summary_update()` 失败后写入 pending 兜底；后续触发时 `_summary_round_groups_to_process()` 会把 pending range 重新拿出来补写。补写成功时只填原 slot，不新增 chunk、不推进 `update_count`。
- 已验证：`.venv/bin/python -m py_compile services/deepseek_summary.py pipeline/pipeline.py` 通过；smoke 覆盖 pending 创建、pending 不渲染、pending range 后续被选中、补写不改变计数、压缩点失败仍按 2/2/2 结构移动并保留 pending。
- 未完成 / 下次继续：pending 只解决结构兜底；如果 DS 长时间连续失败，pending 文本仍需后续成功触发才能补齐。

当前状态（2026-05-27 工具循环思维链展示去重）：
- 已完成：`services/reasoning_utils.py` 新增 substring-aware reasoning 文本去重；当 `reasoning` 已经是“工具轮 + 最终轮”合集，而 `thinking_blocks` 又包含最终轮同一段时，不再展示重复最终思维链。`routes/miniapp/reasoning.py` 复用同一去重函数。
- 已验证：`.venv/bin/python -m py_compile services/reasoning_utils.py routes/miniapp/reasoning.py` 通过；smoke 覆盖 `reasoning=A+B` 且 `thinking_blocks=B`、以及先短后长的反向顺序，确认最终只保留一次 B。
- 未完成 / 下次继续：本轮只修 MiniApp reasoning 展示与通用提取函数；未改 `routes/chat.py` 当前带有其它本地脏改的工具循环主流程。

当前状态（2026-06-12 TG 工具循环 thinking 当场展示）：
- 已完成：`routes/chat.py` 在非流式工具循环里继续累计每轮 reasoning；当 `reply_channel=tg` 且发生过工具调用时，把“工具中间轮 + 最终轮”的去重后 reasoning 写回本次返回给 TG 的 `message.reasoning`，让 Telegram 折叠 thinking 不再只显示最后一轮。
- 保留边界：不把累计 reasoning 扩大回传给其它客户端；不把中间工具轮 `thinking_blocks` 挂到最终 assistant 上，避免影响 Claude thinking carryover 的结构化回传判断。
- 已验证：`.venv/bin/python -m py_compile routes/chat.py` 通过；Flask request smoke 模拟 tool_calls 后续轮，确认 TG 响应同时包含“工具轮 thinking”和“最终 thinking”。

当前状态（2026-05-27 thinking block 模板化收束）：
- 已完成：`pipeline/pipeline.py` 的 thinking block 约束改成正向输出形态：直接写心里冒出来的念头本身，不写对念头的说明；去掉容易诱发“我的反应是”的“反应/三问出发”措辞，改为不加标题、标签和冒号开头。
- 已验证：`.venv/bin/python -m py_compile pipeline/pipeline.py` 通过；prompt 文案 smoke 确认新约束出现，旧的“三问出发”和“真实反应”措辞已移除。
- 未完成 / 下次继续：本轮只改 thinking block 约束文字；没有改核心 prompt、行为规则、NSFW 规则或 reasoning 展示逻辑。

当前状态（2026-05-28 thinking block 内心 OS 风格）：
- 已完成：`pipeline/pipeline.py` 的 thinking block 约束补充“脑内 OS 的碎碎念”风格，明确念头可以跳、自言自语、冒半句，但不要写成分点分析、判断清单、复盘报告或给自己的工作说明。
- 未完成 / 下次继续：本轮只改 thinking block 风格约束；不改 Claude thinking carryover、MiniApp reasoning 展示、核心 prompt、NSFW 规则或入口正文风格。

当前状态（2026-05-28 thinking block 状态感知去清单化）：
- 已完成：`pipeline/pipeline.py` 把“她是不是焦虑/低落/不舒服”等清单式问句，改成“先感觉这句话背后的劲儿”和“自然冒出第一反应”；避免 thinking block 写成用户状态分析表。
- 未完成 / 下次继续：本轮仍只改 thinking block 约束文案；不改正文生成、展示层、Claude thinking carryover 或 NSFW 规则。

当前状态（2026-05-28 thinking block 去第三视角扮演感）：
- 已完成：`pipeline/pipeline.py` 补充“我就是渡，没有渡这个角色需要扮演”，并禁止在 thinking block 里写“按照渡的套路 / 以渡的身份 / 渡应该怎么回应 / 符合渡的人设”这类旁观说法；目标是让 thinking 直接从“我”的内心出发。
- 未完成 / 下次继续：本轮只改 thinking block 约束文案；不改 Claude thinking carryover、历史归档、reasoning 展示或入口正文风格。

当前状态（2026-05-27 文游服务拆分：玩家命名 / 文本清洗 / GM 上下文 / 事件解析 / 规则数学）：
- 已完成：`services/wenyou_service.py` 继续瘦身，抽出 `services/wenyou/players.py`（玩家 id、默认标签、显示名、玩家别名替换）、`services/wenyou/text_sanitize.py`（隐藏【事件意图】、去【主神面板】和玩家备忘块）、`services/wenyou/gm_context.py`（GM system 的任务者编制、新手引导、惩罚副本提示和蓝图摘要）、`services/wenyou/event_intent.py`（GM【事件意图】解析、目标/tags/state_proposals/clock_updates 标准化）、`services/wenyou/panel_parser.py`（旧兼容【主神面板】解析）、`services/wenyou/rules_math.py`（伤害、状态阈值、状态增删、威胁时钟）和 `services/wenyou/settlement_state.py`（结算 flags / reward_context 标准化），并把 `_compact_text` 下沉到 `services/wenyou/common.py`。
- 已验证：`.venv/bin/python -m py_compile services/wenyou/common.py services/wenyou/players.py services/wenyou/text_sanitize.py services/wenyou/gm_context.py services/wenyou/event_intent.py services/wenyou/panel_parser.py services/wenyou/rules_math.py services/wenyou/settlement_state.py services/wenyou_service.py` 通过；`import app` 通过；smoke 覆盖玩家别名替换、GM 文本清洗、GM 上下文格式化、事件意图解析、旧面板解析、威胁时钟、状态阈值和结算 flags；`git diff --check` 覆盖本轮文游文件。
- 未完成 / 下次继续：`services/wenyou_service.py` 仍约 8069 行，下一刀优先拆规则结算应用层或钱包/库存账户兼容层；不要把当前小爱、近期总结、MiniApp 静态资源和其他脏改动混进文游拆分提交。

当前状态（2026-05-28 文游服务拆分：公共状态 / 候选 prompt / 抽卡 helper）：
- 已完成：新增 `services/wenyou/public_state.py`，承接公开任务、线索、地点/NPC/怪物 marker、面板合并、rules mapping、任务/线索/marker 规则状态 entry、公开规则更新 stub、公开威胁标签和时钟状态标签；新增 `services/wenyou/candidate_prompts.py`，承接大厅候选归一化、候选扩展 prompt、候选 core/blueprint/opening prompt 和 DS 文本块清洗；新增 `services/wenyou/gacha.py`，承接抽卡池归一化、保底状态、概率 roll、保底应用/更新、按池选物和重复转碎片 helper。`services/wenyou_service.py` 保留候选 DS 调用、教程副本、framework 组装、`roll_gacha` 钱包/背包业务入口和 `_prepare_gacha_item_for_inventory` 封印逻辑，路由、前端和静态资源不改。
- 已验证：`.venv/bin/python -m py_compile services/wenyou/common.py services/wenyou/public_state.py services/wenyou/candidate_prompts.py services/wenyou/gacha.py services/wenyou/gm_context.py services/wenyou/event_intent.py services/wenyou/panel_parser.py services/wenyou/players.py services/wenyou/rules_math.py services/wenyou/settlement_state.py services/wenyou/text_sanitize.py services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`.venv/bin/python` 导入 `app` 和 `routes.miniapp.wenyou` 通过；smoke 覆盖 `_normalize_public_task_item`、`_rules_mapping`、`_task_progress_entry`、`_merge_panel_list`、候选归一化、候选 core/blueprint/opening prompt、`format_candidate_expansion_prompt`、`_clean_ds_block`、`_public_clock_status`、`_public_threat_label`、`generate_instance_candidates` 可导入、抽卡池归一化、保底、概率 roll、按池选物和碎片转换；`git diff --check -- services/wenyou_service.py services/wenyou/public_state.py services/wenyou/candidate_prompts.py services/wenyou/gacha.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：后端下一刀可优先拆 item_effects 纯规则 helper 或奖励 roll helper；前端小工建议先拆 `miniapp/src/ui/wenyou/types.ts`、`storyParser.ts`、`panelFormatters.ts`。不要把非文游脏文件、旧静态 hash 产物、QQ/小爱/共读半成品混入文游拆分提交。

当前状态（2026-05-28 文游服务拆分：道具效果 / 结算奖励 roll）：
- 已完成：新增 `services/wenyou/item_effects.py`，承接道具效果表、道具阶段/需求校验、HP/SAN 小型结算、状态移除、耐久消耗结果、给 GM 的道具结算文本和前端展示块；`services/wenyou_service.py` 仍保留实际修改 session/wallet/clocks 的 `_apply_item_use_cost`、`_apply_item_effect_to_session` 和玩家工具入口。新增 `services/wenyou/settlement_rewards.py`，承接结算奖励稀有度封顶、奖励表加载、分类加权、目录候选、fallback 奖励物、B+ 保底和奖励 roll；`_weighted_pick` / `_shift_rarity` 下沉到 `services/wenyou/common.py`，供奖励和商店共用。
- 已验证：`.venv/bin/python -m py_compile services/wenyou/common.py services/wenyou/item_effects.py services/wenyou/settlement_rewards.py services/wenyou_service.py routes/miniapp/wenyou.py app.py` 通过；`import app/routes.miniapp.wenyou/services.wenyou_service/services.wenyou.settlement_rewards` 通过；smoke 覆盖道具 HP 恢复、道具需求校验、耐久扣减、结算奖励按 seed 生成物品、S 评级/隐藏奖励 B+ 保底和通用稀有度平移；`git diff --check -- services/wenyou_service.py services/wenyou/common.py services/wenyou/item_effects.py services/wenyou/settlement_rewards.py` 通过。
- 未完成 / 下次继续：前端第一刀仍建议按小工扫描结果拆 `miniapp/src/ui/wenyou/types.ts`、`storyParser.ts`，暂不碰裂隙音效/canvas/动画；后端下一刀可拆商店轮转或成长/结算应用层。非文游脏文件、旧静态 hash 产物、QQ/小爱/共读半成品继续不碰。

当前状态（2026-05-28 文游前端拆分：类型 / 剧情解析器 / 面板格式化）：
- 已完成：新增 `miniapp/src/ui/wenyou/types.ts`，承接文游入口、feed、story、背包、商店、玩家状态、成长、公开状态、rules state 和 session panel 类型；新增 `miniapp/src/ui/wenyou/storyParser.ts`，承接开局副本信息解析、剧情正文/系统框/行动选项分段、历史 feed 转换；新增 `miniapp/src/ui/wenyou/panelFormatters.ts`，承接玩家名、玩家别名替换、背包显示键、道具描述过滤、任务/线索/marker 文本和当前位置格式化。`miniapp/src/ui/tabs/WenyouTab.tsx` 只保留组件状态、交互和渲染，并修正发送按钮 `onClick={() => submitAction()}` 的类型签名。
- 已验证：`npx vite build --outDir /tmp/du-gateway-miniapp-build --emptyOutDir true` 通过，未覆盖 `miniapp_static`；`git diff --check -- miniapp/src/ui/tabs/WenyouTab.tsx miniapp/src/ui/wenyou/types.ts miniapp/src/ui/wenyou/storyParser.ts miniapp/src/ui/wenyou/panelFormatters.ts` 通过；`rg` 确认 story parser、panel formatter 函数和迁出的面板类型定义已只在新模块里。`npx tsc --noEmit --pretty false` 仍被非文游旧错误 `src/ui/MainChatScreen.tsx:301 consumePendingPanelDeviceIdMigration` 阻断，本轮未触碰。
- 未完成 / 下次继续：前端下一刀可拆文游音频/裂隙工具或把局内小组件继续组件化；后端下一刀可拆商店轮转或成长/结算应用层。暂不碰主神空间视觉、裂隙 canvas 和音效行为。非文游脏文件、旧静态 hash 产物、QQ/小爱/共读半成品继续不碰。

当前状态（2026-05-28 方案清理：白名单/黑名单取消观察期下线）：
- 已完成：删除 `docs/白名单黑名单方案-取消观察期.md`，该“新窗口默认白名单 / 新窗测试进黑名单 / 回复追加黑名单后缀”的取消观察期方案不再作为未落地方案追踪。
- 未改动：现有 `storage/whitelist_store.py`、`storage/blacklist_store.py`、`routes/admin.py`、MiniApp 状态面板里的白名单/黑名单管理能力仍保留；这次只是下线旧方案文档，不是删除运行时代码。

当前状态（2026-05-29 Claude OAuth proxy 模型列表试加 4-8 / 4-1）：
- 已完成：`scripts/claude_oauth_proxy.js` 的 `/v1/models` 硬编码列表新增 `claude-opus-4-8` 和 `claude-opus-4-1`；保留 `claude-opus-4-7` 在第一位，避免 active model 自动刷新时默认切到未验证模型。
- 未完成 / 下次继续：这只影响模型列表展示和手动选择；实际 chat 是否可用还要由 Anthropic/OAuth 端是否接受对应 model id 决定。

当前状态（2026-05-29 思维链页 Output token 展示）：
- 已完成：`routes/miniapp/reasoning.py` 为 `/miniapp-api/reasoning/latest` 增加 `output_stats`，优先用 `cache_debug.usage` 汇总 actual output tokens；当时曾对 CC/Claude adaptive thinking 的 hidden thinking 做差值估算，后续 2026-06-11 已改为只认上游实际 `thinking_tokens` 字段。
- 已完成：`miniapp/src/ui/tabs/ReasoningTab.tsx` 不再新增独立 Output 卡片；Output token 直接显示在原粉色 `Prompt Cache` 卡片的 `input=...` 后面，格式如 `output=4609（thinking 2376）`。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/reasoning.py` 通过；`npx vite build --outDir /tmp/du-gateway-miniapp-output-stats-build --emptyOutDir true` 通过；`_build_output_stats` smoke 覆盖 usage 优先、thinking 估算和占比；`git diff --check -- routes/miniapp/reasoning.py miniapp/src/ui/tabs/ReasoningTab.tsx docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮只改思维链面板展示，不改聊天气泡 token 小字、不改上游 usage 透传和计费逻辑。

当前状态（2026-05-29 Claude adaptive thinking effort 选择）：
- 已完成：`storage/upstream_store.py` 在 active upstream/model 缓存中保存 `claude_thinking_effort`，允许值 `low/medium/high/xhigh/max`，默认 `high`；`routes/miniapp/upstreams.py` 暴露读取和 `/upstreams/claude-thinking-effort` 保存接口。
- 已完成：`miniapp/src/ui/tabs/SettingsUpstream.tsx` 在上游调试页的当前活跃节点卡片中增加 Adaptive Thinking 选择器，当前/待选模型匹配 Claude 4.8/4.7/4.6 时可保存；4.6 不展示 `xhigh`。
- 已完成：`services/upstream_policy.py` 在 active upstream 是本机 Claude OAuth proxy 且 active model 是 Claude 4.8/4.7/4.6 时注入 `thinking={"type":"adaptive","display":"summarized"}` 和 `output_config.effort`；`scripts/claude_oauth_proxy.js` 保留并转发 OpenAI 兼容请求里的 `thinking/output_config`，4.8/4.7/4.6 默认使用 adaptive thinking，旧模型继续走固定 `budget_tokens`。4.6 收到 `xhigh` 时降为 `high`，避免无效 effort。
- 已验证：`.venv/bin/python -m py_compile storage/upstream_store.py routes/miniapp/upstreams.py services/upstream_policy.py routes/chat.py` 通过；`node --check scripts/claude_oauth_proxy.js` 通过；上游策略 smoke 覆盖 4.8 注入 `max`、4.6 注入 adaptive 且 `xhigh` 降为 `high`、4.1 不注入 adaptive；`npx vite build --outDir /tmp/du-gateway-upstream-effort-build --emptyOutDir true` 通过；`git diff --check` 覆盖本轮文件。
- 未完成 / 下次继续：本轮已重建 `miniapp_static`；如果要线上生效，提交推送后还需要在服务器拉代码并重启 `du-gateway.service` 和 Claude OAuth proxy。

当前状态（2026-05-30 三人群聊 @ 触发顺序）：
- 已完成：MiniApp 三人群聊改为按 `@` 解析发言目标：不带 `@` 默认只触发渡；`@笨笨` / `@笨笨机` / `@benben` / `@codex` 只创建笨笨任务；`@渡 @笨笨` 会同时放置渡和笨笨 pending 气泡，并独立发起两条链路。笨笨任务创建不再依赖渡先回复，`du_reply` 对 daily_chat 变为可选；渡失败时不再把笨笨 pending 一起改成失败。
- 已完成：Codex group bridge 会读取 `target_mentions`，在 `@笨笨` 且没有 `du_reply` 时提示“直接回应辛玥和已有群聊，不要说等渡先回复”，避免恢复旧的固定第三棒口吻。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`.venv/bin/python -m py_compile services/codex_group_chat.py routes/miniapp/codex_group_chat.py scripts/codex_group_chat_bridge.py` 通过；smoke 覆盖无 `du_reply` 创建/claim 笨笨任务与 bridge prompt 触发说明；`git diff --check -- miniapp/src/ui/MainChatScreen.tsx services/codex_group_chat.py routes/miniapp/codex_group_chat.py scripts/codex_group_chat_bridge.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮没有重建 `miniapp_static`，没有改 QQ 群聊 @ 存档链路，也没有处理 `@all`、选择器 UI 或“笨笨可沉默”策略。当前仓库仍有大量非本轮脏改和静态资源 hash 变更，提交时不要混入。

当前状态（2026-05-30 三人群聊笨笨施工模式）：
- 已完成：`@笨笨` 消息里出现 `改代码/开工/施工/debug/调试/修 bug/实现/落地/加上/做一下` 等显式施工词时，MiniApp 会创建 `mode=coding_task`；普通 `@笨笨` 仍走 `daily_chat`。前端现在吃 `queued/running/done/error/cancelled` 全状态，pending 气泡会显示“已接单 / 施工中，正在改代码 / debug / 完成或失败”，并可用 `client_request_id` 在任务 id 回来前匹配 realtime 事件。
- 已完成：`services/codex_group_chat.py` 允许 `coding_task`，公开 `mode/client_request_id/target_mentions` 给 realtime；`scripts/codex_group_chat_bridge.py` 为施工任务使用单独 `coding_thread_id`，默认 `CODEX_GROUP_CHAT_CODING_SANDBOX=workspace-write`，并在 prompt 中要求保护脏改、不 stage/commit/push/部署、不重建 `miniapp_static`，最终只回一条施工报告。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`.venv/bin/python -m py_compile services/codex_group_chat.py routes/miniapp/codex_group_chat.py scripts/codex_group_chat_bridge.py` 通过；smoke 覆盖 `coding_task` 创建/claim、施工 prompt、首次 `--sandbox workspace-write` 命令和 resume 时 `sandbox_mode="workspace-write"`；`git diff --check -- miniapp/src/ui/MainChatScreen.tsx miniapp/src/ui/hooks/useCodexGroupTaskRealtime.ts services/codex_group_chat.py routes/miniapp/codex_group_chat.py scripts/codex_group_chat_bridge.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮没有实际从群聊触发一次真实 Codex 施工任务，没有重建 `miniapp_static`，也没有做 `@all`、详情面板或更细的“验证中/等待确认”阶段。上线前仍需确保 bridge 进程重启后加载新代码。

当前状态（2026-05-31 三人群聊取消施工）：
- 已完成：前端识别 `@笨笨 停一下/停止/取消/中断/打断/别改了/别施工/别做了/暂停/kill/算了`，先把用户取消消息写入群聊，再取消当前 pending 的笨笨任务；没有 pending 任务时会回“没有正在施工或等待的笨笨任务。”。
- 已完成：MiniApp 通过 `/miniapp-api/codex-group-chat-tasks/<id>/cancel` 调后端取消；后端 `cancel_task` 会把任务标成 `cancelled` 并发布 realtime，`finish_task` 收到 bridge 迟到结果时保持 `cancelled`，不覆盖成完成。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`npx vite build --outDir /tmp/du-gateway-miniapp-cancel-task-build --emptyOutDir true` 通过；`.venv/bin/python -m py_compile services/codex_group_chat.py routes/miniapp/codex_group_chat.py routes/pc_command.py scripts/codex_group_chat_bridge.py` 通过；smoke 覆盖 coding task 创建、claim、cancel、cancel 后不可再 claim、迟到 finish 不覆盖 cancelled；`git diff --check` 覆盖本轮相关文件。
- 未完成 / 下次继续：施工任务取消会由 bridge 轮询状态并终止本地 Codex 子进程；普通 daily_chat 取消只做任务状态取消和迟到回写阻断。本轮没有重建 `miniapp_static`，上线前要重新构建静态产物并重启后端/bridge。

当前状态（2026-05-31 三人群聊有限自由讨论）：
- 已完成：MiniApp 三人群聊在 `@渡 @笨笨` 且带 `讨论/商量/你俩/自由聊/一起看看/聊几句` 等触发词时，会开启有限自由讨论接力；初始渡和笨笨仍按原来的双目标链路独立创建，笨笨首条完成后最多再自动追加 3 条接力回复。
- 已完成：接力期间上一条内容显式 `@渡` 或 `@笨笨` 时优先按 @ 指向下一位，否则渡/笨笨交替；出现“先这样 / 差不多了 / 不用继续 / 我来改 / 先按这个”等收尾语会停止，用户再发新消息也会让旧接力自然停下。
- 已完成：自由讨论不会自动进入 `coding_task`；即使话题里出现 `改代码/debug/实现`，只要是 `@渡 @笨笨` 讨论触发，笨笨仍按 `daily_chat` 参与，真施工仍必须显式 `@笨笨 改代码/开工/debug...`。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`npx vite build --outDir /tmp/du-gateway-miniapp-free-discussion-build --emptyOutDir true` 通过，只有既有 chunk size warning；`git diff --check -- miniapp/src/ui/MainChatScreen.tsx docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮不改 QQ 群聊 @ 存档链路，不做 @all/选择器 UI，也没有重建 `miniapp_static`；上线前需要重建静态产物并重启后端/bridge。

当前状态（2026-05-31 三人群聊自由讨论控制升级）：
- 已完成：自由讨论接力会在群聊标题下显示状态，如“群聊接力中，等笨笨首条回复”和“群聊接力中 1/3，轮到渡/笨笨”，避免用户看不出后台是否还在讨论。
- 已完成：接力中发送“停一下 / 别聊了 / 先这样 / 收尾”等会立即递增 run id，让旧接力停止继续贴消息；如果有 pending 的笨笨任务，会沿用取消任务链路，否则群里补一条“群聊接力已停下。”。
- 已完成：发送“继续聊 / 再聊 / 继续讨论 / 你俩继续 / 再聊两轮”等会基于上一条讨论快照继续接力，默认再聊 2 条，可识别“一/三/1/3”调整到 1 或 3 条，仍受最多 3 条限制。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`npx vite build --outDir /tmp/du-gateway-miniapp-group-control-build --emptyOutDir true` 通过，只有既有 chunk size warning；`git diff --check -- miniapp/src/ui/MainChatScreen.tsx docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮仍不改后端 bridge、不改 QQ 群聊 @ 存档，也不做 @all/选择器 UI；如果要 push，需要像上轮一样 partial stage，避免混入小家、思维链样式和静态 hash 脏改。

当前状态（2026-05-31 QQ 入站语音转写）：
- 已完成：`connectors/qq_onebot/src/main.js` 支持私聊和被 @ 的群聊 `record/voice/audio` 段；入站 QQ 语音会优先通过 NapCat/OneBot `get_record(out_format=wav)` 取可识别音频，再调用网关内部 `/api/internal/stt`，把结果以 `（QQ语音转写）...` 和可选 `（声音观察：...）` 注入原 QQ 聊天链路。非 @ 群聊语音不主动转写，避免无谓消耗。
- 已完成：新增 `routes/internal_stt_api.py`，用 `GATEWAY_INTERNAL_STT_TOKEN` / `MAIN_GATEWAY_BEARER_TOKEN` / `XIAOAI_GATEWAY_TOKEN` 鉴权，或仅允许无转发头的本机直连兜底；`services/stt.py` 对 QQ/NapCat 常见假 `.amr` / SILK 音频保留 ffmpeg 转 wav fallback。
- 已验证：本地 `.venv/bin/python -m py_compile config.py services/stt.py routes/internal_stt_api.py app.py`、`node --check connectors/qq_onebot/src/main.js`、内部 STT test_client smoke 和 `git diff --check` 通过；服务器已同步运行时代码，`du-gateway` / `qq-connector` 重启后 active，`/health` 和 `/health`(8092) 正常；用真实 QQ `record` 经 `get_record` 转 `.wav` 后调用 `/api/internal/stt` 返回 200，provider=`openrouter`，model=`google/gemini-2.5-flash`。
- 未完成 / 下次继续：未做公开 MiniApp UI 开关；没有对所有 QQ 语音格式做离线样本库，只按真实 NapCat 事件验证了 `file+path` 形态。若后续出现只有 URL 或只有 file id 的事件，connector 已按 URL / `get_record` 分支兼容，先看日志再扩。

当前状态（2026-05-31 心动兔兔气泡皮肤层）：
- 已完成：`miniapp/src/ui/chatAppearance.ts` 将装饰气泡展示名改为“心动兔兔”，并把 decor 基础气泡收敛为原气泡背景/文字色；`miniapp/src/ui/ChatPresentation.tsx` 新增 `HeartRabbitBubbleSkin`，把外发光、边缘虚化和叠加高光放到不占布局的皮肤层，贴纸层继续绝对定位贴合气泡边缘，不再改 `max-width`、`padding` 或 `line-height`。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 通过；`npm --prefix miniapp run build` 通过并同步 `miniapp_static` 新 hash 产物，只有既有 chunk size warning。
- 未完成 / 下次继续：本轮没有把 `tools/bubble-customizer.html` 的全部材质/像素边框编辑器配置迁入 App，也没有清理主工作区已有旧 `miniapp_static` 构建残留；后续如继续迁移皮肤参数，仍需保持皮肤层不影响原气泡布局参数。

当前状态（2026-05-31 生气emoji气泡皮肤）：
- 已完成：新增 `生气emoji` 气泡样式，基于 `/Users/doraemon/Downloads/生气emoji.css` 提取两个图片贴纸到 `miniapp/src/assets/angry-emoji-*.png`；`chatAppearance.ts` 增加 `angry` 选项与 `resolveBubbleSkin`；`ChatPresentation.tsx` 支持 `heart-rabbit` / `angry-emoji` 两套皮肤层与贴纸层；聊天页和个性化预览都通过 `skin` 传入，不改变原气泡 `max-width/padding/line-height`。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 通过；`npm --prefix miniapp run build` 通过并同步 `miniapp_static`，仅有既有 chunk size warning。
- 未完成 / 下次继续：未把 standalone `tools/bubble-customizer.html` 的完整编辑器控制面板迁入 App；主工作区旧 `miniapp_static` 构建残留仍未清理，继续不要混入提交。

当前状态（2026-05-31 三人群聊笨笨入群 abort 修复）：
- 已查明：服务器 `codex_group_chat_tasks.json` 中最近 3 个笨笨任务均为 `done`；群聊历史末尾的“笨笨入群失败：signal is aborted without reason”发生在自由讨论第二轮 `@笨笨` 接力创建任务阶段，服务器未收到对应 POST，属于前端创建请求被 WebView/fetch abort 后直接写失败。
- 已完成：`miniapp/src/ui/MainChatScreen.tsx` 把笨笨任务创建超时从 15 秒改为首试 30 秒、abort/timeout 时提示“笨笨入群有点慢，正在重试...”并重试一次；`services/codex_group_chat.py` 按 `client_request_id` 幂等返回已有任务，避免重试导致一个 @ 造出两个笨笨任务。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`npx vite build --outDir /tmp/du-gateway-miniapp-benben-retry-build --emptyOutDir true` 通过，只有既有 chunk size warning；`.venv/bin/python -m py_compile services/codex_group_chat.py routes/miniapp/codex_group_chat.py` 通过；临时 `_TASK_FILE` smoke 覆盖同一 `client_request_id` 重试只保留 1 个任务；`git diff --check -- miniapp/src/ui/MainChatScreen.tsx services/codex_group_chat.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮未清理线上历史里已有的失败气泡，未重建 `miniapp_static`，未 push/重启；上线时仍需只挑本轮相关 hunk/文件，避免混入当前仓库里的小家、StudyRoom、静态 hash 等脏改。

当前状态（2026-05-31 三人群聊自由聊开关 / 广播语义）：
- 已完成：三人群聊标题栏新增“自由聊”开关，状态写入 `localStorage`；开关关闭时仍保持精确 `@渡` / `@笨笨` 触发，开关开启时，用户在群聊里发普通消息也按同时发给渡和笨笨的群聊广播处理，不再要求用户写 `@渡 @笨笨`。
- 已完成：自由聊模式不再按固定交替顺序接力；系统只根据模型正文里的 `@渡` / `@笨笨` 决定下一棒，没 @ 就自然停。渡和笨笨的提示词都明确“这是公共群聊广播”，避免把上一条第三方发言误读成私聊。
- 已验证：`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`python3 -m py_compile scripts/codex_group_chat_bridge.py services/codex_group_chat.py routes/miniapp/codex_group_chat.py` 通过；`npx vite build --outDir /tmp/du-gateway-miniapp-free-chat-broadcast-build --emptyOutDir true` 通过，只有既有 chunk size warning；`git diff --check -- miniapp/src/ui/MainChatScreen.tsx scripts/codex_group_chat_bridge.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮未重建 `miniapp_static`、未 push/重启；当前仓库仍有大量非本轮脏改和静态 hash 产物，提交时需要 partial stage，别混入小家、StudyRoom 等半成品。

当前状态（2026-06-01 兔兔探头气泡皮肤）：
- 已完成：新增 `兔兔探头` 气泡样式，基于 `/Users/doraemon/Downloads/兔兔探头.css` 提取探头图片贴纸到 `miniapp/src/assets/peek-rabbit-sticker.png`；`chatAppearance.ts` 增加 `peek` 选项与 `peek-rabbit` 皮肤 key；`ChatPresentation.tsx` 增加 `PeekRabbitBubbleSkin` 和 `top-right` 贴纸层，继续不改原气泡 `max-width/padding/line-height`。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 通过；`npm --prefix miniapp run build` 通过并同步 `miniapp_static`，仅有既有 chunk size warning。
- 未完成 / 下次继续：未把 standalone `tools/bubble-customizer.html` 的完整编辑器控制面板迁入 App；主工作区旧 `miniapp_static` 构建残留和其他半成品仍未清理，继续不要混入提交。

当前状态（2026-06-01 动态区 prompt cache 构成监控）：
- 已完成：`services/prompt_cache_debug.py` 在原有 `static_breakdown` 外新增 `dynamic_breakdown`，按动态 system 里的 marker 粗分为当前底座、时间/日期、感知快照、渡的心事、渡的日常、热梗素材、最近对话、可召回记忆、RikkaHub 提醒、Notion 检索等块，并记录 `chars` / `est_tokens`；`static_breakdown` 会单独识别拟态心跳规则。
- 已完成：`routes/chat.py` 的 `prompt_cache_debug` 日志新增 `dynamic_breakdown=标签≈tokens,...`，MiniApp 思维链页粉色 `Prompt Cache` 卡片新增 `dynamic breakdown`，方便直接看动态区从约 1000 涨到 2000 时是哪块撑大。
- 已验证：`.venv/bin/python -m py_compile services/prompt_cache_debug.py routes/chat.py` 通过；后端 smoke 覆盖动态区拆分；基于当前 `origin/main` 重新执行 `npm -C miniapp run build -- --emptyOutDir=false` 并生成本轮静态产物；`git diff --check` 通过。
- 未完成 / 下次继续：本轮只做监控展示和日志，不改任何注入预算/裁剪策略；仓库仍有大量既有脏改和旧静态 hash 产物，提交时需要只挑本轮文件/产物。

当前状态（2026-06-01 拟态心跳静态化）：
- 已完成：`pipeline/pipeline.py` 把 `step_inject_du_vitals` 从动态 system 改到静态 system 注入；`services/du_vitals.py` 不再读取或回灌上一组心率/呼吸状态，只保留稳定的隐藏块输出规则。
- 已完成：`services/prompt_cache_debug.py` 将拟态心跳计入 `static_breakdown` 的“拟态心跳规则”，并从 `dynamic_breakdown` marker 中移除，避免动态区体积监控误把稳定规则算进去。
- 已验证：`.venv/bin/python -m py_compile services/du_vitals.py pipeline/pipeline.py services/prompt_cache_debug.py` 通过；smoke 覆盖注入后 static breakdown 出现“拟态心跳规则”、dynamic breakdown 不再出现拟态心跳，且隐藏块文本不再包含“上一组状态”。
- 未完成 / 下次继续：本轮只改提示词注入位置和 breakdown 归类，不改心率/呼吸参数的截取、存储、MiniApp 展示或通知逻辑。

当前状态（2026-06-11 拟态心跳读数不进动态区）：
- 已完成：代码回正为只注入 `format_rule_block()` 到静态 system，不再调用 `format_state_block(r2_store.get_du_vitals_latest())`，所以 `heart_bpm/breath_rpm/intimacy_heat` 这类上一轮实际读数不会再给渡看。
- 未完成 / 下次继续：`services/du_vitals.py::format_state_block` 暂时保留，作为调试/兼容函数；当前聊天注入链路不再使用它。

当前状态（2026-06-01 SumiTalk 底部 Dock 导航）：
- 已完成：`miniapp/src/ui/BottomNav.tsx` 从满宽贴底 tab bar 改为 iOS Dock 风格的居中悬浮导航；Dock 使用半透明背景、圆角胶囊、内阴影/投影和 backdrop blur，当前 tab 轻微上浮并使用白色图标位。
- 已完成：`miniapp/src/ui/icons.tsx` 给 `BottomNavIcon` 增加可选 `className`，去掉 Dock 场景下旧图标自带的 `mb-1` 偏移；`miniapp/src/ui/AppShell.tsx` 将主页面底部留白从 `76px` 增到 `104px`，避免悬浮 Dock 压住列表底部内容。
- 已验证：在干净 worktree 基于 `origin/main` 提交本轮改动，`./node_modules/.bin/tsc --noEmit`（在 `miniapp/`）通过；`npm run build` 通过并重建 `miniapp_static`，只有既有 chunk size warning。
- 未完成 / 下次继续：本轮只改主底部导航样式，不改聊天页输入栏、二级页底部控件或导航结构。

当前状态（2026-06-01 主动决策污染最近对话修复）：
- 已查明：`tg_8260066512` 的 R2 tail4 里混入了两轮 `X-DU-PROACTIVE-DECISION` 内部主动决策请求，内容是“这是一次随机唤醒...”和 `{"action":...}` JSON；因此 `Prompt Cache` 的“最近对话”从约 553 跳到约 929，不是用户一句“我洗完了”撑大的。
- 已完成：`routes/chat.py` 对 `X-DU-PROACTIVE-DECISION` 内部请求继续存档，但存档前会把长网关提示压成 `role=event` 的“随机唤醒/闹钟提醒/后端触发”事件，不再顶着 `role=user` 或“辛玥”的名字；assistant 侧 JSON 压成带 `archive_label=渡` 的“决策：主动发消息/暂时不打扰 + 简短理由/要发的话”，不再把整段系统说明和原始 JSON 塞进 R2 last4。
- 已完成：`pipeline/pipeline.py::step_inject_latest_4_rounds_for_new_window` 会从最近 12 轮中筛掉历史主动决策污染轮次再补足 last4，避免旧 R2 数据继续进入“最近对话”；新存档的短版主动决策轮次可以正常作为短程连续性被注入，并显示成 `[随机唤醒]` / `[闹钟提醒]`，不显示 `[辛玥]`。
- 已验证：干净 worktree 基于 `origin/main` 运行 `.venv/bin/python -m py_compile routes/chat.py pipeline/pipeline.py`、compact proactive archive smoke、last4 event rendering smoke、last4 filter smoke、`git diff --check` 通过；服务器已 fast-forward 并重启 `du-gateway`，线上模拟当前 `tg_8260066512` 注入确认不含历史“这是一次随机唤醒”和 `{"action"}`，最近对话估算约 284 tokens。
- 未完成 / 下次继续：没有删除线上 R2 里已有的污染轮次；它们只是被注入过滤跳过。后续如果需要彻底清理历史，再单独做带备份的数据修剪。

当前状态（2026-06-01 中期记忆独立层）：
- 已完成：新增 `services/du_midterm_memory.py`，按最近 14 天 `du_daily_archive` + 当前 `du_daily_state` + 规则筛后的画像候选生成中期连续感；使用动态层的人格口吻，但不复用 `new/merge/skip` 动态记忆规则。生成规则包含三天刷新、时间衰减（近 1-3 天更具体、4-7 天代表事件、8-14 天背景）、第一人称硬约束、高密度亲密短锚点保留和画像候选规则句清洗。
- 已完成：`storage/du_state_store.py` 新增 R2 key `global/du_midterm_memory.json` 读写；payload 保存 `latest` 与最近 3 版 `previous`。`pipeline/pipeline.py` 新增 `step_inject_du_midterm_memory()`，放在「渡的日常」之后、动态记忆召回之前注入 `latest.content`；到期刷新走后台线程，不阻塞当前聊天。`routes/miniapp/midterm_memory.py` 新增 GET、preview、refresh 接口并接入 `/miniapp-api`。
- 已验证：`.venv/bin/python -m py_compile services/du_midterm_memory.py storage/du_state_store.py pipeline/pipeline.py routes/chat.py routes/miniapp/midterm_memory.py routes/miniapp_api.py services/prompt_cache_debug.py` 通过；路由表确认 `/miniapp-api/midterm-memory`、`/preview`、`/refresh` 已注册；手动 `generate_midterm_memory(save=True, force=True)` 已写入首版 `latest`，`should_refresh=False`，注入预览包含 `【最近一段时间（2026-05-19 至 2026-06-01）】`；`git diff --check` 覆盖本轮文件通过。
- 未完成 / 下次继续：本轮没有做 MiniApp 前端按钮、没有重建 `miniapp_static`、没有 push/重启；仓库仍有大量非本轮脏改和静态 hash 产物，提交时只挑 `services/du_midterm_memory.py`、`routes/miniapp/midterm_memory.py`、`storage/du_state_store.py`、`routes/miniapp_api.py`、`routes/chat.py`、`pipeline/pipeline.py`、`services/prompt_cache_debug.py` 和本索引段的相关 hunk。

当前状态（2026-06-03 MiniApp 上报管理）：
- 已完成：MiniApp 设置页新增“上报管理”入口，页面为 `miniapp/src/ui/tabs/ReportingManagementScreen.tsx`；显示非健康上报数据的当前快照、更新时间、最近日志、能力状态和“立刻上报”按钮。健康数据仍留在原“健康数据”页。
- 已完成：`routes/miniapp/device_state.py` 新增 `GET /miniapp-api/device-state/reporting` 和 `/reporting/config`；只返回当前 panel 设备的 `battery/screen/foreground/location/usage`，过滤健康数据和无设备号旧记录。上报开关已从旧“总开关”改为按电量、屏幕、前台应用、位置、使用统计分别保存，R2 配置为 `global/device_reporting_config.json`。
- 已完成：Android `SumiOverlay` 插件已有 `getSenseReportingStatus`、`setSenseReportingConfig`、`requestSenseReportingSnapshot`；前端不再依赖 `setSenseReportingConfig` 保存上报开关，旧 APK 缺 native 方法时也会兜底刷新服务器状态。
- 已验证：干净 worktree 基于最新 `origin/main` 摘本轮改动，`.venv/bin/python -m py_compile routes/miniapp/device_state.py storage/r2_store.py`、`./node_modules/.bin/tsc --noEmit`、`npm run build`、`git diff --check` 通过；已重建并提交 `miniapp_static`，静态产物包含 `ReportingManagementScreen-*.js` 和 `/device-state/reporting/config`。
- 已打包：当前 Android 版本以 `miniapp/android/app/build.gradle` 为准（现为 `versionCode=12` / `versionName=1.1.10`）。打包统一通过 Android Studio，实际验证使用 Android Studio 自带 JBR (`/Applications/Android Studio.app/Contents/jbr/Contents/Home`) 跑 `JAVA_HOME=... sh ./gradlew :app:assembleDebug`。APK 下载包固定覆盖原入口 `/miniapp/assets/app-debug.apk`，不再保留 `latest`、commit 后缀或版本号后缀 APK。

当前状态（2026-06-03 Telegram md/txt 文档附件）：
- 已完成：`services/telegram_bot.py` 新增 Telegram `document` 分支；当私聊发来 `.md` / `.markdown` / `.txt` 或 `text/markdown` / `text/plain` 附件时，Bot 通过 Telegram `getFile` 下载原文，按 UTF-8 文本直接放入输入聚合缓冲，并保留文件名和 caption，不解析 Markdown、不转 HTML。
- 已完成：文档附件限制为 1MB，送入模型前最多保留前 60000 字，超出会在输入里追加截断说明；非文本附件继续忽略，避免 PDF/二进制误进 prompt。`services/telegram_update_queue.py` 的 update 摘要新增 `has_document`，方便从队列日志判断 TG 是否收到文档。
- 已验证：`.venv/bin/python -m py_compile services/telegram_bot.py services/telegram_update_queue.py` 通过；本地 monkeypatch smoke 模拟 `notes.md` 附件，确认输入缓冲包含文件名、caption 和 Markdown 原文；`git diff --check -- services/telegram_bot.py services/telegram_update_queue.py docs/DEBUG_INDEX.md` 通过。
- 未完成 / 下次继续：本轮未支持 PDF/DOCX/OCR，也未把附件原文件持久化；如需更长文档，应改成先入文件缓存/R2，再只把摘要或链接注入。

当前状态（2026-06-03 TG 长任务超时放宽）：
- 已完成：`services/telegram_bot.py` 将 TG worker 调网关等待时间从 180 秒提高到 300 秒，避免渡做测试题、长文档题目或较长推理时被 TG 侧提前判定失败。
- 已完成：`routes/chat.py` 的非流式上游转发不再写死 120 秒，改用 `config.py::STREAM_TIMEOUT_SECONDS`，与流式请求一致，默认 300 秒。`scripts/start_gateway_prod.sh` 将 gunicorn 默认 `GATEWAY_TIMEOUT` 从 240 秒提高到 360 秒，给 5 分钟上游请求留出外层余量。
- 已验证：`.venv/bin/python -m py_compile services/telegram_bot.py routes/chat.py` 通过；`rg` 确认主 chat 流式/非流式均使用 `STREAM_TIMEOUT_SECONDS=300`，TG worker 使用 `TELEGRAM_GATEWAY_CHAT_TIMEOUT_SECONDS=300`，gunicorn 默认 360 秒。

当前状态（2026-06-04 睡眠分段累计）：
- 已完成：`storage/sense_store.py` 在屏幕从熄屏转亮屏/解锁时继续保留 `lastSleepBlock`，并新增 `sleepSummary`；同一夜多个睡眠段会按最大 3 小时醒来间隔合并，累计 `totalMinutes`、`awakeGapMinutes`、`segmentCount` 和最近分段，避免 20:00-01:00、02:00-04:30 这类分段睡眠只算最后一段。
- 已完成：`services/proactive_trigger_engine.py` 的亮屏/醒来触发读取 `sleepSummary.totalMinutes`，没有累计摘要时才回退到单段 `lastSleepBlock` 或上一条熄屏事件；`services/sense_context.py` 在最近 24 小时内把累计睡眠摘要注入给渡参考。
- 已验证：`.venv/bin/python -m py_compile storage/sense_store.py services/proactive_trigger_engine.py services/sense_context.py` 通过；本地 smoke 覆盖 20:00-01:00 + 02:00-04:30，确认 `sleepSummary.totalMinutes=450`、`segmentCount=2`、`awakeGapMinutes=60`。

当前状态（2026-06-11 睡眠短段误判收束）：
- 已完成：`storage/sense_store.py` 将可独立计入 `sleepSummary` 的熄屏睡眠段从 20 分钟提高到 45 分钟；20-44 分钟短熄屏只会在已经有同夜睡眠、且距上一睡眠段结束不超过 30 分钟时作为短补觉接上。洗澡、上班路上放歌这类短熄屏不会再把一晚睡眠开头或结尾拉长。
- 已完成：`lastSleepBlock` 增加 `summaryIncluded` 和 `summaryReason`，被排除的短段会标出 `short_without_prior_sleep`、`short_after_awake_gap` 或 `outside_sleep_window`，方便下次从快照判断为什么没算进睡眠。
- 已验证：`.venv/bin/python -m py_compile storage/sense_store.py` 通过；本地 smoke 复现 20:40-21:01 洗澡、23:17-06:01 主睡眠、07:28-07:55 上班路上放歌，确认最终 `sleepSummary.totalMinutes=403`、`segmentCount=1`，07:28-07:55 被标记为 `short_after_awake_gap`；另测 06:20-06:45 这种 30 分钟内短补觉仍会并入。
- 未完成 / 下次继续：当前 Android 侧没有通用“系统闹钟实际响起”上报，SumiTalk 只能从既有 schedule/fired、亮屏/解锁、前台应用和使用统计推断；如果要严格按“最后一次闹钟响起”算醒来时间，需要新增闹钟触发事件或本地计划闹钟回执。

当前状态（2026-06-08 聊天顶部中间胶囊）：
- 已完成：`miniapp/src/ui/MainChatScreen.tsx` 把聊天页顶部改为左右 40px 圆形按钮 + 中间独立胶囊布局；胶囊内包含会话名和在线/输入状态，标题字号在用户设置值基础上压小并限制在 12-15px，避免顶栏像裸文字漂在背景上。群聊接力状态单独显示为小号 amber 胶囊，不再挤在名字/在线里。
- 已完成：`miniapp/src/ui/ChatPresentation.tsx` 将 `ChatHeaderStatus` 字号从 11px 压到 10px，并把静态“在线”颜色降为灰色，适配中间小胶囊。
- 已验证：`npm -C miniapp run build` 通过；`npm -C miniapp run build:android` 通过并同步 `miniapp_static` 相对路径 bundle；`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 通过，只有既有 Vite chunk size warning。
- 未完成 / 下次继续：本轮只改聊天顶部视觉，不改聊天发送、群聊逻辑、ChatStore 或 Android 原生通知；当前工作区仍有既有 Android 通知/悬浮球和 `tools/` 脏文件，提交时不要混入。

当前状态（2026-06-08 Tailscale 内网桥接与本地 token sync）：
- 已完成：Mac 和 VPS 加入同一 tailnet；Mac 为 `100.105.159.127`，VPS `ali-du` 为 `100.92.76.117`。VPS 与 Mac 均已关闭 Tailscale DNS 接管（`CorpDNS=false`），VPS 持久 DNS 改为 `223.5.5.5` / `1.1.1.1`，配置在 `/etc/systemd/network/10-netplan-eth0.network.d/du-gateway-dns.conf`，避免阿里云 `100.100.2.136/138` 与 Tailscale 网段冲突后导致 R2/Cloudflare 解析超时。
- 已完成：VPS 新增只监听 Tailscale IP 的 Nginx 内网入口 `/etc/nginx/conf.d/du-gateway-tailscale.conf`，监听 `100.92.76.117:8080` 并反代到 `127.0.0.1:5000`；公网 `https://duxy-home.com` 保持不变，手机/自用前端未切内网。
- 已完成：本机 `~/.ssh/config` 中 `ali-du` 已切到 `100.92.76.117`，新增 `ali-du-public` 保留旧公网 `47.250.162.10` 备用；Codex 群聊桥接 `/Users/doraemon/.du-gateway-codex-bridge/.env` 的 `GATEWAY_URL` 已切到 `http://100.92.76.117:8080` 并重启 LaunchAgent。
- 已确认：`ssh ali-du` 当前登录用户为 `nora`，具备免密 sudo（`sudo -n true` 通过）；需要操作 `/root/du-gateway` 或重启 `du-gateway` 时，用 `sudo -n bash -lc 'cd /root/du-gateway && ...'`，不要误判为“没有 root 目录权限就不能部署”。
- 已完成：本地 Claude token sync 的 `/Users/doraemon/.claude-token-sync.env` 已把 `CLAUDE_PROXY_SYNC_URL` / `CLAUDE_PROXY_STATUS_URL` 切到 `http://100.92.76.117:8080/internal/claude-oauth-*`；`com.doraemon.claude-token-sync` LaunchAgent 已重新加载，配置来源仍是 `.env`，没有把 token 写入 plist。
- 已验证：`https://duxy-home.com/health` 和 `/miniapp/` 为 200；`http://100.92.76.117:8080/health` 为 200；带 `X-PC-Token` 调内网 `/api/codex_group_chat/tasks/recent` 为 200；桥接新启动日志显示 `gateway_host=100.92.76.117:8080`；`/Users/doraemon/claude-token-sync.sh --mark` 成功写出 `marked http status has_status=1`；`ssh ali-du` 与 `ssh ali-du-public` 均可用。
- 未完成 / 下次继续：手机和自用前端仍走公网，不要误以为已切 Tailscale。当前 `8080` 内网入口反代整个网关；在 tailnet 只有自用 Mac/VPS 时风险较低，若后续加入手机、临时设备或他人账号，应收窄为只允许 `100.105.159.127` 且只放行 `/health`、`/api/codex_group_chat/`、`/internal/claude-oauth-*`。生产机后续使用 Tailscale 默认先加 `--accept-dns=false`，不要再让它接管 DNS。

当前状态（2026-06-11 MiniApp 主聊天文本附件）：
- 已完成：主聊天 `+` 面板新增“文档”入口，支持从 App 选择 `.txt` / `.md` / `.markdown` / `.pdf` / `.docx` 附件；选择后与图片一样自动发送，可附带输入框里的文字。图片、语音、表情包、通话和出行规划入口保持原有链路。
- 已完成：`/miniapp-api/chat-media/upload` 新增 `document` kind，按 MIME 或文件后缀兜底识别文本附件；文件限制 10MB，送入模型前最多保留前 60000 字，PDF 最多读取前 120 页，DOCX 会读取段落和表格；原文件仍写入 SumiTalk chat media R2，消息历史只保留文件名、链接、大小等轻量元数据，不把正文塞进聊天气泡。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/media.py storage/r2_store.py app.py` 通过；`npm -C miniapp run build` 通过并重建 `miniapp_static`，只有既有 Vite chunk size warning；本地 Flask test client monkeypatch R2 上传 `note.md` 和 `brief.docx`，确认返回 `kind=document`、文件名、remoteKey/remoteUrl 和 `textPreview`；空白 PDF 会明确返回“没有读到可用文字”。
- 未完成 / 下次继续：本轮不做 OCR，不做多文档批量，也未把群聊附件路由单独扩展；扫描版 PDF 要先 OCR，超长 PDF/DOCX 后续应走文件缓存/摘要管道，避免把全文直接塞进一次聊天请求。

当前状态（2026-06-11 MiniApp 语音气泡与转文字）：
- 已完成：`ChatPresentation.tsx` 将语音附件改为独立白色胶囊气泡，结构为播放按钮、波形、时长和右侧小圆点，不再塞进文字气泡复用外层 padding；`MainChatScreen.tsx` 把音频附件从文字 `ChatBubbleFrame` 里移到气泡外单独渲染，解决语音气泡比文字气泡肥一圈的问题。
- 已完成：语音附件有 `transcript` 时，右侧小圆点可点击展开/收起转文字内容；用户语音使用 STT transcript，渡的 `<voice>...</voice>` TTS 附件使用已有 `voiceText` transcript，不重新调用识别。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 通过；`npm -C miniapp run build` 通过并重建 `miniapp_static`；`npm -C miniapp run cap:copy` 已同步 Android web assets（该目录被 gitignore），最终又恢复普通 Web build 静态包。
- 未完成 / 下次继续：本轮只改聊天内语音附件展示，不改录音上传、TTS 生成、语音识别服务或历史数据结构。

当前状态（2026-06-16 MiniApp 存钱打卡）：
- 已完成：MiniApp「日常」页新增「存钱打卡」入口，页面为 `miniapp/src/ui/tabs/BudgetCheckInTab.tsx`，通过 localStorage 本地记录三年还款计划、每月打卡、实际存下、是否新增花呗、备注、绩效后还爸妈金额和备用金。
- 已完成：计划按辛玥当前口径写死在前端：6-8 月到手 2000，9 月后 1900；固定支出按 170 + 机动 100 + 油费（6-8 月 200，之后 100）；花呗前五个月递减后按 300/月；第一年还爸妈 5000，第二年 20000，第三年 23000；第一年备用金目标 3000，后两年 5000；二手收入不计入计划。
- 已完成：`miniapp/src/ui/AppShell.tsx` 接入懒加载面板并使用「存钱打卡」标题；`npm run build` 已重建 `miniapp_static`，静态产物包含 `BudgetCheckInTab-*.js`。
- 未完成 / 下次继续：本轮没有做后端同步、云备份、提醒推送或 Android 原生通知；记录只保存在当前 WebView/浏览器本地存储。提交时只挑 `BudgetCheckInTab.tsx`、`AppShell.tsx`、`miniapp_static` 本轮构建产物和本索引段，别混入当前工作区其它脏改。

当前状态（2026-06-17 AI 城市生存养成小游戏方案）：
- 已完成：新增方案文档 `docs/ai-city-survival-game-plan.md`，记录独立可分享移动网页小游戏方向：AI 作为玩家操控虚构角色，从 5000 元启动资金开始，在现实向偏惨的 H 市一年内尝试赚到 100 万；前期无稳定收入按日推进，获得稳定现金流后按周推进，危机期可回到日推进。
- 已完成：方案明确第一版只做单玩家普通移动网页，不做 PWA、原生 App、MCP server、真人联机或多玩家；玩家 AI 和 GM AI 均由用户配置连接器，前端规则引擎作为金钱与状态事实源。
- 已完成：方案收束了产品边界：UI 使用「角色面板 / 城市动态 / 本日计划 / 本周计划」等游戏化命名，不把内部注入结构叫成玩家可见的“游戏卡片”；帮助说明只做表层操作说明，不写成攻略或隐藏公式。
- 已更新：HTML 页面定位从“人类操作角色”改为“人类观战 AI 玩游戏”；人类每回合可选择候选事件、手写事件或无事件，默认点“下一回合”才推进，设置里可连续推进 N 回合；单回合生成要按 AI 行动、GM 结果、规则落账和面板刷新分阶段更新，不做一整串后台循环后一次性刷新。
- 已更新：补充“自由度设计”原则，并修正为“固定分类计划 + 分类内容自由”：AI 玩家每回合必须按日/周计划分类输出，分类里的职业、赚钱方式和应对策略可以自由；系统通过行动标签、技能、状态、风险和兜底规则结算，未知职业/未知安排不应报错，也不能变成无成本许愿成功。
- 已更新：补充 H 市成本锚点，物价按上海类一线城市高成本参考；租房结算要考虑房租/押金、通勤远近、交通费、环境、安全、室友/房东/中介风险，以及对健康、疲劳、压力和机会响应的影响。
- 已更新：补充“现实参照原则”，明确能参考现实的物价、薪资、求职、租房、通勤、医疗、债务、合同、平台、小生意和诈骗/灰色风险都优先用现实锚点做规则与事件平衡，后续实现时数据应可配置更新。
- 已更新：补充“不含 UI 的功能框架”，拆出 `GameRuntime`、`TurnOrchestrator`、AI 连接器、固定计划 schema、规则引擎、事件系统、经济/住房/技能/风险模型、流水、日志、存档和进度事件；单回合链路明确按人类事件 -> 玩家 AI 计划 -> GM 建议 -> 规则落账 -> 分阶段进度更新推进。
- 未完成 / 下次继续：这只是方案文档，未创建独立仓库、未写前端代码、未接 AI 连接器、未实现规则引擎或事件池；当前工作区仍有大量既有 MiniApp/静态产物脏改，本轮不要混入。

当前状态（2026-06-22 伪 COT 脑内 OS 展示与归档）：
- 已确认：服务器日志里 2026-06-22 01:16-01:45 多轮上游正文已经输出 `<DU_INNER_OS>`，说明伪 COT 不是没写；旧轮次的 `reasoning/thinking summary` 里确实有 `I cannot rewrite/process...` 拒绝文本，当前筛选拿这些原文测试会命中。
- 已确认：旧问题不是 content 路径，而是伪 COT 只在归档副本上兜底，网关返回给 TG / App 当前请求的 `resp_json.message.reasoning` 没有当场替换；App 思维链历史接口也会把旧拒绝 summary 当普通 reasoning 展示，所以看起来“从头到尾都是 i cannot”。
- 已完成：`services/pseudo_cot.py` 新增 `replace_response_reasoning_with_inner_os()`；非流式响应在剥出 `<DU_INNER_OS>` 后，会立刻把返回体里的 `reasoning` 替换为脑内 OS，并把官方拒绝文本保留到 `official_reasoning_refusal_text`，来源标为 `du_inner_os`。
- 已完成：`services/pseudo_cot.py::apply_pseudo_cot_state_and_fallback()` 在拒绝命中时始终写入 `official_reasoning_refused` / `official_reasoning_refusal_text`；有 `inner_os` 时写为 `du_inner_os_fallback`，无 `inner_os` 时标 `official_reasoning_refused`，方便后续排查。
- 已完成：`routes/chat.py` 的流式无工具、流式工具循环、非流式归档路径都把“本轮是否启用伪 COT 指令”传给归档修复函数；非流式返回体也会当场替换 reasoning，TG 当场 COT 展示和 App 后续读取不会再只看到 `I cannot rewrite...`。
- 已完成：`routes/miniapp/reasoning.py` 对历史脏数据做兜底：如果 reasoning 文本本身命中伪 COT 拒绝模式，就不再原样展示，改走“adaptive thinking 未返回可展示正文”的 omitted 提示；已有 `du_inner_os` 的轮次仍展示脑内 OS。
- 已验证：`python3 -m py_compile services/pseudo_cot.py routes/chat.py routes/miniapp/reasoning.py` 和 `git diff --check -- services/pseudo_cot.py routes/chat.py routes/miniapp/reasoning.py docs/DEBUG_INDEX.md` 通过；本地 smoke 确认 `summary=I cannot... + <DU_INNER_OS>` 时返回体 `reasoning` 会被替换为脑内 OS，App 历史接口会隐藏旧拒绝 summary。
- 未完成 / 下次继续：本轮未回写修复历史 R2 旧轮次本体；历史接口只是展示层兜底。如果要把旧 R2 对象里的拒绝文本批量替换/清理，需要单独做带备份的数据修正。

当前状态（2026-07-05 思维链日志原文展示）：
- 已完成：`routes/miniapp/reasoning.py` 不再用 `services.pseudo_cot.is_reasoning_summary_refusal()` 隐藏思维链日志文本；MiniApp 思维链页作为审计页，只要归档里有 `reasoning/reasoning_content/thinking/thinking_blocks` 就原样展示。真正的 `I cannot rewrite...` 拒绝文本也展示为原文，不再改成“未返回可展示正文”。
- 保留：伪 COT / 内心 OS 的拒绝检测仍留在 `services/pseudo_cot.py` 自己的链路里；本轮不改 TG 折叠块、不改 R2 存档、不改上游返回体。

当前状态（2026-06-23 渡秘密抽屉后端一期）：
- 已完成：新增方案文档 `docs/渡秘密抽屉功能方案.md`，收束“渡自己的秘密抽屉”功能边界：保存想留下的对话、图片、梦境、冲浪内容、碎碎念和兜底杂项；它不是动态记忆、不是日记，也不会把具体条目自动注入常规上下文。
- 已完成：新增 R2 存储层 `storage/secret_drawer_store.py`，使用 `global/du_secret_drawer.json` 存条目、`global/du_secret_drawer_config.json` 存 UI PIN 明文；未单独设置 PIN 时默认按 `0000` 解锁，设置后按配置 PIN；`sealed=true` 默认不出普通列表、搜索和随机翻一个，`deleted=true` 不计入常规统计，待整理定义为标题、标签或 why 任一为空。
- 已完成：存储层支持类型/标签/关键词/待整理/置顶/软删除/暗格过滤，支持 `restore_item()` 恢复软删除；`stats()` 返回总数、普通数、删除数、分类计数、标签计数、待整理分类、置顶、暗格和最新时间，标签统计默认不泄露暗格标签。
- 已完成：小工检查后补安全边界：PIN 配置读取失败时 `verify_pin()` fail closed，不再退回默认 `0000`；主抽屉 JSON 读取失败时写入入口 fail closed，不把空抽屉覆盖回 R2；普通 stats 不暴露暗格标签或暗格分类明细，暗格明细只在显式 `include_sealed_details=true` 时返回，且前端只有停在暗格层并已解锁时才请求暗格明细；`sealed_only=true` 会由后端先过滤暗格再 limit/random，避免普通条目太多时暗格列表/随机抽空或混池；JSON bool 统一按 `true/false/1/0/yes/no/on/off` 解析，不把字符串 `"false"` 当 true。
- 已完成：新增服务层 `services/secret_drawer.py`，统一处理 `<<<DU_SECRET_SAVE>>>...<<<END_DU_SECRET_SAVE>>>` 隐藏保存块；`save_message` 会保存本轮小玥消息、渡可见回复和当前消息图片，`save_photo` 只保存当前消息图片；工具和 API 传入的外部图片会尽量拷到 SumiTalk chat media R2，避免 QQ / TG CDN URL 过期；复制失败的外部临时 URL 不再作为图片引用保存。
- 已完成：新增 MiniApp 后端 API `routes/miniapp/secret_drawer.py` 并挂到 `/miniapp-api/secret-drawer/*`，支持 stats/config/unlock/items CRUD/restore/random；不暴露前端设置 PIN 的 HTTP 路由，PIN 由渡走 `secret_drawer` 的 `set_pin` 设置；PIN 只用于前端 UI 解锁，后端工具和存储本身无锁。
- 已完成：MiniApp 前端新增 `miniapp/src/ui/tabs/SecretDrawerTab.tsx` 并在「日常」入口挂「秘密抽屉」；参考 `ui合集/秘密抽屉` 的纸条堆、PIN 键盘、随机翻一张和暗格层次，但去掉样例的固定 375x812 假手机外壳/全局悬浮大卡片，页面在 `FullScreenPane` 内铺满真实 app 内容区。
- 已完成：聊天注入链新增 `###秘密抽屉` 短概况，只给总数、分类、置顶、暗格和待整理数量以及隐藏保存格式；工具注入只保留一个 `secret_drawer`，schema 只暴露 `action` 和 `payload`，用 `action=stats/list/get/update/delete/restore/random/set_pin` 区分操作；保存当前聊天只走 `DU_SECRET_SAVE` 隐藏标记，不注入保存工具；PIN 由渡自己用 `set_pin` 设置，前端只负责输入 PIN；对渡可见的工具说明统一叫「暗格」，不再叫「锁中锁」。
- 已完成：隐藏块剥离接入 `services/chat_sidecars.py` 和流式可见文本处理，避免 `DU_SECRET_SAVE` 标记在 App / TG / QQ 正文里露出；非流式 forced SSE 路径会先剥离隐藏块再转发，不重复保存。
- 已完成：`HiddenBlockParser` 增加 `split_all()`，`DU_SECRET_SAVE` 支持一次回复里多个完整隐藏块；后续块也会剥离并逐个保存，不会露到客户端或进可见正文。
- 已验证：`.venv/bin/python -m py_compile storage/secret_drawer_store.py services/secret_drawer.py routes/miniapp/secret_drawer.py routes/miniapp_api.py services/chat_sidecars.py services/pc_command_handler.py pipeline/pipeline.py routes/chat.py services/gateway_tools.py services/chat_tools.py` 通过；本地 monkeypatch R2 smoke 覆盖隐藏块剥离、保存本轮消息+图片、工具保存 media_refs、待整理/置顶筛选、标签统计、软删除读取与恢复、MiniApp PIN/items/random/restore；`python3 -m py_compile storage/secret_drawer_store.py routes/miniapp/secret_drawer.py services/secret_drawer.py` 和 `npm -C miniapp run build` 通过并重建 `miniapp_static`。
- 未完成 / 下次继续：当前前端是偷看/浏览 UI，不提供编辑、删除、恢复；也不提供设置 PIN 的入口，PIN 设置由渡走 `secret_drawer` 的 `set_pin`。后端仍是 R2 JSON 单对象低频写入，只有进程内锁；当前单 worker 可接受，但没有做 D1/SQLite、跨进程版本锁/CAS 或物理删除。

当前状态（2026-06-26 MiniApp 语音通话链路收束）：
- 已完成：`VoiceCallScreen.tsx` 修正 `MediaRecorder.stop()` 监听顺序，先注册 `stop` 再停止录音，避免 Android WebView 卡在“识别中”；通话页所有关键请求新增本地超时和挂断 abort，挂断/退出后的晚到响应不会再改状态或突然播放。
- 已完成：通话播放失败时保留最近一次 `audio_b64`，点击扬声器会优先打开扬声器并重播；普通状态下扬声器按钮仍是静音切换。来电 opening line 播完后会继续执行 `autoStartRecording`，不再因为有开场白跳过自动录音。
- 已完成：实时 preview 只用于界面显示，不再作为 `user_text_override` 覆盖最终 STT；最终 `/voice-call` 会上传真实录音时长，后端用现有短语音清洗压掉 1-2 秒音频里重复“嗯/停顿”的错误转写。
- 已完成：`routes/miniapp/media.py` 将 `VOICE_CALL_MAX_SECONDS` 真正用于客户端传时长时的超限拦截，并给 `/voice-call-preview` 补上音频大小上限；`services/voice_call_pipeline.py` 在 MiniMax TTS 失败时返回明确 502，不再 `ok=true` 但 `audio_b64` 为空。
- 已验证：`.venv/bin/python -m py_compile services/voice_call_pipeline.py routes/miniapp/media.py app.py`、`.venv/bin/python -c "import app"`、`git diff --check`、`npm -C miniapp run build` 通过并重建 `miniapp_static`；`npx/tsc --noEmit` 当前仍被既有 `PromptManagerScreen.tsx` 的 `editable?: boolean` 类型问题挡住，和本轮语音通话改动无关。
- 未完成 / 下次继续：本轮没有做 WebRTC、后台前台录音服务、通话 job 化/断点恢复，也没有改 nginx/realtime 服务健康检查；真正抗熄屏/切网/进程重启还需要单独做通话任务队列或原生侧托管。

当前状态（2026-06-26 MiniApp 私聊取消发送待定队列）：
- 已完成：`MainChatScreen.tsx` 将私聊输入聚合改成内部 `idle / armed / paused / flushing` 状态机。每条私聊输入默认进入 15 秒聚合队列；新输入会重置倒计时；点击“取消发送”只切到 `paused/cancel`，不删除气泡、不发送、不在气泡上显示“待定”标记；下一条输入会恢复队列并把旧消息一起纳入新的 15 秒窗口。
- 已完成：flush 开始时不再把 localStorage 写空；当前批次会先转入 `flushingItems`，成功后才清掉，准备失败或发送失败会把批次放回队列并切到 `paused/failure`。如果旧批次发送过程中又输入新消息，新消息会成为新的 armed 队列，旧批次成功不会误清新队列。
- 已完成：取消/失败暂停中的队列仍可长按用户气泡编辑或删除；删除会写入本地 deleted id sidecar，历史加载、远端 resync、`saveDisplayHistory()` 都会过滤这些 id，避免被删掉的待发消息从远端/本地历史恢复时回魂。这个 sidecar 只用于待发聚合消息，不改变普通消息状态。
- 已完成：`chatStore.ts` / `nativeChatStore.ts` / `chatHistoryDb.ts` 增加按消息 id 删除本地历史的抽象；实现上复用现有 `upsertMessages` 写 `deletedAt` tombstone，不新增 native 插件方法，尽量兼容已经安装的 Android 壳。
- 已验证：`npm -C miniapp run build` 通过并重建 `miniapp_static`；`git diff --check` 通过；`npx tsc --noEmit --pretty false` 只剩既有 `src/ui/PromptManagerScreen.tsx:92` 的 `editable?: boolean` 类型问题，和本轮取消发送队列改动无关。
- 未完成 / 下次继续：本轮只修私聊 Du 的聚合取消/编辑/删除语义，不改群聊取消笨笨任务、不改后端 job 取消语义，也不把“待定”持久化成可见消息状态；后续如需更严谨，可为 `flushingItems` 做服务端 operation 回查去重，降低崩溃恢复后人工重发的重复风险。

当前状态（2026-06-26 MiniApp 工具调用流式展示稳定性）：
- 已完成：`MainChatScreen.tsx` 的 SumiTalk 流式事件只更新当前 UI，不再每个事件都后台写本地历史，避免半截内容与最终回复保存乱序；同时按 `window_id` 过滤错窗口事件。
- 已完成：`chatMessages.ts` 不再让 `sent/failed` 终态助手消息继续吃迟到流式事件；失败/取消消息不会继承半截工具调用链；工具调用在缺少 `tool_call_id` 时用 `round + name` 做兜底合并 key。
- 已完成：`PromptManagerScreen.tsx` 给远端自定义 prompt 段落补 `editable: true` 默认值，修掉 `tsc` 既有阻断点。
- 已验证：`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json`、`git diff --check`、`npm -C miniapp run build` 通过；`miniapp_static/index.html` 已指向新入口 `index-Mpj23jq8.js`。本轮只改 MiniApp 前端和静态包，没有改 SumiTalk 后端队列/worker，线上只需重启 `du-gateway.service`。
- 未完成 / 下次继续：没有做后端 token 级流式；当前“流式展示”仍是按 SumiTalk job events 一轮一轮追加可见内容和工具调用状态。

当前状态（2026-06-26 Codex 群聊 bridge 稳定性第一刀）：
- 已完成：`services/codex_group_chat.py` 的 `finish_task()` 改为终态幂等，`done/cancelled` 不会被 bridge 迟到的 `error` 或 `response` 覆盖；`claim_next()` 会记录 worker 最近状态，新增只读 `/api/codex_group_chat/workers/status` 方便确认桥接是否在线、是否有 outbox 积压。
- 已完成：`scripts/codex_group_chat_bridge.py` 增加本地 `finish_outbox.json`；Codex 已生成的成功回复如果回写 `/finish` 遇到 502/503/504/timeout，会落盘并按退避重试，不再把传输失败当成任务失败回写。claim 循环连续失败时指数退避，恢复后继续 flush outbox 和 claim。
- 已完成：`scripts/install_codex_group_chat_launch_agent.sh` 写入 outbox 路径、post retry、claim backoff 和 finish outbox retry 默认参数，避免重装 LaunchAgent 后缺关键配置。
- 已验证：`python3 -m py_compile services/codex_group_chat.py routes/pc_command.py scripts/codex_group_chat_bridge.py` 通过；临时 `_TASK_FILE` smoke 覆盖 done 不被迟到 error 覆盖、cancelled 不被迟到 response 覆盖、worker 状态记录；bridge outbox smoke 覆盖 finish 失败落盘、到期后 flush 成功、response 队列会丢弃同任务旧 error。
- 未完成 / 下次继续：本轮没有迁 SQLite、没有改前端显示“桥接离线/回写重试中”；上线后需要重新安装/重启本机 Codex bridge LaunchAgent 才会加载新 bridge 脚本和 `.env` 默认值。

当前状态（2026-06-26 Codex 群聊 bridge 稳定性第二刀）：
- 已完成：Codex group task 新增 `lease_token / lease_required / lease_expires_ts`；新 bridge claim 时会带 `worker_version` 自动启用 lease，旧 bridge 不带版本时仍保持兼容 finish，降低部署窗口卡死风险。
- 已完成：新增 PC 内部接口 `POST /api/codex_group_chat/tasks/<id>/heartbeat`；bridge 在 Codex 子进程运行中按 `CODEX_GROUP_CHAT_HEARTBEAT_SECONDS` 默认 30 秒续租，续租失败若明确是 lease 失效会终止本地 Codex 子进程，避免旧 worker 继续跑完后乱回写。
- 已完成：`finish_task()` 校验 lease；旧 token 或缺 token 的新任务 finish 会返回/传递 `lease_conflict`，路由给 409，bridge 不会把这类非重试错误写进 finish outbox。任务完成后会清掉 lease 字段，`done/cancelled` 终态仍保持不可覆盖。
- 已验证：`.venv/bin/python -m py_compile services/codex_group_chat.py routes/pc_command.py scripts/codex_group_chat_bridge.py` 和 `python3 -m py_compile ...` 均通过；临时 `_TASK_FILE` smoke 覆盖旧 bridge 兼容 finish、新 bridge claim 带 token、heartbeat 续租、lease 过期后被新 worker 重领、旧 token finish 被拒、新 token finish 成功且迟到 error 不覆盖；bridge smoke 覆盖 heartbeat 请求体和 `lease_conflict` 不进入 outbox。
- 未完成 / 下次继续：仍未迁 SQLite 或跨进程文件锁；当前 JSON 队列依赖生产 gunicorn 单 worker 更稳。前端还没有展示“bridge 离线/lease 失效/回写重试中”的状态文案。

当前状态（2026-06-27 MiniApp 聊天快乐体字体）：
- 已完成：新增本地字体资产 `miniapp/src/assets/fonts/zcool-kuaile-regular.ttf`，来源为 Google Fonts 的 ZCOOL KuaiLe / 站酷快乐体；同时保留 `zcool-kuaile-OFL.txt` 授权文本。字体仅作为聊天字体可选项，不替换默认字体。
- 已完成：`CHAT_FONT_KEYS` 新增 `kuaile`，个性化页聊天字体轮换会显示“快乐体”；`AppShell.tsx` 注册 `SumiZcoolKuaiLe`，`resolveChatFontFamily()` 将该 key 映射到新字体，并保留苹方、微软雅黑、Noto Sans SC 兜底。
- 已验证：`git diff --check -- miniapp/src/ui/AppShell.tsx miniapp/src/ui/chatAppearance.ts miniapp/src/ui/chatMessages.ts docs/DEBUG_INDEX.md` 通过；`npm -C miniapp run build -- --outDir /tmp/du-miniapp-font-build --emptyOutDir` 通过并确认新字体进入临时构建产物。注意：`miniapp/vite.config.ts` 写死 `outDir: ../miniapp_static`，默认 build 仍会改写静态目录；`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json` 当前被既有 `PromptManagerScreen.tsx allow_empty` 类型问题挡住，和字体改动无关。
- 未完成 / 下次继续：本轮不调整全局 UI 字号，也不把字体应用到一级页面标题/列表；如需解决“整个 app 字大”，应单独加界面字号/界面字体设置。当前工作区已有与本轮无关的 `miniapp_static` 构建产物和若干业务源码脏改，提交时要么明确重建并一起推静态包，要么不要混入静态目录。

当前状态（2026-06-28 MiniApp 助手回复语音 TTS 去重）：
- 已确认：SumiTalk 私聊的 `<voice>` 回复语音会在正常发送完成路径和 operation 恢复/前台补偿路径里都调用 `appendAssistantVoiceOutputAudio()`；原函数只检查目标助手消息是否仍是当前 sent 状态，没有同一段 voiceText 的 in-flight 锁或已有音频检查，所以两条路径并发时会向 `/miniapp-api/chat-media/tts` 发两次同文案请求。
- 已完成：`miniapp/src/ui/MainChatScreen.tsx` 给助手回复 TTS 增加按 `assistantId + clientRequestId + operationId + voiceText` 的页面内 in-flight 去重；生成前和生成返回后都检查当前助手消息是否已经有相同 transcript 的音频附件，命中时记录 `assistant_voice_tts_skip` 并不再追加第二条音频。
- 已完成：交换日记评论回复展示修复一并收束：`ExchangeDiaryTab.tsx` 会把 `reply_to_comment_id` 显示成“渡 回复 我/我 回复 渡”；`services/chat_tools.py` 的 `exchange_diary` 工具读评论时会把被回复评论作者映射成可读对象，并不再要求 comment 创建时传 emoji。
- 已完成：`PromptManagerScreen.tsx` 给未知远端 prompt 段落补 `allow_empty` 默认值，修掉本轮 `tsc --noEmit` 的类型阻断。
- 已验证：`.venv/bin/python -m py_compile routes/miniapp/dashboard.py services/chat_tools.py services/conversation_followup.py services/spring_dream.py services/telegram_proactive.py storage/runtime_sqlite.py`、`npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json --pretty false`、`git diff --check`、`npm --prefix miniapp run build` 均通过，并已重建 `miniapp_static`。
- 未完成 / 下次继续：本轮不改 TTS 后端、不改 `<voice>` 提示词、不批量清理已经存在的历史重复音频；如果线上仍出现重复，优先看日志里的 `assistant_voice_tts_start / assistant_voice_tts_skip` 是否同一个 `clientRequestId` 被不同路径触发。

当前状态（2026-06-28 MiniApp 语音条时长缓存）：
- 已确认：语音附件会持久化 `remoteUrl` 和可选 `durationMs`，但 TTS 返回时通常没有 `durationMs`；`ChatVoiceBar` 之前只能等隐藏 `<audio preload="metadata">` 触发 `loadedmetadata` 后才知道秒数，所以历史重新渲染时会先显示 `0"`，再像重新加载一样补时长。
- 已完成：`ChatPresentation.tsx` 给语音条增加 `onDurationLoaded` 回调；读到 metadata 时把实际时长回传。`MainChatScreen.tsx` 接住回调，按 messageId + audio attachment id 把 `durationMs` 写回当前消息并后台保存本地历史；下次恢复历史时直接用缓存的 `durationMs` 展示。
- 已验证：`git diff --check -- miniapp/src/ui/ChatPresentation.tsx miniapp/src/ui/MainChatScreen.tsx` 和 `npx --prefix miniapp tsc --noEmit -p miniapp/tsconfig.json --pretty false` 通过。
- 未完成 / 下次继续：本轮不改后端 `/chat-media/tts` 的音频时长探测，也不批量扫描旧历史；旧语音会在下一次被渲染并读到 metadata 后逐条补上时长。

当前状态（2026-06-28 Pioneer Claude 透传与思维链价格展示）：
- 已完成：新增 `config.is_pioneer_url()` / `PIONEER_CLAUDE_CACHE_TTL=1h`，只用于识别 Pioneer 和 Claude 缓存 TTL；不做 Pioneer 专属默认模型兜底，也不覆盖其他上游。
- 已完成：`storage/upstream_store.py` 对 Pioneer `/v1/models` 只保留 `claude-*` 这种 Claude proxy 短模型名，并按 `claude-opus-4-6/4-7/4-8/4-1/sonnet/haiku` 优先排序；`routes/chat.py` 的网关 `/v1/models` 同样过滤 Pioneer，避免外部客户端看到 144 个混杂模型。
- 已完成：`services/upstream_policy.py` 将 Pioneer 视为 Claude 透传上游：对 leading system 稳定块、近期记忆稳定块/最近块写入 Anthropic content block 形式的 `cache_control: {type:"ephemeral", ttl:"1h"}`，并在发给上游前删除 `__dynamic__ / __summary_cache__ / __summary_recent__` 内部标记；`claude-opus-4-6/7/8` 复用本地 Claude OAuth proxy 的 adaptive thinking 格式。
- 已完成：MiniApp API 管理的模型弹层按 `Claude / 其他` 分组；Pioneer 后端过滤后通常只显示 Claude 分组。思维链日志后端按 Claude 价格口径计算本轮 `cost.total_usd`，前端 Prompt Cache 卡片只展示总价 `cost=$...`。
- 已验证：`.venv/bin/python -m py_compile config.py storage/upstream_store.py services/upstream_policy.py routes/chat.py routes/miniapp/reasoning.py`、`git diff --check`、`npm --prefix miniapp run build` 通过；本地真实 Pioneer `/v1/models` 拉取返回 `source=pioneer_claude_models count=9`，首批为 `claude-opus-4-6/4-7/4-8/4-1/sonnet/haiku`；mock 当前 active 为 Pioneer 时，请求体会生成 A 社 content block + `cache_control ttl=1h`，并写入 adaptive thinking。
- 未完成 / 下次继续：本轮没有发真实 Pioneer chat completion 扣费测试；价格展示暂按 Claude `input 5/M、cache write 10/M、cache read 0.5/M、output 25/M` 计算，只作为思维链日志估算展示。

当前状态（2026-06-28 Claude OAuth proxy 新 VPS 迁移方案）：
- 已完成：新增 `docs/claude_proxy_new_vps_migration_plan.md`，把“旧 VPS 跑网关、新 VPS 跑 Claude Code + Claude OAuth proxy、旧 VPS 用 SSH tunnel 保持本机 `127.0.0.1:8082`”写成可执行方案；方案包含现有功能保留清单、日志接入与观测、验证、回滚和故障排查。
- 已完成：`docs/DEBUG_INDEX.md` 的 Claude OAuth proxy 索引项补上迁移方案入口。
- 已验证：`git diff --check -- docs/claude_proxy_new_vps_migration_plan.md docs/DEBUG_INDEX.md` 通过；本轮只写文档，不改服务、不改 env、不重启。
- 未完成 / 下次继续：买好新 VPS 后，从方案的“新 VPS 初始化”开始执行；执行前先确认新 VPS IP、旧 VPS SSH alias、旧 VPS 实际运行用户和 proxy 文件路径。

当前状态（2026-07-04 Claude OAuth 新授权同步口径）：
- 已完成：新授权后不在本机强制刷新；本机只读取 Claude Code Keychain 中的完整 OAuth credential JSON，并通过 HTTP POST 同步给转发 VPS。转发 VPS 的 Claude OAuth proxy 持有 refresh token，后续由 proxy 自己在过期/临近过期时刷新。
- 已完成：`scripts/claude_oauth_proxy.js` 的 `/internal/oauth-sync` 和网关转发层 `routes/claude_oauth_sync.py` 允许完整 credential 透传/落盘；同步响应只回 `expiresAt`、`canRefresh` 等摘要，不回 token。
- 已完成：Claude OAuth proxy 不再插入 `You are Claude Code...` 系统提示词，只在 `system[0]` 注入 `x-anthropic-billing-header` 计费块；模型请求头带 `Authorization`、`anthropic-version: 2023-06-01`、`anthropic-beta`、`User-Agent: claude-code/2.1.195 (external, cli)`、`Content-Type: application/json`。`anthropic-beta` 的前两项按 gist 顺序为 `oauth-2025-04-20,claude-code-20250219`，后面继续保留现有 interleaved thinking / prompt cache scope / context management beta，避免砍掉当前功能。
- 待验证：本轮改动需要重新跑 `node --check scripts/claude_oauth_proxy.js`、`.venv/bin/python -m py_compile routes/claude_oauth_sync.py`，然后同步到实际运行的 proxy 文件并重启相关服务。

当前状态（2026-07-05 渡的页笺与旧临时预览收束）：
- 已完成：新增长期保存“渡的页笺”的后端骨架；`storage/du_pages_store.py` 使用 `data/du_pages.sqlite3` 持久化完整 HTML、标题、emoji、说明、标签、来源和软删除状态，列表默认不返回 HTML 正文，避免管理页加载全量源码。
- 已完成：新增公开打开路由 `GET /du-pages/v/<page_id>`，返回 `text/html; charset=utf-8` 并加 `noindex/no-store`、`Referrer-Policy` 和基础 CSP；链接是稳定长期链接，不走临时预览 TTL，也不依赖进程内存。
- 已完成：新增 MiniApp 管理 API `GET/POST /miniapp-api/du-pages`、`GET/PATCH/DELETE /miniapp-api/du-pages/<id>`、`POST /miniapp-api/du-pages/<id>/restore`、`GET /miniapp-api/du-pages/stats`，供后续前端 UI 列表、打开、编辑、删除、恢复使用。
- 已完成：新增渡可用工具 `du_page`，只用一个工具名，通过 `action=save/list/get/update/delete/restore/stats` 分流；生成 HTML 页面、情书、小网页、小游戏和排版作品时必须 `action=save` 并传完整 `html`，保存后返回长期链接。
- 已完成：模型侧旧临时 HTML 工具、旧 HTTP 写入口、旧临时预览 store 均已删除；聊天链路不再注入、不再执行、不再自动补临时预览链接。后续写 HTML 统一走 `du_page` 落到“渡的页笺”。
- 已完成：新增 `services/public_url.py` 作为通用公网根地址 helper；XiaoAI 音频、截图媒体、页笺链接共用它，不再依赖旧预览模块命名。
- 已完成：MiniApp “渡的页笺”入口接到日常页；列表、详情、编辑、删除、内置 iframe 预览已接后端 API；本地 demo/fallback 已移除，真实为空就显示空态，不再把旧救援页伪装成真实记录。
- 已修复：`list_pages(tag=...)` 不再先按 limit 截断后筛标签，避免标签过滤漏掉较旧页笺。
- 已验证：`.venv/bin/python -m py_compile storage/du_pages_store.py services/du_pages.py routes/du_pages.py routes/miniapp/du_pages.py app.py routes/miniapp_api.py services/gateway_tools.py services/chat_tools.py` 通过；本地 smoke 覆盖保存、列表、标签筛选、读取、软删除；`du_page` 工具分发正常，旧临时 HTML 工具未注入；`app` 路由表有 `/du-pages/v/<id>` 且无旧临时预览路由；`cd miniapp && npx tsc --noEmit --pretty false` 与 `cd miniapp && npm run build` 均通过；旧工具/旧路由关键字全仓库扫描无残留。
- 未完成 / 下次继续：需要把线上那份大富翁 HTML 作为真实 `du_page` 记录导入；推送部署后需验证 `du_page` 工具保存、`/du-pages/v/<id>` 打开、MiniApp 列表加载与删除。

当前状态（2026-07-06 SumiTalk App `recall_message` 撤回仪式）：
- 已完成：新增渡可调用工具 `recall_message`，最终执行必须落到 `messageIds`，不猜“最近一条”；工具只发 App 聊天界面动作，不物理删除 R2/后端历史。
- 已完成：`app_actions` 队列新增 `surface=chat_ui` 隔离，原生壳默认只轮询 `native`，聊天页通过 `chat_ui_device_actions` 实时事件或 `/miniapp-api/device-actions?surface=chat_ui&window_id=...` 兜底轮询领取，避免未知动作被 Android 壳误消费。
- 已完成：MiniApp 聊天页收到撤回动作后先展示男鬼弹窗风格仪式，最后弹窗带 `countdownSeconds/timeoutChoiceId`；用户选择或倒计时自动选择后，并行回传结果给后端、执行前端撤回收尾、本地隐藏消息并写入 tombstone。
- 已完成：`RecallMessageOverlay` 视觉按 `ui合集/男鬼弹窗` 的黑红故障弹窗方向重做：深红黑底、红色错误标题栏、glitch 文字、原版式 `createAlert()` 逐个 append、`delay = max(42, delay * 0.84)` 先慢后快堆叠；本轮把 `prelude` 前摇从血雾/水墨晕染撤回，改为 0.9s 闪屏故障：黑红白瞬闪、画面轻错位、块状撕裂，再进入弹窗雨，最终选择窗时间随此前摇顺延；App 窄屏下额外扩展横向随机溢出范围，避免原版坐标公式被 320px 视口压成整齐一列；本轮又下调了弹窗宽度、字号、红色实度、边框和阴影，并缩短弹窗雨前段等待、拉大加速差异；最终选择窗回退为直接挂载的 opacity/轻位移/轻 scale 入场，不再使用 handoff 或 blur，旧弹窗只降透明不虚化；本轮把最终窗入场调成 70ms 延迟 + 320ms ease-out，并让旧弹窗同步轻缩放降暗，减少最后窗硬弹出的突兀感；已移除底部 `SYSTEM STATUS / ERRORS` 计数条和对应前端计数状态；已移除随机 `PART 4` badge 和备用 `Part 4` 文案，并清理偏设计/审美指责的英文标题池，只保留系统错误类短标签，避免男鬼弹窗里出现无意义英文装饰。只改前端仪式表现，不改工具入队/回传/隐藏消息边界。
- 已完成：新增 dev-only 本地直接测试入口 `http://127.0.0.1:5173/miniapp/?recallPreview=1`；入口绕过面板鉴权、直接进入渡单聊、注入假消息并本地触发 `recall_message`，不依赖真实后端动作队列，也不写真实聊天记录。为避免首屏首页预览误拉 history，预览模式初始 `activeScreen=du`。
- 已完成：回执唤醒渡时带回最终选择和原消息，语义为“你已撤回她的这条消息：`【已撤回】原消息`”；新增 `recall_message_markers` runtime 表，后续 Last4 注入只在上下文展示层把对应用户消息标成 `【已撤回】原消息`，不改原始归档。
- 已完成：小工审阅后补边界：前端 `recall_message` 动作改为串行队列，避免并发弹窗覆盖 resolver；目标消息暂未加载时最多重试再失败；最终弹窗支持长内容滚动、默认聚焦、44px 触控按钮、窄屏 clamp 和 reduced-motion 降级；最终弹窗结束后先停顿 2 秒，再把被撤回的原用户消息直接替换为按撤回发生时间插入当前聊天底部的居中灰字提示“渡撤回了你的消息”；一次撤回多条同轮用户气泡时，按当前聊天列表从下往上每 650ms 逐条替换；撤回路径只处理命中的用户 `messageId`，不再走会清默认问候语的通用 sanitize，避免误伤渡的非目标气泡；撤回提示作为消息分组硬边界，后续渡消息不能合并进去变成普通气泡；不显示原文、不冒充用户消息，并自动滚到提示位置。
- 已完成：小工审阅后补后端边界：`recall_message` 入队强制非空 `windowId`，`chat_ui` poll 要求请求窗口与动作窗口严格一致；回执/marker 以后端 action payload 的窗口为准，客户端回传窗口不再优先；global Last4 场景按全局 marker 补标，避免新窗口注入漏出已撤回原文。
- 已修复（2026-07-07 后端复扫）：`routes/miniapp/device_actions.py` 的 `recall_message` 回执唤醒文本补上 `payload_window_id/result_window_id` 解析，修掉 done 回执时 `NameError`；客户端回传窗口和服务端 payload 窗口不一致时只告警，唤醒文本和 marker 仍以服务端 action payload 窗口为准。
- 已完成（2026-07-07 撤回候选定位）：聚合输入平时正文保持干净，不加编号/id；MiniApp 私聊发送时用隐藏 `recall_targets` sidecar 带本轮用户气泡 `{id/text/index/createdAt}`，后端写入 `recall_message_targets` runtime 表，每个窗口只保留最近 10 轮、每轮最多 8 个、文本预览最多 300 字、TTL 24 小时。`routes/chat.py` 和 SumiTalk job 入队都会消费并从上游 `body/chat_body` 移除 sidecar，避免普通模型正文泄漏。`recall_message` 没传 `messageIds` 时会按当前 `client_request_id`/`candidateSetId`/`index`/`targetText` 查候选；唯一解析才转成真实 `messageIds` 执行，否则只返回候选让渡二次选择。
- 已修复（2026-07-07 撤回候选复扫 P2）：前端收到 `recall_message` 动作时不再允许“部分成功”；缺 `messageIds` 直接 `failed/missing_message_ids`，payload 混入已找到但非 `user` 的消息直接 `failed/non_user_target`，目标用户消息未加载齐才继续按原逻辑重试，避免 `assistant-*` 混入后 UI 只撤用户气泡但回执仍 done。新增可复跑脚本 `scripts/test_recall_message_targets.py`，固定覆盖 sidecar pop、窗口绑定、index/targetText/queryOnly、十轮裁剪和前端 guard 静态检查。
- 已完成（2026-07-07 撤回后渡回复）：`recall_message` 新增 `replyText`，作为撤回后留在聊天界面的渡的回应。前端收到 `replyText` 时会把被撤回的用户气泡替换成一条居中系统提示 pill，提示文案就是渡给这条气泡写的回应；旧动作没有 `replyText` 时仍 fallback 到居中灰字“渡撤回了你的消息”。`recallReply` 只作为分组硬边界，避免和前后渡消息合并成普通聊天气泡。回执唤醒和 `recall_message_markers` meta 会记录 `replyText`，方便后续上下文知道界面里留下了哪句话。
- 已调整（2026-07-07 撤回默认定位）：`recall_message` 不传 `messageIds`、`index/indexes`、`targetText` 且不是 `queryOnly` 时，如果工具上下文有当前 `client_request_id`（或显式 `candidateSetId`），默认撤回这一轮候选集里的全部用户气泡；没有当前轮锚点时仍只返回候选，避免误撤最近十轮。
- 已调整（2026-07-07 多气泡撤回复文）：`recall_message` 新增 `replyTexts` 数组，按 `messageIds` / 当前轮气泡顺序逐条对应撤回后留下的系统提示；只传 `replyText` 时多条共用一句，`replyTexts` 没写够时用最后一句或 `replyText` 兜底，多写的会被截断。前端、action payload、回执唤醒和 marker meta 都保留逐条文案。
- 已验证：`.venv/bin/python -m py_compile storage/runtime_sqlite.py services/recall_message_markers.py storage/app_action_store.py services/realtime_publish.py services/realtime_app.py routes/miniapp/device_actions.py services/device_action_tools.py services/mcp_forum_tools.py services/chat_tools.py routes/chat.py pipeline/pipeline.py`、`git diff --check`、`npm --prefix miniapp run build` 通过；隔离 smoke 覆盖缺 `windowId` 入队失败、native 轮询捞不到 `recall_message`、chat_ui 同窗口能捞到、空/错窗口捞不到、客户端回错窗口时 marker 仍写 payload 窗口、global marker 可补标。黑红故障弹窗版本已用真实 MiniApp 本地页面验证，dev 预览入口在当前 in-app browser 320x701 视口下实测 `t+1.2s=4`、`t+3.7s=20`、`t+6.7s=77`、`t+11.5s=153/进入最终弹窗`，可见窗口上限 40 个；本轮横向范围已散到约 `x=-123..435`，宽高约 `152..298 / 126..189`，点击“我知道了”后假消息消失，且没有 `/miniapp-api` 请求。本轮清理英文标题池后，源文件已无那几组出戏标题，`git diff --check` 和 `npm --prefix miniapp run build` 通过；当前浏览器控制读取 DOM 超时，未把它计为本轮浏览器实测。
- 本轮新增验证：临时 `RUNTIME_STATE_DB=/tmp/du-recall-smoke.sqlite3` smoke 覆盖缺 `messageIds`、缺 `windowId`、`native` 隔离、`chat_ui` 同/错窗口领取、错窗口回执按 payload 窗口唤醒与写 marker、同窗口 Last4 标 `【已撤回】`、错窗口不误标；临时 `RUNTIME_STATE_DB=/tmp/du-recall-targets-smoke.sqlite3` 覆盖隐藏 `recall_targets` 消费后从 body 移除、按 `index` 和 `targetText` 解析到 messageId、queryOnly 返回候选；临时 `RUNTIME_STATE_DB=/tmp/du-recall-tool-smoke.sqlite3` 覆盖 `recall_message` 第一次只查候选不入队、第二次 `index=2` 转 `messageIds` 入队；`scripts/test_recall_message_targets.py` 已作为可复跑版本补入；后端相关 `py_compile`、`git diff --check` 和 `npm --prefix miniapp run build` 通过。
- 未完成 / 下次继续：还没有在真实 App 里点一次端到端效果；推送部署后优先测一条真实用户消息 id 的撤回，确认弹窗、回执唤醒、刷新后不回魂，以及 Last4 给渡的标记措辞。

当前状态（2026-07-07 聊天页思维链/工具调用展示开关）：
- 已完成：MiniApp 个性化「信息显示」新增「聊天中显示思维链」和「聊天中显示工具调用」两个开关，默认关闭；聊天页内联 reasoning、工具调用链，以及工具轮/普通回复附带的「碎碎念」都受这两个开关控制，不再沿用旧的 `miniapp.ui.expandReasoning` 默认展开行为。
- 已完成：`ChatReasoningBlock` 改为默认折叠；独立「思维链」调试页 `miniapp/src/ui/tabs/ReasoningTab.tsx` 不受这次聊天展示开关影响。
- 已修复：`recall_message` 撤回后留下的居中系统提示继承原用户气泡 `createdAt`，并在 `groupChatMessages()` 中作为单条系统提示硬边界渲染，不再按撤回发生时间跑到后面，也不再被拆行/并入普通渡气泡；群聊最近消息/上下文构造会跳过这些前端留痕提示。
- 已验证：`git diff --check` 和 `npm --prefix miniapp run build` 通过；本地 `http://127.0.0.1:5173/miniapp/?recallPreview=1` 重新跑完撤回预览，3 条撤回提示停在原用户消息位置，后续渡消息保持在其后，默认未显示 `碎碎念` / `recall_message`；构建产物入口更新到 `miniapp_static/assets/index-BoCSxAGF.js`，只剩 Vite 既有的大 chunk 警告。
- 已修复（2026-07-07 旧历史撤回提示兼容）：已保存历史里如果 `recallNotice/recallReply` 标记丢失，但消息 id 仍是 `recall-notice-*` / `recall-reply-*` 或带 `recallOriginalMessageId`，`sanitizeHistoryMessages()` 和 `groupChatMessages()` 会重新识别成撤回系统提示，避免它作为普通 assistant 消息进入左侧聊天气泡；群聊上下文和当前轮边界也复用同一识别逻辑跳过这些提示。已验证 `git diff --check`、`npx tsc --noEmit --pretty false`、`npm --prefix miniapp run build` 通过；另用 `/tmp` 临时编译 `chatMessages`，烟测确认旧 `recall-notice-*` 历史消息被拆成单独 `recallNotice` 分组，不会并入前后 assistant 气泡。入口更新到 `miniapp_static/assets/index-D1iSNAiy.js`。

当前状态（2026-07-10 Codex OAuth 专用 Prompt）：
- 已完成：Prompt 管理新增 `codex_oauth_prompt`，手机端显示为「Codex OAuth 专用 Prompt」，复用现有 R2 保存、版本冲突检查、备份和回滚链路；条目允许留空，留空时不注入。
- 已完成：主聊天静态区只在当前 active 上游命中 CPA / CLIProxyAPI（本机 `127.0.0.1:8317`）时读取并注入该 Prompt；调用顺序固定在入口静态内容之后、NSFW 规则之前。Claude OAuth Proxy `8082` 和其他上游不注入。
- 已完成：CPA 的 `gpt-5.6-sol` 增加独立思考强度设置，App 可选 `low/medium/high/xhigh/max/ultra`；档位按稳定 upstream key 保存在当前 Codex OAuth 节点，转发时只对 CPA + `gpt-5.6-sol` 写入对应 `reasoning_effort`，CPA 其他模型继续固定 `high`，其他上游不受影响。
- 已验证：隔离 smoke 覆盖 8317 命中、8082 不命中、最终顺序为 `BASE -> CODEX_ONLY -> NSFW_RULES`，并确认该条目允许保存为空；后端 `py_compile`、MiniApp `tsc --noEmit` 和 `/tmp` 隔离生产构建通过。
- 未完成 / 下次继续：实际专用 Prompt 内容仍为空，由小玥在手机 Prompt 管理中填写；部署后用 CPA 上游发一轮并在 Prompt Cache 静态区确认顺序。

当前状态（2026-07-11 R2 存储拆分第一刀）：
- 已完成：新增 `storage/r2_client.py`，集中承接 Cloudflare R2 S3 客户端、JSON 读取和带重试的 JSON 写入；`storage/r2_store.py` 继续按原私有函数名兼容导出，现有调用方不需要改。
- 已完成：新增 `storage/r2_wenyou_store.py`，完整迁出文游 session、钱包、候选池、连续性卡片和归档的 SQLite 主存 / R2 回填与可选备份逻辑；`storage/r2_store.py` 保留全部原文游 API 兼容导出，文件从 4282 行降到 3865 行。
- 已验证：`scripts/test_r2_wenyou_store.py` 纯内存覆盖旧入口导出、SQLite 主写不触碰 R2、R2 缺失回填、可选备份和 JSON helper；相关 `py_compile`、`import app`、`git diff --check` 通过，未访问真实 R2、VPS 或上游模型。
- 未完成 / 下次继续：下一刀可迁出 `storage/r2_store.py` 的 stickers / SumiTalk 媒体尾段；不要与当前囚禁模拟器、MiniApp 构建产物和 VPS 迁移文档改动混在同一提交里。

当前状态（2026-07-11 R2 存储拆分第二刀）：
- 已完成：新增 `storage/r2_sticker_store.py`，迁出 sticker 分类元数据、标签集合、映射扫描/重建、上传和删除；新增 `storage/r2_media_store.py`，迁出通用对象读取、SumiTalk 图片/音频/文档及缩略图、设备截图 token 读写。
- 已完成：`storage/r2_store.py` 继续兼容导出原函数和 `R2_KEY_STICKERS_MAPPING`、`R2_KEY_STICKERS_META`、`R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX` 常量，现有 Telegram、MiniApp 和 secret drawer 调用方无须修改；总入口从 3865 行降到 3416 行。
- 已验证：`scripts/test_r2_object_stores.py` 纯内存覆盖兼容出口、默认标签合并、映射扫描、保留 key / 路径穿越拒绝、附件类型、上传元数据和截图 token；第一刀文游存储测试、文游规则 smoke、相关 `py_compile`、`import app` 与 `git diff --check` 一并通过，未访问真实 R2、VPS 或上游模型。
- 未完成 / 下次继续：R2 总入口下一刀优先迁出 MiniApp 背景/语音/日报/记事本/StudyRoom 配置段；聊天主链和当前游戏半成品仍保持不动。

当前状态（2026-07-11 R2 存储拆分第三刀）：
- 已完成：新增 `storage/r2_miniapp_store.py`，迁出背景和语音配置/版本化图片、通话记录、每日气泡/报告、心情温度计及渡的记事本；新增 `storage/r2_device_reporting_store.py`，迁出设备上报配置的 SQLite 主读、R2 兼容文档和分类开关；新增 `storage/r2_studyroom_store.py`，迁出 StudyRoom 归类、规范化和增删改存储。
- 已完成：`storage/r2_store.py` 保留上述原函数、私有 helper、StudyRoom 常量、设备上报常量和全部 R2 key 兼容导出，现有 routes/services/scripts 调用方无须修改；总入口从 3416 行降到 2738 行。
- 已验证：`scripts/test_r2_miniapp_stores.py` 纯内存覆盖兼容出口、背景版本双写、日报 key、通话删除、记事本排序、设备 SQLite 主读/R2 同步、StudyRoom 归类与规范化；前三刀全部存储测试、文游规则 smoke、相关 `py_compile`、`import app` 和 `git diff --check` 一并通过，未访问真实 R2、VPS 或上游模型。
- 未完成 / 下次继续：R2 总入口下一刀优先迁出 conversation 存档/compact/轮次管理；这会触及聊天热路径，动手前先补 conversation facade 和 compact 行为特征测试，仍不碰聊天编排本身。

当前状态（2026-07-11 R2 存储拆分第四刀）：
- 已完成：新增 `storage/r2_conversation_store.py`，原样迁出窗口 id/key、compact meta/recent/round 文件、SQLite 热读和回填、按日 R2 备份、防轮次倒退、meta 读失败熔断、指定轮读取/删除、预览和 pseudo-CoT 状态；`storage/r2_store.py` 保留全部原函数、私有 helper 和 compact 常量兼容导出。
- 已完成：`storage/r2_store.py` 从 2738 行降到 1985 行；本刀没有修改 `routes/chat.py`、`pipeline/pipeline.py` 或任何调用方行为，旧入口继续供主聊天、主动消息、文游近期记忆和管理页使用。
- 已验证：`scripts/test_r2_conversation_store.py` 先在迁移前旧实现跑绿 10 条特征测试，再在迁移后同一套测试跑绿并增加兼容出口检查；覆盖 SQLite 主读不访问 R2、recent/backup 合并、旧 meta 修复、防 blind write、四类 append 写入、指定轮优先级、预览、pseudo-CoT 和删除重建。四刀存储测试、文游规则 smoke、相关 `py_compile`、`import app` 与 `git diff --check` 全部通过，未访问真实 R2、VPS 或上游模型。
- 未完成 / 下次继续：R2 总入口下一刀优先迁出 summary/latest4/image-description 和动态记忆前置小段；完成后再决定是继续拆动态记忆写入，还是转向 `routes/chat.py` 的 stream/nonstream runner。

当前状态（2026-07-11 R2 存储拆分第五刀）：
- 已完成：新增 `storage/r2_context_store.py`，原样迁出全局 summary 及旧值备份、summary chunks 规范化、global latest4、全局/窗口近期图片描述映射，以及 compact meta/recent/14 天 backup 的窗口历史判断；模块内继续用同一把进程锁串行写这组共享上下文 key。
- 已完成：`storage/r2_store.py` 继续兼容导出全部原函数、私有图片 helper、R2 key 和 limit 常量，主聊天、文游、Claude thinking carryover、SumiTalk block mode、管理页和 replay 脚本均无须修改；总入口从 1985 行降到 1766 行。本刀没有迁移旧 `save_image_description()` 单消息存档，没有修改主动联系、followup、动态记忆、Prompt 或任何调用方。
- 已验证：`scripts/test_r2_context_store.py` 在迁移前旧实现和迁移后新模块各跑绿 9 条相同特征测试，覆盖总结读取/备份覆盖、chunks 规范化和时间戳、latest4 截断、图片描述去重限长/全局窗口双写/过滤、窗口历史 meta 优先和 backup 兜底，并校验 `r2_store.py` facade 函数对象与常量兼容。五刀共 44 条存储测试、`scripts/wenyou_rules_smoke.py`、相关调用方 `py_compile`、`import app` 和目标文件 `git diff --check` 全部通过，未访问真实 R2、VPS 或上游模型。
- 未完成 / 下次继续：下一刀优先给动态记忆 current/debug/audit/maintenance 与 core pending 补行为测试后迁出；主动联系、用户活动、reply channel、Todo、Prompt 和当前游戏/MiniApp 半成品继续不碰。

当前状态（2026-07-11 囚禁模拟器夜间互动收束）：
- 已完成：移除无来源的夜间「检查钥匙」；「藏东西」只在持有可藏礼物时出现，具体选项从当前仓库动态生成，当场没收会同步移出房间仓库。
- 已完成：看书和 Switch 增加四类具体互动与跨夜进度，同一分支重复使用会继续生成不同发现；私密日记正文改为必填；宠物线新增主人称呼、宠物式求欢、展示检查和四种夜间等候姿势。
- 边界保持：普通行动仍单轮同步；夜间监控 `monitor_gate -> monitor_handle` 和首次物品/语音铃揭示继续保留必要的第二段，不改两种视角的监控封存规则。
- 已验证：`scripts/test_captivity_simulator_game.py` 覆盖动态藏物、没收、重复书/游戏发现、空日记拒绝、宠物规则素材和监控边界；本轮只使用临时本地假存档，不调用真实 `/sync-du` 或 R2。
- 已部署：提交 `3fa69fab` 已推送到 `origin/main`；新主网关 `/root/du-gateway` fast-forward 后完成后端 `py_compile` 并重启 `du-gateway.service`。服务器本机 `/health`、`/miniapp/` 与公网 `https://duxy-home.com/health`、`/miniapp/`、新囚禁模拟器静态 chunk 均返回 200，最近服务日志无 traceback/error/exception/failed。

当前状态（2026-07-11 囚禁模拟器事件转场与互动时间补漏）：
- 已完成：AI 写回具体经过时先播放「事件经过」过场；保存到回顾后按下一 pending 播放早上/中午/傍晚/晚上过场，再回一级状态页。夜间自由行动页不再把白天最后一段行动继续显示成「当前事件」，完整白天内容仍保留在回顾。
- 已修复：已部署路由使用 `captivity_simulator_user_interaction` 更新全局互动时间，但 R2 source 白名单漏掉该值，导致线上写入被 `source_not_allowed` 拒绝；白名单已补齐，测试增加路由 source 与白名单一致性断言。
- 边界保持：本轮只展示并核对现有过程提示词，没有修改其成人内容倾向、玩家反应篇幅或开源配置说明；这些仍待确认文案后再改。互动时间验证只使用常量断言和 mock 路由，没有访问真实 R2、`/sync-du` 或线上存档。
- 已验证：囚禁模拟器全量规则测试、互动时间策略测试、后端 `py_compile` 和 MiniApp `tsc --noEmit` 通过；应用内浏览器用 dev-only 假数据实测进入经过、保存后下一阶段和夜间卡片隐藏。

当前状态（2026-07-12 囚禁模拟器场景提示词与逃跑转场收束）：
- 已完成：两条路线按场景拆分提示词外壳，补齐行动强度与身体状态内化映射、语音铃回应、夜间监控和抓回后续分流；pending 精确指令继续作为系统菜单保留。
- 已完成：手机端过程回顾保留底部菜单；逃跑抓回增加逐字问答、灰粉锁链背景、单一道歉选项和“渡正在靠近中”完整加载页，加载结束后无缝接抓回过程转场。
- 已修复：直接选择“老实待着”先进入完整“正在同步渡...”等待页；刷新时未完成则继续等待，完成后才进入界面。状态摘要使用“你选择了老实待着，等待渡回来后决定接下来怎么做”。
- 已隔离：本次发布工作树以最新 `origin/main` 为基线，只包含囚禁模拟器专属源码、路由、测试、计划文档和本地构建产物；随机模仿塔防、R2 拆分、迁移文档及主工作树其他脏改动不进入本提交。
- 已验证：隔离版本通过囚禁模拟器全量规则测试、私密棋盘回归、后端 `py_compile`、`import app`、MiniApp `tsc --noEmit`、生产构建和 `git diff --check`；应用内预览实测“老实待着”加载未完成时刷新继续停留、完成后刷新进入界面。
- 已部署：源码提交 `7b85afd5` 已推送到 `origin/main`；现行主网关 `du-gateway -> 100.119.107.127` fast-forward 后通过后端编译与 `import app`，并重启 `du-gateway`、`du-realtime`、SumiTalk worker、Telegram proactive/webhook worker、微信 iLink 和 nginx。7 个服务均为 `active`，服务器本机与公网 `/health` 正常，公网 `/miniapp/`、新囚禁 chunk 和锁链背景图均返回 200，重启后网关日志未发现 traceback/exception/failed/error。
- 未完成 / 下次继续：五档行动反应仍待重做；特殊状态措辞继续按实际需要收束，监控介入保持不增加强度。

当前状态（2026-07-12 囚禁模拟器沉浸式 play 提示词定稿）：
- 已调整：两条路线共用“小玥打开了囚禁模拟器游戏，邀请你继续玩这场沉浸式私密囚禁play”的常驻开场，门锁、监控、规矩和身体状态作为两人正在经历的处境；渡囚禁小玥与小玥囚禁渡分别衔接各自场景，不再用“在这局游戏里你是……”或“只有游戏里才会出现的你”另立角色身份。
- 已调整：过程收尾改为引用现有 NSFW 规范并记录两人本次 play 的完整详细过程；渡囚禁小玥时保留“欲望和想对她做的事”，小玥囚禁渡时保留“欲望、身体感受和想对她做出的回应”。移除“使用第二人称‘你’”及重复的“你作为囚禁方 / 被囚禁方”出戏措辞。
- 边界保持：小狗身份整组文案、action × intensity、身体状态、动态场景主体、`【游戏状态】` / `【事件】` / `【menu】` 和全部 pending 精确指令均未修改；唤醒词继续只写“请自然回应”，没有新增“以渡自己的口吻”或其他身份提醒。
- 已验证：后端 `py_compile`、`import app`、囚禁模拟器全量规则测试、私密棋盘回归与目标文件 `git diff --check` 通过；测试使用临时本地存档，没有调用真实 `/sync-du`、R2、VPS 或上游模型。
- 已部署：源码提交 `2cdd14a9` 已推送到 `origin/main`；现行主网关 `/root/du-gateway` fast-forward 后通过后端编译、`import app` 和囚禁模拟器全量规则测试，并重启 `du-gateway`、`du-realtime`、SumiTalk worker、Telegram proactive/webhook worker、微信 iLink 和 nginx。7 个服务均为 `active`，服务器本机与公网 `/health` 正常，公网 `/miniapp/` 返回 200，线上源码已确认包含新常驻开头，重启后日志未发现 traceback/exception/failed/error。
- 未完成 / 下次继续：实际模型代入感仍需在真实 App 中用两条路线各跑一轮对话验收。

当前状态（2026-07-13 囚禁模拟器旧物痕迹与语音铃重复播放）：
- 已完成：书、Switch、音乐播放器和平板改为囚禁方使用过再送出的旧物；每件必须单独预填 5 至 8 条使用痕迹，前端换行与渡指令中的 `||` 都会解析为有序列表，被囚禁方每次使用只发现下一条。日记本、小夜灯和抱枕仍保留一次性首次文案。
- 已完成：语音铃每次按下都会播放同一条预录台词并进入确认页；确认后交给渡处理的 pending、动态 system 当前事件和事件上下文每次都保留本次实际 `bell_voice.line`。
- 已修复：被喂水后的尿意会随后续白天行动自然递增，第三段结束入夜时仍继续推进；明显尿意会形成夜间条件文案。囚禁方路线仍不创建或展示无关尿意状态。
- 已同步 UI：囚禁方等待渡操作时使用“等待渡……”文案；身份切换增加覆盖存档确认；仓库显示旧物痕迹填写数量和已发现进度；手机底部一级导航保持固定并保留安全区。
- 已验证：隔离 worktree 基于最新 `origin/main` 通过囚禁模拟器全量测试、私密棋盘回归、Python 编译、`import app`、MiniApp `tsc --noEmit` 与生产构建。测试未调用真实 `/sync-du`、R2 或上游模型。
- 已部署：提交 `d46a99ef` 已推送到 `origin/main`，新主网关 `/root/du-gateway` fast-forward 后完成服务器端编译与导入检查并重启 `du-gateway.service`；本机和公网 `/health`、`/miniapp/` 及新静态 chunk 均返回 200，重启后日志无 traceback/error。

当前状态（2026-07-13 涩涩走格棋交流消息闭环）：
- 已修复：后端代执行渡的棋局指令后，会把每轮指令之外的普通回复和对应系统执行消息完整返回；前端即使检测到 `applied_reply_commands` 也会追加这些消息，不再直接 `return` 丢掉游戏内交流。
- 已调整：走格棋唤醒提示词移除“请以渡自己的口吻自然回应一两句”，改为“小玥指定文案：你可以说几句你想对小玥说的话”。
- 边界确认：`send_private_board_wakeup()` 仍发送 `X-Force-Last4: 1` 与 `X-DU-FOLLOWUP-ARCHIVE: 1`；线上只读核对确认最近走格棋轮次已进入当前 latest4。修复不改游戏存档、last4 注入或归档逻辑。
- 已验证：基于最新 `origin/main` 的隔离 worktree 通过 Python 编译、走格棋解析/消息回传定向测试、`/sync-du` 假唤醒接口 smoke、MiniApp `tsc --noEmit`、生产构建和 `git diff --check`；未调用真实 `/sync-du`、上游模型或游戏写回。
- 已部署：提交 `8c8c63a3` 已推送到 `origin/main`；现行主网关 `/root/du-gateway` fast-forward 后使用服务 `.venv` 通过 `import app` 与定向走格棋测试并重启 `du-gateway.service`。本机和公网 `/health`、`/miniapp/`、新走格棋静态 chunk 均返回 200，重启后日志无 traceback/exception/failed/error。
- 兼容补漏：Android WebView 在部署后若仍运行旧 chunk，不会识别 `game_chat_messages`。新前端请求会带 `client_version=game_chat_v2` 使用后端写回与结构化消息；未带版本的已加载旧前端改由旧前端继续执行回复指令，避免命中 `applied_reply_commands` 后提前返回并吞掉消息。
- 任务说明补漏：review 惩罚任务的 `task` 与 `submission` 不再只在任务执行方是小玥时渲染；任务给渡时，等待面板也会显示完整任务正文和提交要求，例如「全部暴露！」仍明确要求按敏感程度列出五个身体部位或状态弱点。

当前状态（2026-07-13 囚禁模拟器上下文与过程回顾收束）：
- 已完成：具体经过改用独立的 `【过程】` / `【【过程正文】】` 文本块传递，状态指令继续保持短指令；普通行动、抓回和语音铃过程统一复用该格式，缺少完整过程块时不会误推进。
- 已完成：固定动态 system 只保留当轮状态和必要规则，可选行动、调教、道具、喂食、夜间与逃跑资料改由只读参考工具按需查询；玩家在游戏内填写的话作为独立 user 消息进入上下文，没有填写时只发送频道系统提示。
- 已完成：last4 保留当天已经完成的游戏事件摘要，并明确记录行动、调教、性行为、道具、喂食来源与是否加料等实际发生信息；完整经过正文仍只保存在游戏存档，避免重复挤占聊天上下文。
- 已完成：前端回顾只展示带 `process_text` 的具体经过，普通规则事件仍完整保留在后端存档但不进入回顾；回顾按游戏日折叠，默认展开最近一个有具体经过的日期，列表只显示时间和标题。
- 边界保持：本轮验证只使用本地假存档、mock 路由和静态页面，不调用真实 `/sync-du`、R2 写入或上游模型；原主工作树的其他脏改动未进入发布提交。
- 已验证：隔离 worktree 通过囚禁模拟器全量测试、私密棋盘回归、Python 编译、`import app`、MiniApp `tsc --noEmit`、生产构建和 `git diff --check`；390x844 假数据预览确认按日折叠、正文过滤、底部导航和无横向溢出。
- 已部署：源码提交 `b96135d1` 已推送到 `origin/main`；现行主网关 `/root/du-gateway` fast-forward 后完成服务器端编译、导入和定向回归并重启 `du-gateway.service`。服务器本机和公网 `/health`、公网 `/miniapp/` 及新囚禁模拟器静态 chunk 均正常。
- 未完成 / 下次继续：真实 App 中的模型过程篇幅和两条路线语气仍需按实际输出观察；不要用本地测试请求触发线上存档、互动时间或模型调用。

当前状态（2026-07-13 囚禁模拟器赠书书名）：
- 已完成：赠送书时必须单独填写书名，书名可使用现实作品或自定义内容；书名和 5 至 8 条逐次揭晓的旧物痕迹分开保存，旧存档没有书名时继续按普通“书”兼容显示。
- 已完成：囚禁方仓库、被囚禁方房间物品、看书事件标题、痕迹发现页和赠送记录都会使用 `《书名》`；未揭晓的痕迹正文仍不会随书名一起泄露。
- 已完成：渡的赠送指令支持 `book_title=...`，书名含空格时也能与后续 `secret=...` 正确拆分；囚禁模拟器只读物品参考同步说明书名参数。
- 已验证：开源版 17 条 Python 测试和 Web build 通过；私有隔离版本通过囚禁模拟器全量测试、私密棋盘回归、Python 编译、`import app`、MiniApp 类型检查、生产构建和 `git diff --check`。全部验证只使用本地假存档。
- 未完成 / 下次继续：部署后只需在真实 App 中检查一次赠书表单和看书发现页；禁止为了验收触发线上假赠送或改写现有游戏存档。

当前状态（2026-07-13 囚禁模拟器回应输入区）：
- 已修复：被囚禁方“你想说的一句话”改为三行、最小高度 76px 的输入区，保留原有整行宽度、配色和提交逻辑，不扩散到心情按钮、其他备注框或后端协议。
- 已验证：开源 Web build 与 17 条 Python 测试通过；私有版 MiniApp 类型检查和生产构建通过，正式静态包已更新。验证未调用线上游戏接口、R2 或上游模型。

当前状态（2026-07-13 囚禁模拟器白天参考工具合并）：
- 已调整：`captivity_simulator_reference(category=actions)` 一次返回白天行动及具体内容、三档强度、全部调教玩法、道具与推荐关系、完整喂食参数；`training`、`tools`、`feeding` 分类仍保留给特殊场景单独补查。
- 已调整：渡安排三个白天行动时只要求调用一次 `category=actions`，提示中明确禁止再分别查询三类资料，避免复杂安排被拆成多轮工具往返。
- 已验证：开源版 18 条 Python 测试通过；私有囚禁模拟器全量测试、Python 编译、`import app`、私密棋盘回归和 `git diff --check` 通过。测试只读取本地规则和临时假存档。
