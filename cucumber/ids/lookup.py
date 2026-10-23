"""Typed text into the record it names (U0.8 design §3.3).

Voided and retired records are found too: an ID always points at its
record (S3). No permission check: reading needs only a signed-in account,
which the page checks (U0.6).
"""

from dataclasses import dataclass

from django.db.models import Model

from cucumber.ids.reading import Kind
from cucumber.plants.models import Plant


@dataclass(frozen=True)
class Found:
    """The record a typed ID names.

    `kind` is `plant`, `batch` or `event`. `former_sku` is the SKU typed
    when it is no longer the plant's current one ("PHL005 is now HYA004").
    """

    kind: Kind
    record: Model
    former_sku: str | None = None


def look_up(text: str) -> Found | None:
    """The plant, batch or event `text` names, or `None` (AC5–AC8)."""
    raise NotImplementedError("U0.8 G3")


def find_by_sku(sku: str) -> Plant | None:
    """The plant an SKU was issued to, current or former SKU alike (AC6)."""
    raise NotImplementedError("U0.8 G3")
