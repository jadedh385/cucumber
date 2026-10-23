"""U0.8 AC14: `cucumber_check_guards` reports a number generator in trouble (design §6).

Each break is made inside the test's transaction, which undoes it, except a
`setval`: a generator never rolls back, so those tests put it back
(`generators_put_back`). A few breaks only exist once `core 0007` has made
the generators plain sequences; those tests say so first, so before G3 they
fail on the missing migration, not on a statement PostgreSQL refuses.
"""

import pytest

from cucumber.core import expected, guards
from cucumber.core.guards import GUARDS, Kind
from cucumber.core.tests.rows import make_batch, make_event, make_plant, run
from cucumber.core.tests.test_check_guards import check, failures
from cucumber.core.tests.trail import accept_noticed_truncates

pytestmark = pytest.mark.django_db

SINGULAR = {"plants": "plant", "batches": "batch", "events": "event"}
RUNBOOK = 'see the release runbook, "Number generator behind"'


@pytest.fixture(autouse=True)
def earlier_flushes_accepted() -> None:
    """A committing test's flush leaves `truncate` rows; they aren't this test's."""
    accept_noticed_truncates()


@pytest.fixture
def generators_are_sequences() -> None:
    """These breaks need core 0007's plain sequences (design §5.3)."""
    assert expected.U08 in guards.applied_migrations(), (
        f"{expected.U08} hasn't run: plants, batches and events still take"
        " their ids from identity columns (U0.8 G3)"
    )


def three_rows(table: str, user: int, plant: int, batch: int) -> list[int]:
    """Three new rows in `table`, in the order they were made."""
    if table == "plants":
        return [make_plant(user, full_name=f"Row {n}") for n in range(3)]
    if table == "batches":
        return [make_batch(plant, user) for _ in range(3)]
    return [make_event(batch, user, "count", counted_qty=0) for _ in range(3)]


def lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


# ------------------------------------------------------------ the guards
def test_ac14_every_table_s_generator_is_guarded() -> None:
    sequences = [guard for guard in GUARDS if guard.kind == Kind.SEQUENCE]

    assert sorted(guard.name for guard in sequences) == ["batches", "events", "plants"]
    assert {guard.migration for guard in sequences} == {expected.U08}


def test_ac14_the_app_role_may_not_move_a_generator_is_checked() -> None:
    check_ = expected.APP_ROLE_CHECKS.get("sequence update")

    assert check_ is not None
    assert check_.migration == expected.U08


def test_ac14_a_generator_ahead_of_its_rows_passes(
    user: int, plant: int, batch: int
) -> None:
    for table in expected.SEQUENCES:
        three_rows(table, user, plant, batch)

    assert "protections on." in check()


# ---------------------------------------------------------------- behind
@pytest.mark.parametrize("table", list(expected.SEQUENCES))
def test_ac14_a_generator_set_back_below_its_rows_is_reported(
    table: str, user: int, plant: int, batch: int, generators_put_back: None
) -> None:
    first, _, last = three_rows(table, user, plant, batch)
    run("SELECT setval(%s, %s)", [expected.SEQUENCES[table], first])

    output = failures()

    assert (
        f"{table}: the next new one would get id {first + 1}, but id {last} is"
        f" already used; {RUNBOOK}"
    ) in lines(output)


def test_ac14_a_generator_whose_next_number_is_taken_is_reported(
    user: int, plant: int, batch: int, generators_put_back: None
) -> None:
    """The edge: the next value equals `max(id)`."""
    _, _, last = three_rows("plants", user, plant, batch)
    run("SELECT setval(%s, %s)", [expected.SEQUENCES["plants"], last - 1])

    output = failures()

    assert (
        f"plants: the next new one would get id {last}, but id {last} is"
        f" already used; {RUNBOOK}"
    ) in lines(output)


def test_ac14_a_generator_set_back_but_not_yet_called_counts_its_own_number(
    user: int, plant: int, batch: int, generators_put_back: None
) -> None:
    """`is_called = false`: the next value is `last_value` itself (§6)."""
    first, _, last = three_rows("plants", user, plant, batch)
    run("SELECT setval(%s, %s, false)", [expected.SEQUENCES["plants"], first])

    output = failures()

    assert (
        f"plants: the next new one would get id {first}, but id {last} is"
        f" already used; {RUNBOOK}"
    ) in lines(output)


# ------------------------------------------------------- missing, default
def test_ac14_a_missing_generator_is_reported(generators_are_sequences: None) -> None:
    run("DROP SEQUENCE public.plants_id_seq")

    output = failures()

    assert ("plants: its number generator public.plants_id_seq is missing") in lines(
        output
    )


def test_ac14_a_generator_no_longer_owned_by_the_id_column_is_reported(
    generators_are_sequences: None,
) -> None:
    run("ALTER SEQUENCE public.batches_id_seq OWNED BY NONE")

    output = failures()

    assert ("batches: its number generator public.batches_id_seq is missing") in lines(
        output
    )


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE plants ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY",
        "ALTER TABLE plants ALTER COLUMN id"
        " SET DEFAULT nextval('public.plants_id_seq')",
    ],
    ids=["identity", "default"],
)
def test_ac14_an_id_column_with_a_default_again_is_reported(
    statement: str, generators_are_sequences: None
) -> None:
    """A later `AlterField` could put one back without a word (§5.1)."""
    run(statement)

    output = failures()

    assert (
        "plants: id has a default again, so callers can choose it; see U0.8 design §5.1"
    ) in lines(output)


# ------------------------------------------------------------- the app role
@pytest.mark.parametrize("table", list(expected.SEQUENCES))
def test_ac14_an_app_that_cant_take_numbers_is_reported(table: str) -> None:
    sequence = expected.SEQUENCES[table]
    run(f"REVOKE USAGE ON SEQUENCE {sequence} FROM cucumber_app")

    output = failures()

    assert (
        f"{table}: cucumber_app can't take numbers from {sequence},"
        f" so every new {SINGULAR[table]} fails"
    ) in lines(output)


def test_ac14_an_app_that_may_move_a_generator_is_reported() -> None:
    run("GRANT UPDATE ON SEQUENCE public.events_id_seq TO cucumber_app")

    output = failures()

    assert (
        "cucumber_app may UPDATE a number generator, so it could move one (setval)"
    ) in lines(output)
