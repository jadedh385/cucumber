"""AC4–AC8: the database writes one audit row per change (design §4.1).

Plain SQL as the tables' owner, the way a script or a future screen would
write. `named_in_sql` names the person exactly as `audited()` does, with
`set_config(…, true)`. What `cucumber_app` may do is in
test_append_only_attacks.py; the services are in accounts' test_audit_writers.py.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction

from cucumber.core.tests.rows import (
    as_int,
    batch_values,
    db_now,
    fetch_one,
    insert,
    make_plant,
    make_user,
    plant_values,
    quote,
    refused_by,
    run,
)
from cucumber.core.tests.trail import (
    as_system,
    audit_mark,
    audit_rows_since,
    named_in_sql,
    only_row,
)

pytestmark = pytest.mark.django_db

OWNER_VIA = "sql as cucumber_owner"

# Design §4.1: columns left out of the trail, and columns shown only as
# "changed" ("set" on insert), by table.
IGNORED = {
    "plants": {"name_key"},
    "batches": {
        "live_count", "quarantined", "stage_code", "status", "closed_at",
        "voided_at",
    },
    "vendors": {"synced_at"},
    "auth_user": {"last_login"},
    "auth_user_groups": {"id"},
    "waffle_flag": {"modified"},
    "waffle_flag_groups": {"id"},
}  # fmt: skip
MASKED = {"auth_user": {"password", "username", "email", "first_name", "last_name"}}


@dataclass(frozen=True)
class Case:
    """How to add a row to an audited table, and a change that shows."""

    key: str
    make: Callable[[int], object]  # given a staff id, insert a row; its key
    change: dict[str, object] = field(default_factory=dict)


def new_flag(_: int) -> object:
    values = {
        "name": "audit_probe", "everyone": None, "percent": None,
        "testing": False, "superusers": False, "staff": False,
        "authenticated": False, "languages": "", "rollout": False, "note": "",
        "created": db_now(), "modified": db_now(),
    }  # fmt: skip
    return insert("waffle_flag", values)


def new_account(_: int) -> object:
    values = {
        "password": "!", "is_superuser": False, "username": "mali@example.com",
        "first_name": "Mali", "last_name": "", "email": "mali@example.com",
        "is_staff": False, "is_active": True, "date_joined": db_now(),
    }  # fmt: skip
    return insert("auth_user", values)


def new_plant(staff: int) -> object:
    return insert("plants", plant_values(staff, full_name="Audit Probe"))


def new_batch(staff: int) -> object:
    with as_system():
        plant = make_plant(staff, full_name="Batch Probe")
    return insert("batches", batch_values(plant, staff))


def new_reference(table: str, values: dict[str, object]) -> Callable[[int], object]:
    return lambda _: insert(table, values, "code")


def new_vendor(_: int) -> object:
    values = {
        "zoho_contact_id": "ZC-9",
        "name": "Green Leaf Co.",
        "active": True,
        "synced_at": db_now(),
    }
    return insert("vendors", values, "zoho_contact_id")


CASES = {
    "plants": Case("id", new_plant, {"notes": "moved to bench 4"}),
    "batches": Case("id", new_batch, {"location_code": "lab", "stage_code": "P2"}),
    "genera": Case(
        "code",
        new_reference("genera", {"code": "ALO", "name": "Aloe", "active": True}),
        {"name": "Aloe vera"},
    ),
    "stages": Case(
        "code",
        new_reference(
            "stages", {"code": "P9", "label": "P9", "sort_order": 99, "active": True}
        ),
        {"label": "P9 late"},
    ),
    "media_codes": Case(
        "code",
        new_reference("media_codes", {"code": "M999", "label": "M999", "active": True}),
        {"label": "M999 half strength"},
    ),
    "locations": Case(
        "code",
        new_reference("locations", {"code": "bench", "label": "Bench", "active": True}),
        {"label": "Bench 4"},
    ),
    "reasons": Case(
        "code",
        new_reference(
            "reasons",
            {"code": "void_spilled", "label": "Spilled", "applies_to": "void"},
        ),
        {"label": "Spilled jar"},
    ),
    "vendors": Case("zoho_contact_id", new_vendor, {"name": "Green Leaf Company"}),
    # Not `is_staff`: U0.5's auth_user_no_superuser refuses it before any
    # audit trigger runs. The time as the test connection (UTC) shows it.
    "auth_user": Case("id", new_account, {"date_joined": "2026-10-01T02:00:00+00:00"}),
    "waffle_flag": Case("id", new_flag, {"everyone": True}),
}
UPDATABLE = sorted(CASES)


@pytest.fixture
def staff() -> int:
    with as_system():
        return make_user("gene")


def row_json(table: str, key_column: str, key: object) -> dict[str, object]:
    """The row as `to_jsonb` gives it, as the trigger sees it."""
    value = fetch_one(
        f"SELECT to_jsonb(t) FROM {quote(table)} t"  # noqa: S608 (test names)
        f" WHERE {quote(key_column)} = %s",
        [key],
    )[0]
    loaded = value if isinstance(value, dict) else json.loads(str(value))
    assert isinstance(loaded, dict)
    return loaded


def set_columns(
    table: str, key_column: str, key: object, values: dict[str, object]
) -> None:
    assignments = ", ".join(f"{quote(column)} = %s" for column in values)
    run(
        f"UPDATE {quote(table)} SET {assignments}"  # noqa: S608 (test names)
        f" WHERE {quote(key_column)} = %s",
        [*values.values(), key],
    )


# ------------------------------------------------------------------ inserts
@pytest.mark.parametrize("table", UPDATABLE)
def test_an_insert_with_nobody_named_is_refused(table: str, staff: int) -> None:
    """AC5, AC6: the trail can't be skipped by forgetting to name anyone."""
    with refused_by("audit_actor_required"):
        CASES[table].make(staff)


@pytest.mark.parametrize("table", UPDATABLE)
def test_an_insert_writes_one_row_with_the_whole_new_row(
    table: str, staff: int
) -> None:
    """AC4: who, when (the database clock), which row, and `after`."""
    case = CASES[table]
    mark = audit_mark()

    with named_in_sql(staff, via="probe"):
        key = case.make(staff)

    row = only_row(mark, table)
    expected = {
        column: ("set" if column in MASKED.get(table, set()) else value)
        for column, value in row_json(table, case.key, key).items()
        if column not in IGNORED.get(table, set())
    }
    assert (row.actor_id, row.action, row.row_pk) == (staff, "insert", str(key))
    assert (row.before, row.after) == (None, expected)
    assert (row.via, row.reason_code, row.note) == ("probe", None, None)
    assert row.at == db_now()


# ------------------------------------------------------------------ updates
@pytest.mark.parametrize("table", UPDATABLE)
def test_an_update_with_nobody_named_is_refused(table: str, staff: int) -> None:
    case = CASES[table]
    with as_system():
        key = case.make(staff)
    unchanged = row_json(table, case.key, key)

    with refused_by("audit_actor_required"):
        set_columns(table, case.key, key, case.change)

    assert row_json(table, case.key, key) == unchanged


@pytest.mark.parametrize("table", UPDATABLE)
def test_an_update_writes_only_the_columns_that_changed(table: str, staff: int) -> None:
    """AC7, and the projection's own batch columns are left out."""
    case = CASES[table]
    with as_system():
        key = case.make(staff)
    old = row_json(table, case.key, key)
    mark = audit_mark()

    with named_in_sql(staff):
        set_columns(table, case.key, key, case.change)

    shown = {c for c in case.change if c not in IGNORED.get(table, set())}
    row = only_row(mark, table)
    assert (row.actor_id, row.action, row.row_pk) == (staff, "update", str(key))
    assert row.before == {column: old[column] for column in shown}
    assert row.after == {column: case.change[column] for column in shown}
    assert row.via == OWNER_VIA, "raw SQL that doesn't say how is marked"


@pytest.mark.parametrize("table", UPDATABLE)
def test_an_update_that_changes_nothing_writes_nothing_and_needs_nobody(
    table: str, staff: int
) -> None:
    """Design §4.1 step 3: Django's saves that change nothing stay silent."""
    case = CASES[table]
    with as_system():
        key = case.make(staff)
    old = row_json(table, case.key, key)
    mark = audit_mark()

    set_columns(table, case.key, key, {column: old[column] for column in case.change})

    assert audit_rows_since(mark) == []


IGNORED_ONLY: dict[str, dict[str, object]] = {
    "batches": {"live_count": 5},
    "vendors": {"synced_at": "2026-10-20T09:00:00+07:00"},
    "auth_user": {"last_login": "2026-10-20T09:00:00+07:00"},
    "waffle_flag": {"modified": "2026-10-20T09:00:00+07:00"},
}


@pytest.mark.parametrize("table", sorted(IGNORED_ONLY))
def test_a_change_to_ignored_columns_only_writes_nothing_and_needs_nobody(
    table: str, staff: int
) -> None:
    """A login's `last_login`, a projection refresh, the Zoho sync stamp."""
    case = CASES[table]
    with as_system():
        key = case.make(staff)
    mark = audit_mark()

    set_columns(table, case.key, key, IGNORED_ONLY[table])

    assert audit_rows_since(mark) == []


def test_a_plants_generated_name_key_is_left_out(staff: int) -> None:
    with as_system():
        plant = make_plant(staff)
    mark = audit_mark()

    with named_in_sql(staff):
        set_columns("plants", "id", plant, {"full_name": "Pink Princess II"})

    row = only_row(mark, "plants")
    assert row.before == {"full_name": "Pink Princess"}
    assert row.after == {"full_name": "Pink Princess II"}


# ------------------------------------------------------- personal data (AC8)
NEW_PERSONAL_VALUES = {
    "password": "md5$new$hash",
    "username": "gene.new@example.com",
    "email": "gene.new@example.com",
    "first_name": "Gene Two",
    "last_name": "Somchai",
}
# U0.5's auth_user_username_is_email: the two always change together.
CHANGED_WITH = {"username": {"username", "email"}, "email": {"username", "email"}}


@pytest.mark.parametrize("column", sorted(MASKED["auth_user"]))
def test_an_accounts_personal_columns_show_only_that_they_changed(
    column: str, staff: int
) -> None:
    new_value = NEW_PERSONAL_VALUES[column]
    columns = CHANGED_WITH.get(column, {column})
    mark = audit_mark()

    with named_in_sql(staff):
        set_columns("auth_user", "id", staff, dict.fromkeys(columns, new_value))

    row = only_row(mark, "auth_user")
    assert row.before == dict.fromkeys(columns, "changed")
    assert row.after == dict.fromkeys(columns, "changed")
    assert new_value not in json.dumps([row.before, row.after])


# ------------------------------------------------- roles and flag groups
def test_giving_a_role_is_an_insert_keyed_by_the_account(staff: int) -> None:
    tech = Group.objects.get(name="tech")
    mark = audit_mark()

    with named_in_sql(staff):
        insert("auth_user_groups", {"user_id": staff, "group_id": tech.pk})

    row = only_row(mark, "auth_user_groups")
    assert (row.action, row.row_pk) == ("insert", str(staff))
    assert row.after == {"user_id": staff, "group_id": tech.pk}


def test_taking_a_role_away_is_a_delete_keyed_by_the_account(staff: int) -> None:
    tech = Group.objects.get(name="tech")
    with as_system():
        insert("auth_user_groups", {"user_id": staff, "group_id": tech.pk})
    mark = audit_mark()

    with named_in_sql(staff):
        run("DELETE FROM auth_user_groups WHERE user_id = %s", [staff])

    row = only_row(mark, "auth_user_groups")
    assert (row.action, row.row_pk) == ("delete", str(staff))
    assert (row.before, row.after) == ({"user_id": staff, "group_id": tech.pk}, None)


def test_taking_a_role_away_with_nobody_named_is_refused(staff: int) -> None:
    tech = Group.objects.get(name="tech")
    with as_system():
        insert("auth_user_groups", {"user_id": staff, "group_id": tech.pk})

    with refused_by("audit_actor_required"):
        run("DELETE FROM auth_user_groups WHERE user_id = %s", [staff])


def test_a_flags_groups_are_keyed_by_the_flag(staff: int) -> None:
    """Review L2: one flag's history reads as one story."""
    tech = Group.objects.get(name="tech")
    with as_system():
        flag = as_int(new_flag(staff))
    mark = audit_mark()

    with named_in_sql(staff):
        insert("waffle_flag_groups", {"flag_id": flag, "group_id": tech.pk})
        run("DELETE FROM waffle_flag_groups WHERE flag_id = %s", [flag])

    rows = audit_rows_since(mark, "waffle_flag_groups")
    assert [(row.action, row.row_pk) for row in rows] == [
        ("insert", str(flag)),
        ("delete", str(flag)),
    ]


# ----------------------------------------------------- accounts stay (D-07)
def test_an_account_is_never_deleted(staff: int) -> None:
    """Design §4.4: `auth_user_no_delete`, even with a person named."""
    with named_in_sql(staff), refused_by("auth_user_no_delete"):
        run("DELETE FROM auth_user WHERE id = %s", [staff])

    assert User.objects.filter(pk=staff).exists()


# --------------------------------------- the change and its row go together
def test_when_the_audit_row_cant_be_saved_the_change_isnt_either(
    staff: int,
) -> None:
    """AC4: a person who doesn't exist can't be named, so nothing is saved."""
    with as_system():
        plant = make_plant(staff)

    with pytest.raises(IntegrityError), transaction.atomic():
        run("SET CONSTRAINTS ALL IMMEDIATE")
        with named_in_sql(staff + 100_000):
            set_columns("plants", "id", plant, {"notes": "never saved"})
    run("SET CONSTRAINTS ALL DEFERRED")

    assert row_json("plants", "id", plant)["notes"] == ""


# ---------------------------------------------- what the caller can't choose
def test_the_database_stamps_when_and_which_login_whatever_the_insert_says(
    staff: int,
) -> None:
    """Review M3, `audit_log_stamp`: a forged row still shows when and who wrote it."""
    mark = audit_mark()

    insert(
        "audit_log",
        {
            "actor_id": staff,
            "at": "2000-01-01T00:00:00+00:00",
            "table_name": "plants",
            "row_pk": "1",
            "action": "update",
            "via": "app",
            "db_user": "someone_else",
        },
    )

    [row] = audit_rows_since(mark)
    assert row.at == db_now()
    assert row.db_user == "cucumber_owner"


def test_only_a_truncate_row_may_have_nobody(staff: int) -> None:
    with refused_by("audit_log_actor_required"):
        insert(
            "audit_log",
            {"table_name": "plants", "row_pk": "1", "action": "update", "via": "app"},
        )


def test_an_unknown_action_is_refused(staff: int) -> None:
    with refused_by("audit_log_action_valid"):
        insert(
            "audit_log",
            {
                "actor_id": staff,
                "table_name": "plants",
                "row_pk": "1",
                "action": "edited",
                "via": "app",
            },
        )
