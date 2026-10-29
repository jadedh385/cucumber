"""Are the database's protections on? (U0.7 design §8, AC15).

`GUARDS` lists every protection: the append-only, no-delete, reason and
audit triggers, their functions, `cucumber_app`'s grants, the app role
itself and the number generators of plants, batches and events (U0.8 §6).
Each entry names the migration that adds it, and is skipped until that
migration has run. `check()` compares the database with the list;
`cucumber_check_guards` prints what it finds, and the deploy stops on any
failure (steps 3b and 5b).

What each protection should look like is in `expected.py` (triggers,
function bodies, grants); this module reads the database and compares.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from cucumber.core import expected
from cucumber.core.audit import SYSTEM, audited, ssh_via, system_account
from cucumber.core.dates import BANGKOK
from cucumber.core.models import AuditLog

ACCEPT_VIA = "cucumber_check_guards"


class Kind(StrEnum):
    TRIGGER = "trigger"
    FUNCTION = "function"
    GRANT = "grant"
    APP_ROLE = "app role"
    TRUNCATE = "truncate"
    SEQUENCE = "sequence"  # U0.8 §6: a table's number generator


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
    *(Guard(Kind.SEQUENCE, table, expected.U08) for table in expected.SEQUENCES),
)


def applied_migrations() -> set[str]:
    applied = MigrationRecorder(connection).applied_migrations()
    return {f"{app}.{name}" for app, name in applied}


def migration_holes() -> list[str]:
    """Guard migrations not recorded as applied while a later one is (review #1).

    One that simply hasn't run yet (step 3b: the old database, the new code)
    has nothing after it applied. A hole means its protections would be
    skipped without a word: a restored copy, a hand-edited `django_migrations`.
    """
    loader = MigrationLoader(connection)
    applied = set(loader.applied_migrations)
    later = [key for key in applied if key in loader.graph.nodes]
    holes = []
    for name in sorted({guard.migration for guard in GUARDS}):
        key = tuple(name.split(".", 1))
        if key in applied or key not in loader.graph.nodes:
            continue
        if any(key in loader.graph.forwards_plan(node) for node in later):
            holes.append(
                f"migration {name} is not recorded as applied, but later ones are:"
                " its protections can't be checked"
            )
    return holes


def check() -> Report:
    """Every protection in `GUARDS` whose migration has run, checked (§8.1)."""
    applied = applied_migrations()
    due = [guard for guard in GUARDS if guard.migration in applied]
    names = {kind: {g.name for g in due if g.kind == kind} for kind in Kind}
    failures = [
        *migration_holes(),
        *trigger_failures(names[Kind.TRIGGER]),
        *function_failures(names[Kind.FUNCTION]),
        *grant_failures(names[Kind.GRANT]),
        *app_role_failures(names[Kind.APP_ROLE]),
        *(truncate_failures() if names[Kind.TRUNCATE] else []),
        *sequence_failures(names[Kind.SEQUENCE]),
    ]
    return Report(checked=len(due), failures=tuple(failures))


def fetch(sql: str, params: Any = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]


# ------------------------------------------------------------------ triggers

TRIGGERS_NOW = """
SELECT t.tgname, c.relname, p.proname, t.tgtype, t.tgenabled, t.tgnargs, t.tgargs,
       t.tgfoid = to_regprocedure('public.' || p.proname || '()')::oid,
       pn.nspname, t.tgqual IS NOT NULL, t.tgattr::text <> '', t.tgdeferrable
  FROM pg_trigger t
  JOIN pg_class c ON c.oid = t.tgrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
 WHERE NOT t.tgisinternal AND n.nspname = 'public'
"""
ON = {"O", "A"}  # fires in normal sessions (O: origin, A: always)


def trigger_arguments(count: int, raw: bytes | memoryview) -> tuple[str, ...]:
    return tuple(bytes(raw).decode().split("\x00")[:count])


@dataclass(frozen=True)
class Firing:
    """How a trigger fires, beyond what `expected.Trigger` pins (review #1)."""

    enabled: str
    is_ours: bool  # calls the zero-argument function of that name in `public`
    function_schema: str
    has_when: bool
    some_columns: bool  # UPDATE OF <columns>
    deferrable: bool


def trigger_failures(names: set[str]) -> list[str]:
    found = {
        name: (
            expected.Trigger(table, function, tgtype, trigger_arguments(count, raw)),
            Firing(enabled, ours, schema, has_when, some_columns, deferrable),
        )
        for (
            name, table, function, tgtype, enabled, count, raw,
            ours, schema, has_when, some_columns, deferrable,
        ) in fetch(TRIGGERS_NOW)
    }  # fmt: skip
    failures = []
    for name in sorted(names):
        want = expected.TRIGGERS[name][0]
        if name not in found:
            failures.append(f"trigger {name} on {want.table} is missing")
            continue
        have, firing = found[name]
        failures += trigger_differences(name, want, have, firing)
    return failures


def trigger_differences(
    name: str, want: expected.Trigger, have: expected.Trigger, firing: Firing
) -> list[str]:
    where = f"trigger {name} on {have.table}"
    problems = []
    if firing.enabled not in ON:
        state = "replica only" if firing.enabled == "R" else "disabled"
        problems.append(f"{where} is {state}")
    if have.function != want.function or not firing.is_ours:
        problems.append(
            f"{where} calls {firing.function_schema}.{have.function}(),"
            f" not public.{want.function}()"
        )
    if firing.has_when:
        problems.append(f"{where} has a WHEN condition, so it skips some rows")
    if firing.some_columns:
        problems.append(f"{where} fires on some columns only (UPDATE OF)")
    if firing.deferrable:
        problems.append(f"{where} is deferrable, so it can run late or never")
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

    Only an acceptance the owner wrote counts (review M3), and only for the
    rows it lists (review #2).
    """
    accepted = AuditLog.objects.filter(
        action="guards_accepted", db_user=expected.OWNER_ROLE
    ).values_list("after", flat=True)
    listed = {
        row_id
        for after in accepted
        for row_id in (after or {}).get("truncate_rows", [])
    }
    rows = (
        AuditLog.objects.filter(action="truncate").exclude(id__in=listed).order_by("id")
    )
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


# ----------------------------------------------------------------- sequences

# One row: does `id` have a default or identity, is the sequence there and
# owned by `id`, and may the app take numbers from it (U0.8 §6).
GENERATOR_NOW = """
SELECT a.atthasdef OR a.attidentity <> '',
       EXISTS (SELECT 1 FROM pg_depend d
                WHERE d.classid = 'pg_class'::regclass AND d.objid = s.oid
                  AND d.refobjid = a.attrelid AND d.refobjsubid = a.attnum
                  AND d.deptype IN ('a', 'i')),
       s.oid IS NOT NULL AND has_sequence_privilege(%(app)s, s.oid, 'USAGE')
  FROM pg_attribute a
  LEFT JOIN pg_class s ON s.oid = to_regclass(%(sequence)s) AND s.relkind = 'S'
 WHERE a.attrelid = to_regclass(%(table)s) AND a.attname = 'id'
"""
ONE = {"plants": "plant", "batches": "batch", "events": "event"}
BEHIND_HELP = 'see the release runbook, "Number generator behind"'


def sequence_failures(tables: set[str]) -> list[str]:
    failures = []
    for table in sorted(tables, key=list(expected.SEQUENCES).index):
        failures += generator_failures(table, expected.SEQUENCES[table])
    return failures


def generator_failures(table: str, sequence: str) -> list[str]:
    rows = fetch(
        GENERATOR_NOW,
        {"app": expected.APP_ROLE, "sequence": sequence, "table": f"public.{table}"},
    )
    if not rows:  # no table, or no id column: nothing to take numbers for
        return [f"{table}: its number generator {sequence} is missing"]
    [(has_default, owned, usable)] = rows
    failures = []
    if has_default:
        failures.append(
            f"{table}: id has a default again, so callers can choose it;"
            " see U0.8 design §5.1"
        )
    if not owned:
        return [*failures, f"{table}: its number generator {sequence} is missing"]
    if not usable:
        failures.append(
            f"{table}: {expected.APP_ROLE} can't take numbers from {sequence},"
            f" so every new {ONE[table]} fails"
        )
    return failures + generator_behind(table, sequence)


def generator_behind(table: str, sequence: str) -> list[str]:
    """The next value and `max(id)` in one statement (review M2)."""
    next_value = "CASE WHEN is_called THEN last_value + 1 ELSE last_value END"
    [(upcoming, highest)] = fetch(
        f"SELECT {next_value}, (SELECT coalesce(max(id), 0) FROM public.{table})"  # noqa: S608 (fixed names)
        f" FROM {sequence}"
    )
    if upcoming > highest:
        return []
    return [
        f"{table}: the next new one would get id {upcoming}, but id {highest} is"
        f" already used; {BEHIND_HELP}"
    ]


def session_user() -> str:
    return str(fetch("SELECT session_user")[0][0])


def require_owner() -> None:
    """Only the database owner's acceptance counts, so only it may write one."""
    if session_user() != expected.OWNER_ROLE:
        raise ValueError(
            f"Only the database owner ({expected.OWNER_ROLE}) can accept"
            " truncates: run this through the migrate service."
        )


def lock_trail() -> None:
    """Hold off other writers to the trail, so no truncate lands unseen."""
    with connection.cursor() as cursor:
        cursor.execute("LOCK TABLE audit_log IN SHARE ROW EXCLUSIVE MODE")


def accept_truncates(note: str, listed: Sequence[int]) -> list[str]:
    """Accept the listed TRUNCATEs (§8.2); returns what was accepted, as lines.

    Only rows in `listed` that are still noticed, read under a lock on the
    trail: a truncate that came after the listing stays noticed. Writes one
    `guards_accepted` row as System. Nothing to accept: nothing written, and
    no lines. A blank note, or a session that isn't the owner's, is a
    `ValueError`.
    """
    note = note.strip()
    if not note:
        raise ValueError("Say why the truncates are accepted.")
    require_owner()
    with audited(SYSTEM, via=ssh_via(ACCEPT_VIA)):
        lock_trail()
        noticed = [row for row in noticed_truncates() if row[0] in set(listed)]
        if not noticed:
            return []
        AuditLog.objects.create(
            actor=system_account(),
            table_name="audit_log",
            row_pk="",
            action="guards_accepted",
            after={"truncate_rows": [row_id for row_id, _, _ in noticed]},
            note=note,
            via=ssh_via(ACCEPT_VIA),
        )
    return [f"{table} ({when})" for _, table, when in noticed]
