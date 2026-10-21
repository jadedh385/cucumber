"""The audit trail: the database writes it (U0.7 design §4, §5.3).

- `audit_log` gains `reason_code`, `via` and `db_user`; `reason` becomes
  `note`; `actor_id` may be empty on a `truncate` row only.
- `cucumber_audit()` on every audited table (§4.1), the reason rule on every
  switch-off (§4.2), a noticed TRUNCATE on every protected table (§4.4), the
  `audit_log_stamp` (§3.2), and `auth_user_no_delete` (D-07).
- `cucumber_app` may no longer write `auth_user_user_permissions` (review
  L1), and nobody but the owner may make TEMP tables here (review M1: the
  `cucumber` database had this from 01-roles.sh; test databases didn't).

Runs after references 0004 and accounts 0007, so the rows they seed need no
person. Undo refuses once the trail has a row: going back past this release
means restoring the copy (§5.5).
"""

import django.db.models.deletion
from django.apps.registry import Apps
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from cucumber.core import db_rules

FUNCTIONS = [
    db_rules.audit_function(name, body)
    for name, body in db_rules.AUDIT_FUNCTIONS.items()
]
TRIGGERS = [
    db_rules.AUDIT_LOG_STAMP,
    db_rules.no_delete("auth_user"),
    *(db_rules.audit(spec) for spec in db_rules.AUDITED_TABLES),
    *(db_rules.reason_required(spec) for spec in db_rules.SWITCH_OFFS),
    *(db_rules.truncate_noticed(table) for table in db_rules.TRUNCATE_NOTICED_TABLES),
]

GRANTS = """
REVOKE INSERT, UPDATE, DELETE ON auth_user_user_permissions FROM cucumber_app;
DO $$ BEGIN
  EXECUTE format('REVOKE TEMP ON DATABASE %I FROM PUBLIC', current_database());
END $$;
"""
# TEMP stays revoked on undo: production never had it (01-roles.sh).
UNDO_GRANTS = """
GRANT INSERT, UPDATE, DELETE ON auth_user_user_permissions TO cucumber_app;
"""


def refuse_if_audited(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Undo only while `audit_log` is empty (as core 0004 does for plant data)."""
    rows = apps.get_model("core", "AuditLog").objects.count()
    if rows:
        raise RuntimeError(
            f"Refusing to undo the audit trail: audit_log holds {rows} rows,"
            " and undoing would drop their columns. Restore the copy from"
            " before the release instead."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_flag_grants"),
        ("references", "0004_reason_lists"),
        ("accounts", "0007_system_account"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="auditlog", old_name="reason", new_name="note"
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="actor",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="reason",
            field=models.ForeignKey(
                db_column="reason_code",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="references.reason",
            ),
        ),
        # audit_log has no rows yet, so the empty default never stays.
        migrations.AddField(
            model_name="auditlog",
            name="via",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="auditlog",
            name="db_user",
            field=models.TextField(default=""),
        ),
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(actor__isnull=False) | models.Q(action="truncate"),
                name="audit_log_actor_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    action__in=(
                        "insert",
                        "update",
                        "delete",
                        "truncate",
                        "lock_lifted",
                        "guards_accepted",
                    )
                ),
                name="audit_log_action_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["table_name", "row_pk", "at"], name="audit_log_row_at"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["actor", "at"], name="audit_log_actor_at"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["at", "id"], name="audit_log_at_id"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["id"],
                name="audit_log_notices",
                condition=models.Q(action__in=("truncate", "guards_accepted")),
            ),
        ),
        *(migrations.RunSQL(sql.forward, sql.reverse) for sql in FUNCTIONS),
        *(migrations.RunSQL(sql.forward, sql.reverse) for sql in TRIGGERS),
        migrations.RunSQL(GRANTS, UNDO_GRANTS),
        # Last, so an undo checks before anything is dropped.
        migrations.RunPython(migrations.RunPython.noop, refuse_if_audited),
    ]
