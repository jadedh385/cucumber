"""U0.2b: genus reclassification (Q1, AC4b, design §2.2).

The one time a plant's SKU changes: the Admin moves it to another genus,
it gets the next SKU for that genus, and its old SKU stays in the register
as a former SKU, found by search and never issued again.
"""

import pytest
from django.contrib.auth.models import User

from cucumber.core.tests.rows import give_sku, insert, issue_sku, make_plant, refused_by
from cucumber.core.tests.stock import refused
from cucumber.plants.models import Plant, PlantStatusChange, Sku
from cucumber.plants.services import find_by_sku, former_skus, reclassify_genus

pytestmark = pytest.mark.django_db


@pytest.fixture
def ant() -> str:
    """Anthurium, a genus the Admin adds (it isn't seeded)."""
    return str(
        insert(
            "genera",
            {"code": "ANT", "name": "Anthurium", "active": True},
            returning="code",
        )
    )


@pytest.fixture
def phl005(user: int) -> int:
    """A Collection plant holding SKU PHL005."""
    plant = make_plant(user, full_name="Glorious")
    give_sku(plant, "PHL005", user)
    return plant


def test_ac4b_a_reclassified_plant_gets_an_sku_of_its_new_genus(
    phl005: int, ant: str, admin: User
) -> None:
    returned = reclassify_genus(admin, phl005, ant)
    stored = Plant.objects.get(pk=phl005)
    assert (returned.genus_id, returned.sku_id) == ("ANT", "ANT001")
    assert (stored.genus_id, stored.sku_id) == ("ANT", "ANT001")
    issued = Sku.objects.get(pk="ANT001")
    assert (issued.plant_id, issued.genus_id, issued.assigned_by_id) == (
        phl005,
        "ANT",
        admin.pk,
    )


def test_ac4b_the_old_sku_is_listed_as_a_former_sku(
    phl005: int, ant: str, admin: User
) -> None:
    reclassify_genus(admin, phl005, ant)
    assert former_skus(phl005) == ["PHL005"]


def test_ac4b_a_search_for_the_old_sku_finds_the_plant(
    phl005: int, ant: str, admin: User
) -> None:
    reclassify_genus(admin, phl005, ant)
    for sku in ("PHL005", "ANT001"):
        found = find_by_sku(sku)
        assert found is not None and found.pk == phl005
    assert find_by_sku("PHL999") is None


def test_ac4b_no_other_plant_can_ever_get_the_old_sku(
    phl005: int, ant: str, admin: User, user: int
) -> None:
    reclassify_genus(admin, phl005, ant)
    other = make_plant(user, full_name="Other")
    with refused_by("skus_pkey"):
        issue_sku(other, "PHL005", user)
    former = Sku.objects.get(pk="PHL005")
    assert (former.plant_id, former.genus_id) == (phl005, "PHL")


def test_the_new_sku_is_the_next_one_issued_for_the_genus(
    phl005: int, ant: str, admin: User, user: int
) -> None:
    for number, name in ((1, "Clarinervium"), (2, "Warocqueanum")):
        earlier = make_plant(user, genus_code="ANT", full_name=name)
        give_sku(earlier, f"ANT00{number}", user)
    assert reclassify_genus(admin, phl005, ant).sku_id == "ANT003"


def test_reclassification_is_logged_in_the_status_history(
    phl005: int, ant: str, admin: User
) -> None:
    reclassify_genus(admin, phl005, ant)
    change = PlantStatusChange.objects.get(plant_id=phl005)
    assert (change.from_status, change.to_status) == ("collection", "collection")
    assert (change.sku_assigned, change.changed_by_id, change.reason) == (
        "ANT001",
        admin.pk,
        "genus reclassified",
    )


def test_a_plant_without_an_sku_changes_genus_without_one(
    plant: int, ant: str, admin: User
) -> None:
    reclassify_genus(admin, plant, ant)
    stored = Plant.objects.get(pk=plant)
    assert (stored.genus_id, stored.sku_id) == ("ANT", None)
    assert not Sku.objects.filter(plant_id=plant).exists()


def test_only_the_admin_can_reclassify(phl005: int, ant: str, supervisor: User) -> None:
    with refused("admin_only"):
        reclassify_genus(supervisor, phl005, ant)
    stored = Plant.objects.get(pk=phl005)
    assert (stored.genus_id, stored.sku_id) == ("PHL", "PHL005")


def test_a_plant_cannot_move_into_a_genus_that_has_its_name(
    phl005: int, ant: str, admin: User, user: int
) -> None:
    make_plant(user, genus_code="ANT", full_name="glorious")
    with refused("plant_name_unique_in_genus"):
        reclassify_genus(admin, phl005, ant)
    assert Plant.objects.get(pk=phl005).sku_id == "PHL005"
    assert not Sku.objects.filter(genus_id="ANT", plant_id=phl005).exists()


def test_reclassifying_into_the_same_genus_is_refused(phl005: int, admin: User) -> None:
    """No new SKU and no log line for a change that changes nothing (G4)."""
    with refused("plant_same_genus"):
        reclassify_genus(admin, phl005, "PHL")
    assert Plant.objects.get(pk=phl005).sku_id == "PHL005"


def test_reclassifying_a_plant_that_does_not_exist_is_refused(
    ant: str, admin: User
) -> None:
    with refused("plant_not_found"):
        reclassify_genus(admin, 999_999, ant)
