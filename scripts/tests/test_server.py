"""AC3, AC4: each command touches one environment, through its own secrets file."""

from pathlib import Path

import pytest

from scripts.server import (
    Place,
    ServerError,
    check_secrets_private,
    compose_command,
    compose_environment,
    current_version,
    place_for,
    read_secrets,
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
