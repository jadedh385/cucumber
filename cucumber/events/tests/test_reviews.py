"""U0.2b: review rules and the queue (design §2.5, Q3, rule 10; AC19a–d).

Also the "dated before a count" flag (AC16g) and the operation-wide void
shown as one queue item (Q8, architect review M2).
"""

import uuid

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cucumber.core.tests.stock import (
    days_ago,
    intake_into_new_batch,
    log,
    new_lab_batch,
    not_allowed,
    refused,
    save,
    subculture_entries,
)
from cucumber.events.models import Event, EventReview
from cucumber.events.reviews import (
    DATED_BEFORE_COUNT,
    ENTERED_LATE,
    review,
    review_queue,
)
from cucumber.events.services import correct, void

pytestmark = pytest.mark.django_db


def queued(reviewer: User) -> set[int]:
    """Every event id in `reviewer`'s queue."""
    return {event for item in review_queue(reviewer) for event in item.event_ids}


def reviewers_of(event_id: int) -> list[int]:
    return list(
        EventReview.objects.filter(event_id=event_id).values_list(
            "reviewer_id", flat=True
        )
    )


@pytest.fixture
def stock(plant: int, admin: User) -> int:
    """A Nursery batch of 10 the Admin took in: reviewed already, out of the queue."""
    return intake_into_new_batch(admin, plant, 10)


# ------------------------------------------------- Admin auto-review (AC19a)


def test_ac19a_the_admin_s_own_entry_is_reviewed_as_it_is_saved(
    stock: int, admin: User, supervisor: User
) -> None:
    [event] = Event.objects.filter(batch_id=stock)
    review_row = EventReview.objects.get(event=event)
    assert (review_row.reviewer_id, review_row.note) == (admin.pk, "Admin, own entry")
    assert event.pk not in queued(admin) | queued(supervisor)


def test_the_admin_reviews_work_they_did_that_a_supervisor_saved(
    stock: int, admin: User, supervisor: User
) -> None:
    out = log(supervisor, stock, "out", qty_out=1, staff_id=admin.pk)
    assert reviewers_of(out) == []
    assert out in queued(admin)
    review(admin, Event.objects.get(pk=out).operation_id)
    assert reviewers_of(out) == [admin.pk]


# ------------------------------------------------------- who reviews what


def test_a_tech_entry_waits_for_a_supervisor_or_the_admin(
    stock: int, tech: User, other_tech: User, supervisor: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=1)
    assert out in queued(supervisor) & queued(admin)
    assert out not in queued(tech) | queued(other_tech)


def test_a_supervisor_reviews_a_tech_entry(
    stock: int, tech: User, supervisor: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=1)
    review(supervisor, Event.objects.get(pk=out).operation_id, note="looks right")
    review_row = EventReview.objects.get(event_id=out)
    assert (review_row.reviewer_id, review_row.note) == (supervisor.pk, "looks right")
    assert out not in queued(admin)


def test_a_tech_cannot_review(stock: int, tech: User, other_tech: User) -> None:
    """The matrix refuses first (U0.6): a Tech has no Review events row."""
    out = log(tech, stock, "out", qty_out=1)
    with not_allowed("role_not_allowed"):
        review(other_tech, Event.objects.get(pk=out).operation_id)


def test_a_supervisor_s_own_entry_waits_for_the_admin(
    stock: int, supervisor: User, other_supervisor: User, admin: User
) -> None:
    out = log(supervisor, stock, "out", qty_out=1)
    operation_id = Event.objects.get(pk=out).operation_id
    for reviewer in (supervisor, other_supervisor):
        with refused("review_not_allowed"):
            review(reviewer, operation_id)
    assert out in queued(admin)
    assert out not in queued(supervisor) | queued(other_supervisor)


# -------------------------------------- work saved for someone else (AC19d)


@pytest.fixture
def saved_for_tech(plant: int, admin: User, tech: User, supervisor: User) -> uuid.UUID:
    """A Subculture done by the Tech and saved by the Supervisor."""
    parent = new_lab_batch(admin, plant, 10)
    entries = subculture_entries(parent, plant, staff_id=tech.pk)
    return save(supervisor, *entries).operation_id


def test_ac19d_the_event_records_who_did_it_and_who_saved_it(
    saved_for_tech: uuid.UUID, tech: User, supervisor: User
) -> None:
    events = Event.objects.filter(operation_id=saved_for_tech)
    assert {(e.staff_id, e.recorded_by_id) for e in events} == {
        (tech.pk, supervisor.pk)
    }


@pytest.mark.parametrize("who", ["supervisor", "other_supervisor"])
def test_ac19d_neither_person_on_it_nor_another_supervisor_may_review_it(
    saved_for_tech: uuid.UUID, request: pytest.FixtureRequest, who: str
) -> None:
    reviewer: User = request.getfixturevalue(who)
    with refused("review_not_allowed"):
        review(reviewer, saved_for_tech)
    assert not EventReview.objects.filter(event__operation_id=saved_for_tech).exists()


def test_ac19d_the_tech_who_did_it_may_not_review_it(
    saved_for_tech: uuid.UUID, tech: User
) -> None:
    with not_allowed("role_not_allowed"):
        review(tech, saved_for_tech)
    assert not EventReview.objects.filter(event__operation_id=saved_for_tech).exists()


def test_ac19d_it_waits_for_the_admin(
    saved_for_tech: uuid.UUID, admin: User, supervisor: User
) -> None:
    event_ids = set(
        Event.objects.filter(operation_id=saved_for_tech).values_list("id", flat=True)
    )
    assert event_ids <= queued(admin)
    assert not event_ids & queued(supervisor)
    review(admin, saved_for_tech)
    assert EventReview.objects.filter(event_id__in=event_ids).count() == 4


# --------------------------------------------------------- voids (AC19b, M2)


def test_ac19b_a_voided_entry_leaves_the_queue_and_its_void_waits_for_the_admin(
    stock: int, tech: User, supervisor: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=1)
    the_void = void(tech, out, "void_duplicate_entry")
    [void_id] = the_void.event_ids
    assert out not in queued(supervisor) | queued(admin)
    assert void_id in queued(admin)
    assert void_id not in queued(supervisor)
    assert reviewers_of(out) == []  # the Tech can't review their own entry


def test_m2_an_operation_wide_void_is_one_queue_item(
    plant: int, admin: User, tech: User
) -> None:
    parent = new_lab_batch(admin, plant, 10)
    subculture = save(tech, *subculture_entries(parent, plant))
    the_void = void(tech, subculture.event_ids[0], "void_wrong_batch")

    items = [i for i in review_queue(admin) if i.operation_id == the_void.operation_id]

    assert [set(item.event_ids) for item in items] == [set(the_void.event_ids)]
    review(admin, the_void.operation_id)
    for void_id in the_void.event_ids:
        assert reviewers_of(void_id) == [admin.pk]


# ------------------------------------------ a fix marks reviewed (AC19c, Q3)


def test_ac19c_a_supervisor_s_correction_marks_the_original_reviewed(
    stock: int, tech: User, supervisor: User, other_supervisor: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=3)
    fix = correct(supervisor, out, "correction_wrong_quantity", qty_out=2)
    [fix_id] = fix.event_ids
    assert reviewers_of(out) == [supervisor.pk]
    assert out not in queued(admin)
    assert fix_id in queued(admin)
    assert fix_id not in queued(supervisor) | queued(other_supervisor)


def test_a_supervisor_s_void_marks_the_original_reviewed(
    stock: int, tech: User, supervisor: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=3)
    the_void = void(supervisor, out, "void_duplicate_entry")
    assert reviewers_of(out) == [supervisor.pk]
    assert set(the_void.event_ids) <= queued(admin)


def test_a_tech_s_undo_of_their_own_entry_does_not_review_it(
    stock: int, tech: User, admin: User
) -> None:
    """A Tech can't correct (U0.6); their fix is an Undo, which the Admin reviews."""
    out = log(tech, stock, "out", qty_out=3)
    undo = void(tech, out, "void_duplicate_entry")
    assert reviewers_of(out) == []
    assert set(undo.event_ids) <= queued(admin)


def test_the_admin_s_own_fix_is_reviewed_as_it_is_saved(
    stock: int, tech: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=3)
    fix = correct(admin, out, "correction_wrong_quantity", qty_out=2)
    [fix_id] = fix.event_ids
    assert reviewers_of(out) == [admin.pk]
    assert reviewers_of(fix_id) == [admin.pk]
    assert {out, fix_id}.isdisjoint(queued(admin))


# ------------------------------- more fixes and Admin saves (Q3, rule 10)


def test_a_reviewer_s_fix_of_an_entry_they_already_reviewed_keeps_one_review(
    stock: int, tech: User, supervisor: User
) -> None:
    out = log(tech, stock, "out", qty_out=3)
    review(supervisor, Event.objects.get(pk=out).operation_id)
    correct(supervisor, out, "correction_wrong_quantity", qty_out=2)
    assert reviewers_of(out) == [supervisor.pk]


def test_the_admin_s_fix_of_their_own_entry_keeps_one_review(
    stock: int, admin: User
) -> None:
    out = log(admin, stock, "out", qty_out=3)
    fix = correct(admin, out, "correction_wrong_quantity", qty_out=2)
    assert reviewers_of(out) == [admin.pk]
    assert reviewers_of(fix.event_ids[0]) == [admin.pk]


def test_a_supervisor_s_fix_doesn_t_review_an_entry_they_may_not_review(
    stock: int, tech: User, supervisor: User, other_supervisor: User
) -> None:
    """Saved by another Supervisor, for a Tech: only the Admin reviews it.

    (A Supervisor can't correct an entry they saved themselves, U0.6 §4.2.)
    """
    out = log(other_supervisor, stock, "out", qty_out=3, staff_id=tech.pk)
    correct(supervisor, out, "correction_wrong_quantity", qty_out=2)
    assert reviewers_of(out) == []


def test_every_event_of_an_admin_operation_is_reviewed_as_it_is_saved(
    plant: int, admin: User
) -> None:
    parent = new_lab_batch(admin, plant, 10)
    saved = save(admin, *subculture_entries(parent, plant))
    for event_id in saved.event_ids:
        assert reviewers_of(event_id) == [admin.pk]


def test_the_admin_s_void_is_reviewed_as_it_is_saved(
    stock: int, tech: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=1)
    [void_id] = void(admin, out, "void_duplicate_entry").event_ids
    assert reviewers_of(void_id) == [admin.pk]
    assert void_id not in queued(admin)


def test_reviewing_an_operation_twice_writes_no_second_review(
    stock: int, tech: User, supervisor: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=1)
    operation_id = Event.objects.get(pk=out).operation_id
    review(supervisor, operation_id)
    with refused("event_review_once"):
        review(admin, operation_id)
    assert reviewers_of(out) == [supervisor.pk]


# ------------------------------------------- dated before a count (AC16g)


def test_ac16g_an_entry_dated_before_a_count_already_saved_is_flagged(
    plant: int, admin: User, tech: User
) -> None:
    batch = intake_into_new_batch(admin, plant, 100, occurred_at=days_ago(3, 9))
    # Normal order: this entry is saved first, the count comes later.
    earlier = log(tech, batch, "intake", qty_in=2, occurred_at=days_ago(3, 12))
    log(admin, batch, "count", counted_qty=98, occurred_at=days_ago(1, 9))
    before = log(
        tech,
        batch,
        "loss",
        qty_out=5,
        reason_code="loss_rot",
        occurred_at=days_ago(2, 9),
    )
    after = log(tech, batch, "loss", qty_out=1, reason_code="loss_rot")

    flags = {item.event_ids: item.flags for item in review_queue(admin)}

    assert DATED_BEFORE_COUNT in flags[(before,)]
    assert DATED_BEFORE_COUNT not in flags[(after,)]
    assert DATED_BEFORE_COUNT not in flags[(earlier,)]


# ------------------------------------------------ entered late (Q5, §3.1)


def test_an_entry_dated_more_than_24_hours_back_is_flagged_late(
    plant: int, tech: User, admin: User
) -> None:
    # Taken in before the late entry's date, so its own date stays above zero.
    stock = intake_into_new_batch(admin, plant, 10, occurred_at=days_ago(3, 9))
    late = log(tech, stock, "out", qty_out=1, occurred_at=days_ago(2, 9))
    on_time = log(tech, stock, "out", qty_out=1)

    flags = {item.event_ids: item.flags for item in review_queue(admin)}

    assert ENTERED_LATE in flags[(late,)]
    assert ENTERED_LATE not in flags[(on_time,)]


# ------------------------------------------------------- G4 review fixes


def test_reviewing_an_operation_with_nothing_waiting_is_refused(
    stock: int, tech: User, supervisor: User
) -> None:
    """Already reviewed, voided, or no such operation: say so (G4 MEDIUM 4)."""
    out = log(tech, stock, "out", qty_out=1)
    operation_id = Event.objects.get(pk=out).operation_id
    review(supervisor, operation_id)

    with refused("event_review_once"):
        review(supervisor, operation_id)
    with refused("event_review_once"):
        review(supervisor, uuid.uuid4())


def queue_queries(reviewer: User) -> int:
    with CaptureQueriesContext(connection) as queries:
        review_queue(reviewer)
    return len(queries)


def test_the_queue_takes_the_same_queries_however_many_batches_wait(
    plant: int, tech: User, supervisor: User
) -> None:
    """No query per batch (G4 database HIGH 2)."""
    for _ in range(2):
        log(tech, intake_into_new_batch(tech, plant, 5), "count", counted_qty=5)
    few = queue_queries(supervisor)
    for _ in range(4):
        log(tech, intake_into_new_batch(tech, plant, 5), "count", counted_qty=5)
    assert queue_queries(supervisor) == few


def test_a_review_reads_the_reviewer_s_role_once(
    stock: int, tech: User, supervisor: User
) -> None:
    """One standing query, then the matrix rows are checked on it (G4 L5)."""
    operation_id = Event.objects.get(pk=log(tech, stock, "out", qty_out=1)).operation_id

    with CaptureQueriesContext(connection) as queries:
        review(supervisor, operation_id)

    standing_reads = [
        query["sql"]
        for query in queries.captured_queries
        if query["sql"].startswith('SELECT "auth_user"."is_active"')
    ]
    assert len(standing_reads) == 1, standing_reads
