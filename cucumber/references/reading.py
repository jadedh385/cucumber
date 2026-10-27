"""Reading the lists: the one place later screens and rules ask (U0.9 design §3.2).

No permission check on reading: everyone signed in reads the lists (spec Q2),
and the page checks sign-in (U0.6). Not cached: the lists are a few rows each.
The fixed lists come from `fixed.py` and run no query.
"""

from dataclasses import dataclass
from typing import Any

from django.db import models

from cucumber.core.refusals import refuse
from cucumber.references.fixed import Action, CountUnit
from cucumber.references.lists import LIST_RULES, ListName, storable
from cucumber.references.models import (
    ContainerType,
    Genus,
    Location,
    MediaCode,
    Stage,
)

TABLES: dict[ListName, type[models.Model]] = {
    ListName.STAGES: Stage,
    ListName.MEDIA_CODES: MediaCode,
    ListName.LOCATIONS: Location,
    ListName.GENERA: Genus,
    ListName.CONTAINER_TYPES: ContainerType,
}
FIXED: dict[ListName, type[models.TextChoices]] = {
    ListName.ACTIONS: Action,
    ListName.COUNT_UNITS: CountUnit,
}
# The label column is `name` on genera only.
LABEL_COLUMN = {ListName.GENERA: "name"}


@dataclass(frozen=True)
class Item:
    code: str
    label: str  # a genus's name
    active: bool
    sort_order: int | None = None  # stages only


def fixed_items(name: ListName) -> tuple[Item, ...]:
    """A fixed list's values, in the order `fixed.py` gives them; all active."""
    return tuple(Item(value, label, True) for value, label in FIXED[name].choices)


def label_column(name: ListName) -> str:
    return LABEL_COLUMN.get(name, "label")


def manager(name: ListName) -> models.Manager[models.Model]:
    return TABLES[name]._default_manager


def rows(name: ListName) -> models.QuerySet[models.Model, tuple[Any, ...]]:
    """The list's rows as `Item` arguments: code, label, active (and order)."""
    order = ("sort_order",) if name is ListName.STAGES else ()
    return manager(name).values_list("code", label_column(name), "active", *order)


def order_column(name: ListName) -> str:
    """`sort_order`, `code` or the label column (design §3.1)."""
    order = LIST_RULES[name].order
    return label_column(name) if order == "label" else order


def active_items(name: ListName) -> tuple[Item, ...]:
    """A dropdown's items: active only, in the list's order (AC2, AC13). One query."""
    if name in FIXED:
        return fixed_items(name)
    found = rows(name).filter(active=True).order_by(order_column(name), "code")
    return tuple(Item(*row) for row in found)


def item(name: ListName, code: str) -> Item | None:
    """One item by code, switched off or not (AC13: old records still read).

    The code is matched in its exact letter case.
    """
    if name in FIXED:
        return next((found for found in fixed_items(name) if found.code == code), None)
    if not storable(code):
        return None  # no list holds it (G4 M1)
    row = rows(name).filter(code=code).first()
    return None if row is None else Item(*row)


def check_active(name: ListName, *codes: str) -> None:
    """For a write: every code is on the list and active, or Refused.

    `list_item_unknown`, then `list_item_inactive`, whatever order the codes
    are given in. One query for all codes; none for a fixed list.
    """
    if name in FIXED:
        active = {value: True for value in FIXED[name].values}
    else:
        found = manager(name).filter(code__in={c for c in codes if storable(c)})
        active = dict(found.values_list("code", "active"))
    if any(code not in active for code in codes):
        raise refuse("list_item_unknown")
    if not all(active[code] for code in codes):
        raise refuse("list_item_inactive")


def stage_at_or_after(code: str, than: str) -> bool:
    """Is stage `code` at or after `than` in the sort order (AC2)?

    A switched-off stage keeps its place. False for a stage with no place in
    the order (reserved). `list_item_unknown` for a code that is not a stage
    (G2 Q-C), so a typo in a constant fails loudly. One query.
    """
    stages = Stage.objects.filter(code__in={c for c in (code, than) if storable(c)})
    places = dict(stages.values_list("code", "sort_order"))
    if code not in places or than not in places:
        raise refuse("list_item_unknown")
    place, than_place = places[code], places[than]
    if place is None or than_place is None:
        return False
    return place >= than_place
