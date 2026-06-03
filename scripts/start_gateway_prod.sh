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
# Keep the default profile conservative: the gateway usually shares a small VPS
# with NapCat/NTQQ, where extra workers/threads cost real memory headroom.
WORKERS="${GATEWAY_WORKERS:-1}"
THREADS="${GATEWAY_THREADS:-4}"
TIMEOUT="${GATEWAY_TIMEOUT:-360}"
GRACEFUL_TIMEOUT="${GATEWAY_GRACEFUL_TIMEOUT:-30}"
KEEP_ALIVE="${GATEWAY_KEEP_ALIVE:-5}"
MAX_REQUESTS="${GATEWAY_MAX_REQUESTS:-240}"
MAX_REQUESTS_JITTER="${GATEWAY_MAX_REQUESTS_JITTER:-40}"
LOG_LEVEL="${GATEWAY_LOG_LEVEL:-info}"

cap_positive_int() {
  local label="$1"
  local current="$2"
  local cap="$3"
  if [[ "$current" =~ ^[0-9]+$ && "$cap" =~ ^[0-9]+$ && "$cap" -gt 0 && "$current" -gt "$cap" ]]; then
    echo "${label}=${current} exceeds safety cap ${cap}; using ${cap}. Set GATEWAY_DISABLE_SAFETY_CAPS=1 to override." >&2
    printf '%s' "$cap"
    return
  fi
  printf '%s' "$current"
}

if [ "${GATEWAY_DISABLE_SAFETY_CAPS:-0}" != "1" ]; then
  WORKERS="$(cap_positive_int GATEWAY_WORKERS "$WORKERS" "${GATEWAY_WORKERS_MAX:-1}")"
  THREADS="$(cap_positive_int GATEWAY_THREADS "$THREADS" "${GATEWAY_THREADS_MAX:-6}")"
  MAX_REQUESTS="$(cap_positive_int GATEWAY_MAX_REQUESTS "$MAX_REQUESTS" "${GATEWAY_MAX_REQUESTS_CAP:-300}")"
fi

export GATEWAY_EMBEDDED_SCHEDULE_RUNTIME_ENABLED="${GATEWAY_EMBEDDED_SCHEDULE_RUNTIME_ENABLED:-0}"

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
