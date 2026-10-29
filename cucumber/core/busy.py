"""The server's own limits, and the "Busy" page when one is hit (U0.10a §8).

Each limit cancels the statement or ends the session, so the view's
transaction rolls back. The person sees 503 "Busy, please try again." and
the log gets one line.
"""

import logging
from collections.abc import Callable

from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

# PostgreSQL error code → the limit's setting name (design §8.2). Django
# wraps psycopg's error (an OperationalError for the first two, an
# InternalError for 25P03); the code is psycopg's `sqlstate` on `__cause__`.
LIMITS = {
    "55P03": "lock_timeout",
    "57014": "statement_timeout",
    "25P03": "idle_in_transaction_session_timeout",
}

# The request attribute that marks a request answered "Busy", so the log
# filter drops Django's own line for it (§9.2).
BUSY_MARK = "cucumber_busy"


def busy_limit(error: BaseException) -> str | None:
    """The limit that stopped this request, by PostgreSQL error code, or None.

    Walks `__cause__` (Django wraps psycopg's error; the code is psycopg's
    `sqlstate`).
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        limit = LIMITS.get(getattr(current, "sqlstate", None) or "")
        if limit:
            return limit
        current = current.__cause__
    return None


def mark_busy(request: HttpRequest, limit: str) -> None:
    """Mark `request` as answered "Busy" because of `limit`."""
    setattr(request, BUSY_MARK, limit)


def is_marked_busy(request: object) -> bool:
    """True when `request` was answered "Busy" (any object: log records carry one)."""
    return bool(getattr(request, BUSY_MARK, None))


def busy_page(request: HttpRequest, limit: str) -> HttpResponse:
    """Log the one `busy limit=…` line, mark the request, answer 503 "Busy".

    Closes Django's connection when the server ended the session (25P03).
    """
    if limit == LIMITS["25P03"]:
        connection.close()
    user = getattr(request, "user", None)
    logger.warning(
        "busy limit=%s account=%s path=%s",
        limit,
        getattr(user, "pk", None),
        request.path,
    )
    mark_busy(request, limit)
    return render(request, "503.html", status=503)


class BusyAnswer:
    """Middleware: a view stopped by one of the limits answers 503 "Busy"."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> HttpResponse | None:
        limit = busy_limit(exception)
        if limit is None:
            return None
        return busy_page(request, limit)
