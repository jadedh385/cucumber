"""Deploy one version to staging or production (U0.4a design §6, AC10-AC12).

    uv run --no-dev python -m scripts.deploy staging 2026.10.1
    uv run --no-dev python -m scripts.deploy staging main
    uv run --no-dev python -m scripts.deploy production 2026.10.1

Checks, gets the version, builds it, checks the database fits, saves a copy
of the database, migrates, restarts the app and checks it answers. Prints
each step in plain words and saves them to the environment's logs folder.
If the new version doesn't answer, puts the previous one back when that is
safe (design §6.3).
"""

import argparse
import fcntl
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from scripts.next_version import BANGKOK, VERSION_PATTERN
from scripts.server import (
    Place,
    ServerError,
    Tools,
    check_secrets_private,
    compose_command,
    compose_environment,
    current_version,
    place_for,
    read_secrets,
    real_tools,
)

HEALTH_WAIT_SECONDS = 60
HEALTH_RETRY_SECONDS = 2
BACKUPS_KEPT = 5
IMAGES_KEPT = 3
LOG_LINES_ON_FAILURE = 30
BUILD_CACHE_KEPT = "until=168h"  # a week
STAGING_BRANCH = "main"
DB_NAME = "cucumber"  # as deploy/compose.server.yaml names it
# The clone's own virtual environment is never part of the image.
NOT_A_STRAY = {".venv/"}


@dataclass(frozen=True)
class Pending:
    """What `manage.py pending_migrations` reported for one version."""

    to_run: tuple[str, ...]  # migrations this version has and the database lacks
    unknown: tuple[str, ...]  # applied migrations this version doesn't have


# ------------------------------------------------------------ small rules
def is_version_tag(name: str) -> bool:
    """True for a release tag, `YYYY.MM.N` with a month from 01 to 12."""
    return VERSION_PATTERN.fullmatch(name) is not None


def check_version(environment: str, version: str, *, from_source: bool) -> None:
    """Stop unless this environment may run this version (AC11).

    Production takes release tags only; staging also takes `main`, and only
    staging may build from a local checkout (`--source`, CI rehearsal).
    """
    if from_source and environment != "staging":
        raise ServerError("Only staging may build from a local checkout (--source).")
    if is_version_tag(version):
        return
    if environment == "production":
        raise ServerError(
            f"Production runs release tags only, like 2026.10.1, not {version!r}."
        )
    if version != STAGING_BRANCH:
        raise ServerError(
            f"Staging runs a release tag, like 2026.10.1, or main, not {version!r}."
        )


def parse_pending(output: str) -> Pending:
    """Read the JSON that `manage.py pending_migrations` prints."""
    lines = output.strip().splitlines()
    try:
        report = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        report = None
    if not isinstance(report, dict) or not all(
        isinstance(report.get(key), list) for key in ("pending", "unknown")
    ):
        raise ServerError(f"Couldn't read what pending_migrations printed: {output!r}")
    return Pending(tuple(report["pending"]), tuple(report["unknown"]))


def backup_name(now: datetime, version: str) -> str:
    """E.g. `2026-10-13-1405-before-2026.10.1.dump`, in Bangkok time."""
    if now.utcoffset() is None:
        raise ValueError("`now` must carry a time zone, e.g. datetime.now(UTC)")
    return f"{now.astimezone(BANGKOK):%Y-%m-%d-%H%M}-before-{version}.dump"


def format_duration(seconds: float) -> str:
    """E.g. `2 min 41 s`, or `45 s` under a minute."""
    whole = int(seconds)
    if whole < 60:
        return f"{whole} s"
    return f"{whole // 60} min {whole % 60} s"


def images_to_remove(
    tags_newest_first: Sequence[str], keep_also: Sequence[str] = ()
) -> list[str]:
    """Tags beyond the newest IMAGES_KEPT, never one listed in `keep_also`."""
    return [tag for tag in tags_newest_first[IMAGES_KEPT:] if tag not in keep_also]


def changes(count: int) -> str:
    if count == 0:
        return "no changes"
    return "1 change" if count == 1 else f"{count} changes"


def git_ref(version: str) -> str:
    """What to check out: the tag itself, or GitHub's main."""
    return f"origin/{version}" if version == STAGING_BRANCH else version


def restore_line(backup: Path) -> str:
    return f"Restore the copy saved in step 4: backups/{backup.name}"


@contextmanager
def deploy_lock(path: Path) -> Iterator[None]:
    """One deploy at a time on this Mac; a crash leaves no stale lock."""
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ServerError(
                "Another deploy is running. Wait for it to finish, then try again."
            ) from None
        yield


# ------------------------------------------------------------ one deploy
@dataclass(frozen=True)
class Deploy:
    """One deploy run: where, what, and the tools to do it with."""

    place: Place
    version: str
    previous: str | None
    src: Path  # what is built: the environment's clone, or --source
    from_source: bool
    tools: Tools
    shell: Mapping[str, str]
    log: Path
    started: datetime

    def say(self, line: str) -> None:
        """Print a line and add it to this deploy's log file (Q3)."""
        self.tools.say(line)
        self.record(line)

    def record(self, line: str) -> None:
        if not self.place.folder.is_dir():
            return  # not set up yet; nothing to log into
        self.log.parent.mkdir(exist_ok=True)
        with self.log.open("a") as log:
            log.write(line + "\n")

    def stop(self, reason: object) -> None:
        self.say(f"Stopped: {str(reason).rstrip('.')}. {self.still_runs()}")

    def still_runs(self) -> str:
        environment = self.place.environment
        if self.previous is None:
            return f"Nothing runs on {environment} yet."
        return f"{environment.capitalize()} still runs {self.previous}."

    def compose(
        self,
        *args: str,
        version: str | None = None,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> str:
        """`docker compose` for this environment, with a minimal environment."""
        command = compose_command(self.place, *args, src=self.src)
        env = compose_environment(
            self.shell,
            CUCUMBER_VERSION=version or self.version,
            IMAGE_NAME=self.place.image,
        )
        return self.tools.run(command, env, stdin=stdin, stdout=stdout)

    def docker(self, *args: str) -> str:
        return self.tools.run(["docker", *args], compose_environment(self.shell))

    def git(self, *args: str) -> str:
        return self.tools.run(["git", "-C", str(self.place.src), *args])

    def pending(self) -> Pending:
        output = self.compose(
            "run", "--rm", "migrate", "python", "manage.py", "pending_migrations"
        )
        return parse_pending(output)


# ------------------------------------------------- steps 0-4: nothing changed
def check_before_start(run: Deploy) -> dict[str, str]:
    """Step 0, after the lock: the secrets it needs, the tag, a clean clone."""
    secrets = read_secrets(run.place)
    for name in ("APP_PORT", "DJANGO_ALLOWED_HOSTS"):
        if not secrets.get(name):
            raise ServerError(f"{run.place.secrets} has no {name}.")
    if run.from_source:
        return secrets
    if is_version_tag(run.version):
        found = run.git("ls-remote", "--tags", "origin", f"refs/tags/{run.version}")
        if not found.strip():
            raise ServerError(f"No tag {run.version} on GitHub.")
    status = run.git("status", "--porcelain", "--ignored").splitlines()
    strays = [line[3:] for line in status if line[3:] not in NOT_A_STRAY]
    if strays:
        raise ServerError(
            f"{run.src} has files that would end up in the app: "
            f"{', '.join(strays)}. Remove them first."
        )
    return secrets


def get_version(run: Deploy) -> None:
    """Step 1: check out exactly the version's commit in the clone."""
    run.say(f"Getting {run.version} from GitHub")
    ref = git_ref(run.version)
    run.git("fetch", "--tags", "--force", "origin")
    run.git("checkout", "--detach", ref)
    head = run.git("rev-parse", "HEAD^{commit}").strip()
    wanted = run.git("rev-parse", f"{ref}^{{commit}}").strip()
    if head != wanted:
        raise ServerError(f"The clone isn't at {run.version}'s commit after checkout.")


def build(run: Deploy) -> None:
    """Step 2: build the image, named for the environment and version."""
    run.say("Building the app (takes 1–3 minutes)")
    run.docker("build", "-t", f"{run.place.image}:{run.version}", str(run.src))


def check_database_fits(run: Deploy) -> Pending:
    """Step 3: stop if the database has changes this version doesn't know."""
    run.say("Checking the database fits this version")
    pending = run.pending()
    if not pending.unknown:
        return pending
    count = len(pending.unknown)
    question = (
        f"The database has {changes(count).removeprefix('no ')} this version "
        f"doesn't know ({', '.join(pending.unknown)}). It may not work. Restore "
        "an older copy instead, or type yes to go on: "
    )
    answer = run.tools.ask(question)
    run.record(question + answer)
    if answer.strip().lower() != "yes":
        raise ServerError("You chose not to go on")
    return pending


def save_copy(run: Deploy) -> Path:
    """Step 4: a private copy of the database, checked readable; keep 5."""
    run.say("Saving a copy of the database")
    run.place.backups.mkdir(exist_ok=True)
    copy = run.place.backups / backup_name(run.started, run.version)
    try:
        copy.touch(mode=0o600, exist_ok=False)  # never overwrite an earlier copy
    except FileExistsError:
        raise ServerError(
            f"A copy named {copy.name} already exists. Wait a minute and try again"
        ) from None
    copy.chmod(0o600)
    try:
        run.compose(
            "exec", "-T", "db", "pg_dump", "-U", "postgres", "-Fc", DB_NAME, stdout=copy
        )
        listing = run.compose("exec", "-T", "db", "pg_restore", "--list", stdin=copy)
    except RuntimeError:
        copy.unlink(missing_ok=True)
        raise
    if not listing.strip():
        raise ServerError(f"The database copy {copy.name} can't be read")
    for old in sorted(run.place.backups.glob("*.dump"))[:-BACKUPS_KEPT]:
        old.unlink()
    return copy


# ------------------------------------------------ steps 5-7: the change itself
def migrate(run: Deploy, pending: Pending, backup: Path) -> bool:
    """Step 5; on failure, says what changed and whether to restore."""
    run.say(f"Updating the database ({changes(len(pending.to_run))})")
    try:
        run.compose("run", "--rm", "migrate")
        return True
    except RuntimeError as error:
        run.say(f"The database update failed: {error}")
    try:
        still = run.pending().to_run
    except (RuntimeError, ServerError):
        run.say("Couldn't tell which changes were made before it failed.")
        run.say(restore_line(backup))
        return False
    applied = [name for name in pending.to_run if name not in still]
    if not applied:
        running = f", so {run.previous} is still running" if run.previous else ""
        run.say(f"Nothing was changed{running}.")
        return False
    run.say(
        f"These changes were made before it failed: {', '.join(applied)}. "
        "The old version may not work with them."
    )
    run.say(restore_line(backup))
    return False


def restart(run: Deploy, version: str) -> None:
    """Step 6: start the app (and the tunnel, if on) at `version`."""
    run.say("Restarting the app")
    try:
        run.compose("up", "-d", version=version)
    except RuntimeError as error:
        run.say(f"Starting it failed: {error}")


def answers(run: Deploy, secrets: Mapping[str, str]) -> bool:
    """Step 7: /health/ says "ok" within HEALTH_WAIT_SECONDS.

    Asked like Cloudflare asks: the public host name and the HTTPS header,
    or the app would refuse the host and redirect to HTTPS (design §6.2).
    """
    run.say("Checking the app answers")
    url = f"http://127.0.0.1:{secrets['APP_PORT']}/health/"
    host = secrets["DJANGO_ALLOWED_HOSTS"].split(",")[0].strip()
    headers = {"Host": host, "X-Forwarded-Proto": "https"}
    deadline = run.tools.now() + timedelta(seconds=HEALTH_WAIT_SECONDS)
    while True:
        status, body = run.tools.get(url, headers)
        if status == 200 and body.strip() == "ok":
            return True
        if run.tools.now() >= deadline:
            return False
        run.tools.sleep(HEALTH_RETRY_SECONDS)


def show_app_log(run: Deploy) -> None:
    try:
        lines = run.compose(
            "logs", "--no-color", "--tail", str(LOG_LINES_ON_FAILURE), "app"
        )
    except RuntimeError as error:
        run.say(f"Couldn't read the app's log: {error}")
        return
    run.say(f"The app's last {LOG_LINES_ON_FAILURE} log lines:")
    for line in lines.splitlines():
        run.say(f"  {line}")


def recover(
    run: Deploy, pending: Pending, backup: Path, secrets: Mapping[str, str]
) -> None:
    """Step 7 failed: put the previous version back only when that is safe."""
    show_app_log(run)
    if pending.to_run:
        # It may not understand the changed database, so the old one stays off.
        run.place.current.write_text(f"{run.version}\n")
        run.say("The new version changed the database and isn't answering.")
        run.say(restore_line(backup))
    elif run.previous is None:
        run.place.current.write_text(f"{run.version}\n")
        run.say(
            "The new version didn't answer, and there is no previous version "
            "to go back to."
        )
    else:
        put_back(run, run.previous, secrets)


def put_back(run: Deploy, previous: str, secrets: Mapping[str, str]) -> None:
    """Run the previous version again, from its own compose file."""
    if not run.from_source:
        try:
            run.git("checkout", "--detach", git_ref(previous))
        except RuntimeError as error:
            run.say(f"Couldn't check out {previous} again: {error}")
    restart(run, previous)
    if answers(run, secrets):
        run.say(
            f"The new version didn't answer, so {previous} is back. Nothing was lost."
        )
    else:
        run.say(
            f"The new version didn't answer, and {previous} isn't answering "
            "either. Get help before trying again."
        )


def tidy_up(run: Deploy) -> None:
    """Keep the newest images and the previous one; clear old build cache."""
    try:
        listed = run.docker("image", "ls", run.place.image, "--format", "{{.Tag}}")
        tags = [tag for tag in listed.split() if tag != "<none>"]
        keep = [version for version in (run.version, run.previous) if version]
        for tag in images_to_remove(tags, keep_also=keep):
            run.docker("image", "rm", f"{run.place.image}:{tag}")
        run.docker("builder", "prune", "--filter", BUILD_CACHE_KEPT, "-f")
    except RuntimeError as error:
        run.say(
            f"Note: clearing old images failed ({error}). The deploy itself worked."
        )


def finish(run: Deploy) -> None:
    run.place.current.write_text(f"{run.version}\n")
    tidy_up(run)
    was = f" (was {run.previous})" if run.previous else ""
    took = format_duration((run.tools.now() - run.started).total_seconds())
    run.say(f"Done: {run.place.environment} now runs {run.version}{was}. Took {took}.")


def deploy(run: Deploy) -> int:
    """Steps 0 (after the lock) to 7; 0 when the new version answers."""
    try:
        secrets = check_before_start(run)
        if not run.from_source:
            get_version(run)
        build(run)
        pending = check_database_fits(run)
        backup = save_copy(run)
    except (ServerError, RuntimeError) as error:
        run.stop(error)
        return 1
    if not migrate(run, pending, backup):
        return 1
    restart(run, run.version)
    if answers(run, secrets):
        finish(run)
        return 0
    recover(run, pending, backup, secrets)
    return 1


# ------------------------------------------------------------- the command
def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.deploy",
        description="Deploy one version of Cucumber to staging or production.",
    )
    parser.add_argument("environment", help="staging or production")
    parser.add_argument(
        "version", help="a release tag like 2026.10.1, or main (staging only)"
    )
    # CI rehearsal only (design §9): build this checkout, skip GitHub.
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def new_run(
    place: Place, args: argparse.Namespace, tools: Tools, shell: Mapping[str, str]
) -> Deploy:
    started = tools.now()
    stamp = f"{started.astimezone(BANGKOK):%Y-%m-%d-%H%M%S}"
    return Deploy(
        place=place,
        version=args.version,
        previous=current_version(place),
        src=args.source.absolute() if args.source else place.src,
        from_source=args.source is not None,
        tools=tools,
        shell=shell,
        log=place.logs / f"{stamp}-{args.version}.log",
        started=started,
    )


def main(
    argv: Sequence[str] | None = None,
    tools: Tools | None = None,
    os_environ: Mapping[str, str] | None = None,
) -> int:
    """Run one deploy; 0 when the new version answers, 1 otherwise."""
    args = parse_arguments(argv)
    tools = tools or real_tools()
    shell = os.environ if os_environ is None else os_environ
    try:
        place = place_for(args.environment, shell)
    except ServerError as error:
        tools.say(f"Stopped: {error}")
        return 1
    run = new_run(place, args, tools, shell)
    run.say("Checking before we start")
    try:
        check_version(place.environment, run.version, from_source=run.from_source)
        check_secrets_private(place)
        with deploy_lock(place.lock):
            return deploy(run)
    except ServerError as error:
        run.stop(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
