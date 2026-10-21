"""The System account, and accounts that stay off (U0.7 design §5.2).

- **System** (`system@cucumber.invalid`): the person SSH commands and data
  migrations change things as (AC6). Inactive, an unusable password, no
  role. `.invalid` can never be a real address, so it passes U0.5's
  `auth_user_username_is_email` and can't clash with staff.
- `auth_user_anonymised_stays_off`: an anonymised account
  (`former-staff-<id>@cucumber.invalid`) can never be switched back on, even
  by raw SQL (AC13).
- `auth_user_system_stays_off`: the same for System.

Before adding them, `refuse_invalid_emails` names any account already on the
reserved domain, instead of a raw constraint error on a server. Undo refuses
once an audit row names System.
"""

from django.apps.registry import Apps
from django.contrib.auth.hashers import make_password
from django.db import connection, migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import Q

# core.audit.SYSTEM_USERNAME; a migration doesn't import app code.
SYSTEM_USERNAME = "system@cucumber.invalid"
RESERVED_DOMAIN = "@cucumber.invalid"

ANONYMISED_STAYS_OFF = "auth_user_anonymised_stays_off"
SYSTEM_STAYS_OFF = "auth_user_system_stays_off"

ADD = f"""
ALTER TABLE auth_user
  ADD CONSTRAINT {ANONYMISED_STAYS_OFF}
    CHECK (NOT (username LIKE 'former-staff-%@cucumber.invalid' AND is_active)),
  ADD CONSTRAINT {SYSTEM_STAYS_OFF}
    CHECK (NOT (username = '{SYSTEM_USERNAME}' AND is_active));
"""
DROP = f"""
ALTER TABLE auth_user
  DROP CONSTRAINT {ANONYMISED_STAYS_OFF},
  DROP CONSTRAINT {SYSTEM_STAYS_OFF};
"""


def refuse_invalid_emails(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Stop with a readable list of accounts already on the reserved domain."""
    user_model = apps.get_model("auth", "User")
    names = list(
        user_model.objects.filter(
            Q(username__iendswith=RESERVED_DOMAIN) | Q(email__iendswith=RESERVED_DOMAIN)
        )
        .exclude(username=SYSTEM_USERNAME)
        .order_by("username")
        .values_list("username", flat=True)
    )
    if names:
        raise RuntimeError(
            f"These accounts use {RESERVED_DOMAIN}, which U0.7 keeps for the"
            " System account and anonymised staff. Give each a real email,"
            f" then migrate again: {', '.join(names)}"
        )


def add_system_account(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    apps.get_model("auth", "User").objects.create(
        username=SYSTEM_USERNAME,
        email=SYSTEM_USERNAME,
        first_name="System",
        is_active=False,
        password=make_password(None),  # unusable: "!" and random letters
    )


def remove_system_account(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Undo: only while no audit row names System (design §5.2)."""
    database = schema_editor.connection if schema_editor else connection
    with database.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM audit_log a JOIN auth_user u ON u.id = a.actor_id"
            " WHERE u.username = %s",
            [SYSTEM_USERNAME],
        )
        row = cursor.fetchone()
    if row is not None and row[0]:
        raise RuntimeError(
            f"Refusing to remove the System account: {row[0]} audit rows name"
            " it. Restore the copy from before the release instead."
        )
    apps.get_model("auth", "User").objects.filter(username=SYSTEM_USERNAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_one_role"),
        ("core", "0001_initial"),  # audit_log, read by the undo
    ]

    operations = [
        migrations.RunPython(refuse_invalid_emails, migrations.RunPython.noop),
        migrations.RunPython(add_system_account, remove_system_account),
        migrations.RunSQL(ADD, DROP),
    ]
