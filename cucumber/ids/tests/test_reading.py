"""U0.8 AC5–AC8: typed text read back, without the database (design §3.1).

One test per row of the §3.1 tables, then the text that must read as
nothing. `read` never raises: one test feeds it a few thousand random
strings.
"""

import random

import pytest

from cucumber.ids.reading import (
    BIGGEST_ID,
    BIGGEST_PLANT_SEQ,
    LONGEST_TEXT,
    Kind,
    Typed,
    read,
)

PLANT_42 = Typed(Kind.PLANT, number=42)
PHL005 = Typed(Kind.SKU, genus_code="PHL", sku_number=5)
PHL001_B3 = Typed(Kind.BATCH_NAME, genus_code="PHL", sku_number=1, plant_seq=3)
PLANT_42_B3 = Typed(Kind.BATCH_NAME, number=42, plant_seq=3)


# -------------------------------------------------------------------- AC5
@pytest.mark.parametrize(
    "text", ["PLT-0042", "plt-42", "PLT0042", "PLT 42", "Plt-00042", "  PLT-42  "]
)
def test_ac5_a_plant_id_reads_whatever_the_case_dash_or_zeros(text: str) -> None:
    assert read(text) == PLANT_42


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BAT-00117", Typed(Kind.BATCH, number=117)),
        ("bat117", Typed(Kind.BATCH, number=117)),
        ("EVT-01502", Typed(Kind.EVENT, number=1502)),
        ("evt 1502", Typed(Kind.EVENT, number=1502)),
        ("PLT-10000", Typed(Kind.PLANT, number=10000)),
        (f"BAT-{BIGGEST_ID}", Typed(Kind.BATCH, number=BIGGEST_ID)),
    ],
)
def test_ac5_batch_and_event_ids_read_the_same_way(text: str, expected: Typed) -> None:
    assert read(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "PLT‐42",  # hyphen
        "PLT‑42",  # non-breaking hyphen
        "PLT–42",  # en dash
        "PLT—42",  # em dash
        "PLT−42",  # minus sign
    ],
)
def test_ac5_a_dash_typed_another_way_is_a_dash(text: str) -> None:
    assert read(text) == PLANT_42


def test_ac5_full_width_text_from_a_phone_keyboard_reads() -> None:
    assert read("ＰＬＴ－００４２") == PLANT_42


# -------------------------------------------------------------------- AC6
@pytest.mark.parametrize("text", ["PHL005", "phl005", "PHL5", "PHL05", " Phl005 "])
def test_ac6_an_sku_reads_whatever_the_case_or_zeros(text: str) -> None:
    assert read(text) == PHL005


def test_ac6_a_grown_sku_reads() -> None:
    assert read("PHL1000") == Typed(Kind.SKU, genus_code="PHL", sku_number=1000)


# -------------------------------------------------------------------- AC7
@pytest.mark.parametrize(
    "text",
    [
        "PHL001 · B003",
        "PHL001 B3",
        "PHL001-B003",
        "PHL001B3",
        "phl001 · b003",
        "PHL1 · B3",
        "PHL001·B003",
    ],
)
def test_ac7_a_batch_short_name_reads_whatever_the_separator(text: str) -> None:
    assert read(text) == PHL001_B3


@pytest.mark.parametrize(
    "dot", ["•", "∙", "⋅", "・"]
)  # bullet, bullet operator, dot operator, katakana middle dot
def test_ac7_a_middle_dot_typed_another_way_is_a_middle_dot(dot: str) -> None:
    assert read(f"PHL001 {dot} B003") == PHL001_B3


@pytest.mark.parametrize("text", ["PLT-0042 · B3", "plt42 b3", "PLT-42-B003"])
def test_ac7_a_short_name_on_a_plant_without_an_sku_reads(text: str) -> None:
    assert read(text) == PLANT_42_B3


def test_ac7_a_grown_short_name_reads() -> None:
    assert read("PHL1000 · B1000") == Typed(
        Kind.BATCH_NAME, genus_code="PHL", sku_number=1000, plant_seq=1000
    )


# -------------------------------------------------------------------- AC8
NOT_AN_ID = {
    "empty": "",
    "blank": "   ",
    "prefix only": "PLT-",
    "number 0": "PLT-0",
    "zeros only": "BAT-00000",
    "unknown prefix": "XYZ-12",
    "letters in the number": "PLT-12A",
    "two numbers": "PLT-4 2",
    "25 digits": "PLT-" + "1" * 25,
    "past bigint": f"PLT-{BIGGEST_ID + 1}",
    "Thai digits": "PLT-๔๒",
    # Python's upper() makes these HIA005 and ALS005 (review L1).
    "dotless i": "hıa005",
    "long s": "alſ005",
    "2-letter genus": "PH005",
    "4-letter genus": "PHLL005",
    "sku number 0": "PHL000",
    "batch number 0": "PHL001 · B0",
    "batch number past integer": f"PHL001 · B{BIGGEST_PLANT_SEQ + 1}",
    "two batch numbers": "PHL001 · B003 · B004",
    "batch name without B": "PHL001 · 003",
    "words after an id": "PLT-42 please",
    "too long": "PLT-" + "0" * (LONGEST_TEXT - 5) + "42",
}


@pytest.mark.parametrize("name", sorted(NOT_AN_ID))
def test_ac8_text_that_isnt_an_id_reads_as_nothing(name: str) -> None:
    assert read(NOT_AN_ID[name]) is None


def test_ac8_a_number_just_inside_its_column_still_reads() -> None:
    """The edge of AC8's "too big": the biggest number the column holds."""
    assert read(f"PLT-{BIGGEST_ID}") == Typed(Kind.PLANT, number=BIGGEST_ID)
    assert read(f"PHL001 · B{BIGGEST_PLANT_SEQ}") == Typed(
        Kind.BATCH_NAME, genus_code="PHL", sku_number=1, plant_seq=BIGGEST_PLANT_SEQ
    )


def test_ac8_text_at_the_length_limit_still_reads() -> None:
    text = "PLT-" + "0" * (LONGEST_TEXT - 6) + "42"
    assert len(text) == LONGEST_TEXT

    assert read(text) == PLANT_42


# ------------------------------------------------------------ never raises
FUZZ_SEED = 8  # fixed, so a failure can be run again
FUZZ_COUNT = 5_000
FUZZ_LONGEST = 80
FUZZ_ALPHABET = "PLTBAEVHYAC plt-·•‐–—−_0123456789๔๒ＰＬＴ０４ıſ́\x00\n\t#%'\"\\/"


def test_ac8_read_never_raises_on_random_text() -> None:
    chance = random.Random(FUZZ_SEED)  # noqa: S311 (test data, not security)
    texts = [
        "".join(chance.choices(FUZZ_ALPHABET, k=chance.randint(0, FUZZ_LONGEST)))
        for _ in range(FUZZ_COUNT)
    ]

    results = [read(text) for text in texts]

    assert all(result is None or isinstance(result, Typed) for result in results)
