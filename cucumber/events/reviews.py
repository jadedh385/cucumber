"""Review rules and the review queue (U0.2 design §2.5, Q3, rule 10).

Who reviews what: Tech events → a Supervisor or the Admin; an event with a
Supervisor on it (did it or saved it) → the Admin only; every Void → the
Admin only. Nobody but the Admin reviews an event they did or saved.
Roles are the Django groups `admin`, `supervisor`, `tech` (design §2.7).

The Admin's own saves are reviewed as they are saved, and a reviewer's
Correction or Void marks the original reviewed; both happen inside the event
services, in the same transaction.
"""

import uuid
from dataclasses import dataclass

from django.contrib.auth.models import User

# Queue flag: an event dated before the batch's latest count (design §3.1).
DATED_BEFORE_COUNT = "dated_before_count"


@dataclass(frozen=True)
class QueueItem:
    """One item in a reviewer's queue: the unreviewed events of one operation."""

    operation_id: uuid.UUID
    event_ids: tuple[int, ...]
    flags: frozenset[str] = frozenset()


def review_queue(reviewer: User) -> list[QueueItem]:
    """The items `reviewer` may review: unreviewed, non-voided events by operation."""
    raise NotImplementedError("U0.2b G3")


def review(reviewer: User, operation_id: uuid.UUID, note: str = "") -> None:
    """Mark every unreviewed event of the operation reviewed by `reviewer`.

    Refused (`review_not_allowed`) if `reviewer` may not review one of them.
    """
    raise NotImplementedError("U0.2b G3")
