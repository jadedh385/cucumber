"""U0.10a AC16: a stale page's form gets "open too long" and Reload (§9.1).

`Client(enforce_csrf_checks=True)`: the test client skips the CSRF check
otherwise. Django's own `django.security.csrf` line stays the only line,
and no token is in any record (captured with `logged`, §9.2).
"""

import re
from collections.abc import Iterator

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, override_settings

from cucumber.accounts.tests.helpers import (
    LOGIN,
    NEW_PASSWORD,
    PASSWORD,
    PASSWORD_PAGE,
    htmx_headers,
)
from cucumber.core.tests.logs import Line, Logged
from cucumber.core.tests.stock import make_staff

pytestmark = pytest.mark.django_db

STALE_WORDS = "This page was open too long. Reload it and try again."
FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"
CHANGE = {
    "old_password": PASSWORD,
    "new_password1": NEW_PASSWORD,
    "new_password2": NEW_PASSWORD,
}


@pytest.fixture(autouse=True)
def fast_passwords() -> Iterator[None]:
    with override_settings(PASSWORD_HASHERS=[FAST_HASHER]):
        yield


@pytest.fixture
def gene() -> User:
    return make_staff("gene", "tech", PASSWORD)


@pytest.fixture
def checked() -> Client:
    """A client that sends no token unless the test gives one."""
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def gene_checked(gene: User, checked: Client) -> Client:
    checked.force_login(gene)
    return checked


def reload_address(html: str) -> str:
    """Where the page's Reload link goes."""
    found = re.search(r'<a\b[^>]*href="([^"]*)"[^>]*>\s*Reload\s*</a>', html)
    assert found, "the page has no Reload link"
    return found.group(1)


def a_token(client: Client) -> str:
    """The CSRF cookie a page has given this client."""
    client.get(LOGIN)
    return client.cookies[settings.CSRF_COOKIE_NAME].value


# ------------------------------------------------------------------ setting
def test_django_uses_cucumbers_csrf_page() -> None:
    assert settings.CSRF_FAILURE_VIEW == "cucumber.core.views.csrf_failure"


# ------------------------------------------------------------- the page
@pytest.mark.parametrize("token", [None, "x" * 64], ids=["no token", "wrong token"])
def test_a_login_with_a_stale_token_gets_the_kits_page(
    checked: Client, gene: User, token: str | None
) -> None:
    a_token(checked)
    form = {"username": gene.username, "password": PASSWORD}
    if token:
        form["csrfmiddlewaretoken"] = token

    response = checked.post(LOGIN, form)

    assert response.status_code == 403
    html = response.content.decode()
    assert STALE_WORDS in html
    assert "CSRF" not in html, "Django's reason is never shown"
    assert "base.html" in [template.name for template in response.templates]
    assert "_auth_user_id" not in checked.session, "nobody was logged in"


def test_reload_goes_back_to_the_page_the_form_was_on(gene_checked: Client) -> None:
    response = gene_checked.post(
        PASSWORD_PAGE, CHANGE, HTTP_REFERER="http://testserver/accounts/password/"
    )

    assert reload_address(response.content.decode()) == "/accounts/password/"


@pytest.mark.parametrize(
    "referer",
    ["https://elsewhere.example/accounts/password/", "//elsewhere.example/", None],
)
def test_reload_goes_home_when_the_referer_is_not_this_site(
    gene_checked: Client, referer: str | None
) -> None:
    headers = {"Referer": referer} if referer else {}

    response = gene_checked.post(PASSWORD_PAGE, CHANGE, headers=headers)

    assert reload_address(response.content.decode()) == "/"


def test_nothing_is_saved(gene: User, gene_checked: Client) -> None:
    gene_checked.post(PASSWORD_PAGE, CHANGE)

    assert User.objects.get(pk=gene.pk).check_password(PASSWORD)


def test_signed_in_the_page_has_the_menu(gene_checked: Client) -> None:
    response = gene_checked.post(PASSWORD_PAGE, CHANGE)

    assert "kit/menu.html" in [template.name for template in response.templates]


def test_signed_out_the_page_has_no_menu(checked: Client) -> None:
    response = checked.post(LOGIN, {"username": "x", "password": "y"})

    assert response.status_code == 403
    assert "kit/menu.html" not in [template.name for template in response.templates]


def test_an_htmx_request_is_told_the_page_is_stale(gene_checked: Client) -> None:
    """`requests.js` shows the same words in the banner (§4.3)."""
    response = gene_checked.post(
        PASSWORD_PAGE,
        CHANGE,
        headers=htmx_headers("http://testserver/accounts/password/"),
    )

    assert response.status_code == 403
    assert response["Cucumber-Trouble"] == "stale-page"


def test_a_plain_request_is_not_given_the_htmx_header(gene_checked: Client) -> None:
    response = gene_checked.post(PASSWORD_PAGE, CHANGE)

    assert response.status_code == 403
    assert "Cucumber-Trouble" not in response


# --------------------------------------------------------------- the log
def test_djangos_csrf_line_is_the_only_line(
    checked: Client, gene: User, logged: Logged
) -> None:
    checked.post(LOGIN, {"username": gene.username, "password": PASSWORD})

    assert logged.lines() == [
        Line(
            "django.security.csrf", f"Forbidden (CSRF cookie not set.): {LOGIN}", False
        )
    ]


def test_no_token_is_in_any_log_record(
    checked: Client, gene: User, logged: Logged
) -> None:
    cookie = a_token(checked)
    posted = "y" * 64

    checked.post(
        LOGIN,
        {
            "username": gene.username,
            "password": PASSWORD,
            "csrfmiddlewaretoken": posted,
        },
    )

    text = logged.text()
    assert len(logged.lines()) == 1
    assert cookie not in text
    assert posted not in text
