# 文游开源分发方案

本文档只记录开源版的产品形态和接入边界，不绑定当前私有后端实现。

文游开源时建议拆成两个版本：

1. 单 HTML 懒人版：打开即用，适合本地试玩和低门槛体验。
2. 完整开源版：前后端、内容表和规则引擎完整开放，适合二次开发和接入自有系统。

两者共享同一套规则文档、内容表字段和运行时契约，但目标用户、部署方式和安全边界不同。

## 版本 A：单 HTML 懒人版

单 HTML 版的目标是“最快能玩起来”，不是正式生产部署。

建议文件名：

```text
wenyou-standalone.html
```

适合：

- 不想部署后端，只想本地试玩的人。
- 想快速测试副本生成、GM 叙事和基础规则的人。
- 官方 Chat、Claude、其他 Agent 用户，想通过工具桥或 MCP 适配层参与文游的人。
- 开源仓库首页提供的最小体验入口。

不适合：

- 公开网站部署。
- 多用户共享存档。
- 隐藏 API Key 的正式服务。
- 大型内容表、复杂权限、多人账号体系。

### 单 HTML 应包含的功能

- 主界面：
  - 副本日志。
  - 行动输入。
  - 行动选项按钮。
  - 对讲机入口。
  - 背包面板。
  - 角色面板。
  - 结算预览。
- 配置面板：
  - GM API Base URL。
  - GM API Key。
  - GM 模型名。
  - AI 玩家 API Base URL。
  - AI 玩家 API Key。
  - AI 玩家模型名。
  - 文游后端地址，可选。
  - 文游后端 Token，可选。
  - 工具桥地址，可选。
  - MCP 适配地址，可选。
- 本地数据：
  - `localStorage` 保存当前配置和存档。
  - 支持导入/导出存档 JSON。
  - 支持导入/导出内容表 JSON。
- 默认内容：
  - 内置一份最小道具表。
  - 内置一份最小能力表。
  - 内置一份新手副本。
  - 内置基础结算和奖励规则。

### 单 HTML 的安全说明

单 HTML 版允许用户直接填写 API Key，但必须明确提示：

- API Key 会出现在浏览器环境中。
- 本地自用可以接受，公开部署不安全。
- 如果要给别人用，应使用自己的后端代理 LLM 请求。
- 不要把填好真实 API Key 的 HTML 文件直接分享出去。

推荐在配置面板里显示短提示：

```text
单 HTML 版适合本地试玩。浏览器会持有你的 API Key，公开部署前请改用后端代理。
```

### 单 HTML 的运行模式

单 HTML 可以支持三种运行模式：

| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| 本地纯前端 | 浏览器保存存档，直接请求用户填写的 LLM API | 个人试玩 |
| 前端 + 文游后端 | HTML 只负责 UI，规则和存档交给后端 | 轻量部署 |
| 前端 + 工具桥/MCP 适配 | 官方 Chat 或其他 Agent 通过工具接口参与 | 外部 AI 玩家 |

本地纯前端模式可以做得简陋，但要保留稳定数据结构，方便以后迁移到完整后端。

### 单 HTML 的推荐目录

即使是单文件，也建议在仓库中这样组织：

```text
standalone/
  wenyou-standalone.html
  README.md
  examples/
    save.example.json
    config.example.json
```

`wenyou-standalone.html` 可以内联 CSS 和 JS。后续如果变大，再拆成正式前端。

## 版本 B：完整开源版

完整开源版的目标是“可部署、可二开、可接自有系统”。

适合：

- 想把文游接进自己网站、App、小程序或 Bot 的开发者。
- 想替换数据库、LLM、前端 UI、内容表的人。
- 想扩写副本、道具、怪物、奖励和成长系统的人。
- 想接入官方 Chat、Claude、Cursor 或其他 Agent 的人。

完整开源版不应该要求别人使用当前私有后端。它应该提供清楚的边界，让接入方可以替换任何一层。

### 完整开源版建议目录

```text
wenyou/
  frontend/
    web/
    mobile/
  backend/
    api/
    rules/
    gm/
    storage/
  content/
    default/
      items.json
      abilities.json
      reward_tables.json
      instance_seeds.json
  schemas/
    item.schema.json
    ability.schema.json
    reward_table.schema.json
    save.schema.json
  adapters/
    openai-compatible.md
    custom-backend.md
    mcp-server.md
    agent-tool-bridge.md
  docs/
    rules/
    integration/
    deployment/
```

### 完整开源版必须开放的内容

- 规则文档：
  - 核心循环。
  - 数值成长。
  - 道具/能力。
  - 商店/抽卡。
  - 结算奖励。
  - 怪物与遭遇。
  - 惩罚副本。
- 内容表：
  - 道具表。
  - 能力表。
  - 奖励表。
  - 默认副本种子。
  - 默认怪物模板。
- 后端契约：
  - session/save 结构。
  - `public_state / gm_state / rules_state` 分层。
  - `state_patch` 格式。
  - GM 输入输出边界。
  - Rules Engine 函数边界。
- AI 玩家契约：
  - 玩家二身份映射。
  - AI 玩家上下文。
  - 工具调用。
  - 消费流水。
  - 对讲机频道。
- 适配器：
  - OpenAI-compatible Chat Completions。
  - 自定义后端。
  - SQLite 默认存储。
  - 自定义存储适配器。
  - 外部 AI 工具桥。
  - 可选 MCP Server。

### 存储边界

完整开源版默认可以用 SQLite 跑起来。SQLite 负责当前存档、长期钱包、已归档副本、候选池、连续性卡片和玩家流水；远程对象存储只作为可选备份，不作为必须依赖。

推荐把存储层收敛为一个可替换适配器：

```text
WenyouStore
  get_session / save_session / delete_session
  get_wallet / save_wallet
  save_archive / list_archives / get_archive
  get_candidates / save_candidates
  get_card / save_card
```

接入方只要实现这组接口，就可以把默认 SQLite 换成自己的数据库。

## HTTP 工具桥和 MCP 的定位

文游不应该把 MCP 当作唯一入口。

推荐分层：

| 层 | 用途 | 是否必须 |
| --- | --- | --- |
| HTTP API | 前端和后端之间的主通信协议 | 必须 |
| HTTP 工具桥 | 外部 AI 玩家读取上下文、调用工具 | 推荐 |
| MCP Server | 给官方 Chat、Claude、Cursor 等 Agent 使用 | 可选 |

### HTTP 工具桥

HTTP 工具桥是文游自己的轻量协议，推荐协议名：

```text
wenyou-ai-player-tools-v1
```

它不是标准 MCP 服务。它只负责：

- 获取 AI 玩家上下文。
- 获取工具 schema。
- 提交工具调用。
- 返回规则层结果。

推荐入口：

```text
GET  /wenyou/ai-player/tools?actor_id=player2
POST /wenyou/ai-player/tool-call
GET  /wenyou/ai-player/sse?actor_id=player2
```

旧的 `/mcp/*` 命名如果存在，只应作为兼容别名，不作为开源推荐接口。

### MCP Server

MCP 适合作为高级接入层，用来让外部 Agent 玩文游。

MCP Server 可以提供这些工具：

| 工具 | 作用 |
| --- | --- |
| `get_game_state` | 获取当前公开局面 |
| `submit_action` | 提交玩家行动 |
| `send_radio_message` | 发送对讲机消息 |
| `get_inventory` | 查看背包 |
| `use_item` | 使用道具 |
| `transfer` | 转交积分或物品 |
| `buy_item` | 购买商店物品 |
| `roll_gacha` | 抽卡 |
| `export_save` | 导出存档 |

MCP Server 不应该绕过 Rules Engine。所有积分、背包、道具、结算、奖励和状态变化仍由规则层判断。

### MCP 不建议放进纯 HTML

纯 HTML 可以连接一个已有的 MCP/工具桥适配服务，但不建议自己实现完整 MCP Server。

原因：

- 浏览器端密钥和鉴权难保护。
- MCP Server 通常需要稳定进程。
- 外部 Agent 调用需要可访问的服务地址。
- 工具执行最终仍要落到规则层和存档层。

因此：

- 单 HTML 版只做“连接 MCP/工具桥”的配置入口。
- 完整开源版提供可选 `mcp-server` 适配器。

## 后端适配边界

开源版应该允许接入方替换后端。

后端至少需要实现：

| 能力 | 说明 |
| --- | --- |
| 会话读写 | 读取和保存当前游戏 session |
| 角色读写 | 玩家一、玩家二角色卡 |
| 背包读写 | 玩家个人背包和任务物品 |
| 钱包读写 | 玩家个人积分、债务、抽卡保底 |
| 内容表读取 | 道具、能力、奖励、怪物和副本种子 |
| Rules Engine | 执行数值和状态变化 |
| GM 调用 | 调用叙事模型 |
| AI 玩家调用 | 可选，调用玩家二模型 |
| 工具桥 | 可选，给外部 AI 玩家使用 |
| MCP Server | 可选，给外部 Agent 使用 |

最小后端可以很薄，但必须遵守：

- GM 不能直接改积分、背包、属性和结算结果。
- AI 玩家不能直接改真实玩家资源。
- 所有状态变化必须形成 `state_patch` 或等价结构。
- 前端只展示后端返回的公开状态。

## 单 HTML 到完整后端的迁移

单 HTML 版的存档结构应尽量贴近完整后端。

建议至少保留这些字段：

```json
{
  "schema_version": "wenyou_save_v1",
  "session": {},
  "wallet": {},
  "content_refs": {},
  "settings": {},
  "exported_at": ""
}
```

迁移时：

1. 导出 HTML 本地存档。
2. 完整后端导入 JSON。
3. 后端校验 schema。
4. 后端补齐缺失字段。
5. 重新生成公开面板和运行时缓存。

## README 推荐写法

开源首页应该直接告诉用户有两个版本：

```text
文游提供两种运行方式：

1. 单 HTML 懒人版
   打开 wenyou-standalone.html，填 API 地址和 Key，即可本地试玩。

2. 完整开源版
   部署 backend + frontend，导入默认内容表，可替换自己的数据库、LLM、前端和规则扩展。
```

不要把两个版本混成一个入口。单 HTML 是玩具和演示，完整开源版是系统和骨架。

## 暂不做的事

第一阶段不建议做：

- 在纯 HTML 中实现完整多人账号系统。
- 在纯 HTML 中隐藏平台 API Key。
- 把 MCP 当成唯一通信协议。
- 让 GM 直接写背包、积分、掉落和结算。
- 让 AI 玩家读取隐藏状态或全量内容表。
- 把当前私有后端路径写成开源唯一标准。

这些都可以后续扩展，但不要挡住第一版开源体验。
