"""AC1, AC8, AC13: the settings the running app relies on (U0.4a design §1, §5, §7)."""

import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.staticfiles import finders
from waffle.utils import get_setting

WHITENOISE = "whitenoise.middleware.WhiteNoiseMiddleware"
SECURITY = "django.middleware.security.SecurityMiddleware"
DUMMY_CACHE = "django.core.cache.backends.dummy.DummyCache"
CSP = "cucumber.core.csp.ContentSecurityPolicy"
BUSY = "cucumber.core.busy.BusyAnswer"


# ------------------------------------------------- AC1: CSS from the app itself
def test_static_files_are_collected_into_staticfiles() -> None:
    assert "django.contrib.staticfiles" in settings.INSTALLED_APPS
    assert Path(str(settings.STATIC_ROOT)) == Path(settings.BASE_DIR) / "staticfiles"


def test_whitenoise_serves_them_straight_after_the_security_middleware() -> None:
    middleware = list(settings.MIDDLEWARE)

    assert middleware.index(WHITENOISE) == middleware.index(SECURITY) + 1


def test_the_security_policy_is_set_straight_after_whitenoise() -> None:
    """U0.10a AC4 (§5.2): every page Django makes carries it, error pages too."""
    middleware = list(settings.MIDDLEWARE)

    assert CSP in middleware
    assert middleware.index(CSP) == middleware.index(WHITENOISE) + 1


def test_a_view_stopped_by_a_limit_answers_busy() -> None:
    """U0.10a AC15 (§8.2): the middleware that turns a limit into 503 "Busy"."""
    assert BUSY in settings.MIDDLEWARE


def test_cucumbers_own_stylesheet_is_found() -> None:
    assert finders.find("core/cucumber.css") is not None


def test_collected_files_are_never_committed() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "staticfiles/core/cucumber.css"],
        cwd=settings.BASE_DIR,
        check=False,
    )
    assert ignored.returncode == 0


# ---------------------------------------------- AC8: the database connection
def test_a_save_waiting_on_a_lock_gives_up_after_five_seconds() -> None:
    database: dict[str, Any] = settings.DATABASES["default"]
    options = database.get("OPTIONS", {})

    assert "-c lock_timeout=5s" in options.get("options", "")


def test_a_stuck_query_and_an_idle_transaction_end_after_ten_seconds() -> None:
    """U0.10a AC15 (§8.1): the three limits, each from a named constant."""
    database: dict[str, Any] = settings.DATABASES["default"]
    options = database.get("OPTIONS", {}).get("options", "")

    assert options.split() == [
        "-c",
        "lock_timeout=5s",
        "-c",
        "statement_timeout=10s",
        "-c",
        "idle_in_transaction_session_timeout=10s",
    ]


def test_connections_are_reused_for_a_minute_and_checked_first() -> None:
    database: dict[str, Any] = settings.DATABASES["default"]

    assert database["CONN_MAX_AGE"] == 60
    assert database["CONN_HEALTH_CHECKS"] is True


# ------------------------------------------------------------- AC13: flags
def test_flags_are_never_cached_so_a_change_shows_on_the_next_page() -> None:
    cache_name = get_setting("CACHE_NAME")

    assert cache_name != "default"
    assert settings.CACHES[cache_name]["BACKEND"] == DUMMY_CACHE


def test_a_missing_flag_is_off_and_never_created() -> None:
    assert get_setting("CREATE_MISSING_FLAGS") is False
    assert get_setting("FLAG_DEFAULT") is False


def test_flags_can_not_be_switched_from_the_address_bar() -> None:
    """Waffle's override lets `?dwft_<name>=1` switch a flag; it must stay off."""
    assert get_setting("OVERRIDE") is False
