"""U0.9 G2: a switched-off list item is refused when a person picks it (AC13).

The check is in the service (design §3.4, review H1 and M4): after the
permission check and `start_operation`, on the values a person picked. What a
record only carries is not checked: a split's location and stage, and a
Correction's values that are the same as they are now.

Items are switched off in set-up as System with a reason, since the Admin's
writers are stubs until G3.
"""

import uuid

import pytest
from django.contrib.auth.models import User

from cucumber.batches.models import Batch
from cucumber.core.tests.stock import (
    live_count,
    log,
    new_lab_batch,
    not_allowed,
    refused,
    save,
)
from cucumber.events.models import Event, Operation
from cucumber.events.services import NewBatch, NewEvent, correct, save_operation, split
from cucumber.references.lists import ListName
from cucumber.references.tests.support import switched_off

pytestmark = pytest.mark.django_db

INACTIVE = "list_item_inactive"
REASON = "correction_wrong_quantity"


def lab_intake(
    plant: int, *, media: str = "M001", stage: str = "P2", location: str = "lab"
) -> NewEvent:
    """An intake of 5 into a new batch, with the values a person picked."""
    batch = NewBatch(plant_id=plant, origin="intake", location_code=location)
    return NewEvent(
        "intake", new_batch=batch, qty_in=5, stage_to=stage, media_code=media
    )


def counts() -> tuple[int, int, int]:
    """Operations, events and batches saved so far."""
    return Operation.objects.count(), Event.objects.count(), Batch.objects.count()


# ------------------------------------------------------- save_operation


@pytest.mark.parametrize(
    ("name", "code", "picked"),
    [
        (ListName.MEDIA_CODES, "M002", {"media": "M002"}),
        (ListName.STAGES, "P1", {"stage": "P1"}),
        (ListName.LOCATIONS, "nursery", {"location": "nursery"}),
    ],
    ids=["medium", "stage", "location"],
)
def test_ac13_a_save_that_picks_a_switched_off_item_is_refused(
    plant: int, tech: User, name: ListName, code: str, picked: dict[str, str]
) -> None:
    switched_off(name, code)
    before = counts()

    with refused(INACTIVE):
        save(tech, lab_intake(plant, **picked))

    assert counts() == before


def test_ac13_the_same_items_are_fine_while_they_are_switched_on(
    plant: int, tech: User
) -> None:
    saved = save(tech, lab_intake(plant, media="M002", stage="P1"))

    assert len(saved.batch_ids) == 1


def test_ac13_a_switched_off_medium_on_an_existing_batch_is_refused(
    plant: int, tech: User
) -> None:
    batch = new_lab_batch(tech, plant, 10)
    switched_off(ListName.MEDIA_CODES, "M002")
    before = counts()

    with refused(INACTIVE):
        log(tech, batch, "intake", qty_in=2, stage_to="P2", media_code="M002")

    assert counts() == before
    assert live_count(batch) == 10


def test_ac13_one_refused_entry_writes_none_of_the_operation(
    plant: int, tech: User
) -> None:
    switched_off(ListName.MEDIA_CODES, "M002")
    before = counts()

    with refused(INACTIVE):
        save(tech, lab_intake(plant), lab_intake(plant, media="M002"))

    assert counts() == before


def test_ac13_the_permission_check_comes_before_the_inactive_check(
    plant: int, read_only: User
) -> None:
    switched_off(ListName.MEDIA_CODES, "M002")

    with not_allowed("role_not_allowed"):
        save(read_only, lab_intake(plant, media="M002"))


def test_h1_a_resend_of_a_saved_operation_still_gets_already_saved(
    plant: int, tech: User
) -> None:
    operation_id = uuid.uuid4()
    entries = [lab_intake(plant, media="M002")]
    first = save_operation(operation_id, tech, entries)
    switched_off(ListName.MEDIA_CODES, "M002")
    before = counts()

    second = save_operation(operation_id, tech, entries)

    assert second.already_saved
    assert (second.event_ids, second.batch_ids) == (first.event_ids, first.batch_ids)
    assert counts() == before


def test_h1_a_new_operation_with_the_same_medium_is_refused(
    plant: int, tech: User
) -> None:
    save_operation(uuid.uuid4(), tech, [lab_intake(plant, media="M002")])
    switched_off(ListName.MEDIA_CODES, "M002")

    with refused(INACTIVE):
        save_operation(uuid.uuid4(), tech, [lab_intake(plant, media="M002")])


# ------------------------------------------------------------------ split


@pytest.mark.parametrize(
    ("name", "code"),
    [(ListName.STAGES, "P2"), (ListName.LOCATIONS, "lab")],
    ids=["stage", "location"],
)
def test_h1_a_batch_in_a_switched_off_stage_or_location_can_be_split(
    plant: int, tech: User, name: ListName, code: str
) -> None:
    parent = new_lab_batch(tech, plant, 10)
    switched_off(name, code)

    saved = split(uuid.uuid4(), tech, parent, 4, note="pre-order")

    [child] = Batch.objects.filter(pk__in=saved.batch_ids)
    assert (child.parent_batch_id, child.live_count) == (parent, 4)
    assert (child.location_id, child.stage_id) == ("lab", "P2")
    assert live_count(parent) == 6


# ------------------------------------------------------------- Correction


@pytest.fixture
def lab_intake_event(plant: int, tech: User) -> tuple[int, int]:
    """A Lab batch of 10 and its intake event (medium M001, stage P2)."""
    batch = new_lab_batch(tech, plant, 10)
    return batch, Event.objects.get(batch_id=batch).pk


@pytest.mark.parametrize(
    ("media_code", "stage_to"),
    [(None, None), ("M001", None), (None, "P2"), ("M001", "P2")],
    ids=["left out", "medium sent again", "stage sent again", "both sent again"],
)
def test_m4_a_quantity_fix_works_while_the_event_s_medium_and_stage_are_off(
    lab_intake_event: tuple[int, int],
    supervisor: User,
    media_code: str | None,
    stage_to: str | None,
) -> None:
    batch, intake = lab_intake_event
    switched_off(ListName.MEDIA_CODES, "M001")
    switched_off(ListName.STAGES, "P2")

    saved = correct(
        supervisor, intake, REASON, qty_in=8, media_code=media_code, stage_to=stage_to
    )

    [fix] = Event.objects.filter(pk__in=saved.event_ids)
    assert (fix.corrects_event_id, fix.qty_in) == (intake, 8)
    assert (fix.media_code_id, fix.stage_to_id) == ("M001", "P2")
    assert live_count(batch) == 8


def test_m4_a_correction_may_move_off_a_switched_off_medium_to_an_active_one(
    lab_intake_event: tuple[int, int], supervisor: User
) -> None:
    _, intake = lab_intake_event
    switched_off(ListName.MEDIA_CODES, "M001")

    saved = correct(supervisor, intake, REASON, media_code="M004")

    assert Event.objects.get(pk=saved.event_ids[0]).media_code_id == "M004"


@pytest.mark.parametrize(
    ("name", "code", "media_code", "stage_to"),
    [
        (ListName.MEDIA_CODES, "M002", "M002", None),
        (ListName.STAGES, "P1", None, "P1"),
    ],
    ids=["medium", "stage"],
)
def test_ac13_a_correction_that_picks_a_switched_off_item_is_refused(
    lab_intake_event: tuple[int, int],
    supervisor: User,
    name: ListName,
    code: str,
    media_code: str | None,
    stage_to: str | None,
) -> None:
    batch, intake = lab_intake_event
    switched_off(name, code)
    before = counts()

    with refused(INACTIVE):
        correct(supervisor, intake, REASON, media_code=media_code, stage_to=stage_to)

    assert counts() == before
    assert live_count(batch) == 10


def test_ac13_a_pick_is_still_refused_when_the_quantity_changes_too(
    lab_intake_event: tuple[int, int], supervisor: User
) -> None:
    batch, intake = lab_intake_event
    switched_off(ListName.MEDIA_CODES, "M002")

    with refused(INACTIVE):
        correct(supervisor, intake, REASON, qty_in=8, media_code="M002")

    assert live_count(batch) == 10


def test_m4_restated_means_the_same_as_the_effective_value_not_the_first_row(
    lab_intake_event: tuple[int, int], supervisor: User
) -> None:
    """The intake's medium is M002 now (corrected once). Restating M002 after
    it is switched off keeps it, so a quantity fix still works (design §3.4,
    `current_values`)."""
    batch, intake = lab_intake_event
    correct(supervisor, intake, REASON, media_code="M002")
    switched_off(ListName.MEDIA_CODES, "M002")

    saved = correct(supervisor, intake, REASON, qty_in=8, media_code="M002")

    assert Event.objects.get(pk=saved.event_ids[0]).media_code_id == "M002"
    assert live_count(batch) == 8


def test_ac13_going_back_to_the_first_row_s_switched_off_medium_is_a_pick(
    lab_intake_event: tuple[int, int], supervisor: User
) -> None:
    """M001 is the intake row's medium, but the effective one is M002: sending
    M001 changes it, so a switched-off M001 is refused."""
    _, intake = lab_intake_event
    correct(supervisor, intake, REASON, media_code="M002")
    switched_off(ListName.MEDIA_CODES, "M001")
    before = counts()

    with refused(INACTIVE):
        correct(supervisor, intake, REASON, media_code="M001")

    assert counts() == before


def test_h1_a_resent_correction_still_gets_already_saved(
    lab_intake_event: tuple[int, int], supervisor: User
) -> None:
    _, intake = lab_intake_event
    operation_id = uuid.uuid4()
    first = correct(
        supervisor, intake, REASON, media_code="M002", operation_id=operation_id
    )
    switched_off(ListName.MEDIA_CODES, "M002")
    before = counts()

    second = correct(
        supervisor, intake, REASON, media_code="M002", operation_id=operation_id
    )

    assert second.already_saved
    assert second.event_ids == first.event_ids
    assert counts() == before
