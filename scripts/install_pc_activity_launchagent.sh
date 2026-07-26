#!/bin/zsh
set -euo pipefail

LABEL="com.du.pc-activity-agent"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_SCRIPT="$REPO_ROOT/scripts/pc_activity_agent.py"
SERVICE_DIR="$HOME/Library/Application Support/DuPcActivityAgent"
SERVICE_SCRIPT="$SERVICE_DIR/pc_activity_agent.py"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
STDOUT_LOG="$LOG_DIR/$LABEL.out.log"
STDERR_LOG="$LOG_DIR/$LABEL.err.log"
DOWNLOAD_ENV="$HOME/Downloads/.env"

if [[ ! -f "$SOURCE_SCRIPT" ]]; then
  echo "未找到活动上报脚本: $SOURCE_SCRIPT"
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "未找到 Python 3"
  exit 1
fi

GATEWAY_URL_VALUE=""
PC_COMMAND_TOKEN_VALUE=""
PC_ACTIVITY_POLL_SECONDS_VALUE="30"
PC_DEVICE_ID_VALUE=""
if [[ -f "$DOWNLOAD_ENV" ]]; then
  while IFS='=' read -r raw_key raw_value; do
    key="$(printf '%s' "$raw_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    value="$(printf '%s' "${raw_value:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$key" || "$key" == \#* ]] && continue
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    case "$key" in
      GATEWAY_URL) GATEWAY_URL_VALUE="$value" ;;
      PC_COMMAND_TOKEN) PC_COMMAND_TOKEN_VALUE="$value" ;;
      PC_ACTIVITY_POLL_SECONDS) PC_ACTIVITY_POLL_SECONDS_VALUE="$value" ;;
      PC_DEVICE_ID) PC_DEVICE_ID_VALUE="$value" ;;
    esac
  done <"$DOWNLOAD_ENV"
fi

if [[ -z "$GATEWAY_URL_VALUE" || -z "$PC_COMMAND_TOKEN_VALUE" ]]; then
  echo "缺少 GATEWAY_URL 或 PC_COMMAND_TOKEN，请先配置 $DOWNLOAD_ENV"
  exit 1
fi

mkdir -p "$SERVICE_DIR" "$PLIST_DIR" "$LOG_DIR"
cp "$SOURCE_SCRIPT" "$SERVICE_SCRIPT"

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$SERVICE_SCRIPT</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$SERVICE_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>GATEWAY_URL</key>
    <string>$GATEWAY_URL_VALUE</string>
    <key>PC_COMMAND_TOKEN</key>
    <string>$PC_COMMAND_TOKEN_VALUE</string>
    <key>PC_ACTIVITY_POLL_SECONDS</key>
    <string>$PC_ACTIVITY_POLL_SECONDS_VALUE</string>
    <key>PC_DEVICE_ID</key>
    <string>$PC_DEVICE_ID_VALUE</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$STDOUT_LOG</string>
  <key>StandardErrorPath</key>
  <string>$STDERR_LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "已安装并启动独立电脑活动 LaunchAgent: $LABEL"
echo "plist: $PLIST_PATH"
echo "stdout: $STDOUT_LOG"
echo "stderr: $STDERR_LOG"
