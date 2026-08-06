#!/usr/bin/env bash

set -euo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

repo=/root/du-gateway
service=qq-connector.service
health_url=http://127.0.0.1:8092/health
target_sha="${1:-}"
lock_file=/run/lock/du-deploy-qq.lock

if [[ $# -ne 1 || ! "$target_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: du-deploy-qq <40-character-main-commit>" >&2
  exit 2
fi

exec 9>"$lock_file"
flock 9

if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]]; then
  echo "refusing deployment: production tracked worktree is dirty" >&2
  exit 1
fi

git -C "$repo" fetch origin main
git -C "$repo" cat-file -e "$target_sha^{commit}"

current_sha="$(git -C "$repo" rev-parse HEAD)"
origin_main_sha="$(git -C "$repo" rev-parse origin/main)"

if git -C "$repo" merge-base --is-ancestor "$target_sha" "$current_sha"; then
  echo "QQ connector target is already deployed: $target_sha"
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
if [[ ${#changed_paths[@]} -eq 0 ]]; then
  echo "QQ connector target has no changes to deploy: $target_sha"
  exit 0
fi

for changed_path in "${changed_paths[@]}"; do
  case "$changed_path" in
    connectors/qq_onebot/src/*)
      ;;
    *)
      echo "refusing deployment: path outside QQ connector source: $changed_path" >&2
      exit 1
      ;;
  esac
done

git -C "$repo" diff --check "$current_sha" "$target_sha" -- connectors/qq_onebot/src/

candidate_parent="$(mktemp -d /tmp/du-deploy-qq.XXXXXX)"
candidate="$candidate_parent/tree"
candidate_attached=0
merged=0
deploy_started_at=0

finish() {
  status=$?
  if [[ $candidate_attached -eq 1 ]]; then
    git -C "$repo" worktree remove --force "$candidate" >/dev/null 2>&1 || true
  fi
  rmdir "$candidate_parent" >/dev/null 2>&1 || true
  if [[ $status -ne 0 && $merged -eq 1 ]]; then
    echo "deployment failed; restoring $current_sha" >&2
    git -C "$repo" reset --hard "$current_sha"
    systemctl restart "$service" || true
  fi
  exit "$status"
}
trap finish EXIT

git -C "$repo" worktree add --detach "$candidate" "$target_sha"
candidate_attached=1
for changed_path in "${changed_paths[@]}"; do
  if [[ "$changed_path" == *.js && -f "$candidate/$changed_path" ]]; then
    node --check "$candidate/$changed_path"
  fi
done
git -C "$repo" worktree remove --force "$candidate"
candidate_attached=0
rmdir "$candidate_parent"

git -C "$repo" merge --ff-only "$target_sha"
merged=1
deploy_started_at="$(date +%s)"
systemctl restart "$service"
systemctl is-active --quiet "$service"
curl -fsS "$health_url"

restart_count="$(systemctl show "$service" -p NRestarts --value)"
echo
echo "NRestarts=$restart_count"

warning_log="$(journalctl -q -u "$service" --since "@$deploy_started_at" -p warning --no-pager || true)"
if [[ -n "$warning_log" ]]; then
  echo "$warning_log" >&2
  exit 1
fi

merged=0
echo "QQ connector deployed: $target_sha"
