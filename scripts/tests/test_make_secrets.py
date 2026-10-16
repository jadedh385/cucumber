"""U0.4a G6: a server's secrets file, made on the server (U0.4b design §10.1)."""

import hashlib
import stat
from collections.abc import Callable
from itertools import count
from pathlib import Path
from secrets import token_urlsafe

import pytest

from scripts.make_secrets import (
    RANDOM_NAMES,
    TEMPLATE,
    fill_template,
    fingerprint,
    main,
    values_for,
    write_private,
)
from scripts.server import Place, ServerError, read_secrets


def numbered_random() -> Callable[[int], str]:
    """A fake `token_urlsafe`: different, readable text on each call."""
    numbers = count(1)
    return lambda size: f"random{next(numbers)}-" + "x" * size


def secrets_in(path: Path) -> dict[str, str]:
    """Read one secrets file the way the deploy command does."""
    return read_secrets(Place(path.parent.name, path.parent.parent))


def test_production_gets_its_own_name_ports_and_memory_caps() -> None:
    values = values_for("production", numbered_random())

    assert values["DJANGO_ENVIRONMENT"] == "production"
    assert values["DJANGO_ALLOWED_HOSTS"] == "cucumber.southeastcanopy.com"
    assert (
        values["DJANGO_CSRF_TRUSTED_ORIGINS"] == "https://cucumber.southeastcanopy.com"
    )
    assert (values["APP_PORT"], values["DB_LOCAL_PORT"]) == ("8000", "5436")
    # U0.4b Q3: app 1 GB, database 1.5 GB, tunnel 128 MB.
    caps = (
        values["APP_MEMORY_LIMIT"],
        values["DB_MEMORY_LIMIT"],
        values["TUNNEL_MEMORY_LIMIT"],
    )
    assert caps == ("1g", "1536m", "128m")


def test_staging_matches_what_runs_on_the_asus() -> None:
    values = values_for("staging", numbered_random())

    assert values["DJANGO_ALLOWED_HOSTS"] == "cucumber-staging.southeastcanopy.com"
    assert (values["APP_PORT"], values["DB_LOCAL_PORT"]) == ("8001", "5435")
    assert values["APP_MEMORY_LIMIT"] == "512m"


def test_https_starts_at_one_hour_and_the_tunnel_starts_off() -> None:
    values = values_for("production", numbered_random())

    assert values["DJANGO_HSTS_SECONDS"] == "3600"
    assert values["COMPOSE_PROFILES"] == ""
    # Compose needs some text even with the tunnel off (secrets.env.example).
    assert values["TUNNEL_TOKEN"]


def test_every_secret_and_password_is_new_random_text_and_all_differ() -> None:
    values = values_for("production", numbered_random())

    randoms = [values[name] for name in RANDOM_NAMES]
    assert len(set(randoms)) == len(RANDOM_NAMES)
    assert all(value.startswith("random") for value in randoms)


def test_the_secret_key_passes_the_apps_weak_key_check() -> None:
    key = values_for("production", token_urlsafe)["DJANGO_SECRET_KEY"]

    assert len(key) >= 50
    assert len(set(key)) >= 5
    assert not key.startswith("django-insecure-")


def test_an_unknown_environment_is_refused() -> None:
    with pytest.raises(ServerError, match="staging or production"):
        values_for("local", numbered_random())


def test_the_template_is_filled_and_its_comments_kept() -> None:
    template = "# Which copy\nDJANGO_ENVIRONMENT=\n\n# Ports\nAPP_PORT=\n"

    text = fill_template(
        template, {"DJANGO_ENVIRONMENT": "production", "APP_PORT": "8000"}
    )

    assert (
        text
        == "# Which copy\nDJANGO_ENVIRONMENT=production\n\n# Ports\nAPP_PORT=8000\n"
    )


def test_a_name_in_the_template_with_no_value_is_refused() -> None:
    with pytest.raises(ServerError, match="NEW_SETTING"):
        fill_template("APP_PORT=\nNEW_SETTING=\n", {"APP_PORT": "8000"})


def test_a_value_the_template_has_no_line_for_is_refused() -> None:
    with pytest.raises(ServerError, match="OLD_SETTING"):
        fill_template("APP_PORT=\n", {"APP_PORT": "8000", "OLD_SETTING": "x"})


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_the_real_template_and_the_values_name_the_same_settings(
    environment: str,
) -> None:
    text = fill_template(
        TEMPLATE.read_text(), values_for(environment, numbered_random())
    )

    assert f"DJANGO_ENVIRONMENT={environment}\n" in text


def test_a_fingerprint_is_the_first_8_characters_of_the_sha256() -> None:
    assert fingerprint("some secret") == hashlib.sha256(b"some secret").hexdigest()[:8]


def test_the_file_is_written_readable_by_its_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "secrets.env"

    write_private(path, "APP_PORT=8000\n")

    assert path.read_text() == "APP_PORT=8000\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_an_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "secrets.env"
    path.write_text("the real one\n")

    with pytest.raises(ServerError, match="already exists"):
        write_private(path, "a new one\n")

    assert path.read_text() == "the real one\n"


def test_main_makes_a_file_the_deploy_command_accepts(tmp_path: Path) -> None:
    code = main(["production"], {"CUCUMBER_HOME": str(tmp_path)})

    secrets_file = tmp_path / "production" / "secrets.env"
    assert code == 0
    assert stat.S_IMODE(secrets_file.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "production").stat().st_mode) == 0o700
    assert secrets_in(secrets_file)["DJANGO_ENVIRONMENT"] == "production"


def test_main_shows_fingerprints_but_never_a_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["production"], {"CUCUMBER_HOME": str(tmp_path)})

    printed = capsys.readouterr().out
    values = secrets_in(tmp_path / "production" / "secrets.env")
    for name in RANDOM_NAMES:
        assert values[name] not in printed
        assert f"{name} {fingerprint(values[name])}" in printed


def test_main_stops_with_a_plain_reason_when_the_file_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["production"], {"CUCUMBER_HOME": str(tmp_path)})
    capsys.readouterr()

    code = main(["production"], {"CUCUMBER_HOME": str(tmp_path)})

    assert code == 1
    assert "Stopped:" in capsys.readouterr().out
