#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-du-aifarm}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_USER="${SERVICE_USER:-root}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 sudo 运行：sudo bash scripts/install_aifarm_service.sh" >&2
  exit 1
fi

if [ ! -x "$REPO_ROOT/scripts/start_aifarm.sh" ]; then
  echo "找不到 AI 农场启动脚本：$REPO_ROOT/scripts/start_aifarm.sh" >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "服务用户不存在：$SERVICE_USER" >&2
  exit 1
fi

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Du AI Farm Sidecar
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$REPO_ROOT
EnvironmentFile=-$REPO_ROOT/.env
Environment=AIFARM_BIND_HOST=127.0.0.1
Environment=AIFARM_PORT=8080
ExecStart=$REPO_ROOT/scripts/start_aifarm.sh
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME.service"

echo "已安装并启用 $SERVICE_NAME.service；本脚本不会直接启动它。"
echo "首次启动：sudo systemctl start $SERVICE_NAME.service"
echo "查看日志：sudo journalctl -u $SERVICE_NAME.service -f"
