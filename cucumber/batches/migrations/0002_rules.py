"""Batch rules Django can't declare (design §2.3, §4).

- A parent batch belongs to the same plant: `(parent_batch_id, plant_id)` →
  `batches (id, plant_id)`, so lineage stays inside one plant.
- Batches are never deleted (rule 9).
"""

from django.db import migrations

from cucumber.core import db_rules

RULES = [
    db_rules.two_column_link(
        "batch_parent_same_plant",
        "batches",
        "parent_batch_id, plant_id",
        "batches",
        "id, plant_id",
    ),
    db_rules.no_delete("batches"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("batches", "0001_initial"),
        ("core", "0002_protection_functions"),
    ]

    operations = [migrations.RunSQL(rule.forward, rule.reverse) for rule in RULES]
