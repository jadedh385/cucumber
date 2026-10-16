"""AC9: on a 375 px phone, staging shows "Practice data" and keeps it in view."""

from collections.abc import Callable, Iterator

import pytest
from django.test import override_settings
from playwright.sync_api import Locator, Page, expect
from pytest_django.live_server_helper import LiveServer

pytestmark = pytest.mark.django_db(transaction=True)

PHONE_WIDTH = 375
TOP_OF_SCREEN = 50  # px


@pytest.fixture
def environment() -> Iterator[Callable[[str], None]]:
    """Pretend the live server is staging or production for one test."""
    overrides: list[override_settings] = []

    def become(name: str) -> None:
        override = override_settings(ENVIRONMENT=name)
        override.enable()
        overrides.append(override)

    yield become
    for override in reversed(overrides):
        override.disable()


def banner(page: Page) -> Locator:
    """The banner as shown; the wording may differ on phones and desktops."""
    return page.get_by_text("PRACTICE DATA").filter(visible=True)


def open_login(live_server: LiveServer, page: Page) -> None:
    response = page.goto(f"{live_server.url}/accounts/login/")
    assert response is not None and response.ok


def test_staging_login_page_shows_the_banner_and_fits_the_screen(
    live_server: LiveServer, page: Page, environment: Callable[[str], None]
) -> None:
    environment("staging")

    open_login(live_server, page)

    expect(banner(page)).to_have_count(1)
    assert page.title().startswith("[Practice]")
    page_width = page.evaluate("document.documentElement.scrollWidth")
    assert page_width <= PHONE_WIDTH, "the banner makes the page scroll sideways"


def test_the_banner_stays_at_the_top_while_scrolling(
    live_server: LiveServer, page: Page, environment: Callable[[str], None]
) -> None:
    environment("staging")
    open_login(live_server, page)
    page.evaluate("document.body.style.minHeight = '3000px'")

    page.mouse.wheel(0, 2000)
    page.wait_for_function("window.scrollY > 0")

    box = banner(page).bounding_box()
    assert box is not None
    assert box["y"] < TOP_OF_SCREEN, "the banner scrolled out of view"


def test_production_shows_no_banner(
    live_server: LiveServer, page: Page, environment: Callable[[str], None]
) -> None:
    environment("production")

    open_login(live_server, page)

    expect(page.get_by_text("PRACTICE DATA")).to_have_count(0)
