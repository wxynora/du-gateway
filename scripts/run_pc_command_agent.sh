#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "[ERROR] 未找到 python3 或 python，请先安装 Python 3。"
  exit 1
fi

pkill -f "pc_command_agent.py" >/dev/null 2>&1 || true

exec "$PYTHON_BIN" "$REPO_ROOT/scripts/pc_command_agent.py"
