"""Helpers for the U0.2a schema tests (U0.2 design §6, §7.1).

The schema tests write rows with plain SQL, not models, on purpose: the
database must refuse bad data even when Django's own checks are skipped (spec
story S1). Each refusal is checked by the rule's stable name from design §7.1,
so a test can't pass because a different rule happened to refuse the row.

Loaded for every test through `pytest_plugins` in the root conftest.py.
"""

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import psycopg
import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError, connection, transaction

from cucumber.core.audit import SYSTEM, Reason, audited

Values = Mapping[str, object]
Params = list[Any] | None
AppConnection = psycopg.Connection[tuple[object, ...]]


# A test's own `via`, so its set-up rows are easy to tell apart (U0.7).
VIA_TEST = "test"


@contextmanager
def as_system(reason: Reason | None = None) -> Iterator[None]:
    """Test set-up that writes audited tables, made by System (U0.7 design §13).

    The builders below use it; it is never on for the whole suite (review
    H3), so a service that forgets `audited()` still fails its test. Set-up
    that switches something off passes its reason (AC11).
    """
    with audited(SYSTEM, via=VIA_TEST, reason=reason):
        yield


# ------------------------------------------------------------------ plain SQL


def quote(name: str) -> str:
    return connection.ops.quote_name(name)


def run(sql: str, params: Params = None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def fetch_one(sql: str, params: Params = None) -> tuple[object, ...]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    assert row is not None, f"no row from: {sql}"
    return tuple(row)


def fetch_all(sql: str, params: Params = None) -> list[tuple[object, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]


def as_int(value: object) -> int:
    assert isinstance(value, int), f"expected an integer, got {value!r}"
    return value


def insert(table: str, values: Values, returning: str = "id") -> object:
    """Insert one row and return its `returning` column."""
    columns = ", ".join(quote(column) for column in values)
    placeholders = ", ".join(["%s"] * len(values))
    # Table and column names come from the tests themselves and are quoted.
    sql = (
        f"INSERT INTO {quote(table)} ({columns}) VALUES ({placeholders})"  # noqa: S608
        f" RETURNING {quote(returning)}"
    )
    return fetch_one(sql, list(values.values()))[0]


def update(table: str, key: object, values: Values, key_column: str = "id") -> None:
    """Update the one row whose `key_column` is `key`."""
    assignments = ", ".join(f"{quote(column)} = %s" for column in values)
    sql = f"UPDATE {quote(table)} SET {assignments} WHERE {quote(key_column)} = %s"  # noqa: S608
    run(sql, [*values.values(), key])


def db_now() -> datetime:
    """The database's `now()`: the start of the current transaction."""
    value = fetch_one("SELECT now()")[0]
    assert isinstance(value, datetime)
    return value


# ------------------------------------------------------------------ refusals


def rule_name(error: BaseException) -> str | None:
    """The constraint, index or trigger rule that refused a statement.

    Check, unique and foreign-key errors carry the constraint's name. Triggers
    report theirs with `RAISE … USING CONSTRAINT = '<name>'`, so the service
    can look every refusal up in design §7.1 the same way.
    """
    cause = error if isinstance(error, psycopg.Error) else error.__cause__
    if isinstance(cause, psycopg.Error):
        return cause.diag.constraint_name
    return None


@contextmanager
def refused_by(rule: str) -> Iterator[None]:
    """Expect the database to refuse the statements inside, naming `rule`.

    Runs them in a savepoint, so the test can carry on after the refusal.
    """
    with pytest.raises(DatabaseError) as caught, transaction.atomic():
        yield
    found = rule_name(caught.value)
    assert found == rule, (
        f"expected rule {rule!r}, refused by {found!r}: {caught.value}"
    )


def refused_for_app(app_db: AppConnection, sql: str) -> None:
    """Expect the app user, `cucumber_app`, not to be allowed to run `sql`."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_db.execute(sql.encode())


# -------------------------------------------------------------- row builders
#
# Every builder supplies every column that has no database default, so a test
# changes only the one value it is about. Column names are the design's (§2).


def staff_email(name: str) -> str:
    """A test account's email, which is also its user name (U0.5 design §3.4)."""
    return f"{name}@example.com"


def make_user(name: str = "tech") -> int:
    email = staff_email(name)
    with as_system():
        return as_int(User.objects.create_user(username=email, email=email).pk)


def make_operation(recorded_by: int) -> uuid.UUID:
    operation_id = uuid.uuid4()
    insert("operations", {"id": operation_id, "recorded_by": recorded_by})
    return operation_id


def make_vendor(zoho_contact_id: str = "ZC-1", name: str = "Green Leaf Co.") -> str:
    values = {
        "zoho_contact_id": zoho_contact_id,
        "name": name,
        "active": True,
        "synced_at": db_now(),
    }
    with as_system():
        insert("vendors", values, returning="zoho_contact_id")
    return zoho_contact_id


def plant_values(created_by: int, **overrides: object) -> dict[str, object]:
    """A valid Collection plant, given as a gift, with no SKU."""
    return {
        "genus_code": "PHL",
        "full_name": "Pink Princess",
        "status": "collection",
        "source": "gift",
        "source_note": None,
        "vendor_id": None,
        "zoho_ref": None,
        "min_saleable_qty": None,
        "notes": "",
        "created_at": db_now(),
        "created_by": created_by,
        **overrides,
    }


def make_plant(created_by: int, **overrides: object) -> int:
    with as_system():
        return as_int(insert("plants", plant_values(created_by, **overrides)))


def issue_sku(
    plant_id: int, sku: str, assigned_by: int, genus_code: str | None = None
) -> None:
    """Add `sku` to the SKU register for `plant_id`; the plant isn't pointed at it."""
    values = {
        "sku": sku,
        "plant_id": plant_id,
        "genus_code": genus_code or sku[:3],
        "assigned_at": db_now(),
        "assigned_by": assigned_by,
    }
    insert("skus", values, returning="sku")


def give_sku(plant_id: int, sku: str, assigned_by: int) -> None:
    """Issue `sku` to the plant and point the plant at it."""
    issue_sku(plant_id, sku, assigned_by)
    with as_system():
        update("plants", plant_id, {"sku": sku})


def next_plant_seq(plant_id: int) -> int:
    row = fetch_one(
        "SELECT coalesce(max(plant_seq), 0) + 1 FROM batches WHERE plant_id = %s",
        [plant_id],
    )
    return as_int(row[0])


def batch_values(
    plant_id: int, created_by: int, **overrides: object
) -> dict[str, object]:
    """A valid, empty, open Nursery batch from an intake."""
    values: dict[str, object] = {
        "plant_id": plant_id,
        "plant_seq": None,
        "parent_batch_id": None,
        "origin": "intake",
        "created_operation_id": None,
        "location_code": "nursery",
        "stage_code": None,
        "quarantined": False,
        "status": "open",
        "live_count": 0,
        "created_at": db_now(),
        "created_by": created_by,
        "closed_at": None,
        "voided_at": None,
        **overrides,
    }
    if values["plant_seq"] is None:
        values["plant_seq"] = next_plant_seq(plant_id)
    if values["created_operation_id"] is None:
        values["created_operation_id"] = make_operation(created_by)
    return values


def make_batch(plant_id: int, created_by: int, **overrides: object) -> int:
    with as_system():
        return as_int(
            insert("batches", batch_values(plant_id, created_by, **overrides))
        )


def reason_code(applies_to: str) -> str:
    """Any seeded reason for `applies_to` (`void`, `correction` or `loss`)."""
    code = fetch_one(
        "SELECT code FROM reasons WHERE applies_to = %s ORDER BY code LIMIT 1",
        [applies_to],
    )[0]
    assert isinstance(code, str)
    return code


def event_values(
    batch_id: int,
    user_id: int,
    action: str,
    reason: str | None = None,
    **overrides: object,
) -> dict[str, object]:
    """An event done and saved by `user_id`, dated now.

    `reason` names a reason list (`void`, `correction`, `loss`); a seeded
    reason from that list is used. `recorded_at` is left to the database.
    """
    return {
        "operation_id": make_operation(user_id),
        "batch_id": batch_id,
        "action": action,
        "qty_in": 0,
        "qty_out": 0,
        "counted_qty": None,
        "media_code": None,
        "stage_to": None,
        "staff_id": user_id,
        "recorded_by": user_id,
        "occurred_at": db_now(),
        "reason_code": reason_code(reason) if reason else None,
        "voids_event_id": None,
        "corrects_event_id": None,
        "note": "",
        "entered_via": "form",
        **overrides,
    }


def make_event(
    batch_id: int,
    user_id: int,
    action: str,
    reason: str | None = None,
    **overrides: object,
) -> int:
    values = event_values(batch_id, user_id, action, reason, **overrides)
    return as_int(insert("events", values))


def make_review(event_id: int, reviewer_id: int) -> int:
    values = {"event_id": event_id, "reviewer_id": reviewer_id, "note": ""}
    return as_int(insert("event_reviews", values))


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def user() -> int:
    return make_user("tech")


@pytest.fixture
def reviewer() -> int:
    return make_user("supervisor")


@pytest.fixture
def plant(user: int) -> int:
    return make_plant(user)


@pytest.fixture
def batch(plant: int, user: int) -> int:
    return make_batch(plant, user)
