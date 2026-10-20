"""The audit trail's table (U0.2 design §2.7; written by the database, U0.7 §4)."""

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Index, Q

from cucumber.core.expressions import TransactionNow
from cucumber.references.models import Reason

# U0.7 design §5.3, §5.4: a trigger's row, a noticed TRUNCATE, or one of the
# two rows a service writes itself.
ACTIONS = ("insert", "update", "delete", "truncate", "lock_lifted", "guards_accepted")


class AuditLog(models.Model):
    """One change to plants, batches, reference lists, vendors, accounts,
    roles or flags (U0.7 AC4).

    Insert-only. The audit triggers write it; `audit_log_stamp` sets `at` and
    `db_user` whatever the insert says (review M3). Events and reviews need
    no audit rows: they are their own record.
    """

    # Empty only on a `truncate` row (design §4.4).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    at = models.DateTimeField(db_default=TransactionNow())
    table_name = models.TextField()
    row_pk = models.TextField()
    action = models.TextField()
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    reason = models.ForeignKey(
        Reason,
        on_delete=models.PROTECT,
        null=True,
        db_column="reason_code",
        related_name="+",
    )
    note = models.TextField(null=True)
    # How the change came in: app, a command, login, migration, sql as <role>.
    via = models.TextField()
    # The database login that wrote the row; `audit_log_stamp` sets it.
    db_user = models.TextField(default="")

    class Meta:
        db_table = "audit_log"
        constraints = [
            CheckConstraint(
                condition=Q(actor__isnull=False) | Q(action="truncate"),
                name="audit_log_actor_required",
            ),
            CheckConstraint(
                condition=Q(action__in=ACTIONS), name="audit_log_action_valid"
            ),
        ]
        indexes = [
            Index(fields=["table_name", "row_pk", "at"], name="audit_log_row_at"),
            Index(fields=["actor", "at"], name="audit_log_actor_at"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.table_name} {self.row_pk}"
