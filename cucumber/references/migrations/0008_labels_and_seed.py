"""The stage labels, the Seed stage and the container types (U0.9 design §2.4).

- `S0` Seed: first in the order (0), no subculture interval, active (AC1).
- A real label for every other stage. Media codes keep their codes as
  labels (Q1): the Admin labels them later, on the U0.10 list page.
- Seven container types, all active (Q2).

It checks the System account exists first, so it can't stop halfway on
`audit_actor_required` (review L5), then names System as the one making the
change (`db_rules.AS_SYSTEM_SQL`, `via = 'migration'`), so each change has
its own audit row.

Undo refuses, saying to restore the copy, while a batch or an event is at
`S0`, while an audit row newer than this migration's last run names one of
its codes (an Admin change), or while a list holds a code nobody seeded
(review M5, G4 D1). Otherwise it puts the labels back and removes `S0` and the
container types, writing a `delete` audit row for each by hand: the list
tables' audit trigger doesn't fire on DELETE.
"""

from django.apps.registry import Apps
from django.db import IntegrityError, connection, migrations, transaction
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.utils import CursorWrapper

from cucumber.core import db_rules

# core.audit.SYSTEM_USERNAME; a migration doesn't import app code.
SYSTEM_USERNAME = "system@cucumber.invalid"
VIA = "migration"

SEED = "S0"
STAGE_LABELS = {
    "P0": "Sterilization / new species introduction",
    "P1": "Multiplication",
    "P2": "Growth",
    "A1": "Acclimatization (hardening off)",
    "P4": "Growth maturity (potted plants)",
    "P3": "Transport",
    "T1": "Digital content",
    "C0": "Clean",
}
CONTAINER_TYPES = {
    "flask_250ml": "250 ml flask",
    "magenta_box": "Magenta box",
    "pot_4in": "4-inch pot",
    "grow_bag": "Grow bag",
    "jar": "Jar",
    "disposable_cup": "Disposable cup",
    "tray": "Tray",
}
# references 0002's seeds: any other code was added by the Admin since.
SEEDED_MEDIA_CODES = ["M001", "M002", "M003", "M004", "G001", "G002", "R001"]
SEEDED_GENERA = ["HYA", "PHL", "ALC"]

# The codes this migration adds or relabels, by table.
CHANGED = {
    "stages": [SEED, *STAGE_LABELS],
    "container_types": list(CONTAINER_TYPES),
}
# The codes each list may hold before the undo, by table.
SEEDED = {
    "container_types": list(CONTAINER_TYPES),
    "media_codes": SEEDED_MEDIA_CODES,
    "genera": SEEDED_GENERA,
}
REFUSED = (
    "Refusing to undo the U0.9 labels and seeds: {blockers}. Restore the copy"
    " from before the release instead."
)


def cursor_for(schema_editor: BaseDatabaseSchemaEditor | None) -> CursorWrapper:
    database = schema_editor.connection if schema_editor else connection
    return database.cursor()


def as_system(cursor: CursorWrapper) -> None:
    """Name System for every audit row from here on, or stop naming it."""
    cursor.execute("SELECT 1 FROM auth_user WHERE username = %s", [SYSTEM_USERNAME])
    if cursor.fetchone() is None:
        raise RuntimeError(
            f"The System account ({SYSTEM_USERNAME}) is missing, so this"
            " migration can't say who made its changes. Run accounts 0007 or"
            " restore the account, then run it again."
        )
    cursor.execute(db_rules.AS_SYSTEM_SQL)


def label_and_seed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    with cursor_for(schema_editor) as cursor:
        as_system(cursor)
        # The first row this run writes: the undo counts changes after it.
        cursor.execute(
            "INSERT INTO stages"
            " (code, label, sort_order, default_subculture_days, active)"
            " VALUES (%s, 'Seed', 0, NULL, true)",
            [SEED],
        )
        for code, label in STAGE_LABELS.items():
            cursor.execute(
                "UPDATE stages SET label = %s WHERE code = %s", [label, code]
            )
        # One already there is kept as it is (Owner, session 2): on a server
        # the table is empty here, but a test may have restored one.
        for code, label in CONTAINER_TYPES.items():
            cursor.execute(
                "INSERT INTO container_types (code, label) VALUES (%s, %s)"
                " ON CONFLICT (code) DO NOTHING",
                [code, label],
            )


# ------------------------------------------------------------------- undo
def seed_in_use(cursor: CursorWrapper) -> list[str]:
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM batches WHERE stage_code = %s)"
        " OR EXISTS (SELECT 1 FROM events WHERE stage_to = %s)",
        [SEED, SEED],
    )
    row = cursor.fetchone()
    return [f"{SEED} (a batch or an event is at it)"] if row and row[0] else []


def changed_since(cursor: CursorWrapper) -> list[str]:
    """Codes with an audit row newer than the latest run, other than a migration's.

    The latest run starts with its `S0` insert; rows from before it (a
    staging walkthrough, an earlier forward and undo) don't count (M5).
    With no such row (a test database after a flush), nothing is newer.
    """
    cursor.execute(
        "SELECT max(id) FROM audit_log WHERE table_name = 'stages'"
        " AND row_pk = %s AND action = 'insert' AND via = %s",
        [SEED, VIA],
    )
    row = cursor.fetchone()
    first = row[0] if row else None
    if first is None:
        return []
    found: list[str] = []
    for table, codes in CHANGED.items():
        cursor.execute(
            "SELECT DISTINCT row_pk FROM audit_log WHERE id >= %s"
            " AND via IS DISTINCT FROM %s"
            " AND table_name = %s AND row_pk = ANY(%s) ORDER BY row_pk",
            [first, VIA, table, codes],
        )
        found += [f"{code} (changed since)" for (code,) in cursor.fetchall()]
    return found


def added_since(cursor: CursorWrapper) -> list[str]:
    """Codes nobody seeded.

    An added container type would make `0006`'s undo refuse after this one
    ran, half undone (M5). An added media code or genus wouldn't, but an undo
    after the Admin has used the lists isn't rehearsed: restore instead
    (G4 D1, Owner).
    """
    found: list[str] = []
    for table, codes in SEEDED.items():
        cursor.execute(
            f"SELECT code FROM {table} WHERE code <> ALL(%s) ORDER BY code",  # noqa: S608 (constants)
            [codes],
        )
        found += [f"{code} (added to {table})" for (code,) in cursor.fetchall()]
    return found


def refuse_if_anything_newer(cursor: CursorWrapper) -> None:
    blockers = [*seed_in_use(cursor), *changed_since(cursor), *added_since(cursor)]
    if blockers:
        raise RuntimeError(REFUSED.format(blockers=", ".join(blockers)))


def deferred_links_to(cursor: CursorWrapper, table: str) -> list[str]:
    """Names of the deferred foreign keys that point at `table`: the ones
    set `IMMEDIATE` for a delete and put back to `DEFERRED` after it."""
    cursor.execute(
        "SELECT quote_ident(conname) FROM pg_constraint"
        " WHERE contype = 'f' AND condeferrable AND condeferred"
        " AND confrelid = %s::regclass ORDER BY conname",
        [f"public.{table}"],
    )
    return [str(row[0]) for row in cursor.fetchall()]


def delete_and_record(cursor: CursorWrapper, table: str, codes: list[str]) -> None:
    """Delete `codes` from `table`, with one `delete` audit row each, as System."""
    cursor.execute(
        f"WITH gone AS (DELETE FROM {table} WHERE code = ANY(%s) RETURNING *)"  # noqa: S608 (constants)
        " INSERT INTO audit_log (actor_id, table_name, row_pk, action, before, via)"
        " SELECT current_setting('cucumber.actor_id')::integer, %s, gone.code,"
        " 'delete', to_jsonb(gone), %s FROM gone",
        [codes, table, VIA],
    )


def remove_seeded(cursor: CursorWrapper, table: str, codes: list[str]) -> None:
    """`delete_and_record` with `<table>_no_delete` off for that one statement.

    ALTER TABLE waits for no deferred check: run the ones on `table` now, by
    name, so a pending check elsewhere isn't run or blamed (review L1).
    """
    links = deferred_links_to(cursor, table)
    if links:
        cursor.execute(f"SET CONSTRAINTS {', '.join(links)} IMMEDIATE")
    cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_no_delete")
    try:
        # A savepoint, so the refusal leaves the transaction usable.
        with transaction.atomic(using=cursor.db.alias):
            delete_and_record(cursor, table, codes)
    except IntegrityError as error:
        raise RuntimeError(
            REFUSED.format(blockers=f"a later table still points at {table} ({error})")
        ) from error
    finally:
        cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_no_delete")
        if links:
            cursor.execute(f"SET CONSTRAINTS {', '.join(links)} DEFERRED")


def undo_label_and_seed(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    with cursor_for(schema_editor) as cursor:
        refuse_if_anything_newer(cursor)
        as_system(cursor)
        cursor.execute(
            "UPDATE stages SET label = code WHERE code = ANY(%s)", [list(STAGE_LABELS)]
        )
        remove_seeded(cursor, "stages", [SEED])
        remove_seeded(cursor, "container_types", list(CONTAINER_TYPES))


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0007_container_type_rules"),
        ("accounts", "0007_system_account"),  # System, who makes the changes
    ]

    operations = [migrations.RunPython(label_and_seed, undo_label_and_seed)]
