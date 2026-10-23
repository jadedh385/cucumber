"""U0.8 design §5.2–§5.5: the three migrations, forward and undo.

`core 0007` swaps each identity column for a plain sequence of the same
name and carries on from the same position, so the next row gets the
number it would have had. Its undo puts the identity back at the same
position. `plants 0003` names any SKU the new pattern refuses before it
changes the check, and its undo is refused while a 4-digit SKU exists.

The forward and undo tests migrate the test database itself, so they
commit, and always migrate everything forward again afterwards. Each one
first migrates to a U0.8 migration by name, so before G3 they stop there,
on "Cannot find a migration".
"""

import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest
from django.apps import apps
from django.core.management import call_command

from cucumber.core import expected
from cucumber.core.tests.rows import (
    fetch_all,
    fetch_one,
    give_sku,
    issue_sku,
    make_batch,
    make_event,
    make_plant,
    make_user,
    run,
)
from cucumber.core.tests.stock import restore_reference_rows
from cucumber.ids.tests.generators import TABLES, next_id

BEFORE_CORE_0007 = "0006_audit_trail"
CORE_0007 = expected.U08.split(".", 1)[1]
PLANTS_0003 = "0003_sku_grows"
BEFORE_PLANTS_0003 = "0002_rules"
REFERENCES_0005 = "0005_genus_not_id_prefix"
BEFORE_REFERENCES_0005 = "0004_reason_lists"

committing = pytest.mark.django_db(transaction=True)


def migration(app: str, name: str) -> ModuleType:
    """A migration module; fails plainly while it isn't written yet."""
    try:
        return importlib.import_module(f"cucumber.{app}.migrations.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"migration {app}.{name} isn't written yet (U0.8 G3)")


def migrate(app: str, name: str) -> None:
    call_command("migrate", app, name, verbosity=0)


@pytest.fixture
def forward_again(transactional_db: None) -> Iterator[None]:
    """Whatever the test migrates, every app is migrated forward afterwards."""
    try:
        yield
    finally:
        call_command("migrate", verbosity=0)


def some_rows() -> None:
    """A few plants, batches and events, made as the owner."""
    restore_reference_rows()
    user = make_user("tech")
    plant = make_plant(user)
    for _ in range(2):
        batch = make_batch(plant, user)
        make_event(batch, user, "count", counted_qty=0)


def serial_sequence(table: str) -> object:
    return fetch_one("SELECT pg_get_serial_sequence(%s, 'id')", [f"public.{table}"])[0]


def id_column(table: str) -> tuple[object, ...]:
    """(attidentity, atthasdef) of the table's `id` column."""
    return fetch_one(
        "SELECT attidentity, atthasdef FROM pg_attribute"
        " WHERE attrelid = %s::regclass AND attname = 'id'",
        [f"public.{table}"],
    )


def triggers_on(table: str) -> set[str]:
    rows = fetch_all(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = %s::regclass"
        " AND NOT tgisinternal",
        [f"public.{table}"],
    )
    return {str(row[0]) for row in rows}


# ------------------------------------------------------------- core 0007
@committing
@pytest.mark.usefixtures("forward_again", "generators_put_back")
def test_core_0007_carries_each_generator_on_from_where_it_was() -> None:
    migrate("core", BEFORE_CORE_0007)
    some_rows()
    due = {table: next_id(table) for table in TABLES}

    migrate("core", CORE_0007)

    assert {table: next_id(table) for table in TABLES} == due
    for table in TABLES:
        assert serial_sequence(table) == expected.SEQUENCES[table]
        assert id_column(table) == ("", False), table
        assert f"{table}_id_from_sequence" in triggers_on(table)
    assert "plants_id_fixed" in triggers_on("plants")
    assert "batches_id_fixed" in triggers_on("batches")


@committing
@pytest.mark.usefixtures("forward_again", "generators_put_back")
def test_core_0007_repairs_a_generator_that_is_already_behind() -> None:
    migrate("core", BEFORE_CORE_0007)
    some_rows()
    highest = int(str(fetch_one("SELECT max(id) FROM plants")[0]))
    run("SELECT setval(%s, 1)", [expected.SEQUENCES["plants"]])

    migrate("core", CORE_0007)

    assert next_id("plants") > highest


@committing
@pytest.mark.usefixtures("forward_again", "generators_put_back")
def test_core_0007_starts_an_empty_table_at_1() -> None:
    migrate("core", BEFORE_CORE_0007)
    run("ALTER TABLE plants ALTER COLUMN id RESTART WITH 1")
    assert fetch_one("SELECT count(*) FROM plants") == (0,)

    migrate("core", CORE_0007)

    assert next_id("plants") == 1


@committing
@pytest.mark.usefixtures("forward_again", "generators_put_back")
def test_core_0007_undo_puts_each_identity_back_at_the_same_position() -> None:
    migrate("core", CORE_0007)
    some_rows()
    events_due = next_id("events")
    run("SELECT setval(%s, %s, false)", [expected.SEQUENCES["events"], events_due])
    due = {table: next_id(table) for table in TABLES}

    migrate("core", BEFORE_CORE_0007)

    assert {table: next_id(table) for table in TABLES} == due
    for table in TABLES:
        assert serial_sequence(table) == expected.SEQUENCES[table]
        assert id_column(table) == ("d", False), table
        assert f"{table}_id_from_sequence" not in triggers_on(table)


@committing
@pytest.mark.usefixtures("forward_again", "generators_put_back")
def test_core_0007_runs_forward_again_after_its_undo() -> None:
    migrate("core", CORE_0007)
    some_rows()
    migrate("core", BEFORE_CORE_0007)
    due = {table: next_id(table) for table in TABLES}

    migrate("core", CORE_0007)

    assert {table: next_id(table) for table in TABLES} == due
    assert all(id_column(table) == ("", False) for table in TABLES)


# ------------------------------------------------------------ plants 0003
@pytest.mark.django_db
def test_plants_0003_names_every_sku_the_new_pattern_refuses(user: int) -> None:
    """Review L3: the old pattern allowed XXX000, and `skus` had no check."""
    run("ALTER TABLE plants DROP CONSTRAINT IF EXISTS plant_sku_format")
    run("ALTER TABLE skus DROP CONSTRAINT IF EXISTS skus_sku_format")
    give_sku(make_plant(user, full_name="Zero"), "PHL000", user)
    give_sku(make_plant(user, full_name="Fine"), "PHL005", user)
    issue_sku(make_plant(user, genus_code="ALC", full_name="Too"), "ALC000", user)
    step = migration("plants", PLANTS_0003)

    with pytest.raises(RuntimeError) as caught:
        step.refuse_skus_that_dont_fit(apps, None)

    assert "PHL000" in str(caught.value)
    assert "ALC000" in str(caught.value)
    assert "PHL005" not in str(caught.value)


@pytest.mark.django_db
def test_plants_0003_passes_when_every_sku_fits(user: int) -> None:
    give_sku(make_plant(user), "PHL005", user)
    step = migration("plants", PLANTS_0003)

    step.refuse_skus_that_dont_fit(apps, None)


@committing
@pytest.mark.usefixtures("forward_again")
def test_plants_0003_undo_is_refused_while_a_4_digit_sku_exists() -> None:
    """The older code couldn't read PHL1000, so going back is refused (§5.5)."""
    migrate("plants", PLANTS_0003)
    restore_reference_rows()
    user = make_user("tech")
    plant = make_plant(user)
    give_sku(plant, "PHL1000", user)

    with pytest.raises(Exception, match="plant_sku_format|PHL1000"):
        migrate("plants", BEFORE_PLANTS_0003)

    assert fetch_one("SELECT sku FROM plants WHERE id = %s", [plant]) == ("PHL1000",)


# -------------------------------------------------------- references 0005
@committing
@pytest.mark.usefixtures("forward_again")
def test_references_0005_undo_drops_only_its_check() -> None:
    migrate("references", REFERENCES_0005)

    migrate("references", BEFORE_REFERENCES_0005)

    names = {
        str(row[0])
        for row in fetch_all(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'genera'::regclass"
        )
    }
    assert "genera_code_not_id_prefix" not in names
    assert "genera_code_format" in names
