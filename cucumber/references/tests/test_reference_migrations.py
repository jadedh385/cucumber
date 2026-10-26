"""U0.9 design §2.2–§2.5: the three migrations, forward and undo.

`0006` names any media code, label or genus name the new checks would
refuse, before it adds them. `0008` checks System exists before it writes
anything as System. Its undo refuses, saying to restore the copy, while
anything newer than `0008` uses or changed what it would take back (review
M5); otherwise it puts the labels back, removes `S0` and the seven container
types, and writes a `delete` audit row for each by hand.

Contracts the G3 build follows: `0006`'s pre-check is
`refuse_rows_that_dont_fit(apps, schema_editor)`; `0008` is
`label_and_seed(apps, schema_editor)` and its undo
`undo_label_and_seed(apps, schema_editor)`. Each takes `schema_editor=None`,
as U0.7's undos do, and refuses with a `RuntimeError`.

The forward and undo tests migrate the test database itself, so they commit,
and always migrate everything forward again afterwards. Each one first
migrates to a U0.9 migration by name, so before G3 it stops there, on
"Cannot find a migration". The flush before a committing test empties the
lists, so those tests put the U0.2a seeds back first.
"""

import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command

from cucumber.core.audit import SYSTEM_USERNAME, audited
from cucumber.core.tests.rows import (
    fetch_one,
    insert,
    make_batch,
    make_event,
    run,
    update,
)
from cucumber.core.tests.trail import (
    as_system,
    audit_mark,
    audit_rows_since,
    system_id,
)
from cucumber.references.tests.support import ARCHIVE_REASON
from cucumber.references.tests.test_labels_and_seed import (
    CONTAINER_TYPES,
    MEDIA_CODES,
    STAGE_LABELS,
    labels,
)

BEFORE_U09 = "0005_genus_not_id_prefix"
REFERENCES_0006 = "0006_container_types"
REFERENCES_0007 = "0007_container_type_rules"
REFERENCES_0008 = "0008_labels_and_seed"
U02A_STAGES = [
    ("P0", 1), ("P1", 2), ("P2", 3), ("A1", 4), ("P4", 5),
    ("P3", None), ("T1", None), ("C0", None),
]  # fmt: skip
U02A_STAGE_LABELS = {code: code for code, _ in U02A_STAGES}
# The checks 0006 adds to the existing lists, and their tables.
NEW_CHECKS = {
    "media_codes_code_format": "media_codes",
    "media_codes_label_valid": "media_codes",
    "stages_label_valid": "stages",
    "locations_label_valid": "locations",
    "genera_name_valid": "genera",
}
S0_ROW = {
    "code": "S0",
    "label": "Seed",
    "sort_order": 0,
    "default_subculture_days": None,
    "active": True,
}

committing = pytest.mark.django_db(transaction=True)


def migration(name: str) -> ModuleType:
    """A references migration module; fails plainly while it isn't written yet."""
    try:
        return importlib.import_module(f"cucumber.references.migrations.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"Cannot find a migration references.{name} (U0.9 G3)")


def migrate(name: str) -> None:
    call_command("migrate", "references", name, verbosity=0)


@pytest.fixture
def forward_again(transactional_db: None) -> Iterator[None]:
    """Whatever the test migrates, every app is migrated forward afterwards."""
    try:
        yield
    finally:
        call_command("migrate", verbosity=0)


def u02a_lists() -> None:
    """The lists as U0.2a seeded them (labels are codes), after a flush."""
    with as_system():
        for code, order in U02A_STAGES:
            if order is not None:
                run(
                    "INSERT INTO stages (code, label, sort_order, active)"
                    " VALUES (%s, %s, %s, true) ON CONFLICT DO NOTHING",
                    [code, code, order],
                )
        run(
            "INSERT INTO locations (code, label, active)"
            " VALUES ('lab', 'Lab', true), ('nursery', 'Nursery', true)"
            " ON CONFLICT DO NOTHING"
        )
        for code in MEDIA_CODES:
            run(
                "INSERT INTO media_codes (code, label, active)"
                " VALUES (%s, %s, true) ON CONFLICT DO NOTHING",
                [code, code],
            )
        run(
            "INSERT INTO genera (code, name, active) VALUES ('HYA', 'Hoya', true),"
            " ('PHL', 'Philodendron', true), ('ALC', 'Alocasia', true)"
            " ON CONFLICT DO NOTHING"
        )
    with as_system(ARCHIVE_REASON):  # a reserved stage is off from the start
        for code, order in U02A_STAGES:
            if order is None:
                run(
                    "INSERT INTO stages (code, label, sort_order, active)"
                    " VALUES (%s, %s, NULL, false) ON CONFLICT DO NOTHING",
                    [code, code],
                )


def stage_labels() -> dict[str, str]:
    return labels("stages")


def exists(kind: str, name: str) -> bool:
    """Is there a table, function, trigger or constraint by this name?"""
    sql = {
        "table": "SELECT to_regclass(%s) IS NOT NULL",
        "function": "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = %s)",
        "trigger": "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = %s)",
        "constraint": "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = %s)",
    }[kind]
    return fetch_one(sql, [name]) == (True,)


def assert_u09_is_there() -> None:
    assert stage_labels() == STAGE_LABELS
    assert labels("container_types") == CONTAINER_TYPES
    assert exists("trigger", "stages_order_fixed")
    assert exists("trigger", "locations_fixed")
    assert exists("function", "cucumber_owner_only")
    assert [name for name in NEW_CHECKS if not exists("constraint", name)] == []


def assert_u09_is_gone() -> None:
    assert stage_labels() == U02A_STAGE_LABELS
    assert not exists("table", "public.container_types")
    assert not exists("trigger", "stages_order_fixed")
    assert not exists("trigger", "locations_fixed")
    assert not exists("function", "cucumber_owner_only")
    assert [name for name in NEW_CHECKS if exists("constraint", name)] == []


# ------------------------------------------------- forward, undo, forward
@committing
@pytest.mark.usefixtures("forward_again")
def test_forward_undo_in_order_and_forward_again() -> None:
    migrate(REFERENCES_0008)
    migrate(REFERENCES_0007)  # nothing to take back: the flush emptied the lists
    u02a_lists()

    migrate(REFERENCES_0008)
    assert_u09_is_there()

    migrate(BEFORE_U09)  # 0008, then 0007, then 0006
    assert_u09_is_gone()

    migrate(REFERENCES_0008)
    assert_u09_is_there()


@committing
@pytest.mark.usefixtures("forward_again")
def test_0008_undo_doesnt_count_audit_rows_older_than_0008() -> None:
    """Review M5: a staging walkthrough before U0.9 doesn't block it for good."""
    migrate(REFERENCES_0008)
    migrate(REFERENCES_0007)
    u02a_lists()
    with as_system():
        update("stages", "P1", {"label": "P1 walkthrough"}, "code")
        update("stages", "P1", {"label": "P1"}, "code")
    migrate(REFERENCES_0008)

    migrate(REFERENCES_0007)

    assert stage_labels() == U02A_STAGE_LABELS


@committing
@pytest.mark.usefixtures("forward_again")
def test_0008_undo_works_again_after_forward_undo_forward() -> None:
    """G6 rehearses the undo on staging; a second rehearsal must work too.

    The first undo's own rows (labels back, deletes) are older than the
    second forward's, so they don't count either.
    """
    migrate(REFERENCES_0008)
    migrate(REFERENCES_0007)
    u02a_lists()
    migrate(REFERENCES_0008)
    migrate(REFERENCES_0007)
    migrate(REFERENCES_0008)

    migrate(REFERENCES_0007)

    assert stage_labels() == U02A_STAGE_LABELS
    assert fetch_one("SELECT count(*) FROM container_types") == (0,)


@committing
@pytest.mark.usefixtures("forward_again")
def test_0006_undo_refuses_while_container_types_has_a_row() -> None:
    """Design §2.2: it runs only after 0008's undo, and never drops a row the
    Admin added. It names the code and says to restore the copy."""
    migrate(REFERENCES_0008)
    migrate(REFERENCES_0007)  # 0008 undone: no seeded container types left
    with as_system():
        insert("container_types", {"code": "jiffy_pot", "label": "Jiffy pot"}, "code")

    with pytest.raises(RuntimeError) as caught:
        migrate(BEFORE_U09)

    assert "jiffy_pot" in str(caught.value)
    assert "restore" in str(caught.value).lower()
    assert exists("table", "public.container_types")


# --------------------------------------------------- 0006's pre-check (L3)
@pytest.mark.django_db
def test_0006_names_every_row_the_new_checks_would_refuse() -> None:
    """Instead of a bare constraint error on staging or production (§2.2)."""
    step = migration(REFERENCES_0006)
    for name, table in NEW_CHECKS.items():
        run(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    with as_system():
        insert("media_codes", {"code": "m01", "label": "m01", "active": True}, "code")
        update("media_codes", "M002", {"label": " M002"}, "code")
        update("stages", "A1", {"label": ""}, "code")
        update("genera", "HYA", {"name": "x" * 101}, "code")

    with pytest.raises(RuntimeError) as caught:
        step.refuse_rows_that_dont_fit(apps, None)

    message = str(caught.value)
    assert [code for code in ["m01", "M002", "A1", "HYA"] if code not in message] == []
    assert [code for code in ["M001", "P1", "PHL"] if code in message] == []


@pytest.mark.django_db
def test_0006_passes_when_every_row_fits() -> None:
    step = migration(REFERENCES_0006)

    step.refuse_rows_that_dont_fit(apps, None)


# -------------------------------------------- 0008 needs System first (L5)
@pytest.mark.django_db
def test_0008_without_the_system_account_stops_naming_it() -> None:
    """Not halfway, on `audit_actor_required` (design §2.4)."""
    step = migration(REFERENCES_0008)
    run("ALTER TABLE auth_user DISABLE TRIGGER USER")
    try:
        run(
            "UPDATE auth_user SET username = 'gone@example.com' WHERE username = %s",
            [SYSTEM_USERNAME],
        )
    finally:
        run("ALTER TABLE auth_user ENABLE TRIGGER USER")
    mark = audit_mark()

    with pytest.raises(RuntimeError, match=SYSTEM_USERNAME):
        step.label_and_seed(apps, None)

    assert audit_rows_since(mark) == []


# ------------------------------------------------ 0008's undo refuses (M5)
@pytest.fixture
def step() -> ModuleType:
    """`0008`, found before any set-up row: before G3 the test stops here."""
    return migration(REFERENCES_0008)


def refused_undo(step: ModuleType, code: str) -> None:
    """The undo refuses, names `code`, says to restore the copy, takes nothing."""
    labels = stage_labels()

    with pytest.raises(RuntimeError) as caught:
        step.undo_label_and_seed(apps, None)

    assert code in str(caught.value)
    assert "restore" in str(caught.value).lower()
    assert stage_labels() == labels
    assert fetch_one("SELECT count(*) FROM stages WHERE code = 'S0'") == (1,)


@pytest.mark.django_db
def test_0008_undo_refuses_while_a_batch_is_at_s0(
    step: ModuleType, plant: int, user: int
) -> None:
    make_batch(plant, user, location_code="lab", stage_code="S0")

    refused_undo(step, "S0")


@pytest.mark.django_db
def test_0008_undo_refuses_while_an_event_moved_a_batch_to_s0(
    step: ModuleType, batch: int, user: int
) -> None:
    make_event(batch, user, "stage_change", stage_to="S0")

    refused_undo(step, "S0")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("table", "code", "values"),
    [
        ("stages", "P1", {"label": "Multiplication (bench 2)"}),
        ("container_types", "jar", {"label": "Glass jar"}),
    ],
)
def test_0008_undo_refuses_after_the_admin_changed_one_of_its_labels(
    step: ModuleType, table: str, code: str, values: dict[str, object], admin: User
) -> None:
    with audited(admin):
        update(table, code, values, "code")

    refused_undo(step, code)


@pytest.mark.django_db
def test_0008_undo_refuses_after_the_admin_switched_a_container_type_off(
    step: ModuleType, admin: User
) -> None:
    with audited(admin, reason=ARCHIVE_REASON):
        update("container_types", "tray", {"active": False}, "code")

    refused_undo(step, "tray")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("table", "values"),
    [
        ("container_types", {"code": "jiffy_pot", "label": "Jiffy pot"}),
        ("media_codes", {"code": "M777", "label": "M777"}),
        ("genera", {"code": "ANT", "name": "Anthurium"}),
    ],
)
def test_0008_undo_refuses_while_the_admin_added_an_item(
    step: ModuleType, table: str, values: dict[str, object], admin: User
) -> None:
    """Otherwise 0008 would undo and 0006 refuse: half undone (review M5)."""
    with audited(admin):
        insert(table, {**values, "active": True}, "code")

    refused_undo(step, str(values["code"]))


# --------------------------------------- 0008's undo completes (L1, §2.4)
@pytest.mark.django_db
def test_0008_undo_completes_with_deferred_checks_pending(
    step: ModuleType, plant: int, user: int
) -> None:
    """L1: removing `S0` and a new batch at `P2` both leave deferred checks on
    `stages`; the undo runs only those, by name, not the one elsewhere."""
    make_batch(plant, user, location_code="lab", stage_code="P2")
    run(
        "CREATE TABLE elsewhere (id integer PRIMARY KEY, parent integer"
        " REFERENCES elsewhere (id) DEFERRABLE INITIALLY DEFERRED)"
    )
    run("INSERT INTO elsewhere VALUES (1, 99)")  # fails only at commit

    step.undo_label_and_seed(apps, None)

    assert stage_labels() == U02A_STAGE_LABELS
    assert fetch_one("SELECT count(*) FROM container_types") == (0,)
    run("DELETE FROM elsewhere")  # so the test's own clean-up check passes


@pytest.mark.django_db
def test_0008_undo_writes_its_rows_as_system_via_migration(step: ModuleType) -> None:
    """Design §6: label updates by the trigger, and a `delete` row by hand for
    each row it removes (the list tables' trigger doesn't fire on DELETE)."""
    mark = audit_mark()

    step.undo_label_and_seed(apps, None)

    rows = audit_rows_since(mark)
    assert {(row.actor_id, row.via) for row in rows} == {(system_id(), "migration")}
    assert sorted((row.table_name, row.row_pk, row.action) for row in rows) == sorted(
        [
            ("stages", "S0", "delete"),
            *(("stages", code, "update") for code in STAGE_LABELS if code != "S0"),
            *(("container_types", code, "delete") for code in CONTAINER_TYPES),
        ]
    )
    by_code = {row.row_pk: (row.before, row.after) for row in rows}
    assert by_code["S0"] == (S0_ROW, None)
    assert by_code["P1"] == ({"label": "Multiplication"}, {"label": "P1"})
    assert by_code["jar"] == ({"code": "jar", "label": "Jar", "active": True}, None)
