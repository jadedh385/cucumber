"""`manage.py check_projections`: does every batch match its events? (design §3.3)

Recalculates each batch's projection with the same function the event
services use and reports any batch whose stored numbers differ. It only
reports; it never changes a batch. Runs in CI and nightly in production.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from cucumber.batches.models import Batch, BatchStatus
from cucumber.events.models import Event
from cucumber.events.writing import projected_columns


def differences(batch: Batch) -> list[str]:
    """Each stored column that differs from the events, stored value first."""
    effective = Event.objects.effective_events(batch.pk)
    is_voided = batch.status == BatchStatus.VOIDED
    expected = projected_columns(batch.origin, effective, is_voided)
    return [
        f"{column}: stored {getattr(batch, column)!r}, events give {value!r}"
        for column, value in expected.items()
        if getattr(batch, column) != value
    ]


class Command(BaseCommand):
    help = "Report batches whose live count, stage or open/closed differ from events."

    def handle(self, *args: Any, **options: Any) -> None:
        checked = 0
        drifted = 0
        for batch in Batch.objects.order_by("id").iterator():
            checked += 1
            found = differences(batch)
            if found:
                drifted += 1
                self.stdout.write(f"Batch {batch.pk}: {'; '.join(found)}")
        if drifted:
            raise CommandError(
                f"{drifted} of {checked} batches differ from their events."
            )
        self.stdout.write(f"All {checked} batches match their events.")
