"""`manage.py cucumber_check_guards`: are the database's protections on? (AC15).

    cucumber_check_guards                      check; exit 1 if any is off
    cucumber_check_guards --accept "why"       accept the noticed TRUNCATEs

Prints one line per protection that is missing, switched off or changed,
then stops with an error (exit 1); with none, prints `All N protections on.`
The deploy runs it before the copy and after migrating (U0.7 design §8.3).
`--accept` runs as the database owner, through the migrate service (§8.2).
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from cucumber.core import guards


class Command(BaseCommand):
    help = "Check the database's protections are on; --accept a noticed TRUNCATE."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--accept",
            metavar="WHY",
            help="accept the TRUNCATEs noticed so far, saying why",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        note: str | None = options["accept"]
        if note is not None:
            self.accept(note)
            return
        report = guards.check()
        if report.failures:
            for failure in report.failures:
                self.stdout.write(failure)
            raise CommandError(
                f"{len(report.failures)} of the database's protections are not on."
            )
        self.stdout.write(f"All {report.checked} protections on.")

    def accept(self, note: str) -> None:
        try:
            accepted = guards.accept_truncates(note)
        except ValueError as error:
            raise CommandError(str(error)) from None
        if not accepted:
            self.stdout.write("Nothing to accept.")
            return
        self.stdout.write(f"These were truncated: {', '.join(accepted)}")
        self.stdout.write("Accepted. The deploy will go on.")
