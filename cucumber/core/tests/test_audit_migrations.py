"""Design §5: the three U0.7 migrations' pre-checks and guarded undos.

`references 0004` (the new reason lists), `accounts 0007` (System and the
anonymised rule) and `core 0006` (the trail). Each undo refuses once the
trail has used what it would remove, so going back past this release means
restoring the copy (§5.5).
"""

import importlib
import json
from types import ModuleType

import pytest
from django.apps import apps
from django.contrib.auth.models import User

from cucumber.core.tests.rows import fetch_one, insert, run
from cucumber.core.tests.trail import LEFT_COMPANY, as_system, empty_trail, system_id

pytestmark = pytest.mark.django_db

SYSTEM_EMAIL = "system@cucumber.invalid"


def migration(app: str, name: str) -> ModuleType:
    return importlib.import_module(f"cucumber.{app}.migrations.{name}")


def a_trail_row(**values: object) -> None:
    row = {
        "actor_id": system_id(),
        "table_name": "plants",
        "row_pk": "1",
        "action": "update",
        "after": json.dumps({"notes": "x"}),
        "via": "test",
    }
    insert("audit_log", row | values)


def grant_temp_to_public() -> None:
    run(
        "DO $$ BEGIN EXECUTE format('GRANT TEMP ON DATABASE %I TO PUBLIC',"
        " current_database()); END $$"
    )


def count(sql: str, params: list[object] | None = None) -> int:
    return int(str(fetch_one(sql, params)[0]))


# ------------------------------------------------------- references 0004
def test_the_reason_lists_cant_be_undone_once_the_trail_uses_one() -> None:
    a_trail_row(reason_code=LEFT_COMPANY)

    with pytest.raises(RuntimeError, match=LEFT_COMPANY):
        migration("references", "0004_reason_lists").unseed_lists(apps, None)

    assert count("SELECT count(*) FROM reasons WHERE code = %s", [LEFT_COMPANY]) == 1


def test_the_reason_lists_undo_removes_only_its_own_rows() -> None:
    migration("references", "0004_reason_lists").unseed_lists(apps, None)

    new_lists = "('deactivate', 'retire', 'archive')"
    assert count(f"SELECT count(*) FROM reasons WHERE applies_to IN {new_lists}") == 0  # noqa: S608
    assert count("SELECT count(*) FROM reasons WHERE applies_to = 'void'") > 0


def test_the_reason_lists_undo_names_a_later_table_that_still_points_at_one() -> None:
    """Review item 11: a clear refusal, not a raw foreign-key error."""
    run(
        "CREATE TABLE later_use (reason_code text REFERENCES reasons (code)"
        " DEFERRABLE INITIALLY DEFERRED)"
    )
    run("INSERT INTO later_use VALUES (%s)", [LEFT_COMPANY])

    with pytest.raises(RuntimeError, match="later_use"):
        migration("references", "0004_reason_lists").unseed_lists(apps, None)


def test_the_reason_lists_undo_leaves_other_deferred_checks_alone() -> None:
    """It runs the checks on `reasons` only, not every check in the session."""
    run(
        "CREATE TABLE elsewhere (id integer PRIMARY KEY, parent integer"
        " REFERENCES elsewhere (id) DEFERRABLE INITIALLY DEFERRED)"
    )
    run("INSERT INTO elsewhere VALUES (1, 99)")  # fails only at commit

    migration("references", "0004_reason_lists").unseed_lists(apps, None)

    assert count("SELECT count(*) FROM reasons WHERE applies_to = 'retire'") == 0
    run("DELETE FROM elsewhere")  # so the test's own clean-up check passes


# ---------------------------------------------------------- accounts 0007
def test_the_system_account_exists_after_migrating() -> None:
    row = fetch_one(
        "SELECT first_name, is_active, password LIKE '!%%'"
        " FROM auth_user WHERE username = %s",
        [SYSTEM_EMAIL],
    )

    assert row == ("System", False, True)


def test_the_pre_check_names_accounts_already_on_the_reserved_domain() -> None:
    """Instead of a raw constraint error on staging or production (§5.2)."""
    with as_system():
        User.objects.create(
            username="odd@cucumber.invalid", email="odd@cucumber.invalid"
        )
        User.objects.create(username="gene@example.com", email="gene@example.com")

    with pytest.raises(RuntimeError) as caught:
        migration("accounts", "0007_system_account").refuse_invalid_emails(apps, None)

    assert "odd@cucumber.invalid" in str(caught.value)
    assert "gene@example.com" not in str(caught.value)
    assert SYSTEM_EMAIL not in str(caught.value)


def test_the_pre_check_passes_when_only_system_is_there() -> None:
    migration("accounts", "0007_system_account").refuse_invalid_emails(apps, None)


def test_system_cant_be_removed_once_the_trail_names_it() -> None:
    a_trail_row()

    with pytest.raises(RuntimeError, match="System"):
        migration("accounts", "0007_system_account").remove_system_account(apps, None)

    assert User.objects.filter(username=SYSTEM_EMAIL).exists()


# -------------------------------------------------------------- core 0006
def test_the_trail_cant_be_undone_once_it_has_a_row() -> None:
    a_trail_row()

    with pytest.raises(RuntimeError, match="audit_log"):
        migration("core", "0006_audit_trail").refuse_if_audited(apps, None)


def test_the_trail_undo_is_allowed_while_it_is_empty() -> None:
    empty_trail()  # references 0008 writes its changes to the trail
    assert count("SELECT count(*) FROM audit_log") == 0

    migration("core", "0006_audit_trail").refuse_if_audited(apps, None)


def index_definition(name: str) -> str:
    return str(
        fetch_one("SELECT indexdef FROM pg_indexes WHERE indexname = %s", [name])[0]
    )


def test_the_guard_check_reads_the_trail_through_a_partial_index() -> None:
    """G4 review #10: each deploy looks for truncates, not at every row."""
    definition = index_definition("audit_log_notices")

    assert "(id)" in definition
    assert "truncate" in definition
    assert "guards_accepted" in definition
    assert "WHERE" in definition


def test_the_trail_has_a_time_and_id_index_for_reading_newest_first() -> None:
    assert "(at, id)" in index_definition("audit_log_at_id")


def test_a_revoke_that_changed_nothing_is_refused() -> None:
    """Review item 11: `REVOKE TEMP` by a non-owner only warns.

    The tests' login owns the database, so a REVOKE that does nothing is
    stood in for by a statement that does nothing.
    """
    revoke_temp = migration("core", "0006_audit_trail").REVOKE_TEMP
    assert "'REVOKE TEMP ON DATABASE %I FROM PUBLIC'" in revoke_temp
    does_nothing = revoke_temp.replace("REVOKE TEMP ON", "COMMENT ON")
    grant_temp_to_public()

    with pytest.raises(Exception, match="could not revoke TEMP"):
        run(does_nothing.replace("FROM PUBLIC'", "IS NULL'"))


def test_the_real_revoke_leaves_public_without_temp() -> None:
    grant_temp_to_public()

    run(migration("core", "0006_audit_trail").REVOKE_TEMP)
