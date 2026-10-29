"""The Content Security Policy header on every answer (U0.10a §5, AC4).

Built once from `settings.SECURE_CSP`, written in Django 6's shape, so
moving to Django 6.2 LTS deletes this class and keeps the setting. Placed
straight after WhiteNoise. Left off with `DEBUG=1`, so Django's debug pages
(inline style and script) still work.
"""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

HEADER = "Content-Security-Policy"


def header_value(policy: dict[str, list[str]]) -> str:
    """`{"default-src": ["'self'"], ...}` as one header, in the setting's order."""
    return "; ".join(
        f"{directive} {' '.join(sources)}" for directive, sources in policy.items()
    )


class ContentSecurityPolicy:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.value = header_value(settings.SECURE_CSP)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not settings.DEBUG and HEADER not in response:
            response[HEADER] = self.value
        return response
