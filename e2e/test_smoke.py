"""AC10: on a 375 px phone screen, the health page and the login page open."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.django_db(transaction=True)

PHONE_WIDTH = 375


def test_browser_is_phone_sized(page: Page) -> None:
    assert page.viewport_size is not None
    assert page.viewport_size["width"] == PHONE_WIDTH


def test_health_page_says_ok(site_url: str, page: Page) -> None:
    page.goto(f"{site_url}/health/")

    expect(page.locator("body")).to_have_text("ok")


def test_login_page_opens_and_fits_the_screen(site_url: str, page: Page) -> None:
    response = page.goto(f"{site_url}/accounts/login/")

    assert response is not None and response.ok
    expect(page.get_by_label("Username")).to_be_visible()
    expect(page.get_by_label("Password")).to_be_visible()
    page_width = page.evaluate("document.documentElement.scrollWidth")
    assert page_width <= PHONE_WIDTH, "login page scrolls sideways on a phone"
