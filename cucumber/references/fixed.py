"""The two lists nobody can change: event actions and count units (U0.9 design §4).

They are in code, not a table: stock sums, the event shapes and the projection
are written against these values. Changing one changes a database check, so
`makemigrations --check` asks for a migration, and that needs its own G0
(U0.9 AC15, AC16). This module imports no app models, so the projection can
import it without a cycle.
"""

from django.db import models


class Action(models.TextChoices):
    """The fourteen event actions. The labels stay Django's own (design §4, M2)."""

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


class CountUnit(models.TextChoices):
    """What a batch's count counts: D-22 as proposed (U0.9 spec Q6)."""

    PLANT = "plant", "Plant"
    VESSEL = "vessel", "Vessel"
    MG = "mg", "mg"
