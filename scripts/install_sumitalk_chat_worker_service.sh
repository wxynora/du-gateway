#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-du-sumitalk-chat-worker}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 sudo 运行：sudo bash scripts/install_sumitalk_chat_worker_service.sh" >&2
  exit 1
fi

if [ ! -d "$REPO_ROOT" ]; then
  echo "仓库目录不存在：$REPO_ROOT" >&2
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "未找到可执行的项目 Python：$PYTHON_BIN" >&2
  echo "请先在仓库里准备 .venv，或显式传入 PYTHON_BIN=/path/to/python" >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import flask  # noqa: F401
import scripts.run_sumitalk_chat_worker  # noqa: F401
PY

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Du Gateway SumiTalk Chat Worker
After=network-online.target du-gateway.service
Wants=network-online.target du-gateway.service

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON_BIN $REPO_ROOT/scripts/run_sumitalk_chat_worker.py
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME.service"
systemctl restart "$SERVICE_NAME.service"
systemctl status "$SERVICE_NAME.service" --no-pager -l | sed -n "1,45p"

echo
echo "查看日志：sudo journalctl -u $SERVICE_NAME.service -f"
echo "重启服务：sudo systemctl restart $SERVICE_NAME.service"
