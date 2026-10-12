"""U0.2b: `manage.py check_projections` (design §3.3).

It recalculates every batch from its events with the services' own
projection function and reports any batch that differs. It never fixes one.
Drift is made here with plain SQL, the way a bug or a manual edit would.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from cucumber.core.tests.rows import db_now, update
from cucumber.core.tests.stock import (
    batch_of,
    intake_into_new_batch,
    live_count,
    log,
    new_lab_batch,
)

pytestmark = pytest.mark.django_db


def check() -> str:
    """Run the command; return what it printed."""
    output = StringIO()
    call_command("check_projections", stdout=output)
    return output.getvalue()


def check_finds_drift() -> str:
    """Run the command, expecting it to fail; return its output and error."""
    output = StringIO()
    with pytest.raises(CommandError) as caught:
        call_command("check_projections", stdout=output)
    return f"{output.getvalue()}\n{caught.value}"


def test_when_every_batch_matches_it_says_so(plant: int, tech: User) -> None:
    intake_into_new_batch(tech, plant, 5)
    new_lab_batch(tech, plant, 7)
    assert "All 2 batches match their events." in check()


def test_a_wrong_live_count_is_reported_and_left_alone(plant: int, tech: User) -> None:
    good = intake_into_new_batch(tech, plant, 5)
    drifted = intake_into_new_batch(tech, plant, 5)
    update("batches", drifted, {"live_count": 7})

    report = check_finds_drift()

    assert f"Batch {drifted}:" in report
    assert f"Batch {good}:" not in report
    assert live_count(drifted) == 7


def test_a_wrong_stage_is_reported(plant: int, tech: User) -> None:
    batch = new_lab_batch(tech, plant, 5, stage="P2")
    update("batches", batch, {"stage_code": "P1"})
    assert f"Batch {batch}:" in check_finds_drift()


def test_a_batch_closed_without_a_close_event_is_reported(
    plant: int, tech: User
) -> None:
    batch = intake_into_new_batch(tech, plant, 5)
    log(tech, batch, "out", qty_out=5)
    update("batches", batch, {"status": "closed", "closed_at": db_now()})
    assert f"Batch {batch}:" in check_finds_drift()
    assert batch_of(batch).status == "closed"
