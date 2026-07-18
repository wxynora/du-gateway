# Du Gateway 实时待办

> 最后更新：2026-07-18 20:25:50 +0800
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
| `work-queue` | 已完成 | `docs/CURRENT_WORK.md`、`AGENTS.md` | 实时待办本体与项目强制规则均已落地 | 确认提交边界 | 规则一致性、索引边界、`git diff --check` 均通过 |
| `pipeline-cache-order` | 已完成 | `pipeline/pipeline.py`、`docs/DEBUG_INDEX.md` | system 前缀重排实现已完成，准备随本轮已完成改动提交 | 确认提交边界 | marker 顺序定向回归和模块编译通过 |
| `tool-injection-audit` | 已完成 | 注入工具 schema、Pipeline 与执行分发 | 当前无缺失执行端的空壳工具；旧 HTML 预览、Notion、微博工具已退出注入，首批失效分支已清理，剩余仅重复 schema 和旧 MiniApp 文案可单独收束 | 确认提交边界 | 已核对实际 schema、注入条件、执行分发、方案文档与相关 Git 历史 |
| `tool-legacy-cleanup` | 已完成 | `services/chat_tools.py`、`services/amap_mcp_tools.py`、`services/amap_trip_planner.py`、`pipeline/pipeline.py` | 聊天工具 `daily` 分支及 `amap_trip_plan` 旧 schema、分发、执行和专属辅助代码已删除；文游及当前有效工具未改 | 确认提交边界 | 定向 `py_compile`、工具 schema 回归、`import app`、全项目残余引用及 `git diff --check` 均通过 |
| `wenyou-tool-mode` | 已完成 | `routes/chat.py`、`routes/miniapp/settings.py`、`storage/wenyou_mode_store.py`、`pipeline/pipeline.py`、`docs/DEBUG_INDEX.md` | 文游玩家工具已按“无限流游戏模式”条件注入，准备随本轮提交 | 确认提交边界 | 隔离临时存储、GET/PUT 接口及开关前后工具 schema 回归通过 |
| `sumitalk-app-style` | 已完成 | `pipeline/pipeline.py` | SumiTalk App 常驻提示已加入短句、无句号、口语化和自然分段要求，准备随本轮提交 | 确认提交边界 | 常量断言、模块编译和 `import app` 通过 |
| `deploy-main` | 进行中 | 已完成运行代码、相关索引与工作规则 | 定向验证通过；本轮只提交已完成内容，`docs/SumiTalk一起看方案.md` 保持本地且不夹带测试文件 | 提交并推送 `main` | 待远端拉取、全相关服务重启与健康检查 |
| `watch-together-spec` | 待提交 | `docs/SumiTalk一起看方案.md` | 方案共 1017 行，结构完整，无 `TODO`、`FIXME` 或临时占位 | 确认提交边界后纳入版本库 | 已检查结构与工作区状态 |
