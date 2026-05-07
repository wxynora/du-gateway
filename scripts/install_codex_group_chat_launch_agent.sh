#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${CODEX_GROUP_CHAT_LAUNCH_LABEL:-com.dugateway.codex-group-chat-bridge}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$REPO_ROOT/logs"
UID_VALUE="$(id -u)"

case "$REPO_ROOT" in
  "$HOME/Downloads"/*|"$HOME/Desktop"/*|"$HOME/Documents"/*)
    cat >&2 <<EOF
Refusing to install LaunchAgent from a macOS privacy-protected folder:
  $REPO_ROOT

Move the repo to a normal directory such as:
  $HOME/du-gateway

or grant Full Disk Access to /bin/bash and /usr/bin/env, then rerun this script.
EOF
    exit 1
    ;;
esac

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

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
    <string>$REPO_ROOT/scripts/run_codex_group_chat_worker.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
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
launchctl print "gui/$UID_VALUE/$LABEL" | sed -n '1,80p'
