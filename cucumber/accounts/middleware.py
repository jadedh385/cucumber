"""Login needed everywhere, the 30-day limit and the forced change (design §5).

Listed in settings.MIDDLEWARE after Django's authentication and messages,
in this order: SessionLimit, LoginRequired, PasswordChangeDue.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from cucumber.accounts.services import NOT_BUILT

GetResponse = Callable[[HttpRequest], HttpResponse]


class SessionLimit:
    """Log out a session 30 days after its login (AC13)."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError(NOT_BUILT)


class LoginRequired:
    """Every page needs a login; HTMX gets 401 + HX-Redirect (AC17-AC20)."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError(NOT_BUILT)


class PasswordChangeDue:
    """Send someone with a temporary password to change it first (AC25)."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError(NOT_BUILT)
