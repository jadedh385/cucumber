"""U0.8 AC12: a voided or retired record's number is never given again.

Nothing is deleted (`*_no_delete`, `*_append_only`) and the generator only
moves forward, so a new record always gets a higher number. A former SKU is
never issued again either: U0.2's test in `plants/tests/test_reclassification.py`
(`test_ac4b_no_other_plant_can_ever_get_the_old_sku`) proves it, kept as it is.
"""

import pytest

from cucumber.core.tests.rows import db_now, make_batch, make_event, make_plant

pytestmark = pytest.mark.django_db


def test_ac12_a_voided_or_retired_plant_s_number_is_never_given_again(
    user: int,
) -> None:
    voided = make_plant(user, status="voided", full_name="Voided")
    retired = make_plant(user, status="retired", full_name="Retired")

    new = make_plant(user, full_name="New")

    assert new > max(voided, retired)


def test_ac12_a_voided_batch_s_number_is_never_given_again(
    plant: int, user: int
) -> None:
    voided = make_batch(plant, user, status="voided", voided_at=db_now())

    new = make_batch(plant, user)

    assert new > voided


def test_ac12_a_voided_event_s_number_is_never_given_again(
    batch: int, user: int
) -> None:
    original = make_event(batch, user, "count", counted_qty=0)
    make_event(batch, user, "void", "void", voids_event_id=original)

    new = make_event(batch, user, "count", counted_qty=0)

    assert new > original
