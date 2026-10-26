"""Container types are protected like the other lists; the stage order and the
two locations change by migration only (U0.9 design §2.3).

- `container_types`: no delete, no code rename, an audit row per change, an
  `archive` reason to switch one off, a `truncate` row if emptied.
- `cucumber_owner_only()` and its two triggers: `stages_order_fixed` (no new
  stage, no change of `sort_order`) and `locations_fixed` (no new location,
  no change of `active`). Only `cucumber_owner`, who runs migrations, is let
  through (spec AC5, AC9).
- An explicit `SELECT, INSERT, UPDATE` grant to `cucumber_app`; the default
  privileges give only `SELECT, INSERT` (U0.8 review L2).

The triggers lock `stages` and `locations`, which every batch and event
points at, so it waits at most 5 s for them, both ways. Undo drops the seven
triggers and the function, and takes back the UPDATE grant: the table is
then as `0006` made it.
"""

from django.db import migrations

from cucumber.core import db_rules

LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s';"
TABLE = "container_types"
GRANT = db_rules.Sql(
    forward=f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO cucumber_app;",
    reverse=f"REVOKE UPDATE ON {TABLE} FROM cucumber_app;",
)

RULES = [
    *(
        db_rules.audit_function(name, body)
        for name, body in db_rules.U09_FUNCTIONS.items()
    ),
    *(db_rules.no_delete(table) for table in db_rules.U09_REFERENCE_LISTS),
    *(db_rules.code_rename(table) for table in db_rules.U09_REFERENCE_LISTS),
    *(db_rules.audit(spec) for spec in db_rules.U09_AUDITED),
    *(db_rules.reason_required(spec) for spec in db_rules.U09_SWITCH_OFFS),
    *(db_rules.truncate_noticed(table) for table in db_rules.U09_TRUNCATE_NOTICED),
    *(db_rules.owner_only(spec) for spec in db_rules.OWNER_ONLY),
    GRANT,
]


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0006_container_types"),
        ("core", "0007_id_sequences"),
    ]

    operations = [
        migrations.RunSQL(LOCK_TIMEOUT, migrations.RunSQL.noop),
        *(migrations.RunSQL(rule.forward, rule.reverse) for rule in RULES),
        # Last, so the undo sets it before it drops anything.
        migrations.RunSQL(migrations.RunSQL.noop, LOCK_TIMEOUT),
    ]
