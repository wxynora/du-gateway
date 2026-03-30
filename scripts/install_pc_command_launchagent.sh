#!/bin/zsh
set -euo pipefail

LABEL="${1:-com.du.pc-command-agent}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
STDOUT_LOG="$LOG_DIR/${LABEL}.out.log"
STDERR_LOG="$LOG_DIR/${LABEL}.err.log"
SERVICE_DIR="$HOME/Library/Application Support/DuPcCommandAgent"
SERVICE_SCRIPT="$SERVICE_DIR/pc_command_agent.py"
RUNNER="$SERVICE_DIR/run_pc_command_agent.sh"
DOWNLOAD_ENV="$HOME/Downloads/.env"
VENV_DIR="$SERVICE_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
INSTALL_STAMP="$SERVICE_DIR/.deps_installed"

if [[ ! -f "$REPO_ROOT/scripts/pc_command_agent.py" ]]; then
  echo "未找到主脚本: $REPO_ROOT/scripts/pc_command_agent.py"
  exit 1
fi

mkdir -p "$PLIST_DIR" "$LOG_DIR" "$SERVICE_DIR"
cp "$REPO_ROOT/scripts/pc_command_agent.py" "$SERVICE_SCRIPT"

if command -v python3 >/dev/null 2>&1; then
  BOOTSTRAP_PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  BOOTSTRAP_PYTHON="$(command -v python)"
else
  echo "未找到 python3 或 python，请先安装 Python 3。"
  exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install requests python-dotenv plyer pyautogui
touch "$INSTALL_STAMP"

cat >"$RUNNER" <<EOF
#!/bin/zsh
set -euo pipefail

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[ERROR] 未找到虚拟环境 Python: $VENV_PYTHON"
  exit 1
fi

pkill -f "pc_command_agent.py" >/dev/null 2>&1 || true

exec "$VENV_PYTHON" "$SERVICE_SCRIPT"
EOF

chmod +x "$RUNNER"

GATEWAY_URL_VALUE=""
PC_COMMAND_TOKEN_VALUE=""
PC_POLL_SECONDS_VALUE=""
if [[ -f "$DOWNLOAD_ENV" ]]; then
  while IFS='=' read -r raw_key raw_value; do
    key="$(printf '%s' "$raw_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    value="$(printf '%s' "${raw_value:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$key" ]] && continue
    [[ "$key" == \#* ]] && continue
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    fi
    if [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    case "$key" in
      GATEWAY_URL) GATEWAY_URL_VALUE="$value" ;;
      PC_COMMAND_TOKEN) PC_COMMAND_TOKEN_VALUE="$value" ;;
      PC_POLL_SECONDS) PC_POLL_SECONDS_VALUE="$value" ;;
    esac
  done <"$DOWNLOAD_ENV"
fi

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RUNNER</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$SERVICE_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>GATEWAY_URL</key>
    <string>$GATEWAY_URL_VALUE</string>
    <key>PC_COMMAND_TOKEN</key>
    <string>$PC_COMMAND_TOKEN_VALUE</string>
    <key>PC_POLL_SECONDS</key>
    <string>$PC_POLL_SECONDS_VALUE</string>
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

echo "已安装并启动 LaunchAgent: $LABEL"
echo "plist: $PLIST_PATH"
echo "stdout: $STDOUT_LOG"
echo "stderr: $STDERR_LOG"
