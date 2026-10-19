#!/usr/bin/env bash
# The 10× timing check (U0.4b design §13; U0.2a/U0.2b G5 timing notes).
# Makes a fresh throwaway database, cucumber_timing (your dev data isn't
# touched), loads 10× today's data, prints the timings and saves them to
# uat/timing_10x-result.md. Needs `docker compose up -d`. Takes a few minutes.
set -euo pipefail
cd "$(dirname "$0")/.."   # run from the repo root, wherever it was started

set -a; . ./.env; set +a
export DB_NAME=cucumber_timing

fresh_database() {
  docker compose exec -T db psql -U postgres -q \
    -c "DROP DATABASE IF EXISTS cucumber_timing" \
    -c "CREATE DATABASE cucumber_timing OWNER cucumber_owner" 2>&1 | grep -v NOTICE || true
}

fresh_database
.venv/bin/python manage.py migrate -v0
{
  echo "# 10× timing, $(hostname -s), $(date '+%Y-%m-%d %H:%M')"
  echo
  .venv/bin/python -m scripts.timing_10x
  echo
  echo "## Logging in (U0.5)"
  echo
  .venv/bin/python -m scripts.timing_login
} | tee uat/timing_10x-result.md
fresh_database   # leave no 362,000-entry database behind
