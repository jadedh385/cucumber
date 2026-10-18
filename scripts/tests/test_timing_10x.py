"""Tests for the 10× timing script (U0.4b design §13, U0.2a/U0.2b G5 notes)."""

import psycopg
import pytest
from django.core.management import call_command

from cucumber.batches.models import Batch
from cucumber.events.models import Event
from cucumber.events.reviews import waiting_for_review
from cucumber.plants.models import Plant
from scripts import timing_10x
from scripts.timing_10x import Scale, Summary

SMALL = Scale(plants=5, batches=12, events_per_batch=14, busy_events=31, backlog=9)


# ---------------------------------------------------------------- plain parts


def test_ten_times_scale_matches_the_g5_notes() -> None:
    # Owner, 2026-10-12: ~300 plants, 1,000 open batches, 100 entries a day.
    scale = Scale()

    assert (scale.plants, scale.batches) == (3_000, 10_000)
    assert scale.total_events == 362_000
    assert (scale.backlog, scale.busy_events) == (7_000, 2_000)


def test_summary_gives_median_and_95th_percentile() -> None:
    samples = [float(n) for n in range(1, 101)]

    assert timing_10x.summarize(samples) == Summary(median=50.5, p95=95.0)


def test_summary_of_one_sample_is_that_sample() -> None:
    assert timing_10x.summarize([7.0]) == Summary(median=7.0, p95=7.0)


@pytest.mark.parametrize("events", [2, 14, 36, 2_000])
def test_final_count_never_goes_below_zero(events: int) -> None:
    assert timing_10x.final_count(events) > 0


def test_final_count_is_the_start_less_every_out() -> None:
    # Event 0 is the intake; 1-9 are outs, 10 is a count, 11-13 outs again.
    assert timing_10x.final_count(14) == timing_10x.start_qty(14) - 12


def test_table_lists_each_row_in_milliseconds() -> None:
    rows = [
        ("Save an entry", Summary(9.04, 15.0)),
        ("Review queue", Summary(1600, 1612)),
    ]

    table = timing_10x.as_table(rows)

    assert "| Save an entry | 9.0 ms | 15.0 ms |" in table
    assert "| Review queue | 1.60 s | 1.61 s |" in table


def test_refuses_any_database_but_the_throwaway_one() -> None:
    timing_10x.check_database("cucumber_timing")
    with pytest.raises(SystemExit, match="cucumber_timing"):
        timing_10x.check_database("cucumber")


# ------------------------------------------------------------------- the load


@pytest.mark.django_db
def test_load_makes_the_rows_the_scale_asks_for() -> None:
    timing_10x.load(SMALL)

    assert Plant.objects.count() == SMALL.plants
    assert Batch.objects.count() == SMALL.batches + 1  # and the busy batch
    assert Event.objects.count() == SMALL.total_events
    assert len(waiting_for_review()) == SMALL.backlog


@pytest.mark.django_db
def test_loaded_batches_match_their_events() -> None:
    timing_10x.load(SMALL)

    call_command("check_projections")  # raises CommandError on any drift


# ---------------------------------------------------------------- the timings


@pytest.mark.django_db(transaction=True)
def test_every_timing_runs_without_a_refusal(
    app_db: psycopg.Connection[tuple[object, ...]],
) -> None:
    timing_10x.load(SMALL)

    rows = timing_10x.measure(SMALL, runs=2, app=app_db)

    assert [label for label, _ in rows] == list(timing_10x.LABELS)
    assert all(summary.median > 0 for _, summary in rows)
    call_command("check_projections")
