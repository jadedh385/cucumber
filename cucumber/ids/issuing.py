"""SKUs and batch numbers, issued under a row lock (U0.8 design §4).

Each runs inside the caller's transaction (and `audited()`, where the
caller writes audited tables). Lock order, as in `events/writing.py`:
genus or plants first, then batches by ascending `id`.
"""

from collections.abc import Collection, Mapping, Sequence

from django.contrib.auth.models import User
from django.db.models import Max

from cucumber.accounts.permissions import Permission, require
from cucumber.batches.models import Batch
from cucumber.ids.formats import SKU_ORDER, sku, sku_number
from cucumber.plants.models import Plant, Sku
from cucumber.references.models import Genus


def issue_next_sku(plant_id: int, genus_code: str, assigned_by: User) -> str:
    """Add the genus's next SKU to the register, issued to the plant (AC10).

    Needs `PLANT_LIFECYCLE`. The genus row is locked, so two issues into the
    same genus take turns while other genera carry on. `PHL999` is followed
    by `PHL1000` (Q2).
    """
    require(assigned_by, Permission.PLANT_LIFECYCLE)
    list(Genus.objects.select_for_update(no_key=True).filter(pk=genus_code))
    highest = (
        Sku.objects.filter(genus_id=genus_code)
        .order_by(*SKU_ORDER)
        .values_list("sku", flat=True)
        .last()
    )
    issued = sku(genus_code, 1 if highest is None else sku_number(highest) + 1)
    Sku.objects.create(
        sku=issued, plant_id=plant_id, genus_id=genus_code, assigned_by=assigned_by
    )
    return issued


def lock_plants(plant_ids: Collection[int]) -> dict[int, int]:
    """Lock the plants in `id` order; each one's next free `plant_seq` (AC11)."""
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


def plant_seqs(next_seq: Mapping[int, int], plant_ids: Sequence[int]) -> list[int]:
    """Each new batch's `plant_seq`, given the new batches' plants in entry order.

    `next_seq` is what `lock_plants` returned (review M3).
    """
    taken = dict(next_seq)
    seqs = []
    for plant_id in plant_ids:
        seqs.append(taken[plant_id])
        taken[plant_id] += 1
    return seqs
