"""U0.10a AC6: the menu in one hand (design §6.2, §6.3).

At 375 px a bar fixed to the bottom of the screen with at most four items;
every page within two taps of Home; at 1280 px a side menu and no bottom
bar. The Admin's tests also run on staging; the other roles need new
accounts, so they run locally only.
"""

import pytest
from playwright.sync_api import Page, expect

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff
from e2e.conftest import E2E_PASSWORD
from e2e.pages import (
    DESKTOP,
    ROLES,
    pages_for,
    pages_within_two_taps,
    sign_in_as,
    the_menu,
)

pytestmark = pytest.mark.django_db(transaction=True)

MOST_ITEMS = 4
SCROLL_PX = 1500
SIDE_MENU_WIDEST = 400  # px: a column on the left, not a bar across


def test_the_bottom_bar_stays_put_while_the_page_scrolls(
    site_url: str, page: Page, account: tuple[str, str]
) -> None:
    sign_in_as(Role.ADMIN, page, site_url, account)
    page.evaluate("document.body.style.minHeight = '3000px'")
    bar = the_menu(page)
    expect(bar).to_have_count(1)
    before = bar.bounding_box()

    page.mouse.wheel(0, SCROLL_PX)
    page.wait_for_function("window.scrollY > 0")

    after = bar.bounding_box()
    assert before is not None and after is not None
    assert after == before, "the bottom bar moved with the page"
    viewport = page.viewport_size
    assert viewport is not None
    assert after["y"] + after["height"] == pytest.approx(viewport["height"], abs=1), (
        "the bar isn't at the bottom of the screen"
    )


@pytest.mark.parametrize("name", ROLES)
def test_every_page_is_two_taps_from_home_with_four_items_at_most(
    name: str, site_url: str, page: Page, account: tuple[str, str]
) -> None:
    role = ROLES[name]
    if role is Role.ADMIN and not site_url.startswith("https://"):
        make_staff("gene", "tech", E2E_PASSWORD)  # a person's page to reach
    sign_in_as(role, page, site_url, account)

    expect(the_menu(page)).to_have_count(1)
    assert the_menu(page).locator("a").count() <= MOST_ITEMS
    assert set(pages_within_two_taps(page, site_url)) == pages_for(role)


def test_a_desktop_has_a_side_menu_and_no_bottom_bar(
    site_url: str, page: Page, account: tuple[str, str]
) -> None:
    sign_in_as(Role.ADMIN, page, site_url, account)

    page.set_viewport_size(DESKTOP)

    menu = the_menu(page)
    expect(menu).to_have_count(1)
    box = menu.bounding_box()
    assert box is not None
    assert box["x"] < DESKTOP["width"] / 4, "the menu isn't on the left"
    assert box["width"] <= SIDE_MENU_WIDEST, "the menu runs across the screen"
    assert box["y"] < DESKTOP["height"] / 2, "the menu sits at the bottom"
    expect(menu.get_by_role("link", name="Staff")).to_be_visible()
