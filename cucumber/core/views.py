"""Core pages. Kept thin: the checks live in services.py."""

import logging
import sys
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import requires_csrf_token
from django.views.decorators.http import require_safe

from cucumber.core.busy import busy_limit, busy_page
from cucumber.core.refusals import PageRefused
from cucumber.core.services import database_is_reachable

logger = logging.getLogger(__name__)

# Tells `requests.js` an HTMX form met the CSRF page (U0.10a §4.3).
TROUBLE_HEADER = "Cucumber-Trouble"


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
    processors, and with them the "Practice data" banner, never run. A
    database limit hit outside the view (a middleware's query, the session
    save) answers "Busy" instead (U0.10a §8.2). The page is bare: it never
    reads the database.
    """
    error = sys.exc_info()[1]
    limit = busy_limit(error) if error else None
    if limit:
        return busy_page(request, limit)
    return render(request, "500.html", status=500)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """`CSRF_FAILURE_VIEW`: "This page was open too long." and Reload (AC16).

    403. Reload goes to the same-site Referer, else Home; an HTMX request also
    gets `Cucumber-Trouble: stale-page`. Django's `reason` is never shown or
    logged here: Django's own `django.security.csrf` line is the one line.
    """
    response = render(
        request, "csrf.html", {"reload_to": same_site_path(request)}, status=403
    )
    if request.headers.get("HX-Request") == "true":
        response[TROUBLE_HEADER] = "stale-page"
    return response


def same_site_path(request: HttpRequest) -> str:
    """The Referer's path when it is this site, else Home ("/").

    Not the form's own address: Staff buttons are POST only (§9.1).
    """
    referer = request.headers.get("Referer", "")
    is_this_site = url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    path = urlsplit(referer).path if is_this_site else ""
    if path.startswith("/") and url_has_allowed_host_and_scheme(path, None):
        return path
    return "/"


@requires_csrf_token
def permission_denied(request: HttpRequest, exception: Exception) -> HttpResponse:
    """The 403 page: "You don't have access to this page." (U0.6 AC10).

    Every 403 has one Cucumber line: RoleRequired writes its own; any other
    refusal is written here, with a service's rule or `rule=none`.
    """
    if not isinstance(exception, PageRefused):
        logger.info(
            "page refused account=%s rule=%s path=%s",
            getattr(request.user, "pk", None),
            getattr(exception, "rule", "none"),
            request.path,
        )
    return render(request, "403.html", status=403)
