# QQ OneBot 连接器（直连 du-gateway）

目标：把 `NapCat / OneBot v11` 的 QQ 私聊文本消息，直接转发到本仓库网关的 `POST /v1/chat/completions`，再把回复发回 QQ。

## 云服务器傻瓜版步骤

### 1) 安装

```bash
cd /root/du-gateway/connectors/qq_onebot
npm install
cp .env.example .env
```

编辑 `.env`，至少确认：

- `QQ_ONEBOT_PORT`
- `QQ_ONEBOT_API_BASE`
- `GATEWAY_BASE_URL`
- `GATEWAY_CHAT_PATH`
- 根目录 `.env` 里的 `TELEGRAM_PROACTIVE_TARGET_USER_ID`

### 2) 启动

```bash
cd /root/du-gateway/connectors/qq_onebot
npm start
```

### 3) NapCat / OneBot 配置

把 HTTP 上报地址指到：

```txt
http://127.0.0.1:8092/onebot/events
```

如果你配置了 `QQ_ONEBOT_ACCESS_TOKEN`，NapCat 上报时也要带同一个 token。

### 4) 当前行为

- 只处理 QQ 私聊文本
- 不保留 QQ 本地上下文缓存，直接走共享的 TG 窗口上下文
- 同一用户 15 秒内多条消息会合并成一次请求
- 回复按换行优先切分，短段尽量不单独发
- 不区分消息来源
- 若网关回复里有 Markdown 图片，会尝试发 QQ 图片
- 若网关回复里有 `<voice>...</voice>`，会调用网关 TTS 接口并发 QQ 语音

## 当前限制

- 当前已处理：
  - QQ 私聊文本
  - QQ 私聊图片（按 OneBot 图片段转成 `image_url` 多模态进网关）
  - 回复侧图片（Markdown 图片）
  - 回复侧语音（`<voice>...</voice>` -> TTS -> QQ 语音）
- 当前还没处理：
  - 群聊
  - 入站语音
  - 文件
