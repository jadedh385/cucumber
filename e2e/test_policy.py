"""U0.10a AC2, AC4: pages use only the site itself, under its CSP (§5).

AC2: every request a page makes goes to the site (Playwright's request log),
on every page the Admin reaches. AC4: the console watcher (e2e/conftest.py)
fails any browser test that meets a CSP refusal; here a test-only page that
breaks the policy shows it is caught. That page is in a test URLconf, so
that test runs on the local live server only; the others run on staging too.
"""

from collections.abc import Iterator

import pytest
from django.test import override_settings
from playwright.sync_api import Page, Request, expect

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff
from e2e.conftest import E2E_PASSWORD, ConsoleWatch, is_policy_break
from e2e.pages import is_staging, pages_within_two_taps, sign_in_as
from e2e.urls_csp import BREAKS_THE_POLICY, RAN

pytestmark = pytest.mark.django_db(transaction=True)

# Addresses a browser makes up itself, which never leave the phone.
IN_THE_PAGE = ("data:", "blob:", "about:")


@pytest.fixture
def policy_breaker(local_only: None) -> Iterator[None]:
    with override_settings(ROOT_URLCONF="e2e.urls_csp"):
        yield


def test_no_request_leaves_the_site(
    site_url: str, page: Page, account: tuple[str, str]
) -> None:
    if not is_staging(site_url):
        make_staff("gene", "tech", E2E_PASSWORD)  # a person's page too
    requested: list[str] = []

    def note(request: Request) -> None:
        requested.append(request.url)

    page.on("request", note)
    page.goto(f"{site_url}/accounts/login/")
    sign_in_as(Role.ADMIN, page, site_url, account)
    pages_within_two_taps(page, site_url)

    elsewhere = [
        url for url in requested if not url.startswith((f"{site_url}/", *IN_THE_PAGE))
    ]
    assert elsewhere == []
    assert requested, "the request log is empty"


def test_a_page_carries_the_policy(site_url: str, page: Page) -> None:
    response = page.goto(f"{site_url}/accounts/login/")

    assert response is not None
    assert "script-src 'self'" in response.headers.get("content-security-policy", "")


def test_a_page_that_breaks_the_policy_is_caught(
    policy_breaker: None, site_url: str, page: Page, console_watch: ConsoleWatch
) -> None:
    page.goto(f"{site_url}{BREAKS_THE_POLICY}")
    expect(page.locator("p")).to_be_visible()

    caught = console_watch.take()  # taken, so this test itself passes

    assert page.title() != RAN, "the inline script ran"
    assert any(is_policy_break(line) for line in caught), caught
    assert any("inline script" in line for line in caught), caught
