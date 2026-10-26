"""AC4–AC9, AC15, AC16: which change each list allows (design §3.1).

Each allowed change works; each refused one names its rule and saves nothing
(AC21). The permission check comes first, so a Tech meets `role_not_allowed`
before any of these.
"""

import pytest
from django.contrib.auth.models import User

from cucumber.accounts.permissions import NotAllowed
from cucumber.core.refusals import Refused
from cucumber.references.lists import ListName
from cucumber.references.reading import Item, active_items, item
from cucumber.references.services import add_item, edit_label, switch_off, switch_on
from cucumber.references.tests.support import (
    ADDABLE,
    ARCHIVE_REASON,
    FIXED,
    SEEDED,
    SWITCHABLE,
    nothing_written,
    switched_off,
)

pytestmark = pytest.mark.django_db

REFUSED_NAMES = {
    ListName.STAGES: "stages_order_fixed",
    ListName.LOCATIONS: "locations_fixed",
    ListName.ACTIONS: "list_fixed",
    ListName.COUNT_UNITS: "list_fixed",
}


def shown_codes(name: ListName) -> list[str]:
    return [shown.code for shown in active_items(name)]


# ------------------------------------------------------------------------ add


@pytest.mark.parametrize(("name", "code"), ADDABLE.items())
def test_the_admin_adds_an_item_to_a_list_that_takes_new_codes(
    admin: User, name: ListName, code: str
) -> None:
    added = add_item(admin, name, code, "New thing")

    assert added == Item(code, "New thing", True)
    assert item(name, code) == added
    assert code in shown_codes(name)


@pytest.mark.parametrize(
    ("name", "code"),
    [
        (ListName.STAGES, "S9"),
        (ListName.LOCATIONS, "farm"),
        (ListName.ACTIONS, "sale"),
        (ListName.COUNT_UNITS, "kg"),
    ],
)
def test_adding_to_a_list_that_takes_no_new_codes_names_its_rule(
    admin: User, name: ListName, code: str
) -> None:
    with nothing_written(name), pytest.raises(Refused) as refused:
        add_item(admin, name, code, "Nine")

    assert refused.value.rule == REFUSED_NAMES[name]


# ---------------------------------------------------------------------- label


@pytest.mark.parametrize(("name", "code"), SEEDED.items())
def test_the_admin_changes_the_label_of_any_editable_list(
    admin: User, name: ListName, code: str
) -> None:
    changed = edit_label(admin, name, code, "A better word")

    assert changed.label == "A better word"
    assert item(name, code) == changed


def test_a_label_edit_leaves_the_stage_code_order_and_state_alone(
    admin: User,
) -> None:
    before = item(ListName.STAGES, "P1")
    assert before is not None

    edit_label(admin, ListName.STAGES, "P1", "Multiplying")

    assert item(ListName.STAGES, "P1") == Item(
        "P1", "Multiplying", before.active, before.sort_order
    )


def test_a_label_edit_is_seen_in_the_dropdown(admin: User) -> None:
    edit_label(admin, ListName.GENERA, "HYA", "Wax plant")

    shown = {found.code: found.label for found in active_items(ListName.GENERA)}
    assert shown["HYA"] == "Wax plant"


def test_a_genus_label_edit_changes_its_name(admin: User) -> None:
    changed = edit_label(admin, ListName.GENERA, "HYA", "Wax plant")

    assert changed == Item("HYA", "Wax plant", True)


def test_a_switched_off_item_can_still_be_relabelled(admin: User) -> None:
    switched_off(ListName.MEDIA_CODES, "M003")

    changed = edit_label(admin, ListName.MEDIA_CODES, "M003", "Old recipe")

    assert changed == Item("M003", "Old recipe", False)


@pytest.mark.parametrize("name", FIXED)
def test_the_label_of_a_fixed_list_cannot_be_changed(
    admin: User, name: ListName
) -> None:
    with pytest.raises(Refused) as refused:
        edit_label(admin, name, FIXED[name], "Anything")

    assert refused.value.rule == "list_fixed"


# ------------------------------------------------------------ switch off / on


@pytest.mark.parametrize("name", SWITCHABLE)
def test_the_admin_switches_an_item_off_and_it_leaves_the_dropdown(
    admin: User, name: ListName
) -> None:
    code = SEEDED[name]

    off = switch_off(admin, name, code, ARCHIVE_REASON)

    assert off.active is False
    assert item(name, code) == off
    assert code not in shown_codes(name)


@pytest.mark.parametrize("name", SWITCHABLE)
def test_the_admin_switches_an_item_back_on_and_it_returns_to_the_dropdown(
    admin: User, name: ListName
) -> None:
    code = SEEDED[name]
    switched_off(name, code)

    on = switch_on(admin, name, code)

    assert on.active is True
    assert code in shown_codes(name)


def test_a_stage_switched_on_again_returns_to_its_place_in_the_order(
    admin: User,
) -> None:
    switch_off(admin, ListName.STAGES, "P2", ARCHIVE_REASON)
    switch_on(admin, ListName.STAGES, "P2")

    assert shown_codes(ListName.STAGES) == ["S0", "P0", "P1", "P2", "A1", "P4"]


def test_the_locations_cannot_be_switched_off(admin: User) -> None:
    with nothing_written(ListName.LOCATIONS), pytest.raises(Refused) as refused:
        switch_off(admin, ListName.LOCATIONS, "lab", ARCHIVE_REASON)

    assert refused.value.rule == "locations_fixed"


def test_the_locations_cannot_be_switched_on(admin: User) -> None:
    with nothing_written(ListName.LOCATIONS), pytest.raises(Refused) as refused:
        switch_on(admin, ListName.LOCATIONS, "lab")

    assert refused.value.rule == "locations_fixed"


@pytest.mark.parametrize("name", FIXED)
def test_a_fixed_list_cannot_be_switched_off(admin: User, name: ListName) -> None:
    with pytest.raises(Refused) as refused:
        switch_off(admin, name, FIXED[name], ARCHIVE_REASON)

    assert refused.value.rule == "list_fixed"


@pytest.mark.parametrize("name", FIXED)
def test_a_fixed_list_cannot_be_switched_on(admin: User, name: ListName) -> None:
    with pytest.raises(Refused) as refused:
        switch_on(admin, name, FIXED[name])

    assert refused.value.rule == "list_fixed"


def test_a_fixed_list_is_refused_even_with_no_reason_given(admin: User) -> None:
    """The list is checked before the reason (design §3.3, step 2 then 3)."""
    with pytest.raises(Refused) as refused:
        switch_off(admin, ListName.ACTIONS, "intake", None)

    assert refused.value.rule == "list_fixed"


@pytest.mark.parametrize("reserved", ["P3", "T1", "C0"])
def test_a_reserved_stage_cannot_be_switched_on(admin: User, reserved: str) -> None:
    with nothing_written(ListName.STAGES), pytest.raises(Refused) as refused:
        switch_on(admin, ListName.STAGES, reserved)

    assert refused.value.rule == "stages_active_needs_sort_order"


# ------------------------------------------------- the permission check first


@pytest.mark.parametrize("name", FIXED)
def test_a_tech_meets_the_role_before_a_fixed_list(tech: User, name: ListName) -> None:
    with pytest.raises(NotAllowed) as refused:
        add_item(tech, name, "x", "X")

    assert refused.value.rule == "role_not_allowed"


def test_a_tech_meets_the_role_before_the_stage_order_rule(tech: User) -> None:
    with pytest.raises(NotAllowed) as refused:
        add_item(tech, ListName.STAGES, "S9", "Nine")

    assert refused.value.rule == "role_not_allowed"


def test_a_switched_off_account_meets_the_account_before_a_fixed_location(
    deactivated_tech: User,
) -> None:
    with pytest.raises(NotAllowed) as refused:
        edit_label(deactivated_tech, ListName.LOCATIONS, "lab", "Lab")

    assert refused.value.rule == "account_not_active"
