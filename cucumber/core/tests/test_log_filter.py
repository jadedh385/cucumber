"""U0.10a AC17: one log line per refusal, no traceback for a 4xx (§9.2).

First the filter as a unit, one test per row of §9.2's table (records in,
records out). Then end to end through the test client, with `logged`: a
handler carrying the same filter on the `django` logger, which doesn't
propagate to `caplog` (architect H4).
"""

import logging
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory, override_settings

from cucumber.accounts.middleware import RoleRequired
from cucumber.accounts.permissions import Permission, allowed_for
from cucumber.accounts.tests.helpers import PASSWORD, signed_in
from cucumber.core import busy
from cucumber.core.logs import OneLinePerRefusal
from cucumber.core.refusals import PageRefused
from cucumber.core.tests import urls_busy
from cucumber.core.tests.logs import Line, Logged, has_traceback
from cucumber.core.tests.stock import make_staff

FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"


def record(
    logger: str,
    status: int | None,
    *,
    with_traceback: bool = False,
    request: HttpRequest | None = None,
) -> logging.LogRecord:
    """A record as Django's `log_response` makes one (`status_code`, `request`)."""
    exc_info = None
    if with_traceback:
        try:
            raise RuntimeError("raised in a view")
        except RuntimeError:
            exc_info = sys.exc_info()
    made = logging.LogRecord(
        logger, logging.WARNING, __file__, 1, "%s: %s", ("Gone", "/x/"), exc_info
    )
    extra: dict[str, object] = {"request": request or RequestFactory().get("/x/")}
    if status is not None:
        extra["status_code"] = status
    made.__dict__.update(extra)
    return made


def after_filter(made: logging.LogRecord) -> logging.LogRecord | None:
    """What the console handler writes: None when dropped."""
    kept = OneLinePerRefusal().filter(made)
    if not kept:
        return None
    return kept if isinstance(kept, logging.LogRecord) else made


# ------------------------------------------------------- the filter, unit
def test_djangos_403_line_is_dropped() -> None:
    """Cucumber's own `page refused` line covers every 403."""
    assert after_filter(record("django.request", 403, with_traceback=True)) is None


@pytest.mark.parametrize("status", [400, 404, 405, 410])
def test_another_4xx_is_kept_without_its_traceback(status: int) -> None:
    made = record("django.request", status, with_traceback=True)
    made.exc_text = "Traceback (cached by an earlier handler)"

    kept = after_filter(made)

    assert kept is not None
    assert not has_traceback(kept)
    assert kept.getMessage() == "Gone: /x/"


def test_the_csrf_line_is_kept_as_one_line() -> None:
    """Django's `django.security.csrf` line is the stale page's one line."""
    kept = after_filter(record("django.security.csrf", 403, with_traceback=True))

    assert kept is not None
    assert not has_traceback(kept)


@pytest.mark.parametrize("status", [503, 500])
def test_a_line_for_a_request_answered_busy_is_dropped(status: int) -> None:
    """503 from the middleware; 500's line when the 500 handler fell back."""
    request = RequestFactory().get("/x/")
    busy.mark_busy(request, "statement_timeout")

    made = record("django.request", status, with_traceback=True, request=request)

    assert after_filter(made) is None


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_5xx_keeps_its_traceback(status: int) -> None:
    kept = after_filter(record("django.request", status, with_traceback=True))

    assert kept is not None
    assert kept.exc_info is not None


@pytest.mark.parametrize("name", ["cucumber.accounts", "cucumber.core.busy", "root"])
def test_records_that_are_not_djangos_are_left_as_they_are(name: str) -> None:
    made = record(name, 403, with_traceback=True)

    assert after_filter(made) is made


@pytest.mark.parametrize("status", [200, 302])
def test_a_line_for_an_answer_that_is_no_refusal_is_left_as_it_is(
    status: int,
) -> None:
    """`runserver` logs every answer through `django.server` (G3)."""
    made = record("django.server", status, with_traceback=True)

    assert after_filter(made) is made


def test_a_record_with_no_status_is_left_as_it_is() -> None:
    made = record("django.db.backends", None, with_traceback=True)

    assert after_filter(made) is made


def test_the_original_record_is_not_changed() -> None:
    """Another handler may still want it whole: the filter returns a copy."""
    made = record("django.request", 404, with_traceback=True)

    after_filter(made)

    assert made.exc_info is not None


# ------------------------------------------------------- where it is set
def test_the_console_handler_carries_the_filter() -> None:
    logging_config: dict[str, Any] = settings.LOGGING
    filters = logging_config.get("filters", {})
    console = logging_config["handlers"]["console"]

    assert [filters[name]["()"] for name in console.get("filters", [])] == [
        "cucumber.core.logs.OneLinePerRefusal"
    ]


def test_django_and_cucumber_lines_share_that_handler() -> None:
    logging_config: dict[str, Any] = settings.LOGGING

    assert logging_config["loggers"]["django"]["handlers"] == ["console"]
    assert logging_config["root"]["handlers"] == ["console"]


def test_the_running_console_handler_has_the_filter() -> None:
    handlers = logging.getLogger("django").handlers

    assert any(
        isinstance(each, OneLinePerRefusal)
        for handler in handlers
        for each in handler.filters
    )


# -------------------------------------------------- end to end, per refusal
@pytest.fixture
def quick() -> Iterator[None]:
    with override_settings(
        ROOT_URLCONF=urls_busy.__name__, PASSWORD_HASHERS=[FAST_HASHER]
    ):
        yield


@pytest.fixture
def gene(db: None, quick: None) -> User:
    return make_staff("gene", "tech", PASSWORD)


@pytest.fixture
def gene_client(gene: User) -> Client:
    """Gene, signed in; a 500 comes back as the page, not re-raised."""
    client = signed_in(gene)
    client.raise_request_exception = False
    return client


def test_a_role_refusal_is_one_page_refused_line(
    gene: User, gene_client: Client, logged: Logged
) -> None:
    response = gene_client.get("/staff/")

    assert response.status_code == 403
    assert logged.cucumber() == [
        f"page refused account={gene.pk} permission=manage_users"
    ]
    assert logged.django() == []


def test_a_service_refusal_is_one_page_refused_line_with_its_rule(
    gene: User, gene_client: Client, logged: Logged
) -> None:
    response = gene_client.get(urls_busy.SERVICE_REFUSED)

    assert response.status_code == 403
    assert logged.cucumber() == [
        f"page refused account={gene.pk} rule=account_not_active"
        f" path={urls_busy.SERVICE_REFUSED}"
    ]
    assert logged.django() == []


def test_a_plain_refusal_is_one_line_with_no_rule(
    gene: User, gene_client: Client, logged: Logged
) -> None:
    response = gene_client.get(urls_busy.PLAIN_REFUSED)

    assert response.status_code == 403
    assert logged.cucumber() == [
        f"page refused account={gene.pk} rule=none path={urls_busy.PLAIN_REFUSED}"
    ]
    assert logged.django() == []


@override_settings(ROOT_URLCONF="cucumber.accounts.tests.urls_without_row")
def test_a_page_with_no_row_is_one_line(gene_client: Client, logged: Logged) -> None:
    response = gene_client.get("/test-only/no-row/")

    assert response.status_code == 403
    assert len(logged.lines()) == 1
    assert logged.cucumber()[0].startswith("page has no permission view=")


def test_a_missing_page_is_one_line_without_a_traceback(
    gene_client: Client, logged: Logged
) -> None:
    response = gene_client.get("/no-such-page/")

    assert response.status_code == 404
    assert logged.lines() == [
        Line("django.request", "Not Found: /no-such-page/", False)
    ]
    assert "Traceback" not in logged.text()


def test_a_wrong_method_is_one_line_without_a_traceback(
    gene_client: Client, logged: Logged
) -> None:
    response = gene_client.post("/")

    assert response.status_code == 405
    lines = logged.lines()
    assert len(lines) == 1
    assert lines[0].message.startswith("Method Not Allowed (POST): /")
    assert not lines[0].has_traceback
    assert "Traceback" not in logged.text()


def test_a_500_keeps_its_traceback(gene_client: Client, logged: Logged) -> None:
    response = gene_client.get(urls_busy.BROKEN)

    assert response.status_code == 500
    assert [line.has_traceback for line in logged.django()] == [True]
    assert urls_busy.BROKEN_MESSAGE in logged.text()


# ------------------------------------- RoleRequired: one line, then PageRefused
def no_page(request: HttpRequest) -> HttpResponse:
    return HttpResponse()


@allowed_for(Permission.MANAGE_USERS)
def staff_page(request: HttpRequest) -> HttpResponse:
    return HttpResponse()


def page_without_a_row(request: HttpRequest) -> HttpResponse:
    return HttpResponse()


def test_role_required_raises_page_refused_after_its_line(gene: User) -> None:
    request = RequestFactory().get("/staff/")
    request.user = gene

    with pytest.raises(PageRefused):
        RoleRequired(no_page).process_view(request, staff_page, (), {})


def test_a_page_with_no_row_raises_page_refused(gene: User) -> None:
    request = RequestFactory().get("/x/")
    request.user = gene

    with pytest.raises(PageRefused):
        RoleRequired(no_page).process_view(request, page_without_a_row, (), {})


def test_page_refused_is_still_a_403() -> None:
    assert issubclass(PageRefused, PermissionDenied)
