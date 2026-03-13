# 渡の网关（Du Gateway）

为 AI 聊天应用搭建的记忆系统网关：白名单、数据清洗、窗口总结、R2 存档、Notion 读写。

## 技术栈

- Python 3 + Flask
- Cloudflare R2（S3 兼容）
- Notion API
- DeepSeek（每 4 轮窗口总结）
- 可选：便宜图像 AI（图片转文字描述存 R2）

## 环境准备

1. 复制环境变量并填写：

```bash
cp .env.example .env
# 编辑 .env，填入 TARGET_AI_URL、TARGET_AI_API_KEY、R2 与（可选）Notion、DeepSeek、图像描述 API
```

2. 安装依赖（或直接用下面一键启动，会自动建虚拟环境并安装）：

```bash
pip install -r requirements.txt
```

3. 启动：

**方式一（推荐，本地不折腾环境）**：双击运行项目里的 **`start.bat`**（或在 Git Bash 里执行 `./start.sh`）。首次会创建 `.venv` 并安装依赖，之后每次直接启动网关，不用再配环境。

**方式二**：

```bash
python app.py
# 或
flask run
```

默认监听 `http://0.0.0.0:5000`。

## 请求流水线

1. **窗口识别 + 白名单**：请求头 `X-Window-Id` 为窗口 ID；在白名单内走完整流程，否则只转发。
2. **两条流清洗**：发给渡 = 只清 Rikka 预设 + 表情包→文字；存 R2 = 完整清洗（Rikka + 表情包→文字 + 图片→占位符，描述在 images/）。表情包统一 `(表情包:xxx)`→`[表情]`。
3. **新窗口**：若该窗口在 R2 无历史，自动注入 R2 中「最新四轮」原文。
4. **记忆注入**：从 R2 读全局总结 + 动态层记忆（关键词匹配 + 权重 Top N），注入 system 末尾。
5. **转发**：请求转发到 `TARGET_AI_URL`。
6. **存档前初筛**：渡的回复若失败（过短或含错误关键词）→ **整轮作废**（老婆问+渡的回复都不存 R2），不触发总结。
7. **存档**：通过初筛则存「完整清洗」版到 R2，且每 4 轮异步触发 DeepSeek 总结；总结为全局一份，存 `global/summary.txt`。

## 白名单

- **A. 一键加当前窗口**：请求时带请求头 `X-Add-To-Whitelist: true`，网关会用本请求的 `X-Window-Id` 加入白名单。
- **B. 管理端**：`GET /admin/windows` 看最近窗口，`POST /admin/whitelist` 传 `{"window_id":"xxx"}` 加入，`DELETE /admin/whitelist/<window_id>` 移除。

## 接口一览

| 用途       | 方法 | 路径 |
|------------|------|------|
| 聊天代理   | POST | `/v1/chat/completions`、`/chat/completions` |
| 健康检查   | GET  | `/health` |
| 最近窗口   | GET  | `/admin/windows` |
| 白名单列表 | GET  | `/admin/whitelist` |
| 加白名单   | POST | `/admin/whitelist` |
| 删白名单   | DELETE | `/admin/whitelist/<window_id>` |
| 删除某一轮对话 | DELETE | `/admin/windows/<window_id>/rounds/<round_index>` |
| Notion 搜索 | POST | `/notion/search` |
| Notion 读页面 | GET | `/notion/pages/<page_id>` |
| Notion 读子块 | GET | `/notion/blocks/<block_id>/children` |
| Notion 建页面 | POST | `/notion/pages` |
| Notion 更新页面 | PATCH | `/notion/pages/<page_id>` |
| Notion 更新/删除块 | PATCH/DELETE | `/notion/blocks/<block_id>` |

## 如何测试

### 1. 只转发（不在白名单）

- 不带头或带任意 `X-Window-Id`，且该 ID 不在白名单：
  - `curl -X POST http://localhost:5000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'`
  - 应直接转发到 `TARGET_AI_URL`，且不写 R2。

### 2. 白名单 A：一键加入

- 请求头带 `X-Window-Id: my-window-1` 和 `X-Add-To-Whitelist: true`，再发一条聊天请求。
- 之后同一 `X-Window-Id` 的请求应走完整流程（清洗、新窗口注入、总结注入、存档）。

### 3. 白名单 B：管理端

- `GET http://localhost:5000/admin/windows`：看最近窗口及是否已在白名单。
- `POST http://localhost:5000/admin/whitelist`，body `{"window_id":"my-window-1"}`：加入白名单。
- `DELETE http://localhost:5000/admin/whitelist/my-window-1`：移出白名单。

### 4. 新窗口注入

- 用一个新的 `X-Window-Id`（从未出现过），且先让某个已存在窗口有过对话并写入 R2。
- 新窗口第一次请求应能在 system 中看到「注入的近期对话上下文」。

### 5. 每 4 轮总结（全局共享）

- 白名单内任意窗口连续对话 4 轮后，会触发 DeepSeek 用该窗口最近 4 轮更新**全局总结**，写回 R2 的 `global/summary.txt`；所有白名单窗口请求时都会注入这份总结（需配置 `DEEPSEEK_API_KEY`）。

### 6. Notion

- 配置 `NOTION_API_KEY` 后，用 `POST /notion/search`、`GET /notion/pages/<id>` 等按 Notion API 格式传参测试读写。

### 7. 图片描述存 R2

- 配置 `IMAGE_DESC_API_URL` 和 `IMAGE_DESC_API_KEY` 后，发带图片的 message（如 `image_url` 为 data URL），检查 R2 对应窗口下 `images/` 是否出现描述文件。

### 8. 失败对话初筛

- 助手端返回的回复若长度 &lt; 10 字，或包含「error」「出错」「失败」「超时」「抱歉，我无法」等关键词，则不会写入 R2、不触发总结。可通过 `FAILED_RESPONSE_MIN_LENGTH`、`FAILED_RESPONSE_ERROR_KEYWORDS` 调整。

### 9. 动态层注入

- R2 中 `dynamic_memory/current.json` 存动态记忆列表。每轮请求前按「话题匹配度 + 权重」排序，在动态层 token 预算内尽量多条注入（不固定条数）。仅 7 天内有 `last_mentioned` 的记忆会参与。若尚无该文件或列表为空，则不注入。

## 记忆注入 token 上限

- 默认 3000 token（总结+动态层合计），可在 `.env` 设 `MEMORY_INJECTION_MAX_TOKENS`（建议 2500–4000）。
- 总结占 60%、动态层 40%，可设 `MEMORY_SUMMARY_TOKEN_RATIO` 调整。

## 多窗口写 R2

- 各窗口的 `windows/<id>/conversation.json` 独立，**不会冲突**。
- 全局 key（`global/summary.txt`、`global/latest_4_rounds.json`、`dynamic_memory/current.json`）多窗口同时写时使用**进程内锁**，单进程下不会互相覆盖；多进程/多机部署需自行加外部锁（如 Redis）。

## 日志（方便排查）

- 控制台输出格式：`时间 [模块名] 级别: 消息`。
- 模块名对应：`[R2]` 存读 R2、`[Pipeline]` 管道、`[Chat]` 转发、`[DeepSeek]` 总结；出错会带 `error=` 和堆栈。
- 日志级别：`.env` 中 `LOG_LEVEL=INFO`（默认），调试可改为 `DEBUG`。

## 表情包对照表（老婆可编辑）

- 文件：`data/emoji_mapping.json`，JSON 格式 `"代码": "描述"`，保存即生效，无需重启。
- 详见 `docs/老婆使用说明.md`。

## 架构与文档对照

与 `docs/记忆系统需求文档-v1.1-最终版.md` 对齐：

- **实时层**：`global/summary.txt`，每 4 轮 DS 总结成「渡的回忆」（第一人称、详细版）。
- **原文存档**：主存 `windows/<id>/conversation.json`，备份 `conversations/YYYY-MM-DD/window_<id>.json`。
- **动态层**：`dynamic_memory/current.json`，读写与请求前注入已实现；演化走 DS 接口（入参：当前轮+现有记忆；出参：是否重要+演化后记忆），占位见 `services/dynamic_layer_ds.py`，约定见文档八.5。
- **核心缓存层**：`core_cache/pending.json`，R2 读写已占位，每周筛选进 Notion 待实现。

## 数据与备份

- 白名单与最近窗口在项目下 `data/whitelist.json`、`data/recent_windows.json`；改代码前可备份 `data/` 目录。
- R2 键：`windows/<window_id>/conversation.json`、`conversations/YYYY-MM-DD/window_<id>.json`、`images/<msg_id>.txt`；全局 `global/summary.txt`、`global/latest_4_rounds.json`；动态层 `dynamic_memory/current.json`；核心缓存 `core_cache/pending.json`。
