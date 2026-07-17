#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${AIFARM_RUNTIME_DIR:-${ROOT_DIR}/vendor/aifarm-oss}"

if ! command -v node >/dev/null 2>&1; then
  echo "未找到 Node.js；AI 农场需要 Node.js >= 20。" >&2
  exit 1
fi

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if [ "${NODE_MAJOR}" -lt 20 ]; then
  echo "当前 Node.js 版本过低；AI 农场需要 Node.js >= 20。" >&2
  exit 1
fi

if [ ! -f "${RUNTIME_DIR}/dist/index.js" ]; then
  echo "找不到 AI 农场运行包：${RUNTIME_DIR}/dist/index.js" >&2
  exit 1
fi

export PORT="${AIFARM_PORT:-8080}"
export HOST="${AIFARM_BIND_HOST:-127.0.0.1}"
export PUBLIC_BASE_URL="${AIFARM_PUBLIC_BASE_URL:-http://127.0.0.1:${PORT}}"

cd "${RUNTIME_DIR}"
exec node dist/index.js
