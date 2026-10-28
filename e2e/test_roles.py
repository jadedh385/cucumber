"""U0.6 on a 375 px phone: the Admin gives roles (design §10.2).

Both change accounts, so they run against the local live server only.
"""

import re

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page, expect

from cucumber.core.tests.stock import make_staff
from e2e.conftest import E2E_PASSWORD
from e2e.pages import fits_the_phone, log_in, log_out, open_from_menu
from e2e.test_login import NEW_PASSWORD, TEMPORARY

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_admin_adds_a_tech_who_then_sees_no_staff_link(
    site_url: str, page: Page, account: tuple[str, str], local_only: None
) -> None:
    log_in(page, site_url, *account)
    open_from_menu(page, "Staff")
    page.get_by_role("link", name="Add").click()
    page.get_by_label("Name").fill("Mali")
    page.get_by_label("Email").fill("mali@example.com")
    page.get_by_label("Tech").check()
    fits_the_phone(page)
    page.get_by_role("button", name="Add account").click()
    temporary = page.get_by_text(TEMPORARY).inner_text()
    log_out(page)

    log_in(page, site_url, "mali@example.com", temporary)
    page.get_by_label("Current password").fill(temporary)
    page.get_by_label("New password", exact=True).fill(NEW_PASSWORD)
    page.get_by_label("New password again").fill(NEW_PASSWORD)
    page.get_by_role("button", name="Save password").click()

    expect(page.get_by_text("Signed in as Mali").first).to_be_visible()
    expect(page.get_by_role("link", name="Staff")).to_have_count(0)
    page.goto(f"{site_url}/staff/")
    expect(page.get_by_text("You don't have access to this page.")).to_be_visible()
    fits_the_phone(page)


def test_the_admin_changes_a_tech_s_role_on_a_phone(
    site_url: str, page: Page, account: tuple[str, str], local_only: None
) -> None:
    gene = make_staff("gene", "tech", E2E_PASSWORD)
    log_in(page, site_url, *account)

    page.goto(f"{site_url}/staff/{gene.pk}/")
    fits_the_phone(page)
    page.get_by_label("Supervisor").check()
    page.get_by_role("button", name="Save role").click()

    expect(page).to_have_url(re.compile(rf"/staff/{gene.pk}/$"))
    expect(page.get_by_text("gene's role is now Supervisor.")).to_be_visible()
    groups = User.objects.get(pk=gene.pk).groups.values_list("name", flat=True)
    assert list(groups) == ["supervisor"]
