"""The `admin` group: the Owner's role (U0.5 design §3.3).

Only `admin` for now; U0.6 adds the other roles and the screens to grant
them. Undo leaves the group, because removing it would silently take the
Admin role away from the Owner.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

ADMIN = "admin"  # services.ADMIN; a migration doesn't import app code


def add_admin_group(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    """Add the group, or find it again after an undo and re-run."""
    group_model = apps.get_model("auth", "Group")
    group_model.objects.get_or_create(name=ADMIN)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(add_admin_group, migrations.RunPython.noop)]
