"""The UI kit's Python side: field classes and the values pages hand to it (U0.10a §7).

Pages build `Table`, `Detail` and `Empty` from service data; the templates
only lay them out. The fields read their choices from `references.reading`
when the form is made, so they hold no list (U0.9 AC22). Django copies each
field when a form is made; the fields read their lists in that copy.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Self

from django import forms
from django.core.exceptions import ValidationError
from django.forms.renderers import TemplatesSetting
from django.utils.dateformat import format as format_date
from django.utils.translation import gettext_lazy as _

from cucumber.core.dates import ENTRY_WINDOW_DAYS, bangkok_today, iso_week
from cucumber.core.refusals import Refused, message_for
from cucumber.references.lists import LIST_RULES, ListName
from cucumber.references.models import ReasonList
from cucumber.references.reading import Item, active_items, active_reasons, check_active


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


# The kit's class for each widget, by Django's `widget_type` (§7.1).
WIDGET_CLASSES = {
    "text": "input w-full",
    "email": "input w-full",
    "password": "input w-full",
    "number": "input w-full",
    "textarea": "textarea w-full",
    "select": "select w-full",
    "weekselect": "select w-full",
    "radioselect": "radio",
    "checkbox": "checkbox",
}


class KitBoundField(forms.BoundField):
    """A field as the kit shows it: the daisyUI class on its widget."""

    def build_widget_attrs(
        self, attrs: dict[str, Any], widget: forms.Widget | None = None
    ) -> dict[str, Any]:
        built = super().build_widget_attrs(attrs, widget)
        kit_class = WIDGET_CLASSES.get(self.widget_type, "")
        # Django lays these over the widget's own attrs, so keep its class too.
        own = (widget or self.field.widget).attrs.get("class", "")
        given = f"{own} {built.get('class', '')}".strip()
        return (
            {**built, "class": f"{given} {kit_class}".strip()} if kit_class else built
        )


class KitRenderer(TemplatesSetting):
    """`FORM_RENDERER`: `{{ form }}` renders each field through `kit/field.html`."""

    form_template_name = "kit/form_fields.html"
    field_template_name = "kit/field.html"
    bound_field_class = KitBoundField


CHOOSE = ("", _("Choose…"))
CHOOSE_A_REASON = ("", _("Choose a reason"))
SWITCHED_OFF = _("(switched off)")
DAY_FORMAT = "D j M"  # Wed 28 Oct, in the page's language


class ListChoiceField(forms.ChoiceField):
    """A coded field: picked from `active_items(name)`, never typed (AC8).

    Choices are read once, when the form is made; the first is "Choose…"
    (empty) unless the field has an initial code. A pick is checked with
    `check_active`, so it gets the list's own refusal words.
    """

    def __init__(self, name: ListName, **kwargs: Any) -> None:
        super().__init__(choices=(), **kwargs)
        self.list_name = name

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        made = super().__deepcopy__(memo)
        name = made.list_name
        offered = [(each.code, choice_text(name, each)) for each in active_items(name)]
        made.choices = offered if made.initial else [CHOOSE, *offered]
        return made

    def validate(self, value: str) -> None:
        forms.Field.validate(self, value)
        if value in self.empty_values:
            return
        try:
            check_active(self.list_name, value)
        except Refused as refused:
            raise ValidationError(refused.message, code=refused.rule) from None


class ReasonChoiceField(forms.ChoiceField):
    """A reason from one list, label only; "Choose a reason" first (§7.3).

    Not required, and any posted code is accepted: `require_reason` in the
    service decides, with its own words.
    """

    def __init__(self, applies_to: ReasonList, **kwargs: Any) -> None:
        super().__init__(choices=(), required=False, **kwargs)
        self.applies_to = applies_to

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        made = super().__deepcopy__(memo)
        reasons = active_reasons(made.applies_to)
        made.choices = [CHOOSE_A_REASON, *((each.code, each.label) for each in reasons)]
        return made

    def validate(self, value: str) -> None:
        """Any code: the service refuses one that doesn't fit."""


class WeekSelect(forms.Select):
    """Each day's `<option>` carries its ISO week for `date-week.js` (§7.5)."""

    def create_option(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        option = super().create_option(*args, **kwargs)
        option["attrs"]["data-week"] = iso_week(date.fromisoformat(option["value"]))
        return option


class DateBoundField(KitBoundField):
    @property
    def week(self) -> str:
        """The week shown under the field before `date-week.js` runs (§7.5)."""
        picked = self.value() or bangkok_today().isoformat()  # the first day
        try:
            return iso_week(date.fromisoformat(str(picked)))
        except ValueError:
            return ""


class PickedDateField(forms.TypedChoiceField):
    """Today and the seven days before, in Bangkok; cleans to a `date` (AC10)."""

    widget = WeekSelect
    bound_field_class = DateBoundField

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(choices=(), coerce=date.fromisoformat, **kwargs)

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        made = super().__deepcopy__(memo)
        made.choices = eight_days(bangkok_today())
        return made

    def validate(self, value: str) -> None:
        forms.Field.validate(self, value)
        if value in self.empty_values:
            return
        try:
            day = date.fromisoformat(value)
            if day.isoformat() != value:  # 20261028 or 2026-W44-3: not a pick
                raise ValueError(value)
        except ValueError:
            raise ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
                params={"value": value},
            ) from None
        today = bangkok_today()
        if day > today:
            raise ValidationError(message_for("event_not_in_future"), code="future")
        if day < today - timedelta(days=ENTRY_WINDOW_DAYS):
            raise ValidationError(message_for("event_within_7_days"), code="too_old")


def eight_days(today: date) -> list[tuple[str, str]]:
    """`("2026-10-28", "Today · Wed 28 Oct")`, then back to seven days before."""
    days = [today - timedelta(days=back) for back in range(ENTRY_WINDOW_DAYS + 1)]
    names = {0: _("Today"), 1: _("Yesterday")}
    return [
        (day.isoformat(), day_text(names.get(back), day))
        for back, day in enumerate(days)
    ]


def day_text(name: Any, day: date) -> str:
    shown = format_date(day, DAY_FORMAT)
    return f"{name} · {shown}" if name else shown


def choice_text(name: ListName, found: Item) -> str:
    """`P1 · Multiplication` where staff use codes (Q2); else the label.

    A label equal to its code reads as the code: `M001`, not `M001 · M001`.
    """
    if not LIST_RULES[name].shows_code or found.label == found.code:
        return found.label
    return f"{found.code} · {found.label}"


def item_text(name: ListName, found: dict[str, Item] | Item | None, code: str) -> str:
    """How a record shows an item: `P3 · Transport (switched off)` (AC9).

    The label alone for a list that doesn't show codes (Q2); the code itself
    when no list holds it. `found` is `all_items(name)` or one `item(…)`.
    """
    held = found.get(code) if isinstance(found, dict) else found
    if held is None or held.code != code:
        return code
    text = choice_text(name, held)
    return text if held.active else f"{text} {SWITCHED_OFF}"
