"""Bangkok dates and ISO weeks, in one place (U0.10a §7.5, AC10).

The day is always Bangkok's, the zone the database rule `event_within_7_days`
hard-codes, whatever `TIME_ZONE` says. `events/models.py`, the guards and
the audit command import the zone and the window from here.
"""

from datetime import date
from zoneinfo import ZoneInfo

from django.utils import timezone

BANGKOK = ZoneInfo("Asia/Bangkok")
ENTRY_WINDOW_DAYS = 7  # Q5: how far back staff may date an entry


def bangkok_today() -> date:
    """Today's date in Bangkok."""
    return timezone.now().astimezone(BANGKOK).date()


def iso_week(day: date) -> str:
    """The ISO 8601 week of `day`: `2026-W44` (SOP §4: worked out, never stored)."""
    return day.strftime("%G-W%V")
