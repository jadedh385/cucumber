"""No genus may be called PLT, BAT or EVT (U0.8 design §3.2, §5.4, AC5a).

Those three start other IDs, so a typed ID could otherwise read as an SKU.
The three seeded genera pass. Undo drops the check.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0004_reason_lists"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="genus",
            constraint=models.CheckConstraint(
                condition=models.Q(("code__in", ["PLT", "BAT", "EVT"]), _negated=True),
                name="genera_code_not_id_prefix",
            ),
        ),
    ]
