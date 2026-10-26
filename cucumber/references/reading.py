"""Reading the lists: the one place later screens and rules ask (U0.9 design §3.2).

No permission check on reading: everyone signed in reads the lists (spec Q2),
and the page checks sign-in (U0.6).
"""

from dataclasses import dataclass

from cucumber.references.lists import ListName

NOT_BUILT = "U0.9 G3"


@dataclass(frozen=True)
class Item:
    code: str
    label: str  # a genus's name
    active: bool
    sort_order: int | None = None  # stages only


def active_items(name: ListName) -> tuple[Item, ...]:
    """A dropdown's items: active only, in the list's order (AC2, AC13). One query."""
    raise NotImplementedError(NOT_BUILT)


def item(name: ListName, code: str) -> Item | None:
    """One item by code, switched off or not (AC13: old records still read)."""
    raise NotImplementedError(NOT_BUILT)


def check_active(name: ListName, *codes: str) -> None:
    """For a write: every code is on the list and active, or Refused.

    `list_item_unknown`, then `list_item_inactive`. One query for all codes.
    """
    raise NotImplementedError(NOT_BUILT)


def stage_at_or_after(code: str, than: str) -> bool:
    """Is stage `code` at or after `than` in the sort order (AC2)?

    False for a stage with no place in the order (reserved).
    `list_item_unknown` for a code that is not a stage (G2 Q-C).
    """
    raise NotImplementedError(NOT_BUILT)
