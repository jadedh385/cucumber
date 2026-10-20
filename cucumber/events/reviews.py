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

from cucumber.accounts.permissions import Permission, Role, require, standing
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
    """The reviewer's role, read from the database now (U0.6 §4.2): someone
    switched off reviews nothing."""
    current = standing(user)
    role = current.role if current.is_active else None
    return Reviewer(
        user_id=user.pk,
        is_admin=role == Role.ADMIN,
        is_supervisor=role == Role.SUPERVISOR,
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


def waiting_for_review(operation_id: uuid.UUID | None = None) -> list[Event]:
    """Unreviewed events, leaving out voided ones, oldest first.

    With `operation_id`, only that operation's.
    """
    reviews = EventReview.objects.filter(event=OuterRef("pk"))
    unreviewed = Event.objects.filter(~Exists(reviews), voided_by__isnull=True)
    if operation_id is not None:
        unreviewed = unreviewed.filter(operation_id=operation_id)
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
    """The events an earlier-saved effective count is dated after (design §3.1).

    Every batch's history is read in one query, however many batches wait.
    """
    by_batch = Event.objects.effective_events_of({event.batch_id for event in events})
    flagged = set()
    for event in events:
        effective = by_batch.get(event.batch_id, [])
        own = next((e for e in effective if e.id == event.pk), None)
        if own is None:
            continue
        counts = [e for e in effective if e.action == Action.COUNT]
        if any(c.id < own.id and c.occurred_at > own.occurred_at for c in counts):
            flagged.add(event.pk)
    return flagged


# -------------------------------------------------------------- reviewing


def review(reviewer: User, operation_id: uuid.UUID, note: str = "") -> None:
    """Mark every unreviewed event of the operation reviewed by `reviewer`.

    Refused (`review_not_allowed`) if `reviewer` may not review one of them
    (rule 10; a Void is also a matrix row, REVIEW_VOIDS: `NotAllowed`),
    and (`event_review_once`) if nothing of it waits: already reviewed,
    voided, or no such operation.
    """
    with database_refusals(), transaction.atomic():
        require(reviewer, Permission.REVIEW_EVENTS)
        who = reviewer_for(reviewer)
        waiting = waiting_for_review(operation_id)
        if not waiting:
            raise refuse("event_review_once")
        if any(event.action == Action.VOID for event in waiting):
            require(reviewer, Permission.REVIEW_VOIDS)
        if not all(may_review(who, event) for event in waiting):
            raise refuse("review_not_allowed")
        write_reviews(reviewer, [event.pk for event in waiting], note)


def write_reviews(
    reviewer: User, event_ids: Sequence[int], note: str, *, skip_reviewed: bool = False
) -> None:
    """One review row per event. With `skip_reviewed`, an event someone else
    reviewed meanwhile keeps that review instead of refusing the save."""
    EventReview.objects.bulk_create(
        (
            EventReview(event_id=event_id, reviewer=reviewer, note=note)
            for event_id in event_ids
        ),
        ignore_conflicts=skip_reviewed,
    )


def review_admin_entry(recorded_by: User, event_ids: Sequence[int]) -> None:
    """Admin auto-review: the Admin's own save is reviewed as it is saved (Q3)."""
    if has_role(recorded_by, ADMIN):
        write_reviews(recorded_by, event_ids, ADMIN_OWN_ENTRY)


def review_fixed_originals(fixed_by: User, originals: Sequence[Event]) -> None:
    """A reviewer's Correction or Void marks the originals reviewed (Q3).

    Only originals `fixed_by` may review. One already reviewed, even by a
    review saving at this moment, keeps its review; the fix still saves.
    """
    who = reviewer_for(fixed_by)
    event_ids = [event.pk for event in originals if may_review(who, event)]
    write_reviews(fixed_by, event_ids, "", skip_reviewed=True)
