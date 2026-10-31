"""U0.10a AC10: the week under the date follows the date picked (design §7.5).

Each day's `<option>` carries its ISO week from the server; `date-week.js`
copies the picked one into the `<output>` under the field. Seven days back
is always the week before, so picking the last day must change the week.
The practice page saves nothing, so this runs on staging too.
"""

import pytest
from playwright.sync_api import Page, expect

from cucumber.accounts.permissions import Role
from e2e.pages import open_practice, sign_in_as

pytestmark = pytest.mark.django_db(transaction=True)


def test_changing_the_date_changes_the_week(
    site_url: str, page: Page, account: tuple[str, str]
) -> None:
    sign_in_as(Role.ADMIN, page, site_url, account)
    open_practice(page, site_url)
    days = page.locator('select[name="date"] option')
    week = page.locator('output[for="id_date"]')
    this_week = days.first.get_attribute("data-week")
    last_week = days.last.get_attribute("data-week")
    assert this_week and last_week and this_week != last_week
    expect(week).to_contain_text(this_week)

    page.locator('select[name="date"]').select_option(days.last.get_attribute("value"))

    expect(week).to_contain_text(last_week)
    expect(week).not_to_contain_text(this_week)
