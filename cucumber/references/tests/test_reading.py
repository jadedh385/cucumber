"""AC2, AC13, AC15, AC16: the readers (design §3.2).

Everyone signed in reads, so no reader takes a person. The lists are the
seeded ones; a switched-off item is made in set-up.
"""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cucumber.core.refusals import MESSAGES, Refused
from cucumber.references.fixed import Action, CountUnit
from cucumber.references.lists import ListName
from cucumber.references.reading import (
    Item,
    active_items,
    check_active,
    item,
    stage_at_or_after,
)
from cucumber.references.tests.support import switched_off

pytestmark = pytest.mark.django_db

STAGE_ORDER = ["S0", "P0", "P1", "P2", "A1", "P4"]
MEDIA_ORDER = ["G001", "G002", "M001", "M002", "M003", "M004", "R001"]
CONTAINER_LABEL_ORDER = [
    "flask_250ml",  # 250 ml flask
    "pot_4in",  # 4-inch pot
    "disposable_cup",
    "grow_bag",
    "jar",
    "magenta_box",
    "tray",
]


def codes(name: ListName) -> list[str]:
    return [found.code for found in active_items(name)]


def count_queries(call: Callable[[], object]) -> int:
    with CaptureQueriesContext(connection) as queries:
        call()
    return len(queries)


# ------------------------------------------------------- active_items: order


def test_stages_are_read_in_sort_order_not_code_order() -> None:
    assert codes(ListName.STAGES) == STAGE_ORDER


def test_a1_sits_between_p2_and_p4() -> None:
    stages = codes(ListName.STAGES)
    assert stages.index("P2") < stages.index("A1") < stages.index("P4")


def test_media_codes_are_read_by_code() -> None:
    assert codes(ListName.MEDIA_CODES) == MEDIA_ORDER


def test_genera_are_read_by_code() -> None:
    assert codes(ListName.GENERA) == ["ALC", "HYA", "PHL"]


def test_locations_are_read_by_code() -> None:
    assert codes(ListName.LOCATIONS) == ["lab", "nursery"]


def test_container_types_are_read_by_label_not_code() -> None:
    assert codes(ListName.CONTAINER_TYPES) == CONTAINER_LABEL_ORDER


def test_actions_are_read_as_the_fourteen_in_fixed_order() -> None:
    assert codes(ListName.ACTIONS) == [action.value for action in Action]


def test_count_units_are_read_as_plant_vessel_mg() -> None:
    assert codes(ListName.COUNT_UNITS) == ["plant", "vessel", "mg"]


# ------------------------------------------- active_items: switched-off items


@pytest.mark.parametrize(
    ("name", "code"),
    [
        (ListName.STAGES, "P2"),
        (ListName.MEDIA_CODES, "M003"),
        (ListName.GENERA, "PHL"),
        (ListName.CONTAINER_TYPES, "jar"),
    ],
)
def test_a_switched_off_item_is_left_out_of_a_dropdown(
    name: ListName, code: str
) -> None:
    before = codes(name)
    switched_off(name, code)

    assert codes(name) == [kept for kept in before if kept != code]


def test_stages_keep_their_order_when_one_in_the_middle_is_off() -> None:
    switched_off(ListName.STAGES, "P2")

    assert codes(ListName.STAGES) == ["S0", "P0", "P1", "A1", "P4"]


def test_reserved_stages_are_never_in_a_dropdown() -> None:
    assert {"P3", "T1", "C0"}.isdisjoint(codes(ListName.STAGES))


def test_an_active_items_read_is_one_query() -> None:
    assert count_queries(lambda: active_items(ListName.STAGES)) == 1
    assert count_queries(lambda: active_items(ListName.CONTAINER_TYPES)) == 1


@pytest.mark.parametrize("name", [ListName.ACTIONS, ListName.COUNT_UNITS])
def test_a_fixed_list_is_read_without_a_query(name: ListName) -> None:
    assert count_queries(lambda: active_items(name)) == 0


def test_every_item_read_is_active() -> None:
    for name in (ListName.STAGES, ListName.MEDIA_CODES, ListName.CONTAINER_TYPES):
        assert all(found.active for found in active_items(name))


# ----------------------------------------------------------------------- item


def test_a_stage_is_read_with_its_label_and_place_in_the_order() -> None:
    assert item(ListName.STAGES, "S0") == Item("S0", "Seed", True, 0)


def test_a_media_code_is_read_with_its_own_code_as_label() -> None:
    assert item(ListName.MEDIA_CODES, "M001") == Item("M001", "M001", True)


def test_a_genus_is_read_with_its_name_as_label() -> None:
    assert item(ListName.GENERA, "HYA") == Item("HYA", "Hoya", True)


def test_a_location_is_read_with_its_label() -> None:
    assert item(ListName.LOCATIONS, "nursery") == Item("nursery", "Nursery", True)


def test_a_container_type_is_read_with_its_label() -> None:
    assert item(ListName.CONTAINER_TYPES, "magenta_box") == Item(
        "magenta_box", "Magenta box", True
    )


def test_a_switched_off_item_is_still_found_by_its_code() -> None:
    switched_off(ListName.MEDIA_CODES, "M003")

    assert item(ListName.MEDIA_CODES, "M003") == Item("M003", "M003", False)


def test_a_switched_off_stage_is_still_found_with_its_place_in_the_order() -> None:
    switched_off(ListName.STAGES, "P2")

    found = item(ListName.STAGES, "P2")

    assert found is not None
    assert (found.active, found.sort_order) == (False, 3)


def test_a_reserved_stage_is_found_inactive_with_no_place_in_the_order() -> None:
    found = item(ListName.STAGES, "P3")

    assert found is not None
    assert (found.active, found.sort_order) == (False, None)


@pytest.mark.parametrize("name", list(ListName))
def test_a_code_not_on_the_list_is_none(name: ListName) -> None:
    assert item(name, "nope") is None


def test_a_code_in_another_letter_case_is_not_found() -> None:
    assert item(ListName.MEDIA_CODES, "m001") is None


def test_an_action_is_found_by_its_value_and_a_count_unit_too() -> None:
    assert item(ListName.ACTIONS, "stage_change") == Item(
        "stage_change", Action.STAGE_CHANGE.label, True
    )
    assert item(ListName.COUNT_UNITS, "mg") == Item("mg", "mg", True)


def test_an_item_read_is_one_query_and_a_fixed_one_is_none() -> None:
    assert count_queries(lambda: item(ListName.MEDIA_CODES, "M001")) == 1
    assert count_queries(lambda: item(ListName.ACTIONS, "intake")) == 0


# --------------------------------------------------------------- check_active


def refusal_of(name: ListName, *given: str) -> str:
    with pytest.raises(Refused) as caught:
        check_active(name, *given)
    return caught.value.rule


def test_active_codes_pass() -> None:
    check_active(ListName.MEDIA_CODES, "M001", "G002")
    check_active(ListName.STAGES, "S0")


def test_a_code_not_on_the_list_is_refused_as_unknown() -> None:
    assert refusal_of(ListName.MEDIA_CODES, "M999") == "list_item_unknown"


def test_a_code_in_another_letter_case_is_refused_as_unknown() -> None:
    assert refusal_of(ListName.MEDIA_CODES, "m001") == "list_item_unknown"


def test_a_switched_off_code_is_refused_as_inactive() -> None:
    switched_off(ListName.MEDIA_CODES, "M004")

    assert refusal_of(ListName.MEDIA_CODES, "M004") == "list_item_inactive"


def test_a_reserved_stage_is_refused_as_inactive() -> None:
    assert refusal_of(ListName.STAGES, "P3") == "list_item_inactive"


@pytest.mark.parametrize("order", [("M004", "M999"), ("M999", "M004")])
def test_unknown_is_reported_before_inactive_whatever_the_order_given(
    order: tuple[str, ...],
) -> None:
    switched_off(ListName.MEDIA_CODES, "M004")

    assert refusal_of(ListName.MEDIA_CODES, *order) == "list_item_unknown"


def test_one_bad_code_among_good_ones_refuses_them_all() -> None:
    switched_off(ListName.MEDIA_CODES, "M004")

    assert refusal_of(ListName.MEDIA_CODES, "M001", "M004", "G001") == (
        "list_item_inactive"
    )


def test_the_refusal_carries_its_message() -> None:
    with pytest.raises(Refused) as caught:
        check_active(ListName.MEDIA_CODES, "M999")

    assert caught.value.message == MESSAGES["list_item_unknown"]


def test_many_codes_are_checked_in_one_query() -> None:
    queries = count_queries(
        lambda: check_active(ListName.MEDIA_CODES, "M001", "M002", "M003", "G001")
    )

    assert queries == 1


def test_a_refusal_also_costs_one_query() -> None:
    switched_off(ListName.MEDIA_CODES, "M004")

    def refused() -> None:
        with pytest.raises(Refused):
            check_active(ListName.MEDIA_CODES, "M001", "M004", "M999")

    assert count_queries(refused) == 1


def test_the_same_code_twice_is_not_a_problem() -> None:
    check_active(ListName.GENERA, "HYA", "HYA")


def test_a_fixed_list_check_is_membership_with_no_query() -> None:
    assert count_queries(lambda: check_active(ListName.ACTIONS, "intake", "void")) == 0
    assert refusal_of(ListName.ACTIONS, "sale") == "list_item_unknown"
    assert refusal_of(ListName.COUNT_UNITS, "kg") == "list_item_unknown"
    check_active(ListName.COUNT_UNITS, "plant", "vessel", "mg")


# ------------------------------------------------------------ stage_at_or_after


@pytest.mark.parametrize(
    ("code", "than", "expected"),
    [
        ("P4", "A1", True),
        ("A1", "P4", False),
        ("P4", "P4", True),
        ("A1", "P2", True),
        ("P2", "A1", False),
        ("P0", "S0", True),
        ("S0", "P0", False),
        ("S0", "S0", True),
    ],
)
def test_a_stage_is_compared_by_sort_order_not_by_code(
    code: str, than: str, expected: bool
) -> None:
    assert stage_at_or_after(code, than) is expected


def test_a_switched_off_stage_still_has_its_place_in_the_order() -> None:
    switched_off(ListName.STAGES, "A1")

    assert stage_at_or_after("A1", "P2") is True
    assert stage_at_or_after("P4", "A1") is True


@pytest.mark.parametrize("reserved", ["P3", "T1", "C0"])
def test_a_reserved_stage_is_at_or_after_nothing(reserved: str) -> None:
    assert stage_at_or_after(reserved, "S0") is False
    assert stage_at_or_after(reserved, "P4") is False


# --------------------------------------------------------------- fixed lists


def test_the_event_actions_are_exactly_these_fourteen() -> None:
    assert [action.value for action in Action] == [
        "intake", "subculture", "stage_change", "count", "contamination",
        "split", "quarantine", "release", "transfer", "out", "loss", "close",
        "correction", "void",
    ]  # fmt: skip


def test_the_count_units_are_exactly_plant_vessel_and_mg() -> None:
    assert [unit.value for unit in CountUnit] == ["plant", "vessel", "mg"]
    assert CountUnit.MG.label == "mg"


def test_the_fixed_lists_read_the_same_as_the_code_lists() -> None:
    assert codes(ListName.ACTIONS) == Action.values
    assert codes(ListName.COUNT_UNITS) == CountUnit.values
