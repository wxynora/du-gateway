#!/usr/bin/env bash
set -uo pipefail

DURATION_SECONDS="${BLACKBOX_DURATION_SECONDS:-5400}"
INTERVAL_SECONDS="${BLACKBOX_INTERVAL_SECONDS:-10}"
LOG_DIR="${BLACKBOX_LOG_DIR:-/var/log/du-gateway-blackbox}"
KEEP_DAYS="${BLACKBOX_KEEP_DAYS:-7}"
LOCK_FILE="${BLACKBOX_LOCK_FILE:-/run/du-server-blackbox.lock}"

mkdir -p "$LOG_DIR"

exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
  if ! flock -n 9; then
    echo "blackbox already running"
    exit 0
  fi
fi

RUN_ID="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/blackbox-$RUN_ID.log"
LATEST_LINK="$LOG_DIR/latest.log"
START_TS="$(date +%s)"
END_TS=$((START_TS + DURATION_SECONDS))

ln -sfn "$LOG_FILE" "$LATEST_LINK" 2>/dev/null || true
find "$LOG_DIR" -type f -name 'blackbox-*.log' -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true

section() {
  printf '\n===== %s =====\n' "$1"
}

safe_run() {
  "$@" 2>&1 || true
}

snapshot() {
  local now
  now="$(date '+%F %T %z')"
  section "snapshot $now"

  printf 'uptime: '
  safe_run uptime

  section "memory"
  safe_run free -h
  safe_run swapon --show
  safe_run awk '/MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|Dirty|Writeback|Slab|SReclaimable|SUnreclaim/ {print}' /proc/meminfo

  section "pressure"
  if [ -r /proc/pressure/cpu ]; then
    printf 'cpu: '
    safe_run cat /proc/pressure/cpu
  fi
  if [ -r /proc/pressure/memory ]; then
    printf 'memory: '
    safe_run cat /proc/pressure/memory
  fi
  if [ -r /proc/pressure/io ]; then
    printf 'io: '
    safe_run cat /proc/pressure/io
  fi

  section "vmstat"
  safe_run vmstat 1 2

  section "top cpu"
  safe_run ps -eo pid,ppid,stat,%cpu,%mem,rss,vsz,etime,cmd --sort=-%cpu | head -35

  section "top rss"
  safe_run ps -eo pid,ppid,stat,%cpu,%mem,rss,vsz,etime,cmd --sort=-rss | head -35

  section "key processes"
  safe_run pgrep -af 'gunicorn|uvicorn|run_telegram_proactive|Napcat|QQ/qq|qq_onebot|wechat_ilink|node ./src/main.js|AliYunDun|argusagent|cloudmonitor|trojan|nginx|journald|rsyslogd'

  section "sockets"
  safe_run ss -s
  safe_run ss -tanp | awk '{print $1,$4,$5,$6,$7}' | sort | uniq -c | sort -nr | head -40

  section "disk"
  safe_run df -h /
  if command -v iostat >/dev/null 2>&1; then
    safe_run iostat -xz 1 2
  else
    safe_run awk '{print}' /proc/diskstats
  fi
}

{
  section "du server blackbox start"
  echo "run_id=$RUN_ID"
  echo "duration_seconds=$DURATION_SECONDS"
  echo "interval_seconds=$INTERVAL_SECONDS"
  echo "log_file=$LOG_FILE"
  echo "started_at=$(date '+%F %T %z')"

  while [ "$(date +%s)" -lt "$END_TS" ]; do
    snapshot
    sleep "$INTERVAL_SECONDS"
  done

  section "du server blackbox end"
  echo "ended_at=$(date '+%F %T %z')"
} >>"$LOG_FILE" 2>&1
