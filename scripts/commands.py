"""Run git and gh for the release scripts, in a way tests can replace."""

import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[[Sequence[str]], str]


def run_command(command: Sequence[str]) -> str:
    """Run `command` and return what it printed.

    Stops on any error, with the command's own error message, so the Draft
    release log says what went wrong (e.g. "gh: Not Found").
    """
    try:
        return subprocess.run(
            list(command), check=True, capture_output=True, text=True
        ).stdout
    except subprocess.CalledProcessError as error:
        details = (error.stderr or "").strip() or f"exit status {error.returncode}"
        raise RuntimeError(f"`{' '.join(command)}` failed: {details}") from error
