"""Operations, events and reviews: the append-only history (U0.2 design §2.4, §2.5, §3).

Events are never updated or deleted; a Void or Correction is a new event
that points at the original. Append-only triggers, the `recorded_at` trigger
and the same-batch links for voids and corrections are in migration 0002.
"""

import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import (
    BaseConstraint,
    CheckConstraint,
    DateField,
    DateTimeField,
    ExpressionWrapper,
    F,
    Func,
    Q,
    UniqueConstraint,
    Value,
)
from django.db.models.functions import Cast
from django.db.models.lookups import GreaterThanOrEqual

from cucumber.batches.models import Batch
from cucumber.core.expressions import TransactionNow
from cucumber.events.projection import Effective, in_order
from cucumber.references.models import MediaCode, Reason, Stage

BANGKOK = "Asia/Bangkok"
ENTRY_WINDOW_DAYS = 7  # Q5: how far back staff may date an entry
CLOCK_ALLOWANCE = timedelta(minutes=5)  # Q5: a phone clock a little ahead


class Operation(models.Model):
    """One user action. Its id comes with the form, so a resend fails (issue #4)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="recorded_by",
        related_name="+",
    )
    recorded_at = models.DateTimeField(db_default=TransactionNow())

    class Meta:
        db_table = "operations"

    def __str__(self) -> str:
        return str(self.id)


class Action(models.TextChoices):
    INTAKE = "intake"
    SUBCULTURE = "subculture"
    STAGE_CHANGE = "stage_change"
    COUNT = "count"
    CONTAMINATION = "contamination"
    SPLIT = "split"
    QUARANTINE = "quarantine"
    RELEASE = "release"
    TRANSFER = "transfer"
    OUT = "out"
    LOSS = "loss"
    CLOSE = "close"
    CORRECTION = "correction"
    VOID = "void"


class EnteredVia(models.TextChoices):
    FORM = "form"
    ASSISTANT = "assistant"  # D-21


NO_UNITS = Q(qty_in=0, qty_out=0)
UNITS_OUT = Q(qty_out__gt=0, qty_in=0)

# What each action's row must look like (design §3). Correction has no shape:
# it restates the original's values.
SHAPES: dict[str, Q] = {
    Action.INTAKE: Q(qty_in__gt=0),
    Action.SUBCULTURE: UNITS_OUT,
    Action.SPLIT: UNITS_OUT,
    Action.CONTAMINATION: UNITS_OUT,
    Action.QUARANTINE: UNITS_OUT,
    Action.OUT: UNITS_OUT,
    Action.LOSS: UNITS_OUT,
    Action.STAGE_CHANGE: NO_UNITS & Q(stage_to__isnull=False),
    Action.COUNT: NO_UNITS & Q(counted_qty__isnull=False),
    Action.RELEASE: NO_UNITS,
    Action.CLOSE: NO_UNITS,
    Action.VOID: NO_UNITS,
    Action.TRANSFER: Q(qty_in__gt=0) | Q(qty_out__gt=0),
}


def only_when(action: str, target: str) -> Q:
    """`(action = <action>) = (<target> IS NOT NULL)`."""
    return Q(action=action, **{f"{target}__isnull": False}) | (
        ~Q(action=action) & Q(**{f"{target}__isnull": True})
    )


def bangkok_date(field: str) -> Cast:
    """`(field AT TIME ZONE 'Asia/Bangkok')::date`: the date the picker shows."""
    local = Func(
        Value(BANGKOK), F(field), function="timezone", output_field=DateTimeField()
    )
    return Cast(local, output_field=DateField())


# Q5, M1: at most 7 calendar days back, in Bangkok dates.
WITHIN_ENTRY_WINDOW = GreaterThanOrEqual(
    bangkok_date("occurred_at"),
    ExpressionWrapper(
        bangkok_date("recorded_at") - Value(ENTRY_WINDOW_DAYS), output_field=DateField()
    ),
)


def shape_constraints() -> list[BaseConstraint]:
    """`event_<action>_shape`: an event of that action must match its shape."""
    return [
        CheckConstraint(
            condition=~Q(action=action) | shape, name=f"event_{action}_shape"
        )
        for action, shape in SHAPES.items()
    ]


def event_constraints() -> list[BaseConstraint]:
    return [
        CheckConstraint(
            condition=Q(action__in=Action.values), name="event_action_valid"
        ),
        CheckConstraint(
            condition=Q(entered_via__in=EnteredVia.values),
            name="event_entered_via_valid",
        ),
        CheckConstraint(  # rule 7
            condition=Q(qty_in__gte=0, qty_out__gte=0), name="event_qty_not_negative"
        ),
        CheckConstraint(
            condition=~Q(qty_in__gt=0, qty_out__gt=0), name="event_qty_one_direction"
        ),
        CheckConstraint(
            condition=Q(counted_qty__isnull=True) | Q(counted_qty__gte=0),
            name="event_counted_not_negative",
        ),
        CheckConstraint(
            condition=only_when(Action.VOID, "voids_event"), name="event_void_target"
        ),
        CheckConstraint(
            condition=only_when(Action.CORRECTION, "corrects_event"),
            name="event_correction_target",
        ),
        CheckConstraint(  # rule 8, Q4
            condition=~Q(action__in=[Action.VOID, Action.CORRECTION, Action.LOSS])
            | Q(reason__isnull=False),
            name="event_reason_required",
        ),
        CheckConstraint(  # Q5
            condition=Q(occurred_at__lte=F("recorded_at") + CLOCK_ALLOWANCE),
            name="event_not_in_future",
        ),
        CheckConstraint(  # Q5: a reviewer's date fix may go further back
            condition=Q(action=Action.CORRECTION) | Q(WITHIN_ENTRY_WINDOW),
            name="event_within_7_days",
        ),
        *shape_constraints(),
        UniqueConstraint(fields=["voids_event"], name="event_void_once"),
        # Target of the same-batch links for voids and corrections.
        UniqueConstraint(fields=["id", "batch"], name="event_id_batch_unique"),
    ]


# The values a Correction restates (design §3.1), as `values()` names them.
CORRECTABLE = (
    "occurred_at",
    "qty_in",
    "qty_out",
    "counted_qty",
    "media_code_id",
    "stage_to_id",
)


def as_effective(original: dict[str, Any], values: dict[str, Any]) -> Effective:
    """The original's id and action with `values` (its own or a correction's)."""
    return Effective(
        id=original["id"],
        action=original["action"],
        occurred_at=values["occurred_at"],
        qty_in=values["qty_in"],
        qty_out=values["qty_out"],
        counted_qty=values["counted_qty"],
        media_code=values["media_code_id"],
        stage_to=values["stage_to_id"],
    )


class EventManager(models.Manager["Event"]):
    def effective_events(self, batch_id: int) -> list[Effective]:
        """The batch's events as they count now, in (`occurred_at`, `id`) order.

        Voided events are left out; each event carries its newest non-voided
        correction's values. Void and correction rows themselves aren't listed.
        The projection, `check_projections` and reports all use this one
        function (design §3.1, architect review M7).
        """
        rows = (
            self.filter(batch_id=batch_id, voided_by__isnull=True)
            .exclude(action=Action.VOID)
            .order_by("id")
            .values("id", "action", "corrects_event_id", *CORRECTABLE)
        )
        originals = []
        newest_fix: dict[int, dict[str, Any]] = {}
        for row in rows:
            if row["action"] == Action.CORRECTION:
                newest_fix[row["corrects_event_id"]] = row  # ascending id: last wins
            else:
                originals.append(row)
        effective = [
            as_effective(row, newest_fix.get(row["id"], row)) for row in originals
        ]
        return in_order(effective)


class Event(models.Model):
    operation = models.ForeignKey(
        Operation, on_delete=models.PROTECT, related_name="events"
    )
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="events")
    action = models.TextField(choices=Action.choices)
    qty_in = models.IntegerField(db_default=0)
    qty_out = models.IntegerField(db_default=0)
    counted_qty = models.IntegerField(null=True)
    media_code = models.ForeignKey(
        MediaCode,
        on_delete=models.PROTECT,
        null=True,
        db_column="media_code",
        related_name="+",
    )
    stage_to = models.ForeignKey(
        Stage,
        on_delete=models.PROTECT,
        null=True,
        db_column="stage_to",
        related_name="+",
    )
    staff = models.ForeignKey(  # who did the work
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_by = models.ForeignKey(  # who saved it
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="recorded_by",
        related_name="+",
    )
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(
        db_default=TransactionNow()
    )  # always now(): trigger
    reason = models.ForeignKey(
        Reason,
        on_delete=models.PROTECT,
        null=True,
        db_column="reason_code",
        related_name="+",
    )
    voids_event = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, related_name="voided_by"
    )
    corrects_event = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, related_name="corrections"
    )
    note = models.TextField(db_default="")
    entered_via = models.TextField(
        choices=EnteredVia.choices, db_default=EnteredVia.FORM
    )

    objects = EventManager()

    class Meta:
        db_table = "events"
        constraints = event_constraints()

    def __str__(self) -> str:
        return f"Event {self.pk}: {self.action}"


class EventReview(models.Model):
    """A "checked" mark on one event (Q3). Insert-only; a fix is a new event."""

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(db_default=TransactionNow())
    note = models.TextField(db_default="")

    class Meta:
        db_table = "event_reviews"
        constraints = [
            UniqueConstraint(fields=["event"], name="event_review_once"),
        ]

    def __str__(self) -> str:
        return f"Review of event {self.event_id}"
