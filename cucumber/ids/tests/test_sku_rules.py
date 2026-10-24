"""U0.8 AC4, AC5a: the database's SKU and genus code rules (design §5.2, §5.4).

Raw SQL, so the database refuses bad data even when Django's checks are
skipped. An SKU is 3 capital letters and 3 or more digits, with no needless
leading zero, on `plants` and now on `skus` too. No genus may be called
PLT, BAT or EVT, so a typed ID never reads as an SKU.

Check constraints run in name order, so `*_sku_format` refuses before
`*_sku_matches_genus` and `skus_prefix_matches_genus` would.
"""

import re

import pytest
from django.contrib.auth.models import User

from cucumber.core.refusals import message_for
from cucumber.core.tests.rows import (
    as_system,
    fetch_one,
    give_sku,
    insert,
    issue_sku,
    make_plant,
    refused_by,
)
from cucumber.ids.formats import SKU_PATTERN
from cucumber.plants.models import Plant
from cucumber.plants.services import reclassify_genus

pytestmark = pytest.mark.django_db

GOOD_SKUS = ["PHL005", "PHL999", "PHL1000", "PHL12345"]
BAD_SKUS = ["PHL0005", "PHL000", "PHL01000", "PHL05", "phl005", "PHL", "PH005"]


# ---------------------------------------------------------- the pattern
@pytest.mark.parametrize("text", GOOD_SKUS)
def test_ac4_the_sku_pattern_accepts_3_or_more_digits(text: str) -> None:
    assert re.match(SKU_PATTERN, text)


@pytest.mark.parametrize("text", BAD_SKUS)
def test_ac4_the_sku_pattern_refuses_a_needless_zero_or_too_few_digits(
    text: str,
) -> None:
    assert not re.match(SKU_PATTERN, text)


def test_ac4_postgresql_reads_the_pattern_the_same_way_as_python() -> None:
    for text in [*GOOD_SKUS, *BAD_SKUS]:
        in_database = fetch_one("SELECT %s ~ %s", [text, SKU_PATTERN])[0]
        assert in_database == bool(re.match(SKU_PATTERN, text)), text


# ----------------------------------------------------------- on plants
@pytest.mark.parametrize("text", GOOD_SKUS)
def test_ac4_a_plant_may_hold_an_sku_of_3_or_more_digits(
    plant: int, user: int, text: str
) -> None:
    give_sku(plant, text, user)

    assert Plant.objects.get(pk=plant).sku_id == text


@pytest.mark.parametrize("text", BAD_SKUS)
def test_ac4_a_badly_formed_plant_sku_is_refused_by_name(user: int, text: str) -> None:
    with refused_by("plant_sku_format"):
        make_plant(user, sku=text)


def test_ac4_the_format_message_says_3_or_more_digits() -> None:
    assert message_for("plant_sku_format") == (
        "An SKU is 3 capital letters and 3 or more digits, e.g. PHL005."
    )


# ------------------------------------------------------------- on skus
@pytest.mark.parametrize("text", GOOD_SKUS)
def test_ac4_the_register_takes_an_sku_of_3_or_more_digits(
    plant: int, user: int, text: str
) -> None:
    issue_sku(plant, text, user)

    assert fetch_one("SELECT plant_id FROM skus WHERE sku = %s", [text]) == (plant,)


@pytest.mark.parametrize("text", [text for text in BAD_SKUS if text[:3] == "PHL"])
def test_ac4_the_register_refuses_a_badly_formed_sku_by_name(
    plant: int, user: int, text: str
) -> None:
    """Before U0.8 only `plants` checked the format (design §5.2).

    `phl005` and `PH005` are left out: `skus_prefix_matches_genus` already
    refuses them, before the format check is reached.
    """
    with refused_by("skus_sku_format"):
        issue_sku(plant, text, user)


# -------------------------------------------------- end to end (AC4, Q2)
def test_q2_a_plant_reclassified_into_a_full_genus_gets_phl1000(
    user: int, admin: User
) -> None:
    issue_sku(make_plant(user, full_name="The 999th"), "PHL999", user)
    plant = make_plant(user, genus_code="HYA", full_name="Moving")
    give_sku(plant, "HYA001", user)

    moved = reclassify_genus(admin, plant, "PHL")

    assert moved.sku_id == "PHL1000"


# ---------------------------------------------------------------- AC5a
@pytest.mark.parametrize("code", ["PLT", "BAT", "EVT"])
def test_ac5a_a_genus_named_like_an_id_prefix_is_refused_by_name(code: str) -> None:
    with refused_by("genera_code_not_id_prefix"), as_system():
        insert("genera", {"code": code, "name": f"Not {code}"}, returning="code")


def test_ac5a_other_genus_codes_are_still_allowed() -> None:
    with as_system():
        insert("genera", {"code": "PLA", "name": "Platycerium"}, returning="code")

    assert fetch_one("SELECT count(*) FROM genera WHERE code = 'PLA'") == (1,)


def test_ac5a_the_message_asks_for_another_genus_code() -> None:
    assert message_for("genera_code_not_id_prefix") == (
        "PLT, BAT and EVT start other IDs. Choose another genus code."
    )
