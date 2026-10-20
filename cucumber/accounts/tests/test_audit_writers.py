"""AC4–AC6, AC10: every writer names its person (design §3.3, §5.4).

One test per row of §3.3: the account services, the own-password page,
logging in, `cucumber_admin`, `cucumber_flag`, the event services and
`reclassify_genus`. Each checks `actor_id` and `via` (and the reason where
one is needed). The plain log lines stay as well (test_log_lines.py).
"""

import uuid
from io import StringIO
from typing import Any

import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, override_settings
from waffle.models import Flag

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import (
    add_account,
    deactivate,
    give_new_password,
    lift_lock,
    reactivate,
    set_role,
)
from cucumber.accounts.tests.helpers import (
    NEW_PASSWORD,
    PASSWORD,
    PASSWORD_PAGE,
    add_failures,
    log_in,
)
from cucumber.accounts.tests.test_cucumber_admin import Answers, run_command
from cucumber.core.audit import Reason
from cucumber.core.tests.rows import make_batch, make_plant
from cucumber.core.tests.stock import intake_into_new_batch, make_staff
from cucumber.core.tests.trail import (
    LEFT_COMPANY,
    AuditRow,
    as_system,
    audit_mark,
    audit_rows_since,
    only_row,
    system_id,
)
from cucumber.events.services import close, split
from cucumber.plants.services import reclassify_genus

pytestmark = pytest.mark.django_db

MASKED_ON_INSERT = {
    "password": "set",
    "username": "set",
    "email": "set",
    "first_name": "set",
    "last_name": "set",
}
PASSWORD_CHANGED = {"password": "changed"}


class OneRoundPBKDF2(PBKDF2PasswordHasher):
    """Django's default hasher, made fast; MD5 hashes upgrade to it at login."""

    iterations = 1


UPGRADING_HASHERS = [
    "cucumber.accounts.tests.test_audit_writers.OneRoundPBKDF2",
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


def who(rows: list[AuditRow]) -> set[tuple[int | None, str]]:
    return {(row.actor_id, row.via) for row in rows}


def shape(rows: list[AuditRow]) -> list[tuple[str, str, str]]:
    return [(row.table_name, row.action, row.row_pk) for row in rows]


# ------------------------------------------------------- the Staff pages
def test_adding_an_account_is_an_account_row_and_a_role_row(owner: User) -> None:
    mark = audit_mark()

    mali = add_account(owner, "Mali", "mali@example.com", Role.TECH).account

    rows = audit_rows_since(mark)
    assert shape(rows) == [
        ("auth_user", "insert", str(mali.pk)),
        ("auth_user_groups", "insert", str(mali.pk)),
    ]
    assert who(rows) == {(owner.pk, "app")}
    assert rows[0].after is not None
    personal = {k: v for k, v in rows[0].after.items() if k in MASKED_ON_INSERT}
    assert personal == MASKED_ON_INSERT
    tech = Group.objects.get(name="tech")
    assert rows[1].after == {"user_id": mali.pk, "group_id": tech.pk}


def test_changing_a_role_is_a_delete_and_an_insert_together(
    owner: User, gene: User
) -> None:
    """Design §4.1, review L3: two rows in one transaction, keyed by the account."""
    mark = audit_mark()

    set_role(owner, gene, Role.SUPERVISOR)

    rows = audit_rows_since(mark)
    groups = {name: Group.objects.get(name=name).pk for name in ("tech", "supervisor")}
    assert shape(rows) == [
        ("auth_user_groups", "delete", str(gene.pk)),
        ("auth_user_groups", "insert", str(gene.pk)),
    ]
    assert rows[0].before == {"user_id": gene.pk, "group_id": groups["tech"]}
    assert rows[1].after == {"user_id": gene.pk, "group_id": groups["supervisor"]}
    assert who(rows) == {(owner.pk, "app")}
    assert rows[0].at == rows[1].at


def test_deactivating_names_the_admin_and_the_reason(owner: User, gene: User) -> None:
    mark = audit_mark()

    deactivate(owner, gene, Reason(LEFT_COMPANY, "moved to Chiang Mai"))

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via) == (owner.pk, "app")
    assert (row.before, row.after) == ({"is_active": True}, {"is_active": False})
    assert (row.reason_code, row.note) == (LEFT_COMPANY, "moved to Chiang Mai")


def test_reactivating_names_the_admin_and_needs_no_reason(
    owner: User, gene: User
) -> None:
    deactivate(owner, gene, Reason(LEFT_COMPANY))
    mark = audit_mark()

    reactivate(owner, gene)

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via, row.reason_code) == (owner.pk, "app", None)
    assert (row.before, row.after) == ({"is_active": False}, {"is_active": True})


def test_a_new_password_shows_only_that_it_changed(owner: User, gene: User) -> None:
    mark = audit_mark()

    give_new_password(owner, gene)

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via) == (owner.pk, "app")
    assert (row.before, row.after) == (PASSWORD_CHANGED, PASSWORD_CHANGED)


def test_lifting_a_lock_writes_its_own_row_with_counts_only(
    owner: User, gene: User
) -> None:
    """Design §5.4: nothing in an audited table changes, so the service writes it."""
    add_failures("gene@example.com", 5)
    add_failures("someone@example.com", 50)  # the same network, now locked too
    mark = audit_mark()

    lift_lock(owner, gene)

    [row] = audit_rows_since(mark)
    assert (row.action, row.table_name, row.row_pk) == (
        "lock_lifted",
        "auth_user",
        str(gene.pk),
    )
    assert (row.actor_id, row.via) == (owner.pk, "app")
    assert (row.before, row.after) == (
        None,
        {"failures_cleared": 5, "networks_lifted": 1},
    )


# ------------------------------------------------------ the person's own
def test_changing_your_own_password_names_you(gene: User, gene_client: Client) -> None:
    mark = audit_mark()

    gene_client.post(
        PASSWORD_PAGE,
        {
            "old_password": PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via) == (gene.pk, "app")
    assert (row.before, row.after) == (PASSWORD_CHANGED, PASSWORD_CHANGED)


def test_a_plain_login_writes_nothing(gene: User) -> None:
    """`last_login` is left out (design §4.3); logins stay in the app log."""
    mark = audit_mark()

    log_in(Client(), "gene@example.com")

    assert audit_rows_since(mark) == []


def test_a_password_re_hashed_at_login_is_recorded_as_system(gene: User) -> None:
    """After a Django upgrade the login itself rewrites the hash (design §4.3)."""
    mark = audit_mark()

    with override_settings(PASSWORD_HASHERS=UPGRADING_HASHERS):
        response = log_in(Client(), "gene@example.com")

    assert response.status_code == 302, "the login must still work"
    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via) == (system_id(), "login")
    assert row.after == PASSWORD_CHANGED
    assert User.objects.get(pk=gene.pk).password.startswith("pbkdf2_sha256$")


# ------------------------------------------------------- SSH commands (AC6)
def test_cucumber_admin_adding_the_first_admin_is_system(db: None) -> None:
    mark = audit_mark()

    run_command(Answers("jade@example.com"))

    rows = audit_rows_since(mark)
    jade = User.objects.get(username="jade@example.com")
    assert shape(rows) == [
        ("auth_user", "insert", str(jade.pk)),
        ("auth_user_groups", "insert", str(jade.pk)),
    ]
    assert who(rows) == {(system_id(), "cucumber_admin")}


def test_cucumber_admin_letting_the_owner_back_in_is_system(owner: User) -> None:
    mark = audit_mark()

    run_command(Answers("jade@example.com"))

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via) == (system_id(), "cucumber_admin")
    assert row.after == PASSWORD_CHANGED


def make_flag(name: str) -> Any:
    """Every field off, as a feature's migration makes it (Waffle's own
    default has `superusers` on, which `cucumber_flag` would switch off)."""
    with as_system():
        return Flag.objects.create(name=name, everyone=False, superusers=False)


def cucumber_flag(*args: str) -> None:
    call_command("cucumber_flag", *args, stdout=StringIO())


def test_switching_a_flag_is_system_via_cucumber_flag(db: None) -> None:
    """AC10 (U0.4a flags), AC6."""
    flag = make_flag("lab_screens")
    mark = audit_mark()

    cucumber_flag("lab_screens", "on")

    row = only_row(mark, "waffle_flag")
    assert (row.actor_id, row.via, row.row_pk) == (
        system_id(),
        "cucumber_flag",
        str(flag.pk),
    )
    assert (row.before, row.after) == ({"everyone": False}, {"everyone": True})


def test_a_flag_on_for_a_group_is_keyed_by_the_flag(db: None) -> None:
    flag = make_flag("lab_screens")
    tech = Group.objects.get(name="tech")
    mark = audit_mark()

    cucumber_flag("lab_screens", "on", "--group", "tech")

    row = only_row(mark, "waffle_flag_groups")
    assert (row.action, row.row_pk) == ("insert", str(flag.pk))
    assert row.after == {"flag_id": flag.pk, "group_id": tech.pk}
    assert who(audit_rows_since(mark)) == {(system_id(), "cucumber_flag")}


# ------------------------------------------------- events and plants (§3.3)
@pytest.fixture
def plant(admin: User) -> int:
    with as_system():
        return make_plant(admin.pk)


def test_a_new_batch_is_one_insert_by_who_saved_it(admin: User, plant: int) -> None:
    """`save_once`; the projection's refresh right after writes nothing (AC7)."""
    mark = audit_mark()

    batch = intake_into_new_batch(admin, plant, 10)

    rows = audit_rows_since(mark)
    assert shape(rows) == [("batches", "insert", str(batch))]
    assert who(rows) == {(admin.pk, "app")}


def test_a_split_names_who_saved_it(admin: User, plant: int) -> None:
    parent = intake_into_new_batch(admin, plant, 10)
    mark = audit_mark()

    saved = split(uuid.uuid4(), admin, parent, 3, "half the jars look different")

    rows = audit_rows_since(mark)
    child = next(batch for batch in saved.batch_ids if batch != parent)
    assert shape(rows) == [("batches", "insert", str(child))]
    assert who(rows) == {(admin.pk, "app")}


def test_closing_a_batch_changes_only_projection_columns(
    admin: User, plant: int
) -> None:
    with as_system():
        empty = make_batch(plant, admin.pk)
    mark = audit_mark()

    close(uuid.uuid4(), admin, empty)

    assert audit_rows_since(mark) == []


def test_reclassifying_a_genus_names_the_admin(admin: User, plant: int) -> None:
    mark = audit_mark()

    reclassify_genus(admin, plant, "HYA")

    row = only_row(mark, "plants")
    assert (row.actor_id, row.via) == (admin.pk, "app")
    assert (row.before, row.after) == ({"genus_code": "PHL"}, {"genus_code": "HYA"})


def test_a_service_that_names_nobody_would_fail_its_own_test(owner: User) -> None:
    """Review H1: set-up as System doesn't leak into the code under test."""
    with as_system():
        pim = make_staff("pim", "tech")
    mark = audit_mark()

    give_new_password(owner, pim)

    assert who(audit_rows_since(mark)) == {(owner.pk, "app")}
