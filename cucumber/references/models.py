"""Reference lists and vendors (U0.2 design §2.1, §2.6).

Codes are the primary keys, are never renamed and are never deleted: an item
that is no longer used is deactivated. The database enforces both
(`<table>_code_rename`, `<table>_no_delete`, migration 0003).
"""

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Length, Trim
from django.db.models.lookups import Exact, LessThanOrEqual

from cucumber.references.lists import (
    CONTAINER_TYPE_PATTERN,
    GENUS_CODE_PATTERN,
    LABEL_MAX_LENGTH,
    MEDIA_CODE_PATTERN,
)


def label_valid(column: str, name: str) -> CheckConstraint:
    """No space at either end, not blank, at most 100 characters (U0.9 §2.1).

    `label = btrim(label) AND label <> '' AND char_length(label) <= 100`.
    """
    return CheckConstraint(
        condition=Q(Exact(F(column), Trim(column)))
        & ~Q(**{column: ""})
        & Q(LessThanOrEqual(Length(column), LABEL_MAX_LENGTH)),
        name=name,
    )


class Genus(models.Model):
    """A plant genus; its code starts every SKU (`PHL` in `PHL001`)."""

    code = models.CharField(primary_key=True, max_length=3)
    name = models.TextField()
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "genera"
        verbose_name_plural = "genera"
        constraints = [
            CheckConstraint(
                condition=Q(code__regex=GENUS_CODE_PATTERN), name="genera_code_format"
            ),
            # A typed ID never reads as an SKU (U0.8 AC5a).
            CheckConstraint(
                condition=~Q(code__in=["PLT", "BAT", "EVT"]),
                name="genera_code_not_id_prefix",
            ),
            UniqueConstraint(fields=["name"], name="genera_name_unique"),
            label_valid("name", "genera_name_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Stage(models.Model):
    """A culture stage. Active stages are shown in `sort_order` (D-06)."""

    code = models.TextField(primary_key=True)
    label = models.TextField()
    sort_order = models.IntegerField(null=True)
    default_subculture_days = models.IntegerField(null=True)  # U2.2
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "stages"
        constraints = [
            UniqueConstraint(fields=["sort_order"], name="stages_sort_order_unique"),
            CheckConstraint(
                condition=Q(active=False) | Q(sort_order__isnull=False),
                name="stages_active_needs_sort_order",
            ),
            CheckConstraint(
                condition=Q(default_subculture_days__isnull=True)
                | Q(default_subculture_days__gt=0),
                name="stages_subculture_days_positive",
            ),
            label_valid("label", "stages_label_valid"),
        ]

    def __str__(self) -> str:
        return self.code


class MediaCode(models.Model):
    code = models.TextField(primary_key=True)
    label = models.TextField()
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "media_codes"
        constraints = [
            CheckConstraint(
                condition=Q(code__regex=MEDIA_CODE_PATTERN),
                name="media_codes_code_format",
            ),
            label_valid("label", "media_codes_label_valid"),
        ]

    def __str__(self) -> str:
        return self.code


class Location(models.Model):
    """Where a batch is: the Lab or the Nursery (D-14)."""

    LAB = "lab"
    NURSERY = "nursery"

    code = models.TextField(primary_key=True)
    label = models.TextField()
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "locations"
        constraints = [label_valid("label", "locations_label_valid")]

    def __str__(self) -> str:
        return self.label


class ContainerType(models.Model):
    """What a batch grows in (U0.9 design §2.1). Listed by label: the code is
    only a key, in small letters (`magenta_box`, Q2)."""

    code = models.TextField(primary_key=True)
    label = models.TextField()
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "container_types"
        constraints = [
            CheckConstraint(
                condition=Q(code__regex=CONTAINER_TYPE_PATTERN),
                name="container_types_code_format",
            ),
            label_valid("label", "container_types_label_valid"),
        ]

    def __str__(self) -> str:
        return self.label


class ReasonList(models.TextChoices):
    VOID = "void"
    CORRECTION = "correction"
    LOSS = "loss"
    # U0.7 AC11: switching something off (design §4.2, §5.1).
    RETIRE = "retire"
    ARCHIVE = "archive"
    DEACTIVATE = "deactivate"


class Reason(models.Model):
    """A reason staff pick for a Void, a Correction or a Loss (rule 8, Q4),
    or for retiring, archiving or deactivating something (U0.7 AC11)."""

    code = models.TextField(primary_key=True)
    label = models.TextField()
    applies_to = models.TextField(choices=ReasonList.choices)
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "reasons"
        constraints = [
            CheckConstraint(
                condition=Q(applies_to__in=ReasonList.values),
                name="reasons_applies_to_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.label


class Vendor(models.Model):
    """A seller, copied from Zoho by the sync job only (D-04, U3.2)."""

    zoho_contact_id = models.TextField(primary_key=True)
    name = models.TextField()
    active = models.BooleanField(db_default=True)
    synced_at = models.DateTimeField()

    class Meta:
        db_table = "vendors"

    def __str__(self) -> str:
        return self.name
