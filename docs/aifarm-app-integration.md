# AI 农场原生 App 接入

当前状态（2026-07-17）：人类 `humanUrl` 与渡的 `playUrl` 双入口后端已通过提交 `4f02b5b4` 部署到线上。`du-aifarm.service` 只监听 `127.0.0.1:8080`，网关与 SumiTalk worker 已加载农场路由和常驻单工具 `farm({action, ...参数})`。线上尚未创建玩家农场或 App 会话；第一次由原生 App 或渡明确进入时才创建「渡的小农场」。MiniApp 不显示或加载 AI 农场。

## 目标

把 `tutusagi/aifarm-oss` 的双入口完整接入现有产品：辛玥从 `sumitalk-android-native` 的 Compose 游戏大厅进入人类 HTML 前端，渡通过网关工具使用上游 `playUrl` 操作同一座农场。当前不做群聊专用玩法或笨笨参与，也不改上游玩法和数值。

## 当前链路

1. 原生游戏大厅读取 `GET /miniapp-api/aifarm/session`，只显示运行与建档状态，不会因此创建农场。
2. 辛玥点击「AI 农场」后，原生 App 通过现有 `MiniAppGatewayHttpClient` 鉴权调用 `POST /miniapp-api/aifarm/session`；首次创建「渡的小农场」，以后复用本地会话。
3. 原生 App 在专用 WebView 中打开 `/aifarm/ui/<humanKey>`；页面不带通用浏览器的地址栏、历史、下载或渡控制能力。
4. 网关只把带合法 `humanKey` 的人类 UI 路由转发给 `127.0.0.1:8080`，并把页面链接、表单 action 和 303 跳转改回 `/aifarm/ui/...`。
5. 网关常驻注入与上游 MCP 一致的单工具 `farm`；渡把动作名放在 `action`，其它参数平铺，执行器使用本机会话中的私有 `playUrl` 请求 `/a/<agentKey>/<action>`。首次由渡调用时也可创建同一座农场，之后与 App 复用会话；首次建档由进程内锁和 `fcntl` 文件锁共同保护，Web 与独立 SumiTalk worker 并发进入也只会创建一次。
6. `playUrl` 只提取 `/a/<agentKey>` 能力路径，真实请求固定发往 `AIFARM_UPSTREAM_URL`；工具结果只返回动作文字及可选安全状态，不返回 `playUrl`、agent key、human key 或主 token。

## 文件与状态

- 上游运行包：`vendor/aifarm-oss/`，来源和下游监听补丁见 `vendor/aifarm-oss/UPSTREAM.md`。
- sidecar 启动：`scripts/start_aifarm.sh`，默认只监听 `127.0.0.1:8080`。
- 本地农场存档：`vendor/aifarm-oss/data/*.json`，由上游自己的 `.gitignore` 排除。
- App 会话：`data/aifarm_app_session.json`，保存 `human_key`、私有 `play_url` 和校验后的 `agent_path`；文件权限设为 `0600`，原生端与模型结果绝不返回这些能力凭据。
- 网关接缝：`services/aifarm_bridge.py`、`services/aifarm_tool.py`、`services/gateway_tools.py`、`services/chat_tools.py`、`routes/aifarm_proxy.py`、`routes/miniapp/aifarm.py`。
- sidecar 服务安装：`scripts/install_aifarm_service.sh` 安装并 enable `du-aifarm.service`，但不会直接启动；服务强制监听 `127.0.0.1:8080`。
- 原生入口：`sumitalk-android-native/app/src/main/java/com/sumitalk/nativeapp/ui/detail/GameHallScreen.kt`。
- 原生页面：`sumitalk-android-native/app/src/main/java/com/sumitalk/nativeapp/ui/game/AIFarmScreen.kt`；只允许在同一 origin 的 `/aifarm/ui/` 能力路径内导航，TLS 或主页面加载错误会显示明确重试。
- 原生协议：`sumitalk-android-native/app/src/main/java/com/sumitalk/nativeapp/data/gateway/GameToolsGatewayClient.kt`。
- MiniApp 边界：误建的 `AIFarmTab.tsx` 已删除，`GamesHubTab.tsx` / `AppShell.tsx` 的农场卡片、状态请求和路由已移除；网关 session API 仍保留给原生 App 使用。

## 安全边界

- 8080 默认只监听 loopback，不能直接暴露公网。
- 公网代理不开放 `/farms`、`/a`、`/agent`、`/mcp` 或根页面，只开放人类 `/ui` 的已知页面与表单动作。
- `humanKey` 是上游定义的低权限页面钥匙；创建农场仍必须走已鉴权的 App API。
- `playUrl` / agent key 只保存在服务端本地状态；即使状态里的 URL origin 被篡改，执行器也只使用经过格式校验的 `/a/<agentKey>` 路径并固定请求本机配置的 sidecar。
- 会话状态和对应 `.lock` 均使用 `0600`；写入先落同目录临时文件再原子替换，跨进程首次建档在文件锁内二次读状态，避免 App 与渡各建一座。
- 渡的工具不允许执行 `new-token`，避免主 token 进入模型工具结果或聊天存档；普通玩法、探险、串门和社交动作按上游 parity 契约透传。
- 原生 WebView 只为受限农场页面开启上游前端必需的 JavaScript；DOM storage、文件访问、第三方 Cookie 与 mixed content 关闭，主导航和子资源请求都只能留在当前网关的 `/aifarm/ui/` 路径内。
- 路径转发有显式 allowlist，拒绝未知段和路径穿越。
- 当前没有 R2、模型调用、群聊注入或共同游戏活动时间写入。

## 配置

- `AIFARM_UPSTREAM_URL`：网关访问 sidecar 的地址，默认 `http://127.0.0.1:8080`。
- `AIFARM_STATE_FILE`：App 会话文件，默认 `data/aifarm_app_session.json`。
- `AIFARM_FARM_NAME` / `AIFARM_AI_NAME` / `AIFARM_HUMAN_NAME`：首次建档名称，默认「渡的小农场 / 渡 / 辛玥」。
- `AIFARM_PORT` / `AIFARM_BIND_HOST` / `AIFARM_RUNTIME_DIR`：启动脚本使用的端口、监听地址和运行包目录。

## 本地验证

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest scripts.test_aifarm_bridge
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile services/aifarm_bridge.py services/aifarm_tool.py routes/aifarm_proxy.py routes/miniapp/aifarm.py
bash -n scripts/start_aifarm.sh scripts/install_aifarm_service.sh
cd vendor/aifarm-oss && npm ci && npm run check

# 在 sumitalk-android-native 的干净临时 worktree 中
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ANDROID_HOME='/Users/doraemon/Library/Android/sdk' \
  ./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:assembleDebugAndroidTest
```

`scripts.test_aifarm_bridge.AIFarmRealSidecarTest` 会复制运行包到临时目录、使用随机本机端口和临时网关状态文件，先让 6 个独立 Python 进程同时首次建档并确认只得到一个农场，再实际执行“plant → status”，随后销毁全部临时数据；不能改成拿现有或线上农场存档做测试。

## 未完成 / 下次继续

- 尚未通过真实原生 App 鉴权请求验证线上 GET/POST，也未用真实线上模型调用 `farm`；第一次由 App 或渡进入时才创建「渡的小农场」。
- 当前没有群聊专用农场编排、笨笨玩家或多农场身份切换；渡只操作本地会话绑定的这一座农场。
- 本次只发布 `du-gateway` 后端，没有改动、提交或推送原生仓库；原生端状态继续由原生仓库单独确认。
- 线上当前没有 `data/aifarm_app_session.json`，sidecar 玩家农场数为 0；不要为了探测而主动 POST session、调用模型或拿共享存档做测试。
