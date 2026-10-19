"""Two rules on `auth_user` (U0.5 design §3.4, AC31).

- `auth_user_no_superuser`: no account is ever a superuser or staff. Admin is
  a group, and Django's admin site isn't installed.
- `auth_user_username_is_email`: the user name is the email, trimmed and in
  lowercase, so two accounts can't share an email even outside the services.
  It must look like an email (something@something), so a U0.3-style name
  such as `gene` is refused too.

Before adding them, `refuse_bad_accounts` names every account that would
break either rule, instead of a raw constraint error on a server.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim

NO_SUPERUSER = "auth_user_no_superuser"
USERNAME_IS_EMAIL = "auth_user_username_is_email"

ADD = f"""
ALTER TABLE auth_user
  ADD CONSTRAINT {NO_SUPERUSER} CHECK (NOT is_superuser AND NOT is_staff),
  ADD CONSTRAINT {USERNAME_IS_EMAIL}
    CHECK (
      username = lower(btrim(username))
      AND email = username
      AND username LIKE '%_@_%'
    );
"""
DROP = f"""
ALTER TABLE auth_user
  DROP CONSTRAINT {NO_SUPERUSER},
  DROP CONSTRAINT {USERNAME_IS_EMAIL};
"""


def refuse_bad_accounts(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Stop with a readable list of accounts the two rules would refuse."""
    user_model = apps.get_model("auth", "User")
    bad = (
        user_model.objects.annotate(clean=Lower(Trim("username")))
        .filter(
            Q(is_superuser=True)
            | Q(is_staff=True)
            | ~Q(username=F("clean"))
            | ~Q(email=F("username"))
            | ~Q(username__regex=r".@.")
        )
        .order_by("username")
        .values_list("username", flat=True)
    )
    names = list(bad)
    if names:
        raise RuntimeError(
            "These accounts break U0.5's rules (no superuser or staff flag; the "
            "user name must be the lowercase email, the same as the email). "
            f"Fix them first, then migrate again: {', '.join(names)}"
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_admin_group")]

    operations = [
        migrations.RunPython(refuse_bad_accounts, migrations.RunPython.noop),
        migrations.RunSQL(ADD, DROP),
    ]
