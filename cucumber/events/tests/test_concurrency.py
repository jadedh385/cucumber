"""U0.2b: saves at the same moment (AC17, AC17a; design §3.3).

Each request runs in its own thread with its own database connection, and
the threads start together, so the row lock and the `operations` primary
key are what keep the data right, not the order the test happens to run.

These tests commit, and pytest-django empties the database after each of
them, seed rows included, so they insert the reference rows they need.
"""

import threading
import uuid
from collections.abc import Callable

import pytest
from django.db import connection

from cucumber.core.refusals import Refused
from cucumber.core.tests.rows import make_plant, run
from cucumber.core.tests.stock import (
    intake_into_new_batch,
    live_count,
    log,
    make_staff,
    new_lab_batch,
    subculture_entries,
)
from cucumber.events.models import Event, Operation
from cucumber.events.services import Saved, save_operation

pytestmark = pytest.mark.django_db(transaction=True)

THREAD_TIMEOUT_SECONDS = 30


def restore_reference_rows() -> None:
    """The genus, locations, stage and media these tests use, if missing."""
    run("""
        INSERT INTO genera (code, name, active) VALUES ('PHL', 'Philodendron', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO locations (code, label, active)
            VALUES ('lab', 'Lab', true), ('nursery', 'Nursery', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO stages (code, label, sort_order, active)
            VALUES ('P2', 'P2', 3, true) ON CONFLICT DO NOTHING;
        INSERT INTO media_codes (code, label, active) VALUES ('M001', 'M001', true)
            ON CONFLICT DO NOTHING;
    """)


def at_the_same_moment(calls: list[Callable[[], object]]) -> list[object]:
    """Run each call in its own thread, all released together.

    Returns each call's result, or the exception it raised, in call order.
    """
    start = threading.Barrier(len(calls))
    results: list[object] = [None] * len(calls)

    def run_one(index: int, call: Callable[[], object]) -> None:
        try:
            start.wait()
            results[index] = call()
        except Exception as error:  # the test inspects what each call raised
            results[index] = error
        finally:
            connection.close()  # this thread's own connection

    threads = [
        threading.Thread(target=run_one, args=(index, call))
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
