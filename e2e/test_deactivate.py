"""U0.7 on a 375 px phone: Deactivate needs a reason (design §10, AC11).

It changes an account, so it runs against the local live server only.
"""

import re

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Page, expect

from cucumber.core.tests.stock import make_staff
from cucumber.core.tests.trail import (
    LEFT_COMPANY,
    audit_mark,
    only_row,
    restore_audit_rows,
)
from e2e.conftest import E2E_PASSWORD
from e2e.test_login import fits_the_phone, log_in

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_admin_deactivates_with_a_reason_on_a_phone(
    site_url: str, page: Page, account: tuple[str, str], local_only: None
) -> None:
    restore_audit_rows()  # the flush before this test removed the reason lists
    gene = make_staff("gene", "tech", E2E_PASSWORD)
    log_in(page, site_url, *account)
    page.goto(f"{site_url}/staff/{gene.pk}/")
    fits_the_phone(page)

    page.get_by_role("button", name="Deactivate").click()

    expect(page.get_by_text("Choose a reason.")).to_be_visible()
    assert User.objects.get(pk=gene.pk).is_active

    mark = audit_mark()
    page.get_by_label("Reason").select_option(label="Left the company")
    fits_the_phone(page)
    page.get_by_role("button", name="Deactivate").click()

    expect(page).to_have_url(re.compile(rf"/staff/{gene.pk}/$"))
    expect(page.get_by_text("gene's account is deactivated.")).to_be_visible()
    assert not User.objects.get(pk=gene.pk).is_active
    row = only_row(mark, "auth_user")
    assert (row.reason_code, row.note) == (LEFT_COMPANY, None)
