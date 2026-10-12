"""Core pages. Kept thin: the checks live in services.py."""

from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from cucumber.core.services import database_is_reachable


@never_cache
@require_safe
def health(request: HttpRequest) -> HttpResponse:
    """`/health/`: "ok" when Cucumber and its database are up, 503 if not.

    Answers GET and HEAD (uptime monitors often send HEAD); needs no login.
    Never cached, so a proxy can't hide an outage behind an old "ok".
    """
    if database_is_reachable(connection):
        return HttpResponse("ok", content_type="text/plain")
    return HttpResponse("database unavailable", status=503, content_type="text/plain")
