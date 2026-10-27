"""U0.9 G2: reclassifying into a switched-off genus is refused (AC13).

The permission check still comes first (design §3.4): a Tech meets
`role_not_allowed`, not `list_item_inactive`.
"""

import pytest
from django.contrib.auth.models import User

from cucumber.core.tests.rows import give_sku, insert, make_plant
from cucumber.core.tests.stock import not_allowed, refused
from cucumber.core.tests.trail import as_system
from cucumber.plants.models import Plant, PlantStatusChange, Sku
from cucumber.plants.services import reclassify_genus
from cucumber.references.lists import ListName
from cucumber.references.tests.support import switched_off

pytestmark = pytest.mark.django_db


def add_anthurium() -> None:
    with as_system():
        insert(
            "genera",
            {"code": "ANT", "name": "Anthurium", "active": True},
            returning="code",
        )


@pytest.fixture
def off_genus() -> str:
    """Anthurium, added and then switched off."""
    add_anthurium()
    switched_off(ListName.GENERA, "ANT")
    return "ANT"


@pytest.fixture
def phl005(user: int) -> int:
    """A Collection plant holding SKU PHL005."""
    plant = make_plant(user, full_name="Glorious")
    give_sku(plant, "PHL005", user)
    return plant


def test_ac13_reclassifying_into_a_switched_off_genus_is_refused(
    phl005: int, off_genus: str, admin: User
) -> None:
    changes = PlantStatusChange.objects.count()

    with refused("list_item_inactive"):
        reclassify_genus(admin, phl005, off_genus)

    stored = Plant.objects.get(pk=phl005)
    assert (stored.genus_id, stored.sku_id) == ("PHL", "PHL005")
    assert not Sku.objects.filter(genus_id=off_genus).exists()
    assert PlantStatusChange.objects.count() == changes


def test_ac13_a_plant_without_an_sku_is_refused_too(
    plant: int, off_genus: str, admin: User
) -> None:
    with refused("list_item_inactive"):
        reclassify_genus(admin, plant, off_genus)

    assert Plant.objects.get(pk=plant).genus_id == "PHL"


def test_ac13_a_tech_meets_the_role_check_not_the_inactive_check(
    phl005: int, off_genus: str, tech: User
) -> None:
    with not_allowed("role_not_allowed"):
        reclassify_genus(tech, phl005, off_genus)

    assert Plant.objects.get(pk=phl005).genus_id == "PHL"


def test_ac13_the_same_genus_is_fine_while_it_is_switched_on(
    phl005: int, admin: User
) -> None:
    add_anthurium()

    assert reclassify_genus(admin, phl005, "ANT").genus_id == "ANT"
