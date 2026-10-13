"""AC1: one image runs Cucumber with gunicorn, as a non-root user (design §2).

Read as text here. CI's "Container image" job (G3) builds it for Intel and
checks the built image itself: its user and that its environment holds no
settings.
"""

import re
from pathlib import Path

import pytest
import yaml
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
DOCKERFILE = ROOT / "Dockerfile"
BASE_IMAGE = re.compile(r"FROM python:3\.13-slim(@sha256:[0-9a-f]{64})(\s+AS\s+\w+)?")
GUNICORN_OPTIONS = [
    "cucumber.wsgi",
    "--bind 0.0.0.0:8000",
    "--worker-class gthread",
    "--workers 2",
    "--threads 4",
    "--timeout 60",
    "--max-requests 1000",
    "--max-requests-jitter 100",
]
KEPT_OUT = [".git", ".venv", ".env", "secrets.env", "spike", "docs", "uat"]


@pytest.fixture(scope="module")
def instructions() -> list[str]:
    """Dockerfile instructions, continuation lines joined, comments dropped."""
    assert DOCKERFILE.is_file(), "Dockerfile is missing"
    joined = re.sub(r"\\\n\s*", " ", DOCKERFILE.read_text())
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def final_stage(instructions: list[str]) -> list[str]:
    starts = [i for i, line in enumerate(instructions) if line.startswith("FROM ")]
    return instructions[starts[-1] :]


def test_two_stages_on_the_same_pinned_python(instructions: list[str]) -> None:
    stages = [line for line in instructions if line.startswith("FROM ")]
    bases = [BASE_IMAGE.fullmatch(line) for line in stages]

    assert len(bases) == 2
    assert all(bases), "each stage must use python:3.13-slim pinned to a digest"
    assert len({match[1] for match in bases if match}) == 1


def test_packages_come_from_the_lock_file_without_dev_tools(
    instructions: list[str],
) -> None:
    sync = [line for line in instructions if "uv sync" in line]

    assert sync and all("--locked" in line and "--no-dev" in line for line in sync)


def test_no_setting_or_password_is_baked_into_the_image(
    instructions: list[str],
) -> None:
    baked = [
        line
        for line in instructions
        if re.match(r"(ENV|ARG)\s", line) and re.search(r"\b(DJANGO|DB)_", line)
    ]

    assert baked == []


def test_static_files_are_collected_as_production_on_one_line(
    instructions: list[str],
) -> None:
    collect = [line for line in instructions if "collectstatic" in line]

    assert len(collect) == 1
    assert collect[0].startswith("RUN ")
    assert "DJANGO_ENVIRONMENT=production" in collect[0]
    assert "--noinput" in collect[0]


def test_the_app_runs_as_a_non_root_user(instructions: list[str]) -> None:
    final = final_stage(instructions)
    users = [line for line in final if line.startswith("USER ")]

    assert users and users[-1] in {"USER cucumber", "USER 10001", "USER 10001:10001"}
    assert any("10001" in line and "cucumber" in line for line in final)


def test_gunicorn_serves_on_port_8000(instructions: list[str]) -> None:
    final = final_stage(instructions)
    command = " ".join(line for line in final if line.startswith("CMD "))
    command = command.replace('", "', " ").replace('","', " ")

    assert "EXPOSE 8000" in final
    assert "gunicorn" in command
    for option in GUNICORN_OPTIONS:
        assert option in command, option


def test_secrets_and_clutter_stay_out_of_the_image() -> None:
    ignore = ROOT / ".dockerignore"
    assert ignore.is_file(), ".dockerignore is missing"
    entries = {
        line.strip().removeprefix("**/").rstrip("/")
        for line in ignore.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert sorted(set(KEPT_OUT) - entries) == []


def test_dependabot_proposes_base_image_updates() -> None:
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())

    ecosystems = {update["package-ecosystem"] for update in config["updates"]}
    assert "docker" in ecosystems
