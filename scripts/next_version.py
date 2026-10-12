"""Print the next release version: YYYY.MM.N in Bangkok time.

N restarts at 1 each month (docs/roadmap/release-process.md). Both git tags
and draft GitHub Releases count as taken, so running twice can't reuse a
number. Used by the Draft release workflow: `python -m scripts.next_version`.
"""

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from scripts.commands import Runner, run_command

BANGKOK = ZoneInfo("Asia/Bangkok")
VERSION_PATTERN = re.compile(r"(\d{4})\.(\d{2})\.(\d+)")
GIT_TAGS = ["git", "tag", "--list"]
GITHUB_RELEASES = [
    "gh", "release", "list", "--limit", "1000",
    "--json", "tagName", "--jq", ".[].tagName",
]  # fmt: skip


def next_version(existing: Iterable[str], now: datetime) -> str:
    """The version after the highest one in `existing` for `now`'s month.

    Names must match VERSION_PATTERN whole (`fullmatch`); `now` must carry a
    time zone.
    """
    if now.utcoffset() is None:
        raise ValueError("`now` must carry a time zone, e.g. datetime.now(UTC)")
    today = now.astimezone(BANGKOK)
    numbers_this_month = [
        int(match[3])
        for name in existing
        if (match := VERSION_PATTERN.fullmatch(name))
        and (int(match[1]), int(match[2])) == (today.year, today.month)
    ]
    number = max(numbers_this_month, default=0) + 1
    return f"{today.year:04d}.{today.month:02d}.{number}"


def existing_versions(run: Runner) -> list[str]:
    """Every git tag and every GitHub Release tag, drafts included.

    Runs `git tag --list` and
    `gh release list --limit 1000 --json tagName --jq .[].tagName`.
    """
    output = "\n".join([run(GIT_TAGS), run(GITHUB_RELEASES)])
    return [line.strip() for line in output.splitlines() if line.strip()]


def main(run: Runner = run_command, now: datetime | None = None) -> None:
    print(next_version(existing_versions(run), now or datetime.now(UTC)))


if __name__ == "__main__":
    main()
