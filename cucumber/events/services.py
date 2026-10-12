"""Rules for the events app. Views call these; they never hold rules themselves.

The event core every action service shares (U0.2 design §3.1, §3.3). Each
save is one transaction: the `operations` row first (a resent form stops
there, "Already saved"), then the affected batches locked in ascending `id`
order (`FOR NO KEY UPDATE`, design §3.4), then the events, then each
batch's projection recalculated from its effective events. Any refusal,
from the database or a service guard, raises `Refused` with the rule's
design §7.1 name, and nothing is written.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from cucumber.batches.models import Batch, BatchOrigin, BatchStatus
from cucumber.core.refusals import Refused, database_refusals, refuse
from cucumber.events.models import Action, Event
from cucumber.events.projection import Effective, count_differences
from cucumber.events.reviews import review_admin_entry, review_fixed_originals
from cucumber.events.writing import (
    check_reason,
    insert_event,
    lock_batches,
    lock_plants,
    refresh_all,
    start_operation,
)

# The rule a resent form meets: its `operation_id` is already saved (§3.3).
ALREADY_SAVED = "operations_pkey"
# Q8: units move between two batches, so a quantity fix is made on both sides.
PAIRED_ACTIONS = (Action.SPLIT, Action.TRANSFER, Action.QUARANTINE)


@dataclass(frozen=True)
class NewBatch:
    """A batch the operation creates; its first event is an `intake` on it."""

    plant_id: int
    origin: str
    location_code: str
    parent_batch_id: int | None = None


@dataclass(frozen=True)
class NewEvent:
    """One event of an operation, on an existing batch or on a `NewBatch`.

    Each entry with a `new_batch` makes its own batch. `occurred_at`
    defaults to now; `staff_id` (who did the work) defaults to the person
    saving it.
    """

    action: str
    batch_id: int | None = None
    new_batch: NewBatch | None = None
    qty_in: int = 0
    qty_out: int = 0
    counted_qty: int | None = None
    media_code: str | None = None
    stage_to: str | None = None
    reason_code: str | None = None
    occurred_at: datetime | None = None
    staff_id: int | None = None
    note: str = ""


@dataclass(frozen=True)
class Saved:
    """What a save wrote: its operation, events and new batches, in entry order.

    `already_saved` is True when the same `operation_id` came again (a double
    tap or a resend): nothing new was written and this is the original result.
    """

    operation_id: uuid.UUID
    event_ids: tuple[int, ...]
    batch_ids: tuple[int, ...] = ()
    already_saved: bool = False


@dataclass(frozen=True)
class Restated:
    """The values a Correction changes; `None` keeps the value as it is now."""

    qty_in: int | None = None
    qty_out: int | None = None
    counted_qty: int | None = None
    media_code: str | None = None
    stage_to: str | None = None
    occurred_at: datetime | None = None

    @property
    def moves_units(self) -> bool:
        return self.qty_in is not None or self.qty_out is not None


# ------------------------------------------------------- saving an operation


def save_operation(
    operation_id: uuid.UUID, recorded_by: User, entries: Sequence[NewEvent]
) -> Saved:
    """Save one user action: all its events, or none (design §3.3)."""
    try:
        with database_refusals(), transaction.atomic():
            return write_operation(operation_id, recorded_by, entries)
    except Refused as refusal:
        if refusal.rule != ALREADY_SAVED:
            raise
    return original_result(operation_id)


def write_operation(
    operation_id: uuid.UUID, recorded_by: User, entries: Sequence[NewEvent]
) -> Saved:
    """The writes of `save_operation`, inside its transaction."""
    start_operation(operation_id, recorded_by)
    plant_ids = {entry.new_batch.plant_id for entry in entries if entry.new_batch}
    next_seq = lock_plants(plant_ids)
    locked = lock_batches({entry.batch_id for entry in entries if entry.batch_id})
    for entry in entries:
        check_entry(entry, locked)
    made = make_batches(operation_id, recorded_by, entries, next_seq)
    now = timezone.now()
    event_ids = [
        insert_event(
            operation_id,
            recorded_by,
            batch_id,
            entry.action,
            entry.occurred_at or now,
            **event_values(entry, recorded_by),
        )
        for entry, batch_id in zip(entries, batch_ids(entries, made), strict=True)
    ]
    refresh_all([*locked.values(), *made.values()])
    review_admin_entry(recorded_by, event_ids)
    return Saved(operation_id, tuple(event_ids), tuple(b.pk for b in made.values()))


def make_batches(
    operation_id: uuid.UUID,
    recorded_by: User,
    entries: Sequence[NewEvent],
    next_seq: dict[int, int],
) -> dict[int, Batch]:
    """Insert each new batch, keyed by its entry's position, in entry order.

    The plants are locked already, so the `plant_seq` numbers are free.
    """
    made: dict[int, Batch] = {}
    for position, entry in enumerate(entries):
        new = entry.new_batch
        if new is None:
            continue
        earlier = sum(1 for batch in made.values() if batch.plant_id == new.plant_id)
        seq = next_seq[new.plant_id] + earlier
        made[position] = make_batch(operation_id, recorded_by, new, seq, entry.stage_to)
    return made


def batch_ids(entries: Sequence[NewEvent], made: dict[int, Batch]) -> list[int]:
    """Each entry's batch: the one it made, or the existing one it names."""
    ids = []
    for position, entry in enumerate(entries):
        if position in made:
            ids.append(made[position].pk)
        elif entry.batch_id is not None:
            ids.append(entry.batch_id)
    return ids


def check_entry(entry: NewEvent, locked: dict[int, Batch]) -> None:
    """Service guards on one entry, under the batch locks (design §3, Q7)."""
    if entry.batch_id is None and entry.new_batch is None:
        raise refuse("event_needs_batch")
    if entry.batch_id is not None:
        batch = locked[entry.batch_id]
        if batch.status != BatchStatus.OPEN:
            raise refuse("batch_not_open")
        if entry.action == Action.CLOSE and batch.live_count != 0:
            raise refuse("batch_closed_needs_zero")
    if entry.action == Action.SPLIT and not entry.note.strip():
        raise refuse("split_needs_note")
    check_reason(entry.action, entry.reason_code)


def make_batch(
    operation_id: uuid.UUID,
    recorded_by: User,
    new: NewBatch,
    plant_seq: int,
    stage_code: str | None,
) -> Batch:
    """Insert a new batch at its starting stage (a Lab batch needs one at once)."""
    return Batch.objects.create(
        plant_id=new.plant_id,
        plant_seq=plant_seq,
        parent_batch_id=new.parent_batch_id,
        origin=new.origin,
        created_operation_id=operation_id,
        location_id=new.location_code,
        stage_id=stage_code,
        quarantined=new.origin == BatchOrigin.QUARANTINE,
        status=BatchStatus.OPEN,
        live_count=0,
        created_by=recorded_by,
    )


def event_values(entry: NewEvent, recorded_by: User) -> dict[str, Any]:
    """The entry's columns, besides the operation, batch, action and date."""
    return {
        "qty_in": entry.qty_in,
        "qty_out": entry.qty_out,
        "counted_qty": entry.counted_qty,
        "media_code_id": entry.media_code,
        "stage_to_id": entry.stage_to,
        "reason_id": entry.reason_code,
        "staff_id": entry.staff_id or recorded_by.pk,
        "note": entry.note,
    }


def original_result(operation_id: uuid.UUID) -> Saved:
    """What the first save of `operation_id` wrote (a resend; issue #4)."""
    events = Event.objects.filter(operation_id=operation_id).order_by("id")
    batches = Batch.objects.filter(created_operation_id=operation_id).order_by("id")
    return Saved(
        operation_id,
        tuple(events.values_list("id", flat=True)),
        tuple(batches.values_list("id", flat=True)),
        already_saved=True,
    )


# ------------------------------------------------------------- Split, Close


def split(
    operation_id: uuid.UUID,
    recorded_by: User,
    batch_id: int,
    qty: int,
    note: str,
    occurred_at: datetime | None = None,
) -> Saved:
    """Move `qty` units into a new child batch, with a note saying why (Q7).

    The child has origin `split`, the parent's location and stage. Both
    events share the operation.
    """
    parent = Batch.objects.get(pk=batch_id)
    child = NewBatch(
        plant_id=parent.plant_id,
        origin=BatchOrigin.SPLIT,
        location_code=parent.location_id,
        parent_batch_id=batch_id,
    )
    entries = [
        NewEvent(
            Action.SPLIT,
            batch_id=batch_id,
            qty_out=qty,
            note=note,
            occurred_at=occurred_at,
        ),
        NewEvent(
            Action.INTAKE,
            new_batch=child,
            qty_in=qty,
            stage_to=parent.stage_id,
            occurred_at=occurred_at,
        ),
    ]
    return save_operation(operation_id, recorded_by, entries)


def close(
    operation_id: uuid.UUID,
    recorded_by: User,
    batch_id: int,
    occurred_at: datetime | None = None,
) -> Saved:
    """Close a batch at 0 with a `close` event (Q7)."""
    entry = NewEvent(Action.CLOSE, batch_id=batch_id, occurred_at=occurred_at)
    return save_operation(operation_id, recorded_by, [entry])


# ---------------------------------------------------------------------- Void


def void(recorded_by: User, event_id: int, reason_code: str, note: str = "") -> Saved:
    """Void an event and every other event of its operation (Q8, design §3.1).

    One Void row per event, all in a new operation. Batches the operation
    created become `voided`. Refused if any of those batches has a later
    event; the refusal lists them.
    """
    target = Event.objects.get(pk=event_id)
    if target.action == Action.VOID:
        raise refuse("void_of_void")
    with database_refusals(), transaction.atomic():
        return write_void(recorded_by, target.operation_id, reason_code, note)


def write_void(
    recorded_by: User, voided_operation: uuid.UUID, reason_code: str, note: str
) -> Saved:
    """The writes of `void`, inside its transaction."""
    operation_id = uuid.uuid4()
    start_operation(operation_id, recorded_by)
    originals = list(Event.objects.filter(operation_id=voided_operation).order_by("id"))
    made_ids = set(
        Batch.objects.filter(created_operation_id=voided_operation).values_list(
            "id", flat=True
        )
    )
    locked = lock_batches({event.batch_id for event in originals} | made_ids)
    check_void(originals, locked, made_ids)
    check_reason(Action.VOID, reason_code)
    now = timezone.now()
    void_ids = [
        insert_event(
            operation_id,
            recorded_by,
            original.batch_id,
            Action.VOID,
            now,
            voids_event_id=original.pk,
            reason_id=reason_code,
            staff_id=recorded_by.pk,
            note=note,
        )
        for original in originals
    ]
    refresh_all(locked.values(), voided_ids=made_ids, voided_at=now)
    review_fixed_originals(recorded_by, originals)
    review_admin_entry(recorded_by, void_ids)
    return Saved(operation_id, tuple(void_ids))


def check_void(
    originals: list[Event], locked: dict[int, Batch], made_ids: set[int]
) -> None:
    """Service guards on an operation-wide void, under the batch locks (Q7, Q8)."""
    if Event.objects.filter(voids_event__in=originals).exists():
        raise refuse("event_void_once")
    operation_ids = {event.operation_id for event in originals}
    later = list(
        Event.objects.filter(batch_id__in=made_ids, voided_by__isnull=True)
        .exclude(operation_id__in=operation_ids)
        .exclude(action__in=[Action.VOID, Action.CORRECTION])
        .order_by("id")
        .values_list("id", flat=True)
    )
    if later:
        raise refuse("void_has_later_events", later)
    for event in originals:
        status = locked[event.batch_id].status
        reopens = status == BatchStatus.CLOSED and event.action == Action.CLOSE
        if status != BatchStatus.OPEN and not reopens:
            raise refuse("batch_not_open")


# ---------------------------------------------------------------- Correction


def correct(
    recorded_by: User,
    event_id: int,
    reason_code: str,
    *,
    qty_in: int | None = None,
    qty_out: int | None = None,
    counted_qty: int | None = None,
    media_code: str | None = None,
    stage_to: str | None = None,
    occurred_at: datetime | None = None,
    note: str = "",
) -> Saved:
    """Restate an event's values; `None` keeps the value as it is now.

    A Correction that doesn't restate the date keeps the original's (M1).
    For a `split`, `transfer` or `quarantine`, a quantity correction is
    written on both sides in one operation (Q8).
    """
    target = Event.objects.get(pk=event_id)
    if target.action in (Action.VOID, Action.CORRECTION):
        raise refuse("event_not_correctable")
    changes = Restated(qty_in, qty_out, counted_qty, media_code, stage_to, occurred_at)
    with database_refusals(), transaction.atomic():
        return write_correction(recorded_by, target, reason_code, changes, note)


def write_correction(
    recorded_by: User, target: Event, reason_code: str, changes: Restated, note: str
) -> Saved:
    """The writes of `correct`, inside its transaction."""
    operation_id = uuid.uuid4()
    start_operation(operation_id, recorded_by)
    fixes = corrections_for(target, changes)
    originals = [original for original, _ in fixes]
    locked = lock_batches({original.batch_id for original in originals})
    if any(batch.status != BatchStatus.OPEN for batch in locked.values()):
        raise refuse("batch_not_open")
    if Event.objects.filter(voids_event__in=originals).exists():
        raise refuse("event_not_correctable")
    check_reason(Action.CORRECTION, reason_code)
    fix_ids = [
        insert_event(
            operation_id,
            recorded_by,
            original.batch_id,
            Action.CORRECTION,
            **restated_values(current_values(original), restated),
            corrects_event_id=original.pk,
            reason_id=reason_code,
            staff_id=recorded_by.pk,
            note=note,
        )
        for original, restated in fixes
    ]
    refresh_all(locked.values())
    review_fixed_originals(recorded_by, originals)
    review_admin_entry(recorded_by, fix_ids)
    return Saved(operation_id, tuple(fix_ids))


def corrections_for(target: Event, changes: Restated) -> list[tuple[Event, Restated]]:
    """Each event to correct, with what changes on it.

    A quantity fix of a split, transfer or quarantine is paired: the other
    side gets the same quantity, so out still equals in (Q8).
    """
    if not changes.moves_units:
        return [(target, changes)]
    sides = list(Event.objects.filter(operation_id=target.operation_id).order_by("id"))
    is_paired = len(sides) == 2 and any(s.action in PAIRED_ACTIONS for s in sides)
    if not is_paired:
        return [(target, changes)]
    qty = changes.qty_out if changes.qty_out is not None else changes.qty_in
    return [
        (side, changes if side.pk == target.pk else same_quantity(side, qty))
        for side in sides
    ]


def same_quantity(side: Event, qty: int | None) -> Restated:
    """The other side of a paired fix: `qty` in its own direction."""
    if side.qty_out > 0:
        return Restated(qty_out=qty)
    return Restated(qty_in=qty)


def current_values(original: Event) -> Effective:
    """The original as it counts now: its newest correction applied."""
    effective = Event.objects.effective_events(original.batch_id)
    return next(event for event in effective if event.id == original.pk)


def restated_values(current: Effective, changes: Restated) -> dict[str, Any]:
    """Every correctable value for the Correction row: changed, or as it is now."""

    def keep(new: Any, now: Any) -> Any:
        return now if new is None else new

    return {
        "occurred_at": keep(changes.occurred_at, current.occurred_at),
        "qty_in": keep(changes.qty_in, current.qty_in),
        "qty_out": keep(changes.qty_out, current.qty_out),
        "counted_qty": keep(changes.counted_qty, current.counted_qty),
        "media_code_id": keep(changes.media_code, current.media_code),
        "stage_to_id": keep(changes.stage_to, current.stage_to),
    }


# -------------------------------------------------------------------- counts


def count_difference(count_event_id: int) -> int:
    """A count's unexplained gain or loss, worked out now (design §3.1)."""
    count = Event.objects.get(pk=count_event_id)
    differences = count_differences(Event.objects.effective_events(count.batch_id))
    if count_event_id not in differences:
        raise ValueError(f"Event {count_event_id} is not a count that still counts")
    return differences[count_event_id]
