#!/usr/bin/env bash

set -Eeuo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

repo=/root/du-gateway
target_sha="${1:-}"
lock_file=/run/lock/du-deploy-main.lock

if [[ $# -ne 1 || ! "$target_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: du-deploy-main <40-character-main-commit>" >&2
  exit 2
fi

exec 9>"$lock_file"
flock 9

if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]]; then
  echo "refusing deployment: production tracked worktree is dirty" >&2
  exit 1
fi

if [[ "$(git -C "$repo" branch --show-current)" != "main" ]]; then
  echo "refusing deployment: production checkout is not on main" >&2
  exit 1
fi

git -C "$repo" fetch origin main
git -C "$repo" cat-file -e "$target_sha^{commit}"

current_sha="$(git -C "$repo" rev-parse HEAD)"
origin_main_sha="$(git -C "$repo" rev-parse origin/main)"

if git -C "$repo" merge-base --is-ancestor "$target_sha" "$current_sha"; then
  echo "main target is already deployed: $target_sha"
  exit 0
fi

if ! git -C "$repo" merge-base --is-ancestor "$current_sha" "$target_sha"; then
  echo "refusing deployment: target is not a fast-forward from production" >&2
  exit 1
fi

if ! git -C "$repo" merge-base --is-ancestor "$target_sha" "$origin_main_sha"; then
  echo "refusing deployment: target is not on origin/main" >&2
  exit 1
fi

mapfile -t changed_paths < <(git -C "$repo" diff --name-only "$current_sha" "$target_sha")
git -C "$repo" diff --check "$current_sha" "$target_sha"

discover_active_repo_services() {
  local unit working_directory exec_start
  while read -r unit _; do
    [[ -n "$unit" ]] || continue
    working_directory="$(systemctl show "$unit" -p WorkingDirectory --value)"
    exec_start="$(systemctl show "$unit" -p ExecStart --value)"
    if [[ "$working_directory" == "$repo" || "$working_directory" == "$repo/"* || "$exec_start" == *"$repo/"* ]]; then
      printf '%s\n' "$unit"
    fi
  done < <(systemctl list-units --type=service --state=active --no-legend --plain)
}

mapfile -t active_services < <(discover_active_repo_services | sort -u)
if [[ ${#active_services[@]} -eq 0 ]]; then
  echo "refusing deployment: no active production services use $repo" >&2
  exit 1
fi

declare -A service_workdirs=()
for service in "${active_services[@]}"; do
  service_workdirs["$service"]="$(systemctl show "$service" -p WorkingDirectory --value)"
done

requirements_changed=0
python_changed=0
declare -a node_dependency_dirs=()

append_node_dependency_dir() {
  local candidate_dir="$1" existing service
  [[ -n "$candidate_dir" && "$candidate_dir" != "." ]] || return
  for service in "${active_services[@]}"; do
    [[ "${service_workdirs[$service]}" == "$repo/$candidate_dir" ]] || continue
    for existing in "${node_dependency_dirs[@]}"; do
      [[ "$existing" == "$candidate_dir" ]] && return
    done
    node_dependency_dirs+=("$candidate_dir")
    return
  done
}

for changed_path in "${changed_paths[@]}"; do
  case "$changed_path" in
    requirements.txt)
      requirements_changed=1
      ;;
    *.py)
      python_changed=1
      ;;
  esac
  case "$changed_path" in
    */package.json|*/package-lock.json)
      append_node_dependency_dir "${changed_path%/*}"
      ;;
  esac
done

candidate_parent="$(mktemp -d /tmp/du-deploy-main.XXXXXX)"
candidate="$candidate_parent/tree"
candidate_attached=0
merged=0

sync_dependencies() {
  local python_bin dependency_dir
  if [[ $requirements_changed -eq 1 ]]; then
    for python_bin in "$repo/.venv/bin/python" "$repo/venv/bin/python"; do
      if [[ -x "$python_bin" ]]; then
        "$python_bin" -m pip install -r "$repo/requirements.txt"
      fi
    done
  fi
  for dependency_dir in "${node_dependency_dirs[@]}"; do
    if [[ -f "$repo/$dependency_dir/package-lock.json" ]]; then
      npm --prefix "$repo/$dependency_dir" ci --omit=dev
    elif [[ -f "$repo/$dependency_dir/package.json" ]]; then
      npm --prefix "$repo/$dependency_dir" install --omit=dev
    fi
  done
}

wait_for_http_health() {
  local label="$1" url="$2" require_gateway_ready="${3:-0}"
  local deadline health_body
  deadline=$(( $(date +%s) + 30 ))
  while (( $(date +%s) < deadline )); do
    if health_body="$(curl -fsS --max-time 1 "$url" 2>/dev/null)"; then
      if [[ "$require_gateway_ready" == "1" ]]; then
        if printf '%s' "$health_body" | "$repo/.venv/bin/python" -c \
          'import json, sys; body = json.load(sys.stdin); assert body.get("live") is True and body.get("ready") is True' 2>/dev/null; then
          echo "$label health ready"
          return 0
        fi
      else
        echo "$label health ready"
        return 0
      fi
    fi
    if (( $(date +%s) < deadline )); then
      sleep 1
    fi
  done
  echo "$label health did not become ready within 30 seconds" >&2
  return 1
}

restart_and_verify_services() {
  local service restart_count
  local failed=0
  if ! systemctl restart "${active_services[@]}"; then
    echo "one or more production services failed to restart" >&2
    failed=1
  fi
  for service in "${active_services[@]}"; do
    if systemctl is-active --quiet "$service"; then
      restart_count="$(systemctl show "$service" -p NRestarts --value)"
      echo "$service active NRestarts=$restart_count"
    else
      echo "$service is not active after restart" >&2
      failed=1
    fi
  done

  for service in "${active_services[@]}"; do
    case "$service" in
      du-gateway.service)
        wait_for_http_health "du-gateway" http://127.0.0.1:5000/health 1 || failed=1
        ;;
      du-realtime.service)
        wait_for_http_health "du-realtime" http://127.0.0.1:5010/health || failed=1
        ;;
      du-wechat-ilink.service)
        wait_for_http_health "du-wechat-ilink" http://127.0.0.1:8091/health || failed=1
        ;;
      qq-connector.service)
        wait_for_http_health "qq-connector" http://127.0.0.1:8092/health || failed=1
        ;;
      du-cedareco.service)
        wait_for_http_health "du-cedareco" http://127.0.0.1:8765/api/health || failed=1
        ;;
    esac
  done
  [[ $failed -eq 0 ]]
}

finish() {
  local status=$?
  set +e
  if [[ $candidate_attached -eq 1 ]]; then
    git -C "$repo" worktree remove --force "$candidate" >/dev/null 2>&1
  fi
  rmdir "$candidate_parent" >/dev/null 2>&1
  if [[ $status -ne 0 && $merged -eq 1 ]]; then
    echo "deployment failed; restoring $current_sha" >&2
    git -C "$repo" reset --hard "$current_sha"
    sync_dependencies
    restart_and_verify_services
  fi
  exit "$status"
}
trap finish EXIT

git -C "$repo" worktree add --detach "$candidate" "$target_sha"
candidate_attached=1
for changed_path in "${changed_paths[@]}"; do
  [[ -f "$candidate/$changed_path" ]] || continue
  case "$changed_path" in
    *.py)
      PYTHONDONTWRITEBYTECODE=1 "$repo/.venv/bin/python" -m py_compile "$candidate/$changed_path"
      ;;
    *.js|*.mjs|*.cjs)
      node --check "$candidate/$changed_path"
      ;;
    *.sh)
      bash -n "$candidate/$changed_path"
      ;;
  esac
done

if [[ $python_changed -eq 1 || $requirements_changed -eq 1 ]]; then
  (
    cd "$candidate"
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$candidate" "$repo/.venv/bin/python" -c 'import app'
  )
fi

git -C "$repo" worktree remove --force "$candidate"
candidate_attached=0
rmdir "$candidate_parent"

git -C "$repo" merge --ff-only "$target_sha"
merged=1
sync_dependencies
restart_and_verify_services

merged=0
echo "main deployed: $target_sha"
