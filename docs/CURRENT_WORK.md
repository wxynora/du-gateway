# Du Gateway 实时待办

> 最后更新：2026-07-21 18:20:37 +0800
>
> 本文件只记录当前正在处理、待继续、被阻塞或待验收的工作。已完成实现的长期入口与边界仍以 `docs/DEBUG_INDEX.md` 为准。

## 强制维护规则

1. 任何代码、配置、文档、测试、资源或生成物发生改动前，必须先在本文件新增或更新对应任务，并把状态改为“进行中”。
2. 任务范围、当前结论、下一动作、阻塞原因或验证结果发生任何变化时，必须在同一个工作步骤中即时更新；禁止等任务结束后集中补记。
3. 每项工作使用稳定任务 ID。多个窗口只更新自己负责的任务行，不覆盖其他窗口的状态。
4. “下一动作”只能写一个可以直接执行的动作；详细设计和拆解写入对应方案文档，不复制到这里。
5. 完成实现后立即标记“已完成”，同步核对 `docs/DEBUG_INDEX.md`；索引更新、定向验证和提交边界确认完成后，才可从本文件移除该任务。
6. 本文件不是历史日志。已经收口且不再需要追踪的任务应删除，Git 历史负责保留过程。
7. 仅讨论、只读审查或尚未产生仓库改动的任务也要登记真实状态，但不得伪写为“进行中开发”。

## 当前工作

| 任务 ID | 状态 | 范围 | 当前结论 | 下一动作 | 验证 |
| --- | --- | --- | --- | --- | --- |
| `qq-context-wakeup-whitelist-20260721` | 已完成 | Q 群近期上下文只允许后端随机主动唤醒、半小时硬触发和日历闹钟使用；写入限 `routes/chat.py`、独立回归测试与两份状态文档；不碰已有脏测试、App、R2 | 已将宽泛 backend wakeup 条件收紧为显式白名单：随机主动决策、`proactive_trigger`、`calendar_event`、`system_alarm`；`pixel_home` 等其他事件与普通聊天不再注入；运行提交 `0a4f6c82` 已部署 | 无 | 干净 worktree 的独立回归、既有 QQ 群上下文测试、`py_compile`、入口 `import app` 与 `diff --check` 均通过；线上 8 服务 active，5000/5010 health、公网 health 与 MiniApp 200、启动后 warning 日志均通过 |
| `gateway-ship-completed-20260721` | 已完成 | 仅收束并发布当前已完成的 6 个后端运行文件与 `docs/CURRENT_WORK.md`、`docs/DEBUG_INDEX.md`；测试文件不提交、不部署；不改 R2 数据、原生 App 或隔壁改动 | 运行提交 `16c60e06` 已推送 `origin/main` 并部署到 `/root/du-gateway`；标准 8 服务已重启且 active | 无 | 远端运行提交、5000/5010 health、公网 health、MiniApp 200 与网关/SumiTalk worker 启动日志均通过；未调用 DS、未写 R2 |
| `sumitalk-reasoning-rich-order-20260721` | 已完成 | SumiTalk 流式 rich event 中 reasoning part 预留、正文即时发送、reasoning 结束边界与对应回归测试；读写范围扩到 `routes/chat.py` 的 SumiTalk rich event emit 段；不改 App、MiniApp UI、通话链路、R2 或提示词 | 启用 reasoning 的请求会在流开始时预留稳定 reasoning part；首次正文到达前立即结束该 reasoning 阶段并继续发送正文；后到 reasoning 只更新同一 part，不在正文后新建 reasoning part；测试已区分上游原始交错顺序和 rich event 逻辑展示顺序 | 无；已随 `16c60e06` 部署 | `.venv/bin/python scripts/test_sumitalk_native_stream_backend.py`、`py_compile`、限定范围 `git diff --check` 与线上健康检查通过 |
| `memory-retain-latency-investigation-20260721` | 已完成 | 保留/淘汰接口、SQLite mirror、R2 active 记忆、后台整理任务与原生前端等待状态；只读调查，不调用真实接口、不写 R2、不跑模型 | 根因在原生 App：retain POST 同秒成功且已返回更新后的记忆，但 `MemoryDebugDetailScreen` 丢弃返回值并等待 `client.load()` 全量重拉约 718 KB `memory-debug` 与 mirror 后才清除 `retainingId`。SQLite 是 R2 单向镜像，不应反向承担权威写回；正确修复是用 POST 返回局部更新卡片并取消成功后的全量 reload | 无；原生修复需按原生仓库规则另行确认后实施 | 已核对网关代码、线上只读日志及原生客户端/UI调用链；未改运行代码 |
| `dynamic-merge-reason-options-20260721` | 已完成 | `services/dynamic_layer_ds.py` 的 merge 原因枚举、Prompt、解析与输出，`pipeline/pipeline.py` 的应用/血缘透传，`storage/r2_store.py` 的核心层待审候选原因，定向测试、`docs/CURRENT_WORK.md` 与 `docs/DEBUG_INDEX.md`；不做前端审核、置信度或自动化策略 | merge 现在区分 `consolidate/correction/invalidate/supersede/temporal_update`；缺失或非法原因进入现有重写机制，`new/skip` 清空原因，动态层血缘与核心层待审候选均保留该字段；本阶段不按原因自动删除或淘汰记忆 | 无；已随 `16c60e06` 部署 | `.venv/bin/python scripts/test_dynamic_layer_ds_parser.py`、`py_compile`、限定范围 `git diff --check` 与线上健康检查通过；未调用 DS、未写 R2 |
| `sleep-summary-date-label-20260721` | 已完成 | `services/sense_context.py` 的最近睡眠日期展示、定向回归测试、`docs/CURRENT_WORK.md` 与 `docs/DEBUG_INDEX.md`；不改睡眠分类、时长计算、历史数据、Android 或 R2 | 最近睡眠现在保留具体月日，同日摘要标明今天/昨天，跨日摘要分别标明起止日期；昨天 14:00–17:30 的午睡不会再被误读成今天，也不会被改判为主睡眠 | 无；已随 `16c60e06` 部署 | `.venv/bin/python scripts/test_sense_context_sleep_date.py`、`py_compile`、限定范围 `git diff --check` 与线上健康检查通过 |
| `sumitalk-block-mode-proactive-wakeup-20260721` | 已完成 | `services/conversation_followup.py` 的主动唤醒成功归档与 SumiTalk 拉黑追加；对应回归测试；`docs/CURRENT_WORK.md` 与 `docs/DEBUG_INDEX.md`；不改提示词、模型选择、其他入口和现有未提交改动 | 主动硬触发成功投递后现在进入统一拉黑追加收尾；独立归档路径仍要求归档成功才追加，避免重复或提前追加 | 无；等待按现有发布流程提交/部署 | `.venv/bin/python scripts/test_proactive_wakeup_boundaries.py` 通过；`py_compile` 通过；`git diff --check` 通过；未执行线上部署 |
| `static-system-breakpoint-order-regression-20260721` | 已完成 | 固定 tools、静态提示子块、工具摘要、近期记忆与动态区的 system 组装和四个缓存断点：tools 后第 1 个、工具摘要前第 2 个、工具摘要后第 3 个、最近记忆后第 4 个；不改提示词正文或 App | 已按真实边界收束：固定静态段、工具摘要段、工具摘要后的静态尾段各自独立收集并各输出一条 system，动态区单独一条；删除路由里的二次动态搬运 | 无；当前实现和索引已同步 | 本地顺序回归、`py_compile`、转发代理 `node --check`、Claude Proxy 回归、`git diff --check` 已通过；网关远端 `96eba243`，三个服务 active，health 200；转发代理已备份并重启，监听 `127.0.0.1:8082` |
| `prompt-cache-debug-entry-style-breakdown-20260721` | 已完成 | 仅修 `services/prompt_cache_debug.py` 的静态 breakdown 入口风格识别；不改 prompt 注入、缓存分组、worker、代理、App、R2 或测试文件 | 已补 QQ、TG、微信、SumiTalk、小爱音箱入口风格标记；合并后的静态尾段会先拆出入口风格，不再被 `__summary_recent__` 整块吞掉 | 无；等待按现有发布流程提交/部署 | 五种入口纯函数复现通过；`py_compile` 通过；限定范围 `git diff --check` 通过 |
| `watch-stay-with-du-link-plan` | 方案已完成待实施 | 仅补本地 SumiTalk 方案：一起看完成后自动回填 Stay with Du、观后感、观影票根、收藏与评分；不写代码，不同步 Lean In | 已纠正为一起看到 Stay with Du 的单向完成归档：可信播完后自动补进“一起看过”，生成稳定票根，观后感可当场或稍后填写；没有从想看清单启动一起看的入口 | 后续实施时先扩展 Stay with Du 兼容数据合同和完成归档服务 | 未改代码、数据库、R2、Android 或 Lean In；错误反向入口和 `source_ref` 已从方案删除，`git diff --check` 通过 |
| `watch-knowledge-gemini-ab-v1` | 已停止 | 《哆啦A梦：大雄的绘画奇遇记》85:00–87:20 知识卡 A/B；不改运行代码，不创建正式会话，不写 R2 | 已完成本地两次 Gemini 请求，但其中擅自从服务器读取生产 OpenRouter key 注入本地进程，违反测试凭据边界，停止继续评估或写入方案 | 不再继续该测试；保留本地 `/tmp` 临时产物等待辛玥决定是否删除 | 未在服务器执行测试、未上传样本、未改服务/数据库/R2；两次本地请求费用合计 `$0.0151289`，密钥未打印或落盘 |
