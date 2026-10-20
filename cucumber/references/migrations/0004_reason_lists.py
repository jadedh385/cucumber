"""The reason lists for switching something off (U0.7 design §5.1, AC11, Q1 a).

`deactivate` (staff accounts), `retire` (plants) and `archive` (reference
lists and vendors). Plant Void reuses the `void` list. The PDPA reason is
seeded switched off: only `cucumber_anonymise` uses it, no page offers it.

Undo refuses while an event or an audit row uses one of the new codes.
Otherwise it removes only the seeded rows (the no-delete trigger is off for
that one statement) and narrows the list check again.
"""

from django.apps.registry import Apps
from django.db import connection, migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.utils import CursorWrapper

OLD_LISTS = ["void", "correction", "loss"]
NEW_LISTS = {
    "deactivate": ["Left the company", "On leave", "Security", "Other"],
    "retire": ["No longer grown", "Mother plant lost", "Other"],
    "archive": ["No longer used", "Duplicate", "Entered by mistake", "Other"],
}
# label, list: seeded switched off.
SWITCHED_OFF = [("PDPA request", "deactivate")]


def reason_code(applies_to: str, label: str) -> str:
    """references 0002's `reason_code`; a migration doesn't import app code."""
    return f"{applies_to}_{label.lower().replace(' ', '_')}"


def seeded() -> list[tuple[str, str, str, bool]]:
    """(code, label, list, active) for every row this migration adds."""
    rows = [
        (reason_code(applies_to, label), label, applies_to, True)
        for applies_to, labels in NEW_LISTS.items()
        for label in labels
    ]
    rows += [
        (reason_code(applies_to, label), label, applies_to, False)
        for label, applies_to in SWITCHED_OFF
    ]
    return rows


def applies_to_check(lists: list[str]) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=models.Q(applies_to__in=lists), name="reasons_applies_to_valid"
    )


def seed_lists(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    reason = apps.get_model("references", "Reason")
    reason.objects.bulk_create(
        reason(code=code, label=label, applies_to=applies_to, active=active)
        for code, label, applies_to, active in seeded()
    )


def codes_in_use(cursor: CursorWrapper, codes: list[str]) -> list[str]:
    """The new codes an event or an audit row points at.

    `audit_log.reason_code` exists only while core 0006 is applied.
    """
    cursor.execute(
        "SELECT reason_code FROM events WHERE reason_code = ANY(%s)", [codes]
    )
    used = {str(row[0]) for row in cursor.fetchall()}
    cursor.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'audit_log' AND column_name = 'reason_code'"
    )
    if cursor.fetchone() is not None:
        cursor.execute(
            "SELECT reason_code FROM audit_log WHERE reason_code = ANY(%s)", [codes]
        )
        used |= {str(row[0]) for row in cursor.fetchall()}
    return sorted(used)


def unseed_lists(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    """Remove the seeded rows, unless something already uses one (§5.1)."""
    codes = [code for code, *_ in seeded()]
    database = schema_editor.connection if schema_editor else connection
    with database.cursor() as cursor:
        used = codes_in_use(cursor, codes)
        if used:
            raise RuntimeError(
                "Refusing to undo the U0.7 reason lists: these reasons are"
                f" already used: {', '.join(used)}. Restore the copy from before"
                " the release instead."
            )
        # ALTER TABLE waits for no deferred check: run them now.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE reasons DISABLE TRIGGER reasons_no_delete")
        cursor.execute("DELETE FROM reasons WHERE code = ANY(%s)", [codes])
        cursor.execute("ALTER TABLE reasons ENABLE TRIGGER reasons_no_delete")
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")


class Migration(migrations.Migration):
    dependencies = [("references", "0003_rules")]

    operations = [
        migrations.AlterField(
            model_name="reason",
            name="applies_to",
            field=models.TextField(
                choices=[
                    ("void", "Void"),
                    ("correction", "Correction"),
                    ("loss", "Loss"),
                    ("retire", "Retire"),
                    ("archive", "Archive"),
                    ("deactivate", "Deactivate"),
                ]
            ),
        ),
        migrations.RemoveConstraint(
            model_name="reason", name="reasons_applies_to_valid"
        ),
        migrations.AddConstraint(
            model_name="reason",
            # ReasonList's order, so the model and this migration agree.
            constraint=applies_to_check(
                [*OLD_LISTS, "retire", "archive", "deactivate"]
            ),
        ),
        migrations.RunPython(seed_lists, unseed_lists),
    ]
