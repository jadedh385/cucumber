"""AC12, AC13: who may save, void, correct and review events (U0.6 design §4).

The generated tests (accounts/tests/test_matrix_services.py) try each matrix
cell; these try the rules that narrow a cell: the Void tree, the 10-minute
Undo by the database clock, N7, a stale session, and a resent form.
"""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cucumber.accounts.permissions import Permission
from cucumber.core.tests.rows import as_int, fetch_one, run
from cucumber.core.tests.stock import (
    intake_into_new_batch,
    log,
    make_staff,
    not_allowed,
    refused,
    save,
)
from cucumber.events.models import Action, Event, Operation
from cucumber.events.permissions import ACTION_ROWS, NOT_THROUGH_SAVE, UNDO_WINDOW
from cucumber.events.reviews import review, review_queue
from cucumber.events.services import NewEvent, correct, save_operation, void

pytestmark = pytest.mark.django_db

VOID_REASON = "void_wrong_batch"
FIX_REASON = "correction_wrong_quantity"


@pytest.fixture
def stock(plant: int, admin: User) -> int:
    """A Nursery batch of 10 the Admin took in."""
    return intake_into_new_batch(admin, plant, 10)


def operation_of(event_id: int) -> uuid.UUID:
    return Event.objects.get(pk=event_id).operation_id


def saved_ago(event_id: int, age: timedelta) -> None:
    """Move the event's operation `age` into the past, by the database's clock.

    `operations` is insert-only even for its owner, so its triggers are off
    for this one update, inside the test's own transaction.
    """
    with_triggers_off(
        "operations",
        "UPDATE operations SET recorded_at = now() - %s WHERE id = %s",
        [age, operation_of(event_id)],
    )


def with_triggers_off(table: str, sql: str, params: list[object]) -> None:
    """Run one update on an insert-only table, its triggers off meanwhile.

    The deferred foreign-key checks run first: PostgreSQL won't alter a
    table while they are still waiting.
    """
    run("SET CONSTRAINTS ALL IMMEDIATE")
    run(f"ALTER TABLE {table} DISABLE TRIGGER USER")
    run(sql, params)
    run(f"ALTER TABLE {table} ENABLE TRIGGER USER")
    run("SET CONSTRAINTS ALL DEFERRED")


def voids_of(event_id: int) -> int:
    return Event.objects.filter(voids_event_id=event_id).count()


def operations() -> int:
    return as_int(fetch_one("SELECT count(*) FROM operations")[0])


# ------------------------------------------------ every action has a row
def test_every_action_has_a_row_or_its_own_service() -> None:
    assert set(ACTION_ROWS) | NOT_THROUGH_SAVE == set(Action.values)
    assert not set(ACTION_ROWS) & NOT_THROUGH_SAVE


def test_each_action_s_row_is_as_designed() -> None:
    assert {a for a, row in ACTION_ROWS.items() if row != Permission.LOG_WORK} == {
        "split",
        "close",
        "loss",
        "quarantine",
        "release",
    }
    assert ACTION_ROWS["release"] == Permission.RELEASE_QUARANTINE


@pytest.mark.parametrize("action", sorted(NOT_THROUGH_SAVE))
def test_a_void_or_correction_cannot_be_saved_as_a_plain_entry(
    stock: int, admin: User, action: str
) -> None:
    with refused("event_action_not_here"):
        log(admin, stock, action, qty_out=1)


def test_the_undo_window_is_10_minutes() -> None:
    assert timedelta(minutes=10) == UNDO_WINDOW


# ---------------------------------------------------------- the Void tree
def test_the_admin_voids_anyone_s_entry_at_any_time(
    stock: int, admin: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=1)
    saved_ago(entry, timedelta(days=3))

    void(admin, entry, VOID_REASON)

    assert voids_of(entry) == 1


def test_a_supervisor_voids_a_tech_s_entry_at_any_time(
    stock: int, supervisor: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=1)
    saved_ago(entry, timedelta(days=3))

    void(supervisor, entry, VOID_REASON)

    assert voids_of(entry) == 1


def test_a_supervisor_cannot_void_an_entry_they_did(
    stock: int, admin: User, supervisor: User
) -> None:
    """Saved by the Admin for the Supervisor: they did it, so it's theirs."""
    entry = log(admin, stock, "out", qty_out=1, staff_id=supervisor.pk)

    with refused("fix_own_entry"):
        void(supervisor, entry, VOID_REASON)

    assert voids_of(entry) == 0


def test_a_supervisor_undoes_their_own_entry_within_10_minutes(
    stock: int, supervisor: User
) -> None:
    """G1 Q4: like a Tech; every Undo still goes to the Admin's queue."""
    entry = log(supervisor, stock, "out", qty_out=1)
    saved_ago(entry, timedelta(minutes=9))

    void(supervisor, entry, VOID_REASON)

    assert voids_of(entry) == 1


def test_after_10_minutes_a_supervisor_s_own_entry_needs_another_reviewer(
    stock: int, supervisor: User
) -> None:
    entry = log(supervisor, stock, "out", qty_out=1)
    saved_ago(entry, timedelta(minutes=11))

    with refused("undo_too_late"):
        void(supervisor, entry, VOID_REASON)

    assert voids_of(entry) == 0


def test_a_tech_undoes_their_own_entry_within_10_minutes(
    stock: int, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=1)
    saved_ago(entry, timedelta(minutes=9))

    void(tech, entry, VOID_REASON)

    assert voids_of(entry) == 1


def test_after_10_minutes_a_tech_asks_a_reviewer(stock: int, tech: User) -> None:
    entry = log(tech, stock, "out", qty_out=1)
    saved_ago(entry, timedelta(minutes=11))

    with refused("undo_too_late"):
        void(tech, entry, VOID_REASON)

    assert voids_of(entry) == 0


def test_a_tech_cannot_undo_someone_else_s_entry(
    stock: int, tech: User, other_tech: User
) -> None:
    entry = log(other_tech, stock, "out", qty_out=1)

    with refused("undo_not_yours"):
        void(tech, entry, VOID_REASON)

    assert voids_of(entry) == 0


def test_a_tech_cannot_undo_work_a_supervisor_saved_for_them(
    stock: int, supervisor: User, tech: User
) -> None:
    """Undo is for entries you saved (`recorded_by`), not only did."""
    entry = log(supervisor, stock, "out", qty_out=1, staff_id=tech.pk)

    with refused("undo_not_yours"):
        void(tech, entry, VOID_REASON)


def test_the_10_minutes_count_from_the_operation_s_own_stamp(
    stock: int, tech: User
) -> None:
    """The database's now() against `operations.recorded_at` (D-07), not the
    event's date, which may be days back."""
    entry = log(tech, stock, "out", qty_out=1)
    with_triggers_off(
        "events",
        "UPDATE events SET occurred_at = now() - interval '3 days' WHERE id = %s",
        [entry],
    )

    void(tech, entry, VOID_REASON)

    assert voids_of(entry) == 1


def test_a_refused_undo_writes_nothing_and_locks_no_batch(
    stock: int, tech: User, other_tech: User
) -> None:
    entry = log(other_tech, stock, "out", qty_out=1)
    before = operations()

    with CaptureQueriesContext(connection) as queries, refused("undo_not_yours"):
        void(tech, entry, VOID_REASON)

    assert operations() == before
    sql = " ".join(query["sql"].upper() for query in queries.captured_queries)
    assert "FOR NO KEY UPDATE" not in sql


def test_every_undo_waits_in_the_admin_s_queue(
    stock: int, admin: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=1)

    undo = void(tech, entry, VOID_REASON)

    queued = {e for item in review_queue(admin) for e in item.event_ids}
    assert set(undo.event_ids) <= queued


# ------------------------------------------------------------ Correction
def test_a_supervisor_corrects_a_tech_s_entry(
    stock: int, supervisor: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=3)

    correct(supervisor, entry, FIX_REASON, qty_out=2)

    assert Event.objects.filter(corrects_event_id=entry).count() == 1


@pytest.mark.parametrize("on_it_as", ["did", "saved"])
def test_a_supervisor_cannot_correct_an_entry_they_did_or_saved(
    stock: int, admin: User, supervisor: User, tech: User, on_it_as: str
) -> None:
    """Even within 10 minutes: Undo is a Void, never a Correction."""
    if on_it_as == "did":
        entry = log(admin, stock, "out", qty_out=3, staff_id=supervisor.pk)
    else:
        entry = log(supervisor, stock, "out", qty_out=3, staff_id=tech.pk)

    with refused("fix_own_entry"):
        correct(supervisor, entry, FIX_REASON, qty_out=2)

    assert Event.objects.filter(corrects_event_id=entry).count() == 0


def test_a_tech_cannot_correct_even_their_own_entry(stock: int, tech: User) -> None:
    entry = log(tech, stock, "out", qty_out=3)

    with not_allowed("role_not_allowed"):
        correct(tech, entry, FIX_REASON, qty_out=2)


def test_the_admin_corrects_their_own_entry(stock: int, admin: User) -> None:
    entry = log(admin, stock, "out", qty_out=3)

    correct(admin, entry, FIX_REASON, qty_out=2)

    assert Event.objects.filter(corrects_event_id=entry).count() == 1


# ----------------------------------------------------------- N7 and staff
def test_a_tech_logs_only_work_they_did(
    stock: int, tech: User, other_tech: User
) -> None:
    with refused("staff_must_be_you"):
        log(tech, stock, "out", qty_out=1, staff_id=other_tech.pk)

    assert not Event.objects.filter(staff_id=other_tech.pk).exists()


def test_a_tech_may_name_themselves(stock: int, tech: User) -> None:
    entry = log(tech, stock, "out", qty_out=1, staff_id=tech.pk)

    assert Event.objects.get(pk=entry).staff_id == tech.pk


def test_one_entry_for_someone_else_refuses_the_whole_operation(
    stock: int, tech: User, other_tech: User
) -> None:
    before = operations()

    with refused("staff_must_be_you"):
        save(
            tech,
            NewEvent("out", batch_id=stock, qty_out=1),
            NewEvent("out", batch_id=stock, qty_out=1, staff_id=other_tech.pk),
        )

    assert operations() == before


@pytest.mark.parametrize("saver", ["supervisor", "admin"])
def test_a_reviewer_logs_work_for_a_tech(
    stock: int, tech: User, saver: str, request: pytest.FixtureRequest
) -> None:
    by: User = request.getfixturevalue(saver)

    entry = log(by, stock, "out", qty_out=1, staff_id=tech.pk)

    assert Event.objects.get(pk=entry).staff_id == tech.pk


@pytest.mark.parametrize("who_did_it", ["read_only", "no_role", "deactivated_tech"])
def test_who_did_the_work_must_be_someone_who_may_log_work(
    stock: int, supervisor: User, who_did_it: str, request: pytest.FixtureRequest
) -> None:
    did_it: User = request.getfixturevalue(who_did_it)

    with refused("staff_not_active"):
        log(supervisor, stock, "out", qty_out=1, staff_id=did_it.pk)


# ------------------------------------------------- a stale session (AC5, AC13)
def test_a_switched_off_person_with_an_open_session_saves_nothing(
    stock: int, tech: User
) -> None:
    """The page holds the old User; the service reads the database."""
    User.objects.filter(pk=tech.pk).update(is_active=False)
    before = operations()

    with not_allowed("account_not_active"):
        log(tech, stock, "out", qty_out=1)

    assert operations() == before


def test_a_role_taken_away_applies_to_the_very_next_save(
    stock: int, tech: User
) -> None:
    log(tech, stock, "out", qty_out=1)
    User.groups.through.objects.filter(user_id=tech.pk).delete()

    with not_allowed("role_not_allowed"):
        log(tech, stock, "out", qty_out=1)


def test_a_switched_off_reviewer_reviews_nothing(
    stock: int, supervisor: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=1)
    User.objects.filter(pk=supervisor.pk).update(is_active=False)

    with not_allowed("account_not_active"):
        review(supervisor, operation_of(entry))


@pytest.mark.parametrize("who", ["read_only", "no_role"])
def test_someone_who_may_not_review_has_an_empty_queue(
    stock: int, tech: User, who: str, request: pytest.FixtureRequest
) -> None:
    log(tech, stock, "out", qty_out=1)

    assert review_queue(request.getfixturevalue(who)) == []


def test_a_supervisor_may_not_review_a_void(
    stock: int, supervisor: User, tech: User
) -> None:
    """Review Voids is the Admin's row in the matrix, not only rule 10."""
    undo = void(tech, log(tech, stock, "out", qty_out=1), VOID_REASON)

    with not_allowed("role_not_allowed"):
        review(supervisor, undo.operation_id)


# ------------------------------------------- a resent form (AC13, G4 L3)
def test_a_form_resent_by_the_same_person_gets_the_first_result(
    stock: int, tech: User
) -> None:
    operation_id = uuid.uuid4()
    entry = [NewEvent("out", batch_id=stock, qty_out=1)]
    first = save_operation(operation_id, tech, entry)

    again = save_operation(operation_id, tech, entry)

    assert again.already_saved
    assert again.event_ids == first.event_ids


def test_a_form_resent_by_someone_else_is_refused_and_shows_nothing(
    stock: int, tech: User, other_tech: User
) -> None:
    operation_id = uuid.uuid4()
    entry = [NewEvent("out", batch_id=stock, qty_out=1)]
    save_operation(operation_id, tech, entry)

    with refused("operation_saved_by_other"):
        save_operation(operation_id, other_tech, entry)

    assert Operation.objects.get(pk=operation_id).recorded_by_id == tech.pk


def test_a_void_resent_by_someone_else_is_refused(
    stock: int, admin: User, supervisor: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=1)
    operation_id = uuid.uuid4()
    void(admin, entry, VOID_REASON, operation_id=operation_id)

    with refused("operation_saved_by_other"):
        void(supervisor, entry, VOID_REASON, operation_id=operation_id)


def test_a_correction_resent_by_someone_else_is_refused(
    stock: int, admin: User, supervisor: User, tech: User
) -> None:
    entry = log(tech, stock, "out", qty_out=3)
    operation_id = uuid.uuid4()
    correct(admin, entry, FIX_REASON, qty_out=2, operation_id=operation_id)

    with refused("operation_saved_by_other"):
        correct(supervisor, entry, FIX_REASON, qty_out=2, operation_id=operation_id)


def test_a_resend_by_someone_switched_off_since_is_refused(
    stock: int, tech: User
) -> None:
    """The standing is read first, so they aren't handed the result (§4.3)."""
    operation_id = uuid.uuid4()
    entry = [NewEvent("out", batch_id=stock, qty_out=1)]
    save_operation(operation_id, tech, entry)
    User.objects.filter(pk=tech.pk).update(is_active=False)

    with not_allowed("account_not_active"):
        save_operation(operation_id, tech, entry)


def test_a_new_staff_member_with_no_role_saves_nothing(stock: int) -> None:
    mali = make_staff("mali", None)

    with not_allowed("role_not_allowed"):
        log(mali, stock, "out", qty_out=1)
