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

from cucumber.core.tests.rows import fetch_one, insert
from cucumber.core.tests.trail import LEFT_COMPANY, as_system, system_id

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
    assert count("SELECT count(*) FROM audit_log") == 0

    migration("core", "0006_audit_trail").refuse_if_audited(apps, None)
