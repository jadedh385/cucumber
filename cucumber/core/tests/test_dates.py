"""U0.10a AC10: Bangkok dates and ISO weeks in one place (design §7.5, review L14).

`ENTRY_WINDOW_DAYS` moves here from `events/models.py`, which imports it; the
number in the database rule doesn't change, so there is no migration.
"""

import ast
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path

import pytest
import time_machine
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from cucumber.core import dates
from cucumber.core.dates import BANGKOK, ENTRY_WINDOW_DAYS, bangkok_today, iso_week
from cucumber.events import models as event_models

CODE = Path(settings.BASE_DIR) / "cucumber"
ZONE = "Asia/Bangkok"
# Where the zone's name may be written: here, and the Django setting.
ZONE_NAMED_IN = {Path("core/dates.py"), Path("settings.py")}


def source_files() -> list[Path]:
    """Every module under cucumber/, leaving out tests and migrations."""
    return [
        path
        for path in sorted(CODE.rglob("*.py"))
        if not {"tests", "migrations"} & set(path.relative_to(CODE).parts)
    ]


def strings_outside_docstrings(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


# ------------------------------------------------------------------ the zone
def test_bangkok_is_the_zone() -> None:
    assert BANGKOK.key == ZONE


def test_the_zone_is_named_in_one_place() -> None:
    """Four modules named it (review L14); they import `BANGKOK` now."""
    named = [
        f"{path.relative_to(CODE)}:{line}"
        for path in source_files()
        if path.relative_to(CODE) not in ZONE_NAMED_IN
        for line, value in strings_outside_docstrings(path)
        if value == ZONE
    ]

    assert named == []


@override_settings(TIME_ZONE="UTC")
@pytest.mark.parametrize(
    ("moment", "today"),
    [
        (datetime(2026, 10, 28, 16, 59, 59, tzinfo=UTC), date(2026, 10, 28)),
        (datetime(2026, 10, 28, 17, 0, 0, tzinfo=UTC), date(2026, 10, 29)),
        (datetime(2026, 12, 31, 17, 0, 0, tzinfo=UTC), date(2027, 1, 1)),
    ],
    ids=["23:59:59 Bangkok", "midnight Bangkok", "new year Bangkok"],
)
def test_today_is_bangkoks_whatever_the_setting(moment: datetime, today: date) -> None:
    with time_machine.travel(moment, tick=False):
        assert bangkok_today() == today


# ------------------------------------------------------------------ the week
@pytest.mark.parametrize(
    ("day", "week"),
    [
        (date(2026, 10, 28), "2026-W44"),
        (date(2026, 12, 28), "2026-W53"),  # 2026 has 53 weeks
        (date(2027, 1, 1), "2026-W53"),  # a Friday: still 2026's last week
        (date(2027, 1, 3), "2026-W53"),
        (date(2027, 1, 4), "2027-W01"),  # the first Monday of 2027's week 1
        (date(2026, 1, 1), "2026-W01"),
        (date(2026, 3, 2), "2026-W10"),  # two digits, zero-filled below 10
    ],
)
def test_the_week_is_the_iso_week(day: date, week: str) -> None:
    assert iso_week(day) == week


# ---------------------------------------------------------- the 7-day window
def test_the_window_is_seven_days() -> None:
    assert ENTRY_WINDOW_DAYS == 7


def test_events_import_the_window_from_here() -> None:
    """By the import, not the value: any two 7s are the same object."""
    tree = ast.parse((CODE / "events/models.py").read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == dates.__name__
        for alias in node.names
    }

    assert "ENTRY_WINDOW_DAYS" in imported
    assert event_models.ENTRY_WINDOW_DAYS == ENTRY_WINDOW_DAYS


def test_events_no_longer_set_the_window_themselves() -> None:
    tree = ast.parse((CODE / "events/models.py").read_text())
    assigned = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and any(
            isinstance(target, ast.Name) and target.id == "ENTRY_WINDOW_DAYS"
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
    ]

    assert assigned == []


@pytest.mark.django_db
def test_moving_it_needs_no_migration() -> None:
    """`makemigrations --check` exits 1 when a model differs from its migrations."""
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())
