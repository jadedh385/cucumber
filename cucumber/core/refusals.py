"""Refusals: why a save was turned down, by rule name (U0.2 design §7.1).

Database refusals and service guards both carry a stable rule name. The
service looks the name up in design §7.1 for the message staff see.
"""

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import psycopg
from django.db import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)

# Shown for every rule marked "Internal" in design §7.1, and any unknown name.
INTERNAL_MESSAGE = "Something went wrong; nothing was saved. Please tell the Admin."

# The name a refusal has when the database gives none.
UNNAMED_RULE = "unnamed"

# Design §7.1: every rule staff can meet. Any name not here is Internal.
MESSAGES: dict[str, str] = {
    # Plants
    "plant_portfolio_needs_sku": "A Portfolio plant needs an SKU.",
    "plant_sku_format": "An SKU is 3 capital letters and 3 digits, e.g. PHL005.",
    "plant_sku_matches_genus": (
        "The SKU's first 3 letters must match the plant's genus."
    ),
    "plant_source_required": "Choose where the plant came from.",
    "plant_portfolio_needs_zoho_link": (
        "Add the vendor and Zoho reference before this plant can join the Portfolio."
    ),
    "plant_vendor_only_if_purchased": (
        "Vendor and Zoho reference apply only to purchased plants."
    ),
    "plant_min_saleable_positive": "Minimum saleable quantity must be at least 1.",
    "plant_name_valid": 'Enter a plant name, without "?" marks.',
    "plant_name_unique_in_genus": (
        "A plant with this name already exists in this genus."
    ),
    # Batches
    "batch_lab_needs_stage": "Batches in the Lab need a stage.",
    "batch_count_not_negative": (
        "This would take the batch below zero. Check the numbers."
    ),
    "batch_closed_needs_zero": (
        "A batch can only be closed or voided when it has 0 units."
    ),
    # Events and reviews
    "event_qty_not_negative": "Quantities can't be negative.",
    "event_counted_not_negative": "A count can't be negative.",
    "event_reason_required": "Choose a reason.",
    "event_not_in_future": "The date can't be in the future.",
    "event_within_7_days": (
        "You can pick a date up to 7 days back. For older work, log it today with"
        " the real date in the note; a reviewer will fix the date."
    ),
    "event_void_once": "This entry has already been voided.",
    "event_review_once": "This entry has already been reviewed.",
    "operations_pkey": "Already saved.",
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
    "split_qty_positive": "Split off at least 1 unit.",
    "staff_not_active": "Choose an active staff member for who did the work.",
    "plant_same_genus": "The plant is already in this genus.",
    "event_correction_keeps_shape": (
        "A correction can't change what kind of entry this is."
        " Void it and log the right entry instead."
    ),
    # Staff accounts (U0.5 design §7.1)
    "account_email_taken": "Another account already uses this email.",
    "account_email_invalid": "Enter a whole email address, like name@example.com.",
    "account_cannot_deactivate_self": "You can't deactivate your own account.",
    "account_cannot_reset_self": "Change your own password on the Password page.",
    "password_same_as_temporary": (
        "Choose a password different from the one you were given."
    ),
}


class Refused(Exception):
    """A save was refused; nothing was written.

    `rule` is the §7.1 name. `event_ids` lists the events the refusal is
    about, when there are any (e.g. the later events that block a void).
    """

    def __init__(self, rule: str, message: str, event_ids: Sequence[int] = ()) -> None:
        # Only the message: a printed refusal never shows the rule name.
        super().__init__(message)
        self.rule = rule
        self.message = message
        self.event_ids = tuple(event_ids)


def message_for(rule: str) -> str:
    """The message staff see for `rule` (design §7.1); Internal if not listed."""
    return MESSAGES.get(rule, INTERNAL_MESSAGE)


def refuse(rule: str, event_ids: Sequence[int] = ()) -> Refused:
    """A `Refused` for `rule`, with its §7.1 message; the caller raises it."""
    return Refused(rule, message_for(rule), event_ids)


def rule_of(error: DatabaseError) -> str:
    """The constraint, index or trigger name the database refused with.

    Triggers report theirs with `RAISE … USING CONSTRAINT` (design §7.1).
    """
    cause = error.__cause__
    if isinstance(cause, psycopg.Error) and cause.diag.constraint_name:
        return cause.diag.constraint_name
    return UNNAMED_RULE


@contextmanager
def database_refusals() -> Iterator[None]:
    """Turn a database refusal inside into `Refused`, by its rule name.

    Wrap the whole `transaction.atomic()` block: Django's one-column foreign
    keys are deferred and refuse only at commit (design §3.4). A refusal with
    the Internal message is logged in full for the Admin.

    A refusal is an integrity error or any error naming a rule. Anything
    else (a lost connection, a deadlock, a bug) goes on as it is: at COMMIT
    the save may have gone through, so "nothing was saved" would be wrong.
    """
    try:
        yield
    except DatabaseError as error:
        rule = rule_of(error)
        if rule == UNNAMED_RULE and not isinstance(error, IntegrityError):
            raise
        if rule not in MESSAGES:
            logger.exception("Save refused by the database (%s)", rule)
        raise refuse(rule) from error
