"""Core pages. Kept thin: the checks live in services.py."""

from django.http import HttpRequest, HttpResponse

from cucumber.core.services import database_is_reachable  # noqa: F401  (G3 uses it)


def health(request: HttpRequest) -> HttpResponse:
    """`/health/`: "ok" when Cucumber and its database are up, 503 if not."""
    raise NotImplementedError("U0.3 G3")
