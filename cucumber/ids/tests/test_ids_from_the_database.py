"""U0.8 AC13, review H1, M1, M5: the database gives every id (design §5.1).

A caller that supplies its own `id` for a plant, batch or event is refused
by `<table>_id_from_sequence`, as `cucumber_app` by raw SQL or through the
ORM. The owner (the V.2 import) may, and the generator moves past its
number by itself, under a table lock. An id never changes, for anyone
(`<table>_id_fixed`). AC12 (a void never frees a number) is in
`test_never_again.py`.

These tests commit: the app user only sees committed rows, and the owner's
table lock has to be held while another connection waits. A generator
doesn't roll back, so the owner tests put it back (`generators_put_back`).
Ids are compared with each other and with `next_id()`, never written out.
"""

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import psycopg
import pytest
from django.db import transaction
from django.db.models import Model
from django.utils import timezone

from cucumber.batches.models import Batch
from cucumber.core import expected
from cucumber.core.tests.rows import (
    AppConnection,
    as_int,
    as_system,
    batch_values,
    event_values,
    fetch_one,
    insert,
    make_batch,
    make_event,
    make_plant,
    make_user,
    next_plant_seq,
    plant_values,
    quote,
    refused_by,
    rule_name,
    update,
)
from cucumber.core.tests.stock import restore_reference_rows
from cucumber.core.tests.trail import system_id
from cucumber.events.models import Event, Operation
from cucumber.events.tests.test_concurrency import (
    LOCK_HOLD_SECONDS,
    THREAD_TIMEOUT_SECONDS,
    at_the_same_moment,
)
from cucumber.ids.tests.generators import (
    AHEAD,
    TABLES,
    ids_in,
    name_system_on,
    next_id,
)
from cucumber.plants.models import Plant

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass(frozen=True)
class Rows:
    """What every test starts from, made as the owner before anything else."""

    user: int
    plant: int
    batch: int
    event: int
    ahead: dict[str, int]  # per table, an id no row has and the generator won't reach


@pytest.fixture
def rows() -> Rows:
    restore_reference_rows()
    user = make_user("tech")
    plant = make_plant(user)
    batch = make_batch(plant, user)
    event = make_event(batch, user, "count", counted_qty=0)
    ahead = {table: next_id(table) + AHEAD for table in TABLES}
    return Rows(user, plant, batch, event, ahead)


def new_values(table: str, rows: Rows) -> dict[str, object]:
    """A valid new row for `table`, as raw SQL columns, with no `id`."""
    if table == "plants":
        return plant_values(rows.user, full_name=f"New {uuid.uuid4()}")
    if table == "batches":
        return batch_values(rows.plant, rows.user)
    return event_values(rows.batch, rows.user, "count", counted_qty=0)


def insert_as(db: AppConnection, table: str, values: dict[str, object]) -> int:
    """`rows.insert`, on another connection (the app's, or a thread's)."""
    columns = ", ".join(quote(column) for column in values)
    placeholders = ", ".join(["%s"] * len(values))
    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"  # noqa: S608
    row = db.execute(sql.encode(), list(values.values())).fetchone()
    assert row is not None
    return as_int(row[0])


def owner_insert(table: str, values: dict[str, object]) -> int:
    with as_system():
        return as_int(insert(table, values))


def use_up_a_number(table: str) -> int:
    """Take one number without a row, as a failed save does (AC9)."""
    return as_int(fetch_one("SELECT nextval(%s)", [expected.SEQUENCES[table]])[0])


# --------------------------------------------- through the ORM, by model
def orm_plant(rows: Rows, **chosen: object) -> Model:
    return Plant.objects.create(
        genus_id="PHL",
        full_name=f"New {uuid.uuid4()}",
        status="collection",
        source="gift",
        created_by_id=rows.user,
        **chosen,
    )


def orm_batch(rows: Rows, **chosen: object) -> Model:
    operation = Operation.objects.create(recorded_by_id=rows.user)
    return Batch.objects.create(
        plant_id=rows.plant,
        plant_seq=next_plant_seq(rows.plant),
        origin="intake",
        created_operation_id=operation.pk,
        location_id="nursery",
        created_by_id=rows.user,
        **chosen,
    )


def orm_event(rows: Rows, **chosen: object) -> Model:
    operation = Operation.objects.create(recorded_by_id=rows.user)
    return Event.objects.create(
        operation=operation,
        batch_id=rows.batch,
        action="count",
        counted_qty=0,
        staff_id=rows.user,
        recorded_by_id=rows.user,
        occurred_at=timezone.now(),
        **chosen,
    )


ORM_CREATE: dict[str, Callable[..., Model]] = {
    "plants": orm_plant,
    "batches": orm_batch,
    "events": orm_event,
}


def existing_id(table: str, rows: Rows) -> int:
    return {"plants": rows.plant, "batches": rows.batch, "events": rows.event}[table]


# ------------------------------------------------- AC13: the app is refused
@pytest.mark.parametrize("table", TABLES)
def test_ac13_the_app_cant_choose_an_id_by_raw_sql(
    table: str, rows: Rows, app_db: AppConnection
) -> None:
    name_system_on(app_db, system_id())
    chosen = rows.ahead[table]

    with pytest.raises(psycopg.Error) as caught:
        insert_as(app_db, table, {"id": chosen, **new_values(table, rows)})

    assert rule_name(caught.value) == f"{table}_id_from_sequence"
    assert chosen not in ids_in(table)


@pytest.mark.parametrize("table", TABLES)
def test_ac13_the_app_cant_choose_an_id_through_the_orm(
    table: str, rows: Rows, as_app_user: None
) -> None:
    chosen = rows.ahead[table]

    with refused_by(f"{table}_id_from_sequence"), as_system():
        ORM_CREATE[table](rows, id=chosen)

    assert chosen not in ids_in(table)


@pytest.mark.parametrize("table", TABLES)
def test_review_m5_an_orm_create_as_the_app_gets_its_id_from_the_database(
    table: str, rows: Rows, as_app_user: None
) -> None:
    with as_system():
        made = ORM_CREATE[table](rows)

    assert int(made.pk) > existing_id(table, rows)
    assert int(made.pk) in ids_in(table)


# ---------------------------------------------------- AC13: the owner path
@pytest.mark.parametrize("table", TABLES)
def test_ac13_an_owner_chosen_id_moves_the_generator_past_it(
    table: str, rows: Rows, generators_put_back: None
) -> None:
    """Q1: the V.2 import keeps the PLT- numbers already in use."""
    chosen = rows.ahead[table]

    kept = owner_insert(table, {"id": chosen, **new_values(table, rows)})
    after = owner_insert(table, new_values(table, rows))

    assert kept == chosen
    assert after == chosen + 1


@pytest.mark.parametrize("table", TABLES)
def test_ac13_an_unused_owner_id_below_the_generator_moves_nothing(
    table: str, rows: Rows, generators_put_back: None
) -> None:
    """Design §5.1: allowed for the owner, and the generator stays put."""
    gap = use_up_a_number(table)
    due = next_id(table)

    kept = owner_insert(table, {"id": gap, **new_values(table, rows)})

    assert kept == gap < due
    assert next_id(table) == due


@pytest.mark.parametrize("table", TABLES)
def test_g4_an_owner_id_below_a_generator_not_yet_called_moves_nothing(
    table: str, rows: Rows, generators_put_back: None
) -> None:
    """G4 M1: core 0007 leaves every generator not yet called (`is_called` false).

    `pg_sequence_last_value` is NULL then, so an owner id below the next one
    must not be taken for "past the generator" and move it backwards.
    """
    gap = use_up_a_number(table)
    use_up_a_number(table)  # so moving back to the gap would show
    due = next_id(table)
    fetch_one("SELECT setval(%s, %s, false)", [expected.SEQUENCES[table], due])

    kept = owner_insert(table, {"id": gap, **new_values(table, rows)})

    assert kept == gap < due
    assert next_id(table) == due


def test_review_m1_an_app_save_waits_for_an_owner_import_then_numbers_past_it(
    rows: Rows, app_db: AppConnection, generators_put_back: None
) -> None:
    name_system_on(app_db, system_id())
    chosen = rows.ahead["plants"]
    imported = {"id": chosen, **new_values("plants", rows)}
    saved_meanwhile = new_values("plants", rows)
    locked = threading.Event()

    def import_slowly() -> int:
        try:
            with transaction.atomic():
                kept = owner_insert("plants", imported)
                locked.set()
                time.sleep(LOCK_HOLD_SECONDS)
        finally:
            locked.set()  # a failed import mustn't leave the save waiting
        return kept

    def save_while_importing() -> tuple[int, float]:
        assert locked.wait(THREAD_TIMEOUT_SECONDS)
        started = time.monotonic()
        made = insert_as(app_db, "plants", saved_meanwhile)
        return made, time.monotonic() - started

    results = at_the_same_moment([import_slowly, save_while_importing])

    kept, saved = results
    assert kept == chosen, results
    assert isinstance(saved, tuple), results
    made, waited = saved
    assert made == chosen + 1
    assert waited >= LOCK_HOLD_SECONDS / 2


# ------------------------------------------------- review H1: ids are fixed
def unreferenced(table: str, rows: Rows) -> int:
    """A row nothing points at yet, so only the new trigger can refuse."""
    if table == "plants":
        return make_plant(rows.user, full_name=f"Alone {uuid.uuid4()}")
    return make_batch(rows.plant, rows.user)


@pytest.mark.parametrize("table", ["plants", "batches"])
def test_review_h1_the_owner_cant_change_an_id(table: str, rows: Rows) -> None:
    row = unreferenced(table, rows)

    with refused_by(f"{table}_id_fixed"), as_system():
        update(table, row, {"id": rows.ahead[table]})

    assert row in ids_in(table)


@pytest.mark.parametrize("table", ["plants", "batches"])
def test_review_h1_the_app_cant_change_an_id(
    table: str, rows: Rows, app_db: AppConnection
) -> None:
    row = unreferenced(table, rows)
    name_system_on(app_db, system_id())

    with pytest.raises(psycopg.Error) as caught:
        app_db.execute(
            f"UPDATE {table} SET id = %s WHERE id = %s".encode(),  # noqa: S608
            [rows.ahead[table], row],
        )

    assert rule_name(caught.value) == f"{table}_id_fixed"
    assert row in ids_in(table)
