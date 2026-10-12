import pytest

from scripts.commands import run_command


def test_returns_what_the_command_printed() -> None:
    assert run_command(["echo", "hello"]) == "hello\n"


def test_stops_when_the_command_fails() -> None:
    with pytest.raises(RuntimeError, match="`false` failed: exit status 1"):
        run_command(["false"])


def test_failure_shows_the_commands_own_error() -> None:
    with pytest.raises(RuntimeError, match="not a git command"):
        run_command(["git", "no-such-command"])
