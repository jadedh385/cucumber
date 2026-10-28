"""The UI kit's Python side: field classes and the values pages hand to it (U0.10a §7).

Pages build `Table`, `Detail` and `Empty` from service data; the templates
only lay them out. The fields read their choices from `references.reading`
when the form is made, so they hold no list (U0.9 AC22). G2 stub: the fields
and `item_text` are built at G3.
"""

from dataclasses import dataclass
from typing import Any

from django import forms

from cucumber.references.lists import ListName
from cucumber.references.models import ReasonList
from cucumber.references.reading import Item


@dataclass(frozen=True)
class Empty:
    """What a list or page shows when it has nothing: a message and maybe a button."""

    message: str
    action_label: str = ""
    action_url: str = ""


@dataclass(frozen=True)
class Column:
    label: str
    is_main: bool = False


@dataclass(frozen=True)
class Row:
    cells: tuple[str, ...]
    href: str


@dataclass(frozen=True)
class Table:
    """One `<table>`; cards below `lg` (§7.6). No rows: `empty` instead."""

    columns: tuple[Column, ...]
    rows: tuple[Row, ...]
    empty: Empty


@dataclass(frozen=True)
class Fact:
    label: str
    value: str


@dataclass(frozen=True)
class Detail:
    """A title, an optional line under it, then the facts as a `<dl>` (§7.7)."""

    title: str
    facts: tuple[Fact, ...]
    line: str = ""


class ListChoiceField(forms.ChoiceField):
    """A coded field: picked from `active_items(name)`, never typed (AC8).

    Choices are read once, when the form is made; the first is "Choose…"
    (empty) unless the field has an initial code. A pick is checked with
    `check_active`, so it gets the list's own refusal words.
    """

    def __init__(self, name: ListName, **kwargs: Any) -> None:
        raise NotImplementedError("U0.10a G3")


class ReasonChoiceField(forms.ChoiceField):
    """A reason from one list, label only; "Choose a reason" first (§7.3).

    Not required, and any posted code is accepted: `require_reason` in the
    service decides, with its own words.
    """

    def __init__(self, applies_to: ReasonList, **kwargs: Any) -> None:
        raise NotImplementedError("U0.10a G3")


class PickedDateField(forms.TypedChoiceField):
    """Today and the seven days before, in Bangkok; cleans to a `date` (AC10)."""

    def __init__(self, **kwargs: Any) -> None:
        raise NotImplementedError("U0.10a G3")


def item_text(name: ListName, found: dict[str, Item] | Item | None, code: str) -> str:
    """How a record shows an item: `P3 · Transport (switched off)` (AC9).

    The label alone for a list that doesn't show codes (Q2); the code itself
    when no list holds it. `found` is `all_items(name)` or one `item(…)`.
    """
    raise NotImplementedError("U0.10a G3")
