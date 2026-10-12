"""The health page: "ok" when Cucumber and its database are up, 503 if not."""

from typing import cast

import pytest
from django.db import OperationalError, connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test import Client

from cucumber.core import views
from cucumber.core.services import database_is_reachable


class UnreachableDatabase:
    """Stands in for a database whose server has gone away."""

    def cursor(self) -> None:
        raise OperationalError("connection refused")


@pytest.mark.django_db
def test_health_page_says_ok(client: Client) -> None:
    response = client.get("/health/")

    assert response.status_code == 200
    assert response.content == b"ok"
    assert response["Content-Type"].startswith("text/plain")


def test_health_page_returns_503_when_database_is_down(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "database_is_reachable", lambda database: False)

    response = client.get("/health/")

    assert response.status_code == 503
    assert response.content == b"database unavailable"


@pytest.mark.django_db
def test_health_page_answers_head_for_uptime_monitors(client: Client) -> None:
    assert client.head("/health/").status_code == 200


def test_health_page_refuses_changes(client: Client) -> None:
    assert client.post("/health/").status_code == 405


@pytest.mark.django_db
def test_database_is_reachable_with_a_working_database() -> None:
    assert database_is_reachable(connection) is True


def test_unreachable_database_is_reported_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = cast(BaseDatabaseWrapper, UnreachableDatabase())

    assert database_is_reachable(broken) is False
    assert "database unreachable" in caplog.text
