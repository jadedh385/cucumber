"""AC13: no secret committed; .env.example names every variable, without values."""

import re
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

from cucumber.env import env

ROOT = Path(settings.BASE_DIR)
# env("NAME") and settings' required("NAME", …), which reads through env().
ENV_CALL = re.compile(r'\b(?:env|required)\(\s*"([A-Z0-9_]+)"')
COMPOSE_VARIABLE = re.compile(r"\$\{([A-Z0-9_]+)")


def example_entries(name: str = ".env.example") -> dict[str, str]:
    """`NAME=value` pairs from an example file, ignoring comments and blank lines."""
    entries = {}
    for line in (ROOT / name).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            name, _, value = line.partition("=")
            entries[name.strip()] = value.strip()
    return entries


def names_read_by_python() -> set[str]:
    """Names passed to env() by the app and shared fixtures (tests use fakes)."""
    app_code = [
        path
        for path in ROOT.joinpath("cucumber").rglob("*.py")
        if "tests" not in path.parts
    ]
    sources = [*app_code, ROOT / "conftest.py"]
    return {name for path in sources for name in ENV_CALL.findall(path.read_text())}


def is_git_ignored(name: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", name], cwd=ROOT, check=False
    )
    return result.returncode == 0


def test_dot_env_is_git_ignored_but_the_example_is_not() -> None:
    assert is_git_ignored(".env")
    assert not is_git_ignored(".env.example")


def test_dot_env_was_never_committed() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", ".env"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert tracked.stdout == ""


def test_example_names_every_variable_the_code_reads() -> None:
    read = names_read_by_python()
    assert read, "found no env() calls: has the helper been renamed?"
    assert sorted(read - example_entries().keys()) == []


def test_example_names_every_variable_compose_reads() -> None:
    read = set(COMPOSE_VARIABLE.findall((ROOT / "compose.yaml").read_text()))
    assert sorted(read - example_entries().keys()) == []


def test_example_holds_no_values() -> None:
    filled = [name for name, value in example_entries().items() if value]
    assert filled == []


# ----------------------------------------- U0.4a AC4: the servers' secrets
SERVER_EXAMPLE = "deploy/secrets.env.example"
SERVER_COMPOSE = "deploy/compose.server.yaml"
# Read by docker compose itself, not by ${...} in the file.
COMPOSE_OWN = {"COMPOSE_PROFILES"}
# Passed by the deploy and flag commands for each run, never kept in the file.
DEPLOY_SUPPLIED = {"IMAGE_NAME", "CUCUMBER_VERSION"}


def test_server_secrets_files_are_git_ignored_but_the_example_is_not() -> None:
    assert is_git_ignored("deploy/secrets.env")
    assert is_git_ignored("secrets.env")
    assert not is_git_ignored(SERVER_EXAMPLE)


def test_server_example_names_every_variable_the_server_compose_reads() -> None:
    read = set(COMPOSE_VARIABLE.findall((ROOT / SERVER_COMPOSE).read_text()))
    listed = example_entries(SERVER_EXAMPLE).keys()

    assert sorted(read - listed - DEPLOY_SUPPLIED) == []
    assert sorted(DEPLOY_SUPPLIED & listed) == []


def test_server_example_lists_nothing_unused() -> None:
    read = set(COMPOSE_VARIABLE.findall((ROOT / SERVER_COMPOSE).read_text()))
    listed = example_entries(SERVER_EXAMPLE).keys()

    assert sorted(listed - read - COMPOSE_OWN) == []


def test_server_example_holds_no_values() -> None:
    filled = [name for name, value in example_entries(SERVER_EXAMPLE).items() if value]
    assert filled == []


def test_env_returns_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUCUMBER_TEST_VALUE", "  hello  ")
    assert env("CUCUMBER_TEST_VALUE", "default") == "hello"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_env_uses_the_default_when_unset_or_blank(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("CUCUMBER_TEST_VALUE", raising=False)
    else:
        monkeypatch.setenv("CUCUMBER_TEST_VALUE", value)
    assert env("CUCUMBER_TEST_VALUE", "default") == "default"
