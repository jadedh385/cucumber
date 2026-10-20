"""Helpers for the U0.7 audit-trail tests (design §13).

Audit rows are read with plain SQL, like the schema tests, and only those
written since the test began (`trail_start`): a database flush leaves
`truncate` rows behind (design §4.4).

`as_system()` names the System account for test set-up that writes audited
tables. It is used where needed, never for the whole suite (review H3), so
a service that forgets `audited()` still fails its test.

Loaded for every test through `pytest_plugins` in the root conftest.py.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from django.db import connection
from psycopg.pq import TransactionStatus

from cucumber.core.audit import SYSTEM_USERNAME, Reason

# `VIA_TEST` and `as_system` live with the row builders, which use them; the
# tests import them from here.
from cucumber.core.tests.rows import VIA_TEST as VIA_TEST
from cucumber.core.tests.rows import as_int, fetch_all, fetch_one, run
from cucumber.core.tests.rows import as_system as as_system

# The three reason lists references 0004 adds (design §5.1, Q1).
NEW_REASONS = {
    "deactivate": ["Left the company", "On leave", "Security", "Other"],
    "retire": ["No longer grown", "Mother plant lost", "Other"],
    "archive": ["No longer used", "Duplicate", "Entered by mistake", "Other"],
}
PDPA_CODE = "deactivate_pdpa_request"
LEFT_COMPANY = "deactivate_left_the_company"
NO_LONGER_GROWN = "retire_no_longer_grown"
NO_LONGER_USED = "archive_no_longer_used"
DUPLICATE_ENTRY = "void_duplicate_entry"
# Any reason will do for tests that deactivate on the way to something else.
LEFT_THE_COMPANY = Reason(LEFT_COMPANY)


@dataclass(frozen=True)
class AuditRow:
    """One `audit_log` row, with every column design §5.3 gives it."""

    id: int
    actor_id: int | None
    at: datetime
    table_name: str
    row_pk: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason_code: str | None
    note: str | None
    via: str
    db_user: str


AUDIT_COLUMNS = (
    "id, actor_id, at, table_name, row_pk, action, before, after,"
    " reason_code, note, via, db_user"
)


def as_json(value: object) -> dict[str, Any] | None:
    if value is None or isinstance(value, dict):
        return value
    loaded = json.loads(str(value))
    assert isinstance(loaded, dict), f"expected a JSON object, got {value!r}"
    return loaded


def as_time(value: object) -> datetime:
    assert isinstance(value, datetime), f"expected a time, got {value!r}"
    return value


def audit_mark() -> int:
    """The newest audit row's id now (0 when there is none)."""
    return as_int(fetch_one("SELECT coalesce(max(id), 0) FROM audit_log")[0])


def audit_rows_since(mark: int, table: str | None = None) -> list[AuditRow]:
    """Rows written after `mark`, oldest first; only `table`'s when given."""
    rows = fetch_all(
        f"SELECT {AUDIT_COLUMNS} FROM audit_log"  # noqa: S608 (a constant)
        " WHERE id > %s AND (%s::text IS NULL OR table_name = %s) ORDER BY id",
        [mark, table, table],
    )
    return [
        AuditRow(
            id=as_int(row[0]),
            actor_id=None if row[1] is None else as_int(row[1]),
            at=as_time(row[2]),
            table_name=str(row[3]),
            row_pk=str(row[4]),
            action=str(row[5]),
            before=as_json(row[6]),
            after=as_json(row[7]),
            reason_code=None if row[8] is None else str(row[8]),
            note=None if row[9] is None else str(row[9]),
            via=str(row[10]),
            db_user=str(row[11]),
        )
        for row in rows
    ]


def only_row(mark: int, table: str) -> AuditRow:
    """The one audit row for `table` since `mark`; fails if there are more."""
    rows = audit_rows_since(mark, table)
    assert len(rows) == 1, f"expected one {table} audit row, got {rows}"
    return rows[0]


@pytest.fixture
def trail_start(db: None) -> int:
    """The audit mark when the test began: count only rows written after it."""
    return audit_mark()


# ----------------------------------------------------------- naming a person


SETTINGS = ("actor_id", "via", "reason_code", "note")


@contextmanager
def named_in_sql(
    actor_id: int | None,
    *,
    via: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> Iterator[None]:
    """Name a person the way raw SQL would: `set_config(…, true)` (design §2).

    Inside a test's transaction the values would outlive the block, so they
    are emptied again on the way out, unless an error has aborted the
    transaction: its rollback empties them.
    """
    values = {
        "actor_id": None if actor_id is None else str(actor_id),
        "via": via,
        "reason_code": reason_code,
        "note": note,
    }
    try:
        for name, value in values.items():
            if value is not None:
                run("SELECT set_config(%s, %s, true)", [f"cucumber.{name}", value])
        yield
    finally:
        if not in_failed_transaction():
            for name in SETTINGS:
                run("SELECT set_config(%s, '', true)", [f"cucumber.{name}"])


def in_failed_transaction() -> bool:
    """True after an error, until the transaction or savepoint is rolled back."""
    raw = connection.connection
    return raw is not None and raw.info.transaction_status == TransactionStatus.INERROR


def setting(name: str) -> str:
    """A `cucumber.*` setting now, '' when unset."""
    value = fetch_one("SELECT current_setting(%s, true)", [f"cucumber.{name}"])[0]
    return "" if value is None else str(value)


# --------------------------------------------------------- System and flushes


def system_id() -> int:
    """The System account's id now (design §5.2)."""
    row = fetch_one("SELECT id FROM auth_user WHERE username = %s", [SYSTEM_USERNAME])
    return as_int(row[0])


def restore_audit_rows() -> None:
    """The System account and the new reason lists, for committing tests.

    A flush empties `auth_user` and `reasons` (design §13, review H2). The
    rows are put back with the triggers off: nobody exists yet to name.
    """
    run("ALTER TABLE auth_user DISABLE TRIGGER USER")
    try:
        run(
            "INSERT INTO auth_user (password, is_superuser, username, first_name,"
            " last_name, email, is_staff, is_active, date_joined)"
            " VALUES ('!', false, %s, 'System', '', %s, false, false, now())"
            " ON CONFLICT (username) DO NOTHING",
            [SYSTEM_USERNAME, SYSTEM_USERNAME],
        )
    finally:
        run("ALTER TABLE auth_user ENABLE TRIGGER USER")
    run("ALTER TABLE reasons DISABLE TRIGGER USER")
    try:
        for applies_to, labels in NEW_REASONS.items():
            for label in labels:
                code = f"{applies_to}_{label.lower().replace(' ', '_')}"
                run(
                    "INSERT INTO reasons (code, label, applies_to, active)"
                    " VALUES (%s, %s, %s, true) ON CONFLICT DO NOTHING",
                    [code, label, applies_to],
                )
        run(
            "INSERT INTO reasons (code, label, applies_to, active)"
            " VALUES (%s, 'PDPA request', 'deactivate', false)"
            " ON CONFLICT DO NOTHING",
            [PDPA_CODE],
        )
    finally:
        run("ALTER TABLE reasons ENABLE TRIGGER USER")


@pytest.fixture(autouse=True)
def system_after_a_flush(request: pytest.FixtureRequest) -> None:
    """A committing test starts after a flush: put System and the lists back.

    Only rows, never a person named (review H3): a service that forgets
    `audited()` still fails. Other tests see the migrated rows.
    """
    marker = request.node.get_closest_marker("django_db")
    committing = (marker is not None and marker.kwargs.get("transaction")) or any(
        name in request.fixturenames for name in ("transactional_db", "live_server")
    )
    if committing:
        request.getfixturevalue("transactional_db")
        restore_audit_rows()


def accept_noticed_truncates() -> None:
    """Accept any flush's `truncate` rows, as `--accept` would (design §8.2).

    Written as the owner (the tests' own login), so it counts (design §5.4).
    """
    noticed = [
        as_int(row[0])
        for row in fetch_all("SELECT id FROM audit_log WHERE action = 'truncate'")
    ]
    if not noticed:
        return
    restore_audit_rows()  # a flush that left these rows also removed System
    run(
        "INSERT INTO audit_log (actor_id, table_name, row_pk, action, after, note, via)"
        " VALUES (%s, 'audit_log', '', 'guards_accepted', %s, 'test flushes', %s)",
        [system_id(), json.dumps({"truncate_rows": noticed}), VIA_TEST],
    )
