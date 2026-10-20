"""Who may save, void, correct and undo events (U0.6 design §4.2).

Each action an operation can save belongs to one matrix row. Void and
Correction never go through `save_operation`; they have their own services
and the Void tree.
"""

import logging
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from cucumber.accounts.permissions import NotAllowed, Permission, Role, Standing, may
from cucumber.core.expressions import TransactionNow
from cucumber.core.refusals import refuse
from cucumber.events.models import Action, Event, Operation

logger = logging.getLogger(__name__)

# D-07: an Undo is a Void of your own save within this long, by the
# database's clock (the one that stamped `operations.recorded_at`).
UNDO_WINDOW = timedelta(minutes=10)

ACTION_ROWS: dict[str, Permission] = {
    Action.INTAKE: Permission.LOG_WORK,
    Action.SUBCULTURE: Permission.LOG_WORK,
    Action.STAGE_CHANGE: Permission.LOG_WORK,
    Action.COUNT: Permission.LOG_WORK,
    Action.CONTAMINATION: Permission.LOG_WORK,
    Action.TRANSFER: Permission.LOG_WORK,
    Action.OUT: Permission.LOG_WORK,
    Action.SPLIT: Permission.SPLIT_CLOSE_LOSS,
    Action.CLOSE: Permission.SPLIT_CLOSE_LOSS,
    Action.LOSS: Permission.SPLIT_CLOSE_LOSS,
    Action.QUARANTINE: Permission.SPLIT_CLOSE_LOSS,
    Action.RELEASE: Permission.RELEASE_QUARANTINE,
}

# Saved by their own services, never by `save_operation` (event_action_not_here).
NOT_THROUGH_SAVE = frozenset({Action.VOID, Action.CORRECTION})


def check_actions(standing: Standing, actions: Sequence[str]) -> None:
    """Each action's matrix row must allow the person (§4.2); else `NotAllowed`."""
    for action in actions:
        row = ACTION_ROWS.get(action)
        if row is None:
            raise refuse("event_action_not_here")
        if not may(standing.role, row):
            raise NotAllowed("role_not_allowed")


def check_work_for(standing: Standing, staff_ids: Sequence[int | None]) -> None:
    """N7: work done by someone else needs ENTER_FOR_OTHERS (`staff_must_be_you`)."""
    others = {staff for staff in staff_ids if staff not in (None, standing.user_id)}
    if others and not may(standing.role, Permission.ENTER_FOR_OTHERS):
        raise refuse("staff_must_be_you")


def people_on(originals: Sequence[Event]) -> set[int]:
    """Everyone who did (`staff_id`) or saved (`recorded_by`) any of the events."""
    return {
        person
        for event in originals
        for person in (event.staff_id, event.recorded_by_id)
        if person is not None
    }


def check_void(standing: Standing, originals: Sequence[Event]) -> None:
    """The Void tree (§4.2): who may void this operation, and as what.

    The Admin always may. A reviewer (VOID_OR_CORRECT) may unless they are on
    it. Otherwise it is an Undo: only the person who saved it, within
    `UNDO_WINDOW`, by the database's clock against `operations.recorded_at`.
    """
    if standing.role == Role.ADMIN:
        return
    is_reviewer = may(standing.role, Permission.VOID_OR_CORRECT)
    if is_reviewer and standing.user_id not in people_on(originals):
        return
    operation_id = originals[0].operation_id
    saved = Operation.objects.filter(pk=operation_id, recorded_by_id=standing.user_id)
    if not saved.exists():
        raise refuse("fix_own_entry" if is_reviewer else "undo_not_yours")
    recent = saved.filter(recorded_at__gt=TransactionNow() - UNDO_WINDOW)
    if not recent.exists():
        raise refuse("undo_too_late")


def check_correction(standing: Standing, originals: Sequence[Event]) -> None:
    """A reviewer other than the Admin can't correct what they did or saved."""
    if standing.role != Role.ADMIN and standing.user_id in people_on(originals):
        raise refuse("fix_own_entry")


def check_resend(operation_id: UUID, saved_by: int) -> None:
    """A resent form is answered only to the person who saved it (§4.3)."""
    first = Operation.objects.filter(pk=operation_id).values_list(
        "recorded_by_id", flat=True
    )
    if first.first() != saved_by:
        logger.warning(
            "operation saved by other operation=%s by=%s", operation_id, saved_by
        )
        raise refuse("operation_saved_by_other")
