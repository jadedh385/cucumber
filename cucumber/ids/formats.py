"""Numbers into IDs: `PLT-0042`, `BAT-00117`, `EVT-01502`, `PHL005` (U0.8 design §2).

Padding is a minimum, never a cut (AC2). Every function takes plain values,
not model objects, so none of them runs a query. A number below 1 is a
`ValueError`: the database never issues 0.
"""

from django.db.models.expressions import Combinable

# G2: still today's rule (exactly 3 digits) and today's text order. G3
# changes both to the design's values (§2, Q2): 3 or more digits with no
# needless zero, and ("genus_id", Length("sku"), "sku").
SKU_PATTERN = r"^[A-Z]{3}[0-9]{3}$"
SKU_ORDER: tuple[str | Combinable, ...] = ("genus_id", "sku")


def plant_id(number: int) -> str:
    """`PLT-` and the number padded to 4 digits: `PLT-0042`."""
    raise NotImplementedError("U0.8 G3")


def batch_id(number: int) -> str:
    """`BAT-` and the number padded to 5 digits: `BAT-00117`."""
    raise NotImplementedError("U0.8 G3")


def event_id(number: int) -> str:
    """`EVT-` and the number padded to 5 digits: `EVT-01502`."""
    raise NotImplementedError("U0.8 G3")


def sku(genus_code: str, number: int) -> str:
    """The genus code and the number padded to 3 digits: `PHL005`, `PHL1000`."""
    raise NotImplementedError("U0.8 G3")


def plant_label(sku: str | None, plant_number: int) -> str:
    """The plant's SKU, or its `PLT-` id when it has none (AC3)."""
    raise NotImplementedError("U0.8 G3")


def batch_short_name(sku: str | None, plant_number: int, plant_seq: int) -> str:
    """`plant_label`, `" · B"` and the batch number padded to 3: `PHL001 · B003`."""
    raise NotImplementedError("U0.8 G3")


def sku_number(sku: str) -> int:
    """The digits after the genus code: `sku_number("PHL1000") == 1000`."""
    raise NotImplementedError("U0.8 G3")
