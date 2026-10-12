"""Run git and gh for the release scripts, in a way tests can replace."""

import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[[Sequence[str]], str]


def run_command(command: Sequence[str]) -> str:
    """Run `command` and return what it printed. Stops on any error."""
    return subprocess.run(
        list(command), check=True, capture_output=True, text=True
    ).stdout
