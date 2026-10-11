"""Core pages. Kept thin: the checks live in services.py."""

from django.http import HttpRequest, HttpResponse


def health(request: HttpRequest) -> HttpResponse:
    """`/health/`: "ok" when Cucumber and its database are up, 503 if not."""
    raise NotImplementedError("U0.3 G3")
