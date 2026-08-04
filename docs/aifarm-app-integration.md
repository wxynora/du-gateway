# AI 农场原生 App 接入

当前状态（2026-08-02）：原私有 sidecar 的 `PQQCHR / 渡的小农场` 已完整迁入自有公共服，新公共门牌为 `3ET3FE`。网关与 SumiTalk worker 仅通过农场专用 `AIFARM_UPSTREAM_URL=https://doorbellcommons.com/farm` 访问公共实例；聊天、模型与网关上游没有改变。原生 App 与渡继续复用同一个服务端会话，旧 `du-aifarm.service` 已停用。公共服代码归档到独立 `doorbell-commons/old-vps/farm/`，网关仓库不再携带农场运行包或 sidecar 启动脚本。MiniApp 不显示或加载 AI 农场。

## 目标

把 `tutusagi/aifarm-oss` 的双入口完整接入现有产品：辛玥从 `sumitalk-android-native` 的 Compose 游戏大厅进入人类 HTML 前端，渡通过网关工具使用上游 `playUrl` 操作同一座农场。当前不做群聊专用玩法或笨笨参与，也不改上游玩法和数值。

## 当前链路

1. 原生游戏大厅读取 `GET /miniapp-api/aifarm/session`，只显示公共农场运行与会话状态，不会创建新农场。
2. 辛玥点击「AI 农场」后，原生 App 通过现有 `MiniAppGatewayHttpClient` 鉴权调用 `POST /miniapp-api/aifarm/session`；当前会话直接复用公共门牌 `3ET3FE / 渡的小农场`。
3. 原生 App 在专用 WebView 中打开 `/aifarm/ui/<humanKey>`；页面不带通用浏览器的地址栏、历史、下载或渡控制能力。
4. 网关只把带合法 `humanKey` 的人类 UI 路由转发给自有公共农场；页面链接、表单 action，以及相对或由公共 nginx 生成的同上游 origin 绝对 303 跳转，都会先去掉 `AIFARM_UPSTREAM_URL` 自带的路径前缀，因此公共服的 `/farm/ui/...` 与原无前缀实例的 `/ui/...` 都会改回 App 允许的 `/aifarm/ui/...`，并保留原 query/fragment；其它 origin 不改写。
5. 网关不再维护农场动作目录、参数表或 GET/POST 分类。每次组装模型工具时，使用服务端会话里已有的私有 agent key 请求公共服 `/mcp/<agentKey>` 的 JSON-RPC `tools/list`，把返回的唯一 `farm` 工具 `name/description/inputSchema` 原样映射为模型函数；执行时把模型参数原样交给同一端点的 `tools/call`。App 与独立 SumiTalk worker 读取同一个 0600 会话文件，因此始终操作同一座公共农场。
6. `playUrl` 仍只提取并校验 `/a/<agentKey>` 能力路径，MCP 路径只由这个已校验 key 派生，真实请求固定发往 `AIFARM_UPSTREAM_URL`。最近一次成功取得的完整 MCP tool schema 保存在同一会话文件中；平时每轮成功读取后只在内容变化时更新，公共服维护或临时不可用时继续注入该缓存，真正调用 `tools/call` 时返回普通工具错误，恢复后下一轮自动刷新。工具结果直接保留公共服 MCP 的 `content/isError`，不返回 MCP URL、agent key、human key 或主 token。

## 文件与状态

- 公共服代码归属：`/Users/doraemon/Downloads/doorbell-commons/old-vps/farm/` 保存从旧 VPS 拉取的当前非秘密运行快照和 service unit；生产仍独立运行在旧 VPS `/opt/aifarm`，数据仍只在 `/var/lib/aifarm`。
- 网关仓库已删除原 tracked `vendor/aifarm-oss/` 运行包与 `scripts/start_aifarm.sh`、`scripts/install_aifarm_service.sh`；生产 `du-aifarm.service` 继续保持 disabled/inactive。
- 原私有农场的未跟踪 `vendor/aifarm-oss/data/farms.json`、`ugc.json` 暂留作旧备份，不参与当前运行或部署；其实际权限为 0644，后续删除或移出仓库目录需单独确认。
- App 会话：`data/aifarm_app_session.json`，保存 `human_key`、私有 `play_url`、校验后的 `agent_path` 和最近一次成功取得的完整 `mcp_tools` schema；文件权限设为 `0600`，原生端与模型结果绝不返回这些能力凭据。
- 公共迁入凭据：主网关 `/var/lib/du-aifarm-public-sync/credentials.json`，目录 0700、文件 0600；保存新门牌、规范快照和只显示一次的同步钥匙，不进入仓库。
- 网关接缝：`services/aifarm_bridge.py`、`services/aifarm_tool.py`、`services/gateway_tools.py`、`services/chat_tools.py`、`routes/aifarm_proxy.py`、`routes/miniapp/aifarm.py`。
- 公共服务与迁入说明：`https://doorbellcommons.com/farm/`、`/farm/sync` 与 `/farm/公共农场注册与存档迁入说明.md`；公共运行包和数据位于独立旧 VPS，不属于网关部署包，其代码快照归 `doorbell-commons/old-vps/farm/` 管理。
- 原生入口：`sumitalk-android-native/app/src/main/java/com/sumitalk/nativeapp/ui/detail/GameHallScreen.kt`。
- 原生页面：`sumitalk-android-native/app/src/main/java/com/sumitalk/nativeapp/ui/game/AIFarmScreen.kt`；只允许在同一 origin 的 `/aifarm/ui/` 能力路径内导航，TLS 或主页面加载错误会显示明确重试。
- 原生协议：`sumitalk-android-native/app/src/main/java/com/sumitalk/nativeapp/data/gateway/GameToolsGatewayClient.kt`。
- MiniApp 边界：误建的 `AIFarmTab.tsx` 已删除，`GamesHubTab.tsx` / `AppShell.tsx` 的农场卡片、状态请求和路由已移除；网关 session API 仍保留给原生 App 使用。

## 安全边界

- 公共农场只暴露在自有 `doorbellcommons.com/farm` 路径下；网关、聊天与模型仍使用原有自有链路。
- `humanKey` 是上游定义的低权限页面钥匙；当前 App 只复用已迁入的服务端会话，不在读取状态时新建农场。
- `playUrl` / agent key 只保存在服务端本地状态；即使状态里的 URL origin 被篡改，执行器也只使用经过格式校验的 `/a/<agentKey>` 路径并固定请求配置的公共农场基址。
- 会话状态和对应 `.lock` 均使用 `0600`；写入先落同目录临时文件再原子替换，跨进程首次建档在文件锁内二次读状态，避免 App 与渡各建一座。
- 渡的工具仍在发送 MCP 请求前拒绝 `action=new-token`，避免主 token 进入模型工具结果或聊天存档；除此之外，工具 schema、模型可见说明、动作参数和动作结果均采用公共服 MCP 当前合同，不再追加网关自创说明。
- 原生 WebView 只为受限农场页面开启上游前端必需的 JavaScript；DOM storage、文件访问、第三方 Cookie 与 mixed content 关闭，主导航和子资源请求都只能留在当前网关的 `/aifarm/ui/` 路径内。
- 路径转发有显式 allowlist，拒绝未知段和路径穿越。
- 当前没有 R2、模型调用、群聊注入或共同游戏活动时间写入。

## 配置

- `AIFARM_UPSTREAM_URL`：网关访问农场服务的地址；代码默认仍为 `http://127.0.0.1:8080`，生产网关与 SumiTalk worker 通过各自 systemd drop-in 固定为 `https://doorbellcommons.com/farm`。
- `AIFARM_STATE_FILE`：App 会话文件，默认 `data/aifarm_app_session.json`。
- `AIFARM_FARM_NAME` / `AIFARM_AI_NAME` / `AIFARM_HUMAN_NAME`：首次建档名称，默认「渡的小农场 / 渡 / 辛玥」。

## 本地验证

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/test_aifarm_mcp_bridge.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile services/aifarm_bridge.py services/aifarm_tool.py routes/aifarm_proxy.py routes/miniapp/aifarm.py

# 在 sumitalk-android-native 的干净临时 worktree 中
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ANDROID_HOME='/Users/doraemon/Library/Android/sdk' \
  ./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:assembleDebugAndroidTest
```

## 当前边界

- 已从网关本机验证 5000/5010 健康、公共人类页面代理和停用旧 sidecar 后的独立可用性；尚未做本轮真实原生 App 点击或真实模型 `farm` 调用。
- 当前没有群聊专用农场编排、笨笨玩家或多农场身份切换；渡只操作服务端会话绑定的公共门牌 `3ET3FE`。
- 本次没有改动原生仓库；原生端仍通过既有游戏大厅和网关协议进入。
- 不通过创建线上测试农场验证公共服务。新用户注册与本地存档迁入按公开 `/farm/公共农场注册与存档迁入说明.md` 执行。
