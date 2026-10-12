"""U0.2b: saving operations, the count wins, Close and Split (design §3.1, §3.3).

AC12a–c, AC16d, AC16g (totals), AC17a for one request after another. Two
requests at the same moment (AC17, AC17a) are in test_concurrency.py.
"""

import uuid
from datetime import timedelta
from typing import NamedTuple

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from cucumber.batches.models import Batch
from cucumber.core.refusals import Refused
from cucumber.core.tests.stock import (
    batch_of,
    days_ago,
    intake_into_new_batch,
    live_count,
    log,
    new_lab_batch,
    refused,
    subculture_entries,
)
from cucumber.events.models import Event, Operation
from cucumber.events.services import (
    NewBatch,
    NewEvent,
    close,
    correct,
    count_difference,
    save_operation,
    split,
    void,
)

pytestmark = pytest.mark.django_db

BELOW_ZERO = "This would take the batch below zero. Check the numbers."


# ------------------------------------------------------- saving an operation


def test_an_operation_saves_its_row_its_events_and_the_count(
    plant: int, tech: User
) -> None:
    operation_id = uuid.uuid4()
    new_batch = NewBatch(plant_id=plant, origin="intake", location_code="nursery")
    entry = NewEvent("intake", new_batch=new_batch, qty_in=10)

    saved = save_operation(operation_id, tech, [entry])

    assert (saved.operation_id, saved.already_saved) == (operation_id, False)
    assert Operation.objects.filter(pk=operation_id, recorded_by=tech).exists()
    [batch] = saved.batch_ids
    [event] = Event.objects.filter(pk__in=saved.event_ids)
    assert (event.operation_id, event.batch_id) == (operation_id, batch)
    assert (event.staff_id, event.recorded_by_id) == (tech.pk, tech.pk)
    assert abs(event.occurred_at - timezone.now()) < timedelta(minutes=1)
    assert batch_of(batch).created_operation_id == operation_id
    assert live_count(batch) == 10


def test_an_intake_into_an_existing_batch_adds_to_it(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    log(tech, batch, "intake", qty_in=5)
    assert live_count(batch) == 15


def test_a_reason_from_another_list_is_refused(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    with refused("event_reason_matches_action"):
        log(tech, batch, "loss", qty_out=1, reason_code="void_wrong_batch")


@pytest.mark.parametrize(
    ("values", "rule"),
    [
        ({"occurred_at": days_ago(8, 12)}, "event_within_7_days"),
        ({"occurred_at": timezone.now() + timedelta(hours=1)}, "event_not_in_future"),
        ({"reason_code": None}, "event_reason_required"),
    ],
    ids=["8-days-back", "future", "no-reason"],
)
def test_a_database_refusal_comes_back_by_its_rule_name(
    plant: int, tech: User, values: dict[str, object], rule: str
) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    with refused(rule):
        log(tech, batch, "loss", qty_out=1, **{"reason_code": "loss_rot", **values})
    assert live_count(batch) == 10


def test_batches_are_locked_without_blocking_foreign_key_checks(
    plant: int, tech: User
) -> None:
    """Design §3.4: `FOR NO KEY UPDATE`; plain `FOR UPDATE` blocks event inserts."""
    batch = intake_into_new_batch(tech, plant, 10)
    with CaptureQueriesContext(connection) as queries:
        log(tech, batch, "out", qty_out=1)
    sql = [query["sql"].upper() for query in queries.captured_queries]
    assert any("FOR NO KEY UPDATE" in statement for statement in sql)
    assert not any("FOR UPDATE" in statement for statement in sql)


def test_the_stage_follows_its_events(plant: int, tech: User) -> None:
    batch = new_lab_batch(tech, plant, 10, stage="P1")
    change = log(tech, batch, "stage_change", stage_to="P2")
    assert batch_of(batch).stage_id == "P2"
    void(tech, change, "void_wrong_batch")
    assert batch_of(batch).stage_id == "P1"


# ------------------------------------------------- the count wins (H2, Q5)


def test_ac16d_a_backdated_count_is_compared_with_the_total_at_its_date(
    plant: int, tech: User
) -> None:
    saturday_9 = days_ago(2, 9)
    batch = intake_into_new_batch(tech, plant, 48, occurred_at=saturday_9)
    log(tech, batch, "intake", qty_in=10, occurred_at=days_ago(1, 9))  # Sunday
    # Entered on Monday (today), dated Saturday 12:00.
    count = log(tech, batch, "count", counted_qty=50, occurred_at=days_ago(2, 12))
    assert count_difference(count) == 2
    assert live_count(batch) == 60


def test_ac16g_a_loss_dated_before_a_count_leaves_the_total(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 100, occurred_at=days_ago(3, 9))
    count = log(tech, batch, "count", counted_qty=98, occurred_at=days_ago(1, 9))
    assert count_difference(count) == -2
    # Entered on Thursday (today), dated Tuesday.
    log(
        tech,
        batch,
        "loss",
        qty_out=5,
        reason_code="loss_rot",
        occurred_at=days_ago(2, 9),
    )
    assert live_count(batch) == 98
    assert count_difference(count) == 3


# ----------------------------------------------------- below zero (rule 7)


def test_an_event_that_takes_the_batch_below_zero_is_refused(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 5)
    with pytest.raises(Refused) as caught:
        log(tech, batch, "out", qty_out=6)
    assert (caught.value.rule, caught.value.message) == (
        "batch_count_not_negative",
        BELOW_ZERO,
    )
    assert live_count(batch) == 5
    assert not Event.objects.filter(batch_id=batch, action="out").exists()


@pytest.mark.parametrize(
    ("action", "values"),
    [
        ("loss", {"qty_out": -2, "reason_code": "loss_rot"}),
        ("out", {"qty_out": -1}),
        ("contamination", {"qty_out": -1}),
        ("intake", {"qty_in": -3}),
        ("loss", {"qty_out": 1, "qty_in": -1, "reason_code": "loss_rot"}),
    ],
    ids=["loss", "out", "contamination", "intake", "loss-with-negative-in"],
)
def test_a_negative_quantity_gets_its_own_message(
    plant: int, tech: User, action: str, values: dict[str, object]
) -> None:
    """U0.2a G5: the database checks each action's shape before the sign (its
    rules run in name order), so a negative loss would show the Internal
    message. The service refuses it by name first."""
    batch = intake_into_new_batch(tech, plant, 5)
    with pytest.raises(Refused) as caught:
        log(tech, batch, action, **values)
    assert (caught.value.rule, caught.value.message) == (
        "event_qty_not_negative",
        "Quantities can't be negative.",
    )
    assert live_count(batch) == 5


def test_a_refused_save_leaves_no_operation_so_the_form_can_be_sent_again(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 5)
    operation_id = uuid.uuid4()
    with refused("batch_count_not_negative"):
        save_operation(operation_id, tech, [NewEvent("out", batch, qty_out=6)])
    assert not Operation.objects.filter(pk=operation_id).exists()

    saved = save_operation(operation_id, tech, [NewEvent("out", batch, qty_out=4)])

    assert not saved.already_saved
    assert live_count(batch) == 1


def test_a_backdated_event_is_refused_when_its_own_date_goes_below_zero(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 10, occurred_at=days_ago(3, 9))
    log(tech, batch, "count", counted_qty=10, occurred_at=days_ago(1, 9))
    # Today's total would stay 10 (the count wins), but on its own date
    # the batch had only 10.
    with refused("batch_count_not_negative"):
        log(tech, batch, "out", qty_out=12, occurred_at=days_ago(2, 9))


def test_a_backdated_event_is_refused_when_a_later_point_goes_below_zero(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 10, occurred_at=days_ago(3, 9))
    log(tech, batch, "out", qty_out=8, occurred_at=days_ago(1, 9))
    log(tech, batch, "count", counted_qty=2, occurred_at=days_ago(1, 12))
    # 5 left on its own date, but −3 after the out of 8, before the count.
    with refused("batch_count_not_negative"):
        log(tech, batch, "out", qty_out=5, occurred_at=days_ago(2, 9))
    assert live_count(batch) == 2


# ------------------------------------------------------ Close (Q7, AC12b–c)


class Emptied(NamedTuple):
    batch: int
    intake: int
    out: int


@pytest.fixture
def emptied(plant: int, tech: User) -> Emptied:
    """A batch brought to 0: an intake of 5, then an out of 5."""
    batch = intake_into_new_batch(tech, plant, 5)
    intake = Event.objects.get(batch_id=batch, action="intake").pk
    return Emptied(batch, intake, log(tech, batch, "out", qty_out=5))


def test_ac12b_closing_a_batch_at_zero_closes_it(emptied: Emptied, tech: User) -> None:
    saved = close(uuid.uuid4(), tech, emptied.batch)
    close_event = Event.objects.get(pk=saved.event_ids[0])
    closed = batch_of(emptied.batch)
    assert (close_event.action, closed.status) == ("close", "closed")
    assert closed.closed_at == close_event.occurred_at


def test_ac12b_voiding_the_close_reopens_the_batch(
    emptied: Emptied, tech: User
) -> None:
    saved = close(uuid.uuid4(), tech, emptied.batch)
    void(tech, saved.event_ids[0], "void_wrong_batch")
    reopened = batch_of(emptied.batch)
    assert (reopened.status, reopened.closed_at) == ("open", None)


def test_a_batch_with_units_cannot_be_closed(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 5)
    with refused("batch_closed_needs_zero"):
        close(uuid.uuid4(), tech, batch)
    assert batch_of(batch).status == "open"


@pytest.fixture
def closed(emptied: Emptied, tech: User) -> Emptied:
    close(uuid.uuid4(), tech, emptied.batch)
    return emptied


@pytest.mark.parametrize(
    ("action", "values"),
    [
        ("intake", {"qty_in": 5}),
        ("count", {"counted_qty": 0}),
        ("stage_change", {"stage_to": "P1"}),
        ("close", {}),
        # At 0 these would also go below zero: the closed batch is named first.
        ("out", {"qty_out": 1}),
        ("loss", {"qty_out": 1, "reason_code": "loss_rot"}),
    ],
)
def test_ac12c_nothing_new_is_logged_on_a_closed_batch(
    closed: Emptied, tech: User, action: str, values: dict[str, object]
) -> None:
    with refused("batch_not_open"):
        log(tech, closed.batch, action, **values)


def test_ac12c_an_older_event_of_a_closed_batch_cannot_be_corrected(
    closed: Emptied, tech: User
) -> None:
    with refused("batch_not_open"):
        correct(tech, closed.out, "correction_wrong_quantity", qty_out=4)


def test_ac12c_an_older_event_of_a_closed_batch_cannot_be_voided(
    closed: Emptied, tech: User
) -> None:
    with refused("batch_not_open"):
        void(tech, closed.out, "void_wrong_batch")
    assert batch_of(closed.batch).status == "closed"


# ------------------------------------------------------------ Split (AC12a)


def test_ac12a_a_split_moves_units_into_a_child_batch(plant: int, tech: User) -> None:
    parent = new_lab_batch(tech, plant, 100, stage="P2")

    saved = split(uuid.uuid4(), tech, parent, 40, note="pre-order for a customer")

    [child_id] = saved.batch_ids
    child = batch_of(child_id)
    assert (child.parent_batch_id, child.origin) == (parent, "split")
    assert (child.location_id, child.stage_id) == ("lab", "P2")
    assert child.created_operation_id == saved.operation_id
    assert (live_count(parent), child.live_count) == (60, 40)
    events = Event.objects.filter(pk__in=saved.event_ids)
    assert {(e.batch_id, e.action, e.qty_in, e.qty_out) for e in events} == {
        (parent, "split", 0, 40),
        (child_id, "intake", 40, 0),
    }
    assert {e.operation_id for e in events} == {saved.operation_id}
    assert events.get(action="split").note == "pre-order for a customer"


def test_a_split_needs_a_note(plant: int, tech: User) -> None:
    parent = intake_into_new_batch(tech, plant, 100)
    with refused("split_needs_note"):
        split(uuid.uuid4(), tech, parent, 40, note="  ")
    assert live_count(parent) == 100


def test_a_split_cannot_take_more_than_the_batch_holds(plant: int, tech: User) -> None:
    parent = intake_into_new_batch(tech, plant, 10)
    with refused("batch_count_not_negative"):
        split(uuid.uuid4(), tech, parent, 11, note="pre-order")
    assert Batch.objects.filter(parent_batch_id=parent).count() == 0


# --------------------------------------- duplicate saves (issue #4, AC17a)


def test_ac17a_the_same_form_sent_twice_is_saved_once(plant: int, tech: User) -> None:
    parent = new_lab_batch(tech, plant, 10)
    operation_id = uuid.uuid4()
    entries = subculture_entries(parent, plant)

    first = save_operation(operation_id, tech, entries)
    second = save_operation(operation_id, tech, entries)

    assert (first.already_saved, second.already_saved) == (False, True)
    assert (second.event_ids, second.batch_ids) == (first.event_ids, first.batch_ids)
    assert Operation.objects.filter(pk=operation_id).count() == 1
    assert Event.objects.filter(operation_id=operation_id).count() == 4
    assert Batch.objects.filter(created_operation_id=operation_id).count() == 3
    assert live_count(parent) == 7


# -------------------------------------------------- G4 review: bad requests


def test_a_split_of_a_batch_that_does_not_exist_is_refused(tech: User) -> None:
    with refused("batch_not_found"):
        split(uuid.uuid4(), tech, 999_999, 1, "too dense")


@pytest.mark.parametrize("qty", [0, -3])
def test_a_split_needs_at_least_one_unit(plant: int, tech: User, qty: int) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    with refused("split_qty_positive"):
        split(uuid.uuid4(), tech, batch, qty, "too dense")
    assert live_count(batch) == 10


def test_an_entry_names_one_batch_not_two(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    new_batch = NewBatch(plant_id=plant, origin="intake", location_code="nursery")
    entry = NewEvent("intake", batch_id=batch, new_batch=new_batch, qty_in=1)
    with refused("event_one_batch"):
        save_operation(uuid.uuid4(), tech, [entry])


def test_work_done_by_a_deactivated_user_is_refused(
    plant: int, supervisor: User, tech: User
) -> None:
    batch = intake_into_new_batch(supervisor, plant, 10)
    User.objects.filter(pk=tech.pk).update(is_active=False)
    with refused("staff_not_active"):
        log(supervisor, batch, "out", qty_out=1, staff_id=tech.pk)
    assert live_count(batch) == 10


def test_work_done_by_a_user_that_does_not_exist_is_refused(
    plant: int, supervisor: User
) -> None:
    batch = intake_into_new_batch(supervisor, plant, 10)
    with refused("staff_not_active"):
        log(supervisor, batch, "out", qty_out=1, staff_id=999_999)
