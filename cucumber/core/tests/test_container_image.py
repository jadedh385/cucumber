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
    # gunicorn 25.1+ opens a control socket under $HOME, which isn't
    # writable in the container (U0.10a §9.3, AC18).
    "--no-control-socket",
]
# `.cache`: the Mac's Tailwind CLI must never be copied in (U0.10a §3.3).
KEPT_OUT = [".git", ".venv", ".env", "secrets.env", "spike", "docs", "uat", ".cache"]
CSS = "/app/.venv/bin/python -m scripts.css"


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


def build_stage(instructions: list[str]) -> list[str]:
    starts = [i for i, line in enumerate(instructions) if line.startswith("FROM ")]
    return instructions[starts[0] : starts[-1]]


def position(lines: list[str], text: str) -> int:
    found = [i for i, line in enumerate(lines) if text in line]
    assert len(found) == 1, f"expected one line with {text!r}, found {len(found)}"
    return found[0]


# ------------------------------------------- U0.10a AC1: the CSS build (§3.3)
def test_the_css_is_built_in_the_build_stage_before_collectstatic(
    instructions: list[str],
) -> None:
    build = build_stage(instructions)
    fetch = position(build, f"{CSS} fetch")
    copy_all = position(build, "COPY . .")
    compile_css = position(build, f"{CSS} build")
    collect = position(build, "collectstatic")

    assert fetch < copy_all < compile_css < collect
    assert all(line.startswith("RUN ") for line in (build[fetch], build[compile_css]))


def test_the_cli_download_is_cached_until_css_py_changes(
    instructions: list[str],
) -> None:
    """Only css.py is copied before `fetch`, so a code change doesn't fetch again."""
    build = build_stage(instructions)
    copy_script = position(build, "COPY scripts/__init__.py scripts/css.py scripts/")

    assert copy_script < position(build, f"{CSS} fetch")


def test_the_cli_is_kept_outside_the_app_folder(instructions: list[str]) -> None:
    """The run stage copies /app only, so the CLI never reaches it."""
    build = build_stage(instructions)

    assert "ENV CUCUMBER_TOOLS=/opt/tools" in build
    assert position(build, "CUCUMBER_TOOLS") < position(build, f"{CSS} fetch")


def test_the_run_stage_has_no_css_tools(instructions: list[str]) -> None:
    final = " ".join(final_stage(instructions))

    assert "scripts.css" not in final
    assert "CUCUMBER_TOOLS" not in final
    assert "/opt/tools" not in final


def test_the_run_stage_copies_only_the_app_from_the_build_stage(
    instructions: list[str],
) -> None:
    copies = [line for line in final_stage(instructions) if line.startswith("COPY ")]

    assert copies == ["COPY --from=build /app /app"]


def test_the_check_script_builds_the_css_before_the_tests() -> None:
    check = commands((ROOT / "scripts" / "check.sh").read_text())

    assert "==> CSS (tailwind)" in check
    assert "scripts.css build" in check
    assert check.index("scripts.css build") < check.index("uv run pytest")


def test_ci_caches_the_tailwind_cli_by_the_hash_of_css_py() -> None:
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    steps = [
        step
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/cache@")
    ]

    assert steps, "no actions/cache step in ci.yml"
    cached = [step for step in steps if ".cache/tools" in str(step["with"]["path"])]
    assert cached, "the Tailwind CLI folder is not cached"
    assert all(re.search(r"@[0-9a-f]{40}", step["uses"]) for step in cached)
    assert all("scripts/css.py" in step["with"]["key"] for step in cached)


# ------------------------------------- U0.10a AC18: no control socket line
def commands(script: str) -> str:
    """The script with its comment lines left out, so a comment can't pass."""
    return "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )


def test_the_deploy_rehearsal_finds_no_control_socket_error() -> None:
    """A line in the script's own shape: the grep, and `fail` when it finds it."""
    rehearsal = commands((ROOT / "scripts" / "rehearse_deploy.sh").read_text())

    assert re.search(r"grep\b.*Control server error.*\bfail\b", rehearsal)


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


def ci_steps_text() -> str:
    """Every `run:` of the CI job that builds and checks the image (design §9)."""
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    jobs = [job for job in ci["jobs"].values() if job.get("name") == "Container image"]
    assert len(jobs) == 1, 'ci.yml has no "Container image" job'
    return "\n".join(step.get("run", "") for step in jobs[0]["steps"])


def test_ci_builds_the_image_for_intel() -> None:
    assert "linux/amd64" in ci_steps_text()


def test_ci_runs_the_deploy_check_inside_the_image() -> None:
    assert "check --deploy --fail-level WARNING" in ci_steps_text()


def test_ci_rehearses_a_staging_deploy_of_the_pull_request() -> None:
    steps = ci_steps_text()

    assert "scripts.deploy staging" in steps
    assert "--source" in steps


def test_dependabot_proposes_base_image_updates() -> None:
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())

    ecosystems = {update["package-ecosystem"] for update in config["updates"]}
    assert "docker" in ecosystems
