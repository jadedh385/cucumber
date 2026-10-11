import subprocess

import pytest

from scripts.commands import run_command


def test_returns_what_the_command_printed() -> None:
    assert run_command(["echo", "hello"]) == "hello\n"


def test_stops_when_the_command_fails() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        run_command(["false"])
