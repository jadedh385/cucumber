"""U0.3 AC12: debug is off unless asked for, and start-up fails closed.

Each test imports the settings in a fresh Python with only the variables it
lists (startup.py). Staging and production rules (U0.4a AC5, AC7) are in
test_server_settings.py.
"""

import pytest

from cucumber.core.tests.startup import error_line, load_settings

REQUIRED_WHEN_DEBUG_OFF = [
    "DJANGO_ENVIRONMENT",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DB_USER",
    "DB_PASSWORD",
]
COMPLETE = {
    "DJANGO_ENVIRONMENT": "local",
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DJANGO_ALLOWED_HOSTS": "localhost",
    "DB_USER": "cucumber_app",
    "DB_PASSWORD": "test-only-not-a-secret",
}


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


@pytest.mark.parametrize("hosts", [",", " , ", "*", "localhost,*"])
def test_refuses_hosts_that_are_empty_or_wildcard(hosts: str) -> None:
    result = load_settings({**COMPLETE, "DJANGO_ALLOWED_HOSTS": hosts})

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in error_line(result)


def test_weak_staff_passwords_are_refused() -> None:
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_password("1234")
