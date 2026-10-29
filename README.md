# Cucumber

Plant lab inventory for SEC: plants, batches and everything that happens to
them, recorded as events that are never edited or deleted. Built with Django
5.2 and PostgreSQL 17 ([ADR-0001](docs/roadmap/adr/0001-stack-selection.md)).

The plan, gates and decisions live in [docs/roadmap](docs/roadmap/README.md).

## Set up (Mac)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   and [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. `cp .env.example .env`, then fill in local values: any long random text for
   the passwords and secret key, with `DB_PASSWORD` the same as
   `DB_OWNER_PASSWORD`.
3. `docker compose up -d --wait` starts the local database. Its set-up script
   runs only on an **empty** database: to start over, run
   `docker compose down -v` first (this deletes local data).
4. `uv sync` installs Python and the packages.
5. `uv run playwright install chromium` installs the test browser.
6. `scripts/check.sh` runs every check.
7. `uv run python -m scripts.dev` runs the site at http://127.0.0.1:8000/
   and rebuilds the stylesheet on each change; Ctrl-C stops both. The first
   run downloads the pinned Tailwind CLI into `.cache/tools/`. Edit
   `cucumber/core/css/source.css`, never the built `cucumber.css`.

Every database connection ends a transaction left idle for 10 seconds, and
a query running 10 seconds (U0.10a §8.1). That holds in `pytest`, in
`manage.py shell` and while stopped at a breakpoint too: pausing longer
inside a transaction ends the connection.

## Every check: `scripts/check.sh`

Runs, in order, and stops at the first failure:

| Check | Tool | Fails when |
|---|---|---|
| Format | `ruff format --check` | code isn't formatted (`uv run ruff format .` fixes it) |
| Lint | `ruff check` | likely bugs, unsafe code or untidy imports; names the file and line |
| Types | `mypy` | a value is used as the wrong type |
| Tests | `pytest` | any test fails, or coverage of the app is under 80 % |

GitHub runs the same script on every pull request (`.github/workflows/ci.yml`).

## Layout

| Folder | What's in it |
|---|---|
| `cucumber/` | The Django project: settings and one app per feature (`core`, `accounts`, `references`, `plants`, `batches`, `events`). Each app keeps its rules in `services.py` and its tests in `tests/`. |
| `e2e/` | Browser tests at phone width (Playwright) |
| `scripts/` | `check.sh` and the release-notes helpers |
| `docker/postgres/init/` | Creates the two database users, `cucumber_owner` and `cucumber_app` |
| `docs/` | Roadmap, decisions, runbooks |

## Pull requests and releases

- Titles read `type: description` (`feat`, `fix`, `perf`, `refactor`, `docs`,
  `test`, `chore`, `ci`); a check enforces it. Merges are squash-only, so the
  title becomes the commit.
- Merge only when every check is green: GitHub can't enforce this on our plan.
- Each pull request's **Staff note** goes into the release notes
  ([release process](docs/roadmap/release-process.md)).
