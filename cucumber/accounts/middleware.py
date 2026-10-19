"""Login needed everywhere, the 30-day limit and the forced change (design §5).

Listed in settings.MIDDLEWARE after Django's authentication and messages,
in this order: SessionLimit, LoginRequired, PasswordChangeDue.

An HTMX request (a form saving in the background) never gets a redirect:
htmx would swap the login page into the form. It gets 401 with
`HX-Redirect`, so htmx loads the whole page instead (AC19).
"""

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.contrib.auth import logout
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import url_has_allowed_host_and_scheme

from cucumber.accounts.services import SESSION_MAX_AGE, change_is_due

GetResponse = Callable[[HttpRequest], HttpResponse]

# Stored in the session at login, as whole seconds (§5, accounts/signals.py).
LOGIN_AT = "login_at"

# Pages someone with a change due may still open (§5).
OPEN_DURING_CHANGE = frozenset({"password", "logout", "login", "health"})


def is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def htmx_page(request: HttpRequest) -> str | None:
    """The page htmx sent this request from, if it is on this site."""
    current = request.headers.get("HX-Current-URL", "")
    if not url_has_allowed_host_and_scheme(
        current, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return None
    parts = urlsplit(current)
    return urlunsplit(("", "", parts.path or "/", parts.query, ""))


def htmx_redirect(request: HttpRequest, to: str) -> HttpResponse:
    """401 + HX-Redirect to `to`, with the page the person was on as `next`."""
    page = htmx_page(request)
    location = f"{to}?{urlencode({'next': page})}" if page else to
    response = HttpResponse(status=401)
    response["HX-Redirect"] = location
    return response


def login_is_too_old(login_at: object) -> bool:
    """True when the stamp is missing, broken or older than 30 days."""
    if type(login_at) is not int:
        return True
    return time.time() - login_at > SESSION_MAX_AGE.total_seconds()


class SessionLimit:
    """Log out a session 30 days after its login (AC13).

    The next middleware then treats the request as "not signed in".
    """

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated and login_is_too_old(
            request.session.get(LOGIN_AT)
        ):
            logout(request)
        return self.get_response(request)


class LoginRequired(LoginRequiredMiddleware):
    """Every page needs a login; HTMX gets 401 + HX-Redirect (AC17-AC20).

    Django's own middleware, except for HTMX. Open pages are marked
    `@login_not_required` (the login page and /health/).
    """

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponseBase | None:
        needs_login = getattr(view_func, "login_required", True)
        if is_htmx(request) and needs_login and not request.user.is_authenticated:
            return htmx_redirect(request, resolve_url(self.get_login_url(view_func)))
        response: HttpResponseBase | None = super().process_view(
            request, view_func, view_args, view_kwargs
        )
        return response


class PasswordChangeDue(MiddlewareMixin):
    """Send someone with a temporary password to change it first (AC25).

    Reads the table on every page, so a mark added after login counts at once.
    """

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        if not request.user.is_authenticated:
            return None
        match = request.resolver_match
        if match is not None and match.url_name in OPEN_DURING_CHANGE:
            return None
        if not change_is_due(request.user):
            return None
        password_page = reverse("password")
        if is_htmx(request):
            return htmx_redirect(request, password_page)
        return HttpResponseRedirect(password_page)
