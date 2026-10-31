"""AC7-AC11: too many wrong passwords lock the email, kept in the database (§3.1, §7.2).

Time is moved by ageing the counted failures (helpers.age_failures).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest import mock

import psycopg
import pytest
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.http import HttpRequest
from django.test import Client, RequestFactory, override_settings

from cucumber.accounts import services
from cucumber.accounts.services import (
    ADDRESS_LIMIT,
    LOCK_AFTER_FAILURES,
    LOCK_WINDOW,
    client_address,
    lift_lock,
    locked_until,
    login_failed,
    login_lock,
    login_succeeded,
)
from cucumber.accounts.tests.helpers import (
    ADDRESS,
    LOCKED,
    OTHER_ADDRESS,
    WRONG,
    add_failures,
    age_failures,
    failures,
    failures_from,
    log_in,
    signed_in_as,
    text,
    without_values,
)
from cucumber.core.tests.rows import fetch_one, run

pytestmark = pytest.mark.django_db

GENE = "gene@example.com"
NOBODY = "nobody@example.com"
JUST_PAST = timedelta(seconds=1)


def test_the_limits_are_the_owners_answers() -> None:
    """Spec Q3 and design §7.2."""
    assert LOCK_AFTER_FAILURES == 5
    assert LOCK_WINDOW == timedelta(minutes=15)
    assert ADDRESS_LIMIT == 50


# ------------------------------------------------------------- the service
def test_an_email_locks_at_the_fifth_failure() -> None:
    for _ in range(LOCK_AFTER_FAILURES - 1):
        login_failed(GENE, ADDRESS)
    assert not login_lock(GENE, ADDRESS)

    login_failed(GENE, ADDRESS)

    assert login_lock(GENE, ADDRESS)


def test_failures_are_counted_by_email_key() -> None:
    login_failed(GENE, ADDRESS)

    assert failures(GENE) == 1


def test_the_lock_lifts_15_minutes_after_the_fifth_failure() -> None:
    for _ in range(LOCK_AFTER_FAILURES):
        login_failed(GENE, ADDRESS)

    age_failures(LOCK_WINDOW - timedelta(minutes=1))
    assert login_lock(GENE, ADDRESS)
    age_failures(timedelta(minutes=1) + JUST_PAST)
    assert not login_lock(GENE, ADDRESS)


def test_locked_until_is_15_minutes_after_the_fifth_failure() -> None:
    assert locked_until(GENE) is None
    for _ in range(LOCK_AFTER_FAILURES):
        login_failed(GENE, ADDRESS)
    fifth = fetch_one(
        "SELECT max(at) FROM accounts_login_failure WHERE email_key = %s", [GENE]
    )[0]
    assert isinstance(fifth, datetime)

    assert locked_until(GENE) == fifth + LOCK_WINDOW


def test_a_failure_without_an_address_still_counts_for_the_email() -> None:
    for _ in range(LOCK_AFTER_FAILURES):
        login_failed(GENE, None)

    assert login_lock(GENE, None)
    assert login_lock(GENE, ADDRESS)


def test_a_success_clears_that_emails_count_only() -> None:
    add_failures(GENE, 3)
    add_failures("pim@example.com", 3)

    login_succeeded(GENE)

    assert failures(GENE) == 0
    assert failures("pim@example.com") == 3


def test_the_password_is_never_given_to_the_lock() -> None:
    """The design's signature: email and address only (AC7)."""
    assert list(login_failed.__annotations__) == ["email", "address", "return"]


# ------------------------------------------------------------ AC9 address
def test_one_locked_email_does_not_lock_another_from_the_same_address() -> None:
    add_failures(GENE, LOCK_AFTER_FAILURES, ADDRESS)

    assert not login_lock("pim@example.com", ADDRESS)


def test_an_address_locks_at_50_failures_across_emails() -> None:
    for number in range(ADDRESS_LIMIT - 1):
        add_failures(f"guess{number}@example.com", 1, ADDRESS)
    assert not login_lock("fresh@example.com", ADDRESS)

    add_failures("guess-last@example.com", 1, ADDRESS)

    assert login_lock("fresh@example.com", ADDRESS)
    assert not login_lock("fresh@example.com", OTHER_ADDRESS)
    assert not login_lock("fresh@example.com", None)


def test_an_address_lock_lifts_by_itself_after_15_minutes() -> None:
    for number in range(ADDRESS_LIMIT):
        add_failures(f"guess{number}@example.com", 1, ADDRESS)

    age_failures(LOCK_WINDOW + JUST_PAST)

    assert not login_lock("fresh@example.com", ADDRESS)


def request_from(remote: str, cloudflare: str | None = None) -> HttpRequest:
    request = RequestFactory().post("/accounts/login/")
    request.META["REMOTE_ADDR"] = remote
    if cloudflare is not None:
        request.META["HTTP_CF_CONNECTING_IP"] = cloudflare
    return request


@override_settings(IS_SERVER=True)
@pytest.mark.parametrize("cloudflare", [OTHER_ADDRESS, "2001:db8::7"])
def test_on_a_server_the_address_is_the_one_cloudflare_saw(cloudflare: str) -> None:
    request = request_from("172.18.0.3", cloudflare)

    assert client_address(request) == cloudflare


@override_settings(IS_SERVER=True)
@pytest.mark.parametrize("cloudflare", [None, "", "not-an-address", "1.2.3"])
def test_on_a_server_a_missing_or_bad_header_means_no_address(
    cloudflare: str | None,
) -> None:
    """Not the tunnel's own address: that would lump everyone together."""
    request = request_from("172.18.0.3", cloudflare)

    assert client_address(request) is None


@override_settings(IS_SERVER=False)
def test_locally_the_cloudflare_header_is_ignored() -> None:
    """Anyone can send it locally, so it would let a test dodge the lock."""
    request = request_from(ADDRESS, OTHER_ADDRESS)

    assert client_address(request) == ADDRESS


# -------------------------------------------------------------- the page
def fail(times: int, email: str = GENE, address: str = ADDRESS) -> None:
    for _ in range(times):
        log_in(Client(), email, "not-the-password", address)


def test_five_wrong_passwords_lock_even_the_right_one(gene: User) -> None:
    fail(LOCK_AFTER_FAILURES)
    client = Client()

    response = log_in(client, GENE)

    assert response.status_code == 200
    assert LOCKED in text(response)
    assert WRONG not in text(response)
    assert signed_in_as(client) is None


def test_an_unknown_email_locks_exactly_the_same_way(gene: User) -> None:
    fail(LOCK_AFTER_FAILURES, GENE)
    fail(LOCK_AFTER_FAILURES, NOBODY)

    real = log_in(Client(), GENE)
    unknown = log_in(Client(), NOBODY)

    assert failures(NOBODY) == LOCK_AFTER_FAILURES
    assert real.status_code == unknown.status_code
    assert without_values(text(real)) == without_values(text(unknown))


def test_tries_while_locked_are_not_counted(gene: User) -> None:
    """Or someone who keeps retrying would stay locked for ever."""
    fail(LOCK_AFTER_FAILURES)

    fail(3)
    log_in(Client(), GENE)

    assert failures(GENE) == LOCK_AFTER_FAILURES


def test_a_locked_try_never_reaches_the_password_check(gene: User) -> None:
    """So a locked try can't reveal whether the password was right (§2.2)."""
    fail(LOCK_AFTER_FAILURES)

    with mock.patch.object(
        ModelBackend, "authenticate", autospec=True, return_value=None
    ) as check:
        log_in(Client(), GENE)

    check.assert_not_called()


def test_after_the_wait_the_right_password_works_and_the_count_restarts(
    gene: User,
) -> None:
    fail(LOCK_AFTER_FAILURES)
    age_failures(LOCK_WINDOW + JUST_PAST)
    client = Client()

    response = log_in(client, GENE)

    assert response.status_code == 302
    assert signed_in_as(client) == gene.pk
    assert failures(GENE) == 0


def test_others_on_the_lab_wifi_can_still_log_in(gene: User, pim: User) -> None:
    fail(LOCK_AFTER_FAILURES, GENE, ADDRESS)
    client = Client()

    response = log_in(client, "pim@example.com", address=ADDRESS)

    assert response.status_code == 302
    assert signed_in_as(client) == pim.pk


@override_settings(IS_SERVER=True)
def test_on_a_server_the_page_counts_the_address_cloudflare_saw(gene: User) -> None:
    Client().post(
        "/accounts/login/",
        {"username": GENE, "password": "not-the-password"},
        REMOTE_ADDR="172.18.0.3",
        HTTP_CF_CONNECTING_IP=OTHER_ADDRESS,
        secure=True,
    )

    assert failures_from(OTHER_ADDRESS) == 1
    assert failures_from("172.18.0.3") == 0


def test_a_locked_address_turns_away_every_email_on_the_page(pim: User) -> None:
    for number in range(ADDRESS_LIMIT):
        add_failures(f"guess{number}@example.com", 1, ADDRESS)
    client = Client()

    response = log_in(client, "pim@example.com", address=ADDRESS)

    assert LOCKED in text(response)
    assert signed_in_as(client) is None
    assert log_in(Client(), "pim@example.com", address=OTHER_ADDRESS).status_code == 302


def test_the_admin_can_lift_a_lock_early(owner: User, gene: User) -> None:
    fail(LOCK_AFTER_FAILURES)

    lift_lock(owner, gene)

    assert failures(GENE) == 0
    assert log_in(Client(), GENE).status_code == 302


# ------------------------------------------------------- AC10 one count
@pytest.fixture
def failure_from_another_connection(
    app_db: psycopg.Connection[tuple[object, ...]],
) -> Callable[[str], None]:
    """Count a failure through a second connection, as the app user."""

    def insert_failure(email: str) -> None:
        app_db.execute(
            "INSERT INTO accounts_login_failure (email_key, address, at)"
            " VALUES (%s, %s::inet, now())",
            [email, ADDRESS],
        )

    return insert_failure


def test_failures_written_by_another_connection_lock_this_one(
    failure_from_another_connection: Callable[[str], None],
) -> None:
    """Two gunicorn workers, or a restart, see the same count (AC10)."""
    for _ in range(LOCK_AFTER_FAILURES):
        failure_from_another_connection(GENE)

    assert login_lock(GENE, None)


def test_the_lock_keeps_nothing_in_process_memory() -> None:
    """No module-level dict, list or set a worker could count in (AC10)."""
    mutable = (dict, list, set)
    held = [
        name
        for name, value in vars(services).items()
        if isinstance(value, mutable)
        and not name.startswith("_")
        and not name.isupper()  # constants, e.g. an imported MESSAGES table
    ]

    assert held == []


# ------------------------------------------------------ G4 review (M3, M7)
def test_the_lock_uses_the_database_clock() -> None:
    """An app clock running ahead must not lift the lock early (G4 M7)."""
    for _ in range(LOCK_AFTER_FAILURES):
        login_failed(GENE, ADDRESS)
    ahead = datetime.now(UTC) + timedelta(hours=1)

    with mock.patch("django.utils.timezone.now", return_value=ahead):
        assert locked_until(GENE) is not None


def test_one_emails_tries_are_checked_one_at_a_time(
    app_db: psycopg.Connection[tuple[object, ...]], gene: User
) -> None:
    """Tries sent at the same moment can't all pass the check (G4 M3).

    Another connection holds GENE's try lock; this login must wait for it,
    so with a short lock_timeout it gives up instead of checking the password,
    and answers "Busy" (U0.10a AC15; it raised before the Busy page).
    """
    app_db.execute(
        "SELECT pg_advisory_lock(%s::integer, hashtext(%s))",
        [services.LOGIN_TRY_LOCK, GENE],
    )
    run("SET lock_timeout = '200ms'")
    try:
        response = log_in(Client(), GENE, "not-the-password")
    finally:
        run("RESET lock_timeout")

    assert response.status_code == 503
    assert failures(GENE) == 0


def test_another_emails_try_does_not_wait(
    app_db: psycopg.Connection[tuple[object, ...]], gene: User, pim: User
) -> None:
    app_db.execute(
        "SELECT pg_advisory_lock(%s::integer, hashtext(%s))",
        [services.LOGIN_TRY_LOCK, GENE],
    )
    run("SET lock_timeout = '200ms'")
    try:
        response = log_in(Client(), "pim@example.com")
    finally:
        run("RESET lock_timeout")

    assert response.status_code == 302
