"""AC14: the next YYYY.MM.N version, in Bangkok time."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from scripts.next_version import existing_versions, main, next_version

OCT_11_NOON_BANGKOK = datetime(2026, 10, 11, 5, 0, tzinfo=UTC)


def test_first_release_of_all_is_dot_1() -> None:
    assert next_version([], OCT_11_NOON_BANGKOK) == "2026.10.1"


def test_next_release_in_the_same_month_counts_up() -> None:
    taken = ["2026.10.1", "2026.10.2"]
    assert next_version(taken, OCT_11_NOON_BANGKOK) == "2026.10.3"


def test_a_new_month_starts_again_at_1() -> None:
    taken = ["2026.09.1", "2026.09.2"]
    assert next_version(taken, OCT_11_NOON_BANGKOK) == "2026.10.1"


def test_dot_10_comes_after_dot_9() -> None:
    taken = [f"2026.10.{n}" for n in range(1, 10)]
    assert next_version(taken, OCT_11_NOON_BANGKOK) == "2026.10.10"


def test_month_is_written_with_two_digits() -> None:
    january = datetime(2027, 1, 5, 5, 0, tzinfo=UTC)
    assert next_version([], january) == "2027.01.1"


def test_month_is_decided_in_bangkok_not_utc() -> None:
    # 17:30 UTC on 31 October is already 00:30 on 1 November in Bangkok.
    just_after_bangkok_midnight = datetime(2026, 10, 31, 17, 30, tzinfo=UTC)
    taken = ["2026.10.4"]
    assert next_version(taken, just_after_bangkok_midnight) == "2026.11.1"


def test_names_that_are_not_versions_are_ignored() -> None:
    taken = ["v1.0", "2026.10", "2026.1.7", "2026.10.5-rc", "spike", "2026.10.2"]
    assert next_version(taken, OCT_11_NOON_BANGKOK) == "2026.10.3"


def test_refuses_a_time_without_a_time_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        next_version([], datetime(2026, 10, 11, 12, 0))


class FakeRunner:
    """Answers git and gh like a repo with one tag and one draft release."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> str:
        self.commands.append(list(command))
        if command[0] == "git":
            return "2026.10.1\n"
        return "2026.10.2\n"  # gh release list: a draft not yet tagged


def test_existing_versions_include_tags_and_draft_releases() -> None:
    run = FakeRunner()

    assert sorted(existing_versions(run)) == ["2026.10.1", "2026.10.2"]
    assert [command[0] for command in run.commands] == ["git", "gh"]


def test_main_prints_the_version_after_tags_and_drafts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(run=FakeRunner(), now=OCT_11_NOON_BANGKOK)

    assert capsys.readouterr().out == "2026.10.3\n"
