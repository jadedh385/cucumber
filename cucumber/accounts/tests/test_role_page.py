"""AC4, AC7, AC8: the role on the Staff pages (design §7, §7.1).

The form field is `role`, one radio button per role by its group name, and
on an existing account also `none` for no role. Adding offers only the four.
"""

import html
import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.tests.helpers import (
    PASSWORD,
    STAFF,
    Response,
    signed_in,
    text,
)
from cucumber.core.tests.stock import make_staff

pytestmark = pytest.mark.django_db

ROLE_LABELS = {
    "admin": "Admin",
    "supervisor": "Supervisor",
    "tech": "Tech",
    "read_only": "Read Only",
}


def roles_of(user: User) -> list[str]:
    return sorted(User.objects.get(pk=user.pk).groups.values_list("name", flat=True))


def role_radios(html: str) -> list[str]:
    """Every `<input>` tag that is a radio button named `role`, any attribute order."""
    tags = re.findall(r"<input\b[^>]*>", html)
    return [
        tag
        for tag in tags
        if re.search(r'\btype="radio"', tag) and re.search(r'\bname="role"', tag)
    ]


def radio_values(html: str) -> set[str]:
    return {
        match.group(1)
        for tag in role_radios(html)
        if (match := re.search(r'\bvalue="([^"]*)"', tag))
    }


def checked_values(html: str) -> set[str]:
    return {
        match.group(1)
        for tag in role_radios(html)
        if re.search(r"\bchecked\b", tag)
        and (match := re.search(r'\bvalue="([^"]*)"', tag))
    }


def page_text(response: Response) -> str:
    """The page as a person reads it: `&#x27;` back to an apostrophe."""
    return html.unescape(text(response))


def list_row_of(page: str, email: str) -> str:
    """The Staff list's `<li>` for the account with this email."""
    [row] = [item for item in page.split("<li") if email in item]
    return row


# ------------------------------------------------------------- adding (AC4)
def test_the_add_form_asks_for_one_of_the_four_roles(owner_client: Client) -> None:
    page = page_text(owner_client.get(f"{STAFF}new/"))

    assert radio_values(page) == set(ROLE_LABELS)
    for label in ROLE_LABELS.values():
        assert label in page
    assert checked_values(page) == set()  # no default


def test_adding_without_a_role_is_refused_on_the_page(owner_client: Client) -> None:
    count = User.objects.count()

    response = owner_client.post(
        f"{STAFF}new/", {"name": "Mali", "email": "mali@example.com"}
    )

    assert response.status_code == 200
    assert User.objects.count() == count


def test_no_role_is_not_offered_when_adding(owner_client: Client) -> None:
    count = User.objects.count()

    owner_client.post(
        f"{STAFF}new/", {"name": "Mali", "email": "mali@example.com", "role": "none"}
    )

    assert User.objects.count() == count


def test_adding_with_a_role_gives_it(owner_client: Client) -> None:
    owner_client.post(
        f"{STAFF}new/",
        {"name": "Mali", "email": "mali@example.com", "role": "supervisor"},
    )

    assert roles_of(User.objects.get(username="mali@example.com")) == ["supervisor"]


# ---------------------------------------------- the list and the page (AC4)
def test_the_list_shows_each_account_s_role(owner_client: Client, gene: User) -> None:
    make_staff("mali", None)
    make_staff("pim", "read_only")

    page = page_text(owner_client.get(STAFF))

    assert "Admin" in list_row_of(page, "jade@example.com")
    assert "Tech" in list_row_of(page, "gene@example.com")
    assert "Read Only" in list_row_of(page, "pim@example.com")
    assert "No role" in list_row_of(page, "mali@example.com")


def test_an_account_s_page_offers_every_role_and_no_role(
    owner_client: Client, gene: User
) -> None:
    page = page_text(owner_client.get(f"{STAFF}{gene.pk}/"))

    assert f'action="{STAFF}{gene.pk}/role/"' in page
    assert radio_values(page) == {*ROLE_LABELS, "none"}
    assert checked_values(page) == {"tech"}


def test_an_account_in_a_group_that_is_not_a_role_shows_no_role(
    owner_client: Client,
) -> None:
    """An old group (a flag's `Owner`) reads as no role, never a 500 (G4 M1)."""
    pim = make_staff("pim", "Owner")

    response = owner_client.get(f"{STAFF}{pim.pk}/")

    assert response.status_code == 200
    assert checked_values(page_text(response)) == {"none"}
    assert "No role" in list_row_of(page_text(owner_client.get(STAFF)), "pim@")


def test_your_own_page_shows_your_role_without_a_form(
    owner_client: Client, owner: User
) -> None:
    page = page_text(owner_client.get(f"{STAFF}{owner.pk}/"))

    assert "You can't change your own role." in page
    assert f"{STAFF}{owner.pk}/role/" not in page
    assert radio_values(page) == set()


# ---------------------------------------------------- changing it (AC4, AC7)
@pytest.mark.parametrize(
    ("role", "message"),
    [
        ("supervisor", "gene's role is now Supervisor."),
        ("admin", "gene's role is now Admin."),
        ("read_only", "gene's role is now Read Only."),
        ("none", "gene has no role now."),
    ],
)
def test_changing_a_role_saves_it_and_says_so(
    owner_client: Client, gene: User, role: str, message: str
) -> None:
    response = owner_client.post(f"{STAFF}{gene.pk}/role/", {"role": role})

    assert response.status_code == 302
    assert response["Location"] == f"{STAFF}{gene.pk}/"
    assert roles_of(gene) == ([] if role == "none" else [role])
    assert message in page_text(owner_client.get(response["Location"]))


def test_changing_your_own_role_is_refused_on_the_page(
    owner_client: Client, owner: User
) -> None:
    make_staff("mali", "admin")

    response = owner_client.post(
        f"{STAFF}{owner.pk}/role/", {"role": "tech"}, follow=True
    )

    assert "You can't change your own role." in page_text(response)
    assert roles_of(owner) == ["admin"]


@pytest.mark.parametrize("value", ["", "owner", "Admin", "superuser"])
def test_an_unknown_role_changes_nothing(
    owner_client: Client, gene: User, value: str
) -> None:
    owner_client.post(f"{STAFF}{gene.pk}/role/", {"role": value})

    assert roles_of(gene) == ["tech"]


def test_the_role_page_answers_only_a_form_post(
    owner_client: Client, gene: User
) -> None:
    response = owner_client.get(f"{STAFF}{gene.pk}/role/")

    assert response.status_code == 405
    assert roles_of(gene) == ["tech"]


def test_the_role_form_needs_its_csrf_token(owner: User, gene: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)

    response = client.post(f"{STAFF}{gene.pk}/role/", {"role": "admin"})

    assert response.status_code == 403
    assert roles_of(gene) == ["tech"]


def test_an_unknown_account_is_not_found(owner_client: Client) -> None:
    response = owner_client.post(f"{STAFF}99999/role/", {"role": "tech"})

    assert response.status_code == 404


# --------------------------------------------------------------- AC8
@pytest.mark.parametrize("role", ["supervisor", "tech", "read_only", None])
@pytest.mark.parametrize("method", ["get", "post"])
def test_nobody_but_the_admin_reaches_the_role_page(
    gene: User, role: str | None, method: str
) -> None:
    client = signed_in(make_staff(f"by_{role or 'none'}", role, PASSWORD))

    response = getattr(client, method)(f"{STAFF}{gene.pk}/role/", {"role": "admin"})

    assert response.status_code == 403
    assert roles_of(gene) == ["tech"]
