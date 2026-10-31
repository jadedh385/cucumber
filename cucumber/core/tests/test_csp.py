"""U0.10a AC4: one Content Security Policy on every answer Django makes (§5).

The exact header, on a page, a 404, a 500, the CSRF page and the Busy page;
none with `DEBUG=1` (Django's debug pages use inline style and script).
Its place in the middleware is checked in test_app_settings.py. The E2E
console watcher checks that no page breaks it (session 3).
"""

from collections.abc import Iterator

import pytest
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory, override_settings

from cucumber.accounts.tests.helpers import LOGIN, PASSWORD, log_in
from cucumber.core.csp import HEADER, ContentSecurityPolicy
from cucumber.core.tests import urls_busy
from cucumber.core.tests.stock import make_staff

# §5.1. `img-src data:` is for the marks daisyUI draws in its CSS; G3 drops
# it if the compiled CSS has none.
POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; frame-src 'none'; "
    "object-src 'none'; base-uri 'none'"
)
FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"


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


# ----------------------------------------------------------- the setting
def test_the_policy_is_written_in_django_6s_shape() -> None:
    """So moving to Django 6.2 LTS deletes our class and keeps the setting."""
    policy = getattr(settings, "SECURE_CSP", {})

    assert (
        "; ".join(
            f"{directive} {' '.join(sources)}" for directive, sources in policy.items()
        )
        == POLICY
    )


# ------------------------------------------------------ on every answer
@pytest.mark.django_db
@pytest.mark.parametrize("address", [LOGIN, "/health/"])
def test_a_page_carries_the_policy(address: str) -> None:
    response = Client().get(address)

    assert response[HEADER] == POLICY


@pytest.mark.django_db
def test_a_missing_page_carries_it(gene_client: Client) -> None:
    response = gene_client.get("/no-such-page/")

    assert response.status_code == 404
    assert response[HEADER] == POLICY


@pytest.mark.django_db
def test_a_refused_page_carries_it(gene_client: Client) -> None:
    response = gene_client.get("/staff/")

    assert response.status_code == 403
    assert response[HEADER] == POLICY


@pytest.mark.django_db
def test_the_error_page_carries_it(gene_client: Client) -> None:
    response = gene_client.get(urls_busy.BROKEN)

    assert response.status_code == 500
    assert response[HEADER] == POLICY


@pytest.mark.django_db
def test_the_csrf_page_carries_it() -> None:
    response = Client(enforce_csrf_checks=True).post(LOGIN, {})

    assert response.status_code == 403
    assert response[HEADER] == POLICY


@pytest.mark.django_db(transaction=True)
def test_the_busy_page_carries_it(gene_client: Client) -> None:
    response = gene_client.get(urls_busy.STATEMENT)

    assert response.status_code == 503
    assert response[HEADER] == POLICY


@pytest.mark.django_db
def test_htmx_answers_carry_it_too(gene_client: Client) -> None:
    response = gene_client.get("/", headers={"HX-Request": "true"})

    assert response[HEADER] == POLICY


# --------------------------------------------------------- when it is not
@pytest.mark.django_db
def test_with_debug_on_the_header_is_left_off() -> None:
    """Local only: Django's debug pages need inline style and script."""
    with override_settings(DEBUG=True):
        response = Client().get(LOGIN)

    assert HEADER not in response


def a_page_with_its_own_policy(request: HttpRequest) -> HttpResponse:
    response = HttpResponse("own")
    response[HEADER] = "default-src 'none'"
    return response


def test_an_answer_that_already_has_a_policy_keeps_it() -> None:
    middleware = ContentSecurityPolicy(a_page_with_its_own_policy)

    response = middleware(RequestFactory().get("/"))

    assert response[HEADER] == "default-src 'none'"
