"""Refusals: why a save was turned down, by rule name (U0.2 design §7.1).

Database refusals and service guards both carry a stable rule name. The
service looks the name up in design §7.1 for the message staff see.
"""

from collections.abc import Sequence

# Shown for every rule marked "Internal" in design §7.1, and any unknown name.
INTERNAL_MESSAGE = "Something went wrong; nothing was saved. Please tell the Admin."


class Refused(Exception):
    """A save was refused; nothing was written.

    `rule` is the §7.1 name. `event_ids` lists the events the refusal is
    about, when there are any (e.g. the later events that block a void).
    """

    def __init__(self, rule: str, message: str, event_ids: Sequence[int] = ()) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule
        self.message = message
        self.event_ids = tuple(event_ids)


def message_for(rule: str) -> str:
    """The message staff see for `rule` (design §7.1); Internal if not listed."""
    raise NotImplementedError("U0.2b G3")
