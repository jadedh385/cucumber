#!/usr/bin/env bash
# Every check, in one command: the same on a laptop, the MacBook and GitHub.
# Stops at the first check that fails and says which one.
set -euo pipefail
cd "$(dirname "$0")/.."   # run from the repo root, wherever it was started

if [ -f .env ]; then
  export UV_ENV_FILE=.env   # local values; CI sets its own environment
fi

echo "==> Format (ruff format)";  uv run ruff format --check .
echo "==> Lint (ruff check)";     uv run ruff check .
echo "==> Types (mypy)";          uv run mypy cucumber scripts e2e uat conftest.py
echo "==> Tests and coverage (pytest)"; uv run pytest
