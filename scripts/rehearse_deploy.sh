#!/usr/bin/env bash
# Rehearse a staging deploy of this checkout (U0.4a design §9). CI runs it on
# every pull request; it also runs on a Mac with Docker. Fake secrets only, in
# a throwaway CUCUMBER_HOME:
#
#   export CUCUMBER_HOME="$(mktemp -d)/cucumber"
#   scripts/rehearse_deploy.sh setup
#   uv run --no-dev python -m scripts.deploy staging main --source "$PWD"
#   scripts/rehearse_deploy.sh check
#   scripts/rehearse_deploy.sh teardown    # on a Mac; CI throws it all away
#
# The checks send the Host and HTTPS headers Cloudflare sends (design §6.2).
set -euo pipefail
cd "$(dirname "$0")/.."

: "${CUCUMBER_HOME:?set CUCUMBER_HOME to a throwaway folder}"
STAGING="$CUCUMBER_HOME/staging"
MARKER="$CUCUMBER_HOME/.rehearsal"   # teardown runs only where setup ran
HOST="cucumber-staging.example.invalid"
APP_PORT=8001
FLAG="rehearsal_check"

compose() {
  IMAGE_NAME=cucumber-staging CUCUMBER_VERSION="$(cat "$STAGING/current")" \
    docker compose -p cucumber-staging --env-file "$STAGING/secrets.env" \
    -f deploy/compose.server.yaml "$@"
}

page() {  # page <path> [curl options]: as Cloudflare would ask for it
  local path="$1"; shift
  curl --silent --show-error --fail "$@" \
    -H "Host: $HOST" -H "X-Forwarded-Proto: https" "http://127.0.0.1:$APP_PORT$path"
}

pass() { echo "  ok: $1"; }
fail() { echo "  FAILED: $1" >&2; exit 1; }

setup() {
  mkdir -p "$STAGING/backups" "$STAGING/logs"
  touch "$MARKER"
  local key; key="ci-only-not-a-secret-$(printf 'k%.0s' {1..40})"
  ( umask 077
    cat > "$STAGING/secrets.env" <<SECRETS
DJANGO_ENVIRONMENT=staging
DJANGO_SECRET_KEY=$key
DJANGO_ALLOWED_HOSTS=$HOST
DJANGO_CSRF_TRUSTED_ORIGINS=https://$HOST
DJANGO_HSTS_SECONDS=3600
POSTGRES_PASSWORD=ci-only-not-a-secret-postgres
DB_OWNER_PASSWORD=ci-only-not-a-secret-owner
DB_APP_PASSWORD=ci-only-not-a-secret-app
APP_PORT=$APP_PORT
DB_LOCAL_PORT=5435
TUNNEL_TOKEN=not-used-without-the-tunnel-profile
COMPOSE_PROFILES=
APP_MEMORY_LIMIT=512m
DB_MEMORY_LIMIT=512m
TUNNEL_MEMORY_LIMIT=128m
SECRETS
  )
  echo "Pretend staging server ready at $STAGING"
}

check() {
  echo "Checking the rehearsal deploy"
  [ "$(page /health/)" = "ok" ] || fail "/health/ didn't say ok"
  pass "/health/ says ok"

  local login css
  login="$(page /accounts/login/)"
  grep -q "PRACTICE DATA" <<<"$login" || fail "no Practice data banner on staging"
  pass "the login page shows the Practice data banner"
  css="$(grep -o '/static/core/cucumber\.[0-9a-f]*\.css' <<<"$login" | head -1)"
  [ -n "$css" ] || fail "no hashed cucumber.css link on the login page"
  page "$css" --head | grep -qi '^cache-control:.*max-age=315360000' \
    || fail "$css isn't served with a long cache header"
  pass "$css is served by the app with a long cache header"

  local user
  user="$(compose exec -T app python manage.py shell --verbosity 0 -c \
    "from django.db import connection as c; print(c.cursor().execute('SELECT current_user').fetchone()[0])")"
  [ "$(tr -d '[:space:]' <<<"$user")" = "cucumber_app" ] \
    || fail "the app connects as $user, not cucumber_app"
  pass "the app connects as cucumber_app"
  compose exec -T app python -c \
    "import os, sys; sys.exit('DB_OWNER_PASSWORD' in os.environ)" \
    || fail "the app's environment holds the owner password"
  pass "the app's environment has no owner password"

  check_flags
}

check_flags() {
  # Flags are made by a feature's migration, as the owner; here, by hand,
  # named as System like any script's change (U0.7 AC6).
  compose run --rm migrate python manage.py shell --verbosity 0 -c "
from waffle.models import Flag
from cucumber.core.audit import SYSTEM, audited
with audited(SYSTEM, via='rehearsal'):
    Flag.objects.get_or_create(name='$FLAG', defaults={'everyone': False, 'superusers': False})
" > /dev/null
  uv run --no-dev python -m scripts.flag staging "$FLAG" on
  uv run --no-dev python -m scripts.flag staging list | grep -Eq "^ +$FLAG +on$" \
    || fail "the flag isn't on after switching it"
  grep -q "$FLAG on" "$STAGING/logs/flags.log" || fail "flags.log has no line for it"
  pass "the app user switched a flag and flags.log recorded it"
  # Each gunicorn worker must read flags from the database, not its own cache.
  compose exec -T app python manage.py shell --verbosity 0 -c \
    "from django.conf import settings as s; assert s.CACHES[s.WAFFLE_CACHE_NAME]['BACKEND'].endswith('DummyCache')" \
    || fail "flags are cached per worker"
  pass "flags are read fresh on every request in every worker"
}

teardown() {
  [ -f "$MARKER" ] || fail "$CUCUMBER_HOME wasn't made by setup; not touching it"
  compose down --volumes --remove-orphans
  docker image ls cucumber-staging --format '{{.Repository}}:{{.Tag}}' \
    | xargs -r docker image rm
  rm -rf "$CUCUMBER_HOME"
}

case "${1:-}" in
  setup | check | teardown) "$1" ;;
  *) echo "usage: $0 setup|check|teardown" >&2; exit 2 ;;
esac
