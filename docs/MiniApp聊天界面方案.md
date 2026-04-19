# MiniApp 聊天界面方案

> 目标：在 MiniApp 里加一个聊天 Tab，类似 cakumi 的对话体验。先能用，后续再加语音。

## 现状

- 聊天管道 `POST /v1/chat/completions` 已完整，支持 stream SSE
- 管道自动处理：记忆注入、总结、动态层召回、prompt、工具调用
- 前端只需要发 messages 收 stream，不用管任何后端逻辑
- MiniApp 已有 Tab 切换机制、cream 风格组件库、API 封装

## 整体架构

```
[ChatTab.tsx]
    │
    │  POST /v1/chat/completions
    │  body: { messages, stream: true, window_id: "miniapp_chat" }
    │
    ▼
[网关聊天管道]  ←── 自动注入记忆/总结/感知/工具等
    │
    │  SSE stream: data: {"choices":[{"delta":{"content":"..."}}]}
    │
    ▼
[前端逐字渲染气泡]
```

## UI 设计

```
┌──────────────────────────┐
│  ← 返回        渡 · 在线  │  顶栏
├──────────────────────────┤
│                          │
│        ┌────────────┐    │  渡的回复（左侧气泡）
│        │ 今天怎么样～ │    │
│        └────────────┘    │
│                          │
│    ┌────────────┐        │  用户消息（右侧气泡）
│    │ 还行吧在摸鱼 │        │
│    └────────────┘        │
│                          │
│        ┌────────────┐    │
│        │ 摸鱼也要...  │    │  流式打字中（光标闪烁）
│        └────────────┘    │
│                          │
├──────────────────────────┤
│  [输入框............] 📤  │  底部输入区
│                     🎙️   │  语音按钮（后续加）
└──────────────────────────┘
```

### 气泡风格

沿用 MiniApp 现有 cream 风格：
- 渡的气泡：`bg-white/60 backdrop-blur border-white/45`，左对齐
- 用户气泡：`bg-neutral-900 text-white`，右对齐
- 圆角 `rounded-2xl`，与现有卡片统一

## 核心实现要点

### 1. 消息管理

```typescript
type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

// 前端维护消息列表
const [messages, setMessages] = useState<ChatMessage[]>([]);
```

每次发送时把完整 messages 数组传给后端，后端管道会自动注入记忆等上下文。

### 2. SSE 流式解析

```typescript
const resp = await apiFetch("/v1/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    messages,
    stream: true,
    window_id: "miniapp_chat",
  }),
});

const reader = resp.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  // 按行解析 "data: {...}\n\n"
  const lines = buffer.split("\n");
  buffer = lines.pop()!;
  for (const line of lines) {
    if (!line.startsWith("data: ") || line === "data: [DONE]") continue;
    const chunk = JSON.parse(line.slice(6));
    const delta = chunk.choices?.[0]?.delta?.content || "";
    // 追加到当前 assistant 消息
  }
}
```

### 3. window_id

给 MiniApp 聊天用固定 `window_id: "miniapp_chat"`，这样：
- 有独立的聊天历史和轮次计数
- 总结和记忆召回按这个窗口独立运作
- 不和 Telegram / RikkaHub 的窗口混

### 4. 历史持久化

MVP 阶段：消息存 `localStorage`，刷新不丢。
后续可选：存 R2，跨设备同步。

## 新增文件

| 文件 | 说明 |
|------|------|
| `miniapp/src/ui/tabs/ChatTab.tsx` | 聊天界面主组件 |
| `miniapp/src/ui/hooks/useChat.ts` | 可选，抽取 SSE 解析 + 消息管理逻辑 |

不需要新增后端代码，完全复用现有管道。

## 实施步骤

### Phase 1：基础对话
1. `ChatTab.tsx`：气泡列表 + 输入框 + 发送
2. SSE 流式解析，逐字显示
3. 注册为 MiniApp 的一个 Tab 或入口按钮

### Phase 2：体验打磨
4. 消息 localStorage 持久化
5. 自动滚动到底部
6. 发送中禁用输入 + loading 状态
7. 长消息 Markdown 渲染（可选）

### Phase 3：语音集成
8. 输入框旁加 🎙️ 按钮
9. 按住录音 → 调 `/api/voice` → 播放回复音频
10. 语音和文字共用同一个消息列表

## 注意事项

- **不需要前端拼 system prompt**，后端管道全自动
- **Telegram Mini App WebView** 支持 `ReadableStream`，流式没问题
- **输入法兼容**：移动端注意 `compositionstart/end` 事件，避免中文输入时误触发送
- **键盘弹起**：iOS WebView 键盘弹起时需要滚动处理，避免输入框被遮挡
