"""At most one role per account, kept by the database (U0.6 design §6.2, §8).

Every group is a role (Owner's answer to Q1), so a unique index on
`auth_user_groups (user_id)` is the whole rule. Before it is added,
`refuse_bad_accounts` names any account in more than one group, any account
in a group that isn't a role (G4 M1), and any account whose user name isn't
its own NFKC email key (AC19: it couldn't log in), instead of a raw index
error on a server.
"""

import unicodedata

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import Count

ONE_ROLE = "auth_user_one_role"
# The four roles' group names (permissions.Role); a migration doesn't import app code.
ROLE_NAMES = ("admin", "supervisor", "tech", "read_only")

ADD = f"CREATE UNIQUE INDEX {ONE_ROLE} ON auth_user_groups (user_id);"
DROP = f"DROP INDEX {ONE_ROLE};"


def email_key(text: str) -> str:
    """services.email_key; a migration doesn't import app code."""
    return unicodedata.normalize("NFKC", text).strip().lower()


def refuse_bad_accounts(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Stop with a readable list of accounts the new rules would break."""
    user_model = apps.get_model("auth", "User")
    with_two = list(
        user_model.objects.annotate(roles=Count("groups"))
        .filter(roles__gt=1)
        .order_by("username")
        .values_list("username", flat=True)
    )
    unmatched = [
        name
        for name in user_model.objects.order_by("username").values_list(
            "username", flat=True
        )
        if name != email_key(name)
    ]
    not_a_role = [
        f"{name} ({group})"
        for name, group in user_model.objects.exclude(groups=None)
        .exclude(groups__name__in=ROLE_NAMES)
        .order_by("username", "groups__name")
        .values_list("username", "groups__name")
    ]
    problems = []
    if not_a_role:
        problems.append(
            "These accounts are in a group that isn't one of the four roles;"
            " give each a role instead: " + ", ".join(not_a_role)
        )
    if with_two:
        problems.append(
            "These accounts have more than one role; keep one for each: "
            + ", ".join(with_two)
        )
    if unmatched:
        problems.append(
            "These accounts have a user name that isn't its own normalised"
            " email (they couldn't log in); fix each: " + ", ".join(unmatched)
        )
    if problems:
        raise RuntimeError(" ".join(problems) + " Then migrate again.")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_roles")]

    operations = [
        migrations.RunPython(refuse_bad_accounts, migrations.RunPython.noop),
        migrations.RunSQL(ADD, DROP),
    ]
