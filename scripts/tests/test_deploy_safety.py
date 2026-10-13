"""Deploy safety found in the U0.4a G4 review (design §16).

Staging's `main` moves, so each build is named for its commit; a failed start
is never reported as done; an unexpected error still says how to restore;
copies and logs stay private; and the clone goes back to what still runs.
"""

import dataclasses
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts.deploy import BACKUPS_KEPT, HEALTH_WAIT_SECONDS, main
from scripts.server import Place, Tools
from scripts.tests.fake_server import (
    NEW,
    OTHER_SHA,
    PREVIOUS,
    SHA,
    FakeServer,
    make_home,
    shell_environment,
)

MAIN_NOW = f"main-{SHA[:12]}"
MAIN_BEFORE = f"main-{OTHER_SHA[:12]}"
NONE_TO_RUN = json.dumps({"pending": [], "unknown": []})
BACKUP_NAME = f"2026-10-13-1405-before-{NEW}.dump"


def deploy(
    tmp_path: Path,
    server: FakeServer,
    version: str = NEW,
    *,
    current: str | None = PREVIOUS,
    tools: Tools | None = None,
    named: str | None = None,
) -> tuple[int, Place]:
    home = make_home(tmp_path, current=current, named=named)
    code = main(["staging", version], tools or server.tools(), shell_environment(home))
    return code, Place("staging", home)


def up_versions(server: FakeServer) -> list[str]:
    return [call.env["CUCUMBER_VERSION"] for call in server.all("up") if call.env]


# -------------------------------------------- staging's main, named per commit
def test_staging_main_is_built_and_recorded_under_its_commit(tmp_path: Path) -> None:
    server = FakeServer()

    code, place = deploy(tmp_path, server, "main")

    assert code == 0, server.output()
    assert f"cucumber-staging:{MAIN_NOW}" in server.first("build").command
    assert up_versions(server) == [MAIN_NOW]
    assert place.current.read_text().strip() == MAIN_NOW
    assert server.said[-1].startswith(f"Done: staging now runs {MAIN_NOW}")


def test_a_broken_main_puts_back_the_earlier_main_build(tmp_path: Path) -> None:
    server = FakeServer(broken_versions={MAIN_NOW}, running_version=MAIN_BEFORE)

    code, place = deploy(tmp_path, server, "main", current=MAIN_BEFORE)

    assert code == 1
    assert up_versions(server) == [MAIN_NOW, MAIN_BEFORE]
    assert OTHER_SHA[:12] in server.all("checkout")[-1].command
    assert f"so {MAIN_BEFORE} is back. Nothing was lost." in server.output()
    assert place.current.read_text().strip() == MAIN_BEFORE


# ------------------------------------------------ a start that itself failed
def test_a_failed_start_is_never_reported_as_done(tmp_path: Path) -> None:
    # `up` fails before replacing the container, so the old one still answers.
    server = FakeServer(failing={"up"})

    code, place = deploy(tmp_path, server)

    assert code == 1
    assert not any(line.startswith("Done:") for line in server.said)
    assert place.current.read_text().strip() == PREVIOUS
    assert server.slept < HEALTH_WAIT_SECONDS, "no need to wait for the new one"
    assert "prune" not in server.kinds()


# --------------------------------------------- unexpected errors after step 4
def test_an_unexpected_error_after_the_copy_still_says_how_to_restore(
    tmp_path: Path,
) -> None:
    server = FakeServer()

    def broken_get(url: str, headers: object) -> tuple[int, str]:
        raise ValueError("pretend surprise")

    tools = dataclasses.replace(server.tools(), get=broken_get)

    code, _ = deploy(tmp_path, server, tools=tools)

    assert code == 1
    assert server.said[-2].startswith("Stopped: pretend surprise")
    assert server.said[-1] == f"Restore the copy saved in step 4: backups/{BACKUP_NAME}"


# ------------------------------------------------------------ database copies
def interrupt_on(kind: str, server: FakeServer) -> Tools:
    real = server.run

    def run(
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
        *,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> str:
        output = real(command, env, stdin=stdin, stdout=stdout)
        if server.calls[-1].kind == kind:
            raise KeyboardInterrupt
        return output

    return dataclasses.replace(server.tools(), run=run)


def test_an_interrupted_copy_is_removed(tmp_path: Path) -> None:
    server = FakeServer()

    with pytest.raises(KeyboardInterrupt):
        deploy(tmp_path, server, tools=interrupt_on("backup", server))

    assert not list((tmp_path / "cucumber" / "staging" / "backups").glob("*.dump"))


def test_an_unreadable_copy_is_removed(tmp_path: Path) -> None:
    server = FakeServer()
    real = server.run

    def run(
        command: Sequence[str],
        env: Mapping[str, str] | None = None,
        *,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> str:
        output = real(command, env, stdin=stdin, stdout=stdout)
        return "" if server.calls[-1].kind == "backup-check" else output

    code, place = deploy(
        tmp_path, server, tools=dataclasses.replace(server.tools(), run=run)
    )

    assert code == 1
    assert not list(place.backups.glob("*.dump"))


def test_failed_deploys_never_push_out_older_copies(tmp_path: Path) -> None:
    server = FakeServer(failing={"migrate"}, pending_outputs=[NONE_TO_RUN])
    home = make_home(tmp_path)
    place = Place("staging", home)
    older = [f"2026-10-0{day}-0900-before-2026.09.{day}.dump" for day in range(1, 6)]
    for name in older:
        (place.backups / name).write_bytes(b"good old copy")

    code = main(["staging", NEW], server.tools(), shell_environment(home))

    assert code == 1
    kept = {path.name for path in place.backups.glob("*.dump")}
    assert set(older) <= kept
    assert len(kept) == BACKUPS_KEPT + 1


def test_copies_and_logs_are_private(tmp_path: Path) -> None:
    server = FakeServer()

    code, place = deploy(tmp_path, server)

    assert code == 0, server.output()
    for folder in (place.backups, place.logs):
        assert folder.stat().st_mode & 0o777 == 0o700, folder
    for log in place.logs.iterdir():
        assert log.stat().st_mode & 0o777 == 0o600, log


# --------------------------------------------- the clone matches what runs
@pytest.mark.parametrize("failing", ["build", "migrate"])
def test_after_a_stop_the_clone_is_back_at_the_running_version(
    tmp_path: Path, failing: str
) -> None:
    server = FakeServer(failing={failing}, pending_outputs=[NONE_TO_RUN])

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert PREVIOUS in server.all("checkout")[-1].command
    assert "up" not in server.kinds()


# ------------------------------------------------- checks before anything runs
def test_secrets_for_another_environment_are_refused(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = deploy(tmp_path, server, named="local")

    assert code == 1
    assert "DJANGO_ENVIRONMENT" in server.output()
    assert "build" not in server.kinds()


@pytest.mark.parametrize("version", ["../outside", "a/b"])
def test_a_bad_version_stops_plainly_before_any_log_is_written(
    tmp_path: Path, version: str
) -> None:
    server = FakeServer()

    code, place = deploy(tmp_path, server, version)

    assert code == 1
    assert server.said[-1].startswith("Stopped:")
    assert not list(place.logs.iterdir())
    assert not list(place.folder.glob("*.log"))
