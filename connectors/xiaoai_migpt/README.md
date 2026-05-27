# 小爱音箱 MiGPT Runner

这是给 Mac / Docker 跑的 MiGPT Next runner。

它只做桥接：

```text
小爱音箱 -> MiGPT Next -> du-gateway /api/xiaoai/message -> 小爱播放 audio_url
渡调用 xiaoai_speak -> du-gateway 播放队列 -> MiGPT Next -> 小爱播放 audio_url
```

控制面板在 MiniApp：

```text
工具 -> 小爱音箱
```

面板里的启用开关、入口词、退出词会被 runner 定时拉取。

## 准备

确认小爱音箱已经在米家 / 小爱音箱 App 里绑定并在线。

建议把音箱名称改成稳定名字，例如：

```text
卧室小爱
```

## 配置

```bash
cd connectors/xiaoai_migpt
cp .env.example .env
```

编辑 `.env`：

```bash
XIAOMI_USER_ID=你的小米账号
XIAOMI_PASSWORD=你的小米密码
XIAOAI_DID=卧室小爱
XIAOAI_SPEAKER=卧室小爱

DU_GATEWAY_URL=https://你的网关域名
XIAOAI_GATEWAY_TOKEN=
DU_WINDOW_ID=
XIAOAI_ACTION_POLL_MS=3000
```

`XIAOAI_GATEWAY_TOKEN` 是可选项。现在网关没配就留空，不需要自己找一个“已有 token”。

只有当你以后在 `du-gateway/.env` 里主动加了：

```bash
XIAOAI_GATEWAY_TOKEN=一串随机字符
```

runner 的 `.env` 才需要填同一串。

`DU_WINDOW_ID` 也默认留空。网关会用现有 `TELEGRAM_PROACTIVE_TARGET_USER_ID` 自动推断 `tg_...`，不用重复填 TG 用户 ID。

如果小米账号登录触发安全验证，可以改用：

```bash
XIAOMI_PASS_TOKEN=...
```

有 `XIAOMI_PASS_TOKEN` 时，可以不填 `XIAOMI_PASSWORD`。

## 启动

Mac 先打开 Docker Desktop，然后：

```bash
cd connectors/xiaoai_migpt
docker compose up -d --build
```

看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

## 使用

### 小爱作为渡的音箱

du-gateway 会给渡注入 `xiaoai_speak` 工具。渡需要像手机弹窗一样提醒你、而你没看手机时，可以把短句排到小爱播放队列；runner 默认每 3 秒拉一次队列并播放 MiniMax 生成的音频。

这条链路不需要你对小爱说入口词，只要求 runner 在线、`DU_GATEWAY_URL` 是公网 HTTPS，且网关配置了可用的 MiniMax TTS。

### 小爱作为语音入口

如果还要让“小爱听到入口词后转发给渡”，先在 MiniApp 打开：

```text
工具 -> 小爱音箱 -> 启用开关
```

然后对小爱说：

```text
小爱同学，请求连接渡，测试一下
```

runner 会：

```text
1. 轮询小爱语音文本
2. 判断入口词
3. 调 du-gateway
4. 播放 Minimax audio_url
5. 上报连接状态和小爱日志到 MiniApp
```

## 资源限制

`docker-compose.yml` 默认：

```text
mem_limit: 256m
NODE_OPTIONS=--max-old-space-size=128
```

如果 Mac 内存也吃紧，可以把 `mem_limit` 改成 `192m`，但不建议低于这个值。

## 注意

- Mac 不能睡眠；屏幕可以关，机器不要睡。
- `DU_GATEWAY_URL` 必须是公网 HTTPS 地址，因为小爱要播放 `audio_url`。
- MiGPT Next 走小米云接口，不要求 Mac 和小爱在同一个局域网。
- `abortXiaoAI()`、URL 播放和 TTS 行为跟具体音箱型号有关，需要实机测。
