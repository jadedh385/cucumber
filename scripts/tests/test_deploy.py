"""AC10, AC11: one command deploys a version, step by step, and says so.

The failures of design §6.3 (AC12) are in test_deploy_failures.py.
"""

import fcntl
import json
import re
import threading
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.deploy import BACKUPS_KEPT, main
from scripts.server import Place
from scripts.tests.fake_server import (
    APP_PORT,
    NEW,
    OTHER_SHA,
    OWNER_PASSWORD,
    PREVIOUS,
    PUBLIC_HOST,
    SECRET_VALUE,
    STRAY_SHELL_PASSWORD,
    FakeServer,
    make_home,
    shell_environment,
)

STEP_LINES = [
    "Checking before we start",
    f"Getting {NEW} from GitHub",
    "Building the app",
    "Checking the database fits this version",
    "Saving a copy of the database",
    "Updating the database (no changes)",
    "Restarting the app",
    "Checking the app answers",
    f"Done: staging now runs {NEW} (was {PREVIOUS}). Took ",
]


def deploy(
    tmp_path: Path,
    server: FakeServer,
    *args: str,
    environment: str = "staging",
    current: str | None = PREVIOUS,
) -> tuple[int, Place]:
    home = make_home(tmp_path, environment, current=current)
    argv = [environment, *(args or (NEW,))]
    code = main(argv, server.tools(), shell_environment(home))
    return code, Place(environment, home)


def said_in_order(said: list[str], expected: list[str]) -> bool:
    """Each expected line starts one said line, in this order."""
    position = 0
    for line in said:
        if position < len(expected) and line.startswith(expected[position]):
            position += 1
    return position == len(expected)


# ------------------------------------------------------------ a good deploy
def test_a_good_deploy_prints_each_step_in_plain_words(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = deploy(tmp_path, server)

    assert code == 0, server.output()
    assert said_in_order(server.said, STEP_LINES), server.output()


def test_the_done_line_says_how_long_it_took(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    assert re.search(r"Took (\d+ min )?\d+ s\.$", server.said[-1]), server.said[-1]


def test_steps_run_in_the_design_order(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    order = ["fetch", "checkout", "build", "pending", "backup", "backup-check"]
    order += ["migrate", "up", "health"]
    positions = [server.index(kind) for kind in order]
    assert positions == sorted(positions), server.kinds()


def test_the_running_version_is_recorded(tmp_path: Path) -> None:
    code, place = deploy(tmp_path, FakeServer())

    assert code == 0
    assert place.current.read_text().strip() == NEW


def test_the_tag_is_fetched_with_force_and_checked_out_in_the_clone(
    tmp_path: Path,
) -> None:
    server = FakeServer()

    _, place = deploy(tmp_path, server)

    fetch = server.first("fetch").command
    assert "--tags" in fetch and "--force" in fetch
    checkout = server.first("checkout").command
    assert NEW in checkout
    for call in server.calls:
        if call.command[:1] == ["git"]:
            assert str(place.src) in call.command, call.command


def test_the_image_is_named_for_the_environment_and_version(tmp_path: Path) -> None:
    server = FakeServer()

    _, place = deploy(tmp_path, server)

    build = server.first("build").command
    assert f"cucumber-staging:{NEW}" in build
    assert str(place.src) in build


# ---------------------------------------------------------- the database copy
def test_a_private_database_copy_is_saved_and_checked_before_migrating(
    tmp_path: Path,
) -> None:
    server = FakeServer()

    _, place = deploy(tmp_path, server)

    dump = server.first("backup")
    assert {"exec", "-T", "db", "pg_dump", "-Fc"} <= set(dump.command)
    assert dump.stdout == place.backups / f"2026-10-13-1405-before-{NEW}.dump"
    assert dump.stdout.stat().st_mode & 0o777 == 0o600
    assert server.first("backup-check").stdin == dump.stdout
    assert server.index("backup-check") < server.index("migrate")


def test_an_earlier_copy_is_never_overwritten(tmp_path: Path) -> None:
    """Two deploys in the same minute would give the copy the same name."""
    server = FakeServer()
    home = make_home(tmp_path)
    place = Place("staging", home)
    earlier = place.backups / f"2026-10-13-1405-before-{NEW}.dump"
    earlier.write_bytes(b"the earlier copy")

    code = main(["staging", NEW], server.tools(), shell_environment(home))

    assert code == 1
    assert earlier.read_bytes() == b"the earlier copy"
    assert "Stopped: " in server.output()
    assert {"backup", "migrate", "up"}.isdisjoint(server.kinds())


def test_only_the_last_five_copies_are_kept(tmp_path: Path) -> None:
    server = FakeServer()
    home = make_home(tmp_path)
    place = Place("staging", home)
    older = [f"2026-09-0{day}-0900-before-2026.09.{day}.dump" for day in range(1, 7)]
    for name in older:
        (place.backups / name).write_bytes(b"old copy")

    main(["staging", NEW], server.tools(), shell_environment(home))

    kept = sorted(path.name for path in place.backups.iterdir())
    assert BACKUPS_KEPT == 5
    assert kept == [*older[-4:], f"2026-10-13-1405-before-{NEW}.dump"]


# --------------------------------------------------------------- migrations
@pytest.mark.parametrize(
    ("to_run", "line"),
    [
        (["core.0005_a"], "Updating the database (1 change)"),
        (["core.0005_a", "core.0006_b"], "Updating the database (2 changes)"),
    ],
)
def test_the_number_of_database_changes_is_shown(
    tmp_path: Path, to_run: list[str], line: str
) -> None:
    done = json.dumps({"pending": [], "unknown": []})
    server = FakeServer(
        pending_outputs=[json.dumps({"pending": to_run, "unknown": []}), done]
    )

    deploy(tmp_path, server)

    assert line in server.said, server.output()


def test_migrations_run_once_in_the_one_off_step(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    migrate = server.all("migrate")
    assert len(migrate) == 1
    assert {"run", "--rm", "migrate"} <= set(migrate[0].command)


# --------------------------------------------------------------- compose use
def test_compose_gets_a_minimal_environment_with_the_version(tmp_path: Path) -> None:
    server = FakeServer()

    _, place = deploy(tmp_path, server)

    compose_calls = [call for call in server.calls if "compose" in call.command]
    assert compose_calls
    for call in compose_calls:
        assert call.env is not None, call.command
        extra = {
            name
            for name in call.env
            if name not in {"PATH", "HOME", "CUCUMBER_VERSION", "IMAGE_NAME"}
            and not name.startswith("DOCKER_")
        }
        assert extra == set(), call.command
        assert call.env["CUCUMBER_VERSION"] in {NEW, PREVIOUS}
        assert call.env["IMAGE_NAME"] == "cucumber-staging"
        assert call.command[call.command.index("-p") + 1] == "cucumber-staging"
        env_file = Path(call.command[call.command.index("--env-file") + 1])
        assert env_file == place.secrets


def test_no_secret_is_shown_passed_on_or_logged(tmp_path: Path) -> None:
    server = FakeServer()

    _, place = deploy(tmp_path, server)

    secrets = [SECRET_VALUE, OWNER_PASSWORD, STRAY_SHELL_PASSWORD]
    log = "".join(path.read_text() for path in place.logs.iterdir())
    for secret in secrets:
        assert secret not in server.output()
        assert secret not in log
        for call in server.calls:
            assert not any(secret in part for part in call.command), call.command
            assert secret not in json.dumps(call.env or {}), call.command


# ------------------------------------------------------------- health check
def test_health_is_asked_like_cloudflare_asks(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    health = server.first("health")
    assert health.command == [f"http://127.0.0.1:{APP_PORT}/health/"]
    assert health.env is not None
    assert health.env["Host"] == PUBLIC_HOST
    assert health.env["X-Forwarded-Proto"] == "https"


def test_a_slow_start_is_waited_for(tmp_path: Path) -> None:
    server = FakeServer()
    answers = iter([(503, "starting"), (503, "starting"), (200, "ok")])
    record = server.get

    def slow_get(url: str, headers: Mapping[str, str]) -> tuple[int, str]:
        record(url, headers)
        return next(answers)

    server.get = slow_get  # type: ignore[method-assign]

    code, _ = deploy(tmp_path, server)

    assert code == 0, server.output()
    assert 0 < server.slept < 60


# ------------------------------------------------------ log, images, cache
def test_every_printed_line_is_saved_to_the_deploy_log(tmp_path: Path) -> None:
    server = FakeServer()

    _, place = deploy(tmp_path, server)

    logs = list(place.logs.glob(f"*-{NEW}.log"))
    assert len(logs) == 1
    saved = logs[0].read_text()
    assert all(line in saved for line in server.said)


def test_old_images_are_removed_but_the_previous_one_is_kept(tmp_path: Path) -> None:
    server = FakeServer(
        image_tags=[NEW, "2026.09.5", "2026.09.4", PREVIOUS, "2026.09.2"]
    )

    deploy(tmp_path, server)

    removed = [part for call in server.all("image-remove") for part in call.command]
    assert "cucumber-staging:2026.09.2" in removed
    assert f"cucumber-staging:{PREVIOUS}" not in removed
    assert f"cucumber-staging:{NEW}" not in removed
    assert not any("cucumber-production" in part for part in removed)


def test_old_build_cache_is_cleared_after_a_good_deploy(tmp_path: Path) -> None:
    server = FakeServer()

    deploy(tmp_path, server)

    prune = server.first("prune").command
    assert "builder" in prune and "until=168h" in " ".join(prune)


# ------------------------------------------------------- checks at step 0
def test_another_deploy_running_stops_this_one(tmp_path: Path) -> None:
    server = FakeServer()
    home = make_home(tmp_path)
    place = Place("staging", home)
    codes: list[int] = []
    with place.lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        attempt = threading.Thread(
            target=lambda: codes.append(
                main(["staging", NEW], server.tools(), shell_environment(home))
            ),
            daemon=True,
        )
        attempt.start()
        attempt.join(timeout=10)
        assert not attempt.is_alive(), "the deploy waited for the lock instead"

    assert codes == [1]
    assert "Another deploy is running" in server.output()
    assert "fetch" not in server.kinds()


def test_the_lock_is_let_go_afterwards(tmp_path: Path) -> None:
    _, place = deploy(tmp_path, FakeServer())

    with place.lock.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_secrets_readable_by_others_stop_the_deploy(tmp_path: Path) -> None:
    server = FakeServer()
    home = make_home(tmp_path, secrets_mode=0o644)

    code = main(["staging", NEW], server.tools(), shell_environment(home))

    assert code == 1
    assert "chmod 600" in server.output()
    assert server.calls == []


def test_a_missing_tag_stops_the_deploy(tmp_path: Path) -> None:
    server = FakeServer(tags_on_github={PREVIOUS})

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert f"No tag {NEW} on GitHub" in server.output()
    assert "build" not in server.kinds()


def test_stray_files_in_the_clone_stop_the_deploy(tmp_path: Path) -> None:
    server = FakeServer(stray_files="?? notes.txt\n!! staticfiles/\n")

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert "notes.txt" in server.output()
    assert "build" not in server.kinds()


def test_the_clones_own_virtual_environment_is_not_a_stray(tmp_path: Path) -> None:
    server = FakeServer(stray_files="!! .venv/\n")

    code, _ = deploy(tmp_path, server)

    assert code == 0, server.output()


def test_a_tag_that_moved_since_checkout_stops_the_deploy(tmp_path: Path) -> None:
    server = FakeServer(head_sha=OTHER_SHA)

    code, _ = deploy(tmp_path, server)

    assert code == 1
    assert "build" not in server.kinds()


# ------------------------------------------------------- what may be deployed
@pytest.mark.parametrize("version", ["main", "feature/split-batch", "2026.13.1"])
def test_production_refuses_anything_but_a_release_tag(
    tmp_path: Path, version: str
) -> None:
    server = FakeServer()

    code, _ = deploy(tmp_path, server, version, environment="production")

    assert code == 1
    assert "Stopped:" in server.output()
    assert not any(call.command[:1] == ["docker"] for call in server.calls)


def test_production_refuses_a_local_checkout(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = deploy(
        tmp_path, server, NEW, "--source", str(tmp_path), environment="production"
    )

    assert code != 0
    assert "build" not in server.kinds()


def test_staging_can_practise_with_main(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = deploy(tmp_path, server, "main")

    assert code == 0, server.output()
    assert "fetch" in server.kinds()
    assert "build" in server.kinds()


def test_staging_can_build_a_local_checkout_for_the_ci_rehearsal(
    tmp_path: Path,
) -> None:
    server = FakeServer()
    checkout = tmp_path / "pull-request"
    (checkout / "deploy").mkdir(parents=True)

    code, _ = deploy(tmp_path, server, "main", "--source", str(checkout))

    assert code == 0, server.output()
    assert {"tag-check", "fetch", "checkout"}.isdisjoint(server.kinds())
    assert str(checkout) in server.first("build").command
    up = server.first("up").command
    assert Path(up[up.index("-f") + 1]) == checkout / "deploy" / "compose.server.yaml"


def test_the_source_option_is_not_in_the_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "--source" not in capsys.readouterr().out


def test_an_unknown_environment_is_refused(tmp_path: Path) -> None:
    server = FakeServer()
    home = make_home(tmp_path)

    code = main(["prod", NEW], server.tools(), shell_environment(home))

    assert code == 1
    assert "staging or production" in server.output()
