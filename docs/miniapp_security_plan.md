# MiniApp 安全方案（密码 + 问答 + 白名单可撤销）

目标：在不“绑死 Telegram”的前提下，为 `/miniapp` 与 `/miniapp-api/*` 增加 **两层人工验证** 与 **可管理的白名单**，满足：

- **浏览器可用**：不依赖 Telegram `initData` 才能使用面板（因为你反馈 `initData` 曾经一直出错）。
- **两层验证**：先输入密码，再回答一个问题（第二层问答）。
- **白名单**：通过两层验证后加入白名单；白名单 **对你可见**；你可以 **撤销**；撤销后 **立刻 403**。
- **稳定优先**：不允许出现“验证完以后因为某个不明 bug 反而用不了 MiniApp”的体验；鉴权链路必须可解释、可自测。

> 本文是方案与接口约定，不直接落代码。实现时“先对齐再执行”。

---

## 1. 现状与可复用点

当前 MiniApp API 在 `routes/miniapp_api.py` 有统一 `before_request`：

- `enforce_ip_allowlist()`：若 `MINIAPP_IP_ALLOWLIST` 非空，则只允许白名单 IP
- `enforce_telegram_initdata()`：若 `MINIAPP_TELEGRAM_AUTH_ENABLED=1`，则校验 Telegram WebApp `initData`

这两条机制都可以保留，但你现在的诉求是 **浏览器也能用**，因此：

- **不把 Telegram initData 作为必须条件**（可作为可选增强，而不是主钥匙）
- **核心防护改为：两层验证 → 白名单凭证 → 每次请求校验**

---

## 2. 关键设计：你真正想要的“白名单”是什么

这里的“白名单”不是“IP 白名单”，而是“**受信任的访问主体列表**”。因为你要支持普通浏览器访问，所以主体推荐为：

- **设备/浏览器主体（device）**：用一个随机生成的 `device_id` 标识“这台设备上的这个浏览器”
- （可选）**Telegram 用户主体（tg_user）**：如果将来 `initData` 恢复稳定，可以把同一个人同时绑定到 Telegram user_id

你已明确：**只要 Telegram user_id 粒度够了**，但同时你又希望浏览器可用且不依赖 initData。

因此建议采用“双主体但同一套白名单表”的结构：

- 允许白名单记录类型：`device:<id>` 与 `tg:<user_id>`
- 你管理时看得到所有记录，并可撤销任意一条

---

## 3. 鉴权链路（避免不明 Bug 的核心）

### 3.1 总原则：只允许“单一真相”

每个请求判断“能不能访问”的唯一真相是：

> **请求中是否携带可验证的白名单凭证**（例如 signed token / session），并且该凭证映射到的主体仍在白名单中。

两层验证只负责“**把主体加入白名单**”，不负责每次请求的授权判断。

### 3.2 推荐链路顺序

对 `/miniapp-api/*`（除登录接口）：

1. **（可选）IP allowlist**：如果你愿意继续保留“更硬的门”，可以开；否则关闭
2. **白名单校验（必须）**：从请求里拿到凭证 → 校验签名/时效 → 得到主体 id → 查白名单
3. **（可选）Telegram initData**：仅作为“额外保障”，不作为主钥匙；失败不应阻止浏览器访问

> 关键：第 2 步是核心门禁；第 3 步永远不能成为“某些请求突然 401”的隐形雷。

---

## 4. 两层验证（密码 + 问答）如何“加入白名单”

### 4.1 需要的服务端配置（只列必需，不加兜底）

- `MINIAPP_PANEL_PASSWORD`
- `MINIAPP_PANEL_SECOND_PROMPT`（问答题目文案）
- `MINIAPP_PANEL_SECOND_ANSWER`
- `MINIAPP_PANEL_SIGNING_SECRET`（用于签名短票据/会话）

> 不配置完整就应明确返回 503，并在 MiniApp 页面给出“服务端未配置”的错误提示。

### 4.2 建议的接口（方案约定）

- `GET /miniapp-api/panel-auth/meta`
  - 返回：`enabled`、`second_prompt`
  - 用于前端展示登录页

- `POST /miniapp-api/panel-auth/verify`
  - 入参：`password`、`second_answer`
  - 行为：
    - 校验两层通过后：
      - 生成 `device_id`（如果客户端没有）并写入白名单
      - 签发一个 **短票据**（见下一节）
  - 返回：`panel_token`、`expires_in`

- `GET /miniapp-api/panel-auth/list`
  - 返回白名单列表（仅允许“你本人”查看；如何识别你本人见 6.2）

- `POST /miniapp-api/panel-auth/revoke`
  - 入参：要撤销的主体（`device_id` 或 `tg_user_id`）
  - 行为：从白名单移除；撤销立刻生效（下一次请求直接 403）

---

## 5. “白名单凭证”怎么带（重点：别引入玄学 Bug）

你的 MiniApp 里有几类请求形态，能不能带 header 不一样：

| 场景 | 能带自定义 Header？ | 建议携带方式 |
|---|---:|---|
| `fetch`/XHR | 可以 | `Authorization: Bearer <panel_token>` 或 `X-Panel-Token: ...` |
| `EventSource`（SSE） | 不可以 | `?panel_token=...` query 参数 |
| CSS `background-image: url(...)` / `<img src=...>` | 不可以 | `?panel_token=...` query 参数（或改为 fetch→blob，但成本更高） |

因此方案必须同时支持：

- Header 取 token（主路径）
- Query 取 token（SSE/图片路径）

并且服务端必须保证两种取法逻辑一致。

---

## 6. 白名单可见、可撤销：谁能管理这张表

你希望“白名单对我可见”，意味着必须定义“你是谁”。

### 6.1 浏览器路径（不依赖 Telegram）

最省事的定义是：**能通过两层验证的人就是你**。

但这会导致“你把密码告诉别人”时，对方也能看到名单并撤销。

若你接受这一点（你自己掌握密码/问答即可），那就不用再加第三层。

### 6.2 更稳的定义（推荐，但仍不绑 Telegram）

把“管理权限”单独分离成一个 **只在服务端配置的管理口令**（不同于面板密码），例如：

- `MINIAPP_PANEL_ADMIN_PASSWORD`

管理接口（list/revoke）要求额外带这个口令（或二次输入）。

> 这不是“多余兜底”，而是把“可用性（面板登录）”和“权限（改名单）”拆开，防止面板密码扩散后被反客为主。

是否采用由你拍板。

---

## 7. 存储：白名单放哪

你要“可见可撤销”，最直接的存储是一个 JSON 文件（或你现有 whitelist_store）。

建议字段：

```json
{
  "items": [
    { "id": "device:xxxxxxxx", "added_at": "2026-03-25T12:00:00+08:00", "note": "Chrome@PC" },
    { "id": "tg:12345678", "added_at": "...", "note": "Telegram" }
  ]
}
```

要求：

- 修改要加锁（避免并发写坏）
- 每次请求都以存储为准（撤销立刻 403 的关键）

---

## 8. 失败码（避免“不明 Bug”）

服务端拒绝时必须返回结构化错误：

- `401 panel_token_missing`：未携带 token
- `401 panel_token_invalid`：token 签名不对/过期
- `403 not_trusted`：token 解析出主体，但主体已被撤销（立刻生效）
- `503 panel_auth_misconfigured`：服务端未配置完整

前端只根据 `code` 做行为：

- `panel_token_invalid`：清 token，回到登录页
- `not_trusted`：提示“已被撤销，需要重新验证”

---

## 9. 最小自测清单（上线前必须过）

1. **首次打开**（无 token）：跳转登录页
2. **两层验证正确**：进入面板；刷新页面仍可用
3. **日志 SSE**：能连上（query 带 token）
4. **背景图/预览图**：能加载（query 带 token）
5. **撤销**：在管理页撤销当前设备后，当前设备下一次请求立刻 **403 not_trusted**

---

## 10. 你关心的两个问题的答案（按本方案）

### 10.1 “我在别的浏览器登录 Miniapp，也是看这个吗？”

是的——按本方案，**每个浏览器=一个 device 主体**。你在别的浏览器首次进入，会再次走两层验证；通过后该浏览器进入白名单。

### 10.2 “撤销立刻 403”

可以做到：因为每次请求都查白名单，撤销后立即生效，下一次请求直接 403（`not_trusted`）。

