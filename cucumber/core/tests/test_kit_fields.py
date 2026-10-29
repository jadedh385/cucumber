"""U0.10a AC8, AC10: the kit's dropdowns and its date (design §7.2, §7.3, §7.5).

A coded field is picked from the list, never typed. Each form reads its
lists once, when it is made, so a form class can be declared before the
lists change (and before the database is there). A pick is checked with
`check_active`, so it gets the list's own words, not Django's "Select a
valid choice". The date is one of eight days, in Bangkok, whatever
`TIME_ZONE` says.
"""

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
import time_machine
from django import forms
from django.test import override_settings
from pytest_django import DjangoAssertNumQueries

from cucumber.accounts.forms import DeactivateForm
from cucumber.core.dates import BANGKOK
from cucumber.core.kit import ListChoiceField, PickedDateField, ReasonChoiceField
from cucumber.core.refusals import MESSAGES
from cucumber.core.tests.rows import as_system, update
from cucumber.core.tests.trail import LEFT_COMPANY
from cucumber.references.lists import ListName
from cucumber.references.models import ReasonList
from cucumber.references.tests.support import switched_off

pytestmark = pytest.mark.django_db

CHOOSE = ("", "Choose…")
REQUIRED = "This field is required."
# Q2 a): `code · label` where staff use the code; the label alone elsewhere.
CHOICES = {
    ListName.STAGES: [
        ("S0", "S0 · Seed"),
        ("P0", "P0 · Sterilization / new species introduction"),
        ("P1", "P1 · Multiplication"),
        ("P2", "P2 · Growth"),
        ("A1", "A1 · Acclimatization (hardening off)"),
        ("P4", "P4 · Growth maturity (potted plants)"),
    ],
    ListName.MEDIA_CODES: [
        (code, code)  # labelled with its own code (U0.9 Q1): `M001`, not `M001 · M001`
        for code in ["G001", "G002", "M001", "M002", "M003", "M004", "R001"]
    ],
    ListName.GENERA: [
        ("ALC", "ALC · Alocasia"),
        ("HYA", "HYA · Hoya"),
        ("PHL", "PHL · Philodendron"),
    ],
    ListName.LOCATIONS: [("lab", "Lab"), ("nursery", "Nursery")],
    ListName.CONTAINER_TYPES: [
        ("flask_250ml", "250 ml flask"),
        ("pot_4in", "4-inch pot"),
        ("disposable_cup", "Disposable cup"),
        ("grow_bag", "Grow bag"),
        ("jar", "Jar"),
        ("magenta_box", "Magenta box"),
        ("tray", "Tray"),
    ],
    ListName.COUNT_UNITS: [("plant", "Plant"), ("vessel", "Vessel"), ("mg", "mg")],
}
ACTION_CHOICES_START = [("intake", "Intake"), ("subculture", "Subculture")]


def form_with(**fields: forms.Field) -> type[forms.Form]:
    """A form class holding `fields`, as a page declares one."""
    return type("PageForm", (forms.Form,), dict(fields))


def choices(form: forms.Form, name: str) -> list[tuple[Any, str]]:
    field = form.fields[name]
    assert isinstance(field, forms.ChoiceField)
    offered = cast("Iterable[tuple[Any, Any]]", field.choices)
    return [(value, str(label)) for value, label in offered]


def errors(form: forms.Form, name: str) -> list[str]:
    assert not form.is_valid()
    return [str(message) for message in form.errors[name]]


def error_codes(form: forms.Form, name: str) -> list[str | None]:
    assert not form.is_valid()
    return [error.code for error in form.errors.as_data()[name]]


# ------------------------------------------------------------ ListChoiceField
@pytest.mark.parametrize("name", list(CHOICES), ids=str)
def test_a_dropdown_offers_the_active_items_in_order_after_choose(
    name: ListName,
) -> None:
    form = form_with(pick=ListChoiceField(name))()

    assert choices(form, "pick") == [CHOOSE, *CHOICES[name]]


def test_event_actions_read_as_their_labels() -> None:
    form = form_with(pick=ListChoiceField(ListName.ACTIONS))()

    assert choices(form, "pick")[1:3] == ACTION_CHOICES_START
    assert len(choices(form, "pick")) == 1 + 14


def test_a_media_code_with_its_own_label_reads_code_and_label() -> None:
    with as_system():
        update("media_codes", "M001", {"label": "MS basal"}, "code")

    form = form_with(pick=ListChoiceField(ListName.MEDIA_CODES))()

    assert ("M001", "M001 · MS basal") in choices(form, "pick")


def test_a_switched_off_item_is_not_offered() -> None:
    switched_off(ListName.STAGES, "P2")

    form = form_with(pick=ListChoiceField(ListName.STAGES))()

    assert "P2" not in [value for value, _ in choices(form, "pick")]


def test_an_initial_code_leaves_out_choose() -> None:
    form = form_with(pick=ListChoiceField(ListName.STAGES, initial="P1"))()

    assert choices(form, "pick") == CHOICES[ListName.STAGES]


def test_making_the_field_reads_no_list(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """A page declares its form class at import, before any request."""
    with django_assert_num_queries(0):
        form_with(pick=ListChoiceField(ListName.STAGES))


def test_each_form_reads_each_dropdown_once(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    page_form = form_with(
        stage=ListChoiceField(ListName.STAGES),
        medium=ListChoiceField(ListName.MEDIA_CODES),
        unit=ListChoiceField(ListName.COUNT_UNITS),  # fixed: no query
    )

    with django_assert_num_queries(2):
        form = page_form()
        str(form)


def test_a_form_made_after_a_switch_off_leaves_the_item_out() -> None:
    """Choices are read when the form is made, not when its class was."""
    page_form = form_with(pick=ListChoiceField(ListName.MEDIA_CODES))
    switched_off(ListName.MEDIA_CODES, "M003")

    assert "M003" not in [value for value, _ in choices(page_form(), "pick")]


def test_an_active_pick_is_kept_as_its_code() -> None:
    form = form_with(pick=ListChoiceField(ListName.STAGES))({"pick": "P1"})

    assert form.is_valid()
    assert form.cleaned_data["pick"] == "P1"


def test_a_code_not_on_the_list_gets_the_lists_own_words() -> None:
    form = form_with(pick=ListChoiceField(ListName.MEDIA_CODES))({"pick": "M999"})

    assert errors(form, "pick") == [MESSAGES["list_item_unknown"]]
    assert error_codes(form, "pick") == ["list_item_unknown"]


def test_a_pick_switched_off_since_the_page_opened_says_so() -> None:
    page_form = form_with(pick=ListChoiceField(ListName.MEDIA_CODES))
    switched_off(ListName.MEDIA_CODES, "M003")

    form = page_form({"pick": "M003"})

    assert errors(form, "pick") == [MESSAGES["list_item_inactive"]]
    assert error_codes(form, "pick") == ["list_item_inactive"]


def test_a_fixed_list_pick_not_on_it_is_unknown() -> None:
    form = form_with(pick=ListChoiceField(ListName.COUNT_UNITS))({"pick": "kg"})

    assert errors(form, "pick") == [MESSAGES["list_item_unknown"]]


def test_no_pick_is_djangos_required_message() -> None:
    form = form_with(pick=ListChoiceField(ListName.STAGES))({"pick": ""})

    assert errors(form, "pick") == [REQUIRED]


def test_an_optional_dropdown_left_empty_is_kept_empty() -> None:
    form = form_with(pick=ListChoiceField(ListName.STAGES, required=False))(
        {"pick": ""}
    )

    assert form.is_valid()
    assert form.cleaned_data["pick"] == ""


def test_a_refused_form_shown_again_reads_no_list_again(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """Review M10: callable choices read the list a second time on render."""
    form = form_with(pick=ListChoiceField(ListName.MEDIA_CODES))({"pick": "M999"})
    assert not form.is_valid()

    with django_assert_num_queries(0):
        html = str(form)

    assert 'value="M001"' in html


# ---------------------------------------------------------- ReasonChoiceField
def test_a_reason_dropdown_offers_the_lists_reasons_by_label() -> None:
    form = form_with(reason=ReasonChoiceField(ReasonList.DEACTIVATE))()

    assert choices(form, "reason") == [
        ("", "Choose a reason"),
        (LEFT_COMPANY, "Left the company"),
        ("deactivate_on_leave", "On leave"),
        ("deactivate_security", "Security"),
        ("deactivate_other", "Other"),
    ]


def test_a_reason_dropdown_may_be_left_empty_for_the_service_to_refuse() -> None:
    """`require_reason` gives "Choose a reason." itself (review H3)."""
    form = form_with(reason=ReasonChoiceField(ReasonList.DEACTIVATE))({"reason": ""})

    assert form.is_valid()
    assert form.cleaned_data["reason"] == ""


@pytest.mark.parametrize("code", ["archive_no_longer_used", "made_up"])
def test_a_reason_dropdown_passes_any_code_on_to_the_service(code: str) -> None:
    """The service answers "That reason doesn't fit this change." (review H3)."""
    form = form_with(reason=ReasonChoiceField(ReasonList.DEACTIVATE))({"reason": code})

    assert form.is_valid()
    assert form.cleaned_data["reason"] == code


def test_a_reason_dropdown_reads_its_list_once_per_form(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    with django_assert_num_queries(0):
        page_form = form_with(reason=ReasonChoiceField(ReasonList.ARCHIVE))
    with django_assert_num_queries(1):
        str(page_form())


def test_the_deactivate_form_uses_the_reason_dropdown() -> None:
    field = DeactivateForm().fields["reason_code"]

    assert isinstance(field, ReasonChoiceField)
    assert field.required is False


# ------------------------------------------------------------ PickedDateField
MORNING = datetime(2026, 10, 28, 9, 30, tzinfo=BANGKOK)  # a Wednesday
EIGHT_DAYS = [
    ("2026-10-28", "Today · Wed 28 Oct"),
    ("2026-10-27", "Yesterday · Tue 27 Oct"),
    ("2026-10-26", "Mon 26 Oct"),
    ("2026-10-25", "Sun 25 Oct"),
    ("2026-10-24", "Sat 24 Oct"),
    ("2026-10-23", "Fri 23 Oct"),
    ("2026-10-22", "Thu 22 Oct"),
    ("2026-10-21", "Wed 21 Oct"),
]


def date_form(data: dict[str, str] | None = None) -> forms.Form:
    return form_with(day=PickedDateField())(data)


def option_weeks(html: str) -> dict[str, str]:
    """Each `<option>`'s value and its `data-week`."""
    tags = re.findall(r"<option\b[^>]*>", html)
    return {
        value.group(1): week.group(1)
        for tag in tags
        if (value := re.search(r'value="([^"]*)"', tag))
        and (week := re.search(r'data-week="([^"]*)"', tag))
    }


def test_the_date_offers_today_and_the_seven_days_before() -> None:
    with time_machine.travel(MORNING, tick=False):
        offered = choices(date_form(), "day")

    assert [(str(value), label) for value, label in offered] == EIGHT_DAYS


@override_settings(TIME_ZONE="UTC")
@pytest.mark.parametrize(
    ("moment", "today"),
    [
        (datetime(2026, 10, 28, 16, 59, 59, tzinfo=UTC), "2026-10-28"),
        (datetime(2026, 10, 28, 17, 0, 0, tzinfo=UTC), "2026-10-29"),
        (datetime(2026, 10, 27, 17, 0, 0, tzinfo=UTC), "2026-10-28"),
    ],
    ids=["23:59:59 Bangkok", "midnight Bangkok", "00:00 Bangkok, 17:00 UTC"],
)
def test_today_is_bangkoks_whatever_the_time_zone_setting(
    moment: datetime, today: str
) -> None:
    with time_machine.travel(moment, tick=False):
        offered = choices(date_form(), "day")

    assert str(offered[0][0]) == today


def test_the_days_are_worked_out_when_the_form_is_made() -> None:
    """A form class declared before midnight offers the new day after it."""
    with time_machine.travel(datetime(2026, 10, 28, 23, 59, tzinfo=BANGKOK)):
        page_form = form_with(day=PickedDateField())
    with time_machine.travel(datetime(2026, 10, 29, 0, 1, tzinfo=BANGKOK)):
        offered = choices(page_form(), "day")

    assert str(offered[0][0]) == "2026-10-29"


@pytest.mark.parametrize(("posted", "day"), [("2026-10-28", 28), ("2026-10-21", 21)])
def test_a_picked_day_is_kept_as_a_date(posted: str, day: int) -> None:
    with time_machine.travel(MORNING, tick=False):
        form = date_form({"day": posted})
        assert form.is_valid()

    assert form.cleaned_data["day"] == date(2026, 10, day)


def test_tomorrow_is_refused_as_in_the_future() -> None:
    with time_machine.travel(MORNING, tick=False):
        refused = errors(date_form({"day": "2026-10-29"}), "day")

    assert refused == [MESSAGES["event_not_in_future"]]


@pytest.mark.parametrize("posted", ["2026-10-20", "2025-10-28"])
def test_a_day_before_the_eight_is_refused_with_the_7_day_words(posted: str) -> None:
    with time_machine.travel(MORNING, tick=False):
        refused = errors(date_form({"day": posted}), "day")

    assert refused == [MESSAGES["event_within_7_days"]]


@pytest.mark.parametrize("posted", ["", "soon", "2026-13-01"])
def test_no_day_or_not_a_day_is_refused(posted: str) -> None:
    with time_machine.travel(MORNING, tick=False):
        assert not date_form({"day": posted}).is_valid()


@pytest.mark.parametrize("posted", ["20261028", "2026-W44-3"])
def test_a_day_not_written_as_offered_is_refused(posted: str) -> None:
    """Python reads these as 28 Oct too; only the offered spelling is a pick."""
    with time_machine.travel(MORNING, tick=False):
        assert error_codes(date_form({"day": posted}), "day") == ["invalid_choice"]


def test_an_optional_date_left_empty_is_kept_empty() -> None:
    with time_machine.travel(MORNING, tick=False):
        form = form_with(day=PickedDateField(required=False))({"day": ""})
        assert form.is_valid()

    assert form.cleaned_data["day"] == ""


def test_a_posted_day_that_is_not_a_date_shows_no_week() -> None:
    with time_machine.travel(MORNING, tick=False):
        form = date_form({"day": "soon"})

    assert form["day"].week == ""  # type: ignore[attr-defined]


def test_each_day_carries_its_week_for_the_page() -> None:
    """`date-week.js` copies it under the field; the script does no date maths."""
    with time_machine.travel(MORNING, tick=False):
        weeks = option_weeks(str(date_form()["day"]))

    assert weeks == {
        "2026-10-28": "2026-W44",
        "2026-10-27": "2026-W44",
        "2026-10-26": "2026-W44",
        "2026-10-25": "2026-W43",
        "2026-10-24": "2026-W43",
        "2026-10-23": "2026-W43",
        "2026-10-22": "2026-W43",
        "2026-10-21": "2026-W43",
    }


def test_the_weeks_cross_the_year_as_iso_weeks() -> None:
    with time_machine.travel(datetime(2027, 1, 4, 9, 0, tzinfo=BANGKOK), tick=False):
        weeks = option_weeks(str(date_form()["day"]))

    assert (weeks["2027-01-04"], weeks["2027-01-03"], weeks["2026-12-28"]) == (
        "2027-W01",
        "2026-W53",
        "2026-W53",
    )
