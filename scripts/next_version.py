"""Print the next release version: YYYY.MM.N in Bangkok time.

N restarts at 1 each month (docs/roadmap/release-process.md). Both git tags
and draft GitHub Releases count as taken, so running twice can't reuse a
number. Used by the Draft release workflow: `python -m scripts.next_version`.
"""

import re
from collections.abc import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.commands import Runner, run_command

BANGKOK = ZoneInfo("Asia/Bangkok")
VERSION_PATTERN = re.compile(r"^(\d{4})\.(\d{2})\.(\d+)$")


def next_version(existing: Iterable[str], now: datetime) -> str:
    """The version after the highest one in `existing` for `now`'s month.

    Names must match VERSION_PATTERN whole (`fullmatch`); `now` must carry a
    time zone.
    """
    raise NotImplementedError("U0.3 G3")


def existing_versions(run: Runner) -> list[str]:
    """Every git tag and every GitHub Release tag, drafts included.

    Runs `git tag --list` and
    `gh release list --limit 1000 --json tagName --jq .[].tagName`.
    """
    raise NotImplementedError("U0.3 G3")


def main(run: Runner = run_command, now: datetime | None = None) -> None:
    raise NotImplementedError("U0.3 G3")


if __name__ == "__main__":
    main()
