"""AC4, AC6, AC7: every rule of design §7 with a bad input.

Each refusal names its rule, carries its message, and saves nothing (AC21).
"""

from collections.abc import Callable

import pytest
from django.contrib.auth.models import User

from cucumber.core.refusals import MESSAGES, Refused
from cucumber.core.tests.rows import fetch_one
from cucumber.references.lists import EDITABLE_TABLES, LABEL_MAX_LENGTH, ListName
from cucumber.references.reading import item
from cucumber.references.services import add_item, edit_label, switch_off, switch_on
from cucumber.references.tests.support import (
    ADDABLE,
    ARCHIVE_REASON,
    LABEL_RULE,
    SEEDED,
    long_text,
    nothing_written,
    switched_off,
)

pytestmark = pytest.mark.django_db

M, G, C = ListName.MEDIA_CODES, ListName.GENERA, ListName.CONTAINER_TYPES
BAD_LABELS = ["", "   ", "\t", long_text(LABEL_MAX_LENGTH + 1)]

BAD_CODES = [
    # media: a capital, then 2 to 9 capitals or digits
    (M, "", "media_codes_code_format"),
    (M, "m001", "media_codes_code_format"),
    (M, "M0", "media_codes_code_format"),  # one too few (M01 fits)
    (M, "M", "media_codes_code_format"),
    (M, "M0123456789", "media_codes_code_format"),
    (M, "1M00", "media_codes_code_format"),
    (M, "M-01", "media_codes_code_format"),
    (M, "M 01", "media_codes_code_format"),
    # genera: three capitals; PLT, BAT, EVT start other IDs (U0.8)
    (G, "", "genera_code_format"),
    (G, "phl", "genera_code_format"),
    (G, "Hya", "genera_code_format"),
    (G, "PH", "genera_code_format"),
    (G, "PHLX", "genera_code_format"),
    (G, "PH1", "genera_code_format"),
    (G, "PLT", "genera_code_not_id_prefix"),
    (G, "BAT", "genera_code_not_id_prefix"),
    (G, "EVT", "genera_code_not_id_prefix"),
    # container types: small letters, digits and _, 2 to 32, starting with a letter
    (C, "", "container_types_code_format"),
    (C, "Magenta_Box", "container_types_code_format"),
    (C, "m", "container_types_code_format"),
    (C, "1box", "container_types_code_format"),
    (C, "_box", "container_types_code_format"),
    (C, "magenta box", "container_types_code_format"),
    (C, "magenta-box", "container_types_code_format"),
    (C, "a" + "b" * 32, "container_types_code_format"),  # 33 characters
]

GOOD_CODES = [
    (M, "ABC"),
    (M, "A" + "9" * 9),
    (G, "ZZZ"),
    (C, "ab"),
    (C, "a" + "b" * 31),  # 32 characters
]


def refusal_of(call: Callable[[], object]) -> Refused:
    with pytest.raises(Refused) as caught:
        call()
    return caught.value


# ---------------------------------------------------------------------- codes


@pytest.mark.parametrize(
    ("name", "code", "rule"),
    BAD_CODES,
    ids=[f"{name.value}-{code!r}" for name, code, _ in BAD_CODES],
)
def test_a_code_that_breaks_its_format_is_refused_by_rule_name(
    admin: User, name: ListName, code: str, rule: str
) -> None:
    with nothing_written(name):
        refused = refusal_of(lambda: add_item(admin, name, code, "A label"))

    assert refused.rule == rule
    assert refused.message == MESSAGES[rule]


@pytest.mark.parametrize(("name", "code"), GOOD_CODES)
def test_a_code_at_the_edge_of_its_format_is_accepted(
    admin: User, name: ListName, code: str
) -> None:
    assert add_item(admin, name, code, "A label").code == code


@pytest.mark.parametrize(
    ("name", "typed", "saved"),
    [
        (M, "M777\n", "M777"),
        (M, "  M777 ", "M777"),
        (G, "XYZ\n", "XYZ"),
        (G, "\tXYZ", "XYZ"),
        (C, "jiffy_pot\n", "jiffy_pot"),
        (C, " jiffy_pot ", "jiffy_pot"),
    ],
    ids=lambda value: repr(value),
)
def test_a_code_is_trimmed_like_a_label_so_a_trailing_newline_is_accepted(
    admin: User, name: ListName, typed: str, saved: str
) -> None:
    """Owner decision (session 2, decision 3): codes are trimmed, then checked
    against the format, so what is saved never carries the whitespace."""
    added = add_item(admin, name, typed, "A label")

    assert added.code == saved
    assert item(name, saved) == added


def test_a_code_that_is_only_whitespace_is_refused_as_blank(admin: User) -> None:
    with nothing_written(M):
        refused = refusal_of(lambda: add_item(admin, M, " \n", "A label"))

    assert refused.rule == "media_codes_code_format"


def test_a_trimmed_code_that_is_already_taken_is_refused_by_the_primary_key(
    admin: User,
) -> None:
    with nothing_written(M):
        refused = refusal_of(lambda: add_item(admin, M, "M001\n", "Again"))

    assert refused.rule == "media_codes_pkey"


@pytest.mark.parametrize(("name", "code"), ADDABLE.items())
def test_a_code_already_on_the_list_is_refused_by_the_primary_key(
    admin: User, name: ListName, code: str
) -> None:
    add_item(admin, name, code, "First")

    with nothing_written(name):
        refused = refusal_of(lambda: add_item(admin, name, code, "Second"))

    assert refused.rule == f"{name.value}_pkey"
    assert refused.message == MESSAGES[f"{name.value}_pkey"]


@pytest.mark.parametrize(
    ("name", "taken"), [(M, "M001"), (G, "HYA"), (C, "magenta_box")]
)
def test_a_seeded_code_is_taken_too(admin: User, name: ListName, taken: str) -> None:
    with nothing_written(name):
        refused = refusal_of(lambda: add_item(admin, name, taken, "Again"))

    assert refused.rule == f"{name.value}_pkey"


def test_a_switched_off_code_is_still_taken(admin: User) -> None:
    switched_off(M, "M004")

    with nothing_written(M):
        refused = refusal_of(lambda: add_item(admin, M, "M004", "Again"))

    assert refused.rule == "media_codes_pkey"


def test_a_code_in_another_letter_case_is_a_format_error_not_a_taken_code(
    admin: User,
) -> None:
    """Two codes differing only by case can't both pass the format, so the
    primary key is enough (design §2.1)."""
    with nothing_written(M):
        refused = refusal_of(lambda: add_item(admin, M, "m001", "Again"))

    assert refused.rule == "media_codes_code_format"


# ---------------------------------------------------------------------- label


@pytest.mark.parametrize("label", BAD_LABELS, ids=repr)
@pytest.mark.parametrize("name", ADDABLE)
def test_a_new_item_with_a_blank_or_too_long_label_is_refused(
    admin: User, name: ListName, label: str
) -> None:
    with nothing_written(name):
        refused = refusal_of(lambda: add_item(admin, name, ADDABLE[name], label))

    assert refused.rule == LABEL_RULE[name]
    assert refused.message == MESSAGES[LABEL_RULE[name]]


@pytest.mark.parametrize("label", BAD_LABELS, ids=repr)
@pytest.mark.parametrize("name", SEEDED)
def test_an_edit_to_a_blank_or_too_long_label_is_refused(
    admin: User, name: ListName, label: str
) -> None:
    with nothing_written(name):
        refused = refusal_of(lambda: edit_label(admin, name, SEEDED[name], label))

    assert refused.rule == LABEL_RULE[name]


@pytest.mark.parametrize("name", SEEDED)
def test_a_label_of_exactly_one_hundred_characters_is_accepted(
    admin: User, name: ListName
) -> None:
    label = long_text(LABEL_MAX_LENGTH)

    assert edit_label(admin, name, SEEDED[name], label).label == label


def test_a_label_is_trimmed_before_it_is_saved(admin: User) -> None:
    changed = edit_label(admin, C, "magenta_box", "  Magenta  box \t")

    assert changed.label == "Magenta  box"
    row = fetch_one("SELECT label FROM container_types WHERE code = 'magenta_box'")
    assert row == ("Magenta  box",)


def test_a_new_label_is_trimmed_before_it_is_saved(admin: User) -> None:
    assert add_item(admin, M, "M777", "  Half MS ").label == "Half MS"


def test_the_length_is_counted_after_trimming(admin: User) -> None:
    padded = f"  {long_text(LABEL_MAX_LENGTH)}  "

    assert len(edit_label(admin, M, "M001", padded).label) == LABEL_MAX_LENGTH


# ----------------------------------------------------------------- genus name


def test_a_new_genus_with_a_name_already_used_is_refused(admin: User) -> None:
    with nothing_written(G):
        refused = refusal_of(lambda: add_item(admin, G, "XYZ", "Hoya"))

    assert refused.rule == "genera_name_unique"
    assert refused.message == MESSAGES["genera_name_unique"]


def test_renaming_a_genus_to_another_genus_name_is_refused(admin: User) -> None:
    with nothing_written(G):
        refused = refusal_of(lambda: edit_label(admin, G, "PHL", "Hoya"))

    assert refused.rule == "genera_name_unique"


def test_a_genus_may_keep_its_own_name(admin: User) -> None:
    assert edit_label(admin, G, "HYA", "Hoya").label == "Hoya"


# -------------------------------------------------------------- unknown codes


@pytest.mark.parametrize(
    ("name", "code"),
    [
        (ListName.STAGES, "S9"),
        (ListName.LOCATIONS, "mars"),
        (M, "M999"),
        (G, "ZZZ"),
        (C, "no_such"),
    ],
)
def test_editing_a_label_of_a_code_not_on_the_list_is_refused(
    admin: User, name: ListName, code: str
) -> None:
    with nothing_written(name):
        refused = refusal_of(lambda: edit_label(admin, name, code, "Anything"))

    assert refused.rule == "list_item_unknown"
    assert refused.message == MESSAGES["list_item_unknown"]


@pytest.mark.parametrize(
    ("name", "code"),
    [(ListName.STAGES, "S9"), (M, "M999"), (G, "ZZZ"), (C, "no_such")],
)
def test_switching_off_or_on_a_code_not_on_the_list_is_refused(
    admin: User, name: ListName, code: str
) -> None:
    with nothing_written(name):
        off = refusal_of(lambda: switch_off(admin, name, code, ARCHIVE_REASON))
        on = refusal_of(lambda: switch_on(admin, name, code))

    assert (off.rule, on.rule) == ("list_item_unknown", "list_item_unknown")


# --------------------------------------------------------------- the messages

NEW_MESSAGES = {
    "list_fixed": (
        "Event actions and count units can't be changed. That needs a release."
    ),
    "stages_order_fixed": (
        "Stages can't be added or moved in the order here. That needs a release."
    ),
    "locations_fixed": "Lab and Nursery are fixed. You can change their labels only.",
    "stages_active_needs_sort_order": (
        "A reserved stage can't be switched on here. That needs a release."
    ),
    "media_codes_code_format": (
        "A media code is a capital letter and 2 to 9 more capitals or digits,"
        " e.g. M001."
    ),
    "genera_code_format": "A genus code is 3 capital letters, e.g. PHL.",
    "container_types_code_format": (
        "A container type code is small letters, digits and _, starting with a"
        " letter, e.g. magenta_box."
    ),
    "media_codes_pkey": "That code is already on the list.",
    "genera_pkey": "That code is already on the list.",
    "container_types_pkey": "That code is already on the list.",
    "stages_label_valid": "Enter a label of up to 100 characters.",
    "media_codes_label_valid": "Enter a label of up to 100 characters.",
    "locations_label_valid": "Enter a label of up to 100 characters.",
    "container_types_label_valid": "Enter a label of up to 100 characters.",
    "genera_name_valid": "Enter a genus name of up to 100 characters.",
    "genera_name_unique": "Another genus already has that name.",
    "list_item_unknown": "That choice isn't on the list. Choose another.",
    "list_item_inactive": "That choice is switched off. Choose another.",
}


@pytest.mark.parametrize(("rule", "message"), NEW_MESSAGES.items())
def test_every_rule_of_the_lists_has_its_message(rule: str, message: str) -> None:
    assert MESSAGES.get(rule) == message


def test_every_editable_list_has_a_label_message() -> None:
    """So a new list can't miss its message (design §7). Built from
    `EDITABLE_TABLES`, not from this file's own table of rules."""
    rules = [
        "genera_name_valid" if table == "genera" else f"{table}_label_valid"
        for table in EDITABLE_TABLES
    ]

    assert [rule for rule in rules if rule not in MESSAGES] == []
