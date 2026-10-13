"""Deploy one version to staging or production (U0.4a design §6, AC10-AC12).

    uv run --no-dev python -m scripts.deploy staging 2026.10.1
    uv run --no-dev python -m scripts.deploy staging main
    uv run --no-dev python -m scripts.deploy production 2026.10.1

Checks, gets the version, builds it, checks the database fits, saves a copy
of the database, migrates, restarts the app and checks it answers. Prints
each step in plain words and saves them to the environment's logs folder.
If the new version doesn't answer, puts the previous one back when that is
safe (design §6.3).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from scripts.server import NOT_BUILT, Tools

HEALTH_WAIT_SECONDS = 60
BACKUPS_KEPT = 5
IMAGES_KEPT = 3
LOG_LINES_ON_FAILURE = 30


@dataclass(frozen=True)
class Pending:
    """What `manage.py pending_migrations` reported for one version."""

    to_run: tuple[str, ...]  # migrations this version has and the database lacks
    unknown: tuple[str, ...]  # applied migrations this version doesn't have


def is_version_tag(name: str) -> bool:
    """True for a release tag, `YYYY.MM.N` with a month from 01 to 12."""
    raise NotImplementedError(NOT_BUILT)


def check_version(environment: str, version: str, *, from_source: bool) -> None:
    """Stop unless this environment may run this version (AC11).

    Production takes release tags only; staging also takes `main`, and only
    staging may build from a local checkout (`--source`, CI rehearsal).
    """
    raise NotImplementedError(NOT_BUILT)


def parse_pending(output: str) -> Pending:
    """Read the JSON that `manage.py pending_migrations` prints."""
    raise NotImplementedError(NOT_BUILT)


def backup_name(now: datetime, version: str) -> str:
    """E.g. `2026-10-13-1405-before-2026.10.1.dump`, in Bangkok time."""
    raise NotImplementedError(NOT_BUILT)


def format_duration(seconds: float) -> str:
    """E.g. `2 min 41 s`, or `45 s` under a minute."""
    raise NotImplementedError(NOT_BUILT)


def images_to_remove(
    tags_newest_first: Sequence[str], keep_also: Sequence[str] = ()
) -> list[str]:
    """Tags beyond the newest IMAGES_KEPT, never one listed in `keep_also`."""
    raise NotImplementedError(NOT_BUILT)


def main(
    argv: Sequence[str] | None = None,
    tools: Tools | None = None,
    os_environ: Mapping[str, str] | None = None,
) -> int:
    """Run one deploy; 0 when the new version answers, 1 otherwise."""
    raise NotImplementedError(NOT_BUILT)


if __name__ == "__main__":
    raise SystemExit(main())
