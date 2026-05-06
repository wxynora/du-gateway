#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
else
  echo "未找到 Python。请先安装 python3，或创建 .venv。"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "缺少 FastAPI/Uvicorn。请先执行：$PYTHON_BIN -m pip install -r requirements.txt"
  exit 1
fi

HOST="${REALTIME_BIND_HOST:-127.0.0.1}"
PORT="${REALTIME_BIND_PORT:-5010}"
WORKERS="${REALTIME_WORKERS:-1}"
LOG_LEVEL="${REALTIME_LOG_LEVEL:-info}"

echo "Starting du-gateway realtime service on ${HOST}:${PORT}"

exec "$PYTHON_BIN" -m uvicorn services.realtime_app:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${WORKERS}" \
  --proxy-headers \
  --timeout-keep-alive "${REALTIME_KEEP_ALIVE:-30}" \
  --ws-ping-interval "${REALTIME_WS_PING_INTERVAL:-25}" \
  --ws-ping-timeout "${REALTIME_WS_PING_TIMEOUT:-20}" \
  --log-level "${LOG_LEVEL}"
