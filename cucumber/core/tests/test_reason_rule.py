"""AC11: switching something off needs a reason, in the database too (design §4.2).

Archive (reference lists and vendors), Deactivate (accounts), Retire and
Void (plants). Plain SQL, so a later screen or a script can't skip the rule.
The service side, with its messages, is in accounts' test_deactivate_reason.py.
"""

from dataclasses import dataclass

import pytest

from cucumber.core.tests.rows import (
    db_now,
    fetch_all,
    fetch_one,
    insert,
    make_plant,
    make_user,
    quote,
    refused_by,
    run,
)
from cucumber.core.tests.trail import (
    DUPLICATE_ENTRY,
    LEFT_COMPANY,
    NEW_REASONS,
    NO_LONGER_GROWN,
    NO_LONGER_USED,
    PDPA_CODE,
    as_system,
    audit_mark,
    named_in_sql,
    only_row,
)

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Switch:
    """Switching one row off: the table, its key, the column and off value."""

    table: str
    key_column: str
    column: str
    off: object
    right: str  # a reason from the matching list
    wrong: str  # a reason from another list


def archive(table: str, key_column: str = "code") -> Switch:
    return Switch(table, key_column, "active", False, NO_LONGER_USED, LEFT_COMPANY)


SWITCHES = {
    "genus": archive("genera"),
    "stage": archive("stages"),
    "media": archive("media_codes"),
    "location": archive("locations"),
    "reason": archive("reasons"),
    "vendor": archive("vendors", "zoho_contact_id"),
    "account": Switch(
        "auth_user", "id", "is_active", False, LEFT_COMPANY, NO_LONGER_USED
    ),
    "retire plant": Switch(
        "plants", "id", "status", "retired", NO_LONGER_GROWN, DUPLICATE_ENTRY
    ),
    "void plant": Switch(
        "plants", "id", "status", "voided", DUPLICATE_ENTRY, NO_LONGER_GROWN
    ),
}
SEEDED_KEYS = {
    "genera": "HYA",
    "stages": "P4",
    "media_codes": "G001",
    "locations": "nursery",
    "reasons": "void_test_entry",
}


def a_row(switch: Switch) -> object:
    """A row of `switch.table` that is on now; its key."""
    if switch.table in SEEDED_KEYS:
        return SEEDED_KEYS[switch.table]
    with as_system():
        if switch.table == "plants":
            return make_plant(make_user("gene"))
        if switch.table == "auth_user":
            return make_user("gene")
        values = {
            "zoho_contact_id": "ZC-1",
            "name": "Green Leaf Co.",
            "active": True,
            "synced_at": db_now(),
        }
        return insert("vendors", values, "zoho_contact_id")


def value(switch: Switch, key: object) -> object:
    return fetch_one(
        f"SELECT {quote(switch.column)} FROM {quote(switch.table)}"  # noqa: S608
        f" WHERE {quote(switch.key_column)} = %s",
        [key],
    )[0]


def set_value(switch: Switch, key: object, new: object) -> None:
    run(
        f"UPDATE {quote(switch.table)} SET {quote(switch.column)} = %s"  # noqa: S608
        f" WHERE {quote(switch.key_column)} = %s",
        [new, key],
    )


@pytest.fixture
def staff() -> int:
    with as_system():
        return make_user("jade")


@pytest.mark.parametrize("name", sorted(SWITCHES))
def test_switching_off_without_a_reason_is_refused(name: str, staff: int) -> None:
    switch = SWITCHES[name]
    key = a_row(switch)
    before = value(switch, key)

    with named_in_sql(staff), refused_by("reason_required"):
        set_value(switch, key, switch.off)

    assert value(switch, key) == before


@pytest.mark.parametrize("name", sorted(SWITCHES))
def test_a_reason_from_another_list_is_refused(name: str, staff: int) -> None:
    """A "Duplicate entry" void reason can't retire a plant (design §4.2)."""
    switch = SWITCHES[name]
    key = a_row(switch)
    before = value(switch, key)

    with (
        named_in_sql(staff, reason_code=switch.wrong),
        refused_by("reason_wrong_list"),
    ):
        set_value(switch, key, switch.off)

    assert value(switch, key) == before


@pytest.mark.parametrize("name", sorted(SWITCHES))
def test_a_reason_on_no_list_is_refused(name: str, staff: int) -> None:
    switch = SWITCHES[name]
    key = a_row(switch)

    with (
        named_in_sql(staff, reason_code="made_up"),
        refused_by("reason_wrong_list"),
    ):
        set_value(switch, key, switch.off)


@pytest.mark.parametrize("name", sorted(SWITCHES))
def test_with_the_right_reason_it_is_saved_and_the_reason_is_in_the_trail(
    name: str, staff: int
) -> None:
    switch = SWITCHES[name]
    key = a_row(switch)
    mark = audit_mark()

    with named_in_sql(staff, reason_code=switch.right, note="moved on"):
        set_value(switch, key, switch.off)

    assert value(switch, key) == switch.off
    row = only_row(mark, switch.table)
    assert (row.reason_code, row.note) == (switch.right, "moved on")
    assert row.after == {switch.column: switch.off}


@pytest.mark.parametrize("name", ["genus", "account"])
def test_switching_back_on_needs_no_reason(name: str, staff: int) -> None:
    switch = SWITCHES[name]
    key = a_row(switch)
    with named_in_sql(staff, reason_code=switch.right):
        set_value(switch, key, switch.off)

    with named_in_sql(staff):
        set_value(switch, key, True)

    assert value(switch, key) is True


def test_other_changes_to_a_row_that_is_off_need_no_reason(staff: int) -> None:
    with named_in_sql(staff, reason_code=NO_LONGER_USED):
        run("UPDATE genera SET active = false WHERE code = 'HYA'")

    with named_in_sql(staff):
        run("UPDATE genera SET name = 'Hoya (old)' WHERE code = 'HYA'")

    assert fetch_one("SELECT name FROM genera WHERE code = 'HYA'") == ("Hoya (old)",)


def test_the_pdpa_reason_is_accepted_though_no_page_offers_it(staff: int) -> None:
    """`cucumber_anonymise` uses it; it is inactive on the list (design §5.1)."""
    with as_system():
        gene = make_user("gene")

    with named_in_sql(staff, reason_code=PDPA_CODE):
        run("UPDATE auth_user SET is_active = false WHERE id = %s", [gene])

    assert fetch_one("SELECT is_active FROM auth_user WHERE id = %s", [gene]) == (
        False,
    )


# ------------------------------------------- the new lists (references 0004)
def test_the_three_new_reason_lists_are_seeded() -> None:
    """Design §5.1, Q1 a."""
    rows = fetch_all(
        "SELECT applies_to, label FROM reasons WHERE active"
        " AND applies_to IN ('deactivate', 'retire', 'archive')"
    )
    seeded: dict[str, set[str]] = {}
    for applies_to, label in rows:
        seeded.setdefault(str(applies_to), set()).add(str(label))

    assert seeded == {name: set(labels) for name, labels in NEW_REASONS.items()}


def test_the_new_codes_follow_the_usual_shape() -> None:
    codes = {
        str(row[0])
        for row in fetch_all(
            "SELECT code FROM reasons WHERE applies_to IN"
            " ('deactivate', 'retire', 'archive')"
        )
    }

    assert {LEFT_COMPANY, NO_LONGER_GROWN, NO_LONGER_USED, PDPA_CODE} <= codes


def test_the_pdpa_request_reason_is_seeded_switched_off() -> None:
    row = fetch_one(
        "SELECT applies_to, label, active FROM reasons WHERE code = %s", [PDPA_CODE]
    )

    assert row == ("deactivate", "PDPA request", False)
