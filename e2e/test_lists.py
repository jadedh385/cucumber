"""U0.10a AC19: a list is cards on a phone and a table on a desktop (§7.6).

One copy of the markup: at 375 px the header row is hidden and each row is
a block (a card); at 1280 px a table with its header. The same people show
on both. Reading the Staff list changes nothing, so this runs on staging too.
"""

import pytest
from playwright.sync_api import Page, expect

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff
from e2e.conftest import E2E_PASSWORD
from e2e.pages import DESKTOP, is_staging, sign_in_as

pytestmark = pytest.mark.django_db(transaction=True)

ROW_DISPLAY = "row => getComputedStyle(row).display"
TWO_PEOPLE = 2  # the Admin and one more


def first_cells(page: Page) -> list[str]:
    """The main words of each row, as shown."""
    names: list[str] = page.locator("main tbody tr").evaluate_all(
        "rows => rows.map(row => row.querySelector('td').innerText.trim())"
    )
    return names


def test_staff_are_cards_on_a_phone_and_a_table_on_a_desktop(
    site_url: str, page: Page, account: tuple[str, str]
) -> None:
    if not is_staging(site_url):
        make_staff("gene", "tech", E2E_PASSWORD)
    sign_in_as(Role.ADMIN, page, site_url, account)
    page.goto(f"{site_url}/staff/")
    rows = page.locator("main tbody tr")

    expect(page.locator("main thead")).to_be_hidden()
    assert rows.first.evaluate(ROW_DISPLAY) != "table-row"
    on_a_phone = first_cells(page)

    page.set_viewport_size(DESKTOP)

    expect(page.locator("main thead")).to_be_visible()
    assert rows.first.evaluate(ROW_DISPLAY) == "table-row"
    assert first_cells(page) == on_a_phone
    assert len(on_a_phone) >= TWO_PEOPLE
