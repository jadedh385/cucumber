# ruff: noqa: S608 (the SQL is built from the tests' own table names and ids)
"""AC1–AC3, AC16: attacking the history and the trail from outside.

Every append-only table × UPDATE, DELETE and TRUNCATE × {`cucumber_app` by
raw SQL, the owner by raw SQL, the Django ORM}: refused, and the row is
unchanged. The owner's TRUNCATE is the accepted exception (U0.2a G4): it is
noticed, not refused (design §4.4, spec wording change AC16).

Every audited table, written by raw SQL as `cucumber_app`: refused with
nobody named, and exactly one audit row per write with someone named.
"""

import psycopg
import pytest
from django.db import models, transaction

from cucumber.core.audit import AUDITED
from cucumber.core.models import AuditLog
from cucumber.core.tests.rows import (
    AppConnection,
    as_int,
    db_now,
    fetch_one,
    insert,
    issue_sku,
    make_batch,
    make_event,
    make_operation,
    make_plant,
    make_review,
    make_user,
    quote,
    refused_by,
    rule_name,
    run,
)
from cucumber.core.tests.schema_spec import INSERT_ONLY_TABLES
from cucumber.core.tests.stock import restore_reference_rows
from cucumber.core.tests.trail import (
    as_system,
    audit_mark,
    audit_rows_since,
    restore_audit_rows,
)
from cucumber.events.models import Event, EventReview, Operation
from cucumber.plants.models import PlantStatusChange, Sku

# A harmless column to "update" on each append-only table.
UNCHANGED_COLUMN = {
    "events": "note",
    "operations": "recorded_at",
    "event_reviews": "note",
    "plant_status_changes": "reason",
    "skus": "assigned_at",
    "audit_log": "note",
}
MODELS: dict[str, type[models.Model]] = {
    "events": Event,
    "operations": Operation,
    "event_reviews": EventReview,
    "plant_status_changes": PlantStatusChange,
    "skus": Sku,
    "audit_log": AuditLog,
}
KEY_COLUMN = {"skus": "sku"}


def base_rows() -> tuple[int, int]:
    """A staff member and a plant, made as System; (user id, plant id)."""
    with as_system():
        user = make_user("gene")
        return user, make_plant(user)


def one_row_in(table: str, user: int, plant: int) -> object:
    """A fresh row in `table` that nothing else points at; its key."""
    if table == "operations":
        return make_operation(user)
    if table == "skus":
        issue_sku(plant, "PHL009", user)
        return "PHL009"
    if table == "plant_status_changes":
        values = {
            "plant_id": plant,
            "from_status": "collection",
            "to_status": "collection",
            "sku_assigned": None,
            "changed_by": user,
            "changed_at": db_now(),
            "reason": None,
        }
        return insert("plant_status_changes", values)
    if table == "audit_log":
        values = {
            "actor_id": user,
            "table_name": "plants",
            "row_pk": str(plant),
            "action": "update",
            "via": "app",
        }
        return insert("audit_log", values)
    with as_system():
        batch = make_batch(plant, user)
    event = make_event(batch, user, "count", counted_qty=0)
    if table == "events":
        return event
    with as_system():
        reviewer = make_user("supervisor")
    return make_review(event, reviewer)


def fresh_row(table: str) -> object:
    return one_row_in(table, *base_rows())


def snapshot(table: str, key: object) -> tuple[object, ...]:
    return fetch_one(
        f"SELECT to_jsonb(t)::text FROM {quote(table)} t"  # noqa: S608 (test names)
        f" WHERE {where(table)}",
        [key],
    )


def where(table: str) -> str:
    return f"{quote(KEY_COLUMN.get(table, 'id'))} = %s"


# --------------------------------------------- the owner, by raw SQL (AC2)
@pytest.mark.django_db
@pytest.mark.parametrize("table", INSERT_ONLY_TABLES)
def test_the_owner_cant_update_a_past_row(table: str) -> None:
    key = fresh_row(table)
    before = snapshot(table, key)
    column = quote(UNCHANGED_COLUMN[table])

    with refused_by(f"{table}_append_only"):
        run(
            f"UPDATE {quote(table)} SET {column} = {column}"  # noqa: S608
            f" WHERE {where(table)}",
            [key],
        )

    assert snapshot(table, key) == before


@pytest.mark.django_db
@pytest.mark.parametrize("table", INSERT_ONLY_TABLES)
def test_the_owner_cant_delete_a_past_row(table: str) -> None:
    key = fresh_row(table)
    before = snapshot(table, key)

    with refused_by(f"{table}_append_only"):
        run(f"DELETE FROM {quote(table)} WHERE {where(table)}", [key])  # noqa: S608

    assert snapshot(table, key) == before


# --------------------------------------------------- through the ORM (AC1)
@pytest.mark.django_db
@pytest.mark.parametrize("table", INSERT_ONLY_TABLES)
def test_the_orm_cant_update_a_past_row(table: str) -> None:
    key = fresh_row(table)
    before = snapshot(table, key)
    field = MODELS[table]._meta.get_field(UNCHANGED_COLUMN[table])

    with refused_by(f"{table}_append_only"):
        MODELS[table]._default_manager.filter(pk=key).update(
            **{field.name: models.F(field.name)}
        )

    assert snapshot(table, key) == before


@pytest.mark.django_db
@pytest.mark.parametrize("table", INSERT_ONLY_TABLES)
def test_the_orm_cant_delete_a_past_row(table: str) -> None:
    key = fresh_row(table)
    before = snapshot(table, key)

    with refused_by(f"{table}_append_only"):
        MODELS[table]._default_manager.filter(pk=key).delete()

    assert snapshot(table, key) == before


# ------------------------------------------- the owner's TRUNCATE is noticed
TRUNCATED = sorted({*INSERT_ONLY_TABLES, *AUDITED})


@pytest.mark.django_db
@pytest.mark.parametrize("table", TRUNCATED)
def test_the_owners_truncate_writes_a_truncate_row(table: str) -> None:
    """AC2, AC15, design §4.4: not stopped, but never silent.

    Truncating `audit_log` empties it, and its own row is written after.
    """
    mark = 0 if table == "audit_log" else audit_mark()
    run("SET CONSTRAINTS ALL IMMEDIATE")  # no pending checks, or TRUNCATE refuses

    with transaction.atomic():
        run(f"TRUNCATE {quote(table)} CASCADE")
        rows = [
            row
            for row in audit_rows_since(mark)
            if row.action == "truncate" and row.table_name == table
        ]
    run("SET CONSTRAINTS ALL DEFERRED")

    assert len(rows) == 1, rows
    [row] = rows
    assert row.actor_id is None
    assert row.via == "sql as cucumber_owner"
    assert row.db_user == "cucumber_owner"


# ------------------------------------------------- the 10-minute Undo (AC3)
@pytest.mark.django_db
def test_making_an_entry_look_older_by_raw_sql_is_refused() -> None:
    """AC3: Undo goes by `operations.recorded_at`, which can't be moved back."""
    operation = fresh_row("operations")

    with refused_by("operations_append_only"):
        run(
            "UPDATE operations SET recorded_at = recorded_at - interval '11 minutes'"
            " WHERE id = %s",
            [operation],
        )


# --------------------------------------------- the app user, by raw SQL (AC1)
APP_ATTACKS = [
    statement
    for table in INSERT_ONLY_TABLES
    for statement in (
        f"UPDATE {table} SET {UNCHANGED_COLUMN[table]} = {UNCHANGED_COLUMN[table]}",
        f"DELETE FROM {table}",
        f"TRUNCATE {table}",
    )
]


def app_run(app_db: AppConnection, statements: list[str], named: int | None) -> str:
    """Run `statements` as `cucumber_app` in one transaction; how it ended.

    "saved", "no grant", or the rule that refused it.
    """
    try:
        with app_db.transaction():
            if named is not None:
                app_db.execute(
                    b"SELECT set_config('cucumber.actor_id', %s, true)", [str(named)]
                )
            for statement in statements:
                app_db.execute(statement.encode())
    except psycopg.errors.InsufficientPrivilege:
        return "no grant"
    except psycopg.Error as error:
        return rule_name(error) or str(error)
    return "saved"


def test_the_app_user_cant_change_or_empty_any_past_row(app_db: AppConnection) -> None:
    """All 18 attacks in one committing test: each such test flushes after."""
    restore_audit_rows()
    with as_system():
        restore_reference_rows()
    user, plant = base_rows()
    keys = {table: one_row_in(table, user, plant) for table in INSERT_ONLY_TABLES}
    before = {table: snapshot(table, key) for table, key in keys.items()}

    outcomes = {
        statement: app_run(app_db, [statement], None) for statement in APP_ATTACKS
    }

    assert {s: o for s, o in outcomes.items() if o != "no grant"} == {}
    assert {table: snapshot(table, key) for table, key in keys.items()} == before


# ------------------------------------------- audited tables, as the app user
def app_writes(table: str, staff: int) -> list[str]:
    """The writes `cucumber_app` may make to `table` (its grants, U0.2a)."""
    tech = as_int(fetch_one("SELECT id FROM auth_group WHERE name = 'tech'")[0])
    flag = as_int(fetch_one("SELECT id FROM waffle_flag WHERE name = 'probe'")[0])
    return {
        "plants": [f"UPDATE plants SET notes = 'bench 4' WHERE created_by = {staff}"],
        "batches": [
            "UPDATE batches SET location_code = 'lab', stage_code = 'P2'"
            f" WHERE created_by = {staff}"
        ],
        "genera": ["UPDATE genera SET name = 'Philodendron sp.' WHERE code = 'PHL'"],
        "stages": ["UPDATE stages SET label = 'P2 late' WHERE code = 'P2'"],
        "media_codes": ["UPDATE media_codes SET label = 'half' WHERE code = 'M001'"],
        "locations": ["UPDATE locations SET label = 'The Lab' WHERE code = 'lab'"],
        "container_types": [
            "UPDATE container_types SET label = 'Magenta box II'"
            " WHERE code = 'magenta_box'"
        ],
        "reasons": [
            "UPDATE reasons SET label = 'Wrong batch!' WHERE code = 'void_wrong_batch'"
        ],
        "vendors": ["UPDATE vendors SET name = 'Leafy' WHERE zoho_contact_id = 'ZC-1'"],
        "auth_user": [f"UPDATE auth_user SET first_name = 'Gene' WHERE id = {staff}"],
        "auth_user_groups": [
            f"INSERT INTO auth_user_groups (user_id, group_id) VALUES ({staff}, {tech})"
        ],
        "waffle_flag": [f"UPDATE waffle_flag SET everyone = true WHERE id = {flag}"],
        "waffle_flag_groups": [
            "INSERT INTO waffle_flag_groups (flag_id, group_id)"
            f" VALUES ({flag}, {tech})"
        ],
    }[table]


def committed_set_up() -> int:
    """A row in every audited table, committed so the app's connection sees it.

    The flush before this test removed the seed rows and the groups.
    """
    restore_audit_rows()
    run("INSERT INTO auth_group (name) VALUES ('tech') ON CONFLICT DO NOTHING")
    with as_system():
        restore_reference_rows()
        staff = make_user("gene")
        make_batch(make_plant(staff), staff)
        insert(
            "vendors",
            {
                "zoho_contact_id": "ZC-1",
                "name": "Green Leaf Co.",
                "active": True,
                "synced_at": db_now(),
            },
            "zoho_contact_id",
        )
        insert(
            "waffle_flag",
            {
                "name": "probe",
                "everyone": None,
                "percent": None,
                "testing": False,
                "superusers": False,
                "staff": False,
                "authenticated": False,
                "languages": "",
                "rollout": False,
                "note": "",
                "created": db_now(),
                "modified": db_now(),
            },  # fmt: skip
        )
    return staff


@pytest.mark.parametrize("table", sorted(AUDITED))
def test_the_app_user_cant_skip_the_trail(app_db: AppConnection, table: str) -> None:
    """AC5, AC16: refused with nobody named; one row per write with someone named."""
    staff = committed_set_up()
    statements = app_writes(table, staff)
    mark = audit_mark()

    without = app_run(app_db, statements, named=None)
    with_person = app_run(app_db, statements, named=staff)

    assert without == "audit_actor_required"
    assert with_person == "saved"
    rows = audit_rows_since(mark, table)
    assert len(rows) == len(statements)
    assert {(row.actor_id, row.via, row.db_user) for row in rows} == {
        (staff, "sql as cucumber_app", "cucumber_app")
    }


def test_the_app_user_may_no_longer_give_a_permission_straight_to_an_account(
    app_db: AppConnection,
) -> None:
    """Design §5.3, review L1: roles are groups, so this table can't slip past."""
    staff = committed_set_up()
    permission = as_int(fetch_one("SELECT min(id) FROM auth_permission")[0])
    grant = (
        "INSERT INTO auth_user_user_permissions (user_id, permission_id)"
        f" VALUES ({staff}, {permission})"
    )

    assert app_run(app_db, [grant], named=staff) == "no grant"


def test_the_app_user_cant_forge_when_or_who_wrote_an_audit_row(
    app_db: AppConnection,
) -> None:
    """Review M3: the app may add rows, but `at` and `db_user` are the database's."""
    staff = committed_set_up()
    mark = audit_mark()
    forged = (
        "INSERT INTO audit_log (actor_id, at, table_name, row_pk, action, via, db_user)"
        f" VALUES ({staff}, '2000-01-01', 'plants', '1', 'update', 'app',"
        " 'cucumber_owner')"
    )

    assert app_run(app_db, [forged], named=None) == "saved"

    [row] = audit_rows_since(mark)
    assert row.db_user == "cucumber_app"
    assert row.at.year != 2000
