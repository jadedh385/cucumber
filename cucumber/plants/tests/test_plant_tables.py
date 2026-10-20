"""U0.2a: plants, the SKU register and status history (design §2.2).

AC2–AC4a, AC4c–AC4e, AC5–AC5b; AC6 (no delete) is in core/tests/test_protection.py.
"""

import pytest

from cucumber.core.audit import Reason
from cucumber.core.tests.rows import (
    as_int,
    fetch_one,
    give_sku,
    insert,
    issue_sku,
    make_plant,
    make_vendor,
    plant_values,
    refused_by,
    run,
    update,
)
from cucumber.core.tests.trail import as_system
from cucumber.plants.services import zoho_link_missing

pytestmark = pytest.mark.django_db


def plant_row(plant: int, columns: str) -> tuple[object, ...]:
    return fetch_one(f"SELECT {columns} FROM plants WHERE id = %s", [plant])  # noqa: S608


# -------------------------------------------------------------- SKU (rule 1)


def test_ac2_portfolio_plant_needs_an_sku(plant: int) -> None:
    with refused_by("plant_portfolio_needs_sku"):
        update("plants", plant, {"status": "portfolio"})


def test_portfolio_plant_with_its_sku_is_accepted(plant: int, user: int) -> None:
    give_sku(plant, "PHL001", user)
    with as_system():
        update("plants", plant, {"status": "portfolio"})
    assert plant_row(plant, "status, sku") == ("portfolio", "PHL001")


def test_ac3_an_sku_is_issued_only_once(plant: int, user: int) -> None:
    """AC3: the register is keyed on the SKU, so PHL001 can't be issued twice."""
    other = make_plant(user, full_name="Birkin")
    issue_sku(plant, "PHL001", user)
    with refused_by("skus_pkey"):
        issue_sku(other, "PHL001", user)


def test_ac3_two_plants_cannot_share_an_sku(plant: int, user: int) -> None:
    other = make_plant(user, full_name="Birkin")
    give_sku(plant, "PHL001", user)
    with refused_by("plant_sku_unique"):
        update("plants", other, {"sku": "PHL001"})


def test_a_plant_cannot_take_an_sku_issued_to_another(plant: int, user: int) -> None:
    """Design §2.2: a former SKU can never be handed to another plant."""
    other = make_plant(user, full_name="Birkin")
    issue_sku(plant, "PHL002", user)  # issued, but the plant isn't pointed at it
    with refused_by("plant_sku_belongs_to_plant"):
        update("plants", other, {"sku": "PHL002"})


def test_ac4_sku_prefix_must_match_the_genus(plant: int, user: int) -> None:
    issue_sku(plant, "HYA001", user)
    with refused_by("plant_sku_matches_genus"):
        update("plants", plant, {"sku": "HYA001"})


def test_ac4_register_prefix_must_match_the_genus(plant: int, user: int) -> None:
    with refused_by("skus_prefix_matches_genus"):
        issue_sku(plant, "HYA001", user, genus_code="PHL")


@pytest.mark.parametrize("sku", ["PHL01", "PHL0001", "PHLA01"])
def test_sku_is_three_capitals_and_three_digits(
    plant: int, user: int, sku: str
) -> None:
    """Checked on the plant row; the link to `skus` is only checked at the end
    of the statement, so no register row is needed (and none is written)."""
    with refused_by("plant_sku_format"):
        update("plants", plant, {"sku": sku})


def test_ac4a_sku_cannot_be_cleared(plant: int, user: int) -> None:
    give_sku(plant, "PHL003", user)
    with refused_by("plant_sku_static"):
        update("plants", plant, {"sku": None})


def test_ac4a_sku_cannot_change_without_a_genus_change(plant: int, user: int) -> None:
    give_sku(plant, "PHL003", user)
    issue_sku(plant, "PHL004", user)
    with refused_by("plant_sku_static"):
        update("plants", plant, {"sku": "PHL004"})


def test_ac4a_sku_changes_together_with_the_genus(plant: int, user: int) -> None:
    """Q1 reclassification: the database allows it; the service is U0.2b."""
    with as_system():
        run("INSERT INTO genera (code, name, active) VALUES ('ANT', 'Anthurium', true)")
    give_sku(plant, "PHL005", user)
    issue_sku(plant, "ANT001", user)
    with as_system():
        update("plants", plant, {"genus_code": "ANT", "sku": "ANT001"})
    assert plant_row(plant, "genus_code, sku") == ("ANT", "ANT001")


def test_a_genus_change_must_bring_a_new_sku(plant: int, user: int) -> None:
    """Q1: changing the genus but keeping the old SKU breaks the prefix rule."""
    give_sku(plant, "PHL005", user)
    with refused_by("plant_sku_matches_genus"):
        update("plants", plant, {"genus_code": "HYA"})


def test_a_plant_with_no_sku_can_change_genus(plant: int) -> None:
    """Design §2.2: no SKU, so nothing else has to change."""
    with as_system():
        update("plants", plant, {"genus_code": "HYA"})
    assert plant_row(plant, "genus_code, sku") == ("HYA", None)


def test_notes_default_to_empty(user: int) -> None:
    """Design §2.2: `notes` has a database default of ''."""
    values = plant_values(user)
    del values["notes"]
    with as_system():
        plant = as_int(insert("plants", values))
    assert plant_row(plant, "notes") == ("",)


def test_ac4a_a_retired_plant_keeps_its_sku(plant: int, user: int) -> None:
    """Q1: other statuses keep their SKU; re-promotion reuses it."""
    give_sku(plant, "PHL003", user)
    with as_system(Reason("retire_no_longer_grown")):
        update("plants", plant, {"status": "retired"})
    assert plant_row(plant, "sku") == ("PHL003",)


# -------------------------------------------------- names (rules 12, 13; Q6)


@pytest.mark.parametrize(
    "typed",
    ["pink princess", "'Pink  Princess'", "“Pink Princess”", "  PINK PRINCESS "],
)
def test_ac4c_same_name_in_genus_is_refused_retired_included(
    user: int, typed: str
) -> None:
    make_plant(user, full_name="Pink Princess", status="retired")
    with refused_by("plant_name_unique_in_genus"):
        make_plant(user, full_name=typed)


def test_ac4c_name_is_stored_as_typed_and_matched_by_key(user: int) -> None:
    plant = make_plant(user, full_name="'Pink  Princess'")
    assert plant_row(plant, "full_name, name_key") == (
        "'Pink  Princess'",
        "pink princess",
    )


def test_same_name_in_another_genus_is_accepted(user: int) -> None:
    make_plant(user, full_name="Pink Princess")
    make_plant(user, genus_code="HYA", full_name="Pink Princess")


def test_ac4d_a_voided_plant_frees_its_name(user: int) -> None:
    make_plant(user, full_name="Pink Princess", status="voided")
    make_plant(user, full_name="Pink Princess")


@pytest.mark.parametrize("name", ["Philodendron ???", "", "   "])
def test_ac4e_blank_or_question_mark_names_are_refused(user: int, name: str) -> None:
    with refused_by("plant_name_valid"):
        make_plant(user, full_name=name)


# ---------------------------------------------------- source and Zoho (rule 4)


def test_ac5_purchase_without_zoho_link_is_accepted_and_listed(user: int) -> None:
    vendor = make_vendor()
    missing_both = make_plant(user, full_name="Birkin", source="purchase")
    missing_ref = make_plant(
        user, full_name="Micans", source="purchase", vendor_id=vendor
    )
    missing_vendor = make_plant(
        user, full_name="Mamei", source="purchase", zoho_ref="EXP-0002"
    )
    complete = make_plant(
        user, full_name="Gloriosum", source="purchase", vendor_id=vendor,
        zoho_ref="EXP-0001",
    )  # fmt: skip
    voided = make_plant(
        user, full_name="Verrucosum", source="purchase", status="voided"
    )
    gift = make_plant(user, full_name="Melanochrysum")

    listed = {plant.pk for plant in zoho_link_missing()}

    assert listed == {missing_both, missing_ref, missing_vendor}
    assert not listed & {complete, voided, gift}


def test_ac5a_purchase_cannot_join_portfolio_without_zoho_link(user: int) -> None:
    plant = make_plant(user, source="purchase", vendor_id=make_vendor())
    give_sku(plant, "PHL001", user)
    with refused_by("plant_portfolio_needs_zoho_link"):
        update("plants", plant, {"status": "portfolio"})


def test_ac5a_purchase_with_zoho_link_can_join_portfolio(user: int) -> None:
    plant = make_plant(
        user, source="purchase", vendor_id=make_vendor(), zoho_ref="EXP-0001"
    )
    give_sku(plant, "PHL001", user)
    with as_system():
        update("plants", plant, {"status": "portfolio"})
    assert plant_row(plant, "status") == ("portfolio",)


@pytest.mark.parametrize("source", ["gift", "propagated", "unknown", None])
@pytest.mark.parametrize("link", ["vendor_id", "zoho_ref"])
def test_ac5b_only_purchases_have_a_vendor_or_zoho_ref(
    user: int, source: str | None, link: str
) -> None:
    """AC5b; `None` is the M4 case: a missing source must not slip past the check."""
    value = make_vendor() if link == "vendor_id" else "EXP-0001"
    status = "candidate" if source is None else "collection"
    with refused_by("plant_vendor_only_if_purchased"):
        make_plant(user, source=source, status=status, **{link: value})


def test_only_a_candidate_may_have_no_source(user: int) -> None:
    make_plant(user, full_name="Birkin", status="candidate", source=None)
    with refused_by("plant_source_required"):
        make_plant(user, source=None)


@pytest.mark.parametrize(
    ("column", "value", "rule"),
    [
        ("status", "sold", "plant_status_valid"),
        ("source", "swap", "plant_source_valid"),
        ("min_saleable_qty", 0, "plant_min_saleable_positive"),
    ],
)
def test_plant_values_come_from_their_lists(
    user: int, column: str, value: object, rule: str
) -> None:
    with refused_by(rule):
        make_plant(user, **{column: value})
