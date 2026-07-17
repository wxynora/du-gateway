# 渡の网关（Du Gateway）

面向渡的多入口聊天网关。QQ、Telegram、微信、SumiTalk 与主动唤醒共用同一条聊天、提示词、工具、记忆和归档链路。

当前主产品界面是原生 Android App：`/Users/doraemon/Downloads/sumitalk-android-native`。本仓库内的 MiniApp 主要保留管理、调试、历史兼容和少量 Web 功能页。

## 技术栈

- Python 3 + Flask / Gunicorn
- Cloudflare R2 + 本地 SQLite
- 独立队列 worker：SumiTalk 长回复、Telegram webhook、主动唤醒
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

- SumiTalk 消息先进入持久队列，由 `scripts/run_sumitalk_chat_worker.py` 独立消费；后端不自动重试失败 job。
- Telegram webhook 只负责快速入队，聚合与回复由 `scripts/run_telegram_webhook_worker.py` 消费。
- 主动唤醒、日历和延迟续话由独立调度进程负责，避免 Gunicorn worker 回收时丢状态。
- Notion 运行链已经移除。交换日记、记事本、动态记忆和其他现行数据使用 R2 / SQLite，不再依赖 Notion API。
- 最近窗口仅用于上下文选择和诊断，保存在 `data/recent_windows.json`。

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
