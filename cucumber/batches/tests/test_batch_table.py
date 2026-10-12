"""U0.2a: batches (design §2.3; AC7–AC12, SOP §5 rules 5, 6, 7, 9).

No delete is in core/tests/test_protection.py.
"""

import pytest

from cucumber.core.tests.rows import (
    db_now,
    fetch_one,
    make_batch,
    make_plant,
    refused_by,
    run,
    update,
)

pytestmark = pytest.mark.django_db

CLOSE_STAMPS = [("closed", "closed_at"), ("voided", "voided_at")]


# --------------------------------------------------------- lineage (rule 5)


@pytest.mark.parametrize("origin", ["subculture", "split", "quarantine", "transfer"])
def test_ac7_a_batch_made_from_another_needs_its_parent(
    plant: int, user: int, origin: str
) -> None:
    with refused_by("batch_needs_parent"):
        make_batch(plant, user, origin=origin)


def test_ac7_an_intake_needs_no_parent(plant: int, user: int) -> None:
    make_batch(plant, user, origin="intake")


def test_ac7_a_subculture_with_its_parent_is_accepted(
    plant: int, user: int, batch: int
) -> None:
    child = make_batch(plant, user, origin="subculture", parent_batch_id=batch)
    row = fetch_one("SELECT parent_batch_id FROM batches WHERE id = %s", [child])
    assert row == (batch,)


def test_ac8_parent_must_belong_to_the_same_plant(user: int, batch: int) -> None:
    other_plant = make_plant(user, full_name="Birkin")
    with refused_by("batch_parent_same_plant"):
        make_batch(other_plant, user, origin="subculture", parent_batch_id=batch)


def test_a_batch_cannot_be_its_own_parent(batch: int) -> None:
    with refused_by("batch_not_own_parent"):
        run("UPDATE batches SET parent_batch_id = id WHERE id = %s", [batch])


# ----------------------------------------------------------- stage (rule 6)


def test_ac9_a_lab_batch_needs_a_stage(plant: int, user: int) -> None:
    with refused_by("batch_lab_needs_stage"):
        make_batch(plant, user, location_code="lab", stage_code=None)


def test_ac9_a_lab_batch_with_a_stage_is_accepted(plant: int, user: int) -> None:
    make_batch(plant, user, location_code="lab", stage_code="P0")


def test_ac9_a_nursery_batch_may_have_no_stage(plant: int, user: int) -> None:
    make_batch(plant, user, location_code="nursery", stage_code=None)


# ------------------------------------------------------- count (rules 7, 9)


def test_ac10_live_count_never_goes_below_zero(plant: int, user: int) -> None:
    batch = make_batch(plant, user, live_count=3)
    with refused_by("batch_count_not_negative"):
        update("batches", batch, {"live_count": -1})


@pytest.mark.parametrize(("status", "stamp"), CLOSE_STAMPS)
def test_ac11_a_batch_with_units_cannot_close_or_be_voided(
    plant: int, user: int, status: str, stamp: str
) -> None:
    batch = make_batch(plant, user, live_count=3)
    with refused_by("batch_closed_needs_zero"):
        update("batches", batch, {"status": status, stamp: db_now()})


@pytest.mark.parametrize(("status", "stamp"), CLOSE_STAMPS)
def test_ac11_an_empty_batch_can_close_or_be_voided(
    batch: int, status: str, stamp: str
) -> None:
    update("batches", batch, {"status": status, stamp: db_now()})


@pytest.mark.parametrize(
    ("status", "stamped", "rule"),
    [
        ("closed", None, "batch_closed_at_matches"),
        ("open", "closed_at", "batch_closed_at_matches"),
        ("voided", None, "batch_voided_at_matches"),
        ("open", "voided_at", "batch_voided_at_matches"),
    ],
)
def test_close_and_void_dates_match_the_status(
    batch: int, status: str, stamped: str | None, rule: str
) -> None:
    """Q7: voiding a Close reopens the batch, so `closed_at` must clear with it."""
    values: dict[str, object] = {"status": status}
    if stamped:
        values[stamped] = db_now()
    with refused_by(rule):
        update("batches", batch, values)


def test_ac12_a_plant_can_have_several_open_batches_in_one_place(
    plant: int, user: int
) -> None:
    """Q7: no standing-batch rule."""
    make_batch(plant, user, location_code="nursery")
    make_batch(plant, user, location_code="nursery")
    row = fetch_one(
        "SELECT count(*) FROM batches WHERE plant_id = %s AND status = 'open'",
        [plant],
    )
    assert row == (2,)


# ------------------------------------------------------- quarantine (D-02)


def test_only_a_quarantine_batch_is_quarantined(
    plant: int, user: int, batch: int
) -> None:
    with refused_by("batch_quarantine_origin"):
        make_batch(
            plant, user, origin="subculture", parent_batch_id=batch, quarantined=True
        )


def test_a_quarantine_child_can_be_quarantined(
    plant: int, user: int, batch: int
) -> None:
    make_batch(
        plant, user, origin="quarantine", parent_batch_id=batch, quarantined=True
    )


# ----------------------------------------------------- lists and numbering


@pytest.mark.parametrize(
    ("column", "value", "rule"),
    [
        ("origin", "purchase", "batch_origin_valid"),
        ("status", "archived", "batch_status_valid"),
    ],
)
def test_batch_values_come_from_their_lists(
    plant: int, user: int, column: str, value: str, rule: str
) -> None:
    with refused_by(rule):
        make_batch(plant, user, **{column: value})


def test_batch_number_is_unique_per_plant(plant: int, user: int) -> None:
    """The `Bnnn` in `PHL001 · B003`; allocating it is U0.8."""
    make_batch(plant, user, plant_seq=3)
    with refused_by("batch_plant_seq_unique"):
        make_batch(plant, user, plant_seq=3)


def test_two_plants_can_both_have_batch_one(plant: int, user: int) -> None:
    other = make_plant(user, full_name="Birkin")
    make_batch(plant, user, plant_seq=1)
    make_batch(other, user, plant_seq=1)
