"""Local work in one command (U0.10a §3.5):

    uv run python -m scripts.dev

Starts the CSS watcher (`scripts.css watch`) and `manage.py runserver`
together, each printing to this terminal. Ctrl-C stops both, and so does
either one stopping. `scripts/check.sh` builds the CSS once, so the tests
never need this.
"""

import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from typing import Protocol

COMMANDS = (
    [sys.executable, "-m", "scripts.css", "watch"],
    [sys.executable, "manage.py", "runserver"],
)
POLL_SECONDS = 0.5
STOP_TIMEOUT_SECONDS = 5


class Process(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


Start = Callable[[Sequence[str]], Process]


def start_process(command: Sequence[str]) -> Process:
    return subprocess.Popen(command)


def run_together(
    commands: Sequence[Sequence[str]],
    start: Start = start_process,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run every command until one stops (its exit code) or Ctrl-C (0)."""
    processes: list[Process] = []
    try:
        for command in commands:
            processes.append(start(command))
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    return code
            sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return 0
    finally:
        stop(processes)


def stop(processes: Sequence[Process]) -> None:
    """Ask each running one to stop; kill any still there after a while."""
    running = [process for process in processes if process.poll() is None]
    for process in running:
        process.terminate()
    for process in running:
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    raise SystemExit(run_together(COMMANDS))
