"""What the deploy and flag commands share on the server (U0.4a design §6, §7).

Both find the environment's folder, check its secrets file, and run
`docker compose` for one environment with a minimal set of variables, so a
stray `export` in the shell can't override the secrets file (design §3.1).
They use only Python's standard library: the server runs them with
`uv run --no-dev`.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

ENVIRONMENTS = ("staging", "production")
COMPOSE_FILE = Path("deploy") / "compose.server.yaml"
NOT_BUILT = "U0.4a G3"


class ServerError(Exception):
    """A plain reason the command stopped, shown to the Owner as is."""


class RunCommand(Protocol):
    """Runs one command; returns what it printed, raises RuntimeError on failure.

    `stdin` and `stdout` name files to read from and write to (binary), for
    database copies.
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


def place_for(environment: str, os_environ: Mapping[str, str]) -> Place:
    """The environment's place under `CUCUMBER_HOME` (default `~/cucumber`)."""
    raise NotImplementedError(NOT_BUILT)


def check_secrets_private(place: Place) -> None:
    """Stop unless the secrets file exists and only its owner can read it."""
    raise NotImplementedError(NOT_BUILT)


def read_secrets(place: Place) -> dict[str, str]:
    """`NAME=value` pairs from the secrets file. Values are never printed."""
    raise NotImplementedError(NOT_BUILT)


def current_version(place: Place) -> str | None:
    """The version now running, from the `current` file; None before the first."""
    raise NotImplementedError(NOT_BUILT)


def compose_environment(os_environ: Mapping[str, str], **extra: str) -> dict[str, str]:
    """`PATH`, `HOME` and `DOCKER_*` from the shell, plus `extra`; nothing else."""
    raise NotImplementedError(NOT_BUILT)


def compose_command(place: Place, *args: str, src: Path | None = None) -> list[str]:
    """`docker compose` for this environment's project, secrets and compose file.

    The compose file comes from `src` (default: the environment's own clone),
    so it always matches the version being run.
    """
    raise NotImplementedError(NOT_BUILT)
