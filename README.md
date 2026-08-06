# 渡の网关（Du Gateway）

面向渡的多入口聊天网关。QQ、Telegram、微信、SumiTalk 与主动唤醒共用同一条聊天、提示词、工具、记忆和归档链路。

当前主产品界面是原生 Android App：`/Users/doraemon/Downloads/sumitalk-android-native`。本仓库内的 MiniApp 主要保留管理、调试、历史兼容和少量 Web 功能页。

## 技术栈

- Python 3 + Flask / Gunicorn
- Cloudflare R2 + 本地 SQLite；事件模式额外使用 Redis / Valkey Streams
- 独立 worker：事件 Outbox dispatcher、SumiTalk/TG interactive worker、主动唤醒
- 可切换的 OpenAI 兼容上游与 Claude OAuth / CPA 适配链
- DeepSeek、向量检索、BM25/rerank 等记忆辅助能力

## 本地启动

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

默认监听 `http://0.0.0.0:5000`。生产环境使用 `scripts/start_gateway_prod.sh` 与 systemd，不直接运行开发服务器。

## 当前聊天链路

1. 接收入口消息并确定真实回复通道、目标和 `X-Window-Id`。
2. 清洗入口附带内容，组装静态提示词、近期上下文、记忆、感知状态和工具。
3. 读取 App 明确保存的 active upstream 与 model；探活、拉模型列表和普通请求都不能自行覆盖该选择。
4. 转发到上游，统一处理 stream、tool loop、reasoning、隐藏标记和渠道发送。
5. 成功回复后归档对话，并异步更新需要演化的记忆和上下文数据。

`X-Window-Id` 只标识对话上下文。当前没有聊天白名单或黑名单分流，所有受支持入口走统一主链路。

## 主要接口

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 聊天代理 | POST | `/v1/chat/completions`、`/chat/completions` |
| 模型列表 | GET | `/v1/models` |
| 健康检查 | GET | `/health` |
| 最近窗口 | GET | `/admin/windows` |
| 状态概览 | GET | `/admin/status` |
| 对话轮次 | GET | `/admin/rounds`、`/admin/windows/<window_id>/rounds` |
| 删除对话轮次 | DELETE | `/admin/rounds/<round_index>`、`/admin/windows/<window_id>/rounds/<round_index>` |
| MiniApp / 原生 App 后端 | 多种 | `/miniapp-api/*` |
| Telegram webhook | POST | `/telegram/webhook/*` |
| 小爱音箱 | 多种 | `/api/xiaoai/*` |
| 共读 | 多种 | `/api/co-read/*` |

路由的完整现状以 `app.py`、`routes/miniapp_api.py` 和 `docs/DEBUG_INDEX.md` 为准。

## 运行边界

- `EVENT_RUNTIME_ENABLED=0` 时，SumiTalk 与 Telegram webhook 继续由原 `scripts/run_sumitalk_chat_worker.py`、`scripts/run_telegram_webhook_worker.py` 消费，不要求 Redis。
- `EVENT_RUNTIME_ENABLED=1` 时，两个入口仍先把完整 job 写入原 SQLite；同一事务额外写 `outbox_events`，再由 `scripts/run_event_dispatcher.py` 投递 `du:interactive`，`scripts/run_interactive_worker.py` 阻塞消费。旧 polling worker 会拒绝启动。
- 主动唤醒、日历和延迟续话由独立调度进程负责，避免 Gunicorn worker 回收时丢状态。
- Notion 运行链已经移除。交换日记、记事本、动态记忆和其他现行数据使用 R2 / SQLite，不再依赖 Notion API。
- 最近窗口仅用于上下文选择和诊断，保存在 `data/recent_windows.json`。

## 事件运行时 Phase 1

本阶段只替换 SumiTalk 与 Telegram webhook 的 SQLite `0.5s` polling worker，不迁移业务数据，也不复制聊天正文到 Redis。统一事件为 `sumitalk.chat_job.created` 和 `telegram.webhook_job.created`，信封版本为 `1`；SQLite job 始终是业务事实源，Redis Stream 只负责即时通知、consumer group、pending 与重新 claim。

- job 与 outbox 同事务提交；Redis 不可用不影响入口可靠落库。
- dispatcher 接收 `du:outbox:wakeup` 即时信号，并每 30 秒兜底扫描；发布失败保留 outbox、记录次数/错误并退避，恢复后自动补发。
- `partition_key` 对 SumiTalk 使用 `window_id`，对 Telegram 使用 chat，保证同会话 FIFO；不同 partition 由线程池并行。
- consumer 先精确 claim SQLite job，业务成功并提交 SQLite ack 后才 `XACK`。重复 Stream 事件在 job 已终态或已删除时成为 no-op，不创建第二个 job。
- stale pending 使用 `XAUTOCLAIM`；超过投递上限写 `dead_letter_events`，低频 reconciler 补旧 pending job 的 outbox、恢复过期 lease，并对长期 pending 安排幂等重投。
- `/health` 始终以 HTTP 存活为主，`live=true`；事件模式的 Redis、心跳、outbox、pending 与 dead letter 通过 `event_runtime` 单独汇总，故障时 `ready=false` 而不是把网关判死。

运行入口与服务模板：

- `runtime/`：事件信封、Outbox、Redis Streams、dispatcher、consumer、reconciler、health 与进程锁。
- `deploy/systemd/du-event-dispatcher.service`
- `deploy/systemd/du-interactive-worker.service`
- 定向验证：`EVENT_RUNTIME_TEST_REDIS_URL=redis://127.0.0.1:16379/0 .venv/bin/python scripts/test_event_runtime_phase1.py`

### 正式切换

以下步骤必须在同一维护窗口执行；不要让部署前已经运行、尚未加载新进程锁的旧 worker 与新 worker 重叠：

1. 保持 `EVENT_RUNTIME_ENABLED=0` 部署代码并执行 `.venv/bin/pip install -r requirements.txt`；准备 Redis / Valkey。
2. 安装两个新 systemd unit 并执行 `systemctl daemon-reload`，暂不启动。
3. 停止并 disable `du-sumitalk-chat-worker.service`、`du-telegram-webhook-worker.service`。
4. 在 `.env` 设置 `EVENT_RUNTIME_ENABLED=1` 与正确的 `REDIS_URL`。
5. restart `du-gateway.service`，enable/start `du-event-dispatcher.service`、`du-interactive-worker.service`。
6. 检查 `/health` 的 `event_runtime.ready`、outbox 最老年龄、Redis pending、dead letter 和两个服务日志；旧 pending job 会由 reconciler 补事件。

### 回滚

1. 停止并 disable 两个新事件服务。
2. 将 `.env` 的 `EVENT_RUNTIME_ENABLED` 改回 `0`，restart `du-gateway.service`。
3. enable/start 两个旧 polling worker，并检查原 SQLite 队列。
4. 不删除 outbox 或 Redis Stream；它们不是业务事实源，保留可供再次启用时幂等恢复。

### QQ 边界与后续风险

QQ OneBot 主入口已经由 NapCat HTTP 回调触发，不是本阶段要消除的 SQLite polling worker。本阶段没有修改 QQ，也没有把它改成轮询；现有 15 秒私聊合并、群聊上下文、引用、@、图片、语音和全局出站串行发送全部保留。

当前仍有明确的非持久化风险：OneBot webhook 在实际处理完成前返回 200；私聊 pending、去重、群历史、连续回复限制和出站队列都是进程内状态，进程退出可能丢失。后续阶段应使用持久化 QQ inbox、Transactional Outbox 和 Timer Runtime 迁移，不能拿本阶段的 SumiTalk/TG consumer 直接套成 QQ polling。

## 存储

- R2 领域模块：`storage/r2_*_store.py`
- R2 兼容聚合入口：`storage/r2_store.py`
- 本地运行数据库：`storage/runtime_sqlite.py`
- 文游数据库：`storage/wenyou_sqlite_store.py`
- SumiTalk 队列：`services/sumitalk_chat_queue.py`
- Telegram 队列：`services/telegram_update_queue.py`
- active upstream / model：`storage/upstream_store.py`

共享 R2 不是测试环境。未明确授权时，调试和验证必须 mock 或隔离所有写入。

## 文档规则

- `docs/DEBUG_INDEX.md`：只登记已经完成、当前仍有效的实现、代码入口、运行边界和验证命令。
- `docs/*方案*.md`、`docs/*plan*.md`：承接尚未落地或仍需迭代的设计。
- 功能变更后必须同步清掉索引里的旧文件、旧路由和旧行为，不能把历史施工记录继续堆在索引里。

## 基础验证

```bash
.venv/bin/python -m py_compile app.py routes/chat.py pipeline/pipeline.py
.venv/bin/python -c "import app"
git diff --check
```

小改动只跑与真实行为相关的定向验证，不默认执行全量测试，也不访问生产 R2。
