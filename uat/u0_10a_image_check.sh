#!/usr/bin/env bash
# U0.10a G5: build the image on the production Mac without switching anything
# over (design §3.3, risk M8). The production Mac's linux-arm64 Tailwind CLI is
# first used there, so this proves it downloads, matches its SHA-256 and runs.
#
# Run it on the Owner's Mac, not on the production Mac:
#
#     uat/u0_10a_image_check.sh cucumber-server          # at the shop
#     uat/u0_10a_image_check.sh cucumber-server-remote   # away (Cloudflare Access asks first)
#
# It sends the pull request's files over ssh (nothing is cloned or fetched on
# the production Mac), builds two tags of one image, prints what it finds, then
# deletes both tags and the files. It never runs `docker compose`, and it
# touches nothing under ~/cucumber, so the running app, its database and its
# deploys are left alone. The build cache is not pruned: it belongs to docker,
# and the deploy command clears what is over a week old.
set -euo pipefail
cd "$(dirname "$0")/.."

host=${1:?usage: uat/u0_10a_image_check.sh cucumber-server|cucumber-server-remote [revision]}
revision=${2:-HEAD}
work=/tmp/cucumber-g5-image-check
full=cucumber-g5-image-check:run
build=cucumber-g5-image-check:build

echo "==> sending $(git rev-parse --short "$revision") to $host:$work"
git archive "$revision" | ssh "$host" "rm -rf $work && mkdir -p $work && tar -x -C $work"

ssh "$host" bash -s -- "$work" "$full" "$build" <<'REMOTE'
set -euo pipefail
export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH
work=$1 full=$2 build=$3
cd "$work"

cleanup() {
  docker rmi "$full" "$build" >/dev/null 2>&1 || true
  rm -rf "$work"
  echo "==> deleted $full, $build and $work"
}
trap cleanup EXIT

echo "==> machine"
uname -m
docker version --format 'docker server: {{.Server.Os}}/{{.Server.Arch}}'
df -h / | tail -1

echo "==> docker build (the whole image, as the deploy builds it)"
docker build --progress=plain -t "$full" . 2>&1 | tail -60

echo "==> the build stage again (cached), to look inside it"
docker build --target build -t "$build" . >/dev/null
docker run --rm --entrypoint sh "$build" -c '
  uname -m
  ls -l /opt/tools
  sha256sum /opt/tools/*
  ls -l /app/cucumber/core/static/core/cucumber.css'

echo "==> the run image holds no CLI"
docker run --rm --entrypoint sh "$full" -c \
  'ls /opt/tools 2>&1 || true; ls -l /app/cucumber/core/static/core/cucumber.css'
REMOTE

echo "==> the pinned linux-arm64 hash, for comparison"
grep -m1 '"linux-arm64"' scripts/css.py
