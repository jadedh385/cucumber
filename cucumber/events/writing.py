"""How every event save writes: locks, rows and the projection (design §3.3, §3.4).

The event services in `services.py` call these inside one transaction.
Lock order, always: plants first (when a `plant_seq` is allocated), then
batches by ascending `id`. Locks are `FOR NO KEY UPDATE`, so they don't
block the foreign-key checks of event inserts on the same batch.
"""

import uuid
from collections.abc import Collection, Iterable
from datetime import datetime
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Max

from cucumber.batches.models import Batch, BatchStatus
from cucumber.core.refusals import refuse
from cucumber.events.models import Event, Operation
from cucumber.events.projection import (
    Effective,
    goes_below_zero,
    is_quarantined,
    project,
)
from cucumber.plants.models import Plant
from cucumber.references.models import Reason


def start_operation(operation_id: uuid.UUID, recorded_by: User) -> None:
    """The save's first write. The same id again stops here (`operations_pkey`)."""
    Operation.objects.create(id=operation_id, recorded_by=recorded_by)


def lock_plants(plant_ids: Collection[int]) -> dict[int, int]:
    """Lock the plants and return each one's next free `plant_seq` (design §2.3)."""
    if not plant_ids:
        return {}
    locked = Plant.objects.select_for_update(no_key=True).filter(pk__in=plant_ids)
    list(locked.order_by("id").values_list("id", flat=True))
    highest = dict(
        Batch.objects.filter(plant_id__in=plant_ids)
        .values("plant_id")
        .annotate(top=Max("plant_seq"))
        .values_list("plant_id", "top")
    )
    return {plant_id: highest.get(plant_id, 0) + 1 for plant_id in plant_ids}


def lock_batches(batch_ids: Collection[int]) -> dict[int, Batch]:
    """Lock the batches in ascending `id` order and return them by id."""
    locked = (
        Batch.objects.select_for_update(no_key=True)
        .filter(pk__in=batch_ids)
        .order_by("id")
    )
    batches = {batch.pk: batch for batch in locked}
    if len(batches) != len(set(batch_ids)):
        raise refuse("batch_not_found")
    return batches


def check_reason(action: str, reason_code: str | None) -> None:
    """The reason must come from the action's own list (design §3).

    An unknown code is left to the database's foreign key.
    """
    if reason_code is None:
        return
    applies_to = (
        Reason.objects.filter(pk=reason_code)
        .values_list("applies_to", flat=True)
        .first()
    )
    if applies_to is not None and applies_to != action:
        raise refuse("event_reason_matches_action")


def insert_event(
    operation_id: uuid.UUID,
    recorded_by: User,
    batch_id: int,
    action: str,
    occurred_at: datetime,
    **values: Any,
) -> int:
    """Insert one event; `recorded_by` is always the person saving it.

    A negative quantity is refused here, by the database's own rule name: the
    database checks each action's shape first (rules run in name order), which
    would give staff the Internal message instead (U0.2a G5).
    """
    if (values.get("qty_in") or 0) < 0 or (values.get("qty_out") or 0) < 0:
        raise refuse("event_qty_not_negative")
    event = Event.objects.create(
        operation_id=operation_id,
        recorded_by=recorded_by,
        batch_id=batch_id,
        action=action,
        occurred_at=occurred_at,
        **values,
    )
    return int(event.pk)


def projected_columns(
    origin: str, effective: list[Effective], is_voided: bool
) -> dict[str, Any]:
    """The `batches` columns the projection sets, by model field name.

    A voided batch keeps its stage and status: its events are all voided,
    and a Lab batch must keep a stage. `check_projections` compares these.
    """
    projection = project(effective)
    columns: dict[str, Any] = {
        "live_count": projection.live_count,
        "quarantined": is_quarantined(origin, effective),
    }
    if is_voided:
        return columns
    status = BatchStatus.CLOSED if projection.is_closed else BatchStatus.OPEN
    return {
        **columns,
        "stage_id": projection.stage_code,
        "status": status,
        "closed_at": projection.closed_at,
    }


def refresh(batch: Batch, voided_at: datetime | None = None) -> None:
    """Recalculate the batch's projection from its effective events.

    Refused if the total goes below zero at any point (rule 7). With
    `voided_at`, the batch becomes voided too (Q8).
    """
    effective = Event.objects.effective_events(batch.pk)
    if goes_below_zero(effective):
        raise refuse("batch_count_not_negative")
    is_voided = voided_at is not None or batch.status == BatchStatus.VOIDED
    columns = projected_columns(batch.origin, effective, is_voided)
    if voided_at is not None:
        columns = {**columns, "status": BatchStatus.VOIDED, "voided_at": voided_at}
    Batch.objects.filter(pk=batch.pk).update(**columns)


def refresh_all(
    batches: Iterable[Batch],
    voided_ids: Collection[int] = (),
    voided_at: datetime | None = None,
) -> None:
    """Refresh each batch; those in `voided_ids` become voided at `voided_at`."""
    for batch in sorted(batches, key=lambda batch: batch.pk):
        refresh(batch, voided_at if batch.pk in voided_ids else None)
