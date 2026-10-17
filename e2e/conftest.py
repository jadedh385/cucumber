"""Browser-test set-up: the site under test plus a phone-sized Chromium."""

import os
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Route

from e2e.site import access_headers, remote_site

PHONE_VIEWPORT = {"width": 375, "height": 812}


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
