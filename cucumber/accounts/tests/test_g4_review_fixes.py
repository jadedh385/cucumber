"""U0.10a G4: the review findings fixed at G4 in accounts (design §23).

- Log out moved to Account (Q3 a)), which waits while a password change is
  due, so the forced Password page offers Log out itself (G4 review).
"""

import pytest
from django.contrib.auth.models import User

from cucumber.accounts.tests.helpers import (
    LOGOUT,
    PASSWORD_PAGE,
    mark_change_due,
    signed_in,
    text,
)

pytestmark = pytest.mark.django_db


def test_the_forced_password_page_offers_log_out(gene: User) -> None:
    mark_change_due(gene)

    page = text(signed_in(gene).get(PASSWORD_PAGE))

    assert f'method="post" action="{LOGOUT}">' in page
    assert "Log out" in page
