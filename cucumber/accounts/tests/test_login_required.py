"""AC17-AC20: every page needs a login, except a short allow-list (§5).

AC17 walks every URL pattern, so a page added later can't be left open by
accident: it fails here until it needs a login or joins OPEN_PAGES on purpose.
"""

import re
from collections.abc import Iterator

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client, override_settings
from django.urls import URLPattern, URLResolver, get_resolver

from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    htmx_headers,
    redirect_target,
    text,
)
from cucumber.accounts.tests.urls import SAVED_GROUP

pytestmark = pytest.mark.django_db

# Pages anyone may open (design §5); static files are served before Django.
OPEN_PAGES = {"login", "health"}
# Pages U0.5 adds; the walk must find at least these.
U05_PAGES = {
    "home",
    "logout",
    "password",
    "staff",
    "staff_new",
    "staff_detail",
    "staff_deactivate",
    "staff_reactivate",
    "staff_new_password",
    "staff_unlock",
}
CONVERTER = re.compile(r"<(?:\w+:)?\w+>")


def every_page(
    patterns: list[URLPattern | URLResolver] | None = None, prefix: str = ""
) -> Iterator[tuple[str, str]]:
    """(name, an address for it) for every URL pattern, nested ones included."""
    if patterns is None:
        patterns = get_resolver().url_patterns
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        assert not route.startswith("^"), f"regex route {route!r}: fill it by hand"
        if isinstance(pattern, URLResolver):
            yield from every_page(pattern.url_patterns, route)
        else:
            yield str(pattern.name), "/" + CONVERTER.sub("1", route)


def test_the_walk_finds_every_page() -> None:
    names = {name for name, _ in every_page()}

    assert U05_PAGES | OPEN_PAGES <= names


@pytest.mark.parametrize("method", ["get", "post"])
def test_every_page_needs_a_login_except_the_open_ones(method: str) -> None:
    open_to_anyone = []
    for name, address in every_page():
        if name in OPEN_PAGES:
            continue
        response = getattr(Client(), method)(address)
        target = redirect_target(response) if response.status_code == 302 else None
        if target != (LOGIN, {"next": [address]}):
            open_to_anyone.append(f"{method.upper()} {address} ({name})")

    assert open_to_anyone == []


@pytest.mark.parametrize("address", ["/accounts/login/", "/health/"])
def test_the_open_pages_open_without_a_login(address: str) -> None:
    assert Client().get(address).status_code == 200


# --------------------------------------------------------------------- AC18
def test_home_opens_the_login_page_when_signed_out() -> None:
    response = Client().get(HOME)

    assert response.status_code == 302
    assert redirect_target(response)[0] == LOGIN


def test_home_opens_when_signed_in(gene_client: Client) -> None:
    assert gene_client.get(HOME).status_code == 200


def test_a_signed_out_page_comes_back_after_login(gene: User) -> None:
    client = Client()
    to_login = client.get("/accounts/password/")
    login_page = redirect_target(to_login)

    response = client.post(
        f"{login_page[0]}?next={login_page[1]['next'][0]}",
        {"username": "gene@example.com", "password": "plum-orchid-42"},
    )

    assert response["Location"] == "/accounts/password/"


# --------------------------------------------------------------------- AC19
def test_htmx_without_a_login_gets_401_and_a_whole_page_redirect() -> None:
    response = Client().post("/staff/new/", headers=htmx_headers())

    assert response.status_code == 401
    assert redirect_target(response) == (LOGIN, {"next": ["/staff/"]})
    assert "<form" not in text(response)
    assert "password" not in text(response).lower()


def test_htmx_next_is_the_page_not_the_background_address() -> None:
    current = "http://testserver/accounts/password/"

    response = Client().get("/staff/1/", headers=htmx_headers(current))

    assert redirect_target(response) == (LOGIN, {"next": ["/accounts/password/"]})


@pytest.mark.parametrize(
    "current",
    ["https://evil.example/staff/", "//evil.example/staff/", "http://evil.example/"],
)
def test_htmx_next_pointing_off_site_is_left_out(current: str) -> None:
    response = Client().get("/staff/", headers=htmx_headers(current))

    assert response.status_code == 401
    assert redirect_target(response) == (LOGIN, {})


def test_a_plain_request_without_a_login_still_gets_a_normal_redirect() -> None:
    response = Client().get("/staff/")

    assert response.status_code == 302
    assert "HX-Redirect" not in response


# --------------------------------------------------------------------- AC20
@override_settings(ROOT_URLCONF="cucumber.accounts.tests.urls")
def test_a_save_without_a_login_writes_nothing() -> None:
    response = Client().post("/test-only/save/")

    assert response.status_code == 302
    assert redirect_target(response)[0] == LOGIN
    assert not Group.objects.filter(name=SAVED_GROUP).exists()


@override_settings(ROOT_URLCONF="cucumber.accounts.tests.urls")
def test_the_test_only_save_works_when_signed_in(gene_client: Client) -> None:
    """Proves the test above would see a row if one were written."""
    gene_client.post("/test-only/save/")

    assert Group.objects.filter(name=SAVED_GROUP).exists()
