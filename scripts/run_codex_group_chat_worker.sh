#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  elif [[ -x "$REPO_ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$REPO_ROOT"
exec "$PYTHON_BIN" "$REPO_ROOT/scripts/codex_group_chat_worker.py"
