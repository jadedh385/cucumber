"""What the deploy and flag commands share on the server (U0.4a design §6, §7).

Both find the environment's folder, check its secrets file, and run
`docker compose` for one environment with a minimal set of variables, so a
stray `export` in the shell can't override the secrets file (design §3.1).
They use only Python's standard library: the server runs them with
`uv run --no-dev`.
"""

import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from scripts.web import request

ENVIRONMENTS = ("staging", "production")
COMPOSE_FILE = Path("deploy") / "compose.server.yaml"
# What compose may see from the shell (design §3.1); everything else comes
# from the secrets file.
SHELL_NAMES = ("PATH", "HOME")
SHELL_PREFIX = "DOCKER_"
PRIVATE = 0o077  # group and other permission bits
# A hung build, migration or copy must not hold the deploy lock for ever;
# the slowest step (a build) takes 1-3 minutes.
COMMAND_TIMEOUT_SECONDS = 30 * 60


class ServerError(Exception):
    """A plain reason the command stopped, shown to the Owner as is."""


class RunCommand(Protocol):
    """Runs one command; returns what it printed, raises RuntimeError on failure.

    `stdin` and `stdout` name files to read from and write to (binary), for
    database copies. The caller creates the `stdout` file first, with its
    permissions (a database copy is 0600); the runner only writes into it.
    """

    def __call__(
        self,
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
        *,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> str: ...


GetPage = Callable[[str, Mapping[str, str]], tuple[int, str]]


@dataclass(frozen=True)
class Tools:
    """Everything the commands do to the outside world, so tests can fake it."""

    run: RunCommand
    get: GetPage  # url, headers -> (status, body)
    ask: Callable[[str], str]
    say: Callable[[str], None]
    now: Callable[[], datetime]
    sleep: Callable[[float], None]


@dataclass(frozen=True)
class Place:
    """One environment's folder on the server (design §6.1)."""

    environment: str
    home: Path

    @property
    def folder(self) -> Path:
        return self.home / self.environment

    @property
    def src(self) -> Path:
        return self.folder / "src"

    @property
    def secrets(self) -> Path:
        return self.folder / "secrets.env"

    @property
    def current(self) -> Path:
        return self.folder / "current"

    @property
    def backups(self) -> Path:
        return self.folder / "backups"

    @property
    def logs(self) -> Path:
        return self.folder / "logs"

    @property
    def lock(self) -> Path:
        return self.home / "deploy.lock"

    @property
    def image(self) -> str:
        """Images are named per environment (design §3, H3)."""
        return f"cucumber-{self.environment}"


def run_command(
    command: Sequence[str],
    env: Mapping[str, str] | None = None,
    *,
    stdin: Path | None = None,
    stdout: Path | None = None,
) -> str:
    """The real RunCommand: no shell, exactly `env` when given.

    A failure raises RuntimeError with the command's own error text, so a
    refusal from the app (e.g. "No flag called ...") reaches the Owner. So
    does a command still running after COMMAND_TIMEOUT_SECONDS; it is stopped.
    """
    with ExitStack() as files:
        source = files.enter_context(stdin.open("rb")) if stdin else None
        target = files.enter_context(stdout.open("wb")) if stdout else subprocess.PIPE
        try:
            finished = subprocess.run(
                list(command),
                env=dict(env) if env is not None else None,
                stdin=source,
                stdout=target,
                stderr=subprocess.PIPE,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"`{' '.join(command)}` took longer than "
                f"{COMMAND_TIMEOUT_SECONDS:g} seconds and was stopped."
            ) from None
    if finished.returncode != 0:
        error = finished.stderr.decode(errors="replace").strip()
        details = error or f"exit status {finished.returncode}"
        raise RuntimeError(f"`{' '.join(command)}` failed: {details}")
    return "" if stdout else finished.stdout.decode(errors="replace")


def ask(question: str) -> str:
    """The typed answer; no keyboard (e.g. run from a script) counts as none."""
    try:
        return input(question)
    except EOFError:
        return ""


def say(line: str) -> None:
    print(line, flush=True)


def get_page(url: str, headers: Mapping[str, str]) -> tuple[int, str]:
    """A GET that answers (0, reason) when nothing answers at all yet."""
    try:
        return request(url, headers)
    except OSError as error:
        return 0, type(error).__name__


def real_tools() -> Tools:
    """Tools that act on this machine: commands, HTTP, the keyboard, the clock."""
    return Tools(
        run=run_command,
        get=get_page,
        ask=ask,
        say=say,
        now=lambda: datetime.now(UTC),
        sleep=time.sleep,
    )


def place_for(environment: str, os_environ: Mapping[str, str]) -> Place:
    """The environment's place under `CUCUMBER_HOME` (default `~/cucumber`)."""
    if environment not in ENVIRONMENTS:
        raise ServerError(
            f"The environment must be staging or production, not {environment!r}."
        )
    home = os_environ.get("CUCUMBER_HOME") or str(
        Path(os_environ.get("HOME") or Path.home()) / "cucumber"
    )
    return Place(environment, Path(home).expanduser().absolute())


def check_secrets_private(place: Place) -> None:
    """Stop unless the secrets file exists and only its owner can read it."""
    if not place.secrets.is_file():
        raise ServerError(
            f"There is no {place.secrets}. Make it from deploy/secrets.env.example."
        )
    if place.secrets.stat().st_mode & PRIVATE:
        raise ServerError(
            f"Others can read {place.secrets}. Run: chmod 600 {place.secrets}"
        )


def read_secrets(place: Place) -> dict[str, str]:
    """`NAME=value` pairs from the secrets file. Values are never printed."""
    values = {}
    for line in place.secrets.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip("'\"")
    return values


def current_version(place: Place) -> str | None:
    """The version now running, from the `current` file; None before the first."""
    if not place.current.is_file():
        return None
    return place.current.read_text().strip() or None


def compose_environment(os_environ: Mapping[str, str], **extra: str) -> dict[str, str]:
    """`PATH`, `HOME` and `DOCKER_*` from the shell, plus `extra`; nothing else."""
    passed = {
        name: value
        for name, value in os_environ.items()
        if name in SHELL_NAMES or name.startswith(SHELL_PREFIX)
    }
    return {**passed, **extra}


def compose_command(place: Place, *args: str, src: Path | None = None) -> list[str]:
    """`docker compose` for this environment's project, secrets and compose file.

    The compose file comes from `src` (default: the environment's own clone),
    so it always matches the version being run.
    """
    compose_file = (src or place.src) / COMPOSE_FILE
    return [
        "docker", "compose",
        "-p", place.image,
        "--env-file", str(place.secrets),
        "-f", str(compose_file),
        *args,
    ]  # fmt: skip
