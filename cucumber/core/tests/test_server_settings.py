"""AC5, AC7: staging and production start only when safe (U0.4a design §4).

Each test starts the settings in a fresh Python with only the variables it
lists (startup.py), as a server would.
"""

import pytest

from cucumber.core.tests.startup import (
    error_line,
    load_settings,
    run_python,
    settings_values,
)

SERVERS = ["staging", "production"]
# Long enough, and not starting with django-insecure-, for check --deploy (M8).
FAKE_KEY = "test-only-not-a-secret-" + "q7Zp" * 12
SERVER = {
    "DJANGO_SECRET_KEY": FAKE_KEY,
    "DJANGO_ALLOWED_HOSTS": "cucumber.example.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://cucumber.example.com",
    "DB_USER": "cucumber_app",
    "DB_PASSWORD": "test-only-not-a-secret",
}
REQUIRED_ON_SERVERS = ["DJANGO_ENVIRONMENT", *SERVER]
SECURITY_SETTINGS = [
    "ENVIRONMENT",
    "SECURE_PROXY_SSL_HEADER",
    "SECURE_SSL_REDIRECT",
    "SECURE_REDIRECT_EXEMPT",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "SILENCED_SYSTEM_CHECKS",
    "CSRF_TRUSTED_ORIGINS",
    "STORAGES",
]
WHITENOISE_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
ONE_HOUR = 3600


def server(environment: str, **changes: str) -> dict[str, str]:
    return {**SERVER, "DJANGO_ENVIRONMENT": environment, **changes}


# ------------------------------------------------------------- AC5 refusals
@pytest.mark.parametrize("environment", SERVERS)
@pytest.mark.parametrize("missing", REQUIRED_ON_SERVERS)
def test_a_server_refuses_to_start_without_a_required_variable(
    environment: str, missing: str
) -> None:
    variables = server(environment)
    del variables[missing]

    result = load_settings(variables)

    assert result.returncode != 0
    assert error_line(result).startswith("django.core.exceptions.ImproperlyConfigured")
    assert missing in error_line(result)


@pytest.mark.parametrize("environment", SERVERS)
@pytest.mark.parametrize("blank", REQUIRED_ON_SERVERS)
def test_a_blank_value_counts_as_missing_on_a_server(
    environment: str, blank: str
) -> None:
    result = load_settings(server(environment, **{blank: "  "}))

    assert result.returncode != 0
    assert blank in error_line(result)


@pytest.mark.parametrize("name", ["prod", "Production", "dev", "test", "staging2"])
def test_an_unknown_environment_name_is_refused(name: str) -> None:
    result = load_settings(server(name))

    assert result.returncode != 0
    assert "DJANGO_ENVIRONMENT" in error_line(result)


@pytest.mark.parametrize("environment", SERVERS)
@pytest.mark.parametrize(
    "key",
    [
        "dev-only-not-a-secret",
        "short-" + "x7" * 10,
        "a" * 60,
        "django-insecure-" + "q7Zp" * 12,
    ],
)
def test_a_server_refuses_a_weak_secret_key(environment: str, key: str) -> None:
    """The same rule as `check --deploy`, at every start (G4 security review)."""
    result = load_settings(server(environment, DJANGO_SECRET_KEY=key))

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in error_line(result)


@pytest.mark.parametrize("environment", SERVERS)
def test_debug_can_not_be_on_for_a_server(environment: str) -> None:
    result = load_settings(server(environment, DJANGO_DEBUG="1"))

    assert result.returncode != 0
    assert "DJANGO_DEBUG" in error_line(result)


@pytest.mark.parametrize(
    "origins",
    [
        "http://cucumber.example.com",
        "https://cucumber.example.com,http://cucumber-staging.example.com",
        "cucumber.example.com",
    ],
)
def test_trusted_origins_must_be_https(origins: str) -> None:
    result = load_settings(server("production", DJANGO_CSRF_TRUSTED_ORIGINS=origins))

    assert result.returncode != 0
    assert "DJANGO_CSRF_TRUSTED_ORIGINS" in error_line(result)


def test_local_work_with_debug_on_needs_no_environment_name() -> None:
    values = settings_values({"DJANGO_DEBUG": "1"}, ["ENVIRONMENT"])

    assert values["ENVIRONMENT"] == "local"


# ------------------------------------------------------- AC7 security values
@pytest.mark.parametrize("environment", SERVERS)
def test_a_server_uses_https_only_settings(environment: str) -> None:
    values = settings_values(server(environment), SECURITY_SETTINGS)

    assert values["ENVIRONMENT"] == environment
    assert values["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert values["SECURE_SSL_REDIRECT"] is True
    assert values["SECURE_REDIRECT_EXEMPT"] == []
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["CSRF_COOKIE_SECURE"] is True
    assert values["SECURE_HSTS_SECONDS"] == ONE_HOUR
    assert values["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is True
    assert values["SECURE_HSTS_PRELOAD"] is False
    assert "security.W021" in values["SILENCED_SYSTEM_CHECKS"]
    assert values["CSRF_TRUSTED_ORIGINS"] == ["https://cucumber.example.com"]
    assert values["STORAGES"]["staticfiles"]["BACKEND"] == WHITENOISE_STORAGE


def test_hsts_time_comes_from_its_variable() -> None:
    week = "604800"

    values = settings_values(
        server("production", DJANGO_HSTS_SECONDS=week), ["SECURE_HSTS_SECONDS"]
    )

    assert values["SECURE_HSTS_SECONDS"] == int(week)


@pytest.mark.parametrize("value", ["a week", "-1", "1.5"])
def test_an_hsts_time_that_is_not_whole_seconds_is_refused(value: str) -> None:
    result = load_settings(server("production", DJANGO_HSTS_SECONDS=value))

    assert result.returncode != 0
    assert "DJANGO_HSTS_SECONDS" in error_line(result)


def test_local_work_has_no_https_settings_and_plain_static_files() -> None:
    values = settings_values({"DJANGO_DEBUG": "1"}, SECURITY_SETTINGS)

    assert values["SECURE_SSL_REDIRECT"] is False
    assert values["SESSION_COOKIE_SECURE"] is False
    assert values["CSRF_COOKIE_SECURE"] is False
    assert values["SECURE_HSTS_SECONDS"] == 0
    assert values["SECURE_PROXY_SSL_HEADER"] is None
    assert values["STORAGES"]["staticfiles"]["BACKEND"] != WHITENOISE_STORAGE


@pytest.mark.parametrize("environment", SERVERS)
def test_errors_go_to_the_container_log_and_never_by_email(environment: str) -> None:
    values = settings_values(server(environment), ["LOGGING", "ADMINS"])

    logging = values["LOGGING"]
    handlers = logging["handlers"].values()
    assert any(handler["class"] == "logging.StreamHandler" for handler in handlers)
    assert not any("AdminEmailHandler" in handler["class"] for handler in handlers)
    assert logging["root"]["level"] == "WARNING"
    assert values["ADMINS"] == []


LOG_AN_ERROR = """
import logging
import django
django.setup()
from django.conf import settings
def save(password=settings.DATABASES["default"]["PASSWORD"]):
    raise RuntimeError("save failed")
try:
    save()
except RuntimeError:
    logging.getLogger("django.request").exception("Internal Server Error: /save/")
"""


@pytest.mark.parametrize("environment", SERVERS)
def test_a_logged_error_shows_no_password_or_secret(environment: str) -> None:
    variables = {"DJANGO_SETTINGS_MODULE": "cucumber.settings", **server(environment)}

    result = run_python(["-c", LOG_AN_ERROR], variables)

    assert result.returncode == 0, result.stderr
    assert "Internal Server Error: /save/" in result.stderr
    assert "save failed" in result.stderr
    assert SERVER["DB_PASSWORD"] not in result.stderr
    assert FAKE_KEY not in result.stderr


@pytest.mark.parametrize("environment", SERVERS)
def test_check_deploy_reports_nothing(environment: str) -> None:
    """AC7: the same check CI runs inside the image (design §4.3)."""
    result = run_python(
        ["manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        server(environment),
    )

    assert result.returncode == 0, result.stderr or result.stdout
