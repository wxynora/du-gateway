# 小爱音箱接入渡：MiGPT Next 联动方案

## 结论

用 MiGPT Next 做小爱音箱桥接层。

小爱音箱负责听、说、播放、音量和部分 MiOT 动作；`du-gateway` 负责聊天、上下文、记忆、工具调用、家居控制和存档。

## 目标

- 小爱音箱作为唤醒渡的语音入口。
- 只有用户说“请求连接渡”开头，才进入渡。
- 所有小爱入口消息复用 Telegram 的窗口 ID。
- MiGPT Next 不维护上下文、不做人格、不保存长期记忆。
- 上下文、记忆、工具调用、存档全部交给 `du-gateway`。
- 不使用 MiGPT Next 自带默认模型兜底。
- 小爱入口是独立 `channel=xiaoai`，使用自己的入口风格 system，不复用 Telegram / QQ / 微信的风格 system。
- 小爱入口只能发语音，渡的输出必须且只能是一个 `<voice>...</voice>`。
- 第一版直接使用 Minimax 生成 mp3 并让小爱播放音频 URL；小爱自带 TTS 只做失败兜底。
- 第一版先不上口头二级口令；`XIAOAI_GATEWAY_TOKEN` 是可选服务鉴权，没配置就不要求 runner 传 token。

## 总链路

```text
小爱音箱
-> MiGPT Next
-> 入口关键词过滤：请求连接渡
-> du-gateway
-> X-Window-Id: tg_<你的TG用户ID>
-> X-Reply-Channel: xiaoai
-> 小爱入口风格 system：只能 <voice>
-> 渡现有聊天链路
-> MiGPT Next
-> 抽取 <voice> 文本
-> Minimax mp3 URL
-> 小爱播放音频 URL
```

示例：

```text
你说：小爱同学，请求连接渡，今天有什么安排
MiGPT Next 收到：请求连接渡，今天有什么安排
发给渡：今天有什么安排
窗口 ID：tg_<你的TG用户ID>
入口 channel：xiaoai
渡回复：<voice>今天主要有三件事，我先帮你捋一遍。</voice>
MiGPT Next 抽取 voice 文本
du-gateway 生成 Minimax mp3 URL
小爱播放这个 mp3
```

## MiGPT Next 可利用的小爱能力

### 语音输入

MiGPT Next 会轮询小爱音箱的对话记录，拿到用户对小爱说的话。

用途：

- 小爱作为唤醒渡的入口。
- 语音转文字后发给 `du-gateway`。
- 只处理指定关键词，避免普通小爱命令污染渡的记忆。

入口规则：

```text
请求连接渡
```

不以这个开头的内容，一律忽略。

输入格式需要第一时间实测并记录：

```text
MiGPT Next 预期拿到的是小爱 ASR 后的文本字段 query
不是原始音频
```

实测时要保存一条原始 payload，确认：

- 文本是否已经被小爱 NLU 改写。
- 是否会出现同一句话被切成多条记录。
- 是否会出现“请求连接渡，今天有什么安排”和“今天有什么安排”连续两条。
- 是否存在型号差异。

如果实际拿到的是音频流，而不是文本，则本方案需要额外增加 ASR 层；第一版不按这个假设设计。

### 小爱文字播报

MiGPT Next 支持：

```js
engine.speaker.play({ text: "要播报的内容" })
```

用途：

- Minimax 失败时作为兜底。
- 网关离线或 TTS 失败时播报短错误提示。

限制：

- 这是小爱自己的 TTS 声音。
- 部分型号 TTS 可能不稳定，需要实测。
- 第一版主路径不使用小爱 TTS。

### 播放音频 URL

MiGPT Next 支持：

```js
engine.speaker.play({ url: "https://example.com/reply.mp3" })
```

用途：

- 渡回复 `<voice>` 文本后，调用 Minimax 生成 mp3。
- 云服务器暴露短时可访问的 mp3 URL。
- 小爱播放这个 URL。

这就是“听起来像小爱换成 Minimax 声音”。

### 音量控制

MiGPT Next 暴露了：

```js
engine.MiNA.setVolume(50)
```

用途：

- 渡可以控制小爱音量。
- 固定口令可直接处理，例如“请求连接渡，音量 30”。

### 播放控制

MiGPT Next 的 `MiNA` 有这些能力：

```js
engine.MiNA.play()
engine.MiNA.pause()
engine.MiNA.playOrPause()
engine.MiNA.stop()
engine.MiNA.getStatus()
engine.MiNA.getVolume()
```

用途：

- 播放、暂停、继续、停止。
- 查询当前播放状态。
- 查询音量。

### MiOT 动作

MiGPT Next 支持：

```js
engine.MiOT.doAction(siid, aiid, args)
engine.MiOT.setProperty(siid, piid, value)
engine.MiOT.rpc(method, params)
```

用途：

- 调音箱本身暴露的 MIoT 能力。
- 某些型号可以用指定 `siid/aiid` 做 TTS 或设备动作。
- 后续可查 `home.miot-spec.com` 对应型号能力。

限制：

- 不同小爱型号的 `siid/piid/aiid` 不一样。
- 不能先假设所有型号都支持同一套动作。

### 打断小爱原回答

MiGPT Next 有：

```js
engine.speaker.abortXiaoAI()
```

但当前实现里不是稳定能力，很多型号无法真正打断。

结论：

- 可以保留调用位。
- 不把它当核心依赖。

### 固定口令直达

MiGPT Next 的 `onMessage` 可以自己拦截。

适合不进大模型的命令：

```text
请求连接渡，音量 30
请求连接渡，停止播放
请求连接渡，暂停
请求连接渡，继续播放
请求连接渡，播放测试音频
```

这些可以 MiGPT Next 直接处理，不必发给渡。

### 临时会话模式

第一版默认仍使用“请求连接渡”前缀，先保证安全和可控。

第二版可以加临时会话模式：

```text
请求连接渡
-> 进入渡模式
-> 接下来 N 秒内的语音都直接发给 du-gateway
-> 用户说“退出渡”或超时后自动退出
```

建议默认参数：

```text
渡模式有效期：60 秒
每次有效对话后续期：30 秒
退出口令：退出渡
```

风险：

- 进入渡模式后，家里其他人的声音也可能进入同一个 TG 窗口。
- 所以临时会话模式必须和二级口令、超时退出一起做，不作为第一版必需项。

### 家居控制入口

小爱入口把话送给渡，渡再决定怎么控家居。

```text
请求连接渡，打开卧室空调
-> du-gateway
-> 渡判断是家居控制
-> mijiaAPI / HA / 巴法云
```

分工：

```text
米家已有设备：mijiaAPI --run
美的设备：HA / 巴法云
小爱音箱自身：MiGPT Next 的 MiNA / MiOT
```

### 闹钟和提醒

这块作为后续能力接入。

可利用方向：

```text
渡创建提醒
-> 调小爱闹钟/提醒接口
-> 到点小爱响
```

但这块不写死进第一版，因为 MiGPT Next README 没把闹钟作为明确能力暴露出来，需要单独查小米接口或实测。

## 聊天链路

推荐新增专用入口：

```http
POST /api/xiaoai/message
```

原因：

- MiGPT Next 不需要知道当前模型。
- 不需要在 MiGPT Next 里填任何默认模型。
- `du-gateway` 内部自己走现有模型选择逻辑。
- 拉不到可用模型就直接报错，不兜底。
- 网关可以按 `source=xiaoai` / `X-Reply-Channel: xiaoai` 注入小爱入口风格 system。
- 网关可以统一抽取 `<voice>` 并生成 Minimax 音频 URL。

请求：

```json
{
  "text": "今天有什么安排",
  "source": "xiaoai",
  "speaker": "卧室小爱"
}
```

Header：

```http
X-Window-Id: tg_<你的TG用户ID>
X-Reply-Channel: xiaoai
```

如果网关配置了 `XIAOAI_GATEWAY_TOKEN`，再额外带：

```http
Authorization: Bearer <XIAOAI_GATEWAY_TOKEN>
```

配置复用：

```text
TELEGRAM_GATEWAY_URL：复用现有网关地址
TELEGRAM_CHAT_PATH：复用现有聊天路径
TELEGRAM_PROACTIVE_TARGET_USER_ID：缺省窗口 ID 来源
XIAOAI_GATEWAY_TOKEN：可选；小爱入口专用 Bearer 鉴权，不复用主网关 token
MINIMAX_*：复用现有 Minimax TTS 配置
GATEWAY_PUBLIC_BASE_URL / TELEGRAM_GATEWAY_URL：复用现有公网 URL 推断
```

不新增：

```text
XIAOAI_SECRET
XIAOAI_SHARED_SECRET
XIAOAI_TTS_TTL_SECONDS
XIAOAI_TTS_MAX_ITEMS
```

返回：

```json
{
  "ok": true,
  "reply": "<voice>今天主要有三件事，我先帮你捋一遍。</voice>",
  "voice_text": "今天主要有三件事，我先帮你捋一遍。",
  "audio_url": "https://duxy-home.com/api/xiaoai/tts/xxx.mp3",
  "speak_mode": "audio"
}
```

错误返回：

```json
{
  "ok": false,
  "error": {
    "code": "MODEL_UNAVAILABLE",
    "message": "当前没有可用模型"
  },
  "speak_text": "渡暂时无法接通"
}
```

建议错误码：

```text
UNAUTHORIZED：鉴权失败
MODEL_UNAVAILABLE：当前没有可用模型
GATEWAY_TIMEOUT：网关处理超时
UPSTREAM_UNAVAILABLE：上游模型不可用
BAD_REQUEST：请求格式错误
INTERNAL_ERROR：网关内部错误
```

MiGPT Next 收到 `ok: false` 时，不要静默失败，直接播放 `speak_text`。

如果不新增接口，也可以直接打现有 OpenAI 兼容接口：

```http
POST /v1/chat/completions
X-Window-Id: tg_<你的TG用户ID>
```

但这种方式必须传 `model`，不如专用入口干净。

## App 工具页

MiniApp 的“工具”里新增“小爱音箱”入口，第一版只做可运行控制台，不扩展复杂策略。

包含：

```text
启用开关：控制 /api/xiaoai/message 是否接受小爱消息
入口词：MiGPT Next 拉取后用于判断是否进入渡
退出词：MiGPT Next 拉取后用于退出临时会话模式
连接状态：展示 MiGPT Next 最近一次心跳、音箱名、最近文本、最近错误和最近音频
小爱日志：展示网关收到的小爱消息、TTS 结果、错误和 MiGPT Next 主动上报日志
```

接口：

```http
GET  /miniapp-api/xiaoai/overview
GET  /miniapp-api/xiaoai/config
PUT  /miniapp-api/xiaoai/config
GET  /miniapp-api/xiaoai/status
GET  /miniapp-api/xiaoai/logs

GET  /api/xiaoai/config
GET  /api/xiaoai/status
POST /api/xiaoai/status
GET  /api/xiaoai/logs
POST /api/xiaoai/logs
```

MiGPT Next 启动时或定时拉：

```http
GET /api/xiaoai/config
```

拿到：

```json
{
  "enabled": true,
  "entry_phrases": ["请求连接渡"],
  "exit_phrases": ["退出渡"]
}
```

MiGPT Next 心跳和日志上报：

```http
POST /api/xiaoai/status
POST /api/xiaoai/logs
```

这让 App 里的开关、入口词和退出词可以不改 `config.js` 就生效。第一版配置和日志存在网关本地 `DATA_DIR/xiaoai_state.json`。

## Mac Docker Runner

Mac 上可以直接跑仓库内置的 Docker 版 MiGPT runner：

```text
connectors/xiaoai_migpt
```

文件：

```text
Dockerfile
docker-compose.yml
.env.example
src/runner.mjs
README.md
```

启动：

```bash
cd connectors/xiaoai_migpt
cp .env.example .env
# 编辑 .env：填小米账号、音箱 did、du-gateway URL；token 没配置就留空
docker compose up -d --build
```

runner 行为：

```text
定时 GET /api/xiaoai/config
按 App 工具页的启用开关、入口词、退出词处理小爱语音
POST /api/xiaoai/message 转发给渡
优先播放 audio_url，失败时播 voice_text
POST /api/xiaoai/status 上报连接状态
POST /api/xiaoai/logs 上报小爱日志
```

默认资源限制：

```text
mem_limit: 256m
NODE_OPTIONS=--max-old-space-size=128
```

Mac 必须保持不睡眠；屏幕可以关，机器不能睡。

## 小爱入口风格 system

小爱和 Telegram / QQ / 微信一样，是独立入口 channel。

它共用 `du-gateway` 聊天链路和 TG 的 `window_id`，但不共用其他入口的风格 system。

小爱入口注入的 system：

```text
你正在通过小爱音箱和辛玥说话。
这是语音播报入口，不是文字聊天入口。
你的回复必须且只能输出一个 <voice>...</voice> 标签。
请简短、口语、适合 TTS。
不要使用 Markdown、列表、分割线、视觉排版、括号内心独白、表情包标签。
不要在 <voice> 外输出任何内容。
语音要像口语短句；停顿只靠自然短句和标点，不写停顿控制标签，也不要堆省略号/破折号。
不要写括号动作提示，例如“轻笑”“低声说”或 MiniMax 动作标签。
```

示例：

```text
正确：<voice>我在。你刚刚说的事，我先帮你记下来。</voice>
正确：<voice>我想一下。先把最要紧的那件事处理掉。</voice>
错误：我在。<voice>你要我帮你做什么？</voice>
错误：<voice>一、先这样。二、再那样。</voice>
错误：<voice>[happy] 嗯……这个——我想想。</voice>
```

说明：

- 小爱入口默认发语音，不需要让渡自己判断要不要发语音。
- `<voice>` 仍沿用现有语音标签思想，但小爱 channel 是强制语音，不是 Telegram 的“文字 + 可选语音”。
- MiGPT Next 只抽 `<voice>` 里的文本。
- 如果渡没有按规范输出 `<voice>`，网关或 MiGPT Next 用可见文本兜底抽取，并记录格式错误日志。

## 上下文处理

原则：

```text
MiGPT Next 不维护上下文
du-gateway 维护上下文
TG 和小爱共用同一个 window_id
```

MiGPT Next 配置：

```js
context: {
  historyMaxLength: 0
},
prompt: {
  system: ""
},
callAIKeywords: []
```

实际实现里不要调用 `engine.askAI(msg)`，而是在 `onMessage` 里自己请求 `du-gateway`。

注意：MiGPT Next 内部历史实现可能会把 `historyMaxLength: 0` 修正成最小 1。这里不依赖这个配置实现隔离，真正的隔离方式是完全不走 `engine.askAI(msg)`，只在 `onMessage` 里手动请求 `du-gateway`。

原因：

- MiGPT Next 自带上下文不该参与。
- 否则会出现 MiGPT 一份上下文，`du-gateway` 又一份上下文。
- 小爱和 TG 共用窗口，所以唯一上下文来源必须是 `du-gateway` 的 TG 窗口。

## MiGPT Next 核心逻辑

```js
const ENTRY = "请求连接渡";
const XIAOAI_GATEWAY_TOKEN = process.env.XIAOAI_GATEWAY_TOKEN || "";
const RECENT_TTL_MS = 10000;
const recent = new Map();

function normalizeUserText(raw) {
  return String(raw || "")
    .trim()
    .replace(/^请求连接渡[，,。.\s]*/, "")
    .trim();
}

function isDuplicate(speaker, userText) {
  const key = `${speaker || "default"}:${userText}`;
  const now = Date.now();
  const last = recent.get(key) || 0;
  recent.set(key, now);
  return now - last < RECENT_TTL_MS;
}

async function onMessage(engine, { text }) {
  const raw = String(text || "").trim();

  if (!raw.startsWith(ENTRY)) {
    return { handled: true };
  }

  const userText = normalizeUserText(raw);

  await engine.speaker.abortXiaoAI();

  if (!userText) {
    await engine.speaker.play({ text: "已连接渡，你说。" });
    return { handled: true };
  }

  if (isDuplicate("卧室小爱", userText)) {
    return { handled: true };
  }

  if (/^音量\s*\d{1,3}$/.test(userText)) {
    const volume = Number(userText.match(/\d{1,3}/)[0]);
    await engine.MiNA.setVolume(volume);
    await engine.speaker.play({ text: `音量已调到 ${volume}` });
    return { handled: true };
  }

  if (["暂停", "暂停播放"].includes(userText)) {
    await engine.MiNA.pause();
    return { handled: true };
  }

  if (["继续", "继续播放"].includes(userText)) {
    await engine.MiNA.play();
    return { handled: true };
  }

  if (["停止", "停止播放"].includes(userText)) {
    await engine.MiNA.stop();
    return { handled: true };
  }

  const reply = await sendToDuGateway({
    text: userText,
    speaker: "卧室小爱",
    channel: "xiaoai",
    authToken: XIAOAI_GATEWAY_TOKEN
  });

  if (reply.audioUrl) {
    await engine.speaker.play({ url: reply.audioUrl });
  } else {
    await engine.speaker.play({ text: reply.voiceText || "渡暂时说不出话。" });
  }
  return { handled: true };
}
```

## Minimax 声音方案

第一版主路径：

```text
渡回复 <voice>文本</voice>
-> du-gateway 抽取 voice_text
-> du-gateway 调 Minimax TTS
-> 生成 mp3
-> 临时托管成公网 URL
-> MiGPT Next 调 engine.speaker.play({ url })
```

兜底路径：

```text
Minimax 失败 / audio_url 播放失败
-> 小爱自带 TTS 播放 voice_text
```

建议新增 TTS URL 接口：

```http
POST /api/xiaoai/tts
```

请求：

```json
{
  "text": "我在，怎么啦？",
  "speaker": "卧室小爱"
}
```

返回：

```json
{
  "ok": true,
  "audio_url": "https://duxy-home.com/api/xiaoai/tts/xxx.mp3",
  "expires_in": 600
}
```

MiGPT Next 判断：

```js
if (data.audio_url) {
  await engine.speaker.play({ url: data.audio_url });
} else {
  await engine.speaker.play({ text: data.voice_text || "渡暂时说不出话。" });
}
```

要求：

- mp3 URL 必须公网可访问。
- URL 可以是短时效签名地址，不能依赖内网地址。
- 如果播放 URL 失败，回退到小爱文字 TTS。
- Minimax 生成耗时过长时，先播放“我想一下”，再播放音频。
- 需要实测播放 URL 是否能被打断、是否影响当前播放状态。

## 记忆与存档

固定使用：

```http
X-Window-Id: tg_<你的TG用户ID>
```

效果：

- TG 聊过的内容，小爱能接上。
- 小爱说过的内容，也进入 TG 同一个窗口。
- 总结、动态记忆、R2 存档都复用现有逻辑。
- 不新增 `xiaoai_home` 窗口。

风险：

- 家里其他人说“请求连接渡”也会写进你的 TG 记忆。
- 第一版先不上口头二级口令，靠入口词和服务端 Bearer 鉴权控制入口；多人场景再加暂停响应、二级口令或声纹。
- 敏感工具调用不要只凭小爱入口直接执行，建议要求 TG 端确认。

建议权限策略：

```text
小爱入口：
- 允许普通聊天
- 允许低风险音箱控制
- 允许低风险家居控制
- 禁止读取敏感档案
- 禁止删除/覆盖记忆
- 禁止高风险设备控制

TG 入口：
- 保留完整权限
- 高风险操作走 TG 确认
```

## 去重与防误触

建议 MiGPT Next 本地做：

```text
同一 speaker
同一 userText
10 秒内只处理一次
```

原因：

- 轮询小爱对话记录时可能重复看到同一条。
- 避免重复发给渡、重复播报。
- 去重时要比较去掉“请求连接渡”后的 `userText`。
- 如果实测出现轻微文本差异，再考虑模糊去重；第一版先严格相等。

## 并发和顺序

TG 和小爱共用同一个 `window_id`，多端几乎同时发消息时，R2 里的对话顺序可能交错。

第一版接受这个边界，不额外拆窗口。

建议：

- 小爱请求带 `source: "xiaoai"` 和 `speaker`。
- 小爱请求带 `X-Reply-Channel: xiaoai`。
- 网关存档时保留 source 信息，方便排查。
- 如果后续频繁出现顺序问题，再在 `du-gateway` 侧加 per-window 队列。

## 功能分工

```text
MiGPT Next：
- 监听小爱语音文本
- 入口关键词过滤
- 抽取 `<voice>` 文本
- 小爱播放音频 URL
- Minimax 失败时小爱文字 TTS 兜底
- 音量/暂停/停止等音箱自身能力
- 必要时调用 MiOT 原始能力

du-gateway：
- 聊天
- 上下文
- 记忆
- 存档
- 小爱 channel style system 注入
- `<voice>` 规范校验与抽取
- 工具调用
- 家居控制路由
- Minimax TTS 生成 mp3 URL

mijiaAPI：
- 小爱执行米家自然语言控制
- `xiaoai_run_command` 工具底层调用：

```bash
mijiaAPI --run "关闭卧室空调" --wifispeaker_name "小爱音箱Play 增强版" --quiet
```

- 运行环境由 `MIJIA_API_COMMAND`、`MIJIA_API_AUTH_PATH`、`MIJIA_WIFISPEAKER_NAME`、`MIJIA_API_TIMEOUT_SECONDS` 配置。
- 这个工具不依赖 MiGPT runner，适合“渡主动控制智能家居”；MiGPT runner 只继续负责“小爱作为语音入口/音箱外放”。

HA / 巴法云：
- 美的和非米家设备控制

Minimax：
- 渡的声音
```

## 第一版验收标准

- 说“请求连接渡，测试一下”，小爱能用 Minimax 音频播出渡的回复。
- 小爱入口回复必须是一个 `<voice>...</voice>`，不能在标签外输出文字。
- MiGPT Next 能抽取 `<voice>` 文本，并优先播放 `audio_url`。
- Minimax 失败时，小爱能用自带 TTS 播放兜底文本。
- 普通喊“小爱同学，今天天气怎么样”不会进网关。
- 如果配置了 `XIAOAI_GATEWAY_TOKEN`，不带 `Authorization: Bearer ...` 不能进入网关。
- 网关离线、超时、模型不可用时，小爱能播报明确错误提示。
- 能记录一条小爱原始 payload，确认拿到的是 ASR 文本。
- `du-gateway` 里看到窗口 ID 是 TG 的 `window_id`。
- TG 和小爱共用上下文。
- 说“请求连接渡，音量 30”，能直接调小爱音量。
- 说“请求连接渡，停止播放”，能停止小爱播放。
- 不使用 MiGPT Next 默认模型兜底。
- 拉不到网关可用模型时，直接返回错误，不乱换模型。

## 风险

- MiGPT Next 仓库已归档，后续小米接口变化可能要自己维护。
- 小米账号登录可能触发安全验证，必要时用 `passToken`。
- 不同小爱型号对 TTS、播放 URL、MiOT 动作支持不一致。
- `abortXiaoAI()` 不保证能真正打断原小爱回答。
- Minimax 音频播放依赖小爱能访问公网 mp3 URL。
- Minimax 会增加语音回复延迟，需要实测从说完话到开始播放的总耗时。

## 参考

- [idootop/migpt-next](https://github.com/idootop/migpt-next)
- [MiGPT Next README](https://github.com/idootop/migpt-next/blob/main/apps/next/README.md)
