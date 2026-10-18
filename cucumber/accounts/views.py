"""Account pages (design §6). Thin: read the form, call a service, show the result."""

from django.http import HttpRequest, HttpResponse

from cucumber.accounts.services import NOT_BUILT


def home(request: HttpRequest) -> HttpResponse:
    """`/`: who is signed in; a link to Staff for the Admin (AC18, AC21)."""
    raise NotImplementedError(NOT_BUILT)


def password(request: HttpRequest) -> HttpResponse:
    """Change your own password; also the forced change (AC25, AC26)."""
    raise NotImplementedError(NOT_BUILT)


def staff_list(request: HttpRequest) -> HttpResponse:
    raise NotImplementedError(NOT_BUILT)


def staff_new(request: HttpRequest) -> HttpResponse:
    """Add an account; the POST answers with its temporary password (§6.2)."""
    raise NotImplementedError(NOT_BUILT)


def staff_detail(request: HttpRequest, account_id: int) -> HttpResponse:
    raise NotImplementedError(NOT_BUILT)


def staff_deactivate(request: HttpRequest, account_id: int) -> HttpResponse:
    raise NotImplementedError(NOT_BUILT)


def staff_reactivate(request: HttpRequest, account_id: int) -> HttpResponse:
    raise NotImplementedError(NOT_BUILT)


def staff_new_password(request: HttpRequest, account_id: int) -> HttpResponse:
    """Answers with the new temporary password (§6.2)."""
    raise NotImplementedError(NOT_BUILT)


def staff_unlock(request: HttpRequest, account_id: int) -> HttpResponse:
    raise NotImplementedError(NOT_BUILT)
