"""CI skips the slow jobs when a push changes only docs (saves Actions minutes)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.docs_only import (
    READ_BY_TESTS,
    SLOW_JOBS,
    can_skip,
    is_doc,
    main,
)

REPO = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO / ".github/workflows/ci.yml"


def compare(*files: str, status: str = "ahead") -> dict[str, Any]:
    """Shaped like GitHub's compare API reply."""
    return {"status": status, "files": [{"filename": name} for name in files]}


def checks(**conclusions: str | None) -> dict[str, Any]:
    """Shaped like GitHub's check-runs API reply, one run per slow job."""
    names = dict(zip(["tests", "image"], SLOW_JOBS, strict=True))
    return {
        "check_runs": [
            {"name": names[key], "conclusion": value}
            for key, value in conclusions.items()
        ]
    }


GREEN = checks(tests="success", image="success")


# Which files count as docs


@pytest.mark.parametrize(
    "path",
    ["docs/roadmap/tracker.md", "docs/roadmap/units/u0.10a-design.md", "README.md"],
)
def test_markdown_and_the_docs_folder_are_docs(path: str) -> None:
    assert is_doc(path)


@pytest.mark.parametrize(
    "path",
    [
        "cucumber/settings.py",
        "scripts/check.sh",
        ".github/workflows/ci.yml",
        ".github/pull_request_template.md",  # the release notes read its shape
        "pyproject.toml",
    ],
)
def test_code_and_github_files_are_not_docs(path: str) -> None:
    assert not is_doc(path)


@pytest.mark.parametrize("path", sorted(READ_BY_TESTS))
def test_a_doc_a_test_reads_is_not_a_doc(path: str) -> None:
    assert not is_doc(path)


def test_every_doc_a_test_reads_is_listed() -> None:
    """A new test that opens a doc must add it to READ_BY_TESTS."""
    named = {
        match
        for test_file in REPO.glob("*/**/test_*.py")
        if test_file != Path(__file__).resolve() and ".venv" not in test_file.parts
        for match in re.findall(r"docs/[\w./-]+\.md", test_file.read_text())
    }

    assert named <= READ_BY_TESTS


# When the slow jobs may be skipped


def test_skips_when_only_docs_changed_since_a_green_commit() -> None:
    assert can_skip(compare("docs/roadmap/tracker.md"), GREEN)


def test_skips_after_an_earlier_skip() -> None:
    """A chain of docs pushes still rests on the last commit that ran the tests."""
    assert can_skip(
        compare("docs/roadmap/tracker.md"), checks(tests="skipped", image="skipped")
    )


def test_runs_when_any_code_changed() -> None:
    assert not can_skip(compare("docs/roadmap/tracker.md", "cucumber/urls.py"), GREEN)


def test_runs_when_nothing_changed() -> None:
    assert not can_skip(compare(), GREEN)


@pytest.mark.parametrize("status", ["diverged", "behind", "identical"])
def test_runs_unless_the_new_commit_builds_on_the_old(status: str) -> None:
    """A force-push or a rebase: the old commit's results say nothing."""
    assert not can_skip(compare("README.md", status=status), GREEN)


def test_runs_when_github_lists_its_maximum_of_files() -> None:
    """GitHub stops listing at 300 files, so the rest may be code."""
    docs = [f"docs/page-{n}.md" for n in range(300)]

    assert not can_skip(compare(*docs), GREEN)


@pytest.mark.parametrize(
    "previous",
    [
        checks(tests="failure", image="success"),
        checks(tests="success", image="cancelled"),
        checks(tests=None, image="success"),  # still running
        checks(tests="success"),  # the image job never ran
        {"check_runs": []},
    ],
)
def test_runs_unless_both_slow_jobs_passed_on_the_old_commit(
    previous: dict[str, Any],
) -> None:
    """A cancelled run means that code was never tested."""
    assert not can_skip(compare("README.md"), previous)


def test_a_rerun_that_passed_counts() -> None:
    previous = checks(tests="failure", image="success")
    previous["check_runs"].append({"name": SLOW_JOBS[0], "conclusion": "success"})

    assert can_skip(compare("README.md"), previous)


# The command the workflow runs


def write_json(folder: Path, name: str, data: dict[str, Any]) -> str:
    path = folder / name
    path.write_text(json.dumps(data))
    return str(path)


@pytest.mark.parametrize(
    ("changed", "printed"),
    [("README.md", "skip=true"), ("cucumber/urls.py", "skip=false")],
)
def test_main_prints_the_answer_for_github_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], changed: str, printed: str
) -> None:
    main(
        [
            write_json(tmp_path, "compare.json", compare(changed)),
            write_json(tmp_path, "checks.json", GREEN),
        ]
    )

    assert capsys.readouterr().out.strip() == printed


# The workflow uses it the right way


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    loaded = yaml.safe_load(CI_WORKFLOW.read_text())
    assert isinstance(loaded, dict)
    return dict(loaded["jobs"])


def test_the_slow_job_names_match_the_workflow(jobs: dict[str, Any]) -> None:
    assert {job["name"] for job in jobs.values()} >= set(SLOW_JOBS)


def test_each_slow_job_waits_for_the_answer(jobs: dict[str, Any]) -> None:
    slow = [job for job in jobs.values() if job["name"] in SLOW_JOBS]

    assert len(slow) == len(SLOW_JOBS)
    for job in slow:
        assert job["needs"] == "changes"
        # !cancelled(): if the docs check itself breaks, the tests still run.
        assert job["if"] == "!cancelled() && needs.changes.outputs.skip != 'true'"


def test_the_docs_check_may_only_read(jobs: dict[str, Any]) -> None:
    assert jobs["changes"]["permissions"] == {"contents": "read", "checks": "read"}


def test_no_expression_is_pasted_into_a_shell_line(jobs: dict[str, Any]) -> None:
    for step in jobs["changes"]["steps"]:
        assert "${{" not in step.get("run", ""), step["run"]
