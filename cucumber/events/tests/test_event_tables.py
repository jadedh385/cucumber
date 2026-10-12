"""U0.2a: events, operations and reviews (design §2.4, §2.5, §3).

AC14–AC16c, AC18; append-only (AC13, AC19) is in core/tests/test_protection.py.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from cucumber.core.tests.rows import (
    db_now,
    event_values,
    fetch_one,
    insert,
    make_batch,
    make_event,
    make_operation,
    make_review,
    refused_by,
    run,
)

pytestmark = pytest.mark.django_db

BANGKOK = ZoneInfo("Asia/Bangkok")

OUT_ACTIONS = ["subculture", "split", "contamination", "quarantine", "out", "loss"]

# One valid event of each plain action (design §3).
VALID_SHAPES: dict[str, dict[str, object]] = {
    "intake": {"qty_in": 5, "stage_to": "P0", "media_code": "M001"},
    "subculture": {"qty_out": 2, "media_code": "M001"},
    "split": {"qty_out": 2, "note": "pre-order"},
    "contamination": {"qty_out": 1},
    "quarantine": {"qty_out": 1},
    "out": {"qty_out": 1},
    "loss": {"qty_out": 1},
    "stage_change": {"stage_to": "P1"},
    "count": {"counted_qty": 7},
    "release": {},
    "transfer": {"qty_out": 3},
    "close": {},
}

NO_UNITS_OUT: dict[str, object] = {"qty_out": 0}
UNITS_IN: dict[str, object] = {"qty_in": 1}

# Each breaks only its own action's shape rule, `event_<action>_shape`.
BAD_SHAPES: list[tuple[str, dict[str, object]]] = [
    ("intake", {"qty_in": 0}),
    *[(action, NO_UNITS_OUT) for action in OUT_ACTIONS],
    *[(action, UNITS_IN) for action in OUT_ACTIONS],
    ("stage_change", {}),
    ("stage_change", {"stage_to": "P1", "qty_in": 1}),
    ("count", {}),
    ("count", {"counted_qty": 5, "qty_out": 1}),
    ("release", {"qty_out": 1}),
    ("close", {"qty_in": 1}),
    ("transfer", {}),
]


def reason_for(action: str) -> str | None:
    """The reason list an action must use, if it needs a reason (rule 8, Q4)."""
    return action if action in {"void", "correction", "loss"} else None


# ------------------------------------------------------------- event shapes


@pytest.mark.parametrize("action", sorted(VALID_SHAPES))
def test_each_action_has_a_valid_shape(batch: int, user: int, action: str) -> None:
    make_event(batch, user, action, reason_for(action), **VALID_SHAPES[action])


@pytest.mark.parametrize(("action", "values"), BAD_SHAPES)
def test_each_action_refuses_the_wrong_shape(
    batch: int, user: int, action: str, values: dict[str, object]
) -> None:
    with refused_by(f"event_{action}_shape"):
        make_event(batch, user, action, reason_for(action), **values)


def test_a_transfer_moves_units_one_way(batch: int, user: int) -> None:
    with refused_by("event_qty_one_direction"):
        make_event(batch, user, "transfer", qty_in=1, qty_out=1)


def test_an_unknown_action_is_refused(batch: int, user: int) -> None:
    with refused_by("event_action_valid"):
        make_event(batch, user, "reopen")


def test_entry_route_is_form_or_assistant(batch: int, user: int) -> None:
    """D-21."""
    make_event(batch, user, "count", counted_qty=1, entered_via="assistant")
    with refused_by("event_entered_via_valid"):
        make_event(batch, user, "count", counted_qty=1, entered_via="import")


# ------------------------------------------------------ quantities (rule 7)


@pytest.fixture
def original(batch: int, user: int) -> int:
    """An event to void, correct or review."""
    return make_event(batch, user, "out", qty_out=2)


@pytest.mark.parametrize("column", ["qty_in", "qty_out"])
def test_ac16_quantities_are_never_negative(
    batch: int, user: int, original: int, column: str
) -> None:
    """A Correction has no shape rule, so only the sign check can refuse it."""
    with refused_by("event_qty_not_negative"):
        make_event(
            batch, user, "correction", "correction",
            corrects_event_id=original, **{column: -1},
        )  # fmt: skip


def test_a_count_is_never_negative(batch: int, user: int) -> None:
    with refused_by("event_counted_not_negative"):
        make_event(batch, user, "count", counted_qty=-1)


# ------------------------------------------------ void and correction (rule 8)


@pytest.mark.parametrize(
    ("action", "target"),
    [("void", "voids_event_id"), ("correction", "corrects_event_id")],
)
def test_ac14_a_void_or_correction_needs_a_reason(
    batch: int, user: int, original: int, action: str, target: str
) -> None:
    with refused_by("event_reason_required"):
        make_event(batch, user, action, None, **{target: original})


def test_ac16a_a_loss_needs_a_reason(batch: int, user: int) -> None:
    with refused_by("event_reason_required"):
        make_event(batch, user, "loss", None, qty_out=1)


def test_ac16a_a_loss_needs_units(batch: int, user: int) -> None:
    with refused_by("event_loss_shape"):
        make_event(batch, user, "loss", "loss", qty_out=0)


def test_a_void_and_a_correction_with_reasons_are_accepted(
    batch: int, user: int, original: int
) -> None:
    make_event(
        batch, user, "correction", "correction", corrects_event_id=original, qty_out=1
    )
    make_event(batch, user, "void", "void", voids_event_id=original)


def test_a_void_moves_no_units(batch: int, user: int, original: int) -> None:
    with refused_by("event_void_shape"):
        make_event(batch, user, "void", "void", voids_event_id=original, qty_in=1)


@pytest.mark.parametrize(
    ("action", "target", "rule"),
    [
        ("void", None, "event_void_target"),
        ("count", "voids_event_id", "event_void_target"),
        ("correction", None, "event_correction_target"),
        ("count", "corrects_event_id", "event_correction_target"),
    ],
)
def test_only_voids_and_corrections_point_at_an_event(
    batch: int, user: int, original: int, action: str, target: str | None, rule: str
) -> None:
    values: dict[str, object] = {"counted_qty": 1} if action == "count" else {}
    if target:
        values[target] = original
    with refused_by(rule):
        make_event(batch, user, action, reason_for(action), **values)


def test_ac15_an_event_is_voided_only_once(
    batch: int, user: int, original: int
) -> None:
    make_event(batch, user, "void", "void", voids_event_id=original)
    with refused_by("event_void_once"):
        make_event(batch, user, "void", "void", voids_event_id=original)


@pytest.mark.parametrize(
    ("action", "target", "rule"),
    [
        ("void", "voids_event_id", "event_void_same_batch"),
        ("correction", "corrects_event_id", "event_correction_same_batch"),
    ],
)
def test_a_fix_stays_on_the_batch_of_the_event_it_fixes(
    plant: int, user: int, original: int, action: str, target: str, rule: str
) -> None:
    other_batch = make_batch(plant, user)
    with refused_by(rule):
        make_event(other_batch, user, action, action, **{target: original})


# ---------------------------------------------------------- dates (Q5, M1)


@pytest.fixture
def recorded_at_from_test() -> None:
    """Let a test choose `recorded_at`, to pin "now" to a Bangkok time.

    PostgreSQL's clock can't be frozen from Python, so this switches off the
    trigger that stamps `now()`, inside the test's own transaction (rolled
    back afterwards, which also switches the trigger back on). The check
    constraints under test still run.

    It must run before any event is inserted in the test: PostgreSQL refuses
    to alter a table with pending trigger events. `usefixtures` fixtures run
    before the ones a test names as arguments (such as `original`).
    """
    run("ALTER TABLE events DISABLE TRIGGER events_recorded_at_now")


def bangkok(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=BANGKOK)


# Tuesday 13 Oct, 00:30 in Bangkok: still Monday 12 Oct (17:30) in UTC.
JUST_AFTER_MIDNIGHT = bangkok(10, 13, 0, 30)


def dated_count(batch: int, user: int, occurred: datetime, recorded: datetime) -> None:
    make_event(
        batch, user, "count", counted_qty=1, occurred_at=occurred, recorded_at=recorded
    )


@pytest.mark.usefixtures("recorded_at_from_test")
@pytest.mark.parametrize(
    "occurred",
    [
        bangkok(10, 13, 0, 10),  # today, 20 minutes ago
        bangkok(10, 6, 0, 0),  # 7 Bangkok days back, first minute
        bangkok(10, 6, 23, 59),
    ],
)
def test_ac16b_dates_up_to_7_bangkok_days_back_are_accepted(
    batch: int, user: int, occurred: datetime
) -> None:
    dated_count(batch, user, occurred, JUST_AFTER_MIDNIGHT)


@pytest.mark.usefixtures("recorded_at_from_test")
def test_ac16b_8_bangkok_days_back_is_refused_where_utc_would_allow_it(
    batch: int, user: int
) -> None:
    """5 Oct 23:59 Bangkok is 5 Oct 16:59 UTC: 7 UTC days before 12 Oct UTC."""
    with refused_by("event_within_7_days"):
        dated_count(batch, user, bangkok(10, 5, 23, 59), JUST_AFTER_MIDNIGHT)


@pytest.mark.usefixtures("recorded_at_from_test")
def test_ac16b_calendar_days_not_rolling_hours(batch: int, user: int) -> None:
    """Saved Monday 14:00: last Monday midday is 7 days 2 hours ago, still allowed."""
    dated_count(batch, user, bangkok(10, 5, 12), bangkok(10, 12, 14))


@pytest.mark.usefixtures("recorded_at_from_test")
def test_ac16b_up_to_5_minutes_ahead_is_allowed(batch: int, user: int) -> None:
    """Room for a phone clock a little ahead of the server."""
    ahead = JUST_AFTER_MIDNIGHT + timedelta(minutes=5)
    dated_count(batch, user, ahead, JUST_AFTER_MIDNIGHT)


@pytest.mark.usefixtures("recorded_at_from_test")
def test_ac16b_further_in_the_future_is_refused(batch: int, user: int) -> None:
    ahead = JUST_AFTER_MIDNIGHT + timedelta(minutes=5, seconds=1)
    with refused_by("event_not_in_future"):
        dated_count(batch, user, ahead, JUST_AFTER_MIDNIGHT)


@pytest.mark.usefixtures("recorded_at_from_test")
def test_ac16c_a_correction_can_restate_a_date_3_weeks_back(
    batch: int, user: int, original: int
) -> None:
    make_event(
        batch, user, "correction", "correction", corrects_event_id=original,
        qty_out=2, occurred_at=bangkok(9, 22, 12), recorded_at=JUST_AFTER_MIDNIGHT,
    )  # fmt: skip


def test_ac16b_a_normal_event_3_weeks_back_is_refused(batch: int, user: int) -> None:
    """Against the database's own clock, with the trigger on."""
    with refused_by("event_within_7_days"):
        make_event(
            batch, user, "count", counted_qty=1,
            occurred_at=db_now() - timedelta(days=21),
        )  # fmt: skip


def test_ac16c_a_correction_3_weeks_back_is_accepted(
    batch: int, user: int, original: int
) -> None:
    make_event(
        batch, user, "correction", "correction", corrects_event_id=original,
        qty_out=2, occurred_at=db_now() - timedelta(days=21),
    )  # fmt: skip


def test_recorded_at_is_always_the_real_save_time(batch: int, user: int) -> None:
    """M1, N6: the app can't move the 7-day window by sending its own time."""
    event = make_event(
        batch, user, "count", counted_qty=1, recorded_at=bangkok(10, 1, 9)
    )
    row = fetch_one("SELECT recorded_at = now() FROM events WHERE id = %s", [event])
    assert row == (True,)


def test_quantities_note_and_entry_route_have_defaults(batch: int, user: int) -> None:
    """Design §2.4: `qty_in`, `qty_out` default 0, `note` '', `entered_via` 'form'."""
    values = event_values(batch, user, "count", counted_qty=1)
    for column in ["qty_in", "qty_out", "note", "entered_via"]:
        del values[column]
    event = insert("events", values)
    row = fetch_one(
        "SELECT qty_in, qty_out, note, entered_via FROM events WHERE id = %s", [event]
    )
    assert row == (0, 0, "", "form")


def test_recorded_at_defaults_to_now(batch: int, user: int) -> None:
    event = make_event(batch, user, "count", counted_qty=1)
    row = fetch_one("SELECT recorded_at = now() FROM events WHERE id = %s", [event])
    assert row == (True,)


# --------------------------------------------------------------- operations


def test_one_operation_id_is_saved_only_once(user: int) -> None:
    """Issue #4: a form sent twice hits the primary key, never a second set."""
    operation = make_operation(user)
    with refused_by("operations_pkey"):
        insert("operations", {"id": operation, "recorded_by": user})


def test_events_of_one_action_share_its_operation(batch: int, user: int) -> None:
    """Q8: one user action, one `operation_id`, many events."""
    operation = make_operation(user)
    insert(
        "events", event_values(batch, user, "out", operation_id=operation, qty_out=1)
    )
    insert("events", event_values(batch, user, "count", operation_id=operation,
                                  counted_qty=4))  # fmt: skip
    row = fetch_one("SELECT count(*) FROM events WHERE operation_id = %s", [operation])
    assert row == (2,)


def test_operation_time_defaults_to_now(user: int) -> None:
    operation = make_operation(user)
    row = fetch_one(
        "SELECT recorded_at = now() FROM operations WHERE id = %s", [operation]
    )
    assert row == (True,)


# ------------------------------------------------------------- reviews (Q3)


def test_ac18_an_event_is_reviewed_only_once(
    original: int, reviewer: int, user: int
) -> None:
    make_review(original, reviewer)
    with refused_by("event_review_once"):
        make_review(original, user)


def test_review_time_defaults_to_now(original: int, reviewer: int) -> None:
    review = make_review(original, reviewer)
    row = fetch_one(
        "SELECT reviewed_at = now() FROM event_reviews WHERE id = %s", [review]
    )
    assert row == (True,)
