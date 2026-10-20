"""Core pages. Kept thin: the checks live in services.py."""

from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.http import require_safe

from cucumber.core.services import database_is_reachable


@login_not_required
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


@requires_csrf_token
def server_error(request: HttpRequest) -> HttpResponse:
    """The error page, rendered with the request so the banner shows (AC9).

    Django's own 500 view renders without the request, so context
    processors, and with them the "Practice data" banner, never run.
    """
    return render(request, "500.html", status=500)


@requires_csrf_token
def permission_denied(request: HttpRequest, exception: Exception) -> HttpResponse:
    """The 403 page: "You don't have access to this page." (U0.6 AC10)."""
    return render(request, "403.html", status=403)
