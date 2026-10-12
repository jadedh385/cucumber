"""`manage.py check_projections`: does every batch match its events? (design §3.3)

Recalculates each batch's projection with the same function the event
services use and reports any batch whose stored numbers differ. It only
reports; it never changes a batch. Runs in CI and nightly in production.
"""

from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Report batches whose live count, stage or open/closed differ from events."

    def handle(self, *args: Any, **options: Any) -> None:
        raise NotImplementedError("U0.2b G3")
