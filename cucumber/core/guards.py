"""Are the database's protections on? (U0.7 design §8, AC15).

`GUARDS` lists every protection: the append-only, no-delete, reason and
audit triggers, their functions, `cucumber_app`'s grants and the app role
itself. Each entry names the migration that adds it, and is skipped until
that migration has run. `check()` compares the database with the list;
`cucumber_check_guards` prints what it finds, and the deploy stops on any
failure (steps 3b and 5b).
"""

from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    TRIGGER = "trigger"
    FUNCTION = "function"
    GRANT = "grant"
    APP_ROLE = "app role"
    TRUNCATE = "truncate"


@dataclass(frozen=True)
class Guard:
    """One protection: its kind, its name (a trigger, a function, a table)."""

    kind: Kind
    name: str
    migration: str  # "app_label.0006_name": skipped until it has run


@dataclass(frozen=True)
class Report:
    """What `check()` found: one plain line per failure (design §8.1)."""

    checked: int
    failures: tuple[str, ...]


# Filled at G3, with the migrations that add the U0.7 protections.
GUARDS: tuple[Guard, ...] = ()


def check() -> Report:
    """Every protection in `GUARDS` whose migration has run, checked (§8.1)."""
    raise NotImplementedError("U0.7 G3")


def accept_truncates(note: str) -> list[str]:
    """Accept the noticed TRUNCATEs (§8.2); returns what was accepted, as lines."""
    raise NotImplementedError("U0.7 G3")
