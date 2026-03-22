# Miniapp 功能路线图（可交接）

本文用于后续 Agent 交接，约定 Miniapp 的三批次功能范围、数据结构、接口和验收标准。

## 总体原则

- 低耦合：新功能尽量通过独立 API + R2 JSON，不改主聊天主链路。
- 可降级：任一模块失败时显示“暂无”，不影响页面打开。
- 低频计算：周报/温度按天或按周更新，避免高频实时计算。
- 可追踪：关键生成结果要有 `updated_at`，便于排查。

---

## 第一批（已执行，持续打磨）

### 目标

- 首页气泡下新增“每周小报告”折叠栏。
- 树模块新增“心情温度计”。

### 数据键（R2）

- `global/miniapp_weekly_report.json`
- `global/miniapp_mood_meter.json`

### API（后端）

- `GET /miniapp-api/weekly-report`
- `POST /miniapp-api/weekly-report/refresh`
- `GET /miniapp-api/mood-meter`
- `POST /miniapp-api/mood-meter/refresh`

### UI（前端）

- 首页：周报折叠栏（摘要 + 详情 + 刷新按钮）
- 树弹窗：心情温度卡片（含刷新）

### 第一批后续小优化（待做）

- 周报支持“本周/上周”切换。
- 心情温度支持迷你折线图（当前为文本列表）。

---

## 第二批（已落地 · 徽章 + 树联动）

### 成就徽章系统

- 目标：增加趣味反馈，不影响主链路。
- 示例徽章：
  - 连续聊天 7 天
  - 本周提醒触发 ≥5 次（`schedule/fired` 按 occurrence 日期落在本周）
  - 累积 3 天用户消息含「晚安」
- 数据键建议：
  - `global/miniapp_badges.json`
- API 建议：
  - `GET /miniapp-api/badges`
  - `POST /miniapp-api/badges/refresh`
- UI 建议：
  - 首页周报下方展示徽章墙（含进度与刷新）。

### 树联动（轻量）

- 徽章或周报可对树做轻量彩蛋联动（如光效或飘花）。
- 禁止把树成长核心逻辑和徽章强绑定，避免牵一发而动全身。
- **已实现**：`GET /miniapp-api/cyber-tree` 返回 `badgeFx`；至少点亮一枚徽章时树 SVG 有轻微光点动画（`GrowthTreeSVG` 的 `sparkle`）。

---

## 第三批（计划）

### 时间胶囊

- 目标：增强仪式感（按月写入、次月解锁）。
- 数据键建议：
  - `global/miniapp_time_capsule.json`
- 核心字段建议：
  - `month_key`
  - `content`
  - `created_at`
  - `unlock_at`
  - `status`（locked/unlocked）
- API 建议：
  - `GET /miniapp-api/time-capsule`
  - `POST /miniapp-api/time-capsule/create`
  - `POST /miniapp-api/time-capsule/unlock`（可由调度触发）

### 设计要求

- 入口明确，避免与记事本混淆。
- 未解锁内容仅显示占位，避免剧透。

---

## 验收标准（跨批次）

- 页面可打开，不因任一模块失败白屏。
- 接口失败有兜底文案。
- 数据结构可回放、可排查（带 `updated_at`）。
- 各模块独立可开关（后续可加 env flag）。

---

## 交接提示

- 第一批已落地在以下核心文件：
  - `routes/miniapp_api.py`
  - `storage/r2_store.py`
  - `miniapp/src/ui/App.tsx`
- 后续 Agent 优先在上述文件扩展，避免分散实现。
- 每次改 UI 后需执行 `miniapp` 构建，确保 `miniapp_static` 同步更新。
