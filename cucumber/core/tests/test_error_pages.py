"""U0.10a AC21: the error pages, on the kit (§7.8, §14).

403 and 404 are on `base.html`, with the menu when someone is signed in.
500 (and Busy, test_busy.py) are on `kit/bare.html`: no menu, no "Signed in
as", and no database at all, so the page still shows when the database is
what broke. Each offers Home.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import OperationalError, connection
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import get_resolver
from pytest_django import DjangoAssertNumQueries

from cucumber.accounts.tests.helpers import PASSWORD, log_in
from cucumber.core.tests import urls_busy
from cucumber.core.tests.stock import make_staff

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

pytestmark = pytest.mark.django_db

FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"
HOME_LINK = 'href="/"'
NO_ACCESS = "You don't have access to this page."
NOT_FOUND = [
    "Page not found",
    "There is no page at this address. Check the link, or go home.",
]
WENT_WRONG = [
    "Something went wrong",
    "Nothing was saved. Please try again in a moment. If it keeps happening,"
    " tell the Owner what you were doing.",
]


@pytest.fixture(autouse=True)
def test_pages() -> Iterator[None]:
    with override_settings(
        ROOT_URLCONF=urls_busy.__name__, PASSWORD_HASHERS=[FAST_HASHER]
    ):
        yield


@pytest.fixture
def gene_client() -> Client:
    """Gene, signed in; a 500 comes back as the page, not re-raised."""
    client = Client(raise_request_exception=False)
    gene = make_staff("gene", "tech", PASSWORD)
    assert log_in(client, gene.username).status_code == 302
    return client


def names(response: "TestResponse") -> list[str]:
    return [template.name or "" for template in response.templates]


def words(response: "TestResponse") -> str:
    """The page's text with line breaks and indents read as single spaces."""
    return " ".join(response.content.decode().split())


# --------------------------------------------------------------------- 403
def test_the_no_access_page_says_so_and_offers_home(gene_client: Client) -> None:
    response = gene_client.get("/staff/")

    assert response.status_code == 403
    assert NO_ACCESS in words(response)
    assert HOME_LINK in words(response)
    assert "base.html" in names(response)
    assert "kit/menu.html" in names(response)


# --------------------------------------------------------------------- 404
def test_a_missing_page_says_so_and_offers_home(gene_client: Client) -> None:
    response = gene_client.get("/no-such-page/")

    assert response.status_code == 404
    for sentence in NOT_FOUND:
        assert sentence in words(response)
    assert HOME_LINK in words(response)
    assert "base.html" in names(response)


def test_signed_in_a_missing_page_has_the_menu(gene_client: Client) -> None:
    assert "kit/menu.html" in names(gene_client.get("/no-such-page/"))


def test_signed_out_a_missing_page_has_no_menu() -> None:
    response = Client().get("/no-such-page/")

    assert response.status_code == 404
    assert "kit/menu.html" not in names(response)


def test_a_missing_page_marks_no_menu_item_as_current(gene_client: Client) -> None:
    """There is no `resolver_match` on a 404 (§6.2)."""
    response = gene_client.get("/no-such-page/")

    assert 'aria-current="page"' not in words(response)


# --------------------------------------------------------------------- 500
def test_the_error_page_says_nothing_was_saved_and_offers_home(
    gene_client: Client,
) -> None:
    response = gene_client.get(urls_busy.BROKEN)

    assert response.status_code == 500
    for sentence in WENT_WRONG:
        assert sentence in words(response)
    assert HOME_LINK in words(response)


def test_the_error_page_is_bare(gene_client: Client) -> None:
    """No menu and no "Signed in as": both would need the database."""
    response = gene_client.get(urls_busy.BROKEN)

    assert "kit/bare.html" in names(response)
    assert "base.html" not in names(response)
    assert "kit/menu.html" not in names(response)
    assert "Signed in as" not in words(response)


def signed_in_request(client: Client) -> HttpRequest:
    """A request with the client's session and a lazy user, as the
    middleware leaves it: reading either would query the database."""
    request = RequestFactory().get("/")
    request.COOKIES.update(
        {key: morsel.value for key, morsel in client.cookies.items()}
    )

    def no_page(request: HttpRequest) -> HttpResponse:
        return HttpResponse()

    SessionMiddleware(no_page).process_request(request)
    AuthenticationMiddleware(no_page).process_request(request)
    return request


def database_down() -> None:
    raise OperationalError("connection to server failed (test)")


def test_the_error_page_shows_with_the_database_broken(
    gene_client: Client,
    django_assert_num_queries: DjangoAssertNumQueries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = signed_in_request(gene_client)
    handler = get_resolver().resolve_error_handler(500)

    with django_assert_num_queries(0), monkeypatch.context() as broken:
        broken.setattr(connection, "ensure_connection", database_down)
        response = handler(request)

    assert response.status_code == 500
    html = " ".join(response.content.decode().split())
    assert WENT_WRONG[0] in html
    assert "Signed in as" not in html


def test_the_error_page_shows_with_no_error_being_handled() -> None:
    """`handler500` may be called directly (test_practice_banner.py does)."""
    handler = get_resolver().resolve_error_handler(500)

    response = handler(RequestFactory().get("/"))

    assert response.status_code == 500
    assert WENT_WRONG[0] in response.content.decode()
