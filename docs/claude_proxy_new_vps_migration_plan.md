# Claude OAuth Proxy 新 VPS 迁移方案

目标：旧 VPS 继续跑 `du-gateway`、QQ/TG/App 等现有服务；新 VPS 单独跑 Claude Code CLI 和 Claude OAuth proxy。旧 VPS 只通过本机 `127.0.0.1:8082` 访问新 VPS proxy，避免主网关大搬家，也避免 Claude OAuth proxy 暴露公网。

当前推荐架构：

```text
QQ / TG / App
  -> 旧 VPS: du-gateway / workers / nginx
  -> 旧 VPS: 127.0.0.1:8082
  -> SSH tunnel
  -> 新 VPS: 127.0.0.1:8082 claude-oauth-proxy
  -> Anthropic
```

## 边界

旧 VPS 负责：
- 保持 `du-gateway.service`、`nginx`、Telegram/QQ/SumiTalk 等现有服务。
- 保持网关 upstream 仍指向 `http://127.0.0.1:8082/v1/chat/completions`。
- 新增一个 systemd tunnel，把旧 VPS 的 `127.0.0.1:8082` 转发到新 VPS 的 `127.0.0.1:8082`。
- 不保存 Claude OAuth token。

新 VPS 负责：
- 安装并登录 Claude Code CLI。
- 运行 `claude-oauth-proxy.service`。
- 保存 Claude OAuth 文件，只允许本机 proxy 读取。
- 只开放 SSH 公网入口；`8082` 必须只监听 `127.0.0.1`。

本机 Mac 负责：
- 初期只作为操作机。
- 迁移完成后停用本机 `claude-token-sync`，不要继续每 5 分钟往旧链路同步 token。

## 端口表

| 机器 | 端口 | 监听地址 | 作用 | 公网可访问 |
| --- | --- | --- | --- | --- |
| 旧 VPS | 80/443 | `0.0.0.0` | `duxy-home.com` | 是 |
| 旧 VPS | 5000 | `127.0.0.1` | Flask/gunicorn | 否 |
| 旧 VPS | 8080 | Tailscale/内网 | 内网管理入口 | 否 |
| 旧 VPS | 8082 | `127.0.0.1` | SSH tunnel 本地端 | 否 |
| 新 VPS | 22 | 公网 IP | SSH 管理 | 是，最好限制来源 |
| 新 VPS | 8082 | `127.0.0.1` | Claude OAuth proxy | 否 |

安全验证时，“该不通的端口确实不通”跟“该通的端口能通”一样重要。

## 当前代码依赖

不要直接把 upstream 改成 `http://新VPS:8082/...`，除非同步改代码识别逻辑。当前代码有多处只把本机 `127.0.0.1:8082` 当成 Claude OAuth proxy：

- `services/upstream_policy.py::is_local_claude_oauth_proxy_url()`：只认 `127.0.0.1` / `localhost` + `8082`。
- `services/upstream_policy.py::apply_active_model_request_policy()`：命中本机 Claude OAuth proxy 时才注入 adaptive thinking 设置。
- `routes/chat.py`：Claude thinking carryover 和动态 marker 保留依赖 active upstream 判断。
- `routes/miniapp/upstreams.py`：MiniApp 上游页把本机 8082 识别为 `Claude Code` / OAuth 节点，并读取 `/internal/oauth-status`。
- `miniapp/src/ui/tabs/SettingsUpstream.tsx`：前端也按本机 8082 展示 Claude Code 节点。

所以迁移第一版要保持旧 VPS 看到的是：

```text
http://127.0.0.1:8082/v1/chat/completions
```

## 迁移前准备

在本地准备变量，后续命令里的占位不要提交进仓库：

```bash
NEW_VPS_IP="新 VPS 公网 IP"
NEW_VPS_USER="duproxy"
OLD_VPS_ALIAS="ali-du"
```

确认旧 VPS 当前 Claude proxy 已停：

```bash
ssh "$OLD_VPS_ALIAS" 'systemctl --user status claude-oauth-proxy.service --no-pager -l | sed -n "1,45p"; ss -ltnp 2>/dev/null | grep ":8082" || true'
```

如果还在跑，先停旧 proxy：

```bash
ssh "$OLD_VPS_ALIAS" 'systemctl --user stop claude-oauth-proxy.service; systemctl --user disable claude-oauth-proxy.service; ss -ltnp 2>/dev/null | grep ":8082" || true'
```

## 新 VPS 初始化

以下假设新 VPS 是 Ubuntu 24.04。先用 root 登录一次：

```bash
ssh root@"$NEW_VPS_IP"
```

创建专用用户，不用 root 跑 proxy。下面默认把 root 已经能登录的新 VPS 公钥复制给 `duproxy`，避免 `--disabled-password` 后再用 `ssh-copy-id` 卡住：

```bash
adduser --disabled-password --gecos "" duproxy
install -d -m 700 -o duproxy -g duproxy /home/duproxy/.ssh
if [ -f /root/.ssh/authorized_keys ]; then
  install -m 600 -o duproxy -g duproxy /root/.ssh/authorized_keys /home/duproxy/.ssh/authorized_keys
fi
usermod -aG sudo duproxy
```

如果 root 没有可复用的 `authorized_keys`，再从本机单独放公钥：

```bash
ssh-copy-id duproxy@"$NEW_VPS_IP"
```

基础包：

```bash
ssh duproxy@"$NEW_VPS_IP" 'sudo apt update && sudo apt install -y git curl ca-certificates nodejs npm ufw'
```

防火墙只放 SSH：

```bash
ssh duproxy@"$NEW_VPS_IP" 'sudo ufw allow OpenSSH && sudo ufw --force enable && sudo ufw status verbose'
```

不要开放 `8082`。

## 新 VPS 安装 Claude Code

优先按 [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code/getting-started)当前推荐方式安装。2026-06-28 官方文档里 Linux/macOS 推荐 native installer：

```bash
ssh duproxy@"$NEW_VPS_IP" 'curl -fsSL https://claude.ai/install.sh | bash'
```

如果 native installer 在 VPS 网络里失败，再考虑官方 apt 或 npm 方案。安装后验证：

```bash
ssh duproxy@"$NEW_VPS_IP" '~/.local/bin/claude --version || claude --version'
ssh duproxy@"$NEW_VPS_IP" '~/.local/bin/claude doctor || claude doctor'
```

登录新号。官方文档当前写法是运行 `claude` 后按浏览器提示完成授权；如果本机版本支持 `auth login`，也可以用子命令，但不要把它当唯一入口：

```bash
ssh -t duproxy@"$NEW_VPS_IP" 'PATH="$HOME/.local/bin:$PATH"; claude'
```

按终端给的链接/设备码在浏览器完成授权。不要把 OAuth token、refresh token、cookie 发到聊天里。

验证登录状态，只看是否 logged in，不贴完整邮箱和 org id。不同版本命令略有差异，优先用 `doctor`：

```bash
ssh duproxy@"$NEW_VPS_IP" 'PATH="$HOME/.local/bin:$PATH"; claude doctor'
```

## 新 VPS 部署 Claude OAuth Proxy

在新 VPS 放 proxy 目录：

```bash
ssh duproxy@"$NEW_VPS_IP" 'mkdir -p ~/claude-proxy ~/.cli-proxy-api'
scp scripts/claude_oauth_proxy.js duproxy@"$NEW_VPS_IP":~/claude-proxy/proxy.js
```

创建 env 文件。下面只写占位，真实值在新 VPS 上手动填：

```bash
ssh -t duproxy@"$NEW_VPS_IP" 'umask 077; cat > ~/claude-proxy/.env <<'"'"'EOF'"'"'
HOST=127.0.0.1
PORT=8082
PROXY_KEY=填一个长随机字符串
CLAUDE_OAUTH_SYNC_KEY=填另一个长随机字符串
CLAUDE_OAUTH_FILE=/home/duproxy/.cli-proxy-api/claude-oauth.json
CLAUDE_CODE_VERSION=2.1.195
CLAUDE_MAX_TOKENS=33000
CLAUDE_THINKING_BUDGET_TOKENS=32000
CLAUDE_PROMPT_CACHE_TTL=1h
CLAUDE_ADAPTIVE_THINKING_EFFORT=high
EOF
chmod 600 ~/claude-proxy/.env'
```

负责刷新的本地组件可以持有 refresh token；Claude OAuth proxy 只读取 access-only 文件。第一版更稳的做法是：在新 VPS 上跑本地 token sync，从 Claude Code credential 读取/刷新 token，再把过滤后的 `accessToken/expiresAt` 写到 `CLAUDE_OAUTH_FILE`。

创建 user systemd 服务。先由 root/sudo 允许 `duproxy` 用户服务开机常驻：

```bash
ssh duproxy@"$NEW_VPS_IP" 'sudo loginctl enable-linger duproxy'
```

再写入并启动 user service：

```bash
ssh duproxy@"$NEW_VPS_IP" 'mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/claude-oauth-proxy.service <<'"'"'EOF'"'"'
[Unit]
Description=Claude OAuth OpenAI-compatible proxy
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/duproxy/claude-proxy
EnvironmentFile=/home/duproxy/claude-proxy/.env
ExecStart=/usr/bin/node /home/duproxy/claude-proxy/proxy.js
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now claude-oauth-proxy.service'
```

验证新 VPS proxy 只监听本机：

```bash
ssh duproxy@"$NEW_VPS_IP" 'systemctl --user status claude-oauth-proxy.service --no-pager -l | sed -n "1,60p"; ss -ltnp | grep ":8082" || true'
```

期望看到 `127.0.0.1:8082`，不应该看到 `0.0.0.0:8082`。

从本机测公网不通：

```bash
curl -sS --max-time 5 "http://$NEW_VPS_IP:8082/v1/models" || echo "expected: public 8082 blocked"
```

## 新 VPS OAuth 文件准备

第一版有两种方式，二选一，不要混用。

### 方式 A：新 VPS 本机刷新并写 OAuth 文件

适合最终方案：Claude Code 和 proxy 都在新 VPS，本机 Mac 不再参与 token sync。

需要写一个新 VPS 本地同步脚本，从 Claude Code 本机 credential 中读取 refresh token 并刷新，然后把 access-only JSON 写到：

```text
/home/duproxy/.cli-proxy-api/claude-oauth.json
```

注意：
- 不要用 `scp -r ~/.claude` 整目录搬。
- 不要把 token 放进 systemd 命令行参数。
- 脚本日志只能写 expiresAt / 是否成功，不写 token。
- 如果 Claude Code 版本改变 OAuth 存储格式，先只读检查 key 名，不要 broad dump credential。

### 方式 B：过渡期继续用旧网关转发 sync

适合先跑通 tunnel：本机 Mac 的 `/Users/doraemon/claude-token-sync.sh` POST 到旧网关 `/internal/claude-oauth-sync`，旧网关再经 tunnel 转给新 VPS `/internal/oauth-sync`。

需要保证旧 VPS 的 `CLAUDE_OAUTH_SYNC_TARGET_BASE` 仍指向：

```text
http://127.0.0.1:8082
```

这样旧网关不用知道新 VPS 存在。

当前用户更想取消本机脚本，所以最终目标是方式 A。方式 B 只作为短期救火。

## 旧 VPS 创建 SSH Tunnel

旧 VPS 上创建专用 SSH key，只用于 tunnel，不复用个人主 key：

```bash
ssh "$OLD_VPS_ALIAS" 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/claude-proxy-tunnel -N "" -C "claude-proxy-tunnel"'
ssh "$OLD_VPS_ALIAS" 'cat ~/.ssh/claude-proxy-tunnel.pub'
```

把输出的公钥加入新 VPS `duproxy` 的 `~/.ssh/authorized_keys`。

更严格的 authorized_keys 前缀可后续加：

```text
from="旧VPS公网IP",no-agent-forwarding,no-X11-forwarding ssh-ed25519 ...
```

不要加 `no-port-forwarding`，否则 tunnel 不能用。

先手动试 tunnel：

```bash
ssh "$OLD_VPS_ALIAS" 'ssh -i ~/.ssh/claude-proxy-tunnel -N -L 127.0.0.1:8082:127.0.0.1:8082 duproxy@新VPS公网IP'
```

另开一个终端验证旧 VPS 本地能连：

```bash
ssh "$OLD_VPS_ALIAS" 'curl -sS --max-time 10 -H "Authorization: Bearer 填PROXY_KEY" http://127.0.0.1:8082/v1/models | head -c 300; echo'
```

确认能连后，Ctrl-C 结束手动 tunnel。

创建旧 VPS systemd tunnel 服务：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo tee /etc/systemd/system/claude-proxy-tunnel.service >/dev/null <<'"'"'EOF'"'"'
[Unit]
Description=Tunnel local Claude proxy port to new VPS
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nora
ExecStart=/usr/bin/ssh -i /home/nora/.ssh/claude-proxy-tunnel -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -L 127.0.0.1:8082:127.0.0.1:8082 duproxy@新VPS公网IP
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now claude-proxy-tunnel.service
sudo systemctl status claude-proxy-tunnel.service --no-pager -l | sed -n "1,60p"'
```

检查旧 VPS 的 8082 只监听本机：

```bash
ssh "$OLD_VPS_ALIAS" 'ss -ltnp 2>/dev/null | grep ":8082" || true'
```

期望是 `127.0.0.1:8082`，不应该有 `0.0.0.0:8082`。

## 旧 VPS upstream 不改或少改

如果旧 VPS 环境变量里已有：

```text
TARGET_AI_URLS=...,http://127.0.0.1:8082/v1/chat/completions,...
TARGET_AI_API_KEYS=...,对应 PROXY_KEY,...
```

就不需要改主网关配置。

如果之前把 Claude OAuth upstream 删掉了，需要在旧 VPS 的 du-gateway 环境里恢复这一项。恢复后重启：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo systemctl restart du-gateway && sudo systemctl status du-gateway --no-pager -l | sed -n "1,60p"'
```

不要把 `TARGET_AI_URLS` 直接写成新 VPS 公网 `http://新VPS:8082/...`。

## 现有功能保留清单

这次迁移只换 Claude OAuth proxy 的实际运行机器，不改网关对外入口和业务链路。下面这些功能应该继续保留：

- QQ / TG / App / SumiTalk 入口：仍然进旧 VPS 的 `du-gateway`。
- upstream active 选择：旧 VPS 仍看到 `http://127.0.0.1:8082/v1/chat/completions`，所以现有 Claude OAuth 节点识别不变。
- Claude thinking carryover：仍由旧网关按本机 8082 判断，不需要把新 VPS 地址写进网关。
- adaptive thinking / effort：仍由 `services/upstream_policy.py` 对本机 Claude OAuth proxy upstream 注入。
- prompt cache / tools / content block 转换：仍由 `scripts/claude_oauth_proxy.js` 在新 VPS 上执行。
- MiniApp 上游页状态：旧网关 `/internal/claude-oauth-status` 仍转发到 `127.0.0.1:8082/internal/oauth-status`，经 tunnel 到新 VPS。
- OAuth token sync：过渡期可以继续走旧网关 `/internal/claude-oauth-sync` 转发；最终改成新 VPS 本机刷新并写本机 OAuth 文件。
- rate limit / usage 快照：proxy 成功转发 Anthropic 响应后仍写 `rateLimitSnapshot`，MiniApp 继续从状态接口看。

刻意改变的只有：

- 旧 VPS 不再直接运行 `claude-oauth-proxy.service`。
- 旧 VPS 新增 `claude-proxy-tunnel.service`，占用本机 `127.0.0.1:8082`。
- Claude OAuth token 最终只保留在新 VPS，本机 Mac 的定时 token sync 后续停用。

## 日志接入与观测

日志目标：能判断问题卡在旧网关、SSH tunnel、新 VPS proxy、OAuth token、Anthropic 上游中的哪一层；同时不在日志里打印 token、sync key、Authorization header、完整 cookie 或完整账号 ID。

### 新 VPS：Claude OAuth proxy 日志

实时看 proxy：

```bash
ssh duproxy@"$NEW_VPS_IP" 'journalctl --user -u claude-oauth-proxy.service -f -o cat'
```

看最近错误摘要：

```bash
ssh duproxy@"$NEW_VPS_IP" 'journalctl --user -u claude-oauth-proxy.service -n 200 --no-pager -o cat | grep -Ei "listen|oauth|sync|401|403|429|500|529|rate|limit|cloudflare|error|token|model"'
```

看服务状态和监听端口：

```bash
ssh duproxy@"$NEW_VPS_IP" 'systemctl --user status claude-oauth-proxy.service --no-pager -l | sed -n "1,80p"; ss -ltnp | grep ":8082" || true'
```

期望：
- 启动日志显示 proxy 在 `127.0.0.1:8082`。
- OAuth sync 成功时只显示同步成功和 `expiresAt` 这类摘要，不显示 token。
- 401 多半是 OAuth 失效；403 多半是 Claude/Cloudflare/账号侧阻断；429/529 多半是上游限流或拥塞。

### 旧 VPS：SSH tunnel 日志

实时看 tunnel：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo journalctl -u claude-proxy-tunnel.service -f -o cat'
```

看最近 tunnel 状态：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo systemctl status claude-proxy-tunnel.service --no-pager -l | sed -n "1,80p"; sudo journalctl -u claude-proxy-tunnel.service -n 120 --no-pager -o cat'
```

常见判断：
- `ExitOnForwardFailure` 失败：旧 VPS 本机 `127.0.0.1:8082` 被别的进程占用，通常是旧 proxy 没停干净。
- `Permission denied publickey`：旧 VPS tunnel key 没加到新 VPS `duproxy`。
- `Connection timed out`：新 VPS SSH 端口、防火墙、安全组或 IP 写错。
- tunnel active 但 chat 不通：继续查新 VPS proxy 日志和 `/v1/models`。

### 旧 VPS：网关日志

看主网关：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo journalctl -u du-gateway -n 200 --no-pager -o cat | grep -Ei "Chat|Upstream resp hint|8082|oauth|claude|401|403|429|500|502|503|529|timeout|error"'
```

看 SumiTalk worker：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo journalctl -u du-sumitalk-chat-worker.service -n 200 --no-pager -o cat | grep -Ei "sumitalk|chat_job|gateway_call|upstream|8082|401|403|429|500|502|503|529|timeout|error"'
```

判断顺序：
1. 网关日志如果连 `upstream_post_start` 都没有，问题在入口/worker/job。
2. 有 `upstream_post_start`，但没有新 VPS proxy 日志，问题在旧 VPS upstream 配置或 tunnel。
3. 新 VPS proxy 有收到请求但返回 401/403/429/529，问题在 OAuth/账号/上游。
4. 新 VPS proxy 成功返回，但 App/QQ/TG 没收到，问题在网关后处理或对应 channel 发送。

### 状态接口

旧 VPS 视角：

```bash
ssh "$OLD_VPS_ALIAS" 'curl -sS --max-time 10 -H "X-OAuth-Sync-Key: 填SYNC_KEY" http://127.0.0.1:8082/internal/oauth-status'
```

新 VPS 本机视角：

```bash
ssh duproxy@"$NEW_VPS_IP" 'curl -sS --max-time 10 -H "X-OAuth-Sync-Key: 填SYNC_KEY" http://127.0.0.1:8082/internal/oauth-status'
```

两边都通才说明 tunnel 和 proxy 都正常。只允许看 `expiresAt`、`oauth_ready`、`stale`、`rateLimitSnapshot` 等摘要字段，不要把完整返回里可能含有的敏感内容贴到聊天里。

## 验证清单

新 VPS：

```bash
ssh duproxy@"$NEW_VPS_IP" 'systemctl --user is-active claude-oauth-proxy.service'
ssh duproxy@"$NEW_VPS_IP" 'ss -ltnp | grep ":8082" || true'
curl -sS --max-time 5 "http://$NEW_VPS_IP:8082/v1/models" || echo "expected blocked"
```

旧 VPS：

```bash
ssh "$OLD_VPS_ALIAS" 'systemctl is-active claude-proxy-tunnel.service'
ssh "$OLD_VPS_ALIAS" 'ss -ltnp 2>/dev/null | grep ":8082" || true'
ssh "$OLD_VPS_ALIAS" 'curl -sS --max-time 10 -H "Authorization: Bearer 填PROXY_KEY" http://127.0.0.1:8082/v1/models | head -c 500; echo'
```

主网关：

```bash
ssh "$OLD_VPS_ALIAS" 'curl -sS --max-time 10 http://127.0.0.1:5000/health'
curl -sS --max-time 12 https://duxy-home.com/health
curl -I --max-time 12 https://duxy-home.com/miniapp/
```

上游页面：
- MiniApp 上游列表应仍显示 Claude Code/OAuth 节点。
- 状态接口能看到 `expiresAt`。
- 用量快照只有在 proxy 成功转发过一次 Anthropic 请求后才会刷新；刚同步 token 不会自动刷新用量。

真实最小 chat：

```bash
ssh "$OLD_VPS_ALIAS" 'cd /实际/du-gateway/目录 && .venv/bin/python - <<'"'"'PY'"'"'
from storage.upstream_store import load_upstreams, get_cached_active_model
data = load_upstreams()
print("active", data.get("active"))
for i, it in enumerate(data.get("items") or []):
    print(i, it.get("name"), it.get("url"), "key_len", len(it.get("api_key") or ""))
print("model", get_cached_active_model(refresh_if_missing=False))
PY'
```

## 回滚

回滚原则：不要依赖新 VPS 可用。

如果新 VPS 或 tunnel 出问题：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo systemctl stop claude-proxy-tunnel.service'
```

然后二选一：

1. 切到其它已可用上游：
   - 在 MiniApp 上游设置里选 OpenRouter / DeepSeek / 其它节点。
   - 或改 `data/upstreams.json` active index 后重启网关。

2. 临时恢复旧 VPS 本地 Claude proxy：

```bash
ssh "$OLD_VPS_ALIAS" 'systemctl --user enable --now claude-oauth-proxy.service; systemctl --user status claude-oauth-proxy.service --no-pager -l | sed -n "1,60p"'
```

如果旧 IP 已确认被标记，不建议长时间恢复旧 proxy，只作为应急验证。

## 故障排查

### MiniApp 上游列表没有 Claude Code

先查旧 VPS 主网关的 env 是否还包含 `127.0.0.1:8082`：

```bash
ssh "$OLD_VPS_ALIAS" 'sudo systemctl cat du-gateway | grep -nE "TARGET_AI_URL|8082" || true'
```

如果 env 没有，就不是 tunnel 问题，是 upstream 配置项没进网关。

### Claude Code 节点显示状态失败

查 tunnel：

```bash
ssh "$OLD_VPS_ALIAS" 'systemctl status claude-proxy-tunnel.service --no-pager -l | sed -n "1,80p"'
ssh "$OLD_VPS_ALIAS" 'curl -sS --max-time 10 -H "X-OAuth-Sync-Key: 填SYNC_KEY" http://127.0.0.1:8082/internal/oauth-status'
```

### Chat 401 / Invalid authentication credentials

这通常不是 tunnel，而是 OAuth token 不可用：

```bash
ssh duproxy@"$NEW_VPS_IP" 'journalctl --user -u claude-oauth-proxy.service -n 120 --no-pager -o cat | grep -Ei "401|auth|oauth|error|token"'
```

再重新在新 VPS 登录 Claude Code，或运行新 VPS 本地 token sync。

### Chat 401 / Invalid proxy key

旧 VPS upstream 的 api key 与新 VPS `PROXY_KEY` 不一致。检查长度即可，不要打印原文：

```bash
ssh "$OLD_VPS_ALIAS" 'cd /实际/du-gateway/目录 && .venv/bin/python - <<'"'"'PY'"'"'
from storage.upstream_store import load_upstreams
for i,it in enumerate(load_upstreams().get("items") or []):
    if "8082" in str(it.get("url")):
        print(i, it.get("url"), len(it.get("api_key") or ""))
PY'
ssh duproxy@"$NEW_VPS_IP" 'awk -F= "/^PROXY_KEY=/{print length($2)}" ~/claude-proxy/.env'
```

### 用量不更新

用量 `rateLimitSnapshot` 只在成功转发 Anthropic 响应后更新。刚同步 OAuth 只会更新 `expiresAt`，不会自动刷新 5h/周用量。

## 当前状态记录

- 2026-06-28：旧 VPS 上 `claude-oauth-proxy.service` 已先停用，避免旧 IP/旧号继续撞 Anthropic 401。
- 迁移未开始：还没有新 VPS IP，也没有新 VPS Claude Code 登录。
- 下次从这里继续：买好新 VPS 后，先做“新 VPS 初始化”和“新 VPS 安装 Claude Code”，再部署 proxy 和 tunnel。
- 不要碰：主网关现有服务、MiniApp 静态构建产物、其它上游配置，除非确认要切换 active upstream。
