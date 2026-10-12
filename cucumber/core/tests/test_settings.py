"""AC12: debug is off unless asked for, and start-up fails closed.

Each test imports the settings in a fresh Python with only the variables it
lists, so nothing from the developer's own environment or .env leaks in.
"""

import os
import subprocess
import sys

import pytest
from django.conf import settings

REQUIRED_WHEN_DEBUG_OFF = ["DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DB_PASSWORD"]
COMPLETE = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DJANGO_ALLOWED_HOSTS": "localhost",
    "DB_PASSWORD": "test-only-not-a-secret",
}
PRINT_DEBUG = "import cucumber.settings as s; print(s.DEBUG)"


def error_line(result: subprocess.CompletedProcess[str]) -> str:
    """The exception's own line; the traceback above it echoes source code."""
    lines = result.stderr.strip().splitlines()
    return lines[-1] if lines else ""


def load_settings(variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", PRINT_DEBUG],
        cwd=settings.BASE_DIR,
        env={"PATH": os.environ["PATH"], **variables},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_debug_is_off_when_DJANGO_DEBUG_is_missing() -> None:
    result = load_settings(COMPLETE)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.parametrize("value", ["0", "true", "True", "yes", "on", " "])
def test_debug_stays_off_unless_DJANGO_DEBUG_is_exactly_1(value: str) -> None:
    result = load_settings({**COMPLETE, "DJANGO_DEBUG": value})

    assert result.stdout.strip() == "False", result.stderr


def test_DJANGO_DEBUG_1_turns_debug_on() -> None:
    result = load_settings({"DJANGO_DEBUG": "1"})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


@pytest.mark.parametrize("missing", REQUIRED_WHEN_DEBUG_OFF)
def test_refuses_to_start_without_required_variable(missing: str) -> None:
    variables = {name: value for name, value in COMPLETE.items() if name != missing}

    result = load_settings(variables)

    assert result.returncode != 0
    assert error_line(result).startswith("django.core.exceptions.ImproperlyConfigured")
    assert missing in error_line(result)


@pytest.mark.parametrize("blank", REQUIRED_WHEN_DEBUG_OFF)
def test_blank_value_counts_as_missing(blank: str) -> None:
    result = load_settings({**COMPLETE, blank: "   "})

    assert result.returncode != 0
    assert blank in error_line(result)
