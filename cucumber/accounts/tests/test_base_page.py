"""AC6, AC21: the base page every signed-in screen uses.

The "Practice data" banner on every full page is already checked for every
template by core's test_practice_banner.py. The check that every word is
marked for translation moved to core's test_translation.py and covers every
app (U0.10a AC26). `base.html` moved to core (U0.10a §6.1); Log out moved to
the Account page (U0.10a Q3 a), test_account_page.py).
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, override_settings

from cucumber.accounts.tests.helpers import (
    HOME,
    PASSWORD,
    PASSWORD_PAGE,
    STAFF,
    shows_signed_in,
    signed_in,
    text,
)
from cucumber.core.tests.trail import as_system

CODE = Path(settings.BASE_DIR) / "cucumber"
DESIGNED_TEMPLATES = [
    "core/templates/base.html",
    "accounts/templates/accounts/home.html",
    "accounts/templates/accounts/password.html",
    "accounts/templates/registration/login.html",
]


# ------------------------------------------------------------ templates
@pytest.mark.parametrize("name", DESIGNED_TEMPLATES)
def test_the_designed_templates_exist(name: str) -> None:
    assert (CODE / name).is_file()


def test_the_base_page_is_only_in_core() -> None:
    """One `base.html`, so no app's copy can win the template search."""
    assert sorted(
        path.relative_to(CODE) for path in CODE.glob("*/templates/base.html")
    ) == [Path("core/templates/base.html")]


def test_the_staff_pages_have_their_templates() -> None:
    """List, add and detail at least (design §1)."""
    staff_pages = (CODE / "accounts/templates/accounts").glob("staff_*.html")
    assert len(list(staff_pages)) >= 3


# ----------------------------------------------------------- AC21 base
SIGNED_IN_PAGES = [HOME, PASSWORD_PAGE, STAFF, f"{STAFF}new/", "/account/"]


@pytest.mark.django_db
@pytest.mark.parametrize("address", SIGNED_IN_PAGES)
def test_signed_in_pages_use_the_base_page(owner_client: Client, address: str) -> None:
    response = owner_client.get(address)

    assert response.status_code == 200
    assert "base.html" in [template.name for template in response.templates]
    assert "Cucumber" in text(response)
    assert shows_signed_in(text(response), "jade")


@pytest.mark.django_db
def test_an_account_without_a_name_is_shown_by_its_email(db: None) -> None:
    with as_system():
        nameless = User.objects.create_user(
            username="nn@example.com", email="nn@example.com", password=PASSWORD
        )

    html = text(signed_in(nameless).get(HOME))

    assert shows_signed_in(html, "nn@example.com")


@pytest.mark.django_db
@override_settings(ENVIRONMENT="staging")
def test_the_home_page_shows_the_practice_banner_on_staging(
    gene_client: Client,
) -> None:
    assert "PRACTICE DATA" in text(gene_client.get(HOME))
