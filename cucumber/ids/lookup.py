"""Typed text into the record it names (U0.8 design §3.3).

Voided and retired records are found too: an ID always points at its
record (S3). No permission check: reading needs only a signed-in account,
which the page checks (U0.6).
"""

from dataclasses import dataclass

from django.db.models import Model

from cucumber.batches.models import Batch
from cucumber.events.models import Event
from cucumber.ids.formats import sku as sku_text
from cucumber.ids.reading import Kind, Typed, read
from cucumber.plants.models import Plant, Sku

MODELS: dict[Kind, type[Plant] | type[Batch] | type[Event]] = {
    Kind.PLANT: Plant,
    Kind.BATCH: Batch,
    Kind.EVENT: Event,
}


@dataclass(frozen=True)
class Found:
    """The record a typed ID names.

    `kind` is `plant`, `batch` or `event`. `former_sku` is the SKU typed
    when it is no longer the plant's current one ("PHL005 is now HYA004").
    """

    kind: Kind
    record: Model
    former_sku: str | None = None


def _found_by_id(typed: Typed) -> Found | None:
    if typed.number is None:
        return None
    record = MODELS[typed.kind].objects.filter(pk=typed.number).first()
    return None if record is None else Found(typed.kind, record)


def _issued(genus_code: str, number: int) -> tuple[Plant, str] | None:
    """The plant a typed SKU was issued to, and the SKU as rebuilt (one query)."""
    issued = sku_text(genus_code, number)
    row = Sku.objects.select_related("plant").filter(pk=issued).first()
    return None if row is None else (row.plant, issued)


def _former(plant: Plant, issued: str) -> str | None:
    return None if plant.sku_id == issued else issued


def _found_by_sku(typed: Typed) -> Found | None:
    issued = _issued(typed.genus_code or "", typed.sku_number or 0)
    if issued is None:
        return None
    plant, text = issued
    return Found(Kind.PLANT, plant, _former(plant, text))


def _found_by_batch_name(typed: Typed) -> Found | None:
    former_sku = None
    plant_id = typed.number
    if typed.plant_seq is None:
        return None
    if plant_id is None:
        issued = _issued(typed.genus_code or "", typed.sku_number or 0)
        if issued is None:
            return None
        plant_id = issued[0].pk
        former_sku = _former(*issued)
    batch = Batch.objects.filter(plant_id=plant_id, plant_seq=typed.plant_seq).first()
    return None if batch is None else Found(Kind.BATCH, batch, former_sku)


def look_up(text: str) -> Found | None:
    """The plant, batch or event `text` names, or `None` (AC5–AC8)."""
    typed = read(text)
    if typed is None:
        return None
    if typed.kind is Kind.SKU:
        return _found_by_sku(typed)
    if typed.kind is Kind.BATCH_NAME:
        return _found_by_batch_name(typed)
    return _found_by_id(typed)


def find_by_sku(sku: str) -> Plant | None:
    """The plant an SKU was issued to, current or former SKU alike (AC6)."""
    issued = Sku.objects.select_related("plant").filter(pk=sku).first()
    return issued.plant if issued else None
