"""U0.8 AC1–AC4, AC4a: numbers into IDs, and back again (design §2, §12).

Padding is a minimum, never a cut: `PLT-10000`, `BAT-100000`, `PHL1000`,
`B1000`. The round trips feed every number from 1 to 20 000, and a few huge
ones, through a format and `read`, so two numbers can never share an ID.
"""

from collections.abc import Callable

import pytest

from cucumber.core.tests.rows import give_sku, issue_sku, make_plant
from cucumber.ids.formats import (
    SKU_ORDER,
    batch_id,
    batch_short_name,
    event_id,
    plant_id,
    plant_label,
    sku,
    sku_number,
)
from cucumber.ids.reading import BIGGEST_ID, BIGGEST_PLANT_SEQ, Kind, Typed, read
from cucumber.plants.models import Plant, Sku

ROUND_TRIP_UP_TO = 20_000
HUGE = (10**6, 10**9, 10**12, BIGGEST_ID)


# --------------------------------------------------------------- AC1, AC2
@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "PLT-0001"), (42, "PLT-0042"), (9999, "PLT-9999"), (10000, "PLT-10000")],
)
def test_ac1_a_plant_id_is_plt_and_the_number_padded_to_4(
    number: int, expected: str
) -> None:
    assert plant_id(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "BAT-00001"),
        (117, "BAT-00117"),
        (99999, "BAT-99999"),
        (100000, "BAT-100000"),
    ],
)
def test_ac1_a_batch_id_is_bat_and_the_number_padded_to_5(
    number: int, expected: str
) -> None:
    assert batch_id(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "EVT-00001"), (1502, "EVT-01502"), (100000, "EVT-100000")],
)
def test_ac1_an_event_id_is_evt_and_the_number_padded_to_5(
    number: int, expected: str
) -> None:
    assert event_id(number) == expected


def test_ac2_a_huge_number_is_never_cut_short() -> None:
    assert plant_id(BIGGEST_ID) == f"PLT-{BIGGEST_ID}"
    assert batch_id(BIGGEST_ID) == f"BAT-{BIGGEST_ID}"
    assert event_id(BIGGEST_ID) == f"EVT-{BIGGEST_ID}"


def test_ac2_two_different_numbers_never_give_the_same_plant_id() -> None:
    numbers = range(1, ROUND_TRIP_UP_TO + 1)

    made = {plant_id(number) for number in numbers}

    assert len(made) == len(numbers)


# -------------------------------------------------------------------- AC4
@pytest.mark.parametrize(
    ("genus", "number", "expected"),
    [
        ("PHL", 1, "PHL001"),
        ("PHL", 5, "PHL005"),
        ("HYA", 999, "HYA999"),
        ("PHL", 1000, "PHL1000"),
        ("PHL", 12345, "PHL12345"),
    ],
)
def test_ac4_an_sku_is_the_genus_code_and_the_number_padded_to_3(
    genus: str, number: int, expected: str
) -> None:
    assert sku(genus, number) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("PHL001", 1), ("PHL005", 5), ("PHL999", 999), ("PHL1000", 1000)],
)
def test_ac4a_sku_number_is_the_digits_after_the_genus_code(
    text: str, expected: int
) -> None:
    assert sku_number(text) == expected


# -------------------------------------------------------------------- AC3
def test_ac3_a_plant_label_is_its_sku() -> None:
    assert plant_label("PHL001", 42) == "PHL001"


def test_ac3_a_plant_with_no_sku_is_labelled_by_its_plt_id() -> None:
    assert plant_label(None, 42) == "PLT-0042"


@pytest.mark.parametrize(
    ("current_sku", "plant_seq", "expected"),
    [
        ("PHL001", 3, "PHL001 · B003"),
        (None, 3, "PLT-0042 · B003"),
        ("PHL001", 999, "PHL001 · B999"),
        ("PHL001", 1000, "PHL001 · B1000"),
        ("PHL1000", 1, "PHL1000 · B001"),
    ],
)
def test_ac3_a_batch_short_name_is_the_plant_label_then_b_and_3_digits(
    current_sku: str | None, plant_seq: int, expected: str
) -> None:
    assert batch_short_name(current_sku, 42, plant_seq) == expected


# ------------------------------------------------------- 0 is never issued
NOT_ISSUED: dict[str, Callable[[int], str]] = {
    "plant id": plant_id,
    "batch id": batch_id,
    "event id": event_id,
    "sku": lambda number: sku("PHL", number),
    "plant label": lambda number: plant_label(None, number),
    "batch number": lambda number: batch_short_name("PHL001", 42, number),
    "plant of a batch": lambda number: batch_short_name(None, number, 1),
}


@pytest.mark.parametrize("name", sorted(NOT_ISSUED))
@pytest.mark.parametrize("number", [0, -1])
def test_a_number_below_1_is_a_programming_error(name: str, number: int) -> None:
    with pytest.raises(ValueError, match=str(number)):
        NOT_ISSUED[name](number)


# ------------------------------------------------------------ round trips
def mismatches(
    numbers: range | tuple[int, ...],
    made: Callable[[int], str],
    expected: Callable[[int], Typed],
) -> list[tuple[int, str, Typed | None]]:
    """Every number whose ID doesn't read back as `expected(number)`."""
    wrong = []
    for number in numbers:
        text = made(number)
        found = read(text)
        if found != expected(number):
            wrong.append((number, text, found))
    return wrong


EVERY_NUMBER = range(1, ROUND_TRIP_UP_TO + 1)
ID_FORMATS: dict[Kind, Callable[[int], str]] = {
    Kind.PLANT: plant_id,
    Kind.BATCH: batch_id,
    Kind.EVENT: event_id,
}


@pytest.mark.parametrize("kind", sorted(ID_FORMATS))
def test_ac2_every_id_reads_back_as_its_own_number(kind: Kind) -> None:
    numbers = (*EVERY_NUMBER, *HUGE)

    wrong = mismatches(
        numbers, ID_FORMATS[kind], lambda number: Typed(kind, number=number)
    )

    assert wrong == []


def test_ac4_every_sku_reads_back_as_its_own_number() -> None:
    wrong = mismatches(
        EVERY_NUMBER,
        lambda number: sku("PHL", number),
        lambda number: Typed(Kind.SKU, genus_code="PHL", sku_number=number),
    )

    assert wrong == []


def test_ac3_every_short_name_reads_back_as_its_plant_and_batch_number() -> None:
    numbers = (*range(1, 2_001), BIGGEST_PLANT_SEQ)

    wrong = mismatches(
        numbers,
        lambda seq: batch_short_name("PHL001", 42, seq),
        lambda seq: Typed(
            Kind.BATCH_NAME, genus_code="PHL", sku_number=1, plant_seq=seq
        ),
    )

    assert wrong == []


def test_ac3_a_short_name_without_an_sku_reads_back_as_its_plant_id() -> None:
    wrong = mismatches(
        (1, 42, 10_000, BIGGEST_ID),
        lambda number: batch_short_name(None, number, 3),
        lambda number: Typed(Kind.BATCH_NAME, number=number, plant_seq=3),
    )

    assert wrong == []


# ------------------------------------------------------------------- AC4a
SKUS_IN_TEXT_ORDER = ["ALC002", "PHL001", "PHL100", "PHL1000", "PHL999"]
SKUS_BY_NUMBER = ["ALC002", "PHL001", "PHL100", "PHL999", "PHL1000"]


def test_ac4a_sku_number_sorts_a_python_list_by_number() -> None:
    phl = [text for text in SKUS_IN_TEXT_ORDER if text.startswith("PHL")]

    assert sorted(phl, key=sku_number) == ["PHL001", "PHL100", "PHL999", "PHL1000"]


@pytest.mark.django_db
def test_ac4a_the_sku_register_sorts_by_genus_then_number(user: int) -> None:
    plant = make_plant(user)
    for text in SKUS_IN_TEXT_ORDER:
        issue_sku(plant, text, user)

    ordered = Sku.objects.filter(sku__in=SKUS_IN_TEXT_ORDER).order_by(*SKU_ORDER)

    assert list(ordered.values_list("sku", flat=True)) == SKUS_BY_NUMBER


@pytest.mark.django_db
def test_ac4a_plants_sort_by_genus_then_sku_number(user: int) -> None:
    for text in SKUS_IN_TEXT_ORDER:
        plant = make_plant(user, genus_code=text[:3], full_name=f"Plant {text}")
        give_sku(plant, text, user)

    ordered = Plant.objects.filter(sku__in=SKUS_IN_TEXT_ORDER).order_by(*SKU_ORDER)

    assert list(ordered.values_list("sku", flat=True)) == SKUS_BY_NUMBER
