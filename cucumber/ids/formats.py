"""Numbers into IDs: `PLT-0042`, `BAT-00117`, `EVT-01502`, `PHL005` (U0.8 design §2).

Padding is a minimum, never a cut (AC2). Every function takes plain values,
not model objects, so none of them runs a query. A number below 1 is a
`ValueError`: the database never issues 0.
"""

from django.db.models.expressions import Combinable
from django.db.models.functions import Length

GENUS_CODE_LENGTH = 3
PLANT_DIGITS = 4
BATCH_DIGITS = 5
EVENT_DIGITS = 5
SKU_DIGITS = 3  # the least; PHL1000 grows past it (Q2)
PLANT_SEQ_DIGITS = 3

# Three capitals, then exactly 3 digits (001–999) or 4 or more with no
# leading zero (1000 up), so each number has one spelling (§2, Q2).
SKU_PATTERN = r"^[A-Z]{3}(?!000)(?:[0-9]{3}|[1-9][0-9]{3,})$"
# A longer SKU is a bigger number; same length sorts as text (AC4a).
SKU_ORDER: tuple[str | Combinable, ...] = ("genus_id", Length("sku"), "sku")


def _padded(number: int, digits: int) -> str:
    """The number padded to at least `digits` digits; below 1 is a `ValueError`."""
    if number < 1:
        raise ValueError(f"an ID number starts at 1, not {number}")
    return f"{number:0{digits}d}"


def plant_id(number: int) -> str:
    """`PLT-` and the number padded to 4 digits: `PLT-0042`."""
    return f"PLT-{_padded(number, PLANT_DIGITS)}"


def batch_id(number: int) -> str:
    """`BAT-` and the number padded to 5 digits: `BAT-00117`."""
    return f"BAT-{_padded(number, BATCH_DIGITS)}"


def event_id(number: int) -> str:
    """`EVT-` and the number padded to 5 digits: `EVT-01502`."""
    return f"EVT-{_padded(number, EVENT_DIGITS)}"


def sku(genus_code: str, number: int) -> str:
    """The genus code and the number padded to 3 digits: `PHL005`, `PHL1000`."""
    return f"{genus_code}{_padded(number, SKU_DIGITS)}"


def plant_label(sku: str | None, plant_number: int) -> str:
    """The plant's SKU, or its `PLT-` id when it has none (AC3)."""
    return plant_id(plant_number) if sku is None else sku


def batch_short_name(sku: str | None, plant_number: int, plant_seq: int) -> str:
    """`plant_label`, `" · B"` and the batch number padded to 3: `PHL001 · B003`."""
    label = plant_label(sku, plant_number)
    return f"{label} · B{_padded(plant_seq, PLANT_SEQ_DIGITS)}"


def sku_number(sku: str) -> int:
    """The digits after the genus code: `sku_number("PHL1000") == 1000`."""
    return int(sku[GENUS_CODE_LENGTH:])
