"""Refuse to undo the schema while it holds data (G4 review, H1; design §6).

Undoing U0.2a's migrations drops its tables, and triggers don't fire on a
drop, so history would be lost without a trace. This is the last U0.2a
migration, so any undo that reaches those tables runs this check first.
On an empty database (development, CI, a rehearsal) undo still works.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# Tables whose rows are plant data or history. Seeded lists are left out:
# they are always there.
DATA_MODELS = [
    ("plants", "Plant"),
    ("plants", "Sku"),
    ("plants", "PlantStatusChange"),
    ("batches", "Batch"),
    ("events", "Operation"),
    ("events", "Event"),
    ("events", "EventReview"),
    ("core", "AuditLog"),
    ("references", "Vendor"),
]


def refuse_if_data(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    holding = [
        apps.get_model(app, model)._meta.db_table
        for app, model in DATA_MODELS
        if apps.get_model(app, model).objects.exists()
    ]
    if holding:
        raise RuntimeError(
            "Refusing to undo the Cucumber schema: these tables hold data, and "
            f"undoing would drop them: {', '.join(holding)}. Restore a backup "
            "or write a forward migration instead."
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0003_app_grants")]

    operations = [migrations.RunPython(migrations.RunPython.noop, refuse_if_data)]
