"""Rules for the core app. Views call these; they never hold rules themselves."""
import os

import logging

from django.db import DatabaseError
from django.db.backends.base.base import BaseDatabaseWrapper

logger = logging.getLogger(__name__)


def database_is_reachable(database: BaseDatabaseWrapper) -> bool:
    """True when a trivial query against `database` succeeds.

    A failure is logged with its details (for the server log) and reported as
    False, so the health page can answer 503 instead of crashing.
    """
    try:
        with database.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("Health check: database unreachable")
        return False
    return True
