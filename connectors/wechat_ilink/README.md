# 微信 iLink 连接器（直连 du-gateway）

目标：把微信个人号（ClawBot/iLink）的**私聊文本**消息，直接转发到本仓库网关的 `POST /v1/chat/completions`，再把回复发回微信。

## 云服务器傻瓜版步骤

### 1) 安装

```bash
cd /root/du-gateway/connectors/wechat_ilink
npm install
cp .env.example .env
```

编辑 `.env`，至少确认：

- `GATEWAY_BASE_URL`
- `GATEWAY_CHAT_PATH`（默认 `/v1/chat/completions`）

### 2) 第一次扫码登录（拿 bot_token）

```bash
cd /root/du-gateway/connectors/wechat_ilink
npm run login
```

成功后会生成状态文件（默认 `.wechat_ilink_state.json`），包含：
- `bot_token`
- `get_updates_buf`

注意：这是敏感信息，不要提交到 git。

### 3) 正常运行

```bash
cd /root/du-gateway/connectors/wechat_ilink
npm start
```

### 4) 验收

在微信里给 ClawBot 发一句纯文本（例如“你好”），应能收到来自网关的回复。

## 目前限制

- 仅处理文本（`item_list.type=1`）
- 暂不支持图片/语音/文件（后续做会涉及 CDN + AES 加解密）

# 微信 iLink 连接器（直连 du-gateway）

目标：把微信个人号（ClawBot/iLink）的**私聊文本**消息，直接转发到本仓库网关的 `POST /v1/chat/completions`，再把回复发回微信。

## 你需要准备什么（傻瓜版）

- 云服务器能跑你的网关（`python app.py` 已启动）
- 云服务器能访问 `https://ilinkai.weixin.qq.com`
- 手机微信里已经能看到并启用 **ClawBot** 插件
- 云服务器有 Node.js（建议 Node >= 22）

## 一次性安装

在服务器上：

```bash
cd /root/du-gateway/connectors/wechat_ilink
npm install
cp .env.example .env
```

编辑 `.env`，至少确认：

- `GATEWAY_BASE_URL`
- `GATEWAY_CHAT_PATH`（默认 `/v1/chat/completions`）

## 第一次登录（扫码）

```bash
cd /root/du-gateway/connectors/wechat_ilink
npm run login
```

终端会打印二维码（或二维码链接），用微信扫码确认绑定。

成功后会在 `WECHAT_ILINK_STATE_FILE` 写入：

- `bot_token`
- `get_updates_buf`

> 注意：这些是敏感信息，不要提交到 git。

## 正常运行

```bash
cd /root/du-gateway/connectors/wechat_ilink
npm start
```

## 最小验证方法

1. 给你的微信 ClawBot 对话发一句纯文本（例如 “你好”）
2. 连接器会调用网关 `/v1/chat/completions`
3. 你应能在微信里收到网关生成的回复

## 目前的限制（按阶段逐步加）

- 只做 **私聊文本**（`item_list.type=1`）
- 先不做图片/语音/文件（后续要做会涉及 CDN + AES 加解密）

