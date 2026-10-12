"""U0.2b: the message staff see for each refusal (design §7.1)."""

import pytest

from cucumber.core.refusals import INTERNAL_MESSAGE, message_for

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
        "no_such_rule",
    ],
)
def test_internal_and_unknown_rules_show_the_internal_message(rule: str) -> None:
    assert message_for(rule) == INTERNAL_MESSAGE
