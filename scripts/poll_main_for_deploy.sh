#!/usr/bin/env bash

set -Eeuo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

repo="${DU_DEPLOY_REPO:-/root/du-gateway}"
deployer="${DU_DEPLOY_COMMAND:-/usr/local/sbin/du-deploy-main}"

git -C "$repo" fetch --quiet origin main

current_sha="$(git -C "$repo" rev-parse HEAD)"
target_sha="$(git -C "$repo" rev-parse origin/main)"

if [[ "$current_sha" == "$target_sha" ]]; then
  exit 0
fi

exec "$deployer" "$target_sha"
