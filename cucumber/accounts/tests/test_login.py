"""AC1-AC6, AC14: logging in with an email, and logging out (design §2, §6, §7.4)."""

import re
from unittest import mock

import pytest
from django.contrib.auth import base_user
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.services import email_key
from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    LOGOUT,
    PASSWORD,
    WRONG,
    log_in,
    redirect_target,
    shows_signed_in,
    signed_in_as,
    text,
    without_values,
)

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------- AC1, AC4
def test_a_good_login_lands_on_the_home_page(gene: User) -> None:
    client = Client()

    response = log_in(client, "gene@example.com")

    assert response.status_code == 302
    assert response["Location"] == HOME
    assert signed_in_as(client) == gene.pk
    assert shows_signed_in(text(client.get(HOME)), "gene")


def test_a_next_page_inside_cucumber_is_kept(gene: User) -> None:
    client = Client()

    response = client.post(
        f"{LOGIN}?next=/staff/", {"username": "gene@example.com", "password": PASSWORD}
    )

    assert response["Location"] == "/staff/"


@pytest.mark.parametrize(
    "next_page", ["//evil.example", "https://evil.example", "https://evil.example/x"]
)
def test_a_next_page_on_another_site_is_ignored(gene: User, next_page: str) -> None:
    client = Client()

    response = client.post(
        f"{LOGIN}?next={next_page}",
        {"username": "gene@example.com", "password": PASSWORD},
    )

    assert response.status_code == 302
    assert response["Location"] == HOME


# ---------------------------------------------------------------------- AC2
def refused_page(email: str, password: str) -> tuple[int, str]:
    client = Client()
    response = log_in(client, email, password)
    assert signed_in_as(client) is None
    return response.status_code, without_values(text(response))


def test_wrong_password_unknown_email_and_deactivated_look_the_same(
    gene: User, pim: User
) -> None:
    pim.is_active = False
    pim.save()

    wrong_password = refused_page("gene@example.com", "not-the-password")
    unknown_email = refused_page("nobody@example.com", PASSWORD)
    deactivated = refused_page("pim@example.com", PASSWORD)

    assert wrong_password[0] == 200
    assert WRONG in wrong_password[1]
    assert unknown_email == wrong_password
    assert deactivated == wrong_password


def test_an_unknown_email_still_runs_the_password_hasher(db: None) -> None:
    """So it takes about as long as a wrong password for a real account."""
    with mock.patch.object(base_user, "make_password", wraps=make_password) as hasher:
        refused_page("nobody@example.com", PASSWORD)

    assert hasher.called


# ---------------------------------------------------------------------- AC3
@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("gene@example.com", "gene@example.com"),
        ("  Gene@Example.COM ", "gene@example.com"),
        ("\tGENE@EXAMPLE.COM\n", "gene@example.com"),
    ],
)
def test_email_key_trims_and_lowercases(typed: str, stored: str) -> None:
    assert email_key(typed) == stored


def test_email_key_lowercases_like_postgresql_not_casefold() -> None:
    """`casefold()` turns ß into ss; PostgreSQL's lower() keeps it (§2.1)."""
    assert email_key("Straße@Example.com") == "straße@example.com"


def test_capitals_and_spaces_log_into_the_same_account(gene: User) -> None:
    client = Client()

    response = log_in(client, "  Gene@Example.COM ")

    assert response.status_code == 302
    assert signed_in_as(client) == gene.pk


# ---------------------------------------------------------------------- AC5
def test_a_login_without_a_csrf_token_is_refused(gene: User) -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        LOGIN, {"username": "gene@example.com", "password": PASSWORD}
    )

    assert response.status_code == 403
    assert signed_in_as(client) is None


# ---------------------------------------------------------------------- AC6
def test_the_login_page_asks_for_an_email_phones_and_managers_understand(
    db: None,
) -> None:
    html = text(Client().get(LOGIN))

    assert re.search(r"<label[^>]*>\s*Email\s*:?\s*</label>", html)
    assert 'type="email"' in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'name="viewport"' in html


def test_the_login_page_has_no_user_name_box_any_more(db: None) -> None:
    """It replaces U0.3's stopgap page, which asked for a "Username"."""
    assert "Username" not in text(Client().get(LOGIN))


# --------------------------------------------------------------------- AC14
def test_opening_logout_as_a_link_is_refused_and_keeps_you_signed_in(
    gene_client: Client, gene: User
) -> None:
    response = gene_client.get(LOGOUT)

    assert response.status_code == 405
    assert signed_in_as(gene_client) == gene.pk


def test_the_logout_button_signs_you_out(gene_client: Client) -> None:
    response = gene_client.post(LOGOUT)

    assert response.status_code == 302
    assert redirect_target(response)[0] == LOGIN
    assert signed_in_as(gene_client) is None
    assert gene_client.get(HOME).status_code == 302
