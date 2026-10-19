"""AC12, AC13, AC15, AC16: how long a login lasts, and the cookie (§4, §5, §7.5)."""

import time
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from cucumber.accounts.services import SESSION_MAX_AGE
from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    add_failures,
    end_idle_sessions_now,
    failures,
    htmx_headers,
    log_in,
    redirect_target,
    set_login_age,
    signed_in_as,
)
from cucumber.core.tests.rows import run

pytestmark = pytest.mark.django_db

SEVEN_DAYS = 7 * 24 * 60 * 60
ONE_MINUTE = timedelta(minutes=1)


def goes_to_login(client: Client) -> bool:
    response = client.get(HOME)
    return response.status_code == 302 and redirect_target(response)[0] == LOGIN


# --------------------------------------------------------------- settings
def test_sessions_last_7_days_and_each_page_restarts_them() -> None:
    assert settings.SESSION_COOKIE_AGE == SEVEN_DAYS
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


def test_the_absolute_limit_is_30_days() -> None:
    assert timedelta(days=30) == SESSION_MAX_AGE


def test_the_cookie_rules_are_set_explicitly() -> None:
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_login_settings_name_cucumbers_pages() -> None:
    assert settings.LOGIN_URL == "login"
    assert settings.LOGIN_REDIRECT_URL == "home"
    assert settings.LOGOUT_REDIRECT_URL == "login"


def test_the_account_middleware_runs_in_the_designed_order() -> None:
    """After Django's authentication and messages; limit, login, change (§5)."""
    middleware = settings.MIDDLEWARE
    ours = [
        "cucumber.accounts.middleware.SessionLimit",
        "cucumber.accounts.middleware.LoginRequired",
        "cucumber.accounts.middleware.PasswordChangeDue",
    ]
    assert all(name in middleware for name in ours), "not in settings.MIDDLEWARE"

    positions = [middleware.index(name) for name in ours]
    authentication = middleware.index(
        "django.contrib.auth.middleware.AuthenticationMiddleware"
    )
    messages = middleware.index("django.contrib.messages.middleware.MessageMiddleware")
    assert positions == sorted(positions)
    assert positions[0] > max(authentication, messages)


# ------------------------------------------------------------- AC12 idle
def test_a_session_ends_after_7_days_without_a_page(gene_client: Client) -> None:
    end_idle_sessions_now()

    assert goes_to_login(gene_client)


def test_each_page_pushes_the_7_days_forward(gene_client: Client) -> None:
    run("UPDATE django_session SET expire_date = now() + interval '1 day'")

    assert gene_client.get(HOME).status_code == 200

    expiry = Session.objects.get().expire_date
    assert expiry > timezone.now() + timedelta(days=6)


# ---------------------------------------------------------- AC13 30 days
def test_a_login_is_stamped_in_whole_seconds(gene_client: Client) -> None:
    login_at = gene_client.session["login_at"]

    assert isinstance(login_at, int)
    assert abs(login_at - time.time()) < 60


def test_a_session_used_daily_still_works_on_day_29(gene_client: Client) -> None:
    set_login_age(gene_client, timedelta(days=29))

    assert gene_client.get(HOME).status_code == 200


def test_a_session_used_daily_still_ends_30_days_after_login(
    gene_client: Client,
) -> None:
    set_login_age(gene_client, SESSION_MAX_AGE + ONE_MINUTE)

    assert goes_to_login(gene_client)
    assert signed_in_as(gene_client) is None


@pytest.mark.parametrize("stamp", [None, "yesterday", 1.5, [1]])
def test_a_session_with_a_missing_or_broken_stamp_ends(
    gene_client: Client, stamp: object
) -> None:
    """Sessions from before U0.5, or anything odd, count as ended (§5)."""
    session = gene_client.session
    if stamp is None:
        del session["login_at"]
    else:
        session["login_at"] = stamp
    session.save()

    assert goes_to_login(gene_client)


def test_an_htmx_request_at_30_days_gets_401_and_hx_redirect(
    gene_client: Client,
) -> None:
    set_login_age(gene_client, SESSION_MAX_AGE + ONE_MINUTE)

    response = gene_client.post("/staff/", headers=htmx_headers())

    assert response.status_code == 401
    assert redirect_target(response)[0] == LOGIN


# ------------------------------------------------------- AC15 the cookie
def test_logging_in_gives_a_new_session_id(gene: User) -> None:
    client = Client()
    planted = client.session
    planted["planted"] = True
    planted.save()
    before = planted.session_key

    log_in(client, "gene@example.com")

    assert client.session.session_key != before
    assert not Session.objects.filter(session_key=before).exists()


def test_the_session_cookie_is_hidden_from_scripts_and_other_sites(
    gene: User,
) -> None:
    response = log_in(Client(), "gene@example.com")

    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"


# --------------------------------------------- AC16 tidy up at each login
def test_a_login_removes_ended_sessions_and_day_old_failures(gene: User) -> None:
    stale = Client()
    log_in(stale, "gene@example.com")
    end_idle_sessions_now()
    add_failures("old@example.com", 2)
    run("UPDATE accounts_login_failure SET at = now() - interval '25 hours'")
    add_failures("recent@example.com", 2)

    log_in(Client(), "gene@example.com")

    assert Session.objects.filter(expire_date__lt=timezone.now()).count() == 0
    assert failures("old@example.com") == 0
    assert failures("recent@example.com") == 2


def test_a_failed_login_also_removes_day_old_failures() -> None:
    """Without a good login the table would only grow (G4 M4)."""
    add_failures("old@example.com", 2)
    run("UPDATE accounts_login_failure SET at = now() - interval '25 hours'")
    add_failures("recent@example.com", 2)

    log_in(Client(), "nobody@example.com", "not-the-password")

    assert failures("old@example.com") == 0
    assert failures("recent@example.com") == 2
