"""U0.8 AC9–AC11: never issued twice, at the same moment (design §12, Q1).

"At the same moment" is 100 creates from 25 connections released together,
4 in a row on each (Q1): always 25 saves fighting for the same lock or
number, 3× the most production can run at once (2 workers × 4 threads).
The lock and the generator keep the numbers apart, not the thread count.

These tests commit, and pytest-django empties the database after each, so
they put back the reference rows they need first.
"""

import threading
import time
from collections.abc import Callable

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from cucumber.batches.models import Batch
from cucumber.core.tests.rows import as_system, insert, make_plant
from cucumber.core.tests.stock import (
    intake_into_new_batch,
    make_staff,
    restore_reference_rows,
    save,
)
from cucumber.events.services import NewBatch, NewEvent, Saved
from cucumber.events.tests.test_concurrency import (
    LOCK_HOLD_SECONDS,
    THREAD_TIMEOUT_SECONDS,
    at_the_same_moment,
)
from cucumber.ids.issuing import issue_next_sku
from cucumber.ids.tests.generators import ids_in

pytestmark = pytest.mark.django_db(transaction=True)

CONNECTIONS = 25
IN_A_ROW = 4
CREATES = CONNECTIONS * IN_A_ROW  # 100


def from_25_connections(make_one: Callable[[int], object]) -> list[object]:
    """`make_one(0)` … `make_one(99)`: 25 connections released together, 4 each."""

    def four_in_a_row(first: int) -> Callable[[], list[object]]:
        return lambda: [make_one(first + step) for step in range(IN_A_ROW)]

    results = at_the_same_moment(
        [four_in_a_row(connection * IN_A_ROW) for connection in range(CONNECTIONS)]
    )
    failures = [result for result in results if not isinstance(result, list)]
    assert failures == [], failures
    made = [item for result in results if isinstance(result, list) for item in result]
    assert len(made) == CREATES
    return made


@pytest.fixture
def tech() -> User:
    restore_reference_rows()
    return make_staff("tech_1", "tech")


@pytest.fixture
def admin() -> User:
    restore_reference_rows()
    return make_staff("admin", "admin")


def plants_for(owner: User, count: int, genus: str = "PHL") -> list[int]:
    return [
        make_plant(owner.pk, genus_code=genus, full_name=f"Plant {number}")
        for number in range(count)
    ]


# -------------------------------------------------------------------- AC9
def test_ac9_100_plants_made_at_once_get_100_different_ids(tech: User) -> None:
    made = from_25_connections(
        lambda number: make_plant(tech.pk, full_name=f"At once {number}")
    )

    assert len(set(made)) == CREATES
    assert set(made) <= ids_in("plants")


def test_ac9_100_intakes_at_once_make_100_batches_and_100_events(tech: User) -> None:
    plants = plants_for(tech, CREATES)

    def intake(number: int) -> Saved:
        new_batch = NewBatch(
            plant_id=plants[number], origin="intake", location_code="nursery"
        )
        return save(tech, NewEvent("intake", new_batch=new_batch, qty_in=1))

    made = from_25_connections(intake)

    saved = [result for result in made if isinstance(result, Saved)]
    batch_ids = {batch for result in saved for batch in result.batch_ids}
    event_ids = {event for result in saved for event in result.event_ids}
    assert len(batch_ids) == CREATES
    assert len(event_ids) == CREATES


# ------------------------------------------------------------------- AC10
def issue_in_its_own_save(plant: int, genus: str, admin: User) -> str:
    with transaction.atomic():
        return issue_next_sku(plant, genus, admin)


def test_ac10_100_skus_issued_into_one_genus_at_once_are_phl001_to_phl100(
    admin: User,
) -> None:
    plants = plants_for(admin, CREATES)

    issued = from_25_connections(
        lambda number: issue_in_its_own_save(plants[number], "PHL", admin)
    )

    assert sorted(map(str, issued)) == [
        f"PHL{number:03d}" for number in range(1, CREATES + 1)
    ]


def test_ac10_an_sku_for_another_genus_isnt_held_up_by_a_waiting_lock(
    admin: User,
) -> None:
    """While PHL is held, HYA is issued at once and a second PHL waits its turn."""
    with as_system():
        insert("genera", {"code": "HYA", "name": "Hoya"}, returning="code")
    first, second = plants_for(admin, 2)
    [hoya] = plants_for(admin, 1, genus="HYA")
    held = threading.Event()

    def hold_phl() -> float:
        try:
            with transaction.atomic():
                issue_next_sku(first, "PHL", admin)
                held.set()
                time.sleep(LOCK_HOLD_SECONDS)
        finally:
            held.set()  # a failed hold mustn't leave the others waiting
        return time.monotonic()

    def after_the_hold(plant: int, genus: str) -> Callable[[], tuple[str, float]]:
        def issue() -> tuple[str, float]:
            assert held.wait(THREAD_TIMEOUT_SECONDS)
            return issue_in_its_own_save(plant, genus, admin), time.monotonic()

        return issue

    results = at_the_same_moment(
        [hold_phl, after_the_hold(hoya, "HYA"), after_the_hold(second, "PHL")]
    )

    released, other_genus, same_genus = results
    assert isinstance(released, float), results
    assert isinstance(other_genus, tuple), results
    assert isinstance(same_genus, tuple), results
    assert other_genus[0] == "HYA001"
    assert other_genus[1] < released
    assert same_genus[0] == "PHL002"
    assert same_genus[1] >= released


# ------------------------------------------------------------------- AC11
def test_ac11_100_batches_made_on_one_plant_at_once_are_numbered_1_to_100(
    tech: User,
) -> None:
    plant = make_plant(tech.pk)

    made = from_25_connections(lambda _: intake_into_new_batch(tech, plant, 1))

    batches = [batch for batch in made if isinstance(batch, int)]
    numbers = sorted(
        Batch.objects.filter(pk__in=batches).values_list("plant_seq", flat=True)
    )
    assert numbers == list(range(1, CREATES + 1))
