"""`manage.py cucumber_check_guards`: are the database's protections on? (AC15).

    cucumber_check_guards                      check; exit 1 if any is off
    cucumber_check_guards --accept "why"       accept the noticed TRUNCATEs

Prints one line per protection that is missing, switched off or changed,
then stops with an error (exit 1); with none, prints `All N protections on.`
The deploy runs it before the copy and after migrating (U0.7 design §8.3).
`--accept` runs as the database owner, through the migrate service (§8.2).
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Check the database's protections are on; --accept a noticed TRUNCATE."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--accept",
            metavar="WHY",
            help="accept the TRUNCATEs noticed so far, saying why",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        raise NotImplementedError("U0.7 G3")
