# 交换日记 App 原生化当前方案

当前状态（2026-06-27）：交换日记已经迁入 App/R2。R2 是正本，VPS 和本地 SQLite 只是热镜像；临时迁移产物已删除，不再保留含正文的迁移证据文件。

## 当前边界

1. 交换日记不再依赖 Notion 作为正本。
2. App 负责展示、编辑、新建、删除和评论。
3. 渡通过 `exchange_diary_*` 工具读写和评论交换日记。
4. `NOTION_TOOLS_ENABLED` 只控制通用 Notion runtime 工具，不影响交换日记、记事本、Stay with Du、气泡等网关原生工具。
5. 通用 Notion 检索、日程、小本本、卧室原文等链路仍按各自用途保留，后续是否删除单独处理。

## 数据结构

R2 key：

```text
exchange_diary/v1/manifest.json
exchange_diary/v1/months/YYYY-MM.json
exchange_diary/v1/entries/YYYY/MM/<entry_id>.json
```

职责：

1. `manifest.json`：版本、月份列表、总数、最新摘要、更新时间。
2. `months/YYYY-MM.json`：当月列表摘要，不放长正文。
3. `entries/YYYY/MM/<entry_id>.json`：单条完整正文、评论、来源信息、删除标记。

SQLite：

1. `runtime_state.sqlite3.exchange_diary_entries` 是热镜像。
2. 写入时先同步 R2，R2 成功后再写 SQLite。
3. SQLite 丢失时，可从 R2 最近月份冷启动回填。
4. 不部署本地 `data/*.sqlite3` 到 VPS。
5. 带 `client_request_id` 的新建和评论使用稳定 id，R2 局部写成功后重试不会随机生成重复对象。

## App 页面

入口在 MiniApp「日常」里的「交换日记」。

页面行为：

1. 默认打开「渡的Diary」。
2. 可切换「我的Diary」。
3. 列表是纸条时间线，只显示标题、emoji 和时间。
4. 点开纸条进入详情，详情展示正文和评论。
5. 右下角加号只新增「我的Diary」。
6. 新建、编辑、删除、评论都走后端接口，失败时保留当前输入，不假装成功。

## MiniApp API

接口：

```text
GET    /miniapp-api/exchange-diary
POST   /miniapp-api/exchange-diary
GET    /miniapp-api/exchange-diary/<entry_id>
PATCH  /miniapp-api/exchange-diary/<entry_id>
DELETE /miniapp-api/exchange-diary/<entry_id>
POST   /miniapp-api/exchange-diary/<entry_id>/comments
```

约定：

1. 列表接口默认返回 compact 列表。
2. 详情接口返回完整正文和评论。
3. 评论支持 `reply_to_comment_id`；不填就是直接评论日记，填了就是回复那条评论。
4. 删除为软删除；普通 App API 不接受 `include_deleted` 读取已删除条目。
5. App 新建和评论的作者由后端强制为 `xy`；渡写入和评论走 `exchange_diary_*` 工具。

## 渡可用工具

工具名：

```text
exchange_diary_create
exchange_diary_list
exchange_diary_read
exchange_diary_comment_create
```

`exchange_diary_list`：

1. `author` 不传或传空：按时间混合查看双方日记。
2. `author=du`：只看渡写的。
3. `author=xy`：只看辛玥写的。
4. 默认 `limit=5`，最大 `20`。
5. 返回正文、最近评论和 comment id，减少二次工具调用。

`exchange_diary_comment_create`：

1. `entry_id` 必填。
2. `content` 必填。
3. `reply_to_comment_id` 可选。
4. 默认作者为 `du`。

## 已完成迁移结果

历史交换日记已迁入 R2/SQLite：

1. 总数 123 条。
2. `source_notion_page_id` 去重 123。
3. 月份分布：2026-06 30 条、2026-05 30 条、2026-04 37 条、2026-03 26 条。
4. 本地热索引校验：`notion_import=123`、`distinct_source_notion_page_id=123`。

部署时不要再迁移数据。只要 R2 正本完整，VPS SQLite 可在首次列表请求时从 R2 回填。

## 部署注意

1. 部署代码和 `miniapp_static` 静态产物。
2. 重启 `du-gateway.service`。
3. 如果 SumiTalk App 聊天走独立 worker，并且工具调用路径有改动，也要重启 `du-sumitalk-chat-worker.service`。
4. 不部署本地 `data/*.sqlite3`。

检查：

```bash
curl -sS http://127.0.0.1:5000/health
curl -I https://duxy-home.com/miniapp/
ls -1 /root/du-gateway/miniapp_static/assets/ExchangeDiaryTab-*.js
```

可选只读检查：

```bash
sqlite3 /root/du-gateway/data/runtime_state.sqlite3 \
  "select count(*), count(distinct source_notion_page_id) from exchange_diary_entries;"
```

## 验证清单

1. App 列表能看到双方历史日记。
2. App 新建「我的Diary」成功。
3. App 编辑、删除、评论成功。
4. 渡调用 `exchange_diary_list` 默认能看到混合时间线。
5. 渡调用 `exchange_diary_create` 能写入新日记。
6. 渡调用 `exchange_diary_comment_create` 能评论或回复评论。
7. 随机唤醒选择写日记时调用 `exchange_diary_create`。
8. dashboard 只把 `exchange_diary_create` 摘要成“写了日记”，读取和评论工具不展示。
9. 关闭通用 Notion 工具注入时，`exchange_diary_*` 仍可注入。

## 当前残留

本轮不删除这些，因为它们不属于交换日记链路：

1. 通用 Notion 检索。
2. Notion 日程。
3. Notion 小本本。
4. 卧室原文写入。
5. 归档与核心缓存同步里的 Notion 相关代码。

如果以后确定这些也不用，再单独做一轮删除，先全项目 `rg` 引用，再删定义端。
