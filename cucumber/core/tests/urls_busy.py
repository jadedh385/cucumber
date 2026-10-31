"""Cucumber's addresses plus test-only pages that hit each limit (U0.10a AC15).

Used with `override_settings(ROOT_URLCONF=...)`, never by the running app.
Each page saves a row first, so a test can show nothing was saved, then
hits its limit, made short with `SET LOCAL` so the tests stay quick. The
values the app really runs with are checked with `SHOW` (test_busy.py).
Also a page that raises, and one refused by a service (AC17, AC21).
"""

import time
from collections.abc import Callable

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from django.urls import path

from cucumber.accounts.permissions import NotAllowed, Permission, allowed_for
from cucumber.urls import handler403, handler500
from cucumber.urls import urlpatterns as cucumber_urlpatterns

SAVED_GROUP = "saved-before-the-limit"
SHORT_LOCK = "SET LOCAL lock_timeout = '150ms'"
SHORT_STATEMENT = "SET LOCAL statement_timeout = '150ms'"
SHORT_IDLE = "SET LOCAL idle_in_transaction_session_timeout = '150ms'"
LONGER_THAN_SHORT_SECONDS = 0.6

LOCK = "/test-only/busy/lock/"
STATEMENT = "/test-only/busy/statement/"
IDLE = "/test-only/busy/idle/"
IN_MIDDLEWARE = "/test-only/busy/middleware/"
BROKEN = "/test-only/broken/"
SERVICE_REFUSED = "/test-only/service-refused/"
PLAIN_REFUSED = "/test-only/plain-refused/"
BROKEN_MESSAGE = "a bug in a test-only page"


def save_then(shorten: str, step: Callable[[], None]) -> None:
    """In one transaction: save a row, shorten one limit, run `step`."""
    with transaction.atomic():
        Group.objects.create(name=SAVED_GROUP)
        query(shorten)
        step()


def query(sql: str, params: list[int] | None = None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def sleep_in_the_database() -> None:
    query("SELECT pg_sleep(2)")


def pause_then_query() -> None:
    time.sleep(LONGER_THAN_SHORT_SECONDS)
    query("SELECT 1")


@allowed_for(Permission.OWN_ACCOUNT)
def wait_for_a_lock(request: HttpRequest) -> HttpResponse:
    """Waits on the row lock another connection holds (`?group=<id>`)."""
    group = int(request.GET["group"])
    save_then(
        SHORT_LOCK,
        lambda: query("SELECT 1 FROM auth_group WHERE id = %s FOR UPDATE", [group]),
    )
    return HttpResponse("not busy")


@allowed_for(Permission.OWN_ACCOUNT)
def run_too_long(request: HttpRequest) -> HttpResponse:
    save_then(SHORT_STATEMENT, sleep_in_the_database)
    return HttpResponse("not busy")


@allowed_for(Permission.OWN_ACCOUNT)
def pause_too_long(request: HttpRequest) -> HttpResponse:
    """Python pauses inside the transaction; the server ends the session."""
    save_then(SHORT_IDLE, pause_then_query)
    return HttpResponse("not busy")


@allowed_for(Permission.OWN_ACCOUNT)
def reached_after_the_middleware(request: HttpRequest) -> HttpResponse:
    return HttpResponse("not busy")


@allowed_for(Permission.OWN_ACCOUNT)
def broken(request: HttpRequest) -> HttpResponse:
    raise RuntimeError(BROKEN_MESSAGE)


@allowed_for(Permission.OWN_ACCOUNT)
def refused_by_a_service(request: HttpRequest) -> HttpResponse:
    """As a service's `require()` would refuse after the page check passed."""
    raise NotAllowed("account_not_active")


@allowed_for(Permission.OWN_ACCOUNT)
def refused_plainly(request: HttpRequest) -> HttpResponse:
    """As `signed_in_user` refuses: a plain PermissionDenied, no rule."""
    raise PermissionDenied


class SlowMiddleware:
    """Hits `statement_timeout` before the view, where `process_exception`
    can't see it: the 500 handler's fallback must answer "Busy" (§8.2)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == IN_MIDDLEWARE:
            save_then(SHORT_STATEMENT, sleep_in_the_database)
        return self.get_response(request)


urlpatterns = [
    *cucumber_urlpatterns,
    path(LOCK.lstrip("/"), wait_for_a_lock),
    path(STATEMENT.lstrip("/"), run_too_long),
    path(IDLE.lstrip("/"), pause_too_long),
    path(IN_MIDDLEWARE.lstrip("/"), reached_after_the_middleware),
    path(BROKEN.lstrip("/"), broken),
    path(SERVICE_REFUSED.lstrip("/"), refused_by_a_service),
    path(PLAIN_REFUSED.lstrip("/"), refused_plainly),
]

__all__ = ["handler403", "handler500", "urlpatterns"]
