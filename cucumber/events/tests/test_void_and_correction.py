"""U0.2b: Void and Correction (design §3.1; Q8; AC16e, AC16f).

Closing and reopening with a Void of the Close (AC12b–c) is in
test_event_services.py; what voids and corrections do to the review queue
(AC19b–c) is in test_reviews.py.
"""

import uuid
from typing import NamedTuple

import pytest
from django.contrib.auth.models import User

from cucumber.core.refusals import Refused
from cucumber.core.tests.stock import (
    batch_of,
    days_ago,
    intake_into_new_batch,
    live_count,
    log,
    new_lab_batch,
    refused,
    save,
    subculture_entries,
)
from cucumber.events.models import Event
from cucumber.events.services import Saved, correct, count_difference, split, void

pytestmark = pytest.mark.django_db


class Subcultured(NamedTuple):
    parent: int  # B010
    children: tuple[int, ...]  # B011–B013
    saved: Saved


@pytest.fixture
def subcultured(plant: int, tech: User) -> Subcultured:
    """B010 (10 jars) subcultured: 3 jars used, 3 child batches of 4 made."""
    parent = new_lab_batch(tech, plant, 10)
    saved = save(tech, *subculture_entries(parent, plant))
    return Subcultured(parent, saved.batch_ids, saved)


# ------------------------------------------------- operation-wide void (Q8)


def test_ac16e_voiding_one_event_voids_its_whole_operation(
    subcultured: Subcultured, tech: User
) -> None:
    b012_intake = Event.objects.get(batch_id=subcultured.children[1]).pk

    result = void(tech, b012_intake, "void_wrong_batch")

    voids = Event.objects.filter(pk__in=result.event_ids)
    assert len(voids) == len(subcultured.saved.event_ids)
    assert {v.voids_event_id for v in voids} == set(subcultured.saved.event_ids)
    assert {(v.action, v.reason_id) for v in voids} == {("void", "void_wrong_batch")}
    assert {v.operation_id for v in voids} == {result.operation_id}
    assert result.operation_id != subcultured.saved.operation_id


def test_ac16e_batches_the_operation_made_become_voided(
    subcultured: Subcultured, tech: User
) -> None:
    void(tech, subcultured.saved.event_ids[0], "void_wrong_batch")
    for child_id in subcultured.children:
        child = batch_of(child_id)
        assert (child.status, child.live_count) == ("voided", 0)
        assert child.voided_at is not None
    parent = batch_of(subcultured.parent)
    assert (parent.status, parent.live_count) == ("open", 10)


def test_ac16e_a_later_event_on_a_made_batch_blocks_the_void_and_is_named(
    subcultured: Subcultured, tech: User
) -> None:
    later = log(tech, subcultured.children[1], "count", counted_qty=4)

    with pytest.raises(Refused) as caught:
        void(tech, subcultured.saved.event_ids[0], "void_wrong_batch")

    assert (caught.value.rule, caught.value.event_ids) == (
        "void_has_later_events",
        (later,),
    )
    assert not Event.objects.filter(action="void").exists()
    assert {batch_of(b).status for b in subcultured.children} == {"open"}


def test_once_the_later_event_is_voided_the_operation_can_be_voided(
    subcultured: Subcultured, tech: User
) -> None:
    later = log(tech, subcultured.children[1], "count", counted_qty=4)
    void(tech, later, "void_wrong_batch")
    void(tech, subcultured.saved.event_ids[0], "void_wrong_batch")
    assert {batch_of(b).status for b in subcultured.children} == {"voided"}


# --------------------------------------------------------------- void rules


def test_a_void_cannot_be_voided(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    the_void = void(tech, log(tech, batch, "out", qty_out=1), "void_wrong_batch")
    with refused("void_of_void"):
        void(tech, the_void.event_ids[0], "void_wrong_batch")


def test_an_event_is_voided_only_once(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    out = log(tech, batch, "out", qty_out=1)
    void(tech, out, "void_wrong_batch")
    with refused("event_void_once"):
        void(tech, out, "void_duplicate_entry")


def test_a_void_that_takes_the_batch_below_zero_is_refused(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 2)
    added = log(tech, batch, "intake", qty_in=10)
    log(tech, batch, "out", qty_out=11)
    with refused("batch_count_not_negative"):
        void(tech, added, "void_wrong_batch")
    assert live_count(batch) == 1


# --------------------------------------------------------------- correction


def test_a_correction_restates_a_value_and_the_count_follows(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    out = log(tech, batch, "out", qty_out=3)

    saved = correct(tech, out, "correction_wrong_quantity", qty_out=1)

    [fix] = Event.objects.filter(pk__in=saved.event_ids)
    assert (fix.action, fix.corrects_event_id, fix.batch_id) == (
        "correction",
        out,
        batch,
    )
    assert (fix.qty_out, fix.reason_id) == (1, "correction_wrong_quantity")
    assert live_count(batch) == 9


def test_m1_a_correction_that_doesn_t_fix_the_date_keeps_the_original_s(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 10, occurred_at=days_ago(4, 9))
    out = log(tech, batch, "out", qty_out=3, occurred_at=days_ago(3, 9))
    saved = correct(tech, out, "correction_wrong_quantity", qty_out=2)
    fix = Event.objects.get(pk=saved.event_ids[0])
    assert fix.occurred_at == days_ago(3, 9)


def test_q5_a_reviewer_s_date_fix_may_go_back_more_than_7_days(
    plant: int, tech: User, supervisor: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    three_weeks_ago = days_ago(21, 12)
    first = Event.objects.get(batch_id=batch).pk
    correct(supervisor, first, "correction_wrong_date", occurred_at=three_weeks_ago)
    [effective] = Event.objects.effective_events(batch)
    assert (effective.id, effective.occurred_at) == (first, three_weeks_ago)


def test_a_second_correction_keeps_the_first_one_s_fix(plant: int, tech: User) -> None:
    batch = new_lab_batch(tech, plant, 10)
    added = log(tech, batch, "intake", qty_in=5, stage_to="P2", media_code="M001")
    correct(tech, added, "correction_wrong_media_code", media_code="M002")
    correct(tech, added, "correction_wrong_quantity", qty_in=4)
    effective = next(e for e in Event.objects.effective_events(batch) if e.id == added)
    assert (effective.qty_in, effective.media_code) == (4, "M002")
    assert live_count(batch) == 14


# ------------------------------------------- paired corrections (Q8, AC16f)


@pytest.mark.parametrize("side", ["split", "intake"])
def test_ac16f_correcting_a_split_corrects_both_sides(
    plant: int, tech: User, side: str
) -> None:
    parent = intake_into_new_batch(tech, plant, 100)  # B010
    saved = split(uuid.uuid4(), tech, parent, 40, note="pre-order")
    [child] = saved.batch_ids  # B015
    moved_out = Event.objects.get(operation_id=saved.operation_id, action="split")
    moved_in = Event.objects.get(operation_id=saved.operation_id, action="intake")

    if side == "split":
        result = correct(tech, moved_out.pk, "correction_wrong_quantity", qty_out=30)
    else:
        result = correct(tech, moved_in.pk, "correction_wrong_quantity", qty_in=30)

    fixes = Event.objects.filter(pk__in=result.event_ids)
    assert {(f.batch_id, f.corrects_event_id, f.qty_in, f.qty_out) for f in fixes} == {
        (parent, moved_out.pk, 0, 30),
        (child, moved_in.pk, 30, 0),
    }
    assert {f.operation_id for f in fixes} == {result.operation_id}
    assert (live_count(parent), live_count(child)) == (70, 30)


def test_a_quantity_correction_of_a_subculture_leaves_its_children(
    subcultured: Subcultured, tech: User
) -> None:
    used = subcultured.saved.event_ids[0]
    result = correct(tech, used, "correction_wrong_quantity", qty_out=2)
    assert len(result.event_ids) == 1
    assert live_count(subcultured.parent) == 8
    assert [live_count(child) for child in subcultured.children] == [4, 4, 4]


def test_a_paired_correction_that_takes_the_child_below_zero_is_refused(
    plant: int, tech: User
) -> None:
    parent = intake_into_new_batch(tech, plant, 100)
    saved = split(uuid.uuid4(), tech, parent, 40, note="pre-order")
    [child] = saved.batch_ids
    log(tech, child, "out", qty_out=35)
    moved_out = Event.objects.get(operation_id=saved.operation_id, action="split")
    with refused("batch_count_not_negative"):
        correct(tech, moved_out.pk, "correction_wrong_quantity", qty_out=30)
    assert (live_count(parent), live_count(child)) == (60, 5)


# ------------------------------------- fixes to events before a count (§3.1)


class Counted(NamedTuple):
    batch: int
    count_event: int
    loss: int


@pytest.fixture
def loss_before_count(plant: int, tech: User) -> Counted:
    """AC16g: 100 Monday, a count of 98 Wednesday, then a loss of 5 dated Tuesday."""
    batch = intake_into_new_batch(tech, plant, 100, occurred_at=days_ago(3, 9))
    count = log(tech, batch, "count", counted_qty=98, occurred_at=days_ago(1, 9))
    loss = log(
        tech,
        batch,
        "loss",
        qty_out=5,
        reason_code="loss_rot",
        occurred_at=days_ago(2, 9),
    )
    return Counted(batch, count, loss)


def test_voiding_an_event_before_a_count_changes_only_the_difference(
    loss_before_count: Counted, tech: User
) -> None:
    void(tech, loss_before_count.loss, "void_wrong_batch")
    assert live_count(loss_before_count.batch) == 98
    assert count_difference(loss_before_count.count_event) == -2


def test_correcting_an_event_before_a_count_changes_only_the_difference(
    loss_before_count: Counted, tech: User
) -> None:
    correct(tech, loss_before_count.loss, "correction_wrong_quantity", qty_out=2)
    assert live_count(loss_before_count.batch) == 98
    assert count_difference(loss_before_count.count_event) == 0


def test_correcting_a_count_sets_the_total(plant: int, tech: User) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    count = log(tech, batch, "count", counted_qty=8)
    correct(tech, count, "correction_wrong_quantity", counted_qty=9)
    assert live_count(batch) == 9
    assert count_difference(count) == -1


def test_a_correction_that_takes_the_batch_below_zero_is_refused(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 5)
    out = log(tech, batch, "out", qty_out=3)
    with refused("batch_count_not_negative"):
        correct(tech, out, "correction_wrong_quantity", qty_out=6)
    assert live_count(batch) == 2


def test_corrections_point_at_the_original_never_at_a_fix(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 10)
    out = log(tech, batch, "out", qty_out=3)
    fix = correct(tech, out, "correction_wrong_quantity", qty_out=2).event_ids[0]
    with refused("event_not_correctable"):
        correct(tech, fix, "correction_wrong_quantity", qty_out=1)
    other = log(tech, batch, "out", qty_out=1)
    the_void = void(tech, other, "void_wrong_batch").event_ids[0]
    with refused("event_not_correctable"):
        correct(tech, the_void, "correction_wrong_quantity", qty_out=1)
