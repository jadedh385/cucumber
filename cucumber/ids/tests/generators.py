"""Helpers for the U0.8 number-generator tests (design §5, §12).

A generator never rolls back with a test (review M5), so a test that moves
one puts it back afterwards (`generators_put_back`), on a throwaway
connection of its own: the test's connection may be inside a transaction
or logged in as the app user. No test expects an absolute id; each one
compares ids with each other or with `next_id()`.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import psycopg
import pytest
from django.db import connection

from cucumber.core import expected
from cucumber.core.tests.rows import AppConnection, as_int, fetch_one

TABLES = tuple(expected.SEQUENCES)  # plants, batches, events: the lock order
# A number well past anything a test makes, for an id the caller chooses.
AHEAD = 100_000
Position = tuple[int, bool]  # (last_value, is_called)


def next_id(table: str) -> int:
    """The id the table's generator gives next, without taking it."""
    sequence = expected.SEQUENCES[table]  # a fixed name, never typed text
    next_value = "CASE WHEN is_called THEN last_value + 1 ELSE last_value END"
    row = fetch_one(f"SELECT {next_value} FROM {sequence}")  # noqa: S608
    return as_int(row[0])


def ids_in(table: str) -> set[int]:
    """Every id in the table now."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM {table}")  # noqa: S608 (a fixed name)
        return {as_int(row[0]) for row in cursor.fetchall()}


@contextmanager
def owner_connection() -> Iterator[AppConnection]:
    """A throwaway connection as the tables' owner, committing each statement."""
    settings = connection.settings_dict
    owner = psycopg.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"],
        port=settings["PORT"],
        autocommit=True,
    )
    try:
        yield owner
    finally:
        owner.close()


def positions(db: AppConnection) -> dict[str, Position]:
    found = {}
    for table, sequence in expected.SEQUENCES.items():
        row = db.execute(
            f"SELECT last_value, is_called FROM {sequence}".encode()  # noqa: S608
        ).fetchone()
        assert row is not None
        found[table] = (as_int(row[0]), bool(row[1]))
    return found


def put_back(db: AppConnection, where: Mapping[str, Position]) -> None:
    for table, (last_value, is_called) in where.items():
        db.execute(
            b"SELECT setval(%s, %s, %s)",
            [expected.SEQUENCES[table], last_value, is_called],
        )


@pytest.fixture
def generators_put_back() -> Iterator[None]:
    """The three generators, put back where they were after the test."""
    with owner_connection() as owner:
        before = positions(owner)
    yield
    with owner_connection() as owner:
        put_back(owner, before)


def name_system_on(app_db: AppConnection, system_id: int) -> None:
    """Raw SQL on the app's connection names System for the trail (U0.7 §2)."""
    app_db.execute(
        b"SELECT set_config('cucumber.actor_id', %s, false)", [str(system_id)]
    )
