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

from django.contrib.auth.models import User


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


def save_operation(
    operation_id: uuid.UUID, recorded_by: User, entries: Sequence[NewEvent]
) -> Saved:
    """Save one user action: all its events, or none (design §3.3)."""
    raise NotImplementedError("U0.2b G3")


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
    raise NotImplementedError("U0.2b G3")


def close(
    operation_id: uuid.UUID,
    recorded_by: User,
    batch_id: int,
    occurred_at: datetime | None = None,
) -> Saved:
    """Close a batch at 0 with a `close` event (Q7)."""
    raise NotImplementedError("U0.2b G3")


def void(recorded_by: User, event_id: int, reason_code: str, note: str = "") -> Saved:
    """Void an event and every other event of its operation (Q8, design §3.1).

    One Void row per event, all in a new operation. Batches the operation
    created become `voided`. Refused if any of those batches has a later
    event; the refusal lists them.
    """
    raise NotImplementedError("U0.2b G3")


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
    raise NotImplementedError("U0.2b G3")


def count_difference(count_event_id: int) -> int:
    """A count's unexplained gain or loss, worked out now (design §3.1)."""
    raise NotImplementedError("U0.2b G3")
