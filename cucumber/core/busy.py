"""The server's own limits, and the "Busy" page when one is hit (U0.10a §8).

Each limit cancels the statement or ends the session, so the view's
transaction rolls back. The person sees 503 "Busy, please try again." and
the log gets one line. G2 stub: the behaviour is built at G3.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

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
    raise NotImplementedError("U0.10a G3")


def mark_busy(request: HttpRequest, limit: str) -> None:
    """Mark `request` as answered "Busy" because of `limit`."""
    raise NotImplementedError("U0.10a G3")


def is_marked_busy(request: object) -> bool:
    """True when `request` was answered "Busy" (any object: log records carry one)."""
    raise NotImplementedError("U0.10a G3")


def busy_page(request: HttpRequest, limit: str) -> HttpResponse:
    """Log the one `busy limit=…` line, mark the request, answer 503 "Busy".

    Closes Django's connection when the server ended the session (25P03).
    """
    raise NotImplementedError("U0.10a G3")


class BusyAnswer:
    """Middleware: a view stopped by one of the limits answers 503 "Busy"."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> HttpResponse | None:
        raise NotImplementedError("U0.10a G3")
