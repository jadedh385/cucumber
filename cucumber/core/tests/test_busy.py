"""U0.10a AC15: the server's own limits, and "Busy" when one is hit (§8).

Each limit is hit through a test-only page (urls_busy.py) that saves a row
first, under `transactional_db` so a save would really be committed (and
the idle limit can end the session). The client is made with
`raise_request_exception=False`: the test client otherwise re-raises an
error the 500 handler has already answered.
"""

import threading
from collections.abc import Iterator
from typing import TYPE_CHECKING

import psycopg
import pytest
from django.contrib.auth.models import Group, User
from django.db import DatabaseError, InternalError, OperationalError, connection
from django.test import Client, modify_settings, override_settings

from cucumber.accounts.tests.helpers import PASSWORD, log_in
from cucumber.core import busy
from cucumber.core.tests import urls_busy
from cucumber.core.tests.logs import Logged
from cucumber.core.tests.stock import make_staff

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

pytestmark = pytest.mark.django_db(transaction=True)

URLCONF = "cucumber.core.tests.urls_busy"
FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"
BUSY_WORDS = "Busy, please try again."
# If the lock timeout is missing, the lock is let go after this long, so the
# test fails instead of hanging.
SAFETY_RELEASE_SECONDS = 15


@pytest.fixture(autouse=True)
def busy_pages() -> Iterator[None]:
    with override_settings(ROOT_URLCONF=URLCONF, PASSWORD_HASHERS=[FAST_HASHER]):
        yield


@pytest.fixture
def gene() -> User:
    return make_staff("gene", "tech", PASSWORD)


@pytest.fixture
def client(gene: User) -> Client:
    """Gene, signed in; errors answered by the 500 handler come back as pages."""
    client = Client(raise_request_exception=False)
    assert log_in(client, gene.username).status_code == 302
    return client


@pytest.fixture
def other_connection() -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A second connection to the test database, as another save would be."""
    settings = connection.settings_dict
    other = psycopg.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"],
        port=settings["PORT"],
    )
    try:
        yield other
    finally:
        other.rollback()
        other.close()


def busy_lines(logged: Logged) -> list[str]:
    return [line for line in logged.cucumber() if line.startswith("busy ")]


def nothing_saved() -> bool:
    return not Group.objects.filter(name=urls_busy.SAVED_GROUP).exists()


def backend_pid() -> int:
    """Which server session Django's connection is on."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def template_names(response: "TestResponse") -> list[str]:
    return [template.name or "" for template in response.templates]


def assert_busy(
    response: "TestResponse", logged: Logged, limit: str, gene: User
) -> None:
    """503, the Busy words, one `busy` line, no Django line, nothing saved."""
    assert response.status_code == 503
    assert BUSY_WORDS in response.content.decode()
    assert busy_lines(logged) == [
        f"busy limit={limit} account={gene.pk} path={response.wsgi_request.path}"
    ]
    assert logged.django() == [], "Django's own line for a busy request is dropped"
    assert nothing_saved()


# ------------------------------------------------------------- the values
@pytest.mark.parametrize(
    ("show", "value"),
    [
        ("SHOW lock_timeout", "5s"),
        ("SHOW statement_timeout", "10s"),
        ("SHOW idle_in_transaction_session_timeout", "10s"),
    ],
)
def test_the_apps_connection_has_each_limit(show: str, value: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(show)
        row = cursor.fetchone()

    assert row == (value,)


# --------------------------------------------------- telling the limits apart
@pytest.mark.parametrize(
    ("error", "limit"),
    [
        (psycopg.errors.LockNotAvailable, "lock_timeout"),
        (psycopg.errors.QueryCanceled, "statement_timeout"),
        (
            psycopg.errors.IdleInTransactionSessionTimeout,
            "idle_in_transaction_session_timeout",
        ),
    ],
)
def test_each_limit_is_named_by_its_postgresql_code(
    error: type[psycopg.Error], limit: str
) -> None:
    """Django wraps psycopg's error; the code is on `__cause__` (§8.2)."""
    wrapped = OperationalError("stopped")
    wrapped.__cause__ = error("stopped")

    assert busy.busy_limit(wrapped) == limit


def test_the_code_is_found_however_deep_it_is_wrapped() -> None:
    inner = InternalError("stopped")
    inner.__cause__ = psycopg.errors.IdleInTransactionSessionTimeout("stopped")
    outer = RuntimeError("while saving")
    outer.__cause__ = inner

    assert busy.busy_limit(outer) == "idle_in_transaction_session_timeout"


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("a bug"),
        DatabaseError("no cause"),
        psycopg.errors.UniqueViolation("taken"),
        psycopg.errors.DeadlockDetected("deadlock"),
        psycopg.errors.AdminShutdown("server stopping"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_any_other_error_is_no_limit(error: BaseException) -> None:
    wrapped = OperationalError("failed")
    wrapped.__cause__ = error

    assert busy.busy_limit(error) is None
    assert busy.busy_limit(wrapped) is None


def test_the_idle_limit_arrives_with_its_code_as_an_internal_error() -> None:
    """G2 finding (§21): PostgreSQL 17 + psycopg 3 send 25P03 with its code,
    and Django wraps it as InternalError, not OperationalError."""
    with pytest.raises(InternalError) as stopped:
        urls_busy.save_then(urls_busy.SHORT_IDLE, urls_busy.pause_then_query)

    cause = stopped.value.__cause__
    assert isinstance(cause, psycopg.errors.IdleInTransactionSessionTimeout)
    assert cause.sqlstate == "25P03"
    assert nothing_saved()


# ------------------------------------------------- a view stopped by a limit
def test_a_save_waiting_on_a_lock_answers_busy(
    client: Client,
    gene: User,
    logged: Logged,
    other_connection: psycopg.Connection[tuple[object, ...]],
) -> None:
    locked = Group.objects.create(name="locked by another save")
    other_connection.execute(
        "SELECT 1 FROM auth_group WHERE id = %s FOR UPDATE", (locked.pk,)
    )
    safety = threading.Timer(SAFETY_RELEASE_SECONDS, other_connection.rollback)
    safety.start()
    try:
        response = client.get(urls_busy.LOCK, {"group": locked.pk})
    finally:
        safety.cancel()

    assert_busy(response, logged, "lock_timeout", gene)
    assert client.get("/").status_code == 200, "the next page works"


def test_a_stuck_query_answers_busy(client: Client, gene: User, logged: Logged) -> None:
    response = client.get(urls_busy.STATEMENT)

    assert_busy(response, logged, "statement_timeout", gene)
    assert client.get("/").status_code == 200, "the next page works"


def test_a_transaction_left_idle_answers_busy(
    client: Client, gene: User, logged: Logged
) -> None:
    response = client.get(urls_busy.IDLE)

    assert_busy(response, logged, "idle_in_transaction_session_timeout", gene)


def test_after_the_idle_limit_the_next_page_gets_a_fresh_connection(
    client: Client,
) -> None:
    """The server ended the session; Django must not reuse the dead one."""
    ended = backend_pid()

    client.get(urls_busy.IDLE)

    assert client.get("/").status_code == 200
    assert backend_pid() != ended


def test_the_busy_page_has_no_menu_and_does_not_say_who_is_signed_in(
    client: Client,
) -> None:
    """It must not touch the database (§7.8)."""
    response = client.get(urls_busy.STATEMENT)
    html = response.content.decode()

    assert "kit/bare.html" in template_names(response)
    assert "kit/menu.html" not in template_names(response)
    assert "Signed in as" not in html
    assert 'href="/"' in html, "the Busy page offers Home"


def test_busy_is_marked_on_the_request_for_the_log_filter(client: Client) -> None:
    response = client.get(urls_busy.STATEMENT)

    assert busy.is_marked_busy(response.wsgi_request)
    assert getattr(response.wsgi_request, busy.BUSY_MARK) == "statement_timeout"


# ------------------------------------------- a limit hit outside the view
@modify_settings(MIDDLEWARE={"append": "cucumber.core.tests.urls_busy.SlowMiddleware"})
def test_a_limit_hit_in_a_middleware_also_answers_busy(
    gene: User, logged: Logged
) -> None:
    """`process_exception` sees view errors only; the 500 handler falls back.

    Its own client: a client keeps the middleware it loaded first."""
    client = Client(raise_request_exception=False)
    assert log_in(client, gene.username).status_code == 302

    response = client.get(urls_busy.IN_MIDDLEWARE)

    assert_busy(response, logged, "statement_timeout", gene)


def test_any_other_error_is_still_a_500(client: Client, logged: Logged) -> None:
    response = client.get(urls_busy.BROKEN)

    assert response.status_code == 500
    assert busy_lines(logged) == []
