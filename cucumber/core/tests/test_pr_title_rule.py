"""AC5: the rule the pr-title workflow applies to pull request titles.

The live check is the workflow itself; this test reads its pattern so the
accepted and rejected examples stay written down next to the code.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

WORKFLOW = Path(settings.BASE_DIR) / ".github" / "workflows" / "pr-title.yml"


def title_pattern() -> re.Pattern[str]:
    for line in WORKFLOW.read_text().splitlines():
        name, _, value = line.strip().partition(":")
        if name == "PATTERN":
            return re.compile(value.strip().strip("'"))
    raise AssertionError("pr-title.yml has no PATTERN line")


@pytest.mark.parametrize(
    "title",
    [
        "feat: split a batch for a pre-order",
        "fix: date picker no longer jumps a month",
        "perf: faster batch list",
        "refactor: move ID rules into services",
        "docs: U0.3 G2 evidence",
        "test: cover Bangkok midnight",
        "chore(deps): bump django",
        "ci: cache uv downloads",
        "feat!: drop the old import",
    ],
)
def test_accepts_type_colon_description(title: str) -> None:
    assert title_pattern().match(title)


@pytest.mark.parametrize(
    "title",
    [
        "Update stuff",
        "feature: wrong type name",
        "feat:no space after the colon",
        "feat: ",
        "Feat: capital type",
        "wip",
    ],
)
def test_rejects_anything_else(title: str) -> None:
    assert not title_pattern().match(title)
