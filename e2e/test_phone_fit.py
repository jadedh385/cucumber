"""U0.10a AC7: every page at 375 px, for each role and none (design §6.3).

No sideways scroll; every button, menu item, list link and top-bar control
at least 44 x 44; text in every input, select and text area at least 16 px.
The pages are the ones each role reaches from Home (AC6), plus the 404 page,
the 403 page for those refused Staff, and the login page signed out.
"""

import pytest
from playwright.sync_api import Page

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff
from e2e.conftest import E2E_PASSWORD
from e2e.pages import (
    PHONE_WIDTH,
    ROLES,
    pages_within_two_taps,
    sideways_scroll,
    sign_in_as,
    small_targets,
    small_text,
)

pytestmark = pytest.mark.django_db(transaction=True)

NOT_FOUND = "/no-such-page/"
STAFF = "/staff/"


def problems_on(page: Page, site_url: str, path: str) -> list[str]:
    page.goto(f"{site_url}{path}")
    found = [
        f"{path}: tap target under 44 x 44: {name}" for name in small_targets(page)
    ]
    found += [f"{path}: text under 16 px: {name}" for name in small_text(page)]
    if sideways_scroll(page) > PHONE_WIDTH:
        found.append(f"{path}: scrolls sideways")
    return found


@pytest.mark.parametrize("name", ROLES)
def test_every_page_fits_a_phone_held_in_one_hand(
    name: str, site_url: str, page: Page, account: tuple[str, str]
) -> None:
    role = ROLES[name]
    if role is Role.ADMIN and not site_url.startswith("https://"):
        make_staff("gene", "tech", E2E_PASSWORD)  # a person's page to check
    sign_in_as(role, page, site_url, account)
    paths = [*pages_within_two_taps(page, site_url).values(), NOT_FOUND]
    if role is not Role.ADMIN:
        paths.append(STAFF)  # the 403 page

    problems = [found for path in paths for found in problems_on(page, site_url, path)]

    assert problems == []


def test_the_login_page_fits_a_phone(site_url: str, page: Page) -> None:
    assert problems_on(page, site_url, "/accounts/login/") == []
