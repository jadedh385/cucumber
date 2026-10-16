"""AC12: when a deploy goes wrong it says so plainly and is safe (design §6.3).

One test per row of the §6.3 table, plus the first-ever deploy.
"""

import json
from pathlib import Path

import pytest

from scripts.deploy import HEALTH_WAIT_SECONDS, LOG_LINES_ON_FAILURE, main
from scripts.server import Place
from scripts.tests.fake_server import (
    APP_LOG,
    NEW,
    PREVIOUS,
    FakeServer,
    make_home,
    shell_environment,
)

TWO_TO_RUN = json.dumps({"pending": ["core.0005_a", "core.0006_b"], "unknown": []})
ONE_TO_RUN = json.dumps({"pending": ["core.0006_b"], "unknown": []})
NONE_TO_RUN = json.dumps({"pending": [], "unknown": []})
DATABASE_AHEAD = json.dumps({"pending": [], "unknown": ["core.0099_future"]})
BACKUP_NAME = f"2026-10-13-1405-before-{NEW}.dump"


def deploy(
    tmp_path: Path, server: FakeServer, *, current: str | None = PREVIOUS
) -> tuple[int, Place]:
    home = make_home(tmp_path, current=current)
    code = main(["staging", NEW], server.tools(), shell_environment(home))
    return code, Place("staging", home)


def last_index(kinds: list[str], kind: str) -> int:
    return len(kinds) - 1 - kinds[::-1].index(kind)


# --------------------------------------------------- steps 0-2: nothing changed
@pytest.mark.parametrize("failing", ["fetch", "checkout", "build"])
def test_an_early_failure_changes_nothing(tmp_path: Path, failing: str) -> None:
    server = FakeServer(failing={failing})

    code, place = deploy(tmp_path, server)

    assert code == 1
    assert server.said[-1].startswith("Stopped: ")
    assert server.said[-1].endswith(f"Staging still runs {PREVIOUS}.")
    assert {"backup", "migrate", "up"}.isdisjoint(server.kinds())
    assert place.current.read_text().strip() == PREVIOUS


# ------------------------------------------- step 3: database ahead of version
def test_a_database_ahead_of_the_version_asks_first(tmp_path: Path) -> None:
    server = FakeServer(pending_outputs=[DATABASE_AHEAD], answers=["no"])

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert len(server.asked) == 1
    question = server.asked[0]
    assert "1 change this version doesn't know" in question
    assert "core.0099_future" in question
    assert "type yes" in question
    assert {"backup", "migrate", "up"}.isdisjoint(server.kinds())


def test_typing_yes_goes_on_with_a_database_ahead(tmp_path: Path) -> None:
    server = FakeServer(pending_outputs=[DATABASE_AHEAD], answers=["yes"])

    code, _ = deploy(tmp_path, server)

    assert code == 0, server.output()
    assert "up" in server.kinds()


def test_a_database_that_fits_asks_nothing(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    assert server.asked == []


# ------------------------------------------------- step 4: the database copy
@pytest.mark.parametrize("failing", ["backup", "backup-check"])
def test_no_good_copy_means_no_migration(tmp_path: Path, failing: str) -> None:
    server = FakeServer(failing={failing})

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert "Stopped: " in server.output()
    assert {"migrate", "up"}.isdisjoint(server.kinds())


# ---------------------------------------------------------- step 5: migration
def test_a_migration_failing_before_any_change_keeps_the_old_version(
    tmp_path: Path,
) -> None:
    server = FakeServer(pending_outputs=[TWO_TO_RUN], failing={"migrate"})

    code, place = deploy(tmp_path, server)

    assert code == 1
    assert "up" not in server.kinds()
    assert f"{PREVIOUS} is still running" in server.output()
    assert "Restore" not in server.output()
    assert place.current.read_text().strip() == PREVIOUS


def test_a_migration_failing_halfway_says_to_restore_the_copy(
    tmp_path: Path,
) -> None:
    server = FakeServer(pending_outputs=[TWO_TO_RUN, ONE_TO_RUN], failing={"migrate"})

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert "up" not in server.kinds()
    assert "core.0005_a" in server.output()
    restore = f"Restore the copy saved in step 4: backups/{BACKUP_NAME}"
    assert restore in server.output()


# -------------------------------------------------- step 7: app doesn't answer
def test_no_answer_without_database_changes_puts_the_old_version_back(
    tmp_path: Path,
) -> None:
    server = FakeServer(broken_versions={NEW})

    code, place = deploy(tmp_path, server)

    assert code == 1
    assert server.slept >= HEALTH_WAIT_SECONDS
    ups = [call.env["CUCUMBER_VERSION"] for call in server.all("up") if call.env]
    assert ups == [NEW, PREVIOUS]
    kinds = server.kinds()
    assert PREVIOUS in server.all("checkout")[-1].command
    assert last_index(kinds, "checkout") < last_index(kinds, "up")
    back = f"The new version didn't answer, so {PREVIOUS} is back. Nothing was lost."
    assert back in server.said
    assert place.current.read_text().strip() == PREVIOUS
    assert "prune" not in kinds


def test_after_a_local_checkout_build_the_clone_is_left_alone(
    tmp_path: Path,
) -> None:
    """A `source-…` build has no commit in the clone to check out again."""
    practice = "source-2026-10-13-140000"
    server = FakeServer(broken_versions={NEW})

    code, place = deploy(tmp_path, server, current=practice)

    assert code == 1
    ups = [call.env["CUCUMBER_VERSION"] for call in server.all("up") if call.env]
    assert ups == [NEW, practice]
    assert not any(practice in call.command for call in server.all("checkout"))
    assert f"so {practice} is back. Nothing was lost." in server.output()
    assert place.current.read_text().strip() == practice


def test_no_answer_after_database_changes_says_to_restore(tmp_path: Path) -> None:
    server = FakeServer(
        pending_outputs=[TWO_TO_RUN, NONE_TO_RUN], broken_versions={NEW}
    )

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert len(server.all("up")) == 1, "must not put back a version the database left"
    output = server.output()
    assert "The new version changed the database and isn't answering." in output
    assert f"Restore the copy saved in step 4: backups/{BACKUP_NAME}" in output
    assert "app" in server.first("logs").command
    assert LOG_LINES_ON_FAILURE == 30
    assert APP_LOG[-1] in output
    assert APP_LOG[-LOG_LINES_ON_FAILURE] in output
    assert APP_LOG[-LOG_LINES_ON_FAILURE - 1] not in output


# --------------------------------------------------------- first ever deploy
def test_a_first_deploy_has_no_previous_version(tmp_path: Path) -> None:
    server = FakeServer(running_version=None)

    code, place = deploy(tmp_path, server, current=None)

    assert code == 0, server.output()
    assert server.said[-1].startswith(f"Done: staging now runs {NEW}")
    assert "(was" not in server.said[-1]
    assert place.current.read_text().strip() == NEW


def test_a_first_deploy_that_does_not_answer_says_there_is_nothing_to_go_back_to(
    tmp_path: Path,
) -> None:
    server = FakeServer(running_version=None, broken_versions={NEW})

    code, _ = deploy(tmp_path, server, current=None)

    assert code == 1
    assert len(server.all("up")) == 1
    assert "no previous version" in server.output()
