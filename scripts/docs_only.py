"""Say whether CI may skip its slow jobs because a push changed only docs.

Most pushes add a tracker row or a design note, and the tests and the image
build cost about 6 of the month's Actions minutes each time. The CI workflow's
`changes` job asks GitHub what changed since the previous commit and how CI
went there, saves both replies, and runs
`python -m scripts.docs_only compare.json checks.json`. It prints `skip=true`
or `skip=false` for GITHUB_OUTPUT.

Skipping is safe only when the previous commit's code was itself checked:
both slow jobs passed there, or were skipped there for the same reason.
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# The `name:` of each slow job in .github/workflows/ci.yml.
SLOW_JOBS = ("Lint, types, tests", "Container image")
PASSED = frozenset({"success", "skipped"})
# GitHub's compare reply lists at most this many files; beyond it, unknown.
MAX_LISTED_FILES = 300
# Docs that a test opens: changing one can turn the tests red.
READ_BY_TESTS = frozenset({"docs/roadmap/units/u0.2-design.md"})


def is_doc(path: str) -> bool:
    """True for files under docs/ and Markdown files outside .github/."""
    if path in READ_BY_TESTS or path.startswith(".github/"):
        return False
    return path.startswith("docs/") or path.endswith(".md")


def changed_files(compare: dict[str, Any]) -> list[str]:
    return [str(entry["filename"]) for entry in compare.get("files", [])]


def slow_jobs_passed(checks: dict[str, Any]) -> bool:
    """Each slow job has a run that passed (a passing re-run counts)."""
    passed = {
        run["name"]
        for run in checks.get("check_runs", [])
        if run.get("conclusion") in PASSED
    }
    return passed >= set(SLOW_JOBS)


def can_skip(compare: dict[str, Any], checks: dict[str, Any]) -> bool:
    """`compare` and `checks` are GitHub's replies about the previous commit.

    "ahead" means the new commit builds on the previous one, so the files
    listed are everything that differs between them.
    """
    files = changed_files(compare)
    return (
        compare.get("status") == "ahead"
        and 0 < len(files) < MAX_LISTED_FILES
        and all(is_doc(path) for path in files)
        and slow_jobs_passed(checks)
    )


def main(argv: Sequence[str] | None = None) -> None:
    compare_path, checks_path = argv if argv is not None else sys.argv[1:]
    compare = json.loads(Path(compare_path).read_text(encoding="utf-8"))
    checks = json.loads(Path(checks_path).read_text(encoding="utf-8"))
    print(f"skip={str(can_skip(compare, checks)).lower()}")


if __name__ == "__main__":
    main()
