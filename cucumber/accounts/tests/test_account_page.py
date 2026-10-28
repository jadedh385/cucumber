"""U0.10a Q3 a): the Account page holds Change password and Log out (§6.2, §11.1).

The menu's Account item opens it. The top bar keeps only the name, so Log
out is no longer on every page (U0.5 AC21 as changed at U0.10a G1, §16).
"""

import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.permissions import Role
from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    LOGOUT,
    PASSWORD,
    PASSWORD_PAGE,
    Response,
    redirect_target,
    shows_signed_in,
    text,
)
from cucumber.core.tests.stock import make_staff

pytestmark = pytest.mark.django_db

ACCOUNT = "/account/"


def logout_form(response: Response) -> str | None:
    """The whole Log out form, if the page has one."""
    found = re.search(
        r'<form\b[^>]*action="/accounts/logout/"[^>]*>.*?</form>',
        text(response),
        re.DOTALL,
    )
    return found.group(0) if found else None


def test_the_page_shows_your_name_and_email(owner: User, owner_client: Client) -> None:
    response = owner_client.get(ACCOUNT)

    assert response.status_code == 200
    assert owner.first_name in text(response)
    assert owner.email in text(response)


def test_it_leads_to_change_password(owner_client: Client) -> None:
    html = text(owner_client.get(ACCOUNT))

    assert f'href="{PASSWORD_PAGE}"' in html
    assert "Change password" in html


def test_it_has_the_log_out_button_as_a_form_post(owner_client: Client) -> None:
    form = logout_form(owner_client.get(ACCOUNT))

    assert form is not None, "no Log out form"
    assert 'method="post"' in form.lower()
    assert 'name="csrfmiddlewaretoken"' in form
    assert "Log out" in form


def test_its_log_out_button_logs_out(owner_client: Client) -> None:
    owner_client.get(ACCOUNT)

    response = owner_client.post(LOGOUT)

    assert response.status_code == 302
    assert redirect_target(owner_client.get(HOME))[0] == LOGIN


def test_home_no_longer_carries_log_out(owner_client: Client) -> None:
    assert logout_form(owner_client.get(HOME)) is None


def test_it_is_on_the_base_page_with_who_is_signed_in(owner_client: Client) -> None:
    response = owner_client.get(ACCOUNT)

    assert "base.html" in [template.name for template in response.templates]
    assert shows_signed_in(text(response), "jade")


@pytest.mark.parametrize("role", [*Role, None], ids=str)
def test_every_role_and_no_role_opens_it(role: Role | None) -> None:
    client = Client()
    client.force_login(make_staff(f"person_{role or 'none'}", role, PASSWORD))

    assert client.get(ACCOUNT).status_code == 200


def test_head_is_answered_and_a_post_is_not(owner_client: Client) -> None:
    assert owner_client.head(ACCOUNT).status_code == 200
    assert owner_client.post(ACCOUNT).status_code == 405


def test_signed_out_it_opens_the_login_page() -> None:
    response = Client().get(ACCOUNT)

    assert response.status_code == 302
    assert redirect_target(response)[0] == LOGIN
