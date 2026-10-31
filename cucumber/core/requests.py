"""Small questions about a request, each answered in one place (U0.10a G4)."""

from django.conf import settings
from django.http import HttpRequest

PRODUCTION = "production"


def is_htmx(request: HttpRequest) -> bool:
    """True when htmx sent the request (its `HX-Request: true` header)."""
    return request.headers.get("HX-Request") == "true"


def is_production() -> bool:
    """True on the production server. Read each time, so tests can switch it."""
    return settings.ENVIRONMENT == PRODUCTION


def loggable(text: str) -> str:
    """`text` with each control character escaped (a newline becomes `\\n`),
    so a value from the request can't split a log line."""
    return "".join(
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in text
    )
