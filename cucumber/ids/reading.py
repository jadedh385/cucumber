"""Typed text back into what it names, without the database (U0.8 design §3.1).

`read` tidies the text (length cap, NFKC, dashes and dots, ASCII upper
case), then matches it as a plant, batch or event id, a batch short name,
or an SKU, in that order. Anything else is `None`; `read` never raises.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

LONGEST_TEXT = 64  # longer typed text is None at once (review L1)
BIGGEST_ID = 9_223_372_036_854_775_807  # bigint: plants, batches, events
BIGGEST_PLANT_SEQ = 2_147_483_647  # integer: batches.plant_seq

MIDDLE_DOT = "\u00b7"
# Dashes NFKC leaves alone (U+2010–2014, U+2212), and separator dots.
DASHES = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2212", "-"))
DOTS = str.maketrans(dict.fromkeys("\u2022\u2219\u22c5\u30fb", MIDDLE_DOT))
FULL_WIDTH_LETTERS = ("\uff21", "\uff5a")  # ＡＢＣ…ａｂｃ…: NFKC makes them ASCII
ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")

ID_TEXT = re.compile(r"(PLT|BAT|EVT)[\s-]*([0-9]+)", re.ASCII)
BATCH_NAME_TEXT = re.compile(
    r"(?:(PLT)[\s-]*([0-9]+)|([A-Z]{3})([0-9]+))[\s\u00b7-]*B([0-9]+)", re.ASCII
)
SKU_TEXT = re.compile(r"([A-Z]{3})([0-9]+)", re.ASCII)


class Kind(StrEnum):
    PLANT = "plant"
    BATCH = "batch"
    EVENT = "event"
    SKU = "sku"
    BATCH_NAME = "batch_name"


ID_KINDS = {"PLT": Kind.PLANT, "BAT": Kind.BATCH, "EVT": Kind.EVENT}


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


def tidy(text: str) -> str | None:
    """The text ready to match, or `None` when it can't be an ID (§3.1)."""
    if len(text) > LONGEST_TEXT or _has_foreign_letter(text):
        return None
    tidied = unicodedata.normalize("NFKC", text).translate(DASHES).translate(DOTS)
    tidied = tidied.strip().translate(ASCII_UPPER)
    # Only the middle dot may be left that isn't ASCII (e.g. `ı` is not an `I`).
    return tidied if tidied.replace(MIDDLE_DOT, "").isascii() else None


def _has_foreign_letter(text: str) -> bool:
    """A non-ASCII letter that isn't full width, before NFKC can fold it.

    NFKC alone would turn `ſ` into `s` and the Kelvin sign into `K`, so
    `alſ005` would read as `ALS005` (review L1).
    """
    low, high = FULL_WIDTH_LETTERS
    return any(c.isalpha() and not c.isascii() and not low <= c <= high for c in text)


def _fits(number: int, biggest: int) -> bool:
    return 1 <= number <= biggest


def _read_id(tidied: str) -> Typed | None:
    match = ID_TEXT.fullmatch(tidied)
    if match is None or not _fits(int(match[2]), BIGGEST_ID):
        return None
    return Typed(ID_KINDS[match[1]], number=int(match[2]))


def _read_batch_name(tidied: str) -> Typed | None:
    match = BATCH_NAME_TEXT.fullmatch(tidied)
    if match is None:
        return None
    plant_seq = int(match[5])
    if not _fits(plant_seq, BIGGEST_PLANT_SEQ):
        return None
    if match[1]:  # PLT-0042 · B3
        if not _fits(int(match[2]), BIGGEST_ID):
            return None
        return Typed(Kind.BATCH_NAME, number=int(match[2]), plant_seq=plant_seq)
    if int(match[4]) < 1:  # PHL001 · B3
        return None
    return Typed(
        Kind.BATCH_NAME,
        genus_code=match[3],
        sku_number=int(match[4]),
        plant_seq=plant_seq,
    )


def _read_sku(tidied: str) -> Typed | None:
    match = SKU_TEXT.fullmatch(tidied)
    if match is None or int(match[2]) < 1:
        return None
    return Typed(Kind.SKU, genus_code=match[1], sku_number=int(match[2]))


def read(text: str) -> Typed | None:
    """What `text` names, or `None` when it isn't an ID (AC5–AC8)."""
    tidied = tidy(text)
    if tidied is None:
        return None
    return _read_id(tidied) or _read_batch_name(tidied) or _read_sku(tidied)
