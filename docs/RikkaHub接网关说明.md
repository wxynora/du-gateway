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
这样配置后，RikkaHub 会向「网关的 `/v1/chat/completions` 或 `/chat/completions`」发 POST，由网关处理后再转发。

**当前逻辑**：所有请求统一走完整管道（清洗、注入记忆/总结、转发、存档），无按助手或关键词的开头过滤。

---

**看网关日志/输出：**

| 运行方式 | 在哪看 |
|----------|--------|
| **本机命令行**（`python app.py` 或 `flask run`） | **运行网关的那个终端窗口**，每来一条聊天就多一行。 |
| **服务器 systemd** | `journalctl -u 你的网关服务名 -f`，或该服务的「日志」输出。 |
| **Docker** | `docker logs -f 容器名`。 |
| **云平台**（如 Railway、Render、Fly.io） | 该平台控制台里的 **Logs / 日志** 面板，看标准输出。 |

网关**没有默认写日志文件**，日志只打到**标准输出**。若需要落文件，可运行时重定向，例如：`python app.py >> gateway.log 2>&1`。

**常见情况：RikkaHub 填的是云服务器公网 IP，浏览器能打开 公网IP:5000**

说明网关就是在云服务器上跑的。你用 Git Bash 用 root SSH 连上公网 IP 后，当前终端**已经在云服务器上**了。

- 要看 `chat 收到 window_id=...`，就在这台云服务器上找「跑网关的那个进程」的输出。
- **先确认网关是怎么在跑的**（在 Ubuntu 上执行，前面可加 `sudo`）：
  - `sudo lsof -i :5000` 或 `sudo ss -tlnp | grep 5000`：看谁在监听 5000；
  - 若没有输出，可能网关在别的端口或通过 Nginx 反向代理，可试 `sudo ss -tlnp` 看所有监听端口；
  - `ps aux | grep python`：看有没有 python 进程。
- 操作步骤：
  1. SSH 登录云服务器（任意终端均可，不必非用 Git Bash）。
  2. 看网关是怎么跑的：
     - **直接 `python app.py`**：在 SSH 里进项目目录执行 `python app.py`，日志会打在这个终端；或用 `nohup python app.py >> gateway.log 2>&1 &` 后台跑，然后 `tail -f gateway.log` 看日志。
     - **systemd 服务**：`journalctl -u 服务名 -f`（服务名可 `systemctl list-units --type=service` 里找）。
     - **Docker**：`docker ps` 看容器名，再 `docker logs -f 容器名`。
     - **云平台**（如宝塔、面板等）：在平台里找该应用的**日志/输出**入口。

**在 Ubuntu 云服务器上直接改代码（不用 Git Bash）**

- **改配置/代码**：可以在本机改完 **git push**，到云服务器上执行 **git pull**，再重启网关即可，不必在服务器上用 nano 改。若直接在服务器上改，可用 `nano 文件名`（Ctrl+O 保存，Ctrl+X 退出）。

**Ubuntu 上查「谁在跑、日志在哪」的一键命令（复制整段到 SSH 里执行）**

```bash
echo "=== 监听中的端口（含 5000）==="
sudo ss -tlnp 2>/dev/null | grep -E "5000|LISTEN"
echo "=== 所有 python 进程 ==="
ps aux | grep -E "[p]ython|[f]lask"
echo "=== 当前目录下是否有 gateway.log / nohup.out ==="
ls -la gateway.log nohup.out 2>/dev/null || true
echo "=== 若项目在 /root/du-gateway，看该目录 ==="
ls -la /root/du-gateway/gateway.log /root/du-gateway/nohup.out 2>/dev/null || true
```

若某一段完全没有输出，说明没有对应项（例如没有 gateway.log）；有输出就能看到端口、进程或日志文件路径。

**若 tail -f gateway.log 里连 [Chat] 或 chat 四个字都没出现过**

说明**真正在接请求、在写你看到的那份日志的，不是你在当前目录 nohup 起来的进程**。常见情况：云上另有进程（例如 systemd 服务、或之前起的 nohup）在监听 5000，请求被它接了，你 tail 的可能是它的输出，或你 nohup 的进程根本没收到请求。

按下面在云服务器上执行，确认「谁在监听 5000、用的哪份代码、日志在哪」：

```bash
# 1) 谁在监听 5000（记下 PID 和 命令）
sudo lsof -i :5000
# 或
sudo ss -tlnp | grep 5000

# 2) 该进程的详细信息和启动目录（把 PID 换成上面看到的）
sudo cat /proc/PID/cwd
sudo cat /proc/PID/cmdline | tr '\0' ' '

# 3) 是否有 systemd 在跑网关（若有，日志用 journalctl 看）
systemctl list-units --type=service | grep -iE "gateway|flask|du|chat"
```

若发现是 **systemd 服务**在跑：停掉它再用手动 nohup，或改该服务的代码路径并重启服务，这样你改的代码才会生效、[Chat] 才会出现在你 tail 的日志里。若发现是**另一个 nohup/旧进程**：用 `kill PID` 停掉它，再在当前目录重新 `nohup ./venv/bin/python app.py >> gateway.log 2>&1 &`，再 tail 当前目录的 gateway.log，发请求应能看到 [Chat]。

---

**云服务器一次性配置：虚拟环境 + 后台常驻（以后每次打开不用重弄）**

- **虚拟环境只建一次**：在项目目录执行一次即可，以后不会消失。
  ```bash
  cd /root/du-gateway   # 换成你的项目路径
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt
  ```
  以后要跑网关，用 `./venv/bin/python app.py` 即可，不用再装依赖。

- **让网关在后台一直跑（断开连接也不关）**：这样你每次打开远程，只是看日志或改配置，不用重新启动。
  ```bash
  cd /root/du-gateway
  nohup ./venv/bin/python app.py >> gateway.log 2>&1 &
  ```
  之后：
  - 看日志：`tail -f /root/du-gateway/gateway.log`（Ctrl+C 只退出 tail，网关照常跑）。
  - 关掉远程、断线都没事，网关会一直跑；下次连上来继续用 `tail -f gateway.log` 看即可。
  - 只有要改代码或 .env 时，改完需要重启一次：先 `pkill -f "python app.py"`（或查到进程号后 `kill 进程号`），再重新执行上面的 `nohup ./venv/bin/python app.py ...`。

- **小结**：虚拟环境 + nohup 各做一次，之后「每次打开」= 连上服务器看日志或改配置即可，不用每次重新装依赖、重新弄环境。

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

---

## 4. 填了网关地址但 RikkaHub 没有出现模型

**原因**：RikkaHub 会请求网关的 `GET /v1/models` 拉模型列表。网关会去请求你配置的 **TARGET 的 /v1/models**。若你的上游（渡 / 其他中转）**没有提供** 或 **不开放** 这个接口，或云服务器访问上游超时/失败，就会拿不到列表，RikkaHub 就显示不出模型。

**排查**：

1. 在浏览器或本机用 curl 直接访问一次网关的模型接口，看返回什么：
   - 地址：`https://你的网关域名/v1/models`
   - 若返回 502 或 `{"error":"..."}`，说明网关访问上游失败或上游没有该接口。
2. 看云服务器上网关日志，是否有「拉取模型列表失败」之类的报错。

**解决**：给网关配置**静态模型列表**，上游失败或没有接口时用这份列表返回，RikkaHub 就能显示。

在 **.env** 里增加一行（把模型名改成你实际要用的，逗号分隔）：

```env
GATEWAY_MODELS=gpt-4,gpt-4o,claude-3-5-sonnet
```

例如你实际用的是「渡」的某个模型名，就填那个名字，如：

```env
GATEWAY_MODELS=你的模型id1,你的模型id2
```

保存后重启网关，再在 RikkaHub 里刷新或重新打开模型选择，列表就会出现。
