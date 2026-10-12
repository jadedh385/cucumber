"""Reference codes can't be renamed; lists and vendors can't be deleted (design §4)."""

from django.db import migrations

from cucumber.core import db_rules

CODE_TABLES = ["genera", "stages", "media_codes", "locations", "reasons"]

RULES = [
    *(db_rules.no_delete(table) for table in [*CODE_TABLES, "vendors"]),
    *(db_rules.code_rename(table) for table in CODE_TABLES),
]


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0002_seed"),
        ("core", "0002_protection_functions"),
    ]

    operations = [migrations.RunSQL(rule.forward, rule.reverse) for rule in RULES]
