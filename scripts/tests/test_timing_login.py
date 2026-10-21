"""Tests for the 10× login timing script (U0.5 G5)."""

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db.models.functions import Now

from cucumber.accounts.models import LoginFailure
from cucumber.core.audit import SYSTEM_USERNAME
from scripts import timing_login
from scripts.timing_login import LoginScale

SMALL = LoginScale(
    accounts=6, devices=2, ended_sessions=7, recent_failures=9, old_failures=4
)


# ---------------------------------------------------------------- plain parts


def test_ten_times_scale_matches_the_g5_note() -> None:
    # About 10 staff today, each on up to 3 devices; the rest is generous.
    scale = LoginScale()

    assert (scale.accounts, scale.devices) == (100, 3)
    assert scale.live_sessions == 300
    assert (scale.ended_sessions, scale.recent_failures, scale.old_failures) == (
        3_000,
        5_000,
        5_000,
    )


def test_an_unexpected_answer_stops_the_run() -> None:
    with pytest.raises(SystemExit, match="Log in.*expected 302, got 200"):
        timing_login.expect("Log in", 200, 302)


# ------------------------------------------------------------------- the load


@pytest.mark.django_db
def test_load_makes_the_rows_the_scale_asks_for() -> None:
    timing_login.load(SMALL)

    # Every account but System, which migrations add (U0.7 design §5.2).
    staff = User.objects.exclude(username=SYSTEM_USERNAME)
    assert staff.count() == SMALL.accounts
    assert Session.objects.filter(expire_date__gt=Now()).count() == SMALL.live_sessions
    assert Session.objects.filter(expire_date__lt=Now()).count() == SMALL.ended_sessions
    assert LoginFailure.objects.count() == SMALL.recent_failures + SMALL.old_failures


@pytest.mark.django_db
def test_loaded_failures_never_lock_the_accounts_that_are_timed() -> None:
    timing_login.load(SMALL)

    emails = User.objects.values_list("username", flat=True)
    assert not LoginFailure.objects.filter(email_key__in=emails).exists()


# ---------------------------------------------------------------- the timings


@pytest.mark.django_db
def test_every_timing_runs_and_gets_the_expected_answer() -> None:
    timing_login.load(SMALL)

    rows = timing_login.measure(SMALL, runs=2)

    assert [label for label, _ in rows] == list(timing_login.LABELS)
    assert all(summary.median > 0 for _, summary in rows)


@pytest.mark.django_db
def test_the_first_login_clears_the_ended_sessions() -> None:
    timing_login.load(SMALL)

    timing_login.measure(SMALL, runs=1)

    assert not Session.objects.filter(expire_date__lt=Now()).exists()
