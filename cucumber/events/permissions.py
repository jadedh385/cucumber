"""Who may save, void, correct and undo events (U0.6 design §4.2).

Each action an operation can save belongs to one matrix row. Void and
Correction never go through `save_operation`; they have their own services
and the Void tree.
"""

from datetime import timedelta

from cucumber.accounts.permissions import Permission
from cucumber.events.models import Action

# D-07: an Undo is a Void of your own save within this long, by the
# database's clock (the one that stamped `operations.recorded_at`).
UNDO_WINDOW = timedelta(minutes=10)

ACTION_ROWS: dict[str, Permission] = {
    Action.INTAKE: Permission.LOG_WORK,
    Action.SUBCULTURE: Permission.LOG_WORK,
    Action.STAGE_CHANGE: Permission.LOG_WORK,
    Action.COUNT: Permission.LOG_WORK,
    Action.CONTAMINATION: Permission.LOG_WORK,
    Action.TRANSFER: Permission.LOG_WORK,
    Action.OUT: Permission.LOG_WORK,
    Action.SPLIT: Permission.SPLIT_CLOSE_LOSS,
    Action.CLOSE: Permission.SPLIT_CLOSE_LOSS,
    Action.LOSS: Permission.SPLIT_CLOSE_LOSS,
    Action.QUARANTINE: Permission.SPLIT_CLOSE_LOSS,
    Action.RELEASE: Permission.RELEASE_QUARANTINE,
}

# Saved by their own services, never by `save_operation` (event_action_not_here).
NOT_THROUGH_SAVE = frozenset({Action.VOID, Action.CORRECTION})
