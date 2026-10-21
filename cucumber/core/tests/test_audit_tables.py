"""AC17 and design §4: every table is audited or deliberately not.

A new table can't ship unaudited by accident: it must be on `AUDITED` (and
have its trigger) or on `NOT_AUDITED` with a reason. The triggers' arguments
are pinned to design §4.1's table, so a trigger remade with every column
ignored fails here as well as in `cucumber_check_guards`.
"""

import pytest
from django.db.models import Field

from cucumber.batches.models import Batch
from cucumber.core.audit import AUDITED, NOT_AUDITED
from cucumber.core.tests.rows import fetch_all
from cucumber.core.tests.schema_spec import INSERT_ONLY_TABLES
from cucumber.events.writing import projected_columns

pytestmark = pytest.mark.django_db

# pg_trigger.tgtype bits.
ROW, BEFORE, INSERT, DELETE, UPDATE, TRUNCATE = 1, 2, 4, 8, 16, 32

# Design §4.1: (key column, ignored columns, masked columns) per table.
AUDIT_ARGUMENTS = {
    "plants": ("id", {"name_key"}, set()),
    "batches": (
        "id",
        {"live_count", "quarantined", "stage_code", "status", "closed_at", "voided_at"},
        set(),
    ),
    **{
        table: ("code", set(), set())
        for table in ["genera", "stages", "media_codes", "locations", "reasons"]
    },
    "vendors": ("zoho_contact_id", {"synced_at"}, set()),
    "auth_user": (
        "id",
        {"last_login"},
        {"password", "username", "email", "first_name", "last_name"},
    ),
    "auth_user_groups": ("user_id", {"id"}, set()),
    "waffle_flag": ("id", {"modified"}, set()),
    "waffle_flag_groups": ("flag_id", {"id"}, set()),
}
DELETES_AUDITED = {"auth_user_groups", "waffle_flag", "waffle_flag_groups"}

# Design §4.2: the column, then each "off" value and the reason list for it.
REASON_ARGUMENTS = {
    **{
        table: ("active", "false", "archive")
        for table in [
            "genera",
            "stages",
            "media_codes",
            "locations",
            "reasons",
            "vendors",
        ]
    },  # fmt: skip
    "auth_user": ("is_active", "false", "deactivate"),
    "plants": ("status", "retired", "retire", "voided", "void"),
}

NEW_FUNCTIONS = [
    "cucumber_audit",
    "cucumber_reason_required",
    "cucumber_truncate_noticed",
    "audit_log_stamp",
]


def public_tables() -> set[str]:
    rows = fetch_all("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {str(row[0]) for row in rows}


def trigger(name: str) -> tuple[str, str, int, tuple[str, ...]] | None:
    """(table, function, tgtype, arguments) of a trigger, or None."""
    rows = fetch_all(
        "SELECT c.relname, p.proname, t.tgtype, t.tgnargs, t.tgargs"
        " FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
        " JOIN pg_proc p ON p.oid = t.tgfoid"
        " WHERE t.tgname = %s AND NOT t.tgisinternal",
        [name],
    )
    if not rows:
        return None
    table, function, tgtype, count, raw = rows[0]
    assert isinstance(raw, bytes | memoryview)
    arguments = tuple(bytes(raw).decode().split("\x00")[: int(str(count))])
    return str(table), str(function), int(str(tgtype)), arguments


def as_set(argument: str) -> set[str]:
    return {column for column in argument.split(",") if column}


# ------------------------------------------------------------------- AC17
def test_every_table_is_audited_or_deliberately_not() -> None:
    assert sorted(public_tables() - AUDITED - set(NOT_AUDITED)) == []


def test_no_table_is_on_both_lists() -> None:
    assert sorted(AUDITED & set(NOT_AUDITED)) == []


def test_every_reason_for_not_auditing_is_written_down() -> None:
    assert [table for table, why in NOT_AUDITED.items() if not why.strip()] == []


@pytest.mark.parametrize("table", sorted(AUDITED))
def test_every_audited_table_has_its_audit_trigger(table: str) -> None:
    found = trigger(f"{table}_audit")

    assert found is not None, f"{table}_audit is missing"
    on, function, tgtype, _ = found
    assert (on, function) == (table, "cucumber_audit")
    assert tgtype & ROW and not tgtype & BEFORE, "AFTER … FOR EACH ROW"
    assert tgtype & INSERT and tgtype & UPDATE
    assert bool(tgtype & DELETE) == (table in DELETES_AUDITED)


@pytest.mark.parametrize("table", sorted(AUDITED))
def test_each_audit_trigger_reads_the_table_as_designed(table: str) -> None:
    """Design §4.1's table: key, ignored and masked columns (review M2)."""
    found = trigger(f"{table}_audit")
    assert found is not None

    key, ignored, masked = found[3]

    assert (key, as_set(ignored), as_set(masked)) == AUDIT_ARGUMENTS[table]


def test_a_batches_ignored_columns_are_exactly_the_projections() -> None:
    """AC7: `projected_columns()` plus `voided_at`, by column name (review L6)."""
    projected = projected_columns("intake", [], is_voided=False)
    fields = [Batch._meta.get_field(name) for name in projected]
    columns = {field.column for field in fields if isinstance(field, Field)}

    assert AUDIT_ARGUMENTS["batches"][1] == columns | {"voided_at"}


# ------------------------------------------------------------ reasons, §4.2
@pytest.mark.parametrize("table", sorted(REASON_ARGUMENTS))
def test_every_switch_off_needs_a_reason_in_the_database(table: str) -> None:
    found = trigger(f"{table}_reason_required")

    assert found is not None, f"{table}_reason_required is missing"
    on, function, tgtype, arguments = found
    assert (on, function) == (table, "cucumber_reason_required")
    assert tgtype & ROW and tgtype & BEFORE and tgtype & UPDATE
    assert arguments == REASON_ARGUMENTS[table]


# ------------------------------------------------------------ TRUNCATE, §4.4
@pytest.mark.parametrize("table", sorted({*INSERT_ONLY_TABLES, *AUDITED}))
def test_every_protected_table_notices_a_truncate(table: str) -> None:
    found = trigger(f"{table}_truncate_noticed")

    assert found is not None, f"{table}_truncate_noticed is missing"
    on, function, tgtype, _ = found
    assert (on, function) == (table, "cucumber_truncate_noticed")
    assert tgtype & TRUNCATE and not tgtype & ROW


def test_audit_rows_are_stamped_by_the_database() -> None:
    found = trigger("audit_log_stamp")

    assert found is not None
    on, function, tgtype, _ = found
    assert (on, function) == ("audit_log", "audit_log_stamp")
    assert tgtype & ROW and tgtype & BEFORE and tgtype & INSERT


def test_accounts_are_never_deleted() -> None:
    found = trigger("auth_user_no_delete")

    assert found is not None
    assert found[:2] == ("auth_user", "cucumber_no_delete")


# ---------------------------------------------------------- review M1
@pytest.mark.parametrize("function", NEW_FUNCTIONS)
def test_the_new_functions_fix_their_search_path_and_run_as_the_caller(
    function: str,
) -> None:
    rows = fetch_all(
        "SELECT prosecdef, proconfig FROM pg_proc p"
        " JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE proname = %s AND nspname = 'public'",
        [function],
    )

    assert rows, f"{function} is missing"
    [(security_definer, config)] = rows
    assert security_definer is False
    assert config == ["search_path=pg_catalog, public, pg_temp"]
