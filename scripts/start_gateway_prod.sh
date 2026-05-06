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

if ! "$PYTHON_BIN" -c "import gunicorn" >/dev/null 2>&1; then
  echo "缺少 gunicorn。请先执行：$PYTHON_BIN -m pip install -r requirements.txt"
  exit 1
fi

HOST="${GATEWAY_BIND_HOST:-127.0.0.1}"
PORT="${GATEWAY_BIND_PORT:-5000}"
WORKERS="${GATEWAY_WORKERS:-2}"
THREADS="${GATEWAY_THREADS:-8}"
TIMEOUT="${GATEWAY_TIMEOUT:-240}"
GRACEFUL_TIMEOUT="${GATEWAY_GRACEFUL_TIMEOUT:-30}"
KEEP_ALIVE="${GATEWAY_KEEP_ALIVE:-5}"
MAX_REQUESTS="${GATEWAY_MAX_REQUESTS:-800}"
MAX_REQUESTS_JITTER="${GATEWAY_MAX_REQUESTS_JITTER:-80}"
LOG_LEVEL="${GATEWAY_LOG_LEVEL:-info}"

echo "Starting du-gateway via gunicorn on ${HOST}:${PORT}"
echo "workers=${WORKERS} threads=${THREADS} timeout=${TIMEOUT}s max_requests=${MAX_REQUESTS}+${MAX_REQUESTS_JITTER}"

exec "$PYTHON_BIN" -m gunicorn app:app \
  --bind "${HOST}:${PORT}" \
  --worker-class gthread \
  --workers "${WORKERS}" \
  --threads "${THREADS}" \
  --timeout "${TIMEOUT}" \
  --graceful-timeout "${GRACEFUL_TIMEOUT}" \
  --keep-alive "${KEEP_ALIVE}" \
  --max-requests "${MAX_REQUESTS}" \
  --max-requests-jitter "${MAX_REQUESTS_JITTER}" \
  --access-logfile - \
  --error-logfile - \
  --capture-output \
  --log-level "${LOG_LEVEL}"
