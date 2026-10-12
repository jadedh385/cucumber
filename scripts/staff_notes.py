"""Collect the "Staff note" of every pull request in a release.

The pull requests are found from the `(#N)` endings of the squash commits in
the release's git range, so the notes always match the commits. Notes that
say "None" are skipped. Used by the Draft release workflow:
`python -m scripts.staff_notes <last-tag>..<sha>`.
"""

import argparse
import re
import sys
from collections.abc import Callable, Iterable, Sequence

from scripts.commands import Runner, run_command

NO_NOTES = "Nothing staff will notice in this release."
PR_ENDING = re.compile(r"\(#(\d+)\)\s*$")
STAFF_NOTE_HEADING = re.compile(r"##\s+staff note\s*", re.IGNORECASE)
NEXT_HEADING = re.compile(r"#{1,2}\s")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
NOTHING_TO_SAY = {"", "none", "none."}


def pr_numbers(log: str) -> list[int]:
    """Pull request numbers from commit subjects ending in `(#N)`, in order."""
    return [
        int(match[1]) for line in log.splitlines() if (match := PR_ENDING.search(line))
    ]


def _section_lines(body: str) -> list[str] | None:
    """The lines under `## Staff note`, up to the next heading; None if absent."""
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if STAFF_NOTE_HEADING.fullmatch(line.strip()):
            section = lines[index + 1 :]
            ends = [i for i, text in enumerate(section) if NEXT_HEADING.match(text)]
            return section[: ends[0]] if ends else section
    return None


def staff_note(body: str) -> str | None:
    """The text under `## Staff note`, or None if missing, empty or "None"."""
    lines = _section_lines(body)
    if lines is None:
        return None
    text = " ".join(HTML_COMMENT.sub(" ", "\n".join(lines)).split())
    return None if text.lower() in NOTHING_TO_SAY else text


def collect_notes(
    numbers: Iterable[int], fetch_body: Callable[[int], str]
) -> list[str]:
    """The staff notes of these pull requests, skipping those without one."""
    return [note for number in numbers if (note := staff_note(fetch_body(number)))]


def format_notes(notes: Sequence[str]) -> str:
    """One bullet per note, or a sentence saying there is nothing."""
    return "\n".join(f"- {note}" for note in notes) or NO_NOTES


def main(argv: Sequence[str] | None = None, run: Runner = run_command) -> None:
    """Print the notes for one git range, e.g. `2026.10.1..<sha>`.

    Runs `git log --reverse --format=%s <range>`, then for each pull request
    `gh pr view <N> --json body --jq .body`.
    """
    parser = argparse.ArgumentParser(description="Print a release's staff notes.")
    parser.add_argument("range", help="git range, e.g. 2026.10.1..<sha>")
    args = parser.parse_args(argv)

    def fetch_body(number: int) -> str:
        return run(["gh", "pr", "view", str(number), "--json", "body", "--jq", ".body"])

    log = run(["git", "log", "--reverse", "--format=%s", args.range])
    print(format_notes(collect_notes(pr_numbers(log), fetch_body)))


if __name__ == "__main__":
    main(sys.argv[1:])
