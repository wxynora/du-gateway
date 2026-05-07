#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行：sudo bash scripts/install_server_blackbox_timer.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BLACKBOX_SCRIPT="$REPO_ROOT/scripts/server_blackbox.sh"

if [ ! -f "$BLACKBOX_SCRIPT" ]; then
  echo "未找到采样脚本：$BLACKBOX_SCRIPT"
  exit 1
fi

chmod +x "$BLACKBOX_SCRIPT"

cat >/etc/systemd/system/du-server-blackbox.service <<EOF
[Unit]
Description=Du Gateway nightly server blackbox capture

[Service]
Type=oneshot
WorkingDirectory=$REPO_ROOT
Environment=BLACKBOX_DURATION_SECONDS=5400
Environment=BLACKBOX_INTERVAL_SECONDS=10
Environment=BLACKBOX_LOG_DIR=/var/log/du-gateway-blackbox
Environment=BLACKBOX_KEEP_DAYS=7
ExecStart=$BLACKBOX_SCRIPT
TimeoutStartSec=2h
Nice=10
IOSchedulingClass=idle
EOF

cat >/etc/systemd/system/du-server-blackbox.timer <<'EOF'
[Unit]
Description=Run Du Gateway server blackbox capture at 23:00

[Timer]
OnCalendar=*-*-* 23:00:00
AccuracySec=30s
Persistent=false
Unit=du-server-blackbox.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now du-server-blackbox.timer
systemctl list-timers --all du-server-blackbox.timer --no-pager

echo "已安装：每天 23:00 启动黑匣子，默认采样 90 分钟。"
echo "日志目录：/var/log/du-gateway-blackbox/"
echo "最新日志：/var/log/du-gateway-blackbox/latest.log"
echo "手动试跑：systemctl start du-server-blackbox.service"
