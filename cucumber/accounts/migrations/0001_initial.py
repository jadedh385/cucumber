"""The lock and change-due tables, and what the app user may do with them
(U0.5 design §3.1, §3.2).

U0.2a's default privileges give every new table SELECT, INSERT to
`cucumber_app`. These two also need DELETE (a good login clears the count, a
chosen password clears the mark), but never UPDATE: a row is added or
removed, never edited.
"""

import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models

# Table names are this constant, never input.
TABLES = "accounts_login_failure, accounts_password_change_due"
GRANT = f"GRANT DELETE ON {TABLES} TO cucumber_app;"
REVOKE = f"REVOKE DELETE ON {TABLES} FROM cucumber_app;"


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0003_app_grants"),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordChangeDue",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "since",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now()
                    ),
                ),
            ],
            options={
                "db_table": "accounts_password_change_due",
            },
        ),
        migrations.CreateModel(
            name="LoginFailure",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email_key", models.CharField(max_length=150)),
                ("address", models.GenericIPAddressField(null=True)),
                (
                    "at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now()
                    ),
                ),
            ],
            options={
                "db_table": "accounts_login_failure",
                "indexes": [
                    models.Index(
                        fields=["email_key", "at"], name="login_failure_email_at"
                    ),
                    models.Index(
                        fields=["address", "at"], name="login_failure_address_at"
                    ),
                ],
            },
        ),
        migrations.RunSQL(GRANT, REVOKE),
    ]
