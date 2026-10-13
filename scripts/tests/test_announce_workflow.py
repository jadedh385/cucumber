"""AC14: the announcement workflow runs on publish only, safely (design §8)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github/workflows/announce-release.yml"
)


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    assert WORKFLOW.is_file(), f"{WORKFLOW.name} is missing"
    loaded = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(loaded, dict)
    return loaded


def steps(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_it_runs_only_when_a_release_is_published(workflow: dict[Any, Any]) -> None:
    triggers = workflow.get("on", workflow.get(True))  # YAML reads `on` as True

    assert triggers == {"release": {"types": ["published"]}}


def test_it_may_only_read_the_repo(workflow: dict[Any, Any]) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert job.get("permissions", {"contents": "read"}) == {"contents": "read"}


def test_no_expression_is_pasted_into_a_shell_line(workflow: dict[Any, Any]) -> None:
    """Release text is read from GITHUB_EVENT_PATH, so it can't run commands."""
    for step in steps(workflow):
        assert "${{" not in step.get("run", ""), step["run"]


def test_the_webhook_comes_from_the_secret_as_a_variable(
    workflow: dict[Any, Any],
) -> None:
    announcing = [step for step in steps(workflow) if "announce_release" in str(step)]

    assert len(announcing) == 1
    step = announcing[0]
    assert "scripts.announce_release" in step["run"]
    webhook = step["env"]["DISCORD_RELEASE_WEBHOOK"]
    assert webhook == "${{ secrets.DISCORD_RELEASE_WEBHOOK }}"


def test_checkout_keeps_no_credentials(workflow: dict[Any, Any]) -> None:
    checkouts = [
        step for step in steps(workflow) if "actions/checkout" in step.get("uses", "")
    ]

    assert checkouts
    assert all(step["with"]["persist-credentials"] is False for step in checkouts)
