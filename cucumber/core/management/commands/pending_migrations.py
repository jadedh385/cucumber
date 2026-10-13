"""`manage.py pending_migrations`: how this version and the database differ.

Prints one line of JSON for the deploy command (U0.4a design §6.2):

    {"pending": ["core.0005_flag_grants"], "unknown": []}

`pending`: migrations this version has that the database hasn't run yet.
`unknown`: migrations the database has run that this version doesn't have
(it is older than the database, design §6.3).
"""

import json
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "Print, as JSON, the migrations still to run and those not known here."

    def handle(self, *args: Any, **options: Any) -> None:
        loader = MigrationLoader(connection)
        known = set(loader.disk_migrations)
        applied = set(loader.applied_migrations)
        report = {
            "pending": [f"{app}.{name}" for app, name in sorted(known - applied)],
            "unknown": [f"{app}.{name}" for app, name in sorted(applied - known)],
        }
        self.stdout.write(json.dumps(report))
