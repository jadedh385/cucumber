"""The projection: a batch's numbers worked out from its events (design §3.1).

One calculation, used by the event services and `check_projections`, so
they can't disagree. It works on plain values, not database rows: the
caller passes the batch's effective events (`Event.objects.effective_events`).

**The count wins** (architect review H2): the total is the latest count plus
the events after it; with no count, the sum of all events. Order is always
(`occurred_at`, `id`).
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime

COUNT = "count"
CLOSE = "close"
RELEASE = "release"
QUARANTINE_ORIGIN = "quarantine"


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


@dataclass(frozen=True)
class Step:
    """One event in date order, with the batch's total just before and after it."""

    event: Effective
    before: int
    after: int


def in_order(events: Sequence[Effective]) -> list[Effective]:
    """The events in (`occurred_at`, `id`) order."""
    return sorted(events, key=lambda event: (event.occurred_at, event.id))


def running_totals(events: Sequence[Effective]) -> Iterator[Step]:
    """Walk the events in order: a count sets the total, the rest add or take."""
    total = 0
    for event in in_order(events):
        before = total
        if event.action == COUNT and event.counted_qty is not None:
            total = event.counted_qty
        else:
            total += event.qty_in - event.qty_out
        yield Step(event, before, total)


def project(events: Sequence[Effective]) -> Projection:
    """The batch's projection from its effective events, in any order."""
    live_count = 0
    stage_code = None
    closed_at = None
    for step in running_totals(events):
        live_count = step.after
        if step.event.stage_to is not None:
            stage_code = step.event.stage_to
        if step.event.action == CLOSE:
            closed_at = step.event.occurred_at
    return Projection(
        live_count=live_count,
        stage_code=stage_code,
        is_closed=closed_at is not None,
        closed_at=closed_at,
    )


def count_differences(events: Sequence[Effective]) -> dict[int, int]:
    """Each count's difference: `counted_qty` minus the total just before it.

    Keyed by the count's event id. Never stored, so it stays right when an
    earlier event is added, voided or corrected later.
    """
    return {
        step.event.id: step.after - step.before
        for step in running_totals(events)
        if step.event.action == COUNT
    }


def goes_below_zero(events: Sequence[Effective]) -> bool:
    """True if the total is below zero at any point (design §3.1, rule 7).

    That covers an event's own date and every later point before the next
    count, which sets the total afresh.
    """
    return any(step.after < 0 for step in running_totals(events))


def is_quarantined(origin: str, events: Sequence[Effective]) -> bool:
    """A quarantine batch stays quarantined until a `release` (D-02)."""
    return origin == QUARANTINE_ORIGIN and not any(
        event.action == RELEASE for event in events
    )
