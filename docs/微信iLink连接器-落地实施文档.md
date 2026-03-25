# 微信 iLink 连接器（直连）落地实施文档

目标：把微信个人号（ClawBot/iLink）私聊接入做成**独立常驻进程（connector）**，只负责 iLink 协议收发；对话能力全部复用本仓库网关 `POST /v1/chat/completions`。

## 1. 架构

```
[iLink 云端]  <--HTTP 长轮询/发送-->  [wechat_ilink connector]  <--HTTP-->  [du-gateway Flask]
```

## 2. 连接器必须做的事（最小闭环）

- **扫码登录拿 bot_token**
- **长轮询 getupdates** 收消息，并维护游标 `get_updates_buf`
- **只处理私聊文本**（`item_list.type=1`）
- **窗口隔离**：`window_id = wechat_<from_user_id>`，调用网关时用 `X-Window-Id` 传入
- **调用网关**：`POST /v1/chat/completions`（建议 `stream=false`）
- **回微信**：`sendmessage` 必须带 `context_token`（从入站消息原样带回）

## 3. 运行配置（建议环境变量）

连接器自己的 `.env`（不要和网关 `.env` 混用）：

- `ILINK_BASE_URL=https://ilinkai.weixin.qq.com`
- `WECHAT_ILINK_STATE_FILE=.wechat_ilink_state.json`
- `GATEWAY_BASE_URL=http://127.0.0.1:5000`
- `GATEWAY_CHAT_PATH=/v1/chat/completions`
- `GATEWAY_MODEL=`（可选）
- `WECHAT_MAX_REPLY_CHARS=800`

## 4. 上线前自检

- [ ] 能扫码拿到 `bot_token`（日志脱敏）
- [ ] `get_updates_buf` 能持续更新并落盘（重启不重复刷历史）
- [ ] 只处理私聊文本，不误处理群聊
- [ ] 回复能回到同一会话（`context_token` 生效）
- [ ] 网关异常时不会卡死（能继续下一轮轮询）

# 微信 iLink 连接器（直连）落地实施文档

> 目标：按 `docs/wechat_ilink_direct.md` 的架构，把微信私聊接入做成**独立常驻进程（connector）**，与网关 Flask 主链路隔离。  
> 网关侧不新增“微信专用业务分支”，只复用现有 OpenAI 兼容聊天入口（`/v1/chat/completions` 或等价路径）。

---

## 1. 总体架构与边界

### 1.1 架构图

```
[iLink 云端]  <--HTTP 长轮询/发送-->  [wechat_ilink_connector 进程]  <--HTTP-->  [du-gateway Flask]
```

### 1.2 边界（必须遵守）

- **只处理私聊**：群聊/频道等消息一律丢弃（或仅记录统计，不进入 AI）。
- **协议细节不写死**：iLink 的具体 URL/字段以你手头 iLink 文档为准；本实现只规定职责与接口抽象层。
- **连接器独立进程**：出错应退出，让进程管理器拉起；不要把“无限重试/自动绕过鉴权”写成隐藏逻辑。
- **敏感信息不落库不进仓库**：`bot_token`、登录态、用户消息、模型回复都要严格控制日志与保存位置。

---

## 2. 需要准备的东西（最小集）

### 2.1 iLink 侧（按文档获取）

- `ILINK_BASE_URL`：iLink API 基准地址
- `ILINK_BOT_TOKEN`：登录/扫码获得的 token（或等价凭证）
- 轮询接口（下称“拉取更新”）与发送接口（下称“发送消息”）的路径、方法、字段名

> 注意：iLink 可能需要 `context_token`（或类似字段）来把回复关联回原会话；此字段必须原样带回发送接口。

### 2.2 网关侧（你现有的）

- 网关地址：例如 `http://127.0.0.1:5000`
- chat 路径：例如 `/v1/chat/completions`（与 Telegram 调网关方式保持一致）
- 模型名：按网关支持/你当前默认模型来

---

## 3. 连接器职责清单（落地版）

连接器必须具备以下能力，缺一不可：

### 3.1 登录与凭证管理

- 完成 iLink 登录/扫码流程，拿到 `ILINK_BOT_TOKEN`
- token 存储到：
  - **环境变量**（推荐）或
  - 权限受限文件（例如仅 root 可读的文件），但**禁止**提交到仓库
- 日志中禁止打印完整 token（最多显示前后 3～4 位）

### 3.2 长轮询收消息（只私聊）

- 循环调用“拉取更新”接口（长轮询）
- 解析返回：
  - 只保留**私聊消息**
  - 丢弃非文本（或仅做占位提示），避免多模态先把链路弄复杂

### 3.3 事件去重（必须做）

原因：长轮询重试、网络抖动、服务端重复投递都可能导致同一条消息多次出现。

- 为每条入站消息提取一个稳定 `event_id`（按 iLink 字段）
- 维护一个“最近 N 条 event_id 缓存”（内存 LRU 或持久化小文件皆可）
- 已处理过的 event 直接跳过

### 3.4 window_id 映射（必须稳定）

为每个微信私聊用户映射稳定窗口：

- `window_id = "wechat_" + <对方唯一标识>`
- 唯一标识优先使用：
  1) iLink 返回的 user_id/openid/unionid（按文档）
  2) 若只有会话 id，则使用会话 id，但要保证稳定不变

> 关键：window_id 不稳定 = 记忆串窗 = 后续很难修。

### 3.5 调用网关 chat（建议先非流式）

连接器把微信消息转换为 OpenAI 兼容请求：

- `messages`: 至少包含一条 `{"role":"user","content":"..."}`
- `stream`: **建议先 false**（实现与排障最简单）
- `model`: 可配，或者留空走网关默认（以网关实际逻辑为准）

window_id 的传递方式（按仓库约定二选一）：

- 方式 A：请求头 `X-Window-Id: wechat_xxx`
- 方式 B：请求体带 `window_id: "wechat_xxx"`

> 连接器应尽量对齐 Telegram 调网关的方式，避免出现两套不一致。

### 3.6 解析网关回复并回发微信

非流式建议取：

- `choices[0].message.content`

再调用 iLink 的“发送消息”接口，把回复发回去：

- 必须携带 iLink 要求的 `context_token`（或等价字段）
- 做长度分段（若微信/iLink 有单条长度上限）

---

## 4. 运行形态与进程管理（推荐）

### 4.1 目录建议（不强制）

```
du-gateway/
  connectors/
    wechat_ilink/
      main.py
      ilink_client.py
      gateway_client.py
      dedupe.py
      README.md
```

### 4.2 环境变量建议（连接器进程）

#### iLink

- `ILINK_BASE_URL`
- `ILINK_BOT_TOKEN`
- `ILINK_POLL_TIMEOUT_SECONDS`（默认 30～60）

#### 网关

- `GATEWAY_BASE_URL`（例：`http://127.0.0.1:5000`）
- `GATEWAY_CHAT_PATH`（例：`/v1/chat/completions`）
- `GATEWAY_MODEL`（可选）
- `GATEWAY_STREAM`（建议默认 `0`）

#### 行为控制

- `WECHAT_ILINK_ENABLED`（`1/0`）
- `WECHAT_ILINK_LOG_LEVEL`（`INFO/DEBUG`）
- `WECHAT_ILINK_MAX_REPLY_CHARS`（分段用）

---

## 5. 超时、重试、退避（务实策略）

### 5.1 拉取更新（长轮询）

- 正常情况：按 `poll_timeout` 长轮询，返回就立刻处理下一轮
- 网络异常/5xx：
  - 记录简要错误
  - 指数退避：例如 1s → 2s → 4s → 8s（上限 30s）
  - 连续失败超过阈值（例如 50 次）可选择退出进程，交给 supervisor 拉起

### 5.2 发送消息

- 失败时最多重试 1～2 次（短退避），再失败就记录并放弃该条，避免卡死循环

### 5.3 调网关

- HTTP 超时建议 60～120s（模型慢时）
- 若网关返回 4xx（参数/鉴权问题）：
  - 记录并跳过，不要重试刷爆
- 若 5xx 或网络异常：
  - 可重试 1 次（短退避），再失败告警

---

## 6. 安全与隐私（上线前必须过一遍）

- token/密钥：
  - 仅环境变量或受限文件
  - 日志脱敏
- 用户内容与模型回复：
  - 默认不落盘
  - 若要落盘，仅保存必要的 debug 片段且可一键关闭
- 访问控制：
  - 连接器只连本机网关 `127.0.0.1`（推荐同机部署）
  - 如跨机器，必须走内网或 mTLS/反代鉴权

---

## 7. 自测清单（建议逐条打勾）

### 7.1 连接器基本功能

- [ ] 能成功登录并拿到 `ILINK_BOT_TOKEN`（未在日志中泄露）
- [ ] 长轮询能持续运行（无消息时不狂刷）
- [ ] 仅私聊进入处理，群聊被丢弃
- [ ] 同一条消息重复投递不会导致重复回复（去重生效）

### 7.2 与网关对接

- [ ] `window_id` 稳定（同一用户多次发消息都落在同一 window）
- [ ] 网关返回的回复能正确解析并发送回微信
- [ ] 超时/异常时不会卡死（能继续处理下一条）

### 7.3 压力与边界

- [ ] 连续发 20 条消息不会乱序（至少保证“单会话串行处理”）
- [ ] 超长回复会分段发送（若需要）

---

## 8. 版本演进建议（按收益排序）

1. **先上线非流式**（稳定第一）
2. 再做：
   - 单会话串行队列（避免并发导致上下文错位）
   - 发送分段策略优化
   - 失败告警（例如写到日志/推到 Telegram 运维）
3. 最后才考虑流式（SSE 拼包/增量回传）

