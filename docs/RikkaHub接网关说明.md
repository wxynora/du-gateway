# RikkaHub 接网关说明

## 请求是谁发给谁

```
RikkaHub（你用的 app）
    ↓ 发聊天请求
网关（du-gateway，本仓库）
    ↓ 转发请求
TARGET_AI_URL（真正出回复的对话 API）
```

所以有两处要填：**RikkaHub 里填网关**，**网关 .env 里填 TARGET**。

---

## 1. RikkaHub 里要填什么

在 RikkaHub 的「API / 接口 / 自定义后端」之类设置里：

- **Base URL / API 地址**：填**网关的地址**，让 RikkaHub 把聊天请求发到网关，而不是直接发到别的 API。
  - 本地：`http://你的电脑IP:5000` 或 `http://localhost:5000`（仅本机）
  - 已部署：`https://你的网关域名`（不要加 `/v1` 或 `/chat/completions`，RikkaHub 一般会自动拼）
- **API Key**：看 RikkaHub 是否必填。若必填，可以随便填一个（网关不校验这个），或者用网关文档里说的请求头（如有）。
- **窗口 ID**：若 RikkaHub 支持自定义请求头，建议加上 `X-Window-Id`，值为每个对话窗口的唯一 ID（网关靠这个做白名单、存档）。

这样配置后，RikkaHub 会向「网关的 `/v1/chat/completions` 或 `/chat/completions`」发 POST，由网关处理后再转发。

---

## 2. 网关 .env 里 TARGET 填什么

这里的 TARGET 是**网关收到 RikkaHub 的请求后，要转发的目标**，也就是**真正提供对话能力的 API**。

- **TARGET_AI_URL**  
  填「对话接口的完整 URL」，例如：
  - OpenAI：`https://api.openai.com/v1/chat/completions`
  - DeepSeek：`https://api.deepseek.com/v1/chat/completions`
  - 其他兼容 OpenAI 格式的：填对方提供的 `.../v1/chat/completions` 或等价地址
  - 你当前用的服务（如 DZ / 渡 等）：填对方文档里给的 **chat completions** 的 URL

- **TARGET_AI_API_KEY**  
  填调用上面这个 URL 时需要的 **API Key**（若对方不需要 Key，可留空）。

也就是说：**RikkaHub 里配置的是「我的 API」指的是网关；网关里 TARGET 配置的是「网关要调用的那个对话 API」**。你在 RikkaHub 里配置的 API，如果是「直接调某个模型」的 Key，那个 Key 应该填在网关的 **TARGET_AI_API_KEY**，对应的地址填在 **TARGET_AI_URL**。

---

## 3. 小结

| 填在哪里       | 填什么 |
|----------------|--------|
| **RikkaHub**   | **网关的地址**（例如 `http://IP:5000` 或 `https://网关域名`），让 app 请求先到网关。 |
| **网关 .env**  | **TARGET_AI_URL** = 对话 API 的 URL；**TARGET_AI_API_KEY** = 调用该 API 的 Key（没有就留空）。 |

你「在 RikkaHub 里配置的 API」如果是「渡 / 某个模型的接口地址 + Key」，那就把**同一个地址**填到网关的 **TARGET_AI_URL**，**同一个 Key** 填到 **TARGET_AI_API_KEY**；RikkaHub 里则改成填**网关的地址**，这样流量就会变成：RikkaHub → 网关 → 你现在的 API。
