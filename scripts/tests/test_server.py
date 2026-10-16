"""AC3, AC4: each command touches one environment, through its own secrets file."""

from pathlib import Path

import pytest

from scripts.server import (
    Place,
    ServerError,
    ask,
    check_secrets_private,
    compose_command,
    compose_environment,
    current_version,
    place_for,
    read_secrets,
    real_tools,
    run_command,
)
from scripts.tests.fake_server import APP_PORT, make_home, shell_environment


def test_home_is_cucumber_in_the_admins_folder_by_default() -> None:
    place = place_for("staging", {"HOME": "/Users/sawat"})

    assert place.home == Path("/Users/sawat/cucumber")
    assert place.secrets == Path("/Users/sawat/cucumber/staging/secrets.env")


def test_CUCUMBER_HOME_moves_the_home_folder(tmp_path: Path) -> None:
    place = place_for("production", {"HOME": "/x", "CUCUMBER_HOME": str(tmp_path)})

    assert place.folder == tmp_path / "production"
    assert place.lock == tmp_path / "deploy.lock"


@pytest.mark.parametrize("name", ["prod", "Staging", "local", ""])
def test_unknown_environment_is_refused(name: str) -> None:
    with pytest.raises(ServerError, match="staging or production"):
        place_for(name, {"HOME": "/x"})


def test_each_environment_has_its_own_image_name() -> None:
    assert Place("staging", Path("/h")).image == "cucumber-staging"
    assert Place("production", Path("/h")).image == "cucumber-production"


def test_missing_secrets_file_is_refused(tmp_path: Path) -> None:
    place = Place("staging", tmp_path)

    with pytest.raises(ServerError, match="secrets.env"):
        check_secrets_private(place)


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660])
def test_secrets_readable_by_others_is_refused(tmp_path: Path, mode: int) -> None:
    home = make_home(tmp_path, secrets_mode=mode)

    with pytest.raises(ServerError, match="chmod 600"):
        check_secrets_private(Place("staging", home))


def test_secrets_readable_only_by_the_admin_is_accepted(tmp_path: Path) -> None:
    home = make_home(tmp_path, secrets_mode=0o600)

    check_secrets_private(Place("staging", home))


def test_secrets_are_read_ignoring_comments_and_blank_lines(tmp_path: Path) -> None:
    home = make_home(tmp_path)
    secrets = Place("staging", home).secrets
    secrets.write_text(secrets.read_text() + "\n# a note\nEMPTY=\n")

    values = read_secrets(Place("staging", home))

    assert values["APP_PORT"] == APP_PORT
    assert values["EMPTY"] == ""
    assert not any(name.startswith("#") for name in values)


def test_current_version_is_none_before_the_first_deploy(tmp_path: Path) -> None:
    home = make_home(tmp_path, current=None)

    assert current_version(Place("staging", home)) is None


def test_current_version_is_read_without_the_line_ending(tmp_path: Path) -> None:
    home = make_home(tmp_path, current="2026.09.3")

    assert current_version(Place("staging", home)) == "2026.09.3"


def test_compose_gets_only_path_home_and_docker_variables(tmp_path: Path) -> None:
    shell = {**shell_environment(tmp_path), "DOCKER_CONTEXT": "desktop-linux"}

    passed = compose_environment(shell, CUCUMBER_VERSION="2026.10.1")

    assert passed == {
        "PATH": shell["PATH"],
        "HOME": shell["HOME"],
        "DOCKER_HOST": shell["DOCKER_HOST"],
        "DOCKER_CONTEXT": "desktop-linux",
        "CUCUMBER_VERSION": "2026.10.1",
    }


def test_compose_command_names_the_project_secrets_and_file(tmp_path: Path) -> None:
    place = Place("staging", tmp_path)

    command = compose_command(place, "up", "-d", "app")

    assert command[:2] == ["docker", "compose"]
    assert command[command.index("-p") + 1] == "cucumber-staging"
    env_file = Path(command[command.index("--env-file") + 1])
    assert env_file.is_absolute() and env_file == place.secrets
    compose_file = Path(command[command.index("-f") + 1])
    assert compose_file == place.src / "deploy" / "compose.server.yaml"
    assert command[-3:] == ["up", "-d", "app"]


def test_compose_file_can_come_from_another_checkout(tmp_path: Path) -> None:
    place = Place("staging", tmp_path)
    checkout = tmp_path / "pull-request"

    command = compose_command(place, "build", src=checkout)

    compose_file = Path(command[command.index("-f") + 1])
    assert compose_file == checkout / "deploy" / "compose.server.yaml"


# ------------------------------------------------------- the real runner
def test_the_runner_returns_what_the_command_printed() -> None:
    assert run_command(["echo", "hello"]) == "hello\n"


def test_the_runner_passes_exactly_the_given_environment() -> None:
    printed = run_command(["env"], {"PATH": "/usr/bin:/bin", "ONLY": "this"})

    names = {line.split("=", 1)[0] for line in printed.splitlines()}
    assert names <= {"PATH", "ONLY", "PWD", "SHLVL", "_"}
    assert "ONLY" in names


def test_the_runner_uses_no_shell(tmp_path: Path) -> None:
    printed = run_command(["echo", "$HOME; touch", str(tmp_path / "made")])

    assert "$HOME" in printed
    assert not (tmp_path / "made").exists()


def test_a_failure_carries_the_commands_own_error() -> None:
    with pytest.raises(RuntimeError, match="No flag called typo"):
        run_command(["sh", "-c", "echo 'No flag called typo' >&2; exit 1"])


def test_the_runner_reads_and_writes_files(tmp_path: Path) -> None:
    source = tmp_path / "in.bin"
    source.write_bytes(b"\x00binary\xff")
    copy = tmp_path / "out.bin"
    copy.touch(mode=0o600)

    run_command(["cat"], stdin=source, stdout=copy)

    assert copy.read_bytes() == b"\x00binary\xff"
    assert copy.stat().st_mode & 0o777 == 0o600


def test_a_command_that_hangs_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung build or copy must not hold the deploy lock for ever (G4 review)."""
    monkeypatch.setattr("scripts.server.COMMAND_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(RuntimeError, match="took longer than"):
        run_command(["sleep", "5"])


def test_no_keyboard_counts_as_no(monkeypatch: pytest.MonkeyPatch) -> None:
    def closed(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)

    assert ask("Type yes to go on: ") == ""


def test_real_tools_are_complete() -> None:
    tools = real_tools()

    assert tools.run is run_command
