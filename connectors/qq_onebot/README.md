# QQ OneBot 连接器（直连 du-gateway）

目标：把 `NapCat / OneBot v11` 的 QQ 私聊和被 @ 的群聊消息，直接转发到本仓库网关的 `POST /v1/chat/completions`，再把回复发回 QQ。

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
- `QQ_BOT_USER_ID`：机器人自己的 QQ 号，默认 `3195570280`
- `QQ_OWNER_USER_ID`：本人 QQ 号，默认 `1336091712`
- `QQ_OWNER_DISPLAY_NAME`：本人展示名，默认 `辛玥`

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

- QQ 私聊直接走共享的 TG 窗口上下文
- QQ 群聊只在机器人被 @ 时回复，群聊上下文同样走共享的 TG 窗口上下文
- 群聊会带 @ 之前最近 10 条群消息作为公开上下文，格式包含群昵称/QQ 号；`QQ_OWNER_USER_ID` 会额外标记为“当前用户/辛玥”
- 群聊不跑动态记忆层
- 同一用户 15 秒内多条消息会合并成一次请求
- 回复按换行优先切分，短段尽量不单独发
- 若网关回复里有 Markdown 图片，会尝试发 QQ 图片
- 若网关回复里有 `<voice>...</voice>`，会调用网关 TTS 接口并发 QQ 语音

## 当前限制

- 当前已处理：
  - QQ 私聊文本
  - QQ 私聊图片（按 OneBot 图片段转成 `image_url` 多模态进网关）
  - QQ 群聊 @ 回复（带最近群消息上下文）
  - 回复侧图片（Markdown 图片）
  - 回复侧语音（`<voice>...</voice>` -> TTS -> QQ 语音）
- 当前还没处理：
  - 入站语音
  - 文件
