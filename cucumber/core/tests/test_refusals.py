"""U0.2b: the message staff see for each refusal (design §7.1)."""

import pytest
from django.db import IntegrityError, OperationalError

from cucumber.core.refusals import Refused, database_refusals, message_for, refuse

# Design §7.1, written out so a wrong constant in the code is caught.
INTERNAL = "Something went wrong; nothing was saved. Please tell the Admin."

WITHIN_7_DAYS = (
    "You can pick a date up to 7 days back. For older work, log it today with"
    " the real date in the note; a reviewer will fix the date."
)

DESIGN_MESSAGES = {
    # Database rules
    "batch_count_not_negative": (
        "This would take the batch below zero. Check the numbers."
    ),
    "batch_closed_needs_zero": (
        "A batch can only be closed or voided when it has 0 units."
    ),
    "event_reason_required": "Choose a reason.",
    "event_void_once": "This entry has already been voided.",
    "event_within_7_days": WITHIN_7_DAYS,
    "plant_name_unique_in_genus": (
        "A plant with this name already exists in this genus."
    ),
    # Service guards (U0.2b)
    "batch_not_open": (
        "This batch is closed. Only voiding its Close can be logged on it."
    ),
    "void_has_later_events": "Void the later entries on the batches this made first.",
    "void_of_void": "A void can't be voided. Log the entry again instead.",
    "split_needs_note": "Say why these units are split off.",
    "review_not_allowed": (
        "You can't review this entry; it waits for another reviewer."
    ),
    "admin_only": "Only the Admin can do this.",
    # Service guards (U0.2b G4)
    "split_qty_positive": "Split off at least 1 unit.",
    "staff_not_active": "Choose an active staff member for who did the work.",
    "plant_same_genus": "The plant is already in this genus.",
}


@pytest.mark.parametrize(("rule", "message"), DESIGN_MESSAGES.items())
def test_each_rule_shows_its_design_message(rule: str, message: str) -> None:
    assert message_for(rule) == message


@pytest.mark.parametrize(
    "rule",
    [
        "event_void_target",
        "events_append_only",
        "event_reason_matches_action",
        "batch_not_found",
        "event_not_found",
        "plant_not_found",
        "event_one_batch",
        "event_correction_keeps_shape",
        "no_such_rule",
    ],
)
def test_internal_and_unknown_rules_show_the_internal_message(rule: str) -> None:
    assert message_for(rule) == INTERNAL


def test_a_refusal_reads_as_its_message_only() -> None:
    """Printing a refusal never shows the internal rule name (G4 security M4)."""
    assert str(refuse("split_needs_note")) == "Say why these units are split off."


def test_a_database_refusal_without_a_name_is_refused_as_internal() -> None:
    with pytest.raises(Refused) as caught, database_refusals():
        raise IntegrityError("a deferred foreign key failed at commit")
    assert (caught.value.rule, caught.value.message) == ("unnamed", INTERNAL)


def test_a_database_failure_that_is_not_a_refusal_is_not_hidden() -> None:
    """A lost connection or deadlock isn't "nothing was saved" (G4 HIGH 1).

    At COMMIT the save may have gone through, and a deadlock can be retried,
    so the error goes on to the caller as it is.
    """
    with pytest.raises(OperationalError), database_refusals():
        raise OperationalError("server closed the connection unexpectedly")
