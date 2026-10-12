"""`manage.py check_projections`: does every batch match its events? (design §3.3)

Recalculates each batch's projection with the same function the event
services use and reports any batch whose stored numbers differ. It only
reports; it never changes a batch. Runs in CI and nightly in production.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Choices

from cucumber.batches.models import Batch, BatchStatus
from cucumber.events.models import Event
from cucumber.events.writing import projected_columns


def shown(value: Any) -> str:
    """A value as the report prints it: a choice by its stored text."""
    return repr(str(value) if isinstance(value, Choices) else value)


def differences(batch: Batch) -> list[str]:
    """Each stored column that differs from the events, stored value first.

    A batch counts as voided only when none of its events still count, so a
    status set to voided by hand is reported, not trusted.
    """
    effective = Event.objects.effective_events(batch.pk)
    is_voided = batch.status == BatchStatus.VOIDED and not effective
    expected = projected_columns(batch.origin, effective, is_voided)
    return [
        f"{column}: stored {shown(getattr(batch, column))}, events give {shown(value)}"
        for column, value in expected.items()
        if getattr(batch, column) != value
    ]


def differences_under_lock(batch_id: int) -> list[str]:
    """`differences`, re-read under the batch's lock.

    A save that was committing during the first read has finished by now, so
    it isn't reported as drift.
    """
    with transaction.atomic():
        batch = Batch.objects.select_for_update(no_key=True).get(pk=batch_id)
        return differences(batch)


class Command(BaseCommand):
    help = "Report batches whose live count, stage or open/closed differ from events."

    def handle(self, *args: Any, **options: Any) -> None:
        checked = 0
        drifted = 0
        for batch in Batch.objects.order_by("id").iterator():
            checked += 1
            found = differences(batch) and differences_under_lock(batch.pk)
            if found:
                drifted += 1
                self.stdout.write(f"Batch {batch.pk}: {'; '.join(found)}")
        if drifted:
            raise CommandError(
                f"{drifted} of {checked} batches differ from their events."
            )
        self.stdout.write(f"All {checked} batches match their events.")
