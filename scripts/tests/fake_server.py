"""A pretend server for the deploy and flag command tests (U0.4a design §10).

It records every command and answers like git, docker and the app would,
using a real folder under pytest's `tmp_path` for `~/cucumber`. Commands are
recognised by their distinctive words, so the tests check what the commands
do, not every option they pass.
"""

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.server import Tools

SHA = "a" * 40
OTHER_SHA = "b" * 40
PREVIOUS = "2026.09.3"
NEW = "2026.10.1"
APP_PORT = "8001"
PUBLIC_HOST = "cucumber-staging.example.com"
SECRET_VALUE = "sentinel-secret-key-never-shown-1234567890-abcdefghij"  # noqa: S105 (pretend)
OWNER_PASSWORD = "sentinel-owner-password-never-shown"  # noqa: S105 (pretend)
STRAY_SHELL_PASSWORD = "stray-shell-password"  # noqa: S105 (pretend)
START = datetime(2026, 10, 13, 7, 5, tzinfo=UTC)  # 14:05 in Bangkok
NO_CHANGES = json.dumps({"pending": [], "unknown": []})
APP_LOG = [f"app log line {number}" for number in range(1, 41)]
# Seconds a command takes on the pretend clock; the build is the slow one.
COMMAND_SECONDS = {"build": 120.0}


@dataclass
class Call:
    kind: str
    command: list[str]
    env: dict[str, str] | None = None
    stdin: Path | None = None
    stdout: Path | None = None


def kind_of(command: Sequence[str]) -> str:
    """Which step a command belongs to, from its distinctive words."""
    words = set(command)
    rules = [
        ("tag-check", "ls-remote" in words),
        ("stray-check", "status" in words and "--porcelain" in words),
        ("fetch", "fetch" in words),
        ("checkout", "checkout" in words),
        ("rev-parse", "rev-parse" in words),
        ("pending", "pending_migrations" in words),
        ("guards", "cucumber_check_guards" in words),
        ("flag", "cucumber_flag" in words),
        ("backup", "pg_dump" in words),
        ("backup-check", "pg_restore" in words),
        ("prune", "prune" in words),
        ("image-list", "images" in words or {"image", "ls"} <= words),
        ("image-remove", "rmi" in words or {"image", "rm"} <= words),
        ("build", command[:1] == ["docker"] and "build" in words),
        ("migrate", "migrate" in words and "run" in words),
        ("up", "up" in words),
        ("logs", "logs" in words),
    ]
    return next((kind for kind, matches in rules if matches), "other")


@dataclass
class FakeServer:
    """Answers commands; tests change the fields to make a step go wrong."""

    tags_on_github: set[str] = field(default_factory=lambda: {PREVIOUS, NEW})
    head_sha: str = SHA
    tag_sha: str = SHA
    stray_files: str = ""
    pending_outputs: list[str] = field(default_factory=lambda: [NO_CHANGES])
    # Each guard check in turn: None passes, a text fails with it (the last repeats).
    guard_results: list[str | None] = field(default_factory=lambda: [None])
    failing: set[str] = field(default_factory=set)
    broken_versions: set[str] = field(default_factory=set)
    image_tags: list[str] = field(default_factory=list)
    flag_output: str = ""
    answers: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    said: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    clock: datetime = START
    slept: float = 0.0
    running_version: str | None = PREVIOUS

    def tools(self) -> Tools:
        return Tools(
            run=self.run,
            get=self.get,
            ask=self.ask,
            say=self.said.append,
            now=lambda: self.clock,
            sleep=self.sleep,
        )

    # ----------------------------------------------------------- the tools
    def run(
        self,
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
        *,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> str:
        kind = kind_of(command)
        recorded_env = dict(env) if env is not None else None
        self.calls.append(Call(kind, list(command), recorded_env, stdin, stdout))
        self.clock += timedelta(seconds=COMMAND_SECONDS.get(kind, 1.0))
        if kind in self.failing:
            raise RuntimeError(f"`{' '.join(command)}` failed: pretend {kind} error")
        if kind == "guards":
            return self._guards()
        return self._answer(kind, list(command), env or {}, stdout)

    def _guards(self) -> str:
        result = self.guard_results[0]
        if len(self.guard_results) > 1:
            self.guard_results.pop(0)
        if result is not None:
            raise RuntimeError(result)
        return "All 120 protections on.\n"

    def get(self, url: str, headers: Mapping[str, str]) -> tuple[int, str]:
        self.calls.append(Call("health", [url], dict(headers)))
        if self.running_version in self.broken_versions:
            return 503, "database unavailable"
        return 200, "ok"

    def ask(self, question: str) -> str:
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else "no"

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.clock += timedelta(seconds=seconds)

    # ------------------------------------------------------------- answers
    def _answer(
        self, kind: str, command: list[str], env: Mapping[str, str], out: Path | None
    ) -> str:
        if kind == "tag-check":
            tag = command[-1].removeprefix("refs/tags/")
            return f"{SHA}\trefs/tags/{tag}\n" if tag in self.tags_on_github else ""
        if kind == "stray-check":
            return self.stray_files
        if kind == "rev-parse":
            asks_head = any(part.startswith("HEAD") for part in command)
            return f"{self.head_sha if asks_head else self.tag_sha}\n"
        if kind == "pending":
            output = self.pending_outputs[0]
            if len(self.pending_outputs) > 1:
                self.pending_outputs.pop(0)
            return output + "\n"
        if kind == "backup" and out is not None:
            out.write_bytes(b"PGDMP pretend database copy")
        if kind == "backup-check":
            return "; Archive created at 2026-10-13 14:05:00\n; dbname: cucumber\n"
        if kind == "image-list":
            return "".join(f"{tag}\n" for tag in self.image_tags)
        if kind == "up":
            self.running_version = env.get("CUCUMBER_VERSION")
        if kind == "logs":
            return "".join(f"{line}\n" for line in APP_LOG[-tail(command) :])
        if kind == "flag":
            return self.flag_output
        return ""

    # ------------------------------------------------------------- reading
    def kinds(self) -> list[str]:
        return [call.kind for call in self.calls]

    def first(self, kind: str) -> Call:
        return next(call for call in self.calls if call.kind == kind)

    def all(self, kind: str) -> list[Call]:
        return [call for call in self.calls if call.kind == kind]

    def index(self, kind: str) -> int:
        return self.kinds().index(kind)

    def output(self) -> str:
        return "\n".join(self.said)


def tail(command: Sequence[str]) -> int:
    """The number after `--tail` (or `-n`), or every line."""
    for option in ("--tail", "-n"):
        if option in command:
            return int(command[command.index(option) + 1])
    return len(APP_LOG)


def make_home(
    root: Path,
    environment: str = "staging",
    *,
    current: str | None = PREVIOUS,
    secrets_mode: int = 0o600,
    named: str | None = None,
) -> Path:
    """`~/cucumber` with one environment's folder, secrets file and clone.

    The secrets file names its own environment; `named` makes it say another.
    """
    home = root / "cucumber"
    folder = home / environment
    (folder / "src" / "deploy").mkdir(parents=True)
    (folder / "backups").mkdir()
    (folder / "logs").mkdir()
    secrets = folder / "secrets.env"
    secrets.write_text(
        "# pretend secrets for tests\n"
        f"DJANGO_ENVIRONMENT={named or environment}\n"
        f"APP_PORT={APP_PORT}\n"
        f"DJANGO_ALLOWED_HOSTS={PUBLIC_HOST},localhost\n"
        f"DJANGO_SECRET_KEY={SECRET_VALUE}\n"
        f"DB_OWNER_PASSWORD={OWNER_PASSWORD}\n"
    )
    os.chmod(secrets, secrets_mode)
    if current is not None:
        (folder / "current").write_text(f"{current}\n")
    return home


def shell_environment(home: Path) -> dict[str, str]:
    """The Owner's shell: what the commands may pass on, plus strays they mustn't."""
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home.parent),
        "CUCUMBER_HOME": str(home),
        "DOCKER_HOST": "unix:///pretend/docker.sock",
        "DB_PASSWORD": STRAY_SHELL_PASSWORD,
        "DJANGO_SECRET_KEY": "stray-shell-secret-key",
    }
