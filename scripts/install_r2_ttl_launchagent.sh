#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TTL_SCRIPT="$REPO_ROOT/scripts/prune_r2_ttl.py"
PLIST_DIR="$HOME/Library/LaunchAgents"
STATE_DIR="$HOME/Library/Application Support/DuGatewayR2TTL"
LOG_DIR="$HOME/Library/Logs/du-gateway-r2-ttl"
DAILY_LABEL="${DU_R2_TTL_DAILY_LABEL:-com.dugateway.r2-ttl.daily}"
MONTHLY_LABEL="${DU_R2_TTL_MONTHLY_LABEL:-com.dugateway.r2-ttl.monthly}"
DAILY_PLIST="$PLIST_DIR/$DAILY_LABEL.plist"
MONTHLY_PLIST="$PLIST_DIR/$MONTHLY_LABEL.plist"
UID_VALUE="$(id -u)"

if [[ ! -f "$TTL_SCRIPT" ]]; then
  echo "未找到 R2 TTL 清理脚本：$TTL_SCRIPT"
  exit 1
fi

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "未找到 Python。请先安装 python3，或创建 $REPO_ROOT/.venv。"
  exit 1
fi

mkdir -p "$PLIST_DIR" "$STATE_DIR" "$LOG_DIR"
chmod +x "$TTL_SCRIPT"

cat >"$DAILY_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$DAILY_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$TTL_SCRIPT</string>
    <string>--apply</string>
    <string>--skip-conversations</string>
    <string>--manifest</string>
    <string>$STATE_DIR/daily-latest-manifest.json</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>4</integer>
    <key>Minute</key>
    <integer>35</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/daily.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/daily.err.log</string>
</dict>
</plist>
EOF

cat >"$MONTHLY_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$MONTHLY_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$TTL_SCRIPT</string>
    <string>--apply</string>
    <string>--skip-sense-history</string>
    <string>--skip-summary-backups</string>
    <string>--manifest</string>
    <string>$STATE_DIR/monthly-latest-manifest.json</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Day</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>4</integer>
    <key>Minute</key>
    <integer>55</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/monthly.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/monthly.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$UID_VALUE" "$DAILY_PLIST" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE" "$MONTHLY_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_VALUE" "$DAILY_PLIST"
launchctl bootstrap "gui/$UID_VALUE" "$MONTHLY_PLIST"
launchctl enable "gui/$UID_VALUE/$DAILY_LABEL"
launchctl enable "gui/$UID_VALUE/$MONTHLY_LABEL"

echo "已安装本地 LaunchAgent："
echo "- ${DAILY_LABEL}：每天 04:35 清理 24h TTL（sense/history、summary_backups）"
echo "- ${MONTHLY_LABEL}：每月 1 日 04:55 清理对话原文/思维链归档"
echo "plist: $DAILY_PLIST"
echo "plist: $MONTHLY_PLIST"
echo "日志目录: $LOG_DIR"
echo "清单目录: $STATE_DIR"
echo "手动查看:"
echo "launchctl print gui/$UID_VALUE/$DAILY_LABEL"
echo "launchctl print gui/$UID_VALUE/$MONTHLY_LABEL"
