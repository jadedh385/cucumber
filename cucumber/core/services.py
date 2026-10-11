"""Rules for the core app. Views call these; they never hold rules themselves."""

from django.db.backends.base.base import BaseDatabaseWrapper


def database_is_reachable(database: BaseDatabaseWrapper) -> bool:
    """True when a trivial query against `database` succeeds."""
    raise NotImplementedError("U0.3 G3")
