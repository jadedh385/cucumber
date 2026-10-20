"""The other three role groups: supervisor, tech, read_only (U0.6 design §6.1).

`admin` came with 0002. Undo is refused while anyone holds one of the three,
or a feature flag is on for one: deleting a group would silently take people's
roles (and the flag's group) away, as core 0004 refuses an undo with data.
With neither, the three groups are deleted. `admin` stays (U0.5 §3.3).
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# services.Role; a migration doesn't import app code.
NEW_ROLES = ("supervisor", "tech", "read_only")


def add_roles(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    """Add the groups, or find them again after an undo and re-run."""
    group_model = apps.get_model("auth", "Group")
    for name in NEW_ROLES:
        group_model.objects.get_or_create(name=name)


def remove_roles(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    """Delete the three groups, unless a person or a flag still uses one."""
    user_model = apps.get_model("auth", "User")
    flag_model = apps.get_model("waffle", "Flag")
    holders = user_model.objects.filter(groups__name__in=NEW_ROLES).distinct().count()
    if holders:
        raise RuntimeError(
            f"{holders} account(s) still hold a supervisor, tech or read_only"
            " role. Remove those roles first, then undo this migration."
        )
    flags = list(
        flag_model.objects.filter(groups__name__in=NEW_ROLES)
        .distinct()
        .values_list("name", flat=True)
    )
    if flags:
        raise RuntimeError(
            "These feature flags are on for a role that this undo would delete;"
            f" switch the role off for each flag first: {', '.join(sorted(flags))}"
        )
    apps.get_model("auth", "Group").objects.filter(name__in=NEW_ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_failure_time_index"),
        ("auth", "0001_initial"),
        ("waffle", "0001_initial"),
    ]

    operations = [migrations.RunPython(add_roles, remove_roles)]
