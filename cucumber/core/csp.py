"""The Content Security Policy header on every answer (U0.10a §5, AC4).

Built once from `settings.SECURE_CSP`, written in Django 6's shape, so
moving to Django 6.2 LTS deletes this class and keeps the setting. Placed
straight after WhiteNoise. Left off with `DEBUG=1`, so Django's debug pages
(inline style and script) still work. G2 stub: the behaviour is built at G3.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

HEADER = "Content-Security-Policy"


class ContentSecurityPolicy:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError("U0.10a G3")
