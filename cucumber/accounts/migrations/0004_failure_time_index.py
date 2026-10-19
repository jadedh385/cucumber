"""An index on the failure time alone, for the day-old clean-up (G4 M4)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_auth_user_rules"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="loginfailure",
            index=models.Index(fields=["at"], name="login_failure_at"),
        ),
    ]
