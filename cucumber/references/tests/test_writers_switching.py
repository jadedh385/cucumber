"""AC10–AC12 and design §3.3: switching off needs a reason, switching on needs
none, and a call that changes nothing writes nothing."""

from collections.abc import Callable

import pytest
from django.contrib.auth.models import User

from cucumber.core.audit import Reason
from cucumber.core.refusals import MESSAGES, Refused
from cucumber.core.tests.trail import (
    DUPLICATE_ENTRY,
    LEFT_COMPANY,
    NO_LONGER_USED,
    audit_mark,
    audit_rows_since,
)
from cucumber.references.lists import ListName
from cucumber.references.reading import Item, item
from cucumber.references.services import edit_label, switch_off, switch_on
from cucumber.references.tests.support import (
    ARCHIVE_REASON,
    SEEDED,
    SWITCHABLE,
    nothing_written,
    switched_off,
)

pytestmark = pytest.mark.django_db

M = ListName.MEDIA_CODES
LONGEST_NOTE = 500

BAD_REASONS = [
    (None, "reason_required"),
    (Reason(""), "reason_required"),
    (Reason("   "), "reason_required"),
    (Reason(DUPLICATE_ENTRY), "reason_wrong_list"),  # a `void` reason
    (Reason(LEFT_COMPANY), "reason_wrong_list"),  # a `deactivate` reason
    (Reason("archive_made_up"), "reason_wrong_list"),
    (Reason(NO_LONGER_USED, "x" * (LONGEST_NOTE + 1)), "reason_note_too_long"),
]


@pytest.mark.parametrize(
    ("reason", "rule"), BAD_REASONS, ids=[rule for _, rule in BAD_REASONS]
)
def test_a_switch_off_with_a_bad_reason_is_refused_by_rule_name(
    admin: User, reason: Reason | None, rule: str
) -> None:
    with nothing_written(M), pytest.raises(Refused) as refused:
        switch_off(admin, M, "M001", reason)

    assert refused.value.rule == rule
    assert refused.value.message == MESSAGES[rule]


@pytest.mark.parametrize("name", SWITCHABLE)
def test_a_switch_off_with_no_reason_is_refused_on_every_list(
    admin: User, name: ListName
) -> None:
    with nothing_written(name), pytest.raises(Refused) as refused:
        switch_off(admin, name, SEEDED[name], None)

    assert refused.value.rule == "reason_required"


def test_a_note_of_exactly_five_hundred_characters_is_accepted(admin: User) -> None:
    reason = Reason(NO_LONGER_USED, "x" * LONGEST_NOTE)

    assert switch_off(admin, M, "M001", reason).active is False


def test_the_length_of_a_note_is_counted_after_trimming(admin: User) -> None:
    reason = Reason(NO_LONGER_USED, f"  {'x' * LONGEST_NOTE}  ")

    assert switch_off(admin, M, "M001", reason).active is False


def test_a_note_is_optional(admin: User) -> None:
    assert switch_off(admin, M, "M001", Reason(NO_LONGER_USED)).active is False


def test_a_reason_is_still_asked_for_an_item_already_off(admin: User) -> None:
    """So the call always means the same thing (design §3.3)."""
    switched_off(M, "M004")

    with nothing_written(M), pytest.raises(Refused) as refused:
        switch_off(admin, M, "M004", None)

    assert refused.value.rule == "reason_required"


def test_a_bad_reason_is_refused_before_a_code_that_is_not_there(admin: User) -> None:
    """Step 3 (the inputs) comes before the database rules of step 5."""
    with pytest.raises(Refused) as refused:
        switch_off(admin, M, "M999", None)

    assert refused.value.rule == "reason_required"


# ------------------------------------------------------------------ switch on


@pytest.mark.parametrize("name", SWITCHABLE)
def test_switching_on_asks_no_reason(admin: User, name: ListName) -> None:
    switched_off(name, SEEDED[name])

    assert switch_on(admin, name, SEEDED[name]).active is True


def test_an_item_switched_off_and_on_again_keeps_its_label(admin: User) -> None:
    edit_label(admin, M, "M002", "Half MS")

    switch_off(admin, M, "M002", ARCHIVE_REASON)
    switch_on(admin, M, "M002")

    assert item(M, "M002") == Item("M002", "Half MS", True)


# ----------------------------------------------------------------- no change


def audit_rows_made_by(call: Callable[[], object]) -> int:
    mark = audit_mark()
    call()
    return len(audit_rows_since(mark))


def test_saving_the_same_label_writes_no_audit_row(admin: User) -> None:
    same = item(M, "M001")
    assert same is not None

    written = audit_rows_made_by(lambda: edit_label(admin, M, "M001", same.label))

    assert written == 0


def test_saving_the_same_label_returns_the_item_as_it_is(admin: User) -> None:
    same = item(M, "M001")
    assert same is not None

    assert edit_label(admin, M, "M001", same.label) == same


def test_saving_the_same_label_with_padding_writes_no_audit_row(admin: User) -> None:
    same = item(ListName.GENERA, "HYA")
    assert same is not None

    written = audit_rows_made_by(
        lambda: edit_label(admin, ListName.GENERA, "HYA", f"  {same.label} ")
    )

    assert written == 0


def test_switching_on_an_item_already_on_writes_no_audit_row(admin: User) -> None:
    assert audit_rows_made_by(lambda: switch_on(admin, M, "M001")) == 0
    assert switch_on(admin, M, "M001") == Item("M001", "M001", True)


def test_switching_off_an_item_already_off_writes_no_audit_row(admin: User) -> None:
    switched_off(M, "M004")

    written = audit_rows_made_by(lambda: switch_off(admin, M, "M004", ARCHIVE_REASON))

    assert written == 0
    assert item(M, "M004") == Item("M004", "M004", False)
