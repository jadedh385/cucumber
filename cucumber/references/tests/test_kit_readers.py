"""U0.10a AC8, AC9: the two readers the kit adds (design §7.3, §7.4).

`all_items` shows records that may hold switched-off items, so it reads
every item, in the list's order. `active_reasons` feeds a reason dropdown,
by label with "Other" last, the rule `deactivate_reasons` had.
"""

from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cucumber.accounts.services import deactivate_reasons
from cucumber.core.tests.rows import as_system, update
from cucumber.core.tests.trail import LEFT_COMPANY, PDPA_CODE
from cucumber.references.fixed import Action, CountUnit
from cucumber.references.lists import ListName
from cucumber.references.models import ReasonList
from cucumber.references.reading import Item, active_reasons, all_items
from cucumber.references.tests.support import ARCHIVE_REASON, switched_off

pytestmark = pytest.mark.django_db

# Sort order, then the reserved stages (no place in the order) by code.
STAGE_ORDER = ["S0", "P0", "P1", "P2", "A1", "P4", "C0", "P3", "T1"]
MEDIA_ORDER = ["G001", "G002", "M001", "M002", "M003", "M004", "R001"]
CONTAINER_LABEL_ORDER = [
    "flask_250ml",
    "pot_4in",
    "disposable_cup",
    "grow_bag",
    "jar",
    "magenta_box",
    "tray",
]
REASON_LABELS = {
    ReasonList.DEACTIVATE: ["Left the company", "On leave", "Security", "Other"],
    ReasonList.RETIRE: ["Mother plant lost", "No longer grown", "Other"],
    ReasonList.ARCHIVE: ["Duplicate", "Entered by mistake", "No longer used", "Other"],
    ReasonList.VOID: [
        "Duplicate entry", "Test entry", "Wrong batch", "Wrong plant", "Other",
    ],
    ReasonList.LOSS: [
        "Damage", "Failed acclimatization", "Pest", "Rot", "Unknown", "Other",
    ],
}  # fmt: skip


def count_queries(call: Callable[[], object]) -> int:
    with CaptureQueriesContext(connection) as queries:
        call()
    return len(queries)


def labels(applies_to: ReasonList) -> list[str]:
    return [reason.label for reason in active_reasons(applies_to)]


def reason_switched_off(code: str) -> None:
    with as_system(ARCHIVE_REASON):
        update("reasons", code, {"active": False}, "code")


# ------------------------------------------------------------------ all_items
@pytest.mark.parametrize(
    ("name", "order"),
    [
        (ListName.STAGES, STAGE_ORDER),
        (ListName.MEDIA_CODES, MEDIA_ORDER),
        (ListName.LOCATIONS, ["lab", "nursery"]),
        (ListName.GENERA, ["ALC", "HYA", "PHL"]),
        (ListName.CONTAINER_TYPES, CONTAINER_LABEL_ORDER),
        (ListName.ACTIONS, Action.values),
        (ListName.COUNT_UNITS, CountUnit.values),
    ],
)
def test_every_item_is_read_in_the_lists_order(
    name: ListName, order: list[str]
) -> None:
    assert list(all_items(name)) == order


def test_a_switched_off_item_is_kept_in_its_place() -> None:
    switched_off(ListName.MEDIA_CODES, "M003")

    found = all_items(ListName.MEDIA_CODES)

    assert list(found) == MEDIA_ORDER
    assert found["M003"] == Item("M003", "M003", False)


def test_each_item_is_keyed_by_its_code_and_read_whole() -> None:
    stages = all_items(ListName.STAGES)

    assert stages["P1"] == Item("P1", "Multiplication", True, 2)
    assert stages["P3"] == Item("P3", "Transport", False, None)
    assert all_items(ListName.GENERA)["PHL"] == Item("PHL", "Philodendron", True)


def test_the_fixed_lists_read_with_their_labels_all_active() -> None:
    actions = all_items(ListName.ACTIONS)

    assert actions["stage_change"] == Item("stage_change", "Stage Change", True)
    assert all(found.active for found in actions.values())


@pytest.mark.parametrize(
    "name", [ListName.STAGES, ListName.MEDIA_CODES, ListName.CONTAINER_TYPES]
)
def test_reading_every_item_is_one_query(name: ListName) -> None:
    assert count_queries(lambda: all_items(name)) == 1


@pytest.mark.parametrize("name", [ListName.ACTIONS, ListName.COUNT_UNITS])
def test_a_fixed_list_is_read_without_a_query(name: ListName) -> None:
    assert count_queries(lambda: all_items(name)) == 0


# ------------------------------------------------------------- active_reasons
@pytest.mark.parametrize("applies_to", list(REASON_LABELS), ids=str)
def test_reasons_are_read_by_label_with_other_last(applies_to: ReasonList) -> None:
    assert labels(applies_to) == REASON_LABELS[applies_to]


def test_a_switched_off_reason_is_left_out() -> None:
    reason_switched_off(LEFT_COMPANY)

    assert labels(ReasonList.DEACTIVATE) == ["On leave", "Security", "Other"]


def test_the_pdpa_reason_is_never_offered() -> None:
    """It is inactive on the deactivate list: for `anonymise` only (U0.7 §5.1)."""
    codes = [reason.code for reason in active_reasons(ReasonList.DEACTIVATE)]

    assert PDPA_CODE not in codes


def test_a_reason_is_read_as_an_active_item() -> None:
    first = active_reasons(ReasonList.DEACTIVATE)[0]

    assert first == Item(LEFT_COMPANY, "Left the company", True)


def test_reading_the_reasons_is_one_query() -> None:
    assert count_queries(lambda: active_reasons(ReasonList.VOID)) == 1


def test_the_deactivate_reasons_are_the_readers() -> None:
    """`deactivate_reasons` now asks `active_reasons` (§7.3)."""
    assert deactivate_reasons() == [
        (reason.code, reason.label) for reason in active_reasons(ReasonList.DEACTIVATE)
    ]
