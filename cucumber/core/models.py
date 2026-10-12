"""The audit trail's table (U0.2 design §2.7). How it is written is U0.7."""

from django.conf import settings
from django.db import models

from cucumber.core.expressions import TransactionNow


class AuditLog(models.Model):
    """One insert or update to plants, batches, reference lists or vendors.

    Insert-only. Events and reviews need no audit rows: they are their own record.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    at = models.DateTimeField(db_default=TransactionNow())
    table_name = models.TextField()
    row_pk = models.TextField()
    action = models.TextField()
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    reason = models.TextField(null=True)

    class Meta:
        db_table = "audit_log"

    def __str__(self) -> str:
        return f"{self.action} {self.table_name} {self.row_pk}"
