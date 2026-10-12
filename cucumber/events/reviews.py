"""Review rules and the review queue (U0.2 design §2.5, Q3, rule 10).

Who reviews what: Tech events → a Supervisor or the Admin; an event with a
Supervisor on it (did it or saved it) → the Admin only; every Void → the
Admin only. Nobody but the Admin reviews an event they did or saved.
Roles are the Django groups `admin`, `supervisor`, `tech` (design §2.7).

The Admin's own saves are reviewed as they are saved, and a reviewer's
Correction or Void marks the original reviewed; both happen inside the event
services, in the same transaction.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Exists, OuterRef

from cucumber.accounts.services import ADMIN, SUPERVISOR, has_role, members_of
from cucumber.core.refusals import database_refusals, refuse
from cucumber.events.models import Action, Event, EventReview

# Queue flags (design §3.1). Dated before a count: an effective count saved
# before this event (a lower id) is dated after it, so the event changed that
# count's difference instead of the total. A normal entry that a later count
# follows isn't flagged.
DATED_BEFORE_COUNT = "dated_before_count"
# Entered late: `occurred_at` more than 24 hours before `recorded_at` (Q5).
ENTERED_LATE = "entered_late"
LATE_AFTER = timedelta(hours=24)

ADMIN_OWN_ENTRY = "Admin, own entry"
# Fix rows are dated by what they restate, so the date flags skip them.
FIX_ACTIONS = (Action.VOID, Action.CORRECTION)


@dataclass(frozen=True)
class QueueItem:
    """One item in a reviewer's queue: the unreviewed events of one operation."""

    operation_id: uuid.UUID
    event_ids: tuple[int, ...]
    flags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Reviewer:
    """A would-be reviewer's roles, looked up once."""

    user_id: int
    is_admin: bool
    is_supervisor: bool
    supervisor_ids: frozenset[int]

    @property
    def reviews_anything(self) -> bool:
        return self.is_admin or self.is_supervisor


def reviewer_for(user: User) -> Reviewer:
    return Reviewer(
        user_id=user.pk,
        is_admin=has_role(user, ADMIN),
        is_supervisor=has_role(user, SUPERVISOR),
        supervisor_ids=members_of(SUPERVISOR),
    )


def may_review(reviewer: Reviewer, event: Event) -> bool:
    """Rule 10: whether `reviewer` may mark `event` reviewed."""
    if reviewer.is_admin:
        return True
    if not reviewer.is_supervisor or event.action == Action.VOID:
        return False
    people = {event.staff_id, event.recorded_by_id}
    return reviewer.user_id not in people and not people & reviewer.supervisor_ids


def waiting_for_review() -> list[Event]:
    """Unreviewed events, leaving out voided ones, oldest first."""
    reviews = EventReview.objects.filter(event=OuterRef("pk"))
    unreviewed = Event.objects.filter(~Exists(reviews), voided_by__isnull=True)
    return list(unreviewed.order_by("id"))


# ------------------------------------------------------------------ the queue


def review_queue(reviewer: User) -> list[QueueItem]:
    """The items `reviewer` may review: unreviewed, non-voided events by operation."""
    who = reviewer_for(reviewer)
    if not who.reviews_anything:
        return []
    events = [event for event in waiting_for_review() if may_review(who, event)]
    flags = event_flags(events)
    by_operation: dict[uuid.UUID, list[Event]] = {}
    for event in events:
        by_operation.setdefault(event.operation_id, []).append(event)
    return [
        QueueItem(
            operation_id=operation_id,
            event_ids=tuple(event.pk for event in grouped),
            flags=frozenset().union(*(flags.get(event.pk, ()) for event in grouped)),
        )
        for operation_id, grouped in by_operation.items()
    ]


def event_flags(events: Sequence[Event]) -> dict[int, frozenset[str]]:
    """Each original event's queue flags, by event id."""
    originals = [event for event in events if event.action not in FIX_ACTIONS]
    before_count = dated_before_count(originals)
    return {
        event.pk: frozenset(
            flag
            for flag, applies in (
                (ENTERED_LATE, event.recorded_at - event.occurred_at > LATE_AFTER),
                (DATED_BEFORE_COUNT, event.pk in before_count),
            )
            if applies
        )
        for event in originals
    }


def dated_before_count(events: Sequence[Event]) -> set[int]:
    """The events an earlier-saved effective count is dated after (design §3.1)."""
    flagged = set()
    for batch_id in {event.batch_id for event in events}:
        effective = {e.id: e for e in Event.objects.effective_events(batch_id)}
        counts = [e for e in effective.values() if e.action == Action.COUNT]
        for event in events:
            own = effective.get(event.pk)
            if event.batch_id != batch_id or own is None:
                continue
            if any(c.id < own.id and c.occurred_at > own.occurred_at for c in counts):
                flagged.add(event.pk)
    return flagged


# -------------------------------------------------------------- reviewing


def review(reviewer: User, operation_id: uuid.UUID, note: str = "") -> None:
    """Mark every unreviewed event of the operation reviewed by `reviewer`.

    Refused (`review_not_allowed`) if `reviewer` may not review one of them.
    """
    who = reviewer_for(reviewer)
    waiting = [e for e in waiting_for_review() if e.operation_id == operation_id]
    if not who.reviews_anything or not all(may_review(who, e) for e in waiting):
        raise refuse("review_not_allowed")
    with database_refusals(), transaction.atomic():
        write_reviews(reviewer, [event.pk for event in waiting], note)


def write_reviews(reviewer: User, event_ids: Sequence[int], note: str) -> None:
    EventReview.objects.bulk_create(
        EventReview(event_id=event_id, reviewer=reviewer, note=note)
        for event_id in event_ids
    )


def review_admin_entry(recorded_by: User, event_ids: Sequence[int]) -> None:
    """Admin auto-review: the Admin's own save is reviewed as it is saved (Q3)."""
    if has_role(recorded_by, ADMIN):
        write_reviews(recorded_by, event_ids, ADMIN_OWN_ENTRY)


def review_fixed_originals(fixed_by: User, originals: Sequence[Event]) -> None:
    """A reviewer's Correction or Void marks the originals reviewed (Q3).

    Only originals not yet reviewed, and only those `fixed_by` may review.
    """
    who = reviewer_for(fixed_by)
    reviewed = set(
        EventReview.objects.filter(event__in=originals).values_list(
            "event_id", flat=True
        )
    )
    event_ids = [
        event.pk
        for event in originals
        if event.pk not in reviewed and may_review(who, event)
    ]
    write_reviews(fixed_by, event_ids, "")
