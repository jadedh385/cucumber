"""U0.8 AC5–AC8, S3: typed text into the record it names (design §3.3).

Voided records are found too: an ID always points at its record. A former
SKU finds the plant it was issued to, with `former_sku` set so a screen can
say "PHL005 is now HYA004". One query for each look-up, two for a short
name, none for text that isn't an ID.
"""

import pytest
from pytest_django import DjangoAssertNumQueries

from cucumber.batches.models import Batch
from cucumber.core.refusals import message_for
from cucumber.core.tests.rows import (
    as_system,
    db_now,
    give_sku,
    issue_sku,
    make_batch,
    make_event,
    make_plant,
    update,
)
from cucumber.events.models import Event
from cucumber.ids.lookup import Found, find_by_sku, look_up
from cucumber.ids.reading import Kind
from cucumber.ids.tests.generators import AHEAD, next_id
from cucumber.plants.models import Plant

pytestmark = pytest.mark.django_db


def found(text: str) -> tuple[Kind, int, str | None]:
    """What `look_up` found, as (kind, the record's id, former SKU)."""
    result = look_up(text)
    assert result is not None, f"nothing found for {text!r}"
    return result.kind, int(result.record.pk), result.former_sku


@pytest.fixture
def reclassified(user: int) -> int:
    """A plant that held PHL005 and now holds HYA004 (a genus reclassification)."""
    plant = make_plant(user, full_name="Glorious")
    give_sku(plant, "PHL005", user)
    issue_sku(plant, "HYA004", user)
    with as_system():
        update("plants", plant, {"genus_code": "HYA", "sku": "HYA004"})
    return plant


# -------------------------------------------------------------------- AC5
@pytest.mark.parametrize("spelling", ["PLT-{:04d}", "plt-{}", "PLT{}", "PLT {:06d}"])
def test_ac5_a_typed_plant_id_finds_the_plant(plant: int, spelling: str) -> None:
    assert found(spelling.format(plant)) == (Kind.PLANT, plant, None)


def test_ac5_a_typed_batch_id_finds_the_batch(batch: int) -> None:
    assert found(f"bat-{batch}") == (Kind.BATCH, batch, None)


def test_ac5_a_typed_event_id_finds_the_event(batch: int, user: int) -> None:
    event = make_event(batch, user, "count", counted_qty=0)

    assert found(f"EVT{event:05d}") == (Kind.EVENT, event, None)


def test_ac5_the_record_found_is_the_model_instance(plant: int) -> None:
    result = look_up(f"PLT-{plant}")

    assert isinstance(result, Found)
    assert isinstance(result.record, Plant)


# -------------------------------------------------------------------- AC6
@pytest.mark.parametrize("text", ["PHL005", "phl005", "PHL5"])
def test_ac6_a_typed_sku_finds_its_plant(plant: int, user: int, text: str) -> None:
    give_sku(plant, "PHL005", user)

    assert found(text) == (Kind.PLANT, plant, None)


def test_ac6_a_former_sku_finds_the_plant_and_says_it_is_former(
    reclassified: int,
) -> None:
    assert found("phl5") == (Kind.PLANT, reclassified, "PHL005")
    assert found("HYA004") == (Kind.PLANT, reclassified, None)


def test_ac6_find_by_sku_finds_current_and_former_skus(reclassified: int) -> None:
    for text in ("PHL005", "HYA004"):
        plant = find_by_sku(text)
        assert plant is not None and plant.pk == reclassified, text
    assert find_by_sku("PHL999") is None


# -------------------------------------------------------------------- AC7
@pytest.mark.parametrize("spelling", ["PHL005 · B{:03d}", "phl5 b{}", "PHL005-B{}"])
def test_ac7_a_typed_short_name_finds_the_batch(
    plant: int, user: int, spelling: str
) -> None:
    give_sku(plant, "PHL005", user)
    make_batch(plant, user)
    second = make_batch(plant, user)
    seq = Batch.objects.get(pk=second).plant_seq

    assert found(spelling.format(seq)) == (Kind.BATCH, second, None)


def test_ac7_a_short_name_with_a_former_sku_finds_the_batch(
    reclassified: int, user: int
) -> None:
    batch = make_batch(reclassified, user)
    seq = Batch.objects.get(pk=batch).plant_seq

    assert found(f"PHL005 · B{seq}") == (Kind.BATCH, batch, "PHL005")


def test_ac7_a_short_name_on_a_plant_without_an_sku_finds_the_batch(
    plant: int, batch: int
) -> None:
    seq = Batch.objects.get(pk=batch).plant_seq

    assert found(f"PLT-{plant:04d} · B{seq:03d}") == (Kind.BATCH, batch, None)


def test_ac7_a_short_name_with_no_such_batch_finds_nothing(
    plant: int, user: int
) -> None:
    give_sku(plant, "PHL005", user)

    assert look_up("PHL005 · B001") is None


# --------------------------------------------------------------------- S3
def test_s3_a_voided_plant_is_still_found(user: int) -> None:
    voided = make_plant(user, status="voided")

    assert found(f"PLT-{voided}") == (Kind.PLANT, voided, None)


def test_s3_a_voided_batch_is_still_found(plant: int, user: int) -> None:
    voided = make_batch(plant, user, status="voided", voided_at=db_now())

    assert found(f"BAT-{voided}") == (Kind.BATCH, voided, None)


def test_s3_a_voided_event_and_its_void_are_still_found(batch: int, user: int) -> None:
    original = make_event(batch, user, "count", counted_qty=0)
    void = make_event(batch, user, "void", "void", voids_event_id=original)

    assert found(f"EVT-{original}") == (Kind.EVENT, original, None)
    assert found(f"EVT-{void}") == (Kind.EVENT, void, None)
    assert Event.objects.filter(voids_event_id=original).count() == 1


# -------------------------------------------------------------------- AC8
def test_ac8_an_id_nobody_has_finds_nothing() -> None:
    unused = next_id("plants") + AHEAD

    assert look_up(f"PLT-{unused}") is None
    assert look_up(f"BAT-{unused}") is None
    assert look_up(f"EVT-{unused}") is None
    assert look_up("PHL999") is None


@pytest.mark.parametrize("text", ["", "nonsense", "PLT-12A", "PLT-๔๒"])
def test_ac8_text_that_isnt_an_id_finds_nothing_without_asking_the_database(
    text: str, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    with django_assert_num_queries(0):
        assert look_up(text) is None


def test_ac8_the_page_says_no_record_has_that_id() -> None:
    assert message_for("id_not_found") == "No plant, batch or event has that ID."


# --------------------------------------------------------------- queries
def test_a_look_up_by_id_is_one_query(
    plant: int, batch: int, django_assert_max_num_queries: DjangoAssertNumQueries
) -> None:
    for text in (f"PLT-{plant}", f"BAT-{batch}"):
        with django_assert_max_num_queries(1):
            assert look_up(text) is not None


def test_a_look_up_by_sku_is_one_query(
    reclassified: int, django_assert_max_num_queries: DjangoAssertNumQueries
) -> None:
    with django_assert_max_num_queries(1):
        assert look_up("PHL005") is not None


def test_a_look_up_by_short_name_is_two_queries(
    reclassified: int, user: int, django_assert_max_num_queries: DjangoAssertNumQueries
) -> None:
    make_batch(reclassified, user)

    with django_assert_max_num_queries(2):
        assert look_up("HYA004 · B001") is not None
