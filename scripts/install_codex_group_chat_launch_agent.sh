#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${CODEX_GROUP_CHAT_LAUNCH_LABEL:-com.dugateway.codex-group-chat-bridge}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INSTALL_DIR="${CODEX_GROUP_CHAT_INSTALL_DIR:-$HOME/.du-gateway-codex-bridge}"
RUNTIME_REPO="$INSTALL_DIR/runtime_repo"
LOG_DIR="$INSTALL_DIR/logs"
RUNNER="$INSTALL_DIR/run_codex_group_chat_worker.sh"
BRIDGE_SCRIPT="$INSTALL_DIR/codex_group_chat_bridge.py"
ENV_FILE="$INSTALL_DIR/.env"
UID_VALUE="$(id -u)"
HOST_NAME="$(hostname)"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$RUNTIME_REPO"

read_dotenv_value() {
  local key="$1"
  local file="$2"
  python3 - "$key" "$file" <<'PY'
import shlex
import sys

key, path = sys.argv[1], sys.argv[2]
try:
    lines = open(path, "r", encoding="utf-8").read().splitlines()
except Exception:
    raise SystemExit(0)
prefix = f"{key}="
export_prefix = f"export {key}="
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith(export_prefix):
        value = line[len(export_prefix):].strip()
    elif line.startswith(prefix):
        value = line[len(prefix):].strip()
    else:
        continue
    try:
        parts = shlex.split(value, comments=False, posix=True)
        if parts:
            print(parts[0])
        else:
            print("")
    except Exception:
        print(value.strip().strip("\"'"))
    break
PY
}

for SOURCE_ENV in "$REPO_ROOT/.env" "$HOME/Downloads/.env"; do
  if [[ -f "$SOURCE_ENV" ]]; then
    GATEWAY_URL="${GATEWAY_URL:-$(read_dotenv_value GATEWAY_URL "$SOURCE_ENV")}"
    PC_COMMAND_TOKEN="${PC_COMMAND_TOKEN:-$(read_dotenv_value PC_COMMAND_TOKEN "$SOURCE_ENV")}"
  fi
done
for SOURCE_ENV in "$REPO_ROOT/.env" "$HOME/Downloads/.env"; do
  if [[ -f "$SOURCE_ENV" ]]; then
    GATEWAY_URL="${GATEWAY_URL:-$(read_dotenv_value TELEGRAM_GATEWAY_URL "$SOURCE_ENV")}"
  fi
done

if [[ -z "${GATEWAY_URL:-}" || -z "${PC_COMMAND_TOKEN:-}" ]]; then
  cat >&2 <<EOF
GATEWAY_URL 或 PC_COMMAND_TOKEN 未配置。
请先在 $REPO_ROOT/.env 里配置，或在当前 shell 导出后重试。
EOF
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-$INSTALL_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$INSTALL_DIR/.venv"
  "$PYTHON_BIN" -m pip install --upgrade pip >/dev/null
  "$PYTHON_BIN" -m pip install requests python-dotenv >/dev/null
fi

CODEX_BIN="${CODEX_BIN:-$(command -v codex || true)}"
CODEX_BIN="${CODEX_BIN:-codex}"

cp "$REPO_ROOT/scripts/codex_group_chat_bridge.py" "$BRIDGE_SCRIPT"
if [[ -f "$REPO_ROOT/AGENTS.md" ]]; then
  cp "$REPO_ROOT/AGENTS.md" "$RUNTIME_REPO/AGENTS.md"
else
  printf '你是笨笨机。短一点、自然一点、不要抢渡的位置。\n' > "$RUNTIME_REPO/AGENTS.md"
fi

cat > "$ENV_FILE" <<EOF
GATEWAY_URL=$GATEWAY_URL
PC_COMMAND_TOKEN=$PC_COMMAND_TOKEN
CODEX_BIN=$CODEX_BIN
CODEX_GROUP_CHAT_REPO=$RUNTIME_REPO
CODEX_GROUP_CHAT_STATE_PATH=$INSTALL_DIR/state.json
CODEX_GROUP_CHAT_FINISH_OUTBOX_PATH=$INSTALL_DIR/finish_outbox.json
CODEX_GROUP_CHAT_WORKER_ID=${CODEX_GROUP_CHAT_WORKER_ID:-benben-codex-bridge@$HOST_NAME}
CODEX_GROUP_CHAT_RESUME_ENABLED=${CODEX_GROUP_CHAT_RESUME_ENABLED:-1}
CODEX_GROUP_CHAT_POST_RETRY_ATTEMPTS=${CODEX_GROUP_CHAT_POST_RETRY_ATTEMPTS:-3}
CODEX_GROUP_CHAT_CLAIM_BACKOFF_MAX_SECONDS=${CODEX_GROUP_CHAT_CLAIM_BACKOFF_MAX_SECONDS:-8}
CODEX_GROUP_CHAT_HEARTBEAT_SECONDS=${CODEX_GROUP_CHAT_HEARTBEAT_SECONDS:-30}
CODEX_GROUP_CHAT_FINISH_OUTBOX_RETRY_MAX_SECONDS=${CODEX_GROUP_CHAT_FINISH_OUTBOX_RETRY_MAX_SECONDS:-60}
CODEX_GROUP_CHAT_EXTRA_CODEX_ARGS=${CODEX_GROUP_CHAT_EXTRA_CODEX_ARGS:---skip-git-repo-check}
EOF
chmod 600 "$ENV_FILE"

cat > "$RUNNER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$INSTALL_DIR"
exec "$PYTHON_BIN" "$BRIDGE_SCRIPT"
EOF
chmod +x "$RUNNER"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$RUNNER</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$INSTALL_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/codex_group_chat_bridge.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/codex_group_chat_bridge.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$UID_VALUE" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_VALUE" "$PLIST"
launchctl kickstart -k "gui/$UID_VALUE/$LABEL"

echo "installed $LABEL"
echo "runtime $INSTALL_DIR"
launchctl print "gui/$UID_VALUE/$LABEL" | sed -n '1,80p'
