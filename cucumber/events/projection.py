"""The projection: a batch's numbers worked out from its events (design §3.1).

One calculation, used by the event services and `check_projections`, so
they can't disagree. It works on plain values, not database rows: the
caller passes the batch's effective events (`Event.objects.effective_events`).

**The count wins** (architect review H2): the total is the latest count plus
the events after it; with no count, the sum of all events. Order is always
(`occurred_at`, `id`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Effective:
    """An event as it counts now: not voided, its newest correction applied.

    `id` and `action` are the original event's; the values (date included)
    are the newest non-voided correction's, if there is one.
    """

    id: int
    action: str
    occurred_at: datetime
    qty_in: int = 0
    qty_out: int = 0
    counted_qty: int | None = None
    media_code: str | None = None
    stage_to: str | None = None


@dataclass(frozen=True)
class Projection:
    """What `batches` holds for one batch: `live_count`, `stage_code`, open/closed."""

    live_count: int
    stage_code: str | None
    is_closed: bool
    closed_at: datetime | None


def project(events: Sequence[Effective]) -> Projection:
    """The batch's projection from its effective events, in any order."""
    raise NotImplementedError("U0.2b G3")


def count_differences(events: Sequence[Effective]) -> dict[int, int]:
    """Each count's difference: `counted_qty` minus the total just before it.

    Keyed by the count's event id. Never stored, so it stays right when an
    earlier event is added, voided or corrected later.
    """
    raise NotImplementedError("U0.2b G3")
