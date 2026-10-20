"""U0.7 AC15: the deploy checks the database's protections (design §8.3).

Step 3b, before the copy: against the database as it is. Step 5b, after
migrating: with the new version's list. Both run `cucumber_check_guards`
as the owner through the migrate service; any failure stops the deploy.
"""

from pathlib import Path

from scripts.deploy import main
from scripts.server import Place
from scripts.tests.fake_server import (
    NEW,
    PREVIOUS,
    FakeServer,
    make_home,
    shell_environment,
)

BACKUP_NAME = f"2026-10-13-1405-before-{NEW}.dump"
BROKEN = "plants_audit is switched off"


def deploy(tmp_path: Path, server: FakeServer) -> tuple[int, Place]:
    home = make_home(tmp_path)
    code = main(["staging", NEW], server.tools(), shell_environment(home))
    return code, Place("staging", home)


def test_the_check_runs_before_the_copy_and_again_after_migrating(
    tmp_path: Path,
) -> None:
    server = FakeServer()

    code, _ = deploy(tmp_path, server)

    assert code == 0, server.output()
    kinds = [k for k in server.kinds() if k in {"guards", "backup", "migrate", "up"}]
    assert kinds == ["guards", "backup", "migrate", "guards", "up"]


def test_the_check_runs_as_the_owner_through_the_migrate_service(
    tmp_path: Path,
) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    calls = server.all("guards")
    assert len(calls) == 2
    for call in calls:
        command = call.command
        assert command[command.index("run") :][:2] == ["run", "--rm"]
        assert command[-4:] == [
            "migrate",
            "python",
            "manage.py",
            "cucumber_check_guards",
        ]


def test_each_check_is_a_step_said_in_plain_words(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    said = server.said
    first = said.index("Checking the database's protections")
    again = said.index("Checking the database's protections again")
    assert said.index("Checking the database fits this version") < first
    assert first < said.index("Saving a copy of the database") < again
    assert again < said.index("Restarting the app")


def test_protections_off_before_the_copy_stop_with_nothing_changed(
    tmp_path: Path,
) -> None:
    server = FakeServer(guard_results=[BROKEN])

    code, place = deploy(tmp_path, server)

    assert code == 1
    assert {"backup", "migrate", "up"}.isdisjoint(server.kinds())
    output = server.output()
    assert "The database's protections are not all on:" in output
    assert BROKEN in output
    assert "See the release runbook." in output
    assert server.said[-1].endswith(f"Staging still runs {PREVIOUS}.")
    assert place.current.read_text().strip() == PREVIOUS


def test_protections_off_after_migrating_stop_before_the_restart(
    tmp_path: Path,
) -> None:
    server = FakeServer(guard_results=[None, BROKEN])

    code, place = deploy(tmp_path, server)

    assert code == 1
    assert "migrate" in server.kinds()
    assert "up" not in server.kinds()
    output = server.output()
    assert "The database was updated, but its protections are not all on:" in output
    assert BROKEN in output
    assert f"The app was not restarted, so {PREVIOUS} is still running." in output
    assert "See the release runbook." in output
    assert server.said[-1] == f"Restore the copy saved in step 4: backups/{BACKUP_NAME}"
    assert place.current.read_text().strip() == PREVIOUS
