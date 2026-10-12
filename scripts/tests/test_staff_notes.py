"""AC14: staff notes are gathered from exactly the release's pull requests."""

from collections.abc import Sequence

import pytest

from scripts.staff_notes import (
    NO_NOTES,
    collect_notes,
    format_notes,
    main,
    pr_numbers,
    staff_note,
)


def pr_body(note: str) -> str:
    """A pull request description shaped like .github/pull_request_template.md."""
    return (
        "## Summary\n\nTechnical summary.\n\n"
        "## Staff note\n\n"
        "<!--\nOne or two plain sentences.\n-->\n\n"
        f"{note}\n\n"
        "## Test plan\n\n- [x] ran it\n"
    )


def test_pr_numbers_come_from_squash_commit_endings() -> None:
    log = (
        "feat: split a batch (#12)\n"
        "fix: date picker (#9)\n"
        "chore: pushed straight to main\n"
        "docs: mentions (#3) in the middle\n"
    )
    assert pr_numbers(log) == [12, 9]


def test_staff_note_is_the_text_under_its_heading() -> None:
    body = pr_body("You can now split a batch for a pre-order.")
    assert staff_note(body) == "You can now split a batch for a pre-order."


def test_a_note_over_several_lines_becomes_one_line() -> None:
    body = pr_body("Losses now need a reason.\nSee SOP §6.4.")
    assert staff_note(body) == "Losses now need a reason. See SOP §6.4."


@pytest.mark.parametrize("note", ["None", "none", "None.", ""])
def test_none_or_empty_note_is_skipped(note: str) -> None:
    assert staff_note(pr_body(note)) is None


def test_a_sentence_starting_with_none_is_kept() -> None:
    body = pr_body("None of the screens changed, but saving is faster.")
    assert staff_note(body) == "None of the screens changed, but saving is faster."


def test_note_as_the_last_section_is_found() -> None:
    body = "## Summary\n\nTech.\n\n## Staff note\n\nStaff can now log in.\n"
    assert staff_note(body) == "Staff can now log in."


def test_comment_inside_the_note_is_dropped() -> None:
    body = pr_body("Losses need a reason.<!-- reviewer: check SOP --> See SOP §6.4.")
    assert staff_note(body) == "Losses need a reason. See SOP §6.4."


def test_heading_inside_a_comment_does_not_end_the_note() -> None:
    body = (
        "## Staff note\n\n<!--\n## Example\nLosses need a reason.\n-->\n\n"
        "Staff can now log in.\n\n## Test plan\n"
    )
    assert staff_note(body) == "Staff can now log in."


def test_body_without_the_section_has_no_note() -> None:
    assert staff_note("## Summary\n\nJust a fix.\n") is None


def test_windows_line_endings_are_understood() -> None:
    body = pr_body("Staff can now log in.").replace("\n", "\r\n")
    assert staff_note(body) == "Staff can now log in."


def test_collect_notes_keeps_order_and_skips_none() -> None:
    bodies = {12: pr_body("Split batches."), 9: pr_body("None"), 4: pr_body("Fixed.")}

    assert collect_notes([12, 9, 4], bodies.__getitem__) == ["Split batches.", "Fixed."]


def test_format_notes_writes_one_bullet_each() -> None:
    assert format_notes(["Split batches.", "Fixed."]) == "- Split batches.\n- Fixed."


def test_format_notes_says_so_when_there_is_nothing() -> None:
    assert format_notes([]) == NO_NOTES


GH_BODY_ONLY = ["--json", "body", "--jq", ".body"]


class FakeRunner:
    """Answers git log and gh pr view like a release with two pull requests."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> str:
        self.commands.append(list(command))
        if command[0] == "git":
            return "feat: split a batch (#12)\nchore(deps): bump django (#13)\n"
        number = int(command[3])  # gh pr view <N> …
        return pr_body("Split batches." if number == 12 else "None")


def test_main_prints_the_notes_for_the_given_range(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = FakeRunner()

    main(["2026.10.1..abc123"], run=run)

    assert capsys.readouterr().out == "- Split batches.\n"
    assert run.commands[0][-1] == "2026.10.1..abc123"
    assert [command[:4] for command in run.commands[1:]] == [
        ["gh", "pr", "view", "12"],
        ["gh", "pr", "view", "13"],
    ]
    # gh prints JSON unless asked for the bare body, which the fake returns.
    assert all(command[4:] == GH_BODY_ONLY for command in run.commands[1:])


def test_main_with_no_pull_requests_says_there_is_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(command: Sequence[str]) -> str:
        return "chore: pushed straight to main\n"

    main(["2026.10.1..abc123"], run=run)

    assert capsys.readouterr().out == NO_NOTES + "\n"


def test_main_needs_exactly_one_range() -> None:
    with pytest.raises(SystemExit):
        main([], run=FakeRunner())
