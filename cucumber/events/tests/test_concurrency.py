"""U0.2b: saves that commit (AC17, AC17a; design §3.3, §3.4).

Each request runs in its own thread with its own database connection, and
the threads start together, so the row lock and the `operations` primary
key are what keep the data right, not the order the test happens to run.

Also here: a refusal that only arrives at commit. Django's one-column
foreign keys are deferred, so they are checked when the transaction
commits, which never happens inside an ordinary test's outer transaction.

These tests commit, and pytest-django empties the database after each of
them, seed rows included, so they insert the reference rows they need.
"""

import threading
import time
import uuid
from collections.abc import Callable

import pytest
from django.db import connection, transaction

from cucumber.batches.models import Batch
from cucumber.core.refusals import Refused
from cucumber.core.tests.rows import make_plant, run
from cucumber.core.tests.stock import (
    intake_into_new_batch,
    live_count,
    log,
    make_staff,
    new_lab_batch,
    restore_reference_rows,
    subculture_entries,
)
from cucumber.core.tests.trail import as_system
from cucumber.events.models import Event, Operation
from cucumber.events.services import NewEvent, Saved, save_operation, split, void

pytestmark = pytest.mark.django_db(transaction=True)

THREAD_TIMEOUT_SECONDS = 30
# Long enough that the split reaches its lock wait before the change commits.
LOCK_HOLD_SECONDS = 1.0
INTERNAL = "Something went wrong; nothing was saved. Please tell the Admin."


def at_the_same_moment(calls: list[Callable[[], object]]) -> list[object]:
    """Run each call in its own thread, all released together.

    Each thread connects before the barrier, so the calls really overlap.
    Returns each call's result, or the exception it raised, in call order.
    """
    start = threading.Barrier(len(calls))
    results: list[object] = [None] * len(calls)

    def run_one(index: int, call: Callable[[], object]) -> None:
        try:
            connection.ensure_connection()
            start.wait()
            results[index] = call()
        except Exception as error:  # the test inspects what each call raised
            results[index] = error
        finally:
            connection.close()  # this thread's own connection

    threads = [
        threading.Thread(target=run_one, args=(index, call), daemon=True)
        for index, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(THREAD_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "a save never finished: a lock wait?"
    return results


def test_ac17_of_two_saves_that_would_go_below_zero_exactly_one_succeeds() -> None:
    restore_reference_rows()
    tech = make_staff("tech_1", "tech")
    batch = intake_into_new_batch(tech, make_plant(tech.pk), 5)

    def take_four() -> int:
        return log(tech, batch, "out", qty_out=4)

    results = at_the_same_moment([take_four, take_four])

    saved = [result for result in results if isinstance(result, int)]
    refusals = [result for result in results if isinstance(result, Refused)]
    assert len(saved) == 1, results
    assert [refusal.rule for refusal in refusals] == ["batch_count_not_negative"]
    assert live_count(batch) == 1
    assert Event.objects.filter(batch_id=batch, action="out").count() == 1


def test_ac17a_a_form_sent_four_times_at_once_is_saved_once() -> None:
    """Issue #4: a slow phone sent the same form 4 times in one second."""
    restore_reference_rows()
    tech = make_staff("tech_1", "tech")
    plant = make_plant(tech.pk)
    parent = new_lab_batch(tech, plant, 10)
    operation_id = uuid.uuid4()
    entries = subculture_entries(parent, plant)

    def send() -> Saved:
        return save_operation(operation_id, tech, entries)

    results = at_the_same_moment([send] * 4)

    answers = [result for result in results if isinstance(result, Saved)]
    assert len(answers) == 4, results  # every request answered, none failed
    assert sorted(answer.already_saved for answer in answers) == [
        False,
        True,
        True,
        True,
    ]
    assert len({(a.event_ids, a.batch_ids) for a in answers}) == 1
    assert Operation.objects.filter(pk=operation_id).count() == 1
    assert Event.objects.filter(operation_id=operation_id).count() == 4
    assert live_count(parent) == 7


def test_two_voids_of_one_event_at_once_write_one_void() -> None:
    restore_reference_rows()
    tech = make_staff("tech_1", "tech")
    batch = intake_into_new_batch(tech, make_plant(tech.pk), 5)
    out = log(tech, batch, "out", qty_out=1)

    def void_it() -> Saved:
        return void(tech, out, "void_wrong_batch")

    results = at_the_same_moment([void_it, void_it])

    assert len([r for r in results if isinstance(r, Saved)]) == 1, results
    refusals = [r for r in results if isinstance(r, Refused)]
    assert [refusal.rule for refusal in refusals] == ["event_void_once"]
    assert Event.objects.filter(voids_event_id=out).count() == 1
    assert live_count(batch) == 5


def test_a_foreign_key_refused_at_commit_is_reported_and_nothing_is_saved() -> None:
    """Design §3.4: map errors around the whole transaction, not one insert."""
    restore_reference_rows()
    tech = make_staff("tech_1", "tech")
    batch = intake_into_new_batch(tech, make_plant(tech.pk), 5)
    operation_id = uuid.uuid4()

    unknown_media = NewEvent("intake", batch, qty_in=1, media_code="M999")

    # U0.9's inactive check would refuse M999 first (`list_item_unknown`), so
    # it is skipped here to reach the foreign key at COMMIT (Owner, G3 s3).
    with pytest.raises(Refused) as caught:
        save_operation(operation_id, tech, [unknown_media], picked=False)

    assert caught.value.message == INTERNAL
    assert not Operation.objects.filter(pk=operation_id).exists()
    assert Event.objects.filter(batch_id=batch).count() == 1
    assert live_count(batch) == 5


def test_a_split_takes_the_parent_s_stage_after_waiting_for_its_lock() -> None:
    """A stage change saving at that moment isn't lost (G4 HIGH 2).

    The first request holds the parent's lock while it moves P2 → P3; the
    split waits for it, then copies the parent as it is after the change.
    """
    restore_reference_rows()
    with as_system():
        run("""INSERT INTO stages (code, label, sort_order, active)
               VALUES ('P3', 'P3', 4, true) ON CONFLICT DO NOTHING""")
    tech = make_staff("tech_1", "tech")
    parent = new_lab_batch(tech, make_plant(tech.pk), 10)
    locked = threading.Event()

    def change_stage_slowly() -> None:
        with transaction.atomic():
            log(tech, parent, "stage_change", stage_to="P3")
            locked.set()
            time.sleep(LOCK_HOLD_SECONDS)

    def split_after_the_lock_is_taken() -> Saved:
        assert locked.wait(THREAD_TIMEOUT_SECONDS)
        return split(uuid.uuid4(), tech, parent, 4, "too dense")

    results = at_the_same_moment([change_stage_slowly, split_after_the_lock_is_taken])

    saved = results[1]
    assert isinstance(saved, Saved), results
    [child] = saved.batch_ids
    assert Batch.objects.get(pk=child).stage_id == "P3"
