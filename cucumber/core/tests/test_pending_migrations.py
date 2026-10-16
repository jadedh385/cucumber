"""AC12: `pending_migrations` tells the deploy how version and database differ.

It prints one line of JSON (U0.4a design §6.2), so the deploy command never
reads Django's human-readable output.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.db.migrations.recorder import MigrationRecorder

pytestmark = pytest.mark.django_db

Recorded = MigrationRecorder.Migration


def pending_migrations() -> dict[str, list[str]]:
    out = StringIO()
    call_command("pending_migrations", stdout=out)
    lines = out.getvalue().strip().splitlines()
    assert len(lines) == 1, out.getvalue()
    report = json.loads(lines[0])
    assert set(report) == {"pending", "unknown"}
    return {key: list(value) for key, value in report.items()}


def test_an_up_to_date_database_has_no_differences() -> None:
    assert pending_migrations() == {"pending": [], "unknown": []}


def test_a_migration_not_yet_run_is_pending() -> None:
    latest = Recorded.objects.filter(app="core").order_by("-name").first()
    assert latest is not None
    latest.delete()

    assert pending_migrations()["pending"] == [f"core.{latest.name}"]


def test_a_migration_this_version_does_not_have_is_unknown() -> None:
    Recorded.objects.create(app="core", name="0099_from_a_newer_version")

    report = pending_migrations()

    assert report["unknown"] == ["core.0099_from_a_newer_version"]
    assert report["pending"] == []


def test_a_migration_of_an_app_this_version_lacks_is_unknown() -> None:
    Recorded.objects.create(app="stockroom", name="0001_initial")

    assert pending_migrations()["unknown"] == ["stockroom.0001_initial"]
