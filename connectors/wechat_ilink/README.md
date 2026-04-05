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
- 根目录 `.env` 里的 `TELEGRAM_PROACTIVE_TARGET_USER_ID`

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

### 4) 行为（对齐 Telegram 的点）

- **15 秒输入聚合**：同一用户 15 秒内多条消息会合并成一次请求（可用 `WECHAT_INPUT_IDLE_SECONDS` 调）
- **超过阈值立即提交**：单条/累计超过 200 字就立即提交（`WECHAT_INPUT_IMMEDIATE_CHARS`）
- **输出切分**：优先按换行分条；每条超过 100 字再拆（`WECHAT_OUTPUT_CHUNK_CHARS`）
- **不保留微信本地上下文缓存**：直接走共享的 TG 窗口上下文，不在微信入口重复补最近几轮
- **失败兜底**：网关失败会保留 pending，下次再试，并最多每 30 秒提示一次
- **统一聊天 system**：不输出脑内 OS、不带小本本提示，不区分消息来源
- **支持回语音**：若网关回复里带 `<voice>...</voice>`，微信连接器会调用网关 TTS 接口生成音频并回发语音
- **正在输入中**：网关处理期间会发送 iLink `sendtyping`（可在 `.env` 调开关/间隔/次数）

## 当前限制

- 当前已处理：
  - 文本（`item_list.type=1`）
  - 回复侧语音（`<voice>...</voice>` -> TTS -> 语音消息）
- 当前还没处理：
  - 微信入站语音下载/解密
  - 图片
  - 文件
  - 视频

## typing 配置（可选）

- `WECHAT_TYPING_ENABLED=1`
- `WECHAT_TYPING_FIRST_DELAY_MS=1000`
- `WECHAT_TYPING_INTERVAL_MS=4000`
- `WECHAT_TYPING_MAX_SIGNALS=3`
