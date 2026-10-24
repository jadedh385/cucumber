"""An SKU grows past 3 digits when it needs to (U0.8 design §2, §5.2, AC4).

- `plant_sku_format` is put back with the new pattern: 3 or more digits,
  with no needless leading zero (`PHL999`, then `PHL1000`).
- `skus_sku_format` is new: the same pattern on the SKU register, which
  had no format check before.

The pattern is written out here, as Django writes it; changing
`ids.formats.SKU_PATTERN` needs a new migration. The old pattern allowed
`XXX000`, so the migration first names every SKU the new one refuses
(review L3). Undo puts the 3-digit check back, which is refused while a
4-digit SKU exists: the older code couldn't read it (§5.5). Both ways wait
at most 5 s for the lock on `plants`, as core 0007 does.
"""

import django.db.models.lookups
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

SKU_PATTERN = "^[A-Z]{3}(?!000)(?:[0-9]{3}|[1-9][0-9]{3,})$"
# A check locks `plants` and scans it: give up rather than stall the pages
# behind a slow request (U0.8 review M4), forward and undo.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s';"


def refuse_skus_that_dont_fit(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Stop with the SKUs named, not with a bare constraint error."""
    # Every `plants.sku` is a row in `skus` (the foreign key), so reading the
    # register finds every SKU in either table.
    skus = apps.get_model("plants", "Sku").objects
    unfit = skus.exclude(sku__regex=SKU_PATTERN).values_list("sku", flat=True)
    if unfit:
        raise RuntimeError(
            "These SKUs don't fit the new SKU rule (3 capital letters and 3 or"
            f" more digits, not 000): {', '.join(sorted(unfit))}. Correct them"
            " before running this migration again."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("plants", "0002_rules"),
        ("references", "0005_genus_not_id_prefix"),
    ]

    operations = [
        migrations.RunSQL(LOCK_TIMEOUT, migrations.RunSQL.noop),
        migrations.RunPython(refuse_skus_that_dont_fit, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="plant",
            name="plant_sku_format",
        ),
        migrations.AddConstraint(
            model_name="plant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sku__isnull", True),
                    django.db.models.lookups.Regex(models.F("sku"), SKU_PATTERN),
                    _connector="OR",
                ),
                name="plant_sku_format",
            ),
        ),
        migrations.AddConstraint(
            model_name="sku",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    django.db.models.lookups.Regex(models.F("sku"), SKU_PATTERN)
                ),
                name="skus_sku_format",
            ),
        ),
        # Last, so the undo sets it before it changes anything.
        migrations.RunSQL(migrations.RunSQL.noop, LOCK_TIMEOUT),
    ]
