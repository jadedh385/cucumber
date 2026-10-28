"""U0.10a Q4 a), AC11: the Practice page, on local and staging only (§11.1, §13).

Stage, medium and container dropdowns and the date, as one HTMX form. Save
checks the answers and saves nothing. It is labelled `OWN_ACCOUNT`, so every
role and no role may open it. On production the view answers 404; the
address always exists, so a test can switch the environment.

A refused answer comes back 422 with the form's fragment: every answer
kept, the message under its field (§11.2).
"""

import re
from collections.abc import Iterator
from datetime import datetime

import pytest
import time_machine
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve

from cucumber.accounts.permissions import Permission, Role
from cucumber.accounts.tests.helpers import PASSWORD, Response, htmx_headers, text
from cucumber.core.dates import BANGKOK
from cucumber.core.refusals import MESSAGES
from cucumber.core.tests.stock import make_staff
from cucumber.references.lists import ListName
from cucumber.references.tests.support import switched_off

pytestmark = pytest.mark.django_db

PRACTICE = "/practice/"
CHECKED = "Checked. Nothing was saved (practice page)."
TODAY = "2026-10-28"
GOOD = {"stage": "P1", "medium": "M001", "container": "magenta_box", "date": TODAY}
FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"
WRITES = ("INSERT", "UPDATE", "DELETE")


@pytest.fixture(autouse=True)
def a_wednesday_morning() -> Iterator[None]:
    with (
        time_machine.travel(datetime(2026, 10, 28, 9, 30, tzinfo=BANGKOK)),
        override_settings(PASSWORD_HASHERS=[FAST_HASHER]),
    ):
        yield


def client_for(role: Role | None = Role.TECH) -> Client:
    client = Client()
    client.force_login(make_staff(f"person_{role or 'none'}", role, PASSWORD))
    return client


def send(client: Client, data: dict[str, str]) -> Response:
    response: Response = client.post(
        PRACTICE, data, headers=htmx_headers(f"http://testserver{PRACTICE}")
    )
    return response


def form_tag(html: str) -> str:
    start = html.index("<form")
    return html[start : html.index(">", start) + 1]


def selected(html: str, field: str) -> str | None:
    """The value of the selected option in the `<select name=field>`."""
    select = re.search(rf'<select\b[^>]*name="{field}".*?</select>', html, re.DOTALL)
    assert select, f"no select {field}"
    picked = re.search(r'<option\b[^>]*value="([^"]*)"[^>]*\bselected', select.group(0))
    return picked.group(1) if picked else None


def error_under(html: str, field: str) -> str:
    found = re.search(
        rf'<(\w+)\b[^>]*\bid="id_{field}_error"[^>]*>(.*?)</\1>', html, re.DOTALL
    )
    assert found, f"no error under {field}"
    return found.group(2)


# ------------------------------------------------------------------ the page
def test_the_page_is_labelled_with_the_own_account_row() -> None:
    view = resolve(PRACTICE).func

    assert getattr(view, "cucumber_permission", None) == Permission.OWN_ACCOUNT


@pytest.mark.parametrize("role", [*Role, None], ids=str)
def test_every_role_and_no_role_opens_it(role: Role | None) -> None:
    response = client_for(role).get(PRACTICE)

    assert response.status_code == 200
    assert "base.html" in [t.name for t in response.templates]


@override_settings(ENVIRONMENT="staging")
def test_staging_has_it() -> None:
    assert client_for().get(PRACTICE).status_code == 200


@override_settings(ENVIRONMENT="production")
@pytest.mark.parametrize("method", ["get", "post"])
def test_production_answers_page_not_found(method: str) -> None:
    response = getattr(client_for(Role.ADMIN), method)(PRACTICE, GOOD)

    assert response.status_code == 404


def test_the_form_has_the_four_dropdowns_from_the_kit() -> None:
    html = text(client_for().get(PRACTICE))

    for field in ("stage", "medium", "container", "date"):
        assert f'name="{field}"' in html, field
    assert "P1 · Multiplication" in html
    assert "Magenta box" in html
    assert "Today · Wed 28 Oct" in html


def test_the_form_is_the_kits_htmx_form() -> None:
    """One tap, one request: htmx drops a second send and disables Save (§4.2)."""
    response = client_for().get(PRACTICE)
    tag = form_tag(text(response))

    assert "kit/form.html" in [t.name for t in response.templates]
    assert f'hx-post="{PRACTICE}"' in tag
    assert 'hx-sync="this:drop"' in tag
    assert 'hx-disabled-elt="find button[type=submit]"' in tag
    assert 'hx-target="this"' in tag
    assert 'hx-swap="outerHTML"' in tag
    assert 'name="csrfmiddlewaretoken"' in text(response)


# ------------------------------------------------------------------ saving
def test_good_answers_are_checked_and_nothing_is_saved() -> None:
    client = client_for()

    with CaptureQueriesContext(connection) as queries:
        response = send(client, GOOD)

    assert response.status_code == 200
    assert CHECKED in text(response)
    writes = [
        query["sql"]
        for query in queries.captured_queries
        if query["sql"].lstrip().upper().startswith(WRITES)
        and "django_session" not in query["sql"]
    ]
    assert writes == []


def test_the_answer_is_the_forms_fragment_not_a_page() -> None:
    html = text(send(client_for(), GOOD))

    assert "<html" not in html
    assert html.lstrip().startswith("<form")


@pytest.mark.parametrize(
    ("medium", "rule"),
    [("M999", "list_item_unknown"), ("M003", "list_item_inactive")],
    ids=["not on the list", "switched off since the page opened"],
)
def test_a_refused_pick_comes_back_422_under_its_field(medium: str, rule: str) -> None:
    client = client_for()
    client.get(PRACTICE)
    switched_off(ListName.MEDIA_CODES, "M003")

    response = send(client, {**GOOD, "medium": medium})
    html = text(response)

    assert response.status_code == 422
    assert html.lstrip().startswith("<form")
    assert MESSAGES[rule] in error_under(html, "medium")
    assert CHECKED not in html


def test_a_refused_form_keeps_every_other_answer() -> None:
    html = text(send(client_for(), {**GOOD, "medium": "M999"}))

    assert selected(html, "stage") == "P1"
    assert selected(html, "container") == "magenta_box"
    assert selected(html, "date") == TODAY


def test_a_date_outside_the_eight_days_comes_back_422_under_the_date() -> None:
    response = send(client_for(), {**GOOD, "date": "2026-10-29"})

    assert response.status_code == 422
    assert MESSAGES["event_not_in_future"] in error_under(text(response), "date")
