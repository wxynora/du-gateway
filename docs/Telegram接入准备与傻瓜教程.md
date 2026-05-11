# Telegram 接入：需要准备的东西 + 傻瓜版教程

## 一、需要你准备好的东西（清单）

| 序号 | 东西 | 说明 | 必须？ |
|------|------|------|--------|
| 1 | **Telegram 账号** | 用来和 Bot 聊天、收渡的回复 | ✅ 必须 |
| 2 | **Bot Token** | 在 Telegram 里找 @BotFather 创建 Bot 后拿到的一串密钥 | ✅ 必须 |
| 3 | **能访问 Telegram 的网络** | 国内需🪜，否则收不到消息 | ✅ 必须 |
| 4 | **网关已能正常跑** | 本机或云服务器上 `python app.py` 能起来，R2/Notion 等按你现有配置 | ✅ 必须 |
| 5 | **.env 里已有网关相关配置** | 如 TARGET_AI_URL、TARGET_AI_API_KEY、R2、DeepSeek 等（你平时 RikkaHub 能用就行） | ✅ 必须 |
| 6 | **Python 环境** | 项目能跑起来的那套（含 `requests`） | ✅ 必须 |
| 7 | **TELEGRAM_GATEWAY_URL** | Bot 调网关的地址：Bot 和网关同机填 `http://127.0.0.1:5000`；公网访问填你的域名，例如 `https://duxy-home.com` | ✅ 必须 |
| 8 | **TELEGRAM_CHAT_MODEL（可选）** | 想让渡用哪个模型；不填则用 GATEWAY_MODELS 第一个或 gpt-4 | 可选 |

**总结：你必须准备的就是「一个 Telegram 账号 + 一个 Bot Token + 能上 Telegram 的网络 + 已经能跑的网关 + .env 里填好 TELEGRAM 相关项」。**

---

## 二、傻瓜版教程（一步步做）

### 第一步：在 Telegram 里创建一个 Bot，拿到 Token

1. 打开 Telegram（手机或电脑都行）。
2. 在搜索框输入 **@BotFather**，进入官方 Bot。
3. 发送：`/newbot`。
4. 按提示操作：
   - 给 Bot 起个名字（例如：`渡的小助手`）。
   - 再起一个**用户名**，必须以 `bot` 结尾，例如：`du_gateway_bot`（若被占用就换一个，如 `du_gateway_xxx_bot`）。
5. 创建成功后，BotFather 会发给你**一串 Token**，长得像：  
   `7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
6. **复制这串 Token**，后面要贴到 `.env` 里，不要发给别人。

---

### 第二步：在项目里配置 .env

1. 打开项目根目录下的 **`.env`** 文件（没有就复制 `.env.example` 为 `.env`）。
2. 在文件末尾加上或修改这几行（把 `你的BotToken` 换成第一步拿到的 Token）：

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_GATEWAY_URL=http://127.0.0.1:5000
```

说明：

- **本机测试**：网关和 Bot 都在你电脑上跑，就填 `http://127.0.0.1:5000`（端口要和 `app.py` 里的一致，默认 5000）。
- **Bot 和网关在同一台云服务器**：填 `http://127.0.0.1:5000`。
- **Bot 在别的机器、要调公网网关**：填你的网关公网地址，例如 `https://duxy-home.com`，不要末尾斜杠。

3. 保存 `.env`。

---

### 第三步：先启动网关

1. 在项目根目录打开终端（PowerShell 或 CMD）。
2. 执行：

```bash
cd d:\du-gateway
python app.py
```

3. 看到类似 `Running on http://0.0.0.0:5000` 就说明网关已起来。
4. **保持这个窗口开着**，网关要一直运行。

---

### 第四步：设置 Telegram Webhook（替代轮询）

1. 确保你的网关已部署到公网 HTTPS 域名（例如 `https://duxy-home.com`），且能访问到 `https://duxy-home.com/health`。
2. 在服务器上用 Bot Token 调 Telegram API 设置 Webhook：

```bash
curl -sS "https://api.telegram.org/bot<你的BOT_TOKEN>/setWebhook" \
  -d "url=https://duxy-home.com/telegram/webhook" \
  -d "drop_pending_updates=true"
```

3. 设置成功后，Telegram 会把新消息推送到你的网关，不需要轮询进程。

---

### 第五步：在 Telegram 里和渡聊天

1. 打开 Telegram，在搜索框输入你第一步创建的 **Bot 用户名**（例如 `@du_gateway_bot`）。
2. 点进和 Bot 的对话，点 **Start** 或发一条任意文字，例如：`你好`。
3. 稍等几秒，渡的回复会从网关经 Bot 发回 Telegram。

若一直没回复：

- 看 **运行 Bot 的那个终端** 有没有报错（例如连不上网关、网关返回非 200）。
- 确认 **网关那个终端** 没有报错。
- 确认 `.env` 里 `TELEGRAM_GATEWAY_URL` 和实际网关地址、端口一致。

---

## 三、常见问题（FAQ）

**Q：国内收不到 Telegram 消息？**  
A：需要能访问 Telegram 的网络（🪜），否则 Bot 拉不到更新。

**Q：Bot 报错「暂时没连上渡」？**  
A：多半是 Bot 连不上网关。检查：① 网关是否已启动；② `TELEGRAM_GATEWAY_URL` 是否填对（本机用 `http://127.0.0.1:5000`）；③ 若网关在云服务器，Bot 在本地，要把 URL 改成云服务器公网地址。

**Q：想用指定模型？**  
A：在 `.env` 里加一行，例如：`TELEGRAM_CHAT_MODEL=claude-3-5-sonnet-20241022`（填你网关支持的模型名）。  
补充：如果你的中转站**只允许特定模型名**或**多中转站模型名不一致**，则建议显式配置 `TELEGRAM_CHAT_MODEL`；否则 Bot 可能会用兜底模型名导致上游 403。

**Q：还需要跑 du-telegram-bot（轮询）吗？**  
A：不需要轮询。但 Webhook 现在分两段：网关服务只负责接收并写入 `data/telegram_webhook_queue.sqlite3`，还需要常驻 `python scripts/run_telegram_webhook_worker.py` 来消费队列、做输入聚合并回复；主动消息调度（du-telegram-proactive）可按需保留。

**Q：Token 泄露了怎么办？**  
A：去 @BotFather 里用 `/mybots` 找到你的 Bot，进 API Token 重新生成一个新 Token，再把 `.env` 里的旧 Token 换掉。

---

## 四、准备清单（可打印/勾选）

- [ ] 已有 Telegram 账号
- [ ] 已在 @BotFather 创建 Bot 并拿到 Token
- [ ] 网络能访问 Telegram
- [ ] 网关在本机/服务器能正常跑（`python app.py`）
- [ ] Webhook worker 已常驻运行（`python scripts/run_telegram_webhook_worker.py`）
- [ ] `.env` 已配置：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_GATEWAY_URL`
- [ ] 已为 Bot 设置 Webhook 到 `https://你的域名/telegram/webhook`
- [ ] 在 Telegram 里给 Bot 发消息，能收到渡的回复

全部勾选 = 接入完成。
