"""Shared protection trigger functions; the audit log is insert-only (§4)."""

from django.db import migrations

from cucumber.core import db_rules

AUDIT_APPEND_ONLY = db_rules.append_only("audit_log")


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunSQL(db_rules.FUNCTIONS, db_rules.DROP_FUNCTIONS),
        migrations.RunSQL(AUDIT_APPEND_ONLY.forward, AUDIT_APPEND_ONLY.reverse),
    ]
