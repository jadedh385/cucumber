"""The container type list, and the code and label rules (U0.9 design §2.1, §2.2).

- `container_types` is new: a code in small letters (`magenta_box`) and a
  label. Its protection (triggers, grant) is `0007`; its rows are `0008`.
- `media_codes_code_format`: a capital letter, then 2 to 9 capitals or digits.
- A label rule on every list (`<table>_label_valid`; `genera_name_valid` on
  the genus name): no space at either end, not blank, at most 100 characters.

The patterns are written out here, as Django writes them; changing the ones
in `references.lists` needs a new migration. The migration first names every
row the new checks would refuse (U0.8 review L3), and waits at most 5 s for a
lock, both ways. Undo drops the checks and the table, and refuses while the
table has a row: `0008`'s undo removes the seeded ones first (review M5).
"""

import django.db.models.functions.text
import django.db.models.lookups
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

MEDIA_CODE_PATTERN = "^[A-Z][A-Z0-9]{2,9}$"
CONTAINER_TYPE_PATTERN = "^[a-z][a-z0-9_]{1,31}$"
LABEL_MAX_LENGTH = 100
# Each check locks a small table `batches` and `events` point at: give up
# rather than stall behind a slow request (as U0.8's migrations do).
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s';"

# The model, the label column and the check on it, for each existing list.
LABELLED = [
    ("Stage", "label", "stages_label_valid"),
    ("MediaCode", "label", "media_codes_label_valid"),
    ("Location", "label", "locations_label_valid"),
    ("Genus", "name", "genera_name_valid"),
]


def label_valid(column: str) -> models.Q:
    """`label = btrim(label) AND label <> '' AND char_length(label) <= 100`."""
    return models.Q(
        django.db.models.lookups.Exact(
            models.F(column), django.db.models.functions.text.Trim(column)
        ),
        models.Q((column, ""), _negated=True),
        django.db.models.lookups.LessThanOrEqual(
            django.db.models.functions.text.Length(column), LABEL_MAX_LENGTH
        ),
    )


def refuse_rows_that_dont_fit(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Stop with every unfit row named, not with a bare constraint error."""
    media = apps.get_model("references", "MediaCode").objects
    bad_codes = media.exclude(code__regex=MEDIA_CODE_PATTERN)
    unfit = [
        *(f"media code {code}" for code in bad_codes.values_list("code", flat=True)),
        *(
            f"{rule} {code}"
            for model, column, rule in LABELLED
            for code in apps.get_model("references", model)
            .objects.exclude(label_valid(column))
            .values_list("code", flat=True)
        ),
    ]
    if unfit:
        raise RuntimeError(
            "These rows don't fit the new list rules (a media code is a capital"
            " letter and 2 to 9 capitals or digits; a label has no space at"
            " either end, isn't blank and is at most 100 characters):"
            f" {', '.join(sorted(unfit))}. Correct them before running this"
            " migration again."
        )


def refuse_while_container_types_has_rows(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    """Undo never drops a container type the Admin added (Q-B a)."""
    rows = apps.get_model("references", "ContainerType").objects
    codes = list(rows.order_by("code").values_list("code", flat=True))
    if codes:
        raise RuntimeError(
            f"container_types still holds {', '.join(codes)}. Undoing this"
            " migration would drop them: restore the pre-deploy copy instead."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0005_genus_not_id_prefix"),
    ]

    operations = [
        migrations.RunSQL(LOCK_TIMEOUT, migrations.RunSQL.noop),
        migrations.RunPython(refuse_rows_that_dont_fit, migrations.RunPython.noop),
        migrations.CreateModel(
            name="ContainerType",
            fields=[
                ("code", models.TextField(primary_key=True, serialize=False)),
                ("label", models.TextField()),
                ("active", models.BooleanField(db_default=True)),
            ],
            options={
                "db_table": "container_types",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("code__regex", CONTAINER_TYPE_PATTERN)),
                        name="container_types_code_format",
                    ),
                    models.CheckConstraint(
                        condition=label_valid("label"),
                        name="container_types_label_valid",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="mediacode",
            constraint=models.CheckConstraint(
                condition=models.Q(("code__regex", MEDIA_CODE_PATTERN)),
                name="media_codes_code_format",
            ),
        ),
        *(
            migrations.AddConstraint(
                model_name=model.lower(),
                constraint=models.CheckConstraint(
                    condition=label_valid(column), name=rule
                ),
            )
            for model, column, rule in LABELLED
        ),
        # Undo runs these last two first: the timeout, then the refusal,
        # before any check or the table is dropped.
        migrations.RunPython(
            migrations.RunPython.noop, refuse_while_container_types_has_rows
        ),
        migrations.RunSQL(migrations.RunSQL.noop, LOCK_TIMEOUT),
    ]
