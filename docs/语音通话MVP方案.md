# 语音通话 MVP 方案

> 目标：在 MiniApp 里加一个语音通话入口，按住说话 → 网关转文字 → 走聊天管道 → TTS 回音频播放。先能用，不追求实时双工。

## 现状

| 模块 | 状态 |
|------|------|
| TTS（MiniMax T2A v2） | ✅ 已完成，`services/minimax_tts.py` |
| STT（语音转文字） | ❌ 完全空白 |
| 前端通话 UI | ❌ 完全空白 |
| 聊天管道 | ✅ `POST /v1/chat/completions` 已稳定 |

## 整体流程

```
[MiniApp 前端]                    [网关]                         [外部服务]
     │                              │                               │
     │  1. 按住录音 (MediaRecorder) │                               │
     │  2. 松手 → 上传 audio blob   │                               │
     │ ─────── POST /api/voice ────>│                               │
     │                              │  3. 音频 → STT 服务            │
     │                              │ ─────────────────────────────> │
     │                              │ <── 文字 ────────────────────  │
     │                              │                               │
     │                              │  4. 文字 → 聊天管道（pipeline） │
     │                              │     与普通文字消息走同一条路     │
     │                              │                               │
     │                              │  5. 回复文字 → TTS（MiniMax）   │
     │                              │ ─────────────────────────────> │
     │                              │ <── mp3 bytes ───────────────  │
     │                              │                               │
     │ <── { text, audio_url } ──── │                               │
     │                              │                               │
     │  6. 播放音频 + 显示文字       │                               │
```

## 一、STT 服务选型

### 方案对比

| 服务 | 优点 | 缺点 | 费用 |
|------|------|------|------|
| **MiniMax ASR** | 和 TTS 同一家，一套 key | 文档较少，中文效果待验证 | 按量 |
| **Whisper API（OpenAI）** | 中文效果好，接口简单 | 需要额外 key，延迟稍高 | $0.006/分钟 |
| **Cloudflare Workers AI whisper** | 已有 CF 账号，免费额度 | 模型较小，中文可能不够好 | 免费额度内 0 |
| **本地 faster-whisper** | 免费，隐私好 | 需要 GPU 或 CPU 算力，部署麻烦 | 0（算力自付） |

### 建议

先用 **Whisper API（OpenAI）**，理由：
- 接口最简单（`POST /v1/audio/transcriptions`，传文件就行）
- 中文识别质量稳定
- 已有 `OPENAI_API_KEY` 配置项
- 费用极低，日常聊天一天可能就几分钟语音

如果后续想省钱或降延迟，再换 CF Workers AI whisper 或 MiniMax ASR。

## 二、网关端实现

### 新增文件

**`services/stt.py`** — STT 服务封装

```python
def speech_to_text(audio_bytes: bytes, mime_type: str = "audio/webm") -> str | None:
    """音频转文字，返回识别结果文本。"""
    # 调用 OpenAI Whisper API
    # POST https://api.openai.com/v1/audio/transcriptions
    # multipart/form-data: file=audio, model=whisper-1, language=zh
```

**`routes/voice_api.py`** — 语音通话路由

```python
@bp.route("/api/voice", methods=["POST"])
def api_voice():
    """
    接收前端录音，STT → 聊天管道 → TTS，返回文字+音频。

    请求：multipart/form-data
      - audio: 录音文件 (webm/ogg/mp3)
      - window_id: 可选，聊天窗口 ID

    响应：JSON
      {
        "ok": true,
        "user_text": "识别出的用户语音",
        "reply_text": "渡的回复文字",
        "audio_url": "/api/voice/audio/xxx.mp3"  // 或 base64
      }
    """
```

### 音频传输方式

MVP 阶段直接把 TTS 音频 base64 编码放在 JSON 响应里返回，省掉文件存储：

```json
{
  "ok": true,
  "user_text": "今天天气怎么样",
  "reply_text": "今天晴天哦，适合出门~",
  "audio_b64": "//uQxAAAAAANIAAAAAE...",
  "audio_format": "mp3"
}
```

后续如果音频太大再改成先存 R2 返回 URL。

### 配置项（`.env`）

```bash
# STT
STT_BACKEND=openai_whisper          # 后续可扩展 minimax_asr / cf_whisper
OPENAI_API_KEY=sk-xxx               # 已有，复用
STT_MODEL=whisper-1
STT_LANGUAGE=zh                     # 默认中文
STT_MAX_DURATION_SECONDS=60         # 单条语音最大时长
```

## 三、前端实现

### 新增 Tab / 入口

在 MiniApp 加一个「语音」按钮（可以先放在 Overview 页面，或者作为独立 tab）。

### 核心交互

**按住说话模式（Push-to-Talk）**：
1. 用户按住麦克风按钮 → 开始录音（`MediaRecorder` API，`audio/webm` 格式）
2. 松手 → 停止录音 → 上传到 `/api/voice`
3. 显示"识别中..."状态
4. 收到回复 → 显示文字 + 自动播放音频
5. 播放完毕 → 回到待命状态

### 简化 UI 草案

```
┌─────────────────────────┐
│                         │
│   💬 渡的回复文字        │
│   （带滚动历史）         │
│                         │
│                         │
├─────────────────────────┤
│                         │
│     🎤 识别出的文字      │
│                         │
│   ┌─────────────────┐   │
│   │   🎙️ 按住说话    │   │
│   └─────────────────┘   │
│                         │
│   状态：等待中 / 录音中  │
│        / 识别中 / 播放中 │
└─────────────────────────┘
```

### 关键前端代码片段

```typescript
// 录音
const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
const chunks: Blob[] = [];
mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
mediaRecorder.onstop = async () => {
  const blob = new Blob(chunks, { type: "audio/webm" });
  // 上传
  const form = new FormData();
  form.append("audio", blob, "voice.webm");
  const resp = await fetch("/api/voice", { method: "POST", body: form });
  const data = await resp.json();
  // 播放
  const audio = new Audio(`data:audio/mp3;base64,${data.audio_b64}`);
  audio.play();
};
```

### 浏览器兼容

- `MediaRecorder` 在现代浏览器（Chrome/Safari/Firefox）和 Telegram WebApp 内均支持
- iOS Safari 需要 `audio/mp4` 格式，可能需要做格式判断
- Telegram Mini App 的 WebView 基于系统浏览器，基本都支持

## 四、实施步骤

按优先级排序，每步都可以独立测试：

### Phase 1：STT 通路打通
1. 写 `services/stt.py`，封装 Whisper API 调用
2. 写 `routes/voice_api.py`，`POST /api/voice` 接收音频文件，返回识别文字
3. 用 curl 测试：录一段 webm 上传，确认能返回中文文字

### Phase 2：串联聊天管道 + TTS
4. `/api/voice` 里拿到 STT 文字后，调用聊天管道获取回复
5. 回复文字走 MiniMax TTS 生成音频
6. 返回 `{ user_text, reply_text, audio_b64 }`
7. 用 curl / Postman 端到端测试

### Phase 3：前端 UI
8. 新建 `VoiceTab.tsx`（或在 Overview 加入口）
9. 实现按住录音 + 上传 + 播放
10. 基础状态管理（录音中/识别中/播放中）

### Phase 4：体验优化（后续）
- 录音波形动画
- 连续对话（播放完自动进入下一轮录音）
- 流式 TTS（边生成边播放，降低等待感）
- 语音消息也写入聊天历史
- iOS 兼容性处理

## 五、注意事项

- **录音权限**：浏览器会弹权限请求，Telegram Mini App 内需要用户授权麦克风
- **音频格式**：`MediaRecorder` 默认 webm(opus)，Whisper API 支持 webm/mp3/mp4/wav，不需要转码
- **耗时预估**：STT ~1-2s + 聊天管道 ~2-5s + TTS ~1-2s = 总共 4-9s，可接受
- **并发**：MVP 不考虑，单人用没问题
- **费用**：Whisper $0.006/min + MiniMax TTS 按字计费，日常用量几乎可忽略
