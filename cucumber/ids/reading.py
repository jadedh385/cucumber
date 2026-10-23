"""Typed text back into what it names, without the database (U0.8 design §3.1).

`read` tidies the text (length cap, NFKC, dashes and dots, ASCII upper
case), then matches it as a plant, batch or event id, a batch short name,
or an SKU, in that order. Anything else is `None`; `read` never raises.
"""

from dataclasses import dataclass
from enum import StrEnum

LONGEST_TEXT = 64  # longer typed text is None at once (review L1)
BIGGEST_ID = 9_223_372_036_854_775_807  # bigint: plants, batches, events
BIGGEST_PLANT_SEQ = 2_147_483_647  # integer: batches.plant_seq


class Kind(StrEnum):
    PLANT = "plant"
    BATCH = "batch"
    EVENT = "event"
    SKU = "sku"
    BATCH_NAME = "batch_name"


@dataclass(frozen=True)
class Typed:
    """What a typed ID names. Only the parts its kind has are set.

    A plant, batch or event: `number`. An SKU: `genus_code` and
    `sku_number`. A batch short name: `plant_seq`, and either `genus_code`
    and `sku_number` (`PHL001 · B003`) or `number` (`PLT-0042 · B003`).
    """

    kind: Kind
    number: int | None = None
    genus_code: str | None = None
    sku_number: int | None = None
    plant_seq: int | None = None


def read(text: str) -> Typed | None:
    """What `text` names, or `None` when it isn't an ID (AC5–AC8)."""
    raise NotImplementedError("U0.8 G3")
