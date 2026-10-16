"""AC2, AC3, AC6, AC8: the one compose file staging and production share.

Read as data (U0.4a design §3, §5). What differs between the two copies
comes only from the project name (`-p`) and the secrets file.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
COMPOSE = ROOT / "deploy" / "compose.server.yaml"
LONG_RUNNING = ["db", "app", "tunnel"]
VARIABLE = re.compile(r"\$\{([A-Z0-9_]+)(:?[?-])?([^}]*)\}")
MEMORY_CAPS = {
    "app": "APP_MEMORY_LIMIT",
    "db": "DB_MEMORY_LIMIT",
    "tunnel": "TUNNEL_MEMORY_LIMIT",
}
DIGEST = r"@sha256:[0-9a-f]{64}"
# Which services may see each secret (design §3.1).
SECRET_USERS = {
    "POSTGRES_PASSWORD": {"db"},
    "DB_OWNER_PASSWORD": {"db", "migrate"},
    "DB_APP_PASSWORD": {"db", "app"},
    "DJANGO_SECRET_KEY": {"migrate", "app"},
    "TUNNEL_TOKEN": {"tunnel"},
}
LOG_FLAGS = [
    "log_lock_waits=on",
    "log_min_duration_statement=500ms",
    "log_min_error_statement=panic",
]
# Values that make sense to compose, for the check that the file is valid.
FAKE_VALUES = {
    "APP_PORT": "8001",
    "DB_LOCAL_PORT": "5435",
    "IMAGE_NAME": "cucumber-check",
    "CUCUMBER_VERSION": "2026.10.1",
    **{name: "512m" for name in MEMORY_CAPS.values()},
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    assert COMPOSE.is_file(), "deploy/compose.server.yaml is missing"
    loaded = yaml.safe_load(COMPOSE.read_text())
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found = compose["services"]
    assert isinstance(found, dict)
    return found


def environment_of(service: dict[str, Any]) -> dict[str, str]:
    """A service's `environment:`, written as a map or as NAME=value lines."""
    environment = service.get("environment", {})
    if isinstance(environment, list):
        return dict(line.split("=", 1) for line in environment)
    return {name: str(value) for name, value in environment.items()}


def variables_in(value: object) -> set[str]:
    return {match[0] for match in VARIABLE.findall(yaml.safe_dump(value))}


def compose_variables() -> set[str]:
    return {name for name, _, _ in VARIABLE.findall(COMPOSE.read_text())}


# ------------------------------------------------------- AC2: comes back up
def test_it_has_the_four_services(services: dict[str, dict[str, Any]]) -> None:
    assert set(services) == {"db", "migrate", "app", "tunnel"}


@pytest.mark.parametrize("name", LONG_RUNNING)
def test_long_running_services_restart_after_a_reboot(
    services: dict[str, dict[str, Any]], name: str
) -> None:
    assert services[name]["restart"] == "unless-stopped"


def test_migrations_never_restart_by_themselves(
    services: dict[str, dict[str, Any]],
) -> None:
    migrate = services["migrate"]

    assert migrate["restart"] == "no"
    assert migrate["profiles"] == ["migrate"]


def test_the_tunnel_starts_only_when_its_profile_is_on(
    services: dict[str, dict[str, Any]],
) -> None:
    assert services["tunnel"]["profiles"] == ["tunnel"]
    assert "profiles" not in services["db"]
    assert "profiles" not in services["app"]


@pytest.mark.parametrize("name", LONG_RUNNING)
def test_logs_are_rotated_so_they_cannot_fill_the_disk(
    services: dict[str, dict[str, Any]], name: str
) -> None:
    options = services[name]["logging"]["options"]

    assert options == {"max-size": "10m", "max-file": "3"}


def test_database_data_lives_in_a_named_volume(compose: dict[str, Any]) -> None:
    db = compose["services"]["db"]

    assert "db-data:/var/lib/postgresql/data" in db["volumes"]
    assert "db-data" in compose["volumes"]
    assert "../docker/postgres/init:/docker-entrypoint-initdb.d:ro" in db["volumes"]


def test_the_app_starts_after_the_database_is_healthy(
    services: dict[str, dict[str, Any]],
) -> None:
    assert "healthcheck" in services["db"]
    assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert services["migrate"]["depends_on"]["db"]["condition"] == "service_healthy"


# ------------------------------------------------ AC3: two copies, one Mac
def test_names_come_only_from_the_project_name(compose: dict[str, Any]) -> None:
    assert "name" not in compose, "a fixed name would make both copies one project"
    for name, service in compose["services"].items():
        assert "container_name" not in service, name
        assert "build" not in service, name


@pytest.mark.parametrize("section", ["volumes", "networks"])
def test_volumes_and_networks_belong_to_one_project(
    compose: dict[str, Any], section: str
) -> None:
    """A fixed `name:` or `external:` would let staging and production share one."""
    for name, definition in (compose.get(section) or {}).items():
        definition = definition or {}
        assert "name" not in definition, f"{section}: {name}"
        assert not definition.get("external"), f"{section}: {name}"


@pytest.mark.parametrize("name", ["migrate", "app"])
def test_the_app_image_is_named_per_environment_and_version(
    services: dict[str, dict[str, Any]], name: str
) -> None:
    image = services[name]["image"]

    pattern = r"\$\{IMAGE_NAME:\?[^}]+\}:\$\{CUCUMBER_VERSION:\?[^}]+\}"
    assert re.fullmatch(pattern, image), image


def test_outside_images_are_pinned_to_a_digest(
    services: dict[str, dict[str, Any]],
) -> None:
    assert re.fullmatch(rf"postgres:17{DIGEST}", services["db"]["image"])
    tunnel = services["tunnel"]["image"]
    assert re.fullmatch(rf"cloudflare/cloudflared(:[\w.-]+)?{DIGEST}", tunnel)


def test_ports_open_on_this_mac_only_and_come_from_the_secrets(
    services: dict[str, dict[str, Any]],
) -> None:
    db_ports = services["db"]["ports"]
    app_ports = services["app"]["ports"]

    assert len(db_ports) == 1
    assert re.fullmatch(r"127\.0\.0\.1:\$\{DB_LOCAL_PORT:\?[^}]+\}:5432", db_ports[0])
    assert len(app_ports) == 1
    assert re.fullmatch(r"127\.0\.0\.1:\$\{APP_PORT:\?[^}]+\}:8000", app_ports[0])
    assert "ports" not in services["migrate"]
    assert "ports" not in services["tunnel"]


@pytest.mark.parametrize(("name", "variable"), MEMORY_CAPS.items())
def test_memory_caps_come_from_the_secrets_with_an_equal_swap_cap(
    services: dict[str, dict[str, Any]], name: str, variable: str
) -> None:
    service = services[name]
    cap = f"${{{variable}:-0}}"

    assert service["mem_limit"] == cap
    assert service["memswap_limit"] == cap


def test_every_other_value_must_be_set_with_a_clear_message() -> None:
    for name, operator, message in VARIABLE.findall(COMPOSE.read_text()):
        if name in MEMORY_CAPS.values():
            continue
        assert operator == ":?", f"{name} has a default or no check"
        assert "secrets.env" in message, f"{name}'s message doesn't name the file"


# ------------------------------------------ AC6: who gets which secret
def test_no_service_is_handed_the_whole_secrets_file(
    services: dict[str, dict[str, Any]],
) -> None:
    assert [name for name, service in services.items() if "env_file" in service] == []


@pytest.mark.parametrize(("secret", "users"), SECRET_USERS.items())
def test_each_secret_reaches_only_the_services_that_need_it(
    services: dict[str, dict[str, Any]], secret: str, users: set[str]
) -> None:
    seen_by = {
        name for name, service in services.items() if secret in variables_in(service)
    }

    assert seen_by == users


def test_migrations_connect_as_the_owner_and_the_app_as_the_app_user(
    services: dict[str, dict[str, Any]],
) -> None:
    migrate = environment_of(services["migrate"])
    app = environment_of(services["app"])

    assert migrate["DB_USER"] == "cucumber_owner"
    assert variables_in(migrate["DB_PASSWORD"]) == {"DB_OWNER_PASSWORD"}
    assert app["DB_USER"] == "cucumber_app"
    assert variables_in(app["DB_PASSWORD"]) == {"DB_APP_PASSWORD"}
    assert migrate["DB_HOST"] == app["DB_HOST"] == "db"


def test_the_tunnel_token_is_a_variable_not_an_argument(
    services: dict[str, dict[str, Any]],
) -> None:
    tunnel = services["tunnel"]

    assert "TUNNEL_TOKEN" in environment_of(tunnel)
    assert "--token" not in yaml.safe_dump(tunnel.get("command", ""))


# ------------------------------------------------------- AC8: database logs
def test_the_database_logs_lock_waits_and_slow_statements_without_values(
    services: dict[str, dict[str, Any]],
) -> None:
    command = services["db"]["command"]

    assert command[0] == "postgres"
    for flag in LOG_FLAGS:
        assert flag in command, flag
        assert command[command.index(flag) - 1] == "-c", flag


# ------------------------------------------- compose itself reads the file
def has_docker_compose() -> bool:
    if shutil.which("docker") is None:
        return False
    version = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, check=False
    )
    return version.returncode == 0


needs_docker = pytest.mark.skipif(
    not has_docker_compose(), reason="needs the docker compose command"
)


def compose_config(env_file: Path) -> subprocess.CompletedProcess[str]:
    """`docker compose config --quiet`: checks the file, prints no secrets."""
    command = ["docker", "compose", "-p", "cucumber-check"]
    command += ["--env-file", str(env_file), "-f", str(COMPOSE)]
    command += ["--profile", "migrate", "--profile", "tunnel", "config", "--quiet"]
    return subprocess.run(
        command,
        # The real HOME and DOCKER_* so compose finds its plugin and context,
        # as the deploy command passes them (design §3.1).
        env={
            name: value
            for name, value in os.environ.items()
            if name in {"PATH", "HOME"} or name.startswith("DOCKER_")
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@needs_docker
def test_compose_stops_with_a_clear_message_when_a_value_is_missing(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "secrets.env"
    empty.write_text("")

    result = compose_config(empty)

    assert result.returncode != 0
    assert "missing from secrets.env" in result.stderr


@needs_docker
def test_compose_accepts_a_complete_secrets_file(tmp_path: Path) -> None:
    assert COMPOSE.is_file(), "deploy/compose.server.yaml is missing"
    complete = tmp_path / "secrets.env"
    complete.write_text(
        "".join(
            f"{name}={FAKE_VALUES.get(name, 'test-only')}\n"
            for name in sorted(compose_variables())
        )
    )

    result = compose_config(complete)

    assert result.returncode == 0, result.stderr
