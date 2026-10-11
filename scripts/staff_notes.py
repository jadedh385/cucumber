"""Collect the "Staff note" of every pull request in a release.

The pull requests are found from the `(#N)` endings of the squash commits in
the release's git range, so the notes always match the commits. Notes that
say "None" are skipped. Used by the Draft release workflow:
`python -m scripts.staff_notes <last-tag>..<sha>`.
"""

import sys
from collections.abc import Callable, Iterable, Sequence

from scripts.commands import Runner, run_command

NO_NOTES = "Nothing staff will notice in this release."


def pr_numbers(log: str) -> list[int]:
    """Pull request numbers from commit subjects ending in `(#N)`, in order."""
    raise NotImplementedError("U0.3 G3")


def staff_note(body: str) -> str | None:
    """The text under `## Staff note`, or None if missing, empty or "None"."""
    raise NotImplementedError("U0.3 G3")


def collect_notes(
    numbers: Iterable[int], fetch_body: Callable[[int], str]
) -> list[str]:
    """The staff notes of these pull requests, skipping those without one."""
    raise NotImplementedError("U0.3 G3")


def format_notes(notes: Sequence[str]) -> str:
    """One bullet per note, or a sentence saying there is nothing."""
    raise NotImplementedError("U0.3 G3")


def main(argv: Sequence[str] | None = None, run: Runner = run_command) -> None:
    raise NotImplementedError("U0.3 G3")


if __name__ == "__main__":
    main(sys.argv[1:])
