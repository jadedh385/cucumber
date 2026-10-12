"""U0.2b: review rules and the queue (design §2.5, Q3, rule 10; AC19a–d).

Also the "dated before a count" flag (AC16g) and the operation-wide void
shown as one queue item (Q8, architect review M2).
"""

import uuid

import pytest
from django.contrib.auth.models import User

from cucumber.core.tests.stock import (
    days_ago,
    intake_into_new_batch,
    log,
    new_lab_batch,
    refused,
    save,
    subculture_entries,
)
from cucumber.events.models import Event, EventReview
from cucumber.events.reviews import DATED_BEFORE_COUNT, review, review_queue
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
    out = log(tech, stock, "out", qty_out=1)
    with refused("review_not_allowed"):
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


@pytest.mark.parametrize("who", ["tech", "supervisor", "other_supervisor"])
def test_ac19d_neither_person_on_it_nor_another_supervisor_may_review_it(
    saved_for_tech: uuid.UUID, request: pytest.FixtureRequest, who: str
) -> None:
    reviewer: User = request.getfixturevalue(who)
    with refused("review_not_allowed"):
        review(reviewer, saved_for_tech)
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


def test_a_tech_s_fix_of_their_own_entry_does_not_review_it(
    stock: int, tech: User, supervisor: User
) -> None:
    out = log(tech, stock, "out", qty_out=3)
    fix = correct(tech, out, "correction_wrong_quantity", qty_out=2)
    assert reviewers_of(out) == []
    assert {out, *fix.event_ids} <= queued(supervisor)


def test_the_admin_s_own_fix_is_reviewed_as_it_is_saved(
    stock: int, tech: User, admin: User
) -> None:
    out = log(tech, stock, "out", qty_out=3)
    fix = correct(admin, out, "correction_wrong_quantity", qty_out=2)
    [fix_id] = fix.event_ids
    assert reviewers_of(out) == [admin.pk]
    assert reviewers_of(fix_id) == [admin.pk]
    assert {out, fix_id}.isdisjoint(queued(admin))


# ------------------------------------------- dated before a count (AC16g)


def test_ac16g_an_entry_dated_before_a_count_is_flagged(
    plant: int, admin: User, tech: User
) -> None:
    batch = intake_into_new_batch(admin, plant, 100, occurred_at=days_ago(3, 9))
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
