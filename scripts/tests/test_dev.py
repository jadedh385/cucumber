"""U0.10a §3.5: one command runs the CSS watcher and the dev server together.

The processes are faked: each answers `poll` from a list of codes (None
while running) and remembers whether it was stopped.
"""

import subprocess
import sys
from collections.abc import Sequence

import pytest

from scripts import dev


class FakeProcess:
    def __init__(self, polls: Sequence[int | None], hangs: bool = False) -> None:
        self.polls = list(polls)
        self.hangs = hangs  # ignores terminate, so it must be killed
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        if self.terminated and not self.hangs or self.killed:
            return -15
        return self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        if self.hangs and not self.killed:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return -15


class FakeStart:
    """Hands out the given processes in order and remembers each command."""

    def __init__(self, *processes: FakeProcess) -> None:
        self.processes = list(processes)
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> FakeProcess:
        self.commands.append(list(command))
        return self.processes[len(self.commands) - 1]


def no_sleep(seconds: float) -> None:
    pass


def test_it_starts_the_css_watcher_and_the_dev_server() -> None:
    assert dev.COMMANDS == (
        [sys.executable, "-m", "scripts.css", "watch"],
        [sys.executable, "manage.py", "runserver"],
    )


def test_when_one_stops_the_other_is_stopped_and_its_code_returned() -> None:
    watcher = FakeProcess([None, None, 1])
    server = FakeProcess([None])
    start = FakeStart(watcher, server)

    code = dev.run_together(dev.COMMANDS, start=start, sleep=no_sleep)

    assert code == 1
    assert start.commands == [list(command) for command in dev.COMMANDS]
    assert server.terminated
    assert not watcher.terminated, "it had stopped already"


def test_ctrl_c_stops_both() -> None:
    watcher = FakeProcess([None])
    server = FakeProcess([None])

    def interrupted(seconds: float) -> None:
        raise KeyboardInterrupt

    code = dev.run_together(
        dev.COMMANDS, start=FakeStart(watcher, server), sleep=interrupted
    )

    assert code == 0
    assert watcher.terminated
    assert server.terminated


def test_one_that_will_not_stop_is_killed() -> None:
    watcher = FakeProcess([0])
    server = FakeProcess([None], hangs=True)

    dev.run_together(dev.COMMANDS, start=FakeStart(watcher, server), sleep=no_sleep)

    assert server.killed


def test_if_the_second_cannot_start_the_first_is_stopped() -> None:
    watcher = FakeProcess([None])

    def start(command: Sequence[str]) -> FakeProcess:
        if "runserver" in command:
            raise OSError("no such file")
        return watcher

    with pytest.raises(OSError):
        dev.run_together(dev.COMMANDS, start=start, sleep=no_sleep)

    assert watcher.terminated
