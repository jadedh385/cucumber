"""Plants, the SKU register and plant status history (U0.2 design §2.2).

Single-row rules are check constraints here. The static-SKU trigger and the
"SKU issued to this plant" two-column link are added in migration 0002.
"""

from django.conf import settings
from django.db import models
from django.db.models import (
    CheckConstraint,
    F,
    Func,
    Q,
    UniqueConstraint,
    Value,
)
from django.db.models.functions import Coalesce, Left, Lower, Trim
from django.db.models.lookups import Exact, Regex

from cucumber.core.expressions import TransactionNow
from cucumber.ids.formats import SKU_PATTERN
from cucumber.references.models import Genus, Vendor


def regexp_replace(text: Func | F, pattern: str, replacement: str) -> Func:
    return Func(
        text, Value(pattern), Value(replacement), Value("g"), function="regexp_replace"
    )


# Q6: the name without quote marks, spaces collapsed, lower case. So
# 'Pink Princess', pink princess and Pink  Princess are the same name.
NAME_KEY = Lower(
    Trim(regexp_replace(regexp_replace(F("full_name"), "['\"‘’“”]", ""), r"\s+", " "))
)

IS_PURCHASE = Exact(
    Coalesce(F("source"), Value(""), output_field=models.TextField()), Value("purchase")
)


class PlantStatus(models.TextChoices):
    CANDIDATE = "candidate"
    COLLECTION = "collection"
    PORTFOLIO = "portfolio"
    RETIRED = "retired"
    VOIDED = "voided"


class PlantSource(models.TextChoices):
    PURCHASE = "purchase"
    GIFT = "gift"
    PROPAGATED = "propagated"
    UNKNOWN = "unknown"


class Plant(models.Model):
    genus = models.ForeignKey(
        Genus, on_delete=models.PROTECT, db_column="genus_code", related_name="plants"
    )
    full_name = models.TextField()
    name_key = models.GeneratedField(
        expression=NAME_KEY, output_field=models.TextField(), db_persist=True
    )
    sku = models.ForeignKey(
        "Sku",
        on_delete=models.PROTECT,
        null=True,
        db_column="sku",
        related_name="+",
    )
    status = models.TextField(choices=PlantStatus.choices)
    source = models.TextField(choices=PlantSource.choices, null=True)
    source_note = models.TextField(null=True)
    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT, null=True, related_name="plants"
    )
    zoho_ref = models.TextField(null=True)  # Admin-only (U1.9)
    min_saleable_qty = models.IntegerField(null=True)  # T-2
    notes = models.TextField(db_default="")
    created_at = models.DateTimeField(db_default=TransactionNow())
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="created_by",
        related_name="+",
    )

    class Meta:
        db_table = "plants"
        constraints = [
            CheckConstraint(
                condition=Q(status__in=PlantStatus.values), name="plant_status_valid"
            ),
            CheckConstraint(
                condition=~Q(status="portfolio") | Q(sku__isnull=False),
                name="plant_portfolio_needs_sku",
            ),
            CheckConstraint(
                condition=Q(sku__isnull=True) | Q(Regex(F("sku"), SKU_PATTERN)),
                name="plant_sku_format",
            ),
            CheckConstraint(
                condition=Q(sku__isnull=True) | Q(Exact(Left(F("sku"), 3), F("genus"))),
                name="plant_sku_matches_genus",
            ),
            CheckConstraint(
                condition=Q(source__isnull=True) | Q(source__in=PlantSource.values),
                name="plant_source_valid",
            ),
            CheckConstraint(
                condition=Q(status="candidate") | Q(source__isnull=False),
                name="plant_source_required",
            ),
            CheckConstraint(
                condition=~Q(status="portfolio")
                | ~Q(IS_PURCHASE)
                | Q(vendor__isnull=False, zoho_ref__isnull=False),
                name="plant_portfolio_needs_zoho_link",
            ),
            CheckConstraint(
                condition=Q(IS_PURCHASE)
                | Q(vendor__isnull=True, zoho_ref__isnull=True),
                name="plant_vendor_only_if_purchased",
            ),
            CheckConstraint(
                condition=Q(min_saleable_qty__isnull=True) | Q(min_saleable_qty__gte=1),
                name="plant_min_saleable_positive",
            ),
            CheckConstraint(
                condition=~Q(Exact(Trim(F("full_name")), Value("")))
                & ~Q(full_name__contains="?"),
                name="plant_name_valid",
            ),
            UniqueConstraint(
                fields=["genus", "name_key"],
                condition=~Q(status="voided"),
                name="plant_name_unique_in_genus",
            ),
            UniqueConstraint(fields=["sku"], name="plant_sku_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.genus_id} {self.full_name}"


class Sku(models.Model):
    """Every SKU ever issued. Insert-only, so an SKU is never issued twice (Q1).

    A plant's former SKUs are its rows here other than its current one.
    """

    sku = models.TextField(primary_key=True)
    plant = models.ForeignKey(Plant, on_delete=models.PROTECT, related_name="skus")
    genus = models.ForeignKey(
        Genus, on_delete=models.PROTECT, db_column="genus_code", related_name="+"
    )
    assigned_at = models.DateTimeField(db_default=TransactionNow())
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="assigned_by",
        related_name="+",
    )

    class Meta:
        db_table = "skus"
        constraints = [
            CheckConstraint(
                condition=Q(Exact(Left(F("sku"), 3), F("genus"))),
                name="skus_prefix_matches_genus",
            ),
            # Target of the plants (sku, id) link: an SKU belongs to one plant.
            UniqueConstraint(fields=["sku", "plant"], name="skus_sku_plant_unique"),
        ]

    def __str__(self) -> str:
        return self.sku


class PlantStatusChange(models.Model):
    """Insert-only history of status changes; the latest gives "promoted by / at"."""

    plant = models.ForeignKey(
        Plant, on_delete=models.PROTECT, related_name="status_changes"
    )
    from_status = models.TextField()
    to_status = models.TextField()
    sku_assigned = models.TextField(null=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="changed_by",
        related_name="+",
    )
    changed_at = models.DateTimeField(db_default=TransactionNow())
    reason = models.TextField(null=True)

    class Meta:
        db_table = "plant_status_changes"

    def __str__(self) -> str:
        return f"{self.plant_id}: {self.from_status} → {self.to_status}"
