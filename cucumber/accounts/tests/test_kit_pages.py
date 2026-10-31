"""U0.10a AC11, AC19, AC20, AC22, AC23: the existing pages on the kit (§10.1).

Every word U0.5 design §14 gives is kept, so the U0.5, U0.6 and U0.7
behaviour tests pass unchanged (AC22). These check what the kit adds: forms
through its renderer (`kit/field.html`), a refusal under its field, the Staff
list as one table, a person's page as a detail, and Home's tiles.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.permissions import Role
from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    PASSWORD,
    PASSWORD_PAGE,
    STAFF,
    Response,
    shows_signed_in,
    text,
)
from cucumber.core.tests.stock import make_staff

pytestmark = pytest.mark.django_db

ADD = f"{STAFF}new/"
TAKEN = "Another account already uses this email."
NO_WORK = "No work to show yet. Lab work will appear here."
# Home's tiles: every menu item the person may open but Home (§10.1, §12).
TILES = {
    Role.ADMIN: {"/staff/", "/practice/", "/account/"},
    Role.SUPERVISOR: {"/practice/", "/account/"},
    Role.TECH: {"/practice/", "/account/"},
    Role.READ_ONLY: {"/practice/", "/account/"},
    None: {"/practice/", "/account/"},
}


def names(response: Response) -> list[str]:
    return [template.name or "" for template in response.templates]  # type: ignore[attr-defined]


def main_of(response: Response) -> str:
    found = re.search(r"<main\b.*?</main>", text(response), re.DOTALL)
    assert found, "the page has no <main>"
    return found.group(0)


def links_in(html: str) -> set[str]:
    return set(re.findall(r'<a\b[^>]*href="([^"]*)"', html))


def element_with_id(html: str, element_id: str) -> str:
    found = re.search(
        rf'<(\w+)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>(.*?)</\1>', html, re.DOTALL
    )
    assert found, f"no element with id {element_id}"
    return found.group(2)


def input_named(html: str, name: str) -> str:
    found = re.search(rf'<input\b[^>]*\bname="{name}"[^>]*>', html)
    assert found, f"no input {name}"
    return found.group(0)


# ------------------------------------------------------------ forms (AC11)
@pytest.mark.parametrize(
    ("address", "fields"),
    [(LOGIN, 2), (PASSWORD_PAGE, 3), (ADD, 3)],
    ids=["login", "password", "add staff"],
)
def test_each_form_renders_its_fields_through_the_kit(
    owner_client: Client, address: str, fields: int
) -> None:
    client = Client() if address == LOGIN else owner_client

    rendered = names(client.get(address))

    assert rendered.count("kit/field.html") == fields
    assert "accounts/_field.html" not in rendered


def test_the_old_field_include_is_gone() -> None:
    """The kit's field replaces it (§2)."""
    old = Path(settings.BASE_DIR) / "cucumber/accounts/templates/accounts/_field.html"

    assert not old.exists()


def test_a_service_refusal_lands_under_its_field_with_the_answers_kept(
    owner_client: Client, gene: User
) -> None:
    """A plain form: 200 with the form again (§11.2)."""
    response = owner_client.post(
        ADD, {"name": "Gene Two", "email": gene.email, "role": "supervisor"}
    )
    html = text(response)

    assert response.status_code == 200
    assert TAKEN in element_with_id(html, "id_email_error")
    email = input_named(html, "email")
    assert 'aria-invalid="true"' in email
    assert 'aria-describedby="id_email_error"' in email
    assert 'value="Gene Two"' in input_named(html, "name")
    assert re.search(r'<input\b[^>]*value="supervisor"[^>]*\bchecked', html)


def test_a_form_check_lands_under_its_field_too(owner_client: Client) -> None:
    response = owner_client.post(
        ADD, {"name": "", "email": "m@example.com", "role": "tech"}
    )

    assert "This field is required." in element_with_id(text(response), "id_name_error")


# ------------------------------------------------------- Staff list (AC19)
def test_the_staff_list_is_the_kits_table(owner_client: Client, gene: User) -> None:
    response = owner_client.get(STAFF)
    html = text(response)

    assert "kit/table.html" in names(response)
    assert html.count("<table") == 1
    headers = [
        " ".join(cell.split())
        for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", html, re.S)
    ]
    assert headers == ["Name", "Email", "Role", "State"]
    assert f'href="{STAFF}{gene.pk}/"' in html


def test_the_staff_list_has_add_above_the_table(owner_client: Client) -> None:
    html = text(owner_client.get(STAFF))

    assert f'href="{ADD}"' in html
    assert html.index(f'href="{ADD}"') < html.index("<table")


# ------------------------------------------------------ Staff detail (AC20)
def test_a_persons_page_is_the_kits_detail(owner_client: Client, gene: User) -> None:
    response = owner_client.get(f"{STAFF}{gene.pk}/")
    html = text(response)

    assert "kit/detail.html" in names(response)
    terms = [
        " ".join(t.split()) for t in re.findall(r"<dt\b[^>]*>(.*?)</dt>", html, re.S)
    ]
    assert terms[:3] == ["Email", "Role", "State"]
    assert re.search(r"<h1\b[^>]*>\s*gene\s*</h1>", html)


def test_a_persons_buttons_follow_the_facts(owner_client: Client, gene: User) -> None:
    html = text(owner_client.get(f"{STAFF}{gene.pk}/"))
    actions = html.index('class="kit-actions"')

    assert html.index("</dl>") < actions
    for button in ("deactivate", "new-password", "unlock"):
        assert actions < html.index(f'action="{STAFF}{gene.pk}/{button}/"'), button


# --------------------------------------------------------------- Home (AC23)
def person_client(role: Role | None) -> Client:
    client = Client()
    client.force_login(make_staff("mali", role, PASSWORD))
    return client


@pytest.mark.parametrize("role", [*Role, None], ids=str)
def test_home_greets_the_person_and_says_who_is_signed_in(role: Role | None) -> None:
    html = text(person_client(role).get(HOME))

    assert "Hello, mali" in html
    assert shows_signed_in(html, "mali")


@pytest.mark.parametrize("role", [*Role, None], ids=str)
def test_home_has_a_tile_per_menu_item_the_person_may_open(role: Role | None) -> None:
    assert links_in(main_of(person_client(role).get(HOME))) == TILES[role]


def test_home_says_there_is_no_work_yet(gene_client: Client) -> None:
    response = gene_client.get(HOME)

    assert NO_WORK in main_of(response)
    assert "kit/empty.html" in names(response)
