# 主网关 VPS 全量迁移方案

更新时间：2026-07-10

目标：把旧阿里云主网关上的业务完整迁移到一台新的 `2 vCPU / 4 GB` VPS；迁移完成后，旧主网关不删除，收缩成独立代理节点。Claude OAuth 转发 VPS 保持原样，不和这次主网关搬家混在一起。

这份方案按“先保命、再复制、后切流、可随时退回”的顺序执行。没有到 DNS 切换阶段前，线上业务仍由旧主网关承担。

当前执行状态（2026-07-10）：主网关业务已切换到腾讯云首尔新机 `43.155.136.6`，本机主 SSH alias 为 `du-gateway`（Tailscale `100.119.107.127`），公网备用 alias 为 `du-gateway-public`。`duxy-home.com` 已完成 DNS 切换，公网 `/health` 和 `/miniapp/` 均返回 200；网关、realtime、SumiTalk、TG、微信、QQ/NapCat、CPA、Claude tunnel 和 Codex 群聊桥接均在新机运行。最终 `data/`、`.env`、主 SQLite/WAL/SHM 和 QQ 数据已核对一致，全部 SQLite `PRAGMA quick_check` 通过。旧主网关业务已停止并禁用自启，只保留 nginx、Trojan、Tailscale、Fail2ban 和旧代理域名；Claude OAuth 转发 VPS 未改。新旧 nginx 均已增加等待 Tailscale 地址并失败重试的 systemd drop-in。新独立代理 `kr.duxy-home.com:8443` 已部署，使用独立密码、证书和随机订阅路径，并以专用 `trojan` 系统用户运行；完整 SOCKS 出口验证为新机公网 IP。待办只剩新机整机 reboot 验收和入口实聊抽测。

## 1. 最终拓扑

```text
QQ / TG / WeChat / SumiTalk / MiniApp / XiaoAI
  -> duxy-home.com
  -> 新主网关 VPS
     - nginx
     - du-gateway
     - du-realtime
     - SumiTalk 独立 worker
     - Telegram 两个 worker
     - WeChat iLink
     - NapCat / QQ connector / Xvfb
     - CPA / CLIProxyAPI: 127.0.0.1:8317
     - Claude tunnel: 127.0.0.1:8082
     - 新的独立 Trojan 代理节点

新主网关 VPS: 127.0.0.1:8082
  -> SSH tunnel over Tailscale
  -> Claude OAuth 转发 VPS: 100.86.248.99:8082

旧主网关 VPS
  - 保留 proxy.duxy-home.com
  - 保留原 Trojan、证书续期、Tailscale、SSH、Fail2ban
  - 停止网关、QQ/TG/微信/App 等业务服务

Claude OAuth 转发 VPS
  - 保持 us.duxy-home.com / 45.76.171.91
  - 保持 Claude Code OAuth proxy 和自刷新逻辑
  - 本次不迁移、不重装、不改鉴权
```

## 2. 已确认的现状

### 2.1 主机与域名

| 角色 | 当前地址 | 迁移后 |
| --- | --- | --- |
| 旧主网关 | `du-proxy-old-ts` / Tailscale `100.92.76.117`；`du-proxy-old` / 公网 `47.250.162.10` | 收缩为旧代理节点 |
| 新主网关 | `du-gateway` / Tailscale `100.119.107.127`；`du-gateway-public` / 公网 `43.155.136.6` | 承接主网关业务和新独立代理节点 |
| Claude OAuth 转发 VPS | `du-claude-proxy` / Tailscale `100.86.248.99` / 公网 `45.76.171.91` | 保持不变 |
| 主域名 | `duxy-home.com -> 47.250.162.10` | 切到新主网关公网 IP |
| 旧代理域名 | `proxy.duxy-home.com -> 47.250.162.10` | 保持不变 |
| 转发 VPS 域名 | `us.duxy-home.com -> 45.76.171.91` | 保持不变 |
| 新代理域名 | 尚未确定 | 指向新主网关公网 IP |

本机开启 Clash 时，`dig` 可能返回 `198.18.*` fake-IP。迁移核对 DNS 必须使用服务器侧解析、Cloudflare 控制台或权威 DNS 查询，不能把本机 fake-IP 当成真实记录。

### 2.2 旧主网关规格与运行环境

- Ubuntu 24.04 LTS，2 vCPU，1.6 GiB 内存，40 GB 系统盘。
- 2 GB swap，当前未使用。
- Python 3.12.3。
- Node.js 24.14.0 / npm 11.9.0。
- nginx 1.24.0。
- Trojan 1.16.0。
- CLIProxyAPI 7.2.55。
- 系统时区为 `Asia/Shanghai`。
- `/root/du-gateway` 当前约 771 MB，线上工作树不是干净状态；迁移不能只做一次 `git clone`，必须以线上工作树和持久数据为准。

### 2.3 需要迁移的服务

| 服务 | 当前状态 | 迁移要求 |
| --- | --- | --- |
| `du-gateway.service` | enabled/running | 迁移 |
| `du-realtime.service` | enabled/running | 迁移 |
| `du-sumitalk-chat-worker.service` | enabled/running | 迁移 |
| `du-telegram-proactive.service` | enabled/running | 迁移 |
| `du-telegram-webhook-worker.service` | enabled/running | 迁移 |
| `du-wechat-ilink.service` | enabled/running | 迁移 |
| `napcat.service` | enabled/running | 迁移 |
| `qq-connector.service` | enabled/running | 迁移 |
| `claude-proxy-tunnel.service` | enabled/running | 迁移，并继续保留本机 `127.0.0.1:8082` 语义 |
| `cliproxyapi.service` | nora user service，enabled/running | 迁移到新主网关 |
| `nginx.service` | enabled/running | 拆分迁移：主域名去新机，旧代理域名留旧机 |
| `trojan.service` | enabled/running | 旧机保留；新机另建独立节点 |
| `tailscaled.service` | enabled/running | 新机重新加入同一 tailnet |
| `fail2ban.service` | enabled/running | 新机重新配置 |
| `du-telegram-bot.service` | disabled | 只归档，不启用 |

不要迁移阿里云厂商组件：`AssistDaemon`、`aegis`、`aliyun`、`cloudmonitor` 及其他 Aegis/云助手/云监控进程。

### 2.4 当前监听端口

| 端口 | 当前用途 | 新机对公网开放 |
| --- | --- | --- |
| TCP 22 | SSH | 是，密钥登录；Tailscale 验证后可进一步收紧 |
| TCP 80/443 | nginx / MiniApp / API | 是 |
| TCP 8443 | 旧 Trojan | 新机新代理需要；旧机继续保留 |
| UDP 41641 | Tailscale 直连 | 建议开放 |
| TCP 5000 | Flask/gunicorn | 否，只允许 loopback |
| TCP 5010 | realtime | 否，只允许 loopback |
| TCP 8082 | Claude SSH tunnel | 否，只允许 loopback |
| TCP 8317 | CPA / CLIProxyAPI | 否，只允许 loopback |
| TCP 8080 | Tailscale 管理入口 | 否，只允许 `tailscale0` |
| TCP 8091 | WeChat iLink | 否；即使程序监听 `0.0.0.0`，防火墙也不得放公网 |
| TCP 8092 | QQ connector | 否；即使程序监听 `0.0.0.0`，防火墙也不得放公网 |
| TCP 3000/6099 | NapCat/QQ 内部端口 | 否 |

### 2.5 必须迁移的配置与数据

- `/root/du-gateway`：线上实际代码、`.env`、`data/`、`miniapp_static/`、连接器、脚本。
- `/root/du-gateway/data/runtime_state.sqlite3` 及同名 WAL/SHM。
- 其他 SQLite：动态记忆 provenance/mirror、SumiTalk queue、Telegram queue、wakeup、页笺、热梗、游戏存档等。
- `/root/du-gateway/data/sumitalk_chat_jobs/`、注入快照、设备状态、小爱状态等文件型状态。
- `/root/.config/QQ` 与 `/root/Napcat`：QQ/NapCat 安装与登录状态。
- `/etc/systemd/system` 中本项目服务和 drop-in。
- root crontab 中 QQ entry watchdog。
- `/home/nora/.config/systemd/user/cliproxyapi.service`、linger 设置。
- `/home/nora/.cli-proxy-api` 中 CPA 配置、认证和状态文件。
- `/etc/nginx`、主域名证书、`/etc/trojan`、`/etc/fail2ban`。
- `/root/.ssh/du_new_vps_ed25519`：仅用于主网关到 Claude 转发 VPS 的专用 tunnel key；它不是管理员登录密钥。
- Telegram、微信、QQ、SumiTalk、XiaoAI 所依赖的所有未提交 server-only 配置。

日志可以归档后迁移一份，但不作为新机运行依赖。`venv`、`.venv`、`node_modules`、Go build cache 优先在新机重建，避免跨机器复制旧缓存；只有实际安装程序或无法重建的运行文件才复制。

## 3. 不做的事情

1. 不把本机 Mac 的 `.env` 覆盖到服务器。
2. 不改 Claude OAuth 转发 VPS 的 token、proxy、域名或刷新机制。
3. 不删除旧主网关，也不删除旧 `proxy.duxy-home.com` 代理。
4. 不在迁移同时把 CPA 改去转发 VPS；先原样搬到新主网关，架构调整另开任务。
5. 不把 `8082`、`8317`、`5000`、`5010`、`8091`、`8092` 暴露公网。
6. 不把旧的 disabled unit、备份 unit、临时锁文件启用到新机。
7. 不在新管理员账号验证成功前关闭 root 会话或修改 SSH 登录策略。
8. 不在新机通过本地验收前修改 `duxy-home.com` DNS。
9. 不把迁移和“疯狂读盘”根因修复混成一次代码改造；先搬家并保留诊断数据，再单独修。

## 4. 变量与命名

执行前在本机终端设置，不写进仓库：

```bash
export OLD_GATEWAY_ALIAS="du-proxy-old"
export OLD_GATEWAY_TS_ALIAS="du-proxy-old-ts"
export FORWARDING_VPS_TS_IP="100.86.248.99"
export NEW_GATEWAY_IP="43.155.136.6"
export NEW_GATEWAY_TS_IP="100.119.107.127"
export NEW_GATEWAY_USER="nora"
export NEW_GATEWAY_ALIAS="du-gateway"
export NEW_PROXY_DOMAIN="待填写"
```

管理员登录只复用本机现有公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

不要发送或复制私钥内容。新机控制台只填写 `.pub` 公钥。

## 5. 阶段 A：新 VPS 创建与云防火墙

推荐镜像：Ubuntu 24.04 LTS x64。磁盘至少 40 GB；如果价格差不大，优先 NVMe。

### A1. 云防火墙必须先做

新机启动后，第一件事是绑定云防火墙/安全组：

| 协议 | 端口 | 来源 | 备注 |
| --- | --- | --- | --- |
| TCP | 22 | 初期可 `0.0.0.0/0` | 只允许密钥；Tailscale 验证后再收紧 |
| TCP | 80 | `0.0.0.0/0` | ACME 和 HTTP 跳转 |
| TCP | 443 | `0.0.0.0/0` | 主站/API |
| TCP | 8443 | `0.0.0.0/0` | 新 Trojan 节点 |
| UDP | 41641 | `0.0.0.0/0` | Tailscale 直连，可选但推荐 |
| ICMP | - | `0.0.0.0/0` | 可选，便于诊断 |

其他入站一律拒绝。若启用了公网 IPv6，同步添加 IPv6 规则或暂时不分配 IPv6，避免只防 IPv4。

### A2. 首次 SSH

先保留 provider root 控制台和当前 SSH 会话。确认本机公钥登录：

```bash
ssh root@"$NEW_GATEWAY_IP"
```

创建管理员 `nora`，复制 root 已有的本机公钥并授予 sudo：

```bash
adduser --disabled-password --gecos "" nora
install -d -m 700 -o nora -g nora /home/nora/.ssh
install -m 600 -o nora -g nora /root/.ssh/authorized_keys /home/nora/.ssh/authorized_keys
usermod -aG sudo nora
printf 'nora ALL=(ALL) NOPASSWD:ALL\n' >/etc/sudoers.d/90-nora
chmod 440 /etc/sudoers.d/90-nora
visudo -cf /etc/sudoers.d/90-nora
```

在第二个本机终端验证，旧 root 会话先不要关：

```bash
ssh nora@"$NEW_GATEWAY_IP" 'id; sudo -n true; echo sudo-ok'
```

本机 `~/.ssh/config` 新增：

```sshconfig
Host du-gateway
    HostName NEW_GATEWAY_IP
    User nora
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

验证 alias 后再继续。

## 6. 阶段 B：系统加固与基础环境

阶段 B 实际状态（2026-07-10）：

- 已创建 `nora` 管理员并复用本机 `~/.ssh/id_ed25519.pub`，`sudo -n` 验证通过。
- 已关闭 root、密码和键盘交互登录，只允许 `nora` 公钥登录；fresh SSH 连接和 `sshd -t` 通过。
- UFW、Fail2ban、约 2 GB `/swap.img`、journald 容量/保留期限制和 `Asia/Shanghai` 时区均已验证。
- Tailscale `1.98.8` 已加入现有 tailnet，新主机名为 `du-gateway-main`，IP 为 `100.119.107.127`。
- 新主网关到 Claude 转发 VPS 为 Tailscale 直连；转发 VPS 的 `8082` 不暴露在 Tailscale 地址上，迁移时仍须复制专用 SSH key 和 `claude-proxy-tunnel.service`，保持本机 `127.0.0.1:8082` 端口转发。
- 80/443/8443 暂未开放；只有阶段验收完成、准备 ACME/切流或启用新代理时再放行。

### B1. 更新系统和安装基础包

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo apt update && sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y'
ssh "$NEW_GATEWAY_ALIAS" 'sudo apt install -y \
  ca-certificates curl git jq rsync unzip zip sqlite3 lsof sysstat \
  python3 python3-venv python3-pip build-essential \
  nginx certbot python3-certbot-nginx \
  fail2ban ufw cron logrotate xvfb'
```

Node.js 要安装与旧机兼容的 Node 24，不使用 Ubuntu 自带旧版；安装后确认 `node --version` 与 `npm --version`。

### B2. SSH 加固

写独立 drop-in，避免直接手改主配置。OpenSSH 对多数选项使用最先读取到的值；腾讯云镜像自带 `50-cloud-init.conf` 会提前设置 `PasswordAuthentication yes`，因此加固文件必须排在它前面，不能使用 `90-`：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo tee /etc/ssh/sshd_config.d/00-du-hardening.conf >/dev/null <<'"'"'EOF'"'"'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers nora
X11Forwarding no
EOF
sudo sshd -t
sudo systemctl reload ssh'
```

再次新开终端测试 `ssh du-gateway`。失败时用仍保留的 provider console/root 会话修复，不能盲目重启。

### B3. UFW

旧主网关当前 UFW 是 inactive；新机不能照搬。

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo bash -s' <<'EOF'
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 41641/udp
ufw allow in on lo
ufw allow in on tailscale0 to any port 8080 proto tcp
ufw --force enable
ufw status verbose
EOF
```

初始化阶段不要提前放开 80/443/8443。Ubuntu 安装 nginx 后会自动启动默认站点，一旦 UFW 放行，默认页就会立刻暴露公网。只有主站配置、证书、本机预演和最终同步均完成，准备 ACME/切流时才执行：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo ufw allow 80/tcp; sudo ufw allow 443/tcp; sudo ufw allow 8443/tcp'
```

### B4. Fail2ban

至少启用 `sshd` jail，沿用旧机的可靠配置但不直接复制阿里云相关内容：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo systemctl enable --now fail2ban; sudo fail2ban-client status; sudo fail2ban-client status sshd'
```

### B5. Tailscale

安装后加入同一 tailnet，给新机固定一个清楚的名字，例如 `du-gateway-main`：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'curl -fsSL https://tailscale.com/install.sh | sh'
ssh -t "$NEW_GATEWAY_ALIAS" 'sudo tailscale up --hostname=du-gateway-main'
```

需要小玥完成一次网页登录。完成后记录新 Tailscale IP：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'tailscale ip -4; tailscale status'
```

确认 Mac 能通过 Tailscale SSH 后，公网 22 可以在云防火墙中限制来源；不要在验证前收紧。

### B6. Swap 与时区

4 GB 新机仍保留约 2 GB swap 作为保险，不让突发内存直接 OOM。先检查云镜像是否已经提供 `/swap.img`；已有足量 swap 时直接保留，不能再叠加一个 `/swapfile`：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo timedatectl set-timezone Asia/Shanghai'
ssh "$NEW_GATEWAY_ALIAS" 'sudo bash -s' <<'EOF'
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi
swapon --show
EOF
```

### B7. 日志上限

旧机当前 systemd journal 约 143 MB，`/var/log/du-gateway` 约 27 MB。新机保留 journal，但设明确上限，避免日志再次变成读盘/磁盘放大器：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo install -d /etc/systemd/journald.conf.d; sudo tee /etc/systemd/journald.conf.d/90-du-limits.conf >/dev/null <<'"'"'EOF'"'"'
[Journal]
SystemMaxUse=500M
RuntimeMaxUse=128M
SystemMaxFileSize=64M
MaxRetentionSec=14day
EOF
sudo systemctl restart systemd-journald
journalctl --disk-usage'
```

迁移 `/etc/logrotate.d/du-gateway` 后执行一次 `logrotate -d` 只读检查，不能让 QQ/微信日志无界增长。

## 7. 阶段 C：首轮文件迁移

### C1. 先做旧机清单和备份

旧机继续在线，只做一致性要求不高的首轮复制。先记录：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo systemctl list-units --type=service --state=running --no-pager'
ssh "$OLD_GATEWAY_ALIAS" 'cd /root/du-gateway && sudo git status --short && sudo git rev-parse HEAD'
ssh "$OLD_GATEWAY_ALIAS" 'sudo ss -lntup; sudo ufw status verbose; sudo fail2ban-client status'
```

把旧机服务文件、crontab、nginx、证书和数据打一个只在旧机保存的迁移快照：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo bash -s' <<'EOF'
set -e
stamp=$(date +%Y%m%d-%H%M%S)
dir=/root/migration-backup-$stamp
mkdir -p "$dir"
cp -a /etc/systemd/system "$dir/"
cp -a /etc/nginx "$dir/"
cp -a /etc/trojan "$dir/"
cp -a /etc/fail2ban "$dir/"
cp -a /etc/letsencrypt "$dir/"
crontab -l >"$dir/root.crontab" 2>/dev/null || true
tar -C /root -czf "$dir/du-gateway-data.tgz" du-gateway/data du-gateway/.env
chmod -R go-rwx "$dir"
echo "$dir"
EOF
```

快照先留在旧机，不上传仓库，不发到聊天里。

### C2. 复制线上实际工作树

因为旧线上工作树有未提交内容，不能只 `git clone`。管理员私钥不复制到旧机或新机；使用 Mac 同时建立两个 SSH 会话，把 tar 流从旧机转到新机：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo tar -C /root -cpf - du-gateway' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tar -C /root -xpf -'
```

复制后修正权限并检查：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo chown -R root:root /root/du-gateway; sudo chmod 600 /root/du-gateway/.env; sudo du -sh /root/du-gateway'
```

### C3. 不复制旧依赖缓存，重新构建

删除首轮复制带来的可重建目录，再按线上锁文件安装：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo rm -rf /root/du-gateway/.venv /root/du-gateway/venv /root/du-gateway/miniapp/node_modules /root/du-gateway/connectors/wechat_ilink/node_modules'
ssh "$NEW_GATEWAY_ALIAS" 'sudo python3 -m venv /root/du-gateway/.venv'
ssh "$NEW_GATEWAY_ALIAS" 'sudo /root/du-gateway/.venv/bin/pip install -U pip wheel && sudo /root/du-gateway/.venv/bin/pip install -r /root/du-gateway/requirements.txt'
ssh "$NEW_GATEWAY_ALIAS" 'sudo python3 -m venv /root/du-gateway/venv && sudo /root/du-gateway/venv/bin/pip install -U pip wheel && sudo /root/du-gateway/venv/bin/pip install -r /root/du-gateway/requirements.txt'
```

旧线上 unit 同时使用 `venv` 和 `.venv` 两套路径，首轮迁移按原路径分别重建，不能在搬家时擅自合并后改服务入口。

Node 依赖使用锁文件：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'cd /root/du-gateway/miniapp && sudo npm ci'
ssh "$NEW_GATEWAY_ALIAS" 'cd /root/du-gateway/connectors/wechat_ilink && sudo npm ci'
```

### C4. 复制 QQ/NapCat

复制安装目录和登录状态；首轮复制时旧 QQ 仍运行，最终切换前还会停机补一次：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo tar -C /root -cpf - Napcat .config/QQ' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tar -C /root -xpf -'
```

安装 QQ/NapCat 所需的 Xvfb、字体、GTK/NSS/音频库。不要假定只复制目录就能启动；以 `napcat.service` 启动日志为准。若登录态失效，预留扫码登录步骤。

### C5. 复制 CPA

首轮复制 CPA 文件，但新机暂不启动：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo tar -C /home/nora -cpf - .cli-proxy-api .local/bin/cliproxyapi .config/systemd/user/cliproxyapi.service' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tar -C /home/nora -xpf -'
ssh "$NEW_GATEWAY_ALIAS" 'sudo chown -R nora:nora /home/nora/.cli-proxy-api /home/nora/.config /home/nora/.local; sudo loginctl enable-linger nora'
```

CPA 仍只监听 `127.0.0.1:8317`。不要把本地 Mac 的 CPA 配置覆盖过来。

### C6. 复制 systemd、cron 和 tunnel key

只复制已确认的业务 unit，不整目录覆盖：

```bash
for f in \
  du-gateway.service \
  du-realtime.service \
  du-sumitalk-chat-worker.service \
  du-telegram-proactive.service \
  du-telegram-webhook-worker.service \
  du-wechat-ilink.service \
  napcat.service \
  qq-connector.service \
  claude-proxy-tunnel.service; do
  ssh "$OLD_GATEWAY_ALIAS" "sudo cat /etc/systemd/system/$f" \
    | ssh "$NEW_GATEWAY_ALIAS" "sudo tee /etc/systemd/system/$f >/dev/null"
done
```

drop-in 逐个复制并审阅。不要复制：

- `AssistDaemon.service`
- `aegis.service`
- `aliyun.service`
- `cloudmonitor.service`
- disabled `du-telegram-bot.service`
- `.bak-*` 备份 unit
- `.#override.*` 编辑器临时锁文件

Claude tunnel 的专用 key 单独复制并锁权限；管理员仍只用 Mac key：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo cat /root/.ssh/du_new_vps_ed25519' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo bash -c "install -d -m 700 /root/.ssh; umask 077; cat > /root/.ssh/du_new_vps_ed25519"'
```

复制 root crontab 后，只保留 QQ watchdog 那一条；先确认脚本路径存在，再启用。

## 8. 阶段 D：新机服务离线组装

### D1. systemd

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo systemctl daemon-reload; sudo systemctl list-unit-files | grep -E "^(du-|napcat|qq-connector|claude-proxy-tunnel)"'
```

这时只 enable，不要立即启动会写数据或接外部消息的服务。允许先启动并测试：

- Tailscale
- Fail2ban
- CPA（只监听 loopback）
- Claude tunnel（只监听 loopback）

### D2. Claude tunnel

把 `claude-proxy-tunnel.service` 目标固定为转发 VPS Tailscale IP `100.86.248.99`，不要退回公网 IP，也不要改转发 VPS：

```text
127.0.0.1:8082 -> 100.86.248.99:8082
```

验证：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo systemctl enable --now claude-proxy-tunnel.service; sudo ss -ltnp | grep 127.0.0.1:8082'
```

只做不扣费的状态/模型接口检查；未经当前确认，不发真实上游聊天测试。

### D3. CPA

```bash
ssh "$NEW_GATEWAY_ALIAS" 'systemctl --user daemon-reload; systemctl --user enable --now cliproxyapi.service; systemctl --user status cliproxyapi.service --no-pager -l'
ssh "$NEW_GATEWAY_ALIAS" 'ss -ltnp | grep 127.0.0.1:8317'
```

确认模型列表和原有 OpenRouter/硅基流动/Codex OAuth 等配置都在；不能用本机 `.env` 重建。

### D4. nginx 主站预组装

从旧 nginx 配置中拆出：

- 新机保留 `duxy-home.com` 主站/API vhost。
- 旧机保留 `proxy.duxy-home.com` vhost。
- 新机新增 `${NEW_PROXY_DOMAIN}` vhost/Trojan 配置。
- `100.92.76.117:8080` 必须改成新机的 Tailscale IP。

主域名现有证书可以安全复制到新机作为切换过渡，私钥权限必须保持 root-only。切换后由新机续期 `duxy-home.com`；旧机最终停止该主域名 renewal，但继续续期 `proxy.duxy-home.com`。

先复制 nginx 配置作为模板和主域名证书；复制后，新机必须先禁用旧 `proxy-sub`，再编辑配置，不能直接启动：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo tar -C /etc -cpf - nginx logrotate.d/du-gateway \
  letsencrypt/accounts \
  letsencrypt/archive/duxy-home.com \
  letsencrypt/live/duxy-home.com \
  letsencrypt/renewal/duxy-home.com.conf \
  letsencrypt/renewal-hooks \
  letsencrypt/options-ssl-nginx.conf \
  letsencrypt/ssl-dhparams.pem' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tar -C /etc -xpf -'
ssh "$NEW_GATEWAY_ALIAS" 'sudo rm -f /etc/nginx/sites-enabled/proxy-sub; sudo nginx -t'
```

旧 `proxy-sub` 配置只作为新节点模板保留在 `sites-available`，改成 `${NEW_PROXY_DOMAIN}`、新证书和新密码后再单独启用。`/etc/nginx/.htpasswd-million-plan` 等主站现用访问控制文件随 nginx 配置一起迁移。

新代理域名需要独立证书，不能复用旧代理私钥。

### D5. 新 Trojan 代理节点

新主网关上的代理是一个新节点，不覆盖旧节点：

1. 生成新的强随机密码，不复用旧 Trojan 密码。
2. 使用 `${NEW_PROXY_DOMAIN}` 和独立证书。
3. 监听端口沿用经过验证的旧结构，但配置文件独立。
4. 加入现有订阅时保留旧 `proxy.duxy-home.com` 和 `us.duxy-home.com`。
5. 从本机和手机各测试一次出口 IP、DNS、IPv6 和 WebRTC。

### D6. Codex CLI 与群聊桥接

Codex CLI 和群聊桥接随新主网关迁移，但必须和本机桥接保持单实例：

1. 新机安装官方 Codex CLI，只迁移 `~/.codex/auth.json` 和必要的最小配置，不复制本机完整会话、日志或历史线程。
2. 桥接脚本、私有 `.env` 和运行目录放在 `/home/nora/.du-gateway-codex-bridge`，由 `nora` 的 user systemd unit 管理。
3. 新机使用新的 worker id，并从新线程启动；旧线程绑定本机 `/Users/...` 工作目录，不能原样恢复到 Linux。
4. 离线组装阶段保持新机桥接 disabled/inactive。
5. 最终切换时必须先停止本机 LaunchAgent，再启动新机 `codex-group-chat-bridge.service`，禁止两端同时消费群聊任务。
6. 首次启动后只做队列连通、日志和单实例检查；未经当前确认，不额外触发模型测试任务。

当前已完成：新机 Codex CLI、最小 OAuth 凭证、桥接虚拟环境、私有环境变量和 user unit 已就位，登录状态为 ChatGPT；新机 unit 仍保持 disabled/inactive，本机桥接仍在运行。

## 9. 阶段 E：切换前离线验收

### E1. 代码和导入

在新机上验证服务器实际版本：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'cd /root/du-gateway && sudo .venv/bin/python -m py_compile app.py routes/chat.py routes/miniapp_api.py'
ssh "$NEW_GATEWAY_ALIAS" 'cd /root/du-gateway && sudo .venv/bin/python -c "import app; print(\"import-ok\")"'
```

如果 unit 仍使用 `/root/du-gateway/venv/bin/python`，还要用那套解释器验证对应 worker。

### E2. nginx 与端口

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo nginx -t'
ssh "$NEW_GATEWAY_ALIAS" 'sudo ss -lntup'
ssh "$NEW_GATEWAY_ALIAS" 'sudo ufw status verbose'
```

必须确认公网不该通的端口都没开放：`5000`、`5010`、`8080`、`8082`、`8091`、`8092`、`8317`、`3000`、`6099`。

### E3. hosts 定向测试

DNS 未切换前，从本机临时把域名请求定向到新 IP：

```bash
curl --resolve duxy-home.com:443:"$NEW_GATEWAY_IP" https://duxy-home.com/health
curl --resolve duxy-home.com:443:"$NEW_GATEWAY_IP" -I https://duxy-home.com/miniapp/
```

主站证书、nginx、静态资源和 API 都通过后才能进入停写窗口。

## 10. 阶段 F：最终一致性同步

预计需要一个短暂停写窗口。旧代理不停止，只有网关业务服务停写。

### F1. 停旧机业务写入

先停掉每分钟可能重新拉起 QQ 的 watchdog cron，并保存一份可回滚副本：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo bash -s' <<'EOF'
crontab -l >/root/root.crontab.before-gateway-cutover 2>/dev/null || true
crontab -l 2>/dev/null | grep -v 'run_qq_entry_watchdog.py' | crontab -
EOF
```

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo systemctl stop \
  du-gateway.service \
  du-realtime.service \
  du-sumitalk-chat-worker.service \
  du-telegram-proactive.service \
  du-telegram-webhook-worker.service \
  du-wechat-ilink.service \
  qq-connector.service \
  napcat.service'
ssh "$OLD_GATEWAY_ALIAS" 'uid=$(id -u nora); sudo -u nora XDG_RUNTIME_DIR=/run/user/$uid systemctl --user stop cliproxyapi.service'
```

不要停止旧机：

- `trojan.service`
- `nginx.service`
- `tailscaled.service`
- `fail2ban.service`

### F2. 检查队列与 SQLite

停写后确认没有仍持有 DB 的业务进程，再对 SQLite 做完整性检查：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo lsof +D /root/du-gateway/data 2>/dev/null || true'
ssh "$OLD_GATEWAY_ALIAS" 'sudo sqlite3 /root/du-gateway/data/runtime_state.sqlite3 "PRAGMA wal_checkpoint(TRUNCATE); PRAGMA quick_check;"'
```

所有 SQLite 必须把主文件、`-wal`、`-shm` 视为同一个一致性单元。不能在 worker 仍写入时只复制主 `.sqlite3`。

### F3. 最终复制变化数据

停写后重新复制：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo tar -C /root -cpf - \
  du-gateway/.env \
  du-gateway/data \
  .config/QQ \
  Napcat' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tar -C /root -xpf -'
```

重新复制 CPA 状态：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo tar -C /home/nora -cpf - .cli-proxy-api' \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tar -C /home/nora -xpf -; sudo chown -R nora:nora /home/nora/.cli-proxy-api'
```

生成旧机数据内容校验表，在新机逐项核对：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo bash -c "cd /root/du-gateway && find data -type f -print0 | sort -z | xargs -0 sha256sum"' \
  > /tmp/du-gateway-data.sha256
cat /tmp/du-gateway-data.sha256 \
  | ssh "$NEW_GATEWAY_ALIAS" 'sudo tee /tmp/du-gateway-data.sha256 >/dev/null; cd /root/du-gateway && sudo sha256sum -c /tmp/du-gateway-data.sha256'
```

校验表不含文件内容，但仍属于运维临时文件；验收后删除本机和新机 `/tmp/du-gateway-data.sha256`。

### F4. 启动新机业务

按依赖顺序：

1. Tailscale / Claude tunnel / CPA。
2. QQ/NapCat 与 QQ connector。
3. WeChat iLink。
4. gateway / realtime。
5. SumiTalk worker。
6. Telegram webhook worker / proactive worker。
7. nginx。

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo systemctl enable --now \
  napcat.service \
  qq-connector.service \
  du-wechat-ilink.service \
  du-gateway.service \
  du-realtime.service \
  du-sumitalk-chat-worker.service \
  du-telegram-webhook-worker.service \
  du-telegram-proactive.service \
  nginx.service'
```

CPA 是 `nora` 的 user service，单独启动：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'systemctl --user enable --now cliproxyapi.service'
```

如果 QQ 需要扫码，先完成扫码并确认 connector 正常，再切 DNS。

## 11. 阶段 G：DNS 切换

由小玥在 Cloudflare 控制台操作：

1. `duxy-home.com` 的 A 记录从 `47.250.162.10` 改成 `${NEW_GATEWAY_IP}`。
2. 新增 `${NEW_PROXY_DOMAIN}` A 记录到 `${NEW_GATEWAY_IP}`。
3. `proxy.duxy-home.com` 保持 `47.250.162.10`。
4. `us.duxy-home.com` 保持 `45.76.171.91`。
5. 不改 MX、DKIM、SPF 等邮件记录。

切换前可提前把主域名 TTL 降低。切换后从旧 VPS、新 VPS、Mac 和手机分别解析确认，不能只看 Clash fake-IP。

## 12. 阶段 H：完整验收

### H1. 公网入口

- `https://duxy-home.com/health` 返回 200。
- `https://duxy-home.com/miniapp/` 可打开，静态资源无 404/502。
- App 可连接实时日志和聊天。
- nginx access/error log 无循环 499/502/504。
- `/var/log/du-gateway` 的 QQ/微信日志可写，`/etc/logrotate.d/du-gateway` 生效。
- `journalctl --disk-usage` 有上限，不允许 systemd journal 无界增长。

### H2. 聊天入口

- QQ 私聊和群聊各一条。
- Telegram 一条普通消息；确认 webhook worker 和 proactive worker 都正常。
- 微信一条消息。
- SumiTalk 一条文字消息，确认 job 入队、独立 worker 消费、前端收到终态。
- App 图片、语音链路按需各测一次。

真实上游测试会产生调用和费用，执行前单独确认；健康检查、模型列表和本地状态检查可以先做。

### H3. 其他业务

- realtime 日志连接。
- XiaoAI 状态、播放/唤醒链路。
- 定时任务、闹钟、随机唤醒、续话。
- CPA 模型列表和上游配置完整。
- Claude tunnel `127.0.0.1:8082` 可达，OAuth 状态可读。
- QQ watchdog cron 正常且不会每分钟重复拉起健康进程。
- 新 Trojan 节点可用；旧代理节点仍可用。

### H4. 数据

- 最近窗口、Last4、动态记忆、阶段摘要、长期素材未丢。
- SumiTalk 队列没有重复消费。
- 页笺、交换日记、秘密抽屉、小游戏存档可读。
- `runtime_state.sqlite3` 和其他 SQLite `PRAGMA quick_check` 通过。

### H5. 重启验收

全部通过后，安排一次新机 reboot：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'sudo reboot'
```

重启后确认所有 enabled 服务、user service、tunnel、Tailscale、nginx、Trojan 自动恢复。没有通过 reboot 验收，不算迁移完成。

### H6. 资源与读盘

至少观察 30 分钟：

```bash
ssh "$NEW_GATEWAY_ALIAS" 'free -h; swapon --show; uptime; sudo systemd-cgtop -b -n 1 | head -40'
ssh "$NEW_GATEWAY_ALIAS" 'sudo iostat -xz 1 10'
```

重点监控：

- 内存是否稳定在 4 GB 预算内。
- swap 是否持续增长。
- `vda` 是否再次出现约 2500 TPS、140 MB/s 读、60 ms 以上 await。
- gunicorn 是否出现 worker 退出后长时间无 worker。
- App 前台上报是否在恢复后短时间形成请求洪峰。

## 13. 回滚

任何一项核心入口失败时，先回滚，不在切流现场大改代码。

1. 在 Cloudflare 把 `duxy-home.com` A 记录改回 `47.250.162.10`。
2. 停止新机业务写入服务，避免双写继续扩大。
3. 启动旧机原业务服务：

```bash
ssh "$OLD_GATEWAY_ALIAS" 'sudo systemctl start \
  napcat.service \
  qq-connector.service \
  du-wechat-ilink.service \
  du-gateway.service \
  du-realtime.service \
  du-sumitalk-chat-worker.service \
  du-telegram-webhook-worker.service \
  du-telegram-proactive.service'
ssh "$OLD_GATEWAY_ALIAS" 'uid=$(id -u nora); sudo -u nora XDG_RUNTIME_DIR=/run/user/$uid systemctl --user start cliproxyapi.service'
ssh "$OLD_GATEWAY_ALIAS" 'sudo test ! -f /root/root.crontab.before-gateway-cutover || sudo crontab /root/root.crontab.before-gateway-cutover'
```

4. 验证旧 `duxy-home.com/health`、MiniApp 和聊天入口。
5. 旧代理从未停止，因此回滚不影响 `proxy.duxy-home.com`。
6. 比较切换后新机产生的数据，再决定是否单向补回旧机；不能直接双向覆盖 SQLite。

## 14. 迁移稳定后的旧机收口

至少观察 24-48 小时后再做：

### 旧机保留

- `trojan.service`
- 只服务 `proxy.duxy-home.com` 的 nginx 配置
- `proxy.duxy-home.com` 证书和 certbot renewal
- `tailscaled.service`
- `fail2ban.service`
- SSH key-only 登录
- 必要日志轮转
- UFW；只在 Tailscale SSH 和旧代理实测通过后启用，允许 22/80/443/8443、UDP 41641 和 `tailscale0:8080`，不开放原业务端口

### 旧机停止并 disable

- `du-gateway.service`
- `du-realtime.service`
- `du-sumitalk-chat-worker.service`
- Telegram 两个 worker
- WeChat iLink
- NapCat / QQ connector / Xvfb
- CPA
- Claude tunnel
- QQ watchdog cron

旧机的 `duxy-home.com` nginx vhost 和证书 renewal 归档，不影响旧代理 vhost。旧数据快照再保留一段时间，确认新机备份建立后再单独决定是否删除。

## 15. 已知风险

1. **QQ 登录态**：跨机复制后可能要求重新扫码。
2. **线上工作树脏**：不能只按 Git commit 重建；必须迁移线上实际文件，并在新机留下 commit + dirty manifest。
3. **SQLite 一致性**：最终同步必须停写；不能只复制主文件。
4. **证书续期分裂**：主域名 renewal 只能由新机负责，旧代理 renewal 继续由旧机负责。
5. **Tailscale SSH/DERP**：当前 Mac 到旧机 Tailscale 曾出现 banner timeout；迁移期间公网 SSH 不能提前关闭，直到新机 Tailscale 实测稳定。
6. **旧 UFW 未启用**：新机绝不能照搬；云防火墙和 UFW 都要配置。
7. **8091/8092 当前监听所有地址**：即使程序不改，新机防火墙也必须阻止公网访问。
8. **疯狂读盘**：2026-07-10 已确认旧机有约 2500 TPS / 140 MB/s 的读盘尖峰和约 12 分钟 gateway worker 空档。新机更大只能提高容错，不等于根因消失。
9. **恢复洪峰**：gateway 恢复后 App 前台上报、XiaoAI claim、状态轮询会集中补发，验收要看 5-10 分钟后的稳定状态。

## 16. 需要小玥操作的节点

1. 创建新 VPS 并提供公网 IP。
2. 确认新代理域名名称。
3. 在 provider 控制台配置首轮云防火墙。
4. Tailscale 登录授权。
5. QQ 如失效则扫码。
6. Cloudflare 修改 `duxy-home.com` A 记录并新增新代理域名。
7. 最终真实聊天/上游扣费测试前确认。

其他系统初始化、文件迁移、服务组装、日志核对、验收和回滚命令由笨笨机执行并逐步汇报。

## 17. 执行状态

- [x] 旧主网关只读盘点。
- [x] 明确旧主网关、Claude 转发 VPS、旧代理三者边界。
- [x] 完整迁移方案和回滚路径。
- [x] 新 VPS 公网 IP 和新代理域名。
- [x] 云防火墙。
- [x] SSH / sudo / UFW / Fail2ban / Tailscale。
- [x] 首轮代码、配置、QQ、CPA、服务迁移。
- [x] 新机离线验收。
- [x] 最终停写同步。
- [x] DNS 切换。
- [x] 全入口基础验收。
- [x] 旧主网关收缩为代理节点。
- [ ] 新主网关整机 reboot 与 App/QQ/TG/微信/SumiTalk 实聊抽测。
