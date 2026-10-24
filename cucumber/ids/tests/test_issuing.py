"""U0.8 AC10, AC11, Q2: SKUs and batch numbers, issued in `ids.issuing` (design §4).

One at a time here; at the same moment in `test_concurrency.py`. The next
SKU counts on from the highest ever issued for the genus, by number, so
`PHL999` is followed by `PHL1000`.
"""

import pytest
from django.contrib.auth.models import User

from cucumber.core.tests.rows import (
    as_system,
    insert,
    issue_sku,
    make_batch,
    make_plant,
)
from cucumber.core.tests.stock import not_allowed
from cucumber.ids.issuing import issue_next_sku, lock_plants, plant_seqs
from cucumber.plants.models import Sku

pytestmark = pytest.mark.django_db


@pytest.fixture
def ant() -> str:
    """Anthurium, a genus with no SKU issued yet (it isn't seeded)."""
    with as_system():
        return str(
            insert(
                "genera",
                {"code": "ANT", "name": "Anthurium", "active": True},
                returning="code",
            )
        )


# ----------------------------------------------------------- issue_next_sku
def test_ac10_the_first_sku_of_a_genus_is_001(
    plant: int, ant: str, admin: User
) -> None:
    issued = issue_next_sku(plant, ant, admin)

    assert issued == "ANT001"
    row = Sku.objects.get(pk=issued)
    assert (row.plant_id, row.genus_id, row.assigned_by_id) == (plant, ant, admin.pk)


def test_ac10_the_next_sku_counts_on_from_the_highest_ever_issued(
    plant: int, user: int, admin: User
) -> None:
    for text in ("PHL002", "PHL005", "PHL003"):
        issue_sku(make_plant(user, full_name=f"Plant {text}"), text, user)

    assert issue_next_sku(plant, "PHL", admin) == "PHL006"


def test_q2_after_phl999_comes_phl1000(plant: int, user: int, admin: User) -> None:
    issue_sku(make_plant(user, full_name="The 999th"), "PHL999", user)

    assert issue_next_sku(plant, "PHL", admin) == "PHL1000"


def test_q2_the_highest_is_found_by_number_not_by_text(
    plant: int, user: int, admin: User
) -> None:
    """As text, PHL999 sorts after PHL1000."""
    for text in ("PHL999", "PHL1000"):
        issue_sku(make_plant(user, full_name=f"Plant {text}"), text, user)

    assert issue_next_sku(plant, "PHL", admin) == "PHL1001"


def test_ac10_only_a_role_with_plant_lifecycle_may_issue_an_sku(
    plant: int, tech: User
) -> None:
    with not_allowed():
        issue_next_sku(plant, "PHL", tech)

    assert not Sku.objects.filter(plant_id=plant).exists()


# -------------------------------------------------------------- lock_plants
def test_ac11_a_plant_with_no_batches_starts_at_batch_1(plant: int) -> None:
    assert lock_plants({plant}) == {plant: 1}


def test_ac11_the_next_batch_number_is_the_highest_plus_1(
    plant: int, user: int
) -> None:
    other = make_plant(user, full_name="Other")
    for _ in range(3):
        make_batch(plant, user)

    assert lock_plants({plant, other}) == {plant: 4, other: 1}


def test_no_plants_lock_nothing() -> None:
    assert lock_plants(set()) == {}


# --------------------------------------------------------------- plant_seqs
def test_review_m3_new_batches_are_numbered_in_entry_order() -> None:
    next_seq = {7: 3, 9: 1}

    assert plant_seqs(next_seq, [7, 9, 7, 7]) == [3, 1, 4, 5]


def test_review_m3_batch_numbers_grow_past_999() -> None:
    assert plant_seqs({7: 999}, [7, 7]) == [999, 1000]


def test_review_m3_no_new_batches_get_no_numbers() -> None:
    assert plant_seqs({7: 3}, []) == []
