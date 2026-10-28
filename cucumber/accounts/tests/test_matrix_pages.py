"""AC10, AC11, AC14, AC15: every page checks its matrix row (design §3).

Generated from the URL patterns and `MATRIX`: each page names its row
(`view.cucumber_permission`), and each kind of person sends GET and POST to
it, with a valid CSRF token so only the role can refuse. Allowed: anything
but 403. Refused: the 403 page, and nothing in the database changes.
"""

import logging

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import resolve

from cucumber.accounts.permissions import MATRIX, Permission, Role
from cucumber.accounts.services import set_role
from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    PASSWORD,
    STAFF,
    Response,
    htmx_headers,
    redirect_target,
    text,
)
from cucumber.accounts.tests.test_login_required import OPEN_PAGES, every_page
from cucumber.accounts.tests.urls_without_row import NO_ROW_PAGE
from cucumber.core.tests.rows import as_int, fetch_one
from cucumber.core.tests.stock import make_staff, switch_off

pytestmark = pytest.mark.django_db

NO_ACCESS = "You don't have access to this page."
ROWS = {row.permission: row for row in MATRIX}
ROLES: list[Role | None] = [*Role, None]
# A CSRF secret the client sends as both cookie and header (Django accepts an
# unmasked 32-character secret), so the CSRF check never refuses the request.
CSRF_SECRET = "a" * 32
ACCOUNT_TABLES = [
    "auth_user",
    "auth_user_groups",
    "accounts_login_failure",
    "accounts_password_change_due",
]


def guarded_routes() -> list[tuple[str, str]]:
    """(name, address with `{id}` for the account) for every guarded page."""
    return [
        (name, address.replace("/1/", "/{id}/"))
        for name, address in every_page()
        if name not in OPEN_PAGES
    ]


def person(role: Role | None) -> User:
    return make_staff(f"person_{role or 'none'}", role, PASSWORD)


def client_for(user: User) -> Client:
    """Signed in, with the CSRF check on and a valid token sent."""
    client = Client(enforce_csrf_checks=True, HTTP_X_CSRFTOKEN=CSRF_SECRET)
    client.force_login(user)
    client.cookies["csrftoken"] = CSRF_SECRET
    return client


def accounts_snapshot() -> dict[str, object]:
    counts: dict[str, object] = {
        table: as_int(fetch_one(f"SELECT count(*) FROM {table}")[0])  # noqa: S608
        for table in ACCOUNT_TABLES
    }
    active = fetch_one("SELECT count(*) FROM auth_user WHERE is_active")[0]
    groups = fetch_one(
        "SELECT coalesce(string_agg(user_id || ':' || group_id, ','"
        " ORDER BY user_id, group_id), '') FROM auth_user_groups"
    )[0]
    return {**counts, "active": active, "groups": groups}


def row_name(address: str) -> Permission | None:
    view = resolve(address).func
    found: Permission | None = getattr(view, "cucumber_permission", None)
    return found


@pytest.fixture
def target() -> User:
    """The account the Staff pages act on."""
    return make_staff("pim", "tech", PASSWORD)


# ------------------------------------------------------------------- AC15
def test_every_page_but_the_open_ones_names_its_matrix_row() -> None:
    missing = [
        f"{name} {address}"
        for name, address in every_page()
        if name not in OPEN_PAGES and row_name(address) is None
    ]

    assert missing == []


def test_every_named_row_is_a_matrix_row() -> None:
    for name, address in every_page():
        if name not in OPEN_PAGES:
            assert row_name(address) in ROWS, name


# Design §7, typed in again, so a page can't pass with the wrong row.
PAGE_ROWS = {
    "home": Permission.OWN_ACCOUNT,
    "logout": Permission.OWN_ACCOUNT,
    "password": Permission.OWN_ACCOUNT,
    "account": Permission.OWN_ACCOUNT,  # U0.10a Q3 a)
    "practice": Permission.OWN_ACCOUNT,  # U0.10a Q4 a), design §13
    "staff": Permission.MANAGE_USERS,
    "staff_new": Permission.MANAGE_USERS,
    "staff_detail": Permission.MANAGE_USERS,
    "staff_deactivate": Permission.MANAGE_USERS,
    "staff_reactivate": Permission.MANAGE_USERS,
    "staff_new_password": Permission.MANAGE_USERS,
    "staff_role": Permission.MANAGE_USERS,
    "staff_unlock": Permission.MANAGE_USERS,
}


def test_each_page_has_the_row_the_design_gives_it() -> None:
    rows = {
        name: row_name(address)
        for name, address in every_page()
        if name not in OPEN_PAGES
    }

    assert rows == PAGE_ROWS


@override_settings(ROOT_URLCONF="cucumber.accounts.tests.urls")
def test_the_test_only_save_page_has_a_row_too() -> None:
    """It stands in for a page that saves, so the walk covers it (§3.2)."""
    assert row_name("/test-only/save/") == Permission.LOG_WORK


@override_settings(ROOT_URLCONF="cucumber.accounts.tests.urls_without_row")
def test_a_page_without_a_row_is_refused_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Forgetting a row closes the page instead of opening it (§3.1)."""
    client = client_for(person(Role.ADMIN))

    with caplog.at_level(logging.ERROR, logger="cucumber"):
        response = client.get(NO_ROW_PAGE)

    assert response.status_code == 403
    assert any(
        record.levelno == logging.ERROR
        and record.getMessage().startswith("page has no permission view=")
        for record in caplog.records
    )


# ----------------------------------------------------- AC14: every page × role
@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("role", ROLES, ids=str)
@pytest.mark.parametrize(("name", "route"), guarded_routes())
def test_each_role_opens_exactly_the_pages_its_row_allows(
    name: str, route: str, role: Role | None, method: str, target: User
) -> None:
    address = route.format(id=target.pk)
    permission = row_name(address)
    allowed = permission is not None and role in ROWS[permission].allowed
    client = client_for(person(role))
    before = accounts_snapshot()

    response: Response = getattr(client, method)(address)

    if allowed:
        assert response.status_code != 403, f"{method.upper()} {address}"
    else:
        assert response.status_code == 403, f"{method.upper()} {address}"
        assert NO_ACCESS in text(response)
        assert accounts_snapshot() == before


# --------------------------------------------------------------- AC10
def test_the_403_page_says_so_plainly_on_the_base_page() -> None:
    response = client_for(person(Role.TECH)).get(STAFF)

    assert response.status_code == 403
    html = text(response)
    assert NO_ACCESS in html
    assert "Signed in as" in html
    assert 'href="/"' in html
    assert "manage_users" not in html  # nothing about which row refused


@override_settings(ENVIRONMENT="staging")
def test_the_403_page_shows_the_practice_banner_on_staging() -> None:
    response = client_for(person(Role.TECH)).get(STAFF)

    assert "PRACTICE DATA" in text(response)


def test_an_htmx_request_gets_403_too() -> None:
    client = client_for(person(Role.READ_ONLY))

    response = client.post(f"{STAFF}new/", headers=htmx_headers())

    assert response.status_code == 403
    assert "HX-Redirect" not in response


def test_a_refused_form_saves_nothing() -> None:
    client = client_for(person(Role.SUPERVISOR))
    before = accounts_snapshot()

    response = client.post(f"{STAFF}new/", {"name": "Mali", "email": "m@x.com"})

    assert response.status_code == 403
    assert accounts_snapshot() == before


def test_a_refused_page_is_logged_with_ids_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tech = person(Role.TECH)

    with caplog.at_level(logging.INFO, logger="cucumber.accounts"):
        client_for(tech).get(STAFF)

    assert f"page refused account={tech.pk} permission=manage_users" in (
        caplog.messages
    )


def test_a_deactivated_person_with_an_open_session_goes_to_login() -> None:
    """Django signs them out first; they never reach the role check (§3.1)."""
    gene = person(Role.TECH)
    client = client_for(gene)
    switch_off(gene)

    response = client.get(HOME)

    assert response.status_code == 302
    assert redirect_target(response)[0] == LOGIN


# --------------------------------------------------------------- AC11
@pytest.mark.parametrize("role", ROLES, ids=str)
def test_every_page_knows_what_the_person_may_do(role: Role | None) -> None:
    response = client_for(person(role)).get(HOME)

    assert response.context["allowed"] == {
        row.permission for row in MATRIX if role in row.allowed
    }


@pytest.mark.parametrize("role", ROLES, ids=str)
def test_home_shows_the_staff_link_only_to_those_who_manage_users(
    role: Role | None,
) -> None:
    html = text(client_for(person(role)).get(HOME))

    assert ('href="/staff/"' in html) is (role == Role.ADMIN)


def test_the_login_page_has_an_empty_allowed_set() -> None:
    """Pages that skip the role check still render (§3.3)."""
    response = Client().get(LOGIN)

    assert response.status_code == 200
    assert response.context["allowed"] == frozenset()


# --------------------------------------------------------------- AC5
def test_a_role_taken_away_applies_on_the_very_next_page() -> None:
    owner = make_staff("jade", "admin", PASSWORD)
    second = make_staff("mali", "admin", PASSWORD)
    client = client_for(second)
    assert client.get(STAFF).status_code == 200

    set_role(owner, second, Role.TECH)

    assert client.get(STAFF).status_code == 403


def test_a_role_given_applies_on_the_very_next_page() -> None:
    owner = make_staff("jade", "admin", PASSWORD)
    gene = make_staff("gene", "tech", PASSWORD)
    client = client_for(gene)
    assert client.get(STAFF).status_code == 403

    set_role(owner, gene, Role.ADMIN)

    assert client.get(STAFF).status_code == 200


def test_nothing_about_the_role_is_kept_in_the_session() -> None:
    client = client_for(person(Role.TECH))
    client.get(HOME)

    stored = dict(client.session.items())

    role_names = {str(role) for role in Role}
    assert not any("role" in key for key in stored)
    assert not any(str(value) in role_names for value in stored.values())
