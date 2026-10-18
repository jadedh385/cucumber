"""AC30: one plain log line per account event; never a password, session id
or the email typed into a failed login (design §8)."""

import logging
from collections.abc import Callable

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.services import (
    add_account,
    deactivate,
    give_new_password,
    lift_lock,
    reactivate,
)
from cucumber.accounts.tests.helpers import (
    ADDRESS,
    LOGOUT,
    NEW_PASSWORD,
    PASSWORD,
    PASSWORD_PAGE,
    log_in,
    mark_change_due,
    signed_in,
)

pytestmark = pytest.mark.django_db

LOGGER = "cucumber.accounts"
Lines = Callable[[], list[str]]


def is_accounts(name: str) -> bool:
    """`cucumber.accounts` or one of its modules' loggers (`getLogger(__name__)`)."""
    return name == LOGGER or name.startswith(f"{LOGGER}.")


@pytest.fixture
def lines(caplog: pytest.LogCaptureFixture) -> Lines:
    caplog.set_level(logging.INFO, logger=LOGGER)

    def account_lines() -> list[str]:
        return [r.getMessage() for r in caplog.records if is_accounts(r.name)]

    return account_lines


def test_the_cucumber_logger_writes_info_lines() -> None:
    loggers = settings.LOGGING["loggers"]
    assert isinstance(loggers, dict)

    assert loggers["cucumber"]["level"] == "INFO"
    assert loggers["django"]["level"] == "WARNING"


# ------------------------------------------------------------- logging in
def test_a_login(gene: User, lines: Lines) -> None:
    log_in(Client(), "gene@example.com")

    assert lines() == [f"login ok account={gene.pk}"]


def test_a_failed_login_names_the_account_not_the_email(
    gene: User, lines: Lines
) -> None:
    log_in(Client(), "Gene@Example.com", "not-the-password")

    assert lines() == [f"login failed account={gene.pk} address={ADDRESS}"]


def test_a_failed_login_for_no_account(db: None, lines: Lines) -> None:
    """People sometimes type their password into the email box."""
    log_in(Client(), "my-secret-pw-Typed-Here", "x")

    assert lines() == [f"login failed account=unknown address={ADDRESS}"]
    assert "my-secret-pw" not in "\n".join(lines())


def test_a_locked_try(gene: User, lines: Lines) -> None:
    for _ in range(5):
        log_in(Client(), "gene@example.com", "not-the-password")

    log_in(Client(), "gene@example.com")

    assert lines()[-1] == f"login locked account={gene.pk} address={ADDRESS}"


def test_a_locked_try_for_no_account(db: None, lines: Lines) -> None:
    for _ in range(5):
        log_in(Client(), "nobody@example.com", "x")

    log_in(Client(), "nobody@example.com", "x")

    assert lines()[-1] == f"login locked account=unknown address={ADDRESS}"


def test_a_logout(gene: User, lines: Lines) -> None:
    client = signed_in(gene)

    client.post(LOGOUT)

    assert lines()[-1] == f"logout account={gene.pk}"


# ------------------------------------------------------- account changes
def test_account_changes_name_the_account_and_who_did_it(
    owner: User, gene: User, lines: Lines
) -> None:
    mali = add_account(owner, "Mali", "mali@example.com").account
    deactivate(owner, gene)
    reactivate(owner, gene)
    give_new_password(owner, gene)
    lift_lock(owner, gene)

    assert lines() == [
        f"account added account={mali.pk} by={owner.pk}",
        f"account deactivated account={gene.pk} by={owner.pk}",
        f"account reactivated account={gene.pk} by={owner.pk}",
        f"password given account={gene.pk} by={owner.pk}",
        f"lock lifted account={gene.pk} by={owner.pk}",
    ]


def test_choosing_a_password(gene: User, lines: Lines) -> None:
    mark_change_due(gene)
    client = signed_in(gene)

    client.post(
        PASSWORD_PAGE,
        {
            "old_password": PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert lines()[-1] == f"password chosen account={gene.pk}"


# ------------------------------------------------------------ never kept
def test_no_line_ever_holds_a_password_or_session_id(
    owner: User, gene: User, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = signed_in(gene)
    session_key = client.session.session_key
    log_in(Client(), "gene@example.com", "wrong-guess-123")
    temporary = give_new_password(owner, gene)

    everything = caplog.text
    assert session_key and session_key not in everything
    for secret in [PASSWORD, "wrong-guess-123", temporary]:
        assert secret not in everything
