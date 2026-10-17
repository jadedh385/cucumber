"""AC9: on a 375 px phone, staging shows "Practice data" and keeps it in view."""

import os
from collections.abc import Callable, Iterator

import pytest
from django.test import override_settings
from playwright.sync_api import Locator, Page, expect

from e2e.site import REMOTE_ENVIRONMENT, remote_site

pytestmark = pytest.mark.django_db(transaction=True)

PHONE_WIDTH = 375
TOP_OF_SCREEN = 50  # px


@pytest.fixture
def environment() -> Iterator[Callable[[str], None]]:
    """Pretend the live server is staging or production for one test.

    A running site is what it is: a test that needs another environment is
    skipped there (it still runs against the live server).
    """
    overrides: list[override_settings] = []
    is_remote = remote_site(os.environ) is not None

    def become(name: str) -> None:
        if is_remote:
            if name != REMOTE_ENVIRONMENT:
                pytest.skip(f"the site under test is {REMOTE_ENVIRONMENT}, not {name}")
            return
        override = override_settings(ENVIRONMENT=name)
        override.enable()
        overrides.append(override)

    yield become
    for override in reversed(overrides):
        override.disable()


def banner(page: Page) -> Locator:
    """The banner as shown; the wording may differ on phones and desktops."""
    return page.get_by_text("PRACTICE DATA").filter(visible=True)


def open_login(site_url: str, page: Page) -> None:
    response = page.goto(f"{site_url}/accounts/login/")
    assert response is not None and response.ok


def test_staging_login_page_shows_the_banner_and_fits_the_screen(
    site_url: str, page: Page, environment: Callable[[str], None]
) -> None:
    environment("staging")

    open_login(site_url, page)

    expect(banner(page)).to_have_count(1)
    assert page.title().startswith("[Practice]")
    page_width = page.evaluate("document.documentElement.scrollWidth")
    assert page_width <= PHONE_WIDTH, "the banner makes the page scroll sideways"


def test_the_banner_stays_at_the_top_while_scrolling(
    site_url: str, page: Page, environment: Callable[[str], None]
) -> None:
    environment("staging")
    open_login(site_url, page)
    page.evaluate("document.body.style.minHeight = '3000px'")

    page.mouse.wheel(0, 2000)
    page.wait_for_function("window.scrollY > 0")

    box = banner(page).bounding_box()
    assert box is not None
    assert box["y"] < TOP_OF_SCREEN, "the banner scrolled out of view"


def test_production_shows_no_banner(
    site_url: str, page: Page, environment: Callable[[str], None]
) -> None:
    environment("production")

    open_login(site_url, page)

    expect(page.get_by_text("PRACTICE DATA")).to_have_count(0)
