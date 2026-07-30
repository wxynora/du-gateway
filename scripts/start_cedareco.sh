#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${CEDARECO_RUNTIME_DIR:-${ROOT_DIR}/vendor/cedareco}"
DATA_DIR="${CEDARECO_DATA_DIR:-${ROOT_DIR}/data/cedareco}"
PYTHON_BIN="${CEDARECO_PYTHON:-${ROOT_DIR}/.venv/bin/python}"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "找不到 Python：${PYTHON_BIN}" >&2
  exit 1
fi

PYTHON_VERSION_OK="$("${PYTHON_BIN}" -c 'import sys; print(int(sys.version_info >= (3, 7)))')"
if [ "${PYTHON_VERSION_OK}" != "1" ]; then
  echo "瓶中生态需要 Python 3.7+。" >&2
  exit 1
fi

if [ ! -f "${RUNTIME_DIR}/standalone_server.py" ]; then
  echo "找不到瓶中生态运行包：${RUNTIME_DIR}/standalone_server.py" >&2
  exit 1
fi

umask 077
mkdir -p "${DATA_DIR}"

exec "${PYTHON_BIN}" "${RUNTIME_DIR}/standalone_server.py" \
  --host "${CEDARECO_HOST:-127.0.0.1}" \
  --port "${CEDARECO_PORT:-8765}" \
  --save "${CEDARECO_SAVE_FILE:-${DATA_DIR}/eco_save.json}" \
  --allowed-origin "${CEDARECO_ALLOWED_ORIGIN:-https://duxy-home.com}"
