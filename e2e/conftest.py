"""Browser-test set-up: the site under test plus a phone-sized Chromium."""

import os
from collections.abc import Iterator
from typing import Any

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import BrowserContext, Route

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff
from e2e.site import access_headers, login_account, remote_site

PHONE_VIEWPORT = {"width": 375, "height": 812}
E2E_PASSWORD = "plum-orchid-42"  # noqa: S105 (a local test account)


@pytest.fixture(scope="session", autouse=True)
def allow_django_inside_playwright() -> Iterator[None]:
    """Playwright's sync API runs an event loop, which makes Django refuse
    database calls as "unsafe from async".

    Switched off only from the first browser test on (fixtures in this file
    apply to e2e/ only, which pytest runs last) and restored afterwards, so the
    other tests keep Django's guard. It has to cover the whole session because
    Playwright's event loop starts before any single test's database set-up.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
        yield


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    """Every browser test runs at phone width (U0.3 AC10)."""
    return {**browser_context_args, "viewport": PHONE_VIEWPORT}


@pytest.fixture
def context(context: BrowserContext) -> BrowserContext:
    """Add the Access service token (AC25) to requests for the site under test
    only, so no other host (a font, a redirect) ever sees it."""
    site = remote_site(os.environ)
    headers = access_headers(os.environ)
    if site is None or not headers:
        return context

    def add_token(route: Route) -> None:
        route.continue_(headers={**route.request.headers, **headers})

    context.route(f"{site}/**", add_token)
    return context


@pytest.fixture
def site_url(request: pytest.FixtureRequest) -> str:
    """`E2E_SITE_URL` if set (see e2e/site.py), else Django's live server."""
    remote = remote_site(os.environ)
    if remote is not None:
        return remote
    url: str = request.getfixturevalue("live_server").url
    return url


@pytest.fixture
def is_remote() -> bool:
    return remote_site(os.environ) is not None


@pytest.fixture
def local_only(is_remote: bool) -> None:
    """For tests that add or change accounts: never on staging's practice data."""
    if is_remote:
        pytest.skip("changes accounts: runs against the local live server only")


@pytest.fixture
def account(request: pytest.FixtureRequest, is_remote: bool) -> tuple[str, str]:
    """An Admin to log in as: staging's practice account, or a fresh local one."""
    if is_remote:
        found = login_account(os.environ)
        if found is None:
            pytest.skip("set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD (see e2e/site.py)")
        return found
    request.getfixturevalue("transactional_db")
    for role in Role:  # a browser test's flush removes the seeded groups
        Group.objects.get_or_create(name=role)
    owner = make_staff("jade", "admin", E2E_PASSWORD)
    return owner.username, E2E_PASSWORD
