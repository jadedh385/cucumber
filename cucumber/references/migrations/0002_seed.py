"""Seed the reference lists (U0.2 design §2.1)."""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# code, sort order (None: reserved, inactive)
STAGES = [
    ("P0", 1), ("P1", 2), ("P2", 3), ("A1", 4), ("P4", 5),
    ("P3", None), ("T1", None), ("C0", None),
]  # fmt: skip
LOCATIONS = [("lab", "Lab"), ("nursery", "Nursery")]  # D-14
MEDIA_CODES = ["M001", "M002", "M003", "M004", "G001", "G002", "R001"]
GENERA = [("HYA", "Hoya"), ("PHL", "Philodendron"), ("ALC", "Alocasia")]
REASONS = {
    "void": ["Duplicate entry", "Wrong batch", "Wrong plant", "Test entry", "Other"],
    "correction": [
        "Wrong quantity", "Wrong media code", "Wrong stage", "Wrong date", "Other",
    ],
    "loss": [
        "Failed acclimatization", "Pest", "Rot", "Damage", "Unknown", "Other",
    ],
}  # fmt: skip


def reason_code(applies_to: str, label: str) -> str:
    """`void_wrong_batch`: unique across the lists, which share labels like Other."""
    return f"{applies_to}_{label.lower().replace(' ', '_')}"


def seed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    get = apps.get_model
    get("references", "Stage").objects.bulk_create(
        get("references", "Stage")(
            code=code, label=code, sort_order=order, active=order is not None
        )
        for code, order in STAGES
    )
    get("references", "Location").objects.bulk_create(
        get("references", "Location")(code=code, label=label, active=True)
        for code, label in LOCATIONS
    )
    get("references", "MediaCode").objects.bulk_create(
        get("references", "MediaCode")(code=code, label=code, active=True)
        for code in MEDIA_CODES
    )
    get("references", "Genus").objects.bulk_create(
        get("references", "Genus")(code=code, name=name, active=True)
        for code, name in GENERA
    )
    get("references", "Reason").objects.bulk_create(
        get("references", "Reason")(
            code=reason_code(applies_to, label),
            label=label,
            applies_to=applies_to,
            active=True,
        )
        for applies_to, labels in REASONS.items()
        for label in labels
    )


def unseed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Remove only the seeded rows; anything the Admin added stays.

    Runs only after core 0004 has checked there is no plant data, and after
    the no-delete triggers (0003) are gone.
    """
    get = apps.get_model
    reason_codes = [
        reason_code(applies_to, label)
        for applies_to, labels in REASONS.items()
        for label in labels
    ]
    get("references", "Reason").objects.filter(code__in=reason_codes).delete()
    get("references", "Genus").objects.filter(code__in=[c for c, _ in GENERA]).delete()
    get("references", "MediaCode").objects.filter(code__in=MEDIA_CODES).delete()
    get("references", "Location").objects.filter(
        code__in=[c for c, _ in LOCATIONS]
    ).delete()
    get("references", "Stage").objects.filter(code__in=[c for c, _ in STAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [("references", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
