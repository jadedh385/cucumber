"""U0.10a AC5, AC6: the menu, read from the U0.6 matrix (design §6.2).

Each item names the matrix row that decides who sees it; the drift tests
check that row is the one its page is labelled with, so the menu can never
show a page that refuses the person or hide one that lets them in. The menu's
links are the `<a>` elements inside the page's `<nav>` elements (the bottom
bar and the side menu); nothing else on a page is a `<nav>`.
"""

import re
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpRequest
from django.test import Client, RequestFactory, override_settings
from django.urls import resolve, reverse
from pytest_django import DjangoAssertNumQueries

from cucumber.accounts.context_processors import menu, permissions
from cucumber.accounts.menu import MENU, MenuItem
from cucumber.accounts.permissions import MATRIX, Permission, Role, standing
from cucumber.accounts.tests.helpers import (
    HOME,
    PASSWORD,
    PASSWORD_PAGE,
    STAFF,
    Response,
    text,
)
from cucumber.accounts.tests.test_login_required import every_page
from cucumber.core.tests.stock import make_staff

pytestmark = pytest.mark.django_db

ACCOUNT = "/account/"
PRACTICE = "/practice/"
ROLES: list[Role | None] = [*Role, None]
PROCESSOR = "cucumber.accounts.context_processors.menu"
# Design §6.2, typed in again; Practice from the §12 wireframe (Q4 a).
EVERYONE = ["home", "practice", "account"]
SEES = {
    Role.ADMIN: ["home", "staff", "practice", "account"],
    Role.SUPERVISOR: EVERYONE,
    Role.TECH: EVERYONE,
    Role.READ_ONLY: EVERYONE,
    None: EVERYONE,
}
ADDRESS = {"home": HOME, "staff": STAFF, "practice": PRACTICE, "account": ACCOUNT}
MOST_ITEMS = 4  # AC6: the bottom bar holds at most four


def person(role: Role | None) -> User:
    return make_staff(f"person_{role or 'none'}", role, PASSWORD)


def client_for(role: Role | None) -> Client:
    client = Client()
    client.force_login(person(role))
    return client


def nav_links(response: Response) -> set[str]:
    """Every address the page's `<nav>` elements link to."""
    navs = re.findall(r"<nav\b.*?</nav>", text(response), re.DOTALL)
    return {
        href for nav in navs for href in re.findall(r'<a\b[^>]*href="([^"]*)"', nav)
    }


def current_links(response: Response) -> set[str]:
    """The addresses of the links marked `aria-current="page"`."""
    tags = re.findall(r"<a\b[^>]*>", text(response))
    return {
        found.group(1)
        for tag in tags
        if 'aria-current="page"' in tag and (found := re.search(r'href="([^"]*)"', tag))
    }


def names(items: tuple[MenuItem, ...]) -> list[str]:
    return [found.url_name for found in items]


def request_from(user: User | AnonymousUser, with_standing: bool = True) -> HttpRequest:
    request = RequestFactory().get("/")
    request.user = user
    if with_standing:
        request.standing = standing(user)  # type: ignore[attr-defined]
    return request


def page_rows() -> dict[str, Permission | None]:
    """Each page's url name and the row its view is labelled with."""
    return {
        name: getattr(resolve(address).func, "cucumber_permission", None)
        for name, address in every_page()
    }


# ------------------------------------------------------------------ the data
def test_the_menu_is_the_designs() -> None:
    assert [
        (str(item.label), item.url_name, item.permission, item.icon, item.on_production)
        for item in MENU
    ] == [
        ("Home", "home", Permission.OWN_ACCOUNT, "home", True),
        ("Staff", "staff", Permission.MANAGE_USERS, "users", True),
        ("Practice", "practice", Permission.OWN_ACCOUNT, "beaker", False),
        ("Account", "account", Permission.OWN_ACCOUNT, "user", True),
    ]


def test_each_item_is_current_on_its_own_pages() -> None:
    assert {item.url_name: item.marks for item in MENU} == {
        "home": {"home"},
        "staff": {"staff", "staff_new", "staff_detail"},
        "practice": {"practice"},
        "account": {"account", "password"},
    }


def test_every_menu_row_is_a_matrix_row() -> None:
    rows = {row.permission for row in MATRIX}

    assert all(item.permission in rows for item in MENU)


# ----------------------------------------------------- no drift with the pages
@pytest.mark.parametrize("item", MENU, ids=lambda item: item.url_name)
def test_each_items_page_is_labelled_with_the_items_row(item: MenuItem) -> None:
    view = resolve(reverse(item.url_name)).func

    assert getattr(view, "cucumber_permission", None) == item.permission


@pytest.mark.parametrize("item", MENU, ids=lambda item: item.url_name)
def test_each_page_an_item_marks_has_the_items_row(item: MenuItem) -> None:
    """Being "current" on a page the item's row doesn't open would be drift too."""
    rows = page_rows()

    assert {mark: rows.get(mark) for mark in item.marks} == dict.fromkeys(
        item.marks, item.permission
    )


# ------------------------------------------------------- who sees which item
def test_every_page_template_gets_the_menu() -> None:
    templates: list[dict[str, Any]] = settings.TEMPLATES
    processors = templates[0]["OPTIONS"]["context_processors"]

    assert PROCESSOR in processors


@pytest.mark.parametrize("role", ROLES, ids=str)
def test_each_role_is_given_exactly_the_items_its_rows_allow(role: Role | None) -> None:
    given = menu(request_from(person(role)))["menu"]

    assert names(given) == SEES[role]


@pytest.mark.parametrize("role", ROLES, ids=str)
def test_no_one_gets_more_than_four_items(role: Role | None) -> None:
    assert len(menu(request_from(person(role)))["menu"]) <= MOST_ITEMS


@override_settings(ENVIRONMENT="production")
@pytest.mark.parametrize("role", [Role.ADMIN, Role.TECH], ids=str)
def test_production_has_no_practice_item(role: Role) -> None:
    given = names(menu(request_from(person(role)))["menu"])

    assert given == [name for name in SEES[role] if name != "practice"]


@override_settings(ENVIRONMENT="staging")
def test_staging_has_the_practice_item() -> None:
    assert "practice" in names(menu(request_from(person(Role.TECH)))["menu"])


def test_nobody_signed_in_gets_no_items() -> None:
    assert menu(request_from(AnonymousUser()))["menu"] == ()


def test_a_page_that_skipped_the_role_check_reads_the_role_itself(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """404 and the CSRF page have no `request.standing` (§6.2): one query."""
    request = request_from(person(Role.ADMIN), with_standing=False)

    with django_assert_num_queries(1):
        given = menu(request)["menu"]

    assert names(given) == SEES[Role.ADMIN]


@pytest.mark.parametrize("role", ROLES, ids=str)
def test_allowed_is_read_too_when_the_role_check_was_skipped(
    role: Role | None,
) -> None:
    allowed = permissions(request_from(person(role), with_standing=False))["allowed"]

    assert allowed == {row.permission for row in MATRIX if role in row.allowed}


def test_allowed_stays_empty_for_nobody_signed_in() -> None:
    assert permissions(request_from(AnonymousUser(), False))["allowed"] == frozenset()


# ------------------------------------------------------------------ the pages
@pytest.mark.parametrize("role", ROLES, ids=str)
def test_each_roles_pages_show_its_items(role: Role | None) -> None:
    response = client_for(role).get(HOME)

    assert nav_links(response) == {ADDRESS[name] for name in SEES[role]}
    for item in MENU:
        if item.url_name in SEES[role]:
            assert str(item.label) in text(response)


def test_a_signed_out_page_has_no_menu_links() -> None:
    assert nav_links(Client().get("/accounts/login/")) == set()


@pytest.mark.parametrize(
    ("address", "current"),
    [
        (HOME, HOME),
        (STAFF, STAFF),
        (f"{STAFF}new/", STAFF),
        (ACCOUNT, ACCOUNT),
        (PASSWORD_PAGE, ACCOUNT),
        (PRACTICE, PRACTICE),
    ],
)
def test_the_current_page_is_marked_on_its_item_only(
    address: str, current: str
) -> None:
    response = client_for(Role.ADMIN).get(address)

    assert response.status_code == 200
    assert current_links(response) == {current}


def test_a_persons_page_marks_staff_as_current() -> None:
    gene = make_staff("gene", "tech", PASSWORD)

    response = client_for(Role.ADMIN).get(f"{STAFF}{gene.pk}/")

    assert current_links(response) == {STAFF}


def test_the_no_access_page_shows_the_persons_own_items() -> None:
    response = client_for(Role.TECH).get(STAFF)

    assert response.status_code == 403
    assert nav_links(response) == {ADDRESS[name] for name in SEES[Role.TECH]}


@pytest.mark.parametrize("role", [Role.ADMIN, Role.TECH], ids=str)
def test_a_missing_page_shows_the_persons_items(role: Role) -> None:
    response = client_for(role).get("/no-such-page/")

    assert response.status_code == 404
    assert nav_links(response) == {ADDRESS[name] for name in SEES[role]}


def test_the_stale_page_shows_the_persons_items() -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(person(Role.ADMIN))

    response = client.post(PASSWORD_PAGE, {"old_password": PASSWORD})

    assert response.status_code == 403
    assert nav_links(response) == {ADDRESS[name] for name in SEES[Role.ADMIN]}
