"""Are the database's protections on? (U0.7 design §8, AC15).

`GUARDS` lists every protection: the append-only, no-delete, reason and
audit triggers, their functions, `cucumber_app`'s grants and the app role
itself. Each entry names the migration that adds it, and is skipped until
that migration has run. `check()` compares the database with the list;
`cucumber_check_guards` prints what it finds, and the deploy stops on any
failure (steps 3b and 5b).

What each protection should look like is in `expected.py` (triggers,
function bodies, grants); this module reads the database and compares.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from cucumber.core import expected
from cucumber.core.audit import SYSTEM, audited, system_account
from cucumber.core.models import AuditLog

BANGKOK = ZoneInfo("Asia/Bangkok")
ACCEPT_VIA = "cucumber_check_guards"


class Kind(StrEnum):
    TRIGGER = "trigger"
    FUNCTION = "function"
    GRANT = "grant"
    APP_ROLE = "app role"
    TRUNCATE = "truncate"


@dataclass(frozen=True)
class Guard:
    """One protection: its kind, its name (a trigger, a function, a table)."""

    kind: Kind
    name: str
    migration: str  # "app_label.0006_name": skipped until it has run


@dataclass(frozen=True)
class Report:
    """What `check()` found: one plain line per failure (design §8.1)."""

    checked: int
    failures: tuple[str, ...]


GUARDS: tuple[Guard, ...] = (
    *(
        Guard(Kind.TRIGGER, name, migration)
        for name, (_, migration) in expected.TRIGGERS.items()
    ),
    *(
        Guard(Kind.FUNCTION, name, migration)
        for name, (_, migration) in expected.FUNCTIONS.items()
    ),
    *(
        Guard(Kind.GRANT, table, migration)
        for table, (_, migration) in expected.PRIVILEGES.items()
    ),
    *(
        Guard(Kind.APP_ROLE, name, check.migration)
        for name, check in expected.APP_ROLE_CHECKS.items()
    ),
    Guard(Kind.TRUNCATE, "audit_log", expected.U07),
)


def applied_migrations() -> set[str]:
    applied = MigrationRecorder(connection).applied_migrations()
    return {f"{app}.{name}" for app, name in applied}


def check() -> Report:
    """Every protection in `GUARDS` whose migration has run, checked (§8.1)."""
    applied = applied_migrations()
    due = [guard for guard in GUARDS if guard.migration in applied]
    names = {kind: {g.name for g in due if g.kind == kind} for kind in Kind}
    failures = [
        *trigger_failures(names[Kind.TRIGGER]),
        *function_failures(names[Kind.FUNCTION]),
        *grant_failures(names[Kind.GRANT]),
        *app_role_failures(names[Kind.APP_ROLE]),
        *(truncate_failures() if names[Kind.TRUNCATE] else []),
    ]
    return Report(checked=len(due), failures=tuple(failures))


def fetch(sql: str, params: Any = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]


# ------------------------------------------------------------------ triggers

TRIGGERS_NOW = """
SELECT t.tgname, c.relname, p.proname, t.tgtype, t.tgenabled, t.tgnargs, t.tgargs
  FROM pg_trigger t
  JOIN pg_class c ON c.oid = t.tgrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_proc p ON p.oid = t.tgfoid
 WHERE NOT t.tgisinternal AND n.nspname = 'public'
"""
ON = {"O", "A"}  # fires in normal sessions (O: origin, A: always)


def trigger_arguments(count: int, raw: bytes | memoryview) -> tuple[str, ...]:
    return tuple(bytes(raw).decode().split("\x00")[:count])


def trigger_failures(names: set[str]) -> list[str]:
    found = {
        name: (
            expected.Trigger(table, function, tgtype, trigger_arguments(count, raw)),
            enabled,
        )
        for name, table, function, tgtype, enabled, count, raw in fetch(TRIGGERS_NOW)
    }
    failures = []
    for name in sorted(names):
        want = expected.TRIGGERS[name][0]
        if name not in found:
            failures.append(f"trigger {name} on {want.table} is missing")
            continue
        have, enabled = found[name]
        failures += trigger_differences(name, want, have, enabled)
    return failures


def trigger_differences(
    name: str, want: expected.Trigger, have: expected.Trigger, enabled: str
) -> list[str]:
    where = f"trigger {name} on {have.table}"
    problems = []
    if enabled not in ON:
        state = "replica only" if enabled == "R" else "disabled"
        problems.append(f"{where} is {state}")
    if have.function != want.function:
        problems.append(f"{where} calls {have.function}(), not {want.function}()")
    if (have.table, have.tgtype) != (want.table, want.tgtype):
        problems.append(f"{where} fires on the wrong table or at the wrong time")
    if have.arguments != want.arguments:
        problems.append(f"{where} has changed arguments: {have.arguments}")
    return problems


# ----------------------------------------------------------------- functions

FUNCTIONS_NOW = """
SELECT p.proname, md5(p.prosrc), p.prosecdef, coalesce(p.proconfig, '{}')
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
"""


def function_failures(names: set[str]) -> list[str]:
    found = {
        name: (digest, definer, tuple(config))
        for name, digest, definer, config in fetch(FUNCTIONS_NOW)
    }
    failures = []
    for name in sorted(names):
        want = expected.FUNCTIONS[name][0]
        if name not in found:
            failures.append(f"function {name}() is missing")
            continue
        digest, definer, config = found[name]
        if digest != want.md5:
            failures.append(f"function {name}() has a changed body")
        if definer:
            failures.append(f"function {name}() runs as its owner (SECURITY DEFINER)")
        if config != want.config:
            failures.append(f"function {name}() has changed settings: {config}")
    return failures


# -------------------------------------------------------------------- grants

PRIVILEGES_NOW = """
SELECT c.relname, p.privilege,
       has_table_privilege(%(app)s, c.oid, p.privilege),
       p.privilege = ANY(%(column_kinds)s)
         AND has_any_column_privilege(%(app)s, c.oid, p.privilege)
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 CROSS JOIN unnest(%(kinds)s::text[]) AS p(privilege)
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
"""


def privileges_now() -> dict[str, tuple[set[str], set[str]]]:
    """Each table: (table privileges, privileges on any column) of the app."""
    rows = fetch(
        PRIVILEGES_NOW,
        {
            "app": expected.APP_ROLE,
            "kinds": list(expected.TABLE_PRIVILEGES),
            "column_kinds": list(expected.COLUMN_PRIVILEGES),
        },
    )
    tables: dict[str, tuple[set[str], set[str]]] = {}
    for table, privilege, on_table, on_column in rows:
        whole, columns = tables.setdefault(table, (set(), set()))
        if on_table:
            whole.add(privilege)
        if on_column:
            columns.add(privilege)
    return tables


def grant_failures(names: set[str]) -> list[str]:
    failures = []
    for table, (whole, columns) in sorted(privileges_now().items()):
        if table not in expected.PRIVILEGES:
            failures.append(
                f"table {table} isn't known to the guard check: add its grants"
                " to core/expected.py"
            )
        elif table in names:
            failures += table_grant_differences(table, whole, columns)
    return failures


def table_grant_differences(
    table: str, whole: set[str], columns: set[str]
) -> list[str]:
    want = expected.PRIVILEGES[table][0]
    if whole != want:
        return [
            f"table {table}: {expected.APP_ROLE} may {', '.join(sorted(whole))},"
            f" should be {', '.join(sorted(want))}"
        ]
    if columns - whole:
        extra = ", ".join(sorted(columns - whole))
        return [f"table {table}: {expected.APP_ROLE} has column grants for {extra}"]
    return []


# ------------------------------------------------------------------ app role


def app_role_failures(names: set[str]) -> list[str]:
    roles = {"app": expected.APP_ROLE, "owner": expected.OWNER_ROLE}
    return [
        expected.APP_ROLE_CHECKS[name].problem
        for name in sorted(names)
        if fetch(expected.APP_ROLE_CHECKS[name].sql, roles)[0][0]
    ]


# ------------------------------------------------------------------ TRUNCATE


def noticed_truncates() -> list[tuple[int, str, str]]:
    """(id, table, "<Bangkok time>, <via>") of truncates not yet accepted (§8.2).

    Only an acceptance the owner wrote counts (review M3).
    """
    accepted = AuditLog.objects.filter(
        action="guards_accepted", db_user=expected.OWNER_ROLE
    )
    last = accepted.order_by("-id").values_list("id", flat=True).first() or 0
    rows = AuditLog.objects.filter(action="truncate", id__gt=last).order_by("id")
    return [
        (row.id, row.table_name, f"{in_bangkok(row)}, {row.via}")
        for row in rows.only("id", "table_name", "at", "via")
    ]


def in_bangkok(row: AuditLog) -> str:
    return row.at.astimezone(BANGKOK).strftime("%Y-%m-%d %H:%M")


def truncate_failures() -> list[str]:
    return [
        f"table {table} was truncated ({when}); if that was you, run"
        ' cucumber_check_guards --accept "why"'
        for _, table, when in noticed_truncates()
    ]


def accept_truncates(note: str) -> list[str]:
    """Accept the noticed TRUNCATEs (§8.2); returns what was accepted, as lines.

    Writes one `guards_accepted` row as System. Nothing noticed: nothing
    written, and no lines. A blank note is a `ValueError`.
    """
    note = note.strip()
    if not note:
        raise ValueError("Say why the truncates are accepted.")
    with audited(SYSTEM, via=ACCEPT_VIA):
        noticed = noticed_truncates()
        if not noticed:
            return []
        AuditLog.objects.create(
            actor=system_account(),
            table_name="audit_log",
            row_pk="",
            action="guards_accepted",
            after={"truncate_rows": [row_id for row_id, _, _ in noticed]},
            note=note,
            via=ACCEPT_VIA,
        )
    return [f"{table} ({when})" for _, table, when in noticed]
