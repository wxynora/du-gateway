# 后端拆分与 FastAPI 迁移计划

目标：先降低故障风险和调试成本，再迁移到 FastAPI + async。每一步都要求行为保持一致，能单独提交、单独回滚。

## 原则

1. 不做一次性全量重写。
2. 先拆边界，再改框架。
3. 先迁低风险接口，最后迁 chat 主链路。
4. 每次只动一个功能域，保留旧入口兼容。
5. 每步完成后至少跑语法检查；涉及 Android/前端时跑对应构建。
6. 生产部署始终保留回滚路径。

## 当前状态

- Web API 已从 Flask dev server 切到 gunicorn。
- 实时服务 `du-realtime` 已独立为 FastAPI/Uvicorn 进程。
- 日历闹钟调度已从 Web worker 挪到 `du-telegram-proactive`。
- SumiTalk Android 后台消息检查已改为轻量 latest 轮询。
- APK 壳已改为加载服务器 `/miniapp/`，后续 UI 更新不必每次重新打包。

## 阶段 0：止血与运行边界

状态：进行中。

- [x] gunicorn 承接 Flask API。
- [x] `du-realtime` 独立运行。
- [x] Web worker 默认不启动内嵌日历调度。
- [x] `du-telegram-proactive` 接管日历 tick。
- [x] SumiTalk 后台轻量轮询。
- [ ] 日志轮转或日志体积控制。
- [ ] 诊断页适配 systemd/gunicorn/realtime 的最终状态展示。

## 阶段 1：拆 `routes/miniapp_api.py`

目标：先把 4000 行路由按功能域拆出去，不改接口路径。

建议顺序：

1. `routes/miniapp/diagnostics.py`（已完成）
   - 迁移 `/diagnostics` 相关逻辑。
   - 风险低，适合作为第一刀。

2. `routes/miniapp/sumitalk_history.py`（已完成）
   - 迁移 `/sumitalk-history*`。
   - 包括 full history、latest、migrate、save。

3. `routes/miniapp/device_actions.py`（已完成）
   - 迁移 `/device-actions*`。
   - 保留唤醒渡的回执逻辑。

4. `routes/miniapp/device_state.py`（已完成）
   - 迁移 `/device-state/*` 和截图接口。

5. `routes/miniapp/panel_auth.py`（已完成）
   - 迁移 panel auth 和 trusted devices。

6. `routes/miniapp/logs.py`（已完成）
   - 迁移 `/logs*` 和 `/client-error`。

7. `routes/miniapp/upstreams.py`（已完成）
   - 迁移上游列表、探活、切换、模型选择。

验收：

- 原 URL 不变。
- `python3 -m py_compile routes/miniapp_api.py routes/miniapp/*.py` 通过。
- 手机面板能打开，诊断页能刷新。

## 阶段 2：拆 `storage/r2_store.py`

目标：把 R2 读写按数据域拆开，同时保留旧函数名转发，避免全项目大改。

建议结构：

- `storage/r2/history_store.py`
- `storage/r2/device_store.py`
- `storage/r2/action_store.py`
- `storage/r2/memory_store.py`
- `storage/r2/settings_store.py`
- `storage/r2/assets_store.py`

迁移方式：

1. 新模块先实现函数。
2. `r2_store.py` 保留原函数，内部调用新模块。
3. 再逐步把调用方改到新模块。
4. 最后清理 `r2_store.py`。

## 阶段 3：拆 `miniapp/src/ui/App.tsx`

目标：前端大壳瘦身，先拆视图和 hooks，不改变 UI 行为。

建议顺序：

1. SumiTalk 聊天状态和请求逻辑。
2. 诊断页与日志页入口。
3. 设置页和上游设置。
4. 消息渲染组件。
5. 主布局和导航状态。

验收：

- `npm run build` 通过。
- 服务器部署后手机网页 UI 正常加载。

## 阶段 4：FastAPI 外壳

目标：新建正式 API app，但不急着替换 chat。

建议新增：

- `services/api_app.py`
- `routes_fastapi/health.py`
- `routes_fastapi/miniapp/*.py`
- 统一 auth、CORS、错误响应、日志中间件。

先迁接口：

1. `/health`
2. 诊断类只读接口
3. settings/upstreams
4. device state/actions
5. sumitalk history

## 阶段 5：实时链路

目标：让 `du-realtime` 从辅助服务变成正式设备实时通道。

- WebSocket 推送 assistant message。
- WebSocket 推送 device actions。
- Android 回传 action results。
- 旧轮询保留为兜底。

## 阶段 6：最后迁 `routes/chat.py`

这是最高风险阶段，最后做。

拆分目标：

- chat request normalization
- prompt/system 注入
- upstream target selection
- OpenAI/Claude 格式转换
- streaming parser
- tool trace / tool result
- reasoning/thinking 收集
- archive/R2 存档
- fallback/error mapping

迁移要求：

- 先抽纯函数和服务层。
- 再用 `httpx.AsyncClient` 替换 `requests`。
- 最后挂到 FastAPI endpoint。

## 每次开工检查

开工前：

```bash
git status --short
```

验证：

```bash
python3 -m py_compile app.py routes/miniapp_api.py
```

涉及前端：

```bash
cd miniapp
npm run build
```

涉及 Android：

```bash
cd miniapp/android
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew :app:assembleDebug
```

部署后：

```bash
systemctl status du-gateway du-realtime du-telegram-proactive --no-pager
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5010/health
```

## 下一步

第一刀建议拆 `routes/miniapp_api.py` 的 diagnostics 逻辑。它独立、风险低，拆完可以立刻验证诊断页。
