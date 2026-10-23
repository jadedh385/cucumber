"""SKUs and batch numbers, issued under a row lock (U0.8 design §4).

Each runs inside the caller's transaction (and `audited()`, where the
caller writes audited tables). Lock order, as in `events/writing.py`:
genus or plants first, then batches by ascending `id`.
"""

from collections.abc import Collection, Mapping, Sequence

from django.contrib.auth.models import User


def issue_next_sku(plant_id: int, genus_code: str, assigned_by: User) -> str:
    """Add the genus's next SKU to the register, issued to the plant (AC10).

    Needs `PLANT_LIFECYCLE`. The genus row is locked, so two issues into the
    same genus take turns while other genera carry on. `PHL999` is followed
    by `PHL1000` (Q2).
    """
    raise NotImplementedError("U0.8 G3")


def lock_plants(plant_ids: Collection[int]) -> dict[int, int]:
    """Lock the plants in `id` order; each one's next free `plant_seq` (AC11)."""
    raise NotImplementedError("U0.8 G3")


def plant_seqs(next_seq: Mapping[int, int], plant_ids: Sequence[int]) -> list[int]:
    """Each new batch's `plant_seq`, given the new batches' plants in entry order.

    `next_seq` is what `lock_plants` returned (review M3).
    """
    raise NotImplementedError("U0.8 G3")
