"""U0.2b: the projection and effective events (design §3.1, "the count wins").

`project` and `count_differences` are pure, so most cases need no database.
`effective_events` reads rows written with plain SQL, so it is tested apart
from the services that will write them.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from cucumber.core.tests.rows import db_now, make_batch, make_event
from cucumber.events.models import Event
from cucumber.events.projection import (
    Effective,
    Projection,
    count_differences,
    project,
)

BANGKOK = ZoneInfo("Asia/Bangkok")


def on(day: str, hour: int = 9) -> datetime:
    """A day of one week in October 2026, Monday the 5th to Sunday the 11th."""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return datetime(2026, 10, 5 + days.index(day), hour, tzinfo=BANGKOK)


def intake(
    event_id: int, when: datetime, qty: int, stage: str | None = None
) -> Effective:
    return Effective(event_id, "intake", when, qty_in=qty, stage_to=stage)


def out(event_id: int, when: datetime, qty: int, action: str = "out") -> Effective:
    return Effective(event_id, action, when, qty_out=qty)


def count(event_id: int, when: datetime, qty: int) -> Effective:
    return Effective(event_id, "count", when, counted_qty=qty)


def stage_change(event_id: int, when: datetime, stage: str) -> Effective:
    return Effective(event_id, "stage_change", when, stage_to=stage)


# AC16g: 100 Monday, a count of 98 Wednesday, a loss of 5 dated Tuesday.
LOSS_BEFORE_COUNT = [
    intake(1, on("Mon"), 100),
    count(2, on("Wed"), 98),
    out(3, on("Tue"), 5, "loss"),
]

# AC16d: 48 on Saturday 09:00, +10 on Sunday, a count of 50 dated Saturday 12:00.
COUNT_BEFORE_INTAKE = [
    intake(1, on("Sat", 9), 48),
    intake(2, on("Sun"), 10),
    count(3, on("Sat", 12), 50),
]


# ------------------------------------------------------------- live count


def test_with_no_count_the_total_is_the_sum_of_all_events() -> None:
    events = [
        intake(1, on("Mon"), 10),
        out(2, on("Tue"), 3),
        out(3, on("Wed"), 2, "loss"),
    ]
    assert project(events).live_count == 5


def test_ac16g_an_event_dated_before_the_latest_count_leaves_the_total() -> None:
    assert project(LOSS_BEFORE_COUNT).live_count == 98


def test_ac16d_events_after_the_latest_count_apply_on_top() -> None:
    assert project(COUNT_BEFORE_INTAKE).live_count == 60


def test_the_latest_count_is_chosen_by_date_not_by_id() -> None:
    events = [intake(1, on("Mon"), 10), count(2, on("Wed"), 7), count(3, on("Tue"), 9)]
    assert project(events).live_count == 7


def test_events_at_the_same_moment_are_ordered_by_id() -> None:
    same = on("Tue")
    count_then_out = [intake(1, on("Mon"), 10), count(2, same, 10), out(3, same, 4)]
    out_then_count = [intake(1, on("Mon"), 10), out(2, same, 4), count(3, same, 10)]
    assert project(count_then_out).live_count == 6
    assert project(out_then_count).live_count == 10


def test_the_order_events_are_passed_in_does_not_matter() -> None:
    assert project(list(reversed(LOSS_BEFORE_COUNT))) == project(LOSS_BEFORE_COUNT)


def test_a_count_of_zero_is_a_count() -> None:
    events = [intake(1, on("Mon"), 10), count(2, on("Tue"), 0), intake(3, on("Wed"), 5)]
    assert project(events).live_count == 5


# ------------------------------------------------------------ stage, close


def test_the_stage_is_set_by_the_latest_event_that_sets_one() -> None:
    events = [
        intake(1, on("Mon"), 10, stage="P0"),
        stage_change(2, on("Wed"), "P2"),
        stage_change(3, on("Tue"), "P1"),  # backdated: doesn't overwrite P2
        out(4, on("Thu"), 1),  # sets no stage
    ]
    assert project(events).stage_code == "P2"


def test_a_close_event_closes_the_batch_at_its_date() -> None:
    events = [
        intake(1, on("Mon"), 5),
        out(2, on("Tue"), 5),
        Effective(3, "close", on("Wed")),
    ]
    assert project(events) == Projection(
        live_count=0, stage_code=None, is_closed=True, closed_at=on("Wed")
    )


def test_a_batch_with_no_events_is_empty_open_and_unstaged() -> None:
    assert project([]) == Projection(
        live_count=0, stage_code=None, is_closed=False, closed_at=None
    )


# -------------------------------------------------------- count differences


def test_ac16g_a_loss_dated_before_a_count_changes_its_difference() -> None:
    assert count_differences(LOSS_BEFORE_COUNT) == {2: 3}


def test_ac16d_a_count_is_compared_with_the_total_at_its_own_date() -> None:
    assert count_differences(COUNT_BEFORE_INTAKE) == {3: 2}


def test_each_count_is_compared_with_the_total_just_before_it() -> None:
    events = [
        intake(1, on("Mon"), 10),
        count(2, on("Tue"), 8),
        out(3, on("Wed"), 1),
        count(4, on("Thu"), 9),
    ]
    assert count_differences(events) == {2: -2, 4: 2}


def test_a_first_count_with_nothing_before_it_is_all_difference() -> None:
    assert count_differences([count(1, on("Mon"), 5)]) == {1: 5}


def test_no_counts_mean_no_differences() -> None:
    assert count_differences([intake(1, on("Mon"), 5)]) == {}


# ---------------------------------------------------------- effective events
#
# Rows are written with plain SQL. A Correction row restates every
# correctable value of the original, not only the one it changes.


@pytest.fixture
def now() -> datetime:
    return db_now()


@pytest.mark.django_db
def test_voided_events_and_fix_rows_are_left_out(batch: int, user: int) -> None:
    kept = make_event(batch, user, "intake", qty_in=5)
    voided = make_event(batch, user, "intake", qty_in=3)
    make_event(batch, user, "void", "void", voids_event_id=voided)
    effective = Event.objects.effective_events(batch)
    assert [event.id for event in effective] == [kept]


@pytest.mark.django_db
def test_a_correction_s_values_replace_the_original_s(
    batch: int, user: int, now: datetime
) -> None:
    original = make_event(
        batch,
        user,
        "intake",
        qty_in=5,
        media_code="M001",
        stage_to="P0",
        occurred_at=now - timedelta(days=2),
    )
    make_event(
        batch,
        user,
        "correction",
        "correction",
        corrects_event_id=original,
        qty_in=7,
        media_code="M002",
        stage_to="P1",
        occurred_at=now - timedelta(days=20),  # a reviewer's date fix
    )
    assert Event.objects.effective_events(batch) == [
        Effective(
            original,
            "intake",
            now - timedelta(days=20),
            qty_in=7,
            media_code="M002",
            stage_to="P1",
        )
    ]


@pytest.mark.django_db
def test_the_newest_non_voided_correction_wins(
    batch: int, user: int, now: datetime
) -> None:
    original = make_event(batch, user, "intake", qty_in=5, occurred_at=now)

    def correction(qty: int) -> int:
        return make_event(
            batch,
            user,
            "correction",
            "correction",
            corrects_event_id=original,
            qty_in=qty,
            occurred_at=now,
        )

    correction(6)
    assert Event.objects.effective_events(batch)[0].qty_in == 6
    newest = correction(8)
    assert Event.objects.effective_events(batch)[0].qty_in == 8
    make_event(batch, user, "void", "void", voids_event_id=newest)
    assert Event.objects.effective_events(batch)[0].qty_in == 6


@pytest.mark.django_db
def test_effective_events_are_in_date_then_id_order(
    batch: int, user: int, now: datetime
) -> None:
    yesterday = make_event(
        batch, user, "intake", qty_in=1, occurred_at=now - timedelta(days=1)
    )
    first = make_event(
        batch, user, "intake", qty_in=1, occurred_at=now - timedelta(days=2)
    )
    second = make_event(
        batch, user, "intake", qty_in=1, occurred_at=now - timedelta(days=2)
    )
    effective = Event.objects.effective_events(batch)
    assert [event.id for event in effective] == [first, second, yesterday]


@pytest.mark.django_db
def test_a_corrected_date_moves_the_event(batch: int, user: int, now: datetime) -> None:
    moved = make_event(
        batch, user, "intake", qty_in=1, occurred_at=now - timedelta(days=1)
    )
    other = make_event(
        batch, user, "intake", qty_in=1, occurred_at=now - timedelta(days=2)
    )
    make_event(
        batch,
        user,
        "correction",
        "correction",
        corrects_event_id=moved,
        qty_in=1,
        occurred_at=now - timedelta(days=3),
    )
    effective = Event.objects.effective_events(batch)
    assert [event.id for event in effective] == [moved, other]


@pytest.mark.django_db
def test_only_the_batch_s_own_events_are_listed(
    plant: int, batch: int, user: int
) -> None:
    own = make_event(batch, user, "intake", qty_in=1)
    make_event(make_batch(plant, user), user, "intake", qty_in=1)
    effective = Event.objects.effective_events(batch)
    assert [event.id for event in effective] == [own]
