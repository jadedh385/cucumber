"""AC10, AC31 and design §3: the two new tables, their grants, the `admin`
group and the two rules on `auth_user`.

Plain SQL with the design's names, as the U0.2a schema tests do.
"""

import importlib
from types import ModuleType

import psycopg
import pytest
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction

from cucumber.accounts.tests.helpers import mark_change_due
from cucumber.core.tests.rows import fetch_all, fetch_one, refused_by, run
from cucumber.core.tests.stock import make_staff
from cucumber.core.tests.trail import as_system

pytestmark = pytest.mark.django_db

AppConnection = psycopg.Connection[tuple[object, ...]]
RIGHTS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
LOCK_TABLE = "accounts_login_failure"
CHANGE_TABLE = "accounts_password_change_due"
NO_SUPERUSER = "auth_user_no_superuser"
USERNAME_IS_EMAIL = "auth_user_username_is_email"


def migration(name: str) -> ModuleType:
    return importlib.import_module(f"cucumber.accounts.migrations.{name}")


def columns(table: str) -> dict[str, tuple[str, str]]:
    rows = fetch_all(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = %s",
        [table],
    )
    return {str(name): (str(kind), str(nullable)) for name, kind, nullable in rows}


def app_rights(table: str) -> set[str]:
    return {
        right
        for right in RIGHTS
        if fetch_one(
            "SELECT has_table_privilege('cucumber_app', %s, %s)", [table, right]
        )
        == (True,)
    }


# ------------------------------------------------------------- §3.1, §3.2
def test_the_failure_table_holds_only_email_address_and_time() -> None:
    """Never the password typed (AC7)."""
    assert columns(LOCK_TABLE) == {
        "id": ("bigint", "NO"),
        "email_key": ("character varying", "NO"),
        "address": ("inet", "YES"),
        "at": ("timestamp with time zone", "NO"),
    }


def test_the_failure_table_is_indexed_for_both_counts() -> None:
    definitions = " ".join(
        str(row[0])
        for row in fetch_all(
            "SELECT indexdef FROM pg_indexes WHERE tablename = %s", [LOCK_TABLE]
        )
    )

    assert "(email_key, at)" in definitions
    assert "(address, at)" in definitions


def test_the_failure_time_defaults_to_now() -> None:
    run(f"INSERT INTO {LOCK_TABLE} (email_key) VALUES ('gene@example.com')")  # noqa: S608

    assert fetch_one(f"SELECT at IS NOT NULL FROM {LOCK_TABLE}") == (True,)  # noqa: S608


def test_the_failure_table_counts_unknown_emails_too() -> None:
    """No foreign key to auth_user, so a made-up email is counted (AC8)."""
    run(f"INSERT INTO {LOCK_TABLE} (email_key) VALUES ('nobody@example.com')")  # noqa: S608

    assert fetch_one(f"SELECT count(*) FROM {LOCK_TABLE}") == (1,)  # noqa: S608


def test_the_change_due_table_is_one_row_per_account() -> None:
    assert columns(CHANGE_TABLE) == {
        "user_id": ("integer", "NO"),
        "since": ("timestamp with time zone", "NO"),
    }
    primary_key = fetch_one(
        "SELECT a.attname FROM pg_index i"
        " JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)"
        " WHERE i.indrelid = %s::regclass AND i.indisprimary",
        [CHANGE_TABLE],
    )
    assert primary_key == ("user_id",)


@pytest.mark.parametrize("table", [LOCK_TABLE, CHANGE_TABLE])
def test_the_app_may_add_and_remove_rows_but_never_edit_them(table: str) -> None:
    assert app_rights(table) == {"SELECT", "INSERT", "DELETE"}


def test_the_app_user_really_cannot_edit_a_failure(app_db: AppConnection) -> None:
    app_db.execute(f"INSERT INTO {LOCK_TABLE} (email_key) VALUES ('g@example.com')")  # noqa: S608

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_db.execute(f"UPDATE {LOCK_TABLE} SET at = now()")  # noqa: S608


# ------------------------------------------------------------------ §3.3
def test_the_admin_group_exists_after_migrating() -> None:
    assert Group.objects.filter(name="admin").count() == 1


def test_adding_the_admin_group_twice_still_leaves_one() -> None:
    """A re-run after an undo finds the group (§3.3)."""
    add_group = migration("0002_admin_group").add_admin_group

    add_group(apps, None)
    add_group(apps, None)

    assert Group.objects.filter(name="admin").count() == 1


# ------------------------------------------------------------ AC31 §3.4
def test_no_account_can_be_made_a_superuser_even_by_the_owner() -> None:
    gene = make_staff("gene", "tech")

    for flag in ["is_superuser", "is_staff"]:
        with refused_by(NO_SUPERUSER):
            run(f"UPDATE auth_user SET {flag} = true WHERE id = %s", [gene.pk])  # noqa: S608


def test_djangos_create_superuser_is_refused() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_superuser(
            username="root@example.com", email="root@example.com", password=None
        )


@pytest.mark.parametrize(
    ("username", "email"),
    [
        ("Gene@example.com", "Gene@example.com"),  # capitals
        (" gene@example.com", " gene@example.com"),  # spaces
        ("gene@example.com", "other@example.com"),  # two different emails
        ("gene@example.com", ""),  # email missing
        ("gene", "gene"),  # U0.3-style user name
    ],
)
def test_the_user_name_must_be_the_lowercase_email(username: str, email: str) -> None:
    gene = make_staff("gene", "tech")

    with refused_by(USERNAME_IS_EMAIL):
        run(
            "UPDATE auth_user SET username = %s, email = %s WHERE id = %s",
            [username, email, gene.pk],
        )


def test_the_app_user_meets_the_same_rules(
    transactional_db: None, app_db: AppConnection
) -> None:
    gene = make_staff("gene", "tech")

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        app_db.execute(
            "UPDATE auth_user SET is_superuser = true WHERE id = %s", [gene.pk]
        )
    assert caught.value.diag.constraint_name == NO_SUPERUSER

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        app_db.execute("UPDATE auth_user SET is_staff = true WHERE id = %s", [gene.pk])
    assert caught.value.diag.constraint_name == NO_SUPERUSER

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        app_db.execute(
            "INSERT INTO auth_user (username, email, password, is_superuser,"
            " is_staff, is_active, first_name, last_name, date_joined)"
            " VALUES ('root@example.com', 'root@example.com', '', true, false,"
            " true, '', '', now())"
        )
    assert caught.value.diag.constraint_name == NO_SUPERUSER

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        app_db.execute(
            "UPDATE auth_user SET username = 'GENE@example.com' WHERE id = %s",
            [gene.pk],
        )
    assert caught.value.diag.constraint_name == USERNAME_IS_EMAIL


def test_the_app_user_still_cannot_delete_an_account(
    transactional_db: None, app_db: AppConnection
) -> None:
    gene = make_staff("gene", "tech")

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_db.execute("DELETE FROM auth_user WHERE id = %s", [gene.pk])


# ---------------------------------------------------- 0003's pre-check
def test_the_pre_check_names_accounts_that_would_break_the_rules() -> None:
    """Instead of a raw constraint error at G5 on staging or production."""
    run(
        f"ALTER TABLE auth_user DROP CONSTRAINT IF EXISTS {NO_SUPERUSER},"
        f" DROP CONSTRAINT IF EXISTS {USERNAME_IS_EMAIL}"
    )
    with as_system():
        User.objects.create_user(username="Supervisor_1")
        User.objects.create_user(
            username="root@example.com", email="root@example.com", is_superuser=True
        )
    make_staff("gene", "tech")

    with pytest.raises(RuntimeError) as caught:
        migration("0003_auth_user_rules").refuse_bad_accounts(apps, None)

    assert "Supervisor_1" in str(caught.value)
    assert "root@example.com" in str(caught.value)
    assert "gene@example.com" not in str(caught.value)


def test_the_pre_check_passes_when_every_account_is_fine() -> None:
    make_staff("gene", "tech")

    migration("0003_auth_user_rules").refuse_bad_accounts(apps, None)


# ------------------------------------------------------- G4 review (M4, M5)
def test_the_failure_table_is_indexed_by_time_for_the_tidy_up() -> None:
    """The day-old clean-up deletes by `at` alone (G4 M4)."""
    definitions = [
        str(row[0])
        for row in fetch_all(
            "SELECT indexdef FROM pg_indexes WHERE tablename = %s", [LOCK_TABLE]
        )
    ]

    assert any(definition.endswith("(at)") for definition in definitions)


def test_undoing_the_tables_is_allowed_when_no_change_is_due() -> None:
    migration("0001_initial").refuse_undo_while_change_due(apps, None)


def test_undoing_the_tables_is_refused_while_a_change_is_due() -> None:
    """Dropping the marks would let a temporary password stay for good (G4 M5)."""
    gene = make_staff("gene", "tech")
    mark_change_due(gene)

    with pytest.raises(RuntimeError, match=CHANGE_TABLE):
        migration("0001_initial").refuse_undo_while_change_due(apps, None)


def test_the_undo_check_runs_before_anything_is_dropped() -> None:
    """Undo runs operations last-first, so the check must be the last one."""
    last = migration("0001_initial").Migration.operations[-1]

    assert last.reverse_code is migration("0001_initial").refuse_undo_while_change_due
