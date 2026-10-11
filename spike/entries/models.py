from django.conf import settings
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone


class Entry(models.Model):
    """One piece of logged work. Insert-only: the database refuses changes."""

    class Action(models.TextChoices):
        SUBCULTURE = "subculture", "Subculture"
        COUNT = "count", "Count"
        LOSS = "loss", "Loss"

    batch_code = models.CharField("Batch", max_length=20)
    action = models.CharField(max_length=20, choices=Action.choices)
    quantity = models.PositiveIntegerField()
    occurred_on = models.DateField("Date", default=timezone.localdate)
    note = models.TextField(blank=True, default="")
    recorded_at = models.DateTimeField(db_default=Now(), editable=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False
    )

    class Meta:
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="entry_quantity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.batch_code} · {self.action} · {self.quantity}"
