"""Every U0.5 flow works with only the app user's rights (design §3.2, §9).

The other tests run as the tables' owner. `cucumber_app` may add and remove
lock and change-due rows but never edit them, so an "update or create" that
passes as the owner would fail on the servers. Here Django's own connection
logs in as `cucumber_app` for the test, then back as the owner, so
pytest-django can empty the database afterwards.
"""

from collections.abc import Iterator

import pytest
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import Client

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import (
    add_account,
    deactivate,
    give_new_password,
    lift_lock,
    password_chosen,
    reactivate,
    set_role,
)
from cucumber.accounts.tests.helpers import (
    NEW_PASSWORD,
    PASSWORD,
    add_failures,
    change_due,
    failures,
    log_in,
    signed_in_as,
)
from cucumber.accounts.tests.test_cucumber_admin import Answers, run_command
from cucumber.core.tests.stock import make_staff
from cucumber.core.tests.trail import LEFT_THE_COMPANY
from cucumber.env import env

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def as_app_user() -> Iterator[None]:
    """Django's connection, as `cucumber_app`, until the test ends."""
    password = env("DB_APP_PASSWORD")
    if not password:
        pytest.fail("DB_APP_PASSWORD is not set: copy .env.example to .env")
    settings = connection.settings_dict
    owner = (settings["USER"], settings["PASSWORD"])
    connection.close()
    settings["USER"], settings["PASSWORD"] = "cucumber_app", password
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == ("cucumber_app",)
        yield
    finally:
        connection.close()
        settings["USER"], settings["PASSWORD"] = owner


@pytest.fixture
def people() -> tuple[User, User]:
    """The Owner and Gene, made as the owner before switching users."""
    for role in Role:  # the flush before this test removed the seeded groups
        Group.objects.get_or_create(name=role)
    return make_staff("jade", "admin", PASSWORD), make_staff("gene", "tech", PASSWORD)


def test_the_staff_page_actions(people: tuple[User, User], as_app_user: None) -> None:
    owner, gene = people
    add_failures("gene@example.com", 5)

    mali = add_account(owner, "Mali", "mali@example.com", Role.TECH).account
    set_role(owner, mali, Role.SUPERVISOR)  # U0.6: one row out, one row in
    set_role(owner, mali, None)
    give_new_password(owner, gene)
    give_new_password(owner, gene)  # a second one while the first is still due
    lift_lock(owner, gene)
    deactivate(owner, gene, LEFT_THE_COMPANY)
    reactivate(owner, gene)
    password_chosen(gene)

    assert not change_due(gene)
    assert failures("gene@example.com") == 0


def test_logging_in_counting_and_tidying_up(
    people: tuple[User, User], as_app_user: None
) -> None:
    _, gene = people
    stale = Client()
    log_in(stale, "gene@example.com")
    log_in(Client(), "gene@example.com", "not-the-password")
    client = Client()

    log_in(client, "gene@example.com")
    client.post(
        "/accounts/password/",
        {
            "old_password": PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert signed_in_as(client) == gene.pk
    assert failures("gene@example.com") == 0


def test_the_rescue_command(people: tuple[User, User], as_app_user: None) -> None:
    owner, _ = people
    add_failures("jade@example.com", 5)

    run_command(Answers("jade@example.com"))

    assert User.objects.get(pk=owner.pk).check_password(NEW_PASSWORD)
    assert failures("jade@example.com") == 0


def test_promoting_with_the_rescue_command(
    people: tuple[User, User], as_app_user: None
) -> None:
    """U0.6: the command replaces the Tech role with Admin (AC9)."""
    _, gene = people

    run_command(Answers("gene@example.com", "Gene", promote="y"))

    assert list(gene.groups.values_list("name", flat=True)) == ["admin"]
