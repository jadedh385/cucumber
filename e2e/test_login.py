"""U0.5 on a 375 px phone: log in and out, the forced change, adding staff.

The first test also runs against staging (with E2E_LOGIN_EMAIL/PASSWORD);
the others add or change accounts, so they run locally only.
"""

import re

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page, expect

from cucumber.accounts.services import give_new_password
from cucumber.core.tests.stock import make_staff
from e2e.conftest import E2E_PASSWORD
from e2e.pages import fits_the_phone, log_in, log_out, open_from_menu

pytestmark = pytest.mark.django_db(transaction=True)

NEW_PASSWORD = "fern-lantern-87"  # noqa: S105 (a local test account)
TEMPORARY = re.compile(r"[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}")


def test_log_in_see_home_and_log_out(
    site_url: str, page: Page, account: tuple[str, str]
) -> None:
    email, password = account

    log_in(page, site_url, email, password)

    expect(page.get_by_text("Signed in as").first).to_be_visible()
    fits_the_phone(page)
    log_out(page)


def test_the_menu_is_read_once_the_page_has_its_stylesheet(
    site_url: str, slow_stylesheet: Page, account: tuple[str, str]
) -> None:
    """G5 found this on staging: over a slow link the page text shows before
    the stylesheet, so for a moment the side menu and the bottom bar both show
    and "Account" matches two links. A step that reads the page as laid out
    waits for it to load first."""
    page = slow_stylesheet
    log_in(page, site_url, *account)

    expect(page.get_by_text("Signed in as").first).to_be_visible()
    open_from_menu(page, "Account")

    expect(page).to_have_url(re.compile(r"/account/$"))


def test_a_new_password_must_be_changed_at_the_next_login(
    site_url: str, page: Page, account: tuple[str, str], local_only: None
) -> None:
    owner = User.objects.get(username=account[0])
    gene = make_staff("gene", "tech", E2E_PASSWORD)
    temporary = give_new_password(owner, gene)

    log_in(page, site_url, gene.username, temporary)

    expect(page).to_have_url(re.compile(r"/accounts/password/"))
    fits_the_phone(page)
    page.get_by_label("Current password").fill(temporary)
    page.get_by_label("New password", exact=True).fill(NEW_PASSWORD)
    page.get_by_label("New password again").fill(NEW_PASSWORD)
    page.get_by_role("button", name="Save password").click()
    expect(page.get_by_text("Signed in as gene").first).to_be_visible()


def test_the_admin_adds_an_account_on_a_phone(
    site_url: str, page: Page, account: tuple[str, str], local_only: None
) -> None:
    log_in(page, site_url, *account)

    open_from_menu(page, "Staff")
    page.get_by_role("link", name="Add").click()
    page.get_by_label("Name").fill("Mali")
    page.get_by_label("Email").fill("mali@example.com")
    page.get_by_label("Tech").check()  # U0.6: a role is required
    page.get_by_role("button", name="Add account").click()

    expect(page.get_by_text(TEMPORARY)).to_be_visible()
    fits_the_phone(page)
