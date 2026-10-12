"""Batches: groups of plants tracked together (U0.2 design §2.3).

`live_count`, `stage`, `quarantined` and open/closed are a projection of the
batch's events, kept by the event services (U0.2b); the checks here reject a
bad result even if a service has a bug. The same-plant parent link is added
in migration 0002.
"""

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint

from cucumber.core.expressions import TransactionNow
from cucumber.plants.models import Plant
from cucumber.references.models import Location, Stage


def status_matches_stamp(status: str, stamp: str) -> Q:
    """`(status = <status>) = (<stamp> IS NOT NULL)`."""
    return Q(status=status, **{f"{stamp}__isnull": False}) | (
        ~Q(status=status) & Q(**{f"{stamp}__isnull": True})
    )


class BatchOrigin(models.TextChoices):
    INTAKE = "intake"
    SUBCULTURE = "subculture"
    SPLIT = "split"
    QUARANTINE = "quarantine"
    TRANSFER = "transfer"


class BatchStatus(models.TextChoices):
    OPEN = "open"
    CLOSED = "closed"
    VOIDED = "voided"


class Batch(models.Model):
    Origin = BatchOrigin

    Status = BatchStatus

    plant = models.ForeignKey(Plant, on_delete=models.PROTECT, related_name="batches")
    plant_seq = models.IntegerField()  # the Bnnn in PHL001 · B003 (U0.8)
    parent_batch = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, related_name="children"
    )
    origin = models.TextField(choices=Origin.choices)
    created_operation_id = models.UUIDField()  # Q8: found by an operation void
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, db_column="location_code", related_name="+"
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.PROTECT,
        null=True,
        db_column="stage_code",
        related_name="+",
    )
    quarantined = models.BooleanField(db_default=False)
    status = models.TextField(choices=Status.choices, db_default=Status.OPEN)
    live_count = models.IntegerField(db_default=0)
    created_at = models.DateTimeField(db_default=TransactionNow())
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="created_by",
        related_name="+",
    )
    closed_at = models.DateTimeField(null=True)
    voided_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "batches"
        verbose_name_plural = "batches"
        constraints = [
            CheckConstraint(
                condition=Q(origin__in=BatchOrigin.values), name="batch_origin_valid"
            ),
            CheckConstraint(
                condition=Q(status__in=BatchStatus.values), name="batch_status_valid"
            ),
            CheckConstraint(  # rule 5
                condition=Q(origin="intake") | Q(parent_batch__isnull=False),
                name="batch_needs_parent",
            ),
            CheckConstraint(
                condition=Q(parent_batch__isnull=True) | ~Q(parent_batch=F("id")),
                name="batch_not_own_parent",
            ),
            CheckConstraint(  # rule 6
                condition=~Q(location=Location.LAB) | Q(stage__isnull=False),
                name="batch_lab_needs_stage",
            ),
            CheckConstraint(  # rule 7
                condition=Q(live_count__gte=0), name="batch_count_not_negative"
            ),
            CheckConstraint(  # rule 9, Q7
                condition=Q(status="open") | Q(live_count=0),
                name="batch_closed_needs_zero",
            ),
            CheckConstraint(
                condition=status_matches_stamp("closed", "closed_at"),
                name="batch_closed_at_matches",
            ),
            CheckConstraint(
                condition=status_matches_stamp("voided", "voided_at"),
                name="batch_voided_at_matches",
            ),
            CheckConstraint(  # D-02
                condition=Q(quarantined=False) | Q(origin="quarantine"),
                name="batch_quarantine_origin",
            ),
            UniqueConstraint(
                fields=["plant", "plant_seq"], name="batch_plant_seq_unique"
            ),
            # Target of the (parent_batch_id, plant_id) same-plant link.
            UniqueConstraint(fields=["id", "plant"], name="batch_id_plant_unique"),
        ]

    def __str__(self) -> str:
        return f"Batch {self.pk} of plant {self.plant_id}"
