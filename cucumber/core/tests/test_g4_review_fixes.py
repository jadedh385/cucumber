"""U0.10a G4: the review findings fixed at G4 (design §23).

- A path with a newline can't split a log line (G3 finding 10).
- One `PRODUCTION` check and one `HX-Request` check (G3 finding 19).
- The Busy 503 says when to try again and is never stored (G3 finding 22).
- A class set on a widget is kept beside the kit's (G3 finding 8).
"""

import logging
from pathlib import Path

import pytest
from django import forms
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings

from cucumber.core import requests
from cucumber.core.busy import BUSY_RETRY_AFTER_SECONDS, busy_page
from cucumber.core.views import permission_denied

CUCUMBER = Path(__file__).resolve().parents[2]
# `%0A` is a newline once Django decodes the path.
FORGED_PATH = "/x%0Abusy limit=forged account=1"


def logged_messages(caplog: pytest.LogCaptureFixture, logger: str) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == logger]


# ------------------------------------------------- one line per log record
def test_a_newline_in_the_path_stays_inside_the_busy_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = RequestFactory().get(FORGED_PATH)
    assert "\n" in request.path

    with caplog.at_level(logging.WARNING, logger="cucumber.core.busy"):
        busy_page(request, "statement_timeout")

    [line] = logged_messages(caplog, "cucumber.core.busy")
    assert "\n" not in line
    assert line.endswith(r"path=/x\nbusy limit=forged account=1")


@pytest.mark.django_db
def test_a_newline_in_the_path_stays_inside_the_page_refused_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = RequestFactory().get(FORGED_PATH)
    request.user = AnonymousUser()

    with caplog.at_level(logging.INFO, logger="cucumber.core.views"):
        permission_denied(request, PermissionDenied())

    [line] = logged_messages(caplog, "cucumber.core.views")
    assert "\n" not in line
    assert line.endswith(r"path=/x\nbusy limit=forged account=1")


def test_a_path_with_no_control_character_is_logged_as_it_is() -> None:
    assert requests.loggable("/staff/12/ข้าว") == "/staff/12/ข้าว"


# ------------------------------------------- one check each, in one place
def test_an_htmx_request_is_one_with_hx_request_true() -> None:
    factory = RequestFactory()

    assert requests.is_htmx(factory.get("/", headers={"HX-Request": "true"}))
    assert not requests.is_htmx(factory.get("/", headers={"HX-Request": "false"}))
    assert not requests.is_htmx(factory.get("/"))


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("production", True), ("staging", False), ("local", False)],
)
def test_production_is_read_from_the_environment_setting(
    environment: str, expected: bool
) -> None:
    with override_settings(ENVIRONMENT=environment):
        assert requests.is_production() is expected


def test_the_htmx_and_production_checks_are_written_once() -> None:
    """Only `core/requests.py` reads the header or names production
    (settings.py lists the environments)."""
    app_code = [
        path
        for path in CUCUMBER.rglob("*.py")
        if "tests" not in path.parts and path.name != "settings.py"
    ]

    readers = {
        path.relative_to(CUCUMBER).as_posix()
        for path in app_code
        if '"HX-Request"' in path.read_text() or '"production"' in path.read_text()
    }

    assert readers == {"core/requests.py"}


# ------------------------------------------------------------ the Busy 503
def test_the_busy_page_says_when_to_try_again_and_is_never_stored() -> None:
    response = busy_page(RequestFactory().get("/"), "lock_timeout")

    assert response.status_code == 503
    assert response["Retry-After"] == str(BUSY_RETRY_AFTER_SECONDS)
    assert "no-store" in response["Cache-Control"]


# ------------------------------------------------- a widget's own class
class WidgetWithItsOwnClass(forms.Form):
    note = forms.CharField(widget=forms.TextInput(attrs={"class": "font-mono"}))


def test_a_class_set_on_the_widget_is_kept_beside_the_kit_s() -> None:
    html = str(WidgetWithItsOwnClass()["note"])

    assert 'class="font-mono input w-full"' in html
