#!/usr/bin/env bash
# U0.2b Owner walk-through (G5): the event core against the SOP.
# Makes a fresh throwaway database, cucumber_uat (your dev data isn't
# touched), runs the story and prints the result. Needs `docker compose up -d`.
set -euo pipefail
cd "$(dirname "$0")/.."   # run from the repo root, wherever it was started

set -a; . ./.env; set +a
export DB_NAME=cucumber_uat

docker compose exec -T db psql -U postgres -q \
  -c "DROP DATABASE IF EXISTS cucumber_uat" \
  -c "CREATE DATABASE cucumber_uat OWNER cucumber_owner" 2>&1 | grep -v NOTICE || true
.venv/bin/python manage.py migrate -v0
.venv/bin/python uat/u0_2b_walkthrough.py | tee uat/u0_2b-result.md
