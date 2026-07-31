# 瓶中生态原生 App 接入

## 上游与许可

- 上游仓库：`https://github.com/Zizuixixiang/cedareco`
- 固定提交：`e600958941883a8be2cafe69f8b431bd64b71d03`
- 运行包：`vendor/cedareco/`
- 许可：PolyForm Noncommercial License 1.0.0
- Required Notice：`Copyright (c) 2026 南山君 (https://github.com/Zizuixixiang/cedareco)`

`vendor/cedareco/LICENSE`、上游 README 和 Required Notice 必须随运行包保留。该许可禁止商业用途；改变产品用途或分发方式前需重新核对许可。

## 运行模型

瓶中生态以独立 Python sidecar 运行。一个 sidecar 进程对应一座池塘：

- 官方 Web 前端和渡的 `cedareco(command)` 工具均访问同一个 sidecar。
- 存档固定为 `data/cedareco/eco_save.json`，不会分别建立网页存档和 AI 存档。
- App 打开观察窗只创建或复用随机能力 key，不执行 `new`，因此不会重置已有池塘。
- 上游引擎、指令、图鉴、年鉴和六个灾害小游戏保持原样。
- 下游调整 `vendor/cedareco/web/index.html`、`web/style.css` 与 `web/app.js`：前端固定使用当前受保护挂载路径，不能切换到另一台服务；原生观察窗内不再重复网页页头、刷新和无效服务器选择，池塘/图鉴/年鉴以移动端分段导航真实互斥切换。

## 网关入口

### App session

- `GET /miniapp-api/cedareco/session`
  - 返回 `configured`、`running`、池塘名、天数、季节、评分和当前存活物种数。
- `POST /miniapp-api/cedareco/session`
  - sidecar 在线时创建或复用能力 key，返回 `/cedareco/ui/<human_key>/`。
  - sidecar 离线时返回 503，不创建新池塘、不改存档。

session 能力记录保存在 `data/cedareco_app_session.json`，使用进程锁与文件锁串行创建，文件权限为 0600。

### Web/API 代理

`routes/cedareco_proxy.py` 将以下路径转发到 loopback sidecar：

- 页面根路径、`app.js`、`style.css`
- `assets/**`
- `api/**` 的 GET/POST

路径必须携带当前有效的 32 位能力 key；无效 key 或挂载范围外路径返回 404。sidecar 只监听 `127.0.0.1:8765`，不直接暴露公网端口。

### 渡的工具

`services/cedareco_tool.py` 注册一个 `cedareco(command)` 工具，由 `services/chat_tools.py` 分派。`command` 原样交给上游引擎；网关不新增指令白名单、长度、轮数或降级逻辑。

## 原生 App

- `GameHallScreen.kt`
  - 游戏大厅增加池塘绿色“瓶中生态”卡片。
  - 在线时展示天数、季节和当前存活物种数；离线时展示“未启动”。
- `GameToolsGatewayClient.kt`
  - 读取 session 状态并解析能力地址。
- `CedarEcoScreen.kt`
  - 原生自然博物志窄页头包裹官方完整 Web 前端。
  - WebView 仅允许当前 scheme、host、port 和能力路径前缀，禁止文件访问、内容访问和 mixed content。
  - 返回键优先回退 WebView 历史，再回游戏大厅。

本接入不使用旧 MiniApp 植物大战僵尸 UI，也不新增 CedarEco MiniApp 页面。

## sidecar 脚本

本地直接启动：

```bash
scripts/start_cedareco.sh
```

安装 systemd unit：

```bash
sudo bash scripts/install_cedareco_service.sh
sudo systemctl start du-cedareco.service
```

安装脚本只写入并 enable `du-cedareco.service`，不会自动启动或重启服务。

可配置环境变量：

- `CEDARECO_UPSTREAM_URL`
- `CEDARECO_SESSION_FILE`
- `CEDARECO_POND_NAME`
- `CEDARECO_RUNTIME_DIR`
- `CEDARECO_DATA_DIR`
- `CEDARECO_SAVE_FILE`
- `CEDARECO_HOST`
- `CEDARECO_PORT`
- `CEDARECO_ALLOWED_ORIGIN`
- `CEDARECO_PYTHON`

## 已执行验证

- 固定网关 HEAD 加限定 CedarEco 运行 diff 的 detached 工作树：
  - Python 编译、shell 语法、Flask 路由注册和工具注入通过。
  - 临时 sidecar 上完成能力地址、完整页面、JavaScript、中文图片、状态 API、渡的命令和共享临时存档联调。
  - sidecar 停止后，状态正确显示离线，启动入口与受保护页面返回 503。
- 固定原生 HEAD 加全部确认保留的运行 diff 的 detached 工作树：
  - `:app:compileDebugKotlin` 通过。
  - 仅出现既有通知 API 的弃用警告。

上述验证不等于已提交、已推送、已部署、已构建 APK 或已在真机验收。
